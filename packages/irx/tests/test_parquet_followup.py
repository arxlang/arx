"""
title: Native advanced Parquet scans, recursive schemas and commit contracts.
"""

import ctypes
import subprocess
import sys

from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from irx.builder.runtime.record_batch import (
    build_parquet_runtime_feature,
    build_record_batch_runtime_feature,
)
from irx.record_batch import (
    Parquet,
    ParquetOptions,
    ParquetPredicate,
    RecordBatch,
    RecordBatchSchema,
    RecordBatchStreamReader,
    RecordBatchStreamWriter,
)
from irx.record_batch_abi import ArrowArray, ArrowSchema
from pyarrow.cffi import ffi
from typeguard import TypeCheckError

RICH_CASES = [
    (pa.binary(), [b"\0\xff", None, b""]),
    (pa.large_binary(), [b"a", None, b"b"]),
    (pa.binary(2), [b"ab", None, b"cd"]),
    (pa.decimal128(8, 2), [Decimal("1.20"), None, Decimal("-12.30")]),
    (pa.decimal256(50, 3), [Decimal("1.234"), None, Decimal("-12.345")]),
    (pa.list_(pa.binary()), [[b"a", None], None, []]),
    (pa.large_list(pa.int32()), [[1, None], None, []]),
    (pa.list_(pa.int32(), 2), [[1, None], [None, None], [2, 3]]),
    (
        pa.struct([("x", pa.int32()), ("s", pa.string())]),
        [{"x": 1, "s": "λ"}, None, {"x": None, "s": ""}],
    ),
    (pa.map_(pa.string(), pa.int64()), [[("k", 1)], None, []]),
    (pa.dictionary(pa.int8(), pa.string()), ["a", None, "b"]),
    (pa.dictionary(pa.int32(), pa.binary()), [b"a", None, b"b"]),
    (pa.uuid(), [b"0" * 16, None, b"1" * 16]),
    (pa.json_(), ['{"k":1}', None, "[]"]),
    (pa.null(), [None, None, None]),
    (
        pa.list_(pa.struct([("s", pa.list_(pa.string()))])),
        [[{"s": ["x", None]}], None, []],
    ),
]


def write_batch(
    path: Path, batch: pa.RecordBatch, options: ParquetOptions | None = None
) -> None:
    """
    title: Write through the public native facade and release input references.
    parameters:
      path:
        type: Path
      batch:
        type: pa.RecordBatch
      options:
        type: ParquetOptions | None
    """
    schema = RecordBatchSchema.from_arrow(batch.schema)
    native = RecordBatch.from_arrow(batch)
    try:
        with Parquet() as target:
            target.open_write(path, schema, options=options)
            target.write_batch(native)
    finally:
        native.release()
        schema.release()


def read_batches(
    path: Path | str, options: ParquetOptions | None = None
) -> list[pa.RecordBatch]:
    """
    title: Materialize only in tests, retaining independent exported snapshots.
    parameters:
      path:
        type: Path | str
      options:
        type: ParquetOptions | None
    returns:
      type: list[pa.RecordBatch]
    """
    with Parquet() as source:
        source.open_read(path, options=options)
        return [batch.to_arrow() for batch in source]


@pytest.mark.parametrize(("kind", "values"), RICH_CASES, ids=str)
def test_recursive_roundtrip(
    tmp_path: Path, kind: pa.DataType, values: list[object]
) -> None:
    """
    title: Preserve recursive types, nulls, user metadata and owned snapshots.
    parameters:
      tmp_path:
        type: Path
      kind:
        type: pa.DataType
      values:
        type: list[object]
    """
    schema = pa.schema(
        [pa.field("value", kind, metadata={b"field": b"value"})],
        metadata={b"user": b"metadata"},
    )
    batch = pa.record_batch([pa.array(values, type=kind)], schema=schema)
    path = tmp_path / "rich.parquet"
    write_batch(path, batch)
    with Parquet() as source:
        source.open_read(path)
        snapshot = source.schema()
        saved = snapshot.to_arrow()
        snapshot.release()
    assert saved.equals(schema, check_metadata=True)
    result = pa.Table.from_batches(read_batches(path)).combine_chunks()
    assert result.equals(pa.Table.from_batches([batch]), check_metadata=True)


