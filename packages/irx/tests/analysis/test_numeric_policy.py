"""
title: Exhaustive domain tests for the checked-arithmetic policy foundation.
"""

from __future__ import annotations

import astx
import pytest

from irx.analysis.numeric_policy import (
    FLOAT_PRECISIONS,
    SIGNED_TYPES,
    UNSIGNED_TYPES,
    NumericConversionKind,
    classify_numeric_conversion,
    integer_bounds,
    is_lossless_numeric_conversion,
    lossless_common_numeric_type,
)
from typeguard import TypeCheckError

INTEGER_TYPES = tuple(SIGNED_TYPES) + tuple(UNSIGNED_TYPES)
NUMERIC_TYPES = INTEGER_TYPES + tuple(FLOAT_PRECISIONS)

# Independent acceptance table: rows and columns are i8/i16/i32/i64,
# u8/u16/u32/u64, f16/f32/f64. A dash means no lossless common domain.
PROMOTION_TABLE = (
    "i8 i16 i32 i64 i16 i32 i64 - f16 f32 f64",
    "i16 i16 i32 i64 i16 i32 i64 - f32 f32 f64",
    "i32 i32 i32 i64 i32 i32 i64 - f64 f64 f64",
    "i64 i64 i64 i64 i64 i64 i64 - - - -",
    "i16 i16 i32 i64 u8 u16 u32 u64 f16 f32 f64",
    "i32 i32 i32 i64 u16 u16 u32 u64 f32 f32 f64",
    "i64 i64 i64 i64 u32 u32 u32 u64 f64 f64 f64",
    "- - - - u64 u64 u64 u64 - - -",
    "f16 f32 f64 - f16 f32 f64 - f16 f32 f64",
    "f32 f32 f64 - f32 f32 f64 - f32 f32 f64",
    "f64 f64 f64 - f64 f64 f64 - f64 f64 f64",
)
TYPE_NAMES: dict[type[astx.DataType], str] = {
    astx.Int8: "i8",
    astx.Int16: "i16",
    astx.Int32: "i32",
    astx.Int64: "i64",
    astx.UInt8: "u8",
    astx.UInt16: "u16",
    astx.UInt32: "u32",
    astx.UInt64: "u64",
    astx.Float16: "f16",
    astx.Float32: "f32",
    astx.Float64: "f64",
}


@pytest.mark.parametrize("type_class", INTEGER_TYPES)
def test_integer_domain(type_class: type[astx.DataType]) -> None:
    """
    title: Match each complete signed or unsigned integer domain.
    parameters:
      type_class:
        type: type[astx.DataType]
    """
    width = SIGNED_TYPES.get(type_class, UNSIGNED_TYPES.get(type_class, 0))
    bounds = integer_bounds(type_class())
    assert bounds is not None
    assert bounds[1] - bounds[0] + 1 == 2**width
    assert bounds[0] == (
        -(2 ** (width - 1)) if type_class in SIGNED_TYPES else 0
    )


@pytest.mark.parametrize("lhs", NUMERIC_TYPES)
@pytest.mark.parametrize("rhs", NUMERIC_TYPES)
def test_common_domain_matrix(
    lhs: type[astx.DataType], rhs: type[astx.DataType]
) -> None:
    """
    title: Preserve both operand domains and choose a symmetric minimal type.
    parameters:
      lhs:
        type: type[astx.DataType]
      rhs:
        type: type[astx.DataType]
    """
    result = lossless_common_numeric_type(lhs(), rhs())
    reverse = lossless_common_numeric_type(rhs(), lhs())
    expected = PROMOTION_TABLE[NUMERIC_TYPES.index(lhs)].split()[
        NUMERIC_TYPES.index(rhs)
    ]
    assert (TYPE_NAMES[type(result)] if result is not None else "-") == (
        expected
    )
    assert type(result) is type(reverse)
    if lhs in FLOAT_PRECISIONS or rhs in FLOAT_PRECISIONS:
        candidates = tuple(FLOAT_PRECISIONS)
    elif lhs in UNSIGNED_TYPES and rhs in UNSIGNED_TYPES:
        candidates = tuple(UNSIGNED_TYPES)
    else:
        candidates = tuple(SIGNED_TYPES)
    admissible = [
        candidate
        for candidate in candidates
        if is_lossless_numeric_conversion(lhs(), candidate())
        and is_lossless_numeric_conversion(rhs(), candidate())
    ]
    assert type(result) is (admissible[0] if admissible else type(None))
    if lhs is rhs:
        assert type(result) is lhs


@pytest.mark.parametrize(
    "lhs,rhs,result",
    [
        (astx.Int8, astx.UInt8, astx.Int16),
        (astx.Int16, astx.UInt16, astx.Int32),
        (astx.Int32, astx.UInt32, astx.Int64),
        (astx.Int64, astx.UInt32, astx.Int64),
        (astx.Int64, astx.UInt64, None),
        (astx.Int8, astx.UInt64, None),
        (astx.Float16, astx.Int16, astx.Float32),
        (astx.Float32, astx.Int32, astx.Float64),
        (astx.Float64, astx.Int64, None),
        (astx.Float64, astx.UInt64, None),
    ],
)
def test_promotion_policy_examples(
    lhs: type[astx.DataType],
    rhs: type[astx.DataType],
    result: type[astx.DataType] | None,
) -> None:
    """
    title: Check policy boundaries independently of the matrix invariants.
    parameters:
      lhs:
        type: type[astx.DataType]
      rhs:
        type: type[astx.DataType]
      result:
        type: type[astx.DataType] | None
    """
    assert type(lossless_common_numeric_type(lhs(), rhs())) is (
        result if result is not None else type(None)
    )


