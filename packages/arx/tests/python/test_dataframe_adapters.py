"""
title: Logical DataFrame literals and retained explicit compatibility adapters.
"""

from pathlib import Path

import pytest

from arx.codegen import ArxBuilder
from irx.analysis import analyze
from irx.diagnostics import SemanticError
from llvmlite import binding as llvm

from .test_nullable_operations import execute, parse
from .test_tabular_values import example_body


def test_dataframe_adapter_example(tmp_path: Path) -> None:
    """
    title: Execute nullable and nested legacy columns through typed adapters.
    parameters:
      tmp_path:
        type: Path
    """
    source = example_body("dataframe_adapters")
    output = ArxBuilder().translate(parse(source))
    llvm.parse_assembly(output).verify()
    assert "irx_arrow_table_new_typed" in output
    assert "irx_arrow_chunked_array_retain" in output
    result = execute(source, tmp_path / "adapters")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "expression",
    [
        "to_dataframe(array[i32](1))",
        "to_series(array[i32](1))",
        "to_chunked(chunked_array[i32]())",
    ],
)
def test_invalid_adapter(expression: str) -> None:
    """
    title: Reject wrong containers before handle reinterpretation.
    parameters:
      expression:
        type: str
    """
    with pytest.raises(SemanticError):
        analyze(parse(f"fn main() -> i32:\n  {expression}\n  return 0\n"))


def test_dynamic_dataframe_cannot_claim_static_columns() -> None:
    """
    title: Runtime schemas cannot be assigned to unchecked static types.
    """
    with pytest.raises(SemanticError):
        analyze(
            parse(
                "fn main() -> i32:\n"
                "  var rows: dataframe[wrong: i32] = "
                "to_dataframe(table[](0))\n  return 0\n"
            )
        )


def test_dataframe_rejects_inner_scalar_nullability() -> None:
    """
    title: Legacy columns cannot bypass the scalar nullable-owner contract.
    """
    with pytest.raises(SemanticError, match="optional column values"):
        analyze(
            parse(
                "fn invalid(value: dataframe[x: scalar[i32 | none]]) -> i32:\n"
                "  return 0\n"
            )
        )


@pytest.mark.parametrize(
    ("type_name", "operation"),
    [
        ("dataframe[...]", "to_table"),
        ("series[i32]", "to_chunked"),
    ],
)
def test_nullable_legacy_owner_requires_validity(
    type_name: str, operation: str
) -> None:
    """
    title: Reject nullable owner access until validity has been established.
    parameters:
      type_name:
        type: str
      operation:
        type: str
    """
    with pytest.raises(SemanticError):
        analyze(
            parse(
                f"fn invalid(value: {type_name} | none) -> i32:\n"
                f"  {operation}(value)\n  return 0\n"
            )
        )


def test_nullable_dataframe_cannot_claim_static_schema() -> None:
    """
    title: Optional runtime schemas cannot bypass checked projection.
    """
    with pytest.raises(SemanticError):
        analyze(
            parse(
                "fn invalid(value: dataframe[...] | none) -> i32:\n"
                "  var wrong: dataframe[id:i32] | none = value\n"
                "  return 0\n"
            )
        )


@pytest.mark.parametrize("type_name", ["dataframe[...]", "series[i32]"])
def test_absent_legacy_owner_fails_before_runtime_access(
    tmp_path: Path, type_name: str
) -> None:
    """
    title: Null legacy containers fail at the checked unwrap boundary.
    parameters:
      tmp_path:
        type: Path
      type_name:
        type: str
    """
    result = execute(
        f"fn main() -> i32:\n  var value: {type_name} | none = none\n"
        "  expect_valid(value)\n  return 0\n",
        tmp_path / "absent-legacy-owner",
    )
    assert result.returncode != 0
    assert "ARX-RUNTIME-NULL-001" in result.stderr
