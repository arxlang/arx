"""
title: Native file contracts and direct ASTx semantic boundaries.
"""

from __future__ import annotations

import ctypes
import shutil
import subprocess

from pathlib import Path

import astx
import pytest

from irx.analysis import SemanticError, analyze
from irx.analysis.types import clone_type, same_type
from irx.builder import Builder
from irx.builder.runtime.file import FILE_ERROR_CAPACITY
from llvmlite import binding as llvm
from typeguard import TypeCheckError

EXPECTED_BRANCH_EXIT = 7
WRITE_FAULT = 4
FLUSH_FAULT = 5

NATIVE_ROOT = Path(__file__).parents[1] / "src/irx/builder/runtime/file/native"


def module_for(*nodes: astx.AST) -> astx.Module:
    """
    title: Put test nodes in a non-generator main function.
    parameters:
      nodes:
        type: astx.AST
        variadic: positional
    returns:
      type: astx.Module
    """
    body = astx.Block()
    for node in nodes:
        body.append(node)
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module = astx.Module("main")
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
            body,
        )
    )
    return module


def test_file_model_and_direct_translation() -> None:
    """
    title: File identity and keyword calls survive analysis and valid LLVM.
    """
    type_ = astx.FileType()
    assert isinstance(clone_type(type_), astx.FileType)
    assert not same_type(type_, astx.OpaqueHandleType("irx_file"))
    call = astx.FunctionCall(
        "open",
        [],
        keywords=(
            astx.KeywordArgument("file", astx.LiteralString("input.txt")),
        ),
    )
    module = module_for(astx.VariableDeclaration("stream", type_, value=call))
    text = Builder().translate(module)
    llvm.parse_assembly(text).verify()
    assert "irx_file_open" in text
    assert "irx_file_release" in text
    with pytest.raises(TypeCheckError):
        astx.FunctionCall(
            "open",
            [],
            keywords=(
                astx.KeywordArgument("file", astx.LiteralString("ok")),
                "bad",
            ),
        )  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "type_",
    [
        astx.FileType(),
        astx.ListType([astx.FileType()]),
        astx.UnionType([astx.String(), astx.FileType()]),
    ],
)
def test_file_signatures_are_rejected(type_: astx.DataType) -> None:
    """
    title: Opaque file storage never leaks into a general callable ABI.
    parameters:
      type_:
        type: astx.DataType
    """
    prototype = astx.FunctionPrototype(
        "unsupported",
        astx.Arguments(astx.Argument("value", type_)),
        astx.NoneType(),
    )
    with pytest.raises(SemanticError, match="file types are supported only"):
        analyze(module_for(prototype))


