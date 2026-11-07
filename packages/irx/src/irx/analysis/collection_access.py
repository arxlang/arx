# mypy: disable-error-code=no-redef

"""
title: Resolve collection access from semantic receiver types.
"""

import astx

from plum import dispatch
from public import private

from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.ownership import resource_ownership
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@private
@typechecked
def attach_collection_operation(
    analyzer: SemanticAnalyzerCore, node: astx.AST, normalized: astx.Expr
) -> bool:
    """
    title: Preserve an analyzed operation for type-independent lowering.
    summary: >-
      The original receiver is emitted only by the normalized operation.
      Lowering consumes this sidecar without reclassifying receiver types.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.AST
      normalized:
        type: astx.Expr
    returns:
      type: bool
    """
    normalized.loc = node.loc
    analyzer.visit(normalized)
    analyzer._semantic(node).normalized_collection = normalized
    analyzer._set_type(node, analyzer._expr_type(normalized))
    analyzer._set_resource_ownership(node, resource_ownership(normalized))
    return True


@private
@dispatch
@typechecked
def resolve_collection_access(
    analyzer: SemanticAnalyzerCore, node: astx.AST
) -> bool:
    """
    title: Reject unsupported internal collection-access node shapes.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.AST
    returns:
      type: bool
    raises:
      TypeError: If the caller supplies a non-access node.
    """
    del analyzer
    raise TypeError(
        f"Unsupported collection-access node: {type(node).__name__}"
    )


@dispatch
@typechecked
def resolve_collection_access(
    analyzer: SemanticAnalyzerCore, node: astx.MethodCall
) -> bool:
    """
    title: Resolve list append and dataframe metadata from the receiver type.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.MethodCall
    returns:
      type: bool
    """
    analyzer._semantic(node).normalized_collection = None
    receiver_type = analyzer._expr_type(node.receiver)
    if (
        isinstance(receiver_type, astx.ListType)
        and node.method_name == "append"
    ):
        if (
            node.keywords
            or astx.get_template_args(node)
            or len(node.args) != 1
        ):
            analyzer.context.diagnostics.add(
                "List append expects exactly one positional argument "
                "and no templates",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return True
        return attach_collection_operation(
            analyzer, node, astx.ListAppend(node.receiver, node.args[0])
        )
    if not isinstance(
        receiver_type, astx.DataFrameType
    ) or node.method_name not in {"nrows", "ncols"}:
        return False
    if node.args or node.keywords or astx.get_template_args(node):
        analyzer.context.diagnostics.add(
            f"DataFrame {node.method_name} expects no arguments or templates",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return True
    operation = (
        astx.DataFrameRowCount(node.receiver)
        if node.method_name == "nrows"
        else astx.DataFrameColumnCount(node.receiver)
    )
    return attach_collection_operation(analyzer, node, operation)


@dispatch
@typechecked
def resolve_collection_access(
    analyzer: SemanticAnalyzerCore, node: astx.FieldAccess
) -> bool:
    """
    title: Resolve dataframe field-style access without frontend type guesses.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.FieldAccess
    returns:
      type: bool
    """
    analyzer._semantic(node).normalized_collection = None
    if not isinstance(analyzer._expr_type(node.value), astx.DataFrameType):
        return False
    return attach_collection_operation(
        analyzer, node, astx.DataFrameColumnAccess(node.value, node.field_name)
    )


@dispatch
@typechecked
def resolve_collection_access(
    analyzer: SemanticAnalyzerCore, node: astx.SubscriptExpr
) -> bool:
    """
    title: Resolve dataframe string keys while preserving static-schema checks.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.SubscriptExpr
    returns:
      type: bool
    """
    analyzer._semantic(node).normalized_collection = None
    if not isinstance(analyzer._expr_type(node.value), astx.DataFrameType):
        return False
    if node.is_slice or not isinstance(node.index, astx.LiteralString):
        analyzer.context.diagnostics.add(
            "DataFrame column access requires one string literal key",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return True
    return attach_collection_operation(
        analyzer,
        node,
        astx.DataFrameStringColumnAccess(node.value, node.index.value),
    )
