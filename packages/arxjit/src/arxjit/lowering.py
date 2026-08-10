# mypy: disable-error-code=no-redef
"""
title: Python AST to ASTx lowering for arxjit.
summary: >-
  Fourth stage of the arxjit pipeline: turn the ast node of a validated
  function, plus the Signature reconciliation settled on, into the astx module
  IRx compiles. Dispatch is by node type via plum, matching the visitor
  convention used across the Arx packages. This first version lowers the
  function shell — the prototype, its typed arguments, and a body of literal
  returns; variables, arithmetic, and control flow follow in later stages, and
  until then any other construct fails closed with LoweringError. The decorator
  does not call this stage yet, so nothing here changes what @jit does; that
  wiring lands once the lowerer covers the whole validated subset.
"""

from __future__ import annotations

import ast

import astx


# Neither name is re-exported at the astx top level, so both are imported from
# where they are defined: NO_SOURCE_LOCATION is astx's own default for every
# loc parameter, and AnyType is what FunctionPrototype declares its return type
# and Argument its type_ to be.
from astx.base import NO_SOURCE_LOCATION
from astx.types.base import AnyType
from plum import dispatch

from arxjit.errors import LoweringError
from arxjit.locations import diagnostic
from arxjit.source import ExtractedSource
from arxjit.types import Signature, SigType

# Bound by SigType.astx_name, which keeps arxjit.types free of any astx
# import: the type API names its astx target, and this stage is where that
# name becomes a class. Every SigType arxjit exports must appear here, which
# test_every_sig_type_has_an_astx_class pins.
_ASTX_TYPES: dict[str, type[AnyType]] = {
    "Boolean": astx.Boolean,
    "Float32": astx.Float32,
    "Float64": astx.Float64,
    "Int32": astx.Int32,
    "Int64": astx.Int64,
}

# Ordered, and checked in order, because bool is a subclass of int in Python:
# a True literal matches int too, and would lower to an integer without this.
# Widths are the Python defaults rather than the signature's type; see the
# ast.Constant overload for why the declared type deliberately does not drive
# this.
_LITERAL_TYPES: tuple[tuple[type, type[astx.Literal]], ...] = (
    (bool, astx.LiteralBoolean),
    (int, astx.LiteralInt64),
    (float, astx.LiteralFloat64),
)


def _location(
    extracted: ExtractedSource, node: ast.AST
) -> astx.SourceLocation:
    """
    title: Convert an ast node's position into an astx source location.
    summary: >-
      Reuses the diagnostic builder so astx nodes carry exactly the positions
      arxjit reports in its own diagnostics, one-based character columns
      included, rather than raw byte offsets. A node without a position, which
      only the synthesized ones have, maps to astx's own no-location value.
    parameters:
      extracted:
        type: ExtractedSource
      node:
        type: ast.AST
    returns:
      type: astx.SourceLocation
    """
    located = diagnostic(extracted, node, "")
    if located.line is None or located.column is None:
        return NO_SOURCE_LOCATION
    return astx.SourceLocation(line=located.line, col=located.column)


def _astx_type(sig_type: SigType) -> AnyType:
    """
    title: Instantiate the astx type a signature type lowers to.
    parameters:
      sig_type:
        type: SigType
    returns:
      type: AnyType
    raises:
      LoweringError: If the type names an astx class this stage does not map.
    """
    astx_class = _ASTX_TYPES.get(sig_type.astx_name)
    if astx_class is None:
        raise LoweringError(
            f"cannot lower the {sig_type} type: no astx class is mapped for"
            f" {sig_type.astx_name!r}"
        )
    return astx_class()


