"""
title: Canonical format modules and native DataFrame I/O through all stages.
"""

import subprocess

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from irx.analysis import SemanticError
from irx.builder.runtime.errors import parse_runtime_failure_output

from .test_arrow_interop import HAS_NATIVE, compile_program

pytestmark = pytest.mark.skipif(
    not HAS_NATIVE, reason="native compiler required"
)


@pytest.fixture(scope="module")
def convenience(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    title: >-
      Compile aliases, namespace calls, predicates, options and table casts.
    parameters:
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: Path
    """
    binary = tmp_path_factory.mktemp("table-io") / "convenience"
    compile_program(
        """
import (read_csv, write_csv as save_csv) from stdlib.csv
import stdlib.parquet as parquet
import (ParquetOptions, ParquetFilter, where) from stdlib.parquet
fn main() -> i32:
  var frame: dataframe[...] = read_csv("input.csv", block_size=32)
  var options: ParquetOptions = ParquetOptions(compression="gzip", atomic=true)
  parquet.write_parquet(\
    frame=frame, path="output.parquet", options=options,\
    compression="snappy", row_group_size=1\
  )
  var base: ParquetFilter = where("id", ">", 1)
  var selected: ParquetFilter = base.and_where("active", "==", true)
  var result: dataframe[...] = parquet.read_parquet(\
    "output.parquet", columns=["name"], filters=selected, batch_size=1\
  )
  save_csv(result, "selected.csv", delimiter=";", lineterminator="\\r\\n")
  var snapshot: dataframe[...] = parquet.read_parquet(\
    "output.parquet", filters=base\
  )
  save_csv(snapshot, "base.csv")
  var direct: dataframe[...] = parquet.read_parquet(\
    "output.parquet", filters=parquet.where("active", "is_null")\
  )
  save_csv(direct, "nulls.csv")
  var floats: ParquetFilter = where("id", ">", cast(1.5, f64))
  var bounded: ParquetFilter = floats.and_where("id", "<=", 3)
  var named: ParquetFilter = bounded.and_where("name", "==", "c")
  var exact: dataframe[...] = parquet.read_parquet(\
    "output.parquet", filters=named\
  )
  assert exact.nrows() == 1
  return 0
""",
        binary,
    )
    return binary


def test_compiled_module_convenience(
    tmp_path: Path, convenience: Path
) -> None:
    """
    title: Format functions preserve all rows and typed immutable predicates.
    parameters:
      tmp_path:
        type: Path
      convenience:
        type: Path
    """
    source = "id,name,active\n1,a,true\n2,b,false\n3,c,true\n4,d,\n"
    (tmp_path / "input.csv").write_text(source)
    run = subprocess.run(
        [str(convenience)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    assert (tmp_path / "selected.csv").read_bytes() == b'"name"\r\n"c"\r\n'
    assert len((tmp_path / "base.csv").read_text().splitlines()) == 4
    assert len((tmp_path / "nulls.csv").read_text().splitlines()) == 2
    assert pq.ParquetFile(tmp_path / "output.parquet").num_row_groups == 4
    assert (
        pq.ParquetFile(tmp_path / "output.parquet")
        .metadata.row_group(0)
        .column(0)
        .compression
        == "SNAPPY"
    )


def test_compiled_streaming_frames(tmp_path: Path) -> None:
    """
    title: Streaming adapters retain independent frames and canonical schemas.
    parameters:
      tmp_path:
        type: Path
    """
    binary = tmp_path / "stream"
    compile_program(
        """
import CSV from stdlib.csv
import (Parquet, read_parquet, write_parquet) from stdlib.parquet
import Schema from stdlib.arrow
fn main() -> i32:
  var schema: Schema = Schema()
  schema.add("id", "int64", nullable=false)
  var source: CSV = CSV()
  source.open_read_as("input.csv", schema, block_size=16)
  var destination: Parquet = Parquet()
  destination.open_write("output.parquet", source.schema(), row_group_size=2)
  var csv_copy: CSV = CSV()
  csv_copy.open_write("copy.csv", schema)
  while source.next():
    var frame: dataframe[...] = source.frame()
    var typed: dataframe[id:i64] = cast(frame, dataframe[id:i64])
    destination.write(typed)
    csv_copy.write(typed)
  source.close()
  destination.close()
  csv_copy.close()
  write_parquet(read_parquet("output.parquet"), "copy.parquet")
  return 0
""",
        binary,
    )
    (tmp_path / "input.csv").write_text(
        "id\n" + "".join(f"{i}\n" for i in range(30))
    )
    run = subprocess.run(
        [str(binary)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    assert pq.read_table(tmp_path / "copy.parquet").column(
        0
    ).to_pylist() == list(range(30))
    assert (tmp_path / "copy.csv").read_text().splitlines()[1:] == [
        str(value) for value in range(30)
    ]


@pytest.fixture(scope="module")
def checked_cast(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    title: Compile a direct dynamic-to-static table cast across every chunk.
    parameters:
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: Path
    """
    binary = tmp_path_factory.mktemp("table-cast") / "cast"
    compile_program(
        """
import read_parquet from stdlib.parquet
import write_csv from stdlib.csv
fn main() -> i32:
  var input: dataframe[...] = read_parquet("input.parquet", batch_size=1)
  var checked: dataframe[id:i64] = cast(input, dataframe[id:i64])
  write_csv(checked, "output.csv")
  return 0
""",
        binary,
    )
    return binary


@pytest.mark.parametrize("null", [False, True])
def test_compiled_table_cast_checks_later_chunks(
    tmp_path: Path, checked_cast: Path, null: bool
) -> None:
    """
    title: Nulls in a later row group fail before any output is opened.
    parameters:
      tmp_path:
        type: Path
      checked_cast:
        type: Path
      null:
        type: bool
    """
    pq.write_table(
        pa.table({"id": pa.array([1, None if null else 2], type=pa.int64())}),
        tmp_path / "input.parquet",
        row_group_size=1,
    )
    run = subprocess.run(
        [str(checked_cast)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if not null:
        assert run.returncode == 0, run.stderr
        assert (tmp_path / "output.csv").read_text().splitlines()[-2:] == [
            "1",
            "2",
        ]
        return
    assert run.returncode != 0
    failure = parse_runtime_failure_output(run.stderr)
    assert failure is not None
    assert "null" in failure.message
    assert not (tmp_path / "output.csv").exists()


@pytest.mark.parametrize(
    "call",
    [
        "read_csv(1)",
        'read_csv("in", unknown=true)',
        'read_csv("in", columns=[])',
        'read_csv("in", columns=["id", "id"])',
        'read_csv("in", columns=["id", 1])',
        'read_csv("in", block_size=false)',
        'read_csv("in", schema=1)',
        'write_csv(1, "out")',
        'read_parquet("in", filters="id > 1")',
        'where("id", "==", none)',
    ],
)
def test_invalid_table_io_fails_during_analysis(
    tmp_path: Path, call: str
) -> None:
    """
    title: Unsupported option names and types never reach the native boundary.
    parameters:
      tmp_path:
        type: Path
      call:
        type: str
    """
    source = f"""
import (read_csv, write_csv) from stdlib.csv
import (read_parquet, where) from stdlib.parquet
fn main() -> i32:
  {call}
  return 0
"""
    with pytest.raises(SemanticError):
        compile_program(source, tmp_path / "invalid")


def test_compiled_table_argument_order_and_return(tmp_path: Path) -> None:
    """
    title: >-
      Named temporary inputs evaluate once in source order and survive return.
    parameters:
      tmp_path:
        type: Path
    """
    binary = tmp_path / "order"
    compile_program(
        """
import (write_csv, read_csv) from stdlib.csv
fn destination() -> str:
  print(1)
  return "order.csv"
fn source() -> dataframe[...]:
  print(2)
  return read_csv("input.csv")
fn main() -> i32:
  write_csv(path=destination(), frame=source())
  return 0
""",
        binary,
    )
    (tmp_path / "input.csv").write_text("id,name\n1,λ\n2,世界\n")
    run = subprocess.run(
        [str(binary)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.splitlines() == ["1", "2"]
    assert "世界" in (tmp_path / "order.csv").read_text()
