"""
title: Tests for the IRx Tensor layer.
"""

from __future__ import annotations

import shutil
import subprocess

from pathlib import Path
from typing import Any, cast

import astx
import pytest

from irx.analysis import SemanticError, analyze
from irx.buffer import buffer_dtype_handle
from irx.builder import Builder
from irx.builtins.collections.tensor import (
    tensor_element_size_bytes_from_dtype,
)
from llvmlite import binding as llvm
from llvmlite import ir
from public import private

from .conftest import assert_ir_parses, build_and_run


@private
def instrument_tensor_lifetimes(builder: Builder) -> str:
    """
    title: Count live construction resources and fail a repeated native call.
    summary: >-
      Wrap both direct calls and the external owner's release callback. Failed
      pointer outputs are poisoned so unchecked output use cannot pass quietly.
    parameters:
      builder:
        type: Builder
    returns:
      type: str
    """
    module = builder.translator._llvm.module
    integer = ir.IntType(32)
    counters: dict[str, ir.GlobalVariable] = {}
    for name in ("builders", "tensors", "owners", "stage"):
        counter = ir.GlobalVariable(module, integer, "test." + name)
        counter.initializer = ir.Constant(integer, 0)
        counters[name] = counter
    functions = list(module.functions)
    specifications = (
        ("irx_arrow_tensor_builder_new", 1, {"builders": 1}),
        ("irx_arrow_tensor_builder_append_int", 2, {}),
        ("irx_arrow_tensor_builder_finish", 3, {"builders": -1, "tensors": 1}),
        ("irx_arrow_tensor_borrow_buffer_view", 4, {}),
        ("irx_buffer_owner_external_new", 5, {"owners": 1}),
        ("irx_arrow_tensor_builder_release", 0, {"builders": -1}),
        ("irx_arrow_tensor_release", 0, {"tensors": -1}),
        ("irx_buffer_owner_release", 0, {"owners": -1}),
    )
    for name, stage, changes in specifications:
        original = module.get_global(name)
        assert isinstance(original, ir.Function)
        wrapper = ir.Function(module, original.function_type, "test." + name)
        for function in functions:
            for block in function.blocks:
                for instruction in block.instructions:
                    instruction.replace_usage(original, wrapper)
        emitter = ir.IRBuilder(wrapper.append_basic_block("entry"))
        if stage:
            calls = ir.GlobalVariable(module, integer, "test.calls." + name)
            calls.initializer = ir.Constant(integer, 0)
            number = emitter.add(emitter.load(calls), ir.Constant(integer, 1))
            emitter.store(number, calls)
            fail = emitter.and_(
                emitter.icmp_signed(
                    "==",
                    emitter.load(counters["stage"]),
                    ir.Constant(integer, stage),
                ),
                emitter.icmp_signed("==", number, ir.Constant(integer, 2)),
            )
            with emitter.if_then(fail):
                if stage in (1, 3, 5):
                    output = wrapper.args[-1]
                    poison = ir.Constant(ir.IntType(64), 1).inttoptr(
                        output.type.pointee
                    )
                    emitter.store(poison, output)
                emitter.ret(
                    ir.Constant(
                        integer,
                        -1 if name == "irx_buffer_owner_external_new" else -6,
                    )
                )
        status = emitter.call(original, list(wrapper.args))
        if isinstance(status.type, ir.VoidType):
            for resource, delta in changes.items():
                counter = counters[resource]
                emitter.store(
                    emitter.add(
                        emitter.load(counter), ir.Constant(integer, delta)
                    ),
                    counter,
                )
            emitter.ret_void()
            continue
        with emitter.if_then(
            emitter.icmp_signed("==", status, ir.Constant(integer, 0))
        ):
            for resource, delta in changes.items():
                counter = counters[resource]
                emitter.store(
                    emitter.add(
                        emitter.load(counter), ir.Constant(integer, delta)
                    ),
                    counter,
                )
        emitter.ret(status)
    text = str(module).replace(
        'define i32 @"main"()', 'define i32 @"test.original_main"()'
    )
    return (
        text
        + """
define i32 @main() {
entry:
  %stage = call i32 @getchar()
  store i32 %stage, i32* @test.stage
  %result = call i32 @test.original_main()
  %builders = load i32, i32* @test.builders
  %tensors = load i32, i32* @test.tensors
  %owners = load i32, i32* @test.owners
  %b = icmp eq i32 %builders, 0
  %t = icmp eq i32 %tensors, 0
  %o = icmp eq i32 %owners, 0
  %bt = and i1 %b, %t
  %empty = and i1 %bt, %o
  %output = select i1 %empty, i32 %result, i32 99
  ret i32 %output
}
"""
    )


