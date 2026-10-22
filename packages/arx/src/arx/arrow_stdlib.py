"""
title: Host bindings for the bundled Arrow standard library.
summary: >-
  Bind existing ASTx opaque types and explicit IRx native capabilities only
  while loading the reserved bundled module. No grammar or lowering lives here.
"""

import astx

from irx.analysis.module_interfaces import ParsedModule
from irx.builder.runtime.record_batch_api import (
    ARROW_API_SIGNATURES,
    PARQUET_API_SYMBOLS,
)
from irx.native import NativeBinding, TableIOOperation

MODULE_NAMES = frozenset({"stdlib.arrow", "stdlib.csv", "stdlib.parquet"})


IO_FUNCTIONS: dict[str, dict[str, TableIOOperation]] = {
    "stdlib.csv": {
        "read_csv": "read_csv",
        "write_csv": "write_csv",
        "irx_rb_api_csv_frame": "csv_frame",
        "irx_rb_api_csv_write_frame": "csv_write_frame",
    },
    "stdlib.parquet": {
        "read_parquet": "read_parquet",
        "write_parquet": "write_parquet",
        "where": "where",
        "irx_rb_api_parquet_frame": "parquet_frame",
        "irx_rb_api_parquet_write_frame": "parquet_write_frame",
    },
}


def type_bindings(module_name: str) -> dict[str, astx.DataType]:
    """
    title: Supply nominal native handle types to the bundled source parser.
    parameters:
      module_name:
        type: str
    returns:
      type: dict[str, astx.DataType]
    """
    kinds = {
        "stdlib.arrow": ("Schema", "Batch", "Builder", "Reader", "Writer"),
        "stdlib.csv": ("Schema", "Batch", "Csv"),
        "stdlib.parquet": ("Schema", "Batch", "Parquet", "Options"),
    }
    if module_name not in kinds:
        raise ValueError(f"unregistered bundled module: {module_name}")
    return {
        f"Arrow{kind}Handle": astx.OpaqueHandleType(f"IrxRbApi{kind}")
        for kind in kinds[module_name]
    }


def prepare_module(
    module: astx.Module, origin: str, module_name: str
) -> ParsedModule:
    """
    title: Attach native capabilities to actual bundled extern declarations.
    parameters:
      module:
        type: astx.Module
      origin:
        type: str
      module_name:
        type: str
    returns:
      type: ParsedModule
    """
    bindings: list[NativeBinding] = []
    if module_name not in MODULE_NAMES:
        raise ValueError(f"unregistered bundled module: {module_name}")
    for node in module.nodes:
        if not isinstance(node, astx.FunctionPrototype):
            continue
        if not getattr(node, "is_extern", False):
            continue
        operation = IO_FUNCTIONS.get(module_name, {}).get(node.name)
        if operation is not None:
            feature = (
                "parquet"
                if operation in {"read_parquet", "write_parquet", "where"}
                else "record_batch"
            )
            bindings.append(
                NativeBinding(node, (feature,), table_io=operation)
            )
            continue
        if node.name not in ARROW_API_SIGNATURES:
            raise ValueError(f"unregistered Arrow extern: {node.name}")
        format_module = (
            "stdlib.csv"
            if node.name.startswith("irx_rb_api_csv_")
            else "stdlib.parquet"
            if node.name.startswith(
                (
                    "irx_rb_api_parquet_",
                    "irx_rb_api_options_",
                    "irx_rb_api_filter_",
                )
            )
            else "stdlib.arrow"
        )
        if format_module != module_name:
            raise ValueError(f"extern {node.name} belongs to {format_module}")
        if isinstance(node.return_type, astx.String):
            setattr(node, "ffi_return_ownership", "owned")
        feature = (
            "parquet" if node.name in PARQUET_API_SYMBOLS else "record_batch"
        )
        bindings.append(NativeBinding(node, (feature,)))
    return ParsedModule(
        module_name,
        module,
        module_name,
        origin,
        native_bindings=tuple(bindings),
        lazy_declarations=True,
        native_arrow_classes=tuple(
            node
            for node in module.nodes
            if isinstance(node, astx.ClassDefStmt)
        ),
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
