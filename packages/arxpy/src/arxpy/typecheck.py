"""
title: Runtime type-checking helpers for ArxPy.
summary: >-
  Reuse ASTx's import-time runtime-checking policy. Tests enable validation of
  arguments, return values, and every collection item; regular usage does not
  instrument the programmatic compiler API.
"""

from astx.tools.typing import typechecked

__all__ = ["typechecked"]
