# mypy: disable-error-code=no-redef

"""
title: Bind source call operands without reordering their evaluation.
"""

from typing import Callable, cast

import astx

from plum import dispatch
from public import private

from irx.analysis.numeric_literals import contextualize_literal
from irx.analysis.resolved_nodes import SemanticFunction
from irx.analysis.types import sequence_element_type, substitute_type
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
        if isinstance(
            value,
            (
                astx.LiteralInteger,
                astx.LiteralFloat,
                astx.ListExpr,
                astx.LiteralList,
            ),
        ):
            continue
        if slot < len(function.signature.parameters):
            expected = function.signature.parameters[slot].type_
            contextualize_literal(value, substitute_type(expected, selected))
        if not typed_visited:
            visit(value)
        if slot < len(function.signature.parameters):
            expected = function.signature.parameters[slot].type_
            actual = type_of(value)
            collect_literal_context(expected, actual, selected)
    for value, slot in zip(values, slots):
        if not isinstance(
            value,
            (
                astx.LiteralInteger,
                astx.LiteralFloat,
                astx.ListExpr,
                astx.LiteralList,
            ),
        ):
            continue
        expected = (
            function.signature.parameters[slot].type_
            if slot < len(function.signature.parameters)
            else None
        )
        if expected is not None:
            expected = substitute_type(expected, selected)
        contextualize_literal(value, expected)
        visit(value)
    return [type_of(value) for value in values]


@private
@dispatch
@typechecked
def collect_literal_context(
    expected: astx.DataType,
    actual: astx.DataType | None,
    bindings: dict[str, astx.DataType],
) -> None:
    """
    title: Leave unsupported context trees to authoritative call validation.
    summary: >-
      Provisional context never authorizes conversions or resolves conflicts.
      The template resolver validates every binding after literals are typed.
    parameters:
      expected:
        type: astx.DataType
      actual:
        type: astx.DataType | None
      bindings:
        type: dict[str, astx.DataType]
    """
    del expected, actual, bindings


@dispatch
@typechecked
def collect_literal_context(
    expected: astx.TemplateTypeVar,
    actual: astx.DataType | None,
    bindings: dict[str, astx.DataType],
) -> None:
    """
    title: Gather concrete sibling context for an unresolved variable.
    parameters:
      expected:
        type: astx.TemplateTypeVar
      actual:
        type: astx.DataType | None
      bindings:
        type: dict[str, astx.DataType]
    """
    if actual is not None:
        bindings.setdefault(expected.name, actual)


@dispatch
@typechecked
def collect_literal_context(
    expected: astx.SequenceType,
    actual: astx.DataType | None,
    bindings: dict[str, astx.DataType],
) -> None:
    """
    title: Gather exact element context through a sequence adapter.
    parameters:
      expected:
        type: astx.SequenceType
      actual:
        type: astx.DataType | None
      bindings:
        type: dict[str, astx.DataType]
    """
    collect_literal_context(
        expected.element_type, sequence_element_type(actual), bindings
    )


@dispatch
@typechecked
def collect_literal_context(
    expected: astx.ListType,
    actual: astx.ListType,
    bindings: dict[str, astx.DataType],
) -> None:
    """
    title: Gather matching list element contexts without element conversion.
    parameters:
      expected:
        type: astx.ListType
      actual:
        type: astx.ListType
      bindings:
        type: dict[str, astx.DataType]
    """
    if len(expected.element_types) == len(actual.element_types):
        for left, right in zip(expected.element_types, actual.element_types):
            collect_literal_context(
                cast(astx.DataType, left), cast(astx.DataType, right), bindings
            )


@dispatch
@typechecked
def collect_literal_context(
    expected: astx.NullableType,
    actual: astx.NullableType,
    bindings: dict[str, astx.DataType],
) -> None:
    """
    title: Preserve nullability while gathering the inner element context.
    parameters:
      expected:
        type: astx.NullableType
      actual:
        type: astx.NullableType
      bindings:
        type: dict[str, astx.DataType]
    """
    collect_literal_context(expected.value_type, actual.value_type, bindings)


@dispatch
@typechecked
def collect_literal_context(
    expected: astx.SeriesType | astx.TensorType | astx.BufferViewType,
    actual: astx.DataType | None,
    bindings: dict[str, astx.DataType],
) -> None:
    """
    title: Gather storage element contexts only for matching source kinds.
    parameters:
      expected:
        type: astx.SeriesType | astx.TensorType | astx.BufferViewType
      actual:
        type: astx.DataType | None
      bindings:
        type: dict[str, astx.DataType]
    """
    if type(expected) is type(actual):
        left, right = (
            expected.element_type,
            getattr(actual, "element_type", None),
        )
        if left is not None and isinstance(right, astx.DataType):
            collect_literal_context(left, right, bindings)