def test_projection_filter_and_row_groups(tmp_path: Path) -> None:
    """
    title: Push down a conjunction while preserving projection and group order.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "scan.parquet"
    pq.write_table(
        pa.table({"x": list(range(20)), "s": ["v"] * 20}),
        path,
        row_group_size=4,
    )
    options = ParquetOptions(
        columns=("s", "x"),
        row_groups=(3, 1),
        predicates=(ParquetPredicate("x", "gt", 5),),
        batch_size=3,
    )
    batches = read_batches(path, options)
    assert all(batch.num_rows <= options.batch_size for batch in batches)
    result = pa.Table.from_batches(batches)
    assert result.column_names == ["s", "x"]
    assert result["x"].to_pylist() == [12, 13, 14, 15, 6, 7]
    with pytest.raises(RuntimeError, match=r"row group|Row group"):
        read_batches(path, ParquetOptions(row_groups=(99,)))
    with pytest.raises(RuntimeError, match="duplicate"):
        read_batches(path, ParquetOptions(columns=("x", "x")))
    with pytest.raises(RuntimeError):
        read_batches(path, ParquetOptions(columns=("missing",)))


@pytest.mark.parametrize(
    "kind, expected",
    [
        (pa.date64(), pa.date32()),
        (pa.timestamp("s"), pa.timestamp("ms")),
        (pa.time32("s"), pa.time32("ms")),
    ],
)
def test_explicit_temporal_normalization(
    tmp_path: Path, kind: pa.DataType, expected: pa.DataType
) -> None:
    """
    title: Normalize explicitly, reporting the physical output type on read.
    parameters:
      tmp_path:
        type: Path
      kind:
        type: pa.DataType
      expected:
        type: pa.DataType
    """
    values = [0, None, 86400000 if pa.types.is_date64(kind) else 1]
    batch = pa.record_batch([pa.array(values, type=kind)], names=["time"])
    path = tmp_path / "time.parquet"
    write_batch(path, batch, ParquetOptions(normalize=True))
    actual = pq.read_table(path)
    assert actual.schema.field(0).type == expected
    assert actual[0].to_pylist() == batch[0].to_pylist()


@pytest.mark.parametrize(
    "kind, value",
    [
        (pa.date64(), 1),
        (pa.timestamp("s"), (1 << 63) - 1),
    ],
)
def test_normalization_failure_preserves_destination(
    tmp_path: Path, kind: pa.DataType, value: int
) -> None:
    """
    title: Reject truncation and overflow without committing partial output.
    parameters:
      tmp_path:
        type: Path
      kind:
        type: pa.DataType
      value:
        type: int
    """
    path = tmp_path / "destination"
    path.write_bytes(b"original")
    batch = pa.record_batch([pa.array([value], type=kind)], names=["x"])
    with pytest.raises(RuntimeError):
        write_batch(path, batch, ParquetOptions(normalize=True, atomic=True))
    assert path.read_bytes() == b"original"
    assert not list(tmp_path.glob("*.irx-*"))


def test_atomic_append_and_abort(tmp_path: Path) -> None:
    """
    title: Rewrite append and exceptional cleanup never publish partial output.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "atomic.parquet"
    batch = pa.record_batch([pa.array([1, 2])], names=["x"])
    write_batch(path, batch, ParquetOptions(atomic=True))
    write_batch(path, batch, ParquetOptions(append=True, row_group_size=2))
    assert pq.read_table(path)[0].to_pylist() == [1, 2, 1, 2]
    before = path.read_bytes()
    schema = RecordBatchSchema.from_arrow(batch.schema)
    native = RecordBatch.from_arrow(batch)
    try:
        with pytest.raises(ValueError, match="abort"):
            with Parquet() as output:
                output.open_write(
                    path, schema, options=ParquetOptions(atomic=True)
                )
                output.write_batch(native)
                raise ValueError("abort")
    finally:
        schema.release()
        native.release()
    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.irx-*"))


@pytest.mark.parametrize(
    "codec, level", [("gzip", 2), ("zstd", 3), ("brotli", 4)]
)
def test_codec_settings(tmp_path: Path, codec: str, level: int) -> None:
    """
    title: >-
      Configure only available codecs and validate levels before truncation.
    parameters:
      tmp_path:
        type: Path
      codec:
        type: str
      level:
        type: int
    """
    if not pa.Codec.is_available(codec):
        pytest.skip("codec absent from this Arrow build")
    path = tmp_path / "codec.parquet"
    batch = pa.record_batch([pa.array([1, 2, 3])], names=["x"])
    write_batch(
        path,
        batch,
        ParquetOptions(
            compression=codec,
            compression_level=level,
            use_threads=True,
            data_page_size=512,
        ),
    )
    assert pq.read_table(path).num_rows == batch.num_rows
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="compression_level"):
        write_batch(
            path,
            batch,
            ParquetOptions(compression=codec, compression_level=10000),
        )
    assert path.read_bytes() == before


