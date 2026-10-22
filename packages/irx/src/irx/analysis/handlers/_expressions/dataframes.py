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
from typing import cast

import astx

from irx.analysis.arrow_conversion import arrow_ownership
from irx.analysis.class_lifecycle import lifecycle_error
from irx.analysis.handlers.base import (
    SemanticAnalyzerCore,
    SemanticVisitorMixinBase,
)
from irx.analysis.nullable import nullable_error, scalar_type, set_operation
from irx.analysis.ownership import resource_ownership
from irx.analysis.resolved_nodes import OwnershipKind, OwnershipTransferKind
from irx.analysis.types import same_type
from irx.analysis.validation import validate_assignment
from irx.builtins.collections.dataframe import (
    DATAFRAME_COLUMN_INDEX_EXTRA,
    DATAFRAME_SCHEMA_EXTRA,
    SERIES_ELEMENT_TYPE_EXTRA,
    SERIES_NULLABLE_EXTRA,
    DataFrameSchema,
    dataframe_column_type_is_supported,
    dataframe_record_batch_type_id,
    schema_from_type,
)
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@typechecked
class ExpressionDataFrameVisitorMixin(SemanticVisitorMixinBase):
    """
    title: Expression DataFrame visitors.
    """

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.NullCheck) -> None:
        """
        title: Resolve a scalar validity test or an owned Series null mask.
        parameters:
          node:
            type: astx.NullCheck
        """
        self.visit(node.value)
        source = self._expr_type(node.value)
        if not isinstance(source, (astx.NullableType, astx.SeriesType)):
            nullable_error(
                cast(SemanticAnalyzerCore, self),
                node,
                "is_null requires a nullable scalar or Series",
            )
            return
        result = (
            astx.SeriesType(astx.Boolean())
            if isinstance(source, astx.SeriesType)
            else astx.Boolean()
        )
        set_operation(
            cast(SemanticAnalyzerCore, self),
            node,
            "is_null",
            scalar_type(source),
            result,
        )

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.NullFill) -> None:
        """
        title: Resolve eager same-type scalar null replacement.
        parameters:
          node:
            type: astx.NullFill
        """
        self.visit(node.value)
        self.visit(node.replacement)
        source = self._expr_type(node.value)
        inner = scalar_type(source)
        if not isinstance(
            source, (astx.NullableType, astx.SeriesType)
        ) or not same_type(inner, self._expr_type(node.replacement)):
            nullable_error(
                cast(SemanticAnalyzerCore, self),
                node,
                "fill_null requires nullable/Series input and a "
                "matching non-null scalar replacement",
            )
            return
        assert inner is not None
        result = (
            astx.SeriesType(inner)
            if isinstance(source, astx.SeriesType)
            else inner
        )
        set_operation(
            cast(SemanticAnalyzerCore, self), node, "coalesce", inner, result
        )

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
        self._set_type(node, node.type_)
        function = self.context.current_function
        if (
            function is None
            or function.signature.metadata.get("generator") is not None
        ):
            lifecycle_error(
                cast(SemanticAnalyzerCore, self),
                node,
                "Arrow values require a non-generator function",
            )
        self._set_resource_ownership(
            node, arrow_ownership(node.type_, OwnershipKind.OWNED)
        )

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.DataFrameLiteral) -> None:
        """
        title: Visit DataFrameLiteral nodes.
        parameters:
          node:
            type: astx.DataFrameLiteral
        """
        schema = schema_from_type(node.type_)
        if schema is not None and any(
            isinstance(c.type_, astx.ColumnType) for c in schema.columns
        ):
            nullable_error(
                cast(SemanticAnalyzerCore, self),
                node,
                "Parameterized DataFrame columns require a checked "
                "RecordBatch conversion, not a literal",
            )
            return
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
                        "numeric, bool, string and temporal literal values",
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
                    if declared_column.nullable and isinstance(
                        value, astx.LiteralNone
                    ):
                        continue
                    if isinstance(
                        declared_column.type_,
                        (astx.Date, astx.Time, astx.Timestamp, astx.DateTime),
                    ) and not isinstance(
                        value,
                        (
                            astx.LiteralDate,
                            astx.LiteralTime,
                            astx.LiteralTimestamp,
                            astx.LiteralDateTime,
                        ),
                    ):
                        self.context.diagnostics.add(
                            "temporal DataFrame values require literal "
                            "constructors or a RecordBatch conversion",
                            node=value,
                            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                        )
                    validate_assignment(
                        self.context.diagnostics,
                        target_name=(
                            f"dataframe column '{literal_column.name}'"
                        ),
                        target_type=declared_column.type_,
                        value_type=self._expr_type(value),
                        node=value,
                    )

        if schema is not None:
            self._semantic(node).extras["dataframe_storage_ids"] = tuple(
                dataframe_record_batch_type_id(c.type_) for c in schema.columns
            )
        self._set_dataframe_schema(node, schema)
        self._set_type(node, node.type_)
        function = self.context.current_function
        if (
            function is None
            or function.signature.metadata.get("generator") is not None
        ):
            lifecycle_error(
                cast(SemanticAnalyzerCore, self),
                node,
                "Arrow values require a non-generator function",
            )
        self._set_resource_ownership(
            node, arrow_ownership(node.type_, OwnershipKind.OWNED)
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
        if ownership is not None and ownership.kind is OwnershipKind.OWNED:
            self._set_resource_ownership(
                node.base,
                replace(ownership, transfer_kind=OwnershipTransferKind.MOVE),
            )
        elif not isinstance(node.base, astx.Identifier):
            self.context.diagnostics.add(
                "explicit release requires an owned temporary or local",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
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
        if ownership is not None and ownership.kind is OwnershipKind.OWNED:
            self._set_resource_ownership(
                node.base,
                replace(ownership, transfer_kind=OwnershipTransferKind.MOVE),
            )
        elif not isinstance(node.base, astx.Identifier):
            self.context.diagnostics.add(
                "explicit release requires an owned temporary or local",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
        self._set_type(node, astx.Int32())


__all__ = ["ExpressionDataFrameVisitorMixin"]
