"""
title: Optional native backends and coordinated durable dataset commits.
"""

import os
import subprocess
import sys

from dataclasses import replace
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from irx.record_batch import (
    ParquetOptions,
    ParquetStream,
    RecordBatchSchema,
    parquet_library,
)

from .test_parquet_followup import read_batches, write_batch


def test_csv_does_not_require_parquet(tmp_path: Path) -> None:
    """
    title: >-
      CSV builds/loads only the base library even without Parquet libraries.
    parameters:
      tmp_path:
        type: Path
    """
    code = """
from unittest.mock import patch
import pyarrow as pa
from irx.record_batch import CSVStream, RecordBatchSchema
with patch(
    'irx.builder.runtime.record_batch.build_parquet_runtime_feature',
    side_effect=RuntimeError('Parquet disabled'),
):
    schema = RecordBatchSchema.from_arrow(pa.schema([('id', pa.int64())]))
    try:
        with CSVStream() as file:
            file.open_write('empty.csv', schema)
    finally:
        schema.release()
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "empty.csv").is_file()


def test_local_writer_exclusion_and_release(tmp_path: Path) -> None:
    """
    title: A second cooperating writer cannot truncate or lose an append.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "data.parquet"
    batch = pa.record_batch([[1]], names=["id"])
    schema = RecordBatchSchema.from_arrow(batch.schema)
    try:
        with ParquetStream() as first, ParquetStream() as second:
            first.open_write(path, schema, options=ParquetOptions(atomic=True))
            with pytest.raises(RuntimeError, match="busy"):
                second.open_write(path, schema)
            first.close()
            second.open_write(
                path, schema, options=ParquetOptions(atomic=True, durable=True)
            )
    finally:
        schema.release()
    assert pq.read_table(path).num_rows == 0


def test_durable_requires_atomic_without_truncation(tmp_path: Path) -> None:
    """
    title: Invalid durability policy is rejected before touching existing data.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "data.parquet"
    path.write_bytes(b"original")
    with pytest.raises(RuntimeError, match="durable requires"):
        write_batch(
            path,
            pa.record_batch([[1]], names=["id"]),
            ParquetOptions(durable=True),
        )
    assert path.read_bytes() == b"original"


@pytest.mark.skipif(os.name != "posix", reason="POSIX dataset commit protocol")
@pytest.mark.parametrize("key", [None, b"0123456789abcdef"])
def test_atomic_dataset_snapshot_and_encryption(
    tmp_path: Path, key: bytes | None
) -> None:
    """
    title: Publish complete datasets and pin readers to immutable generations.
    parameters:
      tmp_path:
        type: Path
      key:
        type: bytes | None
    """
    path = tmp_path / "dataset"
    batch = pa.record_batch([[1, 2], ["a", "b"]], names=["id", "part"])
    options = ParquetOptions(
        dataset=True,
        hive=True,
        partition_columns=("part",),
        atomic=True,
        durable=True,
        encryption_key=key,
    )
    scan = ParquetOptions(dataset=True, hive=True, encryption_key=key)
    write_batch(path, batch, options)
    assert path.is_symlink()
    old_generation = path.resolve()
    with ParquetStream() as old_reader:
        old_reader.open_read(path, options=scan)
        write_batch(path, batch, options)
        assert path.resolve() != old_generation
        assert old_generation.is_dir()
        old_rows = 0
        while (result := old_reader.next_batch()) is not None:
            old_rows += result.num_rows
            result.release()
        assert old_rows == batch.num_rows
    assert (
        sum(item.num_rows for item in read_batches(path, scan))
        == batch.num_rows
    )
    if key:
        with pytest.raises(RuntimeError):
            read_batches(path, ParquetOptions(dataset=True, hive=True))
        for fragment in path.resolve().rglob("*.parquet"):
            with pytest.raises(OSError):
                pq.read_table(fragment)


def test_atomic_dataset_abort_and_evolution(tmp_path: Path) -> None:
    """
    title: >-
      Evolve only nullable same-typed schemas, with no partial publication.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "dataset"
    first = pa.record_batch([[1], ["a"]], names=["id", "part"])
    second = pa.record_batch([["two"], ["b"]], names=["label", "part"])
    write = ParquetOptions(
        dataset=True, hive=True, atomic=True, partition_columns=("part",)
    )
    write_batch(path, first, write)
    old = path.resolve()
    schema = RecordBatchSchema.from_arrow(first.schema)
    try:
        with pytest.raises(ValueError, match="cancel"):
            with ParquetStream() as writer:
                writer.open_write(path, schema, options=write)
                raise ValueError("cancel")
    finally:
        schema.release()
    assert path.resolve() == old
    write_batch(path, second, replace(write, append=True, unify=True))
    result = pa.Table.from_batches(
        read_batches(path, ParquetOptions(dataset=True, hive=True, unify=True))
    )
    assert result.schema.names == ["id", "part", "label"]
    assert sorted(result.to_pylist(), key=lambda row: row["part"]) == [
        {"id": 1, "part": "a", "label": None},
        {"id": None, "part": "b", "label": "two"},
    ]
    assert old.is_dir()


