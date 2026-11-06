"""
title: Module-owned LLVM representations of resolved ASTx types.
summary: >-
  No source discovery, symbol lookup, conversion policy, or backend state is
  inferred.
"""

from collections.abc import Callable, Mapping

import astx

from llvmlite import ir
from public import private

from irx.analysis.module_symbols import (
    mangle_function_name,
    mangle_struct_name,
)
from irx.analysis.resolved_nodes import SemanticInfo
from irx.builder.diagnostics import (
    raise_lowering_internal_error,
    require_semantic_metadata,
)
from irx.builder.runtime.sequence import sequence_view_type
from irx.typecheck import typechecked


@private
@typechecked
def semantic_info(node: astx.AST) -> SemanticInfo:
    """
    title: Require typed analysis metadata before backend emission.
    parameters:
      node:
        type: astx.AST
    returns:
      type: SemanticInfo
    """
    info = getattr(node, "semantic", None)
    if not isinstance(info, SemanticInfo):
        raise_lowering_internal_error("missing semantic metadata", node=node)
    return info


@private
@typechecked
def resolved_type(node: astx.AST | None) -> astx.DataType | None:
    """
    title: Read a resolved expression type without reconstructing its meaning.
    parameters:
      node:
        type: astx.AST | None
    returns:
      type: astx.DataType | None
    """
    return None if node is None else semantic_info(node).resolved_type


@private
@typechecked
def semantic_symbol_key(node: astx.AST) -> str:
    """
    title: Require the resolved binding identity, never its source spelling.
    parameters:
      node:
        type: astx.AST
    returns:
      type: str
    """
    symbol = require_semantic_metadata(
        semantic_info(node).resolved_symbol,
        node=node,
        metadata="resolved_symbol",
        context="binding identity",
    )
    return symbol.symbol_id


@private
@typechecked
def semantic_assignment_key(node: astx.AST) -> str:
    """
    title: Require the validated assignment target identity.
    parameters:
      node:
        type: astx.AST
    returns:
      type: str
    """
    assignment = require_semantic_metadata(
        semantic_info(node).resolved_assignment,
        node=node,
        metadata="resolved_assignment",
        context="assignment identity",
    )
    return assignment.target.symbol_id


@private
@typechecked
def semantic_function_key(node: astx.AST) -> str:
    """
    title: Require the analyzed callable identity.
    parameters:
      node:
        type: astx.AST
    returns:
      type: str
    """
    function = require_semantic_metadata(
        semantic_info(node).resolved_function,
        node=node,
        metadata="resolved_function",
        context="function identity",
    )
    return function.symbol_id


@private
@typechecked
def semantic_function_name(node: astx.AST) -> str:
    """
    title: Render the LLVM callable name from its resolved signature.
    parameters:
      node:
        type: astx.AST
    returns:
      type: str
    """
    function = require_semantic_metadata(
        semantic_info(node).resolved_function,
        node=node,
        metadata="resolved_function",
        context="function representation",
    )
    symbol_name = function.signature.symbol_name or function.name
    if function.signature.is_extern:
        return symbol_name
    return mangle_function_name(function.module_key, symbol_name)


@private
@typechecked
def semantic_struct_key(node: astx.AST) -> str:
    """
    title: Require the qualified identity selected for a struct declaration.
    parameters:
      node:
        type: astx.AST
    returns:
      type: str
    """
    struct = require_semantic_metadata(
        semantic_info(node).resolved_struct,
        node=node,
        metadata="resolved_struct",
        context="struct identity",
    )
    return struct.qualified_name


@private
@typechecked
def semantic_struct_name(node: astx.AST) -> str:
    """
    title: Render a struct name only from its analyzed module and identity.
    parameters:
      node:
        type: astx.AST
    returns:
      type: str
    """
    struct = require_semantic_metadata(
        semantic_info(node).resolved_struct,
        node=node,
        metadata="resolved_struct",
        context="struct representation",
    )
    return mangle_struct_name(struct.module_key, struct.name)


@private
@typechecked
def semantic_class_key(node: astx.AST) -> str:
    """
    title: Require the qualified semantic identity of a class declaration.
    parameters:
      node:
        type: astx.AST
    returns:
      type: str
    """
    class_ = require_semantic_metadata(
        semantic_info(node).resolved_class,
        node=node,
        metadata="resolved_class",
        context="class identity",
    )
    return class_.qualified_name


