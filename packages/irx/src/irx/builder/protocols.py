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
          method:
            type: Callable[DispatchParameters, None]
        returns:
          type: Any
        """
        del method
        raise NotImplementedError


@typechecked
class ExceptionLoweringTypingBase:
    """
    title: Explicit execution-context and status-ABI lowering services.
    attributes:
      runtime_exception_types:
        type: dict[str, ResolvedExceptionType]
      exception_context:
        type: ir.Value | None
      exception_result_slot:
        type: ir.Value | None
      exception_targets:
        type: list[ExceptionTarget]
      pending_returns:
        type: list[PendingReturn]
      llvm_function_signatures:
        type: dict[str, FunctionSignature]
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
          operation:
            type: str
          args:
            type: list[ir.Value]
        returns:
          type: ir.Value
        """
        del operation, args
        raise NotImplementedError

    def context_value(self) -> ir.Value:
        """
        title: Require the current frame execution context.
        returns:
          type: ir.Value
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
          node:
            type: astx.AST
          callee:
            type: ir.Value
          signature:
            type: FunctionSignature
          args:
            type: list[ir.Value]
        returns:
          type: ir.Value | None
        """
        del node, callee, signature, args
        raise NotImplementedError

    def propagate_status(self, node: astx.AST, status: ir.Value) -> None:
        """
        title: Route failed call status through lexical cleanup regions.
        parameters:
          node:
            type: astx.AST
          status:
            type: ir.Value
        """
        del node, status
        raise NotImplementedError

    def emit_exception_transfer(self, node: astx.AST | None) -> None:
        """
        title: Exit the current region with the context pending exception.
        parameters:
          node:
            type: astx.AST | None
        """
        del node
        raise NotImplementedError

    def emit_success_return(self, value: ir.Value | None) -> None:
        """
        title: Publish successful output after all cleanups.
        parameters:
          value:
            type: ir.Value | None
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
          completions:
            type: tuple[PendingReturn, Ellipsis] | None
          preserved_depth:
            type: int | None
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
          node:
            type: astx.AST
          role:
            type: str
          message:
            type: ir.Value
          code:
            type: str
        """
        del node, role, message, code
        raise NotImplementedError

    def fatal_status(self, node: astx.AST, status: ir.Value) -> None:
        """
        title: Fail without allocation on bookkeeping allocation failure.
        parameters:
          node:
            type: astx.AST
          status:
            type: ir.Value
        """
        del node, status
        raise NotImplementedError

    def checked_native_call(
        self, node: astx.AST, function: ir.Function, args: list[ir.Value]
    ) -> ir.Value:
        """
        title: Invoke a checked native facade with success-only output slots.
        parameters:
          node:
            type: astx.AST
          function:
            type: ir.Function
          args:
            type: list[ir.Value]
        returns:
          type: ir.Value
        """
        del node, function, args
        raise NotImplementedError

    def check_arrow_status(
        self,
        node: astx.AST,
        status: ir.Value,
        operation: str,
        message: ir.Value | None = None,
    ) -> None:
        """
        title: Convert a native Arrow failure category into an exception.
        parameters:
          node:
            type: astx.AST
          status:
            type: ir.Value
          operation:
            type: str
          message:
            type: ir.Value | None
        """
        del node, status, operation, message
        raise NotImplementedError

    def track_native_handle(
        self, node: astx.AST, feature: str, destroy: str, value: ir.Value
    ) -> CleanupAction:
        """
        title: Register rollback for a partially assembled native handle.
        parameters:
          node:
            type: astx.AST
          feature:
            type: str
          destroy:
            type: str
          value:
            type: ir.Value
        returns:
          type: CleanupAction
        """
        del node, feature, destroy, value
        raise NotImplementedError

    def release_native_handle(self, action: CleanupAction) -> None:
        """
        title: Release a native temporary after successful ownership transfer.
        parameters:
          action:
            type: CleanupAction
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
          node:
            type: astx.AST
          condition:
            type: ir.Value
          code:
            type: str
          message:
            type: str
          block_name:
            type: str
          exception_role:
            type: str
        """
        del node, condition, code, message, block_name, exception_role
        raise NotImplementedError


class VisitorProtocol(BaseVisitorProtocol, Protocol):
    """
    title: Stable interface used by visitor mixins and runtime features.
    attributes:
      runtime_exception_types:
        type: dict[str, ResolvedExceptionType]
      exception_context:
        type: ir.Value | None
      exception_result_slot:
        type: ir.Value | None
      exception_targets:
        type: list[ExceptionTarget]
      pending_returns:
        type: list[PendingReturn]
      llvm_function_signatures:
        type: dict[str, FunctionSignature]
      _llvm:
        type: VariablesLLVM
      named_values:
        type: NamedValueMap
      const_vars:
        type: set[str]
      function_protos:
        type: dict[str, astx.FunctionPrototype]
      llvm_functions_by_symbol_id:
        type: dict[str, ir.Function]
      result_stack:
        type: list[ResultStackValue]
      _buffer_view_global_counter:
        type: int
      loop_stack:
        type: list[LoopTargets]
      cleanup_stack:
        type: list[CleanupAction]
      class_construction_stack:
        type: list[ir.Value]
      emitting_failure_cleanup:
        type: bool
      struct_types:
        type: dict[str, ir.Type]
      llvm_structs_by_qualified_name:
        type: dict[str, ir.IdentifiedStructType]
      runtime_features:
        type: RuntimeFeatureState
      entry_function_symbol_id:
        type: str | None
      _fast_math_enabled:
        type: bool
      _current_function_return_type:
        type: astx.DataType | None
      _current_function_signature:
        type: FunctionSignature | None
      _current_generator_frame_ptr:
        type: ir.Value | None
      _current_generator_frame_slots:
        type: dict[str, int]
      _current_generator_out_ptr:
        type: ir.Value | None
      _current_generator_next_state:
        type: int | None
      target:
        type: llvm.TargetRef
      target_machine:
        type: llvm.TargetMachine
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
          node:
            type: astx.ClassDefStmt
        """
        del node
        raise NotImplementedError

    def get_function(self, _name: str) -> ir.Function | None:
        """
        title: Get function.
        parameters:
          _name:
            type: str
        returns:
          type: ir.Function | None
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
          _node:
            type: astx.AST
          _fallback:
            type: str
        returns:
          type: str
        """
        ...

    def create_entry_block_alloca(
        self, _var_name: str, _type_name: str | ir.Type
    ) -> Any:
        """
        title: Create entry block alloca.
        parameters:
          _var_name:
            type: str
          _type_name:
            type: str | ir.Type
        returns:
          type: Any
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
          _values:
            type: tuple[int, Ellipsis]
          purpose:
            type: str
          symbol_namespace:
            type: str
        returns:
          type: ir.Value
        """
        ...

    def _field_address(self, _node: astx.FieldAccess) -> ir.Value:
        """
        title: Lower one field access to an address.
        parameters:
          _node:
            type: astx.FieldAccess
        returns:
          type: ir.Value
        """
        ...

    def _base_class_field_address(
        self,
        _node: astx.BaseFieldAccess,
    ) -> ir.Value:
        """
        title: Lower one base-qualified class field access to an address.
        parameters:
          _node:
            type: astx.BaseFieldAccess
        returns:
          type: ir.Value
        """
        ...

    def _static_class_field_address(
        self,
        _node: astx.StaticFieldAccess,
    ) -> ir.Value:
        """
        title: Lower one static class field access to a global address.
        parameters:
          _node:
            type: astx.StaticFieldAccess
        returns:
          type: ir.Value
        """
        ...

    def _lvalue_address(
        self,
        _node: astx.AST,
    ) -> ir.Value:
        """
        title: Lower one mutable lvalue target to an address.
        parameters:
          _node:
            type: astx.AST
        returns:
          type: ir.Value
        """
        ...

    def _destroy_replaced_list(
        self,
        _node: astx.AST,
        _list_ptr: ir.Value,
        *,
        target_name: str,
    ) -> None:
        """
        title: Destroy owned list storage before a validated replacement.
        parameters:
          _node:
            type: astx.AST
          _list_ptr:
            type: ir.Value
          target_name:
            type: str
        """
        ...

    def _destroy_replaced_string(
        self,
        _node: astx.AST,
        _string_ptr: ir.Value,
        *,
        target_name: str,
    ) -> None:
        """
        title: Destroy owned string storage before a validated replacement.
        parameters:
          _node:
            type: astx.AST
          _string_ptr:
            type: ir.Value
          target_name:
            type: str
        """
        ...

    def _llvm_function_type_for_signature(
        self,
        _signature: FunctionSignature,
    ) -> ir.FunctionType:
        """
        title: Return one LLVM function type for semantic signature metadata.
        parameters:
          _signature:
            type: FunctionSignature
        returns:
          type: ir.FunctionType
        """
        ...

    def _declare_semantic_function(
        self,
        _function: Any,
    ) -> ir.Function:
        """
        title: Declare or reuse one semantic function.
        parameters:
          _function:
            type: Any
        returns:
          type: ir.Function
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
          _start_depth:
            type: int
          _excluded_owner_symbol_ids:
            type: frozenset[str]
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
          _node:
            type: astx.AST
          _list_ptr:
            type: ir.Value
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
          _node:
            type: astx.AST
          _pointer:
            type: ir.Value
        """
        ...

    def _emit_temporary_cleanups(self, _start_depth: int) -> None:
        """
        title: Emit and remove temporary cleanups after one stack depth.
        parameters:
          _start_depth:
            type: int
        """
        ...

    def require_runtime_symbol(
        self, _feature_name: str, _symbol_name: str
    ) -> ir.Function:
        """
        title: Require runtime symbol.
        parameters:
          _feature_name:
            type: str
          _symbol_name:
            type: str
        returns:
          type: ir.Function
        """
        ...

    def activate_runtime_feature(self, _feature_name: str) -> None:
        """
        title: Activate runtime feature.
        parameters:
          _feature_name:
            type: str
        """
        ...

    def set_fast_math(self, _enabled: bool) -> None:
        """
        title: Set fast math.
        parameters:
          _enabled:
            type: bool
        """
        ...

    def _apply_fast_math(self, _inst: ir.Instruction) -> None:
        """
        title: Apply fast math.
        parameters:
          _inst:
            type: ir.Instruction
        """
        ...

    def _emit_fma(
        self, _lhs: ir.Value, _rhs: ir.Value, _addend: ir.Value
    ) -> ir.Value:
        """
        title: Emit fma.
        parameters:
          _lhs:
            type: ir.Value
          _rhs:
            type: ir.Value
          _addend:
            type: ir.Value
        returns:
          type: ir.Value
        """
        ...

    def _is_numeric_value(self, _value: ir.Value) -> bool:
        """
        title: Is numeric value.
        parameters:
          _value:
            type: ir.Value
        returns:
          type: bool
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
          _lhs:
            type: ir.Value
          _rhs:
            type: ir.Value
          unsigned:
            type: bool
        returns:
          type: tuple[ir.Value, ir.Value]
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
          _lhs:
            type: ir.Value | None
          _rhs:
            type: ir.Value | None
          _op_code:
            type: str
        returns:
          type: bool
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
          _node:
            type: astx.AST
          _lhs:
            type: ir.Value
          _rhs:
            type: ir.Value
        returns:
          type: ir.Value
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
          _node:
            type: astx.AST
          _pointer:
            type: ir.Value
        returns:
          type: ir.Value
        """
        ...

    def _handle_string_comparison(
        self, _lhs: ir.Value, _rhs: ir.Value, _op: str
    ) -> ir.Value:
        """
        title: Handle string comparison.
        parameters:
          _lhs:
            type: ir.Value
          _rhs:
            type: ir.Value
          _op:
            type: str
        returns:
          type: ir.Value
        """
        ...

    def _common_list_element_type(
        self, _lhs_ty: ir.Type, _rhs_ty: ir.Type
    ) -> ir.Type:
        """
        title: Common list element type.
        parameters:
          _lhs_ty:
            type: ir.Type
          _rhs_ty:
            type: ir.Type
        returns:
          type: ir.Type
        """
        ...

    def _coerce_to(self, _value: ir.Value, _target_ty: ir.Type) -> ir.Value:
        """
        title: Coerce to.
        parameters:
          _value:
            type: ir.Value
          _target_ty:
            type: ir.Type
        returns:
          type: ir.Value
        """
        ...

    def _mark_set_value(self, _value: ir.Value) -> ir.Value:
        """
        title: Mark set value.
        parameters:
          _value:
            type: ir.Value
        returns:
          type: ir.Value
        """
        ...

    def _subscript_uses_unsigned_semantics(
        self, _node: astx.SubscriptExpr
    ) -> bool:
        """
        title: Subscript uses unsigned semantics.
        parameters:
          _node:
            type: astx.SubscriptExpr
        returns:
          type: bool
        """
        ...

    def _constant_subscript_key_matches(
        self, _entry_key: ir.Constant, _key_val: ir.Constant
    ) -> bool:
        """
        title: Constant subscript key matches.
        parameters:
          _entry_key:
            type: ir.Constant
          _key_val:
            type: ir.Constant
        returns:
          type: bool
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
          _dict_val:
            type: ir.Constant
          _key_val:
            type: ir.Value
          unsigned:
            type: bool
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
          _value:
            type: ir.Value
          unsigned:
            type: bool
        returns:
          type: tuple[ir.Value, str]
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
          _node:
            type: astx.AST
          _fmt_gv:
            type: ir.GlobalVariable
          _args:
            type: list[ir.Value]
        returns:
          type: ir.Value
        """
        ...

    def _get_or_create_format_global(self, _fmt: str) -> ir.GlobalVariable:
        """
        title: Get or create format global.
        parameters:
          _fmt:
            type: str
        returns:
          type: ir.GlobalVariable
        """
        ...


@typechecked
class VisitorMixinTypingBase(ExceptionLoweringTypingBase):
    """
    title: Type-checking-only annotation carrier for llvmliteir visitor mixins.
    attributes:
      runtime_exception_types:
        type: dict[str, ResolvedExceptionType]
      exception_context:
        type: ir.Value | None
      exception_result_slot:
        type: ir.Value | None
      exception_targets:
        type: list[ExceptionTarget]
      pending_returns:
        type: list[PendingReturn]
      llvm_function_signatures:
        type: dict[str, FunctionSignature]
      _llvm:
        type: VariablesLLVM
      named_values:
        type: NamedValueMap
      const_vars:
        type: set[str]
      function_protos:
        type: dict[str, astx.FunctionPrototype]
      llvm_functions_by_symbol_id:
        type: dict[str, ir.Function]
      result_stack:
        type: list[ResultStackValue]
      _buffer_view_global_counter:
        type: int
      loop_stack:
        type: list[LoopTargets]
      cleanup_stack:
        type: list[CleanupAction]
      class_construction_stack:
        type: list[ir.Value]
      emitting_failure_cleanup:
        type: bool
      struct_types:
        type: dict[str, ir.Type]
      llvm_structs_by_qualified_name:
        type: dict[str, ir.IdentifiedStructType]
      runtime_features:
        type: RuntimeFeatureState
      entry_function_symbol_id:
        type: str | None
      _fast_math_enabled:
        type: bool
      _current_function_return_type:
        type: astx.DataType | None
      _current_function_signature:
        type: FunctionSignature | None
      _current_generator_frame_ptr:
        type: ir.Value | None
      _current_generator_frame_slots:
        type: dict[str, int]
      _current_generator_out_ptr:
        type: ir.Value | None
      _current_generator_next_state:
        type: int | None
      target:
        type: llvm.TargetRef
      target_machine:
        type: llvm.TargetMachine
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
          _node:
            type: astx.AST
        """
        raise NotImplementedError

    def visit_child(self, _node: astx.AST) -> None:
        """
        title: Visit one child AST node.
        parameters:
          _node:
            type: astx.AST
        """
        raise NotImplementedError

    def get_function(self, _name: str) -> ir.Function | None:
        """
        title: Get function.
        parameters:
          _name:
            type: str
        returns:
          type: ir.Function | None
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
          _node:
            type: astx.AST
          _fallback:
            type: str
        returns:
          type: str
        """
        return _fallback

    def create_entry_block_alloca(
        self, _var_name: str, _type_name: str | ir.Type
    ) -> Any:
        """
        title: Create entry block alloca.
        parameters:
          _var_name:
            type: str
          _type_name:
            type: str | ir.Type
        returns:
          type: Any
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
          _values:
            type: tuple[int, Ellipsis]
          purpose:
            type: str
          symbol_namespace:
            type: str
        returns:
          type: ir.Value
        """
        _ = purpose, symbol_namespace
        return cast(ir.Value, None)

    def _field_address(self, _node: astx.FieldAccess) -> ir.Value:
        """
        title: Lower one field access to an address.
        parameters:
          _node:
            type: astx.FieldAccess
        returns:
          type: ir.Value
        """
        return cast(ir.Value, None)

    def _static_class_field_address(
        self,
        _node: astx.StaticFieldAccess,
    ) -> ir.Value:
        """
        title: Lower one static class field access to a global address.
        parameters:
          _node:
            type: astx.StaticFieldAccess
        returns:
          type: ir.Value
        """
        return cast(ir.Value, None)

    def _lvalue_address(
        self,
        _node: astx.AST,
    ) -> ir.Value:
        """
        title: Lower one mutable lvalue target to an address.
        parameters:
          _node:
            type: astx.AST
        returns:
          type: ir.Value
        """
        return cast(ir.Value, None)

    def _destroy_replaced_list(
        self,
        _node: astx.AST,
        _list_ptr: ir.Value,
        *,
        target_name: str,
    ) -> None:
        """
        title: Destroy owned list storage before a validated replacement.
        parameters:
          _node:
            type: astx.AST
          _list_ptr:
            type: ir.Value
          target_name:
            type: str
        """
        _ = (_node, _list_ptr, target_name)

    def _destroy_replaced_string(
        self,
        _node: astx.AST,
        _string_ptr: ir.Value,
        *,
        target_name: str,
    ) -> None:
        """
        title: Destroy owned string storage before a validated replacement.
        parameters:
          _node:
            type: astx.AST
          _string_ptr:
            type: ir.Value
          target_name:
            type: str
        """
        _ = (_node, _string_ptr, target_name)

    def _llvm_function_type_for_signature(
        self,
        _signature: FunctionSignature,
    ) -> ir.FunctionType:
        """
        title: Return one LLVM function type for semantic signature metadata.
        parameters:
          _signature:
            type: FunctionSignature
        returns:
          type: ir.FunctionType
        """
        return cast(ir.FunctionType, None)

    def _declare_semantic_function(
        self,
        _function: Any,
    ) -> ir.Function:
        """
        title: Declare or reuse one semantic function.
        parameters:
          _function:
            type: Any
        returns:
          type: ir.Function
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
          _start_depth:
            type: int
          _excluded_owner_symbol_ids:
            type: frozenset[str]
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
          _node:
            type: astx.AST
          _list_ptr:
            type: ir.Value
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
          _node:
            type: astx.AST
          _pointer:
            type: ir.Value
        """
        _ = (_node, _pointer)

    def _emit_temporary_cleanups(self, _start_depth: int) -> None:
        """
        title: Emit and remove temporary cleanups after one stack depth.
        parameters:
          _start_depth:
            type: int
        """
        _ = _start_depth

    def require_runtime_symbol(
        self, _feature_name: str, _symbol_name: str
    ) -> ir.Function:
        """
        title: Require runtime symbol.
        parameters:
          _feature_name:
            type: str
          _symbol_name:
            type: str
        returns:
          type: ir.Function
        """
        return cast(ir.Function, None)

    def activate_runtime_feature(self, _feature_name: str) -> None:
        """
        title: Activate runtime feature.
        parameters:
          _feature_name:
            type: str
        """
        return None

    def set_fast_math(self, _enabled: bool) -> None:
        """
        title: Set fast math.
        parameters:
          _enabled:
            type: bool
        """
        return None

    def _apply_fast_math(self, _inst: ir.Instruction) -> None:
        """
        title: Apply fast math.
        parameters:
          _inst:
            type: ir.Instruction
        """
        return None

    def _emit_fma(
        self, _lhs: ir.Value, _rhs: ir.Value, _addend: ir.Value
    ) -> ir.Value:
        """
        title: Emit fma.
        parameters:
          _lhs:
            type: ir.Value
          _rhs:
            type: ir.Value
          _addend:
            type: ir.Value
        returns:
          type: ir.Value
        """
        return cast(ir.Value, None)

    def _is_numeric_value(self, _value: ir.Value) -> bool:
        """
        title: Is numeric value.
        parameters:
          _value:
            type: ir.Value
        returns:
          type: bool
        """
        return False

    def _namespace_value(
        self,
        _node: astx.AST,
    ) -> ir.Value | None:
        """
        title: Return one lowered namespace value for an analyzed node.
        parameters:
          _node:
            type: astx.AST
        returns:
          type: ir.Value | None
        """
        return cast(ir.Value | None, None)

    def _llvm_type_for_ast_type(
        self,
        _type: astx.DataType | None,
    ) -> ir.Type | None:
        """
        title: LLVM type for AST type.
        parameters:
          _type:
            type: astx.DataType | None
        returns:
          type: ir.Type | None
        """
        return cast(ir.Type | None, None)

    def _resolved_ast_type(
        self, _node: astx.AST | None
    ) -> astx.DataType | None:
        """
        title: Resolved ast type.
        parameters:
          _node:
            type: astx.AST | None
        returns:
          type: astx.DataType | None
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
          _value:
            type: ir.Value
          source_type:
            type: astx.DataType | None
          target_type:
            type: astx.DataType | None
        returns:
          type: ir.Value
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
          _op_code:
            type: str
          _lhs:
            type: ir.Value
          _rhs:
            type: ir.Value
          unsigned:
            type: bool
          name:
            type: str
        returns:
          type: ir.Value
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
          _lhs:
            type: ir.Value
          _rhs:
            type: ir.Value
          unsigned:
            type: bool
        returns:
          type: tuple[ir.Value, ir.Value]
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
          _lhs:
            type: ir.Value | None
          _rhs:
            type: ir.Value | None
          _op_code:
            type: str
        returns:
          type: bool
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
          _node:
            type: astx.AST
          _lhs:
            type: ir.Value
          _rhs:
            type: ir.Value
        returns:
          type: ir.Value
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
          _node:
            type: astx.AST
          _pointer:
            type: ir.Value
        returns:
          type: ir.Value
        """
        return cast(ir.Value, None)

    def _handle_string_comparison(
        self, _lhs: ir.Value, _rhs: ir.Value, _op: str
    ) -> ir.Value:
        """
        title: Handle string comparison.
        parameters:
          _lhs:
            type: ir.Value
          _rhs:
            type: ir.Value
          _op:
            type: str
        returns:
          type: ir.Value
        """
        return cast(ir.Value, None)

    def _common_list_element_type(
        self, _lhs_ty: ir.Type, _rhs_ty: ir.Type
    ) -> ir.Type:
        """
        title: Common list element type.
        parameters:
          _lhs_ty:
            type: ir.Type
          _rhs_ty:
            type: ir.Type
        returns:
          type: ir.Type
        """
        return cast(ir.Type, None)

    def _coerce_to(self, _value: ir.Value, _target_ty: ir.Type) -> ir.Value:
        """
        title: Coerce to.
        parameters:
          _value:
            type: ir.Value
          _target_ty:
            type: ir.Type
        returns:
          type: ir.Value
        """
        return cast(ir.Value, None)

    def _mark_set_value(self, _value: ir.Value) -> ir.Value:
        """
        title: Mark set value.
        parameters:
          _value:
            type: ir.Value
        returns:
          type: ir.Value
        """
        return cast(ir.Value, None)

    def _subscript_uses_unsigned_semantics(
        self, _node: astx.SubscriptExpr
    ) -> bool:
        """
        title: Subscript uses unsigned semantics.
        parameters:
          _node:
            type: astx.SubscriptExpr
        returns:
          type: bool
        """
        return False

    def _constant_subscript_key_matches(
        self, _entry_key: ir.Constant, _key_val: ir.Constant
    ) -> bool:
        """
        title: Constant subscript key matches.
        parameters:
          _entry_key:
            type: ir.Constant
          _key_val:
            type: ir.Constant
        returns:
          type: bool
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
          _dict_val:
            type: ir.Constant
          _key_val:
            type: ir.Value
          unsigned:
            type: bool
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
          _value:
            type: ir.Value
          unsigned:
            type: bool
        returns:
          type: tuple[ir.Value, str]
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
          _node:
            type: astx.AST
          _fmt_gv:
            type: ir.GlobalVariable
          _args:
            type: list[ir.Value]
        returns:
          type: ir.Value
        """
        return cast(ir.Value, None)

    def _get_or_create_format_global(self, _fmt: str) -> ir.GlobalVariable:
        """
        title: Get or create format global.
        parameters:
          _fmt:
            type: str
        returns:
          type: ir.GlobalVariable
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
