"""
title: Native class ownership ABI and direct ASTx construction contracts.
"""

import ctypes
import shutil
import subprocess

from collections.abc import Iterator
from pathlib import Path

import astx
import pytest

from irx.analysis import SemanticError, analyze
from irx.builder import Builder
from llvmlite import binding as llvm
from typeguard import TypeCheckError

NATIVE = Path(__file__).parents[1] / "src/irx/builder/runtime/classes/native"
DROP = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p)
ERROR_CAPACITY = 256
EXPECTED_FIELD_VALUE = 7


@pytest.fixture
def native(tmp_path: Path) -> Iterator[ctypes.CDLL]:
    """
    title: Compile lifetime code with counted, faultable allocation.
    parameters:
      tmp_path:
        type: Path
    returns:
      type: Iterator[ctypes.CDLL]
    """
    clang = shutil.which("clang")
    if clang is None:
        pytest.skip("native ownership tests require clang")
    source = tmp_path / "runtime.c"
    source.write_text(
        """#include <stdlib.h>
static int allocated = 0, fault = 0, calls = 0;
static void* test_calloc(size_t n, size_t size) {
  void* out;
  if (++calls == fault) return NULL;
  out = calloc(n, size);
  if (out) allocated++;
  return out;
}
static void test_free(void* pointer) {
  if (pointer) allocated--;
  free(pointer);
}
#define calloc test_calloc
#define free test_free
#include "irx_class_runtime.c"
void test_fault(int nth) { fault = nth; calls = 0; }
int test_allocated(void) { return allocated; }
void test_references(void* value, uint64_t n) {
  irx_class_token(value)->references = n;
}
""",
        encoding="utf-8",
    )
    library = tmp_path / "runtime.so"
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
            str(NATIVE),
            str(source),
            "-o",
            str(library),
        ],
        check=True,
    )
    runtime = ctypes.CDLL(str(library))
    runtime.irx_class_create.argtypes = [
        ctypes.c_size_t,
        DROP,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
    ]
    for name in ("retain", "release", "require"):
        getattr(runtime, f"irx_class_{name}").argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
    runtime.irx_class_complete.argtypes = [ctypes.c_void_p]
    runtime.irx_class_completed.argtypes = [ctypes.c_void_p]
    runtime.test_references.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    yield runtime
    assert runtime.test_allocated() == 0


@pytest.mark.parametrize("nth", [1, 2])
def test_failed_creation_initializes_output(
    native: ctypes.CDLL, nth: int
) -> None:
    """
    title: Failed owner/payload allocation never publishes an object.
    parameters:
      native:
        type: ctypes.CDLL
      nth:
        type: int
    """

    @DROP
    def drop(value: int, error: int) -> int:
        """
        title: Reject destructor calls without a constructed payload.
        parameters:
          value:
            type: int
          error:
            type: int
        returns:
          type: int
        """
        pytest.fail("drop called without a payload")

    native.test_fault(nth)
    output = ctypes.c_void_p(123)
    error = ctypes.create_string_buffer(ERROR_CAPACITY)
    assert native.irx_class_create(32, drop, ctypes.byref(output), error) != 0
    assert output.value is None
    assert b"allocation" in error.value


def test_last_release_and_drop_failure(native: ctypes.CDLL) -> None:
    """
    title: Final release consumes all storage even on a callback failure.
    parameters:
      native:
        type: ctypes.CDLL
    """
    calls: list[int] = []
    error = ctypes.create_string_buffer(ERROR_CAPACITY)

    @DROP
    def drop(value: int, details: int) -> int:
        """
        title: Forbid resurrection and preserve the destructor error.
        parameters:
          value:
            type: int
          details:
            type: int
        returns:
          type: int
        """
        calls.append(value)
        assert native.irx_class_retain(value, error) != 0
        ctypes.memmove(details, b"drop failed\0", len(b"drop failed\0"))
        return 1

    output = ctypes.c_void_p()
    assert native.irx_class_create(32, drop, ctypes.byref(output), error) == 0
    assert native.irx_class_completed(output) == 0
    native.irx_class_complete(output)
    assert native.irx_class_completed(output) == 1
    assert native.irx_class_retain(output, error) == 0
    assert native.irx_class_release(output, error) == 0
    assert not calls
    assert native.irx_class_release(output, error) != 0
    assert len(calls) == 1
    assert error.value == b"drop failed"