@pytest.fixture(scope="module")
def native(tmp_path_factory: pytest.TempPathFactory) -> ctypes.CDLL:
    """
    title: Build the actual C runtime with small controllable libc test stubs.
    parameters:
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: ctypes.CDLL
    """
    clang = shutil.which("clang")
    if clang is None:
        pytest.skip("clang is required for native file contracts")
    root = tmp_path_factory.mktemp("file-runtime")
    harness = root / "runtime.c"
    harness.write_text(
        """
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
static int fault = 0, calls = 0, live = 0;
void irx_file_test_fault(int value) { fault = value; calls = 0; }
int irx_file_test_live(void) { return live; }
void irx_file_test_free(void* p) { if (p) live--; free(p); }
static void* test_malloc(size_t n) {
  void* p = fault == 1 ? NULL : malloc(n);
  if (p) live++;
  return p;
}
static void* test_realloc(void* p, size_t n) {
  return fault == 2 ? NULL : realloc(p, n);
}
static size_t test_read(void* p, size_t s, size_t n, FILE* f) {
  calls++;
  if (fault == 3 || ((fault == 8 || fault == 10) && calls > 1)) return 0;
  if ((fault == 7 || fault == 8 || fault == 10) && n > 3) n = 3;
  return fread(p, s, n, f);
}
static size_t test_write(const void* p, size_t s, size_t n, FILE* f) {
  calls++;
  if (fault == 4 || ((fault == 8 || fault == 10) && calls > 1)) return 0;
  if ((fault == 7 || fault == 8 || fault == 10) && n > 3) n = 3;
  return fwrite(p, s, n, f);
}
static int test_error(FILE* f) {
  if (fault == 8 && calls > 1) { errno = EIO; return 1; }
  return ferror(f);
}
static int test_flush(FILE* f) {
  if (fault == 5) {
    errno = ENOSPC;
    return EOF;
  }
  return fflush(f);
}
static int test_close(FILE* f) {
  int status = fclose(f);
  if (fault == 6) {
    errno = EIO;
    return EOF;
  }
  return status;
}
/* Exercise narrowing to a smaller target size_t without huge allocations. */
#undef SIZE_MAX
#define SIZE_MAX (fault == 9 ? 31u : (size_t)-1)
#define malloc test_malloc
#define free irx_file_test_free
#define ferror test_error
#define realloc test_realloc
#define fread test_read
#define fwrite test_write
#define fflush test_flush
#define fclose test_close
#include "irx_file_runtime.c"
""",
        encoding="utf-8",
    )
    library = root / "file.so"
    subprocess.run(
        [
            clang,
            "-std=c99",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-shared",
            "-fPIC",
            "-I",
            str(NATIVE_ROOT),
            str(harness),
            "-o",
            str(library),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    lib = ctypes.CDLL(str(library))
    pointer = ctypes.c_void_p
    output = ctypes.POINTER(pointer)
    error = ctypes.c_char_p
    lib.irx_file_open.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_int32,
        output,
        error,
    ]
    lib.irx_file_read_bytes.argtypes = [
        pointer,
        ctypes.c_int64,
        output,
        ctypes.POINTER(ctypes.c_int64),
        error,
    ]
    lib.irx_file_write_bytes.argtypes = [
        pointer,
        pointer,
        ctypes.c_int64,
        ctypes.POINTER(ctypes.c_int64),
        error,
    ]
    lib.irx_file_test_live.restype = ctypes.c_int
    lib.irx_file_test_free.argtypes = [pointer]
    lib.irx_file_test_free.restype = None
    lib.irx_file_read.argtypes = [pointer, output, error]
    lib.irx_file_write.argtypes = [
        pointer,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_int64),
        error,
    ]
    for name in (
        "open",
        "read",
        "write",
        "read_bytes",
        "write_bytes",
        "flush",
        "close",
        "release",
    ):
        function = getattr(lib, f"irx_file_{name}")
        function.restype = ctypes.c_int32
        if name in {"flush", "close", "release"}:
            function.argtypes = [pointer, error]
    lib.irx_file_test_fault.argtypes = [ctypes.c_int]
    lib.irx_file_test_fault.restype = None
    return lib


def read_native(native: ctypes.CDLL, handle: ctypes.c_void_p) -> bytes:
    """
    title: Read native output and release its independent allocation.
    parameters:
      native:
        type: ctypes.CDLL
      handle:
        type: ctypes.c_void_p
    returns:
      type: bytes
    """
    error = ctypes.create_string_buffer(FILE_ERROR_CAPACITY)
    value = ctypes.c_void_p()
    assert native.irx_file_read(handle, ctypes.byref(value), error) == 0, (
        error.value
    )
    try:
        return ctypes.string_at(value)
    finally:
        native.irx_file_test_free(value)


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"one\r\ntwo\rthree\nfour",
        "hé\U0001f600".encode(),
        b"a" * 4094 + b"\r\n" + "é".encode() * 5000,
    ],
)
def test_native_read_and_eof(
    native: ctypes.CDLL, tmp_path: Path, content: bytes
) -> None:
    """
    title: Chunked UTF-8 reads normalize newlines and distinguish empty EOF.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
      content:
        type: bytes
    """
    path = tmp_path / "source"
    path.write_bytes(content)
    handle = ctypes.c_void_p()
    error = ctypes.create_string_buffer(FILE_ERROR_CAPACITY)
    assert (
        native.irx_file_open(
            bytes(path), b"rt", 0, ctypes.byref(handle), error
        )
        == 0
    )
    try:
        assert read_native(native, handle) == content.replace(
            b"\r\n", b"\n"
        ).replace(b"\r", b"\n")
        assert read_native(native, handle) == b""
        assert native.irx_file_flush(handle, error) == 0
        count = ctypes.c_int64(123)
        assert (
            native.irx_file_write(handle, b"no", ctypes.byref(count), error)
            != 0
        )
        assert count.value == 0
        assert native.irx_file_close(handle, error) == 0
        assert native.irx_file_close(handle, error) == 0
        value = ctypes.c_void_p(123)
        assert native.irx_file_read(handle, ctypes.byref(value), error) != 0
        assert value.value is None
        assert b"closed" in error.value
    finally:
        assert native.irx_file_release(handle, error) == 0


