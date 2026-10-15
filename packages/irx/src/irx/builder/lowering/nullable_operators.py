"""
title: Null-propagating scalar arithmetic and short-circuit Kleene logic.
"""

from __future__ import annotations

import astx

from llvmlite import ir
from public import private, public

from irx.analysis.nullability import ResolvedNullableOperator
from irx.analysis.resolved_nodes import SemanticInfo
from irx.analysis.types import is_float_type, is_signed_integer_type
from irx.builder.core import VisitorCore
from irx.builder.diagnostics import raise_lowering_internal_error
from irx.builder.runtime import safe_pop
from irx.typecheck import typechecked


@private
@typechecked
class NullableEmitter:
    """
    title: Emit a validated primitive nullable operation without reading nulls.
    attributes:
      core:
        type: VisitorCore
      node:
        type: astx.BinaryOp | astx.UnaryOp
      resolved:
        type: ResolvedNullableOperator
      builder:
        type: ir.IRBuilder
      result_type:
        type: ir.Type
    """

    core: VisitorCore
    node: astx.BinaryOp | astx.UnaryOp
    resolved: ResolvedNullableOperator
    builder: ir.IRBuilder
    result_type: ir.Type

    def __init__(
        self,
        core: VisitorCore,
        node: astx.BinaryOp | astx.UnaryOp,
        resolved: ResolvedNullableOperator,
    ) -> None:
        """
        title: Bind resolved scalar metadata to the active LLVM builder.
        parameters:
          core:
            type: VisitorCore
          node:
            type: astx.BinaryOp | astx.UnaryOp
          resolved:
            type: ResolvedNullableOperator
        """
        self.core = core
        self.node = node
        self.resolved = resolved
        self.builder = core._llvm.ir_builder
        result_type = core._llvm_type_for_ast_type(
            astx.NullableType(resolved.payload_type)
        )
        assert result_type is not None
        self.result_type = result_type

    def operand(self, node: astx.AST, type_: astx.DataType) -> ir.Value:
        """
        title: Evaluate an operand once and inject nonnullable scalar values.
        parameters:
          node:
            type: astx.AST
          type_:
            type: astx.DataType
        returns:
          type: ir.Value
        """
        self.core.visit_child(node)
        return self.core._cast_ast_value(
            safe_pop(self.core.result_stack),
            source_type=type_,
            target_type=(
                type_
                if isinstance(type_, astx.NullableType)
                else astx.NullableType(type_)
            ),
        )

    def payload(self, value: ir.Value, type_: astx.DataType) -> ir.Value:
        """
        title: Extract and convert a payload only inside a valid branch.
        parameters:
          value:
            type: ir.Value
          type_:
            type: astx.DataType
        returns:
          type: ir.Value
        """
        return self.core._cast_ast_value(
            self.builder.extract_value(value, 1),
            source_type=(
                type_.payload_type
                if isinstance(type_, astx.NullableType)
                else type_
            ),
            target_type=self.resolved.operand_type,
        )

    def pack(self, valid: ir.Value, payload: ir.Value) -> ir.Value:
        """
        title: Assemble one language-owned validity and payload pair.
        parameters:
          valid:
            type: ir.Value
          payload:
            type: ir.Value
        returns:
          type: ir.Value
        """
        value = self.builder.insert_value(
            ir.Constant(self.result_type, None), valid, 0
        )
        return self.builder.insert_value(value, payload, 1)

    def guard_divisor(self, lhs: ir.Value, rhs: ir.Value) -> None:
        """
        title: Check integer division only when both operands are valid.
        parameters:
          lhs:
            type: ir.Value
          rhs:
            type: ir.Value
        """
        builder = self.builder
        invalid = builder.icmp_unsigned("==", rhs, ir.Constant(rhs.type, 0))
        if is_signed_integer_type(self.resolved.operand_type):
            assert isinstance(lhs.type, ir.IntType)
            minimum = ir.Constant(lhs.type, -(1 << (lhs.type.width - 1)))
            overflow = builder.and_(
                builder.icmp_signed("==", lhs, minimum),
                builder.icmp_signed("==", rhs, ir.Constant(rhs.type, -1)),
            )
            invalid = builder.or_(invalid, overflow)
        self.core._guard_runtime_condition(
            self.node,
            builder.not_(invalid),
            code="ARX-RUNTIME-ARITHMETIC-001",
            message="nullable integer division has zero divisor or overflow",
            block_name="nullable.division",
        )

    def scalar(self, lhs: ir.Value, rhs: ir.Value | None) -> ir.Value:
        """
        title: Emit only the resolved numeric or Boolean payload operation.
        parameters:
          lhs:
            type: ir.Value
          rhs:
            type: ir.Value | None
        returns:
          type: ir.Value
        """
        builder = self.builder
        op = self.resolved.op_code
        floating = is_float_type(self.resolved.operand_type)
        if rhs is None:
            if op == "+":
                return lhs
            if op == "!":
                return builder.not_(lhs)
            return builder.fneg(lhs) if floating else builder.neg(lhs)
        if op in {"==", "!=", "<", "<=", ">", ">="}:
            if floating:
                # IEEE NaN is unequal, including when both operands are NaN.
                compare = (
                    builder.fcmp_unordered
                    if op == "!="
                    else builder.fcmp_ordered
                )
            else:
                compare = (
                    builder.icmp_signed
                    if is_signed_integer_type(self.resolved.operand_type)
                    else builder.icmp_unsigned
                )
            return compare(op, lhs, rhs)
        if op in {"/", "%"} and not floating:
            self.guard_divisor(lhs, rhs)
        if floating:
            operation = {
                "+": builder.fadd,
                "-": builder.fsub,
                "*": builder.fmul,
                "/": builder.fdiv,
                "%": builder.frem,
            }[op]
        else:
            signed = is_signed_integer_type(self.resolved.operand_type)
            operation = {
                "+": builder.add,
                "-": builder.sub,
                "*": builder.mul,
                "/": builder.sdiv if signed else builder.udiv,
                "%": builder.srem if signed else builder.urem,
                "&": builder.and_,
                "|": builder.or_,
                "^": builder.xor,
            }[op]
        return operation(lhs, rhs)

    def propagate(self) -> ir.Value:
        """
        title: Skip all payload work unless every operand is valid.
        returns:
          type: ir.Value
        """
        node, resolved, builder = self.node, self.resolved, self.builder
        lhs = self.operand(
            node.lhs if isinstance(node, astx.BinaryOp) else node.operand,
            resolved.lhs_type,
        )
        valid = builder.extract_value(lhs, 0)
        rhs = None
        if isinstance(node, astx.BinaryOp) and resolved.rhs_type is not None:
            rhs = self.operand(node.rhs, resolved.rhs_type)
            valid = builder.and_(valid, builder.extract_value(rhs, 0))
        origin = builder.block
        success = builder.function.append_basic_block("nullable.valid")
        end = builder.function.append_basic_block("nullable.end")
        builder.cbranch(valid, success, end)
        builder.position_at_end(success)
        result = self.scalar(
            self.payload(lhs, resolved.lhs_type),
            self.payload(rhs, resolved.rhs_type)
            if rhs is not None and resolved.rhs_type is not None
            else None,
        )
        packed = self.pack(ir.Constant(ir.IntType(1), 1), result)
        final_success = builder.block
        builder.branch(end)
        builder.position_at_end(end)
        phi = builder.phi(self.result_type, "nullable.result")
        phi.add_incoming(ir.Constant(self.result_type, None), origin)
        phi.add_incoming(packed, final_success)
        return phi

    def safe_boolean(self, value: ir.Value) -> tuple[ir.Value, ir.Value]:
        """
        title: Supply a placeholder without extracting an invalid payload.
        parameters:
          value:
            type: ir.Value
        returns:
          type: tuple[ir.Value, ir.Value]
        """
        builder = self.builder
        valid = builder.extract_value(value, 0)
        origin = builder.block
        success = builder.function.append_basic_block("kleene.valid")
        end = builder.function.append_basic_block("kleene.payload")
        builder.cbranch(valid, success, end)
        builder.position_at_end(success)
        payload = builder.extract_value(value, 1)
        builder.branch(end)
        builder.position_at_end(end)
        result = builder.phi(ir.IntType(1))
        result.add_incoming(ir.Constant(ir.IntType(1), 0), origin)
        result.add_incoming(payload, success)
        return valid, result

    def kleene(self) -> ir.Value:
        """
        title: Short circuit decisive valid Booleans and propagate unknowns.
        returns:
          type: ir.Value
        """
        node, resolved, builder = self.node, self.resolved, self.builder
        assert isinstance(node, astx.BinaryOp)
        assert resolved.rhs_type is not None
        is_or = resolved.op_code in {"or", "||"}
        lv, lp = self.safe_boolean(self.operand(node.lhs, resolved.lhs_type))
        decisive = builder.and_(lv, lp if is_or else builder.not_(lp))
        shortcut = self.pack(ir.Constant(ir.IntType(1), 1), lp)
        origin = builder.block
        evaluate = builder.function.append_basic_block("kleene.rhs")
        end = builder.function.append_basic_block("kleene.end")
        builder.cbranch(decisive, end, evaluate)
        builder.position_at_end(evaluate)
        cleanup_depth = len(self.core.cleanup_stack)
        rv, rp = self.safe_boolean(self.operand(node.rhs, resolved.rhs_type))
        rhs_decisive = builder.and_(rv, rp if is_or else builder.not_(rp))
        valid = builder.or_(builder.and_(lv, rv), rhs_decisive)
        payload = builder.or_(lp, rp) if is_or else builder.and_(lp, rp)
        result = self.pack(valid, payload)
        self.core._emit_temporary_cleanups(cleanup_depth)
        evaluated = builder.block
        builder.branch(end)
        builder.position_at_end(end)
        phi = builder.phi(self.result_type, "kleene.result")
        phi.add_incoming(shortcut, origin)
        phi.add_incoming(result, evaluated)
        return phi


@public
@typechecked
def lower_nullable_operator(
    core: VisitorCore, node: astx.BinaryOp | astx.UnaryOp
) -> bool:
    """
    title: Handle resolved nullable operators before ordinary scalar dispatch.
    parameters:
      core:
        type: VisitorCore
      node:
        type: astx.BinaryOp | astx.UnaryOp
    returns:
      type: bool
    """
    semantic = getattr(node, "semantic", None)
    if not isinstance(semantic, SemanticInfo):
        return False
    resolved = semantic.resolved_nullable_operator
    if resolved is None:
        if isinstance(semantic.resolved_type, astx.NullableType) and (
            node.op_code != "="
        ):
            raise_lowering_internal_error(
                "missing resolved nullable operator", node=node
            )
        return False
    emitter = NullableEmitter(core, node, resolved)
    core.result_stack.append(
        emitter.kleene() if resolved.kleene else emitter.propagate()
    )
    return True