def test_encrypted_file(tmp_path: Path) -> None:
    """
    title: >-
      Native footer-key encryption rejects missing/wrong keys and reads back.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "encrypted.parquet"
    batch = pa.record_batch([pa.array([1, None, 3])], names=["x"])
    key = b"0123456789abcdef"
    options = ParquetOptions(encryption_key=key)
    assert "012345" not in repr(options)
    write_batch(path, batch, options)
    for wrong in (None, b"fedcba9876543210"):
        with pytest.raises(RuntimeError):
            read_batches(path, ParquetOptions(encryption_key=wrong))
    assert read_batches(path, options)[0].equals(batch)
    with pytest.raises(RuntimeError, match="AES key"):
        write_batch(path, batch, ParquetOptions(encryption_key=b"short"))
    assert read_batches(path, options)[0].equals(batch)


def test_hive_dataset_and_evolution(tmp_path: Path) -> None:
    """
    title: Inspect every fragment; union only compatible fields under opt-in.
    parameters:
      tmp_path:
        type: Path
    """
    a, b = tmp_path / "part=a", tmp_path / "part=b"
    a.mkdir()
    b.mkdir()
    pq.write_table(pa.table({"x": [1, 2]}), a / "a.parquet")
    pq.write_table(pa.table({"x": [3], "extra": ["yes"]}), b / "b.parquet")
    with pytest.raises(RuntimeError, match="schemas differ"):
        read_batches(tmp_path, ParquetOptions(dataset=True, hive=True))
    batches = read_batches(
        tmp_path,
        ParquetOptions(
            dataset=True,
            hive=True,
            unify=True,
            columns=("part", "x", "extra"),
            predicates=(ParquetPredicate("x", "gt", 1),),
        ),
    )
    result = pa.Table.from_batches(batches)
    assert result.to_pydict() == {
        "part": ["a", "b"],
        "x": [2, 3],
        "extra": [None, "yes"],
    }
    pq.write_table(pa.table({"x": ["incompatible"]}), b / "c.parquet")
    with pytest.raises(RuntimeError):
        read_batches(tmp_path, ParquetOptions(dataset=True, unify=True))


def test_file_uri_and_unknown_backend(tmp_path: Path) -> None:
    """
    title: Route URI I/O through Arrow and never fall back to a local filename.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "uri.parquet"
    batch = pa.record_batch([pa.array([1])], names=["x"])
    write_batch(path, batch)
    assert read_batches(path.as_uri())[0].equals(batch)
    with pytest.raises(RuntimeError):
        read_batches("unsupported-backend://bucket/file")


def test_required_nested_child(tmp_path: Path) -> None:
    """
    title: >-
      Required children reject real nulls but not storage masked by a parent.
    parameters:
      tmp_path:
        type: Path
    """
    child = pa.field("x", pa.int64(), nullable=False)
    array = pa.StructArray.from_arrays(
        [pa.array([None, 1])], fields=[child], mask=pa.array([True, False])
    )
    good = pa.record_batch([array], names=["record"])
    write_batch(tmp_path / "good", good)
    bad = pa.record_batch(
        [
            pa.StructArray.from_arrays(
                [pa.array([None], type=pa.int64())], fields=[child]
            )
        ],
        names=["record"],
    )
    with pytest.raises(RuntimeError, match="not nullable"):
        write_batch(tmp_path / "bad", bad)


