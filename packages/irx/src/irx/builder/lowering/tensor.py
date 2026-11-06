# mypy: disable-error-code=no-redef

"""
title: Tensor lowering implementation for llvmliteir.
"""

from __future__ import annotations

from typing import Literal, cast

import astx

from llvmlite import ir
from plum import dispatch
from public import private

from irx.analysis.resolved_nodes import SemanticInfo
from irx.analysis.types import is_float_type, is_unsigned_type
from irx.buffer import BUFFER_VIEW_FIELD_INDICES
from irx.builder.diagnostics import (
    raise_lowering_error,
    raise_lowering_internal_error,
    require_semantic_metadata,
)
from irx.builder.lowering.contracts import TensorServices
from irx.builder.runtime import safe_pop
from irx.builder.services.representations import (
    resolved_type as resolved_ast_type,
)
from irx.builder.state import CleanupAction
from irx.builder.types import is_int_type
from irx.builtins.collections.array_primitives import (
    ARRAY_PRIMITIVE_TYPE_SPECS,
    ArrayPrimitiveTypeSpec,
)
from irx.builtins.collections.tensor import (
    TENSOR_ELEMENT_TYPE_EXTRA,
    TENSOR_FLAGS_EXTRA,
    TENSOR_LAYOUT_EXTRA,
    TensorLayout,
    tensor_element_count,
    tensor_primitive_type_name,
)
from irx.diagnostics import DiagnosticCodes
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class TensorLowering:
    """
    title: Tensor lowering implementation.
    attributes:
      services:
        type: TensorServices
    """

    services: TensorServices

    def __init__(self, services: TensorServices) -> None:
        """
        title: Bind explicit family-owned emission dependencies.
        parameters:
          services:
            type: TensorServices
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
            f"no tensor handler for {type(node).__name__}", node=node
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
                "llvm.tensor.TensorLiteral",
                "irx.tensor",
                "lowering",
                astx.TensorLiteral,
                self.visit,
                source="irx.builder.lowering.tensor.TensorLowering.visit",
            ),
            contribute_node(
                "llvm.tensor.TensorView",
                "irx.tensor",
                "lowering",
                astx.TensorView,
                self.visit,
                source="irx.builder.lowering.tensor.TensorLowering.visit",
            ),
            contribute_node(
                "llvm.tensor.TensorIndex",
                "irx.tensor",
                "lowering",
                astx.TensorIndex,
                self.visit,
                source="irx.builder.lowering.tensor.TensorLowering.visit",
            ),
            contribute_node(
                "llvm.tensor.TensorStore",
                "irx.tensor",
                "lowering",
                astx.TensorStore,
                self.visit,
                source="irx.builder.lowering.tensor.TensorLowering.visit",
            ),
            contribute_node(
                "llvm.tensor.TensorNDim",
                "irx.tensor",
                "lowering",
                astx.TensorNDim,
                self.visit,
                source="irx.builder.lowering.tensor.TensorLowering.visit",
            ),
            contribute_node(
                "llvm.tensor.TensorShape",
                "irx.tensor",
                "lowering",
                astx.TensorShape,
                self.visit,
                source="irx.builder.lowering.tensor.TensorLowering.visit",
            ),
            contribute_node(
                "llvm.tensor.TensorStride",
                "irx.tensor",
                "lowering",
                astx.TensorStride,
                self.visit,
                source="irx.builder.lowering.tensor.TensorLowering.visit",
            ),
            contribute_node(
                "llvm.tensor.TensorElementCount",
                "irx.tensor",
                "lowering",
                astx.TensorElementCount,
                self.visit,
                source="irx.builder.lowering.tensor.TensorLowering.visit",
            ),
            contribute_node(
                "llvm.tensor.TensorByteOffset",
                "irx.tensor",
                "lowering",
                astx.TensorByteOffset,
                self.visit,
                source="irx.builder.lowering.tensor.TensorLowering.visit",
            ),
            contribute_node(
                "llvm.tensor.TensorRetain",
                "irx.tensor",
                "lowering",
                astx.TensorRetain,
                self.visit,
                source="irx.builder.lowering.tensor.TensorLowering.visit",
            ),
            contribute_node(
                "llvm.tensor.TensorRelease",
                "irx.tensor",
                "lowering",
                astx.TensorRelease,
                self.visit,
                source="irx.builder.lowering.tensor.TensorLowering.visit",
            ),
        )

    def _static_tensor_layout(self, node: astx.AST) -> TensorLayout:
        """
        title: Return static Tensor layout metadata for lowering.
        parameters:
          node:
            type: astx.AST
        returns:
          type: TensorLayout
        """
        semantic = getattr(node, "semantic", None)
        extras = getattr(semantic, "extras", {})
        layout = extras.get(TENSOR_LAYOUT_EXTRA)
        if isinstance(layout, TensorLayout):
            return layout

        symbol = getattr(semantic, "resolved_symbol", None)
        declaration = getattr(symbol, "declaration", None)
        initializer = getattr(declaration, "value", None)
        initializer_semantic = getattr(initializer, "semantic", None)
        initializer_extras = getattr(initializer_semantic, "extras", {})
        layout = initializer_extras.get(TENSOR_LAYOUT_EXTRA)
        if isinstance(layout, TensorLayout):
            return layout
        raise_lowering_internal_error(
            "tensor lowering requires static layout metadata", node=node
        )

    def _static_tensor_element_type(self, node: astx.AST) -> astx.DataType:
        """
        title: Return static Tensor element type for lowering.
        parameters:
          node:
            type: astx.AST
        returns:
          type: astx.DataType
        """
        semantic = getattr(node, "semantic", None)
        extras = getattr(semantic, "extras", {})
        element_type = extras.get(TENSOR_ELEMENT_TYPE_EXTRA)
        if isinstance(element_type, astx.DataType):
            return element_type

        resolved_type = getattr(
            semantic,
            "resolved_type",
            getattr(node, "type_", None),
        )
        if (
            isinstance(resolved_type, astx.TensorType)
            and resolved_type.element_type is not None
        ):
            return resolved_type.element_type

        symbol = getattr(semantic, "resolved_symbol", None)
        declaration = getattr(symbol, "declaration", None)
        initializer = getattr(declaration, "value", None)
        initializer_semantic = getattr(initializer, "semantic", None)
        initializer_extras = getattr(initializer_semantic, "extras", {})
        element_type = initializer_extras.get(TENSOR_ELEMENT_TYPE_EXTRA)
        if isinstance(element_type, astx.DataType):
            return element_type
        raise_lowering_internal_error(
            "tensor lowering requires a known element type", node=node
        )

    def _static_tensor_flags(self, node: astx.AST) -> int:
        """
        title: Return static Tensor flags for lowering.
        parameters:
          node:
            type: astx.AST
        returns:
          type: int
        """
        semantic = getattr(node, "semantic", None)
        extras = getattr(semantic, "extras", {})
        flags = extras.get(TENSOR_FLAGS_EXTRA)
        if isinstance(flags, int):
            return flags

        symbol = getattr(semantic, "resolved_symbol", None)
        declaration = getattr(symbol, "declaration", None)
        initializer = getattr(declaration, "value", None)
        initializer_semantic = getattr(initializer, "semantic", None)
        initializer_extras = getattr(initializer_semantic, "extras", {})
        flags = initializer_extras.get(TENSOR_FLAGS_EXTRA)
        if isinstance(flags, int):
            return flags
        raise_lowering_internal_error(
            "tensor lowering requires static flags metadata", node=node
        )

    def _extract_view_field(
        self,
        view: ir.Value,
        field_name: str,
        *,
        name: str,
    ) -> ir.Value:
        """
        title: Extract one canonical buffer-view field from an Tensor value.
        parameters:
          view:
            type: ir.Value
          field_name:
            type: str
          name:
            type: str
        returns:
          type: ir.Value
        """
        return self.services.llvm.ir_builder.extract_value(
            view,
            BUFFER_VIEW_FIELD_INDICES[field_name],
            name=name,
        )

    def _tensor_value_from_parts(
        self,
        *,
        data: ir.Value,
        owner: ir.Value,
        dtype: ir.Value,
        layout: TensorLayout,
        flags: int,
        offset_value: ir.Value | None = None,
    ) -> ir.Value:
        """
        title: Assemble one lowered tensor value from storage and layout parts.
        parameters:
          data:
            type: ir.Value
          owner:
            type: ir.Value
          dtype:
            type: ir.Value
          layout:
            type: TensorLayout
          flags:
            type: int
          offset_value:
            type: ir.Value | None
        returns:
          type: ir.Value
        """
        fields: list[ir.Value] = [
            data,
            owner,
            dtype,
            ir.Constant(self.services.llvm.INT32_TYPE, layout.ndim),
            self.services.i64_array_pointer(
                layout.shape,
                purpose="shape",
                symbol_namespace="tensor",
            ),
            self.services.i64_array_pointer(
                layout.strides,
                purpose="strides",
                symbol_namespace="tensor",
            ),
            (
                ir.Constant(self.services.llvm.INT64_TYPE, layout.offset_bytes)
                if offset_value is None
                else offset_value
            ),
            ir.Constant(self.services.llvm.INT32_TYPE, flags),
        ]

        value: ir.Value = ir.Constant(
            self.services.llvm.BUFFER_VIEW_TYPE, None
        )
        for index, field in enumerate(fields):
            value = self.services.llvm.ir_builder.insert_value(
                value,
                field,
                index,
                name=f"irx_tensor_field_{index}",
            )
        return value

    def _require_tensor_value(
        self, node: astx.AST, *, track_temporary: bool = True
    ) -> ir.Value:
        """
        title: Lower one Tensor expression and require buffer-view storage.
        parameters:
          node:
            type: astx.AST
          track_temporary:
            type: bool
            description: >-
              False when forwarding a view or managing it explicitly.
        returns:
          type: ir.Value
        """
        self.services.visit_child(node)
        value = safe_pop(self.services.function_state.result_stack)
        if value is None or value.type != self.services.llvm.BUFFER_VIEW_TYPE:
            raise_lowering_internal_error(
                "tensor lowering requires a TensorType value", node=node
            )
        semantic = require_semantic_metadata(
            cast(SemanticInfo | None, getattr(node, "semantic", None)),
            node=node,
            metadata="semantic",
            context="tensor lifetime lowering",
        )
        if track_temporary and semantic.tensor_temporary_owner:
            owner = self._extract_view_field(
                value, "owner", name="tensor.temporary.owner"
            )
            release = self.services.require_runtime_symbol(
                "buffer", "irx_buffer_owner_release"
            )

            def release_temporary() -> None:
                """
                title: Release the fresh owner after its scalar consumer.
                """
                self.services.llvm.ir_builder.call(release, [owner])

            self.services.exit_state.cleanup_stack.append(
                CleanupAction(release_temporary, fallible=False)
            )
        return value

    @private
    def check_tensor_status(
        self,
        node: astx.AST,
        status: ir.Value,
        operation: str,
        feature: Literal["tensor", "buffer"] = "tensor",
    ) -> None:
        """
        title: Guard construction outputs using the owning runtime's error.
        parameters:
          node:
            type: astx.AST
          status:
            type: ir.Value
          operation:
            type: str
          feature:
            type: Literal[tensor, buffer]
        """
        symbol = (
            "irx_arrow_last_error"
            if feature == "tensor"
            else "irx_buffer_last_error"
        )
        message = self.services.llvm.ir_builder.call(
            self.services.require_runtime_symbol(feature, symbol), []
        )
        self.services.check_arrow_status(node, status, operation, message)

    def _tensor_primitive_spec(
        self,
        element_type: astx.DataType,
    ) -> ArrayPrimitiveTypeSpec:
        """
        title: Return one runtime primitive storage spec for Tensor lowering.
        parameters:
          element_type:
            type: astx.DataType
        returns:
          type: ArrayPrimitiveTypeSpec
        """
        primitive_name = tensor_primitive_type_name(element_type)
        if primitive_name is None:
            raise_lowering_error(
                "tensor lowering has unsupported element type",
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=element_type,
            )

        spec = ARRAY_PRIMITIVE_TYPE_SPECS.get(primitive_name)
        if spec is None or not spec.buffer_view_compatible:
            raise_lowering_internal_error(
                (
                    "tensor lowering requires a buffer-view-compatible "
                    "primitive element type"
                ),
                node=element_type,
            )
        return spec

    def _append_value_to_tensor_builder(
        self,
        *,
        builder_handle: ir.Value,
        value_node: astx.AST,
        element_type: astx.DataType,
    ) -> None:
        """
        title: Append one lowered scalar to the Arrow tensor builder.
        parameters:
          builder_handle:
            type: ir.Value
          value_node:
            type: astx.AST
          element_type:
            type: astx.DataType
        """
        self.services.visit_child(value_node)
        value = safe_pop(self.services.function_state.result_stack)
        if value is None:
            raise_lowering_internal_error(
                "tensor literal expected a scalar value", node=value_node
            )

        value = self.services.numeric.cast_scalar(
            value,
            source_type=resolved_ast_type(value_node),
            target_type=element_type,
        )

        if is_float_type(element_type):
            append = self.services.require_runtime_symbol(
                "tensor",
                "irx_arrow_tensor_builder_append_double",
            )
            if value.type != self.services.llvm.DOUBLE_TYPE:
                value = self.services.llvm.ir_builder.fpext(
                    value,
                    self.services.llvm.DOUBLE_TYPE,
                    name="irx_tensor_double_promote",
                )
            status = self.services.llvm.ir_builder.call(
                append, [builder_handle, value]
            )
            self.check_tensor_status(value_node, status, append.name)
            return

        if not is_int_type(value.type):
            raise_lowering_internal_error(
                "tensor builder requires integer or float values",
                node=value_node,
            )

        if is_unsigned_type(element_type):
            append = self.services.require_runtime_symbol(
                "tensor",
                "irx_arrow_tensor_builder_append_uint",
            )
            if value.type.width < self.services.llvm.INT64_TYPE.width:
                value = self.services.llvm.ir_builder.zext(
                    value,
                    self.services.llvm.INT64_TYPE,
                    name="irx_tensor_uint_promote",
                )
            elif value.type.width > self.services.llvm.INT64_TYPE.width:
                value = self.services.llvm.ir_builder.trunc(
                    value,
                    self.services.llvm.INT64_TYPE,
                    name="irx_tensor_uint_trunc",
                )
            status = self.services.llvm.ir_builder.call(
                append, [builder_handle, value]
            )
            self.check_tensor_status(value_node, status, append.name)
            return

        append = self.services.require_runtime_symbol(
            "tensor",
            "irx_arrow_tensor_builder_append_int",
        )
        if value.type.width < self.services.llvm.INT64_TYPE.width:
            value = self.services.llvm.ir_builder.sext(
                value,
                self.services.llvm.INT64_TYPE,
                name="irx_tensor_int_promote",
            )
        elif value.type.width > self.services.llvm.INT64_TYPE.width:
            value = self.services.llvm.ir_builder.trunc(
                value,
                self.services.llvm.INT64_TYPE,
                name="irx_tensor_int_trunc",
            )
        status = self.services.llvm.ir_builder.call(
            append, [builder_handle, value]
        )
        self.check_tensor_status(value_node, status, append.name)

    def _build_arrow_tensor_from_values(
        self,
        node: astx.AST,
        values: list[astx.AST],
        element_type: astx.DataType,
        layout: TensorLayout,
    ) -> ir.Value:
        """
        title: Build one Arrow tensor handle from scalar AST values.
        parameters:
          node:
            type: astx.AST
          values:
            type: list[astx.AST]
          element_type:
            type: astx.DataType
          layout:
            type: TensorLayout
        returns:
          type: ir.Value
        """
        spec = self._tensor_primitive_spec(element_type)
        builder_new = self.services.require_runtime_symbol(
            "tensor",
            "irx_arrow_tensor_builder_new",
        )
        finish_builder = self.services.require_runtime_symbol(
            "tensor",
            "irx_arrow_tensor_builder_finish",
        )

        builder_slot = self.services.create_entry_block_alloca(
            "irx_tensor_builder_slot",
            self.services.llvm.TENSOR_BUILDER_HANDLE_TYPE,
        )
        status = self.services.llvm.ir_builder.call(
            builder_new,
            [
                ir.Constant(self.services.llvm.INT32_TYPE, spec.type_id),
                ir.Constant(self.services.llvm.INT32_TYPE, layout.ndim),
                self.services.i64_array_pointer(
                    layout.shape,
                    purpose="builder_shape",
                    symbol_namespace="tensor",
                ),
                self.services.i64_array_pointer(
                    layout.strides,
                    purpose="builder_strides",
                    symbol_namespace="tensor",
                ),
                builder_slot,
            ],
        )
        self.check_tensor_status(node, status, builder_new.name)
        builder_handle = self.services.llvm.ir_builder.load(
            builder_slot,
            name="irx_tensor_builder",
        )
        cleanup = self.services.track_native_handle(
            node, "tensor", "irx_arrow_tensor_builder_release", builder_handle
        )

        for value in values:
            self._append_value_to_tensor_builder(
                builder_handle=builder_handle,
                value_node=value,
                element_type=element_type,
            )

        tensor_slot = self.services.create_entry_block_alloca(
            "irx_tensor_handle_slot", self.services.llvm.TENSOR_HANDLE_TYPE
        )
        status = self.services.llvm.ir_builder.call(
            finish_builder,
            [builder_handle, tensor_slot],
        )
        self.check_tensor_status(node, status, finish_builder.name)
        # A successful finish consumes the builder; failure retains it.
        self.services.exit_state.cleanup_stack.remove(cleanup)
        return self.services.llvm.ir_builder.load(
            tensor_slot,
            name="irx_tensor_handle",
        )

    def _wrap_arrow_tensor_handle_as_tensor(
        self,
        *,
        node: astx.AST,
        tensor_handle: ir.Value,
        layout: TensorLayout,
        flags: int,
    ) -> ir.Value:
        """
        title: Wrap one Arrow tensor handle as an owned Tensor value.
        parameters:
          node:
            type: astx.AST
          tensor_handle:
            type: ir.Value
          layout:
            type: TensorLayout
          flags:
            type: int
        returns:
          type: ir.Value
        """
        borrow_view = self.services.require_runtime_symbol(
            "tensor",
            "irx_arrow_tensor_borrow_buffer_view",
        )
        owner_new = self.services.require_runtime_symbol(
            "buffer",
            "irx_buffer_owner_external_new",
        )
        release_tensor = self.services.require_runtime_symbol(
            "tensor",
            "irx_arrow_tensor_release",
        )

        cleanup = self.services.track_native_handle(
            node, "tensor", "irx_arrow_tensor_release", tensor_handle
        )
        borrowed_slot = self.services.create_entry_block_alloca(
            "irx_tensor_borrowed_view", self.services.llvm.BUFFER_VIEW_TYPE
        )
        status = self.services.llvm.ir_builder.call(
            borrow_view,
            [tensor_handle, borrowed_slot],
        )
        self.check_tensor_status(node, status, borrow_view.name)
        borrowed_view = self.services.llvm.ir_builder.load(
            borrowed_slot,
            name="irx_tensor_borrowed_value",
        )

        owner_slot = self.services.create_entry_block_alloca(
            "irx_tensor_owner_slot",
            self.services.llvm.BUFFER_OWNER_HANDLE_TYPE,
        )
        release_fn = self.services.llvm.ir_builder.bitcast(
            release_tensor,
            self.services.llvm.OPAQUE_POINTER_TYPE,
            name="irx_tensor_release_fn",
        )
        status = self.services.llvm.ir_builder.call(
            owner_new,
            [tensor_handle, release_fn, owner_slot],
        )
        self.check_tensor_status(node, status, owner_new.name, "buffer")
        # The external owner now holds the tensor's single release obligation.
        self.services.exit_state.cleanup_stack.remove(cleanup)
        owner_handle = self.services.llvm.ir_builder.load(
            owner_slot,
            name="irx_tensor_owner",
        )

        borrowed_offset = self._extract_view_field(
            borrowed_view,
            "offset_bytes",
            name="irx_tensor_borrowed_offset",
        )
        layout_offset = ir.Constant(
            self.services.llvm.INT64_TYPE,
            layout.offset_bytes,
        )
        final_offset = self.services.llvm.ir_builder.add(
            borrowed_offset,
            layout_offset,
            name="irx_tensor_offset_bytes",
        )
        return self._tensor_value_from_parts(
            data=self._extract_view_field(
                borrowed_view,
                "data",
                name="irx_tensor_data",
            ),
            owner=owner_handle,
            dtype=self._extract_view_field(
                borrowed_view,
                "dtype",
                name="irx_tensor_dtype",
            ),
            layout=layout,
            flags=flags,
            offset_value=final_offset,
        )

    @dispatch
    def visit(self, node: astx.TensorLiteral) -> None:
        """
        title: Visit TensorLiteral nodes.
        parameters:
          node:
            type: astx.TensorLiteral
        """
        layout = self._static_tensor_layout(node)
        flags = self._static_tensor_flags(node)
        element_type = self._static_tensor_element_type(node)
        tensor_handle = self._build_arrow_tensor_from_values(
            node,
            node.values,
            element_type,
            layout,
        )
        self.services.function_state.result_stack.append(
            self._wrap_arrow_tensor_handle_as_tensor(
                node=node,
                tensor_handle=tensor_handle,
                layout=layout,
                flags=flags,
            )
        )

    @dispatch
    def visit(self, node: astx.TensorView) -> None:
        """
        title: Visit TensorView nodes.
        parameters:
          node:
            type: astx.TensorView
        """
        base_value = self._require_tensor_value(
            node.base, track_temporary=False
        )
        layout = self._static_tensor_layout(node)
        flags = self._static_tensor_flags(node)

        self.services.function_state.result_stack.append(
            self._tensor_value_from_parts(
                data=self._extract_view_field(
                    base_value,
                    "data",
                    name="irx_tensor_view_data",
                ),
                owner=self._extract_view_field(
                    base_value,
                    "owner",
                    name="irx_tensor_view_owner",
                ),
                dtype=self._extract_view_field(
                    base_value,
                    "dtype",
                    name="irx_tensor_view_dtype",
                ),
                layout=layout,
                flags=flags,
            )
        )

    @dispatch
    def visit(self, node: astx.TensorIndex) -> None:
        """
        title: Visit TensorIndex nodes.
        parameters:
          node:
            type: astx.TensorIndex
        """
        view = self._require_tensor_value(node.base)
        indices = self.services.lower_buffer_index_indices(node.indices)
        element_ptr = self.services.lower_buffer_element_pointer(
            view,
            indices,
            self._static_tensor_element_type(node.base),
            index_nodes=node.indices,
            node=node,
        )
        result = self.services.llvm.ir_builder.load(
            element_ptr,
            name="irx_tensor_index_load",
            align=1,
        )
        self.services.function_state.result_stack.append(result)

    @dispatch
    def visit(self, node: astx.TensorStore) -> None:
        """
        title: Visit TensorStore nodes.
        parameters:
          node:
            type: astx.TensorStore
        """
        view = self._require_tensor_value(node.base)
        indices = self.services.lower_buffer_index_indices(node.indices)
        element_type = self._static_tensor_element_type(node.base)
        element_ptr = self.services.lower_buffer_element_pointer(
            view,
            indices,
            element_type,
            index_nodes=node.indices,
            node=node,
        )

        self.services.visit_child(node.value)
        value = safe_pop(self.services.function_state.result_stack)
        if value is None:
            raise_lowering_internal_error(
                "tensor indexed store requires a value", node=node
            )
        value = self.services.numeric.cast_scalar(
            value,
            source_type=resolved_ast_type(node.value),
            target_type=element_type,
        )
        self.services.llvm.ir_builder.store(value, element_ptr, align=1)
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.INT32_TYPE, 0)
        )

    @dispatch
    def visit(self, node: astx.TensorNDim) -> None:
        """
        title: Visit TensorNDim nodes.
        parameters:
          node:
            type: astx.TensorNDim
        """
        view = self._require_tensor_value(node.base)
        self.services.function_state.result_stack.append(
            self._extract_view_field(
                view,
                "ndim",
                name="irx_tensor_ndim",
            )
        )

    @dispatch
    def visit(self, node: astx.TensorShape) -> None:
        """
        title: Visit TensorShape nodes.
        parameters:
          node:
            type: astx.TensorShape
        """
        view = self._require_tensor_value(node.base)
        shape_ptr = self._extract_view_field(
            view,
            "shape",
            name="irx_tensor_shape_ptr",
        )
        axis_ptr = self.services.llvm.ir_builder.gep(
            shape_ptr,
            [ir.Constant(self.services.llvm.INT64_TYPE, node.axis)],
            name="irx_tensor_shape_axis_ptr",
        )
        self.services.function_state.result_stack.append(
            self.services.llvm.ir_builder.load(
                axis_ptr,
                name="irx_tensor_shape_axis",
            )
        )

    @dispatch
    def visit(self, node: astx.TensorStride) -> None:
        """
        title: Visit TensorStride nodes.
        parameters:
          node:
            type: astx.TensorStride
        """
        view = self._require_tensor_value(node.base)
        stride_ptr = self._extract_view_field(
            view,
            "strides",
            name="irx_tensor_stride_ptr",
        )
        axis_ptr = self.services.llvm.ir_builder.gep(
            stride_ptr,
            [ir.Constant(self.services.llvm.INT64_TYPE, node.axis)],
            name="irx_tensor_stride_axis_ptr",
        )
        self.services.function_state.result_stack.append(
            self.services.llvm.ir_builder.load(
                axis_ptr,
                name="irx_tensor_stride_axis",
            )
        )

    @dispatch
    def visit(self, node: astx.TensorElementCount) -> None:
        """
        title: Visit TensorElementCount nodes.
        parameters:
          node:
            type: astx.TensorElementCount
        """
        layout = self._static_tensor_layout(node.base)
        self.services.function_state.result_stack.append(
            ir.Constant(
                self.services.llvm.INT64_TYPE,
                tensor_element_count(layout),
            )
        )

    @dispatch
    def visit(self, node: astx.TensorByteOffset) -> None:
        """
        title: Visit TensorByteOffset nodes.
        parameters:
          node:
            type: astx.TensorByteOffset
        """
        view = self._require_tensor_value(node.base)
        indices = self.services.lower_buffer_index_indices(node.indices)
        offset = self.services.lower_buffer_byte_offset(
            view,
            indices,
            index_nodes=node.indices,
            node=node,
        )
        self.services.function_state.result_stack.append(offset)

    @dispatch
    def visit(self, node: astx.TensorRetain) -> None:
        """
        title: Visit TensorRetain nodes.
        parameters:
          node:
            type: astx.TensorRetain
        """
        retain = self.services.require_runtime_symbol(
            "buffer",
            "irx_buffer_view_retain",
        )
        value = self._require_tensor_value(node.base, track_temporary=False)
        slot = self.services.create_entry_block_alloca(
            "irx_tensor_retain_view", self.services.llvm.BUFFER_VIEW_TYPE
        )
        self.services.llvm.ir_builder.store(value, slot)
        self.services.function_state.result_stack.append(
            self.services.llvm.ir_builder.call(
                retain,
                [slot],
                name="irx_tensor_retain_status",
            )
        )

    @dispatch
    def visit(self, node: astx.TensorRelease) -> None:
        """
        title: Visit TensorRelease nodes.
        parameters:
          node:
            type: astx.TensorRelease
        """
        release = self.services.require_runtime_symbol(
            "buffer",
            "irx_buffer_view_release",
        )
        value = self._require_tensor_value(node.base, track_temporary=False)
        slot = self.services.create_entry_block_alloca(
            "irx_tensor_release_view", self.services.llvm.BUFFER_VIEW_TYPE
        )
        self.services.llvm.ir_builder.store(value, slot)
        self.services.function_state.result_stack.append(
            self.services.llvm.ir_builder.call(
                release,
                [slot],
                name="irx_tensor_release_status",
            )
        )
