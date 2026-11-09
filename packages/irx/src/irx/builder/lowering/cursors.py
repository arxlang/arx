"""
title: Checked, closed cursors shared by loops and bounded materialization.
"""

from typing import TYPE_CHECKING, cast

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import CursorProtocol, ResolvedIteration
from irx.builder.core import VisitorCore, semantic_symbol_key
from irx.builder.diagnostics import (
    raise_lowering_error,
    require_lowered_value,
    require_semantic_metadata,
)
from irx.builder.lowering.ranges import range_item
from irx.builder.lowering.sequences import adapt_sequence, read_sequence
from irx.builder.runtime import safe_pop
from irx.builder.state import CleanupAction
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.lowering.control_flow import ControlFlowVisitorMixin
    from irx.builder.lowering.exceptions import ExceptionVisitorMixin


@private
@typechecked
def generator_header_type() -> ir.LiteralStructType:
    """
    title: Share the generator factory, resume, and cursor prefix layout.
    summary: >-
      State is i32, followed by exhausted and acquired Boolean slots. Scalar
      captures follow this prefix; no owning captures or suspended resources
      are supported. A closed frame remains allocated until its lexical owner
      releases it, permitting checked rejection rather than use after free.
    returns:
      type: ir.LiteralStructType
    """
    return ir.LiteralStructType([ir.IntType(32), ir.IntType(1), ir.IntType(1)])


@private
@typechecked
class LoweredCursor:
    """
    title: One acquired position with separate value, exhaustion, and failure.
    summary: >-
      All output reads follow successful advancement. Cleanup is registered
      after acquisition and before any consumer operation can fail. Range
      positions and indexed views are independent; one-shot frames reject a
      second acquisition, including nested or previously failed consumption.
    attributes:
      visitor:
        type: VisitorCore
      plan:
        type: ResolvedIteration
      protocol:
        type: CursorProtocol
      source:
        type: ir.Value
      item:
        type: ir.Value
      position:
        type: ir.Value
      active:
        type: ir.Value
      length:
        type: ir.Value | None
      view:
        type: ir.Value | None
      header:
        type: ir.Value | None
      frame:
        type: ir.Value | None
      resume:
        type: ir.Value | None
      produced:
        type: ir.Value | None
    """

    def __init__(self, visitor: VisitorCore, plan: ResolvedIteration) -> None:
        """
        title: Evaluate once and acquire only a semantically selected protocol.
        parameters:
          visitor:
            type: VisitorCore
          plan:
            type: ResolvedIteration
        """
        self.visitor: VisitorCore = visitor
        self.plan: ResolvedIteration = plan
        self.protocol: CursorProtocol = require_semantic_metadata(
            plan.cursor_protocol,
            node=plan.iterable_node,
            metadata="cursor_protocol",
            context="cursor acquisition",
        )
        visitor.visit_child(plan.iterable_node)
        self.source: ir.Value = require_lowered_value(
            safe_pop(visitor.result_stack),
            node=plan.iterable_node,
            context="cursor input",
        )
        builder = visitor._llvm.ir_builder
        element = require_semantic_metadata(
            visitor._llvm_type_for_ast_type(plan.element_type),
            node=plan.iterable_node,
            metadata="concrete element storage",
            context="cursor acquisition",
        )
        self.item: ir.Value = visitor.create_entry_block_alloca(
            "cursor.item", element
        )
        self.position: ir.Value = visitor.create_entry_block_alloca(
            "cursor.position", ir.IntType(64)
        )
        self.active: ir.Value = visitor.create_entry_block_alloca(
            "cursor.active", ir.IntType(1)
        )
        builder.store(ir.Constant(ir.IntType(64), 0), self.position)
        builder.store(ir.Constant(ir.IntType(1), 1), self.active)
        self.length: ir.Value | None = None
        self.view: ir.Value | None = None
        self.header: ir.Value | None = None
        self.frame: ir.Value | None = None
        self.resume: ir.Value | None = None
        self.produced: ir.Value | None = None
        if self.protocol is CursorProtocol.RANGE:
            self.length = builder.extract_value(self.source, 2)
        elif self.protocol is CursorProtocol.INDEXED:
            adapter = require_semantic_metadata(
                plan.sequence_access,
                node=plan.iterable_node,
                metadata="sequence_access",
                context="indexed cursor acquisition",
            )
            self.view = adapt_sequence(
                visitor, plan.iterable_node, self.source, adapter
            )
            self.length = builder.extract_value(self.view, 1)
        elif self.protocol is CursorProtocol.GENERATOR:
            self.frame = builder.extract_value(self.source, 0)
            self.header = builder.bitcast(
                self.frame, generator_header_type().as_pointer()
            )
            acquired = self.header_slot(2)
            visitor._guard_runtime_condition(
                plan.iterable_node,
                builder.not_(builder.load(acquired)),
                code="ARX-RUNTIME-ITERATOR-001",
                message="one-shot iterator has already been acquired",
                block_name="cursor.acquire",
                exception_role="RuntimeError",
            )
            builder.store(ir.Constant(ir.IntType(1), 1), acquired)
            self.produced = visitor.create_entry_block_alloca(
                "cursor.produced", ir.IntType(1)
            )
            signature = ir.FunctionType(
                ir.IntType(32),
                [
                    ir.IntType(8).as_pointer(),
                    self.frame.type,
                    element.as_pointer(),
                    ir.IntType(1).as_pointer(),
                ],
            )
            self.resume = builder.bitcast(
                builder.extract_value(self.source, 1), signature.as_pointer()
            )
        else:
            raise_lowering_error(
                "unsupported cursor protocol",
                node=plan.iterable_node,
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
            )
        visitor.cleanup_stack.append(CleanupAction(self.close, fallible=False))

    def header_slot(self, index: int) -> ir.Value:
        """
        title: Address one shared generator lifecycle flag.
        parameters:
          index:
            type: int
        returns:
          type: ir.Value
        """
        assert self.header is not None
        return self.visitor._llvm.ir_builder.gep(
            self.header,
            [
                ir.Constant(ir.IntType(32), 0),
                ir.Constant(ir.IntType(32), index),
            ],
            inbounds=True,
        )

    def advance(self) -> ir.Value:
        """
        title: Produce one item or exhaustion, checking failure before output.
        returns:
          type: ir.Value
        """
        visitor = self.visitor
        builder = visitor._llvm.ir_builder
        if self.protocol is CursorProtocol.GENERATOR:
            assert self.frame is not None and self.resume is not None
            assert self.produced is not None
            exceptions: ExceptionVisitorMixin = cast(
                "ExceptionVisitorMixin", visitor
            )
            status = builder.call(
                self.resume,
                [
                    exceptions.context_value(),
                    self.frame,
                    self.item,
                    self.produced,
                ],
            )
            exceptions.propagate_status(self.plan.iterable_node, status)
            return builder.load(self.produced)
        assert self.length is not None
        index = builder.load(self.position)
        has_item = builder.icmp_unsigned("<", index, self.length)
        with builder.if_then(has_item):
            value = (
                range_item(visitor, self.source, index)
                if self.protocol is CursorProtocol.RANGE
                else read_sequence(
                    visitor,
                    self.plan.iterable_node,
                    self.require_view(),
                    index,
                    self.plan.element_type,
                )
            )
            builder.store(value, self.item)
            builder.store(
                builder.add(index, ir.Constant(ir.IntType(64), 1)),
                self.position,
            )
        return has_item

    def require_view(self) -> ir.Value:
        """
        title: Require indexed storage selected during acquisition.
        returns:
          type: ir.Value
        """
        assert self.view is not None
        return self.view

    def close(self) -> None:
        """
        title: Idempotently finalize a cursor without freeing borrowed storage.
        """
        builder = self.visitor._llvm.ir_builder
        with builder.if_then(builder.load(self.active)):
            builder.store(ir.Constant(ir.IntType(1), 0), self.active)
            if self.protocol is CursorProtocol.GENERATOR:
                builder.store(
                    ir.Constant(ir.IntType(1), 1), self.header_slot(1)
                )


