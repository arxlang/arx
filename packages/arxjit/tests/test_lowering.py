"""
title: Tests for Python AST to ASTx lowering.
"""

import ast
import ctypes

from typing import Any, Callable

import arxjit
import astx
import pytest

from arxjit import lowering
from arxjit.errors import LoweringError
from arxjit.lowering import (
    MANGLE_PREFIX,
    RESERVED_NAMES,
    SCALARS,
    location,
    lower,
)
from arxjit.source import ExtractedSource, extract_source
from arxjit.types import Signature, SigType, bool_, f32, f64, i32, i64
from astx.base import NO_SOURCE_LOCATION
from astx.binary_op import _BINARY_OP_TYPES
from irx.analysis.api import analyze
from irx.analysis.registry import MAIN_FUNCTION_NAME
from irx.analysis.types import common_numeric_type
from irx.analysis.typing import binary_result_type
from irx.builder import Builder
from llvmlite import binding as llvm

PyFunc = Callable[..., Any]


def _lower(fn: PyFunc, signature: Signature) -> astx.FunctionDef:
    """
    title: Lower a function and return its single definition (test helper).
    parameters:
      fn:
        type: PyFunc
      signature:
        type: Signature
    returns:
      type: astx.FunctionDef
    """
    module = lower(extract_source(fn), signature)
    definition = module.block[0]
    assert isinstance(definition, astx.FunctionDef)
    return definition


def _from_source(source: str, signature: Signature) -> astx.FunctionDef:
    """
    title: Lower a hand-built function definition (test helper).
    summary: >-
      lower is public and its stages fail closed on nodes validation would have
      rejected first, so those paths are reached by building the source
      directly rather than through a decorated function.
    parameters:
      source:
        type: str
      signature:
        type: Signature
    returns:
      type: astx.FunctionDef
    """
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    extracted = ExtractedSource(
        filename="<test>", source=source, lineno=1, node=node
    )
    definition = lower(extracted, signature).block[0]
    assert isinstance(definition, astx.FunctionDef)
    return definition


def _module_from_source(source: str, signature: Signature) -> astx.Module:
    """
    title: Lower hand-built source and keep the module (test helper).
    summary: >-
      analyze takes the whole module rather than the definition alone, so a
      test that checks an emitted node is one IRx accepts needs both.
    parameters:
      source:
        type: str
      signature:
        type: Signature
    returns:
      type: astx.Module
    """
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    extracted = ExtractedSource(
        filename="<test>", source=source, lineno=1, node=node
    )
    return lower(extracted, signature)


def _returned(module: astx.Module) -> astx.DataType:
    """
    title: Return the value of a single-statement function's return.
    parameters:
      module:
        type: astx.Module
    returns:
      type: astx.DataType
    """
    definition = module.block[0]
    assert isinstance(definition, astx.FunctionDef)
    (returned,) = definition.body.nodes
    assert isinstance(returned, astx.FunctionReturn)
    return returned.value


def execute_bool(module: astx.Module, symbol: str) -> bool:
    """
    title: Translate and JIT-run a no-argument Boolean function.
    parameters:
      module:
        type: astx.Module
      symbol:
        type: str
    returns:
      type: bool
    """
    llvm_module = llvm.parse_assembly(Builder().translate(module))
    llvm_module.verify()
    target_machine = llvm.Target.from_default_triple().create_target_machine()
    engine = llvm.create_mcjit_compiler(
        llvm.parse_assembly(""), target_machine
    )
    engine.add_module(llvm_module)
    engine.finalize_object()
    address = engine.get_function_address(symbol)
    assert address != 0
    function = ctypes.CFUNCTYPE(ctypes.c_bool)(address)
    return bool(function())


def execute_bool_f32(module: astx.Module, symbol: str, value: float) -> bool:
    """
    title: Translate and JIT-run a one-Float32-argument Boolean function.
    parameters:
      module:
        type: astx.Module
      symbol:
        type: str
      value:
        type: float
    returns:
      type: bool
    """
    llvm_module = llvm.parse_assembly(Builder().translate(module))
    llvm_module.verify()
    target_machine = llvm.Target.from_default_triple().create_target_machine()
    engine = llvm.create_mcjit_compiler(
        llvm.parse_assembly(""), target_machine
    )
    engine.add_module(llvm_module)
    engine.finalize_object()
    address = engine.get_function_address(symbol)
    assert address != 0
    function = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_float)(address)
    return bool(function(value))


def test_literal_return_lowers_to_a_single_function_module() -> None:
    """
    title: A constant-returning function becomes a one-function astx module.
    """

    def answer() -> int:
        """
        title: Return a constant.
        returns:
          type: int
        """
        return 42

    module = lower(extract_source(answer), i64())
    assert isinstance(module, astx.Module)
    assert module.name == "answer"
    assert len(module.block) == 1

    definition = module.block[0]
    assert isinstance(definition, astx.FunctionDef)
    assert definition.prototype.name == "answer"
    assert isinstance(definition.prototype.return_type, astx.Int64)
    assert len(definition.prototype.args.nodes) == 0

    (returned,) = definition.body.nodes
    assert isinstance(returned, astx.FunctionReturn)
    assert isinstance(returned.value, astx.LiteralInt64)
    assert returned.value.value == 42


