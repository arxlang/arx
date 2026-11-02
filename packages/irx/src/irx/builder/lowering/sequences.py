"""
title: Lower resolved borrowed numeric views without collection type inference.
"""

from typing import TYPE_CHECKING, cast

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import ResolvedSequenceAccess, SemanticInfo
from irx.analysis.types import bit_width, is_unsigned_type
from irx.builder.core import VisitorCore
from irx.builder.diagnostics import (
    raise_lowering_error,
    require_lowered_value,
    require_semantic_metadata,
)
from irx.builder.runtime import safe_pop
from irx.builder.runtime.sequence import sequence_view_type
from irx.builder.state import CleanupAction
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.lowering.dataframe import DataFrameVisitorMixin
    from irx.builder.lowering.list import ListVisitorMixin


@private
@typechecked
def check_sequence_status(
    visitor: VisitorCore, node: astx.AST, status: ir.Value
) -> None:
    """
    title: >-
      Guard numeric output slots and unwind temporaries before propagating.
    parameters:
      visitor:
        type: VisitorCore
      node:
        type: astx.AST
      status:
        type: ir.Value
    """
    builder = visitor._llvm.ir_builder
    for value, role, message in (
        (4, "IndexError", "numeric sequence index is out of bounds"),
        (2, "OverflowError", "numeric sequence byte offset overflows"),
    ):
        visitor._guard_runtime_condition(
            node,
            builder.icmp_signed("!=", status, ir.Constant(status.type, value)),
            code="ARX-RUNTIME-SEQUENCE-001",
            message=message,
            block_name="sequence.status",
            exception_role=role,
        )
    visitor._guard_runtime_condition(
        node,
        builder.icmp_signed("==", status, ir.Constant(status.type, 0)),
        code="ARX-RUNTIME-SEQUENCE-001",
        message="invalid numeric sequence storage or access",
        block_name="sequence.status",
    )


