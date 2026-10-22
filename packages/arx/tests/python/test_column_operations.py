"""
title: Extended compiled nullable and Series operations.
"""

import subprocess

from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pytest

from .test_arrow_interop import HAS_NATIVE, compile_program

pytestmark = pytest.mark.skipif(
    not HAS_NATIVE, reason="native compiler required"
)


def test_extended_column_operations(tmp_path: Path) -> None:
    """
    title: >-
      Compile reductions, slicing, unary kernels, widening and null values.
    parameters:
      tmp_path:
        type: Path
    """
    source = """
var global_value: nullable[i32] = none

fn missing() -> nullable[i32]:
  return none

fn take(value: nullable[i32] = none) -> bool:
  return is_null(value)

fn main() -> i32:
  assert take()
  assert take(none)
  assert take(value=none)
  assert is_null(global_value)
  global_value = 7
  assert fill_null(global_value, 0) == 7
  var absent: nullable[i32] = none
  assert is_null(absent)
  absent = 3
  absent = none
  assert is_null(absent)
  assert is_null(missing())
  var frame: dataframe[x:i32 | none] = dataframe({x:[1, none, 3, 4]})
  var column: series[i32 | none] = frame.x
  var negative: series[i32 | none] = -column
  assert fill_null(negative[2], 0) == -3
  assert is_null(negative[1])
  var positive: series[i32 | none] = +column
  assert fill_null(positive[0], 0) == 1
  var reverse: series[i32 | none] = column[::-1]
  assert fill_null(reverse[0], 0) == 4
  assert is_null(reverse[2])
  var selected: series[i32 | none] = column[1:4:2]
  assert is_null(selected[0])
  assert fill_null(selected[1], 0) == 4
  var empty: series[i32 | none] = column[2:1]
  assert series_count(empty) == 0
  assert is_null(series_sum(empty))
  assert series_count(column) == 3
  assert fill_null(series_sum(column), cast(0, i64)) == 8
  assert fill_null(series_min(column), 0) == 1
  assert fill_null(series_max(column), 0) == 4
  var wider: series[i64 | none] = column + cast(2, i64)
  assert fill_null(wider[0], cast(0, i64)) == 3
  var mask: series[bool] = !is_null(column)
  assert fill_null(series_any(mask), false)
  assert !fill_null(series_all(mask), true)
  var alias: series[i32 | none] = column
  column[1] = 9
  assert fill_null(alias[1], 0) == 9
  assert is_null(frame.x[1])
  column[0] = none
  assert is_null(alias[0])
  assert fill_null(reverse[3], 0) == 1
  return 0
"""
    executable = tmp_path / "columns"
    compile_program(source, executable)
    result = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_rich_dataframe_literals(tmp_path: Path) -> None:
    """
    title: >-
      Compile nested, decimal, binary and temporal literals into exact IPC.
    parameters:
      tmp_path:
        type: Path
    """
    annotation = (
        "dataframe[amount:decimal128[8,2], items:arrow_list[nullable[i32]], "
        "record:arrow_struct[a:i32,b:nullable[str]], bytes:binary[2], "
        'time:timestamp["ns","UTC"], labels:dictionary[i8,str], '
        "pairs:arrow_map[str,nullable[i32]]]"
    )
    source = """
import (RecordBatch, IPCWriter) from stdlib.arrow
fn main() -> i32:
  var data: ANNOTATION = dataframe({
    amount:["1.25", "-2.00"], items:[[1,none],[]],
    record:[[1,"hi"],[2,none]], bytes:["ab","cd"], time:[1,2],
    labels:["x","x"], pairs:[[["a",1],["b",none]],[]]
  })
  var labels: series[dictionary[i8,str]] = data.labels[::-1]
  assert series_count(labels) == 2
  assert !fill_null(series_any(is_null(labels)), true)
  var batch: RecordBatch = cast(data, RecordBatch)
  var writer: IPCWriter = IPCWriter(batch.schema())
  writer.open_file("literal.arrow")
  writer.write(batch)
  writer.close()
  return 0
"""
    source = source.replace("ANNOTATION", annotation)
    executable = tmp_path / "literal"
    compile_program(source, executable)
    result = subprocess.run(
        [str(executable)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    with pa.ipc.open_file(tmp_path / "literal.arrow") as reader:
        table = reader.read_all()
    assert table["amount"].to_pylist() == [Decimal("1.25"), Decimal("-2.00")]
    assert table["items"].to_pylist() == [[1, None], []]
    assert table["record"].to_pylist() == [
        {"a": 1, "b": "hi"},
        {"a": 2, "b": None},
    ]
    assert table["bytes"].to_pylist() == [b"ab", b"cd"]
    assert table["time"].cast(pa.int64()).to_pylist() == [1, 2]
    assert table["labels"].type == pa.dictionary(pa.int8(), pa.string())
    assert table["pairs"].to_pylist() == [[("a", 1), ("b", None)], []]
