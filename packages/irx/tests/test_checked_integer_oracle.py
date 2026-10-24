"""
title: >-
  Batched mathematical oracles for checked scalar and SIMD integer lowering.
"""

from __future__ import annotations

import ctypes
import random

from collections.abc import Callable

import astx
import pytest

from irx.analysis.normalization import normalize_flags, normalize_operator
from irx.analysis.numeric_policy import (
    classify_numeric_conversion,
    integer_bounds,
)
from irx.analysis.resolved_nodes import SemanticInfo
from irx.builder import Builder
from irx.builder.numeric import integer_operation, lower_numeric_cast
from llvmlite import binding as llvm
from llvmlite import ir
from public import private

ABI_WIDTH = 64
REJECTED = 2


@private
def integer_kernel(
    type_: astx.DataType, operator: str, mode: astx.NumericMode, lanes: int = 1
) -> tuple[llvm.ExecutionEngine, Callable[[int, int, ctypes.c_void_p], int]]:
    """
    title: >-
      Expose the actual lowering guard predicate without terminating a batch.
    summary: >-
      Native subprocess tests independently verify fatal reporting. This
      fixture captures the very same guard condition to exhaustively test every
      8-bit input pair without starting hundreds of thousands of subprocesses.
    parameters:
      type_:
        type: astx.DataType
      operator:
        type: str
      mode:
        type: astx.NumericMode
      lanes:
        type: int
    returns:
      type: >-
        tuple[llvm.ExecutionEngine, Callable[[int, int, ctypes.c_void_p], int]]
    """
    visitor = Builder().translator
    bounds = integer_bounds(type_)
    assert bounds is not None
    width = (bounds[1] - bounds[0] + 1).bit_length() - 1
    storage = ir.IntType(width)
    function = ir.Function(
        visitor._llvm.module,
        ir.FunctionType(
            ir.IntType(8),
            [ir.IntType(64), ir.IntType(64), ir.IntType(64).as_pointer()],
        ),
        "probe",
    )
    visitor._llvm.ir_builder = ir.IRBuilder(
        function.append_basic_block("entry")
    )
    builder = visitor._llvm.ir_builder
    left, right, output = function.args
    if width < ABI_WIDTH:
        lhs = builder.trunc(left, storage)
        rhs = builder.trunc(right, storage)
    else:
        lhs, rhs = left, right
    if lanes > 1:
        packed = ir.IntType(width * lanes)
        vector = ir.VectorType(storage, lanes)
        lhs = builder.bitcast(
            builder.trunc(left, packed) if width * lanes < ABI_WIDTH else left,
            vector,
        )
        rhs = builder.bitcast(
            builder.trunc(right, packed)
            if width * lanes < ABI_WIDTH
            else right,
            vector,
        )
    checks: list[ir.Value] = []

    def capture(
        node: astx.AST,
        condition: ir.Value,
        *,
        code: str,
        message: str,
        block_name: str,
        exception_role: str = "RuntimeError",
    ) -> None:
        """
        title: >-
          Capture the pre-publication validity condition for the batch oracle.
        parameters:
          node:
            type: astx.AST
          condition:
            type: ir.Value
          code:
            type: str
          message:
            type: str
          block_name:
            type: str
          exception_role:
            type: str
        """
        checks.append(condition)

    visitor._guard_runtime_condition = capture  # type: ignore[method-assign]
    node = astx.BinaryOp(operator, astx.LiteralInt32(0), astx.LiteralInt32(0))
    flags = normalize_flags(node, lhs_type=type_, rhs_type=type_)
    plan = normalize_operator(
        operator,
        result_type=type_,
        lhs_type=type_,
        rhs_type=type_,
        flags=flags,
        mode=mode,
    )
    result = integer_operation(visitor, node, lhs, rhs, plan, operator)
    if lanes > 1:
        result = builder.bitcast(result, ir.IntType(width * lanes))
    builder.store(
        builder.zext(result, ir.IntType(64))
        if width * lanes < ABI_WIDTH
        else result,
        output,
    )
    valid = checks[0] if checks else ir.Constant(ir.IntType(1), 1)
    builder.ret(builder.zext(valid, ir.IntType(8)))
    module = llvm.parse_assembly(str(visitor._llvm.module))
    module.verify()
    engine = llvm.create_mcjit_compiler(module, visitor.target_machine)
    engine.finalize_object()
    signature = ctypes.CFUNCTYPE(
        ctypes.c_uint8, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p
    )
    return engine, signature(engine.get_function_address("probe"))


