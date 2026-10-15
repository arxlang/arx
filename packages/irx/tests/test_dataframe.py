"""
title: Tests for the IRx DataFrame layer.
"""

from __future__ import annotations

import shutil

import astx
import pytest

from irx.analysis import (
    OwnershipKind,
    OwnershipTransferKind,
    ResourceKind,
    ResourceViewKind,
    SemanticError,
    analyze,
    resource_ownership,
)
from irx.builder import Builder

from .conftest import assert_ir_parses, build_and_run, make_main_module

EXPECTED_ROW_OR_COLUMN_COUNT = 3
EXPECTED_DATAFRAME_RELEASE_CALL_COUNT = 3


def _dataframe_type() -> astx.DataFrameType:
    """
    title: Build one static DataFrame test schema.
    returns:
      type: astx.DataFrameType
    """
    return astx.DataFrameType(
        (
            astx.DataFrameColumn("id", astx.Int32()),
            astx.DataFrameColumn("score", astx.Float64()),
            astx.DataFrameColumn("ok", astx.Boolean()),
        )
    )


def _dataframe_literal(
    type_: astx.DataFrameType | None = None,
) -> astx.DataFrameLiteral:
    """
    title: Build one DataFrame literal aligned to the test schema.
    parameters:
      type_:
        type: astx.DataFrameType | None
    returns:
      type: astx.DataFrameLiteral
    """
    schema = type_ or _dataframe_type()
    return astx.DataFrameLiteral(
        (
            astx.DataFrameLiteralColumn(
                "id",
                (
                    astx.LiteralInt32(1),
                    astx.LiteralInt32(2),
                    astx.LiteralInt32(3),
                ),
            ),
            astx.DataFrameLiteralColumn(
                "score",
                (
                    astx.LiteralFloat64(0.5),
                    astx.LiteralFloat64(0.8),
                    astx.LiteralFloat64(1.0),
                ),
            ),
            astx.DataFrameLiteralColumn(
                "ok",
                (
                    astx.LiteralBoolean(True),
                    astx.LiteralBoolean(False),
                    astx.LiteralBoolean(True),
                ),
            ),
        ),
        type_=schema,
    )


def _declare_dataframe(name: str = "rows") -> astx.VariableDeclaration:
    """
    title: Build one DataFrame variable declaration.
    parameters:
      name:
        type: str
    returns:
      type: astx.VariableDeclaration
    """
    type_ = _dataframe_type()
    return astx.VariableDeclaration(
        name=name,
        type_=type_,
        mutability=astx.MutabilityKind.mutable,
        value=_dataframe_literal(type_),
    )


def test_dataframe_literal_get_struct_exposes_columns() -> None:
    """
    title: DataFrame literal structs expose column payload and schema entries.
    """
    type_ = _dataframe_type()
    node = _dataframe_literal(type_)

    full = node.get_struct()

    assert "DataFrameLiteral" in full
    content = full["DataFrameLiteral"]["content"]
    assert [column["name"] for column in content["columns"]] == [
        "id",
        "score",
        "ok",
    ]
    assert [column["name"] for column in content["type"]] == [
        "id",
        "score",
        "ok",
    ]


def test_dataframe_analysis_records_owner_copy_and_retained_projection() -> (
    None
):
    """
    title: DataFrame expressions and bindings carry complete ownership flow.
    """
    owner = _declare_dataframe("owner")
    owner_read = astx.Identifier("owner")
    copy = astx.VariableDeclaration(
        name="copy",
        type_=_dataframe_type(),
        mutability=astx.MutabilityKind.mutable,
        value=owner_read,
    )
    copy_read = astx.Identifier("copy")
    projection = astx.DataFrameColumnAccess(copy_read, "score")
    release = astx.SeriesRelease(projection)
    module = make_main_module(owner, copy, astx.FunctionReturn(release))

    analyze(module)

    literal_ownership = resource_ownership(owner.value)
    owner_ownership = resource_ownership(owner)
    owner_read_ownership = resource_ownership(owner_read)
    copy_ownership = resource_ownership(copy)
    projection_ownership = resource_ownership(projection)
    assert literal_ownership is not None
    assert literal_ownership.resource_kind is ResourceKind.TABLE
    assert literal_ownership.transfer_kind is OwnershipTransferKind.MOVE
    assert owner_ownership is not None
    assert owner_ownership.kind is OwnershipKind.OWNED
    assert owner_read_ownership is not None
    assert owner_read_ownership.transfer_kind is OwnershipTransferKind.COPY
    assert copy_ownership is not None
    assert copy_ownership.resource_kind is ResourceKind.TABLE
    assert copy_ownership.kind is OwnershipKind.OWNED
    assert projection_ownership is not None
    assert projection_ownership.resource_kind is ResourceKind.CHUNKED_ARRAY
    assert projection_ownership.kind is OwnershipKind.OWNED
    assert projection_ownership.view_kind is ResourceViewKind.RETAINED
    assert projection_ownership.transfer_kind is OwnershipTransferKind.MOVE