def test_empty_overflow_and_repeated_lifetimes(native: ctypes.CDLL) -> None:
    """
    title: Empty slots, checked counts, and repeated lifetimes stay balanced.
    parameters:
      native:
        type: ctypes.CDLL
    """

    @DROP
    def drop(value: int, error: int) -> int:
        """
        title: Drop a payload without owned fields.
        parameters:
          value:
            type: int
          error:
            type: int
        returns:
          type: int
        """
        return 0

    error = ctypes.create_string_buffer(ERROR_CAPACITY)
    assert native.irx_class_retain(None, error) == 0
    assert native.irx_class_release(None, error) == 0
    assert native.irx_class_require(None, error) != 0
    for _ in range(200):
        output = ctypes.c_void_p()
        assert (
            native.irx_class_create(32, drop, ctypes.byref(output), error) == 0
        )
        native.test_references(output, 2**64 - 1)
        assert native.irx_class_retain(output, error) != 0
        native.test_references(output, 1)
        assert native.irx_class_release(output, error) == 0


def test_constructor_model_runtime_checks() -> None:
    """
    title: Preserve the old construction API and check every argument item.
    """
    assert str(astx.ClassConstruct("Counter")) == "ClassConstruct[Counter]"
    with pytest.raises(TypeCheckError):
        astx.ClassConstruct("Counter", (astx.LiteralInt32(1), "bad"))  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        astx.ClassConstruct("Counter", keywords=("bad",))  # type: ignore[arg-type]
    class_ = astx.ClassDefStmt("Counter")
    call = astx.ClassConstruct("Counter")
    body = astx.Block()
    body.append(call)
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module = astx.Module("main")
    module.block.append(class_)
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
            body,
        )
    )
    text = Builder().translate(module)
    llvm.parse_assembly(text).verify()
    assert "irx_class_create" in text and "irx_class_release" in text
    call.keywords = (astx.KeywordArgument("other", astx.LiteralInt32(1)),)
    with pytest.raises(SemanticError, match="unknown constructor"):
        analyze(module)


def test_reanalysis_clears_class_parameter_ownership() -> None:
    """
    title: >-
      Reanalyzing an edited parameter never retains obsolete class metadata.
    """
    argument = astx.Argument("value", astx.ClassType("Counter"))
    body = astx.Block()
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module = astx.Module("main")
    module.block.append(astx.ClassDefStmt("Counter"))
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype(
                "take", astx.Arguments(argument), astx.Int32()
            ),
            body,
        )
    )
    analyze(module)
    argument.type_ = astx.Int32()
    text = Builder().translate(module)
    llvm.parse_assembly(text).verify()
    assert "irx_class_retain" not in text


@pytest.mark.parametrize("continue_loop", [False, True])
def test_class_cleanup_on_loop_transfer(continue_loop: bool) -> None:
    """
    title: Direct ASTx break and continue release each active iteration owner.
    parameters:
      continue_loop:
        type: bool
    """
    from .conftest import jit_int_main  # noqa: PLC0415

    drops = astx.VariableDeclaration(
        "drops",
        astx.Int32(),
        value=astx.LiteralInt32(0),
        mutability=astx.MutabilityKind.mutable,
    )
    drops.is_static = True
    destructor_body = astx.Block()
    destructor_body.append(
        astx.BinaryOp(
            "=",
            astx.StaticFieldAccess("Counter", "drops"),
            astx.BinaryOp(
                "+",
                astx.StaticFieldAccess("Counter", "drops"),
                astx.LiteralInt32(1),
            ),
        )
    )
    destructor_body.append(astx.FunctionReturn(astx.LiteralNone()))
    class_ = astx.ClassDefStmt(
        "Counter",
        attributes=[drops],
        methods=[
            astx.FunctionDef(
                astx.FunctionPrototype(
                    "__del__", astx.Arguments(), astx.NoneType()
                ),
                destructor_body,
            )
        ],
    )
    loop_body = astx.Block()
    loop_body.append(
        astx.VariableDeclaration(
            "value",
            astx.ClassType("Counter"),
            value=astx.ClassConstruct("Counter"),
        )
    )
    loop_body.append(
        astx.BinaryOp(
            "=",
            astx.Identifier("index"),
            astx.BinaryOp("+", astx.Identifier("index"), astx.LiteralInt32(1)),
        )
    )
    loop_body.append(
        astx.ContinueStmt() if continue_loop else astx.BreakStmt()
    )
    body = astx.Block()
    body.append(
        astx.VariableDeclaration(
            "index",
            astx.Int32(),
            value=astx.LiteralInt32(0),
            mutability=astx.MutabilityKind.mutable,
        )
    )
    body.append(
        astx.WhileStmt(
            astx.BinaryOp("<", astx.Identifier("index"), astx.LiteralInt32(3)),
            loop_body,
        )
    )
    body.append(
        astx.FunctionReturn(astx.StaticFieldAccess("Counter", "drops"))
    )
    module = astx.Module("main")
    module.block.append(class_)
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
            body,
        )
    )
    assert jit_int_main(Builder(), module) == (3 if continue_loop else 1)


