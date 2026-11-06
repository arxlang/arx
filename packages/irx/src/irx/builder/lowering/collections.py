# mypy: disable-error-code=no-redef

"""
title: Common collection method lowering.
summary: >-
  Lower backend-neutral list, tuple, set, and dictionary query nodes using the
  semantic collection sidecars attached during analysis.
"""

from __future__ import annotations

from typing import cast

import astx

from llvmlite import ir
from plum import dispatch
from public import private

from irx.analysis.resolved_nodes import (
    CollectionMethodKind,
    ResolvedCollectionMethod,
)
from irx.analysis.types import same_type
from irx.builder.diagnostics import (
    raise_lowering_internal_error,
    require_semantic_metadata,
)
from irx.builder.lowering.contracts import CollectionServices
from irx.builder.runtime import safe_pop
from irx.builder.services.representations import (
    resolved_type as resolved_ast_type,
)
from irx.builtins.collections.list import LIST_FIELD_INDICES, list_element_type
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class CollectionLowering:
    """
    title: Common collection method lowering implementation.
    attributes:
      services:
        type: CollectionServices
    """

    services: CollectionServices

    def __init__(self, services: CollectionServices) -> None:
        """
        title: Bind explicit family-owned emission dependencies.
        parameters:
          services:
            type: CollectionServices
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
            f"no collections handler for {type(node).__name__}", node=node
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
                "llvm.collections.CollectionLength",
                "irx.collections",
                "lowering",
                astx.CollectionLength,
                self.visit,
                source="irx.builder.lowering.collections.CollectionLowering.visit",
            ),
            contribute_node(
                "llvm.collections.CollectionIsEmpty",
                "irx.collections",
                "lowering",
                astx.CollectionIsEmpty,
                self.visit,
                source="irx.builder.lowering.collections.CollectionLowering.visit",
            ),
            contribute_node(
                "llvm.collections.CollectionContains",
                "irx.collections",
                "lowering",
                astx.CollectionContains,
                self.visit,
                source="irx.builder.lowering.collections.CollectionLowering.visit",
            ),
            contribute_node(
                "llvm.collections.CollectionIndex",
                "irx.collections",
                "lowering",
                astx.CollectionIndex,
                self.visit,
                source="irx.builder.lowering.collections.CollectionLowering.visit",
            ),
            contribute_node(
                "llvm.collections.CollectionCount",
                "irx.collections",
                "lowering",
                astx.CollectionCount,
                self.visit,
                source="irx.builder.lowering.collections.CollectionLowering.visit",
            ),
        )

    def _resolved_collection_method(
        self,
        node: astx.AST,
    ) -> ResolvedCollectionMethod:
        """
        title: Return resolved collection method metadata.
        parameters:
          node:
            type: astx.AST
        returns:
          type: ResolvedCollectionMethod
        """
        semantic = getattr(node, "semantic", None)
        resolution = getattr(semantic, "resolved_collection_method", None)
        return require_semantic_metadata(
            cast(ResolvedCollectionMethod | None, resolution),
            node=node,
            metadata="resolved_collection_method",
            context="collection method lowering",
        )

    def _static_collection_length(self, base: astx.AST) -> int | None:
        """
        title: Return a statically known collection length.
        parameters:
          base:
            type: astx.AST
        returns:
          type: int | None
        """
        if isinstance(base, (astx.LiteralList, astx.LiteralTuple)):
            return len(base.elements)
        if isinstance(base, astx.LiteralSet):
            return len(base.elements)
        if isinstance(base, astx.LiteralDict):
            return len(base.elements)

        base_type = resolved_ast_type(base)
        if isinstance(base_type, astx.TupleType):
            return len(base_type.element_types)
        return None

    def _dynamic_list_length(self, base: astx.AST) -> ir.Value:
        """
        title: Lower one dynamic list length without narrowing.
        parameters:
          base:
            type: astx.AST
        returns:
          type: ir.Value
        """
        list_ptr = self.services.list_pointer_for_call(
            base,
            name="irx_collection_length_value",
        )
        length_ptr = self.services.llvm.ir_builder.gep(
            list_ptr,
            [
                ir.Constant(self.services.llvm.INT32_TYPE, 0),
                ir.Constant(
                    self.services.llvm.INT32_TYPE,
                    LIST_FIELD_INDICES["length"],
                ),
            ],
            inbounds=True,
            name="irx_collection_length_ptr",
        )
        length_i64 = self.services.llvm.ir_builder.load(
            length_ptr,
            name="irx_collection_length_i64",
        )
        return length_i64

    def _collection_length_value(self, base: astx.AST) -> ir.Value:
        """
        title: Lower one collection length to an Int64 value.
        parameters:
          base:
            type: astx.AST
        returns:
          type: ir.Value
        """
        static_length = self._static_collection_length(base)
        if static_length is not None:
            return ir.Constant(self.services.llvm.INT64_TYPE, static_length)

        if isinstance(resolved_ast_type(base), astx.ListType):
            return self._dynamic_list_length(base)

        raise TypeError(
            "collection length lowering currently requires a literal "
            "collection, tuple type, or dynamic list"
        )

    def _emit_collection_equal(
        self,
        lhs: ir.Value,
        rhs: ir.Value,
        *,
        lhs_type: astx.DataType | None,
        name: str,
        resolution: ResolvedCollectionMethod,
    ) -> ir.Value:
        """
        title: Emit one equality comparison for collection search.
        parameters:
          lhs:
            type: ir.Value
          rhs:
            type: ir.Value
          lhs_type:
            type: astx.DataType | None
          name:
            type: str
          resolution:
            type: ResolvedCollectionMethod
        returns:
          type: ir.Value
        """
        if self.services.numeric.is_numeric_value(
            lhs
        ) and self.services.numeric.is_numeric_value(rhs):
            plan = next(
                (
                    plan
                    for plan in resolution.comparison_plans
                    if same_type(plan.lhs_type, lhs_type)
                ),
                None,
            )
            plan = require_semantic_metadata(
                plan,
                node=resolution.receiver_node,
                metadata="numeric comparison",
                context="collection search",
            )
            left = require_semantic_metadata(
                plan.lhs_conversion,
                node=resolution.receiver_node,
                metadata="lhs conversion",
                context="collection search",
            )
            right = require_semantic_metadata(
                plan.rhs_conversion,
                node=resolution.receiver_node,
                metadata="rhs conversion",
                context="collection search",
            )
            lhs = self.services.numeric.cast_scalar(
                lhs, source_type=left.source_type, target_type=left.target_type
            )
            rhs = self.services.numeric.cast_scalar(
                rhs,
                source_type=right.source_type,
                target_type=right.target_type,
            )
            unsigned = plan.flags.unsigned
            return self.services.numeric.emit_numeric_compare(
                "==",
                lhs,
                rhs,
                unsigned=unsigned,
                name=name,
            )

        if (
            isinstance(lhs.type, ir.PointerType)
            and isinstance(rhs.type, ir.PointerType)
            and lhs.type.pointee == self.services.llvm.INT8_TYPE
            and rhs.type.pointee == self.services.llvm.INT8_TYPE
        ):
            return self.services.strings.compare(lhs, rhs, "==")

        raise TypeError(
            f"collection equality does not support {lhs.type} and {rhs.type}"
        )

    def _literal_contains_entries(
        self,
        base: astx.AST,
    ) -> tuple[astx.AST, ...]:
        """
        title: Return literal entries that participate in containment.
        parameters:
          base:
            type: astx.AST
        returns:
          type: tuple[astx.AST, Ellipsis]
        """
        if isinstance(base, (astx.LiteralList, astx.LiteralTuple)):
            return tuple(base.elements)
        if isinstance(base, astx.LiteralSet):
            return tuple(
                sorted(
                    cast(set[astx.AST], base.elements),
                    key=lambda node: repr(node.get_struct(True)),
                )
            )
        if isinstance(base, astx.LiteralDict):
            return tuple(base.elements)
        return ()

    def _entry_can_match_probe(
        self,
        entry_type: astx.DataType | None,
        probe_type: astx.DataType | None,
        resolution: ResolvedCollectionMethod,
    ) -> bool:
        """
        title: Return whether one literal entry can match a probe value.
        parameters:
          entry_type:
            type: astx.DataType | None
          probe_type:
            type: astx.DataType | None
          resolution:
            type: ResolvedCollectionMethod
        returns:
          type: bool
        """
        if entry_type is None or probe_type is None:
            return True
        return any(
            same_type(entry_type, allowed)
            for allowed in resolution.matching_types
        )

    def _lower_literal_collection_contains(
        self,
        *,
        base: astx.AST,
        value: astx.AST,
        resolution: ResolvedCollectionMethod,
    ) -> ir.Value:
        """
        title: Lower containment for a literal collection.
        parameters:
          base:
            type: astx.AST
          value:
            type: astx.AST
          resolution:
            type: ResolvedCollectionMethod
        returns:
          type: ir.Value
        """
        entries = self._literal_contains_entries(base)
        if not entries:
            return ir.Constant(self.services.llvm.BOOLEAN_TYPE, 0)

        self.services.visit_child(value)
        needle = safe_pop(self.services.function_state.result_stack)
        if needle is None:
            raise TypeError("collection containment requires a value")

        probe_type = resolved_ast_type(value)
        result: ir.Value = ir.Constant(self.services.llvm.BOOLEAN_TYPE, 0)
        for index, entry in enumerate(entries):
            entry_type = resolved_ast_type(entry)
            if not self._entry_can_match_probe(
                entry_type, probe_type, resolution
            ):
                continue
            self.services.visit_child(entry)
            candidate = safe_pop(self.services.function_state.result_stack)
            if candidate is None:
                raise TypeError("collection containment entry is not a value")
            match = self._emit_collection_equal(
                candidate,
                needle,
                resolution=resolution,
                lhs_type=entry_type,
                name=f"collection_contains_{index}",
            )
            result = self.services.llvm.ir_builder.or_(
                result,
                match,
                name=f"collection_contains_any_{index}",
            )
        return result

    def _lower_list_search(
        self,
        *,
        base: astx.AST,
        value: astx.AST,
        method: CollectionMethodKind,
        resolution: ResolvedCollectionMethod,
    ) -> ir.Value:
        """
        title: Lower dynamic-list containment, index, or count.
        parameters:
          base:
            type: astx.AST
          value:
            type: astx.AST
          method:
            type: CollectionMethodKind
          resolution:
            type: ResolvedCollectionMethod
        returns:
          type: ir.Value
        """
        list_type = resolved_ast_type(base)
        element_type = list_element_type(list_type)
        if element_type is None:
            raise TypeError("list search requires a concrete element type")

        list_ptr, length = self.services.list_pointer_and_length_for_iteration(
            base,
        )
        self.services.numeric.guard_collection_length(base, length)
        self.services.visit_child(value)
        needle = safe_pop(self.services.function_state.result_stack)
        if needle is None:
            raise TypeError("list search requires a value")
        builder = self.services.llvm.ir_builder
        index_addr = self.services.create_entry_block_alloca(
            "collection_search_index",
            self.services.llvm.INT64_TYPE,
        )
        result_addr = self.services.create_entry_block_alloca(
            "collection_search_result",
            self.services.llvm.INT32_TYPE,
        )
        builder.store(
            ir.Constant(self.services.llvm.INT64_TYPE, 0), index_addr
        )
        builder.store(
            self._initial_list_search_result(method),
            result_addr,
        )

        cond_block = builder.function.append_basic_block(
            "collection.search.cond"
        )
        body_block = builder.function.append_basic_block(
            "collection.search.body"
        )
        advance_block = builder.function.append_basic_block(
            "collection.search.advance"
        )
        exit_block = builder.function.append_basic_block(
            "collection.search.exit"
        )
        builder.branch(cond_block)

        builder.position_at_start(cond_block)
        current_index = builder.load(index_addr, name="collection_search_i")
        has_item = builder.icmp_signed(
            "<",
            current_index,
            length,
            name="collection_search_has_item",
        )
        builder.cbranch(has_item, body_block, exit_block)

        builder.position_at_start(body_block)
        body_index = builder.load(
            index_addr,
            name="collection_search_body_i",
        )
        item = self.services.load_list_element_at_index(
            base=base,
            list_ptr=list_ptr,
            index=body_index,
        )
        match = self._emit_collection_equal(
            item,
            needle,
            resolution=resolution,
            lhs_type=element_type,
            name="collection_search_match",
        )
        if method is CollectionMethodKind.COUNT:
            self._update_list_count_result(match, result_addr)
            builder.branch(advance_block)
        else:
            found_block = builder.function.append_basic_block(
                "collection.search.found"
            )
            builder.cbranch(match, found_block, advance_block)
            builder.position_at_start(found_block)
            self._store_list_search_found_result(
                method,
                result_addr,
                body_index,
            )
            builder.branch(exit_block)

        builder.position_at_start(advance_block)
        next_index = builder.add(
            builder.load(index_addr, name="collection_search_step_i"),
            ir.Constant(self.services.llvm.INT64_TYPE, 1),
            name="collection_search_next_i",
        )
        builder.store(next_index, index_addr)
        builder.branch(cond_block)

        builder.position_at_start(exit_block)
        return cast(
            ir.Value,
            builder.load(result_addr, name="collection_search_result_value"),
        )

    def _initial_list_search_result(
        self,
        method: CollectionMethodKind,
    ) -> ir.Constant:
        """
        title: Return the initial Int32 list-search result.
        parameters:
          method:
            type: CollectionMethodKind
        returns:
          type: ir.Constant
        """
        if method is CollectionMethodKind.INDEX:
            return ir.Constant(self.services.llvm.INT32_TYPE, -1)
        return ir.Constant(self.services.llvm.INT32_TYPE, 0)

    def _update_list_count_result(
        self,
        match: ir.Value,
        result_addr: ir.Value,
    ) -> None:
        """
        title: Update count result for one dynamic-list match.
        parameters:
          match:
            type: ir.Value
          result_addr:
            type: ir.Value
        """
        builder = self.services.llvm.ir_builder
        current = builder.load(result_addr, name="collection_count_current")
        incremented = builder.add(
            current,
            ir.Constant(self.services.llvm.INT32_TYPE, 1),
            name="collection_count_incremented",
        )
        selected = builder.select(
            match,
            incremented,
            current,
            name="collection_count_next",
        )
        builder.store(selected, result_addr)

    def _store_list_search_found_result(
        self,
        method: CollectionMethodKind,
        result_addr: ir.Value,
        index: ir.Value,
    ) -> None:
        """
        title: Store the found result for list contains or index.
        parameters:
          method:
            type: CollectionMethodKind
          result_addr:
            type: ir.Value
          index:
            type: ir.Value
        """
        if method is CollectionMethodKind.CONTAINS:
            self.services.llvm.ir_builder.store(
                ir.Constant(self.services.llvm.INT32_TYPE, 1),
                result_addr,
            )
            return
        self.services.llvm.ir_builder.store(
            self.services.llvm.ir_builder.trunc(
                index,
                self.services.llvm.INT32_TYPE,
                "collection_index_i32",
            ),
            result_addr,
        )

    def _sequence_or_literal_search(
        self,
        *,
        base: astx.AST,
        value: astx.AST,
        method: CollectionMethodKind,
        resolution: ResolvedCollectionMethod,
    ) -> ir.Value:
        """
        title: Lower collection search for literals or dynamic lists.
        parameters:
          base:
            type: astx.AST
          value:
            type: astx.AST
          method:
            type: CollectionMethodKind
          resolution:
            type: ResolvedCollectionMethod
        returns:
          type: ir.Value
        """
        if isinstance(
            base,
            (
                astx.LiteralList,
                astx.LiteralTuple,
                astx.LiteralSet,
                astx.LiteralDict,
            ),
        ):
            if method is CollectionMethodKind.CONTAINS:
                return self._lower_literal_collection_contains(
                    resolution=resolution,
                    base=base,
                    value=value,
                )
            return self._lower_literal_sequence_search(
                resolution=resolution,
                base=base,
                value=value,
                method=method,
            )

        if isinstance(resolved_ast_type(base), astx.ListType):
            result = self._lower_list_search(
                resolution=resolution,
                base=base,
                value=value,
                method=method,
            )
            if method is CollectionMethodKind.CONTAINS:
                return self.services.llvm.ir_builder.icmp_signed(
                    "!=",
                    result,
                    ir.Constant(self.services.llvm.INT32_TYPE, 0),
                    name="collection_contains_bool",
                )
            return result

        raise TypeError(
            "collection search lowering currently requires a literal "
            "collection or dynamic list"
        )

    def _lower_literal_sequence_search(
        self,
        *,
        base: astx.AST,
        value: astx.AST,
        method: CollectionMethodKind,
        resolution: ResolvedCollectionMethod,
    ) -> ir.Value:
        """
        title: Lower index or count for a literal list or tuple.
        parameters:
          base:
            type: astx.AST
          value:
            type: astx.AST
          method:
            type: CollectionMethodKind
          resolution:
            type: ResolvedCollectionMethod
        returns:
          type: ir.Value
        """
        entries = self._literal_contains_entries(base)
        if not isinstance(base, (astx.LiteralList, astx.LiteralTuple)):
            raise TypeError("collection index/count requires list or tuple")
        if not entries:
            return self._initial_list_search_result(method)

        self.services.visit_child(value)
        needle = safe_pop(self.services.function_state.result_stack)
        if needle is None:
            raise TypeError("collection search requires a value")

        probe_type = resolved_ast_type(value)
        result: ir.Value = self._initial_list_search_result(method)
        for index, entry in enumerate(entries):
            entry_type = resolved_ast_type(entry)
            if not self._entry_can_match_probe(
                entry_type, probe_type, resolution
            ):
                continue
            self.services.visit_child(entry)
            candidate = safe_pop(self.services.function_state.result_stack)
            if candidate is None:
                raise TypeError("collection search entry is not a value")
            match = self._emit_collection_equal(
                candidate,
                needle,
                resolution=resolution,
                lhs_type=entry_type,
                name=f"collection_sequence_match_{index}",
            )
            if method is CollectionMethodKind.COUNT:
                result = self._next_literal_count_result(result, match, index)
            elif method is CollectionMethodKind.INDEX:
                result = self._next_literal_index_result(result, match, index)
        return result

    def _next_literal_count_result(
        self,
        result: ir.Value,
        match: ir.Value,
        index: int,
    ) -> ir.Value:
        """
        title: Return the next literal count result.
        parameters:
          result:
            type: ir.Value
          match:
            type: ir.Value
          index:
            type: int
        returns:
          type: ir.Value
        """
        incremented = self.services.llvm.ir_builder.add(
            result,
            ir.Constant(self.services.llvm.INT32_TYPE, 1),
            name=f"collection_literal_count_inc_{index}",
        )
        return cast(
            ir.Value,
            self.services.llvm.ir_builder.select(
                match,
                incremented,
                result,
                name=f"collection_literal_count_{index}",
            ),
        )

    def _next_literal_index_result(
        self,
        result: ir.Value,
        match: ir.Value,
        index: int,
    ) -> ir.Value:
        """
        title: Return the next literal index result.
        parameters:
          result:
            type: ir.Value
          match:
            type: ir.Value
          index:
            type: int
        returns:
          type: ir.Value
        """
        not_found = self.services.llvm.ir_builder.icmp_signed(
            "==",
            result,
            ir.Constant(self.services.llvm.INT32_TYPE, -1),
            name=f"collection_literal_index_open_{index}",
        )
        should_set = self.services.llvm.ir_builder.and_(
            match,
            not_found,
            name=f"collection_literal_index_should_set_{index}",
        )
        return cast(
            ir.Value,
            self.services.llvm.ir_builder.select(
                should_set,
                ir.Constant(self.services.llvm.INT32_TYPE, index),
                result,
                name=f"collection_literal_index_{index}",
            ),
        )

    @dispatch
    def visit(self, node: astx.CollectionLength) -> None:
        """
        title: Visit CollectionLength nodes.
        parameters:
          node:
            type: astx.CollectionLength
        """
        if self.services.sequences.lower(node) or self.services.text.lower(
            node
        ):
            return
        resolution = self._resolved_collection_method(node)
        if resolution.method is not CollectionMethodKind.LENGTH:
            raise TypeError("collection length has invalid semantic method")
        self.services.function_state.result_stack.append(
            self._collection_length_value(node.base)
        )

    @dispatch
    def visit(self, node: astx.CollectionIsEmpty) -> None:
        """
        title: Visit CollectionIsEmpty nodes.
        parameters:
          node:
            type: astx.CollectionIsEmpty
        """
        resolution = self._resolved_collection_method(node)
        if resolution.method is not CollectionMethodKind.IS_EMPTY:
            raise TypeError("collection emptiness has invalid semantic method")
        length = self._collection_length_value(node.base)
        self.services.function_state.result_stack.append(
            self.services.llvm.ir_builder.icmp_signed(
                "==",
                length,
                ir.Constant(self.services.llvm.INT64_TYPE, 0),
                name="collection_is_empty",
            )
        )

    @dispatch
    def visit(self, node: astx.CollectionContains) -> None:
        """
        title: Visit CollectionContains nodes.
        parameters:
          node:
            type: astx.CollectionContains
        """
        resolution = self._resolved_collection_method(node)
        if resolution.method is not CollectionMethodKind.CONTAINS:
            raise TypeError("collection contains has invalid semantic method")
        self.services.function_state.result_stack.append(
            self._sequence_or_literal_search(
                resolution=resolution,
                base=node.base,
                value=node.value,
                method=CollectionMethodKind.CONTAINS,
            )
        )

    @dispatch
    def visit(self, node: astx.CollectionIndex) -> None:
        """
        title: Visit CollectionIndex nodes.
        parameters:
          node:
            type: astx.CollectionIndex
        """
        resolution = self._resolved_collection_method(node)
        if resolution.method is not CollectionMethodKind.INDEX:
            raise TypeError("collection index has invalid semantic method")
        self.services.function_state.result_stack.append(
            self._sequence_or_literal_search(
                resolution=resolution,
                base=node.base,
                value=node.value,
                method=CollectionMethodKind.INDEX,
            )
        )

    @dispatch
    def visit(self, node: astx.CollectionCount) -> None:
        """
        title: Visit CollectionCount nodes.
        parameters:
          node:
            type: astx.CollectionCount
        """
        resolution = self._resolved_collection_method(node)
        if resolution.method is not CollectionMethodKind.COUNT:
            raise TypeError("collection count has invalid semantic method")
        self.services.function_state.result_stack.append(
            self._sequence_or_literal_search(
                resolution=resolution,
                base=node.base,
                value=node.value,
                method=CollectionMethodKind.COUNT,
            )
        )
