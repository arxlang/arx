"""
title: Bind source call operands without reordering their evaluation.
"""

from typing import cast

import astx

from public import private

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
