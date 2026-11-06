"""
title: Explicit per-compiler graph of backend implementations and services.
summary: >-
  Typed callback edges resolve cycles only after construction; no provider
  descriptor retains these objects. Families receive their actual module,
  function, region, and feature dependencies, not the compiler driver. Each
  compilation owns a fresh node dispatcher and mutable lowering state.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import TYPE_CHECKING

import astx

from llvmlite import ir
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
from irx.builder.extensions.adapters import CallLoweringBindings
from irx.builder.lowering import contracts
from irx.builder.lowering.materialization import (
    ListConstruction,
    MaterializationEmission,
)
from irx.builder.lowering.sequences import SequenceEmission
from irx.builder.lowering.text import TextEmission
from irx.builder.services.cleanup import CleanupService
from irx.builder.services.collections import CollectionEmission
from irx.builder.services.conversions import NumericEmission
from irx.builder.services.exceptions import (
    ExceptionService,
    RuntimeGuardService,
)
from irx.builder.services.floating import FloatingEmission
from irx.builder.services.layout import LayoutEmission
from irx.builder.services.representations import TypeLowering
from irx.builder.services.values import ValueEmission
from irx.builder.state import CleanupAction
from irx.builder.strings import StringEmission
from irx.extensions.nodes import ScopedNodeDispatch
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.core import VisitorCore

from irx.builder.lowering.array import ArrayLowering
from irx.builder.lowering.binary_ops import BinaryLowering
from irx.builder.lowering.buffer import BufferLowering
from irx.builder.lowering.classes import ClassLowering
from irx.builder.lowering.collections import CollectionLowering
from irx.builder.lowering.control_flow import ControlFlowLowering
from irx.builder.lowering.dataframe import DataFrameLowering
from irx.builder.lowering.exceptions import ExceptionLowering
from irx.builder.lowering.file import FileLowering
from irx.builder.lowering.functions import FunctionLowering
from irx.builder.lowering.generators import GeneratorLowering
from irx.builder.lowering.list import ListLowering
from irx.builder.lowering.literals import LiteralLowering
from irx.builder.lowering.modules import ModuleLowering
from irx.builder.lowering.nullable import NullableLowering
from irx.builder.lowering.system import SystemLowering
from irx.builder.lowering.temporal import TemporalLowering
from irx.builder.lowering.tensor import TensorLowering
from irx.builder.lowering.unary_ops import UnaryLowering
from irx.builder.lowering.variables import VariableLowering


@private
@typechecked
class LoweringFeatures:
    """
    title: Explicit per-compilation dependency wiring.
    attributes:
      arrays:
        type: ArrayLowering
      modules:
        type: ModuleLowering
      classes:
        type: ClassLowering
      literals:
        type: LiteralLowering
      buffers:
        type: BufferLowering
      collections:
        type: CollectionLowering
      variables:
        type: VariableLowering
      generators:
        type: GeneratorLowering
      functions:
        type: FunctionLowering
      exception_handlers:
        type: ExceptionLowering
      tensors:
        type: TensorLowering
      nullable:
        type: NullableLowering
      temporal:
        type: TemporalLowering
      files:
        type: FileLowering
      dataframes:
        type: DataFrameLowering
      lists:
        type: ListLowering
      unary:
        type: UnaryLowering
      system:
        type: SystemLowering
      control_flow:
        type: ControlFlowLowering
      binary:
        type: BinaryLowering
      dispatch:
        type: ScopedNodeDispatch
    """

    arrays: ArrayLowering
    modules: ModuleLowering
    classes: ClassLowering
    literals: LiteralLowering
    buffers: BufferLowering
    collections: CollectionLowering
    variables: VariableLowering
    generators: GeneratorLowering
    functions: FunctionLowering
    exception_handlers: ExceptionLowering
    tensors: TensorLowering
    nullable: NullableLowering
    temporal: TemporalLowering
    files: FileLowering
    dataframes: DataFrameLowering
    lists: ListLowering
    unary: UnaryLowering
    system: SystemLowering
    control_flow: ControlFlowLowering
    binary: BinaryLowering
    dispatch: ScopedNodeDispatch

    def __init__(self, core: VisitorCore) -> None:
        """
        title: >-
          Bind state, wire services, and freeze one compiler's dispatch
          catalog.
        parameters:
          core:
            type: VisitorCore
        """
        core.types = TypeLowering(
            core.module_state.struct_types,
            core._llvm.get_data_type,
            core._llvm.BUFFER_VIEW_TYPE,
        )
        core.exceptions = ExceptionService(
            core.exit_state,
            lambda: core._llvm.ir_builder,
            core.require_runtime_symbol,
            self.exception_location,
            core.types.llvm_type,
            core.create_entry_block_alloca,
            core.checked_facade_signature,
            self.checked_native_call,
            # Cleanup closes this cycle after exception service construction.
            lambda depth: core.cleanup.emit_active(depth),  # noqa: PLW0108
        )
        core.cleanup = CleanupService(
            core.exit_state,
            core.generator_frame_state,
            lambda: core._llvm.ir_builder,
            core.require_runtime_symbol,
            core.exceptions.exception_call,
            core.exceptions.propagate_pending_exception,
        )
        core.guards = RuntimeGuardService(
            lambda: core._llvm.ir_builder,
            self.exception_string,
            self.raise_runtime_exception,
        )
        core.numeric = NumericEmission(
            core._llvm.module,
            lambda: core._llvm.ir_builder,
            core.types,
            core.guards.guard,
            core.activate_runtime_feature,
        )
        assert isinstance(core._llvm.SIZE_T_TYPE, ir.IntType)
        core.strings = StringEmission(
            core._llvm.module,
            core._llvm.SIZE_T_TYPE,
            lambda: core._llvm.ir_builder,
            core.require_runtime_symbol,
            core.guards.guard,
        )
        core.values = ValueEmission(
            lambda: core._llvm.ir_builder,
            core.evaluate_value,
            core.publish_value,
            core.create_entry_block_alloca,
        )
        core.collection = CollectionEmission(
            core.values,
            core.numeric,
            core.require_runtime_symbol,
        )
        core.floating = FloatingEmission(
            core._llvm.module,
            lambda: core._llvm.ir_builder,
        )
        core.text = TextEmission(
            core.values,
            core.types,
            core.numeric,
            core.strings,
            core.require_runtime_symbol,
            core.cleanup,
            core.guards,
        )
        core.sequences = SequenceEmission(
            core.values,
            core.types,
            core.numeric,
            core.require_runtime_symbol,
            core.cleanup,
            core.guards,
            self.literal_list_storage,
            self.check_arrow_status,
        )
        core.materialization = MaterializationEmission(
            core.values,
            core.types,
            core.numeric,
            core.require_runtime_symbol,
            core.cleanup,
            core.guards,
            core.sequences,
            ListConstruction(
                self.llvm_list_type,
                self.empty_list_value,
                self.track_list_construction,
                self.check_list_status,
            ),
            core.exceptions.context_value,
            core.exceptions.propagate_status,
        )
        core.layout = LayoutEmission(
            core._llvm.module,
            lambda: core._llvm.ir_builder,
            core.types,
            core.evaluate_value,
            core.storage_value,
            core.create_entry_block_alloca,
            self.require_class_value,
            self.class_pin,
            self.class_raw,
        )
        core.call_services = CallLoweringBindings(
            core.values,
            core.numeric,
            core.strings,
            self.class_pin,
            self.require_class_value,
            core.require_runtime_symbol,
            self.checked_native_call,
            self.track_native_handle,
            self.release_native_handle,
            self.arrow_temporary,
            self.lower_class_construct,
            core.peek_value,
        )
        self.arrays = ArrayLowering(
            contracts.ArrayServices(
                llvm=core._llvm,
                function_state=core.function_state,
                require_runtime_symbol=core.require_runtime_symbol,
                visit_child=core.visit_child,
            )
        )
        self.modules = ModuleLowering(
            contracts.ModuleServices(
                declare_semantic_function=self.declare_semantic_function,
                llvm=core._llvm,
                translate_modules=core._translate_modules,
                class_field_function=self.class_field_function,
                module_state=core.module_state,
                types=core.types,
                visit_child=core.visit_child,
            )
        )
        self.classes = ClassLowering(
            contracts.ClassServices(
                declare_semantic_function=self.declare_semantic_function,
                default_runtime_initializer=self.default_runtime_initializer,
                llvm=core._llvm,
                cleanup=core.cleanup,
                create_entry_block_alloca=core.create_entry_block_alloca,
                create_native_file=self.create_native_file,
                exception_string=self.exception_string,
                exceptions=core.exceptions,
                exit_state=core.exit_state,
                file_check=self.file_check,
                file_error_buffer=self.file_error_buffer,
                function_state=core.function_state,
                initialize_exception_record=self.initialize_exception_record,
                layout=core.layout,
                numeric=core.numeric,
                require_runtime_symbol=core.require_runtime_symbol,
                strings=core.strings,
                types=core.types,
                visit_child=core.visit_child,
            )
        )
        self.literals = LiteralLowering(
            contracts.LiteralServices(
                collection=core.collection,
                empty_list_value_for_type=self.empty_list_value_for_type,
                llvm=core._llvm,
                lower_list_subscript=self.lower_list_subscript,
                create_entry_block_alloca=core.create_entry_block_alloca,
                function_state=core.function_state,
                lower_class_construct=self.lower_class_construct,
                lower_column_operation=self.lower_column_operation,
                numeric=core.numeric,
                sequences=core.sequences,
                strings=core.strings,
                text=core.text,
                types=core.types,
                visit_child=core.visit_child,
            )
        )
        self.buffers = BufferLowering(
            contracts.BufferServices(
                llvm=core._llvm,
                create_entry_block_alloca=core.create_entry_block_alloca,
                function_state=core.function_state,
                numeric=core.numeric,
                require_runtime_symbol=core.require_runtime_symbol,
                sequences=core.sequences,
                types=core.types,
                visit_child=core.visit_child,
            )
        )
        self.collections = CollectionLowering(
            contracts.CollectionServices(
                list_pointer_and_length_for_iteration=self.list_pointer_and_length_for_iteration,
                list_pointer_for_call=self.list_pointer_for_call,
                llvm=core._llvm,
                load_list_element_at_index=self.load_list_element_at_index,
                create_entry_block_alloca=core.create_entry_block_alloca,
                function_state=core.function_state,
                numeric=core.numeric,
                sequences=core.sequences,
                strings=core.strings,
                text=core.text,
                visit_child=core.visit_child,
            )
        )
        self.variables = VariableLowering(
            contracts.VariableServices(
                empty_list_value_for_type=self.empty_list_value_for_type,
                llvm=core._llvm,
                class_acquire=self.class_acquire,
                class_cleanup=self.class_cleanup,
                class_field_value=self.class_field_value,
                create_entry_block_alloca=core.create_entry_block_alloca,
                exit_state=core.exit_state,
                file_cleanup=self.file_cleanup,
                function_state=core.function_state,
                generator_frame_state=core.generator_frame_state,
                layout=core.layout,
                numeric=core.numeric,
                require_runtime_symbol=core.require_runtime_symbol,
                types=core.types,
                visit_child=core.visit_child,
            )
        )
        self.generators = GeneratorLowering(
            contracts.GeneratorServices(
                floating=core.floating,
                append_basic_blocks=self.append_basic_blocks,
                declare_semantic_function=self.declare_semantic_function,
                discard_child_results=self.discard_child_results,
                module_state=core.module_state,
                llvm=core._llvm,
                loop_scope=self.loop_scope,
                temporary_named_value=self.temporary_named_value,
                cleanup=core.cleanup,
                create_entry_block_alloca=core.create_entry_block_alloca,
                exceptions=core.exceptions,
                exit_state=core.exit_state,
                fatal_status=self.fatal_status,
                function_state=core.function_state,
                generator_frame_state=core.generator_frame_state,
                generator_module_state=core.generator_module_state,
                llvm_function_name_for_node=core.llvm_function_name_for_node,
                numeric=core.numeric,
                types=core.types,
                visit_child=core.visit_child,
            )
        )
        self.functions = FunctionLowering(
            contracts.FunctionServices(
                floating=core.floating,
                emit_generator_stop=self.emit_generator_stop,
                module_state=core.module_state,
                empty_list_value_for_type=self.empty_list_value_for_type,
                llvm=core._llvm,
                lower_generator_function=self.lower_generator_function,
                activate_runtime_feature=core.activate_runtime_feature,
                call_dispatch=core.call_dispatch,
                call_services=core.call_services,
                class_acquire=self.class_acquire,
                class_cleanup=self.class_cleanup,
                class_operation=self.class_operation,
                class_pin=self.class_pin,
                cleanup=core.cleanup,
                create_entry_block_alloca=core.create_entry_block_alloca,
                exception_module_state=core.exception_module_state,
                exceptions=core.exceptions,
                exit_state=core.exit_state,
                function_state=core.function_state,
                generator_frame_state=core.generator_frame_state,
                llvm_function_name_for_node=core.llvm_function_name_for_node,
                lower_class_construct=self.lower_class_construct,
                lower_file_method=self.lower_file_method,
                lower_file_open=self.lower_file_open,
                materialization=core.materialization,
                numeric=core.numeric,
                require_runtime_symbol=core.require_runtime_symbol,
                runtime_features=core.runtime_features,
                sequences=core.sequences,
                strings=core.strings,
                text=core.text,
                types=core.types,
                visit_child=core.visit_child,
            )
        )
        self.exception_handlers = ExceptionLowering(
            contracts.ExceptionServices(
                assert_source_name=self.assert_source_name,
                llvm=core._llvm,
                class_cleanup=self.class_cleanup,
                class_drop_function=self.class_drop_function,
                class_field_function=self.class_field_function,
                class_operation=self.class_operation,
                class_pin=self.class_pin,
                class_raw=self.class_raw,
                cleanup=core.cleanup,
                create_entry_block_alloca=core.create_entry_block_alloca,
                module_state=core.module_state,
                exception_module_state=core.exception_module_state,
                exceptions=core.exceptions,
                exit_state=core.exit_state,
                file_error_buffer=self.file_error_buffer,
                function_state=core.function_state,
                lower_statement_block=self.lower_statement_block,
                require_runtime_symbol=core.require_runtime_symbol,
                strings=core.strings,
                types=core.types,
                visit_child=core.visit_child,
            )
        )
        self.tensors = TensorLowering(
            contracts.TensorServices(
                i64_array_pointer=self.i64_array_pointer,
                llvm=core._llvm,
                lower_buffer_index_indices=self.lower_buffer_index_indices,
                check_arrow_status=self.check_arrow_status,
                create_entry_block_alloca=core.create_entry_block_alloca,
                exit_state=core.exit_state,
                function_state=core.function_state,
                lower_buffer_byte_offset=self.lower_buffer_byte_offset,
                lower_buffer_element_pointer=self.lower_buffer_element_pointer,
                numeric=core.numeric,
                require_runtime_symbol=core.require_runtime_symbol,
                track_native_handle=self.track_native_handle,
                visit_child=core.visit_child,
            )
        )
        self.nullable = NullableLowering(
            contracts.NullableServices(
                llvm=core._llvm,
                arrow_temporary=self.arrow_temporary,
                check_arrow_status=self.check_arrow_status,
                create_entry_block_alloca=core.create_entry_block_alloca,
                function_state=core.function_state,
                numeric=core.numeric,
                require_runtime_symbol=core.require_runtime_symbol,
                strings=core.strings,
                types=core.types,
                visit_child=core.visit_child,
            )
        )
        self.temporal = TemporalLowering(
            contracts.TemporalServices(
                llvm=core._llvm,
                function_state=core.function_state,
            )
        )
        self.files = FileLowering(
            contracts.FileServices(
                empty_list_value=self.empty_list_value,
                llvm=core._llvm,
                llvm_list_type=self.llvm_list_type,
                class_operation=self.class_operation,
                class_pin=self.class_pin,
                cleanup=core.cleanup,
                create_entry_block_alloca=core.create_entry_block_alloca,
                exceptions=core.exceptions,
                exit_state=core.exit_state,
                fatal_status=self.fatal_status,
                function_state=core.function_state,
                lower_bound_call_arguments=self.lower_bound_call_arguments,
                raise_runtime_exception=self.raise_runtime_exception,
                require_runtime_symbol=core.require_runtime_symbol,
                strings=core.strings,
                visit_child=core.visit_child,
            )
        )
        self.dataframes = DataFrameLowering(
            contracts.DataFrameServices(
                llvm=core._llvm,
                arrow_explicit_lifetime=self.arrow_explicit_lifetime,
                arrow_temporary=self.arrow_temporary,
                create_entry_block_alloca=core.create_entry_block_alloca,
                exit_state=core.exit_state,
                fatal_status=self.fatal_status,
                function_state=core.function_state,
                numeric=core.numeric,
                raise_runtime_exception=self.raise_runtime_exception,
                require_runtime_symbol=core.require_runtime_symbol,
                strings=core.strings,
                visit_child=core.visit_child,
            )
        )
        self.lists = ListLowering(
            contracts.ListServices(
                llvm=core._llvm,
                lower_boolean_condition=self.lower_boolean_condition,
                register_owned_string_cleanup=self.register_owned_string_cleanup,
                temporary_named_value=self.temporary_named_value,
                cleanup=core.cleanup,
                create_entry_block_alloca=core.create_entry_block_alloca,
                exit_state=core.exit_state,
                function_state=core.function_state,
                layout=core.layout,
                numeric=core.numeric,
                raise_runtime_exception=self.raise_runtime_exception,
                require_runtime_symbol=core.require_runtime_symbol,
                strings=core.strings,
                target_machine=core.target_machine,
                types=core.types,
                visit_child=core.visit_child,
            )
        )
        self.unary = UnaryLowering(
            contracts.UnaryServices(
                llvm=core._llvm,
                function_state=core.function_state,
                layout=core.layout,
                lower_column_operation=self.lower_column_operation,
                numeric=core.numeric,
                visit_child=core.visit_child,
            )
        )
        self.system = SystemLowering(
            contracts.SystemServices(
                llvm=core._llvm,
                arrow_temporary=self.arrow_temporary,
                checked_native_call=self.checked_native_call,
                class_operation=self.class_operation,
                cleanup=core.cleanup,
                function_state=core.function_state,
                lower_class_construct=self.lower_class_construct,
                numeric=core.numeric,
                release_native_handle=self.release_native_handle,
                require_runtime_symbol=core.require_runtime_symbol,
                strings=core.strings,
                track_native_handle=self.track_native_handle,
                types=core.types,
                visit_child=core.visit_child,
            )
        )
        self.control_flow = ControlFlowLowering(
            contracts.ControlFlowServices(
                apply_calling_convention=self.apply_calling_convention,
                module_state=core.module_state,
                declare_semantic_function=self.declare_semantic_function,
                indirect_method_callee=self.indirect_method_callee,
                list_pointer_and_length_for_iteration=self.list_pointer_and_length_for_iteration,
                llvm=core._llvm,
                load_list_element_at_index=self.load_list_element_at_index,
                lower_generator_for_in_loop=self.lower_generator_for_in_loop,
                register_owned_string_cleanup=self.register_owned_string_cleanup,
                resolved_iteration=self.resolved_iteration,
                cleanup=core.cleanup,
                create_entry_block_alloca=core.create_entry_block_alloca,
                exceptions=core.exceptions,
                exit_state=core.exit_state,
                function_state=core.function_state,
                lower_bound_call_arguments=self.lower_bound_call_arguments,
                numeric=core.numeric,
                raise_runtime_exception=self.raise_runtime_exception,
                sequences=core.sequences,
                strings=core.strings,
                types=core.types,
                visit_child=core.visit_child,
            )
        )
        self.binary = BinaryLowering(
            contracts.BinaryServices(
                floating=core.floating,
                destroy_replaced_list=self.destroy_replaced_list,
                destroy_replaced_string=self.destroy_replaced_string,
                llvm=core._llvm,
                collection=core.collection,
                arrow_reference_count=self.arrow_reference_count,
                arrow_release_binding=self.arrow_release_binding,
                class_acquire=self.class_acquire,
                class_operation=self.class_operation,
                cleanup=core.cleanup,
                function_state=core.function_state,
                guards=core.guards,
                layout=core.layout,
                lower_column_operation=self.lower_column_operation,
                numeric=core.numeric,
                require_runtime_symbol=core.require_runtime_symbol,
                runtime_features=core.runtime_features,
                strings=core.strings,
                visit_child=core.visit_child,
            )
        )
        self.dispatch = ScopedNodeDispatch(
            "lowering",
            (
                *self.arrays.node_handlers(),
                *self.modules.node_handlers(),
                *self.literals.node_handlers(),
                *self.buffers.node_handlers(),
                *self.collections.node_handlers(),
                *self.variables.node_handlers(),
                *self.generators.node_handlers(),
                *self.functions.node_handlers(),
                *self.exception_handlers.node_handlers(),
                *self.tensors.node_handlers(),
                *self.nullable.node_handlers(),
                *self.temporal.node_handlers(),
                *self.dataframes.node_handlers(),
                *self.lists.node_handlers(),
                *self.unary.node_handlers(),
                *self.system.node_handlers(),
                *self.control_flow.node_handlers(),
                *self.binary.node_handlers(),
            ),
            core.reject_node,
        )

    def declare_semantic_function(
        self, function: SemanticFunction
    ) -> ir.Function:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          function:
            type: SemanticFunction
        returns:
          type: ir.Function
        """
        return self.functions._declare_semantic_function(function)

    def class_field_function(self, class_: SemanticClass) -> ir.Function:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          class_:
            type: SemanticClass
        returns:
          type: ir.Function
        """
        return self.classes.class_field_function(class_)

    def default_runtime_initializer(
        self, type_: astx.DataType, *, name_hint: str
    ) -> ir.Value:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          type_:
            type: astx.DataType
          name_hint:
            type: str
        returns:
          type: ir.Value
        """
        return self.literals._default_runtime_initializer(
            type_, name_hint=name_hint
        )

    def create_native_file(
        self,
        node: astx.AST,
        resolution: ResolvedFileOpen,
        values: list[ir.Value],
        *,
        cleanup_temporaries: bool = False,
    ) -> ir.Value:
        """
        title: Route one explicitly typed cross-feature dependency.
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
        return self.files.create_native_file(
            node, resolution, values, cleanup_temporaries=cleanup_temporaries
        )

    def exception_string(self, value: str) -> ir.Value:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          value:
            type: str
        returns:
          type: ir.Value
        """
        return self.exception_handlers.exception_string(value)

    def file_check(
        self,
        node: astx.AST,
        status: ir.Value,
        error: ir.Value,
        *,
        code: str = "ARX-RUNTIME-FILE-001",
        cleanup_temporaries: bool = False,
    ) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
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
        return self.files.file_check(
            node,
            status,
            error,
            code=code,
            cleanup_temporaries=cleanup_temporaries,
        )

    def file_error_buffer(self) -> ir.Value:
        """
        title: Route one explicitly typed cross-feature dependency.
        returns:
          type: ir.Value
        """
        return self.files.file_error_buffer()

    def initialize_exception_record(
        self,
        node: astx.AST,
        payload: ir.Value,
        exception: ResolvedExceptionType,
        *,
        location: list[ir.Value] | None = None,
    ) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
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
        return self.exception_handlers.initialize_exception_record(
            node, payload, exception, location=location
        )

    def empty_list_value_for_type(
        self, type_: astx.DataType | None
    ) -> ir.Constant:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          type_:
            type: astx.DataType | None
        returns:
          type: ir.Constant
        """
        return self.lists._empty_list_value_for_type(type_)

    def lower_list_subscript(
        self, *, base: astx.AST, index_node: astx.AST, result_node: astx.AST
    ) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          base:
            type: astx.AST
          index_node:
            type: astx.AST
          result_node:
            type: astx.AST
        """
        return self.lists._lower_list_subscript(
            base=base, index_node=index_node, result_node=result_node
        )

    def lower_class_construct(
        self, node: astx.AST, resolution: ResolvedClassConstruction
    ) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
          resolution:
            type: ResolvedClassConstruction
        """
        return self.classes.lower_class_construct(node, resolution)

    def lower_column_operation(self, node: astx.AST) -> bool:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
        returns:
          type: bool
        """
        return self.nullable.lower_column_operation(node)

    def list_pointer_and_length_for_iteration(
        self, base: astx.AST
    ) -> tuple[ir.Value, ir.Value]:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          base:
            type: astx.AST
        returns:
          type: tuple[ir.Value, ir.Value]
        """
        return self.lists._list_pointer_and_length_for_iteration(base)

    def list_pointer_for_call(self, node: astx.AST, *, name: str) -> ir.Value:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
          name:
            type: str
        returns:
          type: ir.Value
        """
        return self.lists._list_pointer_for_call(node, name=name)

    def load_list_element_at_index(
        self, *, base: astx.AST, list_ptr: ir.Value, index: ir.Value
    ) -> ir.Value:
        """
        title: Route one explicitly typed cross-feature dependency.
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
        return self.lists._load_list_element_at_index(
            base=base, list_ptr=list_ptr, index=index
        )

    def class_acquire(self, node: astx.AST, value: ir.Value) -> ir.Value:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
        returns:
          type: ir.Value
        """
        return self.classes.class_acquire(node, value)

    def class_cleanup(
        self,
        node: astx.AST,
        value: ir.Value,
        owner: str | None = None,
        *,
        storage: bool = False,
    ) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
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
        return self.classes.class_cleanup(node, value, owner, storage=storage)

    def class_field_value(self, node: astx.AST, value: ir.Value) -> ir.Value:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
        returns:
          type: ir.Value
        """
        return self.classes.class_field_value(node, value)

    def file_cleanup(
        self, node: astx.AST, handle: ir.Value, owner_id: str | None
    ) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
          handle:
            type: ir.Value
          owner_id:
            type: str | None
        """
        return self.files.file_cleanup(node, handle, owner_id)

    def append_basic_blocks(
        self, prefix: str, *roles: str
    ) -> tuple[ir.Block, ...]:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          prefix:
            type: str
          roles:
            type: str
            variadic: positional
        returns:
          type: tuple[ir.Block, Ellipsis]
        """
        return self.control_flow._append_basic_blocks(prefix, *roles)

    def discard_child_results(self, node: astx.AST) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
        """
        return self.control_flow._discard_child_results(node)

    def loop_scope(
        self, *, break_target: ir.Block, continue_target: ir.Block
    ) -> AbstractContextManager[None]:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          break_target:
            type: ir.Block
          continue_target:
            type: ir.Block
        returns:
          type: AbstractContextManager[None]
        """
        return self.control_flow._loop_scope(
            break_target=break_target, continue_target=continue_target
        )

    def temporary_named_value(
        self, key: str, value: ir.Value, *, is_constant: bool = False
    ) -> AbstractContextManager[None]:
        """
        title: Route one explicitly typed cross-feature dependency.
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
        return self.control_flow._temporary_named_value(
            key, value, is_constant=is_constant
        )

    def fatal_status(
        self,
        node: astx.AST,
        status: ir.Value,
        *,
        location: list[ir.Value] | None = None,
    ) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
          status:
            type: ir.Value
          location:
            type: list[ir.Value] | None
        """
        return self.exception_handlers.fatal_status(
            node, status, location=location
        )

    def emit_generator_stop(self, node: astx.AST | None = None) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST | None
        """
        return self.generators._emit_generator_stop(node)

    def lower_generator_function(
        self,
        node: astx.FunctionDef,
        generator: ResolvedGeneratorFunction,
    ) -> ir.Function:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.FunctionDef
          generator:
            type: ResolvedGeneratorFunction
        returns:
          type: ir.Function
        """
        return self.generators._lower_generator_function(node, generator)

    def class_operation(
        self, node: astx.AST, operation: str, value: ir.Value
    ) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
          operation:
            type: str
          value:
            type: ir.Value
        """
        return self.classes.class_operation(node, operation, value)

    def class_pin(self, node: astx.AST, value: ir.Value) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
        """
        return self.classes.class_pin(node, value)

    def lower_file_method(self, node: astx.MethodCall) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.MethodCall
        """
        return self.files.lower_file_method(node)

    def lower_file_open(self, node: astx.FunctionCall) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.FunctionCall
        """
        return self.files.lower_file_open(node)

    def assert_source_name(self, node: astx.AST) -> str:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
        returns:
          type: str
        """
        return self.control_flow._assert_source_name(node)

    def class_drop_function(self, class_: SemanticClass) -> ir.Function:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          class_:
            type: SemanticClass
        returns:
          type: ir.Function
        """
        return self.classes.class_drop_function(class_)

    def class_raw(self, value: ir.Value) -> ir.Value:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          value:
            type: ir.Value
        returns:
          type: ir.Value
        """
        return self.classes.class_raw(value)

    def lower_statement_block(
        self, block: astx.Block, *, preserve_scope: bool = False
    ) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          block:
            type: astx.Block
          preserve_scope:
            type: bool
        """
        return self.control_flow.lower_statement_block(
            block, preserve_scope=preserve_scope
        )

    def i64_array_pointer(
        self,
        values: tuple[int, ...],
        *,
        purpose: str,
        symbol_namespace: str = "buffer",
    ) -> ir.Value:
        """
        title: Route one explicitly typed cross-feature dependency.
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
        return self.buffers._i64_array_pointer(
            values, purpose=purpose, symbol_namespace=symbol_namespace
        )

    def lower_buffer_index_indices(
        self, indices: list[astx.AST]
    ) -> list[ir.Value]:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          indices:
            type: list[astx.AST]
        returns:
          type: list[ir.Value]
        """
        return self.buffers._lower_buffer_index_indices(indices)

    def check_arrow_status(
        self,
        node: astx.AST,
        status: ir.Value,
        operation: str,
        message: ir.Value | None = None,
    ) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
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
        return self.dataframes.check_arrow_status(
            node, status, operation, message
        )

    def lower_buffer_byte_offset(
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
        title: Route one explicitly typed cross-feature dependency.
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
        return self.buffers.lower_buffer_byte_offset(
            view,
            indices,
            index_nodes=index_nodes,
            node=node,
            element_size=element_size,
            bounds_policy=bounds_policy,
        )

    def lower_buffer_element_pointer(
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
        title: Route one explicitly typed cross-feature dependency.
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
        return self.buffers.lower_buffer_element_pointer(
            view,
            indices,
            element_type,
            index_nodes=index_nodes,
            node=node,
            bounds_policy=bounds_policy,
        )

    def track_native_handle(
        self, node: astx.AST, feature: str, destroy: str, value: ir.Value
    ) -> CleanupAction:
        """
        title: Route one explicitly typed cross-feature dependency.
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
        return self.dataframes.track_native_handle(
            node, feature, destroy, value
        )

    def arrow_temporary(self, node: astx.AST, value: ir.Value) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
        """
        return self.classes.arrow_temporary(node, value)

    def empty_list_value(self, node: astx.AST) -> ir.Constant:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
        returns:
          type: ir.Constant
        """
        return self.lists._empty_list_value(node)

    def llvm_list_type(self) -> ir.Type:
        """
        title: Route one explicitly typed cross-feature dependency.
        returns:
          type: ir.Type
        """
        return self.lists._llvm_list_type()

    def lower_bound_call_arguments(
        self,
        resolution: CallResolution,
        *,
        receiver_value: ir.Value | None = None,
    ) -> list[ir.Value]:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          resolution:
            type: CallResolution
          receiver_value:
            type: ir.Value | None
        returns:
          type: list[ir.Value]
        """
        return self.functions.lower_bound_call_arguments(
            resolution, receiver_value=receiver_value
        )

    def raise_runtime_exception(
        self, node: astx.AST, role: str, message: ir.Value, *, code: str
    ) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
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
        return self.exception_handlers.raise_runtime_exception(
            node, role, message, code=code
        )

    def arrow_explicit_lifetime(
        self, node: astx.AST, value: ir.Value, *, retain: bool
    ) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
          retain:
            type: bool
        """
        return self.classes.arrow_explicit_lifetime(node, value, retain=retain)

    def lower_boolean_condition(
        self, value: ir.Value | None, *, node: astx.AST, context: str
    ) -> ir.Value:
        """
        title: Route one explicitly typed cross-feature dependency.
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
        return self.control_flow._lower_boolean_condition(
            value, node=node, context=context
        )

    def register_owned_string_cleanup(
        self,
        node: astx.AST,
        string_ptr: ir.Value,
    ) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
          string_ptr:
            type: ir.Value
        """
        return self.variables._register_owned_string_cleanup(node, string_ptr)

    def checked_native_call(
        self, node: astx.AST, function: ir.Function, args: list[ir.Value]
    ) -> ir.Value:
        """
        title: Route one explicitly typed cross-feature dependency.
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
        return self.dataframes.checked_native_call(node, function, args)

    def release_native_handle(self, action: CleanupAction) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          action:
            type: CleanupAction
        """
        return self.dataframes.release_native_handle(action)

    def apply_calling_convention(self, signature: FunctionSignature) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          signature:
            type: FunctionSignature
        """
        return self.functions._apply_calling_convention(signature)

    def indirect_method_callee(
        self,
        *,
        node: astx.AST,
        method_resolution: ResolvedMethodCall,
        receiver_value: ir.Value,
    ) -> ir.Value:
        """
        title: Route one explicitly typed cross-feature dependency.
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
        return self.functions._indirect_method_callee(
            node=node,
            method_resolution=method_resolution,
            receiver_value=receiver_value,
        )

    def lower_generator_for_in_loop(
        self, node: astx.ForInLoopStmt, iteration: ResolvedIteration
    ) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.ForInLoopStmt
          iteration:
            type: ResolvedIteration
        """
        return self.generators._lower_generator_for_in_loop(node, iteration)

    def resolved_iteration(self, node: astx.AST) -> ResolvedIteration | None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
        returns:
          type: ResolvedIteration | None
        """
        return self.lists._resolved_iteration(node)

    def destroy_replaced_list(
        self, node: astx.AST, list_ptr: ir.Value, *, target_name: str
    ) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
          list_ptr:
            type: ir.Value
          target_name:
            type: str
        """
        return self.variables._destroy_replaced_list(
            node, list_ptr, target_name=target_name
        )

    def destroy_replaced_string(
        self, node: astx.AST, string_ptr: ir.Value, *, target_name: str
    ) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
          string_ptr:
            type: ir.Value
          target_name:
            type: str
        """
        return self.variables._destroy_replaced_string(
            node, string_ptr, target_name=target_name
        )

    def arrow_reference_count(self, owner: str) -> ir.Value:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          owner:
            type: str
        returns:
          type: ir.Value
        """
        return self.classes.arrow_reference_count(owner)

    def arrow_release_binding(
        self, node: astx.AST, value: ir.Value, owner: str
    ) -> None:
        """
        title: Route one explicitly typed cross-feature dependency.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
          owner:
            type: str
        """
        return self.classes.arrow_release_binding(node, value, owner)

    def exception_location(self, node: astx.AST) -> list[ir.Value]:
        """
        title: Resolve diagnostic strings through the exception implementation.
        parameters:
          node:
            type: astx.AST
        returns:
          type: list[ir.Value]
        """
        return self.exception_handlers.exception_location(node)

    def literal_list_storage(
        self, *, base: astx.LiteralList, literal_value: ir.Value
    ) -> ir.Value:
        """
        title: Supply already resolved literal storage to sequence adaptation.
        parameters:
          base:
            type: astx.LiteralList
          literal_value:
            type: ir.Value
        returns:
          type: ir.Value
        """
        return self.lists._literal_list_pointer_for_runtime(
            base=base, literal_value=literal_value
        )

    def track_list_construction(self, value: ir.Value) -> CleanupAction:
        """
        title: Keep a partial list active in the shared cleanup ledger.
        parameters:
          value:
            type: ir.Value
        returns:
          type: CleanupAction
        """
        return self.lists.track_list_construction(value)

    def check_list_status(self, node: astx.AST, status: ir.Value) -> None:
        """
        title: Consume list outputs only on the implementation's success path.
        parameters:
          node:
            type: astx.AST
          status:
            type: ir.Value
        """
        self.lists.check_list_status(node, status)

    def require_class_value(self, node: astx.AST, value: ir.Value) -> None:
        """
        title: Require a live nominal receiver before addressing its payload.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
        """
        self.classes.class_operation(node, "require", value)
