"""
title: Shared concrete core for llvmliteir visitors.
"""

from __future__ import annotations

import ctypes

from typing import TYPE_CHECKING, cast

import astx

from llvmlite import binding as llvm
from llvmlite import ir
from plum import dispatch
from public import private

from irx.analysis import analyze, analyze_modules
from irx.analysis.extensions.records import CallPlan
from irx.analysis.module_interfaces import ImportResolver, ParsedModule
from irx.analysis.resolved_nodes import FunctionSignature
from irx.buffer import BUFFER_VIEW_TYPE_NAME
from irx.builder.base import BuilderVisitor
from irx.builder.diagnostics import (
    raise_lowering_internal_error,
    require_lowered_value,
    require_semantic_metadata,
)
from irx.builder.extensions.calls import (
    LoweringCall,
    default_lowering_configuration,
)
from irx.builder.runtime import safe_pop
from irx.builder.runtime.record_batch_api import is_checked_native_facade
from irx.builder.runtime.registry import (
    RuntimeFeatureState,
    get_default_runtime_feature_registry,
)
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
from irx.builder.services.representations import (
    TypeLowering,
    semantic_class_key,
    semantic_class_name,
    semantic_function_key,
    semantic_function_name,
    semantic_symbol_key,
)
from irx.builder.strings import StringEmission
from irx.builder.types import (
    VariablesLLVM,
)
from irx.diagnostics import DiagnosticCodes
from irx.extensions import HandlerConfiguration, ScopedDispatch
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.extensions.calls import CallLoweringServices
    from irx.builder.lowering.composition import LoweringFeatures
    from irx.builder.lowering.materialization import MaterializationEmission
    from irx.builder.lowering.sequences import SequenceEmission
    from irx.builder.lowering.text import TextEmission
    from irx.builder.services.values import ValueEmission


