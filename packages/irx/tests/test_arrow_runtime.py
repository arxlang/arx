"""
title: Tests for the Arrow runtime feature and lowering path.
"""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
import tempfile
import textwrap

from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Barrier
from typing import TypedDict, cast

import astx
import pyarrow as pa
import pytest

from arx_arrowcpp_sources import (
    bundled_arrowcpp_version,
)
from arx_arrowcpp_sources import (
    get_include_dir as get_arrowcpp_include_dir,
)
from irx.buffer import (
    BUFFER_DTYPE_BOOL,
    BUFFER_DTYPE_INT32,
    BUFFER_DTYPE_UINT64,
    BUFFER_FLAG_BORROWED,
    BUFFER_FLAG_C_CONTIGUOUS,
    BUFFER_FLAG_F_CONTIGUOUS,
    BUFFER_FLAG_READONLY,
    BUFFER_FLAG_VALIDITY_BITMAP,
)
from irx.builder import Builder
from irx.builder.runtime.array.feature import (
    ARRAY_PRIMITIVE_TYPE_SPECS,
    IRX_ARROW_TYPE_BOOL,
    IRX_ARROW_TYPE_FLOAT32,
    IRX_ARROW_TYPE_FLOAT64,
    IRX_ARROW_TYPE_INT8,
    IRX_ARROW_TYPE_INT16,
    IRX_ARROW_TYPE_INT32,
    IRX_ARROW_TYPE_INT64,
    IRX_ARROW_TYPE_UINT8,
    IRX_ARROW_TYPE_UINT16,
    IRX_ARROW_TYPE_UINT32,
    IRX_ARROW_TYPE_UINT64,
    build_array_runtime_feature,
)
from irx.builder.runtime.arrow.abi_generated import (
    FALLIBLE_SYMBOLS,
    RUNTIME_FEATURE_IDS,
    RUNTIME_FEATURE_PACKED_VERSIONS,
    VALUE_RESULTS,
)
from irx.builder.runtime.arrow.bindings import (
    configure_arrow_ctypes_library,
)
from irx.builder.runtime.arrow.feature import (
    build_arrow_core_runtime_feature,
    build_arrow_native_artifact,
)
from irx.builder.runtime.dataframe.feature import (
    build_dataframe_runtime_feature,
)
from irx.builder.runtime.features import NativeArtifact, RuntimeFeature
from irx.builder.runtime.linking import (
    compile_native_artifacts,
    link_executable,
)
from irx.builder.runtime.tensor.feature import build_tensor_runtime_feature
from llvmlite import binding as llvm


class SupportedPrimitiveMetadata(TypedDict):
    type_id: int
    dtype_token: int
    element_size_bytes: int | None
    buffer_view_compatible: bool


PrimitiveValue = int | float | bool | None
BuilderValue = int | float | None
ArrowSchemaFactory = Callable[[], object]
EXPECTED_ARROW_ABI_VERSION = 0x00010000
ARROW_STATUS_OK = 0
ARROW_STATUS_INVALID_ARGUMENT = 100
ARROW_STATUS_NULL_POINTER = 101
ARROW_STATUS_TYPE_MISMATCH = 103
ARROW_STATUS_OVERFLOW = 106
ARROW_STATUS_NOT_SUPPORTED = 107
ARROW_STATUS_CATEGORY_INVALID = 2
ARROW_STATUS_CATEGORY_UNKNOWN = 6
ARROW_HANDLE_KIND_ERROR = 1
ARROW_HANDLE_KIND_SCHEMA = 3
ARROW_HANDLE_KIND_ARRAY_BUILDER = 5
ARROW_HANDLE_KIND_ARRAY = 6
ARROW_HANDLE_KIND_CHUNKED_ARRAY = 7
ARROW_HANDLE_KIND_TABLE = 9
ARROW_HANDLE_KIND_TENSOR_BUILDER = 10
ARROW_HANDLE_KIND_TENSOR = 11
ARROW_HANDLE_OWNERSHIP_SHARED = 1
ARROW_HANDLE_OWNERSHIP_UNIQUE = 2
FULL_ARROW_RUNTIME_CAPABILITIES = (
    "core",
    "array",
    "tensor",
    "dataframe",
    "record_batch",
)


class ArrowSchemaStruct(ctypes.Structure):
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


class BufferViewStruct(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.c_void_p),
        ("owner", ctypes.c_void_p),
        ("dtype", ctypes.c_void_p),
        ("ndim", ctypes.c_int32),
        ("shape", ctypes.POINTER(ctypes.c_int64)),
        ("strides", ctypes.POINTER(ctypes.c_int64)),
        ("offset_bytes", ctypes.c_int64),
        ("flags", ctypes.c_int32),
    ]


PRIMITIVE_IMPORT_CASES: tuple[
    tuple[
        str,
        ArrowSchemaFactory,
        Sequence[PrimitiveValue],
        Sequence[PrimitiveValue],
    ],
    ...,
] = (
    ("int8", pa.int8, [1, -2, 127], [1, -2, 127]),
    ("int16", pa.int16, [1, -32000, 32000], [1, -32000, 32000]),
    (
        "int32",
        pa.int32,
        [1, -2_000_000_000, 2_000_000_000],
        [1, -2_000_000_000, 2_000_000_000],
    ),
    (
        "int64",
        pa.int64,
        [1, -(2**40), 2**40],
        [1, -(2**40), 2**40],
    ),
    ("uint8", pa.uint8, [0, 7, 255], [0, 7, 255]),
    ("uint16", pa.uint16, [0, 42, 65535], [0, 42, 65535]),
    ("uint32", pa.uint32, [0, 7, 2**32 - 1], [0, 7, 2**32 - 1]),
    (
        "uint64",
        pa.uint64,
        [0, 7, 2**63 + 7],
        [0, 7, 2**63 + 7],
    ),
    ("float32", pa.float32, [1.5, -2.25, 3.75], [1.5, -2.25, 3.75]),
    ("float64", pa.float64, [1.25, -2.5, 3.75], [1.25, -2.5, 3.75]),
    (
        "bool",
        pa.bool_,
        [True, False, None, True],
        [True, False, None, True],
    ),
)


BUILDER_CASES: tuple[
    tuple[str, int, str, Sequence[BuilderValue], Sequence[PrimitiveValue]],
    ...,
] = (
    ("int8", IRX_ARROW_TYPE_INT8, "int", [1, -2, 127], [1, -2, 127]),
    (
        "int16",
        IRX_ARROW_TYPE_INT16,
        "int",
        [1, -32000, 32000],
        [1, -32000, 32000],
    ),
    (
        "int32",
        IRX_ARROW_TYPE_INT32,
        "int",
        [1, -2_000_000_000, 2_000_000_000],
        [1, -2_000_000_000, 2_000_000_000],
    ),
    (
        "int64",
        IRX_ARROW_TYPE_INT64,
        "int",
        [1, -(2**40), 2**40],
        [1, -(2**40), 2**40],
    ),
    ("uint8", IRX_ARROW_TYPE_UINT8, "uint", [0, 7, 255], [0, 7, 255]),
    ("uint16", IRX_ARROW_TYPE_UINT16, "uint", [0, 42, 65535], [0, 42, 65535]),
    (
        "uint32",
        IRX_ARROW_TYPE_UINT32,
        "uint",
        [0, 7, 2**32 - 1],
        [0, 7, 2**32 - 1],
    ),
    (
        "uint64",
        IRX_ARROW_TYPE_UINT64,
        "uint",
        [0, 7, 2**63 + 7],
        [0, 7, 2**63 + 7],
    ),
    (
        "float32",
        IRX_ARROW_TYPE_FLOAT32,
        "double",
        [1.5, -2.25, 3.75],
        [1.5, -2.25, 3.75],
    ),
    (
        "float64",
        IRX_ARROW_TYPE_FLOAT64,
        "double",
        [1.25, -2.5, 3.75],
        [1.25, -2.5, 3.75],
    ),
    (
        "bool",
        IRX_ARROW_TYPE_BOOL,
        "int",
        [1, 0, None, 1],
        [True, False, None, True],
    ),
)


def _find_c_compiler() -> str | None:
    """
    title: Find one usable C compiler for runtime tests.
    returns:
      type: str | None
    """
    return shutil.which("clang") or shutil.which("cc")


def _array_length_module(values: list[int]) -> astx.Module:
    """
    title: Array length module.
    parameters:
      values:
        type: list[int]
    returns:
      type: astx.Module
    """
    module = astx.Module()
    main_proto = astx.FunctionPrototype(
        "main", args=astx.Arguments(), return_type=astx.Int32()
    )
    body = astx.Block()
    body.append(
        astx.FunctionReturn(
            astx.ArrayInt32ArrayLength(
                [astx.LiteralInt32(value) for value in values]
            )
        )
    )
    module.block.append(astx.FunctionDef(prototype=main_proto, body=body))
    return module


def _plain_main_module() -> astx.Module:
    """
    title: Plain main module.
    returns:
      type: astx.Module
    """
    module = astx.Module()
    main_proto = astx.FunctionPrototype(
        "main", args=astx.Arguments(), return_type=astx.Int32()
    )
    body = astx.Block()
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module.block.append(astx.FunctionDef(prototype=main_proto, body=body))
    return module


def _arrow_runtime_feature(
    capabilities: tuple[str, ...] = FULL_ARROW_RUNTIME_CAPABILITIES,
) -> RuntimeFeature:
    """
    title: Build a selected linked Arrow runtime feature set for tests.
    parameters:
      capabilities:
        type: tuple[str, Ellipsis]
    returns:
      type: RuntimeFeature
    """
    core = build_arrow_core_runtime_feature()
    if capabilities == FULL_ARROW_RUNTIME_CAPABILITIES:
        core_artifact = core.artifacts[0]
        combined_artifact = NativeArtifact(
            kind="cxx_source",
            path=core_artifact.path.with_name("irx_arrow_runtime.cc"),
            include_dirs=core_artifact.include_dirs,
            compile_flags=(
                *core_artifact.compile_flags,
                "-DIRX_ARROW_RUNTIME_BUILD_CORE",
                "-DIRX_ARROW_RUNTIME_BUILD_ARRAY",
                "-DIRX_ARROW_RUNTIME_BUILD_TENSOR",
                "-DIRX_ARROW_RUNTIME_BUILD_DATAFRAME",
                "-DIRX_ARROW_RUNTIME_BUILD_RECORD_BATCH",
            ),
        )
        return RuntimeFeature(
            name="arrow_test_runtime",
            artifacts=(combined_artifact,),
            linker_flags=core.linker_flags,
        )

    available_features = {
        "core": core,
        "array": build_array_runtime_feature(),
        "tensor": build_tensor_runtime_feature(),
        "dataframe": build_dataframe_runtime_feature(),
        "record_batch": RuntimeFeature(
            name="record_batch",
            artifacts=(build_arrow_native_artifact("record_batch"),),
        ),
    }
    features = tuple(available_features[name] for name in capabilities)
    artifacts: list[NativeArtifact] = []
    linker_flags: list[str] = []
    seen_artifacts: set[tuple[str, str]] = set()
    seen_flags: set[str] = set()

    for feature in features:
        for artifact in feature.artifacts:
            key = (artifact.kind, str(artifact.path))
            if key in seen_artifacts:
                continue
            seen_artifacts.add(key)
            artifacts.append(artifact)
        for flag in feature.linker_flags:
            if flag in seen_flags:
                continue
            seen_flags.add(flag)
            linker_flags.append(flag)

    return RuntimeFeature(
        name="arrow_test_runtime",
        artifacts=tuple(artifacts),
        linker_flags=tuple(linker_flags),
    )