def test_hook_constructs_later_declared_class() -> None:
    """
    title: Direct ASTx hooks can construct a later declared class.
    """
    from .conftest import jit_int_main  # noqa: PLC0415

    init_body = astx.Block()
    init_body.append(
        astx.BinaryOp(
            "=",
            astx.FieldAccess(astx.Identifier("self"), "child"),
            astx.ClassConstruct("Leaf"),
        )
    )
    init_body.append(astx.FunctionReturn(astx.LiteralNone()))
    holder = astx.ClassDefStmt(
        "Holder",
        attributes=[
            astx.VariableDeclaration(
                "child",
                astx.ClassType("Leaf"),
                mutability=astx.MutabilityKind.mutable,
            )
        ],
        methods=[
            astx.FunctionDef(
                astx.FunctionPrototype(
                    "__init__", astx.Arguments(), astx.NoneType()
                ),
                init_body,
            )
        ],
    )
    read_body = astx.Block()
    read_body.append(
        astx.FunctionReturn(astx.FieldAccess(astx.Identifier("self"), "value"))
    )
    leaf = astx.ClassDefStmt(
        "Leaf",
        attributes=[
            astx.VariableDeclaration(
                "value", astx.Int32(), value=astx.LiteralInt32(7)
            )
        ],
        methods=[
            astx.FunctionDef(
                astx.FunctionPrototype("read", astx.Arguments(), astx.Int32()),
                read_body,
            )
        ],
    )
    body = astx.Block()
    body.append(
        astx.VariableDeclaration(
            "holder",
            astx.ClassType("Holder"),
            value=astx.ClassConstruct("Holder"),
        )
    )
    body.append(
        astx.FunctionReturn(
            astx.MethodCall(
                astx.FieldAccess(astx.Identifier("holder"), "child"),
                "read",
                [],
            )
        )
    )
    module = astx.Module("main")
    for node in (
        holder,
        leaf,
        astx.FunctionDef(
            astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
            body,
        ),
    ):
        module.block.append(node)
    assert jit_int_main(Builder(), module) == EXPECTED_FIELD_VALUE


def test_class_list_creation_is_rejected_without_a_declaration() -> None:
    """
    title: Direct ASTx aggregate creation cannot bypass declared-type checks.
    """
    body = astx.Block()
    body.append(astx.ListCreate(astx.ClassType("Counter")))
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module = astx.Module("main")
    module.block.append(astx.ClassDefStmt("Counter"))
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
            body,
        )
    )
    with pytest.raises(
        SemanticError, match="class references inside containers"
    ):
        analyze(module)


@pytest.mark.parametrize("encoding", ["generic", "utf8"])
def test_repeated_string_field_initializer(encoding: str) -> None:
    """
    title: Reused initializer nodes cannot duplicate LLVM literal global names.
    parameters:
      encoding:
        type: str
    """
    literal = (
        astx.LiteralString("same")
        if encoding == "generic"
        else astx.LiteralUTF8String("same")
    )
    class_ = astx.ClassDefStmt(
        "Tag",
        attributes=[
            astx.VariableDeclaration("label", literal.type_, value=literal)
        ],
    )
    body = astx.Block()
    body.append(astx.ClassConstruct("Tag"))
    body.append(astx.ClassConstruct("Tag"))
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module = astx.Module("main")
    module.block.append(class_)
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
            body,
        )
    )
    text = Builder().translate(module)
    llvm.parse_assembly(text).verify()