@pytest.mark.parametrize(
    "content",
    [
        b"a\0b",
        b"\xff",
        b"\xc0\x80",
        b"\xed\xa0\x80",
        b"\xf4\x90\x80\x80",
        b"\xe2\x82",
    ],
)
def test_native_rejects_bad_text(
    native: ctypes.CDLL, tmp_path: Path, content: bytes
) -> None:
    """
    title: Unrepresentable text fails without publishing partial buffers.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
      content:
        type: bytes
    """
    path = tmp_path / "bad"
    path.write_bytes(content)
    error = ctypes.create_string_buffer(FILE_ERROR_CAPACITY)
    handle, value = ctypes.c_void_p(), ctypes.c_void_p(123)
    assert (
        native.irx_file_open(bytes(path), b"r", 0, ctypes.byref(handle), error)
        == 0
    )
    try:
        assert native.irx_file_read(handle, ctypes.byref(value), error) != 0
        assert value.value is None
        assert error.value
    finally:
        native.irx_file_release(handle, error)


@pytest.mark.parametrize(
    "mode", [b"", b"wb+", b"x", b"r+", b"rr", b"tr", b"U"]
)
def test_native_mode_failure_is_non_destructive(
    native: ctypes.CDLL, tmp_path: Path, mode: bytes
) -> None:
    """
    title: Unsupported dynamic modes are rejected before fopen side effects.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
      mode:
        type: bytes
    """
    path = tmp_path / "existing"
    path.write_bytes(b"keep")
    handle = ctypes.c_void_p(123)
    error = ctypes.create_string_buffer(FILE_ERROR_CAPACITY)
    assert (
        native.irx_file_open(bytes(path), mode, 0, ctypes.byref(handle), error)
        != 0
    )
    assert handle.value is None
    assert path.read_bytes() == b"keep"


@pytest.mark.parametrize("content", [b"\xff", b"\xed\xa0\x80", b"\xe2\x82"])
def test_native_write_rejects_bad_utf8(
    native: ctypes.CDLL, tmp_path: Path, content: bytes
) -> None:
    """
    title: Invalid write text and mode mismatches publish no successful output.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
      content:
        type: bytes
    """
    path = tmp_path / "output"
    handle = ctypes.c_void_p()
    error = ctypes.create_string_buffer(FILE_ERROR_CAPACITY)
    assert (
        native.irx_file_open(
            bytes(path), b"wt", 0, ctypes.byref(handle), error
        )
        == 0
    )
    try:
        value = ctypes.c_void_p(123)
        assert native.irx_file_read(handle, ctypes.byref(value), error) != 0
        assert value.value is None
        count = ctypes.c_int64(123)
        assert (
            native.irx_file_write(handle, content, ctypes.byref(count), error)
            != 0
        )
        assert count.value == 0
        assert error.value
    finally:
        assert native.irx_file_release(handle, error) == 0
    assert path.read_bytes() == b""


@pytest.mark.parametrize("fault", [1, 2, 3, 4, 5, 6])
def test_native_failure_slots_and_release(
    native: ctypes.CDLL, tmp_path: Path, fault: int
) -> None:
    """
    title: Allocation, I/O, flush, and consuming-close failures are safe.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
      fault:
        type: int
    """
    path = tmp_path / "fault"
    path.write_bytes(b"a" * 10000)
    error = ctypes.create_string_buffer(FILE_ERROR_CAPACITY)
    handle = ctypes.c_void_p()
    mode = b"r" if fault in {1, 2, 3} else b"w"
    assert (
        native.irx_file_open(bytes(path), mode, 0, ctypes.byref(handle), error)
        == 0
    )
    native.irx_file_test_fault(fault)
    try:
        if fault in {1, 2, 3}:
            value = ctypes.c_void_p(123)
            assert (
                native.irx_file_read(handle, ctypes.byref(value), error) != 0
            )
            assert value.value is None
        elif fault == WRITE_FAULT:
            count = ctypes.c_int64(123)
            assert (
                native.irx_file_write(
                    handle, b"abc", ctypes.byref(count), error
                )
                != 0
            )
            assert count.value == 0
        elif fault == FLUSH_FAULT:
            assert native.irx_file_flush(handle, error) != 0
        else:
            assert native.irx_file_release(handle, error) != 0
            handle = ctypes.c_void_p()
        assert error.value
    finally:
        native.irx_file_test_fault(0)
        native.irx_file_release(handle, error)