@pytest.mark.parametrize(
    ("kind", "values"),
    [
        (pa.dictionary(pa.int8(), pa.int64()), [1, None, 2]),
        (pa.dictionary(pa.uint16(), pa.float64()), [1.5, None, 2.5]),
        (
            pa.dictionary(pa.int16(), pa.decimal128(8, 2)),
            [Decimal("1.20"), None, Decimal("2.30")],
        ),
        (pa.list_(pa.int32(), 2), [[1, 2], None, [None, 3]]),
        (
            pa.struct([("items", pa.list_(pa.int32(), 2))]),
            [{"items": [1, 2]}, {"items": None}, None],
        ),
    ],
)
def test_explicit_reconstruction(
    tmp_path: Path, kind: pa.DataType, values: list[object]
) -> None:
    """
    title: Reconstruct logical types while exposing honest physical storage.
    parameters:
      tmp_path:
        type: Path
      kind:
        type: pa.DataType
      values:
        type: list[object]
    """
    path = tmp_path / "reconstruct.parquet"
    array = (
        pa.DictionaryArray.from_arrays(
            pa.array([0, None, 1], type=kind.index_type),
            pa.array([values[0], values[2]], type=kind.value_type),
        )
        if pa.types.is_dictionary(kind)
        else pa.array(values, type=kind)
    )
    schema = pa.schema(
        [pa.field("value", kind, metadata={b"field": b"yes"})],
        metadata={b"user": b"kept"},
    )
    batch = pa.record_batch([array], schema=schema)
    options = ParquetOptions(reconstruct=True, atomic=True)
    write_batch(path, batch, options)
    restored = pa.Table.from_batches(read_batches(path))
    assert restored.schema.equals(schema, check_metadata=True)
    assert restored.to_pylist() == batch.to_pylist()
    write_batch(path, batch, replace(options, append=True))
    restored = pa.Table.from_batches(read_batches(path))
    assert restored.schema.equals(schema, check_metadata=True)
    assert restored.to_pylist() == batch.to_pylist() * 2
    assert pq.read_schema(path).metadata[b"IRX:logical_schema:v1"]


