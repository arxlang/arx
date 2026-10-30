"""
title: Compatibility aliases for system nodes owned by ASTx.
"""

from typing import TypeAlias

from astx import system as astx_system

AssertStmt: TypeAlias = astx_system.AssertStmt
Cast: TypeAlias = astx_system.Cast
PrintExpr: TypeAlias = astx_system.PrintExpr

__all__ = ["AssertStmt", "Cast", "PrintExpr"]
