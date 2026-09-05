"""
title: Legacy RecordBatch compatibility ABI tests.
"""

from __future__ import annotations

import ctypes
import re
import shutil
import subprocess

from pathlib import Path

import irx.record_batch as record_batch_module
import pytest

from irx.builder.runtime.arrow.bindings import (
    configure_arrow_ctypes_library,
)
from irx.builder.runtime.record_batch import RECORD_BATCH_SYMBOLS
from irx.record_batch import IrxColumnType

RUNTIME_NATIVE_DIR = (
    Path(__file__).parents[1]
    / "src"
    / "irx"
    / "builder"
    / "runtime"
    / "arrow"
    / "native"
)
LEGACY_HEADER = RUNTIME_NATIVE_DIR / "irx_record_batch.h"
ARROW_STATUS_OK = 0
ARROW_STATUS_NULL_POINTER = 101
ARROW_HANDLE_KIND_RECORD_BATCH = 8
ARROW_HANDLE_OWNERSHIP_SHARED = 1
LEGACY_NULL_POINTER = -2


class ArrowSchemaStruct(ctypes.Structure):
    """
    title: Mirror the ArrowSchema C Data structure for compatibility tests.
    """

    _fields_ = [
        ("format", ctypes.c_char_p),
        ("name", ctypes.c_char_p),
        ("metadata", ctypes.c_char_p),
        ("flags", ctypes.c_int64),
        ("n_children", ctypes.c_int64),
        ("children", ctypes.c_void_p),
        ("dictionary", ctypes.c_void_p),
        ("release", ctypes.c_void_p),
        ("private_data", ctypes.c_void_p),
    ]


class ArrowArrayStruct(ctypes.Structure):
    """
    title: Mirror the ArrowArray C Data structure for compatibility tests.
    """

    _fields_ = [
        ("length", ctypes.c_int64),
        ("null_count", ctypes.c_int64),
        ("offset", ctypes.c_int64),
        ("n_buffers", ctypes.c_int64),
        ("n_children", ctypes.c_int64),
        ("buffers", ctypes.c_void_p),
        ("children", ctypes.c_void_p),
        ("dictionary", ctypes.c_void_p),
        ("release", ctypes.c_void_p),
        ("private_data", ctypes.c_void_p),
    ]


def _assert_unified_ok(status: int, failure: ctypes.c_void_p) -> None:
    """
    title: Assert a successful unified ABI call with no error owner.
    parameters:
      status:
        type: int
      failure:
        type: ctypes.c_void_p
    """
    assert status == ARROW_STATUS_OK
    assert failure.value is None


