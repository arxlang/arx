"""
title: Reusable builders and chunked values through native Arx execution.
"""

from __future__ import annotations

import subprocess

from pathlib import Path

import pytest

from arx.codegen import ArxBuilder
from irx.analysis import analyze
from irx.diagnostics import SemanticError
from llvmlite import binding as llvm

from .test_array_values import parse_body
from .test_nullable_operations import parse


def run_body(body: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """
    title: Verify LLVM and execute one native container regression.
    parameters:
      body:
        type: str
      tmp_path:
        type: Path
    returns:
      type: subprocess.CompletedProcess[str]
    """
    module = parse_body(body)
    builder = ArxBuilder()
    llvm.parse_assembly(builder.translate(module)).verify()
    executable = tmp_path / "chunks"
    builder.build(module, output_file=str(executable))
    return subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )


def test_builders_and_chunks_execute(tmp_path: Path) -> None:
    """
    title: Build dynamic nullable values, reuse builders and cross boundaries.
    parameters:
      tmp_path:
        type: Path
    """
    result = run_body(
        (
            "  var builder: array_builder[i32 | none] ="
            " array_builder[i32 | none]()\n"
            "  builder_reserve(builder, 4)\n"
            "  var i: i32 = 0\n"
            "  while i < 3:\n"
            "    builder_append(builder, i)\n"
            "    i = i + 1\n"
            "  builder_append(builder, none)\n"
            "  assert builder_length(builder) == 4\n"
            "  var first: array[i32 | none] = builder_finish(builder)\n"
            "  assert builder_length(builder) == 0\n"
            "  builder_append(builder, 4)\n"
            "  var second: array[i32 | none] = builder_finish(builder)\n"
            "  var chunks: chunked_array[i32 | none] ="
            " chunked_array[i32 | none](first, array[i32 | none](),"
            " second)\n"
            "  assert array_length(chunks) == 5\n"
            "  assert array_null_count(chunks) == 1\n"
            "  assert chunk_count(chunks) == 3\n"
            "  assert expect_valid(array_at(chunks, 4)) == 4\n"
            "  assert is_null(array_at(chunks, 3))\n"
            "  assert array_equal(chunk_at(chunks, 0), first)\n"
            "  var sliced: chunked_array[i32 | none] ="
            " array_slice(chunks, 2, 3)\n"
            "  assert array_equal(combine_chunks(sliced), array[i32 |"
            " none](2, none, 4))\n"
            "  assert array_equal(array_copy(chunks), chunks)\n"
            "  assert array_equal(array_concat(sliced, sliced),"
            " chunked_array[i32 | none](combine_chunks(sliced),"
            " combine_chunks(sliced)))\n"
            "  var total: i64 = 0\n"
            "  var index: i32 = 0\n"
            "  while index < chunk_count(chunks):\n"
            "    total = total + array_length(chunk_at(chunks, index))\n"
            "    index = index + 1\n"
            "  assert total == 5\n"
            "  var empty: chunked_array[i32] = chunked_array[i32]()\n"
            "  assert chunk_count(empty) == 0\n"
            "  assert array_length(combine_chunks(empty)) == 0\n"
            "  var bools: chunked_array[bool | none] ="
            " chunked_array[bool | none](array[bool | none](true),"
            " array_slice(array[bool | none](false, none, true), 1,"
            " 2))\n"
            "  assert is_null(array_at(bools, 1))\n"
            "  assert expect_valid(array_at(bools, 2))\n"
        ),
        tmp_path,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "body,message",
    [
        ("builder_append(array_builder[i32](), none)", "incompatible"),
        ("builder_append(array[i32](), 1)", "requires an array_builder"),
        ("array_builder[i32](1)", "takes no values"),
        ("chunked_array[i32](array[f64]())", "incompatible"),
        ("array_offset(chunked_array[i32]())", "no single physical offset"),
        ("chunk_at(array[i32](), 0)", "requires a chunked_array"),
        (
            (
                "var a: array_builder[i32] = array_builder[i32]()\n"
                "  var b: array_builder[i32] = a"
            ),
            "unique",
        ),
    ],
)
def test_invalid_container_contracts(body: str, message: str) -> None:
    """
    title: Reject container category confusion and builder owner aliases early.
    parameters:
      body:
        type: str
      message:
        type: str
    """
    with pytest.raises(SemanticError, match=message):
        analyze(parse_body("  " + body))


@pytest.mark.parametrize(
    "body",
    [
        "builder_reserve(array_builder[i32](), -1)",
        "chunk_at(chunked_array[i32](), 0)",
        "array_at(chunked_array[i32](array[i32](1)), 1)",
        "array_slice(chunked_array[i32](), 0, 1)",
    ],
)
def test_runtime_bounds(body: str, tmp_path: Path) -> None:
    """
    title: Reject negative reserve and logical or physical bounds violations.
    parameters:
      body:
        type: str
      tmp_path:
        type: Path
    """
    result = run_body("  " + body, tmp_path)
    assert result.returncode != 0
    assert "ARX-RUNTIME" in result.stderr


def test_half_float_chunks(tmp_path: Path) -> None:
    """
    title: Preserve half-float values through builders, slices and extraction.
    parameters:
      tmp_path:
        type: Path
    """
    result = run_body(
        (
            "  var b: array_builder[f16 | none] = array_builder[f16 |"
            " none]()\n"
            "  builder_append(b, cast(1.5, f16))\n"
            "  builder_append(b, none)\n"
            "  builder_append(b, cast(-0.5, f16))\n"
            "  var a: array[f16 | none] = builder_finish(b)\n"
            "  var c: chunked_array[f16 | none] = chunked_array[f16 |"
            " none](array_slice(a, 1, 2), a)\n"
            "  assert is_null(array_at(c, 0))\n"
            "  assert expect_valid(array_at(c, 1)) == cast(-0.5, f16)\n"
            "  assert expect_valid(array_at(c, 2)) == cast(1.5, f16)\n"
            "  assert array_equal(combine_chunks(c),"
            " array_concat(array_slice(a, 1, 2), a))\n"
        ),
        tmp_path,
    )
    assert result.returncode == 0, result.stderr


def test_void_append_is_not_a_null_element() -> None:
    """
    title: Reject void-producing calls rather than silently appending null.
    """
    source = (
        "fn nothing() -> none:\n  return\n"
        "fn main() -> i32:\n"
        "  var b: array_builder[i32 | none] = array_builder[i32 | none]()\n"
        "  builder_append(b, nothing())\n  return 0\n"
    )
    with pytest.raises(SemanticError, match="void call"):
        analyze(parse(source))
