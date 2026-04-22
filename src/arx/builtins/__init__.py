"""
title: Compiler builtin helpers and bundled builtin-module loader.
"""

from __future__ import annotations

from dataclasses import dataclass

import astx
import irx.astx as irx_astx

from arx.builtins.loader import (
    BUILTIN_NAMESPACE,
    BUILTIN_SOURCE_EXTENSION,
    BuiltinModuleAsset,
    get_builtin_source,
    is_builtin_module_specifier,
    list_builtin_modules,
    load_builtin_module,
    resolve_builtin_resource,
)

BUILTIN_CAST = "cast"
BUILTIN_PRINT = "print"
_GENERATORS_MODULE = f"{BUILTIN_NAMESPACE}.generators"


@dataclass(frozen=True)
class AmbientBuiltinBinding:
    """
    title: One compiler-injected builtin binding.
    attributes:
      name:
        type: str
      module:
        type: str
    """

    name: str
    module: str


_AMBIENT_BUILTIN_BINDINGS = (
    AmbientBuiltinBinding(name="range", module=_GENERATORS_MODULE),
)

__all__ = [
    "BUILTIN_CAST",
    "BUILTIN_NAMESPACE",
    "BUILTIN_PRINT",
    "BUILTIN_SOURCE_EXTENSION",
    "AmbientBuiltinBinding",
    "BuiltinModuleAsset",
    "build_cast",
    "build_print",
    "get_ambient_builtin_imports",
    "get_builtin_source",
    "is_builtin",
    "is_builtin_module_specifier",
    "list_builtin_modules",
    "load_builtin_module",
    "resolve_builtin_resource",
]


def is_builtin(name: str) -> bool:
    """
    title: Check whether a function name is a parser-level built-in.
    parameters:
      name:
        type: str
    returns:
      type: bool
    """
    return name in {BUILTIN_CAST, BUILTIN_PRINT}


def build_cast(
    value: astx.DataType, target_type: astx.DataType
) -> irx_astx.Cast:
    """
    title: Build an IRx Cast node.
    parameters:
      value:
        type: astx.DataType
      target_type:
        type: astx.DataType
    returns:
      type: irx_astx.Cast
    """
    return irx_astx.Cast(value=value, target_type=target_type)


def build_print(message: astx.Expr) -> irx_astx.PrintExpr:
    """
    title: Build an IRx PrintExpr node.
    parameters:
      message:
        type: astx.Expr
    returns:
      type: irx_astx.PrintExpr
    """
    return irx_astx.PrintExpr(message=message)


def get_ambient_builtin_imports(
    module_key: str,
) -> tuple[irx_astx.ImportFromStmt, ...]:
    """
    title: Build the implicit builtin imports for one module.
    parameters:
      module_key:
        type: str
    returns:
      type: tuple[irx_astx.ImportFromStmt, Ellipsis]
    """
    grouped_aliases: dict[str, list[irx_astx.AliasExpr]] = {}

    for binding in _AMBIENT_BUILTIN_BINDINGS:
        if module_key == binding.module:
            continue
        aliases = grouped_aliases.setdefault(binding.module, [])
        aliases.append(irx_astx.AliasExpr(binding.name))

    imports: list[irx_astx.ImportFromStmt] = []
    for module_name, aliases in grouped_aliases.items():
        imports.append(irx_astx.ImportFromStmt(aliases, module=module_name))

    return tuple(imports)
