"""
title: Record batch streaming API.
"""

from __future__ import annotations

import ctypes
import math
import shutil
import subprocess
import sys
import time as time_module

from datetime import date, datetime, time, timezone
from pathlib import Path

import irx.builder.runtime.record_batch as record_batch_runtime
import irx.record_batch as record_batch_module
import pyarrow as pa
import pytest

from irx.builder.runtime.record_batch import (
    ensure_record_batch_shared_library,
    record_batch_build_fingerprint,
    record_batch_build_lock,
    record_batch_shared_library_is_current,
    shared_library_fingerprint_path,
    shared_library_path,
)
from irx.record_batch import (
    RECORD_BATCH_ABI_VERSION,
    IrxColumnType,
    RecordBatchBuilder,
    RecordBatchSchema,
    RecordBatchStreamReader,
    RecordBatchStreamWriter,
)
from irx.record_batch_abi import (
    IRX_NATIVE_CACHE_DIR_ENV,
    IRX_RECORD_BATCH_LIBRARY_ENV,
    record_batch_library_name,
    record_batch_library_path,
)

# Helpers

EXPECTED_FIELD_COUNT = 2
ROW_COUNT = 4
NULL_ROW_INDEX = 2
INT32_VALUE = 42
INT32_VALUE_ALT = 7
BATCH_ROW_COUNT = 10
BATCH_ROW_COUNT_LARGE = 20
PYARROW_ROW_COUNT = 5
PYARROW_BATCH_ROW_COUNT = 3
PYARROW_BATCH_COLUMN_COUNT = 2
PYARROW_FIRST_INT32_VALUE = 10
PYARROW_LAST_INT32_VALUE = 30
PYARROW_CONTEXT_MANAGER_INT32_VALUE = 99
RAW_DATE32_DAYS = 20651


def test_record_batch_library_path_uses_abi_scoped_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    title: Generated libraries live in a writable ABI-scoped cache.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    monkeypatch.setenv(IRX_NATIVE_CACHE_DIR_ENV, str(tmp_path))
    monkeypatch.delenv(IRX_RECORD_BATCH_LIBRARY_ENV, raising=False)

    path = record_batch_library_path()

    assert path.parent == tmp_path / "record_batch" / "abi-1"
    assert path.name == record_batch_library_name()


def test_record_batch_library_path_honors_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    title: An explicit native library override takes precedence over caching.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    configured = tmp_path / "custom-record-batch.so"
    monkeypatch.setenv(IRX_RECORD_BATCH_LIBRARY_ENV, str(configured))

    assert shared_library_path() == configured


def test_record_batch_loader_builds_or_refreshes_default_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    title: First direct API use ensures a fingerprint-current cache library.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    monkeypatch.delenv(IRX_RECORD_BATCH_LIBRARY_ENV, raising=False)
    library = tmp_path / record_batch_library_name()
    ensured: list[bool] = []
    loaded: list[str] = []

    def fake_ensure() -> Path:
        """
        title: Return one simulated freshly built native library.
        returns:
          type: Path
        """
        ensured.append(True)
        return library

    def fake_cdll(path: str) -> object:
        """
        title: Record the path passed to ctypes.
        parameters:
          path:
            type: str
        returns:
          type: object
        """
        loaded.append(path)
        return object()

    monkeypatch.setattr(
        record_batch_runtime,
        "ensure_record_batch_shared_library",
        fake_ensure,
    )
    monkeypatch.setattr(record_batch_module.ctypes, "CDLL", fake_cdll)

    result = record_batch_module._load_native_lib()

    assert ensured == [True]
    assert loaded == [str(library)]
    assert result is not None


def test_record_batch_loader_rejects_missing_exact_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    title: An explicit missing native library is never silently replaced.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    missing = tmp_path / record_batch_library_name()
    monkeypatch.setenv(IRX_RECORD_BATCH_LIBRARY_ENV, str(missing))

    with pytest.raises(RuntimeError, match=IRX_RECORD_BATCH_LIBRARY_ENV):
        record_batch_module._load_native_lib()


def test_record_batch_build_lock_times_out_for_live_owner(
    tmp_path: Path,
) -> None:
    """
    title: A competing native build times out while its owner is alive.
    parameters:
      tmp_path:
        type: Path
    """
    output = tmp_path / "libirx_record_batch.so"
    lock_path = output.with_name(f"{output.name}.lock")
    ready_path = tmp_path / "lock-ready"
    script = """
import sys
from pathlib import Path
from irx.builder.runtime.record_batch import record_batch_build_lock

with record_batch_build_lock(Path(sys.argv[1])):
    Path(sys.argv[2]).write_text("locked", encoding="utf-8")
    sys.stdin.read(1)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(output), str(ready_path)],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time_module.monotonic() + 60.0
        while not ready_path.is_file():
            if process.poll() is not None:
                assert process.stderr is not None
                pytest.fail(
                    "lock owner exited before acquiring the lock: "
                    f"{process.stderr.read()}"
                )
            if time_module.monotonic() >= deadline:
                pytest.fail("timed out waiting for the lock owner subprocess")
            time_module.sleep(0.05)
        with pytest.raises(TimeoutError, match="native build lock"):
            with record_batch_build_lock(output, timeout_seconds=0.0):
                pytest.fail("a held build lock must not be acquired")
        assert lock_path.is_file()
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)


def test_record_batch_build_lock_recovers_after_owner_exits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    title: A killed lock owner cannot permanently disable native builds.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    output = tmp_path / "libirx_record_batch.so"
    script = """
import os
import sys
from pathlib import Path
from irx.builder.runtime.record_batch import record_batch_build_lock

with record_batch_build_lock(Path(sys.argv[1])):
    print("locked", flush=True)
    os._exit(0)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(output)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.stdout.strip() == "locked"

    build_calls: list[Path] = []

    def fake_is_current(
        output_path: Path | None = None,
        cxx_binary: str = "c++",
    ) -> bool:
        """
        title: Report the fixture library as stale.
        parameters:
          output_path:
            type: Path | None
          cxx_binary:
            type: str
        returns:
          type: bool
        """
        del output_path, cxx_binary
        return False

    def fake_build(
        output_path: Path | None = None,
        build_dir: Path | None = None,
        cxx_binary: str = "c++",
    ) -> Path:
        """
        title: Materialize a fixture library after recovering the lock.
        parameters:
          output_path:
            type: Path | None
          build_dir:
            type: Path | None
          cxx_binary:
            type: str
        returns:
          type: Path
        """
        del build_dir, cxx_binary
        assert output_path is not None
        output_path.write_bytes(b"fixture")
        build_calls.append(output_path)
        return output_path

    monkeypatch.setattr(
        record_batch_runtime,
        "record_batch_shared_library_is_current",
        fake_is_current,
    )
    monkeypatch.setattr(
        record_batch_runtime,
        "build_record_batch_shared_library",
        fake_build,
    )

    assert ensure_record_batch_shared_library(output) == output
    assert build_calls == [output]
    assert output.read_bytes() == b"fixture"


def test_record_batch_build_lock_ignores_untrusted_file_contents(
    tmp_path: Path,
) -> None:
    """
    title: Lock ownership never depends on parseable lock-file contents.
    parameters:
      tmp_path:
        type: Path
    """
    output = tmp_path / "libirx_record_batch.so"
    lock_path = output.with_name(f"{output.name}.lock")
    lock_path.write_text("not a pid or lease", encoding="utf-8")

    with record_batch_build_lock(output, timeout_seconds=0.0):
        assert lock_path.is_file()
    assert lock_path.is_file()