def test_native_open_allocation_and_nulls(
    native: ctypes.CDLL, tmp_path: Path
) -> None:
    """
    title: Null inputs and initial allocation failure never create a file.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
    """
    path = tmp_path / "uncreated"
    error = ctypes.create_string_buffer(FILE_ERROR_CAPACITY)
    handle = ctypes.c_void_p(123)
    native.irx_file_test_fault(1)
    try:
        assert (
            native.irx_file_open(
                bytes(path), b"w", 0, ctypes.byref(handle), error
            )
            != 0
        )
        assert handle.value is None
        assert not path.exists()
    finally:
        native.irx_file_test_fault(0)
    assert (
        native.irx_file_open(None, b"r", 0, ctypes.byref(handle), error) != 0
    )
    assert native.irx_file_open(bytes(path), b"r", 0, None, error) != 0
    assert native.irx_file_release(None, error) == 0
    pointer = ctypes.c_void_p(123)
    count = ctypes.c_int64(123)
    assert (
        native.irx_file_read_bytes(
            None, 0, ctypes.byref(pointer), ctypes.byref(count), error
        )
        != 0
    )
    assert pointer.value is None and count.value == 0
    assert (
        native.irx_file_read_bytes(None, 0, None, ctypes.byref(count), error)
        != 0
    )
    assert (
        native.irx_file_read_bytes(None, 0, ctypes.byref(pointer), None, error)
        != 0
    )
    assert native.irx_file_write_bytes(None, None, 0, None, error) != 0
    assert (
        native.irx_file_write_bytes(None, None, -1, ctypes.byref(count), error)
        != 0
    )


def test_native_repeated_release_does_not_leak_descriptors(
    native: ctypes.CDLL,
    tmp_path: Path,
) -> None:
    """
    title: Repeated owned-wrapper lifetimes keep descriptor growth bounded.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
    """
    descriptors = Path("/proc/self/fd")
    if not descriptors.is_dir():
        pytest.skip("descriptor accounting requires Linux procfs")
    before = len(list(descriptors.iterdir()))
    error = ctypes.create_string_buffer(FILE_ERROR_CAPACITY)
    for _ in range(200):
        handle = ctypes.c_void_p()
        assert (
            native.irx_file_open(
                bytes(tmp_path / "loop"), b"a", 0, ctypes.byref(handle), error
            )
            == 0
        )
        assert native.irx_file_release(handle, error) == 0
    assert len(list(descriptors.iterdir())) == before


def test_direct_open_rejects_literal_nul() -> None:
    """
    title: Known path NUL fails before native C-string lowering.
    """
    call = astx.FunctionCall("open", [astx.LiteralString("prefix\0suffix")])
    with pytest.raises(SemanticError, match="NUL"):
        analyze(module_for(call))


def test_file_cleanup_in_terminating_branch(tmp_path: Path) -> None:
    """
    title: Direct ASTx control flow releases only successfully acquired files.
    parameters:
      tmp_path:
        type: Path
    """
    if shutil.which("clang") is None:
        pytest.skip("clang is required for branch cleanup execution")
    path = tmp_path / "branch-output"
    branch = astx.Block()
    branch.append(
        astx.VariableDeclaration(
            "stream",
            astx.FileType(),
            value=astx.FunctionCall(
                "open",
                [astx.LiteralString(str(path)), astx.LiteralString("w")],
            ),
        )
    )
    branch.append(
        astx.MethodCall(
            astx.Identifier("stream"), "write", [astx.LiteralString("saved")]
        )
    )
    branch.append(astx.FunctionReturn(astx.LiteralInt32(7)))
    module = module_for(
        astx.IfStmt(astx.LiteralBoolean(True), branch, astx.Block())
    )
    text = Builder().translate(module)
    llvm.parse_assembly(text).verify()
    assert 'call i32 @"irx_file_release"' in text
    assert "store i32 7" in text
    executable = tmp_path / "branch"
    Builder().build(module, str(executable))
    result = subprocess.run(
        [str(executable)], capture_output=True, timeout=10, check=False
    )
    assert result.returncode == EXPECTED_BRANCH_EXIT, result.stderr
    assert path.read_bytes() == b"saved"


