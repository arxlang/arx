"""
title: Fixed-domain lazy range construction and checked access contracts.
"""

import astx

from public import private

from irx.analysis.call_arguments import analyze_numeric_arguments
from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.resolved_nodes import CallingConvention
from irx.analysis.types import is_integer_type
from irx.analysis.validation import validate_call
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked

RANGE_PARAMETERS = ("start", "stop", "step")


@private
@typechecked
def resolve_range_call(
    analyzer: SemanticAnalyzerCore, node: astx.FunctionCall
) -> None:
    """
    title: Bind range operands once through the ordinary named-call machinery.
    summary: >-
      One positional operand denotes stop; two or three denote start, stop,
      step. With an explicit stop keyword, a positional operand denotes start.
      Named start defaults to zero and step to one; stop is required.
      Duplicate, unknown and missing names follow ordinary call diagnostics.
      Endpoints and step require lossless i32 inputs. Zero step raises
      AssertionError at run time, including empty intervals. The result owns no
      allocation.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.FunctionCall
    """
    errors_before = len(analyzer.context.diagnostics.diagnostics)
    positional = tuple(node.args)
    if astx.get_template_args(node) or len(positional) > len(RANGE_PARAMETERS):
        analyzer.context.diagnostics.add(
            "range expects stop or start, stop[, step], without templates",
            node=node,
            code=DiagnosticCodes.SEMANTIC_CALL_ARITY,
        )
        return
    zero = astx.LiteralInt32(0)
    one = astx.LiteralInt32(1)
    analyzer.visit(zero)
    analyzer.visit(one)
    prototype = astx.FunctionPrototype(
        "range",
        args=astx.Arguments(
            astx.Argument("stop", astx.Int32()),
            astx.Argument("start", astx.Int32(), default=zero),
            astx.Argument("step", astx.Int32(), default=one),
        ),
        return_type=astx.RangeType(),
    )
    signature = analyzer.factory.make_function_signature(
        prototype,
        calling_convention=CallingConvention.IRX_DEFAULT,
        is_variadic=False,
        is_extern=False,
        symbol_name="range",
    )
    function = analyzer.factory.make_function(
        "irx.builtins", prototype, signature=signature
    )
    names = (
        ("stop",)
        if len(positional) == 1
        and not any(item.name == "stop" for item in node.keywords)
        else RANGE_PARAMETERS
    )
    keywords = []
    for name, value in zip(names, positional):
        keyword = astx.KeywordArgument(name, value)
        keyword.loc = value.loc
        keywords.append(keyword)
    normalized = astx.FunctionCall(
        "range", [], keywords=(*keywords, *node.keywords)
    )
    normalized.loc = node.loc
    arg_types = analyze_numeric_arguments(
        normalized, function, analyzer.visit, analyzer._expr_type
    )
    resolution = validate_call(
        analyzer.context.diagnostics,
        function=function,
        arg_types=arg_types,
        node=normalized,
    )
    if len(analyzer.context.diagnostics.diagnostics) != errors_before:
        return
    analyzer._semantic(node).range_construction = resolution
    analyzer._set_type(node, astx.RangeType())


@private
@typechecked
def resolve_range_index(
    analyzer: SemanticAnalyzerCore, node: astx.SubscriptExpr
) -> None:
    """
    title: Validate one nonnegative integer index without exposing storage.
    summary: >-
      Slicing is unsupported. Bounds failures raise IndexError, including for
      empty ranges. Integer indices may be signed or unsigned through 64 bits;
      bounds are checked before multiplication or element narrowing.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.SubscriptExpr
    """
    analyzer._set_type(node, None)
    if node.is_slice:
        analyzer.context.diagnostics.add(
            "range slicing is unsupported; use one integer index",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return
    analyzer.visit(node.index)
    type_ = analyzer._expr_type(node.index)
    if not is_integer_type(type_) or isinstance(type_, astx.UInt128):
        analyzer.context.diagnostics.add(
            "range access requires one integer index through 64 bits; "
            "slicing is unsupported",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return
    analyzer._semantic(node).range_access = True
    analyzer._set_type(node, astx.Int32())
