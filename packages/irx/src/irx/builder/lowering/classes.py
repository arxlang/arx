"""
title: Lower resolved class lifetimes without re-resolving ownership or names.
"""

from typing import Any, cast

import astx

from llvmlite import ir
from public import private

from irx.analysis.arrow_conversion import ARROW_RESOURCES
from irx.analysis.ownership import resource_ownership
from irx.analysis.resolved_nodes import (
    ClassHeaderFieldKind,
    OwnershipKind,
    OwnershipTransferKind,
    ResolvedClassConstruction,
    ResourceKind,
    SemanticClass,
    SemanticInfo,
)
from irx.builder.diagnostics import (
    require_lowered_value,
    require_semantic_metadata,
)
from irx.builder.lowering.file import FileVisitorMixin
from irx.builder.runtime import safe_pop
from irx.builder.state import CleanupAction, ExceptionTarget
from irx.typecheck import typechecked


@private
@typechecked
class ClassVisitorMixin(FileVisitorMixin):
    """
    title: Checked creation, reference ownership, and concrete drops.
    """

    def class_raw(self, value: ir.Value) -> ir.Value:
        """
        title: Convert only the public payload pointer to the native ABI.
        parameters:
          value:
            type: ir.Value
        returns:
          type: ir.Value
        """
        pointer = self._llvm.INT8_TYPE.as_pointer()
        return (
            value
            if value.type == pointer
            else self._llvm.ir_builder.bitcast(value, pointer)
        )

    def class_field_function(self, class_: SemanticClass) -> ir.Function:
        """
        title: Locate base-view fields through the concrete descriptor.
        parameters:
          class_:
            type: SemanticClass
        returns:
          type: ir.Function
        """
        layout = require_semantic_metadata(
            class_.layout,
            node=class_.declaration,
            metadata="layout",
            context="class field descriptor",
        )
        name = layout.descriptor_global_name
        existing = self._llvm.module.globals.get(name)
        if isinstance(existing, ir.Function):
            return existing
        pointer = self._llvm.INT8_TYPE.as_pointer()
        integer = self._llvm.INT32_TYPE
        function = ir.Function(
            self._llvm.module,
            ir.FunctionType(pointer, [pointer, integer]),
            name=name,
        )
        function.linkage = "internal"
        previous = self._llvm.ir_builder
        self._llvm.ir_builder = ir.IRBuilder(
            function.append_basic_block("entry")
        )
        try:
            type_ = astx.ClassType(
                class_.name,
                module_key=class_.module_key,
                qualified_name=class_.qualified_name,
            )
            llvm_type = self._llvm_type_for_ast_type(type_)
            assert llvm_type is not None
            value = self._llvm.ir_builder.bitcast(function.args[0], llvm_type)
            missing = function.append_basic_block("missing")
            switch = self._llvm.ir_builder.switch(function.args[1], missing)
            for field in layout.instance_fields:
                block = function.append_basic_block(
                    f"field.{field.access_index}"
                )
                switch.add_case(
                    ir.Constant(integer, field.access_index), block
                )
                self._llvm.ir_builder.position_at_end(block)
                address = self._llvm.ir_builder.gep(
                    value,
                    [
                        ir.Constant(integer, 0),
                        ir.Constant(integer, field.storage_index),
                    ],
                    inbounds=True,
                    name=f"{field.member.name}_addr",
                )
                self._llvm.ir_builder.ret(self.class_raw(address))
            self._llvm.ir_builder.position_at_end(missing)
            self._llvm.ir_builder.ret(ir.Constant(pointer, None))
        finally:
            self._llvm.ir_builder = previous
        return function

    def class_field_value(self, node: astx.AST, value: ir.Value) -> ir.Value:
        """
        title: Snapshot string fields before later expression effects.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
        returns:
          type: ir.Value
        """
        self.class_pin(node, value)
        ownership = resource_ownership(node)
        if (
            ownership is not None
            and ownership.resource_kind is ResourceKind.STRING
            and ownership.kind is OwnershipKind.OWNED
        ):
            value = self._copy_string_to_heap(node, value)
            self._register_owned_string_temporary(node, value)
        return value

    def class_operation(
        self, node: astx.AST, operation: str, value: ir.Value
    ) -> None:
        """
        title: Emit a checked operation on a semantically resolved reference.
        parameters:
          node:
            type: astx.AST
          operation:
            type: str
          value:
            type: ir.Value
        """
        ownership = resource_ownership(node)
        if (
            ownership is not None
            and ownership.resource_kind in ARROW_RESOURCES
        ):
            prefix = (
                "table"
                if ownership.resource_kind is ResourceKind.DATAFRAME
                else "chunked_array"
            )
            function = self.require_runtime_symbol(
                "dataframe", f"irx_arrow_{prefix}_{operation}"
            )
            status = self._llvm.ir_builder.call(function, [value])
            if operation == "retain":
                error_function = self.require_runtime_symbol(
                    "dataframe", "irx_arrow_last_error"
                )
                error = self._llvm.ir_builder.call(error_function, [])
                self.file_check(
                    node, status, error, code="ARX-RUNTIME-ARROW-001"
                )
            return
        error = self.file_error_buffer()
        function = self.require_runtime_symbol(
            "class", f"irx_class_{operation}"
        )
        args = [self.class_raw(value), error]
        if operation == "release":
            args.insert(0, cast(Any, self).context_value())
        status = self._llvm.ir_builder.call(function, args)
        self.file_check(node, status, error, code="ARX-RUNTIME-CLASS-001")

    def class_cleanup(
        self,
        node: astx.AST,
        value: ir.Value,
        owner: str | None = None,
        *,
        storage: bool = False,
    ) -> None:
        """
        title: Release one reference or the current generation of a binding.
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

        ownership = resource_ownership(node)
        counted = (
            storage
            and ownership is not None
            and ownership.resource_kind in ARROW_RESOURCES
        )
        if counted:
            assert owner is not None
            count = self.create_entry_block_alloca(
                "arrow.references", ir.IntType(64)
            )
            self.named_values[f"arrow.references:{owner}"] = count
            self._llvm.ir_builder.store(ir.Constant(ir.IntType(64), 1), count)

        def release() -> None:
            """
            title: >-
              Release only the references owned by this binding or temporary.
            """
            current = self._llvm.ir_builder.load(value) if storage else value
            if counted:
                assert owner is not None
                self.arrow_release_binding(node, current, owner)
            else:
                self.class_operation(node, "release", current)

        self.cleanup_stack.append(
            CleanupAction(
                release,
                owner_symbol_id=owner,
                fallible=ownership is None
                or ownership.resource_kind not in ARROW_RESOURCES,
            )
        )

    def class_pin(self, node: astx.AST, value: ir.Value) -> None:
        """
        title: Pin an evaluated class through the full expression.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
        """
        info = getattr(node, "semantic", None)
        ownership = resource_ownership(node)
        if (
            ownership is None
            or ownership.resource_kind
            not in {ResourceKind.CLASS, *ARROW_RESOURCES}
            or (isinstance(info, SemanticInfo) and info.lifecycle_self)
        ):
            return
        self.class_operation(node, "retain", value)
        self.class_cleanup(node, value)

    def class_acquire(self, node: astx.AST, value: ir.Value) -> ir.Value:
        """
        title: Implement the analyzed retain-versus-move decision of a store.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
        returns:
          type: ir.Value
        """
        info = getattr(node, "semantic", None)
        store = (
            info.resolved_resource_store
            if isinstance(info, SemanticInfo)
            else None
        )
        ownership = require_semantic_metadata(
            store or resource_ownership(node),
            node=node,
            metadata="resource_ownership",
            context="class acquisition",
        )
        if ownership.transfer_kind is OwnershipTransferKind.COPY:
            self.class_operation(node, "retain", value)
        return value

    def class_drop_function(self, class_: SemanticClass) -> ir.Function:
        """
        title: Generate a concrete drop callback from resolved phases.
        parameters:
          class_:
            type: SemanticClass
        returns:
          type: ir.Function
        """
        initialization = require_semantic_metadata(
            class_.initialization,
            node=class_.declaration,
            metadata="initialization",
            context="class drop",
        )
        name = f"irx.drop.{class_.qualified_name}"
        existing = self._llvm.module.globals.get(name)
        if isinstance(existing, ir.Function):
            return existing
        pointer = self._llvm.INT8_TYPE.as_pointer()
        integer = self._llvm.INT32_TYPE
        function = ir.Function(
            self._llvm.module,
            ir.FunctionType(integer, [pointer, pointer, pointer]),
            name=name,
        )
        function.linkage = "internal"
        previous = self._llvm.ir_builder
        self._llvm.ir_builder = ir.IRBuilder(
            function.append_basic_block("entry")
        )
        previous_context = self.exception_context
        previous_targets = self.exception_targets
        previous_cleanups = self.cleanup_stack
        previous_returns = self.pending_returns
        self.pending_returns = []
        self.exception_context = function.args[0]
        self.exception_targets = []
        self.cleanup_stack = []
        try:
            context, value, error = function.args
            type_ = astx.ClassType(
                class_.name,
                module_key=class_.module_key,
                qualified_name=class_.qualified_name,
            )
            llvm_type = self._llvm_type_for_ast_type(type_)
            assert llvm_type is not None
            instance = self._llvm.ir_builder.bitcast(value, llvm_type)
            first = self._llvm.ir_builder.alloca(integer, name="first_status")
            self._llvm.ir_builder.store(ir.Constant(integer, 0), first)
            local_error = self._llvm.ir_builder.alloca(
                ir.ArrayType(ir.IntType(8), 256)
            )
            zero = ir.Constant(integer, 0)
            details = self._llvm.ir_builder.gep(local_error, [zero, zero])
            self._llvm.ir_builder.store(ir.Constant(ir.IntType(8), 0), details)
            completed_fn = self.require_runtime_symbol(
                "class", "irx_class_completed"
            )
            completed = self._llvm.ir_builder.call(completed_fn, [value])
            record = self.require_runtime_symbol("class", "irx_class_record")
            for index in reversed(range(len(initialization.phases))):
                phase = initialization.phases[index]
                if phase.destructor is not None:
                    ready = self._llvm.ir_builder.icmp_signed(
                        ">", completed, ir.Constant(integer, index)
                    )
                    with self._llvm.ir_builder.if_then(ready):
                        hook = self._declare_semantic_function(
                            phase.destructor
                        )
                        receiver = self._llvm.ir_builder.bitcast(
                            instance, hook.args[1].type
                        )
                        token = cast(Any, self).exception_call(
                            "cleanup_enter", [context]
                        )
                        status = self._llvm.ir_builder.call(
                            hook, [context, receiver]
                        )
                        cast(Any, self).exception_call(
                            "cleanup_leave", [context, token]
                        )
                        self._llvm.ir_builder.call(
                            record, [status, details, first, error]
                        )
                for item in reversed(phase.fields):
                    kind = item.field.resource_kind
                    canonical = cast(
                        SemanticInfo, getattr(class_.declaration, "semantic")
                    ).resolved_class
                    assert canonical is not None
                    exception = canonical.exception_type
                    if (
                        exception is not None
                        and item.field == exception.diagnostic_field
                    ):
                        address = self._llvm.ir_builder.gep(
                            instance,
                            [
                                zero,
                                ir.Constant(integer, item.field.storage_index),
                            ],
                        )
                        cast(Any, self).exception_call(
                            "info_release",
                            [self._llvm.ir_builder.load(address)],
                        )
                        self._llvm.ir_builder.store(
                            ir.Constant(pointer, None), address
                        )
                        continue
                    if kind is None:
                        continue
                    address = self._llvm.ir_builder.gep(
                        instance,
                        [zero, ir.Constant(integer, item.field.storage_index)],
                    )
                    stored = self._llvm.ir_builder.load(address)
                    raw = self.class_raw(stored)
                    if kind is ResourceKind.STRING:
                        self._llvm.ir_builder.call(
                            self.require_runtime_symbol("libc", "free"), [raw]
                        )
                    else:
                        feature = (
                            "file" if kind is ResourceKind.FILE else "class"
                        )
                        release = self.require_runtime_symbol(
                            feature, f"irx_{feature}_release"
                        )
                        operands = [raw, details]
                        if feature == "class":
                            operands.insert(0, context)
                        token = cast(Any, self).exception_call(
                            "cleanup_enter", [context]
                        )
                        status = self._llvm.ir_builder.call(release, operands)
                        self._llvm.ir_builder.call(
                            record, [status, details, first, error]
                        )
                        done = function.append_basic_block("drop.field.done")
                        self.exception_targets = [ExceptionTarget(done, 0)]
                        self.file_check(
                            class_.declaration,
                            status,
                            details,
                            code="ARX-RUNTIME-FILE-001"
                            if feature == "file"
                            else "ARX-RUNTIME-CLASS-001",
                        )
                        self._llvm.ir_builder.branch(done)
                        self._llvm.ir_builder.position_at_end(done)
                        self.exception_targets = []
                        cast(Any, self).exception_call(
                            "cleanup_leave", [context, token]
                        )
                    self._llvm.ir_builder.store(
                        ir.Constant(stored.type, None), address
                    )
            self._llvm.ir_builder.ret(self._llvm.ir_builder.load(first))
        finally:
            self._llvm.ir_builder = previous
            self.exception_context = previous_context
            self.exception_targets = previous_targets
            self.cleanup_stack = previous_cleanups
            self.pending_returns = previous_returns
        return function

    def lower_class_construct(
        self, node: astx.AST, resolution: ResolvedClassConstruction
    ) -> None:
        """
        title: Construct an owner with ordered arguments and phase progress.
        parameters:
          node:
            type: astx.AST
          resolution:
            type: ResolvedClassConstruction
        """
        from irx.builder.lowering.literals import (  # noqa: PLC0415
            LiteralVisitorMixin,
        )

        literal = cast(LiteralVisitorMixin, self)
        class_ = resolution.class_
        layout = require_semantic_metadata(
            class_.layout, node=node, metadata="layout", context="construction"
        )
        llvm_type = self._llvm_type_for_ast_type(self._resolved_ast_type(node))
        assert isinstance(llvm_type, ir.PointerType)
        values: list[ir.Value] = []
        for expression in resolution.evaluations:
            self.visit_child(expression)
            value = require_lowered_value(
                safe_pop(self.result_stack),
                node=expression,
                context="constructor argument",
            )
            self.class_pin(expression, value)
            values.append(value)
        pointer = self._llvm.INT8_TYPE.as_pointer()
        output = self.create_entry_block_alloca("class_result", pointer)
        error = self.file_error_buffer()
        size_ptr = self._llvm.ir_builder.gep(
            ir.Constant(llvm_type, None), [ir.Constant(ir.IntType(32), 1)]
        )
        size = self._llvm.ir_builder.ptrtoint(size_ptr, self._llvm.SIZE_T_TYPE)
        create = self.require_runtime_symbol("class", "irx_class_create")
        drop = self.class_drop_function(class_)
        status = self._llvm.ir_builder.call(
            create, [size, drop, output, error]
        )
        self.file_check(
            node,
            status,
            error,
            code="ARX-RUNTIME-CLASS-001",
            cleanup_temporaries=True,
        )
        raw = self._llvm.ir_builder.load(output)
        instance = self._llvm.ir_builder.bitcast(raw, llvm_type)
        zero = ir.Constant(ir.IntType(32), 0)
        for header in layout.header_fields:
            if header.kind is ClassHeaderFieldKind.LIFETIME:
                continue  # Native create installs the opaque token.
            address = self._llvm.ir_builder.gep(
                instance,
                [zero, ir.Constant(ir.IntType(32), header.storage_index)],
            )
            initial: ir.Value = ir.Constant(pointer, None)
            if header.kind is ClassHeaderFieldKind.TYPE_DESCRIPTOR:
                initial = self._llvm.ir_builder.bitcast(
                    self.class_field_function(class_), pointer
                )
            if (
                header.kind is ClassHeaderFieldKind.DISPATCH_TABLE
                and layout.dispatch_table_size
            ):
                dispatch = self._llvm.module.globals[
                    layout.dispatch_global_name
                ]
                initial = self._llvm.ir_builder.bitcast(dispatch, pointer)
            self._llvm.ir_builder.store(initial, address)
        previous_construction = self.class_construction_stack
        self.class_construction_stack = [*previous_construction, raw]
        rollback = CleanupAction(
            lambda: self.class_operation(node, "release", instance)
        )
        self.cleanup_stack.append(rollback)
        try:
            for phase_index, phase in enumerate(
                resolution.initialization.phases
            ):
                for item in phase.fields:
                    field = item.field
                    assert field.member.type_ is not None
                    native_file = resolution.native_file
                    native_exception = resolution.native_exception
                    if (
                        native_exception is not None
                        and field
                        == native_exception.exception_type.diagnostic_field
                    ):
                        value = ir.Constant(pointer, None)
                    elif (
                        native_exception is not None
                        and field
                        == native_exception.exception_type.message_field
                    ):
                        value = (
                            values[native_exception.message_index]
                            if native_exception.message_index is not None
                            else cast(Any, self).exception_string("")
                        )
                    elif (
                        native_file is not None and field == native_file.field
                    ):
                        value = self.create_native_file(
                            node,
                            native_file.operands,
                            values,
                            cleanup_temporaries=True,
                        )
                    elif item.value is None:
                        value = literal._default_runtime_initializer(
                            field.member.type_, name_hint=field.member.name
                        )
                    else:
                        info = getattr(item.value, "semantic", None)
                        receiver = (
                            info.initializer_receiver
                            if isinstance(info, SemanticInfo)
                            else None
                        )
                        previous_receiver = None
                        if receiver is not None:
                            previous_receiver = self.named_values.get(
                                receiver.symbol_id
                            )
                            receiver_type = self._llvm_type_for_ast_type(
                                receiver.type_
                            )
                            assert receiver_type is not None
                            receiver_slot = self.create_entry_block_alloca(
                                "initializer_self", receiver_type
                            )
                            self._llvm.ir_builder.store(
                                self._llvm.ir_builder.bitcast(
                                    instance, receiver_type
                                ),
                                receiver_slot,
                            )
                            self.named_values[receiver.symbol_id] = (
                                receiver_slot
                            )
                        self.visit_child(item.value)
                        if receiver is not None:
                            if previous_receiver is None:
                                self.named_values.pop(receiver.symbol_id, None)
                            else:
                                self.named_values[receiver.symbol_id] = (
                                    previous_receiver
                                )
                        value = require_lowered_value(
                            safe_pop(self.result_stack),
                            node=item.value,
                            context="instance initializer",
                        )
                        value = self._cast_ast_value(
                            value,
                            source_type=self._resolved_ast_type(item.value),
                            target_type=field.member.type_,
                        )
                    ownership = resource_ownership(item.value)
                    if field.resource_kind is ResourceKind.STRING:
                        if (
                            ownership is None
                            or ownership.transfer_kind
                            is not OwnershipTransferKind.MOVE
                        ):
                            value = self._copy_string_to_heap(node, value)
                    elif field.resource_kind is ResourceKind.CLASS:
                        if (
                            ownership is None
                            or ownership.transfer_kind
                            is not OwnershipTransferKind.MOVE
                        ):
                            self.class_operation(node, "retain", value)
                    address = self._llvm.ir_builder.gep(
                        instance,
                        [
                            zero,
                            ir.Constant(ir.IntType(32), field.storage_index),
                        ],
                    )
                    self._llvm.ir_builder.store(value, address)
                if phase.initializer is not None:
                    function = self._declare_semantic_function(
                        phase.initializer
                    )
                    arguments = [
                        self._llvm.ir_builder.bitcast(
                            instance,
                            function.args[
                                int(phase.initializer.signature.exception_abi)
                            ].type,
                        )
                    ]
                    if (
                        phase_index
                        == len(resolution.initialization.phases) - 1
                    ):
                        for index, type_ in zip(
                            resolution.argument_indices,
                            resolution.argument_types,
                        ):
                            arguments.append(
                                self._cast_ast_value(
                                    values[index],
                                    source_type=self._resolved_ast_type(
                                        resolution.evaluations[index]
                                    ),
                                    target_type=type_,
                                )
                            )
                    else:
                        for (
                            parameter
                        ) in phase.initializer.prototype.args.nodes:
                            self.visit_child(parameter.default)
                            arguments.append(
                                self._cast_ast_value(
                                    require_lowered_value(
                                        safe_pop(self.result_stack),
                                        node=parameter,
                                        context="base constructor default",
                                    ),
                                    source_type=self._resolved_ast_type(
                                        parameter.default
                                    ),
                                    target_type=parameter.type_,
                                )
                            )
                    cast(Any, self).emit_resolved_call(
                        node, function, phase.initializer.signature, arguments
                    )
                complete = self.require_runtime_symbol(
                    "class", "irx_class_complete"
                )
                self._llvm.ir_builder.call(complete, [raw])
            if resolution.native_exception is not None:
                cast(Any, self).initialize_exception_record(
                    node, instance, resolution.native_exception.exception_type
                )
        finally:
            self.class_construction_stack = previous_construction
            self.cleanup_stack.remove(rollback)
        ownership = require_semantic_metadata(
            resource_ownership(node),
            node=node,
            metadata="resource_ownership",
            context="class result",
        )
        if ownership.transfer_kind is not OwnershipTransferKind.MOVE:
            self.class_cleanup(node, instance)
        self.result_stack.append(instance)

    def arrow_temporary(self, node: astx.AST, value: ir.Value) -> None:
        """
        title: >-
          Register a temporary Arrow reference unless moved into a binding.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
        """
        ownership = require_semantic_metadata(
            resource_ownership(node),
            node=node,
            metadata="resource_ownership",
            context="Arrow temporary",
        )
        if ownership.transfer_kind is not OwnershipTransferKind.MOVE:
            self.class_cleanup(node, value)

    def arrow_reference_count(self, owner: str) -> ir.Value:
        """
        title: >-
          Fetch a resolved binding's reference counter, not its object
          refcount.
        parameters:
          owner:
            type: str
        returns:
          type: ir.Value
        """
        return self.named_values[f"arrow.references:{owner}"]

    def arrow_release_binding(
        self, node: astx.AST, value: ir.Value, owner: str
    ) -> None:
        """
        title: >-
          Drop all references held by a binding, including explicit retains.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
          owner:
            type: str
        """
        builder = self._llvm.ir_builder
        count = self.arrow_reference_count(owner)
        function = builder.function
        test = function.append_basic_block("arrow.drop.test")
        body = function.append_basic_block("arrow.drop.body")
        done = function.append_basic_block("arrow.drop.done")
        builder.branch(test)
        builder.position_at_end(test)
        remaining = builder.load(count)
        zero = ir.Constant(ir.IntType(64), 0)
        builder.cbranch(
            builder.icmp_unsigned(">", remaining, zero), body, done
        )
        builder.position_at_end(body)
        self.class_operation(node, "release", value)
        builder.store(
            builder.sub(remaining, ir.Constant(ir.IntType(64), 1)), count
        )
        builder.branch(test)
        builder.position_at_end(done)

    def arrow_explicit_lifetime(
        self, node: astx.AST, value: ir.Value, *, retain: bool
    ) -> None:
        """
        title: >-
          Reconcile explicit ASTx lifetime operations with scoped ownership.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
          retain:
            type: bool
        """
        if not isinstance(node, astx.Identifier):
            if retain:
                self.class_cleanup(node, value)
            return
        ownership = require_semantic_metadata(
            resource_ownership(node),
            node=node,
            metadata="resource_ownership",
            context="explicit Arrow lifetime",
        )
        owner = require_semantic_metadata(
            ownership.source_symbol_id,
            node=node,
            metadata="source_symbol_id",
            context="explicit Arrow lifetime",
        )
        count = self.arrow_reference_count(owner)
        builder = self._llvm.ir_builder
        current = builder.load(count)
        one = ir.Constant(ir.IntType(64), 1)
        if retain:
            builder.store(builder.add(current, one), count)
            return
        zero = ir.Constant(ir.IntType(64), 0)
        remaining = builder.select(
            builder.icmp_unsigned(">", current, zero),
            builder.sub(current, one),
            zero,
        )
        builder.store(remaining, count)
        address = self._lvalue_address(node)
        builder.store(
            builder.select(
                builder.icmp_unsigned("==", remaining, zero),
                ir.Constant(value.type, None),
                value,
            ),
            address,
        )
