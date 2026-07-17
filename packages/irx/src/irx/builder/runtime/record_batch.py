"""
title: Record batch streaming API.
"""

from __future__ import annotations

import subprocess
import sys

from dataclasses import replace
from pathlib import Path
from typing import Callable

from llvmlite import ir

from irx.builder.runtime.arrowcpp import (
    arrowcpp_compile_flags,
    arrowcpp_include_dirs,
    arrowcpp_linker_flags,
    arrowcpp_runtime_metadata,
)
from irx.builder.runtime.features import (
    ExternalSymbolSpec,
    NativeArtifact,
    RuntimeFeature,
    declare_external_function,
)
from irx.builder.runtime.linking import compile_native_artifacts
from irx.typecheck import typechecked

# Native source location


@typechecked
def _native_source_dir() -> Path:
    """
    title: _native_source_dir.
    returns:
      type: Path
    """
    return (Path(__file__).resolve().parent / "arrow" / "native").resolve()


@typechecked
def _native_source() -> Path:
    """
    title: _native_source.
    returns:
      type: Path
    """
    return _native_source_dir() / "irx_record_batch.cpp"


# LLVM symbol signature table
# Each entry maps a C symbol to (return type code, [argument type codes]).
# Type codes are resolved against ``visitor._llvm`` at declaration time:
#   p   -> opaque pointer (handle, handle**, char*, void**, uint8_t* ...)
#   i8/i16/i32/i64 -> integer of that width (enums and `int` use i32)
#   f32/f64        -> float / double
#   v              -> void
# The opaque-pointer type covers every pointer (handles, out-params, byte
# buffers); IRx never inspects the C structs, so this is sufficient and matches
# how the ``array`` feature declares its symbols.

_SIGNATURES: dict[str, tuple[str, tuple[str, ...]]] = {
    # Error reporting
    "irx_record_batch_errmsg": ("p", ()),
    # Schema
    "irx_rb_schema_create": ("i32", ("p",)),
    "irx_rb_schema_add_field": ("i32", ("p", "p", "i32", "i32")),
    "irx_rb_schema_num_fields": ("i32", ("p",)),
    "irx_rb_schema_release": ("v", ("p",)),
    # Builder
    "irx_rb_builder_create": ("i32", ("p", "p")),
    "irx_rb_builder_append_int8": ("i32", ("p", "i32", "i8")),
    "irx_rb_builder_append_int16": ("i32", ("p", "i32", "i16")),
    "irx_rb_builder_append_int32": ("i32", ("p", "i32", "i32")),
    "irx_rb_builder_append_int64": ("i32", ("p", "i32", "i64")),
    "irx_rb_builder_append_uint8": ("i32", ("p", "i32", "i8")),
    "irx_rb_builder_append_uint16": ("i32", ("p", "i32", "i16")),
    "irx_rb_builder_append_uint32": ("i32", ("p", "i32", "i32")),
    "irx_rb_builder_append_uint64": ("i32", ("p", "i32", "i64")),
    "irx_rb_builder_append_float32": ("i32", ("p", "i32", "f32")),
    "irx_rb_builder_append_float64": ("i32", ("p", "i32", "f64")),
    "irx_rb_builder_append_bool": ("i32", ("p", "i32", "i32")),
    "irx_rb_builder_append_utf8": ("i32", ("p", "i32", "p", "i64")),
    "irx_rb_builder_append_date": ("i32", ("p", "i32", "i64")),
    "irx_rb_builder_append_timestamp": ("i32", ("p", "i32", "i64")),
    "irx_rb_builder_append_time": ("i32", ("p", "i32", "i64")),
    "irx_rb_builder_append_null": ("i32", ("p", "i32")),
    "irx_rb_builder_finish": ("i32", ("p", "p")),
    "irx_rb_builder_release": ("v", ("p",)),
    # RecordBatch inspection
    "irx_rb_batch_num_rows": ("i64", ("p",)),
    "irx_rb_batch_num_columns": ("i32", ("p",)),
    "irx_rb_batch_get_int8": ("i32", ("p", "i32", "i64", "p")),
    "irx_rb_batch_get_int16": ("i32", ("p", "i32", "i64", "p")),
    "irx_rb_batch_get_int32": ("i32", ("p", "i32", "i64", "p")),
    "irx_rb_batch_get_int64": ("i32", ("p", "i32", "i64", "p")),
    "irx_rb_batch_get_uint8": ("i32", ("p", "i32", "i64", "p")),
    "irx_rb_batch_get_uint16": ("i32", ("p", "i32", "i64", "p")),
    "irx_rb_batch_get_uint32": ("i32", ("p", "i32", "i64", "p")),
    "irx_rb_batch_get_uint64": ("i32", ("p", "i32", "i64", "p")),
    "irx_rb_batch_get_float32": ("i32", ("p", "i32", "i64", "p")),
    "irx_rb_batch_get_float64": ("i32", ("p", "i32", "i64", "p")),
    "irx_rb_batch_get_bool": ("i32", ("p", "i32", "i64", "p")),
    "irx_rb_batch_get_utf8": ("i32", ("p", "i32", "i64", "p", "p")),
    "irx_rb_batch_get_date": ("i32", ("p", "i32", "i64", "p")),
    "irx_rb_batch_get_timestamp": ("i32", ("p", "i32", "i64", "p")),
    "irx_rb_batch_get_time": ("i32", ("p", "i32", "i64", "p")),
    "irx_rb_batch_is_null": ("i32", ("p", "i32", "i64", "p")),
    "irx_rb_batch_value_buffer": ("i32", ("p", "i32", "p", "p")),
    "irx_rb_batch_release": ("v", ("p",)),
    # Stream writer
    "irx_rb_stream_writer_open_file": ("i32", ("p", "p", "p")),
    "irx_rb_stream_writer_open_buffer": ("i32", ("p", "p")),
    "irx_rb_stream_writer_write_batch": ("i32", ("p", "p")),
    "irx_rb_stream_writer_close": ("i32", ("p",)),
    "irx_rb_stream_writer_buffer_data": ("i32", ("p", "p", "p")),
    "irx_rb_stream_writer_release": ("v", ("p",)),
    # Stream reader
    "irx_rb_stream_reader_open_file": ("i32", ("p", "p")),
    "irx_rb_stream_reader_open_buffer": ("i32", ("p", "i64", "p")),
    "irx_rb_stream_reader_next_batch": ("i32", ("p", "p")),
    "irx_rb_stream_reader_schema": ("p", ("p",)),
    "irx_rb_stream_reader_close": ("v", ("p",)),
}

