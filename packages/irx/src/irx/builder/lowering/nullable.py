# mypy: disable-error-code=no-redef
"""
title: Lower resolved nullable operations through focused Arrow primitives.
"""

from __future__ import annotations

from typing import cast

import astx

from llvmlite import ir

from irx.analysis.nullable import ColumnOperation
from irx.builder.core import VisitorCore
from irx.builder.diagnostics import (
    require_lowered_value,
    require_semantic_metadata,
)
from irx.builder.lowering.control_flow import ControlFlowVisitorMixin
from irx.builder.lowering.dataframe import DataFrameVisitorMixin
from irx.builder.runtime import safe_pop
from irx.typecheck import typechecked


@typechecked
class NullableVisitorMixin(DataFrameVisitorMixin):
    """
    title: Materialize scalar validity and independently owned Series results.
    """

    def column_operand(self, node: astx.AST) -> list[ir.Value]:
        """
        title: Encode either an opaque column or fixed-width scalar bits.
        parameters:
          node:
            type: astx.AST
        returns:
          type: list[ir.Value]
        """
        self.visit_child(node)
        value = require_lowered_value(
            safe_pop(self.result_stack), node=node, context="column operand"
        )
        type_ = self._resolved_ast_type(node)
        builder = self._llvm.ir_builder
        valid: ir.Value = ir.Constant(ir.IntType(32), 1)
        if isinstance(type_, astx.SeriesType):
            return [value, ir.Constant(ir.IntType(64), 0), valid]
        if isinstance(type_, astx.NullableType):
            valid = builder.zext(
                builder.extract_value(value, 0), ir.IntType(32)
            )
            value = builder.extract_value(value, 1)
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
            ir.Constant(self._llvm.CHUNKED_ARRAY_HANDLE_TYPE, None),
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
        builder = self._llvm.ir_builder
        nullable = isinstance(plan.result, astx.NullableType)
        inner = (
            plan.result.value_type
            if isinstance(plan.result, astx.NullableType)
            else plan.result
        )
        llvm_type = require_semantic_metadata(
            self._llvm_type_for_ast_type(inner),
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
        self.result_stack.append(value)

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
        builder = self._llvm.ir_builder
        bits = self.create_entry_block_alloca("column_bits", ir.IntType(64))
        valid = self.create_entry_block_alloca("column_valid", ir.IntType(32))
        if isinstance(node, astx.SubscriptExpr):
            operand = self.column_operand(node.value)
            self.visit_child(node.index)
            index = require_lowered_value(
                safe_pop(self.result_stack),
                node=node.index,
                context="Series index",
            )
            index = self._cast_ast_value(
                index,
                source_type=self._resolved_ast_type(node.index),
                target_type=astx.Int64(),
            )
            status = builder.call(
                self.require_runtime_symbol(
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
            self._check_arrow_status(status, "series_index")
            self.column_result(node, plan, bits, valid)
            return True
        if isinstance(node, astx.BinaryOp):
            lhs, rhs = (
                self.column_operand(node.lhs),
                self.column_operand(node.rhs),
            )
        elif isinstance(node, astx.NullFill):
            lhs, rhs = (
                self.column_operand(node.value),
                self.column_operand(node.replacement),
            )
        elif isinstance(node, astx.NullCheck):
            lhs = self.column_operand(node.value)
            rhs = [
                ir.Constant(self._llvm.CHUNKED_ARRAY_HANDLE_TYPE, None),
                ir.Constant(ir.IntType(64), 0),
                ir.Constant(ir.IntType(32), 0),
            ]
        else:
            raise TypeError("invalid column operation metadata")
        output = self.create_entry_block_alloca(
            "column_output", self._llvm.CHUNKED_ARRAY_HANDLE_TYPE
        )
        kernel = cast(
            ControlFlowVisitorMixin, self
        )._constant_c_string_pointer(plan.kernel, name_hint="column_kernel")
        status = builder.call(
            self.require_runtime_symbol(
                "dataframe", "irx_arrow_column_compute"
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
        self._check_arrow_status(status, "column_compute")
        if isinstance(plan.result, astx.SeriesType):
            column = builder.load(output)
            self.arrow_temporary(node, column)
            self.result_stack.append(column)
        else:
            self.column_result(node, plan, bits, valid)
        return True

    @VisitorCore.visit.dispatch
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

    @VisitorCore.visit.dispatch
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
