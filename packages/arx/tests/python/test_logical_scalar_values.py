"""
title: Logical scalar, nested array and tabular value paths through Arx.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arx.codegen import ArxBuilder
from irx.analysis import analyze
from irx.diagnostics import SemanticError
from llvmlite import binding as llvm

from .test_nullable_operations import execute, parse
from .test_tabular_values import example_body


@pytest.mark.parametrize(
    "name",
    [
        "logical_scalar_owners",
        "nested_columnar_values",
        "logical_value_families",
    ],
)
def test_logical_value_examples(name: str, tmp_path: Path) -> None:
    """
    title: Extract owned nested values and transform typed tables.
    parameters:
      name:
        type: str
      tmp_path:
        type: Path
    """
    result = execute(example_body(name), tmp_path / name)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "source",
    [
        "array_from_buffer(array[i32](1))",
        "take_rows(record_batch[](2), array[i32](0))",
        "scalar[i32](3)",
        "scalar[list[item:i32]](array[i64](1))",
        "scalar[struct[x:i32]](none)",
        'scalar_field(scalar[string]("x"), "field")',
        'scalar[string | none]("x")',
        "scalar[null]()",
        'array[string](scalar[binary]("x"))',
        "scalar[dense_union(type_codes=[1])[a:i32]]"
        '("missing", scalar[i32]("1"))',
    ],
)
def test_scalar_diagnostics(source: str) -> None:
    """
    title: Invalid payload, nullability and field contracts fail in analysis.
    parameters:
      source:
        type: str
    """
    with pytest.raises(SemanticError):
        analyze(parse(f"fn main() -> i32:\n  {source}\n  return 0\n"))


def test_scalar_translation() -> None:
    """
    title: Translate scalar source with registered lifetime symbols.
    """
    module = parse(
        "fn main() -> i32:\n"
        '  var value: scalar[string] = scalar[string]("x")\n'
        '  assert scalar_text(value) == "x"\n  return 0\n'
    )
    output = ArxBuilder().translate(module)
    llvm.parse_assembly(output).verify()
    for symbol in (
        "irx_arrow_scalar_parse",
        "irx_arrow_scalar_release",
        "irx_arrow_runtime_has_feature",
    ):
        assert symbol in output
