"""
title: Arx LLVM-IR integration helpers.
"""

from __future__ import annotations

import os
import tempfile

from pathlib import Path
from typing import Literal

import astx

from irx import astx as irx_astx
from irx.analysis.module_interfaces import ImportResolver, ParsedModule
from irx.buffer import BUFFER_VIEW_METADATA_EXTRA
from irx.builder import Builder as LLVMBuilder
from irx.builder import Visitor as LLVMVisitor
from irx.builder.runtime.linking import link_executable
from llvmlite import binding as llvm
from llvmlite import ir

from arx.ndarray import literal_values


class ArxVisitor(LLVMVisitor):
    """
    title: Arx-specific backend visitor customizations.
    attributes:
      _ndarray_global_counter:
        type: int
    """

    def __init__(
        self,
        active_runtime_features: set[str] | None = None,
    ) -> None:
        """
        title: Initialize the Arx visitor.
        parameters:
          active_runtime_features:
            type: set[str] | None
        """
        super().__init__(active_runtime_features=active_runtime_features)
        self._ndarray_global_counter: int = 0

    @LLVMVisitor.visit.dispatch  # type: ignore[attr-defined,untyped-decorator]
    def visit(self, node: irx_astx.BufferViewDescriptor) -> None:
        """
        title: Lower Arx ndarray descriptors to IRx buffer views.
        parameters:
          node:
            type: irx_astx.BufferViewDescriptor
        """
        values = literal_values(node)
        if values is None:
            metadata = getattr(
                getattr(node, "semantic", None),
                "extras",
                {},
            ).get(BUFFER_VIEW_METADATA_EXTRA, node.metadata)
            self.result_stack.append(
                self._buffer_view_value_from_metadata(metadata)
            )
            return

        metadata = getattr(
            getattr(node, "semantic", None),
            "extras",
            {},
        ).get(BUFFER_VIEW_METADATA_EXTRA, node.metadata)
        element_type = node.type_.element_type
        if element_type is None:
            raise TypeError(
                "ndarray descriptors require a scalar element type"
            )

        data_ptr = self._ndarray_data_pointer(values, element_type)
        fields: list[ir.Value] = [
            data_ptr,
            self._buffer_handle_value(
                metadata.owner,
                self._llvm.BUFFER_OWNER_HANDLE_TYPE,
            ),
            self._buffer_handle_value(
                metadata.dtype,
                self._llvm.OPAQUE_POINTER_TYPE,
            ),
            ir.Constant(self._llvm.INT32_TYPE, metadata.ndim),
            self._i64_array_pointer(metadata.shape, purpose="shape"),
            self._i64_array_pointer(metadata.strides, purpose="strides"),
            ir.Constant(self._llvm.INT64_TYPE, metadata.offset_bytes),
            ir.Constant(self._llvm.INT32_TYPE, metadata.flags),
        ]

        value: ir.Value = ir.Constant(self._llvm.BUFFER_VIEW_TYPE, None)
        for index, field in enumerate(fields):
            value = self._llvm.ir_builder.insert_value(
                value,
                field,
                index,
                name=f"arx_ndarray_field_{index}",
            )
        self.result_stack.append(value)

    def _ndarray_data_pointer(
        self,
        values: tuple[irx_astx.Literal, ...],
        element_type: irx_astx.DataType,
    ) -> ir.Value:
        """
        title: Materialize one stable backing store for one literal ndarray.
        parameters:
          values:
            type: tuple[irx_astx.Literal, Ellipsis]
          element_type:
            type: irx_astx.DataType
        returns:
          type: ir.Value
        """
        if not values:
            return ir.Constant(self._llvm.OPAQUE_POINTER_TYPE, None)

        llvm_element_type = self._llvm_type_for_ast_type(element_type)
        if llvm_element_type is None:
            raise TypeError("ndarray element type cannot be lowered")

        array_type = ir.ArrayType(llvm_element_type, len(values))
        initializer = ir.Constant(
            array_type,
            [
                self._ndarray_scalar_constant(value, llvm_element_type)
                for value in values
            ],
        )
        index = self._ndarray_global_counter
        self._ndarray_global_counter += 1
        global_value = ir.GlobalVariable(
            self._llvm.module,
            array_type,
            name=f"arx_ndarray_data_{index}",
        )
        global_value.linkage = "internal"
        global_value.global_constant = True
        global_value.initializer = initializer

        data_ptr = self._llvm.ir_builder.gep(
            global_value,
            [
                ir.Constant(self._llvm.INT32_TYPE, 0),
                ir.Constant(self._llvm.INT32_TYPE, 0),
            ],
            inbounds=True,
            name=f"arx_ndarray_ptr_{index}",
        )
        return self._llvm.ir_builder.bitcast(
            data_ptr,
            self._llvm.OPAQUE_POINTER_TYPE,
            name=f"arx_ndarray_opaque_{index}",
        )

    def _ndarray_scalar_constant(
        self,
        value: irx_astx.Literal,
        llvm_element_type: ir.Type,
    ) -> ir.Constant:
        """
        title: Convert one ndarray scalar literal into one LLVM constant.
        parameters:
          value:
            type: irx_astx.Literal
          llvm_element_type:
            type: ir.Type
        returns:
          type: ir.Constant
        """
        if isinstance(value, irx_astx.LiteralBoolean):
            return ir.Constant(llvm_element_type, int(value.value))
        if isinstance(value, irx_astx.LiteralUTF8Char):
            return ir.Constant(llvm_element_type, ord(value.value))
        if isinstance(
            value,
            (
                irx_astx.LiteralInt8,
                irx_astx.LiteralInt16,
                irx_astx.LiteralInt32,
                irx_astx.LiteralInt64,
            ),
        ):
            if isinstance(llvm_element_type, ir.IntType):
                return ir.Constant(llvm_element_type, int(value.value))
            return ir.Constant(llvm_element_type, float(value.value))
        if isinstance(
            value,
            (
                irx_astx.LiteralFloat32,
                irx_astx.LiteralFloat64,
            ),
        ):
            return ir.Constant(llvm_element_type, float(value.value))
        raise TypeError("unsupported ndarray scalar literal")