def test_arguments_take_names_from_the_def_and_types_from_the_signature() -> (
    None
):
    """
    title: Argument names come from the definition, types from the signature.
    summary: >-
      The signature here is deliberately not the one the annotations would
      derive: i32 has no Python annotation that produces it, so seeing i32 on
      the lowered arguments proves the signature drove the types.
    """

    def add(a: int, b: int) -> int:
        """
        title: Add two numbers.
        parameters:
          a:
            type: int
          b:
            type: int
        returns:
          type: int
        """
        return 0

    definition = _lower(add, i32(i32, i32))
    names = [argument.name for argument in definition.prototype.args.nodes]
    assert names == ["a", "b"]
    for argument in definition.prototype.args.nodes:
        assert isinstance(argument.type_, astx.Int32)
    assert isinstance(definition.prototype.return_type, astx.Int32)


def test_positional_only_parameters_are_lowered() -> None:
    """
    title: Positional-only parameters become ordinary astx arguments.
    summary: >-
      They are positional arguments to a compiled function, and reconciliation
      already counts them, so lowering must not drop them.
    """
    source = "def sample(a, /, b):\n    return 0\n"
    definition = _from_source(source, i64(i64, f64))
    names = [argument.name for argument in definition.prototype.args.nodes]
    assert names == ["a", "b"]
    assert isinstance(definition.prototype.args.nodes[0].type_, astx.Int64)
    assert isinstance(definition.prototype.args.nodes[1].type_, astx.Float64)


@pytest.mark.parametrize(
    ("literal", "sig_type", "expected", "value"),
    [
        ("1", i32, astx.LiteralInt32, 1),
        ("1", i64, astx.LiteralInt64, 1),
        ("1", f32, astx.LiteralFloat32, 1.0),
        ("1", f64, astx.LiteralFloat64, 1.0),
        ("1.5", f32, astx.LiteralFloat32, 1.5),
        ("1.5", f64, astx.LiteralFloat64, 1.5),
        ("True", bool_, astx.LiteralBoolean, True),
        ("False", bool_, astx.LiteralBoolean, False),
    ],
)
def test_a_literal_is_built_at_its_expected_type(
    literal: str,
    sig_type: SigType,
    expected: type[astx.Literal],
    value: object,
) -> None:
    """
    title: A literal takes the width of the type its context declares.
    summary: >-
      IRx only inserts safe widening conversions, so a literal emitted at
      Python's own width would make an i32 or f32 function fail semantic
      analysis. An integer in a float context is converted, which is the
      widening Python itself performs.
    parameters:
      literal:
        type: str
      sig_type:
        type: SigType
      expected:
        type: type[astx.Literal]
      value:
        type: object
    """
    source = f"def sample():\n    return {literal}\n"
    definition = _from_source(source, sig_type())
    (returned,) = definition.body.nodes
    assert isinstance(returned, astx.FunctionReturn)
    assert isinstance(returned.value, expected)
    assert returned.value.value == value


@pytest.mark.parametrize("sig_type", [bool_, f32, f64, i32, i64])
def test_a_lowered_function_passes_irx_semantic_analysis(
    sig_type: SigType,
) -> None:
    """
    title: Every exported scalar type survives IRx analysis end to end.
    summary: >-
      The cross-stage check that pins lowering to what IRx actually accepts
      rather than to what this package believes about it. Both the entry-point
      collision and the literal width policy were found by running analysis on
      a lowered module, and neither is observable from the astx tree alone.
    parameters:
      sig_type:
        type: SigType
    """
    literal = "True" if sig_type is bool_ else "1"
    source = f"def sample():\n    return {literal}\n"
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    module = lower(
        ExtractedSource(filename="<test>", source=source, lineno=1, node=node),
        sig_type(),
    )
    analyze(module)


def test_a_function_named_main_does_not_become_the_irx_entry_point() -> None:
    """
    title: A decorated function called main is emitted under another name.
    summary: >-
      IRx reserves main for the program entry point and requires it to take no
      parameters and return Int32, so lowering it under its own name makes an
      otherwise valid function fail analysis. Analysis is run here because the
      rule being avoided is IRx's, not this package's.
    """
    source = "def main():\n    return 1\n"
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    module = lower(
        ExtractedSource(filename="<test>", source=source, lineno=1, node=node),
        i64(),
    )
    definition = module.block[0]
    assert isinstance(definition, astx.FunctionDef)
    assert definition.prototype.name == f"{MANGLE_PREFIX}main"
    assert module.name == "main"
    analyze(module)


def test_an_ordinary_name_is_not_mangled() -> None:
    """
    title: Only a reserved name is renamed.
    summary: >-
      The control for the test above: mangling every function would make IR
      dumps and compiled symbols harder to recognise for no benefit.
    """
    definition = _from_source("def sample():\n    return 1\n", i64())
    assert definition.prototype.name == "sample"


def test_reserved_names_match_irx() -> None:
    """
    title: The reserved-name list agrees with IRx's own constant.
    summary: >-
      The list is duplicated rather than imported so that importing arxjit does
      not pull in the compiler. This keeps the copy honest: if IRx renames or
      adds an entry point, this fails rather than the mangling quietly ceasing
      to apply.
    """
    assert MAIN_FUNCTION_NAME in RESERVED_NAMES


@pytest.mark.parametrize(
    ("literal", "sig_type"),
    [
        ("True", i64),
        ("True", f64),
        ("1", bool_),
        ("1.5", i64),
        ("1.5", bool_),
    ],
)
def test_a_literal_of_the_wrong_kind_is_rejected(
    literal: str, sig_type: SigType
) -> None:
    """
    title: A literal must belong to the type its context declares.
    summary: >-
      bool is checked before int because it is a subclass of one, so True must
      not satisfy an integer context by accident. A float in an integer context
      has no integer value to preserve, so it is refused rather than truncated.
    parameters:
      literal:
        type: str
      sig_type:
        type: SigType
    """
    source = f"def sample():\n    return {literal}\n"
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, sig_type())
    assert "cannot lower a" in str(excinfo.value)


