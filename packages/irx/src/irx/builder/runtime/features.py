"""
title: Runtime feature specifications and LLVM symbol helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Mapping, TypeAlias, cast

from llvmlite import ir

from irx.native import NativeArtifact, NativeArtifactKind
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.protocols import VisitorProtocol

if TYPE_CHECKING:
    RuntimeSymbolFactory: TypeAlias = Callable[[VisitorProtocol], ir.Function]
else:
    RuntimeSymbolFactory: TypeAlias = Callable[[object], ir.Function]


@typechecked
@dataclass(frozen=True)
class ExternalSymbolSpec:
    """
    title: Describe one external symbol exposed by a runtime feature.
    attributes:
      name:
        type: str
      declare:
        type: RuntimeSymbolFactory
    """

    name: str
    declare: RuntimeSymbolFactory


@typechecked
@dataclass(frozen=True)
class RuntimeFeature:
    """
    title: Describe one optional native runtime feature.
    attributes:
      name:
        type: str
      symbols:
        type: Mapping[str, ExternalSymbolSpec]
      artifacts:
        type: tuple[NativeArtifact, Ellipsis]
      linker_flags:
        type: tuple[str, Ellipsis]
      metadata:
        type: Mapping[str, object]
    """

    name: str
    symbols: Mapping[str, ExternalSymbolSpec] = field(default_factory=dict)
    artifacts: tuple[NativeArtifact, ...] = ()
    linker_flags: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)


@typechecked
def declare_external_function(
    module: ir.Module, name: str, fn_type: ir.FunctionType
) -> ir.Function:
    """
    title: Declare or reuse an external function in an LLVM module.
    parameters:
      module:
        type: ir.Module
      name:
        type: str
      fn_type:
        type: ir.FunctionType
    returns:
      type: ir.Function
    """
    existing = module.globals.get(name)
    if existing is not None:
        if not isinstance(existing, ir.Function):
            raise TypeError(f"Global '{name}' is not a function")
        if existing.function_type != fn_type:
            raise TypeError(
                f"Function '{name}' already exists with a mismatch"
            )
        return cast(ir.Function, existing)

    fn = ir.Function(module, fn_type, name=name)
    fn.linkage = "external"
    return fn


__all__ = [
    "ExternalSymbolSpec",
    "NativeArtifact",
    "NativeArtifactKind",
    "RuntimeFeature",
    "declare_external_function",
]
