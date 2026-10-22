"""
title: Host bindings for the bundled Arrow standard library.
summary: >-
  Bind existing ASTx opaque types and explicit IRx native capabilities only
  while loading the reserved bundled module. No grammar or lowering lives here.
"""

import astx

from irx.analysis.module_interfaces import ParsedModule
from irx.native import NativeBinding

MODULE_NAME = "stdlib.arrow"


def type_bindings() -> dict[str, astx.DataType]:
    """
    title: Supply nominal native handle types to the bundled source parser.
    returns:
      type: dict[str, astx.DataType]
    """
    return {
        f"Arrow{kind}Handle": astx.OpaqueHandleType(f"IrxRbApi{kind}")
        for kind in (
            "Schema",
            "Batch",
            "Builder",
            "Reader",
            "Writer",
            "Parquet",
            "Csv",
        )
    }


def prepare_module(module: astx.Module, origin: str) -> ParsedModule:
    """
    title: Attach native capabilities to actual bundled extern declarations.
    parameters:
      module:
        type: astx.Module
      origin:
        type: str
    returns:
      type: ParsedModule
    """
    bindings: list[NativeBinding] = []
    for node in module.nodes:
        if not isinstance(node, astx.FunctionPrototype):
            continue
        if not getattr(node, "is_extern", False):
            continue
        if isinstance(node.return_type, astx.String):
            setattr(node, "ffi_return_ownership", "owned")
        bindings.append(NativeBinding(node, ("record_batch",)))
    return ParsedModule(
        MODULE_NAME,
        module,
        MODULE_NAME,
        origin,
        native_bindings=tuple(bindings),
        native_record_batch_class=next(
            (
                node
                for node in module.nodes
                if isinstance(node, astx.ClassDefStmt)
                and node.name == "RecordBatch"
            ),
            None,
        ),
    )