@pytest.mark.parametrize("unsigned", [False, True])
@pytest.mark.parametrize("operator", ["+", "-", "*"])
@pytest.mark.parametrize(
    "mode", [astx.NumericMode.CHECKED, astx.NumericMode.WRAPPING]
)
def test_exhaustive_eight_bit_arithmetic(
    unsigned: bool, operator: str, mode: astx.NumericMode
) -> None:
    """
    title: >-
      Compare every 8-bit pair, overflow flag, and modulo result to Python
      ints.
    parameters:
      unsigned:
        type: bool
      operator:
        type: str
      mode:
        type: astx.NumericMode
    """
    type_ = astx.UInt8() if unsigned else astx.Int8()
    bounds = integer_bounds(type_)
    assert bounds is not None
    engine, kernel = integer_kernel(type_, operator, mode)
    output = ctypes.c_uint64()
    pointer = ctypes.cast(ctypes.byref(output), ctypes.c_void_p)
    for left in range(bounds[0], bounds[1] + 1):
        for right in range(bounds[0], bounds[1] + 1):
            exact = (
                left + right
                if operator == "+"
                else left - right
                if operator == "-"
                else left * right
            )
            valid = kernel(left, right, pointer)
            assert bool(valid) == (
                mode is astx.NumericMode.WRAPPING
                or bounds[0] <= exact <= bounds[1]
            )
            assert output.value == exact % 256
    engine.close()


@pytest.mark.parametrize(
    "type_class",
    [
        astx.Int16,
        astx.UInt16,
        astx.Int32,
        astx.UInt32,
        astx.Int64,
        astx.UInt64,
    ],
)
@pytest.mark.parametrize("operator", ["+", "-", "*"])
def test_wider_boundary_biased_oracle(
    type_class: type[astx.DataType], operator: str
) -> None:
    """
    title: >-
      Seeded wider arithmetic includes all extrema and near-boundary products.
    parameters:
      type_class:
        type: type[astx.DataType]
      operator:
        type: str
    """
    type_ = type_class()
    bounds = integer_bounds(type_)
    assert bounds is not None
    engine, kernel = integer_kernel(type_, operator, astx.NumericMode.CHECKED)
    randomizer = random.Random(20261023)
    boundary = [bounds[0], bounds[0] + 1, 0, 1, bounds[1] - 1, bounds[1]]
    pairs = [(a, b) for a in boundary for b in boundary]
    pairs.extend(
        (randomizer.randint(*bounds), randomizer.choice(boundary))
        for _ in range(500)
    )
    output = ctypes.c_uint64()
    pointer = ctypes.cast(ctypes.byref(output), ctypes.c_void_p)
    for left, right in pairs:
        exact = (
            left + right
            if operator == "+"
            else left - right
            if operator == "-"
            else left * right
        )
        valid = kernel(left, right, pointer)
        assert bool(valid) == (bounds[0] <= exact <= bounds[1])
        assert output.value == exact % (bounds[1] - bounds[0] + 1)
    engine.close()