@private
@typechecked
def semantic_class_name(node: astx.AST) -> str:
    """
    title: Require the LLVM class name selected by its resolved layout.
    parameters:
      node:
        type: astx.AST
    returns:
      type: str
    """
    class_ = require_semantic_metadata(
        semantic_info(node).resolved_class,
        node=node,
        metadata="resolved_class",
        context="class representation",
    )
    layout = require_semantic_metadata(
        class_.layout,
        node=node,
        metadata="layout",
        context="class representation",
    )
    if not layout.llvm_name:
        raise_lowering_internal_error(
            "resolved class layout has no LLVM name", node=node
        )
    return layout.llvm_name


@private
@typechecked
class TypeLowering:
    """
    title: Module-local LLVM representation mapping for resolved ASTx types.
    summary: >-
      Struct mappings contain semantically qualified identities, never source
      names. The scalar resolver supplies the target's established scalar and
      temporal representations; buffer views retain the canonical ABI type.
      Class and struct types need their analyzed qualified identity; matching
      source spelling alone never selects a cached representation.
    attributes:
      struct_types:
        type: Mapping[str, ir.Type]
      scalar_type:
        type: Callable[[str], ir.Type]
      buffer_view_type:
        type: ir.Type
    """

    struct_types: Mapping[str, ir.Type]
    scalar_type: Callable[[str], ir.Type]
    buffer_view_type: ir.Type

    def __init__(
        self,
        struct_types: Mapping[str, ir.Type],
        scalar_type: Callable[[str], ir.Type],
        buffer_view_type: ir.Type,
    ) -> None:
        """
        title: Bind only the representation facts needed by this module.
        parameters:
          struct_types:
            type: Mapping[str, ir.Type]
          scalar_type:
            type: Callable[[str], ir.Type]
          buffer_view_type:
            type: ir.Type
        """
        self.struct_types = struct_types
        self.scalar_type = scalar_type
        self.buffer_view_type = buffer_view_type

    def union_storage_ast_type(self, type_: astx.UnionType) -> astx.DataType:
        """
        title: Consume the analysis-selected storage type of a finite union.
        parameters:
          type_:
            type: astx.UnionType
        returns:
          type: astx.DataType
        """
        return require_semantic_metadata(
            semantic_info(type_).numeric_storage,
            node=type_,
            metadata="numeric_storage",
            context="union storage",
        )

    def llvm_type(self, type_: astx.DataType | None) -> ir.Type | None:
        """
        title: >-
          Translate a resolved type without resolving names or conversions.
        parameters:
          type_:
            type: astx.DataType | None
        returns:
          type: ir.Type | None
        """
        if type_ is None:
            return None
        if isinstance(type_, astx.SequenceType):
            return sequence_view_type()
        if isinstance(type_, astx.NullableType):
            inner = self.llvm_type(type_.value_type)
            return (
                None
                if inner is None
                else ir.LiteralStructType([ir.IntType(1), inner])
            )
        if isinstance(type_, astx.UnionType):
            return self.llvm_type(self.union_storage_ast_type(type_))
        pointer = ir.IntType(8).as_pointer()
        if isinstance(
            type_,
            (
                astx.NamespaceType,
                astx.BufferOwnerType,
                astx.OpaqueHandleType,
                astx.DataFrameType,
                astx.SeriesType,
            ),
        ):
            return pointer
        if isinstance(type_, astx.GeneratorType):
            return ir.LiteralStructType([pointer, pointer])
        if isinstance(type_, astx.PointerType):
            if type_.pointee_type is None:
                return pointer
            pointee = self.llvm_type(type_.pointee_type)
            return None if pointee is None else pointee.as_pointer()
        if isinstance(type_, (astx.ListType, astx.Bytes)):
            return ir.LiteralStructType(
                [
                    pointer,
                    ir.IntType(64),
                    ir.IntType(64),
                    ir.IntType(64),
                    ir.IntType(32),
                ]
            )
        if isinstance(type_, (astx.BufferViewType, astx.TensorType)):
            return self.buffer_view_type
        if isinstance(type_, astx.StructType):
            key = type_.qualified_name
            return None if key is None else self.struct_types.get(key)
        if isinstance(type_, astx.ClassType):
            key = type_.qualified_name
            type_value = None if key is None else self.struct_types.get(key)
            return None if type_value is None else type_value.as_pointer()
        return self.scalar_type(type(type_).__name__.lower())
