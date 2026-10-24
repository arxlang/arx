"""
title: Native exception ownership, dynamic scopes, and reporting contracts.
"""

import ctypes
import shutil
import subprocess

from collections.abc import Iterator
from pathlib import Path

import pytest

from irx.builder.runtime.exceptions import parse_exception_output

NATIVE = Path(__file__).parents[1] / "src/irx/builder/runtime"


@pytest.fixture
def runtime(tmp_path: Path) -> Iterator[ctypes.CDLL]:
    """
    title: Build an instrumented class and exception runtime without Arrow.
    parameters:
      tmp_path:
        type: Path
    returns:
      type: Iterator[ctypes.CDLL]
    """
    compiler = shutil.which("clang")
    if compiler is None:
        pytest.skip("native exception tests require clang")
    source = tmp_path / "runtime.c"
    source.write_text(
        """#include <stdlib.h>
#include <stdint.h>
static int allocated = 0, calls = 0, fault = 0, drops = 0;
static int drop_fault = 0;
void* test_object(const char*, const char*);
static void* counted_malloc(size_t size) {
  void* result;
  if (++calls == fault) return NULL;
  result = malloc(size); if (result) allocated++; return result;
}
static void* counted_calloc(size_t count, size_t size) {
  void* result;
  if (++calls == fault) return NULL;
  result = calloc(count, size); if (result) allocated++; return result;
}
static void counted_free(void* value) {
  if (value) allocated--;
  free(value);
}
#define malloc counted_malloc
#define calloc counted_calloc
#define free counted_free
#include "irx_class_runtime.c"
#include "irx_exception_runtime.c"
int test_raise(irx_exception_context*, void*, void*, int);
static irx_exception_info** record(void* payload) {
  return (irx_exception_info**)((char*)payload + sizeof(void*));
}
static int32_t drop(void* context, void* payload, char* error) {
  (void)context; (void)error;
  irx_exception_info_release(*record(payload));
  drops++;
  if (drop_fault) {
    void* secondary;
    drop_fault--;
    secondary = test_object("DropFailure", "release failed");
    if (!secondary) abort();
    if (test_raise(context, secondary, NULL, 0) != 1) abort();
    irx_class_release(context, secondary, error);
    return 1;
  }
  return 0;
}
void* test_object(const char* name, const char* message) {
  void* object = NULL;
  const char* ancestry[] = {
    name, "builtin::Exception", "builtin::BaseException"};
  char error[256];
  if (irx_class_create(2 * sizeof(void*), drop, &object, error)) return NULL;
  if (irx_exception_info_create(name,message,ancestry,3,record(object))) {
    irx_class_release(NULL, object, error); return NULL;
  }
  irx_class_complete(object); return object;
}
int test_raise(irx_exception_context* ctx, void* object,
               void* cause, int mode) {
  return irx_exception_raise(ctx,object,record(object),
    cause ? *record(cause) : NULL,
    mode,"source|é.x",4,7,"TEST");
}
void test_release(irx_exception_context* ctx, void* object) {
  char error[256]; irx_class_release(ctx,object,error);
}
void test_fault(int nth) { calls=0; fault=nth; }
void test_drop_fault(void) { drop_fault=1; }
int test_allocated(void) { return allocated; }
int test_drops(void) { return drops; }
""",
        encoding="utf-8",
    )
    library = tmp_path / "runtime.so"
    subprocess.run(
        [
            compiler,
            "-std=c99",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-shared",
            "-fPIC",
            # LLVM JIT tests may have loaded another runtime globally. Keep
            # allocator accounting inside this independently built harness.
            "-Wl,-Bsymbolic",
            "-I",
            str(NATIVE / "classes/native"),
            "-I",
            str(NATIVE / "exceptions/native"),
            str(source),
            "-o",
            str(library),
        ],
        check=True,
    )
    native = ctypes.CDLL(str(library))
    pointer = ctypes.c_void_p
    native.test_object.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    native.test_object.restype = pointer
    native.test_raise.argtypes = [pointer, pointer, pointer, ctypes.c_int]
    native.test_release.argtypes = [pointer, pointer]
    native.irx_exception_context_create.argtypes = [ctypes.POINTER(pointer)]
    for name in ("context_destroy", "pending", "reraise", "report"):
        getattr(native, "irx_exception_" + name).argtypes = [pointer]
    for name in (
        "handler_enter",
        "finally_enter",
        "cleanup_enter",
        "pending_take",
        "handled_payload",
    ):
        function = getattr(native, "irx_exception_" + name)
        function.argtypes = [pointer]
        function.restype = pointer
    for name in (
        "handler_leave",
        "cleanup_leave",
        "pending_restore",
        "pending_discard",
    ):
        getattr(native, "irx_exception_" + name).argtypes = [pointer, pointer]
    native.irx_exception_finally_leave.argtypes = [
        pointer,
        pointer,
        ctypes.c_int,
    ]
    native.irx_exception_matches.argtypes = [pointer, ctypes.c_char_p]
    native.irx_exception_trace.argtypes = [
        pointer,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_int,
    ]
    yield native
    assert native.test_allocated() == 0