def _compile_arrow_harness(
    source: str,
    capabilities: tuple[str, ...] = FULL_ARROW_RUNTIME_CAPABILITIES,
) -> subprocess.CompletedProcess[str]:
    """
    title: Compile arrow harness.
    parameters:
      source:
        type: str
      capabilities:
        type: tuple[str, Ellipsis]
    returns:
      type: subprocess.CompletedProcess[str]
    """
    feature = _arrow_runtime_feature(capabilities)
    include_dirs: list[Path] = []
    seen_include_dirs: set[Path] = set()
    for artifact in feature.artifacts:
        for include_dir in artifact.include_dirs:
            if include_dir in seen_include_dirs:
                continue
            seen_include_dirs.add(include_dir)
            include_dirs.append(include_dir)

    c_compiler = _find_c_compiler()
    if c_compiler is None:
        pytest.skip("a C compiler is required for Arrow runtime harness tests")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        source_path = tmp_path / "arrow_harness.c"
        object_path = tmp_path / "arrow_harness.o"
        output_path = tmp_path / "arrow_harness"

        source_path.write_text(textwrap.dedent(source), encoding="utf8")
        subprocess.run(
            [
                c_compiler,
                "-c",
                str(source_path),
                "-o",
                str(object_path),
                *[
                    option
                    for include_dir in include_dirs
                    for option in ("-I", str(include_dir))
                ],
                "-std=c99",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        link_executable(
            primary_object=object_path,
            output_file=output_path,
            artifacts=feature.artifacts,
            linker_flags=feature.linker_flags,
            clang_binary=c_compiler,
        )
        return subprocess.run(
            [str(output_path)],
            check=False,
            capture_output=True,
            text=True,
        )


def _shared_library_suffix() -> str:
    """
    title: Shared library suffix.
    returns:
      type: str
    """
    if sys.platform == "darwin":
        return ".dylib"

    return ".so"


@contextmanager
def _load_arrow_runtime_library(
    *,
    compatibility: bool = True,
) -> Iterator[ctypes.CDLL]:
    """
    title: Load arrow runtime library.
    parameters:
      compatibility:
        type: bool
    returns:
      type: Iterator[ctypes.CDLL]
    """
    if sys.platform == "win32":
        pytest.skip("Arrow C++ shared-library tests require Unix")

    feature = _arrow_runtime_feature()
    c_compiler = _find_c_compiler()
    if c_compiler is None:
        pytest.skip("a C compiler is required for Arrow runtime interop tests")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        output_path = (
            tmp_path / f"libirx_arrow_runtime{_shared_library_suffix()}"
        )
        link_inputs = compile_native_artifacts(
            feature.artifacts,
            tmp_path,
            c_compiler,
        )

        cxx_compiler = shutil.which("c++") or shutil.which("clang++")
        if cxx_compiler is None:
            pytest.skip("a C++ compiler is required for Arrow runtime tests")

        command = [cxx_compiler]
        if sys.platform == "darwin":
            command.append("-dynamiclib")
        else:
            command.append("-shared")

        command.extend(str(obj) for obj in link_inputs.objects)
        command.extend(link_inputs.linker_flags)
        command.extend(feature.linker_flags)
        command.extend(["-o", str(output_path)])
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )

        library = ctypes.CDLL(str(output_path))
        if compatibility:
            cleanup = _configure_arrow_runtime_library(library)
        else:
            configure_arrow_ctypes_library(library)

            def cleanup() -> None:
                """
                title: Leave a raw runtime library unchanged.
                """
                pass

        try:
            yield library
        finally:
            cleanup()


def _configure_arrow_runtime_library(
    library: ctypes.CDLL,
) -> Callable[[], None]:
    """
    title: Configure arrow runtime library.
    parameters:
      library:
        type: ctypes.CDLL
    returns:
      type: Callable[[], None]
    """
    configure_arrow_ctypes_library(library)
    native_functions = {
        name: getattr(library, name) for name in FALLIBLE_SYMBOLS
    }
    pending_errors: list[ctypes.c_void_p] = []

    def make_compatibility_call(
        name: str,
        result_type: str | None,
    ) -> Callable[..., object]:
        """
        title: Adapt one explicit-error call for existing behavior tests.
        parameters:
          name:
            type: str
          result_type:
            type: str | None
        returns:
          type: Callable[Ellipsis, object]
        """
        native_function = native_functions[name]

        def call(*arguments: object) -> object:
            """
            title: Invoke one adapted native function.
            parameters:
              arguments:
                type: object
                variadic: positional
            returns:
              type: object
            """
            failure = ctypes.c_void_p()
            if result_type is None:
                status = native_function(
                    *arguments,
                    ctypes.byref(failure),
                )
                if failure.value is not None:
                    pending_errors.append(failure)
                return status

            if result_type in {"int32", "status"}:
                result: object = ctypes.c_int32()
            elif result_type == "int64":
                result = ctypes.c_int64()
            elif result_type == "c_string":
                result = ctypes.c_char_p()
            elif result_type == "const_int64_pointer":
                result = ctypes.POINTER(ctypes.c_int64)()
            else:
                raise AssertionError(f"unsupported ABI result '{result_type}'")
            status = native_function(
                *arguments,
                ctypes.byref(result),
                ctypes.byref(failure),
            )
            if failure.value is not None:
                pending_errors.append(failure)
            if status != ARROW_STATUS_OK and result_type in {
                "int32",
                "int64",
                "status",
            }:
                return -1
            if result_type == "const_int64_pointer":
                return result
            return result.value

        return call

    for name in FALLIBLE_SYMBOLS:
        setattr(
            library,
            name,
            make_compatibility_call(name, VALUE_RESULTS.get(name)),
        )

    raw_error_release = native_functions["irx_arrow_error_release"]

    def cleanup() -> None:
        """
        title: Release errors captured by compatibility calls.
        """
        for failure in pending_errors:
            release_failure = ctypes.c_void_p()
            raw_error_release(
                ctypes.byref(failure),
                ctypes.byref(release_failure),
            )

    return cleanup


def _assert_arrow_ok(library: ctypes.CDLL, code: int) -> None:
    """
    title: Assert arrow ok.
    parameters:
      library:
        type: ctypes.CDLL
      code:
        type: int
    """
    assert code == 0, library.irx_arrow_last_error().decode()


def _assert_handle_metadata(
    library: ctypes.CDLL,
    handle: ctypes.c_void_p,
    expected_kind: int,
    expected_ownership: int,
) -> None:
    """
    title: Assert one opaque handle kind and ownership class.
    parameters:
      library:
        type: ctypes.CDLL
      handle:
        type: ctypes.c_void_p
      expected_kind:
        type: int
      expected_ownership:
        type: int
    """
    kind = ctypes.c_int32()
    ownership = ctypes.c_int32()
    _assert_arrow_ok(
        library,
        library.irx_arrow_handle_kind_of(handle, ctypes.byref(kind)),
    )
    _assert_arrow_ok(
        library,
        library.irx_arrow_handle_ownership_of(
            handle,
            ctypes.byref(ownership),
        ),
    )
    assert kind.value == expected_kind
    assert ownership.value == expected_ownership


def _build_runtime_array(
    library: ctypes.CDLL,
    type_id: int,
    append_kind: str,
    values: Sequence[BuilderValue],
) -> ctypes.c_void_p:
    """
    title: Build runtime array.
    parameters:
      library:
        type: ctypes.CDLL
      type_id:
        type: int
      append_kind:
        type: str
      values:
        type: Sequence[BuilderValue]
    returns:
      type: ctypes.c_void_p
    """
    builder = ctypes.c_void_p()
    array_handle = ctypes.c_void_p()

    _assert_arrow_ok(
        library,
        library.irx_arrow_array_builder_new(type_id, ctypes.byref(builder)),
    )

    try:
        for value in values:
            if value is None:
                _assert_arrow_ok(
                    library,
                    library.irx_arrow_array_builder_append_null(builder, 1),
                )
                continue

            if append_kind == "int":
                _assert_arrow_ok(
                    library,
                    library.irx_arrow_array_builder_append_int(
                        builder,
                        int(value),
                    ),
                )
                continue

            if append_kind == "uint":
                _assert_arrow_ok(
                    library,
                    library.irx_arrow_array_builder_append_uint(
                        builder,
                        int(value),
                    ),
                )
                continue

            if append_kind == "double":
                _assert_arrow_ok(
                    library,
                    library.irx_arrow_array_builder_append_double(
                        builder,
                        float(value),
                    ),
                )
                continue

            raise AssertionError(f"unknown append kind {append_kind!r}")

        _assert_arrow_ok(
            library,
            library.irx_arrow_array_builder_finish(
                ctypes.byref(builder),
                ctypes.byref(array_handle),
            ),
        )
        assert builder.value is None
        return array_handle
    finally:
        if builder.value is not None:
            _assert_arrow_ok(
                library,
                library.irx_arrow_array_builder_release(ctypes.byref(builder)),
            )


def _build_runtime_tensor(
    library: ctypes.CDLL,
    values: Sequence[int],
    shape: Sequence[int],
    strides: Sequence[int],
) -> ctypes.c_void_p:
    """
    title: Build one int32 runtime tensor.
    parameters:
      library:
        type: ctypes.CDLL
      values:
        type: Sequence[int]
      shape:
        type: Sequence[int]
      strides:
        type: Sequence[int]
    returns:
      type: ctypes.c_void_p
    """
    builder = ctypes.c_void_p()
    tensor_handle = ctypes.c_void_p()
    shape_array = (ctypes.c_int64 * len(shape))(*shape)
    strides_array = (ctypes.c_int64 * len(strides))(*strides)

    _assert_arrow_ok(
        library,
        library.irx_arrow_tensor_builder_new(
            IRX_ARROW_TYPE_INT32,
            len(shape),
            shape_array,
            strides_array,
            ctypes.byref(builder),
        ),
    )

    try:
        for value in values:
            _assert_arrow_ok(
                library,
                library.irx_arrow_tensor_builder_append_int(builder, value),
            )

        _assert_arrow_ok(
            library,
            library.irx_arrow_tensor_builder_finish(
                ctypes.byref(builder),
                ctypes.byref(tensor_handle),
            ),
        )
        assert builder.value is None
        return tensor_handle
    finally:
        if builder.value is not None:
            _assert_arrow_ok(
                library,
                library.irx_arrow_tensor_builder_release(
                    ctypes.byref(builder)
                ),
            )


def _arrow_array_struct(addr: int) -> ArrowArrayStruct:
    """
    title: View one ArrowArray at an address.
    parameters:
      addr:
        type: int
    returns:
      type: ArrowArrayStruct
    """
    return ctypes.cast(addr, ctypes.POINTER(ArrowArrayStruct)).contents


def _arrow_schema_struct(addr: int) -> ArrowSchemaStruct:
    """
    title: View one ArrowSchema at an address.
    parameters:
      addr:
        type: int
    returns:
      type: ArrowSchemaStruct
    """
    return ctypes.cast(addr, ctypes.POINTER(ArrowSchemaStruct)).contents


def _capsule_pointer(capsule: object, name: bytes) -> int:
    """
    title: Return a PyCapsule pointer as an integer address.
    parameters:
      capsule:
        type: object
      name:
        type: bytes
    returns:
      type: int
    """
    getter = ctypes.pythonapi.PyCapsule_GetPointer
    getter.argtypes = [ctypes.py_object, ctypes.c_char_p]
    getter.restype = ctypes.c_void_p
    pointer = getter(capsule, name)
    if pointer is None:
        raise RuntimeError(f"PyCapsule {name!r} did not expose a pointer")
    return int(pointer)


def _pyarrow_c_array(
    values: Sequence[object],
    data_type: pa.DataType,
) -> tuple[pa.Array, object, object, int, int]:
    """
    title: Export one PyArrow array through Arrow C Data capsules.
    parameters:
      values:
        type: Sequence[object]
      data_type:
        type: pa.DataType
    returns:
      type: tuple[pa.Array, object, object, int, int]
    """
    array = pa.array(values, type=data_type)
    schema_capsule, array_capsule = array.__arrow_c_array__()
    return (
        array,
        schema_capsule,
        array_capsule,
        _capsule_pointer(schema_capsule, b"arrow_schema"),
        _capsule_pointer(array_capsule, b"arrow_array"),
    )


def _import_exported_array(
    exported_array: ArrowArrayStruct,
    exported_schema: ArrowSchemaStruct,
) -> pa.Array:
    """
    title: Import exported Arrow C Data into PyArrow.
    parameters:
      exported_array:
        type: ArrowArrayStruct
      exported_schema:
        type: ArrowSchemaStruct
    returns:
      type: pa.Array
    """
    return pa.Array._import_from_c(
        ctypes.addressof(exported_array),
        ctypes.addressof(exported_schema),
    )


def _release_c_array(array: ArrowArrayStruct) -> None:
    """
    title: Release an ArrowArray ctypes value if it owns resources.
    parameters:
      array:
        type: ArrowArrayStruct
    """
    if array.release is not None:
        release = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(array.release)
        release(ctypes.c_void_p(ctypes.addressof(array)))


def _release_c_schema(schema: ArrowSchemaStruct) -> None:
    """
    title: Release an ArrowSchema ctypes value if it owns resources.
    parameters:
      schema:
        type: ArrowSchemaStruct
    """
    if schema.release is not None:
        release = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(schema.release)
        release(ctypes.c_void_p(ctypes.addressof(schema)))


def _primitive_spec(name: str) -> tuple[int, int, bool]:
    """
    title: Return one runtime primitive metadata triple.
    parameters:
      name:
        type: str
    returns:
      type: tuple[int, int, bool]
    """
    spec = ARRAY_PRIMITIVE_TYPE_SPECS[name]
    return (
        spec.type_id,
        spec.dtype_token,
        spec.buffer_view_compatible,
    )


def test_arrow_symbols_absent_when_unused() -> None:
    """
    title: Array runtime declarations should be absent when unused.
    """
    builder = Builder()

    ir_text = builder.translate(_array_length_module([]))
    assert "irx_arrow_array_builder_int32_new" in ir_text

    plain_builder = Builder()
    plain_ir = plain_builder.translate(_plain_main_module())
    assert "irx_arrow_" not in plain_ir


def test_arrow_length_codegen_declares_runtime_symbols() -> None:
    """
    title: Array lowering should declare runtime symbols and parse as LLVM.
    """
    builder = Builder()
    ir_text = builder.translate(_array_length_module([1, 2, 3]))

    llvm.parse_assembly(ir_text)

    active_features = (
        builder.translator.runtime_features.active_feature_names()
    )

    assert "array" in active_features
    assert '@"irx_arrow_array_builder_int32_new"' in ir_text
    assert '@"irx_arrow_array_length"' in ir_text
    assert builder.translator.runtime_features.native_artifacts()


def test_arrow_feature_uses_arrowcpp_runtime() -> None:
    """
    title: Arrow runtime should compile against Arrow C++.
    """
    feature = build_array_runtime_feature()
    native_sources = {
        artifact.path
        for artifact in feature.artifacts
        if artifact.kind == "cxx_source"
    }

    assert {path.name for path in native_sources} == {
        "irx_arrow_array_runtime.cc"
    }
    assert feature.dependencies == ("core",)
    assert feature.metadata["implementation"] == "arrow-cpp"
    assert feature.metadata["arrowcpp_version"] == bundled_arrowcpp_version()

    for artifact in feature.artifacts:
        if artifact.kind == "cxx_source":
            assert get_arrowcpp_include_dir() in artifact.include_dirs


def test_arrow_feature_metadata_exposes_supported_primitive_mapping() -> None:
    """
    title: >-
      Arrow feature metadata should publish the explicit primitive mapping.
    """
    feature = build_array_runtime_feature()
    supported = cast(
        dict[str, SupportedPrimitiveMetadata],
        feature.metadata["supported_primitive_types"],
    )

    assert supported["int32"] == {
        "type_id": IRX_ARROW_TYPE_INT32,
        "dtype_token": BUFFER_DTYPE_INT32,
        "element_size_bytes": 4,
        "buffer_view_compatible": True,
    }
    assert supported["uint64"] == {
        "type_id": IRX_ARROW_TYPE_UINT64,
        "dtype_token": BUFFER_DTYPE_UINT64,
        "element_size_bytes": 8,
        "buffer_view_compatible": True,
    }
    assert supported["bool"] == {
        "type_id": IRX_ARROW_TYPE_BOOL,
        "dtype_token": BUFFER_DTYPE_BOOL,
        "element_size_bytes": None,
        "buffer_view_compatible": False,
    }


def test_arrow_length_build_returns_length() -> None:
    """
    title: >-
      Building an array-backed module should link and return the array length.
    """
    if shutil.which("clang") is None:
        pytest.skip("builder.build() currently requires clang")

    builder = Builder()
    module = _array_length_module([10, 20, 30])

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "arrow_len"
        builder.build(module, str(output_path))
        runtime_artifacts = (
            builder.translator.runtime_features.native_artifacts()
        )
        artifact_names = {artifact.path.name for artifact in runtime_artifacts}
        assert artifact_names == {
            "irx_arrow_core_runtime.cc",
            "irx_arrow_array_runtime.cc",
        }

        nm_binary = shutil.which("nm")
        if nm_binary is not None:
            symbols = subprocess.run(
                [nm_binary, "-g", str(output_path)],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            assert "irx_arrow_array_length" in symbols
            assert "irx_arrow_tensor_builder_new" not in symbols
            assert "irx_arrow_table_new_from_arrays" not in symbols

        result = subprocess.run(
            [str(output_path)],
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 3  # noqa: PLR2004
    assert result.stdout == ""


def test_arrow_runtime_harness_lifecycle() -> None:
    """
    title: >-
      Arrow runtime C ABI should support create append finish inspect release.
    """
    result = _compile_arrow_harness(
        """
        #include "irx_arrow_runtime.h"

        int main(void) {
          irx_arrow_array_builder_handle* builder = NULL;
          irx_arrow_array_handle* array = NULL;
          irx_arrow_error_handle* failure = NULL;
          int64_t length = 0;
          int64_t null_count = 0;
          int32_t type_id = IRX_ARROW_TYPE_UNKNOWN;

          if (irx_arrow_array_builder_int32_new(&builder, &failure) != 0) {
            return 11;
          }
          if (irx_arrow_array_builder_append_int32(
                  builder, 1, &failure) != 0) return 12;
          if (irx_arrow_array_builder_append_int32(
                  builder, 2, &failure) != 0) return 13;
          if (irx_arrow_array_builder_append_int32(
                  builder, 3, &failure) != 0) return 14;
          if (irx_arrow_array_builder_finish(
                  &builder, &array, &failure) != 0) {
            return 15;
          }
          if (builder != NULL) return 19;

          if (irx_arrow_array_length(array, &length, &failure) != 0 ||
              length != 3) return 16;
          if (irx_arrow_array_null_count(
                  array, &null_count, &failure) != 0 ||
              null_count != 0) return 17;
          if (irx_arrow_array_type_id(array, &type_id, &failure) != 0 ||
              type_id != IRX_ARROW_TYPE_INT32) {
            return 18;
          }

          if (irx_arrow_array_release(&array, &failure) != 0) return 20;
          if (array != NULL) return 21;
          return 0;
        }
        """
    )

    assert result.returncode == 0
    assert result.stderr == ""


def test_arrow_runtime_reports_stable_abi_and_feature_versions() -> None:
    """
    title: Runtime queries should enforce ABI and feature compatibility.
    """
    result = _compile_arrow_harness(
        """
        #include "irx_arrow_runtime.h"

        #if IRX_ARROW_ABI_VERSION != UINT32_C(0x00010000)
        #error "unexpected packed Arrow ABI version"
        #endif

        #if IRX_ARROW_RUNTIME_FEATURE_ARRAY_CONTRACT_VERSION != \
            UINT32_C(0x00010000)
        #error "unexpected array feature contract version"
        #endif

        int main(void) {
          irx_arrow_error_handle* failure = NULL;
          int32_t available = -1;
          uint32_t supported = UINT32_MAX;

          if (IRX_ARROW_ABI_VERSION_MAJOR != 1) return 11;
          if (IRX_ARROW_ABI_VERSION_MINOR != 0) return 12;
          if (IRX_ARROW_ABI_VERSION_PATCH != 0) return 13;
          if (irx_arrow_abi_version() != IRX_ARROW_ABI_VERSION) return 14;
          if (IRX_ARROW_RUNTIME_FEATURE_CORE != 1) return 22;
          if (IRX_ARROW_RUNTIME_FEATURE_ARRAY != 2) return 23;
          if (IRX_ARROW_RUNTIME_FEATURE_TENSOR != 3) return 24;
          if (IRX_ARROW_RUNTIME_FEATURE_DATAFRAME != 4) return 25;
          if (irx_arrow_runtime_has_feature(
                  IRX_ARROW_RUNTIME_FEATURE_ARRAY,
                  IRX_ARROW_RUNTIME_FEATURE_ARRAY_CONTRACT_VERSION,
                  &available,
                  &supported,
                  &failure) != IRX_ARROW_STATUS_OK) return 15;
          if (available != 1 || supported != UINT32_C(0x00010000)) {
            return 16;
          }
          if (failure != NULL) return 17;

          if (irx_arrow_runtime_has_feature(
                  IRX_ARROW_RUNTIME_FEATURE_ARRAY,
                  UINT32_C(0x00010100),
                  &available,
                  &supported,
                  &failure) != IRX_ARROW_STATUS_OK) return 18;
          if (available != 0 || supported != UINT32_C(0x00010000)) {
            return 19;
          }

          if (irx_arrow_runtime_has_feature(
                  9001,
                  0,
                  &available,
                  &supported,
                  &failure) != IRX_ARROW_STATUS_OK) return 20;
          if (available != 0 || supported != 0) return 21;
          return 0;
        }
        """
    )

    assert result.returncode == 0
    assert result.stderr == ""

    with _load_arrow_runtime_library() as library:
        assert library.irx_arrow_abi_version() == EXPECTED_ARROW_ABI_VERSION

        def query(feature_id: int, required_version: int) -> tuple[int, int]:
            """
            title: Query one runtime feature through the generated binding.
            parameters:
              feature_id:
                type: int
              required_version:
                type: int
            returns:
              type: tuple[int, int]
            """
            available = ctypes.c_int32(-1)
            supported = ctypes.c_uint32(0xFFFFFFFF)
            assert (
                library.irx_arrow_runtime_has_feature(
                    feature_id,
                    required_version,
                    ctypes.byref(available),
                    ctypes.byref(supported),
                )
                == ARROW_STATUS_OK
            )
            return available.value, supported.value

        for name, feature_id in RUNTIME_FEATURE_IDS.items():
            version = RUNTIME_FEATURE_PACKED_VERSIONS[name]
            assert query(feature_id, 0) == (1, version)
            assert query(feature_id, version) == (1, version)
            assert query(feature_id, 0x00010100) == (0, version)
            assert query(feature_id, 0x00020000) == (0, version)

        assert query(9001, 0) == (0, 0)


def test_arrow_runtime_reports_only_linked_capabilities() -> None:
    """
    title: Runtime feature queries should reject capabilities not in the link.
    """
    result = _compile_arrow_harness(
        """
        #include "irx_arrow_runtime.h"

        int main(void) {
          irx_arrow_error_handle* failure = NULL;
          int32_t available = -1;
          uint32_t supported = UINT32_MAX;

          if (irx_arrow_runtime_has_feature(
                  IRX_ARROW_RUNTIME_FEATURE_ARRAY,
                  0,
                  &available,
                  &supported,
                  &failure) != IRX_ARROW_STATUS_OK) return 11;
          if (available != 1 || supported == 0 || failure != NULL) return 12;

          if (irx_arrow_runtime_has_feature(
                  IRX_ARROW_RUNTIME_FEATURE_TENSOR,
                  0,
                  &available,
                  &supported,
                  &failure) != IRX_ARROW_STATUS_OK) return 13;
          if (available != 0 || supported != 0 || failure != NULL) return 14;
          return 0;
        }
        """,
        capabilities=("core", "array"),
    )

    assert result.returncode == 0
    assert result.stderr == ""


def test_arrow_runtime_reports_stable_status_codes() -> None:
    """
    title: Arrow runtime should return stable Arx status codes and categories.
    """
    result = _compile_arrow_harness(
        """
        #include <stdint.h>
        #include "irx_arrow_runtime.h"

        int main(void) {
          int64_t shape[2];
          irx_arrow_tensor_builder_handle* tensor_builder = NULL;
          irx_arrow_array_builder_handle* array_builder = NULL;
          irx_arrow_error_handle* failure = NULL;
          irx_arrow_error_handle* release_failure = NULL;

          shape[0] = INT64_MAX;
          shape[1] = 2;

          if (sizeof(irx_arrow_status) != sizeof(int32_t)) return 11;
          if (IRX_ARROW_STATUS_OK != 0) return 12;
          if (IRX_ARROW_STATUS_END_OF_STREAM != 1) return 13;
          if (IRX_ARROW_STATUS_INVALID_ARGUMENT != 100) return 14;
          if (IRX_ARROW_STATUS_NULL_POINTER != 101) return 15;
          if (IRX_ARROW_STATUS_INVALID_STATE != 102) return 16;
          if (IRX_ARROW_STATUS_TYPE_MISMATCH != 103) return 17;
          if (IRX_ARROW_STATUS_SCHEMA_MISMATCH != 104) return 18;
          if (IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS != 105) return 19;
          if (IRX_ARROW_STATUS_OVERFLOW != 106) return 20;
          if (IRX_ARROW_STATUS_NOT_SUPPORTED != 107) return 21;
          if (IRX_ARROW_STATUS_ABI_MISMATCH != 108) return 22;
          if (IRX_ARROW_STATUS_OUT_OF_MEMORY != 200) return 23;
          if (IRX_ARROW_STATUS_RESOURCE_EXHAUSTED != 201) return 24;
          if (IRX_ARROW_STATUS_IO_ERROR != 300) return 25;
          if (IRX_ARROW_STATUS_CANCELLED != 301) return 26;
          if (IRX_ARROW_STATUS_ARROW_ERROR != 400) return 27;
          if (IRX_ARROW_STATUS_INTERNAL != 401) return 28;
          if (irx_arrow_status_get_category(IRX_ARROW_STATUS_OK) !=
              IRX_ARROW_STATUS_CATEGORY_SUCCESS) return 29;
          if (irx_arrow_status_get_category(IRX_ARROW_STATUS_CANCELLED) !=
              IRX_ARROW_STATUS_CATEGORY_CONTROL) return 30;
          if (irx_arrow_status_get_category(IRX_ARROW_STATUS_OVERFLOW) !=
              IRX_ARROW_STATUS_CATEGORY_INVALID) return 31;
          if (irx_arrow_status_get_category(IRX_ARROW_STATUS_OUT_OF_MEMORY) !=
              IRX_ARROW_STATUS_CATEGORY_RESOURCE) return 32;
          if (irx_arrow_status_get_category(IRX_ARROW_STATUS_IO_ERROR) !=
              IRX_ARROW_STATUS_CATEGORY_IO) return 33;
          if (irx_arrow_status_get_category(IRX_ARROW_STATUS_INTERNAL) !=
              IRX_ARROW_STATUS_CATEGORY_INTERNAL) return 34;
          if (irx_arrow_status_get_category(9999) !=
              IRX_ARROW_STATUS_CATEGORY_UNKNOWN) return 35;

          if (irx_arrow_array_builder_new(
                  IRX_ARROW_TYPE_INT32, NULL, &failure) !=
              IRX_ARROW_STATUS_NULL_POINTER) return 36;
          if (failure == NULL) return 43;
          if (irx_arrow_error_release(&failure, &release_failure) !=
              IRX_ARROW_STATUS_OK) return 44;
          if (irx_arrow_array_builder_new(
                  9999, &array_builder, &failure) !=
              IRX_ARROW_STATUS_NOT_SUPPORTED) return 37;
          if (array_builder != NULL) return 38;
          if (failure == NULL) return 45;
          if (irx_arrow_error_release(&failure, &release_failure) !=
              IRX_ARROW_STATUS_OK) return 46;
          if (irx_arrow_tensor_builder_new(
                  IRX_ARROW_TYPE_INT32,
                  -1,
                  NULL,
                  NULL,
                  &tensor_builder,
                  &failure) != IRX_ARROW_STATUS_INVALID_ARGUMENT) {
            return 39;
          }
          if (tensor_builder != NULL) return 40;
          if (failure == NULL) return 47;
          if (irx_arrow_error_release(&failure, &release_failure) !=
              IRX_ARROW_STATUS_OK) return 48;
          if (irx_arrow_tensor_builder_new(
                  IRX_ARROW_TYPE_INT32,
                  2,
                  shape,
                  NULL,
                  &tensor_builder,
                  &failure) != IRX_ARROW_STATUS_OVERFLOW) return 41;
          if (tensor_builder != NULL) return 42;
          if (failure == NULL) return 49;
          if (irx_arrow_error_release(&failure, &release_failure) !=
              IRX_ARROW_STATUS_OK) return 50;
          return 0;
        }
        """
    )

    assert result.returncode == ARROW_STATUS_OK
    assert result.stderr == ""

    with _load_arrow_runtime_library() as library:
        assert (
            library.irx_arrow_status_get_category(
                ARROW_STATUS_INVALID_ARGUMENT
            )
            == ARROW_STATUS_CATEGORY_INVALID
        )
        assert (
            library.irx_arrow_status_get_category(9999)
            == ARROW_STATUS_CATEGORY_UNKNOWN
        )
        assert (
            library.irx_arrow_array_builder_new(
                IRX_ARROW_TYPE_INT32,
                None,
            )
            == ARROW_STATUS_NULL_POINTER
        )
        assert (
            library.irx_arrow_array_builder_new(
                9999,
                ctypes.byref(ctypes.c_void_p()),
            )
            == ARROW_STATUS_NOT_SUPPORTED
        )
        shape = (ctypes.c_int64 * 2)(2**63 - 1, 2)
        assert (
            library.irx_arrow_tensor_builder_new(
                IRX_ARROW_TYPE_INT32,
                2,
                shape,
                None,
                ctypes.byref(ctypes.c_void_p()),
            )
            == ARROW_STATUS_OVERFLOW
        )
        assert (
            library.irx_arrow_tensor_builder_new(
                0,
                0,
                None,
                None,
                ctypes.byref(ctypes.c_void_p()),
            )
            == ARROW_STATUS_NOT_SUPPORTED
        )


def test_arrow_runtime_returns_explicit_owned_error_details() -> None:
    """
    title: Fallible ABI calls should return owned immutable error details.
    """
    with _load_arrow_runtime_library(compatibility=False) as library:
        builder = ctypes.c_void_p()
        failure = ctypes.c_void_p()
        code = library.irx_arrow_array_builder_new(
            9001,
            ctypes.byref(builder),
            ctypes.byref(failure),
        )

        assert code == ARROW_STATUS_NOT_SUPPORTED
        assert builder.value is None
        assert failure.value is not None

        captured_code = ctypes.c_int32()
        operation = ctypes.c_char_p()
        message = ctypes.c_char_p()
        accessor_failure = ctypes.c_void_p()
        assert (
            library.irx_arrow_error_code(
                failure,
                ctypes.byref(captured_code),
                ctypes.byref(accessor_failure),
            )
            == ARROW_STATUS_OK
        )
        assert (
            library.irx_arrow_error_operation(
                failure,
                ctypes.byref(operation),
                ctypes.byref(accessor_failure),
            )
            == ARROW_STATUS_OK
        )
        assert (
            library.irx_arrow_error_message(
                failure,
                ctypes.byref(message),
                ctypes.byref(accessor_failure),
            )
            == ARROW_STATUS_OK
        )
        assert captured_code.value == ARROW_STATUS_NOT_SUPPORTED
        assert operation.value == b"irx_arrow_array_builder_new"
        assert message.value is not None and b"9001" in message.value
        assert accessor_failure.value is None

        assert (
            library.irx_arrow_error_release(
                ctypes.byref(failure),
                ctypes.byref(accessor_failure),
            )
            == ARROW_STATUS_OK
        )
        assert failure.value is None
        assert accessor_failure.value is None

        available = ctypes.c_int32(7)
        assert (
            library.irx_arrow_runtime_has_feature(
                RUNTIME_FEATURE_IDS["array"],
                RUNTIME_FEATURE_PACKED_VERSIONS["array"],
                ctypes.byref(available),
                None,
                ctypes.byref(failure),
            )
            == ARROW_STATUS_NULL_POINTER
        )
        assert available.value == 0
        assert failure.value is not None
        assert (
            library.irx_arrow_error_operation(
                failure,
                ctypes.byref(operation),
                ctypes.byref(accessor_failure),
            )
            == ARROW_STATUS_OK
        )
        assert operation.value == b"irx_arrow_runtime_has_feature"
        assert (
            library.irx_arrow_error_release(
                ctypes.byref(failure),
                ctypes.byref(accessor_failure),
            )
            == ARROW_STATUS_OK
        )
        assert failure.value is None

        assert (
            library.irx_arrow_array_builder_new(
                IRX_ARROW_TYPE_INT32,
                ctypes.byref(builder),
                ctypes.byref(failure),
            )
            == ARROW_STATUS_OK
        )
        assert builder.value is not None
        assert failure.value is None
        assert (
            library.irx_arrow_array_builder_release(
                ctypes.byref(builder),
                ctypes.byref(failure),
            )
            == ARROW_STATUS_OK
        )
        assert builder.value is None
        assert failure.value is None


def test_arrow_runtime_handle_lifecycle_contracts() -> None:
    """
    title: Every implemented opaque handle should obey its ownership class.
    """
    with _load_arrow_runtime_library() as library:
        empty_array = ctypes.c_void_p()
        _assert_arrow_ok(
            library,
            library.irx_arrow_array_release(ctypes.byref(empty_array)),
        )
        _assert_arrow_ok(
            library,
            library.irx_arrow_array_release(ctypes.byref(empty_array)),
        )
        assert (
            library.irx_arrow_array_release(None) == ARROW_STATUS_NULL_POINTER
        )

        missing_retain = ctypes.c_void_p(1)
        assert (
            library.irx_arrow_array_retain(
                None,
                ctypes.byref(missing_retain),
            )
            == ARROW_STATUS_NULL_POINTER
        )
        assert missing_retain.value is None

        array_builder = ctypes.c_void_p()
        _assert_arrow_ok(
            library,
            library.irx_arrow_array_builder_new(
                IRX_ARROW_TYPE_INT32,
                ctypes.byref(array_builder),
            ),
        )
        _assert_handle_metadata(
            library,
            array_builder,
            ARROW_HANDLE_KIND_ARRAY_BUILDER,
            ARROW_HANDLE_OWNERSHIP_UNIQUE,
        )
        wrong_array_slot = ctypes.c_void_p(array_builder.value)
        assert (
            library.irx_arrow_array_release(ctypes.byref(wrong_array_slot))
            == ARROW_STATUS_TYPE_MISMATCH
        )
        assert wrong_array_slot.value == array_builder.value
        wrong_array_slot.value = None
        _assert_arrow_ok(
            library,
            library.irx_arrow_array_builder_release(
                ctypes.byref(array_builder)
            ),
        )
        assert array_builder.value is None
        assert (
            library.irx_arrow_array_builder_append_int(array_builder, 1)
            == ARROW_STATUS_NULL_POINTER
        )
        _assert_arrow_ok(
            library,
            library.irx_arrow_array_builder_release(
                ctypes.byref(array_builder)
            ),
        )

        shape = (ctypes.c_int64 * 1)(1)
        strides = (ctypes.c_int64 * 1)(4)
        tensor_builder = ctypes.c_void_p()
        _assert_arrow_ok(
            library,
            library.irx_arrow_tensor_builder_new(
                IRX_ARROW_TYPE_INT32,
                1,
                shape,
                strides,
                ctypes.byref(tensor_builder),
            ),
        )
        _assert_handle_metadata(
            library,
            tensor_builder,
            ARROW_HANDLE_KIND_TENSOR_BUILDER,
            ARROW_HANDLE_OWNERSHIP_UNIQUE,
        )
        _assert_arrow_ok(
            library,
            library.irx_arrow_tensor_builder_release(
                ctypes.byref(tensor_builder)
            ),
        )
        assert tensor_builder.value is None
        assert (
            library.irx_arrow_tensor_builder_append_int(tensor_builder, 1)
            == ARROW_STATUS_NULL_POINTER
        )

        array_handle = _build_runtime_array(
            library,
            IRX_ARROW_TYPE_INT32,
            "int",
            [1, 2, 3],
        )
        tensor_handle = _build_runtime_tensor(
            library,
            [1, 2, 3, 4],
            [2, 2],
            [8, 4],
        )
        schema_handle = ctypes.c_void_p()
        table_handle = ctypes.c_void_p()
        column_handle = ctypes.c_void_p()
        retained_handles: list[
            tuple[ctypes.c_void_p, Callable[[object], int]]
        ] = []

        try:
            shared_cases = [
                (
                    array_handle,
                    ARROW_HANDLE_KIND_ARRAY,
                    library.irx_arrow_array_retain,
                    library.irx_arrow_array_release,
                ),
                (
                    tensor_handle,
                    ARROW_HANDLE_KIND_TENSOR,
                    library.irx_arrow_tensor_retain,
                    library.irx_arrow_tensor_release,
                ),
            ]
            for handle, kind, retain, release in shared_cases:
                _assert_handle_metadata(
                    library,
                    handle,
                    kind,
                    ARROW_HANDLE_OWNERSHIP_SHARED,
                )
                retained = ctypes.c_void_p()
                _assert_arrow_ok(
                    library,
                    retain(handle, ctypes.byref(retained)),
                )
                assert retained.value == handle.value
                retained_handles.append((retained, release))

            _assert_arrow_ok(
                library,
                library.irx_arrow_array_schema_copy(
                    array_handle,
                    ctypes.byref(schema_handle),
                ),
            )
            names = (ctypes.c_char_p * 1)(b"values")
            arrays = (ctypes.c_void_p * 1)(array_handle.value)
            _assert_arrow_ok(
                library,
                library.irx_arrow_table_new_from_arrays(
                    1,
                    names,
                    arrays,
                    ctypes.byref(table_handle),
                ),
            )
            _assert_arrow_ok(
                library,
                library.irx_arrow_table_column_by_index(
                    table_handle,
                    0,
                    ctypes.byref(column_handle),
                ),
            )

            more_shared_cases = [
                (
                    schema_handle,
                    ARROW_HANDLE_KIND_SCHEMA,
                    library.irx_arrow_schema_retain,
                    library.irx_arrow_schema_release,
                ),
                (
                    table_handle,
                    ARROW_HANDLE_KIND_TABLE,
                    library.irx_arrow_table_retain,
                    library.irx_arrow_table_release,
                ),
                (
                    column_handle,
                    ARROW_HANDLE_KIND_CHUNKED_ARRAY,
                    library.irx_arrow_chunked_array_retain,
                    library.irx_arrow_chunked_array_release,
                ),
            ]
            for handle, kind, retain, release in more_shared_cases:
                _assert_handle_metadata(
                    library,
                    handle,
                    kind,
                    ARROW_HANDLE_OWNERSHIP_SHARED,
                )
                retained = ctypes.c_void_p()
                _assert_arrow_ok(
                    library,
                    retain(handle, ctypes.byref(retained)),
                )
                retained_handles.append((retained, release))
        finally:
            for retained, cleanup_release in retained_handles:
                _assert_arrow_ok(
                    library,
                    cleanup_release(ctypes.byref(retained)),
                )
            library.irx_arrow_chunked_array_release(
                ctypes.byref(column_handle)
            )
            library.irx_arrow_table_release(ctypes.byref(table_handle))
            library.irx_arrow_schema_release(ctypes.byref(schema_handle))
            library.irx_arrow_tensor_release(ctypes.byref(tensor_handle))
            library.irx_arrow_array_release(ctypes.byref(array_handle))

        released_slots = [
            (column_handle, library.irx_arrow_chunked_array_release),
            (table_handle, library.irx_arrow_table_release),
            (schema_handle, library.irx_arrow_schema_release),
            (tensor_handle, library.irx_arrow_tensor_release),
            (array_handle, library.irx_arrow_array_release),
        ]
        for released, final_release in released_slots:
            assert released.value is None
            _assert_arrow_ok(
                library,
                final_release(ctypes.byref(released)),
            )
        assert library.irx_arrow_array_length(array_handle) == -1


def test_arrow_runtime_shared_handle_refcounts_are_thread_safe() -> None:
    """
    title: Shared Arrow handle tokens should retain and release concurrently.
    """
    with _load_arrow_runtime_library() as library:
        array_handle = _build_runtime_array(
            library,
            IRX_ARROW_TYPE_INT32,
            "int",
            [1, 2, 3],
        )
        address = array_handle.value
        assert address is not None

        def retain_and_release() -> list[tuple[int, int]]:
            """
            title: Retain and release shared tokens on one worker thread.
            returns:
              type: list[tuple[int, int]]
            """
            outcomes: list[tuple[int, int]] = []
            for _ in range(250):
                retained = ctypes.c_void_p()
                retain_status = library.irx_arrow_array_retain(
                    ctypes.c_void_p(address),
                    ctypes.byref(retained),
                )
                release_status = library.irx_arrow_array_release(
                    ctypes.byref(retained)
                )
                outcomes.append((retain_status, release_status))
            return outcomes

        try:
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(
                    executor.map(lambda _: retain_and_release(), range(8))
                )
            assert all(
                outcome == (ARROW_STATUS_OK, ARROW_STATUS_OK)
                for worker_results in results
                for outcome in worker_results
            )
            assert (
                library.irx_arrow_array_length(array_handle) == 3  # noqa: PLR2004
            )
        finally:
            _assert_arrow_ok(
                library,
                library.irx_arrow_array_release(ctypes.byref(array_handle)),
            )


def test_arrow_runtime_error_snapshots_are_owned() -> None:
    """
    title: Arrow error snapshots should outlive later calls until released.
    """
    result = _compile_arrow_harness(
        """
        #include "irx_arrow_runtime.h"

        int main(void) {
          irx_arrow_array_builder_handle* builder = NULL;
          irx_arrow_error_handle* error = NULL;
          irx_arrow_error_handle* retained_error = NULL;
          irx_arrow_error_handle* empty = (irx_arrow_error_handle*)1;
          irx_arrow_error_handle* call_failure = NULL;
          irx_arrow_error_handle* failure = NULL;
          irx_arrow_error_handle* release_failure = NULL;
          irx_arrow_status code = IRX_ARROW_STATUS_OK;
          const char* operation = NULL;
          const char* message = NULL;
          const char* upstream = NULL;
          irx_arrow_handle_kind kind = IRX_ARROW_HANDLE_KIND_UNKNOWN;
          irx_arrow_handle_ownership ownership =
              IRX_ARROW_HANDLE_OWNERSHIP_UNKNOWN;

          if (irx_arrow_error_snapshot(&empty, &failure) !=
              IRX_ARROW_STATUS_OK) return 11;
          if (empty != NULL) return 12;
          if (irx_arrow_array_builder_new(
                  9999, &builder, &call_failure) !=
              IRX_ARROW_STATUS_NOT_SUPPORTED) return 13;
          if (builder != NULL || call_failure == NULL) return 14;
          if (irx_arrow_error_snapshot(&error, &failure) !=
              IRX_ARROW_STATUS_OK) return 15;
          if (error == NULL) return 16;
          if (irx_arrow_error_code(error, &code, &failure) !=
                  IRX_ARROW_STATUS_OK ||
              code != IRX_ARROW_STATUS_NOT_SUPPORTED) return 17;
          if (irx_arrow_error_operation(error, &operation, &failure) !=
                  IRX_ARROW_STATUS_OK || operation[0] == '\\0') return 18;
          if (irx_arrow_error_message(error, &message, &failure) !=
                  IRX_ARROW_STATUS_OK || message[0] == '\\0') return 19;
          if (irx_arrow_error_upstream_detail(
                  error, &upstream, &failure) != IRX_ARROW_STATUS_OK ||
              upstream[0] != '\\0') return 20;
          if (irx_arrow_handle_kind_of(error, &kind, &failure) !=
              IRX_ARROW_STATUS_OK) return 32;
          if (kind != IRX_ARROW_HANDLE_KIND_ERROR) return 33;
          if (irx_arrow_handle_ownership_of(
                  error, &ownership, &failure) !=
              IRX_ARROW_STATUS_OK) return 34;
          if (ownership != IRX_ARROW_HANDLE_OWNERSHIP_SHARED) return 35;
          if (irx_arrow_error_retain(
                  error, &retained_error, &failure) !=
              IRX_ARROW_STATUS_OK) return 36;
          if (retained_error != error) return 37;
          if (irx_arrow_error_release(
                  &call_failure, &release_failure) !=
              IRX_ARROW_STATUS_OK) return 40;

          if (irx_arrow_array_builder_new(
                  IRX_ARROW_TYPE_INT32,
                  &builder,
                  &failure) != IRX_ARROW_STATUS_OK) return 21;
          if (builder == NULL) return 22;
          if (irx_arrow_array_builder_release(&builder, &failure) !=
              IRX_ARROW_STATUS_OK) return 27;
          if (irx_arrow_error_snapshot(&empty, &failure) !=
              IRX_ARROW_STATUS_OK) return 23;
          if (empty != NULL) return 24;
          if (irx_arrow_error_message(error, &message, &failure) !=
                  IRX_ARROW_STATUS_OK || message[0] == '\\0') return 25;
          if (irx_arrow_error_snapshot(NULL, &failure) !=
              IRX_ARROW_STATUS_NULL_POINTER) return 26;
          if (failure == NULL) return 41;
          if (irx_arrow_error_release(&failure, &release_failure) !=
              IRX_ARROW_STATUS_OK) return 42;

          if (irx_arrow_error_release(&error, &failure) !=
              IRX_ARROW_STATUS_OK) return 28;
          if (error != NULL) return 29;
          if (irx_arrow_error_message(
                  retained_error, &message, &failure) !=
                  IRX_ARROW_STATUS_OK || message[0] == '\\0') return 38;
          if (irx_arrow_error_release(&retained_error, &failure) !=
              IRX_ARROW_STATUS_OK) return 39;
          if (irx_arrow_error_release(&error, &failure) !=
              IRX_ARROW_STATUS_OK) return 30;
          if (irx_arrow_error_release(NULL, &failure) !=
              IRX_ARROW_STATUS_NULL_POINTER) return 31;
          if (failure == NULL) return 43;
          if (irx_arrow_error_release(&failure, &release_failure) !=
              IRX_ARROW_STATUS_OK) return 44;
          return 0;
        }
        """
    )

    assert result.returncode == ARROW_STATUS_OK
    assert result.stderr == ""


def test_arrow_runtime_error_snapshots_are_thread_isolated() -> None:
    """
    title: >-
      Arrow error snapshots should be isolated and portable across threads.
    """
    with _load_arrow_runtime_library() as library:
        barrier = Barrier(2)

        def capture_array_error() -> ctypes.c_void_p:
            """
            title: Capture one array error after synchronizing worker threads.
            returns:
              type: ctypes.c_void_p
            """
            builder = ctypes.c_void_p()
            assert (
                library.irx_arrow_array_builder_new(
                    9001,
                    ctypes.byref(builder),
                )
                == ARROW_STATUS_NOT_SUPPORTED
            )
            _ = barrier.wait()
            error = ctypes.c_void_p()
            assert (
                library.irx_arrow_error_snapshot(ctypes.byref(error))
                == ARROW_STATUS_OK
            )
            assert error.value is not None
            return error

        def capture_tensor_error() -> ctypes.c_void_p:
            """
            title: Capture one tensor error after synchronizing worker threads.
            returns:
              type: ctypes.c_void_p
            """
            builder = ctypes.c_void_p()
            assert (
                library.irx_arrow_tensor_builder_new(
                    IRX_ARROW_TYPE_INT32,
                    -7,
                    None,
                    None,
                    ctypes.byref(builder),
                )
                == ARROW_STATUS_INVALID_ARGUMENT
            )
            _ = barrier.wait()
            error = ctypes.c_void_p()
            assert (
                library.irx_arrow_error_snapshot(ctypes.byref(error))
                == ARROW_STATUS_OK
            )
            assert error.value is not None
            return error

        with ThreadPoolExecutor(max_workers=2) as executor:
            array_future = executor.submit(capture_array_error)
            tensor_future = executor.submit(capture_tensor_error)
            array_error = array_future.result()
            tensor_error = tensor_future.result()

        try:
            assert (
                library.irx_arrow_error_code(array_error)
                == ARROW_STATUS_NOT_SUPPORTED
            )
            assert (
                library.irx_arrow_error_operation(array_error).decode()
                == "irx_arrow_array_builder_new"
            )
            assert (
                "9001" in library.irx_arrow_error_message(array_error).decode()
            )
            assert (
                library.irx_arrow_error_code(tensor_error)
                == ARROW_STATUS_INVALID_ARGUMENT
            )
            assert (
                library.irx_arrow_error_operation(tensor_error).decode()
                == "irx_arrow_tensor_builder_new"
            )
            assert (
                "ndim"
                in library.irx_arrow_error_message(tensor_error).decode()
            )

            main_thread_error = ctypes.c_void_p()
            assert (
                library.irx_arrow_error_snapshot(
                    ctypes.byref(main_thread_error)
                )
                == ARROW_STATUS_OK
            )
            assert main_thread_error.value is None
        finally:
            library.irx_arrow_error_release(ctypes.byref(array_error))
            library.irx_arrow_error_release(ctypes.byref(tensor_error))


def test_arrow_runtime_harness_c_data_roundtrip() -> None:
    """
    title: Arrow runtime should roundtrip int32 arrays through Arrow C Data.
    """
    result = _compile_arrow_harness(
        """
        #include "irx_arrow_runtime.h"

        int main(void) {
          irx_arrow_array_builder_handle* builder = NULL;
          irx_arrow_array_handle* array = NULL;
          irx_arrow_array_handle* imported = NULL;
          irx_arrow_error_handle* failure = NULL;
          int64_t length = 0;
          int32_t type_id = IRX_ARROW_TYPE_UNKNOWN;
          struct ArrowArray exported_array;
          struct ArrowSchema exported_schema;

          if (irx_arrow_array_builder_int32_new(
                  &builder, &failure) != 0) return 21;
          if (irx_arrow_array_builder_append_int32(
                  builder, 4, &failure) != 0) return 22;
          if (irx_arrow_array_builder_append_int32(
                  builder, 5, &failure) != 0) return 23;
          if (irx_arrow_array_builder_finish(
                  &builder, &array, &failure) != 0) {
            return 24;
          }

          if (
              irx_arrow_array_export(
                  array, &exported_array, &exported_schema, &failure) != 0) {
            return 25;
          }

          if (
              irx_arrow_array_import(
                  &exported_array,
                  &exported_schema,
                  &imported,
                  &failure) != 0) {
            if (exported_array.release != NULL) {
              exported_array.release(&exported_array);
            }
            if (exported_schema.release != NULL) {
              exported_schema.release(&exported_schema);
            }
            return 26;
          }

          if (exported_array.release != NULL) {
            exported_array.release(&exported_array);
          }
          if (exported_schema.release != NULL) {
            exported_schema.release(&exported_schema);
          }

          if (irx_arrow_array_length(
                  imported, &length, &failure) != 0 || length != 2) return 27;
          if (irx_arrow_array_type_id(
                  imported, &type_id, &failure) != 0 ||
              type_id != IRX_ARROW_TYPE_INT32) {
            return 28;
          }

          irx_arrow_array_release(&imported, &failure);
          irx_arrow_array_release(&array, &failure);
          return 0;
        }
        """
    )

    assert result.returncode == 0
    assert result.stderr == ""


def test_arrow_runtime_harness_buffer_view_bridge() -> None:
    """
    title: >-
      Arrow runtime C ABI should expose supported numeric buffers as views.
    """
    result = _compile_arrow_harness(
        """
        #include "irx_arrow_runtime.h"

        int main(void) {
          irx_arrow_array_builder_handle* builder = NULL;
          irx_arrow_array_handle* array = NULL;
          irx_arrow_error_handle* failure = NULL;
          int32_t has_validity = 0;
          irx_buffer_view view = {0};

          if (
              irx_arrow_array_builder_new(
                  IRX_ARROW_TYPE_INT16,
                  &builder,
                  &failure) != 0) {
            return 31;
          }
          if (irx_arrow_array_builder_append_int(
                  builder, 10, &failure) != 0) return 32;
          if (irx_arrow_array_builder_append_null(
                  builder, 1, &failure) != 0) return 33;
          if (irx_arrow_array_builder_append_int(
                  builder, 30, &failure) != 0) return 34;
          if (irx_arrow_array_builder_finish(
                  &builder, &array, &failure) != 0) {
            return 35;
          }

          if (irx_arrow_array_has_validity_bitmap(
                  array, &has_validity, &failure) != 0 ||
              has_validity != 1) return 36;
          if (irx_arrow_array_borrow_buffer_view(
                  array, &view, &failure) != 0) return 37;
          if (view.dtype != (void*)IRX_BUFFER_DTYPE_INT16) return 38;
          if (view.ndim != 1) return 39;
          if (view.shape == NULL || view.shape[0] != 3) return 40;
          if (view.strides == NULL || view.strides[0] != 2) return 41;
          if ((view.flags & IRX_BUFFER_FLAG_VALIDITY_BITMAP) == 0) return 42;

          irx_arrow_array_release(&array, &failure);
          return 0;
        }
        """
    )

    assert result.returncode == 0
    assert result.stderr == ""


def test_arrow_runtime_imports_python_pyarrow_array() -> None:
    """
    title: Arrow runtime should import arrays built by Python PyArrow.
    """
    with _load_arrow_runtime_library() as library:
        _, schema_capsule, array_capsule, schema_addr, array_addr = (
            _pyarrow_c_array([7, 8, 9], pa.int32())
        )
        array_handle = ctypes.c_void_p()

        try:
            _assert_arrow_ok(
                library,
                library.irx_arrow_array_import(
                    array_addr,
                    schema_addr,
                    ctypes.byref(array_handle),
                ),
            )

            assert array_handle.value is not None
            assert library.irx_arrow_array_length(array_handle) == 3  # noqa: PLR2004
            assert library.irx_arrow_array_null_count(array_handle) == 0
            assert library.irx_arrow_array_type_id(array_handle) == (
                IRX_ARROW_TYPE_INT32
            )
        finally:
            _ = (schema_capsule, array_capsule)
            if array_handle.value is not None:
                library.irx_arrow_array_release(ctypes.byref(array_handle))


def test_arrow_runtime_exports_to_python_pyarrow_array() -> None:
    """
    title: Arrow runtime should export arrays consumable by Python PyArrow.
    """
    with _load_arrow_runtime_library() as library:
        array_handle = _build_runtime_array(
            library,
            IRX_ARROW_TYPE_INT32,
            "int",
            [4, 5, 6],
        )
        try:
            exported_schema = ArrowSchemaStruct()
            exported_array = ArrowArrayStruct()

            _assert_arrow_ok(
                library,
                library.irx_arrow_array_export(
                    array_handle,
                    ctypes.byref(exported_array),
                    ctypes.byref(exported_schema),
                ),
            )

            exported = _import_exported_array(
                exported_array,
                exported_schema,
            )
            assert len(exported) == 3  # noqa: PLR2004
            assert exported.to_pylist() == [4, 5, 6]
        finally:
            library.irx_arrow_array_release(ctypes.byref(array_handle))


@pytest.mark.parametrize(
    ("name", "schema_factory", "values", "expected"),
    PRIMITIVE_IMPORT_CASES,
    ids=[case[0] for case in PRIMITIVE_IMPORT_CASES],
)
def test_arrow_runtime_import_export_roundtrips_supported_primitives(
    name: str,
    schema_factory: ArrowSchemaFactory,
    values: Sequence[PrimitiveValue],
    expected: Sequence[PrimitiveValue],
) -> None:
    """
    title: Arrow runtime should roundtrip the supported primitive set.
    parameters:
      name:
        type: str
      schema_factory:
        type: ArrowSchemaFactory
      values:
        type: Sequence[PrimitiveValue]
      expected:
        type: Sequence[PrimitiveValue]
    """
    with _load_arrow_runtime_library() as library:
        type_id, _, _ = _primitive_spec(name)
        _, schema_capsule, array_capsule, schema_addr, array_addr = (
            _pyarrow_c_array(values, cast(pa.DataType, schema_factory()))
        )
        array_handle = ctypes.c_void_p()

        try:
            _assert_arrow_ok(
                library,
                library.irx_arrow_array_import_copy(
                    array_addr,
                    schema_addr,
                    ctypes.byref(array_handle),
                ),
            )

            assert library.irx_arrow_array_type_id(array_handle) == type_id
            assert library.irx_arrow_array_length(array_handle) == len(
                expected
            )
            assert library.irx_arrow_array_null_count(array_handle) == sum(
                value is None for value in expected
            )

            exported_schema = ArrowSchemaStruct()
            exported_array = ArrowArrayStruct()
            _assert_arrow_ok(
                library,
                library.irx_arrow_array_export(
                    array_handle,
                    ctypes.byref(exported_array),
                    ctypes.byref(exported_schema),
                ),
            )

            exported = _import_exported_array(
                exported_array,
                exported_schema,
            )
            assert exported.to_pylist() == expected
        finally:
            _ = (schema_capsule, array_capsule)
            if array_handle.value is not None:
                library.irx_arrow_array_release(ctypes.byref(array_handle))


def test_arrow_runtime_import_copy_rejects_short_buffer_layout() -> None:
    """
    title: Copy import should reject malformed Arrow C Data buffer counts.
    """
    with _load_arrow_runtime_library() as library:
        _, schema_capsule, array_capsule, schema_addr, array_addr = (
            _pyarrow_c_array([1, 2, 3], pa.int32())
        )
        raw_array = _arrow_array_struct(array_addr)
        raw_array.n_buffers = 1
        array_handle = ctypes.c_void_p()

        try:
            code = library.irx_arrow_array_import_copy(
                ctypes.byref(raw_array),
                schema_addr,
                ctypes.byref(array_handle),
            )

            assert code == ARROW_STATUS_INVALID_ARGUMENT
            assert array_handle.value is None
            assert "n_buffers" in library.irx_arrow_last_error().decode()
        finally:
            _ = (schema_capsule, array_capsule)


def test_arrow_runtime_import_copy_rejects_missing_validity() -> None:
    """
    title: Copy import should validate null metadata before reading buffers.
    """
    with _load_arrow_runtime_library() as library:
        _, schema_capsule, array_capsule, schema_addr, array_addr = (
            _pyarrow_c_array([1, None, 3], pa.int32())
        )
        raw_array = _arrow_array_struct(array_addr)
        raw_buffers = ctypes.cast(
            raw_array.buffers,
            ctypes.POINTER(ctypes.c_void_p),
        )
        buffers = (ctypes.c_void_p * 2)(None, raw_buffers[1])
        raw_array.buffers = ctypes.cast(buffers, ctypes.c_void_p).value
        raw_array.null_count = 1
        array_handle = ctypes.c_void_p()

        try:
            code = library.irx_arrow_array_import_copy(
                ctypes.byref(raw_array),
                schema_addr,
                ctypes.byref(array_handle),
            )

            assert code == ARROW_STATUS_NULL_POINTER
            assert array_handle.value is None
            assert "validity bitmap" in (
                library.irx_arrow_last_error().decode()
            )
        finally:
            _ = (schema_capsule, array_capsule, buffers)


@pytest.mark.parametrize(
    ("name", "type_id", "append_kind", "values", "expected"),
    BUILDER_CASES,
    ids=[case[0] for case in BUILDER_CASES],
)
def test_arrow_runtime_builder_supports_supported_primitives(
    name: str,
    type_id: int,
    append_kind: str,
    values: Sequence[BuilderValue],
    expected: Sequence[PrimitiveValue],
) -> None:
    """
    title: >-
      Arrow runtime builders should produce all supported primitive arrays.
    parameters:
      name:
        type: str
      type_id:
        type: int
      append_kind:
        type: str
      values:
        type: Sequence[BuilderValue]
      expected:
        type: Sequence[PrimitiveValue]
    """
    with _load_arrow_runtime_library() as library:
        array_handle = _build_runtime_array(
            library,
            type_id,
            append_kind,
            values,
        )

        try:
            assert library.irx_arrow_array_type_id(array_handle) == type_id
            assert library.irx_arrow_array_length(array_handle) == len(
                expected
            )
            assert library.irx_arrow_array_null_count(array_handle) == sum(
                value is None for value in expected
            )

            exported_schema = ArrowSchemaStruct()
            exported_array = ArrowArrayStruct()
            _assert_arrow_ok(
                library,
                library.irx_arrow_array_export(
                    array_handle,
                    ctypes.byref(exported_array),
                    ctypes.byref(exported_schema),
                ),
            )

            exported = _import_exported_array(
                exported_array,
                exported_schema,
            )
            assert exported.to_pylist() == expected
        finally:
            library.irx_arrow_array_release(ctypes.byref(array_handle))


def test_arrow_cpp_tensor_runtime_borrows_buffer_views() -> None:
    """
    title: Arrow C++ tensors should project stable metadata into buffer views.
    """
    with _load_arrow_runtime_library() as library:
        tensor_handle = _build_runtime_tensor(
            library,
            [1, 2, 3, 4, 5, 6],
            [2, 3],
            [12, 4],
        )
        view = BufferViewStruct()

        try:
            assert (
                library.irx_arrow_tensor_type_id(tensor_handle)
                == IRX_ARROW_TYPE_INT32
            )
            assert library.irx_arrow_tensor_ndim(tensor_handle) == 2  # noqa: PLR2004
            assert library.irx_arrow_tensor_size(tensor_handle) == 6  # noqa: PLR2004

            shape = library.irx_arrow_tensor_shape(tensor_handle)
            strides = library.irx_arrow_tensor_strides(tensor_handle)
            assert [shape[index] for index in range(2)] == [2, 3]
            assert [strides[index] for index in range(2)] == [12, 4]

            _assert_arrow_ok(
                library,
                library.irx_arrow_tensor_borrow_buffer_view(
                    tensor_handle,
                    ctypes.byref(view),
                ),
            )

            values = ctypes.cast(
                view.data,
                ctypes.POINTER(ctypes.c_int32),
            )
            assert values[5] == 6  # noqa: PLR2004
            assert view.dtype == BUFFER_DTYPE_INT32
            assert view.ndim == 2  # noqa: PLR2004
            assert [view.shape[index] for index in range(2)] == [2, 3]
            assert [view.strides[index] for index in range(2)] == [12, 4]
            assert view.flags == (
                BUFFER_FLAG_BORROWED
                | BUFFER_FLAG_READONLY
                | BUFFER_FLAG_C_CONTIGUOUS
            )

            retained_tensor = ctypes.c_void_p()
            _assert_arrow_ok(
                library,
                library.irx_arrow_tensor_retain(
                    tensor_handle,
                    ctypes.byref(retained_tensor),
                ),
            )
            library.irx_arrow_tensor_release(ctypes.byref(retained_tensor))
        finally:
            library.irx_arrow_tensor_release(ctypes.byref(tensor_handle))


def test_arrow_cpp_tensor_runtime_reports_f_contiguous_views() -> None:
    """
    title: Arrow C++ tensor buffer views should preserve F-contiguous flags.
    """
    with _load_arrow_runtime_library() as library:
        tensor_handle = _build_runtime_tensor(
            library,
            [1, 2, 3, 4, 5, 6],
            [2, 3],
            [4, 8],
        )
        view = BufferViewStruct()

        try:
            _assert_arrow_ok(
                library,
                library.irx_arrow_tensor_borrow_buffer_view(
                    tensor_handle,
                    ctypes.byref(view),
                ),
            )

            assert view.flags == (
                BUFFER_FLAG_BORROWED
                | BUFFER_FLAG_READONLY
                | BUFFER_FLAG_F_CONTIGUOUS
            )
        finally:
            library.irx_arrow_tensor_release(ctypes.byref(tensor_handle))


def test_arrow_runtime_nullable_numeric_bridge_is_explicit() -> None:
    """
    title: Nullable numeric arrays should stay Arrow-aware even when bridged.
    """
    with _load_arrow_runtime_library() as library:
        _, schema_capsule, array_capsule, schema_addr, array_addr = (
            _pyarrow_c_array([10, None, 30], pa.int32())
        )
        array_handle = ctypes.c_void_p()
        validity_data = ctypes.c_void_p()
        validity_offset_bits = ctypes.c_int64()
        validity_length_bits = ctypes.c_int64()
        view = BufferViewStruct()

        try:
            _assert_arrow_ok(
                library,
                library.irx_arrow_array_import_copy(
                    array_addr,
                    schema_addr,
                    ctypes.byref(array_handle),
                ),
            )

            assert library.irx_arrow_array_is_nullable(array_handle) == 1
            assert library.irx_arrow_array_null_count(array_handle) == 1
            assert (
                library.irx_arrow_array_has_validity_bitmap(array_handle) == 1
            )
            assert (
                library.irx_arrow_array_can_borrow_buffer_view(array_handle)
                == 1
            )

            _assert_arrow_ok(
                library,
                library.irx_arrow_array_validity_bitmap(
                    array_handle,
                    ctypes.byref(validity_data),
                    ctypes.byref(validity_offset_bits),
                    ctypes.byref(validity_length_bits),
                ),
            )
            assert validity_data.value is not None
            assert validity_offset_bits.value == 0
            assert validity_length_bits.value == 3  # noqa: PLR2004

            _assert_arrow_ok(
                library,
                library.irx_arrow_array_borrow_buffer_view(
                    array_handle,
                    ctypes.byref(view),
                ),
            )

            assert view.owner is None
            assert view.dtype == BUFFER_DTYPE_INT32
            assert view.ndim == 1
            assert view.shape[0] == 3  # noqa: PLR2004
            assert view.strides[0] == 4  # noqa: PLR2004
            assert view.offset_bytes == 0
            assert view.flags == (
                BUFFER_FLAG_BORROWED
                | BUFFER_FLAG_READONLY
                | BUFFER_FLAG_C_CONTIGUOUS
                | BUFFER_FLAG_VALIDITY_BITMAP
            )
        finally:
            _ = (schema_capsule, array_capsule)
            if array_handle.value is not None:
                library.irx_arrow_array_release(ctypes.byref(array_handle))


def test_arrow_runtime_bool_arrays_reject_plain_buffer_view_bridge() -> None:
    """
    title: Bit-packed bool arrays should not masquerade as plain buffer views.
    """
    with _load_arrow_runtime_library() as library:
        _, schema_capsule, array_capsule, schema_addr, array_addr = (
            _pyarrow_c_array([True, False, None], pa.bool_())
        )
        array_handle = ctypes.c_void_p()
        view = BufferViewStruct()

        try:
            _assert_arrow_ok(
                library,
                library.irx_arrow_array_import_copy(
                    array_addr,
                    schema_addr,
                    ctypes.byref(array_handle),
                ),
            )

            assert (
                library.irx_arrow_array_type_id(array_handle)
                == IRX_ARROW_TYPE_BOOL
            )
            assert (
                library.irx_arrow_array_can_borrow_buffer_view(array_handle)
                == 0
            )

            code = library.irx_arrow_array_borrow_buffer_view(
                array_handle,
                ctypes.byref(view),
            )
            assert code == ARROW_STATUS_NOT_SUPPORTED
            assert (
                "bit-packed values" in library.irx_arrow_last_error().decode()
            )
        finally:
            _ = (schema_capsule, array_capsule)
            if array_handle.value is not None:
                library.irx_arrow_array_release(ctypes.byref(array_handle))


def test_arrow_runtime_import_move_adopts_offset_arrays() -> None:
    """
    title: Move import should adopt external C Data and preserve offsets.
    """
    with _load_arrow_runtime_library() as library:
        _, schema_capsule, array_capsule, schema_addr, array_addr = (
            _pyarrow_c_array([10, 20, 30, 40], pa.int32())
        )
        raw_array = _arrow_array_struct(array_addr)
        raw_array.length = 2
        raw_array.offset = 1
        raw_array.null_count = 0

        array_handle = ctypes.c_void_p()
        view = BufferViewStruct()

        _assert_arrow_ok(
            library,
            library.irx_arrow_array_import_move(
                array_addr,
                schema_addr,
                ctypes.byref(array_handle),
            ),
        )

        try:
            moved_array = _arrow_array_struct(array_addr)
            moved_schema = _arrow_schema_struct(schema_addr)

            assert moved_array.release is None
            assert moved_schema.release is None
            assert library.irx_arrow_array_length(array_handle) == 2  # noqa: PLR2004
            assert library.irx_arrow_array_offset(array_handle) == 1

            _assert_arrow_ok(
                library,
                library.irx_arrow_array_borrow_buffer_view(
                    array_handle,
                    ctypes.byref(view),
                ),
            )

            assert view.dtype == BUFFER_DTYPE_INT32
            assert view.shape[0] == 2  # noqa: PLR2004
            assert view.strides[0] == 4  # noqa: PLR2004
            assert view.offset_bytes == 4  # noqa: PLR2004
            assert view.flags == (
                BUFFER_FLAG_BORROWED
                | BUFFER_FLAG_READONLY
                | BUFFER_FLAG_C_CONTIGUOUS
            )

            exported_schema = ArrowSchemaStruct()
            exported_array = ArrowArrayStruct()
            _assert_arrow_ok(
                library,
                library.irx_arrow_array_export(
                    array_handle,
                    ctypes.byref(exported_array),
                    ctypes.byref(exported_schema),
                ),
            )
            assert _import_exported_array(
                exported_array,
                exported_schema,
            ).to_pylist() == [20, 30]
        finally:
            _ = (schema_capsule, array_capsule)
            if array_handle.value is not None:
                library.irx_arrow_array_release(ctypes.byref(array_handle))


def test_arrow_runtime_export_copy_survives_source_release() -> None:
    """
    title: Export should return independent C Data copies.
    """
    with _load_arrow_runtime_library() as library:
        array_handle = _build_runtime_array(
            library,
            IRX_ARROW_TYPE_INT32,
            "int",
            [4, 5, 6],
        )
        exported_schema = ArrowSchemaStruct()
        exported_array = ArrowArrayStruct()

        _assert_arrow_ok(
            library,
            library.irx_arrow_array_export(
                array_handle,
                ctypes.byref(exported_array),
                ctypes.byref(exported_schema),
            ),
        )
        library.irx_arrow_array_release(ctypes.byref(array_handle))

        exported = _import_exported_array(exported_array, exported_schema)
        assert exported.to_pylist() == [4, 5, 6]


def test_arrow_runtime_schema_handles_roundtrip_supported_schemas() -> None:
    """
    title: Schema handles should import, retain, export, and reapply schemas.
    """
    with _load_arrow_runtime_library() as library:
        _, schema_capsule, array_capsule, schema_addr, array_addr = (
            _pyarrow_c_array([1, 2, 3], pa.int16())
        )
        schema_handle = ctypes.c_void_p()
        array_handle = ctypes.c_void_p()
        exported_schema = ArrowSchemaStruct()

        try:
            _assert_arrow_ok(
                library,
                library.irx_arrow_schema_import_copy(
                    schema_addr,
                    ctypes.byref(schema_handle),
                ),
            )
            assert (
                library.irx_arrow_schema_type_id(schema_handle)
                == IRX_ARROW_TYPE_INT16
            )
            assert library.irx_arrow_schema_is_nullable(schema_handle) == 1

            retained_schema = ctypes.c_void_p()
            _assert_arrow_ok(
                library,
                library.irx_arrow_schema_retain(
                    schema_handle,
                    ctypes.byref(retained_schema),
                ),
            )
            library.irx_arrow_schema_release(ctypes.byref(retained_schema))
            assert (
                library.irx_arrow_schema_type_id(schema_handle)
                == IRX_ARROW_TYPE_INT16
            )

            _assert_arrow_ok(
                library,
                library.irx_arrow_schema_export(
                    schema_handle,
                    ctypes.byref(exported_schema),
                ),
            )

            _assert_arrow_ok(
                library,
                library.irx_arrow_array_import_copy(
                    array_addr,
                    ctypes.byref(exported_schema),
                    ctypes.byref(array_handle),
                ),
            )
            assert (
                library.irx_arrow_array_type_id(array_handle)
                == IRX_ARROW_TYPE_INT16
            )
        finally:
            _ = (schema_capsule, array_capsule)
            _release_c_schema(exported_schema)
            if array_handle.value is not None:
                library.irx_arrow_array_release(ctypes.byref(array_handle))
            if schema_handle.value is not None:
                library.irx_arrow_schema_release(ctypes.byref(schema_handle))


def test_arrow_runtime_rejects_unsupported_string_arrays() -> None:
    """
    title: Unsupported variable-width layouts should fail clearly.
    """
    with _load_arrow_runtime_library() as library:
        _, schema_capsule, array_capsule, schema_addr, array_addr = (
            _pyarrow_c_array(["a", "b"], pa.string())
        )
        array_handle = ctypes.c_void_p()

        code = library.irx_arrow_array_import_copy(
            array_addr,
            schema_addr,
            ctypes.byref(array_handle),
        )
        _ = (schema_capsule, array_capsule)

        assert code == ARROW_STATUS_NOT_SUPPORTED
        assert array_handle.value is None
        assert "Unsupported Arrow storage type" in (
            library.irx_arrow_last_error().decode()
        )
