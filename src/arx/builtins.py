"""
title: Built-in function handlers for Arx parser lowering.
"""

from __future__ import annotations

import astx
import irx.astx as irx_astx

BUILTIN_CAST = "cast"
BUILTIN_PRINT = "print"


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
    title: Build an IRX Cast node.
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
    title: Build an IRX PrintExpr node.
    parameters:
      message:
        type: astx.Expr
    returns:
      type: irx_astx.PrintExpr
    """
    return irx_astx.PrintExpr(message=message)
