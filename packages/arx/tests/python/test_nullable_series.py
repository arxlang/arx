"""
title: Compiled nullable scalar and Series contracts.
"""

import subprocess

from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pytest

from pyarrow import ipc

from .test_arrow_interop import HAS_NATIVE, compile_program

pytestmark = pytest.mark.skipif(
    not HAS_NATIVE, reason="native compiler required"
)


def test_nullable_series(tmp_path: Path) -> None:
    """
    title: Preserve nulls through scalar and Series kernels.
    parameters:
      tmp_path:
        type: Path
    """
    source = """
class Sample:
  ```
  title: Nullable field storage
  ```
  value: nullable[i32] = cast(none, nullable[i32])

  set: fn(self, value: i32) -> none:
    ```
    title: Set a present value
    ```
    self.value = value

  get: fn(self) -> nullable[i32]:
    ```
    title: Return a nullable field
    ```
    return self.value

keep: fn(value: nullable[i32]) -> nullable[i32]:
  return value

lift: fn(value: i32) -> nullable[i32]:
  return value

consume: fn(value: nullable[i32]) -> i32:
  return fill_null(value, 0)

values: fn() -> series[i32 | none]:
  frame: dataframe[x:i32 | none] = dataframe({x:[1, none, 3]})
  return frame.x

main: fn() -> i32:
  object: Sample = Sample()
  assert is_null(object.get())
  object.set(6)
  assert fill_null(object.get(), 0) == 6
  lifted: nullable[i32] = 4
  assert consume(3) == 3
  assert consume(lift(5)) == 5
  assert fill_null(lifted, 0) == 4
  column: series[i32 | none] = values()
  sum: series[i32 | none] = column + column
  value: nullable[i32] = keep(sum[0])
  assert fill_null(value, 0) == 2
  assert is_null(sum[1])
  assert fill_null(sum[2] + value, 0) == 8
  empty: nullable[i32] = cast(none, nullable[i32])
  assert is_null(empty)
  assert is_null(empty / cast(0, nullable[i32]))
  filled: series[i32] = fill_null(sum, 7)
  assert filled[1] == 7
  mask: series[bool] = is_null(sum)
  assert mask[1]
  assert !mask[0]
  equal: series[bool | none] = sum == column
  assert is_null(equal[1])
  assert !fill_null(equal[0], true)
  logical: series[bool | none] = equal || false
  assert is_null(logical[1])
  assert !fill_null(logical[0], true)
  offset: series[i32 | none] = column + 10
  assert fill_null(offset[2], 0) == 13
  return 0
"""
    binary = tmp_path / "nullable"
    compile_program(source, binary)
    result = subprocess.run(
        [str(binary)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_rich_static_schema(tmp_path: Path) -> None:
    """
    title: Preserve parameterized schemas and metadata across compiled casts.
    parameters:
      tmp_path:
        type: Path
    """

    frame = (
        "dataframe[amount:decimal128[12, 3] | none, "
        'stamp:timestamp["ns", "UTC"] | none, '
        "items:arrow_list[nullable[i32]] | none, "
        "category:dictionary[i8, str] | none, payload:binary[4] | none, "
        "record:arrow_struct[x:nullable[i32]] | none, "
        "mapping:arrow_map[str, nullable[i32]] | none, "
        "fixed:fixed_list[nullable[i32], 2] | none]"
    )
    source = f"""
import (RecordBatch, IPCReader, IPCWriter) from stdlib.arrow
identity: fn(frame: {frame}) -> {frame}:
  return frame
main: fn() -> i32:
  reader: IPCReader = IPCReader()
  reader.open_file("input.arrow")
  assert reader.next()
  batch: RecordBatch = reader.batch()
  frame: {frame} = cast(batch, {frame})
  batch.close()
  output: RecordBatch = cast(identity(frame), RecordBatch)
  writer: IPCWriter = IPCWriter(output.schema())
  writer.open_file("output.arrow")
  writer.write(output)
  writer.close()
  return 0
"""
    binary = tmp_path / "rich"
    compile_program(source, binary)
    fields = [
        pa.field("amount", pa.decimal128(12, 3), metadata={b"unit": b"EUR"}),
        pa.field("stamp", pa.timestamp("ns", "UTC")),
        pa.field("items", pa.list_(pa.int32())),
        pa.field("category", pa.dictionary(pa.int8(), pa.string())),
        pa.field("payload", pa.binary(4)),
        pa.field("record", pa.struct([pa.field("x", pa.int32())])),
        pa.field("mapping", pa.map_(pa.string(), pa.int32())),
        pa.field("fixed", pa.list_(pa.int32(), 2)),
    ]
    schema = pa.schema(fields, metadata={b"source": b"test"})
    batch = pa.record_batch(
        [
            pa.array([Decimal("1.250"), None], type=fields[0].type),
            pa.array([1, None], type=fields[1].type),
            pa.array([[1, None], None], type=fields[2].type),
            pa.array(["a", None], type=fields[3].type),
            pa.array([b"abcd", None], type=fields[4].type),
            pa.array([{"x": None}, None], type=fields[5].type),
            pa.array([[("a", 1), ("b", None)], None], type=fields[6].type),
            pa.array([[1, None], None], type=fields[7].type),
        ],
        schema=schema,
    )
    with ipc.new_file(tmp_path / "input.arrow", schema) as writer:
        writer.write_batch(batch)
    result = subprocess.run(
        [str(binary)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    with ipc.open_file(tmp_path / "output.arrow") as reader:
        assert reader.get_batch(0).equals(batch, check_metadata=True)


@pytest.mark.parametrize(
    "expression,message",
    [
        ("fill_null(left.x[-1], 0)", "out of bounds"),
        ("fill_null(left.x[2], 0)", "out of bounds"),
        ("fill_null((left.x / 0)[0], 0)", "divide by zero"),
        ("fill_null((left.x + 2147483647)[0], 0)", "overflow"),
        ("fill_null((left.x + right.x)[0], 0)", "lengths must match"),
    ],
)
def test_compiled_kernel_failures(
    tmp_path: Path, expression: str, message: str
) -> None:
    """
    title: Native failures report errors rather than reading invalid outputs.
    parameters:
      tmp_path:
        type: Path
      expression:
        type: str
      message:
        type: str
    """
    source = f"""
main: fn() -> i32:
  left: dataframe[x:i32 | none] = dataframe({{x:[1, none]}})
  right: dataframe[x:i32 | none] = dataframe({{x:[1]}})
  return {expression}
"""
    binary = tmp_path / "failure"
    compile_program(source, binary)
    result = subprocess.run(
        [str(binary)], capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert message in result.stderr
