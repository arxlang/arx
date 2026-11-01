"""
title: Lower validated text plans through checked native output slots.
"""

from typing import cast

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import SemanticInfo, TextOperationKind
from irx.analysis.types import (
    is_integer_type,
    is_string_type,
    is_unsigned_type,
)
from irx.builder.core import VisitorCore
from irx.builder.diagnostics import (
    raise_lowering_error,
    require_lowered_value,
)
from irx.builder.lowering.exceptions import ExceptionVisitorMixin
from irx.builder.runtime import safe_pop
from irx.builder.state import CleanupAction
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@private
@typechecked
def check_text_status(
    visitor: VisitorCore,
    node: astx.AST,
    status: ir.Value,
    operation: TextOperationKind,
) -> None:
    """
    title: Raise typed text failures before reading any output slot.
    parameters:
      visitor:
        type: VisitorCore
      node:
        type: astx.AST
      status:
        type: ir.Value
      operation:
        type: TextOperationKind
    """
    builder = visitor._llvm.ir_builder
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
        visitor.require_runtime_symbol("text", "irx_text_status_message"),
        [status],
    )
    fallback = function.append_basic_block("text.runtime_error")
    switch = builder.switch(status, fallback)
    exceptions = cast(ExceptionVisitorMixin, visitor)
    invalid_arguments = {
        TextOperationKind.LENGTH: "len requires non-null UTF-8 text",
        TextOperationKind.ORDINAL: (
            "ord requires exactly one Unicode code point"
        ),
        TextOperationKind.INDEX: "text indexing requires non-null UTF-8 text",
        TextOperationKind.SLICE: (
            "text slices require nonnegative bounds and step 1"
        ),
        TextOperationKind.SPLIT: "split requires a nonempty separator or none",
        TextOperationKind.STRIP: (
            "strip requires text and a character set or none"
        ),
        TextOperationKind.INTEGER: "int requires ASCII digits for base 2..36, "
        "an optional sign, and surrounding whitespace only",
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
        exceptions.raise_runtime_exception(
            node,
            role,
            exceptions.exception_string(invalid_arguments[operation])
            if number == 1
            else message,
            code="ARX-RUNTIME-TEXT-001",
        )
    builder.position_at_end(fallback)
    exceptions.raise_runtime_exception(
        node, "RuntimeError", message, code="ARX-RUNTIME-TEXT-001"
    )
    builder.position_at_end(success)


@private
@typechecked
def lower_text_operation(visitor: VisitorCore, node: astx.AST) -> bool:
    """
    title: Consume a text plan without repeating name or argument resolution.
    summary: >-
      Snapshot string operands before subsequent expressions can replace their
      backing storage. Release inputs after the checked operation; register
      independent result cleanup unless ownership moves to the caller.
    parameters:
      visitor:
        type: VisitorCore
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
    integer = visitor._llvm.INT64_TYPE
    string = visitor._llvm.INT8_TYPE.as_pointer()
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
    depth = len(visitor.cleanup_stack)
    values: list[ir.Value] = []
    for index, expression in enumerate(operation.evaluations):
        visitor.visit_child(expression)
        value = require_lowered_value(
            safe_pop(visitor.result_stack),
            node=expression,
            context="text operand",
        )
        type_ = visitor._resolved_ast_type(expression)
        if is_integer_type(type_):
            value = visitor._cast_value_to_type(
                value, integer, unsigned=is_unsigned_type(type_)
            )
        elif is_string_type(type_) and index + 1 < len(operation.evaluations):
            value = visitor._copy_string_to_heap(expression, value)
            free = visitor.require_runtime_symbol("libc", "free")

            def release(pointer: ir.Value = value) -> None:
                """
                title: Release one operand snapshot on success or failure.
                parameters:
                  pointer:
                    type: ir.Value
                """
                visitor._llvm.ir_builder.call(free, [pointer])

            visitor.cleanup_stack.append(
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
    output_type = visitor._llvm_type_for_ast_type(info.resolved_type)
    if output_type is None:
        raise_lowering_error(
            "text result requires a resolved storage type",
            node=node,
            code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
        )
    output = visitor.create_entry_block_alloca("text.output", output_type)
    status = visitor._llvm.ir_builder.call(
        visitor.require_runtime_symbol(
            "text", f"irx_text_{operation.kind.value}"
        ),
        [*arguments, output],
    )
    check_text_status(visitor, node, status, operation.kind)
    result = visitor._llvm.ir_builder.load(output, name="text.result")
    owned = operation.kind in {
        TextOperationKind.SPLIT,
        TextOperationKind.INDEX,
        TextOperationKind.SLICE,
        TextOperationKind.STRIP,
    }
    if owned:
        split = operation.kind is TextOperationKind.SPLIT
        destroy = visitor.require_runtime_symbol(
            "list" if split else "libc",
            "irx_list_destroy" if split else "free",
        )

        def release_result() -> None:
            """
            title: Roll back a result if operand destruction fails.
            """
            visitor._llvm.ir_builder.call(
                destroy, [output if split else result]
            )

        guard = CleanupAction(release_result, fallible=False)
        visitor.cleanup_stack.insert(depth, guard)
        visitor._emit_temporary_cleanups(depth + 1)
        visitor.cleanup_stack.remove(guard)
    else:
        visitor._emit_temporary_cleanups(depth)
    if operation.kind is TextOperationKind.SPLIT:
        visitor._register_owned_list_temporary(node, output)
    elif operation.kind in {
        TextOperationKind.INDEX,
        TextOperationKind.SLICE,
        TextOperationKind.STRIP,
    }:
        visitor._register_owned_string_temporary(node, result)
    visitor.result_stack.append(result)
    return True
