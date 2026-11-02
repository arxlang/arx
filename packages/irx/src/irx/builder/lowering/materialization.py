"""
title: Bounded, single-pass numeric list construction with rollback.
"""

from typing import TYPE_CHECKING, cast

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import IterationKind, ResolvedMaterialization
from irx.analysis.types import is_unsigned_type
from irx.builder.core import VisitorCore
from irx.builder.diagnostics import (
    require_lowered_value,
    require_semantic_metadata,
)
from irx.builder.lowering.sequences import adapt_sequence, read_sequence
from irx.builder.runtime import safe_pop
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.lowering.exceptions import ExceptionVisitorMixin
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
    exceptions: ExceptionVisitorMixin = cast("ExceptionVisitorMixin", visitor)
    builder = visitor._llvm.ir_builder
    integer = ir.IntType(64)
    zero = ir.Constant(integer, 0)
    iteration = plan.iteration
    depth = len(visitor.cleanup_stack)
    visitor.visit_child(iteration.iterable_node)
    source = require_lowered_value(
        safe_pop(visitor.result_stack), node=node, context="list input"
    )
    llvm_element = require_semantic_metadata(
        visitor._llvm_type_for_ast_type(iteration.element_type),
        node=node,
        metadata="concrete element storage",
        context="materialization",
    )
    yielded = visitor.create_entry_block_alloca("list.item", llvm_element)
    produced = visitor.create_entry_block_alloca(
        "list.produced", ir.IntType(1)
    )
    generator = iteration.kind is IterationKind.GENERATOR
    frame: ir.Value | None = None
    resume: ir.Value | None = None
    view: ir.Value | None = None
    length: ir.Value | None = None
    if generator:
        frame = builder.extract_value(source, 0)
        resume_type = ir.FunctionType(
            ir.IntType(32),
            [
                ir.IntType(8).as_pointer(),
                frame.type,
                llvm_element.as_pointer(),
                ir.IntType(1).as_pointer(),
            ],
        )
        resume = builder.bitcast(
            builder.extract_value(source, 1), resume_type.as_pointer()
        )
    else:
        adapter = require_semantic_metadata(
            iteration.sequence_access,
            node=node,
            metadata="sequence adapter",
            context="list materialization",
        )
        view = adapt_sequence(
            visitor, iteration.iterable_node, source, adapter
        )
        length = builder.extract_value(view, 1)
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
    if generator:
        assert frame is not None and resume is not None
        status = builder.call(
            resume,
            [
                exceptions.context_value(),
                frame,
                yielded,
                produced,
            ],
        )
        exceptions.propagate_status(node, status)
        builder.cbranch(builder.load(produced), body, done)
    else:
        assert length is not None
        builder.cbranch(builder.icmp_signed("<", index, length), body, done)
    builder.position_at_end(body)
    visitor._guard_runtime_condition(
        node,
        builder.icmp_signed("<", index, limit),
        code="ARX-RUNTIME-LIST-001",
        message="input exceeds max_items",
        block_name="list.bound",
        exception_role="ValueError",
    )
    if view is not None:
        value = read_sequence(
            visitor, node, view, index, iteration.element_type
        )
        builder.store(value, yielded)
    append = visitor.require_runtime_symbol("list", "irx_list_append")
    status = builder.call(
        append, [output, builder.bitcast(yielded, ir.IntType(8).as_pointer())]
    )
    lists.check_list_status(node, status)
    builder.store(builder.add(index, ir.Constant(integer, 1)), index_slot)
    builder.branch(condition)
    builder.position_at_end(done)
    visitor.cleanup_stack.remove(rollback)
    visitor._emit_temporary_cleanups(depth)
    visitor._register_owned_list_temporary(node, output)
    visitor.result_stack.append(builder.load(output))
