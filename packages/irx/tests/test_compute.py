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


# Null / boundary helpers (PR 1)

# Integer column with interspersed nulls; expectations derive from the
# non-null subset so aggregations stay data-driven, not magic-valued.
NULLABLE_INT = [10, None, 30, None, 50]
NULLABLE_VALID = [v for v in NULLABLE_INT if v is not None]

_APPENDERS = {
    IrxColumnType.INT64: "append_int64",
    IrxColumnType.UINT64: "append_uint64",
    IrxColumnType.FLOAT64: "append_float64",
    IrxColumnType.BOOL: "append_bool",
    IrxColumnType.UTF8: "append_string",
}


def _build_single_col_batch(
    col_type: IrxColumnType, values: list
) -> RecordBatch:
    """
    title: Build a one-column batch, using append_null for None entries.
    parameters:
      col_type:
        type: IrxColumnType
      values:
        type: list
    returns:
      type: RecordBatch
    """
    schema = RecordBatchSchema()
    schema.add_field("c", col_type)
    builder = RecordBatchBuilder(schema)
    append = getattr(builder, _APPENDERS[col_type])
    for v in values:
        if v is None:
            builder.append_null(0)
        else:
            append(0, v)
    batch = builder.finish()
    builder.release()
    schema.release()
    return batch


def _build_two_int_batch(a: list, b: list) -> RecordBatch:
    """
    title: Build a two-column int64 batch (for binary ops).
    parameters:
      a:
        type: list
      b:
        type: list
    returns:
      type: RecordBatch
    """
    schema = RecordBatchSchema()
    schema.add_field("a", IrxColumnType.INT64)
    schema.add_field("b", IrxColumnType.INT64)
    builder = RecordBatchBuilder(schema)
    for av, bv in zip(a, b):
        builder.append_int64(0, av)
        builder.append_int64(1, bv)
    batch = builder.finish()
    builder.release()
    schema.release()
    return batch


class TestAggregationNulls:
    """
    title: Aggregations skip nulls and handle all-null / empty columns.
    """

    def test_sum_skips_nulls(self):
        """
        title: Sum ignores null slots.
        """
        batch = _build_single_col_batch(IrxColumnType.INT64, NULLABLE_INT)
        assert batch.sum(0) == sum(NULLABLE_VALID)
        batch.release()

    def test_mean_skips_nulls(self):
        """
        title: Mean divides by the non-null count only.
        """
        batch = _build_single_col_batch(IrxColumnType.INT64, NULLABLE_INT)
        assert math.isclose(
            batch.mean(0), sum(NULLABLE_VALID) / len(NULLABLE_VALID)
        )
        batch.release()

    def test_count_excludes_nulls(self):
        """
        title: Count returns the number of non-null values.
        """
        batch = _build_single_col_batch(IrxColumnType.INT64, NULLABLE_INT)
        assert batch.count(0) == len(NULLABLE_VALID)
        batch.release()

    def test_minmax_skip_nulls(self):
        """
        title: Min/max ignore nulls.
        """
        batch = _build_single_col_batch(IrxColumnType.INT64, NULLABLE_INT)
        assert batch.min(0) == min(NULLABLE_VALID)
        assert batch.max(0) == max(NULLABLE_VALID)
        batch.release()

    def test_count_all_null_is_zero(self):
        """
        title: Count of an all-null column is 0, not an error.
        """
        batch = _build_single_col_batch(
            IrxColumnType.INT64, [None, None, None]
        )
        assert batch.count(0) == 0
        batch.release()

    def test_sum_all_null_raises(self):
        """
        title: Non-count aggregation over no valid value raises (cpp:1139).
        """
        batch = _build_single_col_batch(
            IrxColumnType.INT64, [None, None, None]
        )
        with pytest.raises(RuntimeError):
            batch.sum(0)
        batch.release()

    def test_float_minmax(self):
        """
        title: Min/max on a float column return floats (MinMax float branch).
        """
        batch = _build_single_col_batch(
            IrxColumnType.FLOAT64, [1.5, 2.5, 0.5, 4.0, 2.0]
        )
        assert isinstance(batch.min(0), float)
        assert isinstance(batch.max(0), float)
        assert math.isclose(batch.min(0), 0.5)
        assert math.isclose(batch.max(0), 4.0)
        batch.release()

    def test_uint64_sum(self):
        """
        title: Sum of a uint64 column round-trips through the int out-param.
        """
        values = [1, 2, 3, 4, 5]
        batch = _build_single_col_batch(IrxColumnType.UINT64, values)
        assert batch.sum(0) == sum(values)
        batch.release()

    def test_sum_on_utf8_raises(self):
        """
        title: Summing a non-numeric (utf8) column raises rather than crash.
        """
        batch = _build_single_col_batch(IrxColumnType.UTF8, ["a", "b", "c"])
        with pytest.raises(RuntimeError):
            batch.sum(0)
        batch.release()