@pytest.mark.parametrize(
    ("literal", "sig_type"),
    [
        (str(2**31), i32),
        (str(2**63), i64),
        (str(2**2000), f64),
        ("1e39", f32),
    ],
)
def test_a_literal_out_of_range_is_rejected(
    literal: str, sig_type: SigType
) -> None:
    """
    title: A literal too large for its type is refused, not mislabelled.
    summary: >-
      Python integers are unbounded, so without a range check a value too large
      to represent would still be emitted as an Int64 literal that misstates
      its own value. The float cases cover the two ways a value can exceed a
      target: an integer beyond what a double can hold, and a double beyond
      what a single can.
    parameters:
      literal:
        type: str
      sig_type:
        type: SigType
    """
    source = f"def sample():\n    return {literal}\n"
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, sig_type())
    assert "out of range" in str(excinfo.value)


@pytest.mark.parametrize(
    ("literal", "sig_type"),
    [
        (str(2**31 - 1), i32),
        (str(2**63 - 1), i64),
        ("3.4e38", f32),
        ("1e-50", f32),
    ],
)
def test_a_literal_at_the_edge_of_range_is_accepted(
    literal: str, sig_type: SigType
) -> None:
    """
    title: The range check admits the extremes it is meant to admit.
    summary: >-
      The boundary partner of the rejection test: an off-by-one bound would
      pass that test while refusing values the type represents perfectly well.
      Underflow to zero is precision loss rather than overflow, so a tiny float
      is accepted.
    parameters:
      literal:
        type: str
      sig_type:
        type: SigType
    """
    source = f"def sample():\n    return {literal}\n"
    definition = _from_source(source, sig_type())
    (returned,) = definition.body.nodes
    assert isinstance(returned, astx.FunctionReturn)


