"""
title: Native convenience I/O, chunk ownership, configuration and errors.
"""

import ctypes
import subprocess
import sys

from dataclasses import FrozenInstanceError
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from irx import table_io
from irx.parquet_options import ParquetOptions
from irx.record_batch import RecordBatchStreamReader
from irx.table_io import (
    ParquetFilter,
    import_table,
    read_csv,
    read_parquet,
    table_library,
    where,
    write_csv,
    write_parquet,
)
from typeguard import TypeCheckError


def test_csv_chunks_projection_and_ownership(tmp_path: Path) -> None:
    """
    title: Eager reads preserve every batch and independent table ownership.
    parameters:
      tmp_path:
        type: Path
    """
    source = tmp_path / "input.csv"
    source.write_text(
        'id,text\n1,"λ"\n2,""\n3,\n4,NA\n5,NULL\n', encoding="utf-8"
    )
    schema = pa.schema([("id", pa.int64()), ("text", pa.string())])
    table = read_csv(source, schema=schema, block_size=16)
    assert table.column(0).num_chunks > 1
    assert table.to_pydict() == {
        "id": [1, 2, 3, 4, 5],
        "text": ["λ", "", None, "NA", "NULL"],
    }
    projected = read_csv(
        source, schema=schema, columns=["text", "id"], block_size=16
    )
    assert projected.column_names == ["text", "id"]
    source.unlink()
    target = tmp_path / "out.csv"
    write_csv(table, target)
    assert read_csv(target, schema=schema).equals(table)
    assert table.num_rows == len([1, 2, 3, 4, 5])


def test_csv_controls_and_headerless_names(tmp_path: Path) -> None:
    """
    title: Named CSV controls map to the native reader without a second parser.
    parameters:
      tmp_path:
        type: Path
    """
    source = tmp_path / "input.csv"
    source.write_text("ignored\n1;'a;λ'\n\n2;NULL\n3;''\n", encoding="utf-8")
    table = read_csv(
        source,
        header=False,
        names=["id", "text"],
        delimiter=";",
        quotechar="'",
        skiprows=1,
        skip_blank_lines=True,
        null_values=["NULL"],
    )
    assert table.to_pydict() == {"id": [1, 2, 3], "text": ["a;λ", None, ""]}
    source.write_text("text\n'a\\'b'\n", encoding="utf-8")
    assert read_csv(
        source, quotechar="'", doublequote=False, escapechar="\\"
    ).column(0).to_pylist() == ["a'b"]
    source.write_text('text\n\n""\n', encoding="utf-8")
    assert read_csv(
        source, schema=pa.schema([("text", pa.string())]), null_values=[]
    ).column(0).to_pylist() == ["", ""]


def test_csv_projection_does_not_hide_bad_source(tmp_path: Path) -> None:
    """
    title: Unselected columns still undergo full declared parsing and checks.
    parameters:
      tmp_path:
        type: Path
    """
    source = tmp_path / "input.csv"
    source.write_text("id,bad\n1,not-an-integer\n")
    with pytest.raises(RuntimeError, match=r"conversion|invalid"):
        read_csv(
            source,
            schema=pa.schema([("id", pa.int64()), ("bad", pa.int64())]),
            columns=["id"],
        )


@pytest.mark.parametrize("quoting", ["needed", "all_valid", "none"])
def test_csv_writer_options(tmp_path: Path, quoting: str) -> None:
    """
    title: Writers expose supported quoting, EOL, null and delimiter controls.
    parameters:
      tmp_path:
        type: Path
      quoting:
        type: str
    """
    target = tmp_path / "output.csv"
    table = pa.table({"text": ["abc", None, "λ"]})
    write_csv(
        table,
        target,
        delimiter=";",
        lineterminator="\r\n",
        na_rep="NULL",
        quoting=quoting,
    )
    assert b"\r\n" in target.read_bytes()
    assert read_csv(target, null_values=["NULL"]).equals(table)