class TestEmptyBatchCompute:
    """
    title: Compute ops on a zero-row batch.
    """

    def test_sort_empty_returns_empty(self):
        """
        title: sort_indices on an empty column returns an empty list.
        """
        batch = _build_single_col_batch(IrxColumnType.INT64, [])
        assert batch.sort_indices(0) == []
        batch.release()

    def test_count_empty_is_zero(self):
        """
        title: Count of an empty column is 0.
        """
        batch = _build_single_col_batch(IrxColumnType.INT64, [])
        assert batch.count(0) == 0
        batch.release()

    def test_sum_empty_raises(self):
        """
        title: Summing an empty column raises (no valid value).
        """
        batch = _build_single_col_batch(IrxColumnType.INT64, [])
        with pytest.raises(RuntimeError):
            batch.sum(0)
        batch.release()


class TestFilterNulls:
    """
    title: Filter behaviour with null mask slots.
    """

    def test_null_mask_slot_drops_row(self):
        """
        title: A null mask slot drops its row (header contract .h:201-202).
        """
        schema = RecordBatchSchema()
        schema.add_field("v", IrxColumnType.INT64)
        schema.add_field("m", IrxColumnType.BOOL)
        builder = RecordBatchBuilder(schema)
        vals = [10, 20, 30, 40, 50]
        mask = [True, None, True, False, None]
        for v, m in zip(vals, mask):
            builder.append_int64(0, v)
            if m is None:
                builder.append_null(1)
            else:
                builder.append_bool(1, m)
        batch = builder.finish()
        builder.release()
        schema.release()
        result = batch.filter(1)
        # Only rows 0 and 2 have mask == True; nulls (1, 4) drop, row 3 False.
        kept = [v for v, m in zip(vals, mask) if m is True]
        assert result.num_rows == len(kept)
        assert [result.get_int64(0, r) for r in range(result.num_rows)] == kept
        result.release()
        batch.release()


class TestSortNulls:
    """
    title: Sort ordering with nulls.
    """

    def test_nulls_sort_to_end_ascending(self):
        """
        title: Null slots sort after all valid values (ascending, .h:207).
        """
        batch = _build_single_col_batch(
            IrxColumnType.INT64, [3, None, 1, None, 2]
        )
        indices = batch.sort_indices(0)
        # Valid values 1,2,3 first (rows 2,4,0), nulls last (rows 1,3).
        assert indices[:3] == [2, 4, 0]
        assert sorted(indices[3:]) == [1, 3]
        batch.release()

    def test_nulls_sort_to_end_descending(self):
        """
        title: Null slots still sort to the end when descending.
        """
        batch = _build_single_col_batch(
            IrxColumnType.INT64, [3, None, 1, None, 2]
        )
        indices = batch.sort_indices(0, ascending=False)
        assert indices[:3] == [0, 4, 2]
        assert sorted(indices[3:]) == [1, 3]
        batch.release()


class TestArithmeticEdgeCases:
    """
    title: Binary op edge cases.
    """

    def test_integer_divide_by_zero_raises(self):
        """
        title: Integer division by zero surfaces as an error.
        """
        batch = _build_two_int_batch([1, 2, 3], [1, 0, 3])
        with pytest.raises(RuntimeError):
            batch.divide(0, 1)
        batch.release()

    def test_add_overflow_wraps(self):
        """
        title: Non-checked add wraps int64 silently (cpp:1213 "add" kernel).
        """
        big = (1 << 63) - 1  # INT64_MAX
        batch = _build_two_int_batch([big], [1])
        result = batch.add(0, 1)
        # Wrap, not error: INT64_MAX + 1 == INT64_MIN in two's complement.
        assert result.get_int64(0, 0) == -(1 << 63)
        result.release()
        batch.release()
