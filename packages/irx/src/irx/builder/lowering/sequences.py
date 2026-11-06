"""
title: Borrowed numeric view emission from resolved plans and narrow services.
"""

from collections.abc import Callable
from typing import Protocol, runtime_checkable

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import ResolvedSequenceAccess, SemanticInfo
from irx.analysis.types import bit_width, is_unsigned_type
from irx.builder.diagnostics import (
    raise_lowering_error,
    require_semantic_metadata,
)
from irx.builder.runtime.sequence import sequence_view_type
from irx.builder.services.cleanup import CleanupService
from irx.builder.services.conversions import NumericEmission
from irx.builder.services.exceptions import RuntimeGuardService
from irx.builder.services.representations import (
    TypeLowering,
    resolved_type,
    semantic_info,
)
from irx.builder.services.values import ValueEmission
from irx.builder.state import CleanupAction
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@private
@runtime_checkable
class LiteralListStorage(Protocol):
    """
    title: The literal-list storage operation required by borrowed views.
    """

    def __call__(
        self,
        *,
        base: astx.LiteralList,
        literal_value: ir.Value,
    ) -> ir.Value:
        """
        title: >-
          Provide call-scoped literal storage without exposing a list visitor.
        parameters:
          base:
            type: astx.LiteralList
          literal_value:
            type: ir.Value
        returns:
          type: ir.Value
        """
        del base, literal_value
        raise NotImplementedError


