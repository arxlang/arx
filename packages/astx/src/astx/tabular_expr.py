"""
title: Typed tabular construction and immutable structural operations.
"""

from __future__ import annotations

from enum import Enum

from public import public

from astx.base import DataType, Expr, ReprStruct, SourceLocation
from astx.schema import RecordBatchType, TableType
from astx.tools.typing import typechecked
from astx.types import AnyType


@public
@typechecked
class TabularLiteral(DataType):
    """
    title: Construct a typed batch or table with an explicit row count.
    attributes:
      type_:
        type: RecordBatchType | TableType
      values:
        type: tuple[Expr, Ellipsis]
      loc:
        type: SourceLocation
    """

    type_: RecordBatchType | TableType
    values: tuple[Expr, ...]
    loc: SourceLocation

    def __init__(
        self,
        type_: RecordBatchType | TableType,
        values: tuple[Expr, ...],
        *,
        loc: SourceLocation | None = None,
    ) -> None:
        """
        title: >-
          Initialize a row count followed by the ordered column expressions.
        parameters:
          type_:
            type: RecordBatchType | TableType
          values:
            type: tuple[Expr, Ellipsis]
          loc:
            type: SourceLocation | None
        """
        super().__init__()
        self.type_ = type_
        self.values = values
        if loc is not None:
            self.loc = loc

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Preserve the declared type and all element expressions.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            "TabularLiteral",
            {
                "type": self.type_.get_struct(simplified),
                "values": [
                    value.get_struct(simplified) for value in self.values
                ],
            },
            simplified,
        )


@public
@typechecked
class TabularOperation(Enum):
    """
    title: Closed tabular primitives independent of backend symbols.
    """

    ROWS = "num_rows"
    COLUMNS = "num_columns"
    SCHEMA = "container_schema"
    COLUMN = "column"
    COLUMN_AS = "column_as"
    SLICE = "slice_rows"
    TAKE = "take_rows"
    SELECT = "select_columns"
    RENAME = "rename_columns"
    ADD = "add_column"
    REPLACE = "replace_column"
    REMOVE = "remove_column"
    TO_TABLE = "to_table"
    TO_DATAFRAME = "to_dataframe"
    TO_SERIES = "to_series"
    TO_CHUNKED = "to_chunked"
    EXPORT_C_DATA = "export_c_data"
    IMPORT_C_DATA = "array_from_c_data"
    WITH_VALIDITY = "array_with_validity"
    FROM_BUFFERS = "array_from_buffers"
    TO_BATCH = "to_record_batch"
    COMBINE = "table_combine_chunks"
    DYNAMIC = "runtime_schema"


@public
@typechecked
class TabularQuery(DataType):
    """
    title: Apply a typed tabular operation without selecting native storage.
    attributes:
      operation:
        type: TabularOperation
      arguments:
        type: tuple[Expr, Ellipsis]
      type_:
        type: DataType
      loc:
        type: SourceLocation
    """

    operation: TabularOperation
    arguments: tuple[Expr, ...]
    type_: DataType
    loc: SourceLocation

    def __init__(
        self,
        operation: TabularOperation,
        arguments: tuple[Expr, ...],
        *,
        loc: SourceLocation | None = None,
    ) -> None:
        """
        title: Initialize a closed query with ordered expression arguments.
        parameters:
          operation:
            type: TabularOperation
          arguments:
            type: tuple[Expr, Ellipsis]
          loc:
            type: SourceLocation | None
        """
        super().__init__()
        self.operation = operation
        self.arguments = arguments
        self.type_ = AnyType()
        if loc is not None:
            self.loc = loc

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Preserve the operation and arguments in structural snapshots.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            "TabularQuery",
            {
                "operation": self.operation.value,
                "arguments": [
                    arg.get_struct(simplified) for arg in self.arguments
                ],
            },
            simplified,
        )
