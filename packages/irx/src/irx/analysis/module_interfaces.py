"""
title: Host-facing module interfaces for multi-module analysis.
summary: >-
  Define the parser-agnostic types that hosts pass into IRx for multi-module
  compilation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeAlias, runtime_checkable

import astx

from public import private, public

from irx.native import NativeBinding, NativeFeature, TableIOOperation
from irx.typecheck import typechecked

ModuleKey: TypeAlias = str


@public
@typechecked
class ImportResolutionError(LookupError):
    """
    title: Expected host failure while resolving or parsing an import.
    summary: >-
      Hosts raise this type for user-actionable import failures. Unexpected
      resolver exceptions cross the IRx boundary unchanged so compiler bugs are
      not mislabeled as source diagnostics.
    """


@public
@typechecked
@dataclass(frozen=True)
class ParsedModule:
    """
    title: One parsed module supplied by the host compiler.
    summary: >-
      Bundle a host-owned module key with the parsed AST and optional human-
      facing origin metadata.
    attributes:
      key:
        type: ModuleKey
      ast:
        type: astx.Module
      display_name:
        type: str | None
      origin:
        type: str | None
      native_file_class:
        type: astx.ClassDefStmt | None
      native_features:
        type: tuple[NativeFeature, Ellipsis]
      native_bindings:
        type: tuple[NativeBinding, Ellipsis]
      native_record_batch_class:
        type: astx.ClassDefStmt | None
      lazy_declarations:
        type: bool
      native_arrow_classes:
        type: tuple[astx.ClassDefStmt, Ellipsis]
      exception_classes:
        type: tuple[astx.ClassDefStmt, Ellipsis]
        description: >-
          Explicit declaration identities for one complete builtin exception
          hierarchy. IRx validates its nominal bases and native storage schema;
          matching source names alone never register an exception capability.
    """

    key: ModuleKey
    ast: astx.Module
    display_name: str | None = None
    origin: str | None = None
    native_file_class: astx.ClassDefStmt | None = None
    native_features: tuple[NativeFeature, ...] = ()
    native_bindings: tuple[NativeBinding, ...] = ()
    native_record_batch_class: astx.ClassDefStmt | None = None
    lazy_declarations: bool = False
    native_arrow_classes: tuple[astx.ClassDefStmt, ...] = ()
    exception_classes: tuple[astx.ClassDefStmt, ...] = ()

    def __post_init__(self) -> None:
        """
        title: Validate an explicit host capability against its parsed module.
        """
        validate_file_registration(self.native_file_class, self.ast)
        validate_exception_registration(self.exception_classes, self.ast)
        for declaration in self.native_arrow_classes:
            if not any(node is declaration for node in self.ast.nodes):
                raise ValueError(
                    "native Arrow class must belong to its module"
                )
        if self.native_record_batch_class is not None and not any(
            node is self.native_record_batch_class for node in self.ast.nodes
        ):
            raise ValueError("native RecordBatch must belong to its module")
        validate_native_registration(
            self.native_features, self.native_bindings, self.ast
        )


@private
@typechecked
def validate_exception_registration(
    declarations: tuple[astx.ClassDefStmt, ...], module: astx.Module
) -> None:
    """
    title: Validate all exception capability items and declaration membership.
    parameters:
      declarations:
        type: tuple[astx.ClassDefStmt, Ellipsis]
      module:
        type: astx.Module
    """
    if len({id(item) for item in declarations}) != len(declarations):
        raise ValueError("duplicate exception class registration")
    for declaration in declarations:
        if not any(node is declaration for node in module.nodes):
            raise ValueError("exception class must belong to its module")


@private
@typechecked
def validate_native_registration(
    features: tuple[NativeFeature, ...],
    bindings: tuple[NativeBinding, ...],
    module: astx.Module,
) -> None:
    """
    title: Validate capabilities against actual top-level extern identities.
    parameters:
      features:
        type: tuple[NativeFeature, Ellipsis]
      bindings:
        type: tuple[NativeBinding, Ellipsis]
      module:
        type: astx.Module
    """
    names = tuple(feature.name for feature in features)
    if len(names) != len(set(names)):
        raise ValueError("duplicate native feature declarations")
    declarations: set[int] = set()
    for binding in bindings:
        declaration = binding.declaration
        if not any(node is declaration for node in module.nodes):
            raise ValueError("native extern must belong to its module")
        if not getattr(declaration, "is_extern", False):
            raise ValueError("native binding requires an extern declaration")
        if id(declaration) in declarations:
            raise ValueError("duplicate native extern binding")
        declarations.add(id(declaration))
        if binding.table_io is not None:
            validate_table_io_registration(declaration, binding.table_io)


@private
@typechecked
def validate_table_io_registration(
    declaration: astx.FunctionPrototype, operation: TableIOOperation
) -> None:
    """
    title: >-
      Reject malformed trusted prototypes before relaxing the FFI boundary.
    parameters:
      declaration:
        type: astx.FunctionPrototype
      operation:
        type: TableIOOperation
    """
    handle = astx.OpaqueHandleType(
        "IrxRbApiCsv" if operation.startswith("csv_") else "IrxRbApiParquet"
    )
    frame = astx.DataFrameType()
    specs = {
        "read_csv": (("path", astx.String()),),
        "read_parquet": (("path", astx.String()),),
        "write_csv": (("frame", frame), ("path", astx.String())),
        "write_parquet": (("frame", frame), ("path", astx.String())),
        "where": (("column", astx.String()), ("operation", astx.String())),
        "csv_frame": (("box", handle),),
        "parquet_frame": (("box", handle),),
        "csv_write_frame": (("box", handle), ("frame", frame)),
        "parquet_write_frame": (("box", handle), ("frame", frame)),
    }
    expected = specs[operation]
    args = declaration.args.nodes
    if len(args) != len(expected):
        raise ValueError("invalid table I/O capability parameters")
    for argument, (name, type_) in zip(args, expected):
        if argument.name != name or not isinstance(
            argument.type_, type(type_)
        ):
            raise ValueError(
                "invalid table I/O capability parameter type/name"
            )
        if isinstance(type_, astx.OpaqueHandleType) and (
            not isinstance(argument.type_, astx.OpaqueHandleType)
            or argument.type_.handle_name != type_.handle_name
        ):
            raise ValueError("invalid table I/O capability handle")
        if isinstance(argument.type_, astx.DataFrameType) and (
            argument.type_.columns is not None
            or argument.type_.row_count is not None
        ):
            raise ValueError("table I/O capability requires a runtime schema")
    result = declaration.return_type
    if operation == "where":
        valid = isinstance(result, astx.ClassType)
    elif "write" in operation:
        valid = isinstance(result, astx.NoneType)
    else:
        valid = (
            isinstance(result, astx.DataFrameType)
            and result.columns is None
            and result.row_count is None
        )
    if not valid:
        raise ValueError("invalid table I/O capability result")


@private
@typechecked
def validate_file_registration(
    declaration: astx.ClassDefStmt | None, module: astx.Module
) -> None:
    """
    title: Require native File privileges to reference a host-supplied node.
    parameters:
      declaration:
        type: astx.ClassDefStmt | None
      module:
        type: astx.Module
    """
    if declaration is not None and not any(
        node is declaration for node in module.nodes
    ):
        raise ValueError("native File declaration must belong to its module")


@public
@runtime_checkable
class ImportResolver(Protocol):
    """
    title: Host callback that resolves imports to parsed modules.
    summary: >-
      Describe the host-owned callback IRx uses to turn import specifiers into
      already-parsed modules.
    """

    def __call__(
        self,
        requesting_module_key: ModuleKey,
        import_node: astx.ImportStmt | astx.ImportFromStmt,
        requested_specifier: str,
    ) -> ParsedModule:
        """
        title: Resolve one import request.
        summary: >-
          Return the parsed module selected by the host for one import edge.
          Raise ImportResolutionError for expected user-actionable failures;
          other exceptions are treated as internal resolver failures.
        parameters:
          requesting_module_key:
            type: ModuleKey
          import_node:
            type: astx.ImportStmt | astx.ImportFromStmt
          requested_specifier:
            type: str
        returns:
          type: ParsedModule
        """
        _ = requesting_module_key
        _ = import_node
        _ = requested_specifier
        raise NotImplementedError


__all__ = [
    "ImportResolutionError",
    "ImportResolver",
    "ModuleKey",
    "ParsedModule",
]