def test_legacy_batches_are_unified_handles_across_both_abis() -> None:
    """
    title: Legacy construction and access should share the unified owner token.
    """
    library = record_batch_module._get_lib()
    configure_arrow_ctypes_library(
        library,
        features=("core", "array", "record_batch"),
    )
    schema = ctypes.c_void_p()
    builder = ctypes.c_void_p()
    legacy_batch = ctypes.c_void_p()
    retained = ctypes.c_void_p()
    imported = ctypes.c_void_p()
    failure = ctypes.c_void_p()
    exported_array = ArrowArrayStruct()
    exported_schema = ArrowSchemaStruct()

    assert library.irx_rb_schema_create(ctypes.byref(schema)) == 0
    try:
        assert (
            library.irx_rb_schema_add_field(
                schema,
                b"value",
                int(IrxColumnType.INT32),
                0,
            )
            == 0
        )
        assert (
            library.irx_rb_builder_create(schema, ctypes.byref(builder)) == 0
        )
        assert library.irx_rb_builder_append_int32(builder, 0, 42) == 0
        assert (
            library.irx_rb_builder_finish(
                builder,
                ctypes.byref(legacy_batch),
            )
            == 0
        )

        kind = ctypes.c_int32()
        ownership = ctypes.c_int32()
        _assert_unified_ok(
            library.irx_arrow_handle_kind_of(
                legacy_batch,
                ctypes.byref(kind),
                ctypes.byref(failure),
            ),
            failure,
        )
        _assert_unified_ok(
            library.irx_arrow_handle_ownership_of(
                legacy_batch,
                ctypes.byref(ownership),
                ctypes.byref(failure),
            ),
            failure,
        )
        assert kind.value == ARROW_HANDLE_KIND_RECORD_BATCH
        assert ownership.value == ARROW_HANDLE_OWNERSHIP_SHARED

        _assert_unified_ok(
            library.irx_arrow_record_batch_retain(
                legacy_batch,
                ctypes.byref(retained),
                ctypes.byref(failure),
            ),
            failure,
        )
        assert retained.value == legacy_batch.value

        library.irx_rb_batch_release(legacy_batch)
        legacy_batch.value = None
        rows = ctypes.c_int64()
        _assert_unified_ok(
            library.irx_arrow_record_batch_num_rows(
                retained,
                ctypes.byref(rows),
                ctypes.byref(failure),
            ),
            failure,
        )
        assert rows.value == 1

        _assert_unified_ok(
            library.irx_arrow_record_batch_export(
                retained,
                ctypes.byref(exported_array),
                ctypes.byref(exported_schema),
                ctypes.byref(failure),
            ),
            failure,
        )
        _assert_unified_ok(
            library.irx_arrow_record_batch_release(
                ctypes.byref(retained),
                ctypes.byref(failure),
            ),
            failure,
        )
        _assert_unified_ok(
            library.irx_arrow_record_batch_import_move(
                ctypes.byref(exported_array),
                ctypes.byref(exported_schema),
                ctypes.byref(imported),
                ctypes.byref(failure),
            ),
            failure,
        )
        assert exported_array.release is None
        assert exported_schema.release is None

        value = ctypes.c_int32()
        assert (
            library.irx_rb_batch_get_int32(
                imported,
                0,
                0,
                ctypes.byref(value),
            )
            == 0
        )
        assert value.value == 42  # noqa: PLR2004
        assert library.irx_rb_batch_num_rows(imported) == 1
        assert library.irx_rb_batch_num_columns(imported) == 1
    finally:
        if imported.value is not None:
            library.irx_rb_batch_release(imported)
            imported.value = None
        if retained.value is not None:
            _assert_unified_ok(
                library.irx_arrow_record_batch_release(
                    ctypes.byref(retained),
                    ctypes.byref(failure),
                ),
                failure,
            )
        if legacy_batch.value is not None:
            library.irx_rb_batch_release(legacy_batch)
        if builder.value is not None:
            library.irx_rb_builder_release(builder)
        if schema.value is not None:
            library.irx_rb_schema_release(schema)

    assert library.irx_rb_batch_num_rows(None) == LEGACY_NULL_POINTER
    assert b"must not be NULL" in library.irx_record_batch_errmsg()

    rows = ctypes.c_int64(99)
    assert (
        library.irx_arrow_record_batch_num_rows(
            None,
            ctypes.byref(rows),
            ctypes.byref(failure),
        )
        == ARROW_STATUS_NULL_POINTER
    )
    assert rows.value == 0
    assert failure.value is not None
    release_failure = ctypes.c_void_p()
    assert (
        library.irx_arrow_error_release(
            ctypes.byref(failure),
            ctypes.byref(release_failure),
        )
        == ARROW_STATUS_OK
    )
    assert failure.value is None
    assert release_failure.value is None


def test_every_irx_rb_declaration_is_marked_deprecated() -> None:
    """
    title: Every registered irx_rb symbol should carry the warning attribute.
    """
    header = LEGACY_HEADER.read_text(encoding="utf-8")
    expected = {
        name for name in RECORD_BATCH_SYMBOLS if name.startswith("irx_rb_")
    }
    deprecated = set(
        re.findall(
            r"^IRX_RB_DEPRECATED[^\n]*\b(irx_rb_[a-z0-9_]+)\(",
            header,
            flags=re.MULTILINE,
        )
    )

    assert deprecated == expected


def test_legacy_header_emits_and_can_suppress_deprecation_warning(
    tmp_path: Path,
) -> None:
    """
    title: C consumers should receive an actionable irx_rb migration warning.
    parameters:
      tmp_path:
        type: Path
    """
    compiler = shutil.which("clang") or shutil.which("cc")
    if compiler is None:
        pytest.skip("a C compiler is required for the deprecation test")

    source = tmp_path / "legacy_probe.c"
    output = tmp_path / "legacy_probe.o"
    source.write_text(
        '#include "irx_record_batch.h"\n'
        "int probe(const IrxRbBatch *batch) {\n"
        "  return irx_rb_batch_num_columns(batch);\n"
        "}\n",
        encoding="utf-8",
    )
    command = [
        compiler,
        "-std=c11",
        "-Werror=deprecated-declarations",
        "-I",
        str(RUNTIME_NATIVE_DIR),
        "-c",
        str(source),
        "-o",
        str(output),
    ]

    warned = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    assert warned.returncode != 0
    assert "use the irx_arrow ABI" in warned.stderr

    source.write_text(
        "#define IRX_RECORD_BATCH_DISABLE_DEPRECATION_WARNINGS\n"
        + source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    subprocess.run(command, check=True, capture_output=True, text=True)
