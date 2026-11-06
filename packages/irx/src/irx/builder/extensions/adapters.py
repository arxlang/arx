"""
title: Bridge existing LLVM services to the narrow call-plan interface.
summary: >-
  This adapter contains no operation selection or algorithms. It is constructed
  by the concrete visitor, never imported by semantic analysis or
  contributions.
"""

from collections.abc import Callable

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import ResolvedClassConstruction
from irx.builder.diagnostics import require_lowered_value
from irx.builder.lowering.contracts import TrackNativeHandleCallback
from irx.builder.services.conversions import NumericEmission
from irx.builder.services.representations import resolved_type
from irx.builder.services.values import ValueEmission
from irx.builder.state import CleanupAction
from irx.builder.strings import StringEmission
from irx.typecheck import typechecked


@private
@typechecked
class CallLoweringBindings:
    """
    title: Explicit per-compilation dependency wiring.
    attributes:
      values:
        type: ValueEmission
      numeric:
        type: NumericEmission
      strings:
        type: StringEmission
      pin_value:
        type: Callable[[astx.AST, ir.Value], None]
      require_value:
        type: Callable[[astx.AST, ir.Value], None]
      symbol:
        type: Callable[[str, str], ir.Function]
      native:
        type: Callable[[astx.AST, ir.Function, list[ir.Value]], ir.Value]
      track_value:
        type: TrackNativeHandleCallback
      release_value:
        type: Callable[[CleanupAction], None]
      owned:
        type: Callable[[astx.AST, ir.Value], None]
      construct_value:
        type: Callable[[astx.AST, ResolvedClassConstruction], None]
      peek:
        type: Callable[[], ir.Value | None]
    """

    values: ValueEmission
    numeric: NumericEmission
    strings: StringEmission
    pin_value: Callable[[astx.AST, ir.Value], None]
    require_value: Callable[[astx.AST, ir.Value], None]
    symbol: Callable[[str, str], ir.Function]
    native: Callable[[astx.AST, ir.Function, list[ir.Value]], ir.Value]
    track_value: TrackNativeHandleCallback
    release_value: Callable[[CleanupAction], None]
    owned: Callable[[astx.AST, ir.Value], None]
    construct_value: Callable[[astx.AST, ResolvedClassConstruction], None]
    peek: Callable[[], ir.Value | None]

    def __init__(
        self,
        values: ValueEmission,
        numeric: NumericEmission,
        strings: StringEmission,
        pin: Callable[[astx.AST, ir.Value], None],
        require: Callable[[astx.AST, ir.Value], None],
        symbol: Callable[[str, str], ir.Function],
        native: Callable[[astx.AST, ir.Function, list[ir.Value]], ir.Value],
        track: TrackNativeHandleCallback,
        release: Callable[[CleanupAction], None],
        owned: Callable[[astx.AST, ir.Value], None],
        construct: Callable[[astx.AST, ResolvedClassConstruction], None],
        peek: Callable[[], ir.Value | None],
    ) -> None:
        """
        title: Bind only value, class-reference, and checked native services.
        parameters:
          values:
            type: ValueEmission
          numeric:
            type: NumericEmission
          strings:
            type: StringEmission
          pin:
            type: Callable[[astx.AST, ir.Value], None]
          require:
            type: Callable[[astx.AST, ir.Value], None]
          symbol:
            type: Callable[[str, str], ir.Function]
          native:
            type: Callable[[astx.AST, ir.Function, list[ir.Value]], ir.Value]
          track:
            type: TrackNativeHandleCallback
          release:
            type: Callable[[CleanupAction], None]
          owned:
            type: Callable[[astx.AST, ir.Value], None]
          construct:
            type: Callable[[astx.AST, ResolvedClassConstruction], None]
          peek:
            type: Callable[[], ir.Value | None]
        """
        self.values = values
        self.numeric = numeric
        self.strings = strings
        self.pin_value = pin
        self.require_value = require
        self.symbol = symbol
        self.native = native
        self.track_value = track
        self.release_value = release
        self.owned = owned
        self.construct_value = construct
        self.peek = peek

    @property
    def builder(self) -> ir.IRBuilder:
        """
        title: Return the active instruction builder.
        returns:
          type: ir.IRBuilder
        """
        return self.values.builder()

    def text(self, value: str) -> ir.Value:
        """
        title: Reuse module-local string interning.
        parameters:
          value:
            type: str
        returns:
          type: ir.Value
        """
        return self.strings.constant(value, name_hint="table_io")

    def evaluate(self, node: astx.AST) -> ir.Value:
        """
        title: Evaluate and pin one argument without leaking stack entries.
        parameters:
          node:
            type: astx.AST
        returns:
          type: ir.Value
        """
        value = self.values.evaluate(node)
        self.pin_value(node, value)
        return value

    def handle(self, node: astx.AST, value: ir.Value, index: int) -> ir.Value:
        """
        title: Load a resolved opaque-handle field after a lifetime check.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
          index:
            type: int
        returns:
          type: ir.Value
        """
        self.require_value(node, value)
        integer = ir.IntType(32)
        return self.builder.load(
            self.builder.gep(
                value, [ir.Constant(integer, 0), ir.Constant(integer, index)]
            )
        )

    def convert(
        self, node: astx.AST, value: ir.Value, target: astx.DataType
    ) -> ir.Value:
        """
        title: Reuse conversion emission with the operand's resolved type.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
          target:
            type: astx.DataType
        returns:
          type: ir.Value
        """
        return self.numeric.cast_scalar(
            value,
            source_type=resolved_type(node),
            target_type=target,
        )

    def invoke(
        self, node: astx.AST, feature: str, name: str, args: list[ir.Value]
    ) -> ir.Value:
        """
        title: >-
          Reuse checked status/output ABI and registered runtime activation.
        parameters:
          node:
            type: astx.AST
          feature:
            type: str
          name:
            type: str
          args:
            type: list[ir.Value]
        returns:
          type: ir.Value
        """
        return self.native(node, self.symbol(feature, name), args)

    def track(
        self, node: astx.AST, feature: str, destroy: str, value: ir.Value
    ) -> CleanupAction:
        """
        title: Register existing native cleanup behavior.
        parameters:
          node:
            type: astx.AST
          feature:
            type: str
          destroy:
            type: str
          value:
            type: ir.Value
        returns:
          type: CleanupAction
        """
        return self.track_value(node, feature, destroy, value)

    def release(self, cleanup: CleanupAction) -> None:
        """
        title: Discharge a native temporary on the success path.
        parameters:
          cleanup:
            type: CleanupAction
        """
        self.release_value(cleanup)

    def publish(self, node: astx.AST, value: ir.Value) -> None:
        """
        title: Produce one owned Arrow result.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
        """
        self.owned(node, value)
        self.values.publish(value)

    def construct(
        self, node: astx.AST, resolution: ResolvedClassConstruction
    ) -> ir.Value:
        """
        title: Produce one resolved class construction and return its value.
        parameters:
          node:
            type: astx.AST
          resolution:
            type: ResolvedClassConstruction
        returns:
          type: ir.Value
        """
        self.construct_value(node, resolution)
        return require_lowered_value(
            self.peek(),
            node=node,
            context="resolved class construction",
        )
