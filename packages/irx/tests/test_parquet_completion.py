"""
title: Reconstructed datasets and typed Hive keys.
"""

from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pytest

from irx.record_batch import ParquetOptions

from .test_parquet_followup import read_batches, write_batch


@pytest.mark.parametrize("atomic", [False, True])
def test_reconstructed_dataset(tmp_path: Path, atomic: bool) -> None:
    """
    title: >-
      Restore nullable fixed lists and numeric dictionaries across fragments.
    parameters:
      tmp_path:
        type: Path
      atomic:
        type: bool
    """
    batch = pa.record_batch(
        [
            pa.array(["a", "b", "a"]),
            pa.array([[1, None], None, [2, 3]], type=pa.list_(pa.int32(), 2)),
            pa.array([1, None, 2], type=pa.int64()).dictionary_encode(),
        ],
        names=["group", "items", "codes"],
    )
    path = tmp_path / "dataset"
    options = ParquetOptions(
        dataset=True,
        hive=True,
        partition_columns=("group",),
        reconstruct=True,
        atomic=atomic,
    )
    write_batch(path, batch, options)
    write_batch(
        path,
        batch,
        ParquetOptions(
            dataset=True,
            hive=True,
            partition_columns=("group",),
            reconstruct=True,
            atomic=atomic,
            append=True,
        ),
    )
    result = pa.Table.from_batches(
        read_batches(path, ParquetOptions(dataset=True, hive=True))
    )
    assert result.schema == batch.schema
    assert result.num_rows == batch.num_rows * 2
    assert sorted(map(str, result.to_pylist())) == sorted(
        map(str, batch.to_pylist() * 2)
    )
    projected = read_batches(
        path, ParquetOptions(dataset=True, hive=True, columns=("items",))
    )
    assert projected[0].schema == pa.schema([batch.schema.field("items")])


@pytest.mark.parametrize(
    "type_,values",
    [
        (pa.float32(), [1.25, None, -2.5]),
        (pa.float64(), [1.2345678901234567, None, 0.0]),
        (pa.decimal128(8, 2), [Decimal("1.25"), None, Decimal("-2.00")]),
        (
            pa.decimal256(50, 2),
            [
                Decimal("123456789012345678901234567890.12"),
                None,
                Decimal("-2.00"),
            ],
        ),
    ],
)
def test_numeric_hive_keys(
    tmp_path: Path, type_: pa.DataType, values: list[object]
) -> None:
    """
    title: Preserve decimal precision, floating widths and null partition keys.
    parameters:
      tmp_path:
        type: Path
      type_:
        type: pa.DataType
      values:
        type: list[object]
    """
    batch = pa.record_batch(
        [pa.array(values, type=type_), pa.array([0, 1, 2])],
        names=["key", "id"],
    )
    path = tmp_path / "dataset"
    write_batch(
        path,
        batch,
        ParquetOptions(dataset=True, hive=True, partition_columns=("key",)),
    )
    result = pa.Table.from_batches(
        read_batches(path, ParquetOptions(dataset=True, hive=True))
    ).sort_by("id")
    assert result.equals(pa.Table.from_batches([batch]))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.0])
def test_nonroundtrippable_float_keys(tmp_path: Path, value: float) -> None:
    """
    title: >-
      Refuse key values whose grouping cannot preserve bit-level semantics.
    parameters:
      tmp_path:
        type: Path
      value:
        type: float
    """
    batch = pa.record_batch([[value], [1]], names=["key", "id"])
    with pytest.raises(RuntimeError, match=r"finite.*negative zero"):
        write_batch(
            tmp_path / "data",
            batch,
            ParquetOptions(
                dataset=True, hive=True, partition_columns=("key",)
            ),
        )
