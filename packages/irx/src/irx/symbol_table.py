"""
title: Symbol Table classes.
"""

from typing import TypeAlias

from astx.symbol_table import SymbolTable as AstxSymbolTable
from public import public

from irx.typecheck import typechecked

SymbolTable: TypeAlias = AstxSymbolTable

__all__ = ["RegisterTable", "SymbolTable"]


@public
@typechecked
class RegisterTable:
    """
    title: Track named registers in nested scopes.
    attributes:
      stack:
        type: list[int]
    """

    # Each level in the stack represents a context.
    stack: list[int]

    def __init__(self) -> None:
        """
        title: Initialize RegisterTable.
        """
        self.stack: list[int] = []

    def append(self) -> None:
        """
        title: Append.
        """
        self.stack.append(0)

    def increase(self, count: int = 1) -> int:
        """
        title: Increase.
        parameters:
          count:
            type: int
        returns:
          type: int
        """
        self.stack[-1] += count
        return self.stack[-1]

    @property
    def last(self) -> int:
        """
        title: Last.
        returns:
          type: int
        """
        return self.stack[-1]

    def pop(self) -> None:
        """
        title: Pop.
        """
        self.stack.pop()

    def redefine(self, count: int) -> None:
        """
        title: Redefine.
        parameters:
          count:
            type: int
        """
        self.stack[-1] = count

    def reset(self) -> None:
        """
        title: Reset.
        """
        self.stack[-1] = 0