def test_dataframe_owned_locals_release_on_return_in_reverse_order() -> None:
    """
    title: DataFrame lexical owners release before a function return.
    """
    owner = _declare_dataframe("owner")
    copy = astx.VariableDeclaration(
        name="copy",
        type_=_dataframe_type(),
        mutability=astx.MutabilityKind.mutable,
        value=astx.Identifier("owner"),
    )
    module = make_main_module(
        owner,
        copy,
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )

    ir_text = Builder().translate(module)

    assert (
        ir_text.count('call i32 @"irx_arrow_table_release"')
        == EXPECTED_DATAFRAME_RELEASE_CALL_COUNT
    )
    assert ir_text.count('call i32 @"irx_arrow_table_retain"') == 1
    last_release = ir_text.rfind('call i32 @"irx_arrow_table_release"')
    assert last_release < ir_text.rfind("ret i32 0")
    assert_ir_parses(ir_text)


def test_dataframe_assignment_retains_input_before_releasing_old_owner() -> (
    None
):
    """
    title: DataFrame replacement should retain its input before old cleanup.
    """
    assignment = astx.VariableAssignment(
        name="target",
        value=astx.Identifier("owner"),
    )
    module = make_main_module(
        _declare_dataframe("owner"),
        _declare_dataframe("target"),
        assignment,
        astx.FunctionReturn(astx.DataFrameRowCount(astx.Identifier("target"))),
        return_type=astx.Int64(),
    )

    ir_text = Builder().translate(module)

    retain_position = ir_text.find('call i32 @"irx_arrow_table_retain"')
    replacement_position = ir_text.find("target_replacement_release_ok")
    assert 0 <= retain_position < replacement_position
    assert "target_replacement_incoming_slot" in ir_text
    assert_ir_parses(ir_text)


def test_dataframe_literal_lowers_through_arrow_table_runtime() -> None:
    """
    title: DataFrame literals lower through the Arrow Table runtime feature.
    """
    module = make_main_module(
        _declare_dataframe(),
        astx.FunctionReturn(astx.DataFrameRowCount(astx.Identifier("rows"))),
        return_type=astx.Int64(),
    )

    ir_text = Builder().translate(module)

    assert '@"irx_arrow_table_new_typed"' in ir_text
    assert '@"irx_arrow_table_num_rows"' in ir_text
    assert '@"irx_arrow_array_builder_new"' in ir_text
    assert_ir_parses(ir_text)


def test_dataframe_column_access_lowers_to_chunked_array_handle() -> None:
    """
    title: Static DataFrame column access lowers to a ChunkedArray handle.
    """
    module = make_main_module(
        _declare_dataframe(),
        astx.FunctionReturn(
            astx.SeriesRelease(
                astx.DataFrameColumnAccess(astx.Identifier("rows"), "score")
            )
        ),
    )

    ir_text = Builder().translate(module)

    assert '@"irx_arrow_table_column_by_index"' in ir_text
    assert '@"irx_arrow_chunked_array_release"' in ir_text
    assert_ir_parses(ir_text)