@pytest.mark.parametrize(
    "buffering",
    [
        astx.LiteralInt8(-1),
        astx.LiteralInt16(-1),
        astx.LiteralInt64(-1),
    ],
)
def test_open_accepts_signed_constant_default_widths(
    buffering: astx.DataType,
) -> None:
    """
    title: Default buffering is a constant value, not a specific integer width.
    parameters:
      buffering:
        type: astx.DataType
    """
    call = astx.FunctionCall(
        "open",
        [astx.LiteralString("input")],
        keywords=(astx.KeywordArgument("buffering", buffering),),
    )
    analyze(module_for(call))


def test_reanalysis_does_not_reuse_builtin_identity_after_shadowing() -> None:
    """
    title: Reanalysis clears stale native-open bindings when shadowed.
    """
    call = astx.FunctionCall("open", [astx.LiteralString("ignored")])
    module = module_for(call)
    analyze(module)
    body = astx.Block()
    body.append(astx.FunctionReturn(astx.LiteralInt32(7)))
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype(
                "open",
                astx.Arguments(astx.Argument("path", astx.String())),
                astx.Int32(),
            ),
            body,
        )
    )
    text = Builder().translate(module)
    assert "irx_file_open" not in text
    assert getattr(call, "semantic").resolved_file_open is None
    assert getattr(call, "semantic").resource_ownership is None
    module.block.pop()
    assert "irx_file_open" in Builder().translate(module)
    assert getattr(call, "semantic").resolved_call is None


def test_reanalysis_clears_read_ownership_for_statement_only_method() -> None:
    """
    title: A reused close node never inherits heap-string ownership from read.
    """
    opened = astx.FunctionCall("open", [astx.LiteralString("ignored")])
    method = astx.MethodCall(astx.Identifier("file"), "read", [])
    module = module_for(
        astx.VariableDeclaration("file", astx.FileType(), value=opened), method
    )
    analyze(module)
    method.method_name = "close"
    text = Builder().translate(module)
    llvm.parse_assembly(text).verify()
    assert getattr(method, "semantic").resource_ownership is None
    assert "irx_file_read" not in text


def test_native_error_categories_preserve_errno(
    native: ctypes.CDLL, tmp_path: Path
) -> None:
    """
    title: File categories and captured errno do not depend on message text.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
    """
    import errno  # noqa: PLC0415

    native.irx_file_test_fault(0)
    output = ctypes.c_void_p(123)
    error = ctypes.create_string_buffer(256)
    missing = bytes(tmp_path / "missing")
    status = native.irx_file_open(
        missing, b"r", 0, ctypes.byref(output), error
    )
    assert status == 65536 | errno.ENOENT
    assert output.value is None
    status = native.irx_file_open(
        missing, b"bad", 0, ctypes.byref(output), error
    )
    mode_status = 6
    assert status == mode_status
    assert output.value is None
    closed_status = 2
    assert (
        native.irx_file_read(None, ctypes.byref(output), error)
        == closed_status
    )
    assert output.value is None