def test_a_float_overflow_reported_by_exception_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: An overflow raised rather than returned is still a rejection.
    summary: >-
      struct reports a value too large for single precision either by packing
      it to an infinity or by raising OverflowError, and which one is not
      portable: the same CPython version does one on some platforms and the
      other elsewhere. The real out-of-range case above therefore exercises
      only one of the two paths on any given machine, so the other is forced
      here, and both are covered on every cell of the matrix.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """

    def raising(fmt: str, value: float) -> bytes:
        """
        title: Stand in for struct.pack, always overflowing.
        parameters:
          fmt:
            type: str
          value:
            type: float
        returns:
          type: bytes
        raises:
          OverflowError: Always.
        """
        raise OverflowError("float too large to pack with f format")

    monkeypatch.setattr(lowering.struct, "pack", raising)
    with pytest.raises(LoweringError) as excinfo:
        _from_source("def sample():\n    return 1.5\n", f32())
    assert "out of range" in str(excinfo.value)


def test_a_negated_literal_folds_into_one_negative_literal() -> None:
    """
    title: A negative number lowers as a literal, not as an operator.
    summary: >-
      Python parses -1 as USub applied to the constant 1, so a negative value
      never reaches the constant overload on its own. Folding is what makes it
      lowerable at all, since IRx implements no unary minus, and it is also
      what admits the exact minimum of a signed type: -2147483648 is a valid
      i32 while its magnitude, 2147483648, is not. This is the test the
      previous PR left failing for this one to flip.
    """
    definition = _from_source(f"def sample():\n    return -{2**31}\n", i32())
    (returned,) = definition.body.nodes
    assert isinstance(returned, astx.FunctionReturn)
    assert isinstance(returned.value, astx.LiteralInt32)
    assert returned.value.value == -(2**31)


def test_a_negated_literal_below_the_minimum_is_still_rejected() -> None:
    """
    title: Folding widens what is accepted by exactly one value, not more.
    summary: >-
      The boundary partner of the test above: the fold must admit the minimum
      without also admitting everything past it.
    """
    with pytest.raises(LoweringError) as excinfo:
        _from_source(f"def sample():\n    return -{2**31 + 1}\n", i32())
    assert "out of range" in str(excinfo.value)


@pytest.mark.parametrize(
    ("operator", "op_code"),
    [("+", "+"), ("-", "-"), ("*", "*"), ("/", "/"), ("%", "%")],
)
def test_each_arithmetic_operator_lowers_and_analyses(
    operator: str, op_code: str
) -> None:
    """
    title: Every supported binary operator survives IRx analysis.
    summary: >-
      Run through analysis rather than only inspected, because an op_code astx
      does not know specializes to no node and only fails later, in codegen.
    parameters:
      operator:
        type: str
      op_code:
        type: str
    """
    source = f"def sample(a, b):\n    return a {operator} b\n"
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    module = lower(
        ExtractedSource(filename="<test>", source=source, lineno=1, node=node),
        f64(f64, f64),
    )
    definition = module.block[0]
    assert isinstance(definition, astx.FunctionDef)
    (returned,) = definition.body.nodes
    assert isinstance(returned, astx.FunctionReturn)
    assert isinstance(returned.value, astx.BinaryOp)
    assert returned.value.op_code == op_code
    analyze(module)


def test_a_parameter_read_lowers_to_a_variable() -> None:
    """
    title: A name reads the parameter of that name.
    summary: >-
      The reference carries no type: the prototype already declares it, and
      reconciling a variable with its context is IRx's to do, unlike a literal
      whose width this stage chooses.
    """
    definition = _from_source("def sample(a):\n    return a\n", i64(i64))
    (returned,) = definition.body.nodes
    assert isinstance(returned, astx.FunctionReturn)
    assert isinstance(returned.value, astx.Variable)
    assert returned.value.name == "a"


def test_operand_literals_take_the_expected_width() -> None:
    """
    title: A literal inside an expression is built at the declared width.
    summary: >-
      The expected type is propagated into both operands, so the same rule that
      governs a returned literal governs one buried in an expression; an Int64
      literal here would fail analysis in an i32 function.
    """
    definition = _from_source("def sample(a):\n    return a + 1\n", i32(i32))
    (returned,) = definition.body.nodes
    assert isinstance(returned, astx.FunctionReturn)
    assert isinstance(returned.value, astx.BinaryOp)
    assert isinstance(returned.value.rhs, astx.LiteralInt32)


def test_a_unary_plus_lowers_to_its_operand() -> None:
    """
    title: A unary plus contributes no node.
    summary: >-
      It is the identity, and IRx has no operator for it, so the operand is
      lowered alone rather than wrapped in something codegen would reject.
    """
    definition = _from_source("def sample(a):\n    return +a\n", i64(i64))
    (returned,) = definition.body.nodes
    assert isinstance(returned, astx.FunctionReturn)
    assert isinstance(returned.value, astx.Variable)


def test_a_logical_not_lowers_to_the_astx_operator() -> None:
    """
    title: not lowers to the one unary operator IRx implements.
    """
    source = "def sample(a):\n    return not a\n"
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    module = lower(
        ExtractedSource(filename="<test>", source=source, lineno=1, node=node),
        bool_(bool_),
    )
    definition = module.block[0]
    assert isinstance(definition, astx.FunctionDef)
    (returned,) = definition.body.nodes
    assert isinstance(returned, astx.FunctionReturn)
    assert isinstance(returned.value, astx.UnaryOp)
    assert returned.value.op_code == "!"
    analyze(module)


@pytest.mark.parametrize(
    ("operator", "name"), [("//", "FloorDiv"), ("**", "Pow")]
)
def test_an_operator_astx_lacks_is_rejected(operator: str, name: str) -> None:
    """
    title: An operator with no astx entry is refused, not emitted.
    summary: >-
      Validation admits both of these, but astx maps neither to a specialized
      node, so each would reach codegen as "not implemented yet". Refusing here
      keeps the disagreement between the subset and the backend visible as a
      diagnostic rather than as a failure much later.
    parameters:
      operator:
        type: str
      name:
        type: str
    """
    source = f"def sample(a, b):\n    return a {operator} b\n"
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, i64(i64, i64))
    assert f"cannot lower the {name} operator" in str(excinfo.value)


def test_negating_a_variable_is_rejected() -> None:
    """
    title: Only a literal can be negated.
    summary: >-
      IRx implements ++, -- and ! and no unary minus, so a negated variable has
      no operator to lower onto. Emitting one anyway would produce a module
      that analyses cleanly and then fails in codegen.
    """
    with pytest.raises(LoweringError) as excinfo:
        _from_source("def sample(a):\n    return -a\n", i64(i64))
    assert "IRx implements no unary minus" in str(excinfo.value)


def test_a_unary_operator_astx_lacks_is_rejected() -> None:
    """
    title: A unary operator with no astx entry is refused.
    summary: >-
      Validation rejects ~ before lowering runs, so this is reached only
      through the public entry point; IRx implements no bitwise inversion, so
      it must not be emitted.
    """
    with pytest.raises(LoweringError) as excinfo:
        _from_source("def sample(a):\n    return ~a\n", i64(i64))
    assert "cannot lower the Invert operator" in str(excinfo.value)


@pytest.mark.parametrize(
    ("operator", "op_code"),
    [
        ("==", "=="),
        ("!=", "!="),
        ("<", "<"),
        ("<=", "<="),
        (">", ">"),
        (">=", ">="),
    ],
)
def test_a_comparison_lowers_to_a_binary_op(
    operator: str, op_code: str
) -> None:
    """
    title: Each comparison lowers to the binary node IRx implements.
    summary: >-
      astx.CompareOp is what a comparison looks like it should become, but
      IRx's visitor for it is not implemented, so it would pass this stage and
      fail codegen. analyze proves the emitted form is one IRx accepts.
    parameters:
      operator:
        type: str
      op_code:
        type: str
    """
    source = f"def sample(a, b):\n    return a {operator} b\n"
    module = _module_from_source(source, bool_(i64, i64))
    returned = _returned(module)
    assert isinstance(returned, astx.BinaryOp)
    assert returned.op_code == op_code
    analyze(module)


def test_a_chained_comparison_is_rejected_until_it_can_short_circuit() -> None:
    """
    title: A chained comparison is not lowered to eager logical operations.
    summary: >-
      The final modulo must be unreachable after the first comparison is false.
      Until lowering can express that control flow and evaluate middle operands
      exactly once, rejecting the expression preserves Python semantics.
    """
    source = "def sample():\n    return 0 > 1 > (1 % 0)\n"
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, bool_())
    assert "chained comparison" in str(excinfo.value)
    assert "short-circuit control flow" in str(excinfo.value)


def test_a_comparison_lowers_its_operands_at_their_own_type() -> None:
    """
    title: An operand is not lowered at the type of the comparison.
    summary: >-
      The expected type at a comparison is the bool the comparison yields, and
      lowering the literal in ``a < 3`` against it would ask for 3 as a bool
      and refuse a correct program. The operands' own type is used instead.
    """
    source = "def sample(a):\n    return a < 3\n"
    module = _module_from_source(source, bool_(i64))
    returned = _returned(module)
    assert isinstance(returned, astx.BinaryOp)
    assert isinstance(returned.rhs, astx.LiteralInt64)
    analyze(module)


def test_a_comparison_lowers_its_operands_at_the_wider_type() -> None:
    """
    title: Mixed operands compare at a type that can hold both.
    summary: >-
      An integer literal compared against a float parameter is lowered as a
      float, which is the promotion Python performs, rather than narrowing the
      parameter to meet the literal.
    """
    source = "def sample(a):\n    return a < 3\n"
    module = _module_from_source(source, bool_(f64))
    returned = _returned(module)
    assert isinstance(returned, astx.BinaryOp)
    assert isinstance(returned.rhs, astx.LiteralFloat64)


@pytest.mark.parametrize(
    ("literal", "sig_type", "expected"),
    [
        ("3", i32, astx.LiteralInt64),
        ("1.5", f32, astx.LiteralFloat64),
    ],
)
def test_a_narrow_parameter_compares_against_a_wide_literal(
    literal: str, sig_type: SigType, expected: type[astx.Literal]
) -> None:
    """
    title: A narrow parameter is widened to meet its literal, not the reverse.
    summary: >-
      Inference gives a bare literal the widest type of its kind, so an i32 or
      f32 parameter is compared against an Int64 or Float64. That is the one
      place a literal is deliberately not built at the parameter's width: a
      comparison widens both sides rather than assigning to either, and IRx
      inserts exactly this widening, which analyze proves it accepts.
    parameters:
      literal:
        type: str
      sig_type:
        type: SigType
      expected:
        type: type[astx.Literal]
    """
    source = f"def sample(a):\n    return a < {literal}\n"
    module = _module_from_source(source, bool_(sig_type))
    returned = _returned(module)
    assert isinstance(returned, astx.BinaryOp)
    assert isinstance(returned.rhs, expected)
    analyze(module)


@pytest.mark.parametrize(
    "expression",
    ["False and (1 % 0 > 0)", "True or (1 % 0 > 0)"],
)
def test_a_boolean_operator_is_rejected_until_it_can_short_circuit(
    expression: str,
) -> None:
    """
    title: and/or are not lowered to eager logical binary operations.
    summary: >-
      The modulo is unreachable in Python for both expressions. Rejecting them
      is safer than emitting an IRx logical operation that evaluates it.
    parameters:
      expression:
        type: str
    """
    source = f"def sample():\n    return {expression}\n"
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, bool_())
    assert "short-circuit control flow" in str(excinfo.value)


def test_an_n_ary_boolean_expression_is_rejected() -> None:
    """
    title: Wider and/or expressions remain rejected too.
    """
    source = "def sample(a, b, c):\n    return a and b and c\n"
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, bool_(bool_, bool_, bool_))
    assert "short-circuit control flow" in str(excinfo.value)


@pytest.mark.parametrize(
    ("operator", "name"),
    [("is", "Is"), ("is not", "IsNot"), ("in", "In"), ("not in", "NotIn")],
)
def test_a_comparison_irx_lacks_is_rejected(operator: str, name: str) -> None:
    """
    title: A comparison with no IRx op_code is refused, not emitted.
    summary: >-
      Validation rejects all four before lowering runs, so these are reached
      only through the public entry point; none has an operator to lower onto.
    parameters:
      operator:
        type: str
      name:
        type: str
    """
    source = f"def sample(a, b):\n    return a {operator} b\n"
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, bool_(i64, i64))
    assert f"cannot lower the {name} comparison" in str(excinfo.value)


def test_a_negated_bool_literal_is_rejected() -> None:
    """
    title: -True is refused rather than folded to an integer.
    summary: >-
      bool is a subclass of int and negating one in Python yields an int, so
      folding -True would put an Int64 literal where the user wrote a bool and
      slip past the bool-before-int check every other literal path makes.
    """
    with pytest.raises(LoweringError) as excinfo:
        _from_source("def sample():\n    return -True\n", i64())
    assert "cannot lower a negated bool literal" in str(excinfo.value)


def test_a_name_that_is_not_a_parameter_cannot_be_typed() -> None:
    """
    title: Inference refuses a name it has no type for.
    summary: >-
      Validation rejects a free variable before lowering runs, so this is
      reached only through the public entry point; inferring some default type
      for it would compile a program against a type the name does not have.
    """
    source = "def sample(a):\n    return a < missing\n"
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, bool_(i64))
    assert "it is not a parameter" in str(excinfo.value)


def test_an_expression_with_no_inference_overload_fails_closed() -> None:
    """
    title: Inference refuses a node it has no rule for.
    summary: >-
      Inference and lowering cover the same expressions, so a node reaching
      inference without a rule means the two have drifted apart.
    """
    source = "def sample(a):\n    return a < (1 if a else 2)\n"
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, bool_(i64))
    assert "cannot infer the type of a IfExp expression" in str(excinfo.value)


def test_a_literal_of_no_supported_kind_cannot_be_typed() -> None:
    """
    title: Inference refuses a literal kind the subset does not admit.
    summary: >-
      Validation rejects a string before lowering runs; inference must not
      assign it a numeric type on the way past.
    """
    source = "def sample(a):\n    return a < 'x'\n"
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, bool_(i64))
    assert "cannot infer the type of a str literal" in str(excinfo.value)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def sample(a):\n    return a == True\n", astx.LiteralBoolean),
        ("def sample(a):\n    return a == 1.5\n", astx.LiteralFloat64),
    ],
)
def test_a_literal_operand_is_typed_by_its_python_kind(
    source: str, expected: type[astx.Literal]
) -> None:
    """
    title: A literal standing alone is inferred at the widest type of its kind.
    summary: >-
      Nothing in the comparison declares a type for it, so Python's own notion
      of the literal's type is all there is to go on: its floats are doubles,
      and a bool is a bool rather than the integer it can stand in for.
    parameters:
      source:
        type: str
      expected:
        type: type[astx.Literal]
    """
    module = _module_from_source(source, bool_(bool_))
    returned = _returned(module)
    assert isinstance(returned, astx.BinaryOp)
    assert isinstance(returned.rhs, expected)


def test_an_arithmetic_operand_is_typed_from_its_own_operands() -> None:
    """
    title: A comparison against an arithmetic expression infers through it.
    summary: >-
      The float parameter inside the sum makes the whole sum a float, so the
      integer literal it is compared against is lowered as one too.
    """
    source = "def sample(a, b):\n    return a + 1 < b\n"
    module = _module_from_source(source, bool_(f64, f64))
    returned = _returned(module)
    assert isinstance(returned, astx.BinaryOp)
    assert isinstance(returned.lhs, astx.BinaryOp)
    assert isinstance(returned.lhs.rhs, astx.LiteralFloat64)


@pytest.mark.parametrize("expression", ["1 / 2 > 0", "3 / 2 == 1.5"])
def test_integer_true_division_executes_with_python_semantics(
    expression: str,
) -> None:
    """
    title: Integer true division produces a floating-point result at runtime.
    parameters:
      expression:
        type: str
    """
    source = f"def sample():\n    return {expression}\n"
    module = _module_from_source(source, bool_())
    returned = _returned(module)
    assert isinstance(returned, astx.BinaryOp)
    assert isinstance(returned.lhs, astx.BinaryOp)
    assert returned.lhs.op_code == "/"
    assert isinstance(returned.lhs.lhs, astx.LiteralFloat64)
    assert isinstance(returned.lhs.rhs, astx.LiteralFloat64)
    assert execute_bool(module, "sample__sample") is True


def test_int64_and_float32_comparison_executes_at_float64() -> None:
    """
    title: Int64 literals are not rounded to Float32 before comparison.
    summary: >-
      16,777,217 is the first integer Float32 cannot represent exactly. A
      Float32 value of 16,777,216 must remain less than that literal.
    """
    source = "def sample(a):\n    return a < 16777217\n"
    module = _module_from_source(source, bool_(f32))
    returned = _returned(module)
    assert isinstance(returned, astx.BinaryOp)
    assert isinstance(returned.rhs, astx.LiteralFloat64)
    assert execute_bool_f32(module, "sample__sample", 16777216.0) is True


def test_a_negated_operand_keeps_the_type_it_negates() -> None:
    """
    title: Unary minus does not change the type inference sees.
    """
    source = "def sample(a):\n    return -1 < a\n"
    module = _module_from_source(source, bool_(f64))
    returned = _returned(module)
    assert isinstance(returned, astx.BinaryOp)
    assert isinstance(returned.lhs, astx.LiteralFloat64)


@pytest.mark.parametrize(
    ("source", "signature"),
    [
        ("def sample(a):\n    return (not a) == a\n", bool_(bool_)),
        ("def sample(a, b):\n    return a + (not b)\n", i64(i64, bool_)),
    ],
)
def test_a_unary_operand_of_a_binary_operator_is_rejected(
    source: str, signature: Signature
) -> None:
    """
    title: not in either operand position is refused with a location.
    summary: >-
      astx requires a DataType on both operands of a binary operator and gives
      its UnaryOp the generic ExprType, so building one raises a bare Exception
      out of astx with nothing pointing at the user's code. Refusing here
      reports it the way every other unlowerable expression is reported. The
      arithmetic form reaches the same wall without this stage lowering
      comparisons at all, so the refusal covers a path that predates them.
    parameters:
      source:
        type: str
      signature:
        type: Signature
    """
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, signature)
    assert "cannot lower a unary operation" in str(excinfo.value)


def test_a_not_expression_is_inferred_as_a_bool() -> None:
    """
    title: not makes its operand's type irrelevant to what it yields.
    summary: >-
      Checked on the inference rule directly, because astx cannot yet hold a
      unary operation as the operand of a binary one, so there is no expression
      this stage can build that would show the inferred type instead.
    """
    source = "def sample(a):\n    return not a\n"
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    extracted = ExtractedSource(
        filename="<test>", source=source, lineno=1, node=node
    )
    lowerer = lowering.Lowerer(extracted, bool_(i64))
    returned = node.body[0]
    assert isinstance(returned, ast.Return)
    assert returned.value is not None
    assert lowerer.infer(returned.value) == bool_


def test_a_comparison_is_inferred_as_a_bool() -> None:
    """
    title: A comparison result is inferred independently of its operands.
    """
    source = "def sample(a, b):\n    return a < b\n"
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    extracted = ExtractedSource(
        filename="<test>", source=source, lineno=1, node=node
    )
    lowerer = lowering.Lowerer(extracted, bool_(i64, i64))
    returned = node.body[0]
    assert isinstance(returned, ast.Return)
    assert returned.value is not None
    assert lowerer.infer(returned.value) == bool_


@pytest.mark.parametrize(
    ("source", "signature"),
    [
        (
            "def sample(a, b):\n    return a < b and b < a\n",
            bool_(i64, i64),
        ),
        (
            "def sample(a, b, c):\n    return a and (b or c)\n",
            bool_(bool_, bool_, bool_),
        ),
    ],
)
def test_a_boolean_expression_is_inferred_as_a_bool(
    source: str, signature: Signature
) -> None:
    """
    title: Boolean inference remains available while lowering is deferred.
    parameters:
      source:
        type: str
      signature:
        type: Signature
    """
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    extracted = ExtractedSource(
        filename="<test>", source=source, lineno=1, node=node
    )
    lowerer = lowering.Lowerer(extracted, signature)
    returned = node.body[0]
    assert isinstance(returned, ast.Return)
    assert returned.value is not None
    assert lowerer.infer(returned.value) == bool_


def test_negating_a_literal_of_no_supported_kind_is_rejected() -> None:
    """
    title: Only a numeric literal can be folded into a negative one.
    summary: >-
      Validation rejects a string before lowering runs, so this is reached only
      through the public entry point; it must not be folded into a value
      negation does not define.
    """
    with pytest.raises(LoweringError) as excinfo:
        _from_source("def sample():\n    return -'x'\n", i64())
    assert "IRx implements no unary minus" in str(excinfo.value)


def test_the_comparison_tables_agree_with_irx() -> None:
    """
    title: Every comparison op_code is one IRx resolves.
    summary: >-
      IRx returns a type for exactly the op codes it implements and None for
      anything else, so an entry added here without one there would lower
      quietly and fail semantic analysis. Read from IRx directly so the check
      cannot go stale.
    """
    for op_code in lowering.COMPARE_OPS.values():
        assert (
            binary_result_type(op_code, astx.Int64(), astx.Int64()) is not None
        )


def test_numeric_promotion_agrees_with_irx_for_every_type_pair() -> None:
    """
    title: ArxJIT and IRx choose the same type for every numeric pair.
    summary: >-
      In particular, Int32/Float32 stays Float32 while Int64/Float32 becomes
      Float64. Checking the full product prevents either policy drifting.
    """
    numeric_types = (i32, i64, f32, f64)
    source = "def sample():\n    return 1\n"
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    extracted = ExtractedSource(
        filename="<test>", source=source, lineno=1, node=node
    )
    lowerer = lowering.Lowerer(extracted, i64())
    for left in numeric_types:
        for right in numeric_types:
            promoted = lowerer.promote(left, right)
            expected = common_numeric_type(
                lowering.astx_type(left), lowering.astx_type(right)
            )
            assert expected is not None
            assert type(lowering.astx_type(promoted)) is type(expected)


def test_every_scalar_pair_has_a_frontend_promotion() -> None:
    """
    title: Every scalar pair this stage can infer has a promotion entry.
    """
    scalar_names = set(SCALARS)
    expected = {
        frozenset({left, right})
        for left in scalar_names
        for right in scalar_names
    }
    assert set(lowering.PROMOTIONS) == expected


def test_the_operator_tables_agree_with_astx() -> None:
    """
    title: Every operator this stage emits is one astx specializes.
    summary: >-
      astx falls back to a plain BinaryOp for an unknown op_code rather than
      raising, so an operator added here without an entry there would lower
      quietly and only fail in codegen. Read from astx directly so the check
      cannot go stale.
    """
    for op_code in lowering.BINARY_OPS.values():
        assert op_code in _BINARY_OP_TYPES


def test_docstring_and_pass_lower_to_nothing() -> None:
    """
    title: Statements with no compiled effect contribute no astx nodes.
    """

    def nothing() -> int:
        """
        title: Do nothing at all.
        returns:
          type: int
        """
        pass

    definition = _lower(nothing, i64())
    assert definition.body.nodes == []


def test_lowered_nodes_carry_real_file_locations() -> None:
    """
    title: astx nodes are located at the user's real source position.
    summary: >-
      Locations run through the same builder arxjit reports diagnostics with,
      so a compiled artifact points back at the file the user wrote, with the
      one-based character columns Diagnostic documents rather than ast's raw
      byte offsets.
    """

    def sample() -> int:
        """
        title: Return a constant.
        returns:
          type: int
        """
        return 5

    extracted = extract_source(sample)
    definition = _lower(sample, i64())
    assert definition.loc.line == extracted.lineno
    assert definition.loc.col == 5

    (returned,) = definition.body.nodes
    assert isinstance(returned, astx.FunctionReturn)
    lines = extracted.source.splitlines()
    assert lines[returned.loc.line - extracted.lineno].strip() == "return 5"
    assert isinstance(returned.value, astx.LiteralInt64)
    assert returned.value.loc.col > returned.loc.col


def test_a_node_without_a_position_maps_to_no_location() -> None:
    """
    title: A synthesized node lowers to astx's own no-location value.
    summary: >-
      Every node in a parsed function carries a position, so this is the
      fallback for a hand-built one; it maps to NO_SOURCE_LOCATION rather than
      inventing a position that would point at unrelated source.
    """
    source = "def sample():\n    return 1\n"
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    extracted = ExtractedSource(
        filename="<test>", source=source, lineno=1, node=node
    )
    assert location(extracted, ast.Pass()) is NO_SOURCE_LOCATION


def test_bare_return_is_rejected() -> None:
    """
    title: A return with no value cannot satisfy a declared return type.
    """
    with pytest.raises(LoweringError) as excinfo:
        _from_source("def sample():\n    return\n", i64())
    assert "cannot lower a bare return" in str(excinfo.value)
    assert "declares the return type i64" in str(excinfo.value)
    (diagnostic,) = excinfo.value.diagnostics
    assert diagnostic.line == 2


def test_an_unlowerable_statement_fails_closed() -> None:
    """
    title: A statement with no overload is reported, not skipped.
    summary: >-
      Validation admits while loops, so reaching one here means the subset and
      the lowerer disagree; the module must not come back quietly missing the
      loop.
    """
    source = "def sample():\n    while True:\n        return 1\n"
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, i64())
    assert "cannot lower a While statement" in str(excinfo.value)


def test_an_unlowerable_expression_fails_closed() -> None:
    """
    title: An expression with no overload is reported, not skipped.
    summary: >-
      Validation rejects a conditional expression before lowering runs, so this
      is reached only through the public entry point; an expression this stage
      cannot map must be refused rather than dropped from the body.
    """
    source = "def sample(x):\n    return 1 if x else 2\n"
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, i64(bool_))
    assert "cannot lower a IfExp expression" in str(excinfo.value)


def test_a_standalone_expression_statement_is_rejected() -> None:
    """
    title: Only a bare string is dropped in statement position.
    summary: >-
      Validation rejects any other standalone expression before lowering runs,
      so this is reached only through the public entry point; it must not
      discard a statement that computes something.
    """
    source = "def sample():\n    1 + 1\n    return 1\n"
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, i64())
    assert "standalone expression statement" in str(excinfo.value)


def test_an_unsupported_literal_is_rejected() -> None:
    """
    title: A literal outside int, float and bool has no astx mapping here.
    """
    source = 'def sample():\n    return "text"\n'
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, i64())
    assert "cannot lower a str literal" in str(excinfo.value)


@pytest.mark.parametrize(
    ("source", "signature", "expected"),
    [
        ("def sample(*args):\n    return 1\n", i64(), "variadic"),
        ("def sample(**kwargs):\n    return 1\n", i64(), "variadic"),
        ("def sample(*, k):\n    return 1\n", i64(), "variadic"),
        ("def sample(x=1):\n    return 1\n", i64(i64), "parameter default"),
        (
            "def sample(*, k=1):\n    return 1\n",
            i64(),
            "variadic",
        ),
    ],
)
def test_an_unsupported_argument_shape_is_rejected(
    source: str, signature: Signature, expected: str
) -> None:
    """
    title: Shapes an astx argument list cannot express are refused.
    summary: >-
      Validation rejects all of these first, but lower is public and none of
      them can be represented: a variadic or keyword-only parameter would
      simply vanish from the prototype, and a default would silently become a
      required argument. The count check alone does not catch them, because a
      function taking only *args counts as taking none.
    parameters:
      source:
        type: str
      signature:
        type: Signature
      expected:
        type: str
    """
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, signature)
    assert expected in str(excinfo.value)


def test_signature_arity_disagreeing_with_the_definition_is_rejected() -> None:
    """
    title: A signature describing a different function is refused.
    summary: >-
      Reconciliation makes this unreachable through @jit, but lower is public
      and zip would silently drop the excess, producing a module whose calling
      convention no caller could satisfy.
    """
    source = "def sample(a, b):\n    return 1\n"
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, i64(i64))
    assert "declares 1 argument type but it takes 2" in str(excinfo.value)


def test_the_arity_message_pluralizes_the_declared_count() -> None:
    """
    title: The count of declared types reads correctly when it is not one.
    summary: >-
      The singular is covered by the test above. Both are pinned because a
      conditional expression like this one is invisible to line coverage: the
      unexercised branch sits on a line the other branch already ran.
    """
    source = "def sample(a):\n    return 1\n"
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, i64(i64, i64))
    assert "declares 2 argument types but it takes 1" in str(excinfo.value)


def test_an_unmapped_signature_type_is_rejected() -> None:
    """
    title: A SigType naming an astx class this stage lacks fails closed.
    """
    unknown = SigType("i128", "Int128")
    with pytest.raises(LoweringError) as excinfo:
        _from_source("def sample():\n    return 1\n", unknown())
    assert "no astx class is mapped for 'Int128'" in str(excinfo.value)


@pytest.mark.parametrize("sig_type", [bool_, f32, f64, i32, i64])
def test_every_sig_type_is_mapped(sig_type: SigType) -> None:
    """
    title: Every exported signature type can be lowered.
    summary: >-
      The table is keyed by name, so a SigType added to the public type API
      without an entry here would only fail when someone first used it. An
      integer type additionally needs a declared range, without which its
      literals could not be bounds-checked.
    parameters:
      sig_type:
        type: SigType
    """
    mapped = SCALARS[sig_type.astx_name]
    assert (mapped.bounds is not None) == (mapped.kind == "int")


def test_the_sig_type_list_covers_the_public_type_api() -> None:
    """
    title: The exhaustiveness test above is itself exhaustive.
    summary: >-
      Reads the public types out of the package rather than trusting the
      parametrized list, so adding a SigType to arxjit without adding it to
      that list fails here instead of going unnoticed.
    """
    exported = {
        value.astx_name
        for name in arxjit.__all__
        if isinstance(value := getattr(arxjit, name), SigType)
    }
    assert exported == set(SCALARS)
