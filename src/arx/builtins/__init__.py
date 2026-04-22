"""
title: Compiler builtin helpers and bundled builtin-module loader.
"""

from __future__ import annotations

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

__all__ = [
    "BUILTIN_CAST",
    "BUILTIN_NAMESPACE",
    "BUILTIN_PRINT",
    "BUILTIN_SOURCE_EXTENSION",
    "BuiltinModuleAsset",
    "build_cast",
    "build_print",
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
