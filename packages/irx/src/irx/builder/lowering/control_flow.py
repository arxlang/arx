# mypy: disable-error-code=no-redef

"""
title: Control-flow lowering implementations for llvmliteir.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Literal, cast

import astx

from llvmlite import ir
from plum import dispatch
from public import private

from irx.analysis.resolved_nodes import (
    IterationKind,
    MethodDispatchKind,
    ResolvedContextManager,
    ResolvedIteration,
    ResolvedMethodCall,
    SemanticInfo,
)
from irx.analysis.types import (
    is_boolean_type,
    is_float_type,
    is_string_type,
    is_unsigned_type,
)
from irx.builder.diagnostics import (
    lowered_value_type_name,
    raise_lowering_error,
    raise_lowering_internal_error,
    require_lowered_value,
    require_semantic_metadata,
    resolved_ast_type_name,
)
from irx.builder.lowering.contracts import ControlFlowServices
from irx.builder.runtime import safe_pop
from irx.builder.services.representations import (
    resolved_type as resolved_ast_type,
)
from irx.builder.services.representations import (
    semantic_assignment_key,
    semantic_symbol_key,
)
from irx.builder.state import (
    CleanupAction,
    CleanupEmitter,
    CleanupKind,
    LoopTargets,
)
from irx.builder.types import is_fp_type, is_int_type
from irx.builder.vector import emit_add
from irx.diagnostics import DiagnosticCodes
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class ControlFlowLowering:
    """
    title: Lower resolved control flow through registered LLVM handlers.
    visibility: internal
    attributes:
      services:
        type: ControlFlowServices
    """

    services: ControlFlowServices

    def __init__(self, services: ControlFlowServices) -> None:
        """
        title: Bind explicit family-owned emission dependencies.
        parameters:
          services:
            type: ControlFlowServices
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
            f"no control_flow handler for {type(node).__name__}", node=node
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
                "llvm.control_flow.Block",
                "irx.control_flow",
                "lowering",
                astx.Block,
                self.visit,
                source="irx.builder.lowering.control_flow.ControlFlowLowering.visit",
            ),
            contribute_node(
                "llvm.control_flow.AssertStmt",
                "irx.control_flow",
                "lowering",
                astx.AssertStmt,
                self.visit,
                source="irx.builder.lowering.control_flow.ControlFlowLowering.visit",
            ),
            contribute_node(
                "llvm.control_flow.IfStmt",
                "irx.control_flow",
                "lowering",
                astx.IfStmt,
                self.visit,
                source="irx.builder.lowering.control_flow.ControlFlowLowering.visit",
            ),
            contribute_node(
                "llvm.control_flow.WhileStmt",
                "irx.control_flow",
                "lowering",
                astx.WhileStmt,
                self.visit,
                source="irx.builder.lowering.control_flow.ControlFlowLowering.visit",
            ),
            contribute_node(
                "llvm.control_flow.ForCountLoopStmt",
                "irx.control_flow",
                "lowering",
                astx.ForCountLoopStmt,
                self.visit,
                source="irx.builder.lowering.control_flow.ControlFlowLowering.visit",
            ),
            contribute_node(
                "llvm.control_flow.ForRangeLoopStmt",
                "irx.control_flow",
                "lowering",
                astx.ForRangeLoopStmt,
                self.visit,
                source="irx.builder.lowering.control_flow.ControlFlowLowering.visit",
            ),
            contribute_node(
                "llvm.control_flow.ForInLoopStmt",
                "irx.control_flow",
                "lowering",
                astx.ForInLoopStmt,
                self.visit,
                source="irx.builder.lowering.control_flow.ControlFlowLowering.visit",
            ),
            contribute_node(
                "llvm.control_flow.WithStmt",
                "irx.control_flow",
                "lowering",
                astx.WithStmt,
                self.visit,
                source="irx.builder.lowering.control_flow.ControlFlowLowering.visit",
            ),
            contribute_node(
                "llvm.control_flow.BreakStmt",
                "irx.control_flow",
                "lowering",
                astx.BreakStmt,
                self.visit,
                source="irx.builder.lowering.control_flow.ControlFlowLowering.visit",
            ),
            contribute_node(
                "llvm.control_flow.ContinueStmt",
                "irx.control_flow",
                "lowering",
                astx.ContinueStmt,
                self.visit,
                source="irx.builder.lowering.control_flow.ControlFlowLowering.visit",
            ),
        )

    def _resolved_context_manager(
        self,
        node: astx.WithStmt,
    ) -> ResolvedContextManager:
        """
        title: Return one node's resolved context-manager sidecar.
        parameters:
          node:
            type: astx.WithStmt
        returns:
          type: ResolvedContextManager
        """
        semantic = getattr(node, "semantic", None)
        resolution = getattr(semantic, "resolved_context_manager", None)
        return require_semantic_metadata(
            cast(ResolvedContextManager | None, resolution),
            node=node,
            metadata="resolved_context_manager",
            context="with statement lowering",
        )

    def _lower_boolean_condition(
        self,
        value: ir.Value | None,
        *,
        node: astx.AST,
        context: str,
    ) -> ir.Value:
        """
        title: Require one lowered control-flow condition to be Boolean.
        parameters:
          value:
            type: ir.Value | None
          node:
            type: astx.AST
          context:
            type: str
        returns:
          type: ir.Value
        """
        if value is None:
            raise_lowering_internal_error(
                f"{context} condition did not lower to a value",
                node=node,
                notes=(f"semantic type: {resolved_ast_type_name(node)}",),
            )
        if not is_int_type(value.type) or value.type.width != 1:
            raise_lowering_internal_error(
                f"{context} condition must lower to LLVM i1, got "
                f"{lowered_value_type_name(value)}",
                node=node,
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                notes=(f"semantic type: {resolved_ast_type_name(node)}",),
            )
        return value

    def _append_basic_blocks(
        self,
        prefix: str,
        *roles: str,
    ) -> tuple[ir.Block, ...]:
        """
        title: Append one canonical sequence of basic blocks.
        parameters:
          prefix:
            type: str
          roles:
            type: str
            variadic: positional
        returns:
          type: tuple[ir.Block, Ellipsis]
        """
        function = self.services.llvm.ir_builder.function
        return tuple(
            function.append_basic_block(f"{prefix}.{role}") for role in roles
        )

    def _assert_source_name(self, node: astx.AST) -> str:
        """
        title: Return one stable source label for assertion reporting.
        parameters:
          node:
            type: astx.AST
        returns:
          type: str
        """
        current_display_name = (
            self.services.module_state.current_module_display_name
        )
        if current_display_name:
            return current_display_name

        current: astx.AST | None = node
        while current is not None:
            if isinstance(current, astx.Module):
                display_names = self.services.module_state.module_display_names
                display_name = display_names.get(id(current))
                if display_name:
                    return display_name
                module_name = cast(str, getattr(current, "name", ""))
                return module_name or "<module>"
            parent = getattr(current, "parent", None)
            current = parent if isinstance(parent, astx.AST) else None
        return "<module>"

    def _lower_assert_message_pointer(self, node: astx.AssertStmt) -> ir.Value:
        """
        title: Lower one assertion message to one runtime C string pointer.
        parameters:
          node:
            type: astx.AssertStmt
        returns:
          type: ir.Value
        """
        if node.message is None:
            return self.services.strings.constant(
                "assertion failed",
                name_hint="assert_message",
            )

        self.services.visit_child(node.message)
        message_value = require_lowered_value(
            safe_pop(self.services.function_state.result_stack),
            node=node.message,
            context="assert message",
        )
        message_source_type = resolved_ast_type(node.message)
        message_type = message_value.type

        if (
            isinstance(message_type, ir.PointerType)
            and message_type.pointee == self.services.llvm.INT8_TYPE
        ):
            return message_value

        if is_int_type(message_type):
            int_arg, int_fmt = self.services.strings.integer_format(
                message_value,
                unsigned=is_unsigned_type(message_source_type)
                or is_boolean_type(message_source_type),
            )
            int_fmt_gv = self.services.strings.format_global(int_fmt)
            return self.services.strings.format_heap(
                node, int_fmt_gv, [int_arg]
            )

        if isinstance(
            message_type, (ir.HalfType, ir.FloatType, ir.DoubleType)
        ):
            if isinstance(message_type, (ir.HalfType, ir.FloatType)):
                float_arg = self.services.llvm.ir_builder.fpext(
                    message_value,
                    self.services.llvm.DOUBLE_TYPE,
                    "assert_msg_to_double",
                )
            else:
                float_arg = message_value
            float_fmt_gv = self.services.strings.format_global("%.6f")
            return self.services.strings.format_heap(
                node, float_fmt_gv, [float_arg]
            )

        raise_lowering_error(
            "unsupported AssertStmt message lowering for type "
            f"{lowered_value_type_name(message_value)}",
            code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
            node=node.message,
        )

    def _discard_child_results(self, node: astx.AST) -> None:
        """
        title: Visit one statement child without leaking stack values.
        parameters:
          node:
            type: astx.AST
        """
        stack_size_before = len(self.services.function_state.result_stack)
        self.services.visit_child(node)
        del self.services.function_state.result_stack[stack_size_before:]

    @contextmanager
    def _cleanup_scope(
        self,
        cleanup: CleanupEmitter,
    ) -> Iterator[None]:
        """
        title: Push and pop one active cleanup action.
        parameters:
          cleanup:
            type: CleanupEmitter
        returns:
          type: Iterator[None]
        """
        self.services.exit_state.cleanup_stack.append(
            CleanupAction(cleanup, kind=CleanupKind.FINALLY)
        )
        try:
            yield
        finally:
            self.services.exit_state.cleanup_stack.pop()

    @contextmanager
    def _loop_scope(
        self,
        *,
        break_target: ir.Block,
        continue_target: ir.Block,
    ) -> Iterator[None]:
        """
        title: Push and pop one active loop target pair.
        parameters:
          break_target:
            type: ir.Block
          continue_target:
            type: ir.Block
        returns:
          type: Iterator[None]
        """
        self.services.exit_state.loop_stack.append(
            LoopTargets(
                break_target=break_target,
                continue_target=continue_target,
                cleanup_depth=len(self.services.exit_state.cleanup_stack),
            )
        )
        try:
            yield
        finally:
            self.services.exit_state.loop_stack.pop()

    @contextmanager
    def _temporary_named_value(
        self,
        key: str,
        value: ir.Value,
        *,
        is_constant: bool = False,
    ) -> Iterator[None]:
        """
        title: Bind one temporary symbol slot during lowering.
        parameters:
          key:
            type: str
          value:
            type: ir.Value
          is_constant:
            type: bool
        returns:
          type: Iterator[None]
        """
        had_previous = key in self.services.function_state.named_values
        previous_value = self.services.function_state.named_values.get(key)
        had_const = key in self.services.function_state.const_vars

        self.services.function_state.named_values[key] = value
        if is_constant:
            self.services.function_state.const_vars.add(key)

        try:
            yield
        finally:
            if had_previous:
                self.services.function_state.named_values[key] = previous_value
            else:
                self.services.function_state.named_values.pop(key, None)

            if had_const:
                self.services.function_state.const_vars.add(key)
            else:
                self.services.function_state.const_vars.discard(key)

    @contextmanager
    def _context_target_binding(
        self,
        node: astx.WithStmt,
        resolution: ResolvedContextManager,
        enter_value: ir.Value | None,
    ) -> Iterator[None]:
        """
        title: Bind a with-statement target for the body duration.
        parameters:
          node:
            type: astx.WithStmt
          resolution:
            type: ResolvedContextManager
          enter_value:
            type: ir.Value | None
        returns:
          type: Iterator[None]
        """
        target = node.target
        target_symbol = resolution.target_symbol
        if target is None or target_symbol is None:
            yield
            return

        if enter_value is None:
            raise_lowering_internal_error(
                "with target requires __enter__ to lower to a value",
                node=target,
            )

        target_type = target_symbol.type_
        llvm_target_type = self._require_llvm_type(
            target_type,
            node=target,
            context="with target",
        )
        target_addr = self.services.create_entry_block_alloca(
            target_symbol.name,
            llvm_target_type,
        )
        target_value = self.services.numeric.cast_scalar(
            enter_value,
            source_type=resolution.enter.call.result_type,
            target_type=target_type,
        )
        self.services.llvm.ir_builder.store(target_value, target_addr)
        target_key = semantic_symbol_key(target)

        with self._temporary_named_value(
            target_key,
            target_addr,
            is_constant=not target_symbol.is_mutable,
        ):
            yield

    def _lower_context_method_call(
        self,
        *,
        node: astx.WithStmt,
        method_resolution: ResolvedMethodCall,
        manager_value: ir.Value,
        manager_type: astx.DataType | None,
    ) -> ir.Value | None:
        """
        title: Lower one resolved context-manager method call.
        parameters:
          node:
            type: astx.WithStmt
          method_resolution:
            type: ResolvedMethodCall
          manager_value:
            type: ir.Value
          manager_type:
            type: astx.DataType | None
        returns:
          type: ir.Value | None
        """
        receiver_parameter_type = (
            method_resolution.function.signature.parameters[0].type_
            if method_resolution.function.signature.parameters
            else None
        )
        lowered_manager = self.services.numeric.cast_scalar(
            manager_value,
            source_type=manager_type,
            target_type=receiver_parameter_type,
        )
        llvm_defaults = self.services.lower_bound_call_arguments(
            method_resolution.call,
            receiver_value=lowered_manager,
        )
        lowered_args = [lowered_manager, *llvm_defaults]
        callee: ir.Value
        if method_resolution.dispatch_kind is MethodDispatchKind.INDIRECT:
            callee = self.services.indirect_method_callee(
                node=node,
                method_resolution=method_resolution,
                receiver_value=manager_value,
            )
        else:
            callee = self.services.declare_semantic_function(
                method_resolution.function
            )
        self.services.apply_calling_convention(
            method_resolution.function.signature
        )
        return self.services.exceptions.emit_resolved_call(
            node, callee, method_resolution.function.signature, lowered_args
        )

    def _require_llvm_type(
        self,
        type_: astx.DataType | None,
        *,
        node: astx.AST,
        context: str,
    ) -> ir.Type:
        """
        title: Require one concrete LLVM type for lowering.
        parameters:
          type_:
            type: astx.DataType | None
          node:
            type: astx.AST
          context:
            type: str
        returns:
          type: ir.Type
        """
        llvm_type = self.services.types.llvm_type(type_)
        if llvm_type is None:
            raise_lowering_error(
                f"cannot lower {context} with type "
                f"{resolved_ast_type_name(node)}",
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
            )
        return llvm_type

    def _lower_typed_value(
        self,
        node: astx.AST,
        *,
        context: str,
        target_type: astx.DataType | None,
    ) -> ir.Value:
        """
        title: Lower one value and cast it to one target semantic type.
        parameters:
          node:
            type: astx.AST
          context:
            type: str
          target_type:
            type: astx.DataType | None
        returns:
          type: ir.Value
        """
        self.services.visit_child(node)
        lowered = require_lowered_value(
            safe_pop(self.services.function_state.result_stack),
            node=node,
            context=context,
        )
        return self.services.numeric.cast_scalar(
            lowered,
            source_type=resolved_ast_type(node),
            target_type=target_type,
        )

    def _lower_list_for_in_loop(
        self,
        node: astx.ForInLoopStmt,
        iteration: ResolvedIteration,
    ) -> None:
        """
        title: Lower one for-in loop over a list iterable.
        parameters:
          node:
            type: astx.ForInLoopStmt
          iteration:
            type: ResolvedIteration
        """
        target_name = getattr(node.target, "name", "item")
        target_type = (
            iteration.target_symbol.type_
            if iteration.target_symbol is not None
            else iteration.element_type
        )
        llvm_target_type = self._require_llvm_type(
            target_type,
            node=node.target,
            context="for-in loop target",
        )
        target_addr = self.services.create_entry_block_alloca(
            target_name,
            llvm_target_type,
        )
        index_addr = self.services.create_entry_block_alloca(
            f"{target_name}_iter_index",
            self.services.llvm.INT64_TYPE,
        )
        self.services.llvm.ir_builder.store(
            ir.Constant(self.services.llvm.INT64_TYPE, 0),
            index_addr,
        )

        sequence = iteration.sequence_access
        if iteration.kind is IterationKind.SEQUENCE:
            sequence = require_semantic_metadata(
                sequence,
                node=node,
                metadata="sequence adapter",
                context="sequence iteration",
            )
        if sequence is not None:
            self.services.visit_child(node.iterable)
            source = require_lowered_value(
                safe_pop(self.services.function_state.result_stack),
                node=node.iterable,
                context="sequence iteration",
            )
            list_ptr = self.services.sequences.adapt(
                node.iterable, source, sequence
            )
            length = self.services.llvm.ir_builder.extract_value(list_ptr, 1)
        else:
            list_ptr, length = (
                self.services.list_pointer_and_length_for_iteration(
                    node.iterable
                )
            )

        cond_bb, body_bb, advance_bb, exit_bb = self._append_basic_blocks(
            "for.in",
            "cond",
            "body",
            "advance",
            "exit",
        )
        self.services.llvm.ir_builder.branch(cond_bb)

        self.services.llvm.ir_builder.position_at_start(cond_bb)
        current_index = self.services.llvm.ir_builder.load(
            index_addr,
            name="for_in_index",
        )
        loop_cond = self.services.llvm.ir_builder.icmp_signed(
            "<",
            current_index,
            length,
            name="for_in_has_item",
        )
        self.services.llvm.ir_builder.cbranch(loop_cond, body_bb, exit_bb)

        target_key = semantic_symbol_key(node.target)
        is_constant = False
        if isinstance(node.target, astx.InlineVariableDeclaration):
            is_constant = (
                node.target.mutability == astx.MutabilityKind.constant
            )
        else:
            is_constant = True

        with self._loop_scope(
            break_target=exit_bb,
            continue_target=advance_bb,
        ):
            iteration_depth = len(self.services.exit_state.cleanup_stack)
            self.services.llvm.ir_builder.position_at_start(body_bb)
            item_value = (
                self.services.sequences.read(
                    node.iterable,
                    list_ptr,
                    current_index,
                    iteration.element_type,
                )
                if sequence is not None
                else self.services.load_list_element_at_index(
                    base=node.iterable,
                    list_ptr=list_ptr,
                    index=current_index,
                )
            )
            item_value = self.services.numeric.cast_scalar(
                item_value,
                source_type=iteration.element_type,
                target_type=target_type,
            )
            if is_string_type(iteration.element_type):
                item_value = self.services.strings.copy(
                    node.target, item_value
                )
            self.services.llvm.ir_builder.store(item_value, target_addr)
            if is_string_type(iteration.element_type):
                self.services.register_owned_string_cleanup(
                    node.target,
                    target_addr,
                )
            with self._temporary_named_value(
                target_key,
                target_addr,
                is_constant=is_constant,
            ):
                self._discard_child_results(node.body)
            if not self.services.llvm.ir_builder.block.is_terminated:
                self.services.cleanup.emit_active(iteration_depth)
                self.services.llvm.ir_builder.branch(advance_bb)
            del self.services.exit_state.cleanup_stack[iteration_depth:]

        self.services.llvm.ir_builder.position_at_start(advance_bb)
        next_index = self.services.llvm.ir_builder.add(
            self.services.llvm.ir_builder.load(
                index_addr, name="for_in_step_index"
            ),
            ir.Constant(self.services.llvm.INT64_TYPE, 1),
            name="for_in_next_index",
        )
        self.services.llvm.ir_builder.store(next_index, index_addr)
        self.services.llvm.ir_builder.branch(cond_bb)

        self.services.llvm.ir_builder.position_at_start(exit_bb)

    def _zero_value(self, llvm_type: ir.Type) -> ir.Constant:
        """
        title: Return the zero constant for one numeric LLVM type.
        parameters:
          llvm_type:
            type: ir.Type
        returns:
          type: ir.Constant
        """
        if is_fp_type(llvm_type):
            return ir.Constant(llvm_type, 0.0)
        return ir.Constant(llvm_type, 0)

    def _constant_numeric_direction(
        self,
        value: ir.Value,
    ) -> Literal["positive", "negative", "zero"] | None:
        """
        title: Return one compile-time sign classification when available.
        parameters:
          value:
            type: ir.Value
        returns:
          type: Literal[positive, negative, zero] | None
        """
        if not isinstance(value, ir.Constant):
            return None
        constant = value.constant
        if not isinstance(constant, (int, float)):
            return None
        if constant > 0:
            return "positive"
        if constant < 0:
            return "negative"
        return "zero"

    def _range_step_flags(
        self,
        step_value: ir.Value,
        *,
        unsigned: bool,
    ) -> tuple[ir.Value, ir.Value]:
        """
        title: Compute one runtime step-direction pair for for-range loops.
        parameters:
          step_value:
            type: ir.Value
          unsigned:
            type: bool
        returns:
          type: tuple[ir.Value, ir.Value]
        """
        zero = self._zero_value(step_value.type)
        if is_fp_type(step_value.type):
            return (
                self.services.llvm.ir_builder.fcmp_ordered(
                    ">",
                    step_value,
                    zero,
                    "for.range.step.positive",
                ),
                self.services.llvm.ir_builder.fcmp_ordered(
                    "<",
                    step_value,
                    zero,
                    "for.range.step.negative",
                ),
            )
        if unsigned:
            return (
                self.services.llvm.ir_builder.icmp_unsigned(
                    "!=",
                    step_value,
                    zero,
                    "for.range.step.nonzero",
                ),
                ir.Constant(self.services.llvm.BOOLEAN_TYPE, 0),
            )
        return (
            self.services.llvm.ir_builder.icmp_signed(
                ">",
                step_value,
                zero,
                "for.range.step.positive",
            ),
            self.services.llvm.ir_builder.icmp_signed(
                "<",
                step_value,
                zero,
                "for.range.step.negative",
            ),
        )

    def _for_count_update_stores_loop_variable(
        self,
        update: astx.AST,
        *,
        loop_symbol_key: str,
    ) -> bool:
        """
        title: >-
          Return whether one for-count update already writes the loop slot.
        parameters:
          update:
            type: astx.AST
          loop_symbol_key:
            type: str
        returns:
          type: bool
        """
        if isinstance(update, astx.AugAssign):
            semantic = require_semantic_metadata(
                cast(SemanticInfo | None, getattr(update, "semantic", None)),
                node=update,
                metadata="semantic",
                context="compound count-loop update",
            )
            plan = require_semantic_metadata(
                semantic.resolved_aug_assignment,
                node=update,
                metadata="resolved_aug_assignment",
                context="compound count-loop update",
            )
            return plan.target.symbol_id == loop_symbol_key

        if isinstance(update, astx.UnaryOp) and update.op_code in {"++", "--"}:
            operand = update.operand
            if isinstance(operand, astx.Identifier):
                return semantic_symbol_key(operand) == loop_symbol_key
            return False

        if isinstance(update, astx.VariableAssignment):
            return semantic_assignment_key(update) == loop_symbol_key

        if (
            isinstance(update, astx.BinaryOp)
            and update.op_code == "="
            and isinstance(update.lhs, astx.Identifier)
        ):
            return semantic_assignment_key(update) == loop_symbol_key

        return False

    def _for_range_condition(
        self,
        current_value: ir.Value,
        end_value: ir.Value,
        *,
        unsigned: bool,
        step_direction: Literal["positive", "negative", "zero"] | None,
        step_positive: ir.Value | None = None,
        step_negative: ir.Value | None = None,
    ) -> ir.Value:
        """
        title: Lower one canonical for-range loop condition.
        parameters:
          current_value:
            type: ir.Value
          end_value:
            type: ir.Value
          unsigned:
            type: bool
          step_direction:
            type: Literal[positive, negative, zero] | None
          step_positive:
            type: ir.Value | None
          step_negative:
            type: ir.Value | None
        returns:
          type: ir.Value
        """
        builder = self.services.llvm.ir_builder
        before_end = self.services.numeric.emit_numeric_compare(
            "<",
            current_value,
            end_value,
            unsigned=unsigned,
            name="for.range.before_end",
        )

        if step_direction == "positive":
            return before_end
        if step_direction == "zero":
            return ir.Constant(self.services.llvm.BOOLEAN_TYPE, 0)

        if unsigned:
            if step_positive is None:
                raise_lowering_internal_error(
                    "for-range loop missing nonzero-step flag",
                )
            return builder.and_(step_positive, before_end, "for.range.cond")

        after_end = self.services.numeric.emit_numeric_compare(
            ">",
            current_value,
            end_value,
            unsigned=unsigned,
            name="for.range.after_end",
        )

        if step_direction == "negative":
            return after_end

        if step_positive is None or step_negative is None:
            raise_lowering_internal_error(
                "for-range loop missing runtime step-direction flags",
            )

        positive_path = builder.and_(
            step_positive,
            before_end,
            "for.range.cond.positive",
        )
        negative_path = builder.and_(
            step_negative,
            after_end,
            "for.range.cond.negative",
        )
        return builder.or_(positive_path, negative_path, "for.range.cond")

    @dispatch
    def visit(self, block: astx.Block) -> None:
        """
        title: Visit Block nodes.
        parameters:
          block:
            type: astx.Block
        """
        self.lower_statement_block(block)

    def lower_statement_block(
        self, block: astx.Block, *, preserve_scope: bool = False
    ) -> None:
        """
        title: Lower statements with optional ownership continuation into else.
        parameters:
          block:
            type: astx.Block
          preserve_scope:
            type: bool
        """
        cleanup_depth = len(self.services.exit_state.cleanup_stack)
        try:
            for node in block.nodes:
                if isinstance(node, (astx.StructDefStmt, astx.ClassDefStmt)):
                    self.services.visit_child(node)

            result = None
            for node in block.nodes:
                if self.services.llvm.ir_builder.block.terminator is not None:
                    break

                stack_size_before = len(
                    self.services.function_state.result_stack
                )
                statement_cleanup_depth = len(
                    self.services.exit_state.cleanup_stack
                )
                self.services.visit_child(node)
                if (
                    len(self.services.function_state.result_stack)
                    > stack_size_before
                ):
                    result = self.services.function_state.result_stack.pop()

                if self.services.llvm.ir_builder.block.terminator is not None:
                    result = None
                    break
                self.services.cleanup.emit_temporary(statement_cleanup_depth)

            if (
                not preserve_scope
                and self.services.llvm.ir_builder.block.terminator is None
            ):
                self.services.cleanup.emit_active(cleanup_depth)

            if result is not None:
                self.services.function_state.result_stack.append(result)
        finally:
            if not preserve_scope:
                del self.services.exit_state.cleanup_stack[cleanup_depth:]

    @dispatch
    def visit(self, node: astx.AssertStmt) -> None:
        """
        title: Visit AssertStmt nodes.
        parameters:
          node:
            type: astx.AssertStmt
        """
        condition_cleanup_depth = len(self.services.exit_state.cleanup_stack)
        self.services.visit_child(node.condition)
        condition_value = self._lower_boolean_condition(
            safe_pop(self.services.function_state.result_stack),
            node=node.condition,
            context="assert",
        )
        self.services.cleanup.emit_temporary(condition_cleanup_depth)

        pass_bb, fail_bb = self._append_basic_blocks("assert", "pass", "fail")
        self.services.llvm.ir_builder.cbranch(
            condition_value, pass_bb, fail_bb
        )

        self.services.llvm.ir_builder.position_at_start(fail_bb)
        message_ptr = self._lower_assert_message_pointer(node)
        self.services.raise_runtime_exception(
            node,
            "AssertionError",
            message_ptr,
            code="ARX-RUNTIME-ASSERTION-001",
        )

        self.services.llvm.ir_builder.position_at_start(pass_bb)

    @dispatch
    def visit(self, node: astx.IfStmt) -> None:
        """
        title: Visit IfStmt nodes.
        parameters:
          node:
            type: astx.IfStmt
        """
        condition_cleanup_depth = len(self.services.exit_state.cleanup_stack)
        self.services.visit_child(node.condition)
        cond_v = self._lower_boolean_condition(
            safe_pop(self.services.function_state.result_stack),
            node=node.condition,
            context="if",
        )
        self.services.cleanup.emit_temporary(condition_cleanup_depth)

        then_bb = self.services.llvm.ir_builder.function.append_basic_block(
            "bb_if_then"
        )
        else_bb = self.services.llvm.ir_builder.function.append_basic_block(
            "bb_if_else"
        )
        merge_bb = self.services.llvm.ir_builder.function.append_basic_block(
            "bb_if_end"
        )
        self.services.llvm.ir_builder.cbranch(cond_v, then_bb, else_bb)

        self.services.llvm.ir_builder.position_at_start(then_bb)
        then_stack_size = len(self.services.function_state.result_stack)
        self.services.visit_child(node.then)
        then_terminated = (
            self.services.llvm.ir_builder.block.terminator is not None
        )
        then_v = None
        if len(self.services.function_state.result_stack) > then_stack_size:
            then_v = self.services.function_state.result_stack.pop()
        if not then_terminated:
            self.services.llvm.ir_builder.branch(merge_bb)
            then_bb = self.services.llvm.ir_builder.block

        self.services.llvm.ir_builder.position_at_start(else_bb)
        else_stack_size = len(self.services.function_state.result_stack)
        if node.else_ is not None:
            self.services.visit_child(node.else_)
        else_terminated = (
            self.services.llvm.ir_builder.block.terminator is not None
        )
        else_v = None
        if len(self.services.function_state.result_stack) > else_stack_size:
            else_v = self.services.function_state.result_stack.pop()
        if not else_terminated:
            self.services.llvm.ir_builder.branch(merge_bb)
            else_bb = self.services.llvm.ir_builder.block

        then_reaches_merge = not then_terminated
        else_reaches_merge = not else_terminated
        if not then_reaches_merge and not else_reaches_merge:
            self.services.llvm.ir_builder.position_at_start(merge_bb)
            self.services.llvm.ir_builder.unreachable()
            return

        self.services.llvm.ir_builder.position_at_start(merge_bb)
        if (
            then_reaches_merge
            and else_reaches_merge
            and then_v is not None
            and else_v is not None
            and then_v.type == else_v.type
        ):
            phi = self.services.llvm.ir_builder.phi(then_v.type, "iftmp")
            phi.add_incoming(then_v, then_bb)
            phi.add_incoming(else_v, else_bb)
            self.services.function_state.result_stack.append(phi)
            return

        if (
            then_reaches_merge
            and not else_reaches_merge
            and then_v is not None
        ):
            self.services.function_state.result_stack.append(then_v)
            return

        if (
            else_reaches_merge
            and not then_reaches_merge
            and else_v is not None
        ):
            self.services.function_state.result_stack.append(else_v)

    @dispatch
    def visit(self, expr: astx.WhileStmt) -> None:
        """
        title: Visit WhileStmt nodes.
        parameters:
          expr:
            type: astx.WhileStmt
        """
        cond_bb, body_bb, exit_bb = self._append_basic_blocks(
            "while",
            "cond",
            "body",
            "exit",
        )
        self.services.llvm.ir_builder.branch(cond_bb)

        self.services.llvm.ir_builder.position_at_start(cond_bb)
        condition_cleanup_depth = len(self.services.exit_state.cleanup_stack)
        self.services.visit_child(expr.condition)
        cond_val = self._lower_boolean_condition(
            safe_pop(self.services.function_state.result_stack),
            node=expr.condition,
            context="while",
        )
        self.services.cleanup.emit_temporary(condition_cleanup_depth)
        self.services.llvm.ir_builder.cbranch(cond_val, body_bb, exit_bb)

        with self._loop_scope(
            break_target=exit_bb,
            continue_target=cond_bb,
        ):
            self.services.llvm.ir_builder.position_at_start(body_bb)
            self._discard_child_results(expr.body)
            if not self.services.llvm.ir_builder.block.is_terminated:
                self.services.llvm.ir_builder.branch(cond_bb)

        self.services.llvm.ir_builder.position_at_start(exit_bb)

    @dispatch
    def visit(self, node: astx.ForCountLoopStmt) -> None:
        """
        title: Visit ForCountLoopStmt nodes.
        parameters:
          node:
            type: astx.ForCountLoopStmt
        """
        initializer_key = semantic_symbol_key(node.initializer)
        had_previous = (
            initializer_key in self.services.function_state.named_values
        )
        previous_value = self.services.function_state.named_values.get(
            initializer_key
        )
        had_const = initializer_key in self.services.function_state.const_vars

        initializer_stack_size = len(self.services.function_state.result_stack)
        self.services.visit_child(node.initializer)
        del self.services.function_state.result_stack[initializer_stack_size:]

        var_addr = self.services.function_state.named_values.get(
            initializer_key
        )
        if var_addr is None:
            raise_lowering_internal_error(
                "for-count loop initializer did not create storage",
                node=node.initializer,
            )

        cond_bb, body_bb, update_bb, exit_bb = self._append_basic_blocks(
            "for.count",
            "cond",
            "body",
            "update",
            "exit",
        )
        self.services.llvm.ir_builder.branch(cond_bb)

        try:
            self.services.llvm.ir_builder.position_at_start(cond_bb)
            condition_cleanup_depth = len(
                self.services.exit_state.cleanup_stack
            )
            self.services.visit_child(node.condition)
            cond_val = self._lower_boolean_condition(
                safe_pop(self.services.function_state.result_stack),
                node=node.condition,
                context="for-count loop",
            )
            self.services.cleanup.emit_temporary(condition_cleanup_depth)
            self.services.llvm.ir_builder.cbranch(cond_val, body_bb, exit_bb)

            with self._loop_scope(
                break_target=exit_bb,
                continue_target=update_bb,
            ):
                self.services.llvm.ir_builder.position_at_start(body_bb)
                self._discard_child_results(node.body)
                if not self.services.llvm.ir_builder.block.is_terminated:
                    self.services.llvm.ir_builder.branch(update_bb)

            self.services.llvm.ir_builder.position_at_start(update_bb)
            update_cleanup_depth = len(self.services.exit_state.cleanup_stack)
            update_val = self._lower_typed_value(
                node.update,
                context="for-count loop update",
                target_type=node.initializer.type_,
            )
            if not self._for_count_update_stores_loop_variable(
                node.update,
                loop_symbol_key=initializer_key,
            ):
                self.services.llvm.ir_builder.store(update_val, var_addr)
            self.services.cleanup.emit_temporary(update_cleanup_depth)
            self.services.llvm.ir_builder.branch(cond_bb)

            self.services.llvm.ir_builder.position_at_start(exit_bb)
        finally:
            if had_previous:
                self.services.function_state.named_values[initializer_key] = (
                    previous_value
                )
            else:
                self.services.function_state.named_values.pop(
                    initializer_key, None
                )

            if had_const:
                self.services.function_state.const_vars.add(initializer_key)
            else:
                self.services.function_state.const_vars.discard(
                    initializer_key
                )

    @dispatch
    def visit(self, node: astx.ForRangeLoopStmt) -> None:
        """
        title: Visit ForRangeLoopStmt nodes.
        parameters:
          node:
            type: astx.ForRangeLoopStmt
        """
        loop_type = node.variable.type_
        llvm_loop_type = self._require_llvm_type(
            loop_type,
            node=node.variable,
            context="for-range loop variable",
        )
        var_addr = self.services.create_entry_block_alloca(
            node.variable.name,
            llvm_loop_type,
        )

        start_cleanup_depth = len(self.services.exit_state.cleanup_stack)
        start_val = self._lower_typed_value(
            node.start,
            context="for-range start expression",
            target_type=loop_type,
        )
        self.services.llvm.ir_builder.store(start_val, var_addr)
        self.services.cleanup.emit_temporary(start_cleanup_depth)

        end_cleanup_depth = len(self.services.exit_state.cleanup_stack)
        end_val = self._lower_typed_value(
            node.end,
            context="for-range end expression",
            target_type=loop_type,
        )
        self.services.cleanup.emit_temporary(end_cleanup_depth)

        if not isinstance(node.step, astx.LiteralNone):
            step_cleanup_depth = len(self.services.exit_state.cleanup_stack)
            step_val = self._lower_typed_value(
                node.step,
                context="for-range step expression",
                target_type=loop_type,
            )
            self.services.cleanup.emit_temporary(step_cleanup_depth)
        else:
            step_val = ir.Constant(
                llvm_loop_type,
                1.0 if is_float_type(loop_type) else 1,
            )

        unsigned_loop = bool(
            loop_type is not None and is_unsigned_type(loop_type)
        )
        step_direction = self._constant_numeric_direction(step_val)
        step_positive = None
        step_negative = None
        if step_direction is None:
            step_positive, step_negative = self._range_step_flags(
                step_val,
                unsigned=unsigned_loop,
            )

        cond_bb, body_bb, step_bb, exit_bb = self._append_basic_blocks(
            "for.range",
            "cond",
            "body",
            "step",
            "exit",
        )
        self.services.llvm.ir_builder.branch(cond_bb)

        variable_key = semantic_symbol_key(node.variable)
        self.services.llvm.ir_builder.position_at_start(cond_bb)
        current_value = self.services.llvm.ir_builder.load(
            var_addr, node.variable.name
        )
        loop_cond = self._for_range_condition(
            current_value,
            end_val,
            unsigned=unsigned_loop,
            step_direction=step_direction,
            step_positive=step_positive,
            step_negative=step_negative,
        )
        self.services.llvm.ir_builder.cbranch(loop_cond, body_bb, exit_bb)

        with self._loop_scope(
            break_target=exit_bb,
            continue_target=step_bb,
        ):
            self.services.llvm.ir_builder.position_at_start(body_bb)
            with self._temporary_named_value(
                variable_key,
                var_addr,
                is_constant=(
                    node.variable.mutability == astx.MutabilityKind.constant
                ),
            ):
                self._discard_child_results(node.body)
            if not self.services.llvm.ir_builder.block.is_terminated:
                self.services.llvm.ir_builder.branch(step_bb)

        self.services.llvm.ir_builder.position_at_start(step_bb)
        current_value = self.services.llvm.ir_builder.load(
            var_addr, node.variable.name
        )
        next_value = (
            emit_add(
                self.services.llvm.ir_builder,
                current_value,
                step_val,
                "nextvar",
            )
            if is_float_type(loop_type)
            else self.services.numeric.resolved_integer_operation(
                node, current_value, step_val, "+"
            )
        )
        self.services.llvm.ir_builder.store(next_value, var_addr)
        self.services.llvm.ir_builder.branch(cond_bb)

        self.services.llvm.ir_builder.position_at_start(exit_bb)

    @dispatch
    def visit(self, node: astx.ForInLoopStmt) -> None:
        """
        title: Visit ForInLoopStmt nodes.
        parameters:
          node:
            type: astx.ForInLoopStmt
        """
        iteration = self.services.resolved_iteration(node)
        if iteration is None:
            raise_lowering_error(
                "for-in loop is missing resolved iteration metadata",
                node=node,
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
            )
        if iteration.kind in {IterationKind.LIST, IterationKind.SEQUENCE}:
            self._lower_list_for_in_loop(node, iteration)
            return
        if iteration.kind is IterationKind.GENERATOR:
            self.services.lower_generator_for_in_loop(node, iteration)
            return
        raise_lowering_error(
            f"for-in lowering does not yet support {iteration.kind.value} "
            "iterables",
            node=node.iterable,
            code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
        )

    @dispatch
    def visit(self, node: astx.WithStmt) -> None:
        """
        title: Visit WithStmt nodes.
        parameters:
          node:
            type: astx.WithStmt
        """
        resolution = self._resolved_context_manager(node)
        self.services.visit_child(node.manager)
        manager_value = require_lowered_value(
            safe_pop(self.services.function_state.result_stack),
            node=node.manager,
            context="with manager",
        )
        enter_value = self._lower_context_method_call(
            node=node,
            method_resolution=resolution.enter,
            manager_value=manager_value,
            manager_type=resolution.manager_type,
        )

        def cleanup() -> None:
            """
            title: Emit this with statement's exit call.
            """
            token = self.services.exceptions.exception_call(
                "finally_enter", [self.services.exceptions.context_value()]
            )

            def discard() -> None:
                """
                title: Discard the replaced completion on explicit exit.
                """
                self.services.exceptions.exception_call(
                    "finally_leave",
                    [
                        self.services.exceptions.context_value(),
                        token,
                        ir.Constant(ir.IntType(32), 0),
                    ],
                )

            saved = self.services.exit_state.cleanup_stack
            self.services.exit_state.cleanup_stack = [
                *saved,
                CleanupAction(discard, kind=CleanupKind.HANDLER),
            ]
            self._lower_context_method_call(
                node=node,
                method_resolution=resolution.exit,
                manager_value=manager_value,
                manager_type=resolution.manager_type,
            )
            self.services.exit_state.cleanup_stack = saved
            self.services.exceptions.exception_call(
                "finally_leave",
                [
                    self.services.exceptions.context_value(),
                    token,
                    ir.Constant(ir.IntType(32), 1),
                ],
            )

        with self._cleanup_scope(cleanup):
            with self._context_target_binding(node, resolution, enter_value):
                self._discard_child_results(node.body)
            if not self.services.llvm.ir_builder.block.is_terminated:
                self.services.cleanup.emit_active(
                    len(self.services.exit_state.cleanup_stack) - 1
                )

    @dispatch
    def visit(self, node: astx.BreakStmt) -> None:
        """
        title: Visit BreakStmt nodes.
        parameters:
          node:
            type: astx.BreakStmt
        """
        if not self.services.exit_state.loop_stack:
            raise_lowering_error(
                "break statement used outside an active loop",
                node=node,
                code=DiagnosticCodes.LOWERING_INVALID_CONTROL_FLOW,
                hint=(
                    "use `break` only inside while, for-count, or "
                    "for-range loop bodies"
                ),
            )
        self.services.exceptions.abandon_loop_returns(
            self.services.exit_state.loop_stack[-1]
        )
        self.services.cleanup.emit_active(
            self.services.exit_state.loop_stack[-1].cleanup_depth
        )
        if not self.services.llvm.ir_builder.block.is_terminated:
            self.services.llvm.ir_builder.branch(
                self.services.exit_state.loop_stack[-1].break_target
            )

    @dispatch
    def visit(self, node: astx.ContinueStmt) -> None:
        """
        title: Visit ContinueStmt nodes.
        parameters:
          node:
            type: astx.ContinueStmt
        """
        if not self.services.exit_state.loop_stack:
            raise_lowering_error(
                "continue statement used outside an active loop",
                node=node,
                code=DiagnosticCodes.LOWERING_INVALID_CONTROL_FLOW,
                hint=(
                    "use `continue` only inside while, for-count, or "
                    "for-range loop bodies"
                ),
            )
        self.services.exceptions.abandon_loop_returns(
            self.services.exit_state.loop_stack[-1]
        )
        self.services.cleanup.emit_active(
            self.services.exit_state.loop_stack[-1].cleanup_depth
        )
        if not self.services.llvm.ir_builder.block.is_terminated:
            self.services.llvm.ir_builder.branch(
                self.services.exit_state.loop_stack[-1].continue_target
            )
