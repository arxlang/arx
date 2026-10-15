"""
title: Aggregate ownership lowering tests.
summary: >-
  Verify that managed values stored in class objects and generator frames have
  deterministic semantic and native cleanup.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

from pathlib import Path

import astx
import pytest

from irx.analysis import analyze, resource_ownership
from irx.analysis.resolved_nodes import OwnershipKind, ResourceKind
from irx.builder import Builder
from irx.builder.runtime.features import NativeArtifact
from irx.builder.runtime.linking import link_executable
from irx.diagnostics import SemanticError
from llvmlite import binding as llvm

from .conftest import assert_build_succeeds, assert_ir_parses, make_module

HAS_CLANG = shutil.which("clang") is not None
COPIED_CLASS_OWNER_COUNT = 2


@pytest.mark.skipif(
    not HAS_CLANG or sys.platform != "linux",
    reason="allocation accounting needs Clang and GNU linker wrapping",
)
@pytest.mark.parametrize("failure", ["assertion", "division"])
def test_fatal_paths_release_local_string_owners(
    tmp_path: Path, failure: str
) -> None:
    """
    title: Fatal branches release live owners without losing diagnostic bytes.
    parameters:
      tmp_path:
        type: Path
      failure:
        type: str
    """
    body = astx.Block()
    body.append(
        astx.VariableDeclaration(
            "message",
            astx.String(),
            value=astx.BinaryOp(
                "+",
                astx.LiteralString("owned"),
                astx.LiteralString(" message"),
            ),
        )
    )
    if failure == "assertion":
        body.append(
            astx.AssertStmt(
                astx.LiteralBoolean(False), astx.Identifier("message")
            )
        )
    else:
        body.append(
            astx.BinaryOp("/", astx.LiteralInt32(1), astx.LiteralInt32(0))
        )
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    main = astx.FunctionDef(
        astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()), body
    )
    builder = Builder()
    ir_text = builder.translate(make_module("main", main))
    parsed = llvm.parse_assembly(ir_text)
    parsed.verify()
    machine = llvm.Target.from_default_triple().create_target_machine()
    primary = tmp_path / "program.o"
    primary.write_bytes(machine.emit_object(parsed))
    executable = tmp_path / "program"
    link_executable(
        primary,
        executable,
        (
            *builder.translator.runtime_features.native_artifacts(),
            NativeArtifact(
                kind="c_source",
                path=Path(__file__).parent
                / "native"
                / "ownership_accounting.c",
            ),
        ),
        linker_flags=("-Wl,--wrap=malloc", "-Wl,--wrap=free"),
    )
    result = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 1, result.stderr
    if failure == "assertion":
        assert "ARX_ASSERT_FAIL|" in result.stderr
        assert "owned message" in result.stderr
    else:
        assert "ARX-RUNTIME-ARITHMETIC-001" in result.stderr


def _tensor_literal(value: int) -> astx.TensorLiteral:
    """
    title: Build a one-element Int32 tensor literal.
    parameters:
      value:
        type: int
    returns:
      type: astx.TensorLiteral
    """
    return astx.TensorLiteral(
        (astx.LiteralInt32(value),),
        element_type=astx.Int32(),
        shape=(1,),
    )


def _class_field_module(*, replace_field: bool = False) -> astx.Module:
    """
    title: Build a class whose instance owns one Arrow-backed tensor view.
    parameters:
      replace_field:
        type: bool
    returns:
      type: astx.Module
    """
    tensor_type = astx.TensorType(astx.Int32(), shape=(1,))
    field = astx.VariableDeclaration(
        "values",
        tensor_type,
        mutability=astx.MutabilityKind.mutable,
        value=_tensor_literal(7),
    )
    class_node = astx.ClassDefStmt(name="Box", attributes=[field])
    body = astx.Block()
    body.append(
        astx.VariableDeclaration(
            "box",
            astx.ClassType("Box"),
            mutability=astx.MutabilityKind.mutable,
            value=astx.ClassConstruct("Box"),
        )
    )
    if replace_field:
        body.append(
            astx.BinaryOp(
                "=",
                astx.FieldAccess(astx.Identifier("box"), "values"),
                _tensor_literal(8),
            )
        )
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    main = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            "main",
            args=astx.Arguments(),
            return_type=astx.Int32(),
        ),
        body=body,
    )
    return make_module("main", class_node, main)


def test_class_field_owner_has_destructor_contract() -> None:
    """
    title: Managed instance fields should be owned by their class object.
    """
    module = _class_field_module()
    analyze(module)
    class_node = module.nodes[0]
    assert isinstance(class_node, astx.ClassDefStmt)
    field = class_node.attributes[0]
    ownership = resource_ownership(field)

    assert ownership is not None
    assert ownership.kind is OwnershipKind.OWNED
    assert ownership.resource_kind is ResourceKind.BUFFER_VIEW

    ir_text = Builder().translate(module)
    destructor_start = ir_text.index("main__Box__destroy")
    cleanup_start = ir_text.index(
        'call i32 @"irx_buffer_view_release"',
        destructor_start,
    )
    free_start = ir_text.index('call void @"free"', destructor_start)
    assert cleanup_start < free_start
    assert_ir_parses(ir_text)


@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for build tests")
def test_class_field_replacement_and_destruction_execute() -> None:
    """
    title: Replacing and destroying a managed class field should execute.
    """
    assert_build_succeeds(Builder(), _class_field_module(replace_field=True))


def test_class_reference_copy_uses_retain_and_release() -> None:
    """
    title: Copying a class reference should retain before both owners release.
    """
    class_node = astx.ClassDefStmt(name="Box")
    body = astx.Block()
    body.append(
        astx.VariableDeclaration(
            "first",
            astx.ClassType("Box"),
            value=astx.ClassConstruct("Box"),
        )
    )
    body.append(
        astx.VariableDeclaration(
            "second",
            astx.ClassType("Box"),
            value=astx.Identifier("first"),
        )
    )
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    main = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            "main",
            args=astx.Arguments(),
            return_type=astx.Int32(),
        ),
        body=body,
    )
    module = make_module("main", class_node, main)

    ir_text = Builder().translate(module)
    assert 'call i32 @"irx_class_retain"' in ir_text
    assert (
        ir_text.count('call i32 @"irx_class_release"')
        >= COPIED_CLASS_OWNER_COUNT
    )
    assert_ir_parses(ir_text)


def test_owned_string_field_initializer_has_destructor() -> None:
    """
    title: A heap string field receives an owning destructor contract.
    """
    field = astx.VariableDeclaration(
        "text",
        astx.String(),
        value=astx.BinaryOp(
            "+", astx.LiteralString("a"), astx.LiteralString("b")
        ),
    )
    module = make_module(
        "main", astx.ClassDefStmt(name="Text", attributes=[field])
    )
    text = Builder().translate(module)
    assert 'call void @"free"' in text
    assert_ir_parses(text)


@pytest.mark.skipif(
    not HAS_CLANG, reason="clang is required for allocation tests"
)
@pytest.mark.parametrize("aggregate", ["class", "generator"])
def test_aggregate_allocation_failure_reports_instead_of_dereferencing_null(
    aggregate: str,
    tmp_path: Path,
) -> None:
    """
    title: Real malloc failure must take the generated structured failure edge.
    parameters:
      aggregate:
        type: str
      tmp_path:
        type: Path
    """
    if sys.platform != "linux":
        pytest.skip("this failure-injection harness uses GNU linker wrapping")
    body = astx.Block()
    if aggregate == "class":
        definition: astx.AST = astx.ClassDefStmt(name="Box")
        value: astx.AST = astx.ClassConstruct("Box")
        type_: astx.DataType = astx.ClassType("Box")
    else:
        yields = astx.Block()
        yields.append(astx.YieldStmt(astx.LiteralInt32(1)))
        type_ = astx.GeneratorType(astx.Int32())
        definition = astx.FunctionDef(
            astx.FunctionPrototype("values", astx.Arguments(), type_),
            yields,
        )
        value = astx.FunctionCall("values", [])
    body.append(astx.VariableDeclaration("owner", type_, value=value))
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    main = astx.FunctionDef(
        astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
        body,
    )
    builder = Builder()
    ir_text = builder.translate(make_module("main", definition, main))
    parsed = llvm.parse_assembly(ir_text)
    parsed.verify()
    machine = llvm.Target.from_default_triple().create_target_machine()
    primary = tmp_path / "program.o"
    primary.write_bytes(machine.emit_object(parsed))
    shim = tmp_path / "allocation_failure.c"
    shim.write_text(
        "#include <stddef.h>\n"
        "void* __wrap_malloc(size_t n) {(void)n; return NULL;}\n"
    )
    executable = tmp_path / "program"
    link_executable(
        primary,
        executable,
        (
            *builder.translator.runtime_features.native_artifacts(),
            NativeArtifact(kind="c_source", path=shim),
        ),
        linker_flags=("-Wl,--wrap=malloc",),
    )
    result = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 1
    assert "ARX-RUNTIME-ALLOCATION-001" in result.stderr
    assert "allocation failed" in result.stderr


def test_string_field_copies_a_short_lived_local() -> None:
    """
    title: >-
      A field assignment clones borrowed local storage before replacing its
      owner.
    """
    field = astx.VariableDeclaration(
        "text",
        astx.String(),
        mutability=astx.MutabilityKind.mutable,
        value=astx.LiteralString(""),
    )
    body = astx.Block()
    body.append(
        astx.VariableDeclaration(
            "box",
            astx.ClassType("Box"),
            value=astx.ClassConstruct("Box"),
        )
    )
    body.append(
        astx.VariableDeclaration(
            "local",
            astx.String(),
            value=astx.BinaryOp(
                "+",
                astx.LiteralString("a"),
                astx.LiteralString("b"),
            ),
        )
    )
    body.append(
        astx.BinaryOp(
            "=",
            astx.FieldAccess(astx.Identifier("box"), "text"),
            astx.Identifier("local"),
        )
    )
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    main = astx.FunctionDef(
        astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
        body,
    )
    module = make_module(
        "main", astx.ClassDefStmt(name="Box", attributes=[field]), main
    )
    assert_ir_parses(Builder().translate(module))


@pytest.mark.skipif(
    not HAS_CLANG, reason="clang is required for allocation tests"
)
def test_generator_loop_locals_release_each_heap_allocation(
    tmp_path: Path,
) -> None:
    """
    title: Repeated generator loop declarations must not overwrite live owners.
    parameters:
      tmp_path:
        type: Path
    """
    if sys.platform != "linux":
        pytest.skip(
            "this allocation accounting harness uses GNU linker wrapping"
        )

    def block(*nodes: astx.AST) -> astx.Block:
        """
        title: Build one statement block.
        parameters:
          nodes:
            type: astx.AST
            variadic: positional
        returns:
          type: astx.Block
        """
        body = astx.Block()
        for node in nodes:
            body.append(node)
        return body

    counter = astx.Identifier("counter")
    generator = astx.FunctionDef(
        astx.FunctionPrototype(
            "values", astx.Arguments(), astx.GeneratorType(astx.Int32())
        ),
        block(
            astx.VariableDeclaration(
                "counter",
                astx.Int32(),
                value=astx.LiteralInt32(0),
                mutability=astx.MutabilityKind.mutable,
            ),
            astx.WhileStmt(
                astx.BinaryOp("<", counter, astx.LiteralInt32(8)),
                block(
                    astx.VariableDeclaration(
                        "local",
                        astx.String(),
                        value=astx.BinaryOp(
                            "+",
                            astx.LiteralString("owned"),
                            astx.LiteralString(" string"),
                        ),
                    ),
                    astx.VariableAssignment(
                        "counter",
                        astx.BinaryOp(
                            "+",
                            astx.Identifier("counter"),
                            astx.LiteralInt32(1),
                        ),
                    ),
                ),
            ),
            astx.YieldStmt(astx.LiteralInt32(1)),
        ),
    )
    main = astx.FunctionDef(
        astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
        block(
            astx.ForInLoopStmt(
                astx.Identifier("item"),
                astx.FunctionCall("values", []),
                block(),
            ),
            astx.FunctionReturn(astx.LiteralInt32(0)),
        ),
    )
    builder = Builder()
    ir_text = builder.translate(make_module("main", generator, main))
    parsed = llvm.parse_assembly(ir_text)
    parsed.verify()
    machine = llvm.Target.from_default_triple().create_target_machine()
    primary = tmp_path / "program.o"
    primary.write_bytes(machine.emit_object(parsed))
    shim = tmp_path / "allocation_accounting.c"
    shim.write_text(
        "#include <stdlib.h>\n#include <stdio.h>\n"
        "static long live;\n"
        "void* __real_malloc(size_t n);\nvoid __real_free(void* p);\n"
        "void* __wrap_malloc(size_t n) { void* p = __real_malloc(n); "
        "if (p) ++live; return p; }\n"
        "void __wrap_free(void* p) { if (p) --live; __real_free(p); }\n"
        "__attribute__((destructor)) static void check_live(void) { "
        'if (live != 0) { fprintf(stderr, "live owners: %ld\\n", live); '
        "_Exit(99); } }\n"
    )
    executable = tmp_path / "program"
    link_executable(
        primary,
        executable,
        (
            *builder.translator.runtime_features.native_artifacts(),
            NativeArtifact(kind="c_source", path=shim),
        ),
        linker_flags=("-Wl,--wrap=malloc", "-Wl,--wrap=free"),
    )
    result = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("borrowed", [False, True])
def test_unmanaged_list_rejects_dynamic_string_elements(
    borrowed: bool,
) -> None:
    """
    title: List buffers cannot retain string pointers without element cleanup.
    parameters:
      borrowed:
        type: bool
    """
    body = astx.Block()
    body.append(
        astx.VariableDeclaration(
            "text", astx.String(), value=astx.LiteralString("local")
        )
    )
    body.append(
        astx.VariableDeclaration(
            "items",
            astx.ListType([astx.String()]),
            value=astx.ListCreate(astx.String()),
            mutability=astx.MutabilityKind.mutable,
        )
    )
    value = (
        astx.Identifier("text")
        if borrowed
        else astx.BinaryOp(
            "+", astx.LiteralString("owned"), astx.LiteralString(" item")
        )
    )
    body.append(astx.ListAppend(astx.Identifier("items"), value))
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    function = astx.FunctionDef(
        astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()), body
    )
    with pytest.raises(SemanticError, match="element destruction"):
        analyze(make_module("main", function))