def test_reconstruction_reserves_metadata_key(tmp_path: Path) -> None:
    """
    title: Reject a caller-supplied logical schema before truncation.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "sentinel"
    path.write_bytes(b"unchanged")
    batch = pa.record_batch([[1]], names=["x"]).replace_schema_metadata(
        {b"IRX:logical_schema:v1": b"malformed"}
    )
    with pytest.raises(RuntimeError, match="reserves"):
        write_batch(path, batch)
    assert path.read_bytes() == b"unchanged"


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        (pa.bool_(), True),
        (pa.date32(), date(2026, 1, 1)),
        (pa.time64("us"), time(1, 2, 3)),
        (pa.timestamp("ns", "Europe/London"), datetime(2026, 1, 1)),
    ],
)
def test_typed_hive_partitions(
    tmp_path: Path, kind: pa.DataType, value: object
) -> None:
    """
    title: Preserve typed and null partition keys without inference.
    parameters:
      tmp_path:
        type: Path
      kind:
        type: pa.DataType
      value:
        type: object
    """
    batch = pa.record_batch(
        [pa.array([1, 2]), pa.array([value, None], type=kind)],
        names=["id", "part"],
    )
    path = tmp_path / "dataset"
    write_batch(
        path,
        batch,
        ParquetOptions(
            dataset=True, hive=True, atomic=True, partition_columns=("part",)
        ),
    )
    result = pa.Table.from_batches(
        read_batches(path, ParquetOptions(dataset=True, hive=True))
    ).sort_by("id")
    assert result.equals(pa.Table.from_batches([batch]), check_metadata=True)


def test_snapshot_rejects_invalid_evolution_without_publication(
    tmp_path: Path,
) -> None:
    """
    title: Failed evolution cannot replace the public generation.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "dataset"
    options = ParquetOptions(
        dataset=True, hive=True, atomic=True, partition_columns=("part",)
    )
    first = pa.record_batch([[1], ["a"]], names=["id", "part"])
    write_batch(path, first, options)
    previous = path.resolve()
    second = pa.record_batch([["not an integer"], ["b"]], names=["id", "part"])
    with pytest.raises(RuntimeError, match="cannot change"):
        write_batch(path, second, replace(options, append=True, unify=True))
    assert path.resolve() == previous
    with pytest.raises(RuntimeError, match="atomic=true"):
        write_batch(path, first, replace(options, atomic=False, append=True))
    assert path.resolve() == previous
    write_batch(path, first, replace(options, append=True))


def test_reconstruction_projection_and_empty_schema(tmp_path: Path) -> None:
    """
    title: Project reconstructed fields and retain schema for empty files.
    parameters:
      tmp_path:
        type: Path
    """
    kind = pa.dictionary(pa.int8(), pa.int64())
    batch = pa.record_batch(
        [pa.array([1, None, 2], type=kind), pa.array(["a", "b", "c"])],
        names=["value", "label"],
    )
    path = tmp_path / "projection.parquet"
    write_batch(
        path, batch, ParquetOptions(reconstruct=True, row_group_size=1)
    )
    result = pa.Table.from_batches(
        read_batches(
            path, ParquetOptions(columns=("value",), row_groups=(0, 2))
        )
    )
    assert result.schema.equals(
        pa.schema([batch.schema.field("value")]), check_metadata=True
    )
    assert result.column("value").to_pylist() == [1, 2]
    write_batch(path, batch.slice(0, 0), ParquetOptions(reconstruct=True))
    with ParquetStream() as reader:
        reader.open_read(path)
        schema = reader.schema()
        try:
            assert schema.to_arrow().equals(batch.schema, check_metadata=True)
            assert reader.next_batch() is None
        finally:
            schema.release()


class ApplicationType(pa.ExtensionType):
    """
    title: A Python-only extension unknown to native Arrow's registry.
    """

    def __init__(self) -> None:
        """
        title: Register the storage contract without native callbacks.
        """
        super().__init__(pa.int64(), "irx.test.application")

    def __arrow_ext_serialize__(self) -> bytes:
        """
        title: Preserve an application-owned version payload.
        returns:
          type: bytes
        """
        return b"version=1"

    @classmethod
    def __arrow_ext_deserialize__(
        cls, storage_type: pa.DataType, serialized: bytes
    ) -> "ApplicationType":
        """
        title: Restore only matching versioned storage contracts.
        parameters:
          storage_type:
            type: pa.DataType
          serialized:
            type: bytes
        returns:
          type: ApplicationType
        """
        if storage_type != pa.int64() or serialized != b"version=1":
            raise ValueError("unsupported application extension")
        return cls()


