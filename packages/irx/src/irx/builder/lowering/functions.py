# mypy: disable-error-code=no-redef

"""
title: Function visitor mixins for llvmliteir.
"""

from typing import Any, Sequence, cast

import astx

from llvmlite import ir

from irx.analysis.arrow_conversion import ARROW_RESOURCES
from irx.analysis.ownership import resource_ownership
from irx.analysis.resolved_nodes import (
    CallingConvention,
    CallResolution,
    ClassHeaderFieldKind,
    FunctionSignature,
    MethodDispatchKind,
    OwnershipEscapeKind,
    OwnershipKind,
    OwnershipTransferKind,
    ResolvedMethodCall,
    ResourceKind,
    ReturnResolution,
    SemanticFunction,
    SemanticInfo,
)
from irx.analysis.types import display_type_name
from irx.builder.core import (
    VisitorCore,
    semantic_symbol_key,
)
from irx.builder.diagnostics import (
    raise_lowering_error,
    raise_lowering_internal_error,
    require_lowered_value,
    require_semantic_metadata,
)
from irx.builder.lowering.classes import ClassVisitorMixin
from irx.builder.lowering.table_io import lower_table_io
from irx.builder.runtime import safe_pop
from irx.builder.runtime.record_batch_api import is_checked_native_facade
from irx.builder.state import (
    CleanupAction,
    CleanupEmitter,
    CleanupKind,
    PendingReturn,
)
from irx.builder.types import is_int_type
from irx.builtins.collections.list import (
    LIST_DESTROY_SYMBOL,
    LIST_RUNTIME_FEATURE,
)
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@typechecked
class FunctionVisitorMixin(ClassVisitorMixin):
    def _register_call_result_cleanup(
        self,
        node: astx.AST,
        result: ir.Value,
    ) -> None:
        """
        title: Materialize and register cleanup for one owned list call result.
        parameters:
          node:
            type: astx.AST
          result:
            type: ir.Value
        """
        ownership = resource_ownership(node)
        if ownership is None or ownership.kind is not OwnershipKind.OWNED:
            return
        if (
            ownership.transfer_kind is OwnershipTransferKind.MOVE
            or ownership.escape_kind is OwnershipEscapeKind.RETURN
        ):
            return
        if ownership.resource_kind is ResourceKind.STRING:
            self._register_owned_string_temporary(node, result)
            return
        if ownership.resource_kind in {ResourceKind.CLASS, *ARROW_RESOURCES}:
            self.class_cleanup(node, result)
            return
        if ownership.resource_kind is not ResourceKind.LIST:
            raise_lowering_internal_error(
                "call result has an unsupported owned resource kind",
                node=node,
            )
        current_block = self._llvm.ir_builder.block
        result_ptr = self.create_entry_block_alloca(
            "owned_list_call_result",
            result.type,
        )
        initializer_builder = ir.IRBuilder(
            self._llvm.ir_builder.function.entry_basic_block
        )
        initializer_builder.position_after(result_ptr)
        initializer_builder.store(
            cast(Any, self)._empty_list_value_for_type(
                self._resolved_ast_type(node)
            ),
            result_ptr,
        )
        self._llvm.ir_builder.position_at_end(current_block)
        self._llvm.ir_builder.store(result, result_ptr)
        self._register_owned_list_temporary(node, result_ptr)

    def _return_cleanup_exclusions(
        self,
        node: astx.FunctionReturn,
    ) -> frozenset[str]:
        """
        title: Return owner ids moved out through one return statement.
        parameters:
          node:
            type: astx.FunctionReturn
        returns:
          type: frozenset[str]
        """
        ownership = resource_ownership(node)
        if ownership is None:
            return frozenset()
        if (
            ownership.transfer_kind is not OwnershipTransferKind.MOVE
            or ownership.escape_kind is not OwnershipEscapeKind.RETURN
            or ownership.source_symbol_id is None
        ):
            return frozenset()
        return frozenset({ownership.source_symbol_id})

    def _semantic_function(
        self,
        node: astx.AST,
        *,
        label: str,
    ) -> SemanticFunction:
        """
        title: Return the resolved semantic function for one node.
        parameters:
          node:
            type: astx.AST
          label:
            type: str
        returns:
          type: SemanticFunction
        """
        semantic = getattr(node, "semantic", None)
        function = getattr(semantic, "resolved_function", None)
        return require_semantic_metadata(
            cast(SemanticFunction | None, function),
            node=node,
            metadata="resolved_function",
            context=label,
        )

    def _semantic_signature(
        self,
        node: astx.AST,
        *,
        label: str,
    ) -> FunctionSignature:
        """
        title: Return the resolved semantic signature for one node.
        parameters:
          node:
            type: astx.AST
          label:
            type: str
        returns:
          type: FunctionSignature
        """
        return self._semantic_function(node, label=label).signature

    def _semantic_call_resolution(
        self,
        node: astx.FunctionCall,
    ) -> CallResolution:
        """
        title: Return the resolved semantic call metadata for one call.
        parameters:
          node:
            type: astx.FunctionCall
        returns:
          type: CallResolution
        """
        semantic = getattr(node, "semantic", None)
        resolution = getattr(semantic, "resolved_call", None)
        return require_semantic_metadata(
            cast(CallResolution | None, resolution),
            node=node,
            metadata="resolved_call",
            context=f"call to '{node.fn}'",
        )

    def _semantic_method_call(
        self,
        node: astx.BaseMethodCall | astx.MethodCall | astx.StaticMethodCall,
    ) -> ResolvedMethodCall:
        """
        title: Return the resolved semantic method-call metadata for one call.
        parameters:
          node:
            type: astx.BaseMethodCall | astx.MethodCall | astx.StaticMethodCall
        returns:
          type: ResolvedMethodCall
        """
        semantic = getattr(node, "semantic", None)
        resolution = getattr(semantic, "resolved_method_call", None)
        return require_semantic_metadata(
            cast(ResolvedMethodCall | None, resolution),
            node=node,
            metadata="resolved_method_call",
            context="method call lowering",
        )

    def _lower_explicit_call_arguments(
        self,
        *,
        args: Sequence[astx.AST],
        resolution: CallResolution,
        label: str,
    ) -> list[ir.Value]:
        """
        title: Lower one semantically validated explicit call argument list.
        parameters:
          args:
            type: Sequence[astx.AST]
          resolution:
            type: CallResolution
          label:
            type: str
        returns:
          type: list[ir.Value]
        """
        llvm_args: list[ir.Value] = []
        for index, arg in enumerate(args):
            self.visit_child(arg)
            llvm_arg = require_lowered_value(
                safe_pop(self.result_stack),
                node=arg,
                context=f"argument {index + 1} of {label}",
            )
            self.class_pin(arg, llvm_arg)
            target_type = (
                resolution.resolved_argument_types[index]
                if index < len(resolution.resolved_argument_types)
                else None
            )
            llvm_args.append(
                self._cast_ast_value(
                    llvm_arg,
                    source_type=self._resolved_ast_type(arg),
                    target_type=target_type,
                )
            )
        return llvm_args

    def _bind_temporary_call_symbol(
        self,
        *,
        symbol_name: str,
        symbol_id: str,
        llvm_value: ir.Value,
        saved_bindings: dict[str, Any | None],
    ) -> None:
        """
        title: Bind one temporary symbol while lowering default arguments.
        parameters:
          symbol_name:
            type: str
          symbol_id:
            type: str
          llvm_value:
            type: ir.Value
          saved_bindings:
            type: dict[str, Any | None]
        """
        if symbol_id not in saved_bindings:
            saved_bindings[symbol_id] = self.named_values.get(symbol_id)
        alloca = self.create_entry_block_alloca(symbol_name, llvm_value.type)
        self._llvm.ir_builder.store(llvm_value, alloca)
        self.named_values[symbol_id] = alloca

    def _restore_temporary_call_bindings(
        self,
        saved_bindings: dict[str, Any | None],
    ) -> None:
        """
        title: Restore the temporary symbol bindings used for one call.
        parameters:
          saved_bindings:
            type: dict[str, Any | None]
        """
        for symbol_id, previous in saved_bindings.items():
            if previous is None:
                self.named_values.pop(symbol_id, None)
                continue
            self.named_values[symbol_id] = previous

    def lower_bound_call_arguments(
        self,
        resolution: CallResolution,
        *,
        receiver_value: ir.Value | None = None,
    ) -> list[ir.Value]:
        """
        title: >-
          Evaluate in source order, fill defaults, then assemble ABI slots.
        parameters:
          resolution:
            type: CallResolution
          receiver_value:
            type: ir.Value | None
        returns:
          type: list[ir.Value]
        """
        plan = require_semantic_metadata(
            resolution.arguments,
            node=resolution.callee.function.prototype,
            metadata="arguments",
            context="bound call",
        )
        explicit = self._lower_explicit_call_arguments(
            args=plan.evaluations,
            resolution=resolution,
            label="bound call",
        )
        values: list[ir.Value | None] = [None] * plan.argument_count
        for index, value in zip(plan.indices, explicit):
            values[index] = value
        saved: dict[str, Any | None] = {}
        defaults = {item.index: item for item in plan.defaults}
        try:
            if plan.receiver is not None and plan.defaults:
                if receiver_value is None:
                    raise_lowering_internal_error(
                        "method defaults require a resolved receiver",
                        node=resolution.callee.function.prototype,
                    )
                self._bind_temporary_call_symbol(
                    symbol_name=plan.receiver.name,
                    symbol_id=plan.receiver.symbol_id,
                    llvm_value=receiver_value,
                    saved_bindings=saved,
                )
            for index in range(len(resolution.signature.parameters)):
                default = defaults.get(index)
                if default is not None:
                    self.visit_child(default.expression)
                    value = require_lowered_value(
                        safe_pop(self.result_stack),
                        node=default.expression,
                        context="default call argument",
                    )
                    self.class_pin(default.expression, value)
                    values[index] = self._cast_ast_value(
                        value,
                        source_type=self._resolved_ast_type(
                            default.expression
                        ),
                        target_type=default.type_,
                    )
                value = values[index]
                if value is None:
                    raise_lowering_internal_error(
                        "bound call contains an unpopulated parameter slot",
                        node=resolution.callee.function.prototype,
                    )
                if plan.defaults and index < len(plan.parameters):
                    symbol = plan.parameters[index]
                    self._bind_temporary_call_symbol(
                        symbol_name=symbol.name,
                        symbol_id=symbol.symbol_id,
                        llvm_value=value,
                        saved_bindings=saved,
                    )
            if any(value is None for value in values):
                raise_lowering_internal_error(
                    "bound call contains an unpopulated variadic slot",
                    node=resolution.callee.function.prototype,
                )
            return [cast(ir.Value, value) for value in values]
        finally:
            self._restore_temporary_call_bindings(saved)

    def _indirect_method_callee(
        self,
        *,
        node: astx.AST,
        method_resolution: ResolvedMethodCall,
        receiver_value: ir.Value,
    ) -> ir.Value:
        """
        title: Lower one dispatch-table lookup for an instance method.
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
        receiver_class = method_resolution.receiver_class
        if receiver_class is None or receiver_class.layout is None:
            raise_lowering_internal_error(
                "method call is missing receiver class layout metadata",
                node=node,
            )
        dispatch_header = next(
            (
                field
                for field in receiver_class.layout.header_fields
                if field.kind is ClassHeaderFieldKind.DISPATCH_TABLE
            ),
            None,
        )
        if dispatch_header is None or method_resolution.slot_index is None:
            raise_lowering_internal_error(
                "method call is missing dispatch slot metadata",
                node=node,
            )
        dispatch_addr = self._llvm.ir_builder.gep(
            receiver_value,
            [
                ir.Constant(self._llvm.INT32_TYPE, 0),
                ir.Constant(
                    self._llvm.INT32_TYPE,
                    dispatch_header.storage_index,
                ),
            ],
            inbounds=True,
            name=f"{method_resolution.member.name}_dispatch_addr",
        )
        dispatch_raw = self._llvm.ir_builder.load(
            dispatch_addr,
            f"{method_resolution.member.name}_dispatch",
        )
        dispatch_type = ir.ArrayType(
            self._llvm.OPAQUE_POINTER_TYPE,
            receiver_class.layout.dispatch_table_size,
        )
        dispatch_ptr = self._llvm.ir_builder.bitcast(
            dispatch_raw,
            dispatch_type.as_pointer(),
            name=f"{method_resolution.member.name}_dispatch_ptr",
        )
        callee_addr = self._llvm.ir_builder.gep(
            dispatch_ptr,
            [
                ir.Constant(self._llvm.INT32_TYPE, 0),
                ir.Constant(
                    self._llvm.INT32_TYPE,
                    method_resolution.slot_index,
                ),
            ],
            inbounds=True,
            name=f"{method_resolution.member.name}_slot",
        )
        callee_raw = self._llvm.ir_builder.load(
            callee_addr,
            f"{method_resolution.member.name}_raw",
        )
        function_ptr_type = self._llvm_function_type_for_signature(
            method_resolution.function.signature
        ).as_pointer()
        return self._llvm.ir_builder.bitcast(
            callee_raw,
            function_ptr_type,
            name=f"{method_resolution.member.name}_callee",
        )

    def _semantic_return_resolution(
        self,
        node: astx.FunctionReturn,
    ) -> ReturnResolution:
        """
        title: Return the resolved semantic return metadata for one return.
        parameters:
          node:
            type: astx.FunctionReturn
        returns:
          type: ReturnResolution
        """
        semantic = getattr(node, "semantic", None)
        resolution = getattr(semantic, "resolved_return", None)
        return require_semantic_metadata(
            cast(ReturnResolution | None, resolution),
            node=node,
            metadata="resolved_return",
            context="return lowering",
        )

    def _apply_calling_convention(
        self,
        signature: FunctionSignature,
    ) -> None:
        """
        title: Preserve semantic calling-convention intent in lowering.
        parameters:
          signature:
            type: FunctionSignature
        """
        if signature.calling_convention in {
            CallingConvention.IRX_DEFAULT,
            CallingConvention.C,
        }:
            return
        raise_lowering_internal_error(
            "unsupported semantic calling convention "
            f"'{signature.calling_convention.value}'",
            node=None,
        )

    def _llvm_function_type_for_signature(
        self,
        signature: FunctionSignature,
    ) -> ir.FunctionType:
        """
        title: Return the LLVM function type for one semantic signature.
        parameters:
          signature:
            type: FunctionSignature
        returns:
          type: ir.FunctionType
        """
        args_type: list[ir.Type] = []
        for parameter in signature.parameters:
            llvm_type = self._llvm_type_for_ast_type(parameter.type_)
            if llvm_type is None:
                raise_lowering_error(
                    "cannot lower parameter "
                    f"'{parameter.name}' of '{signature.name}' with type "
                    f"{display_type_name(parameter.type_)}",
                    code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                )
            args_type.append(llvm_type)

        return_type = self._llvm_type_for_ast_type(signature.return_type)
        if return_type is None:
            raise_lowering_error(
                "cannot lower return type "
                f"{display_type_name(signature.return_type)} for "
                f"'{signature.name}'",
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
            )
        self._apply_calling_convention(signature)
        if signature.exception_abi:
            args_type.insert(0, ir.IntType(8).as_pointer())
            if not isinstance(return_type, ir.VoidType):
                args_type.append(return_type.as_pointer())
            return_type = ir.IntType(32)
        return ir.FunctionType(
            return_type,
            args_type,
            signature.is_variadic,
        )

    def _declare_semantic_function(
        self,
        function: SemanticFunction,
    ) -> ir.Function:
        """
        title: Declare or reuse one LLVM function from semantic metadata.
        parameters:
          function:
            type: SemanticFunction
        returns:
          type: ir.Function
        """
        function_key = function.symbol_id
        existing = self.llvm_functions_by_symbol_id.get(function_key)
        if existing is not None:
            return existing

        signature = function.signature
        fn_type = self._llvm_function_type_for_signature(signature)
        llvm_name = self.llvm_function_name_for_node(
            function.prototype,
            function.name,
        )
        fn: ir.Function | None = None
        declared_feature_name: str | None = None
        for feature_name in signature.required_runtime_features:
            if self.runtime_features.feature_declares_symbol(
                feature_name,
                signature.symbol_name,
            ):
                fn = self.require_runtime_symbol(
                    feature_name,
                    signature.symbol_name,
                )
                declared_feature_name = feature_name
                checked = is_checked_native_facade(
                    signature.symbol_name,
                    feature_name,
                    self.runtime_features.feature(feature_name).metadata.get(
                        "checked_facade_abi"
                    ),
                )
                expected = fn_type
                if checked:
                    arguments = list(fn_type.args)
                    if not isinstance(fn_type.return_type, ir.VoidType):
                        arguments.append(fn_type.return_type.as_pointer())
                    arguments.append(ir.IntType(8).as_pointer())
                    expected = ir.FunctionType(ir.IntType(32), arguments)
                if fn.function_type != expected:
                    raise_lowering_error(
                        f"runtime feature '{feature_name}' declares symbol "
                        f"'{signature.symbol_name}' with an incompatible "
                        "LLVM signature",
                        code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                        node=function.prototype,
                    )
                break

        for feature_name in signature.required_runtime_features:
            if feature_name == declared_feature_name:
                continue
            self.activate_runtime_feature(feature_name)

        if fn is None:
            global_value = self._llvm.module.globals.get(llvm_name)
            if global_value is not None:
                if not isinstance(global_value, ir.Function):
                    raise_lowering_internal_error(
                        f"global '{llvm_name}' is not a function",
                        node=function.prototype,
                    )
                if global_value.function_type != fn_type:
                    raise_lowering_error(
                        f"function '{llvm_name}' already exists with an "
                        "incompatible LLVM signature",
                        code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                        node=function.prototype,
                    )
                fn = global_value
            else:
                fn = ir.Function(self._llvm.module, fn_type, llvm_name)
                if signature.is_extern or function.definition is None:
                    fn.linkage = "external"

        offset = int(signature.exception_abi)
        if offset:
            fn.args[0].name = "context"
        for idx, symbol in enumerate(function.args):
            fn.args[idx + offset].name = symbol.name
        if offset and not isinstance(signature.return_type, astx.NoneType):
            fn.args[-1].name = "result_out"
        self.llvm_function_signatures[fn.name] = signature

        self.function_protos[function_key] = function.prototype
        self.llvm_functions_by_symbol_id[function_key] = fn
        return fn

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.FunctionCall) -> None:
        """
        title: Visit FunctionCall nodes.
        parameters:
          node:
            type: astx.FunctionCall
        """
        if lower_table_io(self, node):
            return
        semantic = getattr(node, "semantic", None)
        if (
            isinstance(semantic, SemanticInfo)
            and semantic.resolved_class_construction is not None
        ):
            self.lower_class_construct(
                node, semantic.resolved_class_construction
            )
            return
        if (
            isinstance(semantic, SemanticInfo)
            and semantic.resolved_file_open is not None
        ):
            self.lower_file_open(node)
            return
        resolution = self._semantic_call_resolution(node)
        target_function = resolution.callee.function
        callee_f = self._declare_semantic_function(target_function)
        llvm_args = self.lower_bound_call_arguments(resolution)
        self._apply_calling_convention(resolution.signature)
        result = self.emit_resolved_call(
            node, callee_f, resolution.signature, llvm_args
        )
        if result is None:
            return
        self._register_call_result_cleanup(node, result)
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.MethodCall) -> None:
        """
        title: Visit MethodCall nodes.
        parameters:
          node:
            type: astx.MethodCall
        """
        if lower_table_io(self, node):
            return
        semantic = getattr(node, "semantic", None)
        if (
            isinstance(semantic, SemanticInfo)
            and semantic.resolved_class_construction is not None
        ):
            self.lower_class_construct(
                node, semantic.resolved_class_construction
            )
            return
        if (
            isinstance(semantic, SemanticInfo)
            and semantic.resolved_file_operation is not None
        ):
            self.lower_file_method(node)
            return
        module_member = getattr(
            semantic,
            "resolved_module_member_access",
            None,
        )
        if module_member is not None:
            resolution = require_semantic_metadata(
                cast(
                    CallResolution | None,
                    getattr(semantic, "resolved_call", None),
                ),
                node=node,
                metadata="resolved_call",
                context=(
                    f"module namespace call '{module_member.member_name}'"
                ),
            )
            function = require_semantic_metadata(
                cast(
                    SemanticFunction | None,
                    getattr(semantic, "resolved_function", None),
                ),
                node=node,
                metadata="resolved_function",
                context=(
                    f"module namespace call '{module_member.member_name}'"
                ),
            )
            callee = self._declare_semantic_function(function)
            self.visit_child(node.receiver)
            _ = safe_pop(self.result_stack)
            llvm_args = self.lower_bound_call_arguments(resolution)
            self._apply_calling_convention(function.signature)
            result = self.emit_resolved_call(
                node, callee, function.signature, llvm_args
            )
            if result is None:
                return
            self._register_call_result_cleanup(node, result)
            self.result_stack.append(result)
            return

        method_resolution = self._semantic_method_call(node)
        self.visit_child(node.receiver)
        receiver_value = require_lowered_value(
            safe_pop(self.result_stack),
            node=node.receiver,
            context=f"receiver for '{method_resolution.member.name}'",
        )
        self.class_operation(node.receiver, "require", receiver_value)
        self.class_pin(node.receiver, receiver_value)
        receiver_parameter_type = (
            method_resolution.function.signature.parameters[0].type_
            if method_resolution.function.signature.parameters
            else None
        )
        lowered_receiver = self._cast_ast_value(
            receiver_value,
            source_type=self._resolved_ast_type(node.receiver),
            target_type=receiver_parameter_type,
        )
        llvm_args = self.lower_bound_call_arguments(
            method_resolution.call,
            receiver_value=lowered_receiver,
        )
        lowered_args = [lowered_receiver, *llvm_args]
        callee: ir.Value
        if method_resolution.dispatch_kind is MethodDispatchKind.INDIRECT:
            callee = self._indirect_method_callee(
                node=node,
                method_resolution=method_resolution,
                receiver_value=receiver_value,
            )
        else:
            callee = self._declare_semantic_function(
                method_resolution.function
            )
        self._apply_calling_convention(method_resolution.function.signature)
        result = self.emit_resolved_call(
            node, callee, method_resolution.function.signature, lowered_args
        )
        if result is None:
            return
        self._register_call_result_cleanup(node, result)
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.BaseMethodCall) -> None:
        """
        title: Visit BaseMethodCall nodes.
        parameters:
          node:
            type: astx.BaseMethodCall
        """
        method_resolution = self._semantic_method_call(node)
        self.visit_child(node.receiver)
        receiver_value = require_lowered_value(
            safe_pop(self.result_stack),
            node=node.receiver,
            context=(
                f"receiver for '{method_resolution.class_.name}."
                f"{method_resolution.member.name}'"
            ),
        )
        self.class_operation(node.receiver, "require", receiver_value)
        self.class_pin(node.receiver, receiver_value)
        receiver_parameter_type = (
            method_resolution.function.signature.parameters[0].type_
            if method_resolution.function.signature.parameters
            else None
        )
        lowered_receiver = self._cast_ast_value(
            receiver_value,
            source_type=self._resolved_ast_type(node.receiver),
            target_type=receiver_parameter_type,
        )
        llvm_args = self.lower_bound_call_arguments(
            method_resolution.call,
            receiver_value=lowered_receiver,
        )
        lowered_args = [lowered_receiver, *llvm_args]
        callee = self._declare_semantic_function(method_resolution.function)
        self._apply_calling_convention(method_resolution.function.signature)
        result = self.emit_resolved_call(
            node, callee, method_resolution.function.signature, lowered_args
        )
        if result is None:
            return
        self._register_call_result_cleanup(node, result)
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.StaticMethodCall) -> None:
        """
        title: Visit StaticMethodCall nodes.
        parameters:
          node:
            type: astx.StaticMethodCall
        """
        method_resolution = self._semantic_method_call(node)
        callee = self._declare_semantic_function(method_resolution.function)
        llvm_args = self.lower_bound_call_arguments(method_resolution.call)
        self._apply_calling_convention(method_resolution.function.signature)
        result = self.emit_resolved_call(
            node, callee, method_resolution.function.signature, llvm_args
        )
        if result is None:
            return
        self._register_call_result_cleanup(node, result)
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.FunctionDef) -> None:
        """
        title: Visit FunctionDef nodes.
        parameters:
          node:
            type: astx.FunctionDef
        """
        function = self._semantic_function(
            node,
            label="function definition",
        )
        generator = getattr(
            getattr(node, "semantic", None),
            "resolved_generator_function",
            None,
        )
        if generator is not None:
            cast(Any, self)._lower_generator_function(node, generator)
            return
        signature = function.signature
        function_key = function.symbol_id
        fn = self._declare_semantic_function(function)
        if function_key in self._emitted_function_bodies:
            self.result_stack.append(fn)
            return

        basic_block = fn.append_basic_block("entry")
        self._llvm.ir_builder = ir.IRBuilder(basic_block)
        previous_return_type = self._current_function_return_type
        previous_signature = self._current_function_signature
        previous_cleanups = self.cleanup_stack
        self.cleanup_stack = []
        previous_construction = self.class_construction_stack
        self.class_construction_stack = []
        self._current_function_return_type = signature.return_type
        self._current_function_signature = signature
        previous_exception_state = (
            self.exception_context,
            self.exception_result_slot,
            self.exception_targets,
            self.pending_returns,
        )
        self.exception_context = (
            fn.args[0] if signature.exception_abi else None
        )
        self.exception_result_slot = (
            fn.args[-1]
            if signature.exception_abi
            and not isinstance(signature.return_type, astx.NoneType)
            else None
        )
        self.exception_targets = []
        self.pending_returns = []

        try:
            hidden_parameter_count = len(function.args) - len(
                function.prototype.args.nodes
            )
            offset = int(signature.exception_abi)
            source_args = fn.args[offset : offset + len(function.args)]
            for idx, llvm_arg in enumerate(source_args):
                arg_symbol = function.args[idx]
                arg_type = self._llvm_type_for_ast_type(
                    signature.parameters[idx].type_
                )
                if arg_type is None:
                    parameter_type_name = display_type_name(
                        signature.parameters[idx].type_
                    )
                    parameter_node = (
                        function.prototype.args.nodes[
                            idx - hidden_parameter_count
                        ]
                        if idx >= hidden_parameter_count
                        else function.prototype
                    )
                    raise_lowering_error(
                        "cannot lower parameter "
                        f"'{arg_symbol.name}' of '{function.name}' with "
                        f"type {parameter_type_name}",
                        code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                        node=parameter_node,
                    )
                alloca = self._llvm.ir_builder.alloca(
                    arg_type,
                    name=arg_symbol.name,
                )
                self._llvm.ir_builder.store(llvm_arg, alloca)
                if idx < hidden_parameter_count:
                    symbol_key = arg_symbol.symbol_id
                else:
                    symbol_key = semantic_symbol_key(
                        function.prototype.args.nodes[
                            idx - hidden_parameter_count
                        ],
                        arg_symbol.symbol_id,
                    )
                self.named_values[symbol_key] = alloca
                if idx >= hidden_parameter_count:
                    argument = function.prototype.args.nodes[
                        idx - hidden_parameter_count
                    ]
                    ownership = resource_ownership(argument)
                    if (
                        ownership is not None
                        and ownership.resource_kind
                        in {ResourceKind.CLASS, *ARROW_RESOURCES}
                        and ownership.kind is OwnershipKind.OWNED
                    ):
                        self.class_acquire(argument, llvm_arg)
                        self.class_cleanup(
                            argument, alloca, symbol_key, storage=True
                        )
                if idx == 0 and signature.metadata.get("is_class_initializer"):
                    self.class_construction_stack = [llvm_arg]

            self.visit_child(node.body)
            if not self._llvm.ir_builder.block.is_terminated:
                if isinstance(signature.return_type, astx.NoneType):
                    self._emit_active_cleanups()
                    if not self._llvm.ir_builder.block.is_terminated:
                        self.emit_success_return(None)
                else:
                    raise_lowering_internal_error(
                        f"function '{function.name}' reached lowering "
                        "without a terminating return",
                        node=node,
                        notes=(
                            "semantic analysis should reject reachable "
                            "non-void fallthrough before lowering",
                        ),
                    )
        finally:
            self.cleanup_stack = previous_cleanups
            self.class_construction_stack = previous_construction
            self._current_function_return_type = previous_return_type
            self._current_function_signature = previous_signature
            (
                self.exception_context,
                self.exception_result_slot,
                self.exception_targets,
                self.pending_returns,
            ) = previous_exception_state

        self._emitted_function_bodies.add(function_key)
        self.result_stack.append(fn)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.FunctionPrototype) -> None:
        """
        title: Visit FunctionPrototype nodes.
        parameters:
          node:
            type: astx.FunctionPrototype
        """
        function = self._semantic_function(
            node,
            label="function prototype",
        )
        if function.signature.metadata.get("table_io") is not None:
            return
        fn = self._declare_semantic_function(function)
        self.result_stack.append(fn)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.FunctionReturn) -> None:
        """
        title: Visit FunctionReturn nodes.
        parameters:
          node:
            type: astx.FunctionReturn
        """
        if self._current_generator_frame_ptr is not None:
            if node.value is not None and not isinstance(
                node.value, astx.LiteralNone
            ):
                depth = len(self.result_stack)
                self.visit_child(node.value)
                del self.result_stack[depth:]
            cast(Any, self)._emit_generator_stop(node)
            return
        return_resolution = self._semantic_return_resolution(node)
        if return_resolution.returns_void:
            if node.value is not None and not isinstance(
                node.value, astx.LiteralNone
            ):
                depth = len(self.result_stack)
                self.visit_child(node.value)
                del self.result_stack[depth:]
            self._emit_active_cleanups()
            if not self._llvm.ir_builder.block.is_terminated:
                completed_cleanups = self.cleanup_stack
                self.cleanup_stack = []
                try:
                    self.abandon_pending_returns()
                    self.emit_success_return(None)
                finally:
                    self.cleanup_stack = completed_cleanups
            return

        if node.value is not None:
            self.visit_child(node.value)
            retval = require_lowered_value(
                safe_pop(self.result_stack),
                node=node.value,
                context="return expression",
            )
        else:
            retval = None

        if retval is None:
            raise_lowering_internal_error(
                "return expression did not lower to a value",
                node=node,
            )

        retval = self._cast_ast_value(
            retval,
            source_type=self._resolved_ast_type(node.value),
            target_type=return_resolution.expected_type,
        )
        return_ownership = resource_ownership(node)
        preserve_source = (
            return_ownership is not None
            and return_ownership.source_symbol_id is not None
            and return_ownership.resource_kind
            in {ResourceKind.STRING, ResourceKind.CLASS, *ARROW_RESOURCES}
            and (
                bool(self.pending_returns)
                or any(
                    item.kind is CleanupKind.FINALLY
                    for item in self.cleanup_stack
                )
            )
        )
        if (
            return_ownership is not None
            and return_ownership.resource_kind
            in {
                ResourceKind.CLASS,
                *ARROW_RESOURCES,
            }
            and (
                preserve_source
                or return_ownership.transfer_kind
                is not OwnershipTransferKind.MOVE
            )
        ):
            self.class_operation(node, "retain", retval)
        if (
            return_ownership is not None
            and return_ownership.resource_kind is ResourceKind.STRING
            and (
                preserve_source
                or return_ownership.transfer_kind is OwnershipTransferKind.COPY
            )
        ):
            retval = self._copy_string_to_heap(node, retval)
        fn_return_type = self._llvm_type_for_ast_type(
            return_resolution.expected_type
        )
        if is_int_type(fn_return_type) and fn_return_type.width == 1:
            if is_int_type(retval.type) and retval.type.width != 1:
                retval = self._llvm.ir_builder.trunc(retval, ir.IntType(1))
        previous_pending = self.pending_returns
        actions: list[CleanupEmitter] = []
        if return_ownership is not None:
            if return_ownership.resource_kind in {
                ResourceKind.CLASS,
                *ARROW_RESOURCES,
            }:
                actions.append(
                    lambda: self.class_operation(node, "release", retval)
                )
            elif return_ownership.resource_kind is ResourceKind.STRING:
                free = self.require_runtime_symbol("libc", "free")

                def abandon_string() -> None:
                    """
                    title: Release a string result whose return was replaced.
                    """
                    self._llvm.ir_builder.call(free, [retval])

                actions.append(abandon_string)
            elif return_ownership.resource_kind is ResourceKind.LIST:
                returned_list = self.create_entry_block_alloca(
                    "return.list", retval.type
                )
                self._llvm.ir_builder.store(retval, returned_list)
                destroy = self.require_runtime_symbol(
                    LIST_RUNTIME_FEATURE, LIST_DESTROY_SYMBOL
                )

                def abandon_list() -> None:
                    """
                    title: Destroy a moved list whose return was replaced.
                    """
                    self._llvm.ir_builder.call(destroy, [returned_list])

                actions.append(abandon_list)
        restore_depth = None
        if (
            return_ownership is not None
            and return_ownership.resource_kind is ResourceKind.LIST
            and return_ownership.transfer_kind is OwnershipTransferKind.MOVE
            and return_ownership.source_symbol_id is not None
        ):
            restore_depth = next(
                (
                    index
                    for index, action in enumerate(self.cleanup_stack)
                    if action.owner_symbol_id
                    == return_ownership.source_symbol_id
                ),
                None,
            )
        completion = PendingReturn(
            tuple(actions),
            tuple(self.exception_targets),
            tuple(self.loop_stack),
            restore_depth,
        )
        self.pending_returns = [*previous_pending, completion]
        original_cleanups = self.cleanup_stack
        exclusions = (
            frozenset()
            if preserve_source
            else self._return_cleanup_exclusions(node)
        )
        self.cleanup_stack = [
            CleanupAction(
                lambda: None,
                owner_symbol_id=item.owner_symbol_id,
                fallible=False,
            )
            if item.owner_symbol_id in exclusions
            else item
            for item in original_cleanups
        ]
        try:
            self._emit_active_cleanups()
            if not self._llvm.ir_builder.block.is_terminated:
                self.cleanup_stack = []
                self.abandon_pending_returns(tuple(previous_pending))
                self.emit_success_return(retval)
        finally:
            self.pending_returns = previous_pending
            self.cleanup_stack = original_cleanups
