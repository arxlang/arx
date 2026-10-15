# mypy: disable-error-code=no-redef
# mypy: disable-error-code=untyped-decorator

"""
title: Expression DataFrame visitors.
summary: >-
  Handle DataFrame literals, column access, metadata queries, and lifetime
  helper expressions.
"""

from __future__ import annotations

from dataclasses import replace

import astx

from irx.analysis.dataframe_values import dataframe_literal
from irx.analysis.handlers.base import (
    SemanticAnalyzerCore,
    SemanticVisitorMixinBase,
)
from irx.analysis.ownership import (
    arrow_resource_ownership,
    resource_ownership,
    transfer_resource_ownership,
)
from irx.analysis.resolved_nodes import (
    OwnershipKind,
    OwnershipTransferKind,
    ResourceKind,
    ResourceViewKind,
)
from irx.builtins.collections.dataframe import (
    DATAFRAME_COLUMN_INDEX_EXTRA,
    DATAFRAME_SCHEMA_EXTRA,
    SERIES_ELEMENT_TYPE_EXTRA,
    SERIES_NULLABLE_EXTRA,
    DataFrameSchema,
    schema_from_type,
)
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@typechecked
class ExpressionDataFrameVisitorMixin(SemanticVisitorMixinBase):
    """
    title: Expression DataFrame visitors.
    """

    def _dataframe_schema(
        self,
        node: astx.AST,
    ) -> DataFrameSchema | None:
        """
        title: Return static DataFrame schema metadata for one expression.
        parameters:
          node:
            type: astx.AST
        returns:
          type: DataFrameSchema | None
        """
        semantic = getattr(node, "semantic", None)
        extras = getattr(semantic, "extras", {})
        schema = extras.get(DATAFRAME_SCHEMA_EXTRA)
        if isinstance(schema, DataFrameSchema):
            return schema

        resolved_type = self._expr_type(node)
        if isinstance(resolved_type, astx.DataFrameType):
            return schema_from_type(resolved_type)

        return None

    def _set_dataframe_schema(
        self,
        node: astx.AST,
        schema: DataFrameSchema | None,
    ) -> None:
        """
        title: Attach static DataFrame schema metadata when available.
        parameters:
          node:
            type: astx.AST
          schema:
            type: DataFrameSchema | None
        """
        if schema is not None:
            self._semantic(node).extras[DATAFRAME_SCHEMA_EXTRA] = schema

    def _visit_dataframe_column_access(
        self,
        node: astx.DataFrameColumnAccess,
    ) -> None:
        """
        title: Visit shared DataFrame column access semantics.
        parameters:
          node:
            type: astx.DataFrameColumnAccess
        """
        self.visit(node.base)
        base_type = self._expr_type(node.base)
        if not isinstance(base_type, astx.DataFrameType):
            self.context.diagnostics.add(
                "dataframe column access requires a DataFrame value",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_FIELD_ACCESS,
            )
            self._set_type(node, None)
            return

        schema = self._dataframe_schema(node.base)
        column = None if schema is None else schema.column(node.column_name)
        if column is None:
            self.context.diagnostics.add(
                f"dataframe has no column '{node.column_name}'",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_FIELD_ACCESS,
            )
            self._set_type(node, None)
            return

        node.type_ = astx.SeriesType(
            column.type_,
            nullable=column.nullable,
            size=base_type.row_count,
        )
        self._semantic(node).extras[DATAFRAME_COLUMN_INDEX_EXTRA] = (
            column.index
        )
        self._semantic(node).extras[SERIES_ELEMENT_TYPE_EXTRA] = column.type_
        self._semantic(node).extras[SERIES_NULLABLE_EXTRA] = column.nullable
        base_ownership = resource_ownership(node.base)
        self._set_resource_ownership(
            node,
            arrow_resource_ownership(
                ResourceKind.CHUNKED_ARRAY,
                OwnershipKind.OWNED,
                owner_root_symbol_id=(
                    base_ownership.owner_root_symbol_id
                    if base_ownership is not None
                    else None
                ),
                source_symbol_id=(
                    base_ownership.source_symbol_id
                    if base_ownership is not None
                    else None
                ),
                view_kind=ResourceViewKind.RETAINED,
                view_parent_symbol_id=(
                    base_ownership.source_symbol_id
                    if base_ownership is not None
                    else None
                ),
            ),
        )
        self._set_type(node, node.type_)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.DataFrameLiteral) -> None:
        """
        title: Visit DataFrameLiteral nodes.
        parameters:
          node:
            type: astx.DataFrameLiteral
        """
        try:
            normalized = dataframe_literal(node)
        except ValueError as error:
            self.context.diagnostics.add(
                str(error),
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            self._set_type(node, None)
            return
        self.visit(normalized)
        resolved = self._semantic(normalized).resolved_tabular
        if resolved is None:
            self._set_type(node, None)
            return
        self._semantic(node).resolved_tabular = replace(
            resolved, result_type=node.type_
        )
        self._set_dataframe_schema(node, schema_from_type(node.type_))
        self._set_type(node, node.type_)
        self._set_resource_ownership(
            node,
            arrow_resource_ownership(
                ResourceKind.TABLE,
                OwnershipKind.OWNED,
            ),
        )

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.DataFrameColumnAccess) -> None:
        """
        title: Visit DataFrameColumnAccess nodes.
        parameters:
          node:
            type: astx.DataFrameColumnAccess
        """
        self._visit_dataframe_column_access(node)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.DataFrameStringColumnAccess) -> None:
        """
        title: Visit DataFrameStringColumnAccess nodes.
        parameters:
          node:
            type: astx.DataFrameStringColumnAccess
        """
        self._visit_dataframe_column_access(node)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.DataFrameRowCount) -> None:
        """
        title: Visit DataFrameRowCount nodes.
        parameters:
          node:
            type: astx.DataFrameRowCount
        """
        self.visit(node.base)
        if not isinstance(self._expr_type(node.base), astx.DataFrameType):
            self.context.diagnostics.add(
                "dataframe nrows requires a DataFrame value",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        self._set_type(node, astx.Int64())

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.DataFrameColumnCount) -> None:
        """
        title: Visit DataFrameColumnCount nodes.
        parameters:
          node:
            type: astx.DataFrameColumnCount
        """
        self.visit(node.base)
        if not isinstance(self._expr_type(node.base), astx.DataFrameType):
            self.context.diagnostics.add(
                "dataframe ncols requires a DataFrame value",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        self._set_type(node, astx.Int64())

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.DataFrameRetain) -> None:
        """
        title: Visit DataFrameRetain nodes.
        parameters:
          node:
            type: astx.DataFrameRetain
        """
        self.visit(node.base)
        if not isinstance(self._expr_type(node.base), astx.DataFrameType):
            self.context.diagnostics.add(
                "dataframe retain requires a DataFrame value",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        self._set_type(node, astx.Int32())

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.DataFrameRelease) -> None:
        """
        title: Visit DataFrameRelease nodes.
        parameters:
          node:
            type: astx.DataFrameRelease
        """
        self.visit(node.base)
        if not isinstance(self._expr_type(node.base), astx.DataFrameType):
            self.context.diagnostics.add(
                "dataframe release requires a DataFrame value",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        ownership = resource_ownership(node.base)
        if ownership is not None:
            self._set_resource_ownership(
                node.base,
                transfer_resource_ownership(
                    ownership,
                    transfer_kind=OwnershipTransferKind.MOVE,
                ),
            )
        self._set_type(node, astx.Int32())

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.SeriesRetain) -> None:
        """
        title: Visit SeriesRetain nodes.
        parameters:
          node:
            type: astx.SeriesRetain
        """
        self.visit(node.base)
        if not isinstance(self._expr_type(node.base), astx.SeriesType):
            self.context.diagnostics.add(
                "series retain requires a Series value",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        self._set_type(node, astx.Int32())

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.SeriesRelease) -> None:
        """
        title: Visit SeriesRelease nodes.
        parameters:
          node:
            type: astx.SeriesRelease
        """
        self.visit(node.base)
        if not isinstance(self._expr_type(node.base), astx.SeriesType):
            self.context.diagnostics.add(
                "series release requires a Series value",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        ownership = resource_ownership(node.base)
        if ownership is not None:
            self._set_resource_ownership(
                node.base,
                transfer_resource_ownership(
                    ownership,
                    transfer_kind=OwnershipTransferKind.MOVE,
                ),
            )
        self._set_type(node, astx.Int32())


__all__ = ["ExpressionDataFrameVisitorMixin"]