@pytest.mark.parametrize("write", [False, True])
@pytest.mark.parametrize(
    "fault,expected", [(0, 0), (1, 4), (7, 0), (8, 65541), (9, 5), (10, 7)]
)
def test_binary_transfer_faults(
    native: ctypes.CDLL, tmp_path: Path, write: bool, fault: int, expected: int
) -> None:
    """
    title: Retry short progress, gate outputs, and free partial read storage.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
      write:
        type: bool
      fault:
        type: int
      expected:
        type: int
    """
    data = bytes(range(256))
    path = tmp_path / "bytes"
    path.write_bytes(data)
    error = ctypes.create_string_buffer(FILE_ERROR_CAPACITY)
    handle = ctypes.c_void_p()
    pointer = ctypes.c_void_p(123)
    count = ctypes.c_int64(123)
    baseline = native.irx_file_test_live()
    assert (
        native.irx_file_open(
            bytes(path),
            b"wb" if write else b"rb",
            0,
            ctypes.byref(handle),
            error,
        )
        == 0
    )
    native.irx_file_test_fault(fault)
    try:
        if write:
            status = native.irx_file_write_bytes(
                handle, data, len(data), ctypes.byref(count), error
            )
            # Borrowed writes do not allocate payload storage.
            if fault == 1:
                expected = 0
        else:
            status = native.irx_file_read_bytes(
                handle,
                len(data),
                ctypes.byref(pointer),
                ctypes.byref(count),
                error,
            )
        assert status == expected, error.value
        if status == 0:
            assert count.value == len(data)
            if not write:
                assert ctypes.string_at(pointer, count.value) == data
        else:
            assert count.value == 0
            if not write:
                assert pointer.value is None
        if not write:
            native.irx_file_test_free(pointer)
    finally:
        native.irx_file_test_fault(0)
        assert native.irx_file_release(handle, error) == 0
    assert native.irx_file_test_live() == baseline
    if write:
        assert path.read_bytes() == (
            data if expected == 0 else data[:3] if fault in {8, 10} else b""
        )


@pytest.mark.parametrize("mode", [b"r", b"w", b"rb", b"wb", b"ab"])
def test_binary_zero_and_closed_contracts(
    native: ctypes.CDLL, tmp_path: Path, mode: bytes
) -> None:
    """
    title: Empty payloads still validate direction, binary mode, and state.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
      mode:
        type: bytes
    """
    path = tmp_path / "empty"
    path.write_bytes(b"\x00\xff\r\n")
    error = ctypes.create_string_buffer(FILE_ERROR_CAPACITY)
    handle = ctypes.c_void_p()
    pointer = ctypes.c_void_p()
    count = ctypes.c_int64()
    assert (
        native.irx_file_open(bytes(path), mode, 0, ctypes.byref(handle), error)
        == 0
    )
    try:
        for closed in (False, True):
            if closed:
                assert native.irx_file_close(handle, error) == 0
            read = native.irx_file_read_bytes(
                handle, 0, ctypes.byref(pointer), ctypes.byref(count), error
            )
            write = native.irx_file_write_bytes(
                handle, None, 0, ctypes.byref(count), error
            )
            assert (read == 0) == (mode == b"rb" and not closed)
            assert (write == 0) == (mode in {b"wb", b"ab"} and not closed)
            assert pointer.value is None and count.value == 0
            if mode.endswith(b"b") and not closed:
                assert (
                    native.irx_file_read(handle, ctypes.byref(pointer), error)
                    != 0
                )
                assert (
                    native.irx_file_write(
                        handle, b"", ctypes.byref(count), error
                    )
                    != 0
                )
            assert (
                native.irx_file_read_bytes(
                    handle,
                    -1,
                    ctypes.byref(pointer),
                    ctypes.byref(count),
                    error,
                )
                != 0
            )
            assert (
                native.irx_file_write_bytes(
                    handle, None, 1, ctypes.byref(count), error
                )
                != 0
            )
    finally:
        assert native.irx_file_release(handle, error) == 0


@pytest.mark.parametrize("mode", [b"rb", b"wb", b"ab"])
def test_binary_options_precede_open(
    native: ctypes.CDLL, tmp_path: Path, mode: bytes
) -> None:
    """
    title: Dynamic binary text options cannot create or truncate a path.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
      mode:
        type: bytes
    """
    error = ctypes.create_string_buffer(FILE_ERROR_CAPACITY)
    handle = ctypes.c_void_p(123)
    for existing in (False, True):
        path = tmp_path / "preserved"
        if existing:
            path.write_bytes(b"unchanged")
        assert (
            native.irx_file_open(
                bytes(path), mode, 1, ctypes.byref(handle), error
            )
            != 0
        )
        assert handle.value is None
        assert (
            path.read_bytes() == b"unchanged"
            if existing
            else not path.exists()
        )
