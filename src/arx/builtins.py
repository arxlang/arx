"""
title: Built-in function handlers for Arx parser lowering.
"""

from __future__ import annotations

import astx

from irx import system

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


def build_cast(value: astx.AST, target_type: astx.DataType) -> system.Cast:
    """
    title: Build an IRX Cast node.
    parameters:
      value:
        type: astx.AST
      target_type:
        type: astx.DataType
    returns:
      type: system.Cast
    """
    return system.Cast(value=value, target_type=target_type)


def build_print(message: astx.Expr) -> system.PrintExpr:
    """
    title: Build an IRX PrintExpr node.
    parameters:
      message:
        type: astx.Expr
    returns:
      type: system.PrintExpr
    """
    return system.PrintExpr(message=message)
