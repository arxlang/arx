"""
title: Bounded single-pass materialization through explicit emission services.
"""

from collections.abc import Callable

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import IterationKind, ResolvedMaterialization
from irx.analysis.types import is_unsigned_type
from irx.builder.diagnostics import require_semantic_metadata
from irx.builder.lowering.sequences import SequenceEmission
from irx.builder.services.cleanup import CleanupService
from irx.builder.services.conversions import NumericEmission
from irx.builder.services.exceptions import RuntimeGuardService
from irx.builder.services.representations import TypeLowering, resolved_type
from irx.builder.services.values import ValueEmission
from irx.builder.state import CleanupAction
from irx.typecheck import typechecked


@private
@typechecked
class ListConstruction:
    """
    title: >-
      Only the list-storage and rollback operations materialization requires.
    attributes:
      representation:
        type: Callable[[], ir.Type]
      empty:
        type: Callable[[astx.AST], ir.Constant]
      track:
        type: Callable[[ir.Value], CleanupAction]
      check_status:
        type: Callable[[astx.AST, ir.Value], None]
    """

    representation: Callable[[], ir.Type]
    empty: Callable[[astx.AST], ir.Constant]
    track: Callable[[ir.Value], CleanupAction]
    check_status: Callable[[astx.AST, ir.Value], None]

    def __init__(
        self,
        representation: Callable[[], ir.Type],
        empty: Callable[[astx.AST], ir.Constant],
        track: Callable[[ir.Value], CleanupAction],
        check_status: Callable[[astx.AST, ir.Value], None],
    ) -> None:
        """
        title: Inject typed list operations without a list visitor or driver.
        parameters:
          representation:
            type: Callable[[], ir.Type]
          empty:
            type: Callable[[astx.AST], ir.Constant]
          track:
            type: Callable[[ir.Value], CleanupAction]
          check_status:
            type: Callable[[astx.AST, ir.Value], None]
        """
        self.representation = representation
        self.empty = empty
        self.track = track
        self.check_status = check_status


