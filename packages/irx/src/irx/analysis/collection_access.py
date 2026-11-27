# mypy: disable-error-code=no-redef

"""
title: Resolve collection access from semantic receiver types.
"""

import astx

from plum import dispatch
from public import private

from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.ownership import list_resource_ownership, resource_ownership
from irx.analysis.resolved_nodes import (
    FailedInferenceType,
    OwnershipKind,
    ResourceKind,
)
from irx.builtins.collections.list import (
    list_element_type,
    list_supports_owned_element,
)
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@private
@typechecked
def resolve_clone(
    analyzer: SemanticAnalyzerCore, node: astx.FunctionCall
) -> None:
    """
    title: Resolve a read-only copy into a fresh owner of the same list type.
    parameters:
      analyzer: Semantic analyzer resolving the builtin call.
      node: Clone call whose builtin identity is already resolved.
    """
    analyzer._set_type(node, FailedInferenceType())
    operands = tuple(node.args)
    diagnostics = analyzer.context.diagnostics
    if len(operands) != 1 or node.keywords or astx.get_template_args(node):
        diagnostics.add(
            "clone expects one positional list value and no templates",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return
    source = operands[0]
    analyzer.visit(source)
    source_type = analyzer._expr_type(source)
    if isinstance(source_type, FailedInferenceType):
        return
    if not list_supports_owned_element(list_element_type(source_type)):
        diagnostics.add(
            "clone requires a list of numeric, Boolean, or string values",
            node=source,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return
    ownership = resource_ownership(source)
    if (
        ownership is None
        or ownership.resource_kind is not ResourceKind.LIST
        or ownership.kind not in {OwnershipKind.OWNED, OwnershipKind.BORROWED}
    ):
        diagnostics.add(
            "clone requires a dynamic list value",
            node=source,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return
    function = analyzer.context.current_function
    if (
        function is None
        or function.signature.metadata.get("generator") is not None
    ):
        diagnostics.add(
            "clone requires a non-generator function with list cleanup",
            node=node,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return
    analyzer._semantic(node).list_clone_source = source
    analyzer._set_type(node, source_type)
    analyzer._set_resource_ownership(
        node, list_resource_ownership(OwnershipKind.OWNED)
    )


@private
@typechecked
def attach_collection_operation(
    analyzer: SemanticAnalyzerCore, node: astx.AST, normalized: astx.Expr
) -> bool:
    """
    title: Preserve an analyzed operation for type-independent lowering.
    summary: The original receiver is emitted only by the normalized
      operation. Lowering consumes this sidecar without reclassifying
      receiver types.
    parameters:
      analyzer: Semantic analyzer resolving the operation.
      node: Syntax node to process.
      normalized: Normalized.
    returns: 'Result of this operation: preserve an analyzed operation
      for type-independent lowering.'
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
      analyzer: Semantic analyzer resolving the operation.
      node: Syntax node to process.
    returns: 'Result of this operation: reject unsupported internal
      collection-access node shapes.'
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
    title: Resolve list append and dataframe metadata from the receiver
      type.
    summary: DataFrame nrows/ncols take no arguments, keywords, or
      template arguments and normalize to the canonical i64 count
      operations. Invalid signatures report a type mismatch at the
      call's source location; non-DataFrame receivers retain their
      ordinary method rules.
    parameters:
      analyzer: Semantic analyzer resolving the operation.
      node: Syntax node to process.
    returns: Resolved list append and dataframe metadata from the
      receiver type.
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
      analyzer: Semantic analyzer resolving the operation.
      node: Syntax node to process.
    returns: Resolved dataframe field-style access without frontend type
      guesses.
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
      analyzer: Semantic analyzer resolving the operation.
      node: Syntax node to process.
    returns: Resolved dataframe string keys while preserving static-schema
      checks.
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