def test_python_extension_preserves_storage_and_metadata(
    tmp_path: Path,
) -> None:
    """
    title: Native I/O preserves extensions without executing Python code.
    parameters:
      tmp_path:
        type: Path
    """
    kind = ApplicationType()
    pa.register_extension_type(kind)
    try:
        values = pa.ExtensionArray.from_storage(kind, pa.array([1, None, 3]))
        batch = pa.record_batch([values], names=["custom"])
        path = tmp_path / "application.parquet"
        write_batch(path, batch)
        result = pa.Table.from_batches(read_batches(path))
        assert result.equals(
            pa.Table.from_batches([batch]), check_metadata=True
        )
    finally:
        pa.unregister_extension_type(kind.extension_name)


def test_process_death_releases_writer_lease(tmp_path: Path) -> None:
    """
    title: Process death preserves old output and releases advisory locks.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "data.parquet"
    batch = pa.record_batch([[1]], names=["id"])
    write_batch(path, batch)
    before = path.read_bytes()
    code = """
import os
import pyarrow as pa
from irx.record_batch import ParquetStream, ParquetOptions, RecordBatchSchema
schema = RecordBatchSchema.from_arrow(pa.schema([('id', pa.int64())]))
writer = ParquetStream()
writer.open_write('data.parquet', schema, options=ParquetOptions(atomic=True))
os._exit(0)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert path.read_bytes() == before
    write_batch(path, batch, ParquetOptions(atomic=True, durable=True))
    assert pq.read_table(path).to_pydict() == {"id": [1]}


def test_invalid_reconstruction_metadata_fails_on_open(tmp_path: Path) -> None:
    """
    title: Never trust a malformed external logical-schema footer.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "malformed.parquet"
    table = pa.table({"id": [1]}).replace_schema_metadata(
        {b"IRX:logical_schema:v1": b"malformed"}
    )
    pq.write_table(table, path)
    with ParquetStream() as reader:
        with pytest.raises(RuntimeError):
            reader.open_read(path)


def test_reconstruction_rejects_ordered_dictionaries(tmp_path: Path) -> None:
    """
    title: Ordered codebooks cannot silently change their ordering.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "ordered.parquet"
    path.write_bytes(b"unchanged")
    values = pa.DictionaryArray.from_arrays(
        pa.array([1, 0], type=pa.int8()), pa.array([3, 2]), ordered=True
    )
    with pytest.raises(RuntimeError, match="ordered dictionary"):
        write_batch(
            path,
            pa.record_batch([values], names=["x"]),
            ParquetOptions(reconstruct=True),
        )
    assert path.read_bytes() == b"unchanged"


def test_unused_new_flags_remain_compatible_with_older_abi(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    title: Default flags do not require new symbols in explicit overrides.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    lib = parquet_library()
    with ParquetOptions().native(lib):
        pass
    original = lib.irx_parquet_options_int

    def old_flags(handle: int, name: bytes, value: int) -> int:
        """
        title: Emulate an older backend that rejects new option names.
        parameters:
          handle:
            type: int
          name:
            type: bytes
          value:
            type: int
        returns:
          type: int
        """
        if name in (b"durable", b"reconstruct"):
            raise AssertionError("an unused new flag crossed the ABI")
        return int(original(handle, name, value))

    monkeypatch.setattr(
        lib, "irx_parquet_options_int", Mock(side_effect=old_flags)
    )
    path = tmp_path / "older.parquet"
    write_batch(
        path, pa.record_batch([[1]], names=["id"]), ParquetOptions(atomic=True)
    )
    assert pq.read_table(path).to_pydict() == {"id": [1]}