def test_record_batch_native_abi_version_matches_python_contract() -> None:
    """
    title: The loaded native library reports the ABI Python expects.
    """
    lib = record_batch_module._get_lib()

    assert lib.irx_record_batch_abi_version() == RECORD_BATCH_ABI_VERSION


def test_record_batch_native_abi_mismatch_fails_before_symbol_binding(
    tmp_path: Path,
) -> None:
    """
    title: An incompatible native ABI fails with an actionable load error.
    parameters:
      tmp_path:
        type: Path
    """
    compiler = shutil.which("clang") or shutil.which("cc")
    if compiler is None:
        pytest.skip("a C compiler is required for the ABI mismatch test")
    if sys.platform == "win32":
        pytest.skip("the ABI mismatch fixture does not build on Windows yet")

    source = tmp_path / "wrong_abi.c"
    library = tmp_path / (
        "libwrong_abi.dylib" if sys.platform == "darwin" else "libwrong_abi.so"
    )
    source.write_text(
        "#include <stdint.h>\n"
        "uint32_t irx_record_batch_abi_version(void) { return 999; }\n",
        encoding="utf-8",
    )
    shared_flag = "-dynamiclib" if sys.platform == "darwin" else "-shared"
    command = [compiler, shared_flag]
    if sys.platform != "darwin":
        command.append("-fPIC")
    command.extend([str(source), "-o", str(library)])
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    with pytest.raises(RuntimeError, match="expected 1, found 999"):
        record_batch_module._configure_lib(ctypes.CDLL(str(library)))


def test_record_batch_artifact_fingerprint_rejects_stale_sidecar(
    tmp_path: Path,
) -> None:
    """
    title: A native library is current only with the exact build fingerprint.
    parameters:
      tmp_path:
        type: Path
    """
    output = tmp_path / "libirx_record_batch.so"
    output.write_bytes(b"test artifact")
    fingerprint_path = shared_library_fingerprint_path(output)

    assert not record_batch_shared_library_is_current(output)

    fingerprint = record_batch_build_fingerprint()
    fingerprint_path.write_text(f"{fingerprint}\n", encoding="utf-8")
    assert record_batch_shared_library_is_current(output)

    fingerprint_path.write_text("stale\n", encoding="utf-8")
    assert not record_batch_shared_library_is_current(output)


def test_ensure_record_batch_library_rebuilds_stale_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    title: Ensuring a stale native artifact invokes the atomic builder.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    output = tmp_path / "libirx_record_batch.so"
    output.write_bytes(b"stale")
    shared_library_fingerprint_path(output).write_text(
        "stale\n",
        encoding="utf-8",
    )
    rebuilt: list[Path] = []

    def fake_build(
        output_path: Path | None = None,
        build_dir: Path | None = None,
        cxx_binary: str = "c++",
    ) -> Path:
        """
        title: Record one requested native rebuild.
        parameters:
          output_path:
            type: Path | None
          build_dir:
            type: Path | None
          cxx_binary:
            type: str
        returns:
          type: Path
        """
        del build_dir
        del cxx_binary
        assert output_path is not None
        rebuilt.append(output_path)
        return output_path

    monkeypatch.setattr(
        record_batch_runtime,
        "build_record_batch_shared_library",
        fake_build,
    )

    assert ensure_record_batch_shared_library(output) == output
    assert rebuilt == [output]


