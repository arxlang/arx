"""
title: Bind source call operands without reordering their evaluation.
"""

from typing import Callable, cast

import astx

from public import private

from irx.analysis.numeric_literals import contextualize_literal
from irx.analysis.resolved_nodes import SemanticFunction
from irx.diagnostics import DiagnosticBag, DiagnosticCodes
from irx.typecheck import typechecked


@private
@typechecked
def call_evaluations(node: astx.AST) -> tuple[astx.DataType, ...]:
    """
    title: Read positional operands followed by named values in source order.
    parameters:
      node:
        type: astx.AST
    returns:
      type: tuple[astx.DataType, Ellipsis]
    """
    args = cast(tuple[astx.DataType, ...], tuple(getattr(node, "args", ())))
    keywords = cast(
        tuple[astx.KeywordArgument, ...], getattr(node, "keywords", ())
    )
    return (*args, *(keyword.value for keyword in keywords))


@private
@typechecked
def argument_slots(
    function: SemanticFunction,
    node: astx.AST,
    diagnostics: DiagnosticBag | None = None,
) -> tuple[int, ...] | None:
    """
    title: >-
      Bind against visible declaration names, optionally diagnosing errors.
    parameters:
      function:
        type: SemanticFunction
      node:
        type: astx.AST
      diagnostics:
        type: DiagnosticBag | None
    returns:
      type: tuple[int, Ellipsis] | None
    """
    params = tuple(function.prototype.args.nodes)
    count = len(tuple(getattr(node, "args", ())))
    keywords = cast(
        tuple[astx.KeywordArgument, ...], getattr(node, "keywords", ())
    )

    def error(message: str, location: astx.AST) -> None:
        """
        title: Report binding failures only for the selected signature.
        parameters:
          message:
            type: str
          location:
            type: astx.AST
        """
        if diagnostics is not None:
            diagnostics.add(
                message,
                node=location,
                code=DiagnosticCodes.SEMANTIC_CALL_ARITY,
            )

    valid = True
    indices = list(range(count))
    if count > len(params) and not function.signature.is_variadic:
        error(
            f"call to '{function.name}' expects {len(params)} arguments "
            f"but got {count}",
            node,
        )
        valid = False
    names = {param.name: index for index, param in enumerate(params)}
    for keyword in keywords:
        index = names.get(keyword.name)
        if index is None:
            error(
                f"unknown argument '{keyword.name}' to '{function.name}'",
                keyword,
            )
            valid = False
            continue
        if index in indices:
            error(
                f"duplicate argument '{keyword.name}' to '{function.name}'",
                keyword,
            )
            valid = False
        indices.append(index)
    missing = [
        param.name
        for index, param in enumerate(params)
        if index not in indices and isinstance(param.default, astx.Undefined)
    ]
    if missing:
        required = sum(isinstance(p.default, astx.Undefined) for p in params)
        qualifier = (
            "at least "
            if function.signature.is_variadic or required != len(params)
            else ""
        )
        error(
            f"call to '{function.name}' expects {qualifier}{required} "
            f"arguments but got {count + len(keywords)}; "
            f"missing required argument(s): {', '.join(missing)}",
            node,
        )
        valid = False
    return tuple(indices) if valid else None


@private
@typechecked
def contextualize_null_arguments(
    node: astx.FunctionCall, function: SemanticFunction
) -> None:
    """
    title: >-
      Box explicit none arguments using the resolved positional or named
      parameter.
    parameters:
      node:
        type: astx.FunctionCall
      function:
        type: SemanticFunction
    """
    slots = argument_slots(function, node)
    if slots is None:
        return
    values = list(call_evaluations(node))
    for position, slot in enumerate(slots):
        if slot >= len(function.signature.parameters):
            continue
        target = function.signature.parameters[slot].type_
        if isinstance(target, astx.NullableType) and isinstance(
            values[position], astx.LiteralNone
        ):
            value = values[position]
            boxed = astx.Cast(value, target)
            boxed.loc = value.loc
            values[position] = boxed
    count = len(tuple(node.args))
    node.args = values[:count]
    for keyword, value in zip(node.keywords, values[count:]):
        keyword.value = value


@private
@typechecked
def analyze_numeric_arguments(
    node: astx.AST,
    function: SemanticFunction | None,
    visit: Callable[[astx.AST], None],
    type_of: Callable[[astx.AST | None], astx.DataType | None],
    *,
    typed_visited: bool = False,
) -> list[astx.DataType | None]:
    """
    title: Bind literal context after typed arguments, independent of order.
    summary: >-
      Only semantic traversal is reordered; lowering retains source evaluation
      order. Concrete arguments still participate in strict same-T inference.
    parameters:
      node:
        type: astx.AST
      function:
        type: SemanticFunction | None
      visit:
        type: Callable[[astx.AST], None]
      type_of:
        type: Callable[[astx.AST | None], astx.DataType | None]
      typed_visited:
        type: bool
    returns:
      type: list[astx.DataType | None]
    """
    values = call_evaluations(node)
    if function is None:
        for value in values:
            visit(value)
        return [type_of(value) for value in values]
    slots = argument_slots(function, node)
    if slots is None:
        for value in values:
            visit(value)
        return [type_of(value) for value in values]
    explicit = astx.get_template_args(node)
    selected = {
        param.name: type_
        for param, type_ in zip(function.template_params, explicit or ())
    }
    expected: astx.DataType | None
    for value, slot in zip(values, slots):
        if isinstance(value, (astx.SourceInteger, astx.SourceFloat)):
            continue
        if slot < len(function.signature.parameters):
            expected = function.signature.parameters[slot].type_
            contextualize_literal(value, expected)
        if not typed_visited:
            visit(value)
        if slot < len(function.signature.parameters):
            expected = function.signature.parameters[slot].type_
            actual = type_of(value)
            if (
                isinstance(expected, astx.TemplateTypeVar)
                and actual is not None
            ):
                selected.setdefault(expected.name, actual)
    for value, slot in zip(values, slots):
        if not isinstance(value, (astx.SourceInteger, astx.SourceFloat)):
            continue
        expected = (
            function.signature.parameters[slot].type_
            if slot < len(function.signature.parameters)
            else None
        )
        if isinstance(expected, astx.TemplateTypeVar):
            expected = selected.get(expected.name)
        contextualize_literal(value, expected)
        visit(value)
    return [type_of(value) for value in values]