def context(runtime: ctypes.CDLL) -> ctypes.c_void_p:
    """
    title: Allocate one explicit execution context.
    parameters:
      runtime:
        type: ctypes.CDLL
    returns:
      type: ctypes.c_void_p
    """
    result = ctypes.c_void_p()
    assert runtime.irx_exception_context_create(ctypes.byref(result)) == 0
    return result


def test_copied_message_nominal_match_and_dynamic_reraise(
    runtime: ctypes.CDLL, capfd: pytest.CaptureFixture[str]
) -> None:
    """
    title: Pending and handled values retain classes and immutable diagnostics.
    parameters:
      runtime:
        type: ctypes.CDLL
      capfd:
        type: pytest.CaptureFixture[str]
    """
    ctx = context(runtime)
    text = ctypes.create_string_buffer(b"original|message\nline")
    value = runtime.test_object(b"module::Failure", text)
    text.value = b"mutated"
    assert runtime.test_raise(ctx, value, None, 0) == 1
    runtime.test_release(ctx, value)
    assert runtime.irx_exception_matches(ctx, b"module::Failure") == 1
    assert runtime.irx_exception_matches(ctx, b"builtin::Exception") == 1
    assert runtime.irx_exception_matches(ctx, b"Failure") == 0
    handler = runtime.irx_exception_handler_enter(ctx)
    assert runtime.irx_exception_pending(ctx) == 0
    assert runtime.irx_exception_handled_payload(ctx) == value
    assert runtime.irx_exception_reraise(ctx) == 1
    runtime.irx_exception_handler_leave(ctx, handler)
    runtime.irx_exception_trace(ctx, b"caller.x", 9, 2)
    runtime.irx_exception_report(ctx)
    report = parse_exception_output(capfd.readouterr().err)
    assert report is not None
    assert report.message == "original|message\nline"
    assert report.source == "source|é.x"
    assert report.frames[0].source == "caller.x"
    runtime.irx_exception_context_destroy(ctx)
    assert runtime.test_drops() == 1


@pytest.mark.parametrize(
    "mode,role", [(0, "context"), (1, "cause"), (2, None)]
)
def test_chaining_and_suppression(
    runtime: ctypes.CDLL,
    capfd: pytest.CaptureFixture[str],
    mode: int,
    role: str | None,
) -> None:
    """
    title: Causes and contexts are snapshots and suppression hides both.
    parameters:
      runtime:
        type: ctypes.CDLL
      capfd:
        type: pytest.CaptureFixture[str]
      mode:
        type: int
      role:
        type: str | None
    """
    ctx = context(runtime)
    first = runtime.test_object(b"First", b"one")
    second = runtime.test_object(b"Second", b"two")
    assert runtime.test_raise(ctx, first, None, 0) == 1
    handler = runtime.irx_exception_handler_enter(ctx)
    assert (
        runtime.test_raise(ctx, second, first if mode == 1 else None, mode)
        == 1
    )
    runtime.irx_exception_handler_leave(ctx, handler)
    runtime.test_release(ctx, first)
    runtime.test_release(ctx, second)
    runtime.irx_exception_report(ctx)
    report = parse_exception_output(capfd.readouterr().err)
    assert report is not None and report.type_name == "Second"
    assert tuple(item.role for item in report.related) == (
        () if role is None else (role,)
    )
    runtime.irx_exception_context_destroy(ctx)
    assert runtime.test_drops() == len((first, second))


@pytest.mark.parametrize("cleanup", [False, True])
def test_finally_replacement_and_cleanup_priority(
    runtime: ctypes.CDLL, capfd: pytest.CaptureFixture[str], cleanup: bool
) -> None:
    """
    title: Finally overrides errors; implicit cleanup preserves the primary.
    parameters:
      runtime:
        type: ctypes.CDLL
      capfd:
        type: pytest.CaptureFixture[str]
      cleanup:
        type: bool
    """
    ctx = context(runtime)
    first = runtime.test_object(b"First", b"one")
    second = runtime.test_object(b"Second", b"two")
    runtime.test_raise(ctx, first, None, 0)
    enter = (
        runtime.irx_exception_cleanup_enter
        if cleanup
        else runtime.irx_exception_finally_enter
    )
    scope = enter(ctx)
    runtime.test_raise(ctx, second, None, 0)
    if cleanup:
        runtime.irx_exception_cleanup_leave(ctx, scope)
    else:
        runtime.irx_exception_finally_leave(ctx, scope, 1)
    runtime.test_release(ctx, first)
    runtime.test_release(ctx, second)
    runtime.irx_exception_report(ctx)
    report = parse_exception_output(capfd.readouterr().err)
    assert report is not None
    assert report.type_name == ("First" if cleanup else "Second")
    assert any(
        item.role == ("cleanup" if cleanup else "context")
        for item in report.related
    )
    runtime.irx_exception_context_destroy(ctx)


