# mypy: disable-error-code=no-redef
"""
title: Python AST to ASTx lowering for arxjit.
summary: >-
  Fourth stage of the arxjit pipeline: turn the ast node of a validated
  function, plus the Signature reconciliation settled on, into the astx module
  IRx compiles. Dispatch is by node type via plum, matching the visitor
  convention used across the Arx packages. What is lowered so far is the
  function shell — the prototype and its typed arguments — and straight-line
  expressions: literals, parameter reads, arithmetic and unary operators, and
  single comparisons. Boolean operators and chained comparisons fail closed
  until control-flow lowering can preserve their short-circuit behavior. Where
  an expression is not lowered at a type its context declares, the type is
  inferred from the expression itself, over a scope holding the parameters.
  Local assignments and control flow follow in later stages, and until then any
  other construct fails closed with LoweringError. The decorator does not call
  this stage yet, so nothing here changes what @jit does; that wiring lands
  once the lowerer covers the whole validated subset.
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
from arxjit.types import Signature, SigType, bool_, f32, f64, i32, i64


@private
class Scalar(NamedTuple):
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
SCALARS: dict[str, Scalar] = {
    "Boolean": Scalar(astx.Boolean, astx.LiteralBoolean, "bool", None, False),
    "Float32": Scalar(astx.Float32, astx.LiteralFloat32, "float", None, True),
    "Float64": Scalar(astx.Float64, astx.LiteralFloat64, "float", None, False),
    "Int32": Scalar(
        astx.Int32, astx.LiteralInt32, "int", (-(2**31), 2**31 - 1), False
    ),
    "Int64": Scalar(
        astx.Int64, astx.LiteralInt64, "int", (-(2**63), 2**63 - 1), False
    ),
}

# The operator vocabulary astx and IRx share, taken from astx's own
# _BINARY_OP_TYPES table: an op_code outside it specializes to no node and
# reaches codegen as "not implemented yet". Validation admits two Python
# operators with no entry there, ast.FloorDiv and ast.Pow, so they are
# rejected here rather than lowered into a module that cannot be compiled;
# test_the_operator_tables_agree_with_astx pins this table to astx's.
BINARY_OPS: dict[type[ast.operator], str] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.Mod: "%",
}

# Unary is narrower still. IRx implements "!", "++" and "--" and nothing
# else, so there is no operator to lower a negation onto; ast.UAdd needs none,
# being the identity. A negation of a literal is folded instead, which is also
# the only way a negative constant can arrive: see literal_value.
UNARY_OPS: dict[type[ast.unaryop], str] = {
    ast.Not: "!",
}

# A comparison lowers to a BinaryOp carrying the comparison's op_code, not to
# astx.CompareOp: IRx's visitor for that node is _not_implemented, so a
# CompareOp would pass this stage and fail codegen, while these six op codes
# are exactly the ones irx.analysis.typing resolves to Boolean.
# test_the_comparison_tables_agree_with_irx pins the two together.
COMPARE_OPS: dict[type[ast.cmpop], str] = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
}

# Pairwise rather than ranked because Float32 can represent Int32 but cannot
# represent every Int64. Numeric entries mirror IRx's canonical promotion
# policy; the Boolean entries preserve the existing frontend inference rule
# until validation can distinguish Python's numeric bool behavior from IRx's
# strict logical Boolean type.
PROMOTIONS: dict[frozenset[str], SigType] = {
    frozenset({"Boolean"}): bool_,
    frozenset({"Boolean", "Int32"}): i32,
    frozenset({"Boolean", "Int64"}): i64,
    frozenset({"Boolean", "Float32"}): f32,
    frozenset({"Boolean", "Float64"}): f64,
    frozenset({"Int32"}): i32,
    frozenset({"Int32", "Int64"}): i64,
    frozenset({"Int32", "Float32"}): f32,
    frozenset({"Int32", "Float64"}): f64,
    frozenset({"Int64"}): i64,
    frozenset({"Int64", "Float32"}): f64,
    frozenset({"Int64", "Float64"}): f64,
    frozenset({"Float32"}): f32,
    frozenset({"Float32", "Float64"}): f64,
    frozenset({"Float64"}): f64,
}

# IRx reserves "main" as the program entry point and requires it to take no
# parameters and return Int32, so a decorated Python function of that name
# cannot be emitted under its own name. Kept as a literal rather than imported
# from irx.analysis.registry so that importing arxjit does not pull in the
# compiler; test_reserved_names_match_irx pins the two together.
RESERVED_NAMES = frozenset({"main"})
MANGLE_PREFIX = "arxjit_"


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
def scalar(sig_type: SigType) -> Scalar:
    """
    title: Look up everything needed to lower values at a signature type.
    parameters:
      sig_type:
        type: SigType
    returns:
      type: Scalar
    raises:
      LoweringError: If the type names an astx class this stage does not map.
    """
    mapped = SCALARS.get(sig_type.astx_name)
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
    if python_name in RESERVED_NAMES:
        return f"{MANGLE_PREFIX}{python_name}"
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
      scope:
        type: dict[str, SigType]
        description: The type of every name a lowered expression may read.
    """

    def __init__(
        self,
        extracted: ExtractedSource,
        signature: Signature,
    ) -> None:
        """
        title: Initialize the lowerer for one function.
        summary: >-
          The scope is seeded with the parameters, which are the only names in
          it until local assignment is lowered. It is built by zipping rather
          than after checking the two agree, so that constructing a lowerer
          raises nothing: a signature that declares the wrong number of types
          is arguments' to report, and it says so in terms of the whole
          function rather than of whichever parameter ran out first.
        parameters:
          extracted:
            type: ExtractedSource
          signature:
            type: Signature
        """
        self.extracted = extracted
        self.signature = signature
        args = extracted.node.args
        self.scope: dict[str, SigType] = {
            parameter.arg: sig_type
            for parameter, sig_type in zip(
                [*args.posonlyargs, *args.args], signature.arg_types
            )
        }

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
        return self.literal(node, node.value, expected)

    def literal(
        self, node: ast.expr, value: object, expected: SigType
    ) -> astx.DataType:
        """
        title: Build an astx literal for a value at its expected type.
        summary: >-
          Takes the value separately from the node it is located at, so that a
          negated constant can be folded through here as one literal rather
          than lowered as an operator applied to its magnitude. That is not
          only a convenience: it is what lets the exact minimum of a signed
          type through, since its magnitude is one larger than the maximum.
        parameters:
          node:
            type: ast.expr
          value:
            type: object
          expected:
            type: SigType
        returns:
          type: astx.DataType
        raises:
          LoweringError: If the value's kind or magnitude does not fit.
        """
        target = scalar(expected)
        checked = self.literal_value(node, value, expected, target)
        return target.literal(checked, loc=location(self.extracted, node))

    @dispatch
    def expression(self, node: ast.Name, expected: SigType) -> astx.DataType:
        """
        title: Lower a variable read.
        summary: >-
          Only the parameters are in scope at this stage, and their types are
          already declared on the prototype, so the reference carries no type
          of its own and IRx resolves it from the declaration. The expected
          type is therefore not applied here: unlike a literal, a variable has
          the type it was given, and reconciling it with its context is IRx's
          to do.
        parameters:
          node:
            type: ast.Name
          expected:
            type: SigType
        returns:
          type: astx.DataType
        """
        return astx.Variable(name=node.id, loc=location(self.extracted, node))

    @dispatch
    def expression(self, node: ast.BinOp, expected: SigType) -> astx.DataType:
        """
        title: Lower an arithmetic binary operation.
        summary: >-
          Both operands are lowered at the expected type, so a literal in
          either position takes the width of its context rather than Python's.
          The result type is IRx's to compute from the operands.
        parameters:
          node:
            type: ast.BinOp
          expected:
            type: SigType
        returns:
          type: astx.DataType
        raises:
          LoweringError: If the operator has no astx equivalent.
        """
        op_code = BINARY_OPS.get(type(node.op))
        if op_code is None:
            name = type(node.op).__name__
            raise self.reject(
                node,
                f"cannot lower the {name} operator: astx has no binary"
                " operator for it",
            )
        return self.binary(
            node,
            op_code,
            self.expression(node.left, expected),
            self.expression(node.right, expected),
        )

    @dispatch
    def expression(
        self, node: ast.UnaryOp, expected: SigType
    ) -> astx.DataType:
        """
        title: Lower a unary operation.
        summary: >-
          A unary plus is the identity and lowers to its operand alone. A
          negated literal is folded into one negative literal, which is the
          only form a negative constant takes in Python and the only negation
          that can be lowered at all: IRx implements no unary minus, so
          negating anything else is refused rather than emitted as a node
          codegen would later reject.
        parameters:
          node:
            type: ast.UnaryOp
          expected:
            type: SigType
        returns:
          type: astx.DataType
        raises:
          LoweringError: If the operator has no astx equivalent.
        """
        if isinstance(node.op, ast.UAdd):
            return self.expression(node.operand, expected)
        if isinstance(node.op, ast.USub):
            operand = node.operand
            if isinstance(operand, ast.Constant):
                value = operand.value
                # bool before int, as everywhere a literal's kind is read:
                # bool is a subclass of int, but negating one in Python
                # produces an integer, so folding -True would put an int
                # literal where the user wrote a bool and lose the rejection
                # literal_value would otherwise make.
                if isinstance(value, bool):
                    raise self.reject(
                        node,
                        "cannot lower a negated bool literal: negation makes"
                        " it an integer, changing the type of a value the"
                        " subset admits only as a bool",
                    )
                if isinstance(value, (int, float)):
                    return self.literal(node, -value, expected)
            raise self.reject(
                node,
                "cannot lower a negation of anything but a literal: IRx"
                " implements no unary minus",
            )
        op_code = UNARY_OPS.get(type(node.op))
        if op_code is None:
            name = type(node.op).__name__
            raise self.reject(
                node,
                f"cannot lower the {name} operator: astx has no unary"
                " operator for it",
            )
        return astx.UnaryOp(
            op_code,
            self.expression(node.operand, expected),
            loc=location(self.extracted, node),
        )

    @dispatch
    def expression(
        self, node: ast.Compare, expected: SigType
    ) -> astx.DataType:
        """
        title: Lower a single comparison.
        summary: >-
          The operands are lowered at one type wide enough for all of them
          rather than at the expected type, which is the type of the comparison
          itself and never the type being compared: at a condition the expected
          type is bool, and lowering ``a < 3`` there would ask for 3 as a bool.
          Chained comparisons are rejected until this stage can represent their
          short-circuit control flow and evaluate each middle operand once.
        parameters:
          node:
            type: ast.Compare
          expected:
            type: SigType
            description: Unused; a comparison is a bool whatever its context.
        returns:
          type: astx.DataType
        raises:
          LoweringError: >-
            If the comparison is chained or its operator has no IRx equivalent.
        """
        del expected
        if len(node.ops) > 1:
            raise self.reject(
                node,
                "cannot lower a chained comparison without short-circuit"
                " control flow",
            )

        operator = node.ops[0]
        op_code = COMPARE_OPS.get(type(operator))
        if op_code is None:
            name = type(operator).__name__
            raise self.reject(
                node,
                f"cannot lower the {name} comparison: IRx has no"
                " comparison operator for it",
            )
        comparator = node.comparators[0]
        operand_type = self.promote(
            self.infer(node.left), self.infer(comparator)
        )
        return self.binary(
            node,
            op_code,
            self.expression(node.left, operand_type),
            self.expression(comparator, operand_type),
        )

    @dispatch
    def expression(self, node: ast.BoolOp, expected: SigType) -> astx.DataType:
        """
        title: Reject and/or until short-circuit control flow is lowerable.
        parameters:
          node:
            type: ast.BoolOp
          expected:
            type: SigType
            description: Unused; the result is logical whatever its context.
        returns:
          type: astx.DataType
        raises:
          LoweringError: Always.
        """
        del expected
        operator = "and" if isinstance(node.op, ast.And) else "or"
        raise self.reject(
            node,
            f"cannot lower {operator} without short-circuit control flow",
        )

    @private
    def binary(
        self,
        node: ast.expr,
        op_code: str,
        lhs: astx.DataType,
        rhs: astx.DataType,
    ) -> astx.BinaryOp:
        """
        title: Build a binary node, refusing operands astx cannot combine.
        summary: >-
          astx requires both operands of a binary operator to carry a DataType,
          and its UnaryOp carries the generic ExprType instead, so ``not a`` in
          either position raises a bare Exception out of astx's constructor
          with no source location on it. Checked here so the user gets a
          located diagnostic naming the construct, the way every other
          unlowerable expression is reported. The real fix belongs upstream in
          astx, where giving UnaryOp the type of its operand would make these
          compose.
        parameters:
          node:
            type: ast.expr
          op_code:
            type: str
          lhs:
            type: astx.DataType
          rhs:
            type: astx.DataType
        returns:
          type: astx.BinaryOp
        raises:
          LoweringError: If either operand carries no astx DataType.
        """
        for operand in (lhs, rhs):
            if not isinstance(operand.type_, astx.DataType):
                raise self.reject(
                    node,
                    "cannot lower a unary operation as the operand of a"
                    " binary one: astx gives it no data type to combine",
                )
        return astx.BinaryOp(
            op_code, lhs, rhs, loc=location(self.extracted, node)
        )

    @private
    def promote(self, left: SigType, right: SigType) -> SigType:
        """
        title: Pick the type that can represent both of two operand types.
        summary: >-
          Promotion is pairwise because a single ordering cannot describe the
          Int64/Float32 pair: IRx promotes it to Float64, while Int32/Float32
          remains Float32.
        parameters:
          left:
            type: SigType
          right:
            type: SigType
        returns:
          type: SigType
        """
        return PROMOTIONS[frozenset({left.astx_name, right.astx_name})]

    @dispatch
    def infer(self, node: ast.AST) -> SigType:
        """
        title: Refuse to infer a type for a node with no overload.
        summary: >-
          Fails closed for the same reason the lowering dispatch does: this
          runs on a validated function, so a node reaching here means inference
          and the subset disagree, which must surface rather than resolve to
          some default type the expression does not have.
        parameters:
          node:
            type: ast.AST
        returns:
          type: SigType
        raises:
          LoweringError: Always.
        """
        kind = type(node).__name__
        raise self.reject(
            node, f"cannot infer the type of a {kind} expression"
        )

    @dispatch
    def infer(self, node: ast.Constant) -> SigType:
        """
        title: Infer the type of a literal from its Python kind.
        summary: >-
          The widest type of each kind, because a literal standing on its own
          has only Python's own notion of its type to go on: Python integers
          are unbounded and its floats are doubles. A narrower type is still
          reached wherever the context declares one, which is what the expected
          type passed to lowering is for.
        parameters:
          node:
            type: ast.Constant
        returns:
          type: SigType
        raises:
          LoweringError: If the literal is of no kind the subset admits.
        """
        value = node.value
        if isinstance(value, bool):
            return bool_
        if isinstance(value, int):
            return i64
        if isinstance(value, float):
            return f64
        name = type(value).__name__
        raise self.reject(node, f"cannot infer the type of a {name} literal")

    @dispatch
    def infer(self, node: ast.Name) -> SigType:
        """
        title: Infer the type of a name from the scope it was declared in.
        parameters:
          node:
            type: ast.Name
        returns:
          type: SigType
        raises:
          LoweringError: If the name is not in scope.
        """
        sig_type = self.scope.get(node.id)
        if sig_type is None:
            raise self.reject(
                node,
                f"cannot infer the type of {node.id!r}: it is not a parameter"
                " of this function",
            )
        return sig_type

    @dispatch
    def infer(self, node: ast.BinOp) -> SigType:
        """
        title: Infer an arithmetic result from its operator and operands.
        summary: >-
          True division produces a float even when both operands are integers.
          Other arithmetic operators use the same pairwise numeric promotion
          policy as IRx.
        parameters:
          node:
            type: ast.BinOp
        returns:
          type: SigType
        """
        inferred = self.promote(self.infer(node.left), self.infer(node.right))
        if isinstance(node.op, ast.Div) and inferred in (bool_, i32, i64):
            return f64
        return inferred

    @dispatch
    def infer(self, node: ast.UnaryOp) -> SigType:
        """
        title: Infer the type of a unary operation.
        summary: >-
          Only ``not`` changes the type of what it is applied to; the other
          operators the subset admits leave it as it was.
        parameters:
          node:
            type: ast.UnaryOp
        returns:
          type: SigType
        """
        if isinstance(node.op, ast.Not):
            return bool_
        return self.infer(node.operand)

    @dispatch
    def infer(self, node: ast.Compare) -> SigType:
        """
        title: Infer the type of a comparison.
        parameters:
          node:
            type: ast.Compare
        returns:
          type: SigType
        """
        return bool_

    @dispatch
    def infer(self, node: ast.BoolOp) -> SigType:
        """
        title: Infer the type of an and/or expression.
        summary: >-
          Logical once lowered, whatever its operands were, which is what makes
          it usable as a condition.
        parameters:
          node:
            type: ast.BoolOp
        returns:
          type: SigType
        """
        return bool_

    @private
    def literal_value(
        self,
        node: ast.expr,
        value: object,
        expected: SigType,
        target: Scalar,
    ) -> bool | int | float:
        """
        title: Check a literal against its expected type and convert it.
        summary: >-
          bool is checked before int because it is a subclass of one: without
          that order True would satisfy an integer context. An integer in a
          float context is converted, which is the widening Python itself
          performs; the reverse is not, because a float has no integer value to
          preserve. The value is passed in rather than read off the node so a
          negated constant is checked as the negative number it is, which is
          what admits the exact minimum of a signed type: its magnitude alone
          is one larger than that type's maximum.
        parameters:
          node:
            type: ast.expr
          value:
            type: object
          expected:
            type: SigType
          target:
            type: Scalar
        returns:
          type: bool | int | float
        raises:
          LoweringError: If the literal's kind or value does not fit.
        """
        if isinstance(value, bool):
            if target.kind != "bool":
                raise self.reject(
                    node, f"cannot lower a bool literal as {expected}"
                )
            return value
        if isinstance(value, int):
            # The one kind that also belongs in a float context.
            if target.kind == "int":
                return self.in_range(node, value, expected, target)
            if target.kind == "float":
                return self.as_float(node, value, expected, target)
            raise self.reject(
                node, f"cannot lower an int literal as {expected}"
            )
        if isinstance(value, float):
            if target.kind != "float":
                raise self.reject(
                    node, f"cannot lower a float literal as {expected}"
                )
            return self.as_float(node, value, expected, target)
        name = type(value).__name__
        raise self.reject(node, f"cannot lower a {name} literal to astx")

    @private
    def in_range(
        self,
        node: ast.expr,
        value: int,
        expected: SigType,
        target: Scalar,
    ) -> int:
        """
        title: Check an integer literal fits the integer type it lowers into.
        summary: >-
          Python integers are unbounded, so a value has to be checked rather
          than assumed to fit: without this one too large to represent would
          still be labelled Int64 and misstate its own value.
        parameters:
          node:
            type: ast.expr
          value:
            type: int
          expected:
            type: SigType
          target:
            type: Scalar
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

    @private
    def as_float(
        self,
        node: ast.expr,
        value: int | float,
        expected: SigType,
        target: Scalar,
    ) -> float:
        """
        title: Convert a numeric literal to the float type it lowers into.
        summary: >-
          Converting an integer can overflow when it has more magnitude than a
          double holds, and a double can exceed what a single holds, so both
          steps are checked rather than left to produce an infinity.
        parameters:
          node:
            type: ast.expr
          value:
            type: int | float
          expected:
            type: SigType
          target:
            type: Scalar
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
        self.check_shape(args)
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

    @private
    def check_shape(self, args: ast.arguments) -> None:
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
