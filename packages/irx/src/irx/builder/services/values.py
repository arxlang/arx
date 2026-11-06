"""
title: Explicit SSA value-flow dependencies for expression implementations.
summary: >-
  This bundle has no symbol discovery, semantic policy, runtime selection, or
  mutable compiler state. Callbacks emit into the active function; their typed
  boundary keeps feature implementations independent of the compiler driver.
"""

from collections.abc import Callable

import astx

from llvmlite import ir
from public import private

from irx.typecheck import typechecked


@private
@typechecked
class ValueEmission:
    """
    title: >-
      Only evaluation, result publication, storage, and active builder access.
    attributes:
      builder:
        type: Callable[[], ir.IRBuilder]
      evaluate:
        type: Callable[[astx.AST], ir.Value]
      publish:
        type: Callable[[ir.Value], None]
      allocate:
        type: Callable[[str, ir.Type], ir.Value]
    """

    builder: Callable[[], ir.IRBuilder]
    evaluate: Callable[[astx.AST], ir.Value]
    publish: Callable[[ir.Value], None]
    allocate: Callable[[str, ir.Type], ir.Value]

    def __init__(
        self,
        builder: Callable[[], ir.IRBuilder],
        evaluate: Callable[[astx.AST], ir.Value],
        publish: Callable[[ir.Value], None],
        allocate: Callable[[str, ir.Type], ir.Value],
    ) -> None:
        """
        title: >-
          Bind typed expression emission without retaining a visitor owner.
        parameters:
          builder:
            type: Callable[[], ir.IRBuilder]
          evaluate:
            type: Callable[[astx.AST], ir.Value]
          publish:
            type: Callable[[ir.Value], None]
          allocate:
            type: Callable[[str, ir.Type], ir.Value]
        """
        self.builder = builder
        self.evaluate = evaluate
        self.publish = publish
        self.allocate = allocate
