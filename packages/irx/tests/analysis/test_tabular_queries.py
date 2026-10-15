"""
title: Public tabular resolver boundaries independently of parser and lowering.
"""

from __future__ import annotations

import astx
import pytest

from irx.analysis import analyze
from irx.analysis.tabular import resolve_tabular_query, tabular_column_type
from irx.diagnostics import SemanticError
from typeguard import TypeCheckError


def test_tabular_resolver_checks_container_and_arity() -> None:
    """
    title: Reject malformed direct resolver calls without trusting the parser.
    """
    node = astx.TabularQuery(astx.TabularOperation.ROWS, ())
    with pytest.raises(ValueError, match="argument count"):
        resolve_tabular_query(node, ())
    node = astx.TabularQuery(
        astx.TabularOperation.ROWS, (astx.Identifier("value"),)
    )
    with pytest.raises(ValueError, match="table or record_batch"):
        resolve_tabular_query(node, (astx.Int64(),))
    with pytest.raises(TypeCheckError):
        resolve_tabular_query(node, (None,))  # type: ignore[arg-type]


def test_tabular_column_type_requires_a_supported_container() -> None:
    """
    title: Do not interpret future stream types as table-shaped values.
    """
    field = astx.SchemaField("a", astx.LogicalType(astx.LogicalKind.INT32))
    with pytest.raises(TypeCheckError):
        tabular_column_type(astx.StreamType(), field)  # type: ignore[arg-type]
    assert isinstance(
        tabular_column_type(astx.TableType(), field), astx.ChunkedArrayType
    )
    assert isinstance(
        tabular_column_type(astx.RecordBatchType(), field), astx.ArrayType
    )


@pytest.mark.parametrize(
    "type_",
    [
        astx.TableType(),
        astx.RecordBatchType(),
        astx.NullableType(astx.TableType()),
        astx.ArrayType(astx.LogicalType(astx.LogicalKind.INT32)),
        astx.ArrayBuilderType(astx.LogicalType(astx.LogicalKind.INT32)),
        astx.ChunkedArrayType(astx.LogicalType(astx.LogicalKind.INT32)),
    ],
)
def test_managed_struct_fields_require_destruction(
    type_: astx.DataType,
) -> None:
    """
    title: Reject owner-bearing by-value fields rather than silently leaking.
    parameters:
      type_:
        type: astx.DataType
    """
    module = astx.Module()
    module.block.append(
        astx.StructDefStmt(
            name="Owner", attributes=[astx.VariableDeclaration("value", type_)]
        )
    )
    with pytest.raises(
        SemanticError, match="struct fields require destruction"
    ):
        analyze(module)