def test_schema_finalizer_is_safe_after_native_load_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Schema cleanup tolerates a constructor that failed before loading.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """

    def fail_native_load() -> None:
        """
        title: Simulate a missing or incompatible native library.
        """
        raise RuntimeError("native load failed")

    monkeypatch.setattr(record_batch_module, "_get_lib", fail_native_load)
    schema = object.__new__(RecordBatchSchema)

    with pytest.raises(RuntimeError, match="native load failed"):
        schema.__init__()

    schema.__del__()
    assert schema._released is True


def make_simple_schema() -> RecordBatchSchema:
    """
    title: Create a simple schema with one int32 and one float64 column.
    returns:
      type: RecordBatchSchema
    """
    schema = RecordBatchSchema()
    schema.add_field("id", IrxColumnType.INT32, nullable=False)
    schema.add_field("value", IrxColumnType.FLOAT64, nullable=True)
    return schema


def fill_builder(builder: RecordBatchBuilder, n: int) -> None:
    """
    title: Append a simple pattern of rows to a record-batch builder.
    parameters:
      builder:
        type: RecordBatchBuilder
      n:
        type: int
    """
    for i in range(n):
        builder.append_int32(0, i)
        builder.append_float64(1, i * 1.5)


# Schema tests


class TestSchema:
    def test_empty_schema(self):
        """
        title: Ensure an empty schema reports zero fields.
        """
        s = RecordBatchSchema()
        assert s.num_fields == 0
        s.release()

    def test_add_fields(self):
        """
        title: Ensure schema fields can be added and counted.
        """
        s = RecordBatchSchema()
        s.add_field("a", IrxColumnType.INT32)
        s.add_field("b", IrxColumnType.FLOAT64, nullable=False)
        assert s.num_fields == EXPECTED_FIELD_COUNT
        s.release()

    def test_all_types(self):
        """
        title: Ensure every supported scalar column type can be registered.
        """
        s = RecordBatchSchema()
        # LIST and STRUCT are nested types registered via their own add_*
        # helpers, not add_field.
        nested_types = {IrxColumnType.LIST, IrxColumnType.STRUCT}
        scalar_types = [ct for ct in IrxColumnType if ct not in nested_types]
        for ct in scalar_types:
            s.add_field(ct.name.lower(), ct)
        assert s.num_fields == len(scalar_types)
        s.release()

    def test_double_release_is_safe(self):
        """
        title: Ensure releasing a schema more than once is harmless.
        """
        s = RecordBatchSchema()
        s.release()
        s.release()  # must not crash


# Builder / batch tests


class TestBuilder:
    def test_build_and_inspect(self):
        """
        title: Ensure builders can create and inspect a simple batch.
        """
        schema = make_simple_schema()
        builder = RecordBatchBuilder(schema)
        fill_builder(builder, 4)
        batch = builder.finish()

        assert batch.num_rows == ROW_COUNT
        assert batch.num_columns == EXPECTED_FIELD_COUNT

        for i in range(ROW_COUNT):
            assert batch.get_int32(0, i) == i
            assert math.isclose(batch.get_float64(1, i), i * 1.5)

        batch.release()
        builder.release()
        schema.release()

    def test_null_values(self):
        """
        title: Ensure null values are reported correctly.
        """
        schema = RecordBatchSchema()
        schema.add_field("x", IrxColumnType.INT32, nullable=True)
        builder = RecordBatchBuilder(schema)
        builder.append_int32(0, 42)
        builder.append_null(0)
        builder.append_int32(0, 7)
        batch = builder.finish()

        assert batch.is_null(0, 0) is False
        assert batch.is_null(0, 1) is True
        assert batch.is_null(0, NULL_ROW_INDEX) is False
        assert batch.get_int32(0, 0) == INT32_VALUE
        assert batch.get_int32(0, NULL_ROW_INDEX) == INT32_VALUE_ALT

        batch.release()
        builder.release()
        schema.release()

    def test_bool_column(self):
        """
        title: Ensure boolean columns round-trip through the builder.
        """
        schema = RecordBatchSchema()
        schema.add_field("flag", IrxColumnType.BOOL)
        builder = RecordBatchBuilder(schema)
        builder.append_bool(0, True)
        builder.append_bool(0, False)
        builder.append_bool(0, True)
        batch = builder.finish()

        assert batch.get_bool(0, 0) is True
        assert batch.get_bool(0, 1) is False
        assert batch.get_bool(0, 2) is True
        batch.release()
        builder.release()
        schema.release()

    def test_all_numeric_types(self):
        """
        title: Ensure all numeric column types are supported.
        """
        schema = RecordBatchSchema()
        types_and_appenders = [
            (IrxColumnType.INT8, "append_int8", "get_int8", -1),
            (IrxColumnType.INT16, "append_int16", "get_int16", -2),
            (IrxColumnType.INT32, "append_int32", "get_int32", -3),
            (IrxColumnType.INT64, "append_int64", "get_int64", -4),
            (IrxColumnType.UINT8, "append_uint8", "get_uint8", 5),
            (IrxColumnType.UINT16, "append_uint16", "get_uint16", 6),
            (IrxColumnType.UINT32, "append_uint32", "get_uint32", 7),
            (IrxColumnType.UINT64, "append_uint64", "get_uint64", 8),
            (IrxColumnType.FLOAT32, "append_float32", "get_float32", 1.5),
            (IrxColumnType.FLOAT64, "append_float64", "get_float64", 2.5),
        ]
        for i, (ct, _, _, _) in enumerate(types_and_appenders):
            schema.add_field(f"col_{i}", ct)

        builder = RecordBatchBuilder(schema)
        for i, (_, append_fn, _, value) in enumerate(types_and_appenders):
            getattr(builder, append_fn)(i, value)
        batch = builder.finish()

        for i, (_, _, get_fn, expected) in enumerate(types_and_appenders):
            got = getattr(batch, get_fn)(i, 0)
            assert math.isclose(got, expected, rel_tol=1e-5), (
                f"col {i}: got {got!r}, expected {expected!r}"
            )

        batch.release()
        builder.release()
        schema.release()

    def test_oob_column_raises(self):
        """
        title: Ensure out-of-bounds columns raise a runtime error.
        """
        schema = RecordBatchSchema()
        schema.add_field("x", IrxColumnType.INT32)
        builder = RecordBatchBuilder(schema)
        with pytest.raises(RuntimeError, match="out of bounds"):
            builder.append_int32(99, 0)
        builder.release()
        schema.release()

    def test_type_mismatch_raises(self):
        """
        title: Ensure type mismatches raise a runtime error.
        """
        schema = RecordBatchSchema()
        schema.add_field("x", IrxColumnType.INT32)
        builder = RecordBatchBuilder(schema)
        with pytest.raises(RuntimeError, match="type mismatch"):
            builder.append_float64(0, 3.14)
        builder.release()
        schema.release()

    def test_empty_batch(self):
        """
        title: Ensure an empty batch can be produced and inspected.
        """
        schema = make_simple_schema()
        builder = RecordBatchBuilder(schema)
        batch = builder.finish()
        assert batch.num_rows == 0
        batch.release()
        builder.release()
        schema.release()


# Stream writer / reader round-trip — in-memory buffer


class TestBufferRoundTrip:
    def _write_batches(
        self, schema: RecordBatchSchema, batches_data: list
    ) -> bytes:
        """
        title: Write a list of batches into an in-memory stream.
        parameters:
          schema:
            type: RecordBatchSchema
          batches_data:
            type: list
        returns:
          type: bytes
        """
        writer = RecordBatchStreamWriter.open_buffer(schema)
        for rows in batches_data:
            builder = RecordBatchBuilder(schema)
            for i in rows:
                builder.append_int32(0, i)
                builder.append_float64(1, float(i))
            batch = builder.finish()
            writer.write_batch(batch)
            batch.release()
            builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()
        return data

    def test_single_batch_round_trip(self):
        """
        title: Ensure a single batch survives a buffer round-trip.
        """
        schema = make_simple_schema()
        data = self._write_batches(schema, [range(10)])

        reader = RecordBatchStreamReader.open_buffer(data)
        batch = reader.next_batch()
        assert batch is not None
        assert batch.num_rows == BATCH_ROW_COUNT
        for i in range(BATCH_ROW_COUNT):
            assert batch.get_int32(0, i) == i
            assert math.isclose(batch.get_float64(1, i), float(i))
        batch.release()

        assert reader.next_batch() is None  # EOF
        reader.close()
        schema.release()

    def test_multiple_batches_round_trip(self):
        """
        title: Ensure multiple batches survive a buffer round-trip.
        """
        schema = make_simple_schema()
        data = self._write_batches(
            schema, [range(5), range(5, 10), range(10, 15)]
        )

        reader = RecordBatchStreamReader.open_buffer(data)
        all_ids = []
        for batch in reader:  # uses __iter__
            for row in range(batch.num_rows):
                all_ids.append(batch.get_int32(0, row))
        reader.close()

        assert all_ids == list(range(15))
        schema.release()

    def test_empty_stream(self):
        """
        title: Ensure an empty stream yields no batches.
        """
        schema = make_simple_schema()
        writer = RecordBatchStreamWriter.open_buffer(schema)
        writer.close()
        data = writer.buffer_data()
        writer.release()

        reader = RecordBatchStreamReader.open_buffer(data)
        assert reader.next_batch() is None
        reader.close()
        schema.release()

    def test_context_manager(self):
        """
        title: Ensure the writer and reader work as context managers.
        """
        schema = make_simple_schema()
        with RecordBatchStreamWriter.open_buffer(schema) as writer:
            builder = RecordBatchBuilder(schema)
            builder.append_int32(0, 99)
            builder.append_float64(1, 99.0)
            batch = builder.finish()
            writer.write_batch(batch)
            batch.release()
            builder.release()
            writer.close()
            data = writer.buffer_data()

        reader = RecordBatchStreamReader.open_buffer(data)
        batch = reader.next_batch()
        assert batch is not None
        assert batch.get_int32(0, 0) == PYARROW_CONTEXT_MANAGER_INT32_VALUE
        batch.release()
        reader.close()
        schema.release()


# Stream writer / reader round-trip — file


class TestFileRoundTrip:
    def test_file_round_trip(self, tmp_path: Path) -> None:
        """
        title: Ensure file-based streams round-trip correctly.
        parameters:
          tmp_path:
            type: Path
        """
        path = tmp_path / "test.arrows"
        schema = make_simple_schema()

        writer = RecordBatchStreamWriter.open_file(schema, path)
        builder = RecordBatchBuilder(schema)
        for i in range(20):
            builder.append_int32(0, i)
            builder.append_float64(1, i * 0.5)
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        writer.release()

        assert path.exists()
        assert path.stat().st_size > 0

        reader = RecordBatchStreamReader.open_file(str(path))
        rb = reader.next_batch()
        assert rb is not None
        assert rb.num_rows == BATCH_ROW_COUNT_LARGE
        for i in range(BATCH_ROW_COUNT_LARGE):
            assert rb.get_int32(0, i) == i
            assert math.isclose(rb.get_float64(1, i), i * 0.5)
        rb.release()
        assert reader.next_batch() is None
        reader.close()
        schema.release()

    def test_missing_file_raises(self):
        """
        title: Ensure opening a missing file raises a runtime error.
        """
        with pytest.raises(RuntimeError):
            RecordBatchStreamReader.open_file("/nonexistent/path.arrows")


# Large batch stress test


class TestLargeBatch:
    @pytest.mark.parametrize("n", [1_000, 100_000])
    def test_large_batch(self, n: int) -> None:
        """
        title: Ensure large batches can be written and read back.
        parameters:
          n:
            type: int
        """
        schema = RecordBatchSchema()
        schema.add_field("x", IrxColumnType.INT64)
        schema.add_field("y", IrxColumnType.FLOAT64)

        writer = RecordBatchStreamWriter.open_buffer(schema)
        builder = RecordBatchBuilder(schema)
        for i in range(n):
            builder.append_int64(0, i)
            builder.append_float64(1, i * 3.14)
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()

        reader = RecordBatchStreamReader.open_buffer(data)
        rb = reader.next_batch()
        assert rb is not None
        assert rb.num_rows == n
        assert rb.get_int64(0, n - 1) == n - 1
        assert math.isclose(
            rb.get_float64(1, n - 1), (n - 1) * 3.14, rel_tol=1e-9
        )
        rb.release()
        reader.close()
        schema.release()


# PyArrow IPC interop — the core ecosystem-compatibility guarantee


class TestPyArrowInterop:
    """
    title: TestPyArrowInterop.
    """

    def test_irx_buffer_read_by_pyarrow(self):
        """
        title: Ensure PyArrow can read IRx-written IPC bytes.
        """
        schema = make_simple_schema()  # id INT32 non-null, value FLOAT64 null
        writer = RecordBatchStreamWriter.open_buffer(schema)
        builder = RecordBatchBuilder(schema)
        for i in range(5):
            builder.append_int32(0, i)
            if i % 2 == 0:
                builder.append_float64(1, i * 1.5)
            else:
                builder.append_null(1)
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()
        schema.release()

        # PyArrow consumes the IRx-produced IPC bytes directly.
        table = pa.ipc.open_stream(pa.py_buffer(data)).read_all()

        assert table.num_rows == PYARROW_ROW_COUNT
        assert table.column_names == ["id", "value"]
        assert table.schema.field("id").type == pa.int32()
        assert table.schema.field("value").type == pa.float64()
        assert table.column("id").to_pylist() == [0, 1, 2, 3, 4]
        assert table.column("value").to_pylist() == [0.0, None, 3.0, None, 6.0]

    def test_pyarrow_buffer_read_by_irx(self):
        """
        title: Ensure the IRx reader can import PyArrow-written IPC bytes.
        """
        pa_schema = pa.schema(
            [
                pa.field("id", pa.int32(), nullable=False),
                pa.field("value", pa.float64(), nullable=True),
            ]
        )
        record_batch = pa.record_batch(
            [
                pa.array([10, 20, 30], type=pa.int32()),
                pa.array([1.5, None, 4.5], type=pa.float64()),
            ],
            schema=pa_schema,
        )
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, pa_schema) as pa_writer:
            pa_writer.write_batch(record_batch)
        data = sink.getvalue().to_pybytes()

        reader = RecordBatchStreamReader.open_buffer(data)
        rb = reader.next_batch()
        assert rb is not None
        assert rb.num_rows == PYARROW_BATCH_ROW_COUNT
        assert rb.num_columns == PYARROW_BATCH_COLUMN_COUNT
        assert rb.get_int32(0, 0) == PYARROW_FIRST_INT32_VALUE
        assert rb.get_int32(0, 2) == PYARROW_LAST_INT32_VALUE
        assert math.isclose(rb.get_float64(1, 0), 1.5)
        assert rb.is_null(1, 1) is True
        assert math.isclose(rb.get_float64(1, 2), 4.5)
        rb.release()
        assert reader.next_batch() is None
        reader.close()

    def test_irx_pyarrow_all_numeric_types(self):
        """
        title: >-
          Ensure fixed-width numeric types survive the IRx to PyArrow trip.
        """
        schema = RecordBatchSchema()
        schema.add_field("i8", IrxColumnType.INT8)
        schema.add_field("u32", IrxColumnType.UINT32)
        schema.add_field("f32", IrxColumnType.FLOAT32)
        schema.add_field("b", IrxColumnType.BOOL)

        writer = RecordBatchStreamWriter.open_buffer(schema)
        builder = RecordBatchBuilder(schema)
        builder.append_int8(0, -5)
        builder.append_uint32(1, 4_000_000_000)
        builder.append_float32(2, 1.25)
        builder.append_bool(3, True)
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()
        schema.release()

        table = pa.ipc.open_stream(pa.py_buffer(data)).read_all()
        assert table.schema.field("i8").type == pa.int8()
        assert table.schema.field("u32").type == pa.uint32()
        assert table.schema.field("f32").type == pa.float32()
        assert table.schema.field("b").type == pa.bool_()
        assert table.column("i8").to_pylist() == [-5]
        assert table.column("u32").to_pylist() == [4_000_000_000]
        assert math.isclose(table.column("f32").to_pylist()[0], 1.25)
        assert table.column("b").to_pylist() == [True]


# UTF-8 string types — utf8 and large_utf8


class TestStringTypes:
    """
    title: TestStringTypes.
    """

    def test_build_and_inspect_utf8(self):
        """
        title: Build a utf8 column and read the values back.
        """
        schema = RecordBatchSchema()
        schema.add_field("s", IrxColumnType.UTF8, nullable=False)
        builder = RecordBatchBuilder(schema)
        words = ["alpha", "", "gamma"]
        for w in words:
            builder.append_string(0, w)
        batch = builder.finish()
        assert batch.num_rows == len(words)
        for i, w in enumerate(words):
            assert batch.get_string(0, i) == w
        batch.release()
        builder.release()
        schema.release()

    def test_unicode_round_trip(self):
        """
        title: Ensure multi-byte UTF-8 survives a byte-length round-trip.
        """
        schema = RecordBatchSchema()
        schema.add_field("s", IrxColumnType.UTF8, nullable=False)
        builder = RecordBatchBuilder(schema)
        words = ["héllo", "日本語", "😀🎉"]
        for w in words:
            builder.append_string(0, w)
        batch = builder.finish()
        for i, w in enumerate(words):
            assert batch.get_string(0, i) == w
        batch.release()
        builder.release()
        schema.release()

    def test_string_nulls(self):
        """
        title: Ensure null slots in a string column read back as null.
        """
        schema = RecordBatchSchema()
        schema.add_field("s", IrxColumnType.UTF8, nullable=True)
        builder = RecordBatchBuilder(schema)
        builder.append_string(0, "present")
        builder.append_null(0)
        builder.append_string(0, "again")
        batch = builder.finish()
        assert batch.is_null(0, 0) is False
        assert batch.is_null(0, 1) is True
        assert batch.get_string(0, 0) == "present"
        assert batch.get_string(0, 2) == "again"
        batch.release()
        builder.release()
        schema.release()

    def test_large_utf8(self):
        """
        title: Ensure the large_utf8 (64-bit offset) column works.
        """
        schema = RecordBatchSchema()
        schema.add_field("s", IrxColumnType.LARGE_UTF8, nullable=False)
        builder = RecordBatchBuilder(schema)
        words = ["one", "two", "three"]
        for w in words:
            builder.append_string(0, w)
        batch = builder.finish()
        for i, w in enumerate(words):
            assert batch.get_string(0, i) == w
        batch.release()
        builder.release()
        schema.release()

    def test_wrong_column_type_raises(self):
        """
        title: Ensure appending a string to a numeric column is rejected.
        """
        schema = RecordBatchSchema()
        schema.add_field("n", IrxColumnType.INT32, nullable=False)
        builder = RecordBatchBuilder(schema)
        with pytest.raises(RuntimeError):
            builder.append_string(0, "nope")
        builder.release()
        schema.release()

    def test_get_string_on_non_string_column_raises(self):
        """
        title: Ensure get_string on a numeric column raises a type error.
        """
        schema = RecordBatchSchema()
        schema.add_field("n", IrxColumnType.INT32, nullable=False)
        builder = RecordBatchBuilder(schema)
        builder.append_int32(0, 42)
        batch = builder.finish()
        with pytest.raises(RuntimeError, match="type mismatch"):
            batch.get_string(0, 0)
        batch.release()
        builder.release()
        schema.release()

    def test_buffer_round_trip(self):
        """
        title: Ensure string columns survive an in-memory stream round-trip.
        """
        schema = RecordBatchSchema()
        schema.add_field("name", IrxColumnType.UTF8, nullable=True)
        schema.add_field("tag", IrxColumnType.LARGE_UTF8, nullable=False)
        writer = RecordBatchStreamWriter.open_buffer(schema)
        builder = RecordBatchBuilder(schema)
        names = ["ann", None, "cat"]
        for i, nm in enumerate(names):
            if nm is None:
                builder.append_null(0)
            else:
                builder.append_string(0, nm)
            builder.append_string(1, f"t{i}")
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()

        reader = RecordBatchStreamReader.open_buffer(data)
        rb = reader.next_batch()
        assert rb is not None
        for i, nm in enumerate(names):
            if nm is None:
                assert rb.is_null(0, i) is True
            else:
                assert rb.get_string(0, i) == nm
            assert rb.get_string(1, i) == f"t{i}"
        rb.release()
        reader.close()
        schema.release()

    def test_irx_strings_read_by_pyarrow(self):
        """
        title: Ensure PyArrow reads IRx-written utf8 and large_utf8 columns.
        """
        schema = RecordBatchSchema()
        schema.add_field("name", IrxColumnType.UTF8, nullable=True)
        schema.add_field("tag", IrxColumnType.LARGE_UTF8, nullable=False)
        writer = RecordBatchStreamWriter.open_buffer(schema)
        builder = RecordBatchBuilder(schema)
        builder.append_string(0, "x")
        builder.append_null(0)
        builder.append_string(1, "a")
        builder.append_string(1, "b")
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()
        schema.release()

        table = pa.ipc.open_stream(pa.py_buffer(data)).read_all()
        assert table.schema.field("name").type == pa.utf8()
        assert table.schema.field("tag").type == pa.large_utf8()
        assert table.column("name").to_pylist() == ["x", None]
        assert table.column("tag").to_pylist() == ["a", "b"]

    def test_pyarrow_strings_read_by_irx(self):
        """
        title: Ensure the IRx reader imports PyArrow-written string columns.
        """
        pa_schema = pa.schema(
            [
                pa.field("name", pa.utf8(), nullable=True),
                pa.field("tag", pa.large_utf8(), nullable=False),
            ]
        )
        record_batch = pa.record_batch(
            [
                pa.array(["foo", None, "baz"], type=pa.utf8()),
                pa.array(["p", "q", "r"], type=pa.large_utf8()),
            ],
            schema=pa_schema,
        )
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, pa_schema) as pa_writer:
            pa_writer.write_batch(record_batch)
        data = sink.getvalue().to_pybytes()

        reader = RecordBatchStreamReader.open_buffer(data)
        rb = reader.next_batch()
        assert rb is not None
        assert rb.get_string(0, 0) == "foo"
        assert rb.is_null(0, 1) is True
        assert rb.get_string(0, 2) == "baz"
        assert rb.get_string(1, 0) == "p"
        assert rb.get_string(1, 2) == "r"
        rb.release()
        reader.close()


class TestTemporalTypes:
    """
    title: TestTemporalTypes.
    """

    def test_date32_round_trip(self):
        """
        title: >-
          Ensure date32 accepts datetime.date and returns days-since-epoch.
        """
        schema = RecordBatchSchema()
        schema.add_field("d", IrxColumnType.DATE32, nullable=False)
        builder = RecordBatchBuilder(schema)
        values = [date(1970, 1, 1), date(2026, 7, 17), date(1965, 3, 4)]
        for v in values:
            builder.append_date(0, v)
        batch = builder.finish()
        for i, v in enumerate(values):
            expected = (v - date(1970, 1, 1)).days
            assert batch.get_date(0, i) == expected
        batch.release()
        builder.release()
        schema.release()

    def test_date64_round_trip(self):
        """
        title: Ensure date64 stores milliseconds since epoch.
        """
        schema = RecordBatchSchema()
        schema.add_field("d", IrxColumnType.DATE64, nullable=False)
        builder = RecordBatchBuilder(schema)
        v = date(2026, 7, 17)
        builder.append_date(0, v)
        batch = builder.finish()
        expected_ms = (v - date(1970, 1, 1)).days * 86_400_000
        assert batch.get_date(0, 0) == expected_ms
        batch.release()
        builder.release()
        schema.release()

    def test_date_accepts_raw_int(self):
        """
        title: Ensure append_date also accepts raw storage ints.
        """
        schema = RecordBatchSchema()
        schema.add_field("d", IrxColumnType.DATE32, nullable=False)
        builder = RecordBatchBuilder(schema)
        builder.append_date(0, RAW_DATE32_DAYS)
        batch = builder.finish()
        assert batch.get_date(0, 0) == RAW_DATE32_DAYS
        batch.release()
        builder.release()
        schema.release()

    def test_timestamp_all_units_round_trip(self):
        """
        title: Ensure every timestamp unit round-trips at its native scale.
        """
        schema = RecordBatchSchema()
        schema.add_field("ts_s", IrxColumnType.TIMESTAMP_S, nullable=False)
        schema.add_field("ts_ms", IrxColumnType.TIMESTAMP_MS, nullable=False)
        schema.add_field("ts_us", IrxColumnType.TIMESTAMP_US, nullable=False)
        schema.add_field("ts_ns", IrxColumnType.TIMESTAMP_NS, nullable=False)
        builder = RecordBatchBuilder(schema)
        dt = datetime(2026, 7, 17, 12, 34, 56, 789012, tzinfo=timezone.utc)
        for col in range(4):
            builder.append_timestamp(col, dt)
        batch = builder.finish()

        total_us = (
            (dt - datetime(1970, 1, 1, tzinfo=timezone.utc)).days
            * 86_400_000_000
            + (dt.hour * 3600 + dt.minute * 60 + dt.second) * 1_000_000
            + dt.microsecond
        )
        assert batch.get_timestamp(0, 0) == total_us // 1_000_000
        assert batch.get_timestamp(1, 0) == total_us // 1_000
        assert batch.get_timestamp(2, 0) == total_us
        assert batch.get_timestamp(3, 0) == total_us * 1_000
        batch.release()
        builder.release()
        schema.release()

    def test_timestamp_naive_treated_as_utc(self):
        """
        title: Ensure a naive datetime is interpreted as UTC on append.
        """
        schema = RecordBatchSchema()
        schema.add_field("ts", IrxColumnType.TIMESTAMP_S, nullable=False)
        builder = RecordBatchBuilder(schema)
        naive = datetime(2026, 7, 17, 12, 0, 0)
        aware = datetime(2026, 7, 17, 12, 0, 0, tzinfo=timezone.utc)
        builder.append_timestamp(0, naive)
        builder.append_timestamp(0, aware)
        batch = builder.finish()
        assert batch.get_timestamp(0, 0) == batch.get_timestamp(0, 1)
        batch.release()
        builder.release()
        schema.release()

    def test_time_all_units_round_trip(self):
        """
        title: Ensure every time unit round-trips at its native scale.
        """
        schema = RecordBatchSchema()
        schema.add_field("t_s", IrxColumnType.TIME32_S, nullable=False)
        schema.add_field("t_ms", IrxColumnType.TIME32_MS, nullable=False)
        schema.add_field("t_us", IrxColumnType.TIME64_US, nullable=False)
        schema.add_field("t_ns", IrxColumnType.TIME64_NS, nullable=False)
        builder = RecordBatchBuilder(schema)
        tv = time(12, 34, 56, 789012)
        for col in range(4):
            builder.append_time(col, tv)
        batch = builder.finish()

        total_us = (
            tv.hour * 3600 + tv.minute * 60 + tv.second
        ) * 1_000_000 + tv.microsecond
        assert batch.get_time(0, 0) == total_us // 1_000_000
        assert batch.get_time(1, 0) == total_us // 1_000
        assert batch.get_time(2, 0) == total_us
        assert batch.get_time(3, 0) == total_us * 1_000
        batch.release()
        builder.release()
        schema.release()

    def test_temporal_nulls(self):
        """
        title: Ensure null slots in temporal columns read back as null.
        """
        schema = RecordBatchSchema()
        schema.add_field("d", IrxColumnType.DATE32, nullable=True)
        schema.add_field("ts", IrxColumnType.TIMESTAMP_US, nullable=True)
        schema.add_field("t", IrxColumnType.TIME64_NS, nullable=True)
        builder = RecordBatchBuilder(schema)
        builder.append_date(0, date(2026, 7, 17))
        builder.append_null(0)
        builder.append_timestamp(1, datetime(2026, 7, 17, tzinfo=timezone.utc))
        builder.append_null(1)
        builder.append_time(2, time(1, 2, 3))
        builder.append_null(2)
        batch = builder.finish()
        assert batch.is_null(0, 0) is False
        assert batch.is_null(0, 1) is True
        assert batch.is_null(1, 1) is True
        assert batch.is_null(2, 1) is True
        batch.release()
        builder.release()
        schema.release()

    def test_append_wrong_type_raises(self):
        """
        title: Ensure temporal appenders reject non-matching column types.
        """
        schema = RecordBatchSchema()
        schema.add_field("n", IrxColumnType.INT32, nullable=False)
        builder = RecordBatchBuilder(schema)
        with pytest.raises(RuntimeError, match="type mismatch"):
            builder.append_date(0, 0)
        with pytest.raises(RuntimeError, match="type mismatch"):
            builder.append_timestamp(0, 0)
        with pytest.raises(RuntimeError, match="type mismatch"):
            builder.append_time(0, 0)
        builder.release()
        schema.release()

    def test_get_wrong_type_raises(self):
        """
        title: Ensure temporal getters reject non-matching column types.
        """
        schema = RecordBatchSchema()
        schema.add_field("n", IrxColumnType.INT32, nullable=False)
        builder = RecordBatchBuilder(schema)
        builder.append_int32(0, 42)
        batch = builder.finish()
        with pytest.raises(RuntimeError, match="type mismatch"):
            batch.get_date(0, 0)
        with pytest.raises(RuntimeError, match="type mismatch"):
            batch.get_timestamp(0, 0)
        with pytest.raises(RuntimeError, match="type mismatch"):
            batch.get_time(0, 0)
        batch.release()
        builder.release()
        schema.release()

    def test_temporal_family_mismatch_raises(self):
        """
        title: Ensure append_date rejects a timestamp column and vice versa.
        """
        schema = RecordBatchSchema()
        schema.add_field("ts", IrxColumnType.TIMESTAMP_US, nullable=False)
        schema.add_field("d", IrxColumnType.DATE32, nullable=False)
        builder = RecordBatchBuilder(schema)
        with pytest.raises(RuntimeError, match="type mismatch"):
            builder.append_date(0, 0)
        with pytest.raises(RuntimeError, match="type mismatch"):
            builder.append_timestamp(1, 0)
        builder.release()
        schema.release()

    def test_date32_overflow_rejected(self):
        """
        title: append_date rejects values outside int32 range for DATE32.
        summary: |-
          A millisecond-epoch value passed to a DATE32 column would silently
          narrow to a bogus day count; the native guard must reject it instead.
        """
        schema = RecordBatchSchema()
        schema.add_field("d", IrxColumnType.DATE32, nullable=False)
        builder = RecordBatchBuilder(schema)
        with pytest.raises(RuntimeError, match="out of int32 range"):
            builder.append_date(0, 2**40)
        with pytest.raises(RuntimeError, match="out of int32 range"):
            builder.append_date(0, -(2**40))
        builder.release()
        schema.release()

    def test_time32_overflow_rejected(self):
        """
        title: append_time rejects values outside int32 range for TIME32.
        """
        schema = RecordBatchSchema()
        schema.add_field("t", IrxColumnType.TIME32_MS, nullable=False)
        builder = RecordBatchBuilder(schema)
        with pytest.raises(RuntimeError, match="out of int32 range"):
            builder.append_time(0, 2**40)
        builder.release()
        schema.release()

    def test_buffer_round_trip(self):
        """
        title: Ensure temporal columns survive a stream round-trip.
        """
        schema = RecordBatchSchema()
        schema.add_field("d", IrxColumnType.DATE32, nullable=True)
        schema.add_field("ts", IrxColumnType.TIMESTAMP_MS, nullable=False)
        schema.add_field("t", IrxColumnType.TIME64_US, nullable=False)
        writer = RecordBatchStreamWriter.open_buffer(schema)
        builder = RecordBatchBuilder(schema)
        d = date(2026, 7, 17)
        dt = datetime(2026, 7, 17, 9, 30, tzinfo=timezone.utc)
        tv = time(9, 30, 15, 250000)
        builder.append_date(0, d)
        builder.append_null(0)
        builder.append_timestamp(1, dt)
        builder.append_timestamp(1, dt)
        builder.append_time(2, tv)
        builder.append_time(2, tv)
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()
        schema.release()

        reader = RecordBatchStreamReader.open_buffer(data)
        rb = reader.next_batch()
        assert rb is not None
        assert rb.get_date(0, 0) == (d - date(1970, 1, 1)).days
        assert rb.is_null(0, 1) is True
        expected_ms = int(
            (dt - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds()
            * 1000
        )
        assert rb.get_timestamp(1, 0) == expected_ms
        expected_us = (
            tv.hour * 3600 + tv.minute * 60 + tv.second
        ) * 1_000_000 + tv.microsecond
        assert rb.get_time(2, 0) == expected_us
        rb.release()
        reader.close()

    def test_irx_temporal_read_by_pyarrow(self):
        """
        title: Ensure PyArrow reads IRx-written temporal columns.
        """
        schema = RecordBatchSchema()
        schema.add_field("d", IrxColumnType.DATE32, nullable=False)
        schema.add_field("ts", IrxColumnType.TIMESTAMP_US, nullable=False)
        schema.add_field("t", IrxColumnType.TIME64_NS, nullable=False)
        writer = RecordBatchStreamWriter.open_buffer(schema)
        builder = RecordBatchBuilder(schema)
        d = date(2026, 7, 17)
        dt = datetime(2026, 7, 17, 9, 30, tzinfo=timezone.utc)
        tv = time(9, 30, 15, 250000)
        builder.append_date(0, d)
        builder.append_timestamp(1, dt)
        builder.append_time(2, tv)
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()
        schema.release()

        table = pa.ipc.open_stream(pa.py_buffer(data)).read_all()
        assert table.schema.field("d").type == pa.date32()
        assert table.schema.field("ts").type == pa.timestamp("us")
        assert table.schema.field("t").type == pa.time64("ns")
        assert table.column("d").to_pylist() == [d]
        assert table.column("ts").to_pylist() == [dt.replace(tzinfo=None)]
        assert table.column("t").to_pylist() == [tv]

    def test_pyarrow_temporal_read_by_irx(self):
        """
        title: Ensure the IRx reader imports PyArrow-written temporal columns.
        """
        d = date(2026, 7, 17)
        dt = datetime(2026, 7, 17, 9, 30)
        tv = time(9, 30, 15, 250000)
        pa_schema = pa.schema(
            [
                pa.field("d", pa.date32(), nullable=False),
                pa.field("ts", pa.timestamp("us"), nullable=False),
                pa.field("t", pa.time64("ns"), nullable=False),
            ]
        )
        record_batch = pa.record_batch(
            [
                pa.array([d], type=pa.date32()),
                pa.array([dt], type=pa.timestamp("us")),
                pa.array([tv], type=pa.time64("ns")),
            ],
            schema=pa_schema,
        )
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, pa_schema) as pa_writer:
            pa_writer.write_batch(record_batch)
        data = sink.getvalue().to_pybytes()

        reader = RecordBatchStreamReader.open_buffer(data)
        rb = reader.next_batch()
        assert rb is not None
        assert rb.get_date(0, 0) == (d - date(1970, 1, 1)).days
        expected_us = int(
            (
                dt.replace(tzinfo=timezone.utc)
                - datetime(1970, 1, 1, tzinfo=timezone.utc)
            ).total_seconds()
            * 1_000_000
        )
        assert rb.get_timestamp(1, 0) == expected_us
        expected_ns = (
            (tv.hour * 3600 + tv.minute * 60 + tv.second) * 1_000_000
            + tv.microsecond
        ) * 1_000
        assert rb.get_time(2, 0) == expected_ns
        rb.release()
        reader.close()


# List column tests


class TestListColumns:
    """
    title: List column build, inspection, streaming, and PyArrow interop.
    """

    def test_build_and_read_int_lists(self):
        """
        title: Build a list<int32> column and read every row back.
        """
        schema = RecordBatchSchema()
        schema.add_field("id", IrxColumnType.INT32, nullable=False)
        schema.add_list_field("xs", IrxColumnType.INT32, nullable=True)
        builder = RecordBatchBuilder(schema)
        rows = [[10, 20, 30], [], [42]]
        for i, xs in enumerate(rows):
            builder.append_int32(0, i)
            builder.append_list(1, xs)
        batch = builder.finish()

        assert batch.num_rows == len(rows)
        for i, xs in enumerate(rows):
            assert batch.get_int32(0, i) == i
            assert batch.get_list(1, i) == xs
        batch.release()
        builder.release()
        schema.release()

    def test_null_list_slot(self):
        """
        title: A null list slot reads back as None, unlike an empty list.
        """
        schema = RecordBatchSchema()
        schema.add_list_field("xs", IrxColumnType.INT64, nullable=True)
        builder = RecordBatchBuilder(schema)
        builder.append_list(0, [1, 2])
        builder.append_null(0)
        builder.append_list(0, [])
        batch = builder.finish()

        assert batch.get_list(0, 0) == [1, 2]
        assert batch.is_null(0, 1) is True
        assert batch.get_list(0, 1) is None
        assert batch.is_null(0, 2) is False
        assert batch.get_list(0, 2) == []
        batch.release()
        builder.release()
        schema.release()

    def test_float_lists(self):
        """
        title: Build and read a list<float64> column.
        """
        schema = RecordBatchSchema()
        schema.add_list_field("fs", IrxColumnType.FLOAT64)
        builder = RecordBatchBuilder(schema)
        builder.append_list(0, [1.5, 2.5, 3.5])
        batch = builder.finish()

        result = batch.get_list(0, 0)
        assert result is not None
        assert all(math.isclose(a, b) for a, b in zip(result, [1.5, 2.5, 3.5]))
        batch.release()
        builder.release()
        schema.release()

    def test_date_element_lists(self):
        """
        title: Temporal list elements accept date objects and read back raw.
        """
        schema = RecordBatchSchema()
        schema.add_list_field("ds", IrxColumnType.DATE32)
        builder = RecordBatchBuilder(schema)
        days = [date(2026, 7, 17), date(1970, 1, 1)]
        builder.append_list(0, days)
        batch = builder.finish()

        expected = [(d - date(1970, 1, 1)).days for d in days]
        assert batch.get_list(0, 0) == expected
        batch.release()
        builder.release()
        schema.release()

    def test_unsupported_element_type_raises(self):
        """
        title: Schema rejects list element types outside the supported set.
        """
        schema = RecordBatchSchema()
        with pytest.raises(ValueError):
            schema.add_list_field("bad", IrxColumnType.BOOL)
        with pytest.raises(ValueError):
            schema.add_list_field("bad", IrxColumnType.UTF8)
        schema.release()

    def test_append_list_on_scalar_column_raises(self):
        """
        title: append_list on a non-list column raises rather than corrupting.
        """
        schema = RecordBatchSchema()
        schema.add_field("id", IrxColumnType.INT32)
        builder = RecordBatchBuilder(schema)
        with pytest.raises(ValueError):
            builder.append_list(0, [1, 2, 3])
        builder.release()
        schema.release()

    def test_list_buffer_round_trip(self):
        """
        title: A list column survives an IPC buffer round-trip.
        """
        schema = RecordBatchSchema()
        schema.add_list_field("xs", IrxColumnType.INT32, nullable=True)
        writer = RecordBatchStreamWriter.open_buffer(schema)
        builder = RecordBatchBuilder(schema)
        rows = [[1, 2, 3], [], None, [7]]
        for xs in rows:
            if xs is None:
                builder.append_null(0)
            else:
                builder.append_list(0, xs)
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()
        schema.release()

        reader = RecordBatchStreamReader.open_buffer(data)
        rb = reader.next_batch()
        assert rb is not None
        assert rb.get_list(0, 0) == [1, 2, 3]
        assert rb.get_list(0, 1) == []
        assert rb.get_list(0, 2) is None
        assert rb.get_list(0, 3) == [7]
        rb.release()
        reader.close()

    def test_irx_list_read_by_pyarrow(self):
        """
        title: PyArrow can read an IRx-written list column.
        """
        schema = RecordBatchSchema()
        schema.add_list_field("xs", IrxColumnType.INT32, nullable=True)
        writer = RecordBatchStreamWriter.open_buffer(schema)
        builder = RecordBatchBuilder(schema)
        builder.append_list(0, [1, 2])
        builder.append_null(0)
        builder.append_list(0, [3, 4, 5])
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()
        schema.release()

        table = pa.ipc.open_stream(pa.py_buffer(data)).read_all()
        assert table.schema.field("xs").type == pa.list_(pa.int32())
        assert table.column("xs").to_pylist() == [[1, 2], None, [3, 4, 5]]

    def test_pyarrow_list_read_by_irx(self):
        """
        title: The IRx reader imports a PyArrow-written list column.
        """
        pa_schema = pa.schema(
            [pa.field("xs", pa.list_(pa.int32()), nullable=True)]
        )
        record_batch = pa.record_batch(
            [pa.array([[10, 20], None, [], [30]], type=pa.list_(pa.int32()))],
            schema=pa_schema,
        )
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, pa_schema) as pa_writer:
            pa_writer.write_batch(record_batch)
        data = sink.getvalue().to_pybytes()

        reader = RecordBatchStreamReader.open_buffer(data)
        rb = reader.next_batch()
        assert rb is not None
        assert rb.get_list(0, 0) == [10, 20]
        assert rb.get_list(0, 1) is None
        assert rb.get_list(0, 2) == []
        assert rb.get_list(0, 3) == [30]
        rb.release()
        reader.close()


class TestStructColumns:
    """
    title: Struct column build, inspection, streaming, and PyArrow interop.
    """

    def test_build_and_read_struct(self):
        """
        title: Build a struct column with mixed field types and read it back.
        """
        schema = RecordBatchSchema()
        schema.add_field("id", IrxColumnType.INT32, nullable=False)
        schema.add_struct_field(
            "point",
            [("x", IrxColumnType.INT32), ("y", IrxColumnType.FLOAT64)],
            nullable=True,
        )
        builder = RecordBatchBuilder(schema)
        points = [{"x": 10, "y": 2.5}, {"x": 20, "y": 3.5}]
        for i, point in enumerate(points):
            builder.append_int32(0, i)
            builder.append_struct(1, point)
        batch = builder.finish()

        assert batch.num_rows == len(points)
        for i, point in enumerate(points):
            assert batch.get_struct(1, i) == point
        batch.release()
        builder.release()
        schema.release()

    def test_append_struct_positional(self):
        """
        title: append_struct accepts a positional sequence in field order.
        """
        schema = RecordBatchSchema()
        schema.add_struct_field(
            "p",
            [("a", IrxColumnType.INT8), ("b", IrxColumnType.INT64)],
            nullable=False,
        )
        builder = RecordBatchBuilder(schema)
        builder.append_struct(0, [7, 1_000_000])
        batch = builder.finish()

        assert batch.get_struct(0, 0) == {"a": 7, "b": 1_000_000}
        batch.release()
        builder.release()
        schema.release()

    def test_null_struct_slot(self):
        """
        title: A null struct slot reads back as None.
        """
        schema = RecordBatchSchema()
        schema.add_struct_field(
            "p", [("x", IrxColumnType.INT32)], nullable=True
        )
        builder = RecordBatchBuilder(schema)
        builder.append_struct(0, {"x": 1})
        builder.append_null(0)
        builder.append_struct(0, {"x": 3})
        batch = builder.finish()

        assert batch.get_struct(0, 0) == {"x": 1}
        assert batch.get_struct(0, 1) is None
        assert batch.get_struct(0, 2) == {"x": 3}
        batch.release()
        builder.release()
        schema.release()

    def test_temporal_struct_fields(self):
        """
        title: Struct date/time fields take Python temporals, read as ints.
        """
        one_hour_us = 3600 * 1_000_000
        schema = RecordBatchSchema()
        schema.add_struct_field(
            "event",
            [("d", IrxColumnType.DATE32), ("t", IrxColumnType.TIME64_US)],
            nullable=False,
        )
        builder = RecordBatchBuilder(schema)
        builder.append_struct(0, {"d": date(2020, 1, 1), "t": time(1, 0, 0)})
        batch = builder.finish()

        result = batch.get_struct(0, 0)
        assert result["d"] == (date(2020, 1, 1) - date(1970, 1, 1)).days
        assert result["t"] == one_hour_us
        batch.release()
        builder.release()
        schema.release()

    def test_int32_field_overflow_rejected(self):
        """
        title: A too-wide value for an INT32 struct field is refused.
        """
        schema = RecordBatchSchema()
        schema.add_struct_field(
            "p", [("x", IrxColumnType.INT32)], nullable=False
        )
        builder = RecordBatchBuilder(schema)
        with pytest.raises(RuntimeError, match="out of int32 range"):
            builder.append_struct(0, {"x": 2**40})
        builder.release()
        schema.release()

    def test_unsupported_field_type_raises(self):
        """
        title: Schema rejects struct field types outside the supported set.
        """
        schema = RecordBatchSchema()
        with pytest.raises(ValueError):
            schema.add_struct_field("bad", [("f", IrxColumnType.BOOL)])
        with pytest.raises(ValueError):
            schema.add_struct_field("bad", [("f", IrxColumnType.UTF8)])
        schema.release()

    def test_empty_struct_rejected(self):
        """
        title: A struct column must declare at least one field.
        """
        schema = RecordBatchSchema()
        with pytest.raises(ValueError):
            schema.add_struct_field("empty", [])
        schema.release()

    def test_append_struct_on_scalar_column_raises(self):
        """
        title: append_struct on a non-struct column raises rather than corrupt.
        """
        schema = RecordBatchSchema()
        schema.add_field("id", IrxColumnType.INT32)
        builder = RecordBatchBuilder(schema)
        with pytest.raises(ValueError):
            builder.append_struct(0, {"x": 1})
        builder.release()
        schema.release()

    def test_struct_buffer_round_trip(self):
        """
        title: A struct column survives an IPC buffer round-trip.
        """
        schema = RecordBatchSchema()
        schema.add_struct_field(
            "point",
            [("x", IrxColumnType.INT32), ("y", IrxColumnType.INT32)],
            nullable=True,
        )
        writer = RecordBatchStreamWriter.open_buffer(schema)
        builder = RecordBatchBuilder(schema)
        builder.append_struct(0, {"x": 1, "y": 2})
        builder.append_null(0)
        builder.append_struct(0, {"x": 3, "y": 4})
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()
        schema.release()

        reader = RecordBatchStreamReader.open_buffer(data)
        rb = reader.next_batch()
        assert rb is not None
        assert rb.get_struct(0, 0) == {"x": 1, "y": 2}
        assert rb.get_struct(0, 1) is None
        assert rb.get_struct(0, 2) == {"x": 3, "y": 4}
        rb.release()
        reader.close()

    def test_irx_struct_read_by_pyarrow(self):
        """
        title: PyArrow can read an IRx-written struct column.
        """
        schema = RecordBatchSchema()
        schema.add_struct_field(
            "point",
            [("x", IrxColumnType.INT32), ("y", IrxColumnType.FLOAT64)],
            nullable=True,
        )
        writer = RecordBatchStreamWriter.open_buffer(schema)
        builder = RecordBatchBuilder(schema)
        builder.append_struct(0, {"x": 1, "y": 1.5})
        builder.append_null(0)
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()
        schema.release()

        table = pa.ipc.open_stream(pa.py_buffer(data)).read_all()
        assert table.schema.field("point").type == pa.struct(
            [("x", pa.int32()), ("y", pa.float64())]
        )
        assert table.column("point").to_pylist() == [
            {"x": 1, "y": 1.5},
            None,
        ]

    def test_pyarrow_struct_read_by_irx(self):
        """
        title: The IRx reader imports a PyArrow-written struct column.
        """
        struct_type = pa.struct([("x", pa.int32()), ("y", pa.float64())])
        pa_schema = pa.schema([pa.field("point", struct_type, nullable=True)])
        record_batch = pa.record_batch(
            [
                pa.array(
                    [{"x": 10, "y": 2.0}, None, {"x": 30, "y": 4.0}],
                    type=struct_type,
                )
            ],
            schema=pa_schema,
        )
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, pa_schema) as pa_writer:
            pa_writer.write_batch(record_batch)
        data = sink.getvalue().to_pybytes()

        reader = RecordBatchStreamReader.open_buffer(data)
        rb = reader.next_batch()
        assert rb is not None
        assert rb.get_struct(0, 0) == {"x": 10, "y": 2.0}
        assert rb.get_struct(0, 1) is None
        assert rb.get_struct(0, 2) == {"x": 30, "y": 4.0}
        rb.release()
        reader.close()
