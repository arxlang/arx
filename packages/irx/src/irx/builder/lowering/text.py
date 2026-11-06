"""
title: Lower validated text plans through explicit typed emission dependencies.
"""

from collections.abc import Callable

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import SemanticInfo, TextOperationKind
from irx.analysis.types import (
    is_integer_type,
    is_string_type,
    is_unsigned_type,
)
from irx.builder.diagnostics import raise_lowering_error
from irx.builder.services.cleanup import CleanupService
from irx.builder.services.conversions import NumericEmission
from irx.builder.services.exceptions import RuntimeGuardService
from irx.builder.services.representations import TypeLowering, resolved_type
from irx.builder.services.values import ValueEmission
from irx.builder.state import CleanupAction
from irx.builder.strings import StringEmission
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@private
@typechecked
class TextEmission:
    """
    title: >-
      Consume resolved text plans without compiler inheritance or name lookup.
    summary: >-
      Operand snapshots remain active across later argument effects. Checked
      statuses precede output reads; operand and result cleanup use the shared
      lexical cleanup service rather than a feature-owned exit ledger.
    attributes:
      values:
        type: ValueEmission
      types:
        type: TypeLowering
      numeric:
        type: NumericEmission
      strings:
        type: StringEmission
      symbol:
        type: Callable[[str, str], ir.Function]
      cleanup:
        type: CleanupService
      control:
        type: RuntimeGuardService
    """

    values: ValueEmission
    types: TypeLowering
    numeric: NumericEmission
    strings: StringEmission
    symbol: Callable[[str, str], ir.Function]
    cleanup: CleanupService
    control: RuntimeGuardService

    def __init__(
        self,
        values: ValueEmission,
        types: TypeLowering,
        numeric: NumericEmission,
        strings: StringEmission,
        symbol: Callable[[str, str], ir.Function],
        cleanup: CleanupService,
        control: RuntimeGuardService,
    ) -> None:
        """
        title: >-
          Bind only value, representation, runtime, and lifetime dependencies.
        parameters:
          values:
            type: ValueEmission
          types:
            type: TypeLowering
          numeric:
            type: NumericEmission
          strings:
            type: StringEmission
          symbol:
            type: Callable[[str, str], ir.Function]
          cleanup:
            type: CleanupService
          control:
            type: RuntimeGuardService
        """
        self.values = values
        self.types = types
        self.numeric = numeric
        self.strings = strings
        self.symbol = symbol
        self.cleanup = cleanup
        self.control = control

    def check_status(
        self,
        node: astx.AST,
        status: ir.Value,
        operation: TextOperationKind,
    ) -> None:
        """
        title: Raise typed text failures before reading any output slot.
        parameters:
          node:
            type: astx.AST
          status:
            type: ir.Value
          operation:
            type: TextOperationKind
        """
        builder = self.values.builder()
        function = builder.function
        success = function.append_basic_block("text.success")
        failure = function.append_basic_block("text.failure")
        builder.cbranch(
            builder.icmp_signed("==", status, ir.Constant(status.type, 0)),
            success,
            failure,
        )
        builder.position_at_end(failure)
        message = builder.call(
            self.symbol("text", "irx_text_status_message"),
            [status],
        )
        fallback = function.append_basic_block("text.runtime_error")
        switch = builder.switch(status, fallback)
        invalid_arguments = {
            TextOperationKind.LENGTH: "len requires non-null UTF-8 text",
            TextOperationKind.ORDINAL: (
                "ord requires exactly one Unicode code point"
            ),
            TextOperationKind.INDEX: (
                "text indexing requires non-null UTF-8 text"
            ),
            TextOperationKind.SLICE: (
                "text slices require nonnegative bounds and step 1"
            ),
            TextOperationKind.SPLIT: (
                "split requires a nonempty separator or none"
            ),
            TextOperationKind.STRIP: (
                "strip requires text and a character set or none"
            ),
            TextOperationKind.INTEGER: (
                "int requires ASCII digits for base 2..36, "
                "an optional sign, and surrounding whitespace only"
            ),
        }
        for number, role in (
            (1, "ValueError"),
            (2, "OverflowError"),
            (4, "IndexError"),
            (5, "ValueError"),
        ):
            block = function.append_basic_block("text." + role)
            switch.add_case(ir.Constant(status.type, number), block)
            builder.position_at_end(block)
            self.control.raise_exception(
                node,
                role,
                self.control.text(invalid_arguments[operation])
                if number == 1
                else message,
                code="ARX-RUNTIME-TEXT-001",
            )
        builder.position_at_end(fallback)
        self.control.raise_exception(
            node, "RuntimeError", message, code="ARX-RUNTIME-TEXT-001"
        )
        builder.position_at_end(success)

    def lower(self, node: astx.AST) -> bool:
        """
        title: >-
          Consume a text plan without repeating name or argument resolution.
        summary: >-
          Snapshot string operands before subsequent expressions can replace
          their backing storage. Release inputs after the checked operation;
          register independent result cleanup unless ownership moves to the
          caller.
        parameters:
          node:
            type: astx.AST
        returns:
          type: bool
        """
        info = getattr(node, "semantic", None)
        if (
            not isinstance(info, SemanticInfo)
            or info.resolved_text_operation is None
        ):
            return False
        operation = info.resolved_text_operation
        integer = ir.IntType(64)
        string = ir.IntType(8).as_pointer()
        defaults: dict[TextOperationKind, tuple[int | None, ...]] = {
            TextOperationKind.LENGTH: (None,),
            TextOperationKind.ORDINAL: (None,),
            TextOperationKind.INDEX: (None, None),
            TextOperationKind.SLICE: (None, 0, 2**63 - 1, 1),
            TextOperationKind.SPLIT: (None, None, -1),
            TextOperationKind.STRIP: (None, None),
            TextOperationKind.INTEGER: (None, 10),
        }
        if (
            len(operation.argument_indices) != len(defaults[operation.kind])
            or operation.argument_indices[0] is None
        ):
            raise_lowering_error(
                "invalid resolved text argument plan",
                node=node,
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
            )
        depth = len(self.cleanup.state.cleanup_stack)
        values: list[ir.Value] = []
        for index, expression in enumerate(operation.evaluations):
            value = self.values.evaluate(expression)
            type_ = resolved_type(expression)
            if is_integer_type(type_):
                value = self.numeric.cast_value_to_type(
                    value, integer, unsigned=is_unsigned_type(type_)
                )
            elif is_string_type(type_) and index + 1 < len(
                operation.evaluations
            ):
                value = self.strings.copy(expression, value)
                free = self.symbol("libc", "free")

                def release(pointer: ir.Value = value) -> None:
                    """
                    title: Release one operand snapshot on success or failure.
                    parameters:
                      pointer:
                        type: ir.Value
                    """
                    self.values.builder().call(free, [pointer])

                self.cleanup.state.cleanup_stack.append(
                    CleanupAction(release, fallible=False)
                )
            values.append(value)
        arguments: list[ir.Value] = []
        for argument_index, default in zip(
            operation.argument_indices, defaults[operation.kind]
        ):
            if argument_index is None:
                arguments.append(
                    ir.Constant(string, None)
                    if default is None
                    else ir.Constant(integer, default)
                )
            elif 0 <= argument_index < len(values):
                arguments.append(values[argument_index])
            else:
                raise_lowering_error(
                    "text argument index is outside its evaluation plan",
                    node=node,
                    code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                )
        output_type = self.types.llvm_type(info.resolved_type)
        if output_type is None:
            raise_lowering_error(
                "text result requires a resolved storage type",
                node=node,
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
            )
        output = self.values.allocate("text.output", output_type)
        status = self.values.builder().call(
            self.symbol("text", f"irx_text_{operation.kind.value}"),
            [*arguments, output],
        )
        self.check_status(node, status, operation.kind)
        result = self.values.builder().load(output, name="text.result")
        owned = operation.kind in {
            TextOperationKind.SPLIT,
            TextOperationKind.INDEX,
            TextOperationKind.SLICE,
            TextOperationKind.STRIP,
        }
        if owned:
            split = operation.kind is TextOperationKind.SPLIT
            destroy = self.symbol(
                "list" if split else "libc",
                "irx_list_destroy" if split else "free",
            )

            def release_result() -> None:
                """
                title: Roll back a result if operand destruction fails.
                """
                self.values.builder().call(
                    destroy, [output if split else result]
                )

            guard = CleanupAction(release_result, fallible=False)
            self.cleanup.state.cleanup_stack.insert(depth, guard)
            self.cleanup.emit_temporary(depth + 1)
            self.cleanup.state.cleanup_stack.remove(guard)
        else:
            self.cleanup.emit_temporary(depth)
        if operation.kind is TextOperationKind.SPLIT:
            self.cleanup.register_owned_list_temporary(node, output)
        elif operation.kind in {
            TextOperationKind.INDEX,
            TextOperationKind.SLICE,
            TextOperationKind.STRIP,
        }:
            self.cleanup.register_owned_string_temporary(node, result)
        self.values.publish(result)
        return True
