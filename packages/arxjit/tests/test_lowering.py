"""
title: Tests for Python AST to ASTx lowering.
"""

import ast

from typing import Any, Callable

import arxjit
import astx
import pytest

from arxjit import lowering
from arxjit.errors import LoweringError
from arxjit.lowering import (
    _MANGLE_PREFIX,
    _RESERVED_NAMES,
    _SCALARS,
    location,
    lower,
)
from arxjit.source import ExtractedSource, extract_source
from arxjit.types import Signature, SigType, bool_, f32, f64, i32, i64
from astx.base import NO_SOURCE_LOCATION
from astx.binary_op import _BINARY_OP_TYPES
from irx.analysis.api import analyze
from irx.analysis.registry import MAIN_FUNCTION_NAME

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
    assert definition.prototype.name == f"{_MANGLE_PREFIX}main"
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
    assert MAIN_FUNCTION_NAME in _RESERVED_NAMES


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


def test_the_operator_tables_agree_with_astx() -> None:
    """
    title: Every operator this stage emits is one astx specializes.
    summary: >-
      astx falls back to a plain BinaryOp for an unknown op_code rather than
      raising, so an operator added here without an entry there would lower
      quietly and only fail in codegen. Read from astx directly so the check
      cannot go stale.
    """
    for op_code in lowering._BINARY_OPS.values():
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
      Validation admits comparisons, so reaching one here means the subset and
      the lowerer disagree. They lower with the conditionals that give them a
      purpose, not before.
    """
    source = "def sample(x):\n    return x < 1\n"
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, bool_(i64))
    assert "cannot lower a Compare expression" in str(excinfo.value)


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
    mapped = _SCALARS[sig_type.astx_name]
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
    assert exported == set(_SCALARS)
