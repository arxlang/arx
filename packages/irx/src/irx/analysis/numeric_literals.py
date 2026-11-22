"""
title: Contextual numeric literals and constant representability.
"""

from __future__ import annotations

import math

from typing import cast

import astx

from public import private, public

from irx.analysis.context import SemanticContext
from irx.analysis.float_literals import rounded_float
from irx.analysis.numeric_policy import FLOAT_PRECISIONS, integer_bounds
from irx.analysis.resolved_nodes import SemanticInfo
from irx.diagnostics import DiagnosticBag, DiagnosticCodes
from irx.typecheck import typechecked


@public
@typechecked
def default_numeric_literal_type(
    node: astx.LiteralInteger | astx.LiteralFloat,
) -> astx.DataType:
    """
    title: Select the uncontextualized source default without checking
      its value.
    summary: Contextual typing and representability remain semantic
      responsibilities.
    parameters:
      node: Syntax node to process.
    returns: 'Result of this operation: select the uncontextualized
      source default without checking its value.'
    """
    if isinstance(node, astx.LiteralFloat):
        return astx.Float32()
    return (
        astx.Int32() if -(1 << 31) <= node.value < (1 << 31) else astx.Int64()
    )


@private
@typechecked
def floating_literal_expression(node: astx.AST) -> bool | None:
    """
    title: Classify unresolved literal arithmetic without inferring types.
    parameters:
      node: Expression to inspect.
    returns: True for floating literal arithmetic, False for integer-only
      arithmetic, or None for typed operands and unsupported operators.
    """
    if isinstance(node, astx.LiteralFloat):
        return True
    if isinstance(node, astx.LiteralInteger):
        return False
    if isinstance(node, astx.UnaryOp) and node.op_code in {"+", "-"}:
        return floating_literal_expression(node.operand)
    if (
        isinstance(node, astx.BinaryOp)
        and node.mode is astx.NumericMode.CHECKED
        and node.op_code in {"+", "-", "*", "/", "%"}
    ):
        left = floating_literal_expression(node.lhs)
        right = floating_literal_expression(node.rhs)
        if left is not None and right is not None:
            return left or right
    return None


@private
@typechecked
def contextualize_literal(
    value: astx.AST | None, target: astx.DataType | None
) -> None:
    """
    title: Record expected types for exact literals and floating literal
      arithmetic, never for typed computations.
    summary: Integer-only subexpressions retain integer operator semantics.
    parameters:
      value: Value to process.
      target: Destination of the operation.
    """
    from irx.analysis.types import contains_template_variables  # noqa: PLC0415

    if contains_template_variables(target):
        target = None
    if isinstance(value, (astx.ListExpr, astx.LiteralList)) and isinstance(
        target, astx.SequenceType
    ):
        target = astx.ListType([target.element_type])
    if isinstance(value, (astx.SubscriptExpr, astx.ListIndex)):
        base = (
            value.value
            if isinstance(value, astx.SubscriptExpr)
            else value.base
        )
        if isinstance(base, astx.ListExpr) and target is not None:
            contextualize_literal(base, astx.ListType([target]))
        return
    if isinstance(value, astx.ListExpr):
        literal_semantic(value).literal_context = target
        return
    if isinstance(target, astx.NullableType):
        target = target.value_type
    if isinstance(value, (astx.BinaryOp, astx.UnaryOp)):
        literal_semantic(value).literal_context = (
            target
            if type(target) in FLOAT_PRECISIONS
            and floating_literal_expression(value) is True
            else None
        )
        return
    if isinstance(
        value, (astx.LiteralInteger, astx.LiteralFloat)
    ) and isinstance(target, astx.SeriesType):
        target = target.element_type
    if isinstance(value, (astx.LiteralInteger, astx.LiteralFloat)):
        info = literal_semantic(value)
        info.literal_context = None
        if type(target) in FLOAT_PRECISIONS or (
            isinstance(value, astx.LiteralInteger)
            and target is not None
            and integer_bounds(target) is not None
        ):
            info.literal_context = target
        return
    if target is None:
        return
    if isinstance(value, (astx.LiteralList, astx.LiteralSet)):
        element: astx.DataType | None = None
        if (
            isinstance(target, astx.ListType)
            and len(target.element_types) == 1
        ):
            element = cast(astx.DataType, target.element_types[0])
        elif isinstance(
            target, (astx.TensorType, astx.SeriesType, astx.SetType)
        ):
            element = cast(astx.DataType, target.element_type)
        for item in value.elements:
            contextualize_literal(item, element)
    elif isinstance(value, astx.LiteralTuple) and isinstance(
        target, astx.TupleType
    ):
        for item, type_ in zip(value.elements, target.element_types):
            contextualize_literal(item, cast(astx.DataType, type_))
    elif isinstance(value, astx.LiteralDict) and isinstance(
        target, astx.DictType
    ):
        for key, item in value.elements.items():
            contextualize_literal(key, cast(astx.DataType, target.key_type))
            contextualize_literal(item, cast(astx.DataType, target.value_type))


@private
@typechecked
def literal_semantic(node: astx.AST) -> SemanticInfo:
    """
    title: Obtain a literal's semantic sidecar without modifying its payload.
    parameters:
      node: Syntax node to process.
    returns: 'Result of this operation: obtain a literal''s semantic sidecar
      without modifying its payload.'
    """
    info = getattr(node, "semantic", None)
    if not isinstance(info, SemanticInfo):
        info = SemanticInfo()
        setattr(node, "semantic", info)
    return info


