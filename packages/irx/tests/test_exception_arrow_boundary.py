"""
title: Checked Arrow facade output, typed errors, and same-process recovery.
"""

import ctypes

from pathlib import Path

from irx.builder.runtime.record_batch import ensure_record_batch_shared_library
from irx.record_batch import load_parquet_plugin

ERROR_CAPACITY = 1024
TYPE_ERROR = -4
INDEX_ERROR = -3
VALUE_ERROR = -6
NULL_ERROR = -2
OS_ERROR = -5


def test_checked_parquet_options_copy_accepts_absent_source() -> None:
    """
    title: Omitted Parquet options create defaults without weakening outputs.
    """
    native = load_parquet_plugin()
    pointer = ctypes.c_void_p
    output = ctypes.POINTER(pointer)
    text = ctypes.c_char_p
    native.irx_rb_api_options_copy.argtypes = [pointer, output, text]
    native.irx_rb_api_options_int.argtypes = [
        pointer,
        text,
        ctypes.c_int64,
        text,
    ]
    native.irx_rb_api_options_destroy.argtypes = [pointer, text]
    source, copied = pointer(), pointer()
    error = ctypes.create_string_buffer(ERROR_CAPACITY)
    assert native.irx_rb_api_options_copy(None, None, error) == NULL_ERROR
    assert error.value == b"missing result slot"
    assert (
        native.irx_rb_api_options_copy(None, ctypes.byref(source), error) == 0
    )
    try:
        assert source.value is not None and error.value == b""
        assert (
            native.irx_rb_api_options_copy(source, ctypes.byref(copied), error)
            == 0
        )
        assert copied.value is not None and copied.value != source.value
    finally:
        assert native.irx_rb_api_options_destroy(source, error) == 0
    try:
        assert (
            native.irx_rb_api_options_int(copied, b"batch_size", 2, error) == 0
        )
    finally:
        assert native.irx_rb_api_options_destroy(copied, error) == 0


def test_checked_facade_recovery_and_atomic_outputs(tmp_path: Path) -> None:
    """
    title: Failed calls publish no result and a later valid call can succeed.
    parameters:
      tmp_path:
        type: Path
    """
    native = ctypes.CDLL(str(ensure_record_batch_shared_library()))
    pointer = ctypes.c_void_p
    output = ctypes.POINTER(pointer)
    text = ctypes.c_char_p
    integer = ctypes.c_int32
    native.irx_rb_api_schema_new.argtypes = [output, text]
    native.irx_rb_api_schema_add.argtypes = [
        pointer,
        text,
        integer,
        integer,
        text,
    ]
    native.irx_rb_api_schema_name.argtypes = [pointer, integer, output, text]
    native.irx_rb_api_schema_count.argtypes = [
        pointer,
        ctypes.POINTER(integer),
        text,
    ]
    native.irx_rb_api_schema_destroy.argtypes = [pointer, text]
    native.irx_rb_api_reader_new.argtypes = [output, text]
    native.irx_rb_api_reader_file.argtypes = [pointer, text, text]
    native.irx_rb_api_reader_destroy.argtypes = [pointer, text]
    schema = pointer()
    reader = pointer()
    error = ctypes.create_string_buffer(ERROR_CAPACITY)
    assert native.irx_rb_api_schema_new(ctypes.byref(schema), error) == 0
    assert native.irx_rb_api_reader_new(ctypes.byref(reader), error) == 0
    try:
        result = pointer(123)
        status = native.irx_rb_api_schema_name(
            schema, 9, ctypes.byref(result), error
        )
        assert status == INDEX_ERROR
        assert result.value is None
        assert error.value
        assert native.irx_rb_api_schema_add(schema, b"value", 2, 0, error) == 0
        count = integer(-1)
        assert (
            native.irx_rb_api_schema_count(schema, ctypes.byref(count), error)
            == 0
        )
        assert count.value == 1 and error.value == b""
        assert (
            native.irx_rb_api_schema_count(None, ctypes.byref(count), error)
            == NULL_ERROR
        )
        assert count.value == 0
        assert (
            native.irx_rb_api_reader_file(
                reader, bytes(tmp_path / "missing"), error
            )
            == OS_ERROR
        )
        assert error.value
    finally:
        assert native.irx_rb_api_reader_destroy(reader, error) == 0
        assert native.irx_rb_api_schema_destroy(schema, error) == 0


