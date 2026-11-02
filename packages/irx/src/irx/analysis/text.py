"""
title: Semantic contracts for checked Unicode text operations.
summary: >-
  len and ord take one positional text value. int(text, base=10) accepts ASCII
  digits/letters with an optional sign and surrounding whitespace, returning
  i64 without prefixes, underscores, Unicode digits, or partial parse.
  split(sep=none, maxsplit=-1) and strip(chars=none) use Unicode whitespace by
  default. Explicit separators preserve empty fields; chars is a code-point
  set. Indexing and half-open slicing use nonnegative code-point positions,
  clipped slice bounds, and step 1. Owned results never borrow source storage.
"""

import astx

from public import private

from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.numeric_literals import contextualize_literal
from irx.analysis.ownership import (
    list_resource_ownership,
    string_resource_ownership,
)
from irx.analysis.resolved_nodes import (
    OwnershipKind,
    ResolvedTextOperation,
    TextOperationKind,
)
from irx.analysis.types import is_assignable, is_integer_type, is_string_type
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@private
@typechecked
def text_error(
    analyzer: SemanticAnalyzerCore, node: astx.AST, message: str
) -> None:
    """
    title: Report a text-contract violation at its source expression.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.AST
      message:
        type: str
    """
    analyzer.context.diagnostics.add(
        message, node=node, code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH
    )


@private
@typechecked
def set_text_operation(
    analyzer: SemanticAnalyzerCore,
    node: astx.AST,
    kind: TextOperationKind,
    evaluations: tuple[astx.AST, ...],
    indices: tuple[int | None, ...],
) -> None:
    """
    title: Publish a validated operation with explicit result ownership.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.AST
      kind:
        type: TextOperationKind
      evaluations:
        type: tuple[astx.AST, Ellipsis]
      indices:
        type: tuple[int | None, Ellipsis]
    """
    for value in evaluations:
        if not isinstance(value, astx.Expr):
            text_error(analyzer, value, "text operands must be expressions")
            return
    if not all(
        analyzer._require_value_expression(value, context="text operand")
        for value in evaluations
    ):
        return
    info = analyzer._semantic(node)
    info.resolved_text_operation = ResolvedTextOperation(
        kind, evaluations, indices
    )
    info.resource_ownership = None
    result: astx.DataType = astx.Int64()
    if kind is TextOperationKind.SPLIT:
        result = astx.ListType([astx.String()])
        info.resource_ownership = list_resource_ownership(OwnershipKind.OWNED)
    elif kind in {
        TextOperationKind.INDEX,
        TextOperationKind.SLICE,
        TextOperationKind.STRIP,
    }:
        result = astx.String()
        info.resource_ownership = string_resource_ownership(
            OwnershipKind.OWNED
        )
    function = analyzer.context.current_function
    if (
        info.resource_ownership is not None
        and function is not None
        and (function.signature.metadata.get("generator") is not None)
    ):
        text_error(
            analyzer,
            node,
            "owned text results in generators require lifecycle cleanup",
        )
    analyzer._set_type(node, result)


@private
@typechecked
def text_integer_argument(
    analyzer: SemanticAnalyzerCore, value: astx.AST, name: str
) -> bool:
    """
    title: Require an integer losslessly representable in the signed i64 ABI.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      value:
        type: astx.AST
      name:
        type: str
    returns:
      type: bool
    """
    contextualize_literal(value, astx.Int64())
    analyzer.visit(value)
    actual = analyzer._expr_type(value)
    if is_integer_type(actual) and is_assignable(astx.Int64(), actual):
        return True
    text_error(
        analyzer,
        value,
        f"text {name} requires an integer representable as i64; "
        "use an explicit checked cast for wider unsigned values",
    )
    return False


@private
@typechecked
def resolve_text_call(
    analyzer: SemanticAnalyzerCore, node: astx.FunctionCall | astx.MethodCall
) -> None:
    """
    title: Bind builtin text calls without reordering argument evaluation.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.FunctionCall | astx.MethodCall
    """
    method = isinstance(node, astx.MethodCall)
    name = node.method_name if isinstance(node, astx.MethodCall) else node.fn
    schemas = {
        "split": ("sep", "maxsplit"),
        "strip": ("chars",),
        "int": ("text", "base"),
        "ord": ("text",),
    }
    if name not in schemas or (method and name not in {"split", "strip"}):
        text_error(analyzer, node, f"unsupported text method '{name}'")
        return
    names = schemas[name]
    if astx.get_template_args(node) is not None:
        text_error(
            analyzer, node, f"{name} does not accept template arguments"
        )
        return
    positional = tuple(node.args)
    if len(positional) > len(names):
        text_error(analyzer, node, f"too many arguments to {name}")
        return
    supplied = list(zip(names, positional))
    occupied = {key for key, _ in supplied}
    for keyword in node.keywords:
        if keyword.name not in names or name == "ord":
            text_error(
                analyzer, keyword, f"unknown {name} argument '{keyword.name}'"
            )
            return
        if keyword.name in occupied:
            text_error(
                analyzer,
                keyword,
                f"duplicate {name} argument '{keyword.name}'",
            )
            return
        occupied.add(keyword.name)
        supplied.append((keyword.name, keyword.value))
    if not method and "text" not in occupied:
        text_error(analyzer, node, f"{name} requires a text argument")
        return
    evaluations: list[astx.AST] = []
    if isinstance(node, astx.MethodCall):
        evaluations.append(
            node.receiver
        )  # Already analyzed by method dispatch.
    indices: dict[str, int | None] = dict.fromkeys(names)
    valid = True
    for key, expression in supplied:
        indices[key] = len(evaluations)
        evaluations.append(expression)
        if key in {"base", "maxsplit"}:
            valid = text_integer_argument(analyzer, expression, key) and valid
            continue
        analyzer.visit(expression)
        if key in {"sep", "chars"} and isinstance(
            expression, astx.LiteralNone
        ):
            indices[key] = None
            evaluations.pop()
            continue
        if not is_string_type(analyzer._expr_type(expression)):
            text_error(analyzer, expression, f"{name} {key} requires text")
            valid = False
    if not valid:
        return
    kind = TextOperationKind(name)
    arguments = ((0,) if method else ()) + tuple(indices[key] for key in names)
    set_text_operation(analyzer, node, kind, tuple(evaluations), arguments)


@private
@typechecked
def resolve_text_subscript(
    analyzer: SemanticAnalyzerCore, node: astx.SubscriptExpr
) -> None:
    """
    title: Bind a text index or clipped slice after analyzing its receiver.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.SubscriptExpr
    """
    slicing = node.is_slice
    operands = (
        (("start", node.lower), ("stop", node.upper), ("step", node.step))
        if slicing
        else (("index", node.index),)
    )
    evaluations: list[astx.AST] = [node.value]
    indices: list[int | None] = [0]
    valid = True
    for name, expression in operands:
        if slicing and isinstance(expression, astx.LiteralNone):
            indices.append(None)
            continue
        indices.append(len(evaluations))
        evaluations.append(expression)
        valid = text_integer_argument(analyzer, expression, name) and valid
    if valid:
        set_text_operation(
            analyzer,
            node,
            TextOperationKind.SLICE if slicing else TextOperationKind.INDEX,
            tuple(evaluations),
            tuple(indices),
        )