@pytest.mark.parametrize(
    "settings",
    [
        {"columns": []},
        {"columns": ["id", "id"]},
        {"columns": ["missing"]},
        {"names": []},
        {"names": ["id"]},
        {"delimiter": "::"},
        {"quotechar": ","},
        {"escapechar": ","},
        {"block_size": 0},
        {"skiprows": -1},
        {"skiprows": 2**63},
        {"columns": ["id\0"]},
    ],
)
def test_csv_rejects_invalid_settings(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    """
    title: Bad selectors and options fail explicitly instead of being ignored.
    parameters:
      tmp_path:
        type: Path
      settings:
        type: dict[str, object]
    """
    source = tmp_path / "input.csv"
    source.write_text("id\n1\n")
    with pytest.raises((ValueError, RuntimeError, TypeError, OverflowError)):
        read_csv(source, **settings)


def test_csv_validation_precedes_truncation(tmp_path: Path) -> None:
    """
    title: Invalid writer options or unsupported types do not destroy output.
    parameters:
      tmp_path:
        type: Path
    """
    target = tmp_path / "output.csv"
    target.write_text("keep")
    with pytest.raises(RuntimeError, match="na_rep"):
        write_csv(pa.table({"id": [1]}), target, na_rep="a,b")
    assert target.read_text() == "keep"
    with pytest.raises(RuntimeError, match=r"[Uu]nsupported"):
        write_csv(pa.table({"nested": [[1, 2]]}), target)
    assert target.read_text() == "keep"


def test_empty_tables_keep_schema(tmp_path: Path) -> None:
    """
    title: Schema-only results are owned, serializable tables rather than EOF.
    parameters:
      tmp_path:
        type: Path
    """
    table = pa.table({"id": pa.array([], type=pa.int64())})
    csv = tmp_path / "empty.csv"
    write_csv(table, csv)
    assert read_csv(csv, schema=table.schema).equals(table)
    parquet = tmp_path / "empty.parquet"
    write_parquet(table, parquet)
    assert read_parquet(parquet).equals(table)


def test_parquet_nested_chunks_and_schema(tmp_path: Path) -> None:
    """
    title: >-
      Whole-file bridges preserve uneven chunks, nested values and metadata.
    parameters:
      tmp_path:
        type: Path
    """
    schema = pa.schema(
        [
            pa.field("id", pa.int64(), nullable=False),
            pa.field("values", pa.list_(pa.int32())),
        ],
        metadata={b"source": b"table"},
    )
    table = pa.Table.from_arrays(
        [
            pa.chunked_array([[1], [2, 3, 4]], type=pa.int64()),
            pa.chunked_array(
                [[[1], None], [[], [4, 5]]], type=pa.list_(pa.int32())
            ),
        ],
        schema=schema,
    )
    path = tmp_path / "nested.parquet"
    write_parquet(table, path, row_group_size=1)
    loaded = read_parquet(path, schema=schema, batch_size=1)
    assert loaded.equals(table, check_metadata=True)
    assert loaded.column(0).num_chunks == table.num_rows
    expected_chunks = 2
    assert table.column(0).num_chunks == expected_chunks
    with pytest.raises(RuntimeError, match="schema"):
        read_parquet(path, schema=schema.with_metadata({b"source": b"wrong"}))


def test_parquet_filters_options_and_groups(tmp_path: Path) -> None:
    """
    title: >-
      Predicates filter rows, snapshots do not mutate, and defaults override.
    parameters:
      tmp_path:
        type: Path
    """
    table = pa.table(
        {
            "id": [1, 2, 3, 4],
            "name": ["a", "b", "c", "d"],
            "active": [True, False, True, None],
        }
    )
    path = tmp_path / "data.parquet"
    options = ParquetOptions(compression="gzip", row_group_size=4)
    write_parquet(
        table, path, options=options, compression="snappy", row_group_size=1
    )
    assert options.compression == "gzip"
    assert (
        pq.ParquetFile(path).metadata.row_group(0).column(0).compression
        == "SNAPPY"
    )
    first = where("id", ">=", 2)
    combined = first.and_where("active", "==", True)
    assert combined.predicates == (
        *first.predicates,
        *where("active", "==", True).predicates,
    )
    assert len(first.predicates) == 1
    assert read_parquet(
        path, columns=["name"], filters=combined
    ).to_pydict() == {"name": ["c"]}
    assert read_parquet(path, filters=where("active", "is_null")).column(
        "id"
    ).to_pylist() == [4]
    assert read_parquet(path, row_groups=[1, 3]).column("id").to_pylist() == [
        2,
        4,
    ]
    read_options = ParquetOptions(
        columns=("id",), batch_size=1, predicates=first.predicates
    )
    assert read_parquet(
        path,
        options=read_options,
        columns=["name"],
        filters=where("id", "==", 1),
        batch_size=65536,
    ).to_pydict() == {"name": ["a"]}
    assert read_options.columns == ("id",)
    assert read_options.predicates == first.predicates
    with pytest.raises(FrozenInstanceError):
        combined.predicates = ()


@pytest.mark.parametrize(
    "settings",
    [
        {"columns": []},
        {"row_groups": []},
        {"row_groups": [0, 0]},
        {"row_groups": [-1]},
        {"columns": ["id", "id"]},
        {"batch_size": 0},
        {"options": ParquetOptions(atomic=True)},
    ],
)
def test_parquet_rejects_invalid_settings(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    """
    title: Invalid or wrong-mode Parquet options fail instead of falling back.
    parameters:
      tmp_path:
        type: Path
      settings:
        type: dict[str, object]
    """
    path = tmp_path / "data.parquet"
    write_parquet(pa.table({"id": [1]}), path)
    with pytest.raises((RuntimeError, ValueError, TypeError)):
        read_parquet(path, **settings)


def test_parquet_dataset_discovery_and_transactions(tmp_path: Path) -> None:
    """
    title: Directory discovery and local atomic writes reuse the native engine.
    parameters:
      tmp_path:
        type: Path
    """
    table = pa.table({"id": [1, 2, 3], "group": ["a", "b", "a"]})
    root = tmp_path / "dataset"
    write_parquet(table, root, partition_columns=["group"], atomic=True)
    loaded = read_parquet(root)
    assert sorted(loaded.column("id").to_pylist()) == [1, 2, 3]
    with pytest.raises(RuntimeError):
        read_parquet(root, options=ParquetOptions())
    target = tmp_path / "atomic.parquet"
    write_parquet(table, target, atomic=True, durable=True)
    write_parquet(table, target, atomic=True, append=True)
    assert read_parquet(target).num_rows == table.num_rows * 2


@pytest.mark.parametrize(
    "operation,value", [("in", 1), ("eq", 1), ("==", None), ("is_null", 1)]
)
def test_predicate_validation(operation: str, value: int | None) -> None:
    """
    title: Unsupported filter syntax and missing or extra values are rejected.
    parameters:
      operation:
        type: str
      value:
        type: int | None
    """
    with pytest.raises(ValueError):
        where("id", operation, value)


def test_table_failure_slots_are_null() -> None:
    """
    title: Native table errors never leave a plausible output pointer behind.
    """
    lib = table_library()
    lib.irx_rb_table_project.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.irx_rb_table_project.restype = ctypes.c_int
    with import_table(pa.table({"id": [1]}), lib) as table:
        output = ctypes.c_void_p(123)
        assert (
            lib.irx_rb_table_project(table, None, 0, ctypes.byref(output)) < 0
        )
        assert output.value is None


def test_filter_collection_items_and_scalars() -> None:
    """
    title: Public constructors check every item and reject unsupported scalars.
    """
    first = where("id", "==", 1)
    with pytest.raises(TypeCheckError):
        ParquetFilter((*first.predicates, object()))
    with pytest.raises(TypeCheckError):
        where("id", "==", [1])
    for invalid in [float("nan"), float("inf"), 2**63]:
        with pytest.raises(ValueError):
            where("id", "==", invalid)


def test_csv_helpers_without_optional_parquet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    title: >-
      CSV convenience operations never request the optional Parquet plugin.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """

    def unavailable() -> ctypes.CDLL:
        """
        title: Fail immediately on optional runtime activation.
        returns:
          type: ctypes.CDLL
        """
        raise AssertionError("CSV activated Parquet")

    monkeypatch.setattr(table_io, "parquet_library", unavailable)
    path = tmp_path / "only.csv"
    frame = pa.table({"id": [1, 2]})
    write_csv(frame, path)
    assert read_csv(path).equals(frame)


def test_table_import_is_lazy() -> None:
    """
    title: Importing table helpers does not open or compile native libraries.
    """
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import pyarrow
from unittest.mock import patch
with patch("ctypes.CDLL", side_effect=AssertionError("native load on import")):
    from irx.table_io import read_csv, read_parquet, where
    assert len(where("id", "==", 1).predicates) == 1
""",
        ],
        check=True,
        timeout=30,
    )


