# mypy: disable-error-code=no-redef
"""
title: Lower resolved nullable operations through focused Arrow primitives.
"""

from __future__ import annotations

import astx

from llvmlite import ir
from plum import dispatch
from public import private

from irx.analysis.nullable import ColumnOperation
from irx.builder.diagnostics import (
    raise_lowering_internal_error,
    require_lowered_value,
    require_semantic_metadata,
)
from irx.builder.lowering.contracts import NullableServices
from irx.builder.runtime import safe_pop
from irx.builder.services.representations import (
    resolved_type as resolved_ast_type,
)
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class NullableLowering:
    """
    title: Materialize scalar validity and independently owned Series results.
    attributes:
      services:
        type: NullableServices
    """

    services: NullableServices

    def __init__(self, services: NullableServices) -> None:
        """
        title: Bind explicit family-owned emission dependencies.
        parameters:
          services:
            type: NullableServices
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
            f"no nullable handler for {type(node).__name__}", node=node
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
                "llvm.nullable.NullCheck",
                "irx.nullable",
                "lowering",
                astx.NullCheck,
                self.visit,
                source="irx.builder.lowering.nullable.NullableLowering.visit",
            ),
            contribute_node(
                "llvm.nullable.NullFill",
                "irx.nullable",
                "lowering",
                astx.NullFill,
                self.visit,
                source="irx.builder.lowering.nullable.NullableLowering.visit",
            ),
            contribute_node(
                "llvm.nullable.SeriesReduction",
                "irx.nullable",
                "lowering",
                astx.SeriesReduction,
                self.visit,
                source="irx.builder.lowering.nullable.NullableLowering.visit",
            ),
        )

    def column_operand(
        self, node: astx.AST, target: astx.DataType | None = None
    ) -> list[ir.Value]:
        """
        title: Encode either an opaque column or fixed-width scalar bits.
        parameters:
          node:
            type: astx.AST
          target:
            type: astx.DataType | None
        returns:
          type: list[ir.Value]
        """
        self.services.visit_child(node)
        value = require_lowered_value(
            safe_pop(self.services.function_state.result_stack),
            node=node,
            context="column operand",
        )
        type_ = resolved_ast_type(node)
        builder = self.services.llvm.ir_builder
        valid: ir.Value = ir.Constant(ir.IntType(32), 1)
        if isinstance(type_, astx.SeriesType):
            return [value, ir.Constant(ir.IntType(64), 0), valid]
        if isinstance(type_, astx.NullableType):
            valid = builder.zext(
                builder.extract_value(value, 0), ir.IntType(32)
            )
            value = builder.extract_value(value, 1)
            type_ = type_.value_type
        if target is not None:
            value = self.services.numeric.cast_scalar(
                value, source_type=type_, target_type=target
            )
        if isinstance(value.type, ir.FloatType):
            value = builder.bitcast(value, ir.IntType(32))
        elif isinstance(value.type, ir.DoubleType):
            value = builder.bitcast(value, ir.IntType(64))
        if (
            isinstance(value.type, ir.IntType)
            and value.type.width < ir.IntType(64).width
        ):
            value = builder.zext(value, ir.IntType(64))
        return [
            ir.Constant(self.services.llvm.CHUNKED_ARRAY_HANDLE_TYPE, None),
            value,
            valid,
        ]

    def column_result(
        self,
        node: astx.AST,
        plan: ColumnOperation,
        bits: ir.Value,
        valid: ir.Value,
    ) -> None:
        """
        title: Decode scalar bits only after native status success.
        parameters:
          node:
            type: astx.AST
          plan:
            type: ColumnOperation
          bits:
            type: ir.Value
          valid:
            type: ir.Value
        """
        builder = self.services.llvm.ir_builder
        nullable = isinstance(plan.result, astx.NullableType)
        inner = (
            plan.result.value_type
            if isinstance(plan.result, astx.NullableType)
            else plan.result
        )
        llvm_type = require_semantic_metadata(
            self.services.types.llvm_type(inner),
            node=node,
            metadata="result type",
            context="nullable result",
        )
        value = builder.load(bits)
        if llvm_type == ir.FloatType():
            value = builder.bitcast(
                builder.trunc(value, ir.IntType(32)), llvm_type
            )
        elif llvm_type == ir.DoubleType():
            value = builder.bitcast(value, llvm_type)
        elif (
            isinstance(llvm_type, ir.IntType)
            and llvm_type.width < ir.IntType(64).width
        ):
            value = builder.trunc(value, llvm_type)
        if nullable:
            aggregate = ir.Constant(
                ir.LiteralStructType([ir.IntType(1), llvm_type]), None
            )
            result = builder.insert_value(
                aggregate,
                builder.icmp_signed(
                    "!=", builder.load(valid), ir.Constant(ir.IntType(32), 0)
                ),
                0,
            )
            value = builder.insert_value(result, value, 1)
        self.services.function_state.result_stack.append(value)

    def lower_column_operation(self, node: astx.AST) -> bool:
        """
        title: Consume the semantic kernel plan without rediscovering types.
        parameters:
          node:
            type: astx.AST
        returns:
          type: bool
        """
        info = getattr(node, "semantic", None)
        plan = None if info is None else info.extras.get("column_operation")
        if not isinstance(plan, ColumnOperation):
            return False
        builder = self.services.llvm.ir_builder
        if isinstance(node, astx.BinaryOp) and plan.kernel == "set":
            self.lower_series_store(node, plan)
            return True
        bits = self.services.create_entry_block_alloca(
            "column_bits", ir.IntType(64)
        )
        valid = self.services.create_entry_block_alloca(
            "column_valid", ir.IntType(32)
        )
        if isinstance(node, astx.SubscriptExpr) and plan.kernel == "slice":
            self.lower_series_slice(node)
            return True
        if isinstance(node, astx.SubscriptExpr):
            operand = self.column_operand(node.value)
            self.services.visit_child(node.index)
            index = require_lowered_value(
                safe_pop(self.services.function_state.result_stack),
                node=node.index,
                context="Series index",
            )
            index = self.services.numeric.cast_scalar(
                index,
                source_type=resolved_ast_type(node.index),
                target_type=astx.Int64(),
            )
            status = builder.call(
                self.services.require_runtime_symbol(
                    "dataframe", "irx_arrow_series_index"
                ),
                [
                    operand[0],
                    index,
                    ir.Constant(ir.IntType(32), plan.type_id),
                    bits,
                    valid,
                ],
            )
            self.services.check_arrow_status(node, status, "series_index")
            self.column_result(node, plan, bits, valid)
            return True
        if isinstance(node, astx.BinaryOp):
            lhs, rhs = (
                self.column_operand(node.lhs, plan.input_type),
                self.column_operand(node.rhs, plan.input_type),
            )
        elif isinstance(node, astx.NullFill):
            lhs, rhs = (
                self.column_operand(node.value),
                self.column_operand(node.replacement),
            )
        elif isinstance(
            node, (astx.NullCheck, astx.SeriesReduction, astx.UnaryOp)
        ):
            lhs = self.column_operand(
                node.operand if isinstance(node, astx.UnaryOp) else node.value
            )
            rhs = [
                ir.Constant(
                    self.services.llvm.CHUNKED_ARRAY_HANDLE_TYPE, None
                ),
                ir.Constant(ir.IntType(64), 0),
                ir.Constant(ir.IntType(32), 0),
            ]
        else:
            raise TypeError("invalid column operation metadata")
        output = self.services.create_entry_block_alloca(
            "column_output", self.services.llvm.CHUNKED_ARRAY_HANDLE_TYPE
        )
        kernel = self.services.strings.constant(
            plan.kernel, name_hint="column_kernel"
        )
        status = builder.call(
            self.services.require_runtime_symbol(
                "dataframe", "irx_arrow_column_compute_promoted"
            ),
            [
                kernel,
                ir.Constant(ir.IntType(32), plan.type_id),
                *lhs,
                *rhs,
                output,
                bits,
                valid,
            ],
        )
        self.services.check_arrow_status(node, status, "column_compute")
        if isinstance(plan.result, astx.SeriesType):
            column = builder.load(output)
            self.services.arrow_temporary(node, column)
            self.services.function_state.result_stack.append(column)
        else:
            self.column_result(node, plan, bits, valid)
        return True

    @dispatch
    def visit(self, node: astx.NullCheck) -> None:
        """
        title: Lower a resolved null test.
        parameters:
          node:
            type: astx.NullCheck
        """
        if not self.lower_column_operation(node):
            require_semantic_metadata(
                None, node=node, metadata="column_operation", context="is_null"
            )

    @dispatch
    def visit(self, node: astx.NullFill) -> None:
        """
        title: Lower a resolved eager null replacement.
        parameters:
          node:
            type: astx.NullFill
        """
        if not self.lower_column_operation(node):
            require_semantic_metadata(
                None,
                node=node,
                metadata="column_operation",
                context="fill_null",
            )

    def lower_series_slice(self, node: astx.SubscriptExpr) -> None:
        """
        title: Lower resolved slice bounds without reading failed outputs.
        parameters:
          node:
            type: astx.SubscriptExpr
        """
        column = self.column_operand(node.value)[0]
        bounds = 0
        values: list[ir.Value] = []
        for index, (bound, default) in enumerate(
            zip((node.lower, node.upper, node.step), (0, 0, 1))
        ):
            if isinstance(bound, astx.LiteralNone):
                values.append(ir.Constant(ir.IntType(64), default))
                continue
            bounds |= 1 << index
            self.services.visit_child(bound)
            value = require_lowered_value(
                safe_pop(self.services.function_state.result_stack),
                node=bound,
                context="slice bound",
            )
            values.append(
                self.services.numeric.cast_scalar(
                    value,
                    source_type=resolved_ast_type(bound),
                    target_type=astx.Int64(),
                )
            )
        output = self.services.create_entry_block_alloca(
            "slice_output", self.services.llvm.CHUNKED_ARRAY_HANDLE_TYPE
        )
        status = self.services.llvm.ir_builder.call(
            self.services.require_runtime_symbol(
                "dataframe", "irx_arrow_series_slice"
            ),
            [column, *values, ir.Constant(ir.IntType(32), bounds), output],
        )
        self.services.check_arrow_status(node, status, "series_slice")
        value = self.services.llvm.ir_builder.load(output)
        self.services.arrow_temporary(node, value)
        self.services.function_state.result_stack.append(value)

    @dispatch
    def visit(self, node: astx.SeriesReduction) -> None:
        """
        title: Lower a fully resolved null-skipping Series reduction.
        parameters:
          node:
            type: astx.SeriesReduction
        """
        if not self.lower_column_operation(node):
            require_semantic_metadata(
                None,
                node=node,
                metadata="column_operation",
                context="Series reduction",
            )

    def lower_series_store(
        self, node: astx.BinaryOp, plan: ColumnOperation
    ) -> None:
        """
        title: Update one element without producing a statement value.
        parameters:
          node:
            type: astx.BinaryOp
          plan:
            type: ColumnOperation
        """
        assert isinstance(node.lhs, astx.SubscriptExpr)
        column = self.column_operand(node.lhs.value)[0]
        self.services.visit_child(node.lhs.index)
        index = require_lowered_value(
            safe_pop(self.services.function_state.result_stack),
            node=node,
            context="Series update index",
        )
        index = self.services.numeric.cast_scalar(
            index,
            source_type=resolved_ast_type(node.lhs.index),
            target_type=astx.Int64(),
        )
        operand = self.column_operand(node.rhs, plan.input_type)
        source = resolved_ast_type(node.lhs.value)
        assert isinstance(source, astx.SeriesType)
        status = self.services.llvm.ir_builder.call(
            self.services.require_runtime_symbol(
                "dataframe", "irx_arrow_series_set"
            ),
            [
                column,
                index,
                ir.Constant(ir.IntType(32), plan.type_id),
                operand[1],
                operand[2],
                ir.Constant(ir.IntType(32), int(source.nullable)),
            ],
        )
        self.services.check_arrow_status(node, status, "series_set")