def test_checked_facade_type_bounds_and_null_values() -> None:
    """
    title: Structured type and bounds failures preserve initialized outputs.
    """
    native = ctypes.CDLL(str(ensure_record_batch_shared_library()))
    pointer = ctypes.c_void_p
    output = ctypes.POINTER(pointer)
    text = ctypes.c_char_p
    integer = ctypes.c_int32
    wide = ctypes.c_int64
    native.irx_rb_api_schema_new.argtypes = [output, text]
    native.irx_rb_api_schema_add.argtypes = [
        pointer,
        text,
        integer,
        integer,
        text,
    ]
    native.irx_rb_api_builder_new.argtypes = [pointer, output, text]
    native.irx_rb_api_batch_new.argtypes = [output, text]
    native.irx_rb_api_append_i32.argtypes = [pointer, integer, integer, text]
    native.irx_rb_api_append_null.argtypes = [pointer, integer, text]
    native.irx_rb_api_builder_finish.argtypes = [pointer, pointer, text]
    native.irx_rb_api_get_i32.argtypes = [
        pointer,
        integer,
        wide,
        ctypes.POINTER(integer),
        text,
    ]
    native.irx_rb_api_get_i64.argtypes = [
        pointer,
        integer,
        wide,
        ctypes.POINTER(wide),
        text,
    ]
    for name in ("schema", "builder", "batch"):
        getattr(native, f"irx_rb_api_{name}_destroy").argtypes = [
            pointer,
            text,
        ]
    schema, builder, batch = pointer(), pointer(), pointer()
    error = ctypes.create_string_buffer(ERROR_CAPACITY)
    assert native.irx_rb_api_schema_new(ctypes.byref(schema), error) == 0
    try:
        assert native.irx_rb_api_schema_add(schema, b"value", 2, 1, error) == 0
        assert (
            native.irx_rb_api_builder_new(schema, ctypes.byref(builder), error)
            == 0
        )
        assert native.irx_rb_api_batch_new(ctypes.byref(batch), error) == 0
        expected = 42
        assert native.irx_rb_api_append_i32(builder, 0, expected, error) == 0
        assert native.irx_rb_api_append_null(builder, 0, error) == 0
        assert native.irx_rb_api_builder_finish(builder, batch, error) == 0
        result, other = integer(123), wide(123)
        assert (
            native.irx_rb_api_get_i64(batch, 0, 0, ctypes.byref(other), error)
            == TYPE_ERROR
        )
        assert other.value == 0
        assert (
            native.irx_rb_api_get_i32(batch, 0, 9, ctypes.byref(result), error)
            == INDEX_ERROR
        )
        assert result.value == 0
        assert (
            native.irx_rb_api_get_i32(batch, 0, 1, ctypes.byref(result), error)
            == VALUE_ERROR
        )
        assert result.value == 0
        assert (
            native.irx_rb_api_get_i32(batch, 0, 0, ctypes.byref(result), error)
            == 0
        )
        assert result.value == expected
    finally:
        assert native.irx_rb_api_batch_destroy(batch, error) == 0
        assert native.irx_rb_api_builder_destroy(builder, error) == 0
        assert native.irx_rb_api_schema_destroy(schema, error) == 0


def test_cpp_exceptions_cannot_cross_checked_boundary(tmp_path: Path) -> None:
    """
    title: Standard and unknown foreign exceptions are contained by the C ABI.
    parameters:
      tmp_path:
        type: Path
    """
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    import pytest  # noqa: PLC0415

    compiler = shutil.which("c++")
    if compiler is None:
        pytest.skip("C++ compiler required for foreign boundary checks")
    native_dir = (
        Path(__file__).parents[1] / "src/irx/builder/runtime/arrow/native"
    )
    source = tmp_path / "boundary.cc"
    source.write_text(
        """#include "irx_record_batch_api_boundary.h"
extern "C" int fail(int kind, char* error) {
  return irx::api_boundary(error, [=] {
    switch (kind) {
      case 1: throw std::bad_alloc();
      case 2: throw std::out_of_range("index");
      case 3: throw std::invalid_argument("value");
      case 4: throw std::overflow_error("overflow");
      case 5: throw std::runtime_error("runtime");
      case 6: throw 42;
    }
  });
}
""",
        encoding="utf-8",
    )
    library = tmp_path / "boundary.so"
    subprocess.run(
        [
            compiler,
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-shared",
            "-fPIC",
            "-I",
            str(native_dir),
            str(source),
            "-o",
            str(library),
        ],
        check=True,
    )
    runtime = ctypes.CDLL(str(library))
    runtime.fail.argtypes = [ctypes.c_int, ctypes.c_char_p]
    error = ctypes.create_string_buffer(ERROR_CAPACITY)
    statuses = (-7, INDEX_ERROR, VALUE_ERROR, -8, -1, -1)
    for kind, expected in enumerate(statuses, 1):
        assert runtime.fail(kind, error) == expected
        assert error.value
        assert runtime.fail(0, error) == 0
        assert error.value == b""


def test_all_registered_facades_have_status_out_error_signatures() -> None:
    """
    title: Every facade declaration agrees with the native checked ABI shape.
    """
    from irx.builder import Builder  # noqa: PLC0415
    from irx.builder.runtime.record_batch_api import (  # noqa: PLC0415
        ARROW_API_SIGNATURES,
        PARQUET_API_SYMBOLS,
    )
    from irx.builder.runtime.registry import (  # noqa: PLC0415
        get_default_runtime_feature_registry,
    )
    from llvmlite import ir  # noqa: PLC0415

    visitor = Builder().translator
    registry = get_default_runtime_feature_registry()
    for name, (result, arguments) in ARROW_API_SIGNATURES.items():
        feature = "parquet" if name in PARQUET_API_SYMBOLS else "record_batch"
        function = registry.get(feature).symbols[name].declare(visitor)
        signature = function.function_type
        assert signature.return_type == ir.IntType(32)
        assert len(signature.args) == len(arguments) + (result != "v") + 1
        assert signature.args[-1] == ir.IntType(8).as_pointer()
        if result != "v":
            assert isinstance(signature.args[-2], ir.PointerType)