class _Lowerer:
    """
    title: Build the astx nodes for one validated function.
    summary: >-
      Dispatches by node type via plum: each lowerable construct has its own
      overload, and the ast.AST overload is the fail-closed default. Failing
      closed matters more here than in validation, because this stage runs on a
      function already accepted: a node with no overload means the subset and
      the lowerer disagree, which must surface rather than silently produce a
      module missing part of the function.
    attributes:
      extracted:
        description: The extracted source being lowered.
      signature:
        description: The signature reconciliation settled on.
    """

    def __init__(
        self,
        extracted: ExtractedSource,
        signature: Signature,
    ) -> None:
        """
        title: Initialize the lowerer for one function.
        parameters:
          extracted:
            type: ExtractedSource
          signature:
            type: Signature
        """
        self.extracted = extracted
        self.signature = signature

    def _reject(self, node: ast.AST, message: str) -> LoweringError:
        """
        title: Build a LoweringError located at an ast node.
        summary: >-
          Returned rather than raised so callers raise at the point of failure
          and the traceback names the overload that could not proceed.
        parameters:
          node:
            type: ast.AST
          message:
            type: str
        returns:
          type: LoweringError
        """
        return LoweringError(
            message, diagnostics=[diagnostic(self.extracted, node, message)]
        )

    @dispatch
    def statement(self, node: ast.AST) -> astx.AST | None:
        """
        title: Reject any statement with no overload (fail closed).
        parameters:
          node:
            type: ast.AST
        returns:
          type: astx.AST | None
        raises:
          LoweringError: Always.
        """
        kind = type(node).__name__
        raise self._reject(
            node, f"cannot lower a {kind} statement to astx yet"
        )

    @dispatch
    def statement(self, node: ast.Pass) -> astx.AST | None:
        """
        title: Lower a pass statement to nothing.
        summary: >-
          It has no effect to compile, so it contributes no node rather than an
          empty one.
        parameters:
          node:
            type: ast.Pass
        returns:
          type: astx.AST | None
        """
        return None

    @dispatch
    def statement(self, node: ast.Expr) -> astx.AST | None:
        """
        title: Lower a docstring or no-op string statement to nothing.
        summary: >-
          Validation admits a bare string statement and nothing else in this
          position, so the string is discarded and anything else is a
          disagreement between the two stages.
        parameters:
          node:
            type: ast.Expr
        returns:
          type: astx.AST | None
        """
        if isinstance(node.value, ast.Constant) and isinstance(
            node.value.value, str
        ):
            return None
        raise self._reject(
            node, "cannot lower a standalone expression statement to astx"
        )

    @dispatch
    def statement(self, node: ast.Return) -> astx.AST | None:
        """
        title: Lower a return statement.
        summary: >-
          A bare return leaves a function with a declared return type without a
          value, which no signature this stage can be given describes, so it is
          rejected rather than lowered to a return of nothing.
        parameters:
          node:
            type: ast.Return
        returns:
          type: astx.AST | None
        raises:
          LoweringError: If the return has no value.
        """
        if node.value is None:
            raise self._reject(
                node,
                f"cannot lower a bare return: {self.extracted.node.name!r}"
                f" declares the return type {self.signature.return_type}",
            )
        return astx.FunctionReturn(
            self.expression(node.value),
            loc=_location(self.extracted, node),
        )

    @dispatch
    def expression(self, node: ast.AST) -> astx.DataType:
        """
        title: Reject any expression with no overload (fail closed).
        parameters:
          node:
            type: ast.AST
        returns:
          type: astx.DataType
        raises:
          LoweringError: Always.
        """
        kind = type(node).__name__
        raise self._reject(
            node, f"cannot lower a {kind} expression to astx yet"
        )

    @dispatch
    def expression(self, node: ast.Constant) -> astx.DataType:
        """
        title: Lower an int, float, or bool literal.
        summary: >-
          The literal's own Python type picks the astx class, not the declared
          signature type: IRx owns semantic analysis, so a literal narrower or
          wider than its context is its business to check and cast, and
          lowering states only what the source says. The practical consequence
          is that a literal is always 64-bit, since Python has no narrower
          numeric literal, and an i32 or f32 function relies on IRx to convert.
        parameters:
          node:
            type: ast.Constant
        returns:
          type: astx.DataType
        raises:
          LoweringError: If the literal is not an int, float, or bool.
        """
        for python_type, literal_class in _LITERAL_TYPES:
            if isinstance(node.value, python_type):
                return literal_class(
                    node.value, loc=_location(self.extracted, node)
                )
        kind = type(node.value).__name__
        raise self._reject(node, f"cannot lower a {kind} literal to astx")

    def arguments(self) -> astx.Arguments:
        """
        title: Build the typed argument list from the signature.
        summary: >-
          The names come from the definition and the types from the signature,
          which is what makes an explicit signature= able to decide types
          without the function having to annotate. Reconciliation has already
          checked the two agree in count, but lower is public and zip would
          silently drop the excess on either side, so the count is confirmed
          rather than assumed: a module missing an argument would compile to a
          calling convention no caller could satisfy.
        returns:
          type: astx.Arguments
        raises:
          LoweringError: If the signature and the definition disagree in count.
        """
        parameters = [
            *self.extracted.node.args.posonlyargs,
            *self.extracted.node.args.args,
        ]
        declared = len(self.signature.arg_types)
        if declared != len(parameters):
            plural = "" if declared == 1 else "s"
            raise self._reject(
                self.extracted.node,
                f"cannot lower {self.extracted.node.name!r}: the signature"
                f" declares {declared} argument type{plural} but it takes"
                f" {len(parameters)} parameters",
            )
        return astx.Arguments(
            *(
                astx.Argument(
                    name=parameter.arg,
                    type_=_astx_type(sig_type),
                    loc=_location(self.extracted, parameter),
                )
                for parameter, sig_type in zip(
                    parameters, self.signature.arg_types
                )
            )
        )

    def body(self) -> astx.Block:
        """
        title: Lower the function body into an astx block.
        summary: >-
          Statements that compile to nothing, a docstring or a pass, are
          dropped rather than represented, so the block holds only what IRx has
          to translate.
        returns:
          type: astx.Block
        """
        block = astx.Block()
        for node in self.extracted.node.body:
            lowered = self.statement(node)
            if lowered is not None:
                block.append(lowered)
        return block


def lower(extracted: ExtractedSource, signature: Signature) -> astx.Module:
    """
    title: Lower a validated function into a single-function astx module.
    summary: >-
      Takes the function ast from arxjit.source and the Signature from
      arxjit.reconcile, and returns the astx module IRx compiles. The module is
      named after the function so a compiled artifact is identifiable, and
      holds exactly one function definition: arxjit compiles one decorated
      function at a time. Both inputs are expected to have passed their own
      stage; anything this stage cannot map is a LoweringError rather than a
      user-facing rejection.
    parameters:
      extracted:
        type: ExtractedSource
        description: A function that has already passed validation.
      signature:
        type: Signature
        description: The signature resolve_signature settled on.
    returns:
      type: astx.Module
    raises:
      LoweringError: If any part of the function has no astx mapping yet.
    """
    lowerer = _Lowerer(extracted, signature)
    node = extracted.node
    loc = _location(extracted, node)
    prototype = astx.FunctionPrototype(
        name=node.name,
        args=lowerer.arguments(),
        return_type=_astx_type(signature.return_type),
        loc=loc,
    )
    module = astx.Module(name=node.name)
    module.block.append(
        astx.FunctionDef(prototype=prototype, body=lowerer.body(), loc=loc)
    )
    return module


__all__ = ["lower"]
