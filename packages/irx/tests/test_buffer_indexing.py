"""
title: Tests for low-level buffer/view indexing.
"""

from __future__ import annotations

import shutil
import subprocess

from pathlib import Path

import astx
import pytest

from irx.analysis import SemanticError, analyze
from irx.buffer import (
    BufferHandle,
    BufferMutability,
    BufferOwnership,
    BufferViewMetadata,
    buffer_view_flags,
)
from irx.builder import Builder

from .conftest import assert_ir_parses


@pytest.fixture(scope="module")
def checked_store_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    title: Compile dynamic stores once against sentinel-guarded storage.
    parameters:
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: Path
    """
    if shutil.which("clang") is None:
        pytest.skip("native buffer checks require clang")
    module = _module_with_main(
        astx.BufferViewStore(
            _descriptor(
                _metadata(
                    shape=(2,),
                    strides=(4,),
                    mutability=BufferMutability.WRITABLE,
                )
            ),
            [
                astx.BinaryOp(
                    "-", astx.FunctionCall("getchar", []), astx.LiteralInt32(1)
                )
            ],
            astx.LiteralInt32(7),
        )
    )
    getchar = astx.FunctionPrototype(
        "getchar", astx.Arguments(), return_type=astx.Int32()
    )
    getchar.is_extern = True
    getchar.calling_convention = "c"
    module.block.insert(0, getchar)
    builder = Builder()
    text = builder.translate(module)
    address = "inttoptr (i64 4096 to i8*)"
    assert address in text
    text = text.replace(
        address,
        "bitcast (i32* getelementptr ([4 x i32], [4 x i32]* @test.data, "
        "i64 0, i64 1) to i8*)",
    )
    text = text.replace(
        'define i32 @"main"()', 'define i32 @"test.original_main"()'
    )
    text += """