@private
@typechecked
class MaterializationEmission:
    """
    title: >-
      Consume a resolved numeric materialization without compiler inheritance.
    summary: >-
      Limit checks precede publication. The shared cleanup service protects
      source lifetime and partially constructed results across allocation,
      limit evaluation, and generator resumption failures.
    attributes:
      values:
        type: ValueEmission
      types:
        type: TypeLowering
      numeric:
        type: NumericEmission
      symbol:
        type: Callable[[str, str], ir.Function]
      cleanup:
        type: CleanupService
      control:
        type: RuntimeGuardService
      sequences:
        type: SequenceEmission
      lists:
        type: ListConstruction
      context_value:
        type: Callable[[], ir.Value]
      propagate_status:
        type: Callable[[astx.AST, ir.Value], None]
    """

    values: ValueEmission
    types: TypeLowering
    numeric: NumericEmission
    symbol: Callable[[str, str], ir.Function]
    cleanup: CleanupService
    control: RuntimeGuardService
    sequences: SequenceEmission
    lists: ListConstruction
    context_value: Callable[[], ir.Value]
    propagate_status: Callable[[astx.AST, ir.Value], None]

    def __init__(
        self,
        values: ValueEmission,
        types: TypeLowering,
        numeric: NumericEmission,
        symbol: Callable[[str, str], ir.Function],
        cleanup: CleanupService,
        control: RuntimeGuardService,
        sequences: SequenceEmission,
        lists: ListConstruction,
        context_value: Callable[[], ir.Value],
        propagate_status: Callable[[astx.AST, ir.Value], None],
    ) -> None:
        """
        title: >-
          Bind value flow, storage, iteration, and checked completion services.
        parameters:
          values:
            type: ValueEmission
          types:
            type: TypeLowering
          numeric:
            type: NumericEmission
          symbol:
            type: Callable[[str, str], ir.Function]
          cleanup:
            type: CleanupService
          control:
            type: RuntimeGuardService
          sequences:
            type: SequenceEmission
          lists:
            type: ListConstruction
          context_value:
            type: Callable[[], ir.Value]
          propagate_status:
            type: Callable[[astx.AST, ir.Value], None]
        """
        self.values = values
        self.types = types
        self.numeric = numeric
        self.symbol = symbol
        self.cleanup = cleanup
        self.control = control
        self.sequences = sequences
        self.lists = lists
        self.context_value = context_value
        self.propagate_status = propagate_status

    def lower(
        self,
        node: astx.FunctionCall,
        plan: ResolvedMaterialization,
    ) -> None:
        """
        title: >-
          Consume once, detect excess before append, and never publish a
          prefix.
        summary: >-
          Sized sources use a borrowed snapshot. Unsized sources probe once
          beyond the bound; the counter cannot overflow, even at INT64_MAX.
          Cleanup is registered before limit evaluation, resumption, or
          allocation can fail.
        parameters:
          node:
            type: astx.FunctionCall
          plan:
            type: ResolvedMaterialization
        """
        builder = self.values.builder()
        integer = ir.IntType(64)
        zero = ir.Constant(integer, 0)
        iteration = plan.iteration
        depth = len(self.cleanup.state.cleanup_stack)
        source = self.values.evaluate(iteration.iterable_node)
        llvm_element = require_semantic_metadata(
            self.types.llvm_type(iteration.element_type),
            node=node,
            metadata="concrete element storage",
            context="materialization",
        )
        yielded = self.values.allocate("list.item", llvm_element)
        produced = self.values.allocate("list.produced", ir.IntType(1))
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
            view = self.sequences.adapt(
                iteration.iterable_node, source, adapter
            )
            length = builder.extract_value(view, 1)
        limit = length
        if plan.max_items is not None:
            raw_limit = self.values.evaluate(plan.max_items)
            limit = self.numeric.cast_value_to_type(
                raw_limit,
                integer,
                unsigned=is_unsigned_type(resolved_type(plan.max_items)),
            )
        limit = require_semantic_metadata(
            limit,
            node=node,
            metadata="materialization bound",
            context="list materialization",
        )
        self.control.guard(
            node,
            builder.icmp_signed(">=", limit, zero),
            code="ARX-RUNTIME-LIST-001",
            message="max_items must be nonnegative",
            block_name="list.bound",
            exception_role="ValueError",
        )
        if length is not None:
            self.control.guard(
                node,
                builder.icmp_signed("<=", length, limit),
                code="ARX-RUNTIME-LIST-001",
                message="input exceeds max_items",
                block_name="list.bound",
                exception_role="ValueError",
            )
        output = self.values.allocate(
            "list.materialized", self.lists.representation()
        )
        builder.store(self.lists.empty(node), output)
        rollback = self.lists.track(output)
        index_slot = self.values.allocate("list.index", integer)
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
                    self.context_value(),
                    frame,
                    yielded,
                    produced,
                ],
            )
            self.propagate_status(node, status)
            builder.cbranch(builder.load(produced), body, done)
        else:
            assert length is not None
            builder.cbranch(
                builder.icmp_signed("<", index, length), body, done
            )
        builder.position_at_end(body)
        self.control.guard(
            node,
            builder.icmp_signed("<", index, limit),
            code="ARX-RUNTIME-LIST-001",
            message="input exceeds max_items",
            block_name="list.bound",
            exception_role="ValueError",
        )
        if view is not None:
            value = self.sequences.read(
                node, view, index, iteration.element_type
            )
            builder.store(value, yielded)
        item_pointer = yielded
        if plan.checked_bytes:
            value = builder.load(yielded)
            unsigned = is_unsigned_type(iteration.element_type)
            # Widen before checking so i8's upper bound is not truncated to -1.
            wide = self.numeric.cast_value_to_type(
                value, integer, unsigned=unsigned
            )
            valid = builder.icmp_unsigned(
                "<=", wide, ir.Constant(integer, 255)
            )
            self.control.guard(
                node,
                valid,
                code="ARX-RUNTIME-BYTES-001",
                message="bytes items must be integers in 0..255",
                block_name="bytes.item",
                exception_role="ValueError",
            )
            item_pointer = self.values.allocate("bytes.item", ir.IntType(8))
            builder.store(builder.trunc(wide, ir.IntType(8)), item_pointer)
        append = self.symbol("list", "irx_list_append")
        status = builder.call(
            append,
            [
                output,
                builder.bitcast(item_pointer, ir.IntType(8).as_pointer()),
            ],
        )
        self.lists.check_status(node, status)
        builder.store(builder.add(index, ir.Constant(integer, 1)), index_slot)
        builder.branch(condition)
        builder.position_at_end(done)
        self.cleanup.state.cleanup_stack.remove(rollback)
        self.cleanup.emit_temporary(depth)
        self.cleanup.register_owned_list_temporary(node, output)
        self.values.publish(builder.load(output))
