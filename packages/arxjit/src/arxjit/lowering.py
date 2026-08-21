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
import struct

from typing import NamedTuple

import astx


# Neither name is re-exported at the astx top level, so both are imported from
# where they are defined: NO_SOURCE_LOCATION is astx's own default for every
# loc parameter, and AnyType is what FunctionPrototype declares its return type
# and Argument its type_ to be.
from astx.base import NO_SOURCE_LOCATION
from astx.types.base import AnyType
from plum import dispatch
from public import private

from arxjit.errors import LoweringError
from arxjit.locations import diagnostic
from arxjit.source import ExtractedSource
from arxjit.types import Signature, SigType


class _Scalar(NamedTuple):
    """
    title: Everything this stage needs to lower a value at one scalar type.
    summary: >-
      Held together in one row rather than in parallel tables so the parts
      cannot drift: a type with no literal class, or an integer type with no
      range to check against, is not expressible here.
    attributes:
      type_:
        type: type[AnyType]
        description: The astx type class, used for arguments and returns.
      literal:
        type: type[astx.Literal]
        description: The astx literal class values are built with.
      kind:
        type: str
        description: Which Python literals belong here; bool, int, or float.
      bounds:
        type: tuple[int, int] | None
        description: The representable integer range, for integer types.
      single:
        type: bool
        description: Whether the type has single rather than double precision.
    """

    type_: type[AnyType]
    literal: type[astx.Literal]
    kind: str
    bounds: tuple[int, int] | None
    single: bool


# Keyed by SigType.astx_name, which keeps arxjit.types free of any astx
# import: the type API names its astx target, and this stage is where that
# name becomes a class. Every SigType arxjit exports must appear here, which
# test_every_sig_type_is_mapped pins.
#
# A literal is built at the width its context declares, not at the width
# Python happens to give it. IRx only inserts safe widening conversions and
# rejects Int64 -> Int32 and Float64 -> Float32 outright, so emitting every
# integer as Int64 would make an i32 function fail semantic analysis on a
# literal the user wrote perfectly correctly. Python integers are also
# unbounded, so a value has to be checked against the range it is lowered
# into rather than assumed to fit.
_SCALARS: dict[str, _Scalar] = {
    "Boolean": _Scalar(astx.Boolean, astx.LiteralBoolean, "bool", None, False),
    "Float32": _Scalar(astx.Float32, astx.LiteralFloat32, "float", None, True),
    "Float64": _Scalar(
        astx.Float64, astx.LiteralFloat64, "float", None, False
    ),
    "Int32": _Scalar(
        astx.Int32, astx.LiteralInt32, "int", (-(2**31), 2**31 - 1), False
    ),
    "Int64": _Scalar(
        astx.Int64, astx.LiteralInt64, "int", (-(2**63), 2**63 - 1), False
    ),
}

# IRx reserves "main" as the program entry point and requires it to take no
# parameters and return Int32, so a decorated Python function of that name
# cannot be emitted under its own name. Kept as a literal rather than imported
# from irx.analysis.registry so that importing arxjit does not pull in the
# compiler; test_reserved_names_match_irx pins the two together.
_RESERVED_NAMES = frozenset({"main"})
_MANGLE_PREFIX = "arxjit_"


@private
def location(extracted: ExtractedSource, node: ast.AST) -> astx.SourceLocation:
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


@private
def scalar(sig_type: SigType) -> _Scalar:
    """
    title: Look up everything needed to lower values at a signature type.
    parameters:
      sig_type:
        type: SigType
    returns:
      type: _Scalar
    raises:
      LoweringError: If the type names an astx class this stage does not map.
    """
    mapped = _SCALARS.get(sig_type.astx_name)
    if mapped is None:
        raise LoweringError(
            f"cannot lower the {sig_type} type: no astx class is mapped for"
            f" {sig_type.astx_name!r}"
        )
    return mapped


@private
def astx_type(sig_type: SigType) -> AnyType:
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
    return scalar(sig_type).type_()


@private
def function_name(python_name: str) -> str:
    """
    title: Return the astx function name a Python function is emitted under.
    summary: >-
      Usually the Python name unchanged, so IR dumps and compiled symbols stay
      recognisable. A name IRx reserves for the program entry point is prefixed
      instead: a decorated function called main is an ordinary compiled
      function, but emitting it under that name would subject it to IRx's
      entry-point rules, which demand no parameters and an Int32 return.
    parameters:
      python_name:
        type: str
    returns:
      type: str
    """
    if python_name in _RESERVED_NAMES:
        return f"{_MANGLE_PREFIX}{python_name}"
    return python_name


