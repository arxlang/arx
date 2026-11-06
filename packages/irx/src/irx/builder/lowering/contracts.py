"""
title: Explicit backend concern dependencies and typed callback contracts.
summary: >-
  Each frozen record names only services consumed by one implementation family.
  Records belong to a compiler instance, not the immutable provider catalog.
  Shared LLVM, module, function, and lexical state is injected by lifetime;
  cross-family operations are explicit typed callbacks, not a visitor owner.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import astx

from llvmlite import ir
from llvmlite.binding.targets import TargetMachine
from public import private

from irx.analysis.resolved_nodes import (
    CallResolution,
    FunctionSignature,
    ResolvedClassConstruction,
    ResolvedExceptionType,
    ResolvedFileOpen,
    ResolvedGeneratorFunction,
    ResolvedIteration,
    ResolvedMethodCall,
    SemanticClass,
    SemanticFunction,
)
from irx.buffer import BufferIndexBoundsPolicy
from irx.builder.extensions.calls import CallLoweringServices
from irx.builder.lowering.materialization import MaterializationEmission
from irx.builder.lowering.sequences import SequenceEmission
from irx.builder.lowering.text import TextEmission
from irx.builder.runtime.registry import RuntimeFeatureState
from irx.builder.services.cleanup import CleanupService
from irx.builder.services.collections import CollectionEmission
from irx.builder.services.control_state import (
    ExceptionModuleState,
    ExitState,
    FunctionValueState,
    GeneratorFrameState,
    GeneratorModuleState,
    ModuleEmissionState,
)
from irx.builder.services.conversions import NumericEmission
from irx.builder.services.exceptions import (
    ExceptionService,
    RuntimeGuardService,
)
from irx.builder.services.floating import FloatingEmission
from irx.builder.services.layout import LayoutEmission
from irx.builder.services.representations import TypeLowering
from irx.builder.state import CleanupAction
from irx.builder.strings import StringEmission
from irx.builder.types import VariablesLLVM
from irx.extensions import ScopedDispatch
from irx.typecheck import typechecked


@private
@runtime_checkable
class AppendBasicBlocksCallback(Protocol):
    """
    title: Typed cross-feature operation append_basic_blocks.
    """

    def __call__(self, prefix: str, *roles: str) -> tuple[ir.Block, ...]:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          prefix:
            type: str
          roles:
            type: str
            variadic: positional
        returns:
          type: tuple[ir.Block, Ellipsis]
        """
        del prefix, roles
        raise NotImplementedError


@private
@runtime_checkable
class ApplyCallingConventionCallback(Protocol):
    """
    title: Typed cross-feature operation apply_calling_convention.
    """

    def __call__(self, signature: FunctionSignature) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          signature:
            type: FunctionSignature
        """
        del signature
        raise NotImplementedError


@private
@runtime_checkable
class AssertSourceNameCallback(Protocol):
    """
    title: Typed cross-feature operation assert_source_name.
    """

    def __call__(self, node: astx.AST) -> str:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
        returns:
          type: str
        """
        del node
        raise NotImplementedError


@private
@runtime_checkable
class DeclareSemanticFunctionCallback(Protocol):
    """
    title: Typed cross-feature operation declare_semantic_function.
    """

    def __call__(self, function: SemanticFunction) -> ir.Function:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          function:
            type: SemanticFunction
        returns:
          type: ir.Function
        """
        del function
        raise NotImplementedError


@private
@runtime_checkable
class DefaultRuntimeInitializerCallback(Protocol):
    """
    title: Typed cross-feature operation default_runtime_initializer.
    """

    def __call__(self, type_: astx.DataType, *, name_hint: str) -> ir.Value:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          type_:
            type: astx.DataType
          name_hint:
            type: str
        returns:
          type: ir.Value
        """
        del type_, name_hint
        raise NotImplementedError


@private
@runtime_checkable
class DestroyReplacedListCallback(Protocol):
    """
    title: Typed cross-feature operation destroy_replaced_list.
    """

    def __call__(
        self, node: astx.AST, list_ptr: ir.Value, *, target_name: str
    ) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          list_ptr:
            type: ir.Value
          target_name:
            type: str
        """
        del node, list_ptr, target_name
        raise NotImplementedError


@private
@runtime_checkable
class DestroyReplacedStringCallback(Protocol):
    """
    title: Typed cross-feature operation destroy_replaced_string.
    """

    def __call__(
        self, node: astx.AST, string_ptr: ir.Value, *, target_name: str
    ) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          string_ptr:
            type: ir.Value
          target_name:
            type: str
        """
        del node, string_ptr, target_name
        raise NotImplementedError


@private
@runtime_checkable
class DiscardChildResultsCallback(Protocol):
    """
    title: Typed cross-feature operation discard_child_results.
    """

    def __call__(self, node: astx.AST) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
        """
        del node
        raise NotImplementedError


@private
@runtime_checkable
class EmitGeneratorStopCallback(Protocol):
    """
    title: Typed cross-feature operation emit_generator_stop.
    """

    def __call__(self, node: astx.AST | None = None) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST | None
        """
        del node
        raise NotImplementedError


@private
@runtime_checkable
class EmptyListValueCallback(Protocol):
    """
    title: Typed cross-feature operation empty_list_value.
    """

    def __call__(self, node: astx.AST) -> ir.Constant:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
        returns:
          type: ir.Constant
        """
        del node
        raise NotImplementedError


@private
@runtime_checkable
class EmptyListValueForTypeCallback(Protocol):
    """
    title: Typed cross-feature operation empty_list_value_for_type.
    """

    def __call__(self, type_: astx.DataType | None) -> ir.Constant:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          type_:
            type: astx.DataType | None
        returns:
          type: ir.Constant
        """
        del type_
        raise NotImplementedError


@private
@runtime_checkable
class I64ArrayPointerCallback(Protocol):
    """
    title: Typed cross-feature operation i64_array_pointer.
    """

    def __call__(
        self,
        values: tuple[int, ...],
        *,
        purpose: str,
        symbol_namespace: str = "buffer",
    ) -> ir.Value:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          values:
            type: tuple[int, Ellipsis]
          purpose:
            type: str
          symbol_namespace:
            type: str
        returns:
          type: ir.Value
        """
        del values, purpose, symbol_namespace
        raise NotImplementedError


@private
@runtime_checkable
class IndirectMethodCalleeCallback(Protocol):
    """
    title: Typed cross-feature operation indirect_method_callee.
    """

    def __call__(
        self,
        *,
        node: astx.AST,
        method_resolution: ResolvedMethodCall,
        receiver_value: ir.Value,
    ) -> ir.Value:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          method_resolution:
            type: ResolvedMethodCall
          receiver_value:
            type: ir.Value
        returns:
          type: ir.Value
        """
        del node, method_resolution, receiver_value
        raise NotImplementedError


@private
@runtime_checkable
class ListPointerAndLengthForIterationCallback(Protocol):
    """
    title: Typed cross-feature operation list_pointer_and_length_for_iteration.
    """

    def __call__(self, base: astx.AST) -> tuple[ir.Value, ir.Value]:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          base:
            type: astx.AST
        returns:
          type: tuple[ir.Value, ir.Value]
        """
        del base
        raise NotImplementedError


@private
@runtime_checkable
class ListPointerForCallCallback(Protocol):
    """
    title: Typed cross-feature operation list_pointer_for_call.
    """

    def __call__(self, node: astx.AST, *, name: str) -> ir.Value:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          name:
            type: str
        returns:
          type: ir.Value
        """
        del node, name
        raise NotImplementedError


@private
@runtime_checkable
class LlvmListTypeCallback(Protocol):
    """
    title: Typed cross-feature operation llvm_list_type.
    """

    def __call__(self) -> ir.Type:
        """
        title: Invoke the required phase-owned operation.
        returns:
          type: ir.Type
        """
        raise NotImplementedError


@private
@runtime_checkable
class LoadListElementAtIndexCallback(Protocol):
    """
    title: Typed cross-feature operation load_list_element_at_index.
    """

    def __call__(
        self, *, base: astx.AST, list_ptr: ir.Value, index: ir.Value
    ) -> ir.Value:
        """
        title: Invoke the required phase-owned operation.
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
        del base, list_ptr, index
        raise NotImplementedError


@private
@runtime_checkable
class LoopScopeCallback(Protocol):
    """
    title: Typed cross-feature operation loop_scope.
    """

    def __call__(
        self, *, break_target: ir.Block, continue_target: ir.Block
    ) -> AbstractContextManager[None]:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          break_target:
            type: ir.Block
          continue_target:
            type: ir.Block
        returns:
          type: AbstractContextManager[None]
        """
        del break_target, continue_target
        raise NotImplementedError


@private
@runtime_checkable
class LowerBooleanConditionCallback(Protocol):
    """
    title: Typed cross-feature operation lower_boolean_condition.
    """

    def __call__(
        self, value: ir.Value | None, *, node: astx.AST, context: str
    ) -> ir.Value:
        """
        title: Invoke the required phase-owned operation.
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
        del value, node, context
        raise NotImplementedError


@private
@runtime_checkable
class LowerBufferIndexIndicesCallback(Protocol):
    """
    title: Typed cross-feature operation lower_buffer_index_indices.
    """

    def __call__(self, indices: list[astx.AST]) -> list[ir.Value]:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          indices:
            type: list[astx.AST]
        returns:
          type: list[ir.Value]
        """
        del indices
        raise NotImplementedError


@private
@runtime_checkable
class LowerGeneratorForInLoopCallback(Protocol):
    """
    title: Typed cross-feature operation lower_generator_for_in_loop.
    """

    def __call__(
        self, node: astx.ForInLoopStmt, iteration: ResolvedIteration
    ) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.ForInLoopStmt
          iteration:
            type: ResolvedIteration
        """
        del node, iteration
        raise NotImplementedError


@private
@runtime_checkable
class LowerGeneratorFunctionCallback(Protocol):
    """
    title: Typed cross-feature operation lower_generator_function.
    """

    def __call__(
        self, node: astx.FunctionDef, generator: ResolvedGeneratorFunction
    ) -> ir.Function:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.FunctionDef
          generator:
            type: ResolvedGeneratorFunction
        returns:
          type: ir.Function
        """
        del node, generator
        raise NotImplementedError


@private
@runtime_checkable
class LowerListSubscriptCallback(Protocol):
    """
    title: Typed cross-feature operation lower_list_subscript.
    """

    def __call__(
        self, *, base: astx.AST, index_node: astx.AST, result_node: astx.AST
    ) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          base:
            type: astx.AST
          index_node:
            type: astx.AST
          result_node:
            type: astx.AST
        """
        del base, index_node, result_node
        raise NotImplementedError


@private
@runtime_checkable
class RegisterOwnedStringCleanupCallback(Protocol):
    """
    title: Typed cross-feature operation register_owned_string_cleanup.
    """

    def __call__(
        self,
        node: astx.AST,
        string_ptr: ir.Value,
    ) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          string_ptr:
            type: ir.Value
        """
        del node, string_ptr
        raise NotImplementedError


@private
@runtime_checkable
class ResolvedIterationCallback(Protocol):
    """
    title: Typed cross-feature operation resolved_iteration.
    """

    def __call__(self, node: astx.AST) -> ResolvedIteration | None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
        returns:
          type: ResolvedIteration | None
        """
        del node
        raise NotImplementedError


@private
@runtime_checkable
class TemporaryNamedValueCallback(Protocol):
    """
    title: Typed cross-feature operation temporary_named_value.
    """

    def __call__(
        self, key: str, value: ir.Value, *, is_constant: bool = False
    ) -> AbstractContextManager[None]:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          key:
            type: str
          value:
            type: ir.Value
          is_constant:
            type: bool
        returns:
          type: AbstractContextManager[None]
        """
        del key, value, is_constant
        raise NotImplementedError