@pytest.mark.parametrize(
    "type_class", [astx.Int8, astx.UInt8, astx.Int16, astx.UInt16]
)
@pytest.mark.parametrize("operator", ["+", "-", "*"])
def test_simd_rejects_one_overflowing_active_lane(
    type_class: type[astx.DataType], operator: str
) -> None:
    """
    title: >-
      SIMD checks all active lanes and reports any single overflowing lane.
    parameters:
      type_class:
        type: type[astx.DataType]
      operator:
        type: str
    """
    type_ = type_class()
    bounds = integer_bounds(type_)
    assert bounds is not None
    modulus = bounds[1] - bounds[0] + 1
    width = modulus.bit_length() - 1
    engine, kernel = integer_kernel(
        type_, operator, astx.NumericMode.CHECKED, lanes=4
    )
    output = ctypes.c_uint64()
    pointer = ctypes.cast(ctypes.byref(output), ctypes.c_void_p)
    for lane in range(4):
        for overflow in (False, True):
            lefts = [2] * 4
            rights = [1] * 4
            if overflow:
                lefts[lane] = bounds[0] if operator == "-" else bounds[1]
                rights[lane] = 2 if operator == "*" else 1
            left = sum(
                (value % modulus) << (width * index)
                for index, value in enumerate(lefts)
            )
            right = sum(
                (value % modulus) << (width * index)
                for index, value in enumerate(rights)
            )
            assert bool(kernel(left, right, pointer)) is not overflow
    engine.close()


@pytest.mark.parametrize("floating", [False, True])
def test_null_cast_does_not_inspect_invalid_payload(floating: bool) -> None:
    """
    title: Invalid nullable payload bits never reach numeric conversion guards.
    parameters:
      floating:
        type: bool
    """

    visitor = Builder().translator
    source_type = astx.Float64() if floating else astx.Int64()
    source = astx.Identifier("input")
    setattr(
        source,
        "semantic",
        SemanticInfo(resolved_type=astx.NullableType(source_type)),
    )
    node = astx.Cast(source, astx.NullableType(astx.Int8()))
    setattr(node, "semantic", SemanticInfo(resolved_type=node.target_type))
    storage = ir.DoubleType() if floating else ir.IntType(64)
    function = ir.Function(
        visitor._llvm.module,
        ir.FunctionType(ir.IntType(8), [ir.IntType(8), storage]),
        "nullable_probe",
    )
    visitor._llvm.ir_builder = ir.IRBuilder(
        function.append_basic_block("entry")
    )
    builder = visitor._llvm.ir_builder
    observed = builder.alloca(ir.IntType(8))
    builder.store(ir.Constant(ir.IntType(8), 0), observed)

    def capture(
        node: astx.AST,
        condition: ir.Value,
        *,
        code: str,
        message: str,
        block_name: str,
        exception_role: str = "RuntimeError",
    ) -> None:
        """
        title: >-
          Record whether a conversion guard executed and accepted the payload.
        parameters:
          node:
            type: astx.AST
          condition:
            type: ir.Value
          code:
            type: str
          message:
            type: str
          block_name:
            type: str
          exception_role:
            type: str
        """
        builder.store(
            builder.select(
                condition,
                ir.Constant(ir.IntType(8), 1),
                ir.Constant(ir.IntType(8), 2),
            ),
            observed,
        )

    visitor._guard_runtime_condition = capture  # type: ignore[method-assign]
    packed = ir.Constant(ir.LiteralStructType([ir.IntType(1), storage]), None)
    value = builder.insert_value(
        packed, builder.trunc(function.args[0], ir.IntType(1)), 0
    )
    value = builder.insert_value(value, function.args[1], 1)
    plan = classify_numeric_conversion(source_type, astx.Int8())
    assert plan is not None
    lower_numeric_cast(visitor, node, value, plan, astx.NumericMode.CHECKED)
    builder.ret(builder.load(observed))
    module = llvm.parse_assembly(str(visitor._llvm.module))
    module.verify()
    engine = llvm.create_mcjit_compiler(module, visitor.target_machine)
    engine.finalize_object()
    payload = ctypes.c_double if floating else ctypes.c_int64
    kernel = ctypes.CFUNCTYPE(ctypes.c_uint8, ctypes.c_uint8, payload)(
        engine.get_function_address("nullable_probe")
    )
    invalid = float("nan") if floating else (1 << 63) - 1
    assert kernel(0, invalid) == 0
    assert kernel(1, invalid) == REJECTED
    assert kernel(1, 127) == 1
    engine.close()