def test_partitioned_write_append_and_empty(tmp_path: Path) -> None:
    """
    title: >-
      Native dataset writes preserve partition types and use fresh fragments.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "dataset"
    batch = pa.record_batch(
        [pa.array([1, 2, 3]), pa.array([7, 8, 7], type=pa.uint64())],
        names=["value", "group"],
    )
    options = ParquetOptions(
        dataset=True, hive=True, partition_columns=("group",)
    )
    write_batch(path, batch, options)
    write_batch(
        path,
        batch,
        ParquetOptions(
            dataset=True, hive=True, partition_columns=("group",), append=True
        ),
    )
    result = pa.Table.from_batches(
        read_batches(path, ParquetOptions(dataset=True, hive=True))
    )
    assert result.schema.field("group").type == pa.uint64()
    assert sorted(result["value"].to_pylist()) == [1, 1, 2, 2, 3, 3]
    with pytest.raises(RuntimeError, match="exists"):
        write_batch(path, batch, options)
    empty = tmp_path / "empty"
    write_batch(empty, batch.slice(0, 0), options)
    with Parquet() as source:
        source.open_read(
            empty, options=ParquetOptions(dataset=True, hive=True)
        )
        schema = source.schema()
        assert schema.to_arrow().equals(batch.schema, check_metadata=True)
        schema.release()
        assert source.next_batch() is None


def test_fixed_list_null_parent_is_rejected(tmp_path: Path) -> None:
    """
    title: >-
      Reject a backend-unreadable representation rather than emit a bad file.
    parameters:
      tmp_path:
        type: Path
    """
    batch = pa.record_batch(
        [pa.array([None], type=pa.list_(pa.int32(), 2))], names=["x"]
    )
    with pytest.raises(RuntimeError, match="fixed-size list null parents"):
        write_batch(
            tmp_path / "fixed.parquet", batch, ParquetOptions(atomic=True)
        )
    assert not (tmp_path / "fixed.parquet").exists()


def test_base_runtime_does_not_link_parquet() -> None:
    """
    title: The base RecordBatch feature has no format-specific dependencies.
    """
    base = build_record_batch_runtime_feature()
    optional = build_parquet_runtime_feature()
    assert not any(
        "parquet" in artifact.path.name for artifact in base.artifacts
    )
    assert not any(
        "parquet" in flag or "arrow_dataset" in flag
        for flag in base.linker_flags
    )
    assert optional.dependencies == ("record_batch",)
    assert "irx_rb_parquet_reader_open" in optional.symbols
    assert "irx_rb_parquet_reader_open" not in base.symbols


@pytest.mark.parametrize(
    "options",
    [
        ParquetOptions(batch_size=True),
        ParquetOptions(row_groups=(-1,)),
        ParquetOptions(columns=("x\0y",)),
        ParquetOptions(compression_level=1),
    ],
)
def test_invalid_options_do_not_truncate(
    tmp_path: Path, options: ParquetOptions
) -> None:
    """
    title: >-
      Reject integer narrowing, invalid text and unsupported codec options.
    parameters:
      tmp_path:
        type: Path
      options:
        type: ParquetOptions
    """
    path = tmp_path / "existing"
    path.write_bytes(b"sentinel")
    batch = pa.record_batch([pa.array([1])], names=["x"])
    with pytest.raises((RuntimeError, ValueError, TypeError)):
        write_batch(path, batch, options)
    assert path.read_bytes() == b"sentinel"


def test_options_validate_collection_items() -> None:
    """
    title: Collection item checks do not stop after the first valid item.
    """
    with pytest.raises(TypeCheckError):
        ParquetOptions(columns=("valid", 7))  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        ParquetOptions(row_groups=(1, "2"))  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        ParquetOptions(encryption_key="not bytes")  # type: ignore[arg-type]


def test_evolution_rejects_missing_required_and_different_types(
    tmp_path: Path,
) -> None:
    """
    title: >-
      Schema evolution must not synthesize nulls in required fields or promote
      types.
    parameters:
      tmp_path:
        type: Path
    """
    options = ParquetOptions(dataset=True, unify=True)
    pq.write_table(pa.table({"x": [1]}), tmp_path / "a.parquet")
    required = pa.schema(
        [
            pa.field("x", pa.int64()),
            pa.field("extra", pa.int64(), nullable=False),
        ]
    )
    pq.write_table(
        pa.Table.from_arrays([pa.array([2]), pa.array([3])], schema=required),
        tmp_path / "b.parquet",
    )
    with pytest.raises(RuntimeError, match="must be nullable"):
        read_batches(tmp_path, options)
    pq.write_table(pa.table({"x": [None]}), tmp_path / "b.parquet")
    with pytest.raises(RuntimeError, match="types differ"):
        read_batches(tmp_path, options)


def test_predicate_runtime_validation() -> None:
    """
    title: Never turn an unsupported predicate value into a string comparison.
    """
    with pytest.raises(TypeCheckError):
        ParquetPredicate("x", "eq", [1])  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        ParquetPredicate("x", "invalid", 1)  # type: ignore[arg-type]


def test_unregistered_extension_is_not_silently_erased(tmp_path: Path) -> None:
    """
    title: >-
      Unknown extensions retain their opaque storage and extension metadata.
    parameters:
      tmp_path:
        type: Path
    """
    schema = pa.schema(
        [
            pa.field(
                "x",
                pa.int32(),
                metadata={
                    b"ARROW:extension:name": b"unknown.example",
                    b"ARROW:extension:metadata": b"",
                },
            )
        ]
    )
    batch = pa.record_batch([pa.array([1], type=pa.int32())], schema=schema)
    path = tmp_path / "opaque.parquet"
    write_batch(path, batch)
    result = pa.Table.from_batches(read_batches(path))
    assert result.equals(pa.Table.from_batches([batch]), check_metadata=True)


def test_arrow_snapshots_validate_and_outlive_native_owners() -> None:
    """
    title: >-
      C Data snapshots own references and reject released or mistyped inputs.
    """
    original = pa.record_batch([pa.array([[b"value"]])], names=["x"])
    schema = RecordBatchSchema.from_arrow(original.schema)
    batch = RecordBatch.from_arrow(original)
    saved_schema, saved_batch = schema.to_arrow(), batch.to_arrow()
    schema.release()
    batch.release()
    schema.release()
    batch.release()
    assert saved_schema.equals(original.schema)
    assert saved_batch.equals(original)
    with pytest.raises(RuntimeError, match="released"):
        schema.to_arrow()
    with pytest.raises(RuntimeError, match="released"):
        batch.to_arrow()
    with pytest.raises(TypeCheckError):
        RecordBatch.from_arrow(pa.table({"x": [1]}))  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        RecordBatchSchema.from_arrow(["x"])  # type: ignore[arg-type]


def test_raw_atomic_schema_failure_cannot_commit_on_close(
    tmp_path: Path,
) -> None:
    """
    title: Schema rejection poisons the raw writer, not only the Python facade.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "unchanged"
    path.write_bytes(b"sentinel")
    schema = RecordBatchSchema.from_arrow(pa.schema([("x", pa.int64())]))
    wrong = RecordBatch.from_arrow(
        pa.record_batch([pa.array([1])], names=["y"])
    )
    writer = RecordBatchStreamWriter.open_parquet(
        schema, path, options=ParquetOptions(atomic=True)
    )
    try:
        with pytest.raises(RuntimeError, match="schema"):
            writer.write_batch(wrong)
        with pytest.raises(RuntimeError, match="schema"):
            writer.close()
        assert path.read_bytes() == b"sentinel"
        assert not list(tmp_path.glob("*.irx-*"))
    finally:
        writer.release()
        wrong.release()
        schema.release()