@private
@runtime_checkable
class TranslateModulesCallback(Protocol):
    """
    title: Typed cross-feature operation translate_modules.
    """

    def __call__(
        self,
        modules: list[astx.Module],
        declarations: frozenset[int] | None = None,
    ) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          modules:
            type: list[astx.Module]
          declarations:
            type: frozenset[int] | None
        """
        del modules, declarations
        raise NotImplementedError


@private
@runtime_checkable
class ActivateRuntimeFeatureCallback(Protocol):
    """
    title: Typed cross-feature operation activate_runtime_feature.
    """

    def __call__(self, feature_name: str) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          feature_name:
            type: str
        """
        del feature_name
        raise NotImplementedError


@private
@runtime_checkable
class ArrowExplicitLifetimeCallback(Protocol):
    """
    title: Typed cross-feature operation arrow_explicit_lifetime.
    """

    def __call__(
        self, node: astx.AST, value: ir.Value, *, retain: bool
    ) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
          retain:
            type: bool
        """
        del node, value, retain
        raise NotImplementedError


@private
@runtime_checkable
class ArrowReferenceCountCallback(Protocol):
    """
    title: Typed cross-feature operation arrow_reference_count.
    """

    def __call__(self, owner: str) -> ir.Value:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          owner:
            type: str
        returns:
          type: ir.Value
        """
        del owner
        raise NotImplementedError


@private
@runtime_checkable
class ArrowReleaseBindingCallback(Protocol):
    """
    title: Typed cross-feature operation arrow_release_binding.
    """

    def __call__(self, node: astx.AST, value: ir.Value, owner: str) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
          owner:
            type: str
        """
        del node, value, owner
        raise NotImplementedError


@private
@runtime_checkable
class ArrowTemporaryCallback(Protocol):
    """
    title: Typed cross-feature operation arrow_temporary.
    """

    def __call__(self, node: astx.AST, value: ir.Value) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
        """
        del node, value
        raise NotImplementedError


@private
@runtime_checkable
class CheckArrowStatusCallback(Protocol):
    """
    title: Typed cross-feature operation check_arrow_status.
    """

    def __call__(
        self,
        node: astx.AST,
        status: ir.Value,
        operation: str,
        message: ir.Value | None = None,
    ) -> None:
        """
        title: Invoke the required phase-owned operation.
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


@private
@runtime_checkable
class CheckedNativeCallCallback(Protocol):
    """
    title: Typed cross-feature operation checked_native_call.
    """

    def __call__(
        self, node: astx.AST, function: ir.Function, args: list[ir.Value]
    ) -> ir.Value:
        """
        title: Invoke the required phase-owned operation.
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


@private
@runtime_checkable
class ClassAcquireCallback(Protocol):
    """
    title: Typed cross-feature operation class_acquire.
    """

    def __call__(self, node: astx.AST, value: ir.Value) -> ir.Value:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
        returns:
          type: ir.Value
        """
        del node, value
        raise NotImplementedError


@private
@runtime_checkable
class ClassCleanupCallback(Protocol):
    """
    title: Typed cross-feature operation class_cleanup.
    """

    def __call__(
        self,
        node: astx.AST,
        value: ir.Value,
        owner: str | None = None,
        *,
        storage: bool = False,
    ) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
          owner:
            type: str | None
          storage:
            type: bool
        """
        del node, value, owner, storage
        raise NotImplementedError


@private
@runtime_checkable
class ClassDropFunctionCallback(Protocol):
    """
    title: Typed cross-feature operation class_drop_function.
    """

    def __call__(self, class_: SemanticClass) -> ir.Function:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          class_:
            type: SemanticClass
        returns:
          type: ir.Function
        """
        del class_
        raise NotImplementedError


@private
@runtime_checkable
class ClassFieldFunctionCallback(Protocol):
    """
    title: Typed cross-feature operation class_field_function.
    """

    def __call__(self, class_: SemanticClass) -> ir.Function:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          class_:
            type: SemanticClass
        returns:
          type: ir.Function
        """
        del class_
        raise NotImplementedError


@private
@runtime_checkable
class ClassFieldValueCallback(Protocol):
    """
    title: Typed cross-feature operation class_field_value.
    """

    def __call__(self, node: astx.AST, value: ir.Value) -> ir.Value:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
        returns:
          type: ir.Value
        """
        del node, value
        raise NotImplementedError


@private
@runtime_checkable
class ClassOperationCallback(Protocol):
    """
    title: Typed cross-feature operation class_operation.
    """

    def __call__(
        self, node: astx.AST, operation: str, value: ir.Value
    ) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          operation:
            type: str
          value:
            type: ir.Value
        """
        del node, operation, value
        raise NotImplementedError


@private
@runtime_checkable
class ClassPinCallback(Protocol):
    """
    title: Typed cross-feature operation class_pin.
    """

    def __call__(self, node: astx.AST, value: ir.Value) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
        """
        del node, value
        raise NotImplementedError


@private
@runtime_checkable
class ClassRawCallback(Protocol):
    """
    title: Typed cross-feature operation class_raw.
    """

    def __call__(self, value: ir.Value) -> ir.Value:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          value:
            type: ir.Value
        returns:
          type: ir.Value
        """
        del value
        raise NotImplementedError


@private
@runtime_checkable
class CreateEntryBlockAllocaCallback(Protocol):
    """
    title: Typed cross-feature operation create_entry_block_alloca.
    """

    def __call__(self, var_name: str, type_name: str | ir.Type) -> ir.Value:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          var_name:
            type: str
          type_name:
            type: str | ir.Type
        returns:
          type: ir.Value
        """
        del var_name, type_name
        raise NotImplementedError


@private
@runtime_checkable
class CreateNativeFileCallback(Protocol):
    """
    title: Typed cross-feature operation create_native_file.
    """

    def __call__(
        self,
        node: astx.AST,
        resolution: ResolvedFileOpen,
        values: list[ir.Value],
        *,
        cleanup_temporaries: bool = False,
    ) -> ir.Value:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          resolution:
            type: ResolvedFileOpen
          values:
            type: list[ir.Value]
          cleanup_temporaries:
            type: bool
        returns:
          type: ir.Value
        """
        del node, resolution, values, cleanup_temporaries
        raise NotImplementedError


@private
@runtime_checkable
class ExceptionStringCallback(Protocol):
    """
    title: Typed cross-feature operation exception_string.
    """

    def __call__(self, value: str) -> ir.Value:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          value:
            type: str
        returns:
          type: ir.Value
        """
        del value
        raise NotImplementedError


@private
@runtime_checkable
class FatalStatusCallback(Protocol):
    """
    title: Typed cross-feature operation fatal_status.
    """

    def __call__(
        self,
        node: astx.AST,
        status: ir.Value,
        *,
        location: list[ir.Value] | None = None,
    ) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          status:
            type: ir.Value
          location:
            type: list[ir.Value] | None
        """
        del node, status, location
        raise NotImplementedError


@private
@runtime_checkable
class FileCheckCallback(Protocol):
    """
    title: Typed cross-feature operation file_check.
    """

    def __call__(
        self,
        node: astx.AST,
        status: ir.Value,
        error: ir.Value,
        *,
        code: str = "ARX-RUNTIME-FILE-001",
        cleanup_temporaries: bool = False,
    ) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          status:
            type: ir.Value
          error:
            type: ir.Value
          code:
            type: str
          cleanup_temporaries:
            type: bool
        """
        del node, status, error, code, cleanup_temporaries
        raise NotImplementedError


@private
@runtime_checkable
class FileCleanupCallback(Protocol):
    """
    title: Typed cross-feature operation file_cleanup.
    """

    def __call__(
        self, node: astx.AST, handle: ir.Value, owner_id: str | None
    ) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          handle:
            type: ir.Value
          owner_id:
            type: str | None
        """
        del node, handle, owner_id
        raise NotImplementedError


@private
@runtime_checkable
class FileErrorBufferCallback(Protocol):
    """
    title: Typed cross-feature operation file_error_buffer.
    """

    def __call__(self) -> ir.Value:
        """
        title: Invoke the required phase-owned operation.
        returns:
          type: ir.Value
        """
        raise NotImplementedError


@private
@runtime_checkable
class InitializeExceptionRecordCallback(Protocol):
    """
    title: Typed cross-feature operation initialize_exception_record.
    """

    def __call__(
        self,
        node: astx.AST,
        payload: ir.Value,
        exception: ResolvedExceptionType,
        *,
        location: list[ir.Value] | None = None,
    ) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          payload:
            type: ir.Value
          exception:
            type: ResolvedExceptionType
          location:
            type: list[ir.Value] | None
        """
        del node, payload, exception, location
        raise NotImplementedError


@private
@runtime_checkable
class LlvmFunctionNameForNodeCallback(Protocol):
    """
    title: Typed cross-feature operation llvm_function_name_for_node.
    """

    def __call__(self, node: astx.AST) -> str:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
        returns:
          type: str
        """
        del node
        raise NotImplementedError


@private
@runtime_checkable
class LowerBoundCallArgumentsCallback(Protocol):
    """
    title: Typed cross-feature operation lower_bound_call_arguments.
    """

    def __call__(
        self,
        resolution: CallResolution,
        *,
        receiver_value: ir.Value | None = None,
    ) -> list[ir.Value]:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          resolution:
            type: CallResolution
          receiver_value:
            type: ir.Value | None
        returns:
          type: list[ir.Value]
        """
        del resolution, receiver_value
        raise NotImplementedError


@private
@runtime_checkable
class LowerBufferByteOffsetCallback(Protocol):
    """
    title: Typed cross-feature operation lower_buffer_byte_offset.
    """

    def __call__(
        self,
        view: ir.Value,
        indices: list[ir.Value],
        *,
        index_nodes: list[astx.AST],
        node: astx.AST,
        element_size: int = 1,
        bounds_policy: BufferIndexBoundsPolicy = (
            BufferIndexBoundsPolicy.DEFAULT
        ),
    ) -> ir.Value:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          view:
            type: ir.Value
          indices:
            type: list[ir.Value]
          index_nodes:
            type: list[astx.AST]
          node:
            type: astx.AST
          element_size:
            type: int
          bounds_policy:
            type: BufferIndexBoundsPolicy
        returns:
          type: ir.Value
        """
        del view, indices, index_nodes, node, element_size, bounds_policy
        raise NotImplementedError


@private
@runtime_checkable
class LowerBufferElementPointerCallback(Protocol):
    """
    title: Typed cross-feature operation lower_buffer_element_pointer.
    """

    def __call__(
        self,
        view: ir.Value,
        indices: list[ir.Value],
        element_type: astx.DataType,
        *,
        index_nodes: list[astx.AST],
        node: astx.AST,
        bounds_policy: BufferIndexBoundsPolicy = (
            BufferIndexBoundsPolicy.DEFAULT
        ),
    ) -> ir.Value:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          view:
            type: ir.Value
          indices:
            type: list[ir.Value]
          element_type:
            type: astx.DataType
          index_nodes:
            type: list[astx.AST]
          node:
            type: astx.AST
          bounds_policy:
            type: BufferIndexBoundsPolicy
        returns:
          type: ir.Value
        """
        del view, indices, element_type, index_nodes, node, bounds_policy
        raise NotImplementedError


@private
@runtime_checkable
class LowerClassConstructCallback(Protocol):
    """
    title: Typed cross-feature operation lower_class_construct.
    """

    def __call__(
        self, node: astx.AST, resolution: ResolvedClassConstruction
    ) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
          resolution:
            type: ResolvedClassConstruction
        """
        del node, resolution
        raise NotImplementedError