class ArxBuilder(LLVMBuilder):
    """
    title: Arx backend builder with Arx overrides.
    attributes:
      translator:
        type: ArxVisitor
    """

    LINK_MODES = {"auto", "pie", "no-pie"}

    def __init__(self) -> None:
        """
        title: Initialize ArxBuilder.
        """
        super().__init__()
        self.translator: ArxVisitor = self._new_translator()

    def _new_translator(self) -> ArxVisitor:
        """
        title: Create the Arx visitor.
        returns:
          type: ArxVisitor
        """
        return ArxVisitor(
            active_runtime_features=set(self.runtime_feature_names)
        )

    def _build_from_ir_result(
        self,
        result: str,
        output_file: str,
        link: bool,
        link_mode: Literal["auto", "pie", "no-pie"],
    ) -> None:
        """
        title: Materialize LLVM IR into either an object file or executable.
        parameters:
          result:
            type: str
          output_file:
            type: str
          link:
            type: bool
          link_mode:
            type: Literal[auto, pie, no-pie]
        """
        result_mod = llvm.parse_assembly(result)
        result_object = self.translator.target_machine.emit_object(result_mod)

        self.output_file = output_file

        if not link:
            with open(self.output_file, "wb") as file_handler:
                file_handler.write(result_object)
            return

        if link_mode not in self.LINK_MODES:
            raise ValueError(
                "Invalid link mode. Expected one of: auto, pie, no-pie."
            )

        extra_linker_flags: tuple[str, ...] = ()
        if link_mode == "pie":
            extra_linker_flags = ("-pie",)
        elif link_mode == "no-pie":
            extra_linker_flags = ("-no-pie",)

        with tempfile.TemporaryDirectory() as temp_dir:
            self.tmp_path = temp_dir
            file_path_o = Path(temp_dir) / "arx_module.o"
            with open(file_path_o, "wb") as file_handler:
                file_handler.write(result_object)

            link_executable(
                primary_object=file_path_o,
                output_file=Path(self.output_file),
                artifacts=self.translator.runtime_features.native_artifacts(),
                linker_flags=(
                    *self.translator.runtime_features.linker_flags(),
                    *extra_linker_flags,
                ),
            )

        os.chmod(self.output_file, 0o755)

    def build(
        self,
        node: astx.AST,
        output_file: str,
        link: bool = True,
        link_mode: Literal["auto", "pie", "no-pie"] = "auto",
    ) -> None:
        """
        title: >-
          Transpile the ASTx to LLVM-IR and build it to an executable file.
        parameters:
          node:
            type: astx.AST
          output_file:
            type: str
          link:
            type: bool
          link_mode:
            type: Literal[auto, pie, no-pie]
        """
        result = self.translate(node)
        self._build_from_ir_result(result, output_file, link, link_mode)

    def build_modules(
        self,
        root: ParsedModule,
        resolver: ImportResolver,
        output_file: str,
        link: bool = True,
        link_mode: Literal["auto", "pie", "no-pie"] = "auto",
    ) -> None:
        """
        title: Build a reachable graph of parsed modules.
        parameters:
          root:
            type: ParsedModule
          resolver:
            type: ImportResolver
          output_file:
            type: str
          link:
            type: bool
          link_mode:
            type: Literal[auto, pie, no-pie]
        """
        result = self.translate_modules(root, resolver)
        self._build_from_ir_result(result, output_file, link, link_mode)
