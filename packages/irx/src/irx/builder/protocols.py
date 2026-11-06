"""
title: Minimal LLVM representation contract for native symbol factories.
"""

from __future__ import annotations

from typing import Protocol

from irx.builder.types import VariablesLLVM


class VisitorProtocol(Protocol):
    """
    title: >-
      Supply LLVM types and the destination module to runtime declarations.
    summary: Native factories cannot access analysis or lowering families.
    attributes:
      _llvm:
        type: VariablesLLVM
    """

    _llvm: VariablesLLVM