RECORD_BATCH_SYMBOLS: frozenset[str] = frozenset(_SIGNATURES)


@typechecked
def _resolve_type(visitor: object, code: str) -> ir.Type:
    """
    title: _resolve_type.
    parameters:
      visitor:
        type: object
      code:
        type: str
    returns:
      type: ir.Type
    """
    llvm = visitor._llvm  # type: ignore[attr-defined]
    if code == "p":
        return llvm.OPAQUE_POINTER_TYPE
    if code == "v":
        return llvm.VOID_TYPE
    return {
        "i8": llvm.INT8_TYPE,
        "i16": llvm.INT16_TYPE,
        "i32": llvm.INT32_TYPE,
        "i64": llvm.INT64_TYPE,
        "f32": llvm.FLOAT_TYPE,
        "f64": llvm.DOUBLE_TYPE,
    }[code]


@typechecked
def _make_declarer(
    name: str, ret_code: str, arg_codes: tuple[str, ...]
) -> Callable[[object], ir.Function]:
    """
    title: _make_declarer.
    parameters:
      name:
        type: str
      ret_code:
        type: str
      arg_codes:
        type: tuple[str, Ellipsis]
    returns:
      type: Callable[[object], ir.Function]
    """

    def declare(visitor: object) -> ir.Function:
        """
        title: Declare a native record-batch symbol for the current visitor.
        parameters:
          visitor:
            type: object
        returns:
          type: ir.Function
        """
        fn_type = ir.FunctionType(
            _resolve_type(visitor, ret_code),
            [_resolve_type(visitor, code) for code in arg_codes],
        )
        return declare_external_function(
            visitor._llvm.module,  # type: ignore[attr-defined]
            name,
            fn_type,
        )

    return declare


# Runtime feature builder


@typechecked
def build_record_batch_runtime_feature() -> RuntimeFeature:
    """
    title: Build the RecordBatch streaming runtime feature specification.
    returns:
      type: RuntimeFeature
    """
    native_dir = _native_source_dir()
    compile_flags = arrowcpp_compile_flags()
    include_dirs = (native_dir, *arrowcpp_include_dirs())

    artifacts = (
        NativeArtifact(
            kind="cxx_source",
            path=_native_source(),
            include_dirs=include_dirs,
            compile_flags=compile_flags,
        ),
    )

    symbols = {
        name: ExternalSymbolSpec(name, _make_declarer(name, ret, args))
        for name, (ret, args) in _SIGNATURES.items()
    }

    return RuntimeFeature(
        name="record_batch",
        symbols=symbols,
        artifacts=artifacts,
        linker_flags=arrowcpp_linker_flags(),
        metadata={
            "canonical_name": "record_batch",
            "depends_on": ("array",),
            "opaque_handles": {
                "schema": "IrxRbSchema",
                "builder": "IrxRbBuilder",
                "batch": "IrxRbBatch",
                "stream_writer": "IrxRbStreamWriter",
                "stream_reader": "IrxRbStreamReader",
            },
            **arrowcpp_runtime_metadata(),
        },
    )


# Standalone shared-library build (for the ctypes API in irx.record_batch)


@typechecked
def _shared_library_name() -> str:
    """
    title: _shared_library_name.
    returns:
      type: str
    """
    if sys.platform == "darwin":
        return "libirx_record_batch.dylib"
    if sys.platform == "win32":
        return "irx_record_batch.dll"
    return "libirx_record_batch.so"


@typechecked
def shared_library_path() -> Path:
    """
    title: shared_library_path.
    returns:
      type: Path
    """
    arrow_dir = (Path(__file__).resolve().parent / "arrow").resolve()
    return arrow_dir / _shared_library_name()


@typechecked
def build_record_batch_shared_library(
    output_path: Path | None = None,
    build_dir: Path | None = None,
    cxx_binary: str = "c++",
) -> Path:
    """
    title: Compile irx_record_batch.cpp into a standalone shared library.
    summary: >-
      Used by the ctypes-based Python API (``irx.record_batch``) and its test
      suite, which load the library directly rather than going through LLVM
      codegen.
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
    output = output_path or shared_library_path()
    work_dir = build_dir or (_native_source_dir() / "_build")
    work_dir.mkdir(parents=True, exist_ok=True)

    feature = build_record_batch_runtime_feature()
    # Shared objects must be position-independent.
    pic_artifacts = tuple(
        replace(a, compile_flags=(*a.compile_flags, "-fPIC"))
        for a in feature.artifacts
    )

    link_inputs = compile_native_artifacts(
        artifacts=pic_artifacts,
        build_dir=work_dir,
        cxx_binary=cxx_binary,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    command = [cxx_binary, "-shared", "-o", str(output)]
    command.extend(str(obj) for obj in link_inputs.objects)
    command.extend(link_inputs.linker_flags)
    command.extend(feature.linker_flags)
    subprocess.run(command, check=True)
    return output