@private
@typechecked
class VisitorCore(BuilderVisitor):
    """
    title: Coordinate one compilation's module, services, and scoped dispatch.
    summary: >-
      Concern implementations receive narrow dependency records, not this
      driver. Function, region, exception, and generator state have separate
      lifetimes.
    attributes:
      module_state:
        type: ModuleEmissionState
      exit_state:
        type: ExitState
      function_state:
        type: FunctionValueState
      exception_module_state:
        type: ExceptionModuleState
      generator_frame_state:
        type: GeneratorFrameState
      generator_module_state:
        type: GeneratorModuleState
      cleanup:
        type: CleanupService
      exceptions:
        type: ExceptionService
      guards:
        type: RuntimeGuardService
      collection:
        type: CollectionEmission
      floating:
        type: FloatingEmission
      features:
        type: LoweringFeatures
      values:
        type: ValueEmission
      text:
        type: TextEmission
      sequences:
        type: SequenceEmission
      materialization:
        type: MaterializationEmission
      call_services:
        type: CallLoweringServices
      strings:
        type: StringEmission
      types:
        type: TypeLowering
      numeric:
        type: NumericEmission
      layout:
        type: LayoutEmission
      analysis_configuration:
        type: HandlerConfiguration | None
      lowering_configuration:
        type: HandlerConfiguration
      call_dispatch:
        type: ScopedDispatch
      _llvm:
        type: VariablesLLVM
      runtime_features:
        type: RuntimeFeatureState
      target:
        type: llvm.TargetRef
      target_machine:
        type: llvm.TargetMachine
    """

    module_state: ModuleEmissionState
    exit_state: ExitState
    function_state: FunctionValueState
    exception_module_state: ExceptionModuleState
    generator_frame_state: GeneratorFrameState
    generator_module_state: GeneratorModuleState
    cleanup: CleanupService
    exceptions: ExceptionService
    guards: RuntimeGuardService
    collection: CollectionEmission
    floating: FloatingEmission
    features: LoweringFeatures
    values: ValueEmission
    text: TextEmission
    sequences: SequenceEmission
    materialization: MaterializationEmission
    call_services: CallLoweringServices
    strings: StringEmission
    types: TypeLowering
    numeric: NumericEmission
    layout: LayoutEmission
    analysis_configuration: HandlerConfiguration | None
    lowering_configuration: HandlerConfiguration
    call_dispatch: ScopedDispatch
    _llvm: VariablesLLVM
    runtime_features: RuntimeFeatureState
    target: llvm.TargetRef
    target_machine: llvm.TargetMachine

    def __init__(
        self,
        active_runtime_features: set[str] | None = None,
        *,
        analysis_configuration: HandlerConfiguration | None = None,
        lowering_configuration: HandlerConfiguration | None = None,
    ) -> None:
        """
        title: Initialize VisitorCore.
        parameters:
          active_runtime_features:
            type: set[str] | None
          analysis_configuration:
            type: HandlerConfiguration | None
          lowering_configuration:
            type: HandlerConfiguration | None
        """
        super().__init__()
        self.analysis_configuration = analysis_configuration
        self.lowering_configuration = (
            lowering_configuration
            if lowering_configuration is not None
            else default_lowering_configuration()
        )
        self.lowering_configuration.validate_contract(
            "lowering", CallPlan, LoweringCall
        )
        self.call_dispatch = ScopedDispatch(self.lowering_configuration)
        self.module_state = ModuleEmissionState()
        self.exit_state = ExitState()
        self.function_state = FunctionValueState()
        self.exception_module_state = ExceptionModuleState()
        self.generator_module_state = GeneratorModuleState()
        self.generator_frame_state = GeneratorFrameState()
        self.initialize()
        self.target = llvm.Target.from_default_triple()
        try:
            self.target_machine = self.target.create_target_machine(
                codemodel="small",
                reloc="pic",
            )
        except TypeError:
            self.target_machine = self.target.create_target_machine(
                codemodel="small"
            )

        self._llvm.module.triple = self.target_machine.triple
        self._llvm.module.data_layout = str(self.target_machine.target_data)

        if self._llvm.SIZE_T_TYPE is None:
            self._llvm.SIZE_T_TYPE = self._get_size_t_type_from_triple()

        self._add_builtins()
        self.runtime_features = RuntimeFeatureState(
            owner=self,
            registry=get_default_runtime_feature_registry(),
            active_features=active_runtime_features,
        )

    def checked_facade_signature(self, signature: FunctionSignature) -> bool:
        """
        title: >-
          Consume registered checked-facade ABI metadata for a resolved call.
        parameters:
          signature:
            type: FunctionSignature
        returns:
          type: bool
        """
        return any(
            is_checked_native_facade(
                signature.symbol_name,
                name,
                self.runtime_features.feature(name).metadata.get(
                    "checked_facade_abi"
                ),
            )
            for name in signature.required_runtime_features
        )

    def publish_value(self, value: ir.Value) -> None:
        """
        title: Publish one semantically produced result in the active function.
        parameters:
          value:
            type: ir.Value
        """
        self.function_state.result_stack.append(value)

    def evaluate_value(self, node: astx.AST) -> ir.Value:
        """
        title: Evaluate a resolved operand and require its produced value.
        parameters:
          node:
            type: astx.AST
        returns:
          type: ir.Value
        """
        self.visit_child(node)
        return require_lowered_value(
            safe_pop(self.function_state.result_stack),
            node=node,
            context="resolved layout operand",
        )

    def storage_value(self, symbol_id: str) -> ir.Value | None:
        """
        title: Look up already allocated storage by its semantic identity.
        parameters:
          symbol_id:
            type: str
        returns:
          type: ir.Value | None
        """
        value = self.function_state.named_values.get(symbol_id)
        return value if isinstance(value, ir.Value) else None

    def peek_value(self) -> ir.Value | None:
        """
        title: Inspect an already produced class value without consuming it.
        returns:
          type: ir.Value | None
        """
        values = self.function_state.result_stack
        return values[-1] if values else None

    @dispatch
    def visit(self, node: astx.AST) -> None:
        """
        title: Delegate supported syntax through this compiler's node catalog.
        parameters:
          node:
            type: astx.AST
        """
        self.features.dispatch.visit(node)

    def reject_node(self, node: astx.AST) -> None:
        """
        title: Fail explicitly when analyzed input has no lowering handler.
        parameters:
          node:
            type: astx.AST
        """
        raise_lowering_internal_error(
            f"no lowering handler for {type(node).__name__}",
            node=node,
            code=DiagnosticCodes.LOWERING_MISSING_HANDLER,
        )

    def translate(self, node: astx.AST) -> str:
        """
        title: Translate.
        parameters:
          node:
            type: astx.AST
        returns:
          type: str
        """
        analyzed = analyze(node, configuration=self.analysis_configuration)
        self.module_state.module_display_names = {}
        self.module_state.current_module_display_name = None
        if isinstance(analyzed, astx.Module):
            self.module_state.module_display_names[id(analyzed)] = (
                getattr(analyzed, "name", "") or "<module>"
            )
            self._set_entry_function_from_module(analyzed)
            self._translate_modules([analyzed])
        else:
            metadata = getattr(analyzed, "semantic", None)
            if metadata is not None:
                self.exception_module_state.runtime_exception_types.update(
                    metadata.runtime_exception_types
                )
            exception_types = (
                self.exception_module_state.runtime_exception_types.values()
            )
            declarations = [
                item.class_.declaration for item in exception_types
            ]
            for declaration in declarations:
                key = semantic_class_key(declaration)
                type_ = self._llvm.module.context.get_identified_type(
                    semantic_class_name(declaration)
                )
                self.module_state.struct_types[key] = type_
                self.module_state.llvm_structs_by_qualified_name[key] = type_
            for declaration in declarations:
                self.features.modules.declare_class(declaration)
            for declaration in declarations:
                self.visit(declaration)
            self.visit(analyzed)
        return str(self._llvm.module)

    def translate_modules(
        self,
        root: ParsedModule,
        resolver: ImportResolver,
    ) -> str:
        """
        title: Translate a reachable graph of parsed modules to LLVM IR.
        parameters:
          root:
            type: ParsedModule
          resolver:
            type: ImportResolver
        returns:
          type: str
        """
        session = analyze_modules(
            root, resolver, configuration=self.analysis_configuration
        )
        self.runtime_features.add_native_features(
            tuple(session.native_features.values())
        )
        ordered_modules = session.ordered_modules()
        self.module_state.module_display_names = {
            id(parsed_module.ast): (
                parsed_module.display_name
                or getattr(parsed_module.ast, "name", "")
                or str(parsed_module.key)
            )
            for parsed_module in ordered_modules
        }
        self._set_entry_function_from_module(root.ast)
        self._translate_modules(
            [parsed_module.ast for parsed_module in ordered_modules],
            session.lowering_declarations,
        )
        return str(self._llvm.module)

    def _set_entry_function_from_module(self, module: astx.Module) -> None:
        """
        title: >-
          Record the root entrypoint semantic id when a main function exists.
        parameters:
          module:
            type: astx.Module
        """
        self.module_state.entry_function_symbol_id = None
        for node in module.nodes:
            candidate = None
            if (
                isinstance(node, astx.FunctionPrototype)
                and node.name == "main"
            ):
                candidate = node
            elif isinstance(node, astx.FunctionDef) and node.name == "main":
                candidate = node.prototype
            if candidate is None:
                continue
            self.module_state.entry_function_symbol_id = semantic_function_key(
                candidate
            )
            return

    def llvm_function_name_for_node(
        self,
        node: astx.AST,
    ) -> str:
        """
        title: Return the LLVM symbol name for a function node.
        parameters:
          node:
            type: astx.AST
        returns:
          type: str
        """
        function_key = semantic_function_key(node)
        if (
            self.module_state.entry_function_symbol_id is not None
            and function_key == self.module_state.entry_function_symbol_id
        ):
            return "irx.entry.main"
        return semantic_function_name(node)

    def _translate_modules(
        self,
        modules: list[astx.Module],
        declarations: frozenset[int] | None = None,
    ) -> None:
        """
        title: Translate a list of already-analyzed modules.
        parameters:
          modules:
            type: list[astx.Module]
          declarations:
            type: frozenset[int] | None
        """
        module_nodes = [
            (
                module,
                [
                    node
                    for node in [
                        *module.nodes,
                        *astx.generated_template_nodes(module),
                    ]
                    if declarations is None or id(node) in declarations
                ],
            )
            for module in modules
        ]
        for module in modules:
            metadata = getattr(module, "semantic", None)
            if metadata is not None:
                self.exception_module_state.runtime_exception_types.update(
                    metadata.runtime_exception_types
                )
        present = {id(node) for _, nodes in module_nodes for node in nodes}
        if module_nodes:
            for (
                exception
            ) in self.exception_module_state.runtime_exception_types.values():
                declaration = exception.class_.declaration
                if id(declaration) not in present:
                    module_nodes[0][1].append(declaration)
                    present.add(id(declaration))
        for _module, nodes in module_nodes:
            for node in nodes:
                if not isinstance(
                    node,
                    (astx.VariableDeclaration, astx.InlineVariableDeclaration),
                ) or not isinstance(node.type_, astx.NullableType):
                    continue
                info = getattr(node, "semantic", None)
                payload = require_semantic_metadata(
                    None
                    if info is None
                    else info.extras.get("nullable_global"),
                    node=node,
                    metadata="nullable_global",
                    context="nullable global",
                )
                type_ = require_semantic_metadata(
                    self.types.llvm_type(node.type_),
                    node=node,
                    metadata="LLVM type",
                    context="nullable global",
                )
                key = semantic_symbol_key(node)
                storage = ir.GlobalVariable(
                    self._llvm.module, type_, name="nullable_global_" + key
                )
                storage.linkage = "internal"
                storage.global_constant = (
                    node.mutability is astx.MutabilityKind.constant
                )
                storage.initializer = ir.Constant(
                    type_,
                    [
                        ir.Constant(ir.IntType(1), int(payload[0])),
                        ir.Constant(type_.elements[1], payload[1]),
                    ],
                )
                self.function_state.named_values[key] = storage
                if storage.global_constant:
                    self.function_state.const_vars.add(key)
        # Declare pointer identities before any layout asks for a class field
        # type; acyclic reference fields can point to later declarations.
        for module, nodes in module_nodes:
            for node in nodes:
                if isinstance(node, astx.ClassDefStmt):
                    key = semantic_class_key(node)
                    type_ = self._llvm.module.context.get_identified_type(
                        semantic_class_name(node)
                    )
                    self.module_state.struct_types[key] = type_
                    self.module_state.llvm_structs_by_qualified_name[key] = (
                        type_
                    )

        for module, nodes in module_nodes:
            self.module_state.current_module_display_name = (
                self.module_state.module_display_names.get(
                    id(module),
                    getattr(module, "name", "") or "<module>",
                )
            )
            for node in nodes:
                if isinstance(node, astx.ClassDefStmt):
                    self.features.modules.declare_class(node)
                elif isinstance(node, astx.StructDefStmt):
                    self.visit(node)

        for module, nodes in module_nodes:
            self.module_state.current_module_display_name = (
                self.module_state.module_display_names.get(
                    id(module), getattr(module, "name", "") or "<module>"
                )
            )
            for node in nodes:
                if isinstance(node, astx.ClassDefStmt):
                    self.visit(node)

        for module, nodes in module_nodes:
            self.module_state.current_module_display_name = (
                self.module_state.module_display_names.get(
                    id(module),
                    getattr(module, "name", "") or "<module>",
                )
            )
            for node in nodes:
                if isinstance(node, astx.FunctionPrototype):
                    if astx.is_template_node(
                        node
                    ) and not astx.is_template_specialization(node):
                        continue
                    self.visit(node)
                elif isinstance(node, astx.FunctionDef):
                    if astx.is_template_node(
                        node.prototype
                    ) and not astx.is_template_specialization(node):
                        continue
                    self.visit(node.prototype)

        for module, nodes in module_nodes:
            self.module_state.current_module_display_name = (
                self.module_state.module_display_names.get(
                    id(module),
                    getattr(module, "name", "") or "<module>",
                )
            )
            for node in nodes:
                if isinstance(node, astx.FunctionDef):
                    if astx.is_template_node(
                        node.prototype
                    ) and not astx.is_template_specialization(node):
                        continue
                    self.visit(node)

        self.features.exception_handlers.emit_entry_wrapper()
        self.module_state.current_module_display_name = None

    def activate_runtime_feature(self, feature_name: str) -> None:
        """
        title: Activate runtime feature.
        parameters:
          feature_name:
            type: str
        """
        self.runtime_features.activate(feature_name)

    def require_runtime_symbol(
        self, feature_name: str, symbol_name: str
    ) -> ir.Function:
        """
        title: Require runtime symbol.
        parameters:
          feature_name:
            type: str
          symbol_name:
            type: str
        returns:
          type: ir.Function
        """
        return self.runtime_features.require_symbol(feature_name, symbol_name)

    def _init_native_size_types(self) -> None:
        """
        title: Init native size types.
        """
        self._llvm.POINTER_BITS = ctypes.sizeof(ctypes.c_void_p) * 8
        self._llvm.SIZE_T_TYPE = None

    def _get_size_t_type_from_triple(self) -> ir.IntType:
        """
        title: Get size t type from triple.
        returns:
          type: ir.IntType
        """
        triple = self.target_machine.triple.lower()

        if any(
            arch in triple
            for arch in [
                "x86_64",
                "amd64",
                "aarch64",
                "arm64",
                "ppc64",
                "mips64",
            ]
        ):
            return ir.IntType(64)
        if any(arch in triple for arch in ["i386", "i686", "arm", "mips"]):
            if "64" in triple:
                return ir.IntType(64)
            return ir.IntType(32)

        return ir.IntType(ctypes.sizeof(ctypes.c_size_t) * 8)

    def initialize(self) -> None:
        """
        title: Initialize.
        """
        self._llvm = VariablesLLVM()
        # Keep identified class/struct types isolated per translation so
        # reused semantic names never retain stale LLVM bodies.
        llvm_context = ir.Context()
        self._llvm.module = ir.module.Module(
            "Arx",
            context=llvm_context,
        )
        self._llvm.context = llvm_context
        self._init_native_size_types()

        llvm.initialize_all_targets()
        llvm.initialize_all_asmprinters()
        llvm.initialize_native_target()
        llvm.initialize_native_asmparser()
        llvm.initialize_native_asmprinter()

        self._llvm.ir_builder = ir.IRBuilder()
        self._llvm.FLOAT_TYPE = ir.FloatType()
        self._llvm.FLOAT16_TYPE = ir.HalfType()
        self._llvm.DOUBLE_TYPE = ir.DoubleType()
        self._llvm.BOOLEAN_TYPE = ir.IntType(1)
        self._llvm.INT8_TYPE = ir.IntType(8)
        self._llvm.INT16_TYPE = ir.IntType(16)
        self._llvm.INT32_TYPE = ir.IntType(32)
        self._llvm.INT64_TYPE = ir.IntType(64)
        self._llvm.UINT8_TYPE = ir.IntType(8)
        self._llvm.UINT16_TYPE = ir.IntType(16)
        self._llvm.UINT32_TYPE = ir.IntType(32)
        self._llvm.UINT64_TYPE = ir.IntType(64)
        self._llvm.UINT128_TYPE = ir.IntType(128)
        self._llvm.VOID_TYPE = ir.VoidType()
        self._llvm.ASCII_STRING_TYPE = ir.IntType(8).as_pointer()
        self._llvm.UTF8_STRING_TYPE = self._llvm.ASCII_STRING_TYPE
        self._llvm.OPAQUE_POINTER_TYPE = self._llvm.INT8_TYPE.as_pointer()
        self._llvm.BUFFER_OWNER_HANDLE_TYPE = self._llvm.OPAQUE_POINTER_TYPE
        buffer_view_type = self._llvm.module.context.get_identified_type(
            BUFFER_VIEW_TYPE_NAME
        )
        if buffer_view_type.is_opaque:
            buffer_view_type.set_body(
                self._llvm.OPAQUE_POINTER_TYPE,
                self._llvm.BUFFER_OWNER_HANDLE_TYPE,
                self._llvm.OPAQUE_POINTER_TYPE,
                self._llvm.INT32_TYPE,
                self._llvm.INT64_TYPE.as_pointer(),
                self._llvm.INT64_TYPE.as_pointer(),
                self._llvm.INT64_TYPE,
                self._llvm.INT32_TYPE,
            )
        self._llvm.BUFFER_VIEW_TYPE = buffer_view_type
        self._llvm.ARRAY_BUILDER_HANDLE_TYPE = self._llvm.OPAQUE_POINTER_TYPE
        self._llvm.ARRAY_HANDLE_TYPE = self._llvm.OPAQUE_POINTER_TYPE
        self._llvm.ARROW_ARRAY_BUILDER_HANDLE_TYPE = (
            self._llvm.ARRAY_BUILDER_HANDLE_TYPE
        )
        self._llvm.ARROW_ARRAY_HANDLE_TYPE = self._llvm.ARRAY_HANDLE_TYPE
        self._llvm.TENSOR_BUILDER_HANDLE_TYPE = self._llvm.OPAQUE_POINTER_TYPE
        self._llvm.TENSOR_HANDLE_TYPE = self._llvm.OPAQUE_POINTER_TYPE
        self._llvm.ARROW_TENSOR_BUILDER_HANDLE_TYPE = (
            self._llvm.TENSOR_BUILDER_HANDLE_TYPE
        )
        self._llvm.ARROW_TENSOR_HANDLE_TYPE = self._llvm.TENSOR_HANDLE_TYPE
        self._llvm.TABLE_HANDLE_TYPE = self._llvm.OPAQUE_POINTER_TYPE
        self._llvm.CHUNKED_ARRAY_HANDLE_TYPE = self._llvm.OPAQUE_POINTER_TYPE
        self._llvm.ARROW_TABLE_HANDLE_TYPE = self._llvm.TABLE_HANDLE_TYPE
        self._llvm.ARROW_CHUNKED_ARRAY_HANDLE_TYPE = (
            self._llvm.CHUNKED_ARRAY_HANDLE_TYPE
        )
        self._llvm.TIME_TYPE = ir.LiteralStructType(
            [
                self._llvm.INT32_TYPE,
                self._llvm.INT32_TYPE,
                self._llvm.INT32_TYPE,
            ]
        )
        self._llvm.TIMESTAMP_TYPE = ir.LiteralStructType(
            [
                self._llvm.INT32_TYPE,
                self._llvm.INT32_TYPE,
                self._llvm.INT32_TYPE,
                self._llvm.INT32_TYPE,
                self._llvm.INT32_TYPE,
                self._llvm.INT32_TYPE,
                self._llvm.INT32_TYPE,
            ]
        )
        self._llvm.DATETIME_TYPE = ir.LiteralStructType(
            [
                self._llvm.INT32_TYPE,
                self._llvm.INT32_TYPE,
                self._llvm.INT32_TYPE,
                self._llvm.INT32_TYPE,
                self._llvm.INT32_TYPE,
                self._llvm.INT32_TYPE,
            ]
        )

    def _add_builtins(self) -> None:
        """
        title: Add builtins.
        """
        putchar_ty = ir.FunctionType(
            self._llvm.INT32_TYPE,
            [self._llvm.INT32_TYPE],
        )
        putchar = ir.Function(self._llvm.module, putchar_ty, "putchar")

        putchard_ty = ir.FunctionType(
            self._llvm.INT32_TYPE,
            [self._llvm.DOUBLE_TYPE],
        )
        putchard = ir.Function(self._llvm.module, putchard_ty, "putchard")

        ir_builder = ir.IRBuilder(putchard.append_basic_block("entry"))
        ival = ir_builder.fptoui(
            putchard.args[0], self._llvm.INT32_TYPE, "intcast"
        )
        ir_builder.call(putchar, [ival])
        ir_builder.ret(ir.Constant(self._llvm.INT32_TYPE, 0))

    def get_function(self, name: str) -> ir.Function | None:
        """
        title: Get function.
        parameters:
          name:
            type: str
        returns:
          type: ir.Function | None
        """
        if name in self.module_state.llvm_functions_by_symbol_id:
            return self.module_state.llvm_functions_by_symbol_id[name]

        if name in self._llvm.module.globals:
            return cast(ir.Function, self._llvm.module.get_global(name))

        if name in self.module_state.function_protos:
            self.visit(self.module_state.function_protos[name])
            return cast(
                ir.Function, safe_pop(self.function_state.result_stack)
            )

        return None

    def create_entry_block_alloca(
        self,
        var_name: str,
        type_name: str | ir.Type,
    ) -> ir.AllocaInstr:
        """
        title: Create entry block alloca.
        parameters:
          var_name:
            type: str
          type_name:
            type: str | ir.Type
        returns:
          type: ir.AllocaInstr
        """
        llvm_type = (
            self._llvm.get_data_type(type_name)
            if isinstance(type_name, str)
            else type_name
        )
        current_block = self._llvm.ir_builder.block
        self._llvm.ir_builder.position_at_start(
            self._llvm.ir_builder.function.entry_basic_block
        )
        alloca = self._llvm.ir_builder.alloca(llvm_type, None, var_name)
        if current_block is not None:
            self._llvm.ir_builder.position_at_end(current_block)
        return alloca