@pytest.mark.parametrize("nth", range(1, 10))
def test_allocation_faults_publish_nothing(
    runtime: ctypes.CDLL, nth: int
) -> None:
    """
    title: Every partial constructor fault balances ownership and output slots.
    parameters:
      runtime:
        type: ctypes.CDLL
      nth:
        type: int
    """
    runtime.test_fault(nth)
    result = runtime.test_object(b"Failure", b"message")
    if result:
        runtime.test_release(None, result)
    assert runtime.test_allocated() == 0


def test_repeated_same_object_scopes_are_bounded(runtime: ctypes.CDLL) -> None:
    """
    title: Repeated raise and catch creates neither cycles nor leaked refs.
    parameters:
      runtime:
        type: ctypes.CDLL
    """
    ctx = context(runtime)
    value = runtime.test_object(b"Failure", b"message")
    for _ in range(300):
        assert runtime.test_raise(ctx, value, None, 0) == 1
        scope = runtime.irx_exception_handler_enter(ctx)
        runtime.irx_exception_handler_leave(ctx, scope)
    assert runtime.irx_exception_reraise(ctx) == -1
    runtime.test_release(ctx, value)
    runtime.irx_exception_context_destroy(ctx)
    assert runtime.test_drops() == 1


@pytest.mark.parametrize("nth", range(1, 12))
def test_failed_raise_keeps_original_record_and_references(
    runtime: ctypes.CDLL, nth: int
) -> None:
    """
    title: Failed raises publish neither pending values nor partial snapshots.
    parameters:
      runtime:
        type: ctypes.CDLL
      nth:
        type: int
    """
    ctx = context(runtime)
    value = runtime.test_object(b"Failure", b"message")
    baseline = runtime.test_allocated()
    runtime.test_fault(nth)
    status = runtime.test_raise(ctx, value, None, 0)
    if status == -1:
        assert runtime.irx_exception_pending(ctx) == 0
        assert runtime.test_allocated() == baseline
    else:
        assert status == 1
        assert runtime.irx_exception_pending(ctx) == 1
    runtime.test_fault(0)
    runtime.test_release(ctx, value)
    runtime.irx_exception_context_destroy(ctx)
    assert runtime.test_drops() == 1


def test_failed_consuming_drop_preserves_primary(
    runtime: ctypes.CDLL, capfd: pytest.CaptureFixture[str]
) -> None:
    """
    title: A failing real class drop consumes its owner and stays secondary.
    parameters:
      runtime:
        type: ctypes.CDLL
      capfd:
        type: pytest.CaptureFixture[str]
    """
    ctx = context(runtime)
    primary = runtime.test_object(b"Primary", b"original")
    resource = runtime.test_object(b"Resource", b"resource")
    assert runtime.test_raise(ctx, primary, None, 0) == 1
    scope = runtime.irx_exception_cleanup_enter(ctx)
    runtime.test_drop_fault()
    runtime.test_release(ctx, resource)
    runtime.irx_exception_cleanup_leave(ctx, scope)
    runtime.irx_exception_report(ctx)
    report = parse_exception_output(capfd.readouterr().err)
    assert report is not None and report.type_name == "Primary"
    assert any(
        item.type_name == "DropFailure" and item.role == "cleanup"
        for item in report.related
    )
    runtime.test_release(ctx, primary)
    runtime.irx_exception_context_destroy(ctx)
    expected_drops = 3
    assert runtime.test_drops() == expected_drops


def test_scalar_exception_feature_has_no_arrow_dependency() -> None:
    """
    title: Scalar exceptions activate only ordinary class lifetime support.
    """
    from irx.builder.runtime.exceptions import (  # noqa: PLC0415
        build_exception_runtime_feature,
    )

    feature = build_exception_runtime_feature()
    assert feature.dependencies == ("class",)
    assert feature.linker_flags == ()
    assert all("arrow" not in str(item.path) for item in feature.artifacts)
    assert "irx_exception_raise" in feature.symbols
    assert "irx_exception_cleanup_leave" in feature.symbols