@private
@runtime_checkable
class LowerColumnOperationCallback(Protocol):
    """
    title: Typed cross-feature operation lower_column_operation.
    """

    def __call__(self, node: astx.AST) -> bool:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.AST
        returns:
          type: bool
        """
        del node
        raise NotImplementedError


@private
@runtime_checkable
class LowerFileMethodCallback(Protocol):
    """
    title: Typed cross-feature operation lower_file_method.
    """

    def __call__(self, node: astx.MethodCall) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.MethodCall
        """
        del node
        raise NotImplementedError


@private
@runtime_checkable
class LowerFileOpenCallback(Protocol):
    """
    title: Typed cross-feature operation lower_file_open.
    """

    def __call__(self, node: astx.FunctionCall) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          node:
            type: astx.FunctionCall
        """
        del node
        raise NotImplementedError


@private
@runtime_checkable
class LowerStatementBlockCallback(Protocol):
    """
    title: Typed cross-feature operation lower_statement_block.
    """

    def __call__(
        self, block: astx.Block, *, preserve_scope: bool = False
    ) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          block:
            type: astx.Block
          preserve_scope:
            type: bool
        """
        del block, preserve_scope
        raise NotImplementedError


@private
@runtime_checkable
class RaiseRuntimeExceptionCallback(Protocol):
    """
    title: Typed cross-feature operation raise_runtime_exception.
    """

    def __call__(
        self, node: astx.AST, role: str, message: ir.Value, *, code: str
    ) -> None:
        """
        title: Invoke the required phase-owned operation.
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


@private
@runtime_checkable
class ReleaseNativeHandleCallback(Protocol):
    """
    title: Typed cross-feature operation release_native_handle.
    """

    def __call__(self, action: CleanupAction) -> None:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          action:
            type: CleanupAction
        """
        del action
        raise NotImplementedError


@private
@runtime_checkable
class RequireRuntimeSymbolCallback(Protocol):
    """
    title: Typed cross-feature operation require_runtime_symbol.
    """

    def __call__(self, feature_name: str, symbol_name: str) -> ir.Function:
        """
        title: Invoke the required phase-owned operation.
        parameters:
          feature_name:
            type: str
          symbol_name:
            type: str
        returns:
          type: ir.Function
        """
        del feature_name, symbol_name
        raise NotImplementedError