def test_dataframe_string_access_resolves_static_column_index() -> None:
    """
    title: String-key column access shares static schema resolution.
    """
    module = make_main_module(
        _declare_dataframe(),
        astx.FunctionReturn(
            astx.SeriesRelease(
                astx.DataFrameStringColumnAccess(
                    astx.Identifier("rows"),
                    "id",
                )
            )
        ),
    )

    ir_text = Builder().translate(module)

    assert '@"irx_arrow_table_column_by_index"' in ir_text
    assert '@"irx_arrow_table_column_by_name"' not in ir_text
    assert_ir_parses(ir_text)


def test_dataframe_semantic_rejects_mismatched_column_lengths() -> None:
    """
    title: DataFrame literal columns must have equal row counts.
    """
    type_ = _dataframe_type()
    bad_literal = astx.DataFrameLiteral(
        (
            astx.DataFrameLiteralColumn(
                "id",
                (astx.LiteralInt32(1), astx.LiteralInt32(2)),
            ),
            astx.DataFrameLiteralColumn(
                "score",
                (astx.LiteralFloat64(0.5),),
            ),
            astx.DataFrameLiteralColumn(
                "ok",
                (astx.LiteralBoolean(True), astx.LiteralBoolean(False)),
            ),
        ),
        type_=type_,
    )
    module = make_main_module(
        astx.VariableDeclaration(
            name="rows",
            type_=type_,
            mutability=astx.MutabilityKind.mutable,
            value=bad_literal,
        )
    )

    with pytest.raises(SemanticError, match="same length"):
        analyze(module)


def test_dataframe_semantic_rejects_unknown_column() -> None:
    """
    title: Static schema column access rejects unknown names.
    """
    module = make_main_module(
        _declare_dataframe(),
        astx.FunctionReturn(
            astx.SeriesRelease(
                astx.DataFrameColumnAccess(
                    astx.Identifier("rows"),
                    "missing",
                )
            )
        ),
    )

    with pytest.raises(SemanticError, match="no column 'missing'"):
        analyze(module)


def test_dataframe_class_field_has_destructor_support() -> None:
    """
    title: DataFrame class fields should carry owned destructor metadata.
    """
    field = astx.VariableDeclaration(
        "rows",
        _dataframe_type(),
        mutability=astx.MutabilityKind.mutable,
        value=_dataframe_literal(),
    )
    module = astx.Module()
    module.block.append(
        astx.ClassDefStmt(
            "Container",
            attributes=(field,),
        )
    )

    analyze(module)
    ownership = resource_ownership(field)
    assert ownership is not None
    assert ownership.kind is OwnershipKind.OWNED
    assert ownership.resource_kind is ResourceKind.TABLE

    ir_text = Builder().translate(module)
    assert "Container__destroy" in ir_text
    assert 'call i32 @"irx_arrow_table_release"' in ir_text
    assert_ir_parses(ir_text)


def test_dataframe_build_returns_row_count() -> None:
    """
    title: Built DataFrame programs return Arrow Table row counts.
    """
    if shutil.which("clang") is None:
        pytest.skip("builder.build() currently requires clang")

    module = make_main_module(
        _declare_dataframe(),
        astx.FunctionReturn(
            astx.Cast(
                astx.DataFrameRowCount(astx.Identifier("rows")),
                astx.Int32(),
            )
        ),
    )

    result = build_and_run(Builder(), module)

    assert result.returncode == EXPECTED_ROW_OR_COLUMN_COUNT, (
        result.stderr or result.stdout
    )


def test_dataframe_build_releases_accessed_series_and_returns_ncols() -> None:
    """
    title: Built DataFrame programs can acquire and release Series handles.
    """
    if shutil.which("clang") is None:
        pytest.skip("builder.build() currently requires clang")

    module = make_main_module(
        _declare_dataframe(),
        astx.SeriesRelease(
            astx.DataFrameColumnAccess(astx.Identifier("rows"), "score")
        ),
        astx.SeriesRelease(
            astx.DataFrameStringColumnAccess(astx.Identifier("rows"), "id")
        ),
        astx.FunctionReturn(
            astx.Cast(
                astx.DataFrameColumnCount(astx.Identifier("rows")),
                astx.Int32(),
            )
        ),
    )

    result = build_and_run(Builder(), module)

    assert result.returncode == EXPECTED_ROW_OR_COLUMN_COUNT, (
        result.stderr or result.stdout
    )