@pytest.fixture(scope="module")
def tensor_lifetime_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    title: Compile one instrumented tensor consumer for all failure stages.
    parameters:
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: Path
    """
    if shutil.which("clang") is None:
        pytest.skip("native tensor ownership checks require clang")
    loop = astx.Block()
    loop.append(astx.BreakStmt())
    repeated = astx.Block()
    repeated.append(
        astx.VariableAssignment(
            "iteration",
            astx.BinaryOp(
                "+", astx.Identifier("iteration"), astx.LiteralInt32(1)
            ),
        )
    )
    repeated.append(
        astx.TensorIndex(
            _int32_tensor([1, 2], shape=(2,)), [astx.LiteralInt32(0)]
        )
    )
    repeated.append(astx.ContinueStmt())
    module = _module_with_main(
        astx.WhileStmt(
            condition=astx.BinaryOp(
                ">",
                astx.TensorIndex(
                    _int32_tensor([1, 2], shape=(2,)), [astx.LiteralInt32(0)]
                ),
                astx.LiteralInt32(0),
            ),
            body=loop,
        ),
        astx.VariableDeclaration(
            "iteration",
            astx.Int32(),
            value=astx.LiteralInt32(0),
            mutability=astx.MutabilityKind.mutable,
        ),
        astx.WhileStmt(
            condition=astx.BinaryOp(
                "<", astx.Identifier("iteration"), astx.LiteralInt32(2)
            ),
            body=repeated,
        ),
        astx.FunctionReturn(
            astx.TensorIndex(
                astx.TensorView(_int32_tensor([1, 2], shape=(2,)), shape=(2,)),
                [
                    astx.BinaryOp(
                        "/",
                        astx.LiteralInt32(1),
                        astx.FunctionCall("getchar", []),
                    )
                ],
            )
        ),
    )
    prototype = astx.FunctionPrototype(
        "getchar", args=astx.Arguments(), return_type=astx.Int32()
    )
    prototype.is_extern = True
    prototype.calling_convention = "c"
    prototype.symbol_name = "getchar"
    module.block.insert(0, prototype)
    builder = Builder()
    builder.translate(module)
    text = instrument_tensor_lifetimes(builder)
    llvm.parse_assembly(text).verify()
    executable = tmp_path_factory.mktemp("tensor-lifetimes") / "probe"
    builder._build_from_ir(text, str(executable))
    return executable


@pytest.mark.parametrize(
    "stage,divisor", [(0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1), (0, 0)]
)
def test_tensor_temporary_lifetimes(
    tensor_lifetime_binary: Path, stage: int, divisor: int
) -> None:
    """
    title: Exactly-once cleanup survives consumption and construction failures.
    parameters:
      tensor_lifetime_binary:
        type: Path
      stage:
        type: int
      divisor:
        type: int
    """
    result = subprocess.run(
        [str(tensor_lifetime_binary)],
        input=bytes([stage, divisor]),
        capture_output=True,
        check=False,
        timeout=15,
    )
    success = stage == 0 and divisor == 1
    assert result.returncode == (2 if success else 1), result.stderr
    assert result.stdout == b""
    if success:
        assert result.stderr == b""
    else:
        assert b"ARX-RUNTIME-" in result.stderr


def _module_with_main(*nodes: astx.AST) -> astx.Module:
    """
    title: Build an int32 main module.
    parameters:
      nodes:
        type: astx.AST
        variadic: positional
    returns:
      type: astx.Module
    """
    module = astx.Module()
    prototype = astx.FunctionPrototype(
        "main",
        args=astx.Arguments(),
        return_type=astx.Int32(),
    )
    body = astx.Block()
    for node in nodes:
        body.append(node)
    if not any(isinstance(node, astx.FunctionReturn) for node in nodes):
        body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module.block.append(astx.FunctionDef(prototype=prototype, body=body))
    return module


def _int32_tensor(
    values: list[int],
    *,
    shape: tuple[int, ...],
    strides: tuple[int, ...] | None = None,
    offset_bytes: int = 0,
) -> astx.TensorLiteral:
    """
    title: Build one int32 Tensor literal node.
    parameters:
      values:
        type: list[int]
      shape:
        type: tuple[int, Ellipsis]
      strides:
        type: tuple[int, Ellipsis] | None
      offset_bytes:
        type: int
    returns:
      type: astx.TensorLiteral
    """
    return astx.TensorLiteral(
        [astx.LiteralInt32(value) for value in values],
        element_type=astx.Int32(),
        shape=shape,
        strides=strides,
        offset_bytes=offset_bytes,
    )


def test_tensor_literal_get_struct_shapes() -> None:
    """
    title: Tensor literal get_struct should expose shape and stride metadata.
    """
    node = _int32_tensor([1, 2, 3, 4], shape=(2, 2), strides=(8, 4))

    full = node.get_struct()
    assert isinstance(full, dict)
    full_entry = cast(dict[str, Any], full["TensorLiteral"])
    entry = cast(dict[str, Any], full_entry["content"])
    assert entry["shape"] == [2, 2]
    assert entry["strides"] == [8, 4]
    assert entry["offset_bytes"] == 0

    simplified = node.get_struct(simplified=True)
    assert isinstance(simplified, dict)
    simplified_entry = cast(dict[str, Any], simplified["TensorLiteral"])
    assert simplified_entry["shape"] == [2, 2]


def test_tensor_element_size_uses_shared_dtype_metadata() -> None:
    """
    title: Tensor dtype sizes should come from shared primitive metadata.
    """
    int32_dtype = buffer_dtype_handle("int32")
    float64_dtype = buffer_dtype_handle("float64")
    bool_dtype = buffer_dtype_handle("bool")
    int32_size = 4
    float64_size = 8

    assert tensor_element_size_bytes_from_dtype(int32_dtype) == int32_size
    assert tensor_element_size_bytes_from_dtype(float64_dtype) == float64_size
    assert tensor_element_size_bytes_from_dtype(bool_dtype) is None


def test_tensor_rejects_bool_elements() -> None:
    """
    title: Bool Tensors should fail semantic analysis in this phase.
    """
    module = _module_with_main(
        astx.FunctionReturn(
            astx.TensorNDim(
                astx.TensorLiteral(
                    [astx.LiteralBoolean(True), astx.LiteralBoolean(False)],
                    element_type=astx.Boolean(),
                    shape=(2,),
                )
            )
        )
    )

    with pytest.raises(SemanticError, match="bool tensors are not supported"):
        analyze(module)


def test_tensor_rejects_wrong_static_rank_index_count() -> None:
    """
    title: Tensor indexing should validate static rank against index arity.
    """
    module = _module_with_main(
        astx.FunctionReturn(
            astx.TensorIndex(
                _int32_tensor([1, 2, 3, 4], shape=(2, 2)),
                [astx.LiteralInt32(0)],
            )
        )
    )

    with pytest.raises(SemanticError, match="index count must match"):
        analyze(module)


def test_tensor_store_rejects_arrow_cpp_readonly_values() -> None:
    """
    title: Arrow C++ backed Tensor literals remain readonly in this phase.
    """
    module = _module_with_main(
        astx.TensorStore(
            _int32_tensor([1, 2, 3, 4], shape=(2, 2)),
            [astx.LiteralInt32(0), astx.LiteralInt32(1)],
            astx.LiteralInt32(99),
        )
    )

    with pytest.raises(SemanticError, match="readonly tensor view"):
        analyze(module)


def test_tensor_literal_lowers_through_tensor_runtime_and_owner_bridge() -> (
    None
):
    """
    title: >-
      Tensor literals should use the Arrow tensor runtime plus an owner bridge.
    """
    builder = Builder()
    literal = _int32_tensor([1, 2, 3, 4], shape=(2, 2))
    borrowed = astx.TensorView(astx.Identifier("tensor"), shape=(2, 2))
    module = _module_with_main(
        astx.VariableDeclaration(
            name="tensor",
            type_=astx.TensorType(astx.Int32()),
            mutability=astx.MutabilityKind.mutable,
            value=literal,
        ),
        astx.FunctionReturn(
            astx.TensorIndex(
                borrowed,
                [astx.LiteralInt32(1), astx.LiteralInt32(1)],
            )
        ),
    )

    ir_text = builder.translate(module)

    assert '@"irx_arrow_tensor_builder_new"' in ir_text
    assert '@"irx_arrow_tensor_borrow_buffer_view"' in ir_text
    assert '@"irx_buffer_owner_external_new"' in ir_text
    assert "irx_tensor_shape" in ir_text
    assert "irx_tensor_stride" in ir_text
    assert "irx_tensor_index_load" in ir_text
    assert literal.semantic.tensor_temporary_owner
    assert not borrowed.base.semantic.tensor_temporary_owner
    assert not borrowed.semantic.tensor_temporary_owner
    assert 'call i32 @"irx_buffer_owner_release"' not in ir_text
    assert_ir_parses(ir_text)


def test_tensor_view_lowers_custom_shape_stride_and_offset() -> None:
    """
    title: Tensor views should lower with explicit shape, stride, and offset.
    """
    builder = Builder()
    view = astx.TensorView(
        _int32_tensor([10, 20, 30, 40, 50, 60], shape=(2, 3)),
        shape=(2, 2),
        strides=(12, 4),
        offset_bytes=4,
    )
    module = _module_with_main(
        astx.FunctionReturn(
            astx.TensorIndex(
                view,
                [astx.LiteralInt32(1), astx.LiteralInt32(0)],
            )
        )
    )

    ir_text = builder.translate(module)

    assert view.semantic.tensor_temporary_owner
    assert "irx_tensor_shape_ptr" in ir_text or "irx_tensor_shape_" in ir_text
    assert (
        "irx_tensor_stride_ptr" in ir_text or "irx_tensor_strides_" in ir_text
    )
    assert "irx_buffer_index_stride_0" in ir_text
    assert "irx_buffer_index_stride_1" in ir_text
    assert (
        "irx_tensor_offset_bytes" in ir_text
        or "irx_buffer_index_offset_1" in ir_text
    )
    assert_ir_parses(ir_text)


def test_tensor_queries_lower_to_shape_stride_metadata() -> None:
    """
    title: Tensor queries should lower to rank, shape, and stride metadata.
    """
    builder = Builder()
    module = _module_with_main(
        astx.VariableDeclaration(
            name="tensor",
            type_=astx.TensorType(astx.Int32()),
            mutability=astx.MutabilityKind.mutable,
            value=_int32_tensor([1, 2, 3, 4], shape=(2, 2)),
        ),
        astx.FunctionReturn(astx.TensorNDim(astx.Identifier("tensor"))),
    )

    ir_text = builder.translate(module)

    assert "irx_tensor_ndim" in ir_text
    assert_ir_parses(ir_text)


def test_tensor_build_returns_indexed_element() -> None:
    """
    title: Built Tensor programs should return indexed element values.
    """
    if shutil.which("clang") is None:
        pytest.skip("builder.build() currently requires clang")

    module = _module_with_main(
        astx.FunctionReturn(
            astx.TensorIndex(
                _int32_tensor([1, 2, 3, 4, 5, 6], shape=(2, 3)),
                [astx.LiteralInt32(1), astx.LiteralInt32(2)],
            )
        )
    )

    result = build_and_run(Builder(), module)

    expected = 6
    assert result.returncode == expected, result.stderr or result.stdout


def test_tensor_view_build_returns_view_element() -> None:
    """
    title: Built Tensor views should return values through view metadata.
    """
    if shutil.which("clang") is None:
        pytest.skip("builder.build() currently requires clang")

    view = astx.TensorView(
        _int32_tensor([10, 20, 30, 40, 50, 60], shape=(2, 3)),
        shape=(2, 2),
        strides=(12, 4),
        offset_bytes=4,
    )
    module = _module_with_main(
        astx.FunctionReturn(
            astx.TensorIndex(
                view,
                [astx.LiteralInt32(1), astx.LiteralInt32(0)],
            )
        )
    )

    result = build_and_run(Builder(), module)

    expected = 50
    assert result.returncode == expected, result.stderr or result.stdout
