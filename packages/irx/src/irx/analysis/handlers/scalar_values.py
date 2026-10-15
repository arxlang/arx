# mypy: disable-error-code=no-redef
# mypy: disable-error-code=untyped-decorator
"""
title: Analyze opaque logical scalars and their shared lifetime contracts.
"""

from __future__ import annotations

import astx

from irx.analysis.handlers.base import (
    SemanticAnalyzerCore,
    SemanticVisitorMixinBase,
)
from irx.analysis.ownership import (
    resource_contract_for_type,
    typed_resource_ownership,
)
from irx.analysis.resolved_nodes import OwnershipKind
from irx.analysis.scalar_values import (
    ResolvedScalar,
    scalar_constructor,
    scalar_query,
)
from irx.analysis.schema import SchemaError
from irx.analysis.schema_types import columnar_type_diagnostic
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@typechecked
class ScalarValueVisitorMixin(SemanticVisitorMixinBase):
    """
    title: Attach complete constructor signatures and resolved descriptors.
    """

    def scalar_error(self, node: astx.AST, message: str) -> None:
        """
        title: Report invalid logical scalar input before lowering.
        parameters:
          node:
            type: astx.AST
          message:
            type: str
        """
        self.context.diagnostics.add(
            message, node=node, code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH
        )
        self._set_type(node, None)

    def scalar_arguments(
        self, values: tuple[astx.Expr, ...]
    ) -> tuple[astx.DataType, ...]:
        """
        title: Analyze each payload once and reject void expression operands.
        parameters:
          values:
            type: tuple[astx.Expr, Ellipsis]
        returns:
          type: tuple[astx.DataType, Ellipsis]
        """
        types: list[astx.DataType] = []
        for value in values:
            self.visit(value)
            if self._require_value_expression(
                value, context="Scalar payload", allow_none=True
            ):
                actual = self._expr_type(value)
                if actual is not None:
                    types.append(actual)
        return tuple(types)

    def scalar_result(
        self, node: astx.DataType, resolved: ResolvedScalar
    ) -> None:
        """
        title: Attach normalized operands and explicit owned result metadata.
        parameters:
          node:
            type: astx.DataType
          resolved:
            type: ResolvedScalar
        """
        error = columnar_type_diagnostic(resolved.result_type)
        if error is not None:
            self.scalar_error(node, error)
            return
        self._semantic(node).resolved_scalar = resolved
        self._set_type(node, resolved.result_type)
        if resource_contract_for_type(resolved.result_type) is not None:
            self._set_resource_ownership(
                node,
                typed_resource_ownership(
                    resolved.result_type, OwnershipKind.OWNED
                ),
            )

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.ScalarLiteral) -> None:
        """
        title: >-
          Resolve a constructor and synthesize its analyzed type descriptor.
        parameters:
          node:
            type: astx.ScalarLiteral
        """
        types = self.scalar_arguments(node.values)
        if len(types) != len(node.values):
            return
        try:
            resolved = scalar_constructor(node.type_, node.values, types)
        except (ValueError, SchemaError) as error:
            self.scalar_error(node, str(error))
            return
        descriptor = astx.TypeDescriptorLiteral(node.type_.element_type)
        self.visit(descriptor)
        self.scalar_result(
            node,
            ResolvedScalar(
                resolved.symbol,
                resolved.result_type,
                (descriptor, *resolved.arguments),
                (astx.TypeDescriptorType(), *resolved.argument_types),
                resolved.vector,
            ),
        )

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.ScalarQuery) -> None:
        """
        title: Validate scalar queries independently of native representation.
        parameters:
          node:
            type: astx.ScalarQuery
        """
        types = self.scalar_arguments(node.arguments)
        if len(types) != len(node.arguments):
            return
        try:
            resolved = scalar_query(node.operation, node.arguments, types)
        except (ValueError, SchemaError) as error:
            self.scalar_error(node, str(error))
            return
        self.scalar_result(node, resolved)