@private
@typechecked
class SequenceEmission:
    """
    title: >-
      Adapt and query numeric views using analysis-selected access records.
    summary: >-
      Tensor owners are retained and Series snapshots stay independent across
      argument side effects. Bounds and status checks precede output reads;
      borrowed descriptors do not own or escape their call scope.
    attributes:
      values:
        type: ValueEmission
      types:
        type: TypeLowering
      numeric:
        type: NumericEmission
      symbol:
        type: Callable[[str, str], ir.Function]
      cleanup:
        type: CleanupService
      control:
        type: RuntimeGuardService
      literal_list_storage:
        type: LiteralListStorage
      check_arrow_status:
        type: Callable[[astx.AST, ir.Value, str], None]
    """

    values: ValueEmission
    types: TypeLowering
    numeric: NumericEmission
    symbol: Callable[[str, str], ir.Function]
    cleanup: CleanupService
    control: RuntimeGuardService
    literal_list_storage: LiteralListStorage
    check_arrow_status: Callable[[astx.AST, ir.Value, str], None]

    def __init__(
        self,
        values: ValueEmission,
        types: TypeLowering,
        numeric: NumericEmission,
        symbol: Callable[[str, str], ir.Function],
        cleanup: CleanupService,
        control: RuntimeGuardService,
        literal_list_storage: LiteralListStorage,
        check_arrow_status: Callable[[astx.AST, ir.Value, str], None],
    ) -> None:
        """
        title: >-
          Bind only value flow, checked native access, and source lifetimes.
        parameters:
          values:
            type: ValueEmission
          types:
            type: TypeLowering
          numeric:
            type: NumericEmission
          symbol:
            type: Callable[[str, str], ir.Function]
          cleanup:
            type: CleanupService
          control:
            type: RuntimeGuardService
          literal_list_storage:
            type: LiteralListStorage
          check_arrow_status:
            type: Callable[[astx.AST, ir.Value, str], None]
        """
        self.values = values
        self.types = types
        self.numeric = numeric
        self.symbol = symbol
        self.cleanup = cleanup
        self.control = control
        self.literal_list_storage = literal_list_storage
        self.check_arrow_status = check_arrow_status

    def check_status(self, node: astx.AST, status: ir.Value) -> None:
        """
        title: >-
          Guard numeric output slots and unwind temporaries before propagating.
        parameters:
          node:
            type: astx.AST
          status:
            type: ir.Value
        """
        builder = self.values.builder()
        for value, role, message in (
            (4, "IndexError", "numeric sequence index is out of bounds"),
            (2, "OverflowError", "numeric sequence byte offset overflows"),
        ):
            self.control.guard(
                node,
                builder.icmp_signed(
                    "!=", status, ir.Constant(status.type, value)
                ),
                code="ARX-RUNTIME-SEQUENCE-001",
                message=message,
                block_name="sequence.status",
                exception_role=role,
            )
        self.control.guard(
            node,
            builder.icmp_signed("==", status, ir.Constant(status.type, 0)),
            code="ARX-RUNTIME-SEQUENCE-001",
            message="invalid numeric sequence storage or access",
            block_name="sequence.status",
        )

    def adapt(
        self,
        node: astx.AST,
        value: ir.Value,
        plan: ResolvedSequenceAccess,
    ) -> ir.Value:
        """
        title: >-
          Pin a call-scoped source and construct the semantically chosen view.
        summary: >-
          Tensor owners are retained; Series use independent zero-copy
          snapshots so later argument effects cannot replace the viewed chunks.
          Lists borrow their immutable call storage. Descriptors never own or
          escape a call.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
          plan:
            type: ResolvedSequenceAccess
        returns:
          type: ir.Value
        """
        if plan.kind == "sequence":
            return value
        builder = self.values.builder()
        if plan.literal_list is not None:
            pointer = self.literal_list_storage(
                base=plan.literal_list,
                literal_value=value,
            )
            value = builder.load(pointer)
        integer = ir.IntType(64)
        opaque = ir.IntType(8).as_pointer()
        inner = (
            plan.element_type.value_type
            if isinstance(plan.element_type, astx.NullableType)
            else plan.element_type
        )
        configuration = bit_width(inner) // 8
        if plan.kind == "series":
            source_length = builder.call(
                self.symbol("dataframe", "irx_arrow_sequence_length"),
                [value],
            )
            slot = self.values.allocate("sequence.series", value.type)
            status = builder.call(
                self.symbol("dataframe", "irx_arrow_sequence_snapshot"),
                [value, slot],
            )
            self.check_arrow_status(node, status, "sequence snapshot")
            source = builder.load(slot)
            length = source_length
            release = self.symbol(
                "dataframe", "irx_arrow_chunked_array_release"
            )

            def release_series() -> None:
                """
                title: Release the independent borrowed-call snapshot.
                """
                self.values.builder().call(release, [source])

            self.cleanup.state.cleanup_stack.append(
                CleanupAction(release_series, fallible=False)
            )
            reader = self.symbol("dataframe", "irx_arrow_sequence_read")
            configuration = plan.type_id
        elif plan.kind in {"list", "tensor"}:
            slot = self.values.allocate("sequence.source", value.type)
            builder.store(value, slot)
            source = builder.bitcast(slot, opaque)
            if plan.kind == "list":
                length = builder.extract_value(value, 1)
                reader = self.symbol("list", "irx_list_sequence_read")
            else:
                owner = builder.extract_value(value, 1)
                info = semantic_info(node)
                if not info.tensor_temporary_owner:
                    retained = builder.call(
                        self.symbol("buffer", "irx_buffer_owner_retain"),
                        [owner],
                    )
                    self.control.guard(
                        node,
                        builder.icmp_signed(
                            "==", retained, ir.Constant(retained.type, 0)
                        ),
                        code="ARX-RUNTIME-SEQUENCE-001",
                        message="cannot retain tensor sequence owner",
                        block_name="sequence.retain",
                    )
                destroy = self.symbol("buffer", "irx_buffer_owner_release")

                def release_tensor() -> None:
                    """
                    title: Release the call's retained or fresh tensor owner.
                    """
                    self.values.builder().call(destroy, [owner])

                self.cleanup.state.cleanup_stack.append(
                    CleanupAction(release_tensor, fallible=False)
                )
                rank = builder.extract_value(value, 3)
                self.control.guard(
                    node,
                    builder.icmp_signed("==", rank, ir.Constant(rank.type, 1)),
                    code="ARX-RUNTIME-SEQUENCE-001",
                    message="sequence adaptation requires a rank-one tensor",
                    block_name="sequence.rank",
                    exception_role="ValueError",
                )
                shape = builder.extract_value(value, 4)
                self.control.guard(
                    node,
                    builder.icmp_unsigned(
                        "!=", shape, ir.Constant(shape.type, None)
                    ),
                    code="ARX-RUNTIME-SEQUENCE-001",
                    message="tensor sequence requires shape metadata",
                    block_name="sequence.shape",
                )
                length = builder.load(shape)
                reader = self.symbol("buffer", "irx_buffer_sequence_read")
        else:
            raise_lowering_error(
                "unrecognized resolved sequence adapter",
                node=node,
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
            )
        self.control.guard(
            node,
            builder.icmp_signed(">=", length, ir.Constant(integer, 0)),
            code="ARX-RUNTIME-SEQUENCE-001",
            message="numeric sequence length must be nonnegative",
            block_name="sequence.length",
        )
        result: ir.Value = ir.Constant(sequence_view_type(), None)
        for position, field in enumerate(
            (
                source,
                length,
                reader,
                ir.Constant(ir.IntType(32), configuration),
            )
        ):
            result = builder.insert_value(result, field, position)
        return result

    def read(
        self,
        node: astx.AST,
        view: ir.Value,
        index: ir.Value,
        element_type: astx.DataType,
    ) -> ir.Value:
        """
        title: >-
          Check a nonnegative index and decode exact bits only after success.
        parameters:
          node:
            type: astx.AST
          view:
            type: ir.Value
          index:
            type: ir.Value
          element_type:
            type: astx.DataType
        returns:
          type: ir.Value
        """
        builder = self.values.builder()
        integer = ir.IntType(64)
        length = builder.extract_value(view, 1)
        self.control.guard(
            node,
            builder.and_(
                builder.icmp_signed(">=", index, ir.Constant(integer, 0)),
                builder.icmp_signed("<", index, length),
            ),
            code="ARX-RUNTIME-SEQUENCE-001",
            message="numeric sequence index is out of bounds",
            block_name="sequence.index",
            exception_role="IndexError",
        )
        bits = self.values.allocate("sequence.bits", integer)
        valid = self.values.allocate("sequence.valid", ir.IntType(32))
        status = builder.call(
            builder.extract_value(view, 2),
            [
                builder.extract_value(view, 0),
                index,
                builder.extract_value(view, 3),
                bits,
                valid,
            ],
        )
        self.check_status(node, status)
        inner = (
            element_type.value_type
            if isinstance(element_type, astx.NullableType)
            else element_type
        )
        llvm_type = require_semantic_metadata(
            self.types.llvm_type(inner),
            node=node,
            metadata="element storage",
            context="sequence read",
        )
        value = builder.load(bits)
        if isinstance(llvm_type, ir.FloatType):
            value = builder.bitcast(
                builder.trunc(value, ir.IntType(32)), llvm_type
            )
        elif isinstance(llvm_type, ir.DoubleType):
            value = builder.bitcast(value, llvm_type)
        elif (
            isinstance(llvm_type, ir.IntType)
            and llvm_type.width < integer.width
        ):
            value = builder.trunc(value, llvm_type)
        validity = builder.icmp_signed(
            "!=", builder.load(valid), ir.Constant(ir.IntType(32), 0)
        )
        if isinstance(element_type, astx.NullableType):
            aggregate = ir.Constant(
                ir.LiteralStructType([ir.IntType(1), llvm_type]), None
            )
            return builder.insert_value(
                builder.insert_value(aggregate, validity, 0), value, 1
            )
        self.control.guard(
            node,
            validity,
            code="ARX-RUNTIME-SEQUENCE-001",
            message="nonnull numeric sequence yielded a null",
            block_name="sequence.null",
            exception_role="ValueError",
        )
        return value

    def lower(self, node: astx.CollectionLength | astx.SubscriptExpr) -> bool:
        """
        title: Consume analyzed sequence length or index metadata.
        parameters:
          node:
            type: astx.CollectionLength | astx.SubscriptExpr
        returns:
          type: bool
        """
        base = (
            node.base
            if isinstance(node, astx.CollectionLength)
            else node.value
        )
        info = getattr(node, "semantic", None)
        if not isinstance(info, SemanticInfo) or info.sequence_access is None:
            base_type = resolved_type(base)
            if isinstance(base_type, (astx.SequenceType, astx.Bytes)) or (
                isinstance(node, astx.CollectionLength)
                and isinstance(base_type, (astx.SeriesType, astx.TensorType))
            ):
                require_semantic_metadata(
                    None,
                    node=node,
                    metadata="sequence_access",
                    context="numeric sequence query",
                )
            return False
        value = self.values.evaluate(base)
        view = self.adapt(base, value, info.sequence_access)
        if isinstance(node, astx.CollectionLength):
            result = self.values.builder().extract_value(view, 1)
        else:
            index = self.values.evaluate(node.index)
            index = self.numeric.cast_value_to_type(
                index,
                ir.IntType(64),
                unsigned=is_unsigned_type(resolved_type(node.index)),
            )
            result = self.read(
                node, view, index, info.sequence_access.element_type
            )
        self.values.publish(result)
        return True
