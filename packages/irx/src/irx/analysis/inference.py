"""
title: Resolve declaration initializers without erasing inference requests.
"""

import astx

from public import private

from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.numeric_literals import contextualize_literal
from irx.analysis.types import clone_type, is_none_type
from irx.analysis.validation import validate_assignment
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@private
@typechecked
def resolve_initializer_type(
    analyzer: SemanticAnalyzerCore,
    node: astx.VariableDeclaration | astx.InlineVariableDeclaration,
) -> astx.DataType | None:
    """
    title: Resolve an initialized declaration to one concrete storage type.
    summary: >-
      Analyze each initializer once per visit. Explicit annotations provide
      contextual literal types; inference supplies no expected type. Neither
      path changes the original annotation. Missing, ambiguous, and non-value
      inference fails before symbol publication, layout, or lowering.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.VariableDeclaration | astx.InlineVariableDeclaration
    returns:
      type: astx.DataType | None
    """
    info = analyzer._semantic(node)
    info.resolved_type = None
    info.resolved_symbol = None
    info.module_storage = None
    info.resource_ownership = None
    inferred = isinstance(node.type_, astx.InferredType)
    missing = node.value is None or isinstance(node.value, astx.Undefined)
    if not inferred:
        analyzer._resolve_declared_type(node.type_, node=node)
    if missing and (
        inferred or node.mutability == astx.MutabilityKind.constant
    ):
        analyzer.context.diagnostics.add(
            f"Declaration '{node.name}' requires an initializer",
            node=node,
            code=DiagnosticCodes.SEMANTIC_INVALID_ASSIGNMENT_TARGET,
        )
        return None
    if missing:
        return node.type_
    value = node.value
    assert value is not None
    if (
        not inferred
        and isinstance(node.type_, astx.NullableType)
        and isinstance(value, astx.LiteralNone)
    ):
        value = astx.Cast(value, node.type_)
        value.loc = node.value.loc
        node.value = value
    contextualize_literal(value, None if inferred else node.type_)
    analyzer.visit(value)
    if inferred and isinstance(value, astx.LiteralNone):
        analyzer.context.diagnostics.add(
            f"Cannot infer a concrete type for '{node.name}' from none; "
            "supply an explicit nullable type",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return None
    if not analyzer._require_value_expression(
        value, context=f"Initializer for '{node.name}'"
    ):
        return None
    value_type = analyzer._expr_type(value)
    if inferred:
        if (
            value_type is None
            or is_none_type(value_type)
            or isinstance(value_type, astx.InferredType)
            or type(value_type) in {astx.DataType, astx.types.AnyType}
        ):
            analyzer.context.diagnostics.add(
                f"Cannot infer a concrete type for '{node.name}'; "
                "supply an explicit type or typed constructor",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return None
        analyzer._resolve_declared_type(value_type, node=node)
        return clone_type(value_type)
    validate_assignment(
        analyzer.context.diagnostics,
        target_name=node.name,
        target_type=node.type_,
        value_type=value_type,
        node=node,
    )
    return node.type_
