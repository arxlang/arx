# mypy: disable-error-code=no-redef

"""
title: Dynamic-list visitor mixins for llvmliteir.
"""

from __future__ import annotations

from typing import Any, cast

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import (
    IterationKind,
    ResolvedIteration,
    SemanticInfo,
)
from irx.analysis.types import is_string_type
from irx.builder.core import VisitorCore, semantic_symbol_key
from irx.builder.diagnostics import (
    raise_lowering_error,
    require_semantic_metadata,
)
from irx.builder.protocols import DispatchRegistrar, VisitorMixinBase
from irx.builder.runtime import safe_pop
from irx.builder.state import CleanupAction
from irx.builtins.collections.list import (
    LIST_APPEND_SYMBOL,
    LIST_AT_SYMBOL,
    LIST_DESTROY_SYMBOL,
    LIST_FIELD_INDICES,
    LIST_RUNTIME_FEATURE,
    LIST_STATUS_MESSAGE_SYMBOL,
    list_element_type,
)
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@typechecked
class ListVisitorMixin(VisitorMixinBase):
    """
    title: Dynamic-list visitor mixin.
    """

    @private
    def check_list_status(self, node: astx.AST, status: ir.Value) -> None:
        """
        title: Convert typed list statuses before reading success output slots.
        parameters:
          node:
            type: astx.AST
          status:
            type: ir.Value
        """
        function = self._llvm.ir_builder.function
        success = function.append_basic_block("list.success")
        failure = function.append_basic_block("list.failure")
        self._llvm.ir_builder.cbranch(
            self._llvm.ir_builder.icmp_signed(
                "==", status, ir.Constant(status.type, 0)
            ),
            success,
            failure,
        )
        self._llvm.ir_builder.position_at_end(failure)
        message = self._llvm.ir_builder.call(
            self.require_runtime_symbol(
                LIST_RUNTIME_FEATURE, LIST_STATUS_MESSAGE_SYMBOL
            ),
            [status],
        )
        fallback = function.append_basic_block("list.runtime_error")
        switch = self._llvm.ir_builder.switch(status, fallback)
        for number, role in (
            (1, "ValueError"),
            (2, "OverflowError"),
            (4, "IndexError"),
        ):
            block = function.append_basic_block("list." + role)
            switch.add_case(ir.Constant(status.type, number), block)
            self._llvm.ir_builder.position_at_end(block)
            self.raise_runtime_exception(
                node, role, message, code="ARX-RUNTIME-LIST-001"
            )
        self._llvm.ir_builder.position_at_end(fallback)
        self.raise_runtime_exception(
            node, "RuntimeError", message, code="ARX-RUNTIME-LIST-001"
        )
        self._llvm.ir_builder.position_at_end(success)

    def _llvm_list_type(self) -> ir.Type:
        """
        title: Return the canonical lowered list value type.
        returns:
          type: ir.Type
        """
        return cast(
            ir.Type,
            ir.LiteralStructType(
                [
                    self._llvm.INT8_TYPE.as_pointer(),
                    self._llvm.INT64_TYPE,
                    self._llvm.INT64_TYPE,
                    self._llvm.INT64_TYPE,
                    self._llvm.INT32_TYPE,
                ]
            ),
        )

    def _list_element_llvm_type_from_type(
        self,
        type_: astx.DataType | None,
    ) -> ir.Type:
        """
        title: Return the lowered LLVM type for one concrete list element type.
        parameters:
          type_:
            type: astx.DataType | None
        returns:
          type: ir.Type
        """
        element_type = list_element_type(type_)
        if element_type is None:
            raise Exception(
                "dynamic list lowering requires a single concrete element type"
            )
        llvm_type = self._llvm_type_for_ast_type(element_type)
        if llvm_type is None:
            raise Exception(
                "dynamic list lowering requires a lowerable element type"
            )
        return llvm_type

    def _list_element_llvm_type(self, node: astx.AST) -> ir.Type:
        """
        title: Return the lowered element type for one list-valued AST node.
        parameters:
          node:
            type: astx.AST
        returns:
          type: ir.Type
        """
        return self._list_element_llvm_type_from_type(
            self._resolved_ast_type(node)
        )

    def _resolved_iteration(
        self,
        node: astx.AST,
    ) -> ResolvedIteration | None:
        """
        title: Return one node's resolved iteration sidecar.
        parameters:
          node:
            type: astx.AST
        returns:
          type: ResolvedIteration | None
        """
        semantic = getattr(node, "semantic", None)
        iteration = getattr(semantic, "resolved_iteration", None)
        return iteration if isinstance(iteration, ResolvedIteration) else None

    def _list_element_size_from_type(
        self,
        type_: astx.DataType | None,
    ) -> int:
        """
        title: Return the ABI size in bytes for one concrete list type.
        parameters:
          type_:
            type: astx.DataType | None
        returns:
          type: int
        """
        llvm_type = self._list_element_llvm_type_from_type(type_)
        return cast(
            int,
            llvm_type.get_abi_size(self.target_machine.target_data),
        )

    def _list_element_size(self, node: astx.AST) -> int:
        """
        title: Return the ABI size in bytes for one list element type.
        parameters:
          node:
            type: astx.AST
        returns:
          type: int
        """
        return self._list_element_size_from_type(self._resolved_ast_type(node))

    def _empty_list_value_for_type(
        self,
        type_: astx.DataType | None,
    ) -> ir.Constant:
        """
        title: Return one zero-length lowered list value for one list type.
        parameters:
          type_:
            type: astx.DataType | None
        returns:
          type: ir.Constant
        """
        return ir.Constant(
            cast(ir.LiteralStructType, self._llvm_list_type()),
            [
                ir.Constant(self._llvm.INT8_TYPE.as_pointer(), None),
                ir.Constant(self._llvm.INT64_TYPE, 0),
                ir.Constant(self._llvm.INT64_TYPE, 0),
                ir.Constant(
                    self._llvm.INT64_TYPE,
                    self._list_element_size_from_type(type_),
                ),
                ir.Constant(
                    self._llvm.INT32_TYPE,
                    int(is_string_type(list_element_type(type_))),
                ),
            ],
        )

    def _empty_list_value(self, node: astx.AST) -> ir.Constant:
        """
        title: Return one zero-length lowered list value.
        parameters:
          node:
            type: astx.AST
        returns:
          type: ir.Constant
        """
        return self._empty_list_value_for_type(self._resolved_ast_type(node))

    def _list_pointer_for_call(self, node: astx.AST, *, name: str) -> ir.Value:
        """
        title: Return an addressable lowered list value for runtime calls.
        parameters:
          node:
            type: astx.AST
          name:
            type: str
        returns:
          type: ir.Value
        """
        if isinstance(
            node,
            (
                astx.Identifier,
                astx.FieldAccess,
                astx.BaseFieldAccess,
                astx.StaticFieldAccess,
            ),
        ):
            return self._lvalue_address(node)

        self.visit_child(node)
        value = safe_pop(self.result_stack)
        llvm_list_type = self._llvm_list_type()
        if value is None or value.type != llvm_list_type:
            raise Exception("dynamic list lowering requires a list value")
        temp = self.create_entry_block_alloca(name, llvm_list_type)
        self._llvm.ir_builder.store(value, temp)
        return temp

    def _static_integer_literal_value(self, node: astx.AST) -> int | None:
        """
        title: Return one static integer literal value when present.
        parameters:
          node:
            type: astx.AST
        returns:
          type: int | None
        """
        if isinstance(
            node,
            (
                astx.LiteralInt8,
                astx.LiteralInt16,
                astx.LiteralInt32,
                astx.LiteralInteger,
                astx.LiteralInt64,
                astx.LiteralUInt8,
                astx.LiteralUInt16,
                astx.LiteralUInt32,
                astx.LiteralUInt64,
                astx.LiteralUInt128,
            ),
        ):
            return int(node.value)
        return None

    def _load_list_element_via_runtime(
        self,
        *,
        base: astx.AST,
        list_ptr: ir.Value,
        index_node: astx.AST,
    ) -> None:
        """
        title: Load one list element through the shared runtime bounds checks.
        parameters:
          base:
            type: astx.AST
          list_ptr:
            type: ir.Value
          index_node:
            type: astx.AST
        """
        self.visit_child(index_node)
        index = safe_pop(self.result_stack)
        if index is None:
            raise Exception("dynamic list subscript requires an index value")
        index = self._cast_ast_value(
            index,
            source_type=self._resolved_ast_type(index_node),
            target_type=astx.Int64(),
        )
        self.result_stack.append(
            self._load_list_element_at_index(
                base=base,
                list_ptr=list_ptr,
                index=index,
            )
        )

    def _load_list_element_at_index(
        self,
        *,
        base: astx.AST,
        list_ptr: ir.Value,
        index: ir.Value,
    ) -> ir.Value:
        """
        title: Load one list element at a lowered Int64 index.
        parameters:
          base:
            type: astx.AST
          list_ptr:
            type: ir.Value
          index:
            type: ir.Value
        returns:
          type: ir.Value
        """
        output = self.create_entry_block_alloca(
            "list.element.out", self._llvm.OPAQUE_POINTER_TYPE
        )
        status = self._llvm.ir_builder.call(
            self.require_runtime_symbol(LIST_RUNTIME_FEATURE, LIST_AT_SYMBOL),
            [list_ptr, index, output],
            name="irx_list_at_status",
        )
        self.check_list_status(base, status)
        raw_ptr = self._llvm.ir_builder.load(output, name="irx_list_at_ptr")
        llvm_element_type = self._list_element_llvm_type(base)
        typed_ptr = self._llvm.ir_builder.bitcast(
            raw_ptr,
            llvm_element_type.as_pointer(),
            name="irx_list_at_typed_ptr",
        )
        return cast(
            ir.Value,
            self._llvm.ir_builder.load(
                typed_ptr,
                name="irx_list_at_load",
            ),
        )

    def _literal_list_pointer_for_runtime(
        self,
        *,
        base: astx.LiteralList,
        literal_value: ir.Value,
    ) -> ir.Value:
        """
        title: Build one transient runtime list view over one literal list.
        parameters:
          base:
            type: astx.LiteralList
          literal_value:
            type: ir.Value
        returns:
          type: ir.Value
        """
        list_type = cast(ir.LiteralStructType, self._llvm_list_type())
        list_slot = self.create_entry_block_alloca(
            "literal_list_runtime_value", list_type
        )
        zero = ir.Constant(self._llvm.INT32_TYPE, 0)

        def field_ptr(name: str) -> ir.Value:
            """
            title: Return one pointer to one runtime list field.
            parameters:
              name:
                type: str
            returns:
              type: ir.Value
            """
            return self._llvm.ir_builder.gep(
                list_slot,
                [
                    zero,
                    ir.Constant(
                        self._llvm.INT32_TYPE,
                        LIST_FIELD_INDICES[name],
                    ),
                ],
                inbounds=True,
                name=f"literal_list_{name}_ptr",
            )

        element_count = len(base.elements)
        if element_count == 0:
            data_ptr = ir.Constant(self._llvm.INT8_TYPE.as_pointer(), None)
        elif isinstance(literal_value.type, ir.ArrayType):
            literal_slot = self.create_entry_block_alloca(
                "literal_list_runtime_storage", literal_value.type
            )
            self._llvm.ir_builder.store(literal_value, literal_slot)
            first_ptr = self._llvm.ir_builder.gep(
                literal_slot,
                [zero, zero],
                inbounds=True,
                name="literal_list_runtime_data",
            )
            data_ptr = self._llvm.ir_builder.bitcast(
                first_ptr,
                self._llvm.INT8_TYPE.as_pointer(),
                name="literal_list_runtime_bytes",
            )
        elif isinstance(literal_value.type, ir.PointerType):
            data_ptr = self._llvm.ir_builder.bitcast(
                literal_value,
                self._llvm.INT8_TYPE.as_pointer(),
                name="literal_list_runtime_bytes",
            )
        else:
            raise Exception(
                "literal list indexing requires array-like storage"
            )

        element_count_i64 = ir.Constant(self._llvm.INT64_TYPE, element_count)
        element_size_i64 = ir.Constant(
            self._llvm.INT64_TYPE,
            self._list_element_size(base),
        )

        self._llvm.ir_builder.store(data_ptr, field_ptr("data"))
        self._llvm.ir_builder.store(
            element_count_i64,
            field_ptr("length"),
        )
        self._llvm.ir_builder.store(
            element_count_i64,
            field_ptr("capacity"),
        )
        self._llvm.ir_builder.store(
            element_size_i64,
            field_ptr("element_size"),
        )
        # Static views borrow their elements and are never destroyed.
        self._llvm.ir_builder.store(
            ir.Constant(self._llvm.INT32_TYPE, 0), field_ptr("element_kind")
        )
        return list_slot

    @private
    def track_list_construction(self, output: ir.Value) -> CleanupAction:
        """
        title: Roll back initialized elements even for a pending move.
        parameters:
          output:
            type: ir.Value
        returns:
          type: CleanupAction
        """
        destroy = self.require_runtime_symbol(
            LIST_RUNTIME_FEATURE, LIST_DESTROY_SYMBOL
        )

        def release() -> None:
            """
            title: Drop the partially constructed list through its native ABI.
            """
            self._llvm.ir_builder.call(destroy, [output])

        action = CleanupAction(release, fallible=False)
        self.cleanup_stack.append(action)
        return action

    @cast(DispatchRegistrar, VisitorCore.visit).dispatch
    def visit(self, node: astx.ListExpr) -> None:
        """
        title: Construct resolved elements in order with rollback cleanup.
        parameters:
          node:
            type: astx.ListExpr
        """
        info = cast(
            SemanticInfo,
            require_semantic_metadata(
                getattr(node, "semantic", None),
                node=node,
                metadata="semantic",
                context="list construction",
            ),
        )
        tensor = info.collection_tensor
        if tensor is not None:
            self.visit_child(tensor)
            return
        element_type = require_semantic_metadata(
            list_element_type(info.resolved_type),
            node=node,
            metadata="concrete list element type",
            context="list construction",
        )
        output = self.create_entry_block_alloca(
            "list.expression", self._llvm_list_type()
        )
        self._llvm.ir_builder.store(self._empty_list_value(node), output)
        cleanup = self.track_list_construction(output)
        slot = self.create_entry_block_alloca(
            "list.expression.item", self._list_element_llvm_type(node)
        )
        append = self.require_runtime_symbol(
            LIST_RUNTIME_FEATURE, LIST_APPEND_SYMBOL
        )
        for item in node.elements:
            element_depth = len(self.cleanup_stack)
            self.visit_child(item)
            value = safe_pop(self.result_stack)
            if value is None:
                raise_lowering_error(
                    "list element did not produce a value",
                    node=item,
                    code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                )
            value = self._cast_ast_value(
                value,
                source_type=self._resolved_ast_type(item),
                target_type=element_type,
            )
            self._llvm.ir_builder.store(value, slot)
            raw = self._llvm.ir_builder.bitcast(
                slot, self._llvm.INT8_TYPE.as_pointer()
            )
            status = self._llvm.ir_builder.call(append, [output, raw])
            self.check_list_status(item, status)
            self._emit_temporary_cleanups(element_depth)
        self.cleanup_stack.remove(cleanup)
        self._register_owned_list_temporary(node, output)
        self.result_stack.append(
            self._llvm.ir_builder.load(output, name="list.expression.value")
        )

    def _lower_literal_list_index_via_runtime(
        self,
        *,
        base: astx.LiteralList,
        index_node: astx.AST,
    ) -> None:
        """
        title: Lower one literal-list index through the runtime checks.
        parameters:
          base:
            type: astx.LiteralList
          index_node:
            type: astx.AST
        """
        self.visit_child(base)
        literal_value = safe_pop(self.result_stack)
        if literal_value is None:
            raise Exception("literal list indexing requires a lowered value")

        list_ptr = self._literal_list_pointer_for_runtime(
            base=base,
            literal_value=literal_value,
        )
        self._load_list_element_via_runtime(
            base=base,
            list_ptr=list_ptr,
            index_node=index_node,
        )

    def _list_pointer_and_length_for_iteration(
        self,
        base: astx.AST,
    ) -> tuple[ir.Value, ir.Value]:
        """
        title: Return an addressable list value and Int64 length for iteration.
        parameters:
          base:
            type: astx.AST
        returns:
          type: tuple[ir.Value, ir.Value]
        """
        if isinstance(base, astx.LiteralList):
            self.visit_child(base)
            literal_value = safe_pop(self.result_stack)
            if literal_value is None:
                raise Exception("literal list iteration requires a value")
            list_ptr = self._literal_list_pointer_for_runtime(
                base=base,
                literal_value=literal_value,
            )
            return (
                list_ptr,
                ir.Constant(self._llvm.INT64_TYPE, len(base.elements)),
            )

        list_ptr = self._list_pointer_for_call(
            base,
            name="irx_list_iter_value",
        )
        length_ptr = self._llvm.ir_builder.gep(
            list_ptr,
            [
                ir.Constant(self._llvm.INT32_TYPE, 0),
                ir.Constant(
                    self._llvm.INT32_TYPE,
                    LIST_FIELD_INDICES["length"],
                ),
            ],
            inbounds=True,
            name="irx_list_iter_length_ptr",
        )
        return (
            list_ptr,
            self._llvm.ir_builder.load(
                length_ptr,
                name="irx_list_iter_length_i64",
            ),
        )

    def _lower_list_subscript(
        self,
        *,
        base: astx.AST,
        index_node: astx.AST,
        result_node: astx.AST,
    ) -> None:
        """
        title: Lower one list indexing operation.
        parameters:
          base:
            type: astx.AST
          index_node:
            type: astx.AST
          result_node:
            type: astx.AST
        """
        if isinstance(base, astx.LiteralList):
            static_index = self._static_integer_literal_value(index_node)
            if static_index is not None and 0 <= static_index < len(
                base.elements
            ):
                self._lower_literal_list_index(
                    base=base,
                    index_node=index_node,
                )
                self.copy_list_string_result(result_node)
                return
            self._lower_literal_list_index_via_runtime(
                base=base,
                index_node=index_node,
            )
            self.copy_list_string_result(result_node)
            return
        if list_element_type(self._resolved_ast_type(base)) is None:
            raise Exception(
                "dynamic list subscript requires a single concrete element "
                "type"
            )

        list_ptr = self._list_pointer_for_call(
            base,
            name="irx_list_index_value",
        )
        self._load_list_element_via_runtime(
            base=base,
            list_ptr=list_ptr,
            index_node=index_node,
        )
        self.copy_list_string_result(result_node)

    @private
    def copy_list_string_result(self, node: astx.AST) -> None:
        """
        title: Detach indexed string storage from a mutable list owner.
        parameters:
          node:
            type: astx.AST
        """
        if not is_string_type(self._resolved_ast_type(node)):
            return
        value = safe_pop(self.result_stack)
        if value is None:
            raise_lowering_error(
                "string index did not produce a value",
                node=node,
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
            )
        pointer = self._copy_string_to_heap(node, value)
        self._register_owned_string_temporary(node, pointer)
        self.result_stack.append(pointer)

    def _lower_literal_list_index(
        self,
        *,
        base: astx.LiteralList,
        index_node: astx.AST,
    ) -> None:
        """
        title: Lower one literal-list indexing operation.
        summary: >-
          Use direct GEP lowering only when the caller has already proven the
          index is one known-safe constant within bounds.
        parameters:
          base:
            type: astx.LiteralList
          index_node:
            type: astx.AST
        """
        self.visit_child(base)
        literal_value = safe_pop(self.result_stack)
        if literal_value is None:
            raise Exception("literal list indexing requires a lowered value")

        self.visit_child(index_node)
        index = safe_pop(self.result_stack)
        if index is None:
            raise Exception("literal list indexing requires an index value")
        index = self._cast_ast_value(
            index,
            source_type=self._resolved_ast_type(index_node),
            target_type=astx.Int32(),
        )

        zero = ir.Constant(self._llvm.INT32_TYPE, 0)
        if isinstance(literal_value.type, ir.ArrayType):
            literal_slot = self.create_entry_block_alloca(
                "literal_list_index_value", literal_value.type
            )
            self._llvm.ir_builder.store(literal_value, literal_slot)
            element_ptr = self._llvm.ir_builder.gep(
                literal_slot,
                [zero, index],
                inbounds=True,
                name="literal_list_index_ptr",
            )
            self.result_stack.append(
                self._llvm.ir_builder.load(
                    element_ptr,
                    name="literal_list_index_load",
                )
            )
            return

        if isinstance(literal_value.type, ir.PointerType):
            element_ptr = self._llvm.ir_builder.gep(
                literal_value,
                [index],
                inbounds=True,
                name="literal_list_index_ptr",
            )
            self.result_stack.append(
                self._llvm.ir_builder.load(
                    element_ptr,
                    name="literal_list_index_load",
                )
            )
            return

        raise Exception("literal list indexing requires array-like storage")

    def _append_list_comprehension_value(
        self,
        *,
        node: astx.ListComprehension,
        output_ptr: ir.Value,
        element_type: astx.DataType,
    ) -> None:
        """
        title: Append one computed comprehension element to the output list.
        parameters:
          node:
            type: astx.ListComprehension
          output_ptr:
            type: ir.Value
          element_type:
            type: astx.DataType
        """
        element_depth = len(self.cleanup_stack)
        self.visit_child(node.element)
        value = safe_pop(self.result_stack)
        if value is None:
            raise Exception("list comprehension element did not lower")
        value = self._cast_ast_value(
            value,
            source_type=self._resolved_ast_type(node.element),
            target_type=element_type,
        )

        llvm_element_type = self._llvm_type_for_ast_type(element_type)
        if llvm_element_type is None:
            raise_lowering_error(
                "list comprehension element type is not lowerable",
                node=node.element,
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
            )
        value_ptr = self.create_entry_block_alloca(
            "irx_list_comprehension_value", llvm_element_type
        )
        self._llvm.ir_builder.store(value, value_ptr)
        raw_value_ptr = self._llvm.ir_builder.bitcast(
            value_ptr,
            self._llvm.INT8_TYPE.as_pointer(),
            name="irx_list_comprehension_bytes",
        )
        append_status = self._llvm.ir_builder.call(
            self.require_runtime_symbol(
                LIST_RUNTIME_FEATURE,
                LIST_APPEND_SYMBOL,
            ),
            [output_ptr, raw_value_ptr],
            name="irx_list_comprehension_append_status",
        )
        self.check_list_status(node, append_status)
        self._emit_temporary_cleanups(element_depth)

    def _lower_list_comprehension_filters(
        self,
        *,
        node: astx.ListComprehension,
        clauses: list[astx.ComprehensionClause],
        clause_index: int,
        condition_index: int,
        advance_block: ir.Block,
        output_ptr: ir.Value,
        element_type: astx.DataType,
    ) -> None:
        """
        title: Lower one clause's comprehension filters.
        parameters:
          node:
            type: astx.ListComprehension
          clauses:
            type: list[astx.ComprehensionClause]
          clause_index:
            type: int
          condition_index:
            type: int
          advance_block:
            type: ir.Block
          output_ptr:
            type: ir.Value
          element_type:
            type: astx.DataType
        """
        clause = clauses[clause_index]
        conditions = list(clause.conditions.nodes)
        if condition_index >= len(conditions):
            self._lower_list_comprehension_clause(
                node=node,
                clauses=clauses,
                clause_index=clause_index + 1,
                output_ptr=output_ptr,
                element_type=element_type,
            )
            return

        condition = conditions[condition_index]
        passed_block = self._llvm.ir_builder.function.append_basic_block(
            f"list.comp.{clause_index}.filter.{condition_index}.pass"
        )
        condition_depth = len(self.cleanup_stack)
        self.visit_child(condition)
        condition_value = cast(Any, self)._lower_boolean_condition(
            safe_pop(self.result_stack),
            node=condition,
            context="list comprehension filter",
        )
        self._emit_temporary_cleanups(condition_depth)
        self._llvm.ir_builder.cbranch(
            condition_value,
            passed_block,
            advance_block,
        )
        self._llvm.ir_builder.position_at_start(passed_block)
        self._lower_list_comprehension_filters(
            node=node,
            clauses=clauses,
            clause_index=clause_index,
            condition_index=condition_index + 1,
            advance_block=advance_block,
            output_ptr=output_ptr,
            element_type=element_type,
        )

    def _lower_list_comprehension_clause(
        self,
        *,
        node: astx.ListComprehension,
        clauses: list[astx.ComprehensionClause],
        clause_index: int,
        output_ptr: ir.Value,
        element_type: astx.DataType,
    ) -> None:
        """
        title: Lower one nested list-comprehension clause.
        parameters:
          node:
            type: astx.ListComprehension
          clauses:
            type: list[astx.ComprehensionClause]
          clause_index:
            type: int
          output_ptr:
            type: ir.Value
          element_type:
            type: astx.DataType
        """
        if clause_index >= len(clauses):
            self._append_list_comprehension_value(
                node=node,
                output_ptr=output_ptr,
                element_type=element_type,
            )
            return

        clause = clauses[clause_index]
        iteration = self._resolved_iteration(clause)
        if iteration is None:
            raise_lowering_error(
                "list comprehension clause is missing resolved iteration "
                "metadata",
                node=clause,
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
            )
        if iteration.kind is not IterationKind.LIST:
            raise_lowering_error(
                "list comprehension lowering currently supports only list "
                f"iterables, got {iteration.kind.value}",
                node=clause.iterable,
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
            )

        target_name = cast(str, getattr(clause.target, "name", "item"))
        target_type = (
            iteration.target_symbol.type_
            if iteration.target_symbol is not None
            else iteration.element_type
        )
        target_llvm_type = self._llvm_type_for_ast_type(target_type)
        if target_llvm_type is None:
            raise_lowering_error(
                "list comprehension target type is not lowerable",
                node=clause.target,
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
            )
        target_addr = self.create_entry_block_alloca(
            target_name,
            target_llvm_type,
        )
        index_addr = self.create_entry_block_alloca(
            f"{target_name}_comp_index",
            self._llvm.INT64_TYPE,
        )
        self._llvm.ir_builder.store(
            ir.Constant(self._llvm.INT64_TYPE, 0),
            index_addr,
        )
        iterable_depth = len(self.cleanup_stack)
        list_ptr, length = self._list_pointer_and_length_for_iteration(
            clause.iterable
        )

        cond_block = self._llvm.ir_builder.function.append_basic_block(
            f"list.comp.{clause_index}.cond"
        )
        body_block = self._llvm.ir_builder.function.append_basic_block(
            f"list.comp.{clause_index}.body"
        )
        advance_block = self._llvm.ir_builder.function.append_basic_block(
            f"list.comp.{clause_index}.advance"
        )
        exit_block = self._llvm.ir_builder.function.append_basic_block(
            f"list.comp.{clause_index}.exit"
        )
        self._llvm.ir_builder.branch(cond_block)

        self._llvm.ir_builder.position_at_start(cond_block)
        current_index = self._llvm.ir_builder.load(
            index_addr,
            name="list_comp_index",
        )
        has_item = self._llvm.ir_builder.icmp_signed(
            "<",
            current_index,
            length,
            name="list_comp_has_item",
        )
        self._llvm.ir_builder.cbranch(has_item, body_block, exit_block)

        iteration_depth = len(self.cleanup_stack)
        self._llvm.ir_builder.position_at_start(body_block)
        body_index = self._llvm.ir_builder.load(
            index_addr,
            name="list_comp_body_index",
        )
        item_value = self._load_list_element_at_index(
            base=clause.iterable,
            list_ptr=list_ptr,
            index=body_index,
        )
        item_value = self._cast_ast_value(
            item_value,
            source_type=iteration.element_type,
            target_type=target_type,
        )
        if is_string_type(iteration.element_type):
            item_value = self._copy_string_to_heap(clause.target, item_value)
        self._llvm.ir_builder.store(item_value, target_addr)
        if is_string_type(iteration.element_type):
            cast(Any, self)._register_owned_string_cleanup(
                clause.target,
                target_addr,
            )
        target_key = semantic_symbol_key(clause.target, target_name)
        with cast(Any, self)._temporary_named_value(
            target_key,
            target_addr,
            is_constant=True,
        ):
            self._lower_list_comprehension_filters(
                node=node,
                clauses=clauses,
                clause_index=clause_index,
                condition_index=0,
                advance_block=advance_block,
                output_ptr=output_ptr,
                element_type=element_type,
            )
        if not self._llvm.ir_builder.block.is_terminated:
            self._llvm.ir_builder.branch(advance_block)

        self._llvm.ir_builder.position_at_start(advance_block)
        self._emit_active_cleanups(iteration_depth)
        del self.cleanup_stack[iteration_depth:]
        next_index = self._llvm.ir_builder.add(
            self._llvm.ir_builder.load(
                index_addr,
                name="list_comp_step_index",
            ),
            ir.Constant(self._llvm.INT64_TYPE, 1),
            name="list_comp_next_index",
        )
        self._llvm.ir_builder.store(next_index, index_addr)
        self._llvm.ir_builder.branch(cond_block)

        self._llvm.ir_builder.position_at_start(exit_block)
        self._emit_temporary_cleanups(iterable_depth)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.ListComprehension) -> None:
        """
        title: Visit ListComprehension nodes.
        parameters:
          node:
            type: astx.ListComprehension
        """
        result_type = self._resolved_ast_type(node)
        element_type = list_element_type(result_type)
        if element_type is None:
            raise_lowering_error(
                "list comprehension requires a concrete element type",
                node=node,
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
            )
        current_block = self._llvm.ir_builder.block
        output_ptr = self.create_entry_block_alloca(
            "irx_list_comprehension_out",
            self._llvm_list_type(),
        )
        initializer_builder = ir.IRBuilder(
            self._llvm.ir_builder.function.entry_basic_block
        )
        initializer_builder.position_after(output_ptr)
        initializer_builder.store(
            self._empty_list_value_for_type(result_type),
            output_ptr,
        )
        self._llvm.ir_builder.position_at_end(current_block)
        self._llvm.ir_builder.store(
            self._empty_list_value_for_type(result_type),
            output_ptr,
        )
        cleanup = self.track_list_construction(output_ptr)
        clauses = list(node.generators.nodes)
        if clauses:
            self._lower_list_comprehension_clause(
                node=node,
                clauses=clauses,
                clause_index=0,
                output_ptr=output_ptr,
                element_type=element_type,
            )
        else:
            self._append_list_comprehension_value(
                node=node,
                output_ptr=output_ptr,
                element_type=element_type,
            )

        self.cleanup_stack.remove(cleanup)
        self._register_owned_list_temporary(node, output_ptr)
        self.result_stack.append(
            self._llvm.ir_builder.load(
                output_ptr,
                name="irx_list_comprehension_result",
            )
        )

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.SetComprehension) -> None:
        """
        title: Visit SetComprehension nodes.
        parameters:
          node:
            type: astx.SetComprehension
        """
        raise_lowering_error(
            "set comprehension lowering requires the future dynamic set "
            "runtime",
            node=node,
            code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
        )

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.DictComprehension) -> None:
        """
        title: Visit DictComprehension nodes.
        parameters:
          node:
            type: astx.DictComprehension
        """
        raise_lowering_error(
            "dict comprehension lowering requires the future dynamic dict "
            "runtime",
            node=node,
            code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
        )

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.ListCreate) -> None:
        """
        title: Visit ListCreate nodes.
        parameters:
          node:
            type: astx.ListCreate
        """
        self.result_stack.append(self._empty_list_value(node))

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.ListIndex) -> None:
        """
        title: Visit ListIndex nodes.
        parameters:
          node:
            type: astx.ListIndex
        """
        self._lower_list_subscript(
            base=node.base,
            index_node=node.index,
            result_node=node,
        )

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.ListLength) -> None:
        """
        title: Visit ListLength nodes.
        parameters:
          node:
            type: astx.ListLength
        """
        if isinstance(node.base, astx.LiteralList):
            self.result_stack.append(
                ir.Constant(self._llvm.INT64_TYPE, len(node.base.elements))
            )
            return
        list_ptr = self._list_pointer_for_call(
            node.base,
            name="irx_list_length_value",
        )
        length_ptr = self._llvm.ir_builder.gep(
            list_ptr,
            [
                ir.Constant(self._llvm.INT32_TYPE, 0),
                ir.Constant(
                    self._llvm.INT32_TYPE,
                    LIST_FIELD_INDICES["length"],
                ),
            ],
            inbounds=True,
            name="irx_list_length_ptr",
        )
        length_i64 = self._llvm.ir_builder.load(
            length_ptr,
            name="irx_list_length_i64",
        )
        self.result_stack.append(length_i64)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.ListAppend) -> None:
        """
        title: Visit ListAppend nodes.
        parameters:
          node:
            type: astx.ListAppend
        """
        append_fn = self.require_runtime_symbol(
            LIST_RUNTIME_FEATURE,
            LIST_APPEND_SYMBOL,
        )
        list_ptr = self._lvalue_address(node.base)

        self.visit_child(node.value)
        value = safe_pop(self.result_stack)
        if value is None:
            raise Exception("dynamic list append requires a value")

        element_type = list_element_type(self._resolved_ast_type(node.base))
        if element_type is None:
            raise Exception(
                "dynamic list append requires a single concrete element type"
            )
        value = self._cast_ast_value(
            value,
            source_type=self._resolved_ast_type(node.value),
            target_type=element_type,
        )

        llvm_element_type = self._list_element_llvm_type(node.base)
        value_ptr = self.create_entry_block_alloca(
            "irx_list_append_value", llvm_element_type
        )
        self._llvm.ir_builder.store(value, value_ptr)
        raw_value_ptr = self._llvm.ir_builder.bitcast(
            value_ptr,
            self._llvm.INT8_TYPE.as_pointer(),
            name="irx_list_append_bytes",
        )

        result = self._llvm.ir_builder.call(
            append_fn,
            [list_ptr, raw_value_ptr],
            name="irx_list_append_status",
        )
        self.check_list_status(node, result)
        self.result_stack.append(result)
