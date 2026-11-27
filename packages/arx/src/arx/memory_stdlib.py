"""
title: Register memory operations for the bundled stdlib module.
"""

import astx

from irx.analysis.module_interfaces import ParsedModule
from irx.native import NativeBinding
from irx.typecheck import typechecked
from public import private


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
    declarations = [
        node
        for node in module.nodes
        if isinstance(node, astx.FunctionPrototype) and node.name == "copy"
    ]
    if len(declarations) != 1:
        raise ValueError("bundled stdlib.memory requires one copy declaration")
    return ParsedModule(
        "stdlib.memory",
        module,
        "stdlib.memory",
        origin,
        native_bindings=(
            NativeBinding(declarations[0], ("list",), memory="copy"),
        ),
        lazy_declarations=True,
    )
