"""
title: Nullable operators and branch proofs through native Arx execution.
"""

from __future__ import annotations

import subprocess

from pathlib import Path

import astx
import pytest

from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser
from irx.analysis import analyze
from irx.diagnostics import SemanticError
from llvmlite import binding as llvm


def parse(source: str) -> astx.Module:
    """
    title: Parse a documented program using existing operator syntax.
    parameters:
      source:
        type: str
    returns:
      type: astx.Module
    """
    ArxIO.string_to_buffer("```\ntitle: Nullable operations\n```\n" + source)
    return Parser().parse(Lexer().lex())


def execute(source: str, path: Path) -> subprocess.CompletedProcess[str]:
    """
    title: Verify LLVM and execute a compiled nullable program.
    parameters:
      source:
        type: str
      path:
        type: Path
    returns:
      type: subprocess.CompletedProcess[str]
    """
    module = parse(source)
    builder = ArxBuilder()
    llvm.parse_assembly(builder.translate(module)).verify()
    builder.build(module, output_file=str(path))
    return subprocess.run(
        [str(path)], capture_output=True, text=True, check=False
    )


def test_nullable_arithmetic_and_refinement(tmp_path: Path) -> None:
    """
    title: Propagate nulls and invalidate branch proofs after local mutation.
    parameters:
      tmp_path:
        type: Path
    """
    source = """fn identity(x: i32 | none) -> i32:
  if is_valid(x):
    return x
  return 0
fn main() -> i32:
  var x: i32 | none = 6
  var missing: i32 | none = none
  assert expect_valid(x + 2) == 8
  assert expect_valid(2 + x) == 8
  assert expect_valid(x - 2) == 4
  assert expect_valid(x * 2) == 12
  assert expect_valid(x / 2) == 3
  assert expect_valid(x % 4) == 2
  assert expect_valid(-x) == -6
  assert expect_valid(+x) == 6
  assert expect_valid(x > 2)
  assert expect_valid(x >= 6)
  assert expect_valid(x < 7)
  assert expect_valid(x <= 6)
  assert expect_valid(x == 6)
  assert expect_valid(x != 7)
  assert is_null(missing / 0)
  assert is_null(missing % 0)
  assert is_null(missing + x)
  assert is_null(x == missing)
  assert is_null(-missing)
  assert is_valid(x) and x == 6
  assert is_null(missing) or missing == 7
  assert identity(x) == 6
  assert identity(missing) == 0
  if is_valid(x):
    var copy: i32 = x
    assert copy == 6
    assert is_valid(x)
    x = none
    assert is_null(x)
  x = 4
  if is_null(x):
    assert false
  else:
    assert x == 4
  if !is_null(x):
    assert x == 4
  while is_valid(x):
    assert x == 4
    x = none
  assert is_null(x)
  var real: f32 | none = 1.5
  assert expect_valid(real + 0.5) == 2.0
  assert expect_valid(-real) == -1.5
  var wide: f64 | none = real * 2.0
  assert expect_valid(wide) == 3.0
  return 0
"""
    result = execute(source, tmp_path / "nullable-operations")
    assert result.returncode == 0, result.stderr


def test_kleene_truth_tables_and_short_circuit(tmp_path: Path) -> None:
    """
    title: Check all truth-table cells and skip only decisive Boolean operands.
    parameters:
      tmp_path:
        type: Path
    """
    lines = [
        "fn explode() -> bool | none:",
        "  assert false",
        "  return none",
        "fn main() -> i32:",
    ]
    values = ("false", "true", "none")
    for index, value in enumerate(values):
        lines.append(f"  var b{index}: bool | none = {value}")
    for lhs in range(3):
        for rhs in range(3):
            for op, decisive in (("and", 0), ("or", 1)):
                expected = (
                    decisive
                    if decisive in (lhs, rhs)
                    else 2
                    if 2 in (lhs, rhs)
                    else 1 - decisive
                )
                expression = f"b{lhs} {op} b{rhs}"
                assertion = (
                    f"is_null({expression})"
                    if expected == 2
                    else f"expect_valid({expression}) == {values[expected]}"
                )
                lines.append(f"  assert {assertion}")
    lines.extend(
        [
            "  assert !expect_valid(b0 and explode())",
            "  assert expect_valid(b1 or explode())",
            "  assert is_null(!b2)",
            "  assert expect_valid(!b0)",
            "  assert !expect_valid(!b1)",
            "  assert !expect_valid(b2 and false)",
            "  assert expect_valid(true or b2)",
            "  return 0",
        ]
    )
    result = execute("\n".join(lines) + "\n", tmp_path / "kleene")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "body",
    [
        "if is_valid(x):\n    x = none\n    var y: i32 = x",
        "if is_valid(x):\n    var y: i32 = x\n  var z: i32 = x",
        "if is_null(x):\n    var y: i32 = x",
        "if is_valid(x):\n    while true:\n      var y: i32 = x",
        "while is_valid(x):\n    x = none\n    var y: i32 = x",
        "if is_valid(x):\n    if true:\n      x = none\n    var y: i32 = x",
    ],
)
def test_invalidated_or_unproven_reads_fail(body: str) -> None:
    """
    title: Do not carry stale proofs across mutations, joins or loop backedges.
    parameters:
      body:
        type: str
    """
    source = (
        "fn main() -> i32:\n  var x: i32 | none = 1\n  "
        + body
        + "\n  return 0\n"
    )
    with pytest.raises(SemanticError, match="cannot assign"):
        analyze(parse(source))


@pytest.mark.parametrize("expression", ["x / 0", "x % 0"])
def test_valid_division_errors_are_checked(
    expression: str, tmp_path: Path
) -> None:
    """
    title: Preserve fatal arithmetic diagnostics for valid nullable operands.
    parameters:
      expression:
        type: str
      tmp_path:
        type: Path
    """
    result = execute(
        "fn main() -> i32:\n  var x: i32 | none = 1\n"
        f"  var result: i32 | none = {expression}\n  return 0\n",
        tmp_path / "division-error",
    )
    assert result.returncode != 0
    assert "ARX-RUNTIME-ARITHMETIC-001" in result.stderr


def test_refined_nullable_mutation_does_not_change_storage_kind() -> None:
    """
    title: Refined scalar reads do not authorize scalar stores into aggregates.
    """
    with pytest.raises(SemanticError, match="nullable increment/decrement"):
        analyze(
            parse(
                "fn main() -> i32:\n  var x: i32 | none = 1\n"
                "  if is_valid(x):\n    ++x\n  return 0\n"
            )
        )


def test_all_numeric_nullable_payloads_execute(tmp_path: Path) -> None:
    """
    title: Exercise dynamic nullable addition for every numeric payload width.
    parameters:
      tmp_path:
        type: Path
    """
    types = (
        "i8",
        "i16",
        "i32",
        "i64",
        "u8",
        "u16",
        "u32",
        "u64",
        "f16",
        "f32",
        "f64",
    )
    source = "".join(
        f"fn twice_{name}(x: {name} | none) -> {name} | none:\n"
        "  return x + x\n"
        for name in types
    )
    source += "fn main() -> i32:\n"
    for name in types:
        source += (
            f"  assert expect_valid(twice_{name}(cast(2, {name}))) "
            f"== cast(4, {name})\n"
            f"  assert is_null(twice_{name}(none))\n"
        )
    source += "  return 0\n"
    result = execute(source, tmp_path / "nullable-numeric-widths")
    assert result.returncode == 0, result.stderr
