# mypy: disable-error-code=no-redef
# mypy: disable-error-code=untyped-decorator

"""
title: Expression DataFrame visitors.
summary: >-
  Handle DataFrame literals, column access, metadata queries, and lifetime
  helper expressions.
"""

from __future__ import annotations

import astx

from irx.analysis.handlers.base import (
    SemanticAnalyzerCore,
    SemanticVisitorMixinBase,
)
from irx.analysis.validation import validate_assignment
from irx.builtins.collections.dataframe import (
    DATAFRAME_COLUMN_INDEX_EXTRA,
    DATAFRAME_SCHEMA_EXTRA,
    SERIES_ELEMENT_TYPE_EXTRA,
    SERIES_NULLABLE_EXTRA,
    DataFrameSchema,
    dataframe_column_type_is_supported,
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

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.DataFrameLiteral) -> None:
        """
        title: Visit DataFrameLiteral nodes.
        parameters:
          node:
            type: astx.DataFrameLiteral
        """
        schema = schema_from_type(node.type_)
        if schema is None:
            self.context.diagnostics.add(
                "dataframe literals require an explicit static DataFrame type",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        else:
            declared_names = {column.name for column in schema.columns}
            literal_names = {column.name for column in node.columns}
            missing = sorted(declared_names - literal_names)
            extra = sorted(literal_names - declared_names)
            if missing:
                self.context.diagnostics.add(
                    "dataframe literal is missing columns: "
                    + ", ".join(missing),
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
            if extra:
                self.context.diagnostics.add(
                    "dataframe literal has undeclared columns: "
                    + ", ".join(extra),
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
            for column in schema.columns:
                if not dataframe_column_type_is_supported(column.type_):
                    self.context.diagnostics.add(
                        "dataframe columns currently support only "
                        "fixed-width numeric and bool types",
                        node=node,
                        code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                    )

        seen_names: set[str] = set()
        row_count: int | None = None
        for literal_column in node.columns:
            if literal_column.name in seen_names:
                self.context.diagnostics.add(
                    f"duplicate dataframe column '{literal_column.name}'",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
            seen_names.add(literal_column.name)

            if row_count is None:
                row_count = len(literal_column.values)
            elif len(literal_column.values) != row_count:
                self.context.diagnostics.add(
                    "dataframe literal columns must have the same length",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )

            declared_column = (
                None if schema is None else schema.column(literal_column.name)
            )
            for value in literal_column.values:
                self.visit(value)
                if declared_column is not None:
                    validate_assignment(
                        self.context.diagnostics,
                        target_name=(
                            f"dataframe column '{literal_column.name}'"
                        ),
                        target_type=declared_column.type_,
                        value_type=self._expr_type(value),
                        node=value,
                    )

        self._set_dataframe_schema(node, schema)
        self._set_type(node, node.type_)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.DataFrameColumnAccess) -> None:
        """
        title: Visit DataFrameColumnAccess nodes.
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
        )
        self._semantic(node).extras[DATAFRAME_COLUMN_INDEX_EXTRA] = (
            column.index
        )
        self._semantic(node).extras[SERIES_ELEMENT_TYPE_EXTRA] = column.type_
        self._semantic(node).extras[SERIES_NULLABLE_EXTRA] = column.nullable
        self._set_type(node, node.type_)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.DataFrameStringColumnAccess) -> None:
        """
        title: Visit DataFrameStringColumnAccess nodes.
        parameters:
          node:
            type: astx.DataFrameStringColumnAccess
        """
        self.visit(
            cast_column := astx.DataFrameColumnAccess(
                node.base,
                node.column_name,
            )
        )
        semantic = getattr(cast_column, "semantic", None)
        if semantic is not None:
            self._semantic(node).extras.update(semantic.extras)
        node.type_ = cast_column.type_
        self._set_type(node, self._expr_type(cast_column))

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
        self._set_type(node, astx.Int32())


__all__ = ["ExpressionDataFrameVisitorMixin"]
