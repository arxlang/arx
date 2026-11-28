"""
title: Register memory operations for the bundled stdlib module.
"""

import astx

from astx.types import AnyType
from irx.analysis.module_interfaces import ParsedModule
from irx.native import MemoryOperation, NativeBinding
from irx.typecheck import typechecked
from public import private


@private
@typechecked
def type_bindings() -> dict[str, astx.DataType]:
    """
    title: Bind host template bounds within the bundled memory module.
    returns: Private template-bound marker interpreted by IRx copy analysis.
    """
    return {"CopyableClass": AnyType(), "WeakClass": AnyType()}


@private
@typechecked
def prepare_memory_module(module: astx.Module, origin: str) -> ParsedModule:
    """
    title: Bind copy to its actual declaration in the bundled module.
    parameters:
      module: Parsed bundled memory source.
      origin: Bundled source path for diagnostics.
    returns: Parsed module with the trusted declaration registered.
    """
    declarations = {
        node.name: node
        for node in module.nodes
        if isinstance(node, astx.FunctionPrototype)
    }
    operations: tuple[MemoryOperation, ...] = ("copy", "downgrade", "upgrade")
    if set(declarations) != set(operations):
        raise ValueError("bundled stdlib.memory declarations do not match")
    return ParsedModule(
        "stdlib.memory",
        module,
        "stdlib.memory",
        origin,
        native_bindings=tuple(
            NativeBinding(
                declarations[name],
                ("list",) if name == "copy" else ("class",),
                memory=name,
            )
            for name in operations
        ),
        lazy_declarations=True,
        weak_class_type=True,
    )
