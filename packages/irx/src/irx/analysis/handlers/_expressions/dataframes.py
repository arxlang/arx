# mypy: disable-error-code=no-redef

"""
title: Expression DataFrame visitors.
summary: >-
  Handle DataFrame literals, column access, metadata queries, and lifetime
  helper expressions.
"""

from __future__ import annotations

from dataclasses import replace

import astx

from plum import dispatch
from public import private

from irx.analysis.arrow_conversion import arrow_ownership
from irx.analysis.dataframe_literals import dataframe_literal_ipc
from irx.analysis.dependencies.expression_data_frame import (
    ExpressionDataFrameAnalysisServices,
)
from irx.analysis.nullable import (
    scalar_type,
)
from irx.analysis.numeric_literals import contextualize_literal
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
from irx.extensions.handlers import configuration_error
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class ExpressionDataFrameAnalysis:
    """
    title: Expression DataFrame visitors.
    attributes:
      services:
        type: ExpressionDataFrameAnalysisServices
    """

    services: ExpressionDataFrameAnalysisServices

    def __init__(self, services: ExpressionDataFrameAnalysisServices) -> None:
        """
        title: Bind one feature to explicit compilation-owned dependencies.
        parameters:
          services:
            type: ExpressionDataFrameAnalysisServices
        """
        self.services = services

    @dispatch
    def visit(self, node: astx.AST) -> None:
        """
        title: Reject an input outside this feature's explicit support.
        parameters:
          node:
            type: astx.AST
        """
        raise configuration_error(
            f"unsupported {type(node).__name__} in ExpressionDataFrameAnalysis"
        )

    @dispatch
    def visit(self, node: astx.NullCheck) -> None:
        """
        title: Resolve a scalar validity test or an owned Series null mask.
        parameters:
          node:
            type: astx.NullCheck
        """
        self.services.visit(node.value)
        source = self.services.expr_type(node.value)
        if not isinstance(source, (astx.NullableType, astx.SeriesType)):
            self.services.free_nullable_error(
                node,
                "is_null requires a nullable scalar or Series",
            )
            return
        result = (
            astx.SeriesType(astx.Boolean())
            if isinstance(source, astx.SeriesType)
            else astx.Boolean()
        )
        self.services.free_set_operation(
            node,
            "is_null",
            scalar_type(source),
            result,
        )

    @dispatch
    def visit(self, node: astx.NullFill) -> None:
        """
        title: Resolve eager same-type scalar null replacement.
        parameters:
          node:
            type: astx.NullFill
        """
        self.services.visit(node.value)
        source = self.services.expr_type(node.value)
        inner = scalar_type(source)
        contextualize_literal(node.replacement, inner)
        self.services.visit(node.replacement)
        if not isinstance(
            source, (astx.NullableType, astx.SeriesType)
        ) or not same_type(inner, self.services.expr_type(node.replacement)):
            self.services.free_nullable_error(
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
        self.services.free_set_operation(node, "coalesce", inner, result)

    @dispatch
    def visit(self, node: astx.SeriesReduction) -> None:
        """
        title: Resolve an explicitly named null-skipping Series reduction.
        parameters:
          node:
            type: astx.SeriesReduction
        """
        self.services.free_resolve_series_reduction(node)

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

        resolved_type = self.services.expr_type(node)
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
            self.services.semantic(node).extras[DATAFRAME_SCHEMA_EXTRA] = (
                schema
            )

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
        self.services.visit(node.base)
        base_type = self.services.expr_type(node.base)
        if not isinstance(base_type, astx.DataFrameType):
            self.services.context.diagnostics.add(
                "dataframe column access requires a DataFrame value",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_FIELD_ACCESS,
            )
            self.services.set_type(node, None)
            return

        schema = self._dataframe_schema(node.base)
        column = None if schema is None else schema.column(node.column_name)
        if column is None:
            self.services.context.diagnostics.add(
                f"dataframe has no column '{node.column_name}'",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_FIELD_ACCESS,
            )
            self.services.set_type(node, None)
            return

        node.type_ = astx.SeriesType(
            column.type_,
            nullable=column.nullable,
            size=base_type.row_count,
        )
        self.services.semantic(node).extras[DATAFRAME_COLUMN_INDEX_EXTRA] = (
            column.index
        )
        self.services.semantic(node).extras[SERIES_ELEMENT_TYPE_EXTRA] = (
            column.type_
        )
        self.services.semantic(node).extras[SERIES_NULLABLE_EXTRA] = (
            column.nullable
        )
        self.services.set_type(node, node.type_)
        function = self.services.context.current_function
        if (
            function is None
            or function.signature.metadata.get("generator") is not None
        ):
            self.services.free_lifecycle_error(
                node,
                "Arrow values require a non-generator function",
            )
        self.services.set_resource_ownership(
            node, arrow_ownership(node.type_, OwnershipKind.OWNED)
        )

    @dispatch
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
            try:
                self.services.semantic(node).extras[
                    "dataframe_literal_ipc"
                ] = dataframe_literal_ipc(node)
            except (ValueError, OverflowError) as error:
                self.services.free_nullable_error(node, str(error))
                return
            self._set_dataframe_schema(node, schema)
            self.services.set_type(node, node.type_)
            function = self.services.context.current_function
            if (
                function is None
                or function.signature.metadata.get("generator") is not None
            ):
                self.services.free_lifecycle_error(
                    node,
                    "Arrow values require a non-generator function",
                )
            self.services.set_resource_ownership(
                node, arrow_ownership(node.type_, OwnershipKind.OWNED)
            )
            return
        if schema is None:
            self.services.context.diagnostics.add(
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
                self.services.context.diagnostics.add(
                    "dataframe literal is missing columns: "
                    + ", ".join(missing),
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
            if extra:
                self.services.context.diagnostics.add(
                    "dataframe literal has undeclared columns: "
                    + ", ".join(extra),
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
            for column in schema.columns:
                if not dataframe_column_type_is_supported(column.type_):
                    self.services.context.diagnostics.add(
                        "dataframe columns currently support only "
                        "numeric, bool, string and temporal literal values",
                        node=node,
                        code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                    )

        seen_names: set[str] = set()
        row_count: int | None = None
        for literal_column in node.columns:
            if literal_column.name in seen_names:
                self.services.context.diagnostics.add(
                    f"duplicate dataframe column '{literal_column.name}'",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
            seen_names.add(literal_column.name)

            if row_count is None:
                row_count = len(literal_column.values)
            elif len(literal_column.values) != row_count:
                self.services.context.diagnostics.add(
                    "dataframe literal columns must have the same length",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )

            declared_column = (
                None if schema is None else schema.column(literal_column.name)
            )
            for value in literal_column.values:
                contextualize_literal(
                    value,
                    declared_column.type_
                    if declared_column is not None
                    else None,
                )
                self.services.visit(value)
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
                        self.services.context.diagnostics.add(
                            "temporal DataFrame values require literal "
                            "constructors or a RecordBatch conversion",
                            node=value,
                            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                        )
                    validate_assignment(
                        self.services.context.diagnostics,
                        target_name=(
                            f"dataframe column '{literal_column.name}'"
                        ),
                        target_type=declared_column.type_,
                        value_type=self.services.expr_type(value),
                        node=value,
                    )

        if schema is not None:
            self.services.semantic(node).extras["dataframe_storage_ids"] = (
                tuple(
                    dataframe_record_batch_type_id(c.type_)
                    for c in schema.columns
                )
            )
        self._set_dataframe_schema(node, schema)
        self.services.set_type(node, node.type_)
        function = self.services.context.current_function
        if (
            function is None
            or function.signature.metadata.get("generator") is not None
        ):
            self.services.free_lifecycle_error(
                node,
                "Arrow values require a non-generator function",
            )
        self.services.set_resource_ownership(
            node, arrow_ownership(node.type_, OwnershipKind.OWNED)
        )

    @dispatch
    def visit(self, node: astx.DataFrameColumnAccess) -> None:
        """
        title: Visit DataFrameColumnAccess nodes.
        parameters:
          node:
            type: astx.DataFrameColumnAccess
        """
        self._visit_dataframe_column_access(node)

    @dispatch
    def visit(self, node: astx.DataFrameStringColumnAccess) -> None:
        """
        title: Visit DataFrameStringColumnAccess nodes.
        parameters:
          node:
            type: astx.DataFrameStringColumnAccess
        """
        self._visit_dataframe_column_access(node)

    @dispatch
    def visit(self, node: astx.DataFrameRowCount) -> None:
        """
        title: Visit DataFrameRowCount nodes.
        parameters:
          node:
            type: astx.DataFrameRowCount
        """
        self.services.visit(node.base)
        if not isinstance(
            self.services.expr_type(node.base), astx.DataFrameType
        ):
            self.services.context.diagnostics.add(
                "dataframe nrows requires a DataFrame value",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        self.services.set_type(node, astx.Int64())

    @dispatch
    def visit(self, node: astx.DataFrameColumnCount) -> None:
        """
        title: Visit DataFrameColumnCount nodes.
        parameters:
          node:
            type: astx.DataFrameColumnCount
        """
        self.services.visit(node.base)
        if not isinstance(
            self.services.expr_type(node.base), astx.DataFrameType
        ):
            self.services.context.diagnostics.add(
                "dataframe ncols requires a DataFrame value",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        self.services.set_type(node, astx.Int64())

    @dispatch
    def visit(self, node: astx.DataFrameRetain) -> None:
        """
        title: Visit DataFrameRetain nodes.
        parameters:
          node:
            type: astx.DataFrameRetain
        """
        self.services.visit(node.base)
        if not isinstance(
            self.services.expr_type(node.base), astx.DataFrameType
        ):
            self.services.context.diagnostics.add(
                "dataframe retain requires a DataFrame value",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        self.services.set_type(node, astx.Int32())

    @dispatch
    def visit(self, node: astx.DataFrameRelease) -> None:
        """
        title: Visit DataFrameRelease nodes.
        parameters:
          node:
            type: astx.DataFrameRelease
        """
        self.services.visit(node.base)
        if not isinstance(
            self.services.expr_type(node.base), astx.DataFrameType
        ):
            self.services.context.diagnostics.add(
                "dataframe release requires a DataFrame value",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        ownership = resource_ownership(node.base)
        if ownership is not None and ownership.kind is OwnershipKind.OWNED:
            self.services.set_resource_ownership(
                node.base,
                replace(ownership, transfer_kind=OwnershipTransferKind.MOVE),
            )
        elif not isinstance(node.base, astx.Identifier):
            self.services.context.diagnostics.add(
                "explicit release requires an owned temporary or local",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
        self.services.set_type(node, astx.Int32())

    @dispatch
    def visit(self, node: astx.SeriesRetain) -> None:
        """
        title: Visit SeriesRetain nodes.
        parameters:
          node:
            type: astx.SeriesRetain
        """
        self.services.visit(node.base)
        if not isinstance(self.services.expr_type(node.base), astx.SeriesType):
            self.services.context.diagnostics.add(
                "series retain requires a Series value",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        self.services.set_type(node, astx.Int32())

    @dispatch
    def visit(self, node: astx.SeriesRelease) -> None:
        """
        title: Visit SeriesRelease nodes.
        parameters:
          node:
            type: astx.SeriesRelease
        """
        self.services.visit(node.base)
        if not isinstance(self.services.expr_type(node.base), astx.SeriesType):
            self.services.context.diagnostics.add(
                "series release requires a Series value",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        ownership = resource_ownership(node.base)
        if ownership is not None and ownership.kind is OwnershipKind.OWNED:
            self.services.set_resource_ownership(
                node.base,
                replace(ownership, transfer_kind=OwnershipTransferKind.MOVE),
            )
        elif not isinstance(node.base, astx.Identifier):
            self.services.context.diagnostics.add(
                "explicit release requires an owned temporary or local",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
        self.services.set_type(node, astx.Int32())

    def node_handlers(self) -> tuple[NodeHandler, ...]:
        """
        title: Export this feature's supported nominal node signatures.
        returns:
          type: tuple[NodeHandler, Ellipsis]
        """
        return tuple(
            contribute_node(
                "irx.analysis.expression_data_frame." + node_type.__name__,
                "irx.analysis.expression_data_frame",
                "analysis",
                node_type,
                self.visit,
                source=__name__ + ".ExpressionDataFrameAnalysis.visit",
            )
            for node_type in (
                astx.NullCheck,
                astx.NullFill,
                astx.SeriesReduction,
                astx.DataFrameLiteral,
                astx.DataFrameColumnAccess,
                astx.DataFrameStringColumnAccess,
                astx.DataFrameRowCount,
                astx.DataFrameColumnCount,
                astx.DataFrameRetain,
                astx.DataFrameRelease,
                astx.SeriesRetain,
                astx.SeriesRelease,
            )
        )
