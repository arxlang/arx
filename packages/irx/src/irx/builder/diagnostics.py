"""
title: Shared lowering diagnostics helpers.
summary: Centralize the small helpers that lowering uses to raise structured
  diagnostic exceptions instead of ad hoc Exception strings.
"""

from __future__ import annotations

from typing import NoReturn, TypeVar

import astx

from llvmlite import ir

from irx.analysis.types import display_type_name
from irx.diagnostics import (
    Diagnostic,
    DiagnosticCodes,
    LoweringError,
    get_node_module_key,
)
from irx.typecheck import typechecked

T = TypeVar("T")


@typechecked
def resolved_ast_type_name(node: astx.AST | None) -> str:
    """
    title: Return one node's best-effort semantic type name.
    parameters:
      node: Syntax node to process.
    returns: One node's best-effort semantic type name.
    """
    if node is None:
        return "<unknown>"
    semantic = getattr(node, "semantic", None)
    resolved_type = getattr(semantic, "resolved_type", None)
    if isinstance(resolved_type, astx.DataType):
        return display_type_name(resolved_type)
    raw_type = getattr(node, "type_", None)
    return display_type_name(
        raw_type if isinstance(raw_type, astx.DataType) else None
    )


@typechecked
def lowered_value_type_name(value: ir.Value | None) -> str:
    """
    title: Return one lowered LLVM value type name.
    parameters:
      value: Value to process.
    returns: One lowered LLVM value type name.
    """
    if value is None:
        return "<missing>"
    return str(value.type)


@typechecked
def raise_lowering_error(
    message: str,
    *,
    code: str,
    node: astx.AST | None = None,
    notes: tuple[str, ...] = (),
    hint: str | None = None,
    cause: Exception | None = None,
) -> NoReturn:
    """
    title: Raise one user-facing lowering diagnostic.
    parameters:
      message: Diagnostic or output message.
      code: Source code or diagnostic identifier.
      node: Syntax node to process.
      notes: Notes.
      hint: Hint.
      cause: Cause.
    """
    raise LoweringError(
        Diagnostic(
            message=message,
            node=node,
            module_key=get_node_module_key(node),
            code=code,
            phase="lowering",
            notes=notes,
            hint=hint,
            cause=cause,
        )
    )


@typechecked
def raise_lowering_internal_error(
    message: str,
    *,
    node: astx.AST | None = None,
    code: str = DiagnosticCodes.LOWERING_MISSING_SEMANTIC_METADATA,
    notes: tuple[str, ...] = (),
    hint: str | None = None,
    cause: Exception | None = None,
) -> NoReturn:
    """
    title: Raise one internal lowering consistency diagnostic.
    parameters:
      message: Diagnostic or output message.
      node: Syntax node to process.
      code: Source code or diagnostic identifier.
      notes: Notes.
      hint: Hint.
      cause: Cause.
    """
    raise_lowering_error(
        f"internal compiler error: {message}",
        code=code,
        node=node,
        notes=notes,
        hint=hint,
        cause=cause,
    )


@typechecked
def require_semantic_metadata(
    value: T | None,
    *,
    node: astx.AST,
    metadata: str,
    context: str,
) -> T:
    """
    title: Require one semantic sidecar field during lowering.
    parameters:
      value: Value to process.
      node: Syntax node to process.
      metadata: Metadata associated with the operation.
      context: Context for the operation.
    returns: 'Result of this operation: require one semantic sidecar field
      during lowering.'
    """
    if value is None:
        raise_lowering_internal_error(
            f"missing {metadata} metadata during {context}",
            node=node,
            notes=(f"semantic type: {resolved_ast_type_name(node)}",),
        )
    return value


@typechecked
def require_lowered_value(
    value: ir.Value | None,
    *,
    node: astx.AST,
    context: str,
) -> ir.Value:
    """
    title: Require one lowered LLVM value during lowering.
    parameters:
      value: Value to process.
      node: Syntax node to process.
      context: Context for the operation.
    returns: 'Result of this operation: require one lowered LLVM value during
      lowering.'
    """
    if value is None:
        raise_lowering_internal_error(
            f"{context} did not lower to a value",
            node=node,
            notes=(f"semantic type: {resolved_ast_type_name(node)}",),
        )
    return value