@test.data = global [4 x i32] [i32 41, i32 0, i32 0, i32 42]
define i32 @main() {
entry:
  %status = call i32 @test.original_main()
  %lp = getelementptr [4 x i32], [4 x i32]* @test.data, i64 0, i64 0
  %rp = getelementptr [4 x i32], [4 x i32]* @test.data, i64 0, i64 3
  %left = load i32, i32* %lp
  %right = load i32, i32* %rp
  %left_ok = icmp eq i32 %left, 41
  %right_ok = icmp eq i32 %right, 42
  %safe = and i1 %left_ok, %right_ok
  %result = select i1 %safe, i32 %status, i32 99
  ret i32 %result
}
"""
    assert_ir_parses(text)
    executable = tmp_path_factory.mktemp("checked-store") / "probe"
    builder._build_from_ir(text, str(executable))
    return executable


@pytest.mark.parametrize("index", [-1, 0, 1, 2])
def test_dynamic_store_checks_bounds_before_writing(
    checked_store_binary: Path, index: int
) -> None:
    """
    title: Negative and excess indices never overwrite adjacent storage.
    parameters:
      checked_store_binary:
        type: Path
      index:
        type: int
    """
    result = subprocess.run(
        [str(checked_store_binary)],
        input=bytes([index + 1]),
        capture_output=True,
        check=False,
    )
    assert result.returncode == int(index not in (0, 1)), result.stderr


def _metadata(
    *,
    shape: tuple[int, ...] = (4,),
    strides: tuple[int, ...] = (4,),
    offset_bytes: int = 0,
    mutability: BufferMutability = BufferMutability.READONLY,
) -> BufferViewMetadata:
    """
    title: Build static descriptor metadata for indexed access tests.
    parameters:
      shape:
        type: tuple[int, Ellipsis]
      strides:
        type: tuple[int, Ellipsis]
      offset_bytes:
        type: int
      mutability:
        type: BufferMutability
    returns:
      type: BufferViewMetadata
    """
    return BufferViewMetadata(
        data=BufferHandle(4096),
        owner=BufferHandle(),
        dtype=BufferHandle(1),
        ndim=len(shape),
        shape=shape,
        strides=strides,
        offset_bytes=offset_bytes,
        flags=buffer_view_flags(BufferOwnership.BORROWED, mutability),
    )


def _descriptor(
    metadata: BufferViewMetadata,
    element_type: astx.DataType | None = None,
) -> astx.BufferViewDescriptor:
    """
    title: Build a typed buffer view descriptor node.
    parameters:
      metadata:
        type: BufferViewMetadata
      element_type:
        type: astx.DataType | None
    returns:
      type: astx.BufferViewDescriptor
    """
    return astx.BufferViewDescriptor(
        metadata,
        element_type or astx.Int32(),
    )


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


def test_rejects_non_buffer_view_base() -> None:
    """
    title: Indexing should require a BufferViewType base.
    """
    module = _module_with_main(
        astx.FunctionReturn(
            astx.BufferViewIndex(
                astx.LiteralInt32(1),
                [astx.LiteralInt32(0)],
            )
        )
    )

    with pytest.raises(SemanticError, match="BufferViewType base"):
        analyze(module)


def test_rejects_non_integer_index() -> None:
    """
    title: Indexing should reject non-integer indices.
    """
    module = _module_with_main(
        astx.FunctionReturn(
            astx.BufferViewIndex(
                _descriptor(_metadata()),
                [astx.LiteralFloat32(0.0)],
            )
        )
    )

    with pytest.raises(SemanticError, match="indices must be integer typed"):
        analyze(module)


def test_rejects_wrong_static_rank_index_count() -> None:
    """
    title: Static descriptor rank should validate index count.
    """
    module = _module_with_main(
        astx.FunctionReturn(
            astx.BufferViewIndex(
                _descriptor(_metadata(shape=(2, 3), strides=(12, 4))),
                [astx.LiteralInt32(0)],
            )
        )
    )

    with pytest.raises(SemanticError, match="index count must match"):
        analyze(module)


def test_rejects_unknown_scalar_element_type() -> None:
    """
    title: Indexing should require a scalar element type bridge.
    """
    module = _module_with_main(
        astx.FunctionReturn(
            astx.BufferViewIndex(
                _descriptor(_metadata(), element_type=astx.BufferViewType()),
                [astx.LiteralInt32(0)],
            )
        )
    )

    with pytest.raises(SemanticError, match="scalar element type"):
        analyze(module)


def test_rejects_static_out_of_bounds_index() -> None:
    """
    title: Static shape should reject provably out-of-bounds indices.
    """
    module = _module_with_main(
        astx.FunctionReturn(
            astx.BufferViewIndex(
                _descriptor(_metadata(shape=(2,), strides=(4,))),
                [astx.LiteralInt32(2)],
            )
        )
    )

    with pytest.raises(SemanticError, match="statically out of bounds"):
        analyze(module)


def test_rejects_indexed_store_through_readonly_view() -> None:
    """
    title: Indexed stores should reuse readonly view rejection.
    """
    module = _module_with_main(
        astx.BufferViewStore(
            _descriptor(
                _metadata(
                    shape=(2,),
                    strides=(4,),
                    mutability=BufferMutability.READONLY,
                )
            ),
            [astx.LiteralInt32(0)],
            astx.LiteralInt32(7),
        )
    )

    with pytest.raises(SemanticError, match="readonly buffer view"):
        analyze(module)


def test_allows_indexed_store_through_writable_view() -> None:
    """
    title: Writable views should allow indexed stores.
    """
    module = _module_with_main(
        astx.BufferViewStore(
            _descriptor(
                _metadata(
                    shape=(2,),
                    strides=(4,),
                    mutability=BufferMutability.WRITABLE,
                )
            ),
            [astx.LiteralInt32(0)],
            astx.LiteralInt32(7),
        )
    )

    analyze(module)


def test_identifier_indexing_uses_static_initializer_metadata() -> None:
    """
    title: Static descriptor metadata should flow to indexed identifiers.
    """
    indexed = astx.BufferViewIndex(
        astx.Identifier("view"),
        [astx.LiteralInt32(1)],
    )
    module = _module_with_main(
        astx.VariableDeclaration(
            name="view",
            type_=astx.BufferViewType(),
            mutability=astx.MutabilityKind.mutable,
            value=_descriptor(_metadata(shape=(2,), strides=(4,))),
        ),
        astx.FunctionReturn(indexed),
    )

    analyze(module)

    semantic = getattr(indexed, "semantic")
    assert isinstance(semantic.resolved_type, astx.Int32)


def test_rejects_indexing_without_static_descriptor_metadata() -> None:
    """
    title: Dynamic-rank descriptors should wait for a runtime-checking mode.
    """
    view_arg = astx.Argument("view", astx.BufferViewType(astx.Int32()))
    body = astx.Block()
    body.append(
        astx.FunctionReturn(
            astx.BufferViewIndex(
                astx.Identifier("view"),
                [astx.LiteralInt32(0)],
            )
        )
    )
    module = astx.Module()
    module.block.append(
        astx.FunctionDef(
            prototype=astx.FunctionPrototype(
                "main",
                args=astx.Arguments(view_arg),
                return_type=astx.Int32(),
            ),
            body=body,
        )
    )

    with pytest.raises(SemanticError, match="static descriptor metadata"):
        analyze(module)


def test_rank1_read_lowers_through_descriptor_fields() -> None:
    """
    title: Rank-1 reads should compute an element pointer and load it.
    """
    ir_text = Builder().translate(
        _module_with_main(
            astx.FunctionReturn(
                astx.BufferViewIndex(
                    _descriptor(_metadata(shape=(4,), strides=(4,))),
                    [astx.LiteralInt32(1)],
                )
            )
        )
    )

    assert "irx_buffer_view_data" in ir_text
    assert "irx_buffer_index_offset" in ir_text
    assert "buffer.index.view" in ir_text
    assert "irx_buffer_checked_offset" in ir_text
    assert "load i32" in ir_text
    assert "align 1" in ir_text
    assert_ir_parses(ir_text)


def test_identifier_read_lowers_with_static_initializer_metadata() -> None:
    """
    title: Identifier-based reads should reuse the descriptor indexing path.
    """
    ir_text = Builder().translate(
        _module_with_main(
            astx.VariableDeclaration(
                name="view",
                type_=astx.BufferViewType(),
                mutability=astx.MutabilityKind.mutable,
                value=_descriptor(_metadata(shape=(4,), strides=(4,))),
            ),
            astx.FunctionReturn(
                astx.BufferViewIndex(
                    astx.Identifier("view"),
                    [astx.LiteralInt32(1)],
                )
            ),
        )
    )

    assert 'load %"irx_buffer_view"' in ir_text
    assert "irx_buffer_view_data" in ir_text
    assert "irx_buffer_checked_offset" in ir_text
    assert "load i32" in ir_text
    assert "align 1" in ir_text
    assert_ir_parses(ir_text)


def test_rank1_store_lowers_to_pointer_arithmetic_and_store() -> None:
    """
    title: Rank-1 stores should compute an element pointer and store into it.
    """
    ir_text = Builder().translate(
        _module_with_main(
            astx.BufferViewStore(
                _descriptor(
                    _metadata(
                        shape=(4,),
                        strides=(4,),
                        mutability=BufferMutability.WRITABLE,
                    )
                ),
                [astx.LiteralInt32(1)],
                astx.LiteralInt32(7),
            )
        )
    )

    assert "irx_buffer_index_byte_ptr" in ir_text
    assert "irx_buffer_index_element_ptr" in ir_text
    assert "store i32 7" in ir_text
    assert_ir_parses(ir_text)


def test_identifier_store_lowers_with_static_initializer_metadata() -> None:
    """
    title: Identifier-based stores should reuse the descriptor indexing path.
    """
    ir_text = Builder().translate(
        _module_with_main(
            astx.VariableDeclaration(
                name="view",
                type_=astx.BufferViewType(),
                mutability=astx.MutabilityKind.mutable,
                value=_descriptor(
                    _metadata(
                        shape=(4,),
                        strides=(4,),
                        mutability=BufferMutability.WRITABLE,
                    )
                ),
            ),
            astx.BufferViewStore(
                astx.Identifier("view"),
                [astx.LiteralInt32(1)],
                astx.LiteralInt32(7),
            ),
        )
    )

    assert 'load %"irx_buffer_view"' in ir_text
    assert "irx_buffer_view_data" in ir_text
    assert "irx_buffer_checked_offset" in ir_text
    assert "store i32 7" in ir_text
    assert_ir_parses(ir_text)


def test_rank2_read_uses_both_strides() -> None:
    """
    title: Rank-2 reads should include both stride terms in the offset.
    """
    ir_text = Builder().translate(
        _module_with_main(
            astx.FunctionReturn(
                astx.BufferViewIndex(
                    _descriptor(
                        _metadata(
                            shape=(3, 4),
                            strides=(16, 4),
                        )
                    ),
                    [astx.LiteralInt32(1), astx.LiteralInt32(2)],
                )
            )
        )
    )

    assert "irx_buffer_checked_offset" in ir_text
    assert "buffer.index.indices" in ir_text
    assert "i64 16, i64 4" in ir_text
    assert "i32 2, i64 4" in ir_text
    assert "load i32" in ir_text
    assert "align 1" in ir_text
    assert_ir_parses(ir_text)


def test_rank2_store_uses_offset_bytes_and_strides() -> None:
    """
    title: Rank-2 stores should include offset_bytes and both stride terms.
    """
    ir_text = Builder().translate(
        _module_with_main(
            astx.BufferViewStore(
                _descriptor(
                    _metadata(
                        shape=(3, 4),
                        strides=(16, 4),
                        offset_bytes=8,
                        mutability=BufferMutability.WRITABLE,
                    )
                ),
                [astx.LiteralInt32(1), astx.LiteralInt32(2)],
                astx.LiteralInt32(5),
            )
        )
    )

    assert "irx_buffer_index_offset" in ir_text
    assert "irx_buffer_checked_offset" in ir_text
    assert "buffer.index.indices" in ir_text
    assert "store i32 5" in ir_text
    assert_ir_parses(ir_text)
