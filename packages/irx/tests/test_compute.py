"""
title: Compute layer tests (arrow::compute wrappers over RecordBatch).
"""

from __future__ import annotations

import math

import pyarrow as pa
import pyarrow.compute as pc
import pytest

from irx.record_batch import (
    ComputeAgg,
    ComputeBinOp,
    IrxColumnType,
    RecordBatch,
    RecordBatchBuilder,
    RecordBatchSchema,
)

# Helpers

INT_VALUES = [3, 1, 4, 1, 5]
FLOAT_VALUES = [1.5, 2.5, 0.5, 4.0, 2.0]
MASK_VALUES = [True, False, True, True, False]


def _build_numeric_batch() -> RecordBatch:
    """
    title: Build a batch with an int64, a float64 and a bool mask column.
    returns:
      type: RecordBatch
    """
    schema = RecordBatchSchema()
    schema.add_field("i", IrxColumnType.INT64)
    schema.add_field("f", IrxColumnType.FLOAT64)
    schema.add_field("m", IrxColumnType.BOOL)
    builder = RecordBatchBuilder(schema)
    for iv, fv, mv in zip(INT_VALUES, FLOAT_VALUES, MASK_VALUES):
        builder.append_int64(0, iv)
        builder.append_float64(1, fv)
        builder.append_bool(2, mv)
    batch = builder.finish()
    builder.release()
    schema.release()
    return batch


class TestAggregations:
    """
    title: Column reductions.
    """

    def test_integer_aggregations(self):
        """
        title: Sum/min/max/count over an int column stay integer-typed.
        """
        batch = _build_numeric_batch()
        assert batch.sum(0) == sum(INT_VALUES)
        assert isinstance(batch.sum(0), int)
        assert batch.min(0) == min(INT_VALUES)
        assert batch.max(0) == max(INT_VALUES)
        assert batch.count(0) == len(INT_VALUES)
        batch.release()

    def test_float_aggregations(self):
        """
        title: Sum/mean over a float column return floats.
        """
        batch = _build_numeric_batch()
        assert math.isclose(batch.sum(1), sum(FLOAT_VALUES))
        assert math.isclose(
            batch.mean(1), sum(FLOAT_VALUES) / len(FLOAT_VALUES)
        )
        assert isinstance(batch.sum(1), float)
        assert isinstance(batch.mean(1), float)
        batch.release()

    def test_mean_of_integer_column_is_float(self):
        """
        title: Mean always returns a float, even for an integer column.
        """
        batch = _build_numeric_batch()
        result = batch.mean(0)
        assert isinstance(result, float)
        assert math.isclose(result, sum(INT_VALUES) / len(INT_VALUES))
        batch.release()

    def test_aggregate_matches_pyarrow(self):
        """
        title: Aggregations agree with pyarrow.compute on the same data.
        """
        batch = _build_numeric_batch()
        column = pa.array(INT_VALUES, type=pa.int64())
        assert batch.sum(0) == pc.sum(column).as_py()
        assert batch.min(0) == pc.min(column).as_py()
        assert batch.max(0) == pc.max(column).as_py()
        assert math.isclose(batch.mean(0), pc.mean(column).as_py())
        batch.release()

    def test_aggregate_via_enum(self):
        """
        title: The generic aggregate entry point accepts a ComputeAgg.
        """
        batch = _build_numeric_batch()
        assert batch.aggregate(0, ComputeAgg.SUM) == sum(INT_VALUES)
        assert batch.aggregate(0, ComputeAgg.COUNT) == len(INT_VALUES)
        batch.release()

    def test_aggregate_out_of_bounds(self):
        """
        title: Aggregating a missing column raises.
        """
        batch = _build_numeric_batch()
        with pytest.raises(RuntimeError):
            batch.sum(99)
        batch.release()


class TestArithmetic:
    """
    title: Element-wise binary operators.
    """

    def test_add_columns(self):
        """
        title: Adding two columns yields a single "result" column.
        """
        batch = _build_numeric_batch()
        result = batch.add(0, 0)
        assert result.num_columns == 1
        assert [result.get_int64(0, r) for r in range(result.num_rows)] == [
            v * 2 for v in INT_VALUES
        ]
        result.release()
        batch.release()

    def test_all_binary_ops_match_pyarrow(self):
        """
        title: add/subtract/multiply/divide agree with pyarrow.compute.
        """
        batch = _build_numeric_batch()
        left = pa.array(FLOAT_VALUES, type=pa.float64())
        right = pa.array(INT_VALUES, type=pa.int64())
        cases = [
            (ComputeBinOp.ADD, pc.add),
            (ComputeBinOp.SUB, pc.subtract),
            (ComputeBinOp.MUL, pc.multiply),
            (ComputeBinOp.DIV, pc.divide),
        ]
        methods = {
            ComputeBinOp.ADD: batch.add,
            ComputeBinOp.SUB: batch.subtract,
            ComputeBinOp.MUL: batch.multiply,
            ComputeBinOp.DIV: batch.divide,
        }
        for op, pa_fn in cases:
            result = methods[op](1, 0)
            expected = pa_fn(left, right).to_pylist()
            got = [result.get_float64(0, r) for r in range(result.num_rows)]
            assert all(math.isclose(g, e) for g, e in zip(got, expected)), (
                f"{op} mismatch: {got} != {expected}"
            )
            result.release()
        batch.release()

    def test_binary_out_of_bounds(self):
        """
        title: A binary op on a missing column raises.
        """
        batch = _build_numeric_batch()
        with pytest.raises(RuntimeError):
            batch.add(0, 99)
        batch.release()


class TestFilter:
    """
    title: Row selection by boolean mask.
    """

    def test_filter_keeps_masked_rows(self):
        """
        title: Filter returns only the rows where the mask is true.
        """
        batch = _build_numeric_batch()
        result = batch.filter(2)
        expected = [v for v, m in zip(INT_VALUES, MASK_VALUES) if m]
        assert result.num_rows == len(expected)
        assert result.num_columns == batch.num_columns
        assert [
            result.get_int64(0, r) for r in range(result.num_rows)
        ] == expected
        result.release()
        batch.release()

    def test_filter_requires_boolean_mask(self):
        """
        title: Filtering on a non-boolean column raises.
        """
        batch = _build_numeric_batch()
        with pytest.raises(RuntimeError):
            batch.filter(0)
        batch.release()


class TestSortIndices:
    """
    title: Sort permutations.
    """

    def test_sort_ascending(self):
        """
        title: sort_indices returns the ascending permutation.
        """
        batch = _build_numeric_batch()
        indices = batch.sort_indices(0)
        ordered = [INT_VALUES[i] for i in indices]
        assert ordered == sorted(INT_VALUES)
        batch.release()

    def test_sort_descending(self):
        """
        title: sort_indices honours descending order.
        """
        batch = _build_numeric_batch()
        indices = batch.sort_indices(0, ascending=False)
        ordered = [INT_VALUES[i] for i in indices]
        assert ordered == sorted(INT_VALUES, reverse=True)
        batch.release()

    def test_sort_matches_pyarrow(self):
        """
        title: sort_indices agrees with pyarrow.compute.array_sort_indices.
        """
        batch = _build_numeric_batch()
        column = pa.array(FLOAT_VALUES, type=pa.float64())
        expected = pc.array_sort_indices(column).to_pylist()
        assert batch.sort_indices(1) == expected
        batch.release()

    def test_sort_out_of_bounds(self):
        """
        title: Sorting a missing column raises.
        """
        batch = _build_numeric_batch()
        with pytest.raises(RuntimeError):
            batch.sort_indices(99)
        batch.release()