def test_raw_atomic_context_abandons_on_exception(tmp_path: Path) -> None:
    """
    title: >-
      The generic stream writer must not commit an exceptional atomic context.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "unchanged"
    path.write_bytes(b"sentinel")
    original = pa.record_batch([pa.array([1])], names=["x"])
    schema = RecordBatchSchema.from_arrow(original.schema)
    batch = RecordBatch.from_arrow(original)
    try:
        with pytest.raises(ValueError, match="cancel"):
            with RecordBatchStreamWriter.open_parquet(
                schema, path, options=ParquetOptions(atomic=True)
            ) as writer:
                writer.write_batch(batch)
                raise ValueError("cancel")
        assert path.read_bytes() == b"sentinel"
        assert not list(tmp_path.glob("*.irx-*"))
    finally:
        batch.release()
        schema.release()


def test_hive_string_partition_contract(tmp_path: Path) -> None:
    """
    title: Preserve partition order, metadata, nulls and escaped string values.
    parameters:
      tmp_path:
        type: Path
    """
    schema = pa.schema(
        [
            pa.field("part", pa.string(), metadata={b"kind": b"partition"}),
            pa.field("id", pa.int64()),
        ],
        metadata={b"dataset": b"example"},
    )
    values = ["", None, "a/b", "%", "é", "x=y"]
    batch = pa.record_batch(
        [pa.array(values), pa.array(range(len(values)))], schema=schema
    )
    options = ParquetOptions(
        dataset=True, hive=True, partition_columns=("part",)
    )
    path = tmp_path / "dataset"
    write_batch(path, batch, options)
    actual = pa.Table.from_batches(
        read_batches(path, ParquetOptions(dataset=True, hive=True))
    )
    assert actual.schema.equals(schema, check_metadata=True)
    assert actual.sort_by("id").equals(
        pa.Table.from_batches([batch]), check_metadata=True
    )
    reserved = pa.record_batch(
        [pa.array(["__HIVE_DEFAULT_PARTITION__"]), pa.array([0])],
        schema=schema,
    )
    with pytest.raises(RuntimeError, match="reserved Hive null marker"):
        write_batch(tmp_path / "reserved", reserved, options)
    for name in ("a/b", "a=b", "a%20b", "a\\b"):
        invalid = batch.rename_columns([name, "id"])
        destination = tmp_path / "invalid"
        with pytest.raises(RuntimeError, match="partition column names"):
            write_batch(
                destination,
                invalid,
                ParquetOptions(
                    dataset=True, hive=True, partition_columns=(name,)
                ),
            )
        assert not destination.exists()


@pytest.mark.parametrize("layout", [ArrowArray, ArrowSchema])
def test_c_data_storage_matches_arrow_abi(
    layout: type[ctypes.Structure],
) -> None:
    """
    title: Verify standard C Data sizes, alignment and every field offset.
    parameters:
      layout:
        type: type[ctypes.Structure]
    """
    c_type = "struct " + layout.__name__
    assert ctypes.sizeof(layout) == ffi.sizeof(c_type)
    assert ctypes.alignment(layout) == ffi.alignof(c_type)
    for name, _ in layout._fields_:
        assert getattr(layout, name).offset == ffi.offsetof(c_type, name)


def test_interchange_does_not_require_optional_cffi() -> None:
    """
    title: >-
      Public schema/batch interchange needs no undeclared optional dependency.
    """
    code = """