@private
@typechecked
def lower_cursor_loop(
    visitor: VisitorCore, node: astx.ForInLoopStmt, plan: ResolvedIteration
) -> None:
    """
    title: Keep cursor finalization outside continue and on every exiting edge.
    parameters:
      visitor:
        type: VisitorCore
      node:
        type: astx.ForInLoopStmt
      plan:
        type: ResolvedIteration
    """
    control: ControlFlowVisitorMixin = cast("ControlFlowVisitorMixin", visitor)
    depth = len(visitor.cleanup_stack)
    cursor = LoweredCursor(visitor, plan)
    target = require_semantic_metadata(
        plan.target_symbol,
        node=node,
        metadata="target_symbol",
        context="cursor loop",
    )
    type_ = require_semantic_metadata(
        visitor._llvm_type_for_ast_type(target.type_),
        node=node,
        metadata="target storage",
        context="cursor loop",
    )
    storage = visitor.create_entry_block_alloca(target.name, type_)
    condition, body, done = control._append_basic_blocks(
        "cursor", "next", "body", "done"
    )
    builder = visitor._llvm.ir_builder
    builder.branch(condition)
    builder.position_at_end(condition)
    builder.cbranch(cursor.advance(), body, done)
    with control._loop_scope(break_target=done, continue_target=condition):
        builder.position_at_end(body)
        item = visitor._cast_ast_value(
            builder.load(cursor.item),
            source_type=plan.element_type,
            target_type=target.type_,
        )
        builder.store(item, storage)
        key = semantic_symbol_key(node.target, target.name)
        with control._temporary_named_value(
            key, storage, is_constant=not target.is_mutable
        ):
            control._discard_child_results(node.body)
        if not builder.block.is_terminated:
            builder.branch(condition)
    builder.position_at_end(done)
    visitor._emit_active_cleanups(depth)
    del visitor.cleanup_stack[depth:]