@private
def representable(value: float, single: bool) -> bool:
    """
    title: Report whether a float value survives the target's precision.
    summary: |-
      Python floats are doubles, so only a single-precision target can
      overflow. Packing and unpacking is the exact test. Loss of precision,
      including underflow to zero, is not overflow and is accepted, because
      narrowing a float always loses precision and rejecting that would rule
      out most decimals.
      How struct reports an overflow is not portable: the same value packs to
      an infinity on some builds and raises OverflowError on others, and this
      differs between platforms at one CPython version rather than only
      between versions. Both are the same answer, so both are handled here;
      letting the exception escape would also turn a rejectable literal into a
      raw stdlib error rather than a diagnostic.
    parameters:
      value:
        type: float
      single:
        type: bool
    returns:
      type: bool
    """
    if not single:
        return True
    try:
        packed: float = struct.unpack("f", struct.pack("f", value))[0]
    except OverflowError:
        return False
    return packed == value or packed not in (float("inf"), float("-inf"))


@private
class Lowerer:
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

    @private
    def reject(self, node: ast.AST, message: str) -> LoweringError:
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
        raise self.reject(node, f"cannot lower a {kind} statement to astx yet")

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
        raise self.reject(
            node, "cannot lower a standalone expression statement to astx"
        )

    @dispatch
    def statement(self, node: ast.Return) -> astx.AST | None:
        """
        title: Lower a return statement.
        summary: >-
          The value is lowered against the signature's return type, which is
          the type the returned expression is required to have. A bare return
          leaves a function with a declared return type without a value, which
          no signature this stage can be given describes, so it is rejected
          rather than lowered to a return of nothing.
        parameters:
          node:
            type: ast.Return
        returns:
          type: astx.AST | None
        raises:
          LoweringError: If the return has no value.
        """
        if node.value is None:
            raise self.reject(
                node,
                f"cannot lower a bare return: {self.extracted.node.name!r}"
                f" declares the return type {self.signature.return_type}",
            )
        return astx.FunctionReturn(
            self.expression(node.value, self.signature.return_type),
            loc=location(self.extracted, node),
        )

    @dispatch
    def expression(self, node: ast.AST, expected: SigType) -> astx.DataType:
        """
        title: Reject any expression with no overload (fail closed).
        parameters:
          node:
            type: ast.AST
          expected:
            type: SigType
        returns:
          type: astx.DataType
        raises:
          LoweringError: Always.
        """
        kind = type(node).__name__
        raise self.reject(
            node, f"cannot lower a {kind} expression to astx yet"
        )

    @dispatch
    def expression(
        self, node: ast.Constant, expected: SigType
    ) -> astx.DataType:
        """
        title: Lower an int, float, or bool literal at its expected type.
        summary: >-
          The literal is built at the width its context declares rather than at
          Python's own, because IRx only inserts safe widening conversions: an
          Int64 literal in an i32 function is rejected outright, not narrowed.
          The value still has to belong to that type, so a literal of the wrong
          kind, or one outside the type's range, is refused here instead of
          becoming an astx node that misstates its own value.
        parameters:
          node:
            type: ast.Constant
          expected:
            type: SigType
        returns:
          type: astx.DataType
        raises:
          LoweringError: If the literal's kind or value does not fit.
        """
        target = scalar(expected)
        value = self._literal_value(node, expected, target)
        return target.literal(value, loc=location(self.extracted, node))

    def _literal_value(
        self, node: ast.Constant, expected: SigType, target: _Scalar
    ) -> bool | int | float:
        """
        title: Check a literal against its expected type and convert it.
        summary: >-
          bool is checked before int because it is a subclass of one: without
          that order True would satisfy an integer context. An integer in a
          float context is converted, which is the widening Python itself
          performs; the reverse is not, because a float has no integer value to
          preserve. Note that a negative literal never arrives here as one:
          Python parses it as a unary minus applied to a positive constant, so
          when that operator is lowered the range check has to be applied to
          the negated value, or the exact minimum of a signed type would be
          refused for exceeding its own maximum.
        parameters:
          node:
            type: ast.Constant
          expected:
            type: SigType
          target:
            type: _Scalar
        returns:
          type: bool | int | float
        raises:
          LoweringError: If the literal's kind or value does not fit.
        """
        value = node.value
        if isinstance(value, bool):
            if target.kind != "bool":
                raise self.reject(
                    node, f"cannot lower a bool literal as {expected}"
                )
            return value
        if isinstance(value, int):
            # The one kind that also belongs in a float context.
            if target.kind == "int":
                return self._in_range(node, value, expected, target)
            if target.kind == "float":
                return self._as_float(node, value, expected, target)
            raise self.reject(
                node, f"cannot lower an int literal as {expected}"
            )
        if isinstance(value, float):
            if target.kind != "float":
                raise self.reject(
                    node, f"cannot lower a float literal as {expected}"
                )
            return self._as_float(node, value, expected, target)
        name = type(value).__name__
        raise self.reject(node, f"cannot lower a {name} literal to astx")

    def _in_range(
        self,
        node: ast.Constant,
        value: int,
        expected: SigType,
        target: _Scalar,
    ) -> int:
        """
        title: Check an integer literal fits the integer type it lowers into.
        summary: >-
          Python integers are unbounded, so a value has to be checked rather
          than assumed to fit: without this one too large to represent would
          still be labelled Int64 and misstate its own value.
        parameters:
          node:
            type: ast.Constant
          value:
            type: int
          expected:
            type: SigType
          target:
            type: _Scalar
        returns:
          type: int
        raises:
          LoweringError: If the value is outside the type's range.
        """
        assert target.bounds is not None
        low, high = target.bounds
        if not low <= value <= high:
            raise self.reject(
                node, f"the literal {value!r} is out of range for {expected}"
            )
        return value

    def _as_float(
        self,
        node: ast.Constant,
        value: int | float,
        expected: SigType,
        target: _Scalar,
    ) -> float:
        """
        title: Convert a numeric literal to the float type it lowers into.
        summary: >-
          Converting an integer can overflow when it has more magnitude than a
          double holds, and a double can exceed what a single holds, so both
          steps are checked rather than left to produce an infinity.
        parameters:
          node:
            type: ast.Constant
          value:
            type: int | float
          expected:
            type: SigType
          target:
            type: _Scalar
        returns:
          type: float
        raises:
          LoweringError: If the value is outside the type's range.
        """
        try:
            converted = float(value)
        except OverflowError:
            raise self.reject(
                node, f"the literal {value!r} is out of range for {expected}"
            ) from None
        if not representable(converted, target.single):
            raise self.reject(
                node, f"the literal {value!r} is out of range for {expected}"
            )
        return converted

    def arguments(self) -> astx.Arguments:
        """
        title: Build the typed argument list from the signature.
        summary: >-
          The names come from the definition and the types from the signature,
          which is what makes an explicit signature= able to decide types
          without the function having to annotate. Validation rejects every
          shape refused here first, but lower is public and the astx argument
          list cannot express any of them, so each is refused rather than
          quietly dropped: a variadic or keyword-only parameter would vanish
          from the prototype, and a default would become a required argument.
        returns:
          type: astx.Arguments
        raises:
          LoweringError: If the argument shape or count cannot be lowered.
        """
        args = self.extracted.node.args
        self._check_shape(args)
        parameters = [*args.posonlyargs, *args.args]
        declared = len(self.signature.arg_types)
        if declared != len(parameters):
            plural = "" if declared == 1 else "s"
            raise self.reject(
                self.extracted.node,
                f"cannot lower {self.extracted.node.name!r}: the signature"
                f" declares {declared} argument type{plural} but it takes"
                f" {len(parameters)} parameters",
            )
        return astx.Arguments(
            *(
                astx.Argument(
                    name=parameter.arg,
                    type_=astx_type(sig_type),
                    loc=location(self.extracted, parameter),
                )
                for parameter, sig_type in zip(
                    parameters, self.signature.arg_types
                )
            )
        )

    def _check_shape(self, args: ast.arguments) -> None:
        """
        title: Reject an argument shape astx.Arguments cannot express.
        summary: >-
          Checked before the count, because counting the positional parameters
          of a function that also takes *args would report a number no caller
          could act on. Mirrors the shape check reconciliation applies, so the
          two stages refuse the same definitions.
        parameters:
          args:
            type: ast.arguments
        raises:
          LoweringError: >-
            If any parameter is variadic, keyword-only, or has a default.
        """
        offender = next(
            (
                node
                for node in (args.vararg, args.kwarg, *args.kwonlyargs)
                if node is not None
            ),
            None,
        )
        if offender is not None:
            raise self.reject(
                offender,
                "cannot lower a variadic or keyword-only parameter: only"
                " positional parameters are supported",
            )
        default = next(
            (
                node
                for node in (*args.defaults, *args.kw_defaults)
                if node is not None
            ),
            None,
        )
        if default is not None:
            raise self.reject(
                default,
                "cannot lower a parameter default: it would become a required"
                " argument",
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
      arxjit.reconcile, and returns the astx module IRx compiles. The module
      keeps the Python function's name so a compiled artifact is identifiable,
      and holds exactly one function definition: arxjit compiles one decorated
      function at a time. The definition itself may be emitted under a
      different name; see function_name. Both inputs are expected to have
      passed their own stage, so anything this stage cannot map is a
      LoweringError rather than a user-facing rejection.
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
    lowerer = Lowerer(extracted, signature)
    node = extracted.node
    loc = location(extracted, node)
    prototype = astx.FunctionPrototype(
        name=function_name(node.name),
        args=lowerer.arguments(),
        return_type=astx_type(signature.return_type),
        loc=loc,
    )
    module = astx.Module(name=node.name)
    module.block.append(
        astx.FunctionDef(prototype=prototype, body=lowerer.body(), loc=loc)
    )
    return module


__all__ = ["lower"]