@pytest.mark.parametrize("source", NUMERIC_TYPES)
@pytest.mark.parametrize("target", NUMERIC_TYPES)
def test_conversion_policy_matrix(
    source: type[astx.DataType], target: type[astx.DataType]
) -> None:
    """
    title: Classify every scalar numeric conversion without evaluating a value.
    parameters:
      source:
        type: type[astx.DataType]
      target:
        type: type[astx.DataType]
    """
    plan = classify_numeric_conversion(source(), target())
    assert plan is not None
    assert type(plan.source_type) is source
    assert type(plan.target_type) is target
    assert plan.implicit == is_lossless_numeric_conversion(source(), target())
    if plan.implicit:
        assert not plan.requires_range_check
        assert plan.kind in {
            NumericConversionKind.IDENTITY,
            NumericConversionKind.LOSSLESS,
        }
    elif target in INTEGER_TYPES:
        assert plan.requires_range_check
        assert plan.kind is (
            NumericConversionKind.INTEGER_RANGE
            if source in INTEGER_TYPES
            else NumericConversionKind.FLOAT_TO_INTEGER
        )


@pytest.mark.parametrize(
    "type_",
    [
        astx.Boolean(),
        astx.String(),
        astx.NoneType(),
        astx.NullableType(astx.Int32()),
        astx.UInt128(),
    ],
)
def test_unsupported_domains_fail_closed(type_: astx.DataType) -> None:
    """
    title: >-
      Do not accidentally treat bool, containers, or unsupported widths as
      numbers.
    parameters:
      type_:
        type: astx.DataType
    """
    assert integer_bounds(type_) is None
    assert not is_lossless_numeric_conversion(type_, type_)
    assert lossless_common_numeric_type(type_, astx.Int32()) is None
    assert lossless_common_numeric_type(astx.Int32(), type_) is None
    assert classify_numeric_conversion(type_, astx.Int32()) is None


def test_numeric_policy_rejects_invalid_runtime_arguments() -> None:
    """
    title: Runtime checking rejects non-AST types instead of guessing domains.
    """
    with pytest.raises(TypeCheckError):
        integer_bounds("i8")  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        lossless_common_numeric_type(astx.Int8(), [astx.Int8()])  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        classify_numeric_conversion(None, astx.Int8())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "source,target,implicit,checked,kind",
    [
        (astx.Int8, astx.Int8, True, False, NumericConversionKind.IDENTITY),
        (astx.Int8, astx.Int64, True, False, NumericConversionKind.LOSSLESS),
        (astx.UInt32, astx.Int64, True, False, NumericConversionKind.LOSSLESS),
        (
            astx.Int32,
            astx.Float64,
            True,
            False,
            NumericConversionKind.LOSSLESS,
        ),
        (
            astx.Int64,
            astx.Int8,
            False,
            True,
            NumericConversionKind.INTEGER_RANGE,
        ),
        (
            astx.Int32,
            astx.UInt32,
            False,
            True,
            NumericConversionKind.INTEGER_RANGE,
        ),
        (
            astx.UInt32,
            astx.Int32,
            False,
            True,
            NumericConversionKind.INTEGER_RANGE,
        ),
        (
            astx.Float64,
            astx.UInt64,
            False,
            True,
            NumericConversionKind.FLOAT_TO_INTEGER,
        ),
        (
            astx.Int16,
            astx.Float16,
            False,
            False,
            NumericConversionKind.INTEGER_TO_FLOAT,
        ),
        (
            astx.UInt16,
            astx.Float16,
            False,
            True,
            NumericConversionKind.INTEGER_TO_FLOAT,
        ),
        (
            astx.Int64,
            astx.Float64,
            False,
            False,
            NumericConversionKind.INTEGER_TO_FLOAT,
        ),
        (
            astx.Float64,
            astx.Float32,
            False,
            True,
            NumericConversionKind.FLOAT_NARROW,
        ),
    ],
)
def test_conversion_checks_and_precision_loss_are_distinct(
    source: type[astx.DataType],
    target: type[astx.DataType],
    implicit: bool,
    checked: bool,
    kind: NumericConversionKind,
) -> None:
    """
    title: Distinguish explicit precision loss from finite-range failures.
    parameters:
      source:
        type: type[astx.DataType]
      target:
        type: type[astx.DataType]
      implicit:
        type: bool
      checked:
        type: bool
      kind:
        type: NumericConversionKind
    """
    plan = classify_numeric_conversion(source(), target())
    assert plan is not None
    assert plan.kind is kind
    assert plan.implicit is implicit
    assert plan.requires_range_check is checked
