"""
title: CSV and checked DataFrame conversion integration regressions.
"""

import subprocess

from pathlib import Path

import pytest

from irx.analysis import SemanticError
from irx.builder.runtime.errors import parse_runtime_failure_output

from .test_arrow_interop import HAS_NATIVE, compile_program

pytestmark = pytest.mark.skipif(
    not HAS_NATIVE, reason="native compiler required"
)

PIPELINE = """
import (CSVReader, CSVWriter, Schema) from stdlib.arrow
import RecordBatch as Batch from stdlib.arrow

fn keep(frame: dataframe[id:i64]) -> dataframe[id:i64]:
  return frame

fn convert(frame: dataframe[id:i64]) -> Batch:
  return cast(frame, Batch)

fn main() -> i32:
  var reader: CSVReader = CSVReader()
  reader.open_file("input.csv", block_size=128)
  var schema: Schema = Schema()
  schema.add("id", 3, false)
  var writer: CSVWriter = CSVWriter(schema)
  writer.open_file("output.csv")
  var rows: i64 = 0
  while reader.next():
    var batch: Batch = reader.batch()
    var frame: dataframe[id:i64] = cast(batch, dataframe[id:i64])
    batch.close()
    var alias: dataframe[id:i64] = keep(frame)
    frame = alias
    var result: Batch = convert(alias)
    rows = rows + result.nrows()
    writer.write(result)
  writer.close()
  reader.close()
  print(rows)
  return 0
"""


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    title: >-
      Compile once through parsing, analysis, LLVM verification and linking.
    parameters:
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: Path
    """
    binary = tmp_path_factory.mktemp("csv-pipeline") / "csv"
    compile_program(PIPELINE, binary)
    return binary


def test_csv_dataframe_roundtrip(tmp_path: Path, pipeline: Path) -> None:
    """
    title: Process every batch and preserve aliases, replacements and returns.
    parameters:
      tmp_path:
        type: Path
      pipeline:
        type: Path
    """
    contents = "id\n" + "".join(f"{row}\n" for row in range(1000))
    (tmp_path / "input.csv").write_text(contents, encoding="utf-8")
    result = subprocess.run(
        [str(pipeline)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1000"
    assert (tmp_path / "output.csv").read_text().replace('"', "") == contents


@pytest.mark.parametrize(
    "contents,message",
    [
        ("id\n1\n\n", "null values"),
        ("id\ntext\n", "keep this data"),
        ("other\n1\n", "expected"),
        ("id\n1.5\n", "expected"),
    ],
)
def test_compiled_conversion_reports_data_errors(
    tmp_path: Path,
    pipeline: Path,
    contents: str,
    message: str,
) -> None:
    """
    title: >-
      Data-dependent failures use structured Arrow errors, not pointer casts.
    parameters:
      tmp_path:
        type: Path
      pipeline:
        type: Path
      contents:
        type: str
      message:
        type: str
    """
    (tmp_path / "input.csv").write_text(contents)
    result = subprocess.run(
        [str(pipeline)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "ARX-RUNTIME-ARROW-001" in result.stderr
    assert message in result.stderr
    assert parse_runtime_failure_output(result.stderr) is not None


def test_unregistered_recordbatch_name_is_not_a_capability(
    tmp_path: Path,
) -> None:
    """
    title: A user class with the same name cannot activate a native conversion.
    parameters:
      tmp_path:
        type: Path
    """
    source = """
class RecordBatch:
  ```
  title: Not the native RecordBatch
  ```
  value: i32 = 1
fn main() -> i32:
  var batch: RecordBatch = RecordBatch()
  var frame: dataframe[id:i64] = cast(batch, dataframe[id:i64])
  return 0
"""
    with pytest.raises(SemanticError):
        compile_program(source, tmp_path / "fake")