@private
@runtime_checkable
class TrackNativeHandleCallback(Protocol):
    """
    title: Typed cross-feature operation track_native_handle.
    """

    def __call__(
        self, node: astx.AST, feature: str, destroy: str, value: ir.Value
    ) -> CleanupAction:
        """
        title: Invoke the required phase-owned operation.
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


@private
@typechecked
@dataclass(frozen=True)
class ArrayServices:
    """
    title: Dependencies consumed by the array lowering family.
    attributes:
      llvm:
        type: VariablesLLVM
      function_state:
        type: FunctionValueState
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      visit_child:
        type: Callable[[astx.AST], None]
    """

    llvm: VariablesLLVM
    function_state: FunctionValueState
    require_runtime_symbol: RequireRuntimeSymbolCallback
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_array_services(
            self.llvm,
            self.function_state,
            self.require_runtime_symbol,
            self.visit_child,
        )


@private
@typechecked
def validate_array_services(
    llvm: VariablesLLVM,
    function_state: FunctionValueState,
    require_runtime_symbol: RequireRuntimeSymbolCallback,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected array dependency.
    parameters:
      llvm:
        type: VariablesLLVM
      function_state:
        type: FunctionValueState
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del llvm, function_state, require_runtime_symbol, visit_child


@private
@typechecked
@dataclass(frozen=True)
class ModuleServices:
    """
    title: Dependencies consumed by the modules lowering family.
    attributes:
      declare_semantic_function:
        type: DeclareSemanticFunctionCallback
      llvm:
        type: VariablesLLVM
      translate_modules:
        type: TranslateModulesCallback
      class_field_function:
        type: ClassFieldFunctionCallback
      module_state:
        type: ModuleEmissionState
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """

    declare_semantic_function: DeclareSemanticFunctionCallback
    llvm: VariablesLLVM
    translate_modules: TranslateModulesCallback
    class_field_function: ClassFieldFunctionCallback
    module_state: ModuleEmissionState
    types: TypeLowering
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_modules_services(
            self.declare_semantic_function,
            self.llvm,
            self.translate_modules,
            self.class_field_function,
            self.module_state,
            self.types,
            self.visit_child,
        )


@private
@typechecked
def validate_modules_services(
    declare_semantic_function: DeclareSemanticFunctionCallback,
    llvm: VariablesLLVM,
    translate_modules: TranslateModulesCallback,
    class_field_function: ClassFieldFunctionCallback,
    module_state: ModuleEmissionState,
    types: TypeLowering,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected modules dependency.
    parameters:
      declare_semantic_function:
        type: DeclareSemanticFunctionCallback
      llvm:
        type: VariablesLLVM
      translate_modules:
        type: TranslateModulesCallback
      class_field_function:
        type: ClassFieldFunctionCallback
      module_state:
        type: ModuleEmissionState
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        declare_semantic_function,
        llvm,
        translate_modules,
        class_field_function,
        module_state,
        types,
        visit_child,
    )


@private
@typechecked
@dataclass(frozen=True)
class ClassServices:
    """
    title: Dependencies consumed by the classes lowering family.
    attributes:
      declare_semantic_function:
        type: DeclareSemanticFunctionCallback
      default_runtime_initializer:
        type: DefaultRuntimeInitializerCallback
      llvm:
        type: VariablesLLVM
      cleanup:
        type: CleanupService
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      create_native_file:
        type: CreateNativeFileCallback
      exception_string:
        type: ExceptionStringCallback
      exceptions:
        type: ExceptionService
      exit_state:
        type: ExitState
      file_check:
        type: FileCheckCallback
      file_error_buffer:
        type: FileErrorBufferCallback
      function_state:
        type: FunctionValueState
      initialize_exception_record:
        type: InitializeExceptionRecordCallback
      layout:
        type: LayoutEmission
      numeric:
        type: NumericEmission
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      strings:
        type: StringEmission
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """

    declare_semantic_function: DeclareSemanticFunctionCallback
    default_runtime_initializer: DefaultRuntimeInitializerCallback
    llvm: VariablesLLVM
    cleanup: CleanupService
    create_entry_block_alloca: CreateEntryBlockAllocaCallback
    create_native_file: CreateNativeFileCallback
    exception_string: ExceptionStringCallback
    exceptions: ExceptionService
    exit_state: ExitState
    file_check: FileCheckCallback
    file_error_buffer: FileErrorBufferCallback
    function_state: FunctionValueState
    initialize_exception_record: InitializeExceptionRecordCallback
    layout: LayoutEmission
    numeric: NumericEmission
    require_runtime_symbol: RequireRuntimeSymbolCallback
    strings: StringEmission
    types: TypeLowering
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_classes_services(
            self.declare_semantic_function,
            self.default_runtime_initializer,
            self.llvm,
            self.cleanup,
            self.create_entry_block_alloca,
            self.create_native_file,
            self.exception_string,
            self.exceptions,
            self.exit_state,
            self.file_check,
            self.file_error_buffer,
            self.function_state,
            self.initialize_exception_record,
            self.layout,
            self.numeric,
            self.require_runtime_symbol,
            self.strings,
            self.types,
            self.visit_child,
        )


@private
@typechecked
def validate_classes_services(
    declare_semantic_function: DeclareSemanticFunctionCallback,
    default_runtime_initializer: DefaultRuntimeInitializerCallback,
    llvm: VariablesLLVM,
    cleanup: CleanupService,
    create_entry_block_alloca: CreateEntryBlockAllocaCallback,
    create_native_file: CreateNativeFileCallback,
    exception_string: ExceptionStringCallback,
    exceptions: ExceptionService,
    exit_state: ExitState,
    file_check: FileCheckCallback,
    file_error_buffer: FileErrorBufferCallback,
    function_state: FunctionValueState,
    initialize_exception_record: InitializeExceptionRecordCallback,
    layout: LayoutEmission,
    numeric: NumericEmission,
    require_runtime_symbol: RequireRuntimeSymbolCallback,
    strings: StringEmission,
    types: TypeLowering,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected classes dependency.
    parameters:
      declare_semantic_function:
        type: DeclareSemanticFunctionCallback
      default_runtime_initializer:
        type: DefaultRuntimeInitializerCallback
      llvm:
        type: VariablesLLVM
      cleanup:
        type: CleanupService
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      create_native_file:
        type: CreateNativeFileCallback
      exception_string:
        type: ExceptionStringCallback
      exceptions:
        type: ExceptionService
      exit_state:
        type: ExitState
      file_check:
        type: FileCheckCallback
      file_error_buffer:
        type: FileErrorBufferCallback
      function_state:
        type: FunctionValueState
      initialize_exception_record:
        type: InitializeExceptionRecordCallback
      layout:
        type: LayoutEmission
      numeric:
        type: NumericEmission
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      strings:
        type: StringEmission
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        declare_semantic_function,
        default_runtime_initializer,
        llvm,
        cleanup,
        create_entry_block_alloca,
        create_native_file,
        exception_string,
        exceptions,
        exit_state,
        file_check,
        file_error_buffer,
        function_state,
        initialize_exception_record,
        layout,
        numeric,
        require_runtime_symbol,
        strings,
        types,
        visit_child,
    )


@private
@typechecked
@dataclass(frozen=True)
class LiteralServices:
    """
    title: Dependencies consumed by the literals lowering family.
    attributes:
      collection:
        type: CollectionEmission
      empty_list_value_for_type:
        type: EmptyListValueForTypeCallback
      llvm:
        type: VariablesLLVM
      lower_list_subscript:
        type: LowerListSubscriptCallback
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      function_state:
        type: FunctionValueState
      lower_class_construct:
        type: LowerClassConstructCallback
      lower_column_operation:
        type: LowerColumnOperationCallback
      numeric:
        type: NumericEmission
      sequences:
        type: SequenceEmission
      strings:
        type: StringEmission
      text:
        type: TextEmission
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """

    collection: CollectionEmission
    empty_list_value_for_type: EmptyListValueForTypeCallback
    llvm: VariablesLLVM
    lower_list_subscript: LowerListSubscriptCallback
    create_entry_block_alloca: CreateEntryBlockAllocaCallback
    function_state: FunctionValueState
    lower_class_construct: LowerClassConstructCallback
    lower_column_operation: LowerColumnOperationCallback
    numeric: NumericEmission
    sequences: SequenceEmission
    strings: StringEmission
    text: TextEmission
    types: TypeLowering
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_literals_services(
            self.collection,
            self.empty_list_value_for_type,
            self.llvm,
            self.lower_list_subscript,
            self.create_entry_block_alloca,
            self.function_state,
            self.lower_class_construct,
            self.lower_column_operation,
            self.numeric,
            self.sequences,
            self.strings,
            self.text,
            self.types,
            self.visit_child,
        )


@private
@typechecked
def validate_literals_services(
    collection: CollectionEmission,
    empty_list_value_for_type: EmptyListValueForTypeCallback,
    llvm: VariablesLLVM,
    lower_list_subscript: LowerListSubscriptCallback,
    create_entry_block_alloca: CreateEntryBlockAllocaCallback,
    function_state: FunctionValueState,
    lower_class_construct: LowerClassConstructCallback,
    lower_column_operation: LowerColumnOperationCallback,
    numeric: NumericEmission,
    sequences: SequenceEmission,
    strings: StringEmission,
    text: TextEmission,
    types: TypeLowering,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected literals dependency.
    parameters:
      collection:
        type: CollectionEmission
      empty_list_value_for_type:
        type: EmptyListValueForTypeCallback
      llvm:
        type: VariablesLLVM
      lower_list_subscript:
        type: LowerListSubscriptCallback
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      function_state:
        type: FunctionValueState
      lower_class_construct:
        type: LowerClassConstructCallback
      lower_column_operation:
        type: LowerColumnOperationCallback
      numeric:
        type: NumericEmission
      sequences:
        type: SequenceEmission
      strings:
        type: StringEmission
      text:
        type: TextEmission
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        collection,
        empty_list_value_for_type,
        llvm,
        lower_list_subscript,
        create_entry_block_alloca,
        function_state,
        lower_class_construct,
        lower_column_operation,
        numeric,
        sequences,
        strings,
        text,
        types,
        visit_child,
    )


@private
@typechecked
@dataclass(frozen=True)
class BufferServices:
    """
    title: Dependencies consumed by the buffer lowering family.
    attributes:
      llvm:
        type: VariablesLLVM
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      function_state:
        type: FunctionValueState
      numeric:
        type: NumericEmission
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      sequences:
        type: SequenceEmission
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """

    llvm: VariablesLLVM
    create_entry_block_alloca: CreateEntryBlockAllocaCallback
    function_state: FunctionValueState
    numeric: NumericEmission
    require_runtime_symbol: RequireRuntimeSymbolCallback
    sequences: SequenceEmission
    types: TypeLowering
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_buffer_services(
            self.llvm,
            self.create_entry_block_alloca,
            self.function_state,
            self.numeric,
            self.require_runtime_symbol,
            self.sequences,
            self.types,
            self.visit_child,
        )


@private
@typechecked
def validate_buffer_services(
    llvm: VariablesLLVM,
    create_entry_block_alloca: CreateEntryBlockAllocaCallback,
    function_state: FunctionValueState,
    numeric: NumericEmission,
    require_runtime_symbol: RequireRuntimeSymbolCallback,
    sequences: SequenceEmission,
    types: TypeLowering,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected buffer dependency.
    parameters:
      llvm:
        type: VariablesLLVM
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      function_state:
        type: FunctionValueState
      numeric:
        type: NumericEmission
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      sequences:
        type: SequenceEmission
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        llvm,
        create_entry_block_alloca,
        function_state,
        numeric,
        require_runtime_symbol,
        sequences,
        types,
        visit_child,
    )


@private
@typechecked
@dataclass(frozen=True)
class CollectionServices:
    """
    title: Dependencies consumed by the collections lowering family.
    attributes:
      list_pointer_and_length_for_iteration:
        type: ListPointerAndLengthForIterationCallback
      list_pointer_for_call:
        type: ListPointerForCallCallback
      llvm:
        type: VariablesLLVM
      load_list_element_at_index:
        type: LoadListElementAtIndexCallback
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      function_state:
        type: FunctionValueState
      numeric:
        type: NumericEmission
      sequences:
        type: SequenceEmission
      strings:
        type: StringEmission
      text:
        type: TextEmission
      visit_child:
        type: Callable[[astx.AST], None]
    """

    list_pointer_and_length_for_iteration: (
        ListPointerAndLengthForIterationCallback
    )
    list_pointer_for_call: ListPointerForCallCallback
    llvm: VariablesLLVM
    load_list_element_at_index: LoadListElementAtIndexCallback
    create_entry_block_alloca: CreateEntryBlockAllocaCallback
    function_state: FunctionValueState
    numeric: NumericEmission
    sequences: SequenceEmission
    strings: StringEmission
    text: TextEmission
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_collections_services(
            self.list_pointer_and_length_for_iteration,
            self.list_pointer_for_call,
            self.llvm,
            self.load_list_element_at_index,
            self.create_entry_block_alloca,
            self.function_state,
            self.numeric,
            self.sequences,
            self.strings,
            self.text,
            self.visit_child,
        )


@private
@typechecked
def validate_collections_services(
    list_pointer_and_length_for_iteration: (
        ListPointerAndLengthForIterationCallback
    ),
    list_pointer_for_call: ListPointerForCallCallback,
    llvm: VariablesLLVM,
    load_list_element_at_index: LoadListElementAtIndexCallback,
    create_entry_block_alloca: CreateEntryBlockAllocaCallback,
    function_state: FunctionValueState,
    numeric: NumericEmission,
    sequences: SequenceEmission,
    strings: StringEmission,
    text: TextEmission,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected collections dependency.
    parameters:
      list_pointer_and_length_for_iteration:
        type: ListPointerAndLengthForIterationCallback
      list_pointer_for_call:
        type: ListPointerForCallCallback
      llvm:
        type: VariablesLLVM
      load_list_element_at_index:
        type: LoadListElementAtIndexCallback
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      function_state:
        type: FunctionValueState
      numeric:
        type: NumericEmission
      sequences:
        type: SequenceEmission
      strings:
        type: StringEmission
      text:
        type: TextEmission
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        list_pointer_and_length_for_iteration,
        list_pointer_for_call,
        llvm,
        load_list_element_at_index,
        create_entry_block_alloca,
        function_state,
        numeric,
        sequences,
        strings,
        text,
        visit_child,
    )


@private
@typechecked
@dataclass(frozen=True)
class VariableServices:
    """
    title: Dependencies consumed by the variables lowering family.
    attributes:
      empty_list_value_for_type:
        type: EmptyListValueForTypeCallback
      llvm:
        type: VariablesLLVM
      class_acquire:
        type: ClassAcquireCallback
      class_cleanup:
        type: ClassCleanupCallback
      class_field_value:
        type: ClassFieldValueCallback
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      exit_state:
        type: ExitState
      file_cleanup:
        type: FileCleanupCallback
      function_state:
        type: FunctionValueState
      generator_frame_state:
        type: GeneratorFrameState
      layout:
        type: LayoutEmission
      numeric:
        type: NumericEmission
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """

    empty_list_value_for_type: EmptyListValueForTypeCallback
    llvm: VariablesLLVM
    class_acquire: ClassAcquireCallback
    class_cleanup: ClassCleanupCallback
    class_field_value: ClassFieldValueCallback
    create_entry_block_alloca: CreateEntryBlockAllocaCallback
    exit_state: ExitState
    file_cleanup: FileCleanupCallback
    function_state: FunctionValueState
    generator_frame_state: GeneratorFrameState
    layout: LayoutEmission
    numeric: NumericEmission
    require_runtime_symbol: RequireRuntimeSymbolCallback
    types: TypeLowering
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_variables_services(
            self.empty_list_value_for_type,
            self.llvm,
            self.class_acquire,
            self.class_cleanup,
            self.class_field_value,
            self.create_entry_block_alloca,
            self.exit_state,
            self.file_cleanup,
            self.function_state,
            self.generator_frame_state,
            self.layout,
            self.numeric,
            self.require_runtime_symbol,
            self.types,
            self.visit_child,
        )


@private
@typechecked
def validate_variables_services(
    empty_list_value_for_type: EmptyListValueForTypeCallback,
    llvm: VariablesLLVM,
    class_acquire: ClassAcquireCallback,
    class_cleanup: ClassCleanupCallback,
    class_field_value: ClassFieldValueCallback,
    create_entry_block_alloca: CreateEntryBlockAllocaCallback,
    exit_state: ExitState,
    file_cleanup: FileCleanupCallback,
    function_state: FunctionValueState,
    generator_frame_state: GeneratorFrameState,
    layout: LayoutEmission,
    numeric: NumericEmission,
    require_runtime_symbol: RequireRuntimeSymbolCallback,
    types: TypeLowering,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected variables dependency.
    parameters:
      empty_list_value_for_type:
        type: EmptyListValueForTypeCallback
      llvm:
        type: VariablesLLVM
      class_acquire:
        type: ClassAcquireCallback
      class_cleanup:
        type: ClassCleanupCallback
      class_field_value:
        type: ClassFieldValueCallback
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      exit_state:
        type: ExitState
      file_cleanup:
        type: FileCleanupCallback
      function_state:
        type: FunctionValueState
      generator_frame_state:
        type: GeneratorFrameState
      layout:
        type: LayoutEmission
      numeric:
        type: NumericEmission
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        empty_list_value_for_type,
        llvm,
        class_acquire,
        class_cleanup,
        class_field_value,
        create_entry_block_alloca,
        exit_state,
        file_cleanup,
        function_state,
        generator_frame_state,
        layout,
        numeric,
        require_runtime_symbol,
        types,
        visit_child,
    )


@private
@typechecked
@dataclass(frozen=True)
class GeneratorServices:
    """
    title: Dependencies consumed by the generators lowering family.
    attributes:
      append_basic_blocks:
        type: AppendBasicBlocksCallback
      declare_semantic_function:
        type: DeclareSemanticFunctionCallback
      discard_child_results:
        type: DiscardChildResultsCallback
      module_state:
        type: ModuleEmissionState
      llvm:
        type: VariablesLLVM
      loop_scope:
        type: LoopScopeCallback
      temporary_named_value:
        type: TemporaryNamedValueCallback
      cleanup:
        type: CleanupService
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      exceptions:
        type: ExceptionService
      exit_state:
        type: ExitState
      fatal_status:
        type: FatalStatusCallback
      floating:
        type: FloatingEmission
      function_state:
        type: FunctionValueState
      generator_frame_state:
        type: GeneratorFrameState
      generator_module_state:
        type: GeneratorModuleState
      llvm_function_name_for_node:
        type: LlvmFunctionNameForNodeCallback
      numeric:
        type: NumericEmission
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """

    append_basic_blocks: AppendBasicBlocksCallback
    declare_semantic_function: DeclareSemanticFunctionCallback
    discard_child_results: DiscardChildResultsCallback
    module_state: ModuleEmissionState
    llvm: VariablesLLVM
    loop_scope: LoopScopeCallback
    temporary_named_value: TemporaryNamedValueCallback
    cleanup: CleanupService
    create_entry_block_alloca: CreateEntryBlockAllocaCallback
    exceptions: ExceptionService
    exit_state: ExitState
    fatal_status: FatalStatusCallback
    floating: FloatingEmission
    function_state: FunctionValueState
    generator_frame_state: GeneratorFrameState
    generator_module_state: GeneratorModuleState
    llvm_function_name_for_node: LlvmFunctionNameForNodeCallback
    numeric: NumericEmission
    types: TypeLowering
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_generators_services(
            self.append_basic_blocks,
            self.declare_semantic_function,
            self.discard_child_results,
            self.module_state,
            self.llvm,
            self.loop_scope,
            self.temporary_named_value,
            self.cleanup,
            self.create_entry_block_alloca,
            self.exceptions,
            self.exit_state,
            self.fatal_status,
            self.floating,
            self.function_state,
            self.generator_frame_state,
            self.generator_module_state,
            self.llvm_function_name_for_node,
            self.numeric,
            self.types,
            self.visit_child,
        )


@private
@typechecked
def validate_generators_services(
    append_basic_blocks: AppendBasicBlocksCallback,
    declare_semantic_function: DeclareSemanticFunctionCallback,
    discard_child_results: DiscardChildResultsCallback,
    module_state: ModuleEmissionState,
    llvm: VariablesLLVM,
    loop_scope: LoopScopeCallback,
    temporary_named_value: TemporaryNamedValueCallback,
    cleanup: CleanupService,
    create_entry_block_alloca: CreateEntryBlockAllocaCallback,
    exceptions: ExceptionService,
    exit_state: ExitState,
    fatal_status: FatalStatusCallback,
    floating: FloatingEmission,
    function_state: FunctionValueState,
    generator_frame_state: GeneratorFrameState,
    generator_module_state: GeneratorModuleState,
    llvm_function_name_for_node: LlvmFunctionNameForNodeCallback,
    numeric: NumericEmission,
    types: TypeLowering,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected generators dependency.
    parameters:
      append_basic_blocks:
        type: AppendBasicBlocksCallback
      declare_semantic_function:
        type: DeclareSemanticFunctionCallback
      discard_child_results:
        type: DiscardChildResultsCallback
      module_state:
        type: ModuleEmissionState
      llvm:
        type: VariablesLLVM
      loop_scope:
        type: LoopScopeCallback
      temporary_named_value:
        type: TemporaryNamedValueCallback
      cleanup:
        type: CleanupService
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      exceptions:
        type: ExceptionService
      exit_state:
        type: ExitState
      fatal_status:
        type: FatalStatusCallback
      floating:
        type: FloatingEmission
      function_state:
        type: FunctionValueState
      generator_frame_state:
        type: GeneratorFrameState
      generator_module_state:
        type: GeneratorModuleState
      llvm_function_name_for_node:
        type: LlvmFunctionNameForNodeCallback
      numeric:
        type: NumericEmission
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        append_basic_blocks,
        declare_semantic_function,
        discard_child_results,
        module_state,
        llvm,
        loop_scope,
        temporary_named_value,
        cleanup,
        create_entry_block_alloca,
        exceptions,
        exit_state,
        fatal_status,
        floating,
        function_state,
        generator_frame_state,
        generator_module_state,
        llvm_function_name_for_node,
        numeric,
        types,
        visit_child,
    )


@private
@typechecked
@dataclass(frozen=True)
class FunctionServices:
    """
    title: Dependencies consumed by the functions lowering family.
    attributes:
      emit_generator_stop:
        type: EmitGeneratorStopCallback
      module_state:
        type: ModuleEmissionState
      empty_list_value_for_type:
        type: EmptyListValueForTypeCallback
      llvm:
        type: VariablesLLVM
      lower_generator_function:
        type: LowerGeneratorFunctionCallback
      activate_runtime_feature:
        type: ActivateRuntimeFeatureCallback
      call_dispatch:
        type: ScopedDispatch
      call_services:
        type: CallLoweringServices
      class_acquire:
        type: ClassAcquireCallback
      class_cleanup:
        type: ClassCleanupCallback
      class_operation:
        type: ClassOperationCallback
      class_pin:
        type: ClassPinCallback
      cleanup:
        type: CleanupService
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      exception_module_state:
        type: ExceptionModuleState
      exceptions:
        type: ExceptionService
      exit_state:
        type: ExitState
      floating:
        type: FloatingEmission
      function_state:
        type: FunctionValueState
      generator_frame_state:
        type: GeneratorFrameState
      llvm_function_name_for_node:
        type: LlvmFunctionNameForNodeCallback
      lower_class_construct:
        type: LowerClassConstructCallback
      lower_file_method:
        type: LowerFileMethodCallback
      lower_file_open:
        type: LowerFileOpenCallback
      materialization:
        type: MaterializationEmission
      numeric:
        type: NumericEmission
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      runtime_features:
        type: RuntimeFeatureState
      sequences:
        type: SequenceEmission
      strings:
        type: StringEmission
      text:
        type: TextEmission
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """

    emit_generator_stop: EmitGeneratorStopCallback
    module_state: ModuleEmissionState
    empty_list_value_for_type: EmptyListValueForTypeCallback
    llvm: VariablesLLVM
    lower_generator_function: LowerGeneratorFunctionCallback
    activate_runtime_feature: ActivateRuntimeFeatureCallback
    call_dispatch: ScopedDispatch
    call_services: CallLoweringServices
    class_acquire: ClassAcquireCallback
    class_cleanup: ClassCleanupCallback
    class_operation: ClassOperationCallback
    class_pin: ClassPinCallback
    cleanup: CleanupService
    create_entry_block_alloca: CreateEntryBlockAllocaCallback
    exception_module_state: ExceptionModuleState
    exceptions: ExceptionService
    exit_state: ExitState
    floating: FloatingEmission
    function_state: FunctionValueState
    generator_frame_state: GeneratorFrameState
    llvm_function_name_for_node: LlvmFunctionNameForNodeCallback
    lower_class_construct: LowerClassConstructCallback
    lower_file_method: LowerFileMethodCallback
    lower_file_open: LowerFileOpenCallback
    materialization: MaterializationEmission
    numeric: NumericEmission
    require_runtime_symbol: RequireRuntimeSymbolCallback
    runtime_features: RuntimeFeatureState
    sequences: SequenceEmission
    strings: StringEmission
    text: TextEmission
    types: TypeLowering
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_functions_services(
            self.emit_generator_stop,
            self.module_state,
            self.empty_list_value_for_type,
            self.llvm,
            self.lower_generator_function,
            self.activate_runtime_feature,
            self.call_dispatch,
            self.call_services,
            self.class_acquire,
            self.class_cleanup,
            self.class_operation,
            self.class_pin,
            self.cleanup,
            self.create_entry_block_alloca,
            self.exception_module_state,
            self.exceptions,
            self.exit_state,
            self.floating,
            self.function_state,
            self.generator_frame_state,
            self.llvm_function_name_for_node,
            self.lower_class_construct,
            self.lower_file_method,
            self.lower_file_open,
            self.materialization,
            self.numeric,
            self.require_runtime_symbol,
            self.runtime_features,
            self.sequences,
            self.strings,
            self.text,
            self.types,
            self.visit_child,
        )


@private
@typechecked
def validate_functions_services(
    emit_generator_stop: EmitGeneratorStopCallback,
    module_state: ModuleEmissionState,
    empty_list_value_for_type: EmptyListValueForTypeCallback,
    llvm: VariablesLLVM,
    lower_generator_function: LowerGeneratorFunctionCallback,
    activate_runtime_feature: ActivateRuntimeFeatureCallback,
    call_dispatch: ScopedDispatch,
    call_services: CallLoweringServices,
    class_acquire: ClassAcquireCallback,
    class_cleanup: ClassCleanupCallback,
    class_operation: ClassOperationCallback,
    class_pin: ClassPinCallback,
    cleanup: CleanupService,
    create_entry_block_alloca: CreateEntryBlockAllocaCallback,
    exception_module_state: ExceptionModuleState,
    exceptions: ExceptionService,
    exit_state: ExitState,
    floating: FloatingEmission,
    function_state: FunctionValueState,
    generator_frame_state: GeneratorFrameState,
    llvm_function_name_for_node: LlvmFunctionNameForNodeCallback,
    lower_class_construct: LowerClassConstructCallback,
    lower_file_method: LowerFileMethodCallback,
    lower_file_open: LowerFileOpenCallback,
    materialization: MaterializationEmission,
    numeric: NumericEmission,
    require_runtime_symbol: RequireRuntimeSymbolCallback,
    runtime_features: RuntimeFeatureState,
    sequences: SequenceEmission,
    strings: StringEmission,
    text: TextEmission,
    types: TypeLowering,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected functions dependency.
    parameters:
      emit_generator_stop:
        type: EmitGeneratorStopCallback
      module_state:
        type: ModuleEmissionState
      empty_list_value_for_type:
        type: EmptyListValueForTypeCallback
      llvm:
        type: VariablesLLVM
      lower_generator_function:
        type: LowerGeneratorFunctionCallback
      activate_runtime_feature:
        type: ActivateRuntimeFeatureCallback
      call_dispatch:
        type: ScopedDispatch
      call_services:
        type: CallLoweringServices
      class_acquire:
        type: ClassAcquireCallback
      class_cleanup:
        type: ClassCleanupCallback
      class_operation:
        type: ClassOperationCallback
      class_pin:
        type: ClassPinCallback
      cleanup:
        type: CleanupService
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      exception_module_state:
        type: ExceptionModuleState
      exceptions:
        type: ExceptionService
      exit_state:
        type: ExitState
      floating:
        type: FloatingEmission
      function_state:
        type: FunctionValueState
      generator_frame_state:
        type: GeneratorFrameState
      llvm_function_name_for_node:
        type: LlvmFunctionNameForNodeCallback
      lower_class_construct:
        type: LowerClassConstructCallback
      lower_file_method:
        type: LowerFileMethodCallback
      lower_file_open:
        type: LowerFileOpenCallback
      materialization:
        type: MaterializationEmission
      numeric:
        type: NumericEmission
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      runtime_features:
        type: RuntimeFeatureState
      sequences:
        type: SequenceEmission
      strings:
        type: StringEmission
      text:
        type: TextEmission
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        emit_generator_stop,
        module_state,
        empty_list_value_for_type,
        llvm,
        lower_generator_function,
        activate_runtime_feature,
        call_dispatch,
        call_services,
        class_acquire,
        class_cleanup,
        class_operation,
        class_pin,
        cleanup,
        create_entry_block_alloca,
        exception_module_state,
        exceptions,
        exit_state,
        floating,
        function_state,
        generator_frame_state,
        llvm_function_name_for_node,
        lower_class_construct,
        lower_file_method,
        lower_file_open,
        materialization,
        numeric,
        require_runtime_symbol,
        runtime_features,
        sequences,
        strings,
        text,
        types,
        visit_child,
    )


@private
@typechecked
@dataclass(frozen=True)
class ExceptionServices:
    """
    title: Dependencies consumed by the exceptions lowering family.
    attributes:
      assert_source_name:
        type: AssertSourceNameCallback
      llvm:
        type: VariablesLLVM
      class_cleanup:
        type: ClassCleanupCallback
      class_drop_function:
        type: ClassDropFunctionCallback
      class_field_function:
        type: ClassFieldFunctionCallback
      class_operation:
        type: ClassOperationCallback
      class_pin:
        type: ClassPinCallback
      class_raw:
        type: ClassRawCallback
      cleanup:
        type: CleanupService
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      module_state:
        type: ModuleEmissionState
      exception_module_state:
        type: ExceptionModuleState
      exceptions:
        type: ExceptionService
      exit_state:
        type: ExitState
      file_error_buffer:
        type: FileErrorBufferCallback
      function_state:
        type: FunctionValueState
      lower_statement_block:
        type: LowerStatementBlockCallback
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      strings:
        type: StringEmission
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """

    assert_source_name: AssertSourceNameCallback
    llvm: VariablesLLVM
    class_cleanup: ClassCleanupCallback
    class_drop_function: ClassDropFunctionCallback
    class_field_function: ClassFieldFunctionCallback
    class_operation: ClassOperationCallback
    class_pin: ClassPinCallback
    class_raw: ClassRawCallback
    cleanup: CleanupService
    create_entry_block_alloca: CreateEntryBlockAllocaCallback
    module_state: ModuleEmissionState
    exception_module_state: ExceptionModuleState
    exceptions: ExceptionService
    exit_state: ExitState
    file_error_buffer: FileErrorBufferCallback
    function_state: FunctionValueState
    lower_statement_block: LowerStatementBlockCallback
    require_runtime_symbol: RequireRuntimeSymbolCallback
    strings: StringEmission
    types: TypeLowering
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_exceptions_services(
            self.assert_source_name,
            self.llvm,
            self.class_cleanup,
            self.class_drop_function,
            self.class_field_function,
            self.class_operation,
            self.class_pin,
            self.class_raw,
            self.cleanup,
            self.create_entry_block_alloca,
            self.module_state,
            self.exception_module_state,
            self.exceptions,
            self.exit_state,
            self.file_error_buffer,
            self.function_state,
            self.lower_statement_block,
            self.require_runtime_symbol,
            self.strings,
            self.types,
            self.visit_child,
        )


@private
@typechecked
def validate_exceptions_services(
    assert_source_name: AssertSourceNameCallback,
    llvm: VariablesLLVM,
    class_cleanup: ClassCleanupCallback,
    class_drop_function: ClassDropFunctionCallback,
    class_field_function: ClassFieldFunctionCallback,
    class_operation: ClassOperationCallback,
    class_pin: ClassPinCallback,
    class_raw: ClassRawCallback,
    cleanup: CleanupService,
    create_entry_block_alloca: CreateEntryBlockAllocaCallback,
    module_state: ModuleEmissionState,
    exception_module_state: ExceptionModuleState,
    exceptions: ExceptionService,
    exit_state: ExitState,
    file_error_buffer: FileErrorBufferCallback,
    function_state: FunctionValueState,
    lower_statement_block: LowerStatementBlockCallback,
    require_runtime_symbol: RequireRuntimeSymbolCallback,
    strings: StringEmission,
    types: TypeLowering,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected exceptions dependency.
    parameters:
      assert_source_name:
        type: AssertSourceNameCallback
      llvm:
        type: VariablesLLVM
      class_cleanup:
        type: ClassCleanupCallback
      class_drop_function:
        type: ClassDropFunctionCallback
      class_field_function:
        type: ClassFieldFunctionCallback
      class_operation:
        type: ClassOperationCallback
      class_pin:
        type: ClassPinCallback
      class_raw:
        type: ClassRawCallback
      cleanup:
        type: CleanupService
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      module_state:
        type: ModuleEmissionState
      exception_module_state:
        type: ExceptionModuleState
      exceptions:
        type: ExceptionService
      exit_state:
        type: ExitState
      file_error_buffer:
        type: FileErrorBufferCallback
      function_state:
        type: FunctionValueState
      lower_statement_block:
        type: LowerStatementBlockCallback
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      strings:
        type: StringEmission
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        assert_source_name,
        llvm,
        class_cleanup,
        class_drop_function,
        class_field_function,
        class_operation,
        class_pin,
        class_raw,
        cleanup,
        create_entry_block_alloca,
        module_state,
        exception_module_state,
        exceptions,
        exit_state,
        file_error_buffer,
        function_state,
        lower_statement_block,
        require_runtime_symbol,
        strings,
        types,
        visit_child,
    )


@private
@typechecked
@dataclass(frozen=True)
class TensorServices:
    """
    title: Dependencies consumed by the tensor lowering family.
    attributes:
      i64_array_pointer:
        type: I64ArrayPointerCallback
      llvm:
        type: VariablesLLVM
      lower_buffer_index_indices:
        type: LowerBufferIndexIndicesCallback
      check_arrow_status:
        type: CheckArrowStatusCallback
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      exit_state:
        type: ExitState
      function_state:
        type: FunctionValueState
      lower_buffer_byte_offset:
        type: LowerBufferByteOffsetCallback
      lower_buffer_element_pointer:
        type: LowerBufferElementPointerCallback
      numeric:
        type: NumericEmission
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      track_native_handle:
        type: TrackNativeHandleCallback
      visit_child:
        type: Callable[[astx.AST], None]
    """

    i64_array_pointer: I64ArrayPointerCallback
    llvm: VariablesLLVM
    lower_buffer_index_indices: LowerBufferIndexIndicesCallback
    check_arrow_status: CheckArrowStatusCallback
    create_entry_block_alloca: CreateEntryBlockAllocaCallback
    exit_state: ExitState
    function_state: FunctionValueState
    lower_buffer_byte_offset: LowerBufferByteOffsetCallback
    lower_buffer_element_pointer: LowerBufferElementPointerCallback
    numeric: NumericEmission
    require_runtime_symbol: RequireRuntimeSymbolCallback
    track_native_handle: TrackNativeHandleCallback
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_tensor_services(
            self.i64_array_pointer,
            self.llvm,
            self.lower_buffer_index_indices,
            self.check_arrow_status,
            self.create_entry_block_alloca,
            self.exit_state,
            self.function_state,
            self.lower_buffer_byte_offset,
            self.lower_buffer_element_pointer,
            self.numeric,
            self.require_runtime_symbol,
            self.track_native_handle,
            self.visit_child,
        )


@private
@typechecked
def validate_tensor_services(
    i64_array_pointer: I64ArrayPointerCallback,
    llvm: VariablesLLVM,
    lower_buffer_index_indices: LowerBufferIndexIndicesCallback,
    check_arrow_status: CheckArrowStatusCallback,
    create_entry_block_alloca: CreateEntryBlockAllocaCallback,
    exit_state: ExitState,
    function_state: FunctionValueState,
    lower_buffer_byte_offset: LowerBufferByteOffsetCallback,
    lower_buffer_element_pointer: LowerBufferElementPointerCallback,
    numeric: NumericEmission,
    require_runtime_symbol: RequireRuntimeSymbolCallback,
    track_native_handle: TrackNativeHandleCallback,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected tensor dependency.
    parameters:
      i64_array_pointer:
        type: I64ArrayPointerCallback
      llvm:
        type: VariablesLLVM
      lower_buffer_index_indices:
        type: LowerBufferIndexIndicesCallback
      check_arrow_status:
        type: CheckArrowStatusCallback
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      exit_state:
        type: ExitState
      function_state:
        type: FunctionValueState
      lower_buffer_byte_offset:
        type: LowerBufferByteOffsetCallback
      lower_buffer_element_pointer:
        type: LowerBufferElementPointerCallback
      numeric:
        type: NumericEmission
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      track_native_handle:
        type: TrackNativeHandleCallback
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        i64_array_pointer,
        llvm,
        lower_buffer_index_indices,
        check_arrow_status,
        create_entry_block_alloca,
        exit_state,
        function_state,
        lower_buffer_byte_offset,
        lower_buffer_element_pointer,
        numeric,
        require_runtime_symbol,
        track_native_handle,
        visit_child,
    )


@private
@typechecked
@dataclass(frozen=True)
class NullableServices:
    """
    title: Dependencies consumed by the nullable lowering family.
    attributes:
      llvm:
        type: VariablesLLVM
      arrow_temporary:
        type: ArrowTemporaryCallback
      check_arrow_status:
        type: CheckArrowStatusCallback
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      function_state:
        type: FunctionValueState
      numeric:
        type: NumericEmission
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      strings:
        type: StringEmission
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """

    llvm: VariablesLLVM
    arrow_temporary: ArrowTemporaryCallback
    check_arrow_status: CheckArrowStatusCallback
    create_entry_block_alloca: CreateEntryBlockAllocaCallback
    function_state: FunctionValueState
    numeric: NumericEmission
    require_runtime_symbol: RequireRuntimeSymbolCallback
    strings: StringEmission
    types: TypeLowering
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_nullable_services(
            self.llvm,
            self.arrow_temporary,
            self.check_arrow_status,
            self.create_entry_block_alloca,
            self.function_state,
            self.numeric,
            self.require_runtime_symbol,
            self.strings,
            self.types,
            self.visit_child,
        )


@private
@typechecked
def validate_nullable_services(
    llvm: VariablesLLVM,
    arrow_temporary: ArrowTemporaryCallback,
    check_arrow_status: CheckArrowStatusCallback,
    create_entry_block_alloca: CreateEntryBlockAllocaCallback,
    function_state: FunctionValueState,
    numeric: NumericEmission,
    require_runtime_symbol: RequireRuntimeSymbolCallback,
    strings: StringEmission,
    types: TypeLowering,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected nullable dependency.
    parameters:
      llvm:
        type: VariablesLLVM
      arrow_temporary:
        type: ArrowTemporaryCallback
      check_arrow_status:
        type: CheckArrowStatusCallback
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      function_state:
        type: FunctionValueState
      numeric:
        type: NumericEmission
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      strings:
        type: StringEmission
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        llvm,
        arrow_temporary,
        check_arrow_status,
        create_entry_block_alloca,
        function_state,
        numeric,
        require_runtime_symbol,
        strings,
        types,
        visit_child,
    )


@private
@typechecked
@dataclass(frozen=True)
class TemporalServices:
    """
    title: Dependencies consumed by the temporal lowering family.
    attributes:
      llvm:
        type: VariablesLLVM
      function_state:
        type: FunctionValueState
    """

    llvm: VariablesLLVM
    function_state: FunctionValueState

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_temporal_services(self.llvm, self.function_state)


@private
@typechecked
def validate_temporal_services(
    llvm: VariablesLLVM, function_state: FunctionValueState
) -> None:
    """
    title: Check every explicitly injected temporal dependency.
    parameters:
      llvm:
        type: VariablesLLVM
      function_state:
        type: FunctionValueState
    """
    del llvm, function_state


@private
@typechecked
@dataclass(frozen=True)
class FileServices:
    """
    title: Dependencies consumed by the file lowering family.
    attributes:
      empty_list_value:
        type: EmptyListValueCallback
      llvm:
        type: VariablesLLVM
      llvm_list_type:
        type: LlvmListTypeCallback
      class_operation:
        type: ClassOperationCallback
      class_pin:
        type: ClassPinCallback
      cleanup:
        type: CleanupService
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      exceptions:
        type: ExceptionService
      exit_state:
        type: ExitState
      fatal_status:
        type: FatalStatusCallback
      function_state:
        type: FunctionValueState
      lower_bound_call_arguments:
        type: LowerBoundCallArgumentsCallback
      raise_runtime_exception:
        type: RaiseRuntimeExceptionCallback
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      strings:
        type: StringEmission
      visit_child:
        type: Callable[[astx.AST], None]
    """

    empty_list_value: EmptyListValueCallback
    llvm: VariablesLLVM
    llvm_list_type: LlvmListTypeCallback
    class_operation: ClassOperationCallback
    class_pin: ClassPinCallback
    cleanup: CleanupService
    create_entry_block_alloca: CreateEntryBlockAllocaCallback
    exceptions: ExceptionService
    exit_state: ExitState
    fatal_status: FatalStatusCallback
    function_state: FunctionValueState
    lower_bound_call_arguments: LowerBoundCallArgumentsCallback
    raise_runtime_exception: RaiseRuntimeExceptionCallback
    require_runtime_symbol: RequireRuntimeSymbolCallback
    strings: StringEmission
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_file_services(
            self.empty_list_value,
            self.llvm,
            self.llvm_list_type,
            self.class_operation,
            self.class_pin,
            self.cleanup,
            self.create_entry_block_alloca,
            self.exceptions,
            self.exit_state,
            self.fatal_status,
            self.function_state,
            self.lower_bound_call_arguments,
            self.raise_runtime_exception,
            self.require_runtime_symbol,
            self.strings,
            self.visit_child,
        )


@private
@typechecked
def validate_file_services(
    empty_list_value: EmptyListValueCallback,
    llvm: VariablesLLVM,
    llvm_list_type: LlvmListTypeCallback,
    class_operation: ClassOperationCallback,
    class_pin: ClassPinCallback,
    cleanup: CleanupService,
    create_entry_block_alloca: CreateEntryBlockAllocaCallback,
    exceptions: ExceptionService,
    exit_state: ExitState,
    fatal_status: FatalStatusCallback,
    function_state: FunctionValueState,
    lower_bound_call_arguments: LowerBoundCallArgumentsCallback,
    raise_runtime_exception: RaiseRuntimeExceptionCallback,
    require_runtime_symbol: RequireRuntimeSymbolCallback,
    strings: StringEmission,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected file dependency.
    parameters:
      empty_list_value:
        type: EmptyListValueCallback
      llvm:
        type: VariablesLLVM
      llvm_list_type:
        type: LlvmListTypeCallback
      class_operation:
        type: ClassOperationCallback
      class_pin:
        type: ClassPinCallback
      cleanup:
        type: CleanupService
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      exceptions:
        type: ExceptionService
      exit_state:
        type: ExitState
      fatal_status:
        type: FatalStatusCallback
      function_state:
        type: FunctionValueState
      lower_bound_call_arguments:
        type: LowerBoundCallArgumentsCallback
      raise_runtime_exception:
        type: RaiseRuntimeExceptionCallback
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      strings:
        type: StringEmission
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        empty_list_value,
        llvm,
        llvm_list_type,
        class_operation,
        class_pin,
        cleanup,
        create_entry_block_alloca,
        exceptions,
        exit_state,
        fatal_status,
        function_state,
        lower_bound_call_arguments,
        raise_runtime_exception,
        require_runtime_symbol,
        strings,
        visit_child,
    )


@private
@typechecked
@dataclass(frozen=True)
class DataFrameServices:
    """
    title: Dependencies consumed by the dataframe lowering family.
    attributes:
      llvm:
        type: VariablesLLVM
      arrow_explicit_lifetime:
        type: ArrowExplicitLifetimeCallback
      arrow_temporary:
        type: ArrowTemporaryCallback
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      exit_state:
        type: ExitState
      fatal_status:
        type: FatalStatusCallback
      function_state:
        type: FunctionValueState
      numeric:
        type: NumericEmission
      raise_runtime_exception:
        type: RaiseRuntimeExceptionCallback
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      strings:
        type: StringEmission
      visit_child:
        type: Callable[[astx.AST], None]
    """

    llvm: VariablesLLVM
    arrow_explicit_lifetime: ArrowExplicitLifetimeCallback
    arrow_temporary: ArrowTemporaryCallback
    create_entry_block_alloca: CreateEntryBlockAllocaCallback
    exit_state: ExitState
    fatal_status: FatalStatusCallback
    function_state: FunctionValueState
    numeric: NumericEmission
    raise_runtime_exception: RaiseRuntimeExceptionCallback
    require_runtime_symbol: RequireRuntimeSymbolCallback
    strings: StringEmission
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_dataframe_services(
            self.llvm,
            self.arrow_explicit_lifetime,
            self.arrow_temporary,
            self.create_entry_block_alloca,
            self.exit_state,
            self.fatal_status,
            self.function_state,
            self.numeric,
            self.raise_runtime_exception,
            self.require_runtime_symbol,
            self.strings,
            self.visit_child,
        )


@private
@typechecked
def validate_dataframe_services(
    llvm: VariablesLLVM,
    arrow_explicit_lifetime: ArrowExplicitLifetimeCallback,
    arrow_temporary: ArrowTemporaryCallback,
    create_entry_block_alloca: CreateEntryBlockAllocaCallback,
    exit_state: ExitState,
    fatal_status: FatalStatusCallback,
    function_state: FunctionValueState,
    numeric: NumericEmission,
    raise_runtime_exception: RaiseRuntimeExceptionCallback,
    require_runtime_symbol: RequireRuntimeSymbolCallback,
    strings: StringEmission,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected dataframe dependency.
    parameters:
      llvm:
        type: VariablesLLVM
      arrow_explicit_lifetime:
        type: ArrowExplicitLifetimeCallback
      arrow_temporary:
        type: ArrowTemporaryCallback
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      exit_state:
        type: ExitState
      fatal_status:
        type: FatalStatusCallback
      function_state:
        type: FunctionValueState
      numeric:
        type: NumericEmission
      raise_runtime_exception:
        type: RaiseRuntimeExceptionCallback
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      strings:
        type: StringEmission
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        llvm,
        arrow_explicit_lifetime,
        arrow_temporary,
        create_entry_block_alloca,
        exit_state,
        fatal_status,
        function_state,
        numeric,
        raise_runtime_exception,
        require_runtime_symbol,
        strings,
        visit_child,
    )


@private
@typechecked
@dataclass(frozen=True)
class ListServices:
    """
    title: Dependencies consumed by the list lowering family.
    attributes:
      llvm:
        type: VariablesLLVM
      lower_boolean_condition:
        type: LowerBooleanConditionCallback
      register_owned_string_cleanup:
        type: RegisterOwnedStringCleanupCallback
      temporary_named_value:
        type: TemporaryNamedValueCallback
      cleanup:
        type: CleanupService
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      exit_state:
        type: ExitState
      function_state:
        type: FunctionValueState
      layout:
        type: LayoutEmission
      numeric:
        type: NumericEmission
      raise_runtime_exception:
        type: RaiseRuntimeExceptionCallback
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      strings:
        type: StringEmission
      target_machine:
        type: TargetMachine
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """

    llvm: VariablesLLVM
    lower_boolean_condition: LowerBooleanConditionCallback
    register_owned_string_cleanup: RegisterOwnedStringCleanupCallback
    temporary_named_value: TemporaryNamedValueCallback
    cleanup: CleanupService
    create_entry_block_alloca: CreateEntryBlockAllocaCallback
    exit_state: ExitState
    function_state: FunctionValueState
    layout: LayoutEmission
    numeric: NumericEmission
    raise_runtime_exception: RaiseRuntimeExceptionCallback
    require_runtime_symbol: RequireRuntimeSymbolCallback
    strings: StringEmission
    target_machine: TargetMachine
    types: TypeLowering
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_list_services(
            self.llvm,
            self.lower_boolean_condition,
            self.register_owned_string_cleanup,
            self.temporary_named_value,
            self.cleanup,
            self.create_entry_block_alloca,
            self.exit_state,
            self.function_state,
            self.layout,
            self.numeric,
            self.raise_runtime_exception,
            self.require_runtime_symbol,
            self.strings,
            self.target_machine,
            self.types,
            self.visit_child,
        )


@private
@typechecked
def validate_list_services(
    llvm: VariablesLLVM,
    lower_boolean_condition: LowerBooleanConditionCallback,
    register_owned_string_cleanup: RegisterOwnedStringCleanupCallback,
    temporary_named_value: TemporaryNamedValueCallback,
    cleanup: CleanupService,
    create_entry_block_alloca: CreateEntryBlockAllocaCallback,
    exit_state: ExitState,
    function_state: FunctionValueState,
    layout: LayoutEmission,
    numeric: NumericEmission,
    raise_runtime_exception: RaiseRuntimeExceptionCallback,
    require_runtime_symbol: RequireRuntimeSymbolCallback,
    strings: StringEmission,
    target_machine: TargetMachine,
    types: TypeLowering,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected list dependency.
    parameters:
      llvm:
        type: VariablesLLVM
      lower_boolean_condition:
        type: LowerBooleanConditionCallback
      register_owned_string_cleanup:
        type: RegisterOwnedStringCleanupCallback
      temporary_named_value:
        type: TemporaryNamedValueCallback
      cleanup:
        type: CleanupService
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      exit_state:
        type: ExitState
      function_state:
        type: FunctionValueState
      layout:
        type: LayoutEmission
      numeric:
        type: NumericEmission
      raise_runtime_exception:
        type: RaiseRuntimeExceptionCallback
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      strings:
        type: StringEmission
      target_machine:
        type: TargetMachine
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        llvm,
        lower_boolean_condition,
        register_owned_string_cleanup,
        temporary_named_value,
        cleanup,
        create_entry_block_alloca,
        exit_state,
        function_state,
        layout,
        numeric,
        raise_runtime_exception,
        require_runtime_symbol,
        strings,
        target_machine,
        types,
        visit_child,
    )


@private
@typechecked
@dataclass(frozen=True)
class UnaryServices:
    """
    title: Dependencies consumed by the unary_ops lowering family.
    attributes:
      llvm:
        type: VariablesLLVM
      function_state:
        type: FunctionValueState
      layout:
        type: LayoutEmission
      lower_column_operation:
        type: LowerColumnOperationCallback
      numeric:
        type: NumericEmission
      visit_child:
        type: Callable[[astx.AST], None]
    """

    llvm: VariablesLLVM
    function_state: FunctionValueState
    layout: LayoutEmission
    lower_column_operation: LowerColumnOperationCallback
    numeric: NumericEmission
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_unary_ops_services(
            self.llvm,
            self.function_state,
            self.layout,
            self.lower_column_operation,
            self.numeric,
            self.visit_child,
        )


@private
@typechecked
def validate_unary_ops_services(
    llvm: VariablesLLVM,
    function_state: FunctionValueState,
    layout: LayoutEmission,
    lower_column_operation: LowerColumnOperationCallback,
    numeric: NumericEmission,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected unary_ops dependency.
    parameters:
      llvm:
        type: VariablesLLVM
      function_state:
        type: FunctionValueState
      layout:
        type: LayoutEmission
      lower_column_operation:
        type: LowerColumnOperationCallback
      numeric:
        type: NumericEmission
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        llvm,
        function_state,
        layout,
        lower_column_operation,
        numeric,
        visit_child,
    )


@private
@typechecked
@dataclass(frozen=True)
class SystemServices:
    """
    title: Dependencies consumed by the system lowering family.
    attributes:
      llvm:
        type: VariablesLLVM
      arrow_temporary:
        type: ArrowTemporaryCallback
      checked_native_call:
        type: CheckedNativeCallCallback
      class_operation:
        type: ClassOperationCallback
      cleanup:
        type: CleanupService
      function_state:
        type: FunctionValueState
      lower_class_construct:
        type: LowerClassConstructCallback
      numeric:
        type: NumericEmission
      release_native_handle:
        type: ReleaseNativeHandleCallback
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      strings:
        type: StringEmission
      track_native_handle:
        type: TrackNativeHandleCallback
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """

    llvm: VariablesLLVM
    arrow_temporary: ArrowTemporaryCallback
    checked_native_call: CheckedNativeCallCallback
    class_operation: ClassOperationCallback
    cleanup: CleanupService
    function_state: FunctionValueState
    lower_class_construct: LowerClassConstructCallback
    numeric: NumericEmission
    release_native_handle: ReleaseNativeHandleCallback
    require_runtime_symbol: RequireRuntimeSymbolCallback
    strings: StringEmission
    track_native_handle: TrackNativeHandleCallback
    types: TypeLowering
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_system_services(
            self.llvm,
            self.arrow_temporary,
            self.checked_native_call,
            self.class_operation,
            self.cleanup,
            self.function_state,
            self.lower_class_construct,
            self.numeric,
            self.release_native_handle,
            self.require_runtime_symbol,
            self.strings,
            self.track_native_handle,
            self.types,
            self.visit_child,
        )


@private
@typechecked
def validate_system_services(
    llvm: VariablesLLVM,
    arrow_temporary: ArrowTemporaryCallback,
    checked_native_call: CheckedNativeCallCallback,
    class_operation: ClassOperationCallback,
    cleanup: CleanupService,
    function_state: FunctionValueState,
    lower_class_construct: LowerClassConstructCallback,
    numeric: NumericEmission,
    release_native_handle: ReleaseNativeHandleCallback,
    require_runtime_symbol: RequireRuntimeSymbolCallback,
    strings: StringEmission,
    track_native_handle: TrackNativeHandleCallback,
    types: TypeLowering,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected system dependency.
    parameters:
      llvm:
        type: VariablesLLVM
      arrow_temporary:
        type: ArrowTemporaryCallback
      checked_native_call:
        type: CheckedNativeCallCallback
      class_operation:
        type: ClassOperationCallback
      cleanup:
        type: CleanupService
      function_state:
        type: FunctionValueState
      lower_class_construct:
        type: LowerClassConstructCallback
      numeric:
        type: NumericEmission
      release_native_handle:
        type: ReleaseNativeHandleCallback
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      strings:
        type: StringEmission
      track_native_handle:
        type: TrackNativeHandleCallback
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        llvm,
        arrow_temporary,
        checked_native_call,
        class_operation,
        cleanup,
        function_state,
        lower_class_construct,
        numeric,
        release_native_handle,
        require_runtime_symbol,
        strings,
        track_native_handle,
        types,
        visit_child,
    )


@private
@typechecked
@dataclass(frozen=True)
class ControlFlowServices:
    """
    title: Dependencies consumed by the control_flow lowering family.
    attributes:
      apply_calling_convention:
        type: ApplyCallingConventionCallback
      module_state:
        type: ModuleEmissionState
      declare_semantic_function:
        type: DeclareSemanticFunctionCallback
      indirect_method_callee:
        type: IndirectMethodCalleeCallback
      list_pointer_and_length_for_iteration:
        type: ListPointerAndLengthForIterationCallback
      llvm:
        type: VariablesLLVM
      load_list_element_at_index:
        type: LoadListElementAtIndexCallback
      lower_generator_for_in_loop:
        type: LowerGeneratorForInLoopCallback
      register_owned_string_cleanup:
        type: RegisterOwnedStringCleanupCallback
      resolved_iteration:
        type: ResolvedIterationCallback
      cleanup:
        type: CleanupService
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      exceptions:
        type: ExceptionService
      exit_state:
        type: ExitState
      function_state:
        type: FunctionValueState
      lower_bound_call_arguments:
        type: LowerBoundCallArgumentsCallback
      numeric:
        type: NumericEmission
      raise_runtime_exception:
        type: RaiseRuntimeExceptionCallback
      sequences:
        type: SequenceEmission
      strings:
        type: StringEmission
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """

    apply_calling_convention: ApplyCallingConventionCallback
    module_state: ModuleEmissionState
    declare_semantic_function: DeclareSemanticFunctionCallback
    indirect_method_callee: IndirectMethodCalleeCallback
    list_pointer_and_length_for_iteration: (
        ListPointerAndLengthForIterationCallback
    )
    llvm: VariablesLLVM
    load_list_element_at_index: LoadListElementAtIndexCallback
    lower_generator_for_in_loop: LowerGeneratorForInLoopCallback
    register_owned_string_cleanup: RegisterOwnedStringCleanupCallback
    resolved_iteration: ResolvedIterationCallback
    cleanup: CleanupService
    create_entry_block_alloca: CreateEntryBlockAllocaCallback
    exceptions: ExceptionService
    exit_state: ExitState
    function_state: FunctionValueState
    lower_bound_call_arguments: LowerBoundCallArgumentsCallback
    numeric: NumericEmission
    raise_runtime_exception: RaiseRuntimeExceptionCallback
    sequences: SequenceEmission
    strings: StringEmission
    types: TypeLowering
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_control_flow_services(
            self.apply_calling_convention,
            self.module_state,
            self.declare_semantic_function,
            self.indirect_method_callee,
            self.list_pointer_and_length_for_iteration,
            self.llvm,
            self.load_list_element_at_index,
            self.lower_generator_for_in_loop,
            self.register_owned_string_cleanup,
            self.resolved_iteration,
            self.cleanup,
            self.create_entry_block_alloca,
            self.exceptions,
            self.exit_state,
            self.function_state,
            self.lower_bound_call_arguments,
            self.numeric,
            self.raise_runtime_exception,
            self.sequences,
            self.strings,
            self.types,
            self.visit_child,
        )


@private
@typechecked
def validate_control_flow_services(
    apply_calling_convention: ApplyCallingConventionCallback,
    module_state: ModuleEmissionState,
    declare_semantic_function: DeclareSemanticFunctionCallback,
    indirect_method_callee: IndirectMethodCalleeCallback,
    list_pointer_and_length_for_iteration: (
        ListPointerAndLengthForIterationCallback
    ),
    llvm: VariablesLLVM,
    load_list_element_at_index: LoadListElementAtIndexCallback,
    lower_generator_for_in_loop: LowerGeneratorForInLoopCallback,
    register_owned_string_cleanup: RegisterOwnedStringCleanupCallback,
    resolved_iteration: ResolvedIterationCallback,
    cleanup: CleanupService,
    create_entry_block_alloca: CreateEntryBlockAllocaCallback,
    exceptions: ExceptionService,
    exit_state: ExitState,
    function_state: FunctionValueState,
    lower_bound_call_arguments: LowerBoundCallArgumentsCallback,
    numeric: NumericEmission,
    raise_runtime_exception: RaiseRuntimeExceptionCallback,
    sequences: SequenceEmission,
    strings: StringEmission,
    types: TypeLowering,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected control_flow dependency.
    parameters:
      apply_calling_convention:
        type: ApplyCallingConventionCallback
      module_state:
        type: ModuleEmissionState
      declare_semantic_function:
        type: DeclareSemanticFunctionCallback
      indirect_method_callee:
        type: IndirectMethodCalleeCallback
      list_pointer_and_length_for_iteration:
        type: ListPointerAndLengthForIterationCallback
      llvm:
        type: VariablesLLVM
      load_list_element_at_index:
        type: LoadListElementAtIndexCallback
      lower_generator_for_in_loop:
        type: LowerGeneratorForInLoopCallback
      register_owned_string_cleanup:
        type: RegisterOwnedStringCleanupCallback
      resolved_iteration:
        type: ResolvedIterationCallback
      cleanup:
        type: CleanupService
      create_entry_block_alloca:
        type: CreateEntryBlockAllocaCallback
      exceptions:
        type: ExceptionService
      exit_state:
        type: ExitState
      function_state:
        type: FunctionValueState
      lower_bound_call_arguments:
        type: LowerBoundCallArgumentsCallback
      numeric:
        type: NumericEmission
      raise_runtime_exception:
        type: RaiseRuntimeExceptionCallback
      sequences:
        type: SequenceEmission
      strings:
        type: StringEmission
      types:
        type: TypeLowering
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        apply_calling_convention,
        module_state,
        declare_semantic_function,
        indirect_method_callee,
        list_pointer_and_length_for_iteration,
        llvm,
        load_list_element_at_index,
        lower_generator_for_in_loop,
        register_owned_string_cleanup,
        resolved_iteration,
        cleanup,
        create_entry_block_alloca,
        exceptions,
        exit_state,
        function_state,
        lower_bound_call_arguments,
        numeric,
        raise_runtime_exception,
        sequences,
        strings,
        types,
        visit_child,
    )


@private
@typechecked
@dataclass(frozen=True)
class BinaryServices:
    """
    title: Dependencies consumed by the binary_ops lowering family.
    attributes:
      floating:
        type: FloatingEmission
      destroy_replaced_list:
        type: DestroyReplacedListCallback
      destroy_replaced_string:
        type: DestroyReplacedStringCallback
      llvm:
        type: VariablesLLVM
      collection:
        type: CollectionEmission
      arrow_reference_count:
        type: ArrowReferenceCountCallback
      arrow_release_binding:
        type: ArrowReleaseBindingCallback
      class_acquire:
        type: ClassAcquireCallback
      class_operation:
        type: ClassOperationCallback
      cleanup:
        type: CleanupService
      function_state:
        type: FunctionValueState
      guards:
        type: RuntimeGuardService
      layout:
        type: LayoutEmission
      lower_column_operation:
        type: LowerColumnOperationCallback
      numeric:
        type: NumericEmission
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      runtime_features:
        type: RuntimeFeatureState
      strings:
        type: StringEmission
      visit_child:
        type: Callable[[astx.AST], None]
    """

    floating: FloatingEmission
    destroy_replaced_list: DestroyReplacedListCallback
    destroy_replaced_string: DestroyReplacedStringCallback
    llvm: VariablesLLVM
    collection: CollectionEmission
    arrow_reference_count: ArrowReferenceCountCallback
    arrow_release_binding: ArrowReleaseBindingCallback
    class_acquire: ClassAcquireCallback
    class_operation: ClassOperationCallback
    cleanup: CleanupService
    function_state: FunctionValueState
    guards: RuntimeGuardService
    layout: LayoutEmission
    lower_column_operation: LowerColumnOperationCallback
    numeric: NumericEmission
    require_runtime_symbol: RequireRuntimeSymbolCallback
    runtime_features: RuntimeFeatureState
    strings: StringEmission
    visit_child: Callable[[astx.AST], None]

    def __post_init__(self) -> None:
        """
        title: Validate injected services at the composition boundary.
        """
        validate_binary_ops_services(
            self.floating,
            self.destroy_replaced_list,
            self.destroy_replaced_string,
            self.llvm,
            self.collection,
            self.arrow_reference_count,
            self.arrow_release_binding,
            self.class_acquire,
            self.class_operation,
            self.cleanup,
            self.function_state,
            self.guards,
            self.layout,
            self.lower_column_operation,
            self.numeric,
            self.require_runtime_symbol,
            self.runtime_features,
            self.strings,
            self.visit_child,
        )


@private
@typechecked
def validate_binary_ops_services(
    floating: FloatingEmission,
    destroy_replaced_list: DestroyReplacedListCallback,
    destroy_replaced_string: DestroyReplacedStringCallback,
    llvm: VariablesLLVM,
    collection: CollectionEmission,
    arrow_reference_count: ArrowReferenceCountCallback,
    arrow_release_binding: ArrowReleaseBindingCallback,
    class_acquire: ClassAcquireCallback,
    class_operation: ClassOperationCallback,
    cleanup: CleanupService,
    function_state: FunctionValueState,
    guards: RuntimeGuardService,
    layout: LayoutEmission,
    lower_column_operation: LowerColumnOperationCallback,
    numeric: NumericEmission,
    require_runtime_symbol: RequireRuntimeSymbolCallback,
    runtime_features: RuntimeFeatureState,
    strings: StringEmission,
    visit_child: Callable[[astx.AST], None],
) -> None:
    """
    title: Check every explicitly injected binary_ops dependency.
    parameters:
      floating:
        type: FloatingEmission
      destroy_replaced_list:
        type: DestroyReplacedListCallback
      destroy_replaced_string:
        type: DestroyReplacedStringCallback
      llvm:
        type: VariablesLLVM
      collection:
        type: CollectionEmission
      arrow_reference_count:
        type: ArrowReferenceCountCallback
      arrow_release_binding:
        type: ArrowReleaseBindingCallback
      class_acquire:
        type: ClassAcquireCallback
      class_operation:
        type: ClassOperationCallback
      cleanup:
        type: CleanupService
      function_state:
        type: FunctionValueState
      guards:
        type: RuntimeGuardService
      layout:
        type: LayoutEmission
      lower_column_operation:
        type: LowerColumnOperationCallback
      numeric:
        type: NumericEmission
      require_runtime_symbol:
        type: RequireRuntimeSymbolCallback
      runtime_features:
        type: RuntimeFeatureState
      strings:
        type: StringEmission
      visit_child:
        type: Callable[[astx.AST], None]
    """
    del (
        floating,
        destroy_replaced_list,
        destroy_replaced_string,
        llvm,
        collection,
        arrow_reference_count,
        arrow_release_binding,
        class_acquire,
        class_operation,
        cleanup,
        function_state,
        guards,
        layout,
        lower_column_operation,
        numeric,
        require_runtime_symbol,
        runtime_features,
        strings,
        visit_child,
    )
