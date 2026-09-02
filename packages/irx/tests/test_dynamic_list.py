"""
title: Dynamic-list construction and indexing tests.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from pathlib import Path

import astx
import irx.builder.runtime.list.feature as list_runtime_feature
import pytest

from irx.analysis import (
    OwnershipEscapeKind,
    OwnershipKind,
    OwnershipTransferKind,
    SemanticError,
    analyze,
    resource_ownership,
)
from irx.builder import Builder
from irx.builder.base import CommandResult

from .conftest import (
    assert_ir_parses,
    assert_jit_int_main_result,
    workspace_tmpdir_env,
)

HAS_CLANG = shutil.which("clang") is not None
HAS_LITERAL_LIST = hasattr(astx, "LiteralList")
EXPECTED_LIST_AT_CALLS = 3
EXPECTED_REPLACEMENT_DESTROYS = 2


def _list_i32_type() -> astx.ListType:
    """
    title: Return the canonical list[Int32] test type.
    returns:
      type: astx.ListType
    """
    return astx.ListType([astx.Int32()])


def _mutable_decl(
    name: str,
    type_: astx.DataType,
    value: astx.AST,
) -> astx.VariableDeclaration:
    """
    title: Build one mutable local variable declaration.
    parameters:
      name:
        type: str
      type_:
        type: astx.DataType
      value:
        type: astx.AST
    returns:
      type: astx.VariableDeclaration
    """
    return astx.VariableDeclaration(
        name=name,
        type_=type_,
        mutability=astx.MutabilityKind.mutable,
        value=value,
    )


def _index(base: astx.AST, index: int) -> astx.SubscriptExpr:
    """
    title: Build one integer list index expression.
    parameters:
      base:
        type: astx.AST
      index:
        type: int
    returns:
      type: astx.SubscriptExpr
    """
    return astx.SubscriptExpr(base, astx.LiteralInt32(index))


def _module_with_main(*nodes: astx.AST) -> astx.Module:
    """
    title: Build one int32 main module from the provided nodes.
    parameters:
      nodes:
        type: astx.AST
        variadic: positional
    returns:
      type: astx.Module
    """
    module = astx.Module()
    main = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            "main",
            args=astx.Arguments(),
            return_type=astx.Int32(),
        ),
        body=astx.Block(),
    )
    for node in nodes:
        main.body.append(node)
    if not any(isinstance(node, astx.FunctionReturn) for node in nodes):
        main.body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module.block.append(main)
    return module


def _run_workspace_build(
    builder: Builder,
    module: astx.Module,
) -> CommandResult:
    """
    title: Build and run one module using a workspace-local temporary path.
    parameters:
      builder:
        type: Builder
      module:
        type: astx.Module
    returns:
      type: CommandResult
    """
    output_path = ""
    with workspace_tmpdir_env() as temp_root:
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".exe",
                prefix="irx_dynamic_list_",
                dir=temp_root,
                delete=False,
            ) as handle:
                output_path = handle.name

            builder.build(module, output_file=output_path)
            return builder.run(raise_on_error=False)
        finally:
            if output_path and os.path.exists(output_path):
                os.unlink(output_path)


def _assert_workspace_build_output(
    builder: Builder,
    module: astx.Module,
    expected_output: str,
) -> None:
    """
    title: Build and run one module using a workspace-local temporary path.
    parameters:
      builder:
        type: Builder
      module:
        type: astx.Module
      expected_output:
        type: str
    """
    result = _run_workspace_build(builder, module)
    actual_output = result.stdout.strip() or str(result.returncode)
    assert actual_output == expected_output, (
        f"Expected `{expected_output}`, but got `{actual_output}` "
        f"(stderr={result.stderr.strip()!r})"
    )


def _singleton_module() -> astx.Module:
    """
    title: Build one module that appends a variable value into a list.
    returns:
      type: astx.Module
    """
    list_type = _list_i32_type()
    module = astx.Module()

    singleton = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            "singleton",
            args=astx.Arguments(astx.Argument("value", astx.Int32())),
            return_type=list_type,
        ),
        body=astx.Block(),
    )
    singleton.body.append(
        _mutable_decl(
            "out",
            list_type,
            astx.ListCreate(astx.Int32()),
        )
    )
    singleton.body.append(
        astx.ListAppend(astx.Identifier("out"), astx.Identifier("value"))
    )
    singleton.body.append(astx.FunctionReturn(astx.Identifier("out")))
    module.block.append(singleton)

    main = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            "main",
            args=astx.Arguments(),
            return_type=astx.Int32(),
        ),
        body=astx.Block(),
    )
    main.body.append(
        _mutable_decl(
            "vals",
            list_type,
            astx.FunctionCall("singleton", [astx.LiteralInt32(7)]),
        )
    )
    main.body.append(
        _mutable_decl(
            "first", astx.Int32(), _index(astx.Identifier("vals"), 0)
        )
    )
    main.body.append(astx.FunctionReturn(astx.Identifier("first")))
    module.block.append(main)
    return module


def _loop_module() -> astx.Module:
    """
    title: Build one module that appends into a list inside a while loop.
    returns:
      type: astx.Module
    """
    list_type = _list_i32_type()
    module = astx.Module()

    make_list = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            "make_list",
            args=astx.Arguments(),
            return_type=list_type,
        ),
        body=astx.Block(),
    )
    make_list.body.append(
        _mutable_decl("out", list_type, astx.ListCreate(astx.Int32()))
    )
    make_list.body.append(
        _mutable_decl("current", astx.Int32(), astx.LiteralInt32(1))
    )

    loop_body = astx.Block()
    loop_body.append(
        astx.ListAppend(astx.Identifier("out"), astx.Identifier("current"))
    )
    loop_body.append(
        astx.VariableAssignment(
            "current",
            astx.BinaryOp(
                "+",
                astx.Identifier("current"),
                astx.LiteralInt32(1),
            ),
        )
    )
    make_list.body.append(
        astx.WhileStmt(
            astx.BinaryOp(
                "<",
                astx.Identifier("current"),
                astx.LiteralInt32(4),
            ),
            loop_body,
        )
    )
    make_list.body.append(astx.FunctionReturn(astx.Identifier("out")))
    module.block.append(make_list)

    main = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            "main",
            args=astx.Arguments(),
            return_type=astx.Int32(),
        ),
        body=astx.Block(),
    )
    main.body.append(
        _mutable_decl(
            "vals",
            list_type,
            astx.FunctionCall("make_list", []),
        )
    )
    main.body.append(
        _mutable_decl(
            "first", astx.Int32(), _index(astx.Identifier("vals"), 0)
        )
    )
    main.body.append(
        _mutable_decl(
            "second",
            astx.Int32(),
            _index(astx.Identifier("vals"), 1),
        )
    )
    main.body.append(
        _mutable_decl(
            "third", astx.Int32(), _index(astx.Identifier("vals"), 2)
        )
    )
    sum_expr = astx.BinaryOp(
        "+",
        astx.Identifier("first"),
        astx.BinaryOp(
            "+",
            astx.Identifier("second"),
            astx.Identifier("third"),
        ),
    )
    main.body.append(astx.FunctionReturn(sum_expr))
    module.block.append(main)
    return module


def _uninitialized_local_module() -> astx.Module:
    """
    title: >-
      Build one module that appends after an uninitialized list declaration.
    returns:
      type: astx.Module
    """
    list_type = _list_i32_type()
    module = astx.Module()

    main = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            "main",
            args=astx.Arguments(),
            return_type=astx.Int32(),
        ),
        body=astx.Block(),
    )
    main.body.append(
        astx.VariableDeclaration(
            name="out",
            type_=list_type,
            mutability=astx.MutabilityKind.mutable,
        )
    )
    main.body.append(
        astx.ListAppend(astx.Identifier("out"), astx.LiteralInt32(11))
    )
    main.body.append(
        _mutable_decl(
            "first",
            astx.Int32(),
            _index(astx.Identifier("out"), 0),
        )
    )
    main.body.append(astx.FunctionReturn(astx.Identifier("first")))
    module.block.append(main)
    return module


def _direct_list_node_module() -> astx.Module:
    """
    title: Build one module that exercises the direct list helper nodes.
    returns:
      type: astx.Module
    """
    list_type = _list_i32_type()
    return _module_with_main(
        _mutable_decl("out", list_type, astx.ListCreate(astx.Int32())),
        _mutable_decl(
            "status",
            astx.Int32(),
            astx.ListAppend(astx.Identifier("out"), astx.LiteralInt32(11)),
        ),
        _mutable_decl(
            "first",
            astx.Int32(),
            astx.ListIndex(astx.Identifier("out"), astx.LiteralInt32(0)),
        ),
        _mutable_decl(
            "length",
            astx.Int32(),
            astx.ListLength(astx.Identifier("out")),
        ),
        astx.FunctionReturn(
            astx.BinaryOp(
                "+",
                astx.Identifier("status"),
                astx.BinaryOp(
                    "+",
                    astx.Identifier("first"),
                    astx.Identifier("length"),
                ),
            )
        ),
    )


def _literal_list_dynamic_index_module(index: astx.AST) -> astx.Module:
    """
    title: Build one module that indexes one literal list through one variable.
    parameters:
      index:
        type: astx.AST
    returns:
      type: astx.Module
    """
    return _module_with_main(
        _mutable_decl("index", astx.Int32(), index),
        astx.FunctionReturn(
            astx.ListIndex(
                astx.LiteralList(
                    elements=[
                        astx.LiteralInt32(10),
                        astx.LiteralInt32(20),
                        astx.LiteralInt32(30),
                    ]
                ),
                astx.Identifier("index"),
            )
        ),
    )


def test_dynamic_list_appends_variable_values() -> None:
    """
    title: Dynamic list creation should accept appended variable values.
    """
    builder = Builder()
    ir_text = builder.translate(_singleton_module())

    assert 'call i32 @"irx_list_append"' in ir_text
    assert 'call void @"irx_list_require_ok"' in ir_text
    assert 'call i8* @"irx_list_at"' in ir_text
    assert_ir_parses(ir_text)


@pytest.mark.skipif(
    not HAS_CLANG,
    reason="clang is required for runtime tests",
)
def test_dynamic_list_native_status_and_destroy_are_safe(
    tmp_path: Path,
) -> None:
    """
    title: Native list append statuses and repeated destruction are defined.
    parameters:
      tmp_path:
        type: Path
    """
    native_dir = Path(list_runtime_feature.__file__).parent / "native"
    program = tmp_path / "list_runtime_test.c"
    executable = tmp_path / "list_runtime_test"
    program.write_text(
        '#include "irx_list_runtime.h"\n'
        "int main(void) {\n"
        "  irx_list list = {0};\n"
        "  int32_t value = 7;\n"
        "  list.element_size = sizeof(value);\n"
        "  if (irx_list_append(0, &value) != "
        "IRX_LIST_INVALID_ARGUMENT) return 1;\n"
        "  if (irx_list_append(&list, &value) != IRX_LIST_OK) return 2;\n"
        "  if (list.length != 1 || list.data == 0) return 3;\n"
        "  irx_list_destroy(&list);\n"
        "  irx_list_destroy(&list);\n"
        "  if (list.data != 0 || list.length != 0 || "
        "list.capacity != 0) return 4;\n"
        "  return 0;\n"
        "}\n",
        encoding="utf-8",
    )
    compile_result = subprocess.run(
        [
            "clang",
            "-std=c99",
            "-I",
            str(native_dir),
            str(program),
            str(native_dir / "irx_list_runtime.c"),
            "-o",
            str(executable),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    run_result = subprocess.run(
        [str(executable)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert run_result.returncode == 0, run_result.stderr


def test_direct_list_length_from_temporary_list_create() -> None:
    """
    title: Direct list length should work for a non-lvalue ListCreate node.
    """
    builder = Builder()
    module = _module_with_main(
        astx.FunctionReturn(astx.ListLength(astx.ListCreate(astx.Int32())))
    )
    ir_text = builder.translate(module)

    assert "irx_list_length_i32" in ir_text
    assert 'call i32 @"irx_list_append"' not in ir_text
    assert 'call i8* @"irx_list_at"' not in ir_text
    assert_ir_parses(ir_text)

    EXPECTED_EMPTY_LENGTH = 0
    assert_jit_int_main_result(builder, module, EXPECTED_EMPTY_LENGTH)


@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for build tests")
def test_direct_list_nodes_build_and_return() -> None:
    """
    title: Direct list helper nodes should build, lower, and execute cleanly.
    """
    builder = Builder()
    module = _direct_list_node_module()
    ir_text = builder.translate(module)

    assert 'call i32 @"irx_list_append"' in ir_text
    assert 'call i8* @"irx_list_at"' in ir_text
    assert "irx_list_length_i32" in ir_text
    assert "list" in builder.translator.runtime_features.active_feature_names()
    assert_ir_parses(ir_text)

    EXPECTED_DIRECT_NODE_RESULT = 12
    _assert_workspace_build_output(
        builder, module, str(EXPECTED_DIRECT_NODE_RESULT)
    )


@pytest.mark.skipif(
    not HAS_LITERAL_LIST,
    reason="astx.LiteralList not available",
)
def test_direct_list_length_from_literal_list_returns_constant() -> None:
    """
    title: Direct list length should lower LiteralList bases as constants.
    """
    builder = Builder()
    module = _module_with_main(
        astx.FunctionReturn(
            astx.ListLength(
                astx.LiteralList(
                    elements=[
                        astx.LiteralInt32(2),
                        astx.LiteralInt32(4),
                        astx.LiteralInt32(8),
                    ]
                )
            )
        )
    )
    ir_text = builder.translate(module)

    assert "irx_list_length_i32" not in ir_text
    assert 'call i32 @"irx_list_append"' not in ir_text
    assert 'call i8* @"irx_list_at"' not in ir_text
    assert_ir_parses(ir_text)

    EXPECTED_LITERAL_LENGTH = 3
    assert_jit_int_main_result(builder, module, EXPECTED_LITERAL_LENGTH)


@pytest.mark.skipif(
    not HAS_LITERAL_LIST,
    reason="astx.LiteralList not available",
)
def test_direct_list_index_from_literal_list() -> None:
    """
    title: >-
      Direct list index should lower LiteralList bases without runtime calls.
    """
    builder = Builder()
    module = _module_with_main(
        astx.FunctionReturn(
            astx.ListIndex(
                astx.LiteralList(
                    elements=[
                        astx.LiteralInt32(10),
                        astx.LiteralInt32(20),
                        astx.LiteralInt32(30),
                    ]
                ),
                astx.LiteralInt32(1),
            )
        )
    )
    ir_text = builder.translate(module)

    assert "literal_list_index_load" in ir_text
    assert 'call i8* @"irx_list_at"' not in ir_text
    assert_ir_parses(ir_text)

    EXPECTED_LITERAL_INDEX = 20
    assert_jit_int_main_result(builder, module, EXPECTED_LITERAL_INDEX)


@pytest.mark.skipif(
    not HAS_LITERAL_LIST or not HAS_CLANG,
    reason="LiteralList and clang are required for build tests",
)
def test_direct_list_index_from_literal_list_dynamic_index_uses_runtime() -> (
    None
):
    """
    title: Dynamic literal-list indices should use the checked runtime path.
    """
    builder = Builder()
    module = _literal_list_dynamic_index_module(astx.LiteralInt32(1))
    ir_text = builder.translate(module)

    assert 'call i8* @"irx_list_at"' in ir_text
    assert_ir_parses(ir_text)

    EXPECTED_LITERAL_INDEX = 20
    _assert_workspace_build_output(
        builder, module, str(EXPECTED_LITERAL_INDEX)
    )


@pytest.mark.skipif(
    not HAS_LITERAL_LIST or not HAS_CLANG,
    reason="LiteralList and clang are required for build tests",
)
def test_direct_list_index_from_literal_list_dynamic_index_checks_bounds() -> (
    None
):
    """
    title: Dynamic literal-list indices should preserve runtime bounds errors.
    """
    builder = Builder()
    module = _literal_list_dynamic_index_module(astx.LiteralInt32(99))
    ir_text = builder.translate(module)

    assert 'call i8* @"irx_list_at"' in ir_text
    assert_ir_parses(ir_text)

    result = _run_workspace_build(builder, module)

    assert result.returncode == 1
    assert "dynamic list index out of range" in result.stderr


@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for build tests")
def test_dynamic_list_loop_build_and_return() -> None:
    """
    title: A function should append in a loop, return the list, and index it.
    """
    builder = Builder()
    module = _loop_module()
    ir_text = builder.translate(module)

    assert 'call i32 @"irx_list_append"' in ir_text
    assert ir_text.count('call i8* @"irx_list_at"') >= EXPECTED_LIST_AT_CALLS
    assert_ir_parses(ir_text)

    EXPECTED_LOOP_SUM = 6
    _assert_workspace_build_output(builder, module, str(EXPECTED_LOOP_SUM))


@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for build tests")
def test_dynamic_list_uninitialized_local_build_and_append() -> None:
    """
    title: Uninitialized mutable list locals should still append correctly.
    """
    builder = Builder()
    module = _uninitialized_local_module()
    ir_text = builder.translate(module)

    assert 'call i32 @"irx_list_append"' in ir_text
    assert 'call i8* @"irx_list_at"' in ir_text
    assert_ir_parses(ir_text)

    EXPECTED_FIRST_VALUE = 11
    _assert_workspace_build_output(builder, module, str(EXPECTED_FIRST_VALUE))


def test_dynamic_list_append_rejects_type_mismatch() -> None:
    """
    title: Dynamic list append should reject incompatible element values.
    """
    list_type = _list_i32_type()
    module = astx.Module()
    main = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            "main",
            args=astx.Arguments(),
            return_type=astx.Int32(),
        ),
        body=astx.Block(),
    )
    main.body.append(
        _mutable_decl("out", list_type, astx.ListCreate(astx.Int32()))
    )
    main.body.append(
        astx.ListAppend(astx.Identifier("out"), astx.LiteralFloat32(1.5))
    )
    main.body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module.block.append(main)

    with pytest.raises(SemanticError, match="cannot assign Float32"):
        Builder().translate(module)


def test_direct_list_append_rejects_non_lvalue_target() -> None:
    """
    title: >-
      Direct list append should require a mutable variable or field target.
    """
    module = _module_with_main(
        astx.FunctionReturn(
            astx.ListAppend(
                astx.ListCreate(astx.Int32()),
                astx.LiteralInt32(1),
            )
        )
    )

    with pytest.raises(
        SemanticError,
        match="list append target must be a variable or field",
    ):
        analyze(module)


def test_direct_list_index_rejects_non_list_base() -> None:
    """
    title: Direct list index should require a list-valued base expression.
    """
    module = _module_with_main(
        astx.FunctionReturn(
            astx.ListIndex(astx.LiteralInt32(1), astx.LiteralInt32(0))
        )
    )

    with pytest.raises(
        SemanticError,
        match="list indexing requires a list value",
    ):
        analyze(module)


def test_direct_list_index_rejects_non_integer_index() -> None:
    """
    title: Direct list index should require an integer index expression.
    """
    list_type = _list_i32_type()
    module = _module_with_main(
        _mutable_decl("out", list_type, astx.ListCreate(astx.Int32())),
        astx.ListAppend(astx.Identifier("out"), astx.LiteralInt32(7)),
        astx.FunctionReturn(
            astx.ListIndex(
                astx.Identifier("out"),
                astx.LiteralFloat32(0.0),
            )
        ),
    )

    with pytest.raises(
        SemanticError,
        match="list indexing requires an integer index",
    ):
        analyze(module)


def test_direct_list_length_rejects_non_list_base() -> None:
    """
    title: Direct list length should require a list-valued base expression.
    """
    module = _module_with_main(
        astx.FunctionReturn(astx.ListLength(astx.LiteralInt32(1)))
    )

    with pytest.raises(
        SemanticError,
        match="list length requires a list value",
    ):
        analyze(module)


def test_list_ownership_sidecars_track_local_and_return_moves() -> None:
    """
    title: List ownership should track local moves and return escapes.
    """
    module = _singleton_module()
    analyze(module)

    singleton = module.block[0]
    main = module.block[1]
    assert isinstance(singleton, astx.FunctionDef)
    assert isinstance(main, astx.FunctionDef)

    out_decl = singleton.body.nodes[0]
    return_node = singleton.body.nodes[2]
    vals_decl = main.body.nodes[0]
    assert isinstance(out_decl, astx.VariableDeclaration)
    assert isinstance(return_node, astx.FunctionReturn)
    assert isinstance(return_node.value, astx.Identifier)
    assert isinstance(vals_decl, astx.VariableDeclaration)
    assert out_decl.value is not None
    assert vals_decl.value is not None

    out_ownership = resource_ownership(out_decl)
    initializer_ownership = resource_ownership(out_decl.value)
    returned_value_ownership = resource_ownership(return_node.value)
    return_ownership = resource_ownership(return_node)
    vals_ownership = resource_ownership(vals_decl)
    call_ownership = resource_ownership(vals_decl.value)

    assert out_ownership is not None
    assert out_ownership.kind is OwnershipKind.OWNED
    assert out_ownership.owner_symbol_id is not None
    assert initializer_ownership is not None
    assert initializer_ownership.transfer_kind is OwnershipTransferKind.MOVE
    assert initializer_ownership.owner_symbol_id == (
        out_ownership.owner_symbol_id
    )
    assert returned_value_ownership is not None
    assert returned_value_ownership.kind is OwnershipKind.OWNED
    assert returned_value_ownership.transfer_kind is (
        OwnershipTransferKind.MOVE
    )
    assert returned_value_ownership.escape_kind is OwnershipEscapeKind.RETURN
    assert returned_value_ownership.source_symbol_id == (
        out_ownership.owner_symbol_id
    )
    assert return_ownership is not None
    assert return_ownership.source_symbol_id == out_ownership.owner_symbol_id
    assert vals_ownership is not None
    assert vals_ownership.kind is OwnershipKind.OWNED
    assert call_ownership is not None
    assert call_ownership.transfer_kind is OwnershipTransferKind.MOVE
    assert call_ownership.owner_symbol_id == vals_ownership.owner_symbol_id


def test_list_return_rejects_borrowed_parameter() -> None:
    """
    title: A borrowed list parameter must not escape as an owned result.
    """
    list_type = _list_i32_type()
    module = astx.Module()
    identity = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            "identity",
            args=astx.Arguments(astx.Argument("values", list_type)),
            return_type=list_type,
        ),
        body=astx.Block(),
    )
    identity.body.append(astx.FunctionReturn(astx.Identifier("values")))
    module.block.append(identity)

    with pytest.raises(
        SemanticError,
        match="cannot return a borrowed list as an owned result",
    ):
        analyze(module)


def test_list_call_argument_sidecar_records_borrow_and_escape() -> None:
    """
    title: A list call argument should borrow its local owner for the call.
    """
    list_type = _list_i32_type()
    module = astx.Module()
    consume = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            "consume",
            args=astx.Arguments(astx.Argument("values", list_type)),
            return_type=astx.Int32(),
        ),
        body=astx.Block(),
    )
    consume.body.append(
        astx.FunctionReturn(astx.ListLength(astx.Identifier("values")))
    )
    module.block.append(consume)

    values_decl = _mutable_decl(
        "values",
        list_type,
        astx.ListCreate(astx.Int32()),
    )
    call_argument = astx.Identifier("values")
    main = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            "main",
            args=astx.Arguments(),
            return_type=astx.Int32(),
        ),
        body=astx.Block(),
    )
    main.body.append(values_decl)
    main.body.append(
        astx.FunctionReturn(astx.FunctionCall("consume", [call_argument]))
    )
    module.block.append(main)

    analyze(module)

    declaration_ownership = resource_ownership(values_decl)
    argument_ownership = resource_ownership(call_argument)
    assert declaration_ownership is not None
    assert argument_ownership is not None
    assert argument_ownership.kind is OwnershipKind.BORROWED
    assert argument_ownership.transfer_kind is OwnershipTransferKind.BORROW
    assert argument_ownership.escape_kind is OwnershipEscapeKind.CALL
    assert argument_ownership.owner_symbol_id == (
        declaration_ownership.owner_symbol_id
    )


def test_list_local_rejects_borrowed_storage_copy() -> None:
    """
    title: A local list binding must not copy another local's storage.
    """
    list_type = _list_i32_type()
    module = _module_with_main(
        _mutable_decl("first", list_type, astx.ListCreate(astx.Int32())),
        _mutable_decl("copy", list_type, astx.Identifier("first")),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )

    with pytest.raises(
        SemanticError,
        match="would copy borrowed storage",
    ):
        analyze(module)


def test_list_local_rejects_static_literal_storage() -> None:
    """
    title: A dynamic list local must not own static literal storage.
    """
    module = _module_with_main(
        _mutable_decl(
            "values",
            _list_i32_type(),
            astx.LiteralList(elements=[astx.LiteralInt32(1)]),
        ),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )

    with pytest.raises(
        SemanticError,
        match="static list storage cannot initialize dynamic list local",
    ):
        analyze(module)


def test_list_call_rejects_static_literal_argument() -> None:
    """
    title: A static literal list must not cross the dynamic-list call ABI.
    """
    list_type = _list_i32_type()
    module = astx.Module()
    consume = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            "consume",
            args=astx.Arguments(astx.Argument("values", list_type)),
            return_type=astx.Int32(),
        ),
        body=astx.Block(),
    )
    consume.body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module.block.append(consume)
    module.block.append(
        _module_with_main(
            astx.FunctionReturn(
                astx.FunctionCall(
                    "consume",
                    [astx.LiteralList(elements=[astx.LiteralInt32(1)])],
                )
            )
        ).block[0]
    )

    with pytest.raises(
        SemanticError,
        match="static list storage cannot cross a function-call boundary",
    ):
        analyze(module)


def test_list_parameter_rejects_static_literal_default() -> None:
    """
    title: A list parameter must not expose a static literal ABI default.
    """
    list_type = _list_i32_type()
    module = astx.Module()
    function = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            "defaulted",
            args=astx.Arguments(
                astx.Argument(
                    "values",
                    list_type,
                    default=astx.LiteralList(elements=[astx.LiteralInt32(1)]),
                )
            ),
            return_type=astx.Int32(),
        ),
        body=astx.Block(),
    )
    function.body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module.block.append(function)

    with pytest.raises(
        SemanticError,
        match="static list storage cannot be used as a list default",
    ):
        analyze(module)


def test_list_append_rejects_borrowed_parameter_storage() -> None:
    """
    title: List append must reject storage borrowed through a parameter.
    """
    list_type = _list_i32_type()
    module = astx.Module()
    append_borrowed = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            "append_borrowed",
            args=astx.Arguments(astx.Argument("values", list_type)),
            return_type=astx.Int32(),
        ),
        body=astx.Block(),
    )
    append_borrowed.body.append(
        astx.ListAppend(
            astx.Identifier("values"),
            astx.LiteralInt32(1),
        )
    )
    append_borrowed.body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module.block.append(append_borrowed)

    with pytest.raises(
        SemanticError,
        match="list append requires locally owned dynamic storage",
    ):
        analyze(module)


def test_list_lowering_cleans_owned_locals_but_moves_returned_storage() -> (
    None
):
    """
    title: Lowering should clean the caller local but move the callee result.
    """
    ir_text = Builder().translate(_singleton_module())

    singleton_ir, main_ir = ir_text.split('define i32 @"main"()', maxsplit=1)
    assert (
        'call void @"irx_list_destroy"'
        not in singleton_ir.split(
            'define {i8*, i64, i64, i64} @"main__singleton"',
            maxsplit=1,
        )[1]
    )
    assert main_ir.count('call void @"irx_list_destroy"') == 1
    assert main_ir.index('call void @"irx_list_destroy"') < main_ir.index(
        "ret i32"
    )
    assert_ir_parses(ir_text)


def test_list_assignment_destroys_replaced_and_final_storage() -> None:
    """
    title: Replacing an owned list should destroy both lifetime generations.
    """
    list_type = _list_i32_type()
    module = _module_with_main(
        _mutable_decl("out", list_type, astx.ListCreate(astx.Int32())),
        astx.VariableAssignment("out", astx.ListCreate(astx.Int32())),
        astx.FunctionReturn(astx.ListLength(astx.Identifier("out"))),
    )

    ir_text = Builder().translate(module)

    assert (
        ir_text.count('call void @"irx_list_destroy"')
        == EXPECTED_REPLACEMENT_DESTROYS
    )
    assert_ir_parses(ir_text)


def test_binary_list_assignment_destroys_replaced_and_final_storage() -> None:
    """
    title: Parsed assignment syntax should preserve list replacement cleanup.
    """
    list_type = _list_i32_type()
    module = _module_with_main(
        _mutable_decl("out", list_type, astx.ListCreate(astx.Int32())),
        astx.BinaryOp(
            "=",
            astx.Identifier("out"),
            astx.ListCreate(astx.Int32()),
        ),
        astx.FunctionReturn(astx.ListLength(astx.Identifier("out"))),
    )

    ir_text = Builder().translate(module)

    assert (
        ir_text.count('call void @"irx_list_destroy"')
        == EXPECTED_REPLACEMENT_DESTROYS
    )
    assert_ir_parses(ir_text)


def test_list_field_assignment_fails_without_object_cleanup_contract() -> None:
    """
    title: List-valued fields should fail before ownership-blind lowering.
    """
    container = astx.StructDefStmt(
        name="Container",
        attributes=[
            astx.VariableDeclaration(name="values", type_=_list_i32_type())
        ],
    )
    main = _module_with_main(
        _mutable_decl(
            "container",
            astx.StructType("Container"),
            astx.Undefined(),
        ),
        astx.BinaryOp(
            "=",
            astx.FieldAccess(astx.Identifier("container"), "values"),
            astx.ListCreate(astx.Int32()),
        ),
    ).block[0]
    module = astx.Module()
    module.block.append(container)
    module.block.append(main)

    with pytest.raises(
        SemanticError,
        match="object-field ownership and destruction are not supported",
    ):
        analyze(module)


def test_module_owned_list_fails_without_module_cleanup_contract() -> None:
    """
    title: Module-owned lists should fail before ownership-blind lowering.
    """
    module = astx.Module()
    module.block.append(
        _mutable_decl(
            "values",
            _list_i32_type(),
            astx.ListCreate(astx.Int32()),
        )
    )

    with pytest.raises(
        SemanticError,
        match="requires module lifecycle cleanup",
    ):
        analyze(module)


def test_nested_owned_list_elements_fail_without_recursive_cleanup() -> None:
    """
    title: Dynamic lists should reject elements with independent ownership.
    """
    nested_type = astx.ListType([_list_i32_type()])
    module = _module_with_main(
        _mutable_decl(
            "nested",
            nested_type,
            astx.ListCreate(_list_i32_type()),
        )
    )

    with pytest.raises(
        SemanticError,
        match="nested ownership and destruction are not supported",
    ):
        analyze(module)


def test_nested_block_fallthrough_destroys_owned_list() -> None:
    """
    title: Normal nested-block fallthrough should destroy its owned list.
    """
    then_block = astx.Block()
    then_block.append(
        _mutable_decl(
            "nested",
            _list_i32_type(),
            astx.ListCreate(astx.Int32()),
        )
    )
    module = _module_with_main(
        astx.IfStmt(
            condition=astx.LiteralBoolean(True),
            then=then_block,
        ),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )

    ir_text = Builder().translate(module)

    assert ir_text.count('call void @"irx_list_destroy"') == 1
    assert_ir_parses(ir_text)


@pytest.mark.parametrize(
    "terminator",
    [astx.BreakStmt(), astx.ContinueStmt()],
)
def test_loop_transfer_destroys_owned_list(terminator: astx.AST) -> None:
    """
    title: Loop break and continue should destroy body-owned lists.
    parameters:
      terminator:
        type: astx.AST
    """
    loop_body = astx.Block()
    loop_body.append(
        _mutable_decl(
            "iteration",
            _list_i32_type(),
            astx.ListCreate(astx.Int32()),
        )
    )
    loop_body.append(terminator)
    module = _module_with_main(
        astx.WhileStmt(
            condition=astx.LiteralBoolean(False),
            body=loop_body,
        ),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )

    ir_text = Builder().translate(module)

    assert ir_text.count('call void @"irx_list_destroy"') == 1
    assert_ir_parses(ir_text)


def test_while_condition_destroys_list_call_temporary_each_evaluation() -> (
    None
):
    """
    title: A list call temporary in a loop condition should clean in the loop.
    """
    module = _singleton_module()
    main = module.block[1]
    assert isinstance(main, astx.FunctionDef)
    main.body.nodes.clear()

    loop_body = astx.Block()
    loop_body.append(astx.BreakStmt())
    main.body.append(
        astx.WhileStmt(
            condition=astx.BinaryOp(
                ">",
                astx.ListLength(
                    astx.FunctionCall(
                        "singleton",
                        [astx.LiteralInt32(9)],
                    )
                ),
                astx.LiteralInt32(0),
            ),
            body=loop_body,
        )
    )
    main.body.append(astx.FunctionReturn(astx.LiteralInt32(0)))

    ir_text = Builder().translate(module)
    main_ir = ir_text.split('define i32 @"main"()', maxsplit=1)[1]
    condition_ir = main_ir.split("while.cond:", maxsplit=1)[1].split(
        "while.body:", maxsplit=1
    )[0]

    assert condition_ir.count('call void @"irx_list_destroy"') == 1
    assert condition_ir.index('call void @"irx_list_destroy"') < (
        condition_ir.index("br i1")
    )
    assert_ir_parses(ir_text)
