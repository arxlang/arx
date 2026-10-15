"""
title: First-class Arrow arrays across parsing, semantics, LLVM and execution.
"""

from __future__ import annotations

import subprocess

from pathlib import Path

import astx
import pytest

from arx.codegen import ArxBuilder
from arx.exceptions import ParserException
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser
from irx.analysis import analyze
from irx.builder.backend import Visitor
from irx.diagnostics import LoweringError, SemanticError
from llvmlite import binding as llvm


def parse_body(body: str) -> astx.Module:
    """
    title: Parse a documented array regression in an entry point.
    parameters:
      body:
        type: str
    returns:
      type: astx.Module
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Array regression\n```\nfn main() -> i32:\n"
        + body
        + "\n  return 0\n"
    )
    return Parser().parse(Lexer().lex())


def test_array_example_executes(tmp_path: Path) -> None:
    """
    title: Exercise offset arrays, nullable extraction, calls and ownership.
    parameters:
      tmp_path:
        type: Path
    """
    source = Path(__file__).resolve().parents[4] / "examples/columnar_arrays.x"
    ArxIO.string_to_buffer(source.read_text())
    module = Parser().parse(Lexer().lex())
    builder = ArxBuilder()
    output = builder.translate(module)
    llvm.parse_assembly(output).verify()
    for symbol in (
        "array_builder_new",
        "array_builder_finish",
        "array_get_int",
        "array_get_uint",
        "array_get_double",
        "array_slice",
        "array_copy",
        "array_concat",
        "array_equal",
        "array_retain",
        "array_release",
    ):
        assert f"irx_arrow_{symbol}" in output
    assert "arrow::" not in output
    executable = tmp_path / "arrays"
    builder.build(module, output_file=str(executable))
    result = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "body,message",
    [
        ("var a: array[i32] = array[i32](none)", "non-void"),
        ("var a: array[i32] = array[i32](true)", "incompatible"),
        ("array[i8](300)", "incompatible"),
        ("array[string](1)", "incompatible"),
        ("array[f16](1.0)", "incompatible"),
        ("array_at(array[i32](1), true)", "signed integers"),
        ("array_length()", "argument count"),
        ("array_length(1)", "implemented Arrow array"),
        ("array_concat(array[i32](), array[f32]())", "matching element"),
        (
            "array_concat(array[i32](), array[i32 | none]())",
            "matching element",
        ),
        ("var x: i32 = array_at(array[i32](1), 0)", "cannot assign"),
    ],
)
def test_array_semantic_errors(body: str, message: str) -> None:
    """
    title: Reject invalid types, nullability and signatures before lowering.
    parameters:
      body:
        type: str
      message:
        type: str
    """
    with pytest.raises(SemanticError, match=message):
        analyze(parse_body("  " + body))


@pytest.mark.parametrize(
    "expression",
    ["array[i32 | bool](1)", "array_length<i32>(1)"],
)
def test_array_parser_errors(expression: str) -> None:
    """
    title: Reject malformed array annotation and query syntax early.
    parameters:
      expression:
        type: str
    """
    with pytest.raises(ParserException):
        parse_body("  " + expression)


def test_unresolved_array_lowering_is_rejected() -> None:
    """
    title: Never discover array contracts from syntax during code generation.
    """
    node = astx.ArrayLiteral(
        astx.ArrayType(astx.LogicalType(astx.LogicalKind.INT32)), ()
    )
    with pytest.raises(LoweringError, match="missing resolved array"):
        Visitor().visit(node)


@pytest.mark.parametrize(
    "expression",
    [
        "array_at(array[i32](1), -1)",
        "array_at(array[i32](), 0)",
        "array_slice(array[i32](1), 1, 1)",
        "array_slice(array[i32](1), 0, -1)",
    ],
)
def test_array_bounds_are_checked(expression: str, tmp_path: Path) -> None:
    """
    title: Reject invalid extraction and slices with checked runtime failures.
    parameters:
      expression:
        type: str
      tmp_path:
        type: Path
    """
    executable = tmp_path / "invalid-array"
    ArxBuilder().build(
        parse_body("  " + expression), output_file=str(executable)
    )
    result = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "ARX-RUNTIME-ARROW-001" in result.stderr


def test_array_temporaries_in_nullable_short_circuit(tmp_path: Path) -> None:
    """
    title: Branch-local native owners never require undominated cleanup slots.
    parameters:
      tmp_path:
        type: Path
    """
    module = parse_body(
        "  var unknown: bool | none = none\n"
        "  assert is_null(unknown and "
        "array_equal(array[i32](), array[i32]()))\n"
        "  var yes: bool | none = true\n"
        "  assert expect_valid(yes or "
        "array_equal(array[i32](1), array[i32]()))"
    )
    builder = ArxBuilder()
    llvm.parse_assembly(builder.translate(module)).verify()
    executable = tmp_path / "array-short-circuit"
    builder.build(module, output_file=str(executable))
    assert subprocess.run([str(executable)], check=False).returncode == 0


@pytest.mark.parametrize(
    "body",
    [
        "array[i32]() == array[i32]()",
        "array[i32]() != array[i32]()",
        "array[i32]() < array[i32]()",
        "var a: array[i32] = array[i32]()\n  ++a",
        "schema[] == schema[]",
        "datatype[i32] == datatype[i32]",
        'field["name": i32] == field["name": i32]',
    ],
)
def test_columnar_owners_never_use_scalar_pointer_operators(body: str) -> None:
    """
    title: Opaque Arrow handles must never reach string or pointer arithmetic.
    parameters:
      body:
        type: str
    """
    with pytest.raises(SemanticError, match="columnar owners"):
        analyze(parse_body("  " + body))


@pytest.mark.parametrize(
    "type_",
    [
        astx.DataFrameType((astx.DataFrameColumn("value", astx.Int32()),)),
        astx.SeriesType(astx.Int32()),
    ],
)
def test_existing_columnar_owners_also_reject_scalar_comparison(
    type_: astx.DataType,
) -> None:
    """
    title: Shared table and series owners cannot be compared as C strings.
    parameters:
      type_:
        type: astx.DataType
    """
    body = astx.Block()
    body.append(
        astx.FunctionReturn(
            astx.BinaryOp(
                "==",
                astx.Identifier("lhs"),
                astx.Identifier("rhs"),
            )
        )
    )
    module = astx.Module()
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype(
                "compare",
                astx.Arguments(
                    astx.Argument("lhs", type_), astx.Argument("rhs", type_)
                ),
                astx.Boolean(),
            ),
            body,
        )
    )
    with pytest.raises(SemanticError, match="columnar owners"):
        analyze(module)
