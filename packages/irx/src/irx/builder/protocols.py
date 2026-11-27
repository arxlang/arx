"""
title: Typing protocols for llvmliteir visitors.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ParamSpec,
    Protocol,
    cast,
)

import astx

from llvmlite import binding as llvm
from llvmlite import ir

from irx.analysis.resolved_nodes import (
    FunctionSignature,
    ResolvedExceptionType,
)
from irx.base.visitors.protocols import BaseVisitorProtocol
from irx.builder.state import (
    CleanupAction,
    ExceptionTarget,
    LoopTargets,
    NamedValueMap,
    PendingReturn,
    ResultStackValue,
)
from irx.builder.types import VariablesLLVM
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.runtime.registry import RuntimeFeatureState


DispatchParameters = ParamSpec("DispatchParameters")


class DispatchRegistrar(Protocol):
    """
    title: Typed view of Plum's dynamically attached registration method.
    """

    @abstractmethod
    def dispatch(self, method: Callable[DispatchParameters, None]) -> Any:
        """
        title: Register one typed overload in the open dispatch family.
        summary: Plum exposes a dynamic multimethod, not this single signature.
        parameters:
          method: Method.
        returns: 'Result of this operation: register one typed overload in
          the open dispatch family.'
        """
        del method
        raise NotImplementedError


@typechecked
class ExceptionLoweringTypingBase:
    """
    title: Explicit execution-context and status-ABI lowering services.
    attributes:
      runtime_exception_types: Types of runtime exception.
      exception_context: Exception context.
      exception_result_slot: Exception result slot.
      exception_targets: Exception targets.
      pending_returns: Pending returns.
      llvm_function_signatures: LLVM function signatures.
    """

    runtime_exception_types: dict[str, ResolvedExceptionType]
    exception_context: ir.Value | None
    exception_result_slot: ir.Value | None
    exception_targets: list[ExceptionTarget]
    pending_returns: list[PendingReturn]
    llvm_function_signatures: dict[str, FunctionSignature]

    def exception_call(self, operation: str, args: list[ir.Value]) -> ir.Value:
        """
        title: Call an opaque runtime exception operation.
        parameters:
          operation: Operation to resolve or execute.
          args: Arguments supplied to the operation.
        returns: 'Result of this operation: call an opaque runtime exception
          operation.'
        """
        del operation, args
        raise NotImplementedError

    def context_value(self) -> ir.Value:
        """
        title: Require the current frame execution context.
        returns: 'Result of this operation: require the current frame execution
          context.'
        """
        raise NotImplementedError

    def emit_resolved_call(
        self,
        node: astx.AST,
        callee: ir.Value,
        signature: FunctionSignature,
        args: list[ir.Value],
    ) -> ir.Value | None:
        """
        title: Emit a resolved call and consume success-only output storage.
        parameters:
          node: Syntax node to process.
          callee: Callee.
          signature: Resolved callable signature.
          args: Arguments supplied to the operation.
        returns: 'Result of this operation: emit a resolved call and consume
          success-only output storage.'
        """
        del node, callee, signature, args
        raise NotImplementedError

    def propagate_status(self, node: astx.AST, status: ir.Value) -> None:
        """
        title: Route failed call status through lexical cleanup regions.
        parameters:
          node: Syntax node to process.
          status: Native operation status.
        """
        del node, status
        raise NotImplementedError

    def emit_exception_transfer(self, node: astx.AST | None) -> None:
        """
        title: Exit the current region with the context pending exception.
        parameters:
          node: Syntax node to process.
        """
        del node
        raise NotImplementedError

    def emit_success_return(self, value: ir.Value | None) -> None:
        """
        title: Publish successful output after all cleanups.
        parameters:
          value: Value to process.
        """
        del value
        raise NotImplementedError

    def abandon_pending_returns(
        self,
        completions: tuple[PendingReturn, ...] | None = None,
        *,
        preserved_depth: int | None = None,
    ) -> None:
        """
        title: Release values whose pending return was replaced.
        parameters:
          completions: Completions.
          preserved_depth: Preserved depth.
        """
        del completions
        del preserved_depth
        raise NotImplementedError

    def raise_runtime_exception(
        self, node: astx.AST, role: str, message: ir.Value, *, code: str
    ) -> None:
        """
        title: Materialize a builtin nominal exception from native failure.
        parameters:
          node: Syntax node to process.
          role: Role.
          message: Diagnostic or output message.
          code: Source code or diagnostic identifier.
        """
        del node, role, message, code
        raise NotImplementedError

    def fatal_status(self, node: astx.AST, status: ir.Value) -> None:
        """
        title: Fail without allocation on bookkeeping allocation failure.
        parameters:
          node: Syntax node to process.
          status: Native operation status.
        """
        del node, status
        raise NotImplementedError

    def checked_native_call(
        self, node: astx.AST, function: ir.Function, args: list[ir.Value]
    ) -> ir.Value:
        """
        title: Invoke a checked native facade with success-only output
          slots.
        parameters:
          node: Syntax node to process.
          function: Function to process.
          args: Arguments supplied to the operation.
        returns: 'Result of this operation: invoke a checked native
          facade with success-only output slots.'
        """
        del node, function, args
        raise NotImplementedError

    def check_arrow_status(
        self,
        node: astx.AST,
        status: ir.Value,
        operation: str,
        message: ir.Value | None = None,
        *,
        feature: str = "dataframe",
    ) -> None:
        """
        title: Convert a native Arrow failure category into an exception.
        parameters:
          node: Syntax node to process.
          status: Native operation status.
          operation: Operation to resolve or execute.
          message: Diagnostic or output message.
          feature: Feature.
        """
        del node, status, operation, message, feature
        raise NotImplementedError

    def track_native_handle(
        self, node: astx.AST, feature: str, destroy: str, value: ir.Value
    ) -> CleanupAction:
        """
        title: Register rollback for a partially assembled native handle.
        parameters:
          node: Syntax node to process.
          feature: Feature.
          destroy: Destroy.
          value: Value to process.
        returns: 'Result of this operation: register rollback for a partially
          assembled native handle.'
        """
        del node, feature, destroy, value
        raise NotImplementedError

    def release_native_handle(self, action: CleanupAction) -> None:
        """
        title: Release a native temporary after successful ownership transfer.
        parameters:
          action: Action.
        """
        del action
        raise NotImplementedError

    def _guard_runtime_condition(
        self,
        node: astx.AST,
        condition: ir.Value,
        *,
        code: str,
        message: str,
        block_name: str,
        exception_role: str = "RuntimeError",
    ) -> None:
        """
        title: Raise the requested builtin if a native condition fails.
        parameters:
          node: Syntax node to process.
          condition: Condition controlling the operation.
          code: Source code or diagnostic identifier.
          message: Diagnostic or output message.
          block_name: Name of block.
          exception_role: Exception role.
        """
        del node, condition, code, message, block_name, exception_role
        raise NotImplementedError


class VisitorProtocol(BaseVisitorProtocol, Protocol):
    """
    title: Stable interface used by visitor mixins and runtime features.
    attributes:
      runtime_exception_types: Types of runtime exception.
      exception_context: Exception context.
      exception_result_slot: Exception result slot.
      exception_targets: Exception targets.
      pending_returns: Pending returns.
      llvm_function_signatures: LLVM function signatures.
      _llvm: LLVM.
      named_values: Named values.
      const_vars: Const vars.
      function_protos: Function protos.
      llvm_functions_by_symbol_id: Identifier for LLVM functions by symbol.
      result_stack: Stack of lowered expression results.
      _buffer_view_global_counter: Buffer view global counter.
      loop_stack: Loop stack.
      cleanup_stack: Cleanup stack.
      class_construction_stack: Class construction stack.
      emitting_failure_cleanup: Whether to use emitting failure cleanup.
      struct_types: Types of struct.
      llvm_structs_by_qualified_name: Name of LLVM structs by qualified.
      runtime_features: Runtime features.
      entry_function_symbol_id: Identifier for entry function symbol.
      _fast_math_enabled: Whether to use fast math enabled.
      _current_function_return_type: Type of current function return.
      _current_function_signature: Current function signature.
      _current_generator_frame_ptr: Current generator frame ptr.
      _current_generator_frame_slots: Current generator frame slots.
      _current_generator_out_ptr: Current generator out ptr.
      _current_generator_next_state: Current generator next state.
      target: Destination of the operation.
      target_machine: Target machine.
    """

    runtime_exception_types: dict[str, ResolvedExceptionType]
    exception_context: ir.Value | None
    exception_result_slot: ir.Value | None
    exception_targets: list[ExceptionTarget]
    pending_returns: list[PendingReturn]
    llvm_function_signatures: dict[str, FunctionSignature]
    _llvm: VariablesLLVM
    named_values: NamedValueMap
    const_vars: set[str]
    function_protos: dict[str, astx.FunctionPrototype]
    llvm_functions_by_symbol_id: dict[str, ir.Function]
    result_stack: list[ResultStackValue]
    _buffer_view_global_counter: int
    loop_stack: list[LoopTargets]
    cleanup_stack: list[CleanupAction]
    class_construction_stack: list[ir.Value]
    emitting_failure_cleanup: bool
    struct_types: dict[str, ir.Type]
    llvm_structs_by_qualified_name: dict[str, ir.IdentifiedStructType]
    runtime_features: RuntimeFeatureState
    entry_function_symbol_id: str | None
    _fast_math_enabled: bool
    _current_function_return_type: astx.DataType | None
    _current_function_signature: FunctionSignature | None
    _current_generator_frame_ptr: ir.Value | None
    _current_generator_frame_slots: dict[str, int]
    _current_generator_out_ptr: ir.Value | None
    _current_generator_next_state: int | None
    target: llvm.TargetRef
    target_machine: llvm.TargetMachine

    @abstractmethod
    def declare_class(self, node: astx.ClassDefStmt) -> None:
        """
        title: Declare a resolved class layout before lowering method bodies.
        parameters:
          node: Syntax node to process.
        """
        del node
        raise NotImplementedError

    def get_function(self, _name: str) -> ir.Function | None:
        """
        title: Get function.
        parameters:
          _name: Name of .
        returns: Function.
        """
        ...

    def llvm_function_name_for_node(
        self,
        _node: astx.AST,
        _fallback: str,
    ) -> str:
        """
        title: Return the LLVM symbol name for a function node.
        parameters:
          _node: Syntax node to process.
          _fallback: Fallback.
        returns: The LLVM symbol name for a function node.
        """
        ...

    def create_entry_block_alloca(
        self, _var_name: str, _type_name: str | ir.Type
    ) -> Any:
        """
        title: Create entry block alloca.
        parameters:
          _var_name: Name of var.
          _type_name: Name of type.
        returns: Created entry block alloca.
        """
        ...

    def _i64_array_pointer(
        self,
        _values: tuple[int, ...],
        *,
        purpose: str,
        symbol_namespace: str = "buffer",
    ) -> ir.Value:
        """
        title: Lower one tuple of i64 values to a stable global pointer.
        parameters:
          _values: Values.
          purpose: Purpose.
          symbol_namespace: Symbol namespace.
        returns: Lowered one tuple of i64 values to a stable global pointer.
        """
        ...

    def _field_address(self, _node: astx.FieldAccess) -> ir.Value:
        """
        title: Lower one field access to an address.
        parameters:
          _node: Syntax node to process.
        returns: Lowered one field access to an address.
        """
        ...

    def _base_class_field_address(
        self,
        _node: astx.BaseFieldAccess,
    ) -> ir.Value:
        """
        title: Lower one base-qualified class field access to an address.
        parameters:
          _node: Syntax node to process.
        returns: Lowered one base-qualified class field access to an address.
        """
        ...

    def _static_class_field_address(
        self,
        _node: astx.StaticFieldAccess,
    ) -> ir.Value:
        """
        title: Lower one static class field access to a global address.
        parameters:
          _node: Syntax node to process.
        returns: Lowered one static class field access to a global address.
        """
        ...

    def _lvalue_address(
        self,
        _node: astx.AST,
    ) -> ir.Value:
        """
        title: Lower one mutable lvalue target to an address.
        parameters:
          _node: Syntax node to process.
        returns: Lowered one mutable lvalue target to an address.
        """
        ...

    def store_local_resource(
        self, _node: astx.AST, _address: ir.Value, _value: ir.Value
    ) -> ir.Value:
        """
        title: Commit an analyzed local store and return its value.
        parameters:
          _node: Syntax node to process.
          _address: Address of the destination binding.
          _value: Evaluated and converted value.
        returns: The value stored in the destination.
        """
        ...

    def _llvm_function_type_for_signature(
        self,
        _signature: FunctionSignature,
    ) -> ir.FunctionType:
        """
        title: Return one LLVM function type for semantic signature metadata.
        parameters:
          _signature: Signature.
        returns: One LLVM function type for semantic signature metadata.
        """
        ...

    def _declare_semantic_function(
        self,
        _function: Any,
    ) -> ir.Function:
        """
        title: Declare or reuse one semantic function.
        parameters:
          _function: Function.
        returns: 'Result of this operation: declare or reuse one semantic
          function.'
        """
        ...

    def _emit_active_cleanups(
        self,
        _start_depth: int = 0,
        _excluded_owner_symbol_ids: frozenset[str] = frozenset(),
    ) -> None:
        """
        title: Emit all active cleanup actions.
        parameters:
          _start_depth: Start depth.
          _excluded_owner_symbol_ids: Identifiers for excluded owner symbol.
        """
        ...

    def _register_owned_list_temporary(
        self,
        _node: astx.AST,
        _list_ptr: ir.Value,
    ) -> None:
        """
        title: Register cleanup for one non-transferred owned list temporary.
        parameters:
          _node: Syntax node to process.
          _list_ptr: List ptr.
        """
        ...

    def _register_owned_string_temporary(
        self,
        _node: astx.AST,
        _pointer: ir.Value,
    ) -> None:
        """
        title: Register cleanup for one non-transferred owned string.
        parameters:
          _node: Syntax node to process.
          _pointer: Pointer.
        """
        ...

    def _emit_temporary_cleanups(self, _start_depth: int) -> None:
        """
        title: Emit and remove temporary cleanups after one stack depth.
        parameters:
          _start_depth: Start depth.
        """
        ...

    def require_runtime_symbol(
        self, _feature_name: str, _symbol_name: str
    ) -> ir.Function:
        """
        title: Require runtime symbol.
        parameters:
          _feature_name: Name of feature.
          _symbol_name: Name of symbol.
        returns: 'Result of this operation: require runtime symbol.'
        """
        ...

    def activate_runtime_feature(self, _feature_name: str) -> None:
        """
        title: Activate runtime feature.
        parameters:
          _feature_name: Name of feature.
        """
        ...

    def set_fast_math(self, _enabled: bool) -> None:
        """
        title: Set fast math.
        parameters:
          _enabled: Whether to use enabled.
        """
        ...

    def _apply_fast_math(self, _inst: ir.Instruction) -> None:
        """
        title: Apply fast math.
        parameters:
          _inst: Inst.
        """
        ...

    def _emit_fma(
        self, _lhs: ir.Value, _rhs: ir.Value, _addend: ir.Value
    ) -> ir.Value:
        """
        title: Emit fma.
        parameters:
          _lhs: Left operand.
          _rhs: Right operand.
          _addend: Addend.
        returns: 'Result of this operation: emit fma.'
        """
        ...

    def _is_numeric_value(self, _value: ir.Value) -> bool:
        """
        title: Is numeric value.
        parameters:
          _value: Value.
        returns: 'Result of this operation: is numeric value.'
        """
        ...

    def _unify_numeric_operands(
        self,
        _lhs: ir.Value,
        _rhs: ir.Value,
        unsigned: bool = False,
    ) -> tuple[ir.Value, ir.Value]:
        """
        title: Unify numeric operands.
        parameters:
          _lhs: Left operand.
          _rhs: Right operand.
          unsigned: Whether to use unsigned semantics.
        returns: 'Result of this operation: unify numeric operands.'
        """
        _ = unsigned
        raise NotImplementedError

    def _try_set_binary_op(
        self,
        _lhs: ir.Value | None,
        _rhs: ir.Value | None,
        _op_code: str,
    ) -> bool:
        """
        title: Try set binary op.
        parameters:
          _lhs: Left operand.
          _rhs: Right operand.
          _op_code: Op code.
        returns: 'Result of this operation: try set binary op.'
        """
        ...

    def _handle_string_concatenation(
        self,
        _node: astx.AST,
        _lhs: ir.Value,
        _rhs: ir.Value,
    ) -> ir.Value:
        """
        title: Handle string concatenation.
        parameters:
          _node: Syntax node to process.
          _lhs: Left operand.
          _rhs: Right operand.
        returns: 'Result of this operation: handle string concatenation.'
        """
        ...

    def _copy_string_to_heap(
        self,
        _node: astx.AST,
        _pointer: ir.Value,
    ) -> ir.Value:
        """
        title: Copy one static string into owned heap storage.
        parameters:
          _node: Syntax node to process.
          _pointer: Pointer.
        returns: 'Result of this operation: copy one static string into owned
          heap storage.'
        """
        ...

    def _handle_string_comparison(
        self, _lhs: ir.Value, _rhs: ir.Value, _op: str
    ) -> ir.Value:
        """
        title: Handle string comparison.
        parameters:
          _lhs: Left operand.
          _rhs: Right operand.
          _op: Op.
        returns: 'Result of this operation: handle string comparison.'
        """
        ...

    def _common_list_element_type(
        self, _lhs_ty: ir.Type, _rhs_ty: ir.Type
    ) -> ir.Type:
        """
        title: Common list element type.
        parameters:
          _lhs_ty: Left operand ty.
          _rhs_ty: Right operand ty.
        returns: 'Result of this operation: common list element type.'
        """
        ...

    def _coerce_to(self, _value: ir.Value, _target_ty: ir.Type) -> ir.Value:
        """
        title: Coerce to.
        parameters:
          _value: Value.
          _target_ty: Target ty.
        returns: 'Result of this operation: coerce to.'
        """
        ...

    def _mark_set_value(self, _value: ir.Value) -> ir.Value:
        """
        title: Mark set value.
        parameters:
          _value: Value.
        returns: 'Result of this operation: mark set value.'
        """
        ...

    def _subscript_uses_unsigned_semantics(
        self, _node: astx.SubscriptExpr
    ) -> bool:
        """
        title: Subscript uses unsigned semantics.
        parameters:
          _node: Syntax node to process.
        returns: 'Result of this operation: subscript uses unsigned semantics.'
        """
        ...

    def _constant_subscript_key_matches(
        self, _entry_key: ir.Constant, _key_val: ir.Constant
    ) -> bool:
        """
        title: Constant subscript key matches.
        parameters:
          _entry_key: Entry key.
          _key_val: Key val.
        returns: 'Result of this operation: constant subscript key matches.'
        """
        ...

    def _emit_runtime_subscript_lookup(
        self,
        _dict_val: ir.Constant,
        _key_val: ir.Value,
        *,
        unsigned: bool,
    ) -> None:
        """
        title: Emit runtime subscript lookup.
        parameters:
          _dict_val: Dict val.
          _key_val: Key val.
          unsigned: Whether to use unsigned semantics.
        """
        _ = unsigned
        raise NotImplementedError

    def _normalize_int_for_printf(
        self,
        _value: ir.Value,
        *,
        unsigned: bool = False,
    ) -> tuple[ir.Value, str]:
        """
        title: Normalize int for printf.
        parameters:
          _value: Value.
          unsigned: Whether to use unsigned semantics.
        returns: Normalized int for printf.
        """
        _ = unsigned
        return cast(tuple[ir.Value, str], (None, ""))

    def _snprintf_heap(
        self,
        _node: astx.AST,
        _fmt_gv: ir.GlobalVariable,
        _args: list[ir.Value],
    ) -> ir.Value:
        """
        title: Snprintf heap.
        parameters:
          _node: Syntax node to process.
          _fmt_gv: Fmt gv.
          _args: Args.
        returns: 'Result of this operation: snprintf heap.'
        """
        ...

    def _get_or_create_format_global(self, _fmt: str) -> ir.GlobalVariable:
        """
        title: Get or create format global.
        parameters:
          _fmt: Fmt.
        returns: Or create format global.
        """
        ...


@typechecked
class VisitorMixinTypingBase(ExceptionLoweringTypingBase):
    """
    title: Type-checking-only annotation carrier for llvmliteir visitor mixins.
    attributes:
      runtime_exception_types: Types of runtime exception.
      exception_context: Exception context.
      exception_result_slot: Exception result slot.
      exception_targets: Exception targets.
      pending_returns: Pending returns.
      llvm_function_signatures: LLVM function signatures.
      _llvm: LLVM.
      named_values: Named values.
      const_vars: Const vars.
      function_protos: Function protos.
      llvm_functions_by_symbol_id: Identifier for LLVM functions by symbol.
      result_stack: Stack of lowered expression results.
      _buffer_view_global_counter: Buffer view global counter.
      loop_stack: Loop stack.
      cleanup_stack: Cleanup stack.
      class_construction_stack: Class construction stack.
      emitting_failure_cleanup: Whether to use emitting failure cleanup.
      struct_types: Types of struct.
      llvm_structs_by_qualified_name: Name of LLVM structs by qualified.
      runtime_features: Runtime features.
      entry_function_symbol_id: Identifier for entry function symbol.
      _fast_math_enabled: Whether to use fast math enabled.
      _current_function_return_type: Type of current function return.
      _current_function_signature: Current function signature.
      _current_generator_frame_ptr: Current generator frame ptr.
      _current_generator_frame_slots: Current generator frame slots.
      _current_generator_out_ptr: Current generator out ptr.
      _current_generator_next_state: Current generator next state.
      target: Destination of the operation.
      target_machine: Target machine.
    """

    runtime_exception_types: dict[str, ResolvedExceptionType]
    exception_context: ir.Value | None
    exception_result_slot: ir.Value | None
    exception_targets: list[ExceptionTarget]
    pending_returns: list[PendingReturn]
    llvm_function_signatures: dict[str, FunctionSignature]
    _llvm: VariablesLLVM
    named_values: NamedValueMap
    const_vars: set[str]
    function_protos: dict[str, astx.FunctionPrototype]
    llvm_functions_by_symbol_id: dict[str, ir.Function]
    result_stack: list[ResultStackValue]
    _buffer_view_global_counter: int
    loop_stack: list[LoopTargets]
    cleanup_stack: list[CleanupAction]
    class_construction_stack: list[ir.Value]
    emitting_failure_cleanup: bool
    struct_types: dict[str, ir.Type]
    llvm_structs_by_qualified_name: dict[str, ir.IdentifiedStructType]
    runtime_features: RuntimeFeatureState
    entry_function_symbol_id: str | None
    _fast_math_enabled: bool
    _current_function_return_type: astx.DataType | None
    _current_function_signature: FunctionSignature | None
    _current_generator_frame_ptr: ir.Value | None
    _current_generator_frame_slots: dict[str, int]
    _current_generator_out_ptr: ir.Value | None
    _current_generator_next_state: int | None
    target: llvm.TargetRef
    target_machine: llvm.TargetMachine

    def visit(self, _node: astx.AST) -> None:
        """
        title: Visit AST nodes.
        parameters:
          _node: Syntax node to process.
        """
        raise NotImplementedError

    def get_function(self, _name: str) -> ir.Function | None:
        """
        title: Get function.
        parameters:
          _name: Name of .
        returns: Function.
        """
        return cast(ir.Function | None, None)

    def llvm_function_name_for_node(
        self,
        _node: astx.AST,
        _fallback: str,
    ) -> str:
        """
        title: Return the LLVM symbol name for a function node.
        parameters:
          _node: Syntax node to process.
          _fallback: Fallback.
        returns: The LLVM symbol name for a function node.
        """
        return _fallback

    def create_entry_block_alloca(
        self, _var_name: str, _type_name: str | ir.Type
    ) -> Any:
        """
        title: Create entry block alloca.
        parameters:
          _var_name: Name of var.
          _type_name: Name of type.
        returns: Created entry block alloca.
        """
        return cast(Any, None)

    def _i64_array_pointer(
        self,
        _values: tuple[int, ...],
        *,
        purpose: str,
        symbol_namespace: str = "buffer",
    ) -> ir.Value:
        """
        title: Lower one tuple of i64 values to a stable global pointer.
        parameters:
          _values: Values.
          purpose: Purpose.
          symbol_namespace: Symbol namespace.
        returns: Lowered one tuple of i64 values to a stable global pointer.
        """
        _ = purpose, symbol_namespace
        return cast(ir.Value, None)

    def binding_address(self, node: astx.AST, slot: ir.Value) -> ir.Value:
        """
        title: Return the value address granted by resolved binding storage.
        parameters:
          node: Access with a resolved symbol.
          slot: Storage for the resolved binding.
        returns: Address of the value being accessed.
        """
        return slot

    def _field_address(self, _node: astx.FieldAccess) -> ir.Value:
        """
        title: Lower one field access to an address.
        parameters:
          _node: Syntax node to process.
        returns: Lowered one field access to an address.
        """
        return cast(ir.Value, None)

    def _static_class_field_address(
        self,
        _node: astx.StaticFieldAccess,
    ) -> ir.Value:
        """
        title: Lower one static class field access to a global address.
        parameters:
          _node: Syntax node to process.
        returns: Lowered one static class field access to a global address.
        """
        return cast(ir.Value, None)

    def _lvalue_address(
        self,
        _node: astx.AST,
    ) -> ir.Value:
        """
        title: Lower one mutable lvalue target to an address.
        parameters:
          _node: Syntax node to process.
        returns: Lowered one mutable lvalue target to an address.
        """
        return cast(ir.Value, None)

    def store_local_resource(
        self, _node: astx.AST, _address: ir.Value, _value: ir.Value
    ) -> ir.Value:
        """
        title: Commit an analyzed local store and return its value.
        parameters:
          _node: Syntax node to process.
          _address: Address of the destination binding.
          _value: Evaluated and converted value.
        returns: The value stored in the destination.
        """
        return _value

    def _llvm_function_type_for_signature(
        self,
        _signature: FunctionSignature,
    ) -> ir.FunctionType:
        """
        title: Return one LLVM function type for semantic signature metadata.
        parameters:
          _signature: Signature.
        returns: One LLVM function type for semantic signature metadata.
        """
        return cast(ir.FunctionType, None)

    def _declare_semantic_function(
        self,
        _function: Any,
    ) -> ir.Function:
        """
        title: Declare or reuse one semantic function.
        parameters:
          _function: Function.
        returns: 'Result of this operation: declare or reuse one semantic
          function.'
        """
        return cast(ir.Function, None)

    def _emit_active_cleanups(
        self,
        _start_depth: int = 0,
        _excluded_owner_symbol_ids: frozenset[str] = frozenset(),
    ) -> None:
        """
        title: Emit all active cleanup actions.
        parameters:
          _start_depth: Start depth.
          _excluded_owner_symbol_ids: Identifiers for excluded owner symbol.
        """
        _ = _start_depth

    def _register_owned_list_temporary(
        self,
        _node: astx.AST,
        _list_ptr: ir.Value,
    ) -> None:
        """
        title: Register cleanup for one non-transferred owned list temporary.
        parameters:
          _node: Syntax node to process.
          _list_ptr: List ptr.
        """
        _ = (_node, _list_ptr)

    def _register_owned_string_temporary(
        self,
        _node: astx.AST,
        _pointer: ir.Value,
    ) -> None:
        """
        title: Register cleanup for one non-transferred owned string.
        parameters:
          _node: Syntax node to process.
          _pointer: Pointer.
        """
        _ = (_node, _pointer)

    def _emit_temporary_cleanups(self, _start_depth: int) -> None:
        """
        title: Emit and remove temporary cleanups after one stack depth.
        parameters:
          _start_depth: Start depth.
        """
        _ = _start_depth

    def require_runtime_symbol(
        self, _feature_name: str, _symbol_name: str
    ) -> ir.Function:
        """
        title: Require runtime symbol.
        parameters:
          _feature_name: Name of feature.
          _symbol_name: Name of symbol.
        returns: 'Result of this operation: require runtime symbol.'
        """
        return cast(ir.Function, None)

    def activate_runtime_feature(self, _feature_name: str) -> None:
        """
        title: Activate runtime feature.
        parameters:
          _feature_name: Name of feature.
        """
        return None

    def set_fast_math(self, _enabled: bool) -> None:
        """
        title: Set fast math.
        parameters:
          _enabled: Whether to use enabled.
        """
        return None

    def _apply_fast_math(self, _inst: ir.Instruction) -> None:
        """
        title: Apply fast math.
        parameters:
          _inst: Inst.
        """
        return None

    def _emit_fma(
        self, _lhs: ir.Value, _rhs: ir.Value, _addend: ir.Value
    ) -> ir.Value:
        """
        title: Emit fma.
        parameters:
          _lhs: Left operand.
          _rhs: Right operand.
          _addend: Addend.
        returns: 'Result of this operation: emit fma.'
        """
        return cast(ir.Value, None)

    def _is_numeric_value(self, _value: ir.Value) -> bool:
        """
        title: Is numeric value.
        parameters:
          _value: Value.
        returns: 'Result of this operation: is numeric value.'
        """
        return False

    def _namespace_value(
        self,
        _node: astx.AST,
    ) -> ir.Value | None:
        """
        title: Return one lowered namespace value for an analyzed node.
        parameters:
          _node: Syntax node to process.
        returns: One lowered namespace value for an analyzed node.
        """
        return cast(ir.Value | None, None)

    def _llvm_type_for_ast_type(
        self,
        _type: astx.DataType | None,
    ) -> ir.Type | None:
        """
        title: LLVM type for AST type.
        parameters:
          _type: Type of .
        returns: 'Result of this operation: lLVM type for AST type.'
        """
        return cast(ir.Type | None, None)

    def _resolved_ast_type(
        self, _node: astx.AST | None
    ) -> astx.DataType | None:
        """
        title: Resolved ast type.
        parameters:
          _node: Syntax node to process.
        returns: 'Result of this operation: resolved ast type.'
        """
        return cast(astx.DataType | None, None)

    def _cast_ast_value(
        self,
        _value: ir.Value,
        *,
        source_type: astx.DataType | None,
        target_type: astx.DataType | None,
    ) -> ir.Value:
        """
        title: Cast ast value.
        parameters:
          _value: Value.
          source_type: Type of the source value.
          target_type: Destination type for the conversion.
        returns: 'Result of this operation: cast ast value.'
        """
        _ = source_type
        _ = target_type
        return cast(ir.Value, None)

    def _emit_numeric_compare(
        self,
        _op_code: str,
        _lhs: ir.Value,
        _rhs: ir.Value,
        *,
        unsigned: bool,
        name: str,
    ) -> ir.Value:
        """
        title: Emit numeric compare.
        parameters:
          _op_code: Op code.
          _lhs: Left operand.
          _rhs: Right operand.
          unsigned: Whether to use unsigned semantics.
          name: Name identifying the declaration or operation.
        returns: 'Result of this operation: emit numeric compare.'
        """
        _ = unsigned
        _ = name
        return cast(ir.Value, None)

    def _unify_numeric_operands(
        self,
        _lhs: ir.Value,
        _rhs: ir.Value,
        unsigned: bool = False,
    ) -> tuple[ir.Value, ir.Value]:
        """
        title: Unify numeric operands.
        parameters:
          _lhs: Left operand.
          _rhs: Right operand.
          unsigned: Whether to use unsigned semantics.
        returns: 'Result of this operation: unify numeric operands.'
        """
        _ = unsigned
        return cast(tuple[ir.Value, ir.Value], (None, None))

    def _try_set_binary_op(
        self,
        _lhs: ir.Value | None,
        _rhs: ir.Value | None,
        _op_code: str,
    ) -> bool:
        """
        title: Try set binary op.
        parameters:
          _lhs: Left operand.
          _rhs: Right operand.
          _op_code: Op code.
        returns: 'Result of this operation: try set binary op.'
        """
        return False

    def _handle_string_concatenation(
        self,
        _node: astx.AST,
        _lhs: ir.Value,
        _rhs: ir.Value,
    ) -> ir.Value:
        """
        title: Handle string concatenation.
        parameters:
          _node: Syntax node to process.
          _lhs: Left operand.
          _rhs: Right operand.
        returns: 'Result of this operation: handle string concatenation.'
        """
        return cast(ir.Value, None)

    def _copy_string_to_heap(
        self,
        _node: astx.AST,
        _pointer: ir.Value,
    ) -> ir.Value:
        """
        title: Copy one static string into owned heap storage.
        parameters:
          _node: Syntax node to process.
          _pointer: Pointer.
        returns: 'Result of this operation: copy one static string into owned
          heap storage.'
        """
        return cast(ir.Value, None)

    def _handle_string_comparison(
        self, _lhs: ir.Value, _rhs: ir.Value, _op: str
    ) -> ir.Value:
        """
        title: Handle string comparison.
        parameters:
          _lhs: Left operand.
          _rhs: Right operand.
          _op: Op.
        returns: 'Result of this operation: handle string comparison.'
        """
        return cast(ir.Value, None)

    def _common_list_element_type(
        self, _lhs_ty: ir.Type, _rhs_ty: ir.Type
    ) -> ir.Type:
        """
        title: Common list element type.
        parameters:
          _lhs_ty: Left operand ty.
          _rhs_ty: Right operand ty.
        returns: 'Result of this operation: common list element type.'
        """
        return cast(ir.Type, None)

    def _coerce_to(self, _value: ir.Value, _target_ty: ir.Type) -> ir.Value:
        """
        title: Coerce to.
        parameters:
          _value: Value.
          _target_ty: Target ty.
        returns: 'Result of this operation: coerce to.'
        """
        return cast(ir.Value, None)

    def _mark_set_value(self, _value: ir.Value) -> ir.Value:
        """
        title: Mark set value.
        parameters:
          _value: Value.
        returns: 'Result of this operation: mark set value.'
        """
        return cast(ir.Value, None)

    def _subscript_uses_unsigned_semantics(
        self, _node: astx.SubscriptExpr
    ) -> bool:
        """
        title: Subscript uses unsigned semantics.
        parameters:
          _node: Syntax node to process.
        returns: 'Result of this operation: subscript uses unsigned semantics.'
        """
        return False

    def _constant_subscript_key_matches(
        self, _entry_key: ir.Constant, _key_val: ir.Constant
    ) -> bool:
        """
        title: Constant subscript key matches.
        parameters:
          _entry_key: Entry key.
          _key_val: Key val.
        returns: 'Result of this operation: constant subscript key matches.'
        """
        return False

    def _emit_runtime_subscript_lookup(
        self,
        _dict_val: ir.Constant,
        _key_val: ir.Value,
        *,
        unsigned: bool,
    ) -> None:
        """
        title: Emit runtime subscript lookup.
        parameters:
          _dict_val: Dict val.
          _key_val: Key val.
          unsigned: Whether to use unsigned semantics.
        """
        _ = unsigned

    def _normalize_int_for_printf(
        self,
        _value: ir.Value,
        *,
        unsigned: bool = False,
    ) -> tuple[ir.Value, str]:
        """
        title: Normalize int for printf.
        parameters:
          _value: Value.
          unsigned: Whether to use unsigned semantics.
        returns: Normalized int for printf.
        """
        _ = unsigned
        return cast(tuple[ir.Value, str], (None, ""))

    def _snprintf_heap(
        self,
        _node: astx.AST,
        _fmt_gv: ir.GlobalVariable,
        _args: list[ir.Value],
    ) -> ir.Value:
        """
        title: Snprintf heap.
        parameters:
          _node: Syntax node to process.
          _fmt_gv: Fmt gv.
          _args: Args.
        returns: 'Result of this operation: snprintf heap.'
        """
        return cast(ir.Value, None)

    def _get_or_create_format_global(self, _fmt: str) -> ir.GlobalVariable:
        """
        title: Get or create format global.
        parameters:
          _fmt: Fmt.
        returns: Or create format global.
        """
        return cast(ir.GlobalVariable, None)


@typechecked
class VisitorMixinRuntimeBase:
    """
    title: Runtime-empty base shared by llvmliteir visitor mixins.
    """


if TYPE_CHECKING:
    VisitorMixinBase = VisitorMixinTypingBase
else:
    VisitorMixinBase = VisitorMixinRuntimeBase
