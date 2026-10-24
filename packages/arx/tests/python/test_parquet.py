"""
title: Compiled unified file APIs and checked Parquet DataFrame conversion.
"""

import subprocess

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from irx.builder.runtime.exceptions import parse_exception_output

from .test_arrow_interop import HAS_NATIVE, compile_program

pytestmark = pytest.mark.skipif(
    not HAS_NATIVE, reason="native compiler required"
)

PIPELINE = """
import ParquetStream from stdlib.parquet
import CSVStream from stdlib.csv
import (RecordBatch, Schema) from stdlib.arrow

fn keep(frame: dataframe[id:i64]) -> dataframe[id:i64]:
  return frame

fn check_mode(v: i64, r: ParquetStream, w: ParquetStream, \
c: CSVStream, b: RecordBatch) -> none:
  if v == 1001:
    w.next()
    return none
  else:
    if v == 1002:
      r.write(b)
      return none
    else:
      if v == 1003:
        c.open_write("sentinel", w.schema())
        return none
      else:
        if v == 1004:
          c.next()
          return none
        else:
          return none

fn output_schema() -> Schema:
  var schema: Schema = Schema()
  schema.add("id", "int64", false)
  return schema

fn main() -> i32:
  var source: ParquetStream = ParquetStream()
  source.open_read("input.parquet", batch_size=7)
  var input_schema: Schema = source.schema()
  var schema: Schema = Schema()
  schema.add("id", "int64", false)
  var output: ParquetStream = ParquetStream()
  output.open_write("output.parquet", schema, row_group_size=11)
  var csv: CSVStream = CSVStream()
  csv.open_write("output.csv", schema)
  schema.close()
  var rows: i64 = 0
  while source.next():
    var batch: RecordBatch = source.batch()
    var frame: dataframe[id:i64] = cast(batch, dataframe[id:i64])
    batch.close()
    var alias: dataframe[id:i64] = keep(frame)
    frame = alias
    var result: RecordBatch = cast(frame, RecordBatch)
    check_mode(result.get_i64(0, 0), source, output, csv, result)
    output.write(result)
    csv.write(result)
    rows = rows + result.nrows()
  source.close()
  output.close()
  output.close()
  csv.close()
  var actual: Schema = output_schema()
  output.open_read_as("output.parquet", actual, batch_size=3)
  csv.open_read_as("output.csv", actual, block_size=32)
  var csv_rows: i64 = 0
  while csv.next():
    var copied: RecordBatch = csv.batch()
    csv_rows = csv_rows + copied.nrows()
  assert csv_rows == rows
  assert output.schema().equals(actual)
  assert input_schema.nfields() == 1
  csv.close()
  output.close()
  print(rows)
  return 0

"""


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    title: Compile and LLVM-verify the unified APIs once for all data cases.
    parameters:
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: Path
    """
    binary = tmp_path_factory.mktemp("parquet-pipeline") / "parquet"
    compile_program(PIPELINE, binary)
    return binary


def run_pipeline(
    pipeline: Path, tmp_path: Path, table: pa.Table
) -> subprocess.CompletedProcess[str]:
    """
    title: Execute a compiled pipeline against multiple Parquet row groups.
    parameters:
      pipeline:
        type: Path
      tmp_path:
        type: Path
      table:
        type: pa.Table
    returns:
      type: subprocess.CompletedProcess[str]
    """
    pq.write_table(table, tmp_path / "input.parquet", row_group_size=13)
    return subprocess.run(
        [str(pipeline)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("rows", [0, 1, 101])
def test_compiled_roundtrip(pipeline: Path, tmp_path: Path, rows: int) -> None:
    """
    title: Convert every batch with scoped ownership and both unified formats.
    parameters:
      pipeline:
        type: Path
      tmp_path:
        type: Path
      rows:
        type: int
    """
    expected = pa.table({"id": pa.array(range(rows), type=pa.int64())})
    result = run_pipeline(pipeline, tmp_path, expected)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(rows)
    actual = pq.read_table(tmp_path / "output.parquet")
    expected = expected.cast(pa.schema([pa.field("id", pa.int64(), False)]))
    assert actual.equals(expected, check_metadata=True)


@pytest.mark.parametrize(
    "values,message",
    [
        ([1001], "requires read"),
        ([1002], "requires write"),
        ([1003], "requires closed"),
        ([1004], "requires read"),
        ([None], "null values"),
    ],
)
def test_compiled_failures(
    pipeline: Path, tmp_path: Path, values: list[int | None], message: str
) -> None:
    """
    title: >-
      Wrong-mode and conversion failures use structured runtime diagnostics.
    parameters:
      pipeline:
        type: Path
      tmp_path:
        type: Path
      values:
        type: list[int | None]
      message:
        type: str
    """
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"untouched")
    result = run_pipeline(
        pipeline, tmp_path, pa.table({"id": pa.array(values, type=pa.int64())})
    )
    assert result.returncode != 0
    failure = parse_exception_output(result.stderr)
    assert failure is not None
    assert failure.code == "ARX-RUNTIME-ARROW-001"
    assert message in result.stderr
    assert sentinel.read_bytes() == b"untouched"