@private
@typechecked
def resolve_numeric_literal(
    node: astx.AST, diagnostics: DiagnosticBag
) -> astx.DataType | None:
    """
    title: Resolve exact or explicitly typed literals into semantic
      metadata.
    summary: Consume any expected type for this visit; stale prior
      resolutions never determine a context-typed literal's default.
      Preserve original values and declared types, including explicitly
      typed floating payloads.
    parameters:
      node: Syntax node to process.
      diagnostics: Collected structured diagnostics.
    returns: Resolved exact or explicitly typed literals into semantic
      metadata.
    """
    if not isinstance(node, astx.Literal):
        return None
    info = literal_semantic(node)
    expected = info.literal_context
    info.literal_context = None
    info.numeric_constant = None
    target = node.type_
    if isinstance(node, (astx.LiteralInteger, astx.LiteralFloat)):
        target = (
            expected
            if expected is not None
            else default_numeric_literal_type(node)
        )
    if not isinstance(target, astx.DataType):
        return None
    if isinstance(target, astx.UInt128):
        diagnostics.add(
            "UInt128 numeric execution is unsupported",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return target
    bounds = integer_bounds(target)
    invalid = False
    constant: int | float | None = None
    if bounds is not None and isinstance(node.value, int):
        constant = node.value
        invalid = not bounds[0] <= constant <= bounds[1]
    elif type(target) in FLOAT_PRECISIONS:
        try:
            constant = rounded_float(node.value, target)
            invalid = (
                not math.isfinite(constant)
                if isinstance(node, (astx.LiteralInteger, astx.LiteralFloat))
                else math.isfinite(node.value) and not math.isfinite(constant)
            )
            if isinstance(node, astx.LiteralInteger):
                invalid = invalid or constant != node.value
        except (OverflowError, ValueError):
            invalid = True
    if invalid:
        diagnostics.add(
            f"numeric literal is not representable in {type(target).__name__}",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
    else:
        info.numeric_constant = constant
    return target


@private
@typechecked
def numeric_constant(node: astx.AST) -> int | float | None:
    """
    title: Read an already analyzed constant without evaluating user
      functions.
    parameters:
      node: Syntax node to process.
    returns: Read an already analyzed constant without evaluating
      user functions.
    """
    semantic = cast(SemanticInfo | None, getattr(node, "semantic", None))
    return semantic.numeric_constant if semantic is not None else None


@private
@typechecked
def analyze_constant_operation(
    node: astx.BinaryOp | astx.UnaryOp,
    context: SemanticContext,
    result_type: astx.DataType | None,
) -> None:
    """
    title: Diagnose evaluated literal integer operations with exact host
      integers.
    parameters:
      node: Syntax node to process.
      context: Context for the operation.
      result_type: Resolved result type.
    """
    if result_type is None:
        return
    bounds = integer_bounds(result_type)
    if bounds is None:
        return
    left: int | float | None
    if isinstance(node, astx.UnaryOp):
        left = 0
        right = numeric_constant(node.operand)
        op = node.op_code
        if op not in {"+", "-"}:
            return
    else:
        left = numeric_constant(node.lhs)
        right = numeric_constant(node.rhs)
        op = node.op_code
    if not isinstance(left, int) or not isinstance(right, int):
        return
    invalid = False
    if op == "+":
        value = left + right
    elif op == "-":
        value = left - right
    elif op == "*":
        value = left * right
    elif op in {"/", "%"}:
        invalid = right == 0 or (
            bounds[0] < 0 and left == bounds[0] and right == -1
        )
        if invalid:
            value = 0
        else:
            quotient = abs(left) // abs(right)
            if (left < 0) != (right < 0):
                quotient = -quotient
            value = quotient if op == "/" else left - quotient * right
    else:
        return
    if (
        isinstance(node, astx.BinaryOp)
        and node.mode is astx.NumericMode.WRAPPING
    ):
        value = (value - bounds[0]) % (bounds[1] - bounds[0] + 1) + bounds[0]
    invalid = invalid or not bounds[0] <= value <= bounds[1]
    if invalid:
        if context.check_constant_expressions:
            context.diagnostics.add(
                "constant integer arithmetic is out of range or has an "
                "invalid divisor; widen operands before the operation "
                "or request wrapping explicitly",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        return
    semantic = cast(SemanticInfo, getattr(node, "semantic"))
    semantic.numeric_constant = value


@private
@typechecked
def analyze_constant_cast(node: astx.Cast, context: SemanticContext) -> None:
    """
    title: Check constant conversions using the same truncated integer domains.
    parameters:
      node: Syntax node to process.
      context: Context for the operation.
    """
    value = numeric_constant(node.value)
    if value is None:
        return
    info = cast(SemanticInfo, getattr(node, "semantic"))
    plan = info.numeric_conversion
    if plan is None:
        return
    bounds = integer_bounds(plan.target_type)
    invalid = False
    result: int | float = value
    if bounds is not None:
        if isinstance(value, float) and not math.isfinite(value):
            invalid = True
        else:
            result = int(value)
            if node.mode is astx.NumericMode.WRAPPING:
                result = (result - bounds[0]) % (
                    bounds[1] - bounds[0] + 1
                ) + bounds[0]
            invalid = not bounds[0] <= result <= bounds[1]
    else:
        try:
            result = rounded_float(value, plan.target_type)
            invalid = math.isfinite(value) and not math.isfinite(result)
        except OverflowError:
            invalid = True
    if invalid:
        if context.check_constant_expressions:
            context.diagnostics.add(
                "constant numeric conversion is out of range",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        return
    info.numeric_constant = result
