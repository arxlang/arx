# mypy: disable-error-code=no-redef
# mypy: disable-error-code=untyped-decorator
"""
title: Analyze first-class tabular values and their shared owner contracts.
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
from irx.analysis.schema import SchemaError, canonical_schema
from irx.analysis.schema_types import columnar_type_diagnostic
from irx.analysis.tabular import (
    ResolvedTabular,
    resolve_tabular_query,
    tabular_column_type,
)
from irx.analysis.types import is_assignable, is_signed_integer_type
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@typechecked
class TabularVisitorMixin(SemanticVisitorMixinBase):
    """
    title: Resolve schema, conversions and lifetimes before native lowering.
    """

    def tabular_error(self, node: astx.AST, message: str) -> None:
        """
        title: Reject invalid tabular operations at the semantic boundary.
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

    def tabular_result(
        self, node: astx.DataType, resolved: ResolvedTabular
    ) -> None:
        """
        title: Attach a checked ABI plan and an independently owned result.
        parameters:
          node:
            type: astx.DataType
          resolved:
            type: ResolvedTabular
        """
        error = columnar_type_diagnostic(resolved.result_type)
        if error is not None:
            self.tabular_error(node, error)
            return
        for arg in resolved.arguments:
            if getattr(arg, "semantic", None) is None:
                self.visit(arg)
        self._semantic(node).resolved_tabular = resolved
        self._set_type(node, resolved.result_type)
        if resource_contract_for_type(resolved.result_type) is not None:
            self._set_resource_ownership(
                node,
                typed_resource_ownership(
                    resolved.result_type, OwnershipKind.OWNED
                ),
            )

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.TabularLiteral) -> None:
        """
        title: Validate row count and each column against a canonical schema.
        parameters:
          node:
            type: astx.TabularLiteral
        """
        if node.type_.schema is None:
            self.tabular_error(node, "construction requires a static schema")
            return
        try:
            schema = canonical_schema(node.type_.schema)
        except SchemaError as error:
            self.tabular_error(node, str(error))
            return
        if len(node.values) != len(schema.fields) + 1:
            self.tabular_error(
                node,
                "construction requires a row count then one value per field",
            )
            return
        for index, arg in enumerate(node.values):
            self.visit(arg)
            if not self._require_value_expression(
                arg, context="Tabular value"
            ):
                return
            actual = self._expr_type(arg)
            if index == 0:
                valid = is_signed_integer_type(actual)
            else:
                valid = is_assignable(
                    tabular_column_type(node.type_, schema.fields[index - 1]),
                    actual,
                )
            if not valid:
                self.tabular_error(
                    arg, "row count or column type disagrees with schema"
                )
                return
        prefix = (
            "batch"
            if isinstance(node.type_, astx.RecordBatchType)
            else "table"
        )
        self.tabular_result(
            node,
            ResolvedTabular(
                f"irx_arrow_{prefix}_new_typed",
                type(node.type_)(schema),
                (astx.SchemaLiteral(schema), *node.values),
            ),
        )

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.TabularQuery) -> None:
        """
        title: Resolve a closed query and all generated constant ABI operands.
        parameters:
          node:
            type: astx.TabularQuery
        """
        types: list[astx.DataType] = []
        for arg in node.arguments:
            self.visit(arg)
            if not self._require_value_expression(
                arg, context="Tabular query"
            ):
                return
            type_ = self._expr_type(arg)
            if type_ is None:
                return
            types.append(type_)
        try:
            resolved = resolve_tabular_query(node, tuple(types))
        except (ValueError, SchemaError) as error:
            self.tabular_error(node, str(error))
            return
        self.tabular_result(node, resolved)