import sys
sys.modules["cffi"] = None
sys.modules["pyarrow.cffi"] = None
import pyarrow as pa
from irx.record_batch import RecordBatch, RecordBatchSchema
source = pa.record_batch([pa.array([[b"a"], None])], names=["x"])
schema = RecordBatchSchema.from_arrow(source.schema)
batch = RecordBatch.from_arrow(source)
assert schema.to_arrow().equals(source.schema)
assert batch.to_arrow().equals(source)
batch.release()
schema.release()
"""
    subprocess.run([sys.executable, "-c", code], check=True, timeout=60)


@pytest.mark.parametrize(
    "field",
    [
        pa.field("bad\0name", pa.int32()),
        pa.field("items", pa.list_(pa.field("bad\0child", pa.int32()))),
        pa.field("stamp", pa.timestamp("us", tz="UTC\0bad")),
        pa.field(
            "codes",
            pa.dictionary(pa.int32(), pa.struct([("bad\0child", pa.int32())])),
        ),
    ],
)
def test_c_data_import_rejects_lossy_schema(field: pa.Field) -> None:
    """
    title: >-
      Check unrepresentable names before PyArrow exports null-terminated C
      text.
    parameters:
      field:
        type: pa.Field
    """
    schema = pa.schema([field])
    with pytest.raises(ValueError, match="NUL"):
        RecordBatchSchema.from_arrow(schema)
    if pa.types.is_dictionary(field.type):
        array = pa.DictionaryArray.from_arrays(
            pa.array([], type=field.type.index_type),
            pa.array([], type=field.type.value_type),
        )
    else:
        array = pa.array([], type=field.type)
    batch = pa.record_batch([array], schema=schema)
    with pytest.raises(ValueError, match="NUL"):
        RecordBatch.from_arrow(batch)


def test_c_data_export_checks_dictionary_value_fields(tmp_path: Path) -> None:
    """
    title: Rich IPC types must not bypass the recursive C Data name checks.
    parameters:
      tmp_path:
        type: Path
    """
    array = pa.DictionaryArray.from_arrays(
        pa.array([0]), pa.array([{"bad\0child": 1}])
    )
    original = pa.record_batch([array], names=["codes"])
    path = tmp_path / "dictionary.arrow"
    with pa.ipc.new_stream(path, original.schema) as output:
        output.write_batch(original)
    with RecordBatchStreamReader.open_file(path) as reader:
        batch = reader.next_batch()
        assert batch is not None
        try:
            with pytest.raises(RuntimeError, match="NUL"):
                batch.to_arrow()
        finally:
            batch.release()
