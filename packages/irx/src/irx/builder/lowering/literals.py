# mypy: disable-error-code=no-redef

"""
title: Literal lowering implementations for llvmliteir.
"""

from __future__ import annotations

from typing import cast

import astx

from llvmlite import ir
from plum import dispatch
from public import private

from irx.analysis.extensions.literals import (
    DICTIONARY_LOOKUP,
    LITERAL_STORAGE,
)
from irx.analysis.resolved_nodes import (
    ResolvedClassConstruction,
    SemanticInfo,
)
from irx.builder.diagnostics import (
    raise_lowering_internal_error,
    require_semantic_metadata,
)
from irx.builder.lowering.contracts import LiteralServices
from irx.builder.services.representations import (
    resolved_type as resolved_ast_type,
)
from irx.builder.services.representations import (
    semantic_info,
)
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class LiteralLowering:
    """
    title: Lower literal values to LLVM.
    attributes:
      services:
        type: LiteralServices
    """

    services: LiteralServices

    def __init__(self, services: LiteralServices) -> None:
        """
        title: Bind explicit family-owned emission dependencies.
        parameters:
          services:
            type: LiteralServices
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
            f"no literals handler for {type(node).__name__}", node=node
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
                "llvm.literals.ClassConstruct",
                "irx.literals",
                "lowering",
                astx.ClassConstruct,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralInteger",
                "irx.literals",
                "lowering",
                astx.LiteralInteger,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralFloat",
                "irx.literals",
                "lowering",
                astx.LiteralFloat,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralInt32",
                "irx.literals",
                "lowering",
                astx.LiteralInt32,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralFloat32",
                "irx.literals",
                "lowering",
                astx.LiteralFloat32,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralFloat64",
                "irx.literals",
                "lowering",
                astx.LiteralFloat64,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralFloat16",
                "irx.literals",
                "lowering",
                astx.LiteralFloat16,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralNone",
                "irx.literals",
                "lowering",
                astx.LiteralNone,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralBoolean",
                "irx.literals",
                "lowering",
                astx.LiteralBoolean,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralInt64",
                "irx.literals",
                "lowering",
                astx.LiteralInt64,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralInt8",
                "irx.literals",
                "lowering",
                astx.LiteralInt8,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralUInt8",
                "irx.literals",
                "lowering",
                astx.LiteralUInt8,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralUInt16",
                "irx.literals",
                "lowering",
                astx.LiteralUInt16,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralUInt32",
                "irx.literals",
                "lowering",
                astx.LiteralUInt32,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralUInt64",
                "irx.literals",
                "lowering",
                astx.LiteralUInt64,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralUInt128",
                "irx.literals",
                "lowering",
                astx.LiteralUInt128,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralUTF8Char",
                "irx.literals",
                "lowering",
                astx.LiteralUTF8Char,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralUTF8String",
                "irx.literals",
                "lowering",
                astx.LiteralUTF8String,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralString",
                "irx.literals",
                "lowering",
                astx.LiteralString,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralList",
                "irx.literals",
                "lowering",
                astx.LiteralList,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralSet",
                "irx.literals",
                "lowering",
                astx.LiteralSet,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralTuple",
                "irx.literals",
                "lowering",
                astx.LiteralTuple,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralDict",
                "irx.literals",
                "lowering",
                astx.LiteralDict,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.SubscriptExpr",
                "irx.literals",
                "lowering",
                astx.SubscriptExpr,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
            contribute_node(
                "llvm.literals.LiteralInt16",
                "irx.literals",
                "lowering",
                astx.LiteralInt16,
                self.visit,
                source="irx.builder.lowering.literals.LiteralLowering.visit",
            ),
        )

    def _semantic_class_construction(
        self,
        node: astx.ClassConstruct,
    ) -> ResolvedClassConstruction:
        """
        title: Return the resolved semantic class construction metadata.
        parameters:
          node:
            type: astx.ClassConstruct
        returns:
          type: ResolvedClassConstruction
        """
        semantic = getattr(node, "semantic", None)
        resolution = getattr(semantic, "resolved_class_construction", None)
        return require_semantic_metadata(
            cast(ResolvedClassConstruction | None, resolution),
            node=node,
            metadata="resolved_class_construction",
            context="class construction lowering",
        )

    def _empty_string_pointer(self, name_hint: str) -> ir.Value:
        """
        title: Return one canonical empty-string pointer.
        parameters:
          name_hint:
            type: str
        returns:
          type: ir.Value
        """
        empty_str_type = ir.ArrayType(self.services.llvm.INT8_TYPE, 1)
        global_name = f"class_init_empty_str_{name_hint}"
        global_value = self.services.llvm.module.globals.get(global_name)
        if global_value is None:
            global_value = ir.GlobalVariable(
                self.services.llvm.module,
                empty_str_type,
                name=global_name,
            )
            global_value.linkage = "internal"
            global_value.global_constant = True
            global_value.initializer = ir.Constant(
                empty_str_type,
                bytearray(b"\0"),
            )
        return self.services.llvm.ir_builder.gep(
            global_value,
            [
                ir.Constant(self.services.llvm.INT32_TYPE, 0),
                ir.Constant(self.services.llvm.INT32_TYPE, 0),
            ],
            inbounds=True,
            name=f"{name_hint}_empty",
        )

    def _default_runtime_initializer(
        self,
        type_: astx.DataType,
        *,
        name_hint: str,
    ) -> ir.Value:
        """
        title: Return one runtime default value for class field construction.
        parameters:
          type_:
            type: astx.DataType
          name_hint:
            type: str
        returns:
          type: ir.Value
        """
        llvm_type = self.services.types.llvm_type(type_)
        if llvm_type is None:
            raise_lowering_internal_error(
                f"cannot lower default initializer for {type_!r}",
                node=None,
            )
        type_name = type_.__class__.__name__.lower()
        if type_name == "string":
            return self._empty_string_pointer(name_hint)
        if "float" in type_name:
            return ir.Constant(
                self.services.llvm.get_data_type(type_name), 0.0
            )
        if isinstance(type_, astx.ClassType):
            return ir.Constant(llvm_type, None)
        if isinstance(type_, astx.ListType):
            return cast(
                ir.Constant,
                self.services.empty_list_value_for_type(type_),
            )
        if isinstance(
            type_,
            (
                astx.StructType,
                astx.NullableType,
                astx.BufferViewType,
                astx.TensorType,
                astx.DataFrameType,
                astx.SeriesType,
                astx.PointerType,
                astx.OpaqueHandleType,
                astx.BufferOwnerType,
            ),
        ):
            return ir.Constant(llvm_type, None)
        return ir.Constant(self.services.llvm.get_data_type(type_name), 0)

    @dispatch
    def visit(self, node: astx.ClassConstruct) -> None:
        """
        title: Visit ClassConstruct nodes.
        parameters:
          node:
            type: astx.ClassConstruct
        """
        self.services.lower_class_construct(
            node, self._semantic_class_construction(node)
        )

    @dispatch
    def visit(self, node: astx.LiteralInteger | astx.LiteralFloat) -> None:
        """
        title: Emit a source literal using its resolved semantic type.
        parameters:
          node:
            type: astx.LiteralInteger | astx.LiteralFloat
        """
        semantic = require_semantic_metadata(
            getattr(node, "semantic", None),
            node=node,
            metadata="semantic",
            context="numeric literal",
        )
        type_ = require_semantic_metadata(
            self.services.types.llvm_type(semantic.resolved_type),
            node=node,
            metadata="resolved_type",
            context="numeric literal",
        )
        constant = require_semantic_metadata(
            semantic.numeric_constant,
            node=node,
            metadata="numeric_constant",
            context="numeric literal",
        )
        self.services.function_state.result_stack.append(
            ir.Constant(type_, constant)
        )

    @dispatch
    def visit(self, node: astx.LiteralInt32) -> None:
        """
        title: Visit LiteralInt32 nodes.
        parameters:
          node:
            type: astx.LiteralInt32
        """
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.INT32_TYPE, node.value)
        )

    @dispatch
    def visit(self, expr: astx.LiteralFloat32) -> None:
        """
        title: Visit LiteralFloat32 nodes.
        parameters:
          expr:
            type: astx.LiteralFloat32
        """
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.FLOAT_TYPE, expr.value)
        )

    @dispatch
    def visit(self, expr: astx.LiteralFloat64) -> None:
        """
        title: Visit LiteralFloat64 nodes.
        parameters:
          expr:
            type: astx.LiteralFloat64
        """
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.DOUBLE_TYPE, expr.value)
        )

    @dispatch
    def visit(self, node: astx.LiteralFloat16) -> None:
        """
        title: Visit LiteralFloat16 nodes.
        parameters:
          node:
            type: astx.LiteralFloat16
        """
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.FLOAT16_TYPE, node.value)
        )

    @dispatch
    def visit(self, expr: astx.LiteralNone) -> None:
        """
        title: Visit LiteralNone nodes.
        parameters:
          expr:
            type: astx.LiteralNone
        """
        self.services.function_state.result_stack.append(None)

    @dispatch
    def visit(self, node: astx.LiteralBoolean) -> None:
        """
        title: Visit LiteralBoolean nodes.
        parameters:
          node:
            type: astx.LiteralBoolean
        """
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.BOOLEAN_TYPE, int(node.value))
        )

    @dispatch
    def visit(self, node: astx.LiteralInt64) -> None:
        """
        title: Visit LiteralInt64 nodes.
        parameters:
          node:
            type: astx.LiteralInt64
        """
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.INT64_TYPE, node.value)
        )

    @dispatch
    def visit(self, node: astx.LiteralInt8) -> None:
        """
        title: Visit LiteralInt8 nodes.
        parameters:
          node:
            type: astx.LiteralInt8
        """
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.INT8_TYPE, node.value)
        )

    @dispatch
    def visit(self, node: astx.LiteralUInt8) -> None:
        """
        title: Visit LiteralUInt8 nodes.
        parameters:
          node:
            type: astx.LiteralUInt8
        """
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.UINT8_TYPE, node.value)
        )

    @dispatch
    def visit(self, node: astx.LiteralUInt16) -> None:
        """
        title: Visit LiteralUInt16 nodes.
        parameters:
          node:
            type: astx.LiteralUInt16
        """
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.UINT16_TYPE, node.value)
        )

    @dispatch
    def visit(self, node: astx.LiteralUInt32) -> None:
        """
        title: Visit LiteralUInt32 nodes.
        parameters:
          node:
            type: astx.LiteralUInt32
        """
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.UINT32_TYPE, node.value)
        )

    @dispatch
    def visit(self, node: astx.LiteralUInt64) -> None:
        """
        title: Visit LiteralUInt64 nodes.
        parameters:
          node:
            type: astx.LiteralUInt64
        """
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.UINT64_TYPE, node.value)
        )

    @dispatch
    def visit(self, node: astx.LiteralUInt128) -> None:
        """
        title: Visit LiteralUInt128 nodes.
        parameters:
          node:
            type: astx.LiteralUInt128
        """
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.UINT128_TYPE, node.value)
        )

    @dispatch
    def visit(self, expr: astx.LiteralUTF8Char) -> None:
        """
        title: Visit LiteralUTF8Char nodes.
        parameters:
          expr:
            type: astx.LiteralUTF8Char
        """
        self.services.function_state.result_stack.append(
            self.services.strings.constant(expr.value, name_hint="str_ascii")
        )

    @dispatch
    def visit(self, expr: astx.LiteralUTF8String) -> None:
        """
        title: Visit LiteralUTF8String nodes.
        parameters:
          expr:
            type: astx.LiteralUTF8String
        """
        self.services.function_state.result_stack.append(
            self.services.strings.constant(expr.value, name_hint="str_utf8")
        )

    @dispatch
    def visit(self, expr: astx.LiteralString) -> None:
        """
        title: Visit LiteralString nodes.
        parameters:
          expr:
            type: astx.LiteralString
        """
        self.services.visit_child(astx.LiteralUTF8String(value=expr.value))

    @dispatch
    def visit(self, node: astx.LiteralList) -> None:
        """
        title: Visit LiteralList nodes.
        parameters:
          node:
            type: astx.LiteralList
        """
        storage = semantic_info(node).facts.require(LITERAL_STORAGE, node=node)
        if len(storage.conversions) != len(node.elements):
            raise_lowering_internal_error(
                "literal storage conversions do not match its elements",
                node=node,
            )
        target_ty = self.services.types.llvm_type(storage.element_type)
        if target_ty is None:
            raise_lowering_internal_error(
                "literal storage has no LLVM representation", node=node
            )
        coerced: list[ir.Value] = []
        for element, conversion in zip(node.elements, storage.conversions):
            self.services.visit_child(element)
            value = self.services.function_state.result_stack.pop()
            if value is None:
                raise_lowering_internal_error(
                    "literal list element did not produce a value",
                    node=element,
                )
            if conversion is not None:
                value = self.services.numeric.aggregate_scalar(
                    value,
                    source_type=conversion.source_type,
                    target_type=conversion.target_type,
                )
            if value.type != target_ty:
                raise_lowering_internal_error(
                    "literal element does not match its resolved storage",
                    node=element,
                )
            coerced.append(value)
        count = len(coerced)
        if all(isinstance(value, ir.Constant) for value in coerced):
            arr_ty = ir.ArrayType(target_ty, count)
            self.services.function_state.result_stack.append(
                ir.Constant(arr_ty, coerced)
            )
            return

        arr_ty = ir.ArrayType(target_ty, count)
        alloca = self.services.create_entry_block_alloca("list_tmp", arr_ty)
        zero = ir.Constant(self.services.llvm.INT32_TYPE, 0)
        for index, value in enumerate(coerced):
            idx = ir.Constant(self.services.llvm.INT32_TYPE, index)
            slot = self.services.llvm.ir_builder.gep(
                alloca, [zero, idx], inbounds=True
            )
            self.services.llvm.ir_builder.store(value, slot)

        first_ptr = self.services.llvm.ir_builder.gep(
            alloca, [zero, zero], inbounds=True
        )
        self.services.function_state.result_stack.append(first_ptr)

    @dispatch
    def visit(self, node: astx.LiteralSet) -> None:
        """
        title: Visit LiteralSet nodes.
        parameters:
          node:
            type: astx.LiteralSet
        """

        def sort_key(lit: astx.Literal) -> tuple[str, int | float | str]:
            """
            title: Sort key.
            parameters:
              lit:
                type: astx.Literal
            returns:
              type: tuple[str, int | float | str]
            """
            type_name = type(lit).__name__
            value = getattr(lit, "value", None)
            comparable = (
                value if isinstance(value, (int, float, str)) else repr(lit)
            )
            return type_name, comparable

        storage = semantic_info(node).facts.require(LITERAL_STORAGE, node=node)
        if len(storage.conversions) != len(node.elements):
            raise_lowering_internal_error(
                "set storage conversions do not match its elements", node=node
            )
        element_type = self.services.types.llvm_type(storage.element_type)
        if not isinstance(element_type, ir.IntType):
            raise_lowering_internal_error(
                "set storage requires a resolved integer representation",
                node=node,
            )
        conversions = {
            id(element): conversion
            for element, conversion in zip(node.elements, storage.conversions)
        }
        constants: list[ir.Constant] = []
        for element in sorted(node.elements, key=sort_key):
            self.services.visit_child(element)
            value = self.services.function_state.result_stack.pop()
            conversion = conversions[id(element)]
            if value is None or conversion is None:
                raise_lowering_internal_error(
                    "set element is missing its value or conversion plan",
                    node=element,
                )
            value = self.services.numeric.aggregate_scalar(
                value,
                source_type=conversion.source_type,
                target_type=conversion.target_type,
            )
            if (
                not isinstance(value, ir.Constant)
                or value.type != element_type
            ):
                raise_lowering_internal_error(
                    "set element does not match its resolved constant storage",
                    node=element,
                )
            constants.append(value)
        array_type = ir.ArrayType(element_type, len(constants))
        self.services.function_state.result_stack.append(
            self.services.collection.mark_set_value(
                ir.Constant(array_type, constants)
            )
        )

    @dispatch
    def visit(self, node: astx.LiteralTuple) -> None:
        """
        title: Visit LiteralTuple nodes.
        parameters:
          node:
            type: astx.LiteralTuple
        """
        llvm_elems: list[ir.Value] = []
        for elem in node.elements:
            self.services.visit_child(elem)
            value = self.services.function_state.result_stack.pop()
            if value is None:
                raise_lowering_internal_error(
                    "LiteralTuple: invalid element lowering.", node=node
                )
            llvm_elems.append(value)

        count = len(llvm_elems)
        if count == 0:
            struct_ty = ir.LiteralStructType([])
            self.services.function_state.result_stack.append(
                ir.Constant(struct_ty, [])
            )
            return

        first_ty = llvm_elems[0].type
        homogeneous = all(value.type == first_ty for value in llvm_elems)
        all_constants = all(
            isinstance(value, ir.Constant) for value in llvm_elems
        )
        if homogeneous and all_constants:
            struct_ty = ir.LiteralStructType([first_ty] * count)
            self.services.function_state.result_stack.append(
                ir.Constant(struct_ty, llvm_elems)
            )
            return

        raise TypeError(
            "LiteralTuple: only empty or homogeneous constant tuples "
            "are supported"
        )

    @dispatch
    def visit(self, node: astx.LiteralDict) -> None:
        """
        title: Visit LiteralDict nodes.
        parameters:
          node:
            type: astx.LiteralDict
        """
        llvm_pairs: list[tuple[ir.Value, ir.Value]] = []
        for key_node, value_node in node.elements.items():
            self.services.visit_child(key_node)
            key_val = self.services.function_state.result_stack.pop()
            if key_val is None:
                raise_lowering_internal_error(
                    "LiteralDict: failed to lower key.", node=node
                )

            self.services.visit_child(value_node)
            val_val = self.services.function_state.result_stack.pop()
            if val_val is None:
                raise_lowering_internal_error(
                    "LiteralDict: failed to lower value.", node=node
                )

            llvm_pairs.append((key_val, val_val))

        count = len(llvm_pairs)
        if count == 0:
            pair_ty = ir.LiteralStructType(
                [self.services.llvm.INT32_TYPE, self.services.llvm.INT32_TYPE]
            )
            arr_ty = ir.ArrayType(pair_ty, 0)
            self.services.function_state.result_stack.append(
                ir.Constant(arr_ty, [])
            )
            return

        all_constants = all(
            isinstance(key, ir.Constant) and isinstance(value, ir.Constant)
            for key, value in llvm_pairs
        )
        if all_constants:
            first_key_ty = llvm_pairs[0][0].type
            first_val_ty = llvm_pairs[0][1].type
            pair_ty = ir.LiteralStructType([first_key_ty, first_val_ty])
            arr_ty = ir.ArrayType(pair_ty, count)

            struct_consts: list[ir.Constant] = []
            for key_val, val_val in llvm_pairs:
                if (
                    key_val.type != first_key_ty
                    or val_val.type != first_val_ty
                ):
                    raise TypeError(
                        "LiteralDict: heterogeneous constant key/value types "
                        "are not yet supported"
                    )
                struct_consts.append(ir.Constant(pair_ty, [key_val, val_val]))

            self.services.function_state.result_stack.append(
                ir.Constant(arr_ty, struct_consts)
            )
            return

        raise TypeError(
            "LiteralDict: only empty or all-constant dictionaries "
            "are supported in this version"
        )

    @dispatch
    def visit(self, node: astx.SubscriptExpr) -> None:
        """
        title: Visit SubscriptExpr nodes.
        parameters:
          node:
            type: astx.SubscriptExpr
        """
        info = getattr(node, "semantic", None)
        if isinstance(info, SemanticInfo) and info.tensor_index is not None:
            self.services.visit_child(info.tensor_index)
            return
        if self.services.sequences.lower(node) or self.services.text.lower(
            node
        ):
            return
        if self.services.lower_column_operation(node):
            return
        if isinstance(resolved_ast_type(node.value), astx.ListType):
            self.services.lower_list_subscript(
                base=node.value,
                index_node=node.index,
                result_node=node,
            )
            return

        lookup = semantic_info(node).facts.require(
            DICTIONARY_LOOKUP, node=node
        )
        dict_pair_fields = 2
        self.services.visit_child(node.value)
        dict_val = self.services.function_state.result_stack.pop()

        if not (
            isinstance(dict_val, ir.Constant)
            and isinstance(dict_val.type, ir.ArrayType)
            and isinstance(dict_val.type.element, ir.LiteralStructType)
            and len(dict_val.type.element.elements) == dict_pair_fields
        ):
            raise TypeError(
                "SubscriptExpr: only constant LiteralDict subscript "
                "is supported in this version"
            )

        self.services.visit_child(node.index)
        key_val = self.services.function_state.result_stack.pop()
        if key_val is None:
            raise_lowering_internal_error(
                "SubscriptExpr: invalid index lowering.", node=node
            )

        if dict_val.type.count == 0:
            raise KeyError("SubscriptExpr: key lookup on empty dict")

        if isinstance(key_val, ir.Constant):
            for entry in dict_val.constant:
                entry_key = entry.constant[0]
                if self.services.collection.constant_subscript_key_matches(
                    entry_key, key_val, lookup
                ):
                    self.services.function_state.result_stack.append(
                        entry.constant[1]
                    )
                    return
            raise KeyError(
                f"SubscriptExpr: key {key_val.constant!r} not found in dict"
            )

        self.services.collection.emit_runtime_subscript_lookup(
            dict_val,
            key_val,
            lookup,
        )

    @dispatch
    def visit(self, node: astx.LiteralInt16) -> None:
        """
        title: Visit LiteralInt16 nodes.
        parameters:
          node:
            type: astx.LiteralInt16
        """
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.INT16_TYPE, node.value)
        )
