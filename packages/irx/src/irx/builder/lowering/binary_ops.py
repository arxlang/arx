# mypy: disable-error-code=no-redef

"""
title: Binary-operator lowering implementations for llvmliteir.
"""

from __future__ import annotations

from typing import cast

import astx

from astx.binary_op import (
    SPECIALIZED_BINARY_OP_EXTRA,
    AddBinOp,
    AssignmentBinOp,
    BitAndBinOp,
    BitOrBinOp,
    BitXorBinOp,
    DivBinOp,
    EqBinOp,
    GeBinOp,
    GtBinOp,
    LeBinOp,
    LogicalAndBinOp,
    LogicalOrBinOp,
    LtBinOp,
    ModBinOp,
    MulBinOp,
    NeBinOp,
    SubBinOp,
    specialize_binary_op,
)
from llvmlite import ir
from plum import dispatch
from public import private

from irx.analysis.arrow_conversion import ARROW_RESOURCES
from irx.analysis.resolved_nodes import (
    ImplicitConversion,
    OwnershipTransferKind,
    ResourceKind,
    SemanticFlags,
    SemanticInfo,
)
from irx.analysis.types import is_string_type
from irx.builder.diagnostics import (
    raise_lowering_error,
    raise_lowering_internal_error,
    require_lowered_value,
    require_semantic_metadata,
)
from irx.builder.lowering.contracts import BinaryServices
from irx.builder.runtime import safe_pop
from irx.builder.services.representations import (
    resolved_type as resolved_ast_type,
)
from irx.builder.services.representations import (
    semantic_assignment_key,
    semantic_info,
)
from irx.builder.types import is_fp_type, is_int_type
from irx.builder.vector import emit_add, emit_int_div, is_vector
from irx.diagnostics import DiagnosticCodes
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class BinaryLowering:
    """
    title: Lower binary operations to LLVM.
    attributes:
      services:
        type: BinaryServices
    """

    services: BinaryServices

    def __init__(self, services: BinaryServices) -> None:
        """
        title: Bind explicit family-owned emission dependencies.
        parameters:
          services:
            type: BinaryServices
        """
        self.services = services

    @dispatch
    def visit(self, node: astx.AST) -> None:
        """
        title: Fail closed for nodes not exported by this feature family.
        parameters:
          node:
            type: astx.AST
        """
        raise_lowering_internal_error(
            f"no binary_ops handler for {type(node).__name__}", node=node
        )

    def node_handlers(self) -> tuple[NodeHandler, ...]:
        """
        title: >-
          Export explicit concrete signatures without mutating a shared
          dispatcher.
        returns:
          type: tuple[NodeHandler, Ellipsis]
        """
        return (
            contribute_node(
                "llvm.binary_ops.AugAssign",
                "irx.binary_ops",
                "lowering",
                astx.AugAssign,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.BinaryOp",
                "irx.binary_ops",
                "lowering",
                astx.BinaryOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.AssignmentBinOp",
                "irx.binary_ops",
                "lowering",
                AssignmentBinOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.AddBinOp",
                "irx.binary_ops",
                "lowering",
                AddBinOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.SubBinOp",
                "irx.binary_ops",
                "lowering",
                SubBinOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.MulBinOp",
                "irx.binary_ops",
                "lowering",
                MulBinOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.DivBinOp",
                "irx.binary_ops",
                "lowering",
                DivBinOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.ModBinOp",
                "irx.binary_ops",
                "lowering",
                ModBinOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.LogicalAndBinOp",
                "irx.binary_ops",
                "lowering",
                LogicalAndBinOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.LogicalOrBinOp",
                "irx.binary_ops",
                "lowering",
                LogicalOrBinOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.LtBinOp",
                "irx.binary_ops",
                "lowering",
                LtBinOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.GtBinOp",
                "irx.binary_ops",
                "lowering",
                GtBinOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.LeBinOp",
                "irx.binary_ops",
                "lowering",
                LeBinOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.GeBinOp",
                "irx.binary_ops",
                "lowering",
                GeBinOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.EqBinOp",
                "irx.binary_ops",
                "lowering",
                EqBinOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.NeBinOp",
                "irx.binary_ops",
                "lowering",
                NeBinOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.BitOrBinOp",
                "irx.binary_ops",
                "lowering",
                BitOrBinOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.BitAndBinOp",
                "irx.binary_ops",
                "lowering",
                BitAndBinOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
            contribute_node(
                "llvm.binary_ops.BitXorBinOp",
                "irx.binary_ops",
                "lowering",
                BitXorBinOp,
                self.visit,
                source="irx.builder.lowering.binary_ops.BinaryLowering.visit",
            ),
        )

    def compound_conversion(
        self,
        node: astx.AugAssign,
        value: ir.Value,
        conversion: ImplicitConversion,
    ) -> ir.Value:
        """
        title: Apply an analyzed lossless scalar compound conversion.
        parameters:
          node:
            type: astx.AugAssign
          value:
            type: ir.Value
          conversion:
            type: ImplicitConversion
        returns:
          type: ir.Value
        """
        numeric = require_semantic_metadata(
            conversion.numeric,
            node=node,
            metadata="numeric conversion",
            context="compound assignment",
        )
        if not numeric.implicit:
            raise_lowering_internal_error(
                "compound assignment requires a lossless conversion plan",
                node=node,
            )
        return self.services.numeric.cast_scalar(
            value,
            source_type=numeric.source_type,
            target_type=numeric.target_type,
        )

    @dispatch
    def visit(self, node: astx.AugAssign) -> None:
        """
        title: Load, compute, and store a resolved scalar compound mutation.
        summary: >-
          Snapshot the target before evaluating the RHS once. Guards and
          conversions precede the single store; failure preserves the target
          except for independent RHS effects. Push only the stored result.
        parameters:
          node:
            type: astx.AugAssign
        """
        semantic = require_semantic_metadata(
            cast(SemanticInfo | None, getattr(node, "semantic", None)),
            node=node,
            metadata="semantic",
            context="compound assignment",
        )
        plan = require_semantic_metadata(
            semantic.resolved_aug_assignment,
            node=node,
            metadata="resolved_aug_assignment",
            context="compound assignment",
        )
        operation = plan.operation
        require_semantic_metadata(
            operation.computation_type,
            node=node,
            metadata="computation_type",
            context="compound assignment",
        )
        left = require_semantic_metadata(
            operation.lhs_conversion,
            node=node,
            metadata="lhs_conversion",
            context="compound assignment",
        )
        right = require_semantic_metadata(
            operation.rhs_conversion,
            node=node,
            metadata="rhs_conversion",
            context="compound assignment",
        )
        op = operation.op_code
        if op not in {"+", "-", "*", "/", "%"}:
            raise_lowering_internal_error(
                "unsupported resolved compound operator", node=node
            )
        address = self.services.function_state.named_values.get(
            plan.target.symbol_id
        )
        if address is None:
            raise_lowering_internal_error(
                "compound assignment target has no resolved storage", node=node
            )
        old = self.services.llvm.ir_builder.load(address)
        self.services.visit_child(node.value)
        rhs = require_lowered_value(
            safe_pop(self.services.function_state.result_stack),
            node=node.value,
            context="compound assignment RHS",
        )
        lhs = self.compound_conversion(node, old, left)
        rhs = self.compound_conversion(node, rhs, right)
        if is_fp_type(lhs.type):
            if op == "%":
                # LLVM frem may become a platform fmod call at link time.
                self.services.runtime_features.activate("libm")
            instruction = {
                "+": "fadd",
                "-": "fsub",
                "*": "fmul",
                "/": "fdiv",
                "%": "frem",
            }[op]
            result = getattr(self.services.llvm.ir_builder, instruction)(
                lhs, rhs
            )
        elif op in {"+", "-", "*"}:
            result = self.services.numeric.integer_operation(
                node, lhs, rhs, operation, op
            )
        else:
            self._guard_scalar_integer_divisor(
                node, lhs, rhs, unsigned=operation.flags.unsigned
            )
            instruction = ("u" if operation.flags.unsigned else "s") + (
                "div" if op == "/" else "rem"
            )
            result = getattr(self.services.llvm.ir_builder, instruction)(
                lhs, rhs
            )
        result = self.compound_conversion(node, result, plan.store_conversion)
        self.services.llvm.ir_builder.store(result, address)
        self.services.function_state.result_stack.append(result)

    def _resolved_binary_variant(self, node: astx.BinaryOp) -> astx.BinaryOp:
        """
        title: Resolved binary variant.
        parameters:
          node:
            type: astx.BinaryOp
        returns:
          type: astx.BinaryOp
        """
        semantic = getattr(node, "semantic", None)
        extras = getattr(semantic, "extras", None)
        if isinstance(extras, dict):
            specialized = extras.get(SPECIALIZED_BINARY_OP_EXTRA)
            if isinstance(specialized, astx.BinaryOp):
                return specialized
        return specialize_binary_op(node)

    def _load_binary_operands(
        self,
        node: astx.BinaryOp,
        *,
        unify_numeric: bool = True,
    ) -> tuple[ir.Value, ir.Value, bool]:
        """
        title: Load binary operands.
        parameters:
          node:
            type: astx.BinaryOp
          unify_numeric:
            type: bool
        returns:
          type: tuple[ir.Value, ir.Value, bool]
        """
        self.services.visit_child(node.lhs)
        llvm_lhs = safe_pop(self.services.function_state.result_stack)
        self.services.visit_child(node.rhs)
        llvm_rhs = safe_pop(self.services.function_state.result_stack)

        if llvm_lhs is None or llvm_rhs is None:
            raise_lowering_internal_error(
                "codegen: Invalid lhs/rhs", node=node
            )

        unsigned = False
        if (
            unify_numeric
            and self.services.numeric.is_numeric_value(llvm_lhs)
            and self.services.numeric.is_numeric_value(llvm_rhs)
        ):
            semantic = require_semantic_metadata(
                getattr(node, "semantic", None),
                node=node,
                metadata="semantic",
                context="binary",
            )
            operation = require_semantic_metadata(
                semantic.resolved_operator,
                node=node,
                metadata="resolved_operator",
                context="numeric operands",
            )
            require_semantic_metadata(
                operation.computation_type,
                node=node,
                metadata="computation_type",
                context="numeric operands",
            )
            unsigned = operation.flags.unsigned
            left = require_semantic_metadata(
                operation.lhs_conversion,
                node=node,
                metadata="lhs_conversion",
                context="numeric operands",
            )
            right = require_semantic_metadata(
                operation.rhs_conversion,
                node=node,
                metadata="rhs_conversion",
                context="numeric operands",
            )
            llvm_lhs = self.services.numeric.cast_scalar(
                llvm_lhs,
                source_type=require_semantic_metadata(
                    left.source_type,
                    node=node,
                    metadata="lhs_conversion.source_type",
                    context="numeric operands",
                ),
                target_type=require_semantic_metadata(
                    left.target_type,
                    node=node,
                    metadata="lhs_conversion.target_type",
                    context="numeric operands",
                ),
            )
            llvm_rhs = self.services.numeric.cast_scalar(
                llvm_rhs,
                source_type=require_semantic_metadata(
                    right.source_type,
                    node=node,
                    metadata="rhs_conversion.source_type",
                    context="numeric operands",
                ),
                target_type=require_semantic_metadata(
                    right.target_type,
                    node=node,
                    metadata="rhs_conversion.target_type",
                    context="numeric operands",
                ),
            )

        return llvm_lhs, llvm_rhs, unsigned

    def operator_flags(self, node: astx.BinaryOp) -> SemanticFlags:
        """
        title: Consume normalized operator flags without raw-node fallbacks.
        parameters:
          node:
            type: astx.BinaryOp
        returns:
          type: SemanticFlags
        """
        operation = require_semantic_metadata(
            semantic_info(node).resolved_operator,
            node=node,
            metadata="resolved_operator",
            context="binary flags",
        )
        return operation.flags

    def _emit_vector_add(
        self,
        node: AddBinOp,
        llvm_lhs: ir.Value,
        llvm_rhs: ir.Value,
    ) -> ir.Value | None:
        """
        title: Emit vector add.
        parameters:
          node:
            type: AddBinOp
          llvm_lhs:
            type: ir.Value
          llvm_rhs:
            type: ir.Value
        returns:
          type: ir.Value | None
        """
        if not (is_vector(llvm_lhs) and is_vector(llvm_rhs)):
            return None

        is_float_vec = is_fp_type(llvm_lhs.type.element)
        prev_fast_math = self.services.floating.enabled
        if is_float_vec and self.operator_flags(node).fast_math:
            self.services.floating.set_fast_math(True)
        try:
            if is_float_vec:
                result = self.services.llvm.ir_builder.fadd(
                    llvm_lhs, llvm_rhs, name="vfaddtmp"
                )
                self.services.floating.apply_fast_math(result)
            else:
                result = self.services.numeric.resolved_integer_operation(
                    node, llvm_lhs, llvm_rhs, "+"
                )
        finally:
            self.services.floating.set_fast_math(prev_fast_math)
        return result

    def _load_boolean_operands(
        self,
        node: astx.BinaryOp,
    ) -> tuple[ir.Value, ir.Value]:
        """
        title: Load Boolean operands for logical operators.
        parameters:
          node:
            type: astx.BinaryOp
        returns:
          type: tuple[ir.Value, ir.Value]
        """
        llvm_lhs, llvm_rhs, _unsigned = self._load_binary_operands(
            node,
            unify_numeric=False,
        )
        if (
            not is_int_type(llvm_lhs.type)
            or llvm_lhs.type.width != 1
            or not is_int_type(llvm_rhs.type)
            or llvm_rhs.type.width != 1
        ):
            raise_lowering_internal_error(
                (
                    "codegen: logical operator '"
                    f"{node.op_code}"
                    "' must lower Boolean operands."
                ),
                node=node,
            )
        return llvm_lhs, llvm_rhs

    def _lower_short_circuit_boolean(
        self,
        node: astx.BinaryOp,
        *,
        short_circuit_value: bool,
        name: str,
    ) -> None:
        """
        title: Lower one left-to-right short-circuit Boolean expression.
        parameters:
          node:
            type: astx.BinaryOp
          short_circuit_value:
            type: bool
          name:
            type: str
        """
        self.services.visit_child(node.lhs)
        llvm_lhs = safe_pop(self.services.function_state.result_stack)
        if (
            llvm_lhs is None
            or not is_int_type(llvm_lhs.type)
            or llvm_lhs.type.width != 1
        ):
            raise_lowering_internal_error(
                "logical operator lhs must lower to Boolean i1",
                node=node.lhs,
            )

        lhs_block = self.services.llvm.ir_builder.block
        function = self.services.llvm.ir_builder.function
        rhs_block = function.append_basic_block(f"logical.{name}.rhs")
        merge_block = function.append_basic_block(f"logical.{name}.merge")
        if short_circuit_value:
            self.services.llvm.ir_builder.cbranch(
                llvm_lhs,
                merge_block,
                rhs_block,
            )
        else:
            self.services.llvm.ir_builder.cbranch(
                llvm_lhs,
                rhs_block,
                merge_block,
            )

        self.services.llvm.ir_builder.position_at_start(rhs_block)
        self.services.visit_child(node.rhs)
        llvm_rhs = safe_pop(self.services.function_state.result_stack)
        if (
            llvm_rhs is None
            or not is_int_type(llvm_rhs.type)
            or llvm_rhs.type.width != 1
        ):
            raise_lowering_internal_error(
                "logical operator rhs must lower to Boolean i1",
                node=node.rhs,
            )
        rhs_end_block = self.services.llvm.ir_builder.block
        if rhs_end_block.is_terminated:
            raise_lowering_internal_error(
                "logical operator rhs terminated its expression block",
                node=node.rhs,
            )
        self.services.llvm.ir_builder.branch(merge_block)

        self.services.llvm.ir_builder.position_at_start(merge_block)
        result = self.services.llvm.ir_builder.phi(
            self.services.llvm.BOOLEAN_TYPE,
            name=name,
        )
        result.add_incoming(
            ir.Constant(self.services.llvm.BOOLEAN_TYPE, short_circuit_value),
            lhs_block,
        )
        result.add_incoming(llvm_rhs, rhs_end_block)
        self.services.function_state.result_stack.append(result)

    def _guard_scalar_integer_divisor(
        self,
        node: astx.AST,
        llvm_lhs: ir.Value,
        llvm_rhs: ir.Value,
        *,
        unsigned: bool,
    ) -> None:
        """
        title: Reject zero and unrepresentable signed integer division.
        parameters:
          node:
            type: astx.AST
          llvm_lhs:
            type: ir.Value
          llvm_rhs:
            type: ir.Value
          unsigned:
            type: bool
        """
        if not is_int_type(llvm_lhs.type) or not is_int_type(llvm_rhs.type):
            raise_lowering_internal_error(
                "integer division guard requires integer operands",
                node=node,
            )
        if llvm_lhs.type != llvm_rhs.type:
            raise_lowering_internal_error(
                "integer division guard requires unified operand types",
                node=node,
            )

        zero = ir.Constant(llvm_rhs.type, 0)
        valid = self.services.llvm.ir_builder.icmp_unsigned(
            "!=", llvm_rhs, zero
        )
        self.services.guards.guard(
            node,
            valid,
            code="ARX-RUNTIME-ARITHMETIC-001",
            message="integer division or remainder by zero",
            block_name="integer.division.zero",
            exception_role="ZeroDivisionError",
        )
        if not unsigned:
            width = llvm_lhs.type.width
            minimum = ir.Constant(llvm_lhs.type, -(1 << (width - 1)))
            negative_one = ir.Constant(llvm_rhs.type, -1)
            minimum_lhs = self.services.llvm.ir_builder.icmp_signed(
                "==", llvm_lhs, minimum
            )
            negative_one_rhs = self.services.llvm.ir_builder.icmp_signed(
                "==", llvm_rhs, negative_one
            )
            overflow = self.services.llvm.ir_builder.and_(
                minimum_lhs, negative_one_rhs
            )
            self.services.guards.guard(
                node,
                self.services.llvm.ir_builder.not_(overflow),
                code="ARX-RUNTIME-ARITHMETIC-001",
                message="integer division or remainder result overflows",
                block_name="integer.division.overflow",
                exception_role="OverflowError",
            )

    def _emit_vector_sub(
        self,
        node: SubBinOp,
        llvm_lhs: ir.Value,
        llvm_rhs: ir.Value,
    ) -> ir.Value | None:
        """
        title: Emit vector sub.
        parameters:
          node:
            type: SubBinOp
          llvm_lhs:
            type: ir.Value
          llvm_rhs:
            type: ir.Value
        returns:
          type: ir.Value | None
        """
        if not (is_vector(llvm_lhs) and is_vector(llvm_rhs)):
            return None

        is_float_vec = is_fp_type(llvm_lhs.type.element)
        prev_fast_math = self.services.floating.enabled
        if is_float_vec and self.operator_flags(node).fast_math:
            self.services.floating.set_fast_math(True)
        try:
            if is_float_vec:
                result = self.services.llvm.ir_builder.fsub(
                    llvm_lhs, llvm_rhs, name="vfsubtmp"
                )
                self.services.floating.apply_fast_math(result)
            else:
                result = self.services.numeric.resolved_integer_operation(
                    node, llvm_lhs, llvm_rhs, "-"
                )
        finally:
            self.services.floating.set_fast_math(prev_fast_math)
        return result

    def _emit_vector_mul(
        self,
        node: MulBinOp,
        llvm_lhs: ir.Value,
        llvm_rhs: ir.Value,
    ) -> ir.Value | None:
        """
        title: Emit vector mul.
        parameters:
          node:
            type: MulBinOp
          llvm_lhs:
            type: ir.Value
          llvm_rhs:
            type: ir.Value
        returns:
          type: ir.Value | None
        """
        if not (is_vector(llvm_lhs) and is_vector(llvm_rhs)):
            return None

        is_float_vec = is_fp_type(llvm_lhs.type.element)
        set_fast = is_float_vec and self.operator_flags(node).fast_math
        if self.operator_flags(node).fma and is_float_vec:
            fma_rhs_node = self.operator_flags(node).fma_rhs
            if fma_rhs_node is None:
                raise_lowering_internal_error(
                    "FMA requires a third operand (fma_rhs)", node=node
                )
            self.services.visit_child(fma_rhs_node)
            llvm_fma_rhs = safe_pop(self.services.function_state.result_stack)
            if llvm_fma_rhs is None:
                raise_lowering_internal_error(
                    "FMA requires a valid third operand", node=node
                )
            if llvm_fma_rhs.type != llvm_lhs.type:
                raise_lowering_internal_error(
                    (
                        "FMA operand type mismatch: "
                        f"{llvm_lhs.type}"
                        " vs "
                        f"{llvm_fma_rhs.type}"
                    ),
                    node=node,
                )
            prev_fast_math = self.services.floating.enabled
            if set_fast:
                self.services.floating.set_fast_math(True)
            try:
                return self.services.floating.emit_fma(
                    llvm_lhs, llvm_rhs, llvm_fma_rhs
                )
            finally:
                self.services.floating.set_fast_math(prev_fast_math)

        prev_fast_math = self.services.floating.enabled
        if set_fast:
            self.services.floating.set_fast_math(True)
        try:
            if is_float_vec:
                result = self.services.llvm.ir_builder.fmul(
                    llvm_lhs, llvm_rhs, name="vfmultmp"
                )
                self.services.floating.apply_fast_math(result)
            else:
                result = self.services.numeric.resolved_integer_operation(
                    node, llvm_lhs, llvm_rhs, "*"
                )
        finally:
            self.services.floating.set_fast_math(prev_fast_math)
        return result

    def _emit_vector_div(
        self,
        node: DivBinOp,
        llvm_lhs: ir.Value,
        llvm_rhs: ir.Value,
        *,
        unsigned: bool,
    ) -> ir.Value | None:
        """
        title: Emit vector div.
        parameters:
          node:
            type: DivBinOp
          llvm_lhs:
            type: ir.Value
          llvm_rhs:
            type: ir.Value
          unsigned:
            type: bool
        returns:
          type: ir.Value | None
        """
        if not (is_vector(llvm_lhs) and is_vector(llvm_rhs)):
            return None

        is_float_vec = is_fp_type(llvm_lhs.type.element)
        prev_fast_math = self.services.floating.enabled
        if is_float_vec and self.operator_flags(node).fast_math:
            self.services.floating.set_fast_math(True)
        try:
            if is_float_vec:
                result = self.services.llvm.ir_builder.fdiv(
                    llvm_lhs, llvm_rhs, name="vfdivtmp"
                )
                self.services.floating.apply_fast_math(result)
            else:
                for lane in range(llvm_lhs.type.count):
                    index = ir.Constant(ir.IntType(32), lane)
                    self._guard_scalar_integer_divisor(
                        node,
                        self.services.llvm.ir_builder.extract_element(
                            llvm_lhs, index
                        ),
                        self.services.llvm.ir_builder.extract_element(
                            llvm_rhs, index
                        ),
                        unsigned=unsigned,
                    )
                result = emit_int_div(
                    self.services.llvm.ir_builder, llvm_lhs, llvm_rhs, unsigned
                )
        finally:
            self.services.floating.set_fast_math(prev_fast_math)
        return result

    @dispatch
    def visit(self, node: astx.BinaryOp) -> None:
        """
        title: Visit BinaryOp nodes.
        parameters:
          node:
            type: astx.BinaryOp
        """
        if self.services.lower_column_operation(node):
            return
        specialized = self._resolved_binary_variant(node)
        if specialized is node:
            raise_lowering_error(
                f"Binary op {node.op_code} not implemented yet.",
                code=DiagnosticCodes.LOWERING_MISSING_HANDLER,
                node=node,
            )
        self.services.visit_child(specialized)

    @dispatch
    def visit(self, node: AssignmentBinOp) -> None:
        """
        title: Visit AssignmentBinOp nodes.
        parameters:
          node:
            type: AssignmentBinOp
        """
        if self.services.lower_column_operation(node):
            return
        var_lhs = node.lhs
        if not isinstance(
            var_lhs,
            (
                astx.Identifier,
                astx.FieldAccess,
                astx.BaseFieldAccess,
                astx.StaticFieldAccess,
            ),
        ):
            raise_lowering_internal_error(
                "destination of '=' must be a variable or field", node=node
            )

        lhs_name = (
            var_lhs.name
            if isinstance(var_lhs, astx.Identifier)
            else getattr(var_lhs, "field_name", "field")
        )
        lhs_key = semantic_assignment_key(node)
        if (
            isinstance(var_lhs, astx.Identifier)
            and lhs_key in self.services.function_state.const_vars
        ):
            raise_lowering_internal_error(
                f"Cannot assign to '{lhs_name}': declared as constant",
                node=node,
            )

        semantic = getattr(node, "semantic", None)
        managed = (
            semantic.resolved_resource_store if semantic is not None else None
        )
        if (
            managed is not None
            and managed.resource_kind
            in {ResourceKind.CLASS, ResourceKind.FILE, *ARROW_RESOURCES}
        ) or (semantic is not None and semantic.lifecycle_field_store):
            address = self.services.layout.lvalue_address(var_lhs)
            self.services.visit_child(node.rhs)
            value = require_lowered_value(
                safe_pop(self.services.function_state.result_stack),
                node=node.rhs,
                context="managed assignment",
            )
            value = self.services.numeric.cast_scalar(
                value,
                source_type=resolved_ast_type(node.rhs),
                target_type=resolved_ast_type(node),
            )
            assert managed is not None
            if managed.resource_kind in {ResourceKind.CLASS, *ARROW_RESOURCES}:
                value = self.services.class_acquire(node, value)
                previous = self.services.llvm.ir_builder.load(address)
                # A failing release still consumes the old reference. Publish
                # the new generation before checked rollback can revisit it.
                self.services.llvm.ir_builder.store(value, address)
                if managed.resource_kind in ARROW_RESOURCES:
                    assert managed.owner_symbol_id is not None
                    self.services.arrow_release_binding(
                        node, previous, managed.owner_symbol_id
                    )
                    count = self.services.arrow_reference_count(
                        managed.owner_symbol_id
                    )
                    self.services.llvm.ir_builder.store(
                        ir.Constant(ir.IntType(64), 1), count
                    )
                else:
                    self.services.class_operation(node, "release", previous)
            elif managed.resource_kind is ResourceKind.STRING:
                if managed.transfer_kind is OwnershipTransferKind.COPY:
                    value = self.services.strings.copy(node, value)
                free = self.services.require_runtime_symbol("libc", "free")
                self.services.llvm.ir_builder.call(
                    free, [self.services.llvm.ir_builder.load(address)]
                )
            if managed.resource_kind not in {
                ResourceKind.CLASS,
                *ARROW_RESOURCES,
            }:
                self.services.llvm.ir_builder.store(value, address)
            self.services.function_state.result_stack.append(value)
            return
        self.services.visit_child(node.rhs)
        llvm_rhs = safe_pop(self.services.function_state.result_stack)
        if llvm_rhs is None:
            raise_lowering_internal_error(
                "codegen: Invalid rhs expression.", node=node
            )
        llvm_rhs = self.services.numeric.cast_scalar(
            llvm_rhs,
            source_type=resolved_ast_type(node.rhs),
            target_type=resolved_ast_type(node),
        )

        llvm_lhs = self.services.layout.lvalue_address(var_lhs)
        if isinstance(resolved_ast_type(node), (astx.ListType, astx.Bytes)):
            if not isinstance(var_lhs, astx.Identifier):
                raise_lowering_internal_error(
                    "list field assignment reached lowering without an "
                    "object-field ownership contract",
                    node=node,
                )
            self.services.destroy_replaced_list(
                node,
                llvm_lhs,
                target_name=lhs_name,
            )
        elif is_string_type(resolved_ast_type(node)) and isinstance(
            var_lhs,
            astx.Identifier,
        ):
            self.services.destroy_replaced_string(
                node,
                llvm_lhs,
                target_name=lhs_name,
            )
        self.services.llvm.ir_builder.store(llvm_rhs, llvm_lhs)
        self.services.function_state.result_stack.append(llvm_rhs)

    @dispatch
    def visit(self, node: AddBinOp) -> None:
        """
        title: Visit AddBinOp nodes.
        parameters:
          node:
            type: AddBinOp
        """
        if self.services.lower_column_operation(node):
            return
        llvm_lhs, llvm_rhs, _unsigned = self._load_binary_operands(node)

        vector_result = self._emit_vector_add(node, llvm_lhs, llvm_rhs)
        if vector_result is not None:
            self.services.function_state.result_stack.append(vector_result)
            return

        if (
            isinstance(llvm_lhs.type, ir.PointerType)
            and isinstance(llvm_rhs.type, ir.PointerType)
            and llvm_lhs.type.pointee == self.services.llvm.INT8_TYPE
            and llvm_rhs.type.pointee == self.services.llvm.INT8_TYPE
        ):
            result = self.services.strings.concatenate(
                node,
                llvm_lhs,
                llvm_rhs,
            )
            self.services.cleanup.register_owned_string_temporary(node, result)
        elif is_int_type(llvm_lhs.type):
            result = self.services.numeric.resolved_integer_operation(
                node, llvm_lhs, llvm_rhs, "+"
            )
        else:
            result = emit_add(
                self.services.llvm.ir_builder, llvm_lhs, llvm_rhs, "addtmp"
            )
        self.services.function_state.result_stack.append(result)

    @dispatch
    def visit(self, node: SubBinOp) -> None:
        """
        title: Visit SubBinOp nodes.
        parameters:
          node:
            type: SubBinOp
        """
        if self.services.lower_column_operation(node):
            return
        llvm_lhs, llvm_rhs, _unsigned = self._load_binary_operands(node)

        if self.services.collection.try_set_binary_op(
            llvm_lhs, llvm_rhs, node.op_code
        ):
            return

        vector_result = self._emit_vector_sub(node, llvm_lhs, llvm_rhs)
        if vector_result is not None:
            self.services.function_state.result_stack.append(vector_result)
            return

        if is_fp_type(llvm_lhs.type):
            result = self.services.llvm.ir_builder.fsub(
                llvm_lhs, llvm_rhs, "subtmp"
            )
            self.services.floating.apply_fast_math(result)
        else:
            result = self.services.numeric.resolved_integer_operation(
                node, llvm_lhs, llvm_rhs, "-"
            )
        self.services.function_state.result_stack.append(result)

    @dispatch
    def visit(self, node: MulBinOp) -> None:
        """
        title: Visit MulBinOp nodes.
        parameters:
          node:
            type: MulBinOp
        """
        if self.services.lower_column_operation(node):
            return
        llvm_lhs, llvm_rhs, _unsigned = self._load_binary_operands(node)

        vector_result = self._emit_vector_mul(node, llvm_lhs, llvm_rhs)
        if vector_result is not None:
            self.services.function_state.result_stack.append(vector_result)
            return

        if is_fp_type(llvm_lhs.type):
            result = self.services.llvm.ir_builder.fmul(
                llvm_lhs, llvm_rhs, "multmp"
            )
            self.services.floating.apply_fast_math(result)
        else:
            result = self.services.numeric.resolved_integer_operation(
                node, llvm_lhs, llvm_rhs, "*"
            )
        self.services.function_state.result_stack.append(result)

    @dispatch
    def visit(self, node: DivBinOp) -> None:
        """
        title: Visit DivBinOp nodes.
        parameters:
          node:
            type: DivBinOp
        """
        if self.services.lower_column_operation(node):
            return
        llvm_lhs, llvm_rhs, unsigned = self._load_binary_operands(node)

        vector_result = self._emit_vector_div(
            node,
            llvm_lhs,
            llvm_rhs,
            unsigned=unsigned,
        )
        if vector_result is not None:
            self.services.function_state.result_stack.append(vector_result)
            return

        if is_fp_type(llvm_lhs.type):
            result = self.services.llvm.ir_builder.fdiv(
                llvm_lhs, llvm_rhs, "divtmp"
            )
            self.services.floating.apply_fast_math(result)
        elif unsigned:
            self._guard_scalar_integer_divisor(
                node,
                llvm_lhs,
                llvm_rhs,
                unsigned=True,
            )
            result = self.services.llvm.ir_builder.udiv(
                llvm_lhs, llvm_rhs, "divtmp"
            )
        else:
            self._guard_scalar_integer_divisor(
                node,
                llvm_lhs,
                llvm_rhs,
                unsigned=False,
            )
            result = self.services.llvm.ir_builder.sdiv(
                llvm_lhs, llvm_rhs, "divtmp"
            )
        self.services.function_state.result_stack.append(result)

    @dispatch
    def visit(self, node: ModBinOp) -> None:
        """
        title: Visit ModBinOp nodes.
        parameters:
          node:
            type: ModBinOp
        """
        llvm_lhs, llvm_rhs, unsigned = self._load_binary_operands(node)

        if is_vector(llvm_lhs) and is_vector(llvm_rhs):
            raise_lowering_error(
                f"Vector binop {node.op_code} not implemented.",
                code=DiagnosticCodes.LOWERING_MISSING_HANDLER,
                node=node,
            )

        if is_fp_type(llvm_lhs.type) or is_fp_type(llvm_rhs.type):
            result = self.services.llvm.ir_builder.frem(
                llvm_lhs, llvm_rhs, "fremtmp"
            )
        elif unsigned:
            self._guard_scalar_integer_divisor(
                node,
                llvm_lhs,
                llvm_rhs,
                unsigned=True,
            )
            result = self.services.llvm.ir_builder.urem(
                llvm_lhs, llvm_rhs, "uremtmp"
            )
        else:
            self._guard_scalar_integer_divisor(
                node,
                llvm_lhs,
                llvm_rhs,
                unsigned=False,
            )
            result = self.services.llvm.ir_builder.srem(
                llvm_lhs, llvm_rhs, "sremtmp"
            )
        self.services.function_state.result_stack.append(result)

    @dispatch
    def visit(self, node: LogicalAndBinOp) -> None:
        """
        title: Visit LogicalAndBinOp nodes.
        parameters:
          node:
            type: LogicalAndBinOp
        """
        if self.services.lower_column_operation(node):
            return
        self._lower_short_circuit_boolean(
            node,
            short_circuit_value=False,
            name="andtmp",
        )

    @dispatch
    def visit(self, node: LogicalOrBinOp) -> None:
        """
        title: Visit LogicalOrBinOp nodes.
        parameters:
          node:
            type: LogicalOrBinOp
        """
        if self.services.lower_column_operation(node):
            return
        self._lower_short_circuit_boolean(
            node,
            short_circuit_value=True,
            name="ortmp",
        )

    @dispatch
    def visit(self, node: LtBinOp) -> None:
        """
        title: Visit LtBinOp nodes.
        parameters:
          node:
            type: LtBinOp
        """
        if self.services.lower_column_operation(node):
            return
        llvm_lhs, llvm_rhs, unsigned = self._load_binary_operands(node)
        if is_vector(llvm_lhs) and is_vector(llvm_rhs):
            raise_lowering_error(
                f"Vector binop {node.op_code} not implemented.",
                code=DiagnosticCodes.LOWERING_MISSING_HANDLER,
                node=node,
            )
        result = self.services.numeric.emit_numeric_compare(
            "<",
            llvm_lhs,
            llvm_rhs,
            unsigned=unsigned,
            name="lttmp",
        )
        self.services.function_state.result_stack.append(result)

    @dispatch
    def visit(self, node: GtBinOp) -> None:
        """
        title: Visit GtBinOp nodes.
        parameters:
          node:
            type: GtBinOp
        """
        if self.services.lower_column_operation(node):
            return
        llvm_lhs, llvm_rhs, unsigned = self._load_binary_operands(node)
        if is_vector(llvm_lhs) and is_vector(llvm_rhs):
            raise_lowering_error(
                f"Vector binop {node.op_code} not implemented.",
                code=DiagnosticCodes.LOWERING_MISSING_HANDLER,
                node=node,
            )
        result = self.services.numeric.emit_numeric_compare(
            ">",
            llvm_lhs,
            llvm_rhs,
            unsigned=unsigned,
            name="gttmp",
        )
        self.services.function_state.result_stack.append(result)

    @dispatch
    def visit(self, node: LeBinOp) -> None:
        """
        title: Visit LeBinOp nodes.
        parameters:
          node:
            type: LeBinOp
        """
        if self.services.lower_column_operation(node):
            return
        llvm_lhs, llvm_rhs, unsigned = self._load_binary_operands(node)
        if is_vector(llvm_lhs) and is_vector(llvm_rhs):
            raise_lowering_error(
                f"Vector binop {node.op_code} not implemented.",
                code=DiagnosticCodes.LOWERING_MISSING_HANDLER,
                node=node,
            )
        result = self.services.numeric.emit_numeric_compare(
            "<=",
            llvm_lhs,
            llvm_rhs,
            unsigned=unsigned,
            name="letmp",
        )
        self.services.function_state.result_stack.append(result)

    @dispatch
    def visit(self, node: GeBinOp) -> None:
        """
        title: Visit GeBinOp nodes.
        parameters:
          node:
            type: GeBinOp
        """
        if self.services.lower_column_operation(node):
            return
        llvm_lhs, llvm_rhs, unsigned = self._load_binary_operands(node)
        if is_vector(llvm_lhs) and is_vector(llvm_rhs):
            raise_lowering_error(
                f"Vector binop {node.op_code} not implemented.",
                code=DiagnosticCodes.LOWERING_MISSING_HANDLER,
                node=node,
            )
        result = self.services.numeric.emit_numeric_compare(
            ">=",
            llvm_lhs,
            llvm_rhs,
            unsigned=unsigned,
            name="getmp",
        )
        self.services.function_state.result_stack.append(result)

    @dispatch
    def visit(self, node: EqBinOp) -> None:
        """
        title: Visit EqBinOp nodes.
        parameters:
          node:
            type: EqBinOp
        """
        if self.services.lower_column_operation(node):
            return
        llvm_lhs, llvm_rhs, unsigned = self._load_binary_operands(node)

        if is_vector(llvm_lhs) and is_vector(llvm_rhs):
            raise_lowering_error(
                f"Vector binop {node.op_code} not implemented.",
                code=DiagnosticCodes.LOWERING_MISSING_HANDLER,
                node=node,
            )

        if (
            isinstance(llvm_lhs.type, ir.PointerType)
            and isinstance(llvm_rhs.type, ir.PointerType)
            and llvm_lhs.type.pointee == self.services.llvm.INT8_TYPE
            and llvm_rhs.type.pointee == self.services.llvm.INT8_TYPE
        ):
            result = self.services.strings.compare(llvm_lhs, llvm_rhs, "==")
        else:
            result = self.services.numeric.emit_numeric_compare(
                "==",
                llvm_lhs,
                llvm_rhs,
                unsigned=unsigned,
                name="eqtmp",
            )
        self.services.function_state.result_stack.append(result)

    @dispatch
    def visit(self, node: NeBinOp) -> None:
        """
        title: Visit NeBinOp nodes.
        parameters:
          node:
            type: NeBinOp
        """
        if self.services.lower_column_operation(node):
            return
        llvm_lhs, llvm_rhs, unsigned = self._load_binary_operands(node)

        if is_vector(llvm_lhs) and is_vector(llvm_rhs):
            raise_lowering_error(
                f"Vector binop {node.op_code} not implemented.",
                code=DiagnosticCodes.LOWERING_MISSING_HANDLER,
                node=node,
            )

        if (
            isinstance(llvm_lhs.type, ir.PointerType)
            and isinstance(llvm_rhs.type, ir.PointerType)
            and llvm_lhs.type.pointee == self.services.llvm.INT8_TYPE
            and llvm_rhs.type.pointee == self.services.llvm.INT8_TYPE
        ):
            result = self.services.strings.compare(llvm_lhs, llvm_rhs, "!=")
        else:
            result = self.services.numeric.emit_numeric_compare(
                "!=",
                llvm_lhs,
                llvm_rhs,
                unsigned=unsigned,
                name="netmp",
            )
        self.services.function_state.result_stack.append(result)

    @dispatch
    def visit(self, node: BitOrBinOp) -> None:
        """
        title: Visit BitOrBinOp nodes.
        parameters:
          node:
            type: BitOrBinOp
        """
        if self.services.lower_column_operation(node):
            return
        llvm_lhs, llvm_rhs, _unsigned = self._load_binary_operands(
            node,
            unify_numeric=False,
        )
        if self.services.collection.try_set_binary_op(
            llvm_lhs, llvm_rhs, node.op_code
        ):
            return
        raise_lowering_error(
            f"Binary op {node.op_code} not implemented yet.",
            code=DiagnosticCodes.LOWERING_MISSING_HANDLER,
            node=node,
        )

    @dispatch
    def visit(self, node: BitAndBinOp) -> None:
        """
        title: Visit BitAndBinOp nodes.
        parameters:
          node:
            type: BitAndBinOp
        """
        if self.services.lower_column_operation(node):
            return
        llvm_lhs, llvm_rhs, _unsigned = self._load_binary_operands(
            node,
            unify_numeric=False,
        )
        if self.services.collection.try_set_binary_op(
            llvm_lhs, llvm_rhs, node.op_code
        ):
            return
        raise_lowering_error(
            f"Binary op {node.op_code} not implemented yet.",
            code=DiagnosticCodes.LOWERING_MISSING_HANDLER,
            node=node,
        )

    @dispatch
    def visit(self, node: BitXorBinOp) -> None:
        """
        title: Visit BitXorBinOp nodes.
        parameters:
          node:
            type: BitXorBinOp
        """
        llvm_lhs, llvm_rhs, _unsigned = self._load_binary_operands(
            node,
            unify_numeric=False,
        )
        if self.services.collection.try_set_binary_op(
            llvm_lhs, llvm_rhs, node.op_code
        ):
            return
        raise_lowering_error(
            f"Binary op {node.op_code} not implemented yet.",
            code=DiagnosticCodes.LOWERING_MISSING_HANDLER,
            node=node,
        )
