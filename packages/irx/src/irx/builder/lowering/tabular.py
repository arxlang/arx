# mypy: disable-error-code=no-redef
# mypy: disable-error-code=untyped-decorator
"""
title: Lower resolved tabular values through opaque checked native owners.
"""

from __future__ import annotations

from typing import cast

import astx

from llvmlite import ir

from irx.analysis.ownership import arrow_resource_ownership
from irx.analysis.resolved_nodes import (
    OwnershipKind,
    ResourceKind,
    SemanticInfo,
)
from irx.analysis.tabular import ResolvedTabular
from irx.analysis.types import is_signed_integer_type
from irx.builder.core import VisitorCore
from irx.builder.diagnostics import raise_lowering_internal_error
from irx.builder.lowering.array_values import ArrayValueLoweringMixin
from irx.builder.lowering.descriptors import DescriptorLoweringMixin
from irx.builder.protocols import VisitorMixinBase
from irx.builder.runtime import safe_pop
from irx.builder.runtime.arrow.lowering import (
    call_arrow_runtime,
    require_arrow_runtime_success,
)
from irx.typecheck import typechecked


@typechecked
class TabularLoweringMixin(VisitorMixinBase):
    """
    title: Consume schema sidecars without re-resolving fields or ownership.
    """

    def tabular_resolution(self, node: astx.DataType) -> ResolvedTabular:
        """
        title: Require the registered features and resolved tabular contract.
        parameters:
          node:
            type: astx.DataType
        returns:
          type: ResolvedTabular
        """
        info = getattr(node, "semantic", None)
        if not isinstance(info, SemanticInfo) or info.resolved_tabular is None:
            raise_lowering_internal_error(
                "missing tabular resolution", node=node
            )
        resolved = info.resolved_tabular
        for feature in resolved.required_features:
            cast(VisitorCore, self).activate_runtime_feature(feature)
        cast(DescriptorLoweringMixin, self).guard_descriptor_contract(
            node, resolved.required_version, resolved.feature
        )
        return resolved

    def tabular_arguments(self, resolved: ResolvedTabular) -> list[ir.Value]:
        """
        title: Evaluate resolved ABI operands in their specified order.
        parameters:
          resolved:
            type: ResolvedTabular
        returns:
          type: list[ir.Value]
        """
        core = cast(VisitorCore, self)
        arguments: list[ir.Value] = []
        for expr in resolved.arguments:
            self.visit_child(expr)
            value = safe_pop(self.result_stack)
            if value is None:
                raise_lowering_internal_error(
                    "missing tabular argument", node=expr
                )
            type_ = core._resolved_ast_type(expr)
            if is_signed_integer_type(type_):
                value = core._cast_ast_value(
                    value, source_type=type_, target_type=astx.Int64()
                )
            arguments.append(value)
        return arguments

    def tabular_vector(
        self, values: list[ir.Value], type_: ir.Type
    ) -> ir.Value:
        """
        title: Materialize a non-owning ABI vector even for zero elements.
        parameters:
          values:
            type: list[ir.Value]
          type_:
            type: ir.Type
        returns:
          type: ir.Value
        """
        builder = self._llvm.ir_builder
        slots = builder.alloca(ir.ArrayType(type_, max(1, len(values))))
        zero = ir.Constant(ir.IntType(32), 0)
        for index, value in enumerate(values):
            slot = builder.gep(
                slots, [zero, ir.Constant(ir.IntType(32), index)]
            )
            builder.store(value, slot)
        return builder.gep(slots, [zero, zero])

    def tabular_call(
        self,
        node: astx.DataType,
        resolved: ResolvedTabular,
        arguments: list[ir.Value],
    ) -> None:
        """
        title: Guard outputs before registering independent owners.
        parameters:
          node:
            type: astx.DataType
          resolved:
            type: ResolvedTabular
          arguments:
            type: list[ir.Value]
        """
        core = cast(VisitorCore, self)
        output_type = core._llvm_type_for_ast_type(resolved.result_type)
        if output_type is None:
            raise_lowering_internal_error(
                "missing tabular result type", node=node
            )
        output = cast(ArrayValueLoweringMixin, self).array_slot(
            output_type, "tabular.output"
        )
        function = self.require_runtime_symbol(
            resolved.feature, resolved.symbol
        )
        status, error = call_arrow_runtime(
            self, function, [*arguments, output], resolved.symbol
        )
        core._register_resource_slot_cleanup(
            arrow_resource_ownership(ResourceKind.ERROR, OwnershipKind.OWNED),
            error,
        )
        require_arrow_runtime_success(self, node, status, resolved.symbol)
        self.cleanup_stack.pop()
        value = self._llvm.ir_builder.load(output)
        core._register_owned_resource_temporary(node, value)
        self.result_stack.append(value)

    def lower_tabular_literal(self, node: astx.DataType) -> None:
        """
        title: Build from a resolved schema and borrowed ordered columns.
        parameters:
          node:
            type: astx.DataType
        """
        resolved = self.tabular_resolution(node)
        arguments = self.tabular_arguments(resolved)
        columns = self.tabular_vector(
            arguments[2:], self._llvm.OPAQUE_POINTER_TYPE
        )
        self.tabular_call(
            node,
            resolved,
            [
                arguments[0],
                columns,
                ir.Constant(ir.IntType(64), len(arguments) - 2),
                arguments[1],
            ],
        )

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.TabularLiteral) -> None:
        """
        title: Lower a checked schema-first container literal.
        parameters:
          node:
            type: astx.TabularLiteral
        """
        self.lower_tabular_literal(node)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.TabularQuery) -> None:
        """
        title: Lower a closed query and its pre-resolved projection indices.
        parameters:
          node:
            type: astx.TabularQuery
        """
        resolved = self.tabular_resolution(node)
        arguments = self.tabular_arguments(resolved)
        if resolved.indices is not None:
            values: list[ir.Value] = [
                ir.Constant(ir.IntType(64), index)
                for index in resolved.indices
            ]
            arguments.extend(
                [
                    self.tabular_vector(values, ir.IntType(64)),
                    ir.Constant(ir.IntType(64), len(values)),
                ]
            )
        self.tabular_call(node, resolved, arguments)
