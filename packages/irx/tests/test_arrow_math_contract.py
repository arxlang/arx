"""
title: Independent f64 oracles for the proposed Arrow-first math contract.
summary: >-
  These tests specify candidate per-operation tolerances, not implemented Arx
  math functions. Rerun with pinned Arrow 26 before approving its contract.
  Passing with historical dependencies does not qualify Arrow 26 or the
  frontend/IRx call path. Decimal references use 200 significant digits and
  round only at the final conversion to binary64.
"""

from __future__ import annotations

import math
import struct
import sys

from decimal import Decimal, localcontext
from typing import Literal, cast

import pyarrow as pa
import pyarrow.compute as pc
import pytest

Operation = Literal["sqrt", "exp", "log", "power"]
KERNELS: dict[Operation, str] = {
    "sqrt": "sqrt",
    "exp": "exp",
    "log": "ln",
    "power": "power",
}
ULPS: dict[Operation, int] = {"sqrt": 4, "exp": 8, "log": 8, "power": 16}
MIN_SUBNORMAL = math.ulp(0.0)
FINITE: dict[Operation, tuple[tuple[float, ...], ...]] = {
    "sqrt": ((2.0,), (4.0,), (MIN_SUBNORMAL,), (sys.float_info.max,)),
    "exp": ((1.0,), (-1.0,), (709.0,), (710.0,), (-745.0,), (-746.0,)),
    "log": ((2.0,), (0.5,), (MIN_SUBNORMAL,), (sys.float_info.max,)),
    "power": ((2.0, 0.5), (-2.0, 3.0), (2.0, -3.0), (2.0, 1024.0)),
}
SPECIAL: dict[
    Operation, tuple[tuple[tuple[float | None, ...], float | None], ...]
] = {
    "sqrt": (
        ((0.0,), 0.0),
        ((-0.0,), -0.0),
        ((-1.0,), math.nan),
        ((math.inf,), math.inf),
        ((-math.inf,), math.nan),
        ((math.nan,), math.nan),
        ((None,), None),
    ),
    "exp": (
        ((0.0,), 1.0),
        ((-0.0,), 1.0),
        ((math.inf,), math.inf),
        ((-math.inf,), 0.0),
        ((math.nan,), math.nan),
        ((None,), None),
    ),
    "log": (
        ((1.0,), 0.0),
        ((0.0,), -math.inf),
        ((-0.0,), -math.inf),
        ((-1.0,), math.nan),
        ((math.inf,), math.inf),
        ((-math.inf,), math.nan),
        ((math.nan,), math.nan),
        ((None,), None),
    ),
    "power": (
        ((-2.0, 0.5), math.nan),
        ((0.0, 0.0), 1.0),
        ((0.0, -1.0), math.inf),
        ((-0.0, -1.0), -math.inf),
        ((-0.0, 3.0), -0.0),
        ((math.inf, -1.0), 0.0),
        ((-math.inf, 3.0), -math.inf),
        ((-math.inf, 0.5), math.inf),
        ((1.0, math.nan), 1.0),
        ((math.nan, 0.0), 1.0),
        ((math.nan, 2.0), math.nan),
        ((None, 2.0), None),
        ((2.0, None), None),
    ),
}


def decimal_reference(
    operation: Operation, arguments: tuple[float, ...]
) -> float:
    """
    title: Calculate finite-input references without using the Arrow kernel.
    parameters:
      operation:
        type: Operation
      arguments:
        type: tuple[float, Ellipsis]
    returns:
      type: float
    """
    with localcontext() as context:
        context.prec = 200
        left = Decimal.from_float(arguments[0])
        if operation == "sqrt":
            return float(left.sqrt())
        if operation == "exp":
            return float(left.exp())
        if operation == "log":
            return float(left.ln())
        return float(context.power(left, Decimal.from_float(arguments[1])))


def ordered_bits(value: float) -> int:
    """
    title: Order finite binary64 encodings for an integer ULP distance.
    parameters:
      value:
        type: float
    returns:
      type: int
    """
    bits = int.from_bytes(struct.pack(">d", value), "big")
    sign = 1 << 63
    return (~bits & ((1 << 64) - 1)) if bits & sign else bits | sign


def assert_result(
    operation: Operation, result: pa.Scalar, expected: float | None
) -> None:
    """
    title: Compare dtype, validity, IEEE class/sign and finite ULP error.
    parameters:
      operation:
        type: Operation
      result:
        type: pa.Scalar
      expected:
        type: float | None
    """
    assert result.type == pa.float64()
    value = cast(float | None, result.as_py())
    if expected is None:
        assert value is None
        return
    assert isinstance(value, float)
    if math.isnan(expected):
        assert math.isnan(value)
        return
    if math.isinf(expected):
        assert value == expected
        return
    if expected == 0.0:
        assert value == 0.0
        assert math.copysign(1.0, value) == math.copysign(1.0, expected)
        return
    assert math.isfinite(value) and value != 0.0
    assert abs(ordered_bits(value) - ordered_bits(expected)) <= ULPS[operation]


@pytest.mark.parametrize("operation", tuple(KERNELS))
def test_scalar_array_math_contract(operation: Operation) -> None:
    """
    title: Apply one independent oracle to scalar, sliced and chunked inputs.
    parameters:
      operation:
        type: Operation
    """
    vectors = [
        (arguments, decimal_reference(operation, arguments))
        for arguments in FINITE[operation]
    ]
    for arguments, expected in (*vectors, *SPECIAL[operation]):
        scalar = [pa.scalar(value, type=pa.float64()) for value in arguments]
        arrays = [
            pa.array([0.0, value], type=pa.float64()).slice(1)
            for value in arguments
        ]
        chunks = [
            pa.chunked_array(
                [
                    pa.array([None], type=pa.float64()),
                    pa.array([value], type=pa.float64()),
                ]
            )
            for value in arguments
        ]
        for inputs in (scalar, arrays, chunks):
            result = pc.call_function(KERNELS[operation], inputs)  # type: ignore[attr-defined]
            if not isinstance(result, pa.Scalar):
                assert len(result) == len(inputs[0])
                if len(result) > 1:
                    assert not result[0].is_valid
                result = result[-1]
            assert_result(operation, result, expected)
    empty = pc.call_function(  # type: ignore[attr-defined]
        KERNELS[operation],
        [pa.array([], type=pa.float64()) for _ in FINITE[operation][0]],
    )
    assert len(empty) == 0 and empty.type == pa.float64()