def test_table_helpers_reject_stale_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: A library without table symbols gives an actionable error.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    process = ctypes.CDLL(None)
    monkeypatch.setattr(table_io, "c_data_library", lambda: process)
    with pytest.raises(RuntimeError, match=r"rebuild.*unset"):
        table_library()


def test_late_csv_corruption_returns_no_partial_table(tmp_path: Path) -> None:
    """
    title: A conversion error after valid blocks does not return partial rows.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "late.csv"
    path.write_text("id\n" + "1\n" * 64 + "invalid\n")
    with pytest.raises(RuntimeError, match=r"conversion|invalid"):
        read_csv(path, schema=pa.schema([("id", pa.int64())]), block_size=16)


@pytest.mark.parametrize(
    "field",
    [
        pa.field("bad\0name", pa.int32()),
        pa.field("nested", pa.list_(pa.field("bad\0child", pa.int32()))),
        pa.field("stamp", pa.timestamp("us", tz="UTC\0bad")),
    ],
)
def test_table_writers_reject_lossy_c_schemas(
    tmp_path: Path,
    field: pa.Field,
) -> None:
    """
    title: C Stream interchange never truncates names or timezone formats.
    parameters:
      tmp_path:
        type: Path
      field:
        type: pa.Field
    """
    table = pa.Table.from_arrays(
        [pa.array([], type=field.type)], schema=pa.schema([field])
    )
    path = tmp_path / "sentinel"
    path.write_bytes(b"preserve")
    for write in (write_csv, write_parquet):
        with pytest.raises(ValueError, match="NUL"):
            write(table, path)
        assert path.read_bytes() == b"preserve"


def test_native_table_bridge_rejects_lossy_ipc_names(tmp_path: Path) -> None:
    """
    title: Native table construction validates names before exporting a stream.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "bad.arrow"
    table = pa.table({"bad\0name": [1]})
    with pa.ipc.new_stream(path, table.schema) as writer:
        writer.write_table(table)
    lib = table_library()
    lib.irx_rb_reader_read_table.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    lib.irx_rb_reader_read_table.restype = ctypes.c_int
    with RecordBatchStreamReader.open_file(path) as reader:
        output = ctypes.c_void_p(123)
        assert (
            lib.irx_rb_reader_read_table(reader._handle, ctypes.byref(output))
            < 0
        )
        assert output.value is None
        assert b"NUL" in lib.irx_record_batch_errmsg()
