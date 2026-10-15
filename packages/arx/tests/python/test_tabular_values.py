"""
title: Typed tabular owners from source through native execution.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arx.codegen import ArxBuilder
from irx.analysis import analyze
from irx.diagnostics import SemanticError
from llvmlite import binding as llvm

from .test_nullable_operations import execute, parse


def example_body(name: str) -> str:
    """
    title: Load a documented executable example without its module preamble.
    parameters:
      name:
        type: str
    returns:
      type: str
    """
    path = Path(__file__).parents[4] / "examples" / f"{name}.x"
    return path.read_text().split("```", 2)[2].lstrip("\n")


PROGRAM = example_body("columnar_tables")


def test_tabular_translation_contract() -> None:
    """
    title: Activate opaque native features and verify all generated LLVM.
    """
    builder = ArxBuilder()
    text = builder.translate(parse(PROGRAM))
    llvm.parse_assembly(text).verify()
    for symbol in (
        "irx_arrow_batch_new_typed",
        "irx_arrow_table_column_checked",
        "irx_arrow_table_select",
        "irx_arrow_table_set_column",
        "irx_arrow_table_to_batch",
        "irx_arrow_record_batch_retain",
    ):
        assert symbol in text


def test_tabular_execution(tmp_path: Path) -> None:
    """
    title: Construct and transform typed and dynamic containers.
    parameters:
      tmp_path:
        type: Path
    """
    result = execute(PROGRAM, tmp_path / "tabular")
    assert result.returncode == 0, result.stderr


def test_tabular_batch_operations_and_nullable_lifetimes(
    tmp_path: Path,
) -> None:
    """
    title: Preserve metadata and child owners across parent replacement.
    parameters:
      tmp_path:
        type: Path
    """
    result = execute(
        example_body("columnar_table_owners"),
        tmp_path / "tabular-lifetimes",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("record_batch[a: i32]()", "row count"),
        ("record_batch[a: i32](1, array[f64](1.0))", "column type"),
        (
            "record_batch[a: i32, a: i32](0, array[i32](), array[i32]())",
            "duplicate",
        ),
        ('column(batch, "absent")', "unknown column"),
        ('select_columns(batch, "a", "a")', "duplicate"),
        ('rename_columns(batch, "a", "b")', "one name"),
        ("add_column(batch, field[a: i32], array[i32](1))", "duplicate"),
        (
            "replace_column(batch, field[a: i32], array[f64](1.0))",
            "does not match",
        ),
        ('column(runtime_schema(batch), "a")', "static schema"),
        ("column_as(batch, 0, datatype[i32])", "literal field"),
        ("to_table(to_table(batch))", "other container"),
        ("table_combine_chunks(batch)", "requires a table"),
        ("num_rows()", "argument count"),
    ],
)
def test_invalid_tabular_signatures(expression: str, message: str) -> None:
    """
    title: Reject unsupported schemas and signatures before native lowering.
    parameters:
      expression:
        type: str
      message:
        type: str
    """
    with pytest.raises(SemanticError, match=message):
        analyze(
            parse(
                "fn main() -> i32:\n"
                "  var batch: record_batch[a: i32] ="
                " record_batch[a: i32](1, array[i32](1))\n"
                f"  {expression}\n  return 0\n"
            )
        )


@pytest.mark.parametrize(
    "expression",
    [
        "record_batch[a: i32](2, array[i32](1))",
        "record_batch[](-1)",
        "slice_rows(batch, 2, 1)",
        "slice_rows(batch, -1, 0)",
        "slice_rows(batch, 1, 9223372036854775807)",
        "column_as(runtime_schema(batch), 0, field[a: f64])",
        "column_as(runtime_schema(batch), 0, field[a: i32 | none])",
        "column_as(runtime_schema(batch), 1, field[a: i32])",
        "add_column(batch, field[b: i32], array[i32]())",
    ],
)
def test_tabular_runtime_failures(expression: str, tmp_path: Path) -> None:
    """
    title: Check dynamic bounds and schema before reading any output owner.
    parameters:
      expression:
        type: str
      tmp_path:
        type: Path
    """
    result = execute(
        "fn main() -> i32:\n"
        "  var batch: record_batch[a: i32] ="
        " record_batch[a: i32](1, array[i32](1))\n"
        f"  {expression}\n  return 0\n",
        tmp_path / "tabular-error",
    )
    assert result.returncode != 0
    assert "Arrow runtime operation failed" in result.stderr
