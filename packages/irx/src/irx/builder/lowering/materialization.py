"""
title: Bounded, single-pass numeric list construction with rollback.
"""

from typing import TYPE_CHECKING, cast

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import ResolvedMaterialization
from irx.analysis.types import is_unsigned_type
from irx.builder.core import VisitorCore
from irx.builder.diagnostics import (
    require_lowered_value,
    require_semantic_metadata,
)
from irx.builder.lowering.cursors import LoweredCursor
from irx.builder.runtime import safe_pop
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.lowering.list import ListVisitorMixin


@private
@typechecked
def lower_materialization(
    visitor: VisitorCore,
    node: astx.FunctionCall,
    plan: ResolvedMaterialization,
) -> None:
    """
    title: >-
      Consume once, detect excess before append, and never publish a prefix.
    summary: >-
      Sized sources use a borrowed snapshot. Unsized sources probe once beyond
      the bound; the counter cannot overflow, even at INT64_MAX. Cleanup is
      registered before limit evaluation, resumption, or allocation can fail.
    parameters:
      visitor:
        type: VisitorCore
      node:
        type: astx.FunctionCall
      plan:
        type: ResolvedMaterialization
    """
    lists: ListVisitorMixin = cast("ListVisitorMixin", visitor)
    builder = visitor._llvm.ir_builder
    integer = ir.IntType(64)
    zero = ir.Constant(integer, 0)
    iteration = plan.iteration
    depth = len(visitor.cleanup_stack)
    cursor = LoweredCursor(visitor, iteration)
    yielded = cursor.item
    length = cursor.length
    limit = length
    if plan.max_items is not None:
        visitor.visit_child(plan.max_items)
        raw_limit = require_lowered_value(
            safe_pop(visitor.result_stack), node=node, context="max_items"
        )
        limit = visitor._cast_value_to_type(
            raw_limit,
            integer,
            unsigned=is_unsigned_type(
                visitor._resolved_ast_type(plan.max_items)
            ),
        )
    limit = require_semantic_metadata(
        limit,
        node=node,
        metadata="materialization bound",
        context="list materialization",
    )
    visitor._guard_runtime_condition(
        node,
        builder.icmp_signed(">=", limit, zero),
        code="ARX-RUNTIME-LIST-001",
        message="max_items must be nonnegative",
        block_name="list.bound",
        exception_role="ValueError",
    )
    if length is not None:
        visitor._guard_runtime_condition(
            node,
            builder.icmp_signed("<=", length, limit),
            code="ARX-RUNTIME-LIST-001",
            message="input exceeds max_items",
            block_name="list.bound",
            exception_role="ValueError",
        )
    output = visitor.create_entry_block_alloca(
        "list.materialized", lists._llvm_list_type()
    )
    builder.store(lists._empty_list_value(node), output)
    rollback = lists.track_list_construction(output)
    index_slot = visitor.create_entry_block_alloca("list.index", integer)
    builder.store(zero, index_slot)
    function = builder.function
    condition = function.append_basic_block("materialize.next")
    body = function.append_basic_block("materialize.item")
    done = function.append_basic_block("materialize.done")
    builder.branch(condition)
    builder.position_at_end(condition)
    index = builder.load(index_slot)
    builder.cbranch(cursor.advance(), body, done)
    builder.position_at_end(body)
    visitor._guard_runtime_condition(
        node,
        builder.icmp_signed("<", index, limit),
        code="ARX-RUNTIME-LIST-001",
        message="input exceeds max_items",
        block_name="list.bound",
        exception_role="ValueError",
    )
    item_pointer = yielded
    if plan.checked_bytes:
        value = builder.load(yielded)
        unsigned = is_unsigned_type(iteration.element_type)
        # Widen before checking so i8's upper bound is not truncated to -1.
        wide = visitor._cast_value_to_type(value, integer, unsigned=unsigned)
        valid = builder.icmp_unsigned("<=", wide, ir.Constant(integer, 255))
        visitor._guard_runtime_condition(
            node,
            valid,
            code="ARX-RUNTIME-BYTES-001",
            message="bytes items must be integers in 0..255",
            block_name="bytes.item",
            exception_role="ValueError",
        )
        item_pointer = visitor.create_entry_block_alloca(
            "bytes.item", ir.IntType(8)
        )
        builder.store(builder.trunc(wide, ir.IntType(8)), item_pointer)
    append = visitor.require_runtime_symbol("list", "irx_list_append")
    status = builder.call(
        append,
        [output, builder.bitcast(item_pointer, ir.IntType(8).as_pointer())],
    )
    lists.check_list_status(node, status)
    builder.store(builder.add(index, ir.Constant(integer, 1)), index_slot)
    builder.branch(condition)
    builder.position_at_end(done)
    visitor.cleanup_stack.remove(rollback)
    visitor._emit_temporary_cleanups(depth)
    visitor._register_owned_list_temporary(node, output)
    visitor.result_stack.append(builder.load(output))
