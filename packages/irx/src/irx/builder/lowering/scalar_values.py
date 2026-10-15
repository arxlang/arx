# mypy: disable-error-code=no-redef
# mypy: disable-error-code=untyped-decorator
"""
title: Lower resolved scalar operations through registered opaque owners.
"""

from __future__ import annotations

from typing import cast

import astx

from llvmlite import ir

from irx.analysis.resolved_nodes import SemanticInfo
from irx.builder.core import VisitorCore
from irx.builder.diagnostics import raise_lowering_internal_error
from irx.builder.lowering.array_values import ArrayValueLoweringMixin
from irx.builder.lowering.descriptors import DescriptorLoweringMixin
from irx.builder.lowering.tabular import TabularLoweringMixin
from irx.builder.protocols import VisitorMixinBase
from irx.builder.runtime import safe_pop
from irx.typecheck import typechecked


@typechecked
class ScalarValueLoweringMixin(VisitorMixinBase):
    """
    title: Consume scalar sidecars with checked status and independent cleanup.
    """

    def lower_scalar(
        self, node: astx.ScalarLiteral | astx.ScalarQuery
    ) -> None:
        """
        title: >-
          Emit the normalized ABI operands without re-resolving signatures.
        parameters:
          node:
            type: astx.ScalarLiteral | astx.ScalarQuery
        """
        info = getattr(node, "semantic", None)
        if not isinstance(info, SemanticInfo) or info.resolved_scalar is None:
            raise_lowering_internal_error(
                "missing scalar resolution", node=node
            )
        resolved = info.resolved_scalar
        core = cast(VisitorCore, self)
        arrays = cast(ArrayValueLoweringMixin, self)
        for feature in ("core", "array"):
            core.activate_runtime_feature(feature)
        cast(DescriptorLoweringMixin, self).guard_descriptor_contract(
            node, resolved.required_feature_version
        )
        args: list[ir.Value] = []
        for expr, target in zip(
            resolved.arguments, resolved.argument_types, strict=True
        ):
            self.visit_child(expr)
            args.append(
                core._cast_ast_value(
                    safe_pop(self.result_stack),
                    source_type=core._resolved_ast_type(expr),
                    target_type=target,
                )
            )
        if resolved.vector is not None:
            item_type = core._llvm_type_for_ast_type(resolved.vector)
            if item_type is None:
                raise_lowering_internal_error(
                    "missing scalar vector storage", node=node
                )
            args = [
                args[0],
                cast(TabularLoweringMixin, self).tabular_vector(
                    args[1:], item_type
                ),
                ir.Constant(ir.IntType(64), len(args) - 1),
            ]
        output_type = core._llvm_type_for_ast_type(resolved.result_type)
        if isinstance(resolved.result_type, astx.Boolean):
            output_type = ir.IntType(32)
        if output_type is None:
            raise_lowering_internal_error(
                "missing scalar output type", node=node
            )
        slot = arrays.array_slot(output_type, "scalar.output")
        arrays.array_call(node, resolved.symbol, [*args, slot])
        result = self._llvm.ir_builder.load(slot)
        if isinstance(resolved.result_type, astx.Boolean):
            result = self._llvm.ir_builder.icmp_signed(
                "!=", result, ir.Constant(ir.IntType(32), 0)
            )
        core._register_owned_resource_temporary(node, result)
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.ScalarLiteral) -> None:
        """
        title: >-
          Construct a scalar with resolved storage and payload conversions.
        parameters:
          node:
            type: astx.ScalarLiteral
        """
        self.lower_scalar(node)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.ScalarQuery) -> None:
        """
        title: Inspect scalar data or publish an independently owned child.
        parameters:
          node:
            type: astx.ScalarQuery
        """
        self.lower_scalar(node)
