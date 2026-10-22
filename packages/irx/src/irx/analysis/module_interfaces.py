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

from irx.native import NativeBinding, NativeFeature
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

    def __post_init__(self) -> None:
        """
        title: Validate an explicit host capability against its parsed module.
        """
        validate_file_registration(self.native_file_class, self.ast)
        if self.native_record_batch_class is not None and not any(
            node is self.native_record_batch_class for node in self.ast.nodes
        ):
            raise ValueError("native RecordBatch must belong to its module")
        validate_native_registration(
            self.native_features, self.native_bindings, self.ast
        )


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
