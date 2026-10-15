"""
title: Native owned interchange and extent-checked source buffer construction.
"""

from pathlib import Path

import pytest

from arx.codegen import ArxBuilder
from irx.analysis import analyze
from irx.diagnostics import SemanticError
from llvmlite import binding as llvm

from .test_nullable_operations import execute, parse
from .test_tabular_values import example_body


def test_interchange_example(tmp_path: Path) -> None:
    """
    title: Execute offset bitmaps and values that outlive their C Data carrier.
    parameters:
      tmp_path:
        type: Path
    """
    source = example_body("columnar_interchange")
    text = ArxBuilder().translate(parse(source))
    llvm.parse_assembly(text).verify()
    assert "irx_arrow_c_data_release" in text
    result = execute(source, tmp_path / "interchange")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "expression",
    [
        "export_c_data(1)",
        "array_from_c_data(array[i32](1), field[x:i32])",
        "array_with_validity(array[i32](1), array[i32](1), 0)",
        "array_from_buffers(field[x:string], array[u8](), array[u8](), 0, 0)",
    ],
)
def test_interchange_rejects_invalid_types(expression: str) -> None:
    """
    title: Reject unsupported layouts and unmanaged inputs before lowering.
    parameters:
      expression:
        type: str
    """
    with pytest.raises(SemanticError):
        analyze(parse(f"fn main() -> i32:\n  {expression}\n  return 0\n"))
