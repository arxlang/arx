"""
title: >-
  Compiled unified data files, nullable DataFrames and Parquet scan options.
"""

import subprocess

from datetime import date, datetime, time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from irx.record_batch import Parquet, ParquetOptions

from .test_arrow_interop import HAS_NATIVE, compile_program

pytestmark = pytest.mark.skipif(
    not HAS_NATIVE, reason="native compiler required"
)

FRAME = (
    "dataframe[id:u64 | none, label:str | none, "
    "day:date | none, clock:time | none, stamp:timestamp | none]"
)


def test_compiled_nullable_file_conversion(tmp_path: Path) -> None:
    """
    title: >-
      Nullable unsigned, string and temporal columns survive compiled casts.
    parameters:
      tmp_path:
        type: Path
    """
    source = f"""
import (Parquet, ParquetOptions, RecordBatch, Schema) from stdlib.arrow

fn keep(frame: {FRAME}) -> {FRAME}:
  return frame

fn main() -> i32:
  var source: Parquet = Parquet()
  var target: Parquet = Parquet()
  var options: ParquetOptions = ParquetOptions()
  options.set_int("atomic", 1)
  source.open_read("input.parquet", batch_size=2)
  var schema: Schema = Schema()
  schema.add("id", 7, true)
  schema.add("label", 11, true)
  schema.add("day", 13, true)
  schema.add("clock", 21, true)
  schema.add("stamp", 17, true)
  target.open_write_options("output.parquet", schema, options)
  while source.next():
    var batch: RecordBatch = source.batch()
    var frame: {FRAME} = cast(batch, {FRAME})
    var first: u64 = batch.get_u64(0, 0)
    batch.close()
    var alias: {FRAME} = keep(frame)
    var converted: RecordBatch = cast(alias, RecordBatch)
    assert converted.get_u64(0, 0) == first
    target.write(converted)
  target.close()
  source.close()
  return 0
"""
    binary = tmp_path / "convert"
    compile_program(source, binary)
    batch = pa.record_batch(
        [
            pa.array([2**64 - 1, None, 1], type=pa.uint64()),
            pa.array(["λ", None, ""], type=pa.string()),
            pa.array(
                [date(2025, 1, 1), None, date(1970, 1, 1)], type=pa.date32()
            ),
            pa.array([time(1, 2, 3), None, time(0)], type=pa.time64("us")),
            pa.array(
                [datetime(2025, 1, 1), None, datetime(1970, 1, 1)],
                type=pa.timestamp("us"),
            ),
        ],
        names=["id", "label", "day", "clock", "stamp"],
    )
    pq.write_table(pa.Table.from_batches([batch]), tmp_path / "input.parquet")
    result = subprocess.run(
        [str(binary)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert pq.read_table(tmp_path / "output.parquet").equals(
        pa.Table.from_batches([batch])
    )


def test_compiled_nullable_literal_and_filter(tmp_path: Path) -> None:
    """
    title: Construct nullable literals and push a native predicate into a scan.
    parameters:
      tmp_path:
        type: Path
    """
    source = """
import (Parquet, ParquetOptions, RecordBatch) from stdlib.arrow
type Frame = dataframe[id:i64 | none, label:str | none]
fn main() -> i32:
  var frame: Frame = dataframe({id: [1, none, 3], label: ["a", none, "c"]})
  var batch: RecordBatch = cast(frame, RecordBatch)
  var target: Parquet = Parquet()
  target.open_write("literal.parquet", batch.schema())
  target.write(batch)
  target.close()
  var source: Parquet = Parquet()
  var options: ParquetOptions = ParquetOptions()
  options.set_text("column", "label")
  options.where("id", "gt", "1", "int64")
  source.open_read_options("literal.parquet", options)
  var rows: i64 = 0
  while source.next():
    var result: RecordBatch = source.batch()
    rows = rows + result.nrows()
  source.close()
  print(rows)
  return 0
"""
    binary = tmp_path / "literal"
    compile_program(source, binary)
    result = subprocess.run(
        [str(binary)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1"
    assert pq.read_table(tmp_path / "literal.parquet").to_pydict() == {
        "id": [1, None, 3],
        "label": ["a", None, "c"],
    }


def test_compiled_recursive_copy_with_encryption(tmp_path: Path) -> None:
    """
    title: >-
      Compiled programs copy recursive batches and use caller-configured
      encryption.
    parameters:
      tmp_path:
        type: Path
    """
    source = """
import (Parquet, ParquetOptions, RecordBatch) from stdlib.arrow
fn main() -> i32:
  var reader: Parquet = Parquet()
  var writer: Parquet = Parquet()
  var options: ParquetOptions = ParquetOptions()
  options.encryption_key_hex("30313233343536373839616263646566")
  reader.open_read("rich.parquet")
  writer.open_write_options("encrypted.parquet", reader.schema(), options)
  while reader.next():
    var batch: RecordBatch = reader.batch()
    writer.write(batch)
  writer.close()
  reader.close()
  return 0
"""
    batch = pa.record_batch(
        [
            pa.array([[b"a", None], None, []], type=pa.list_(pa.binary())),
            pa.array([b"0" * 16, None, b"1" * 16], type=pa.uuid()),
            pa.array(['{"key":1}', None, "[]"], type=pa.json_()),
        ],
        names=["items", "uuid", "json"],
    )
    # Keep the original item name, not Parquet's default rename.
    pq.write_table(
        pa.Table.from_batches([batch]),
        tmp_path / "rich.parquet",
        use_compliant_nested_type=False,
    )
    binary = tmp_path / "encrypted-copy"
    compile_program(source, binary)
    result = subprocess.run(
        [str(binary)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    with Parquet() as reader:
        reader.open_read(
            tmp_path / "encrypted.parquet",
            options=ParquetOptions(encryption_key=b"0123456789abcdef"),
        )
        result_batch = reader.next_batch()
        assert result_batch is not None
        assert result_batch.to_arrow().equals(batch, check_metadata=True)
        result_batch.release()