@private
@typechecked
def adapt_sequence(
    visitor: VisitorCore,
    node: astx.AST,
    value: ir.Value,
    plan: ResolvedSequenceAccess,
) -> ir.Value:
    """
    title: Pin a call-scoped source and construct the semantically chosen view.
    summary: >-
      Tensor owners are retained; Series use independent zero-copy snapshots so
      later argument effects cannot replace the viewed chunks. Lists borrow
      their immutable call storage. Descriptors never own or escape a call.
    parameters:
      visitor:
        type: VisitorCore
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
    builder = visitor._llvm.ir_builder
    if plan.literal_list is not None:
        lists: ListVisitorMixin = cast("ListVisitorMixin", visitor)
        pointer = lists._literal_list_pointer_for_runtime(
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
            visitor.require_runtime_symbol(
                "dataframe", "irx_arrow_sequence_length"
            ),
            [value],
        )
        slot = visitor.create_entry_block_alloca("sequence.series", value.type)
        status = builder.call(
            visitor.require_runtime_symbol(
                "dataframe", "irx_arrow_sequence_snapshot"
            ),
            [value, slot],
        )
        dataframes: DataFrameVisitorMixin = cast(
            "DataFrameVisitorMixin", visitor
        )
        dataframes.check_arrow_status(node, status, "sequence snapshot")
        source = builder.load(slot)
        length = source_length
        release = visitor.require_runtime_symbol(
            "dataframe", "irx_arrow_chunked_array_release"
        )

        def release_series() -> None:
            """
            title: Release the independent borrowed-call snapshot.
            """
            visitor._llvm.ir_builder.call(release, [source])

        visitor.cleanup_stack.append(
            CleanupAction(release_series, fallible=False)
        )
        reader = visitor.require_runtime_symbol(
            "dataframe", "irx_arrow_sequence_read"
        )
        configuration = plan.type_id
    elif plan.kind in {"list", "tensor"}:
        slot = visitor.create_entry_block_alloca("sequence.source", value.type)
        builder.store(value, slot)
        source = builder.bitcast(slot, opaque)
        if plan.kind == "list":
            length = builder.extract_value(value, 1)
            reader = visitor.require_runtime_symbol(
                "list", "irx_list_sequence_read"
            )
        else:
            owner = builder.extract_value(value, 1)
            info = require_semantic_metadata(
                cast(SemanticInfo | None, getattr(node, "semantic", None)),
                node=node,
                metadata="semantic",
                context="sequence lifetime",
            )
            if not info.tensor_temporary_owner:
                retained = builder.call(
                    visitor.require_runtime_symbol(
                        "buffer", "irx_buffer_owner_retain"
                    ),
                    [owner],
                )
                visitor._guard_runtime_condition(
                    node,
                    builder.icmp_signed(
                        "==", retained, ir.Constant(retained.type, 0)
                    ),
                    code="ARX-RUNTIME-SEQUENCE-001",
                    message="cannot retain tensor sequence owner",
                    block_name="sequence.retain",
                )
            destroy = visitor.require_runtime_symbol(
                "buffer", "irx_buffer_owner_release"
            )

            def release_tensor() -> None:
                """
                title: Release the call's retained or fresh tensor owner.
                """
                visitor._llvm.ir_builder.call(destroy, [owner])

            visitor.cleanup_stack.append(
                CleanupAction(release_tensor, fallible=False)
            )
            rank = builder.extract_value(value, 3)
            visitor._guard_runtime_condition(
                node,
                builder.icmp_signed("==", rank, ir.Constant(rank.type, 1)),
                code="ARX-RUNTIME-SEQUENCE-001",
                message="sequence adaptation requires a rank-one tensor",
                block_name="sequence.rank",
                exception_role="ValueError",
            )
            shape = builder.extract_value(value, 4)
            visitor._guard_runtime_condition(
                node,
                builder.icmp_unsigned(
                    "!=", shape, ir.Constant(shape.type, None)
                ),
                code="ARX-RUNTIME-SEQUENCE-001",
                message="tensor sequence requires shape metadata",
                block_name="sequence.shape",
            )
            length = builder.load(shape)
            reader = visitor.require_runtime_symbol(
                "buffer", "irx_buffer_sequence_read"
            )
    else:
        raise_lowering_error(
            "unrecognized resolved sequence adapter",
            node=node,
            code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
        )
    visitor._guard_runtime_condition(
        node,
        builder.icmp_signed(">=", length, ir.Constant(integer, 0)),
        code="ARX-RUNTIME-SEQUENCE-001",
        message="numeric sequence length must be nonnegative",
        block_name="sequence.length",
    )
    result: ir.Value = ir.Constant(sequence_view_type(), None)
    for position, field in enumerate(
        (source, length, reader, ir.Constant(ir.IntType(32), configuration))
    ):
        result = builder.insert_value(result, field, position)
    return result


@private
@typechecked
def read_sequence(
    visitor: VisitorCore,
    node: astx.AST,
    view: ir.Value,
    index: ir.Value,
    element_type: astx.DataType,
) -> ir.Value:
    """
    title: Check a nonnegative index and decode exact bits only after success.
    parameters:
      visitor:
        type: VisitorCore
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
    builder = visitor._llvm.ir_builder
    integer = ir.IntType(64)
    length = builder.extract_value(view, 1)
    visitor._guard_runtime_condition(
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
    bits = visitor.create_entry_block_alloca("sequence.bits", integer)
    valid = visitor.create_entry_block_alloca("sequence.valid", ir.IntType(32))
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
    check_sequence_status(visitor, node, status)
    inner = (
        element_type.value_type
        if isinstance(element_type, astx.NullableType)
        else element_type
    )
    llvm_type = require_semantic_metadata(
        visitor._llvm_type_for_ast_type(inner),
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
    elif isinstance(llvm_type, ir.IntType) and llvm_type.width < integer.width:
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
    visitor._guard_runtime_condition(
        node,
        validity,
        code="ARX-RUNTIME-SEQUENCE-001",
        message="nonnull numeric sequence yielded a null",
        block_name="sequence.null",
        exception_role="ValueError",
    )
    return value


@private
@typechecked
def lower_sequence_query(
    visitor: VisitorCore, node: astx.CollectionLength | astx.SubscriptExpr
) -> bool:
    """
    title: Consume analyzed sequence length or index metadata.
    parameters:
      visitor:
        type: VisitorCore
      node:
        type: astx.CollectionLength | astx.SubscriptExpr
    returns:
      type: bool
    """
    base = node.base if isinstance(node, astx.CollectionLength) else node.value
    info = getattr(node, "semantic", None)
    if not isinstance(info, SemanticInfo) or info.sequence_access is None:
        base_type = visitor._resolved_ast_type(base)
        if isinstance(base_type, astx.SequenceType) or (
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
    visitor.visit_child(base)
    value = require_lowered_value(
        safe_pop(visitor.result_stack), node=base, context="sequence source"
    )
    view = adapt_sequence(visitor, base, value, info.sequence_access)
    if isinstance(node, astx.CollectionLength):
        result = visitor._llvm.ir_builder.extract_value(view, 1)
    else:
        visitor.visit_child(node.index)
        index = require_lowered_value(
            safe_pop(visitor.result_stack),
            node=node.index,
            context="sequence index",
        )
        index = visitor._cast_value_to_type(
            index,
            ir.IntType(64),
            unsigned=is_unsigned_type(visitor._resolved_ast_type(node.index)),
        )
        result = read_sequence(
            visitor, node, view, index, info.sequence_access.element_type
        )
    visitor.result_stack.append(result)
    return True
