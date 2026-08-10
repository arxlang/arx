"""
title: Tests for Python AST to ASTx lowering.
"""

import ast

from typing import Any, Callable

import arxjit
import astx
import pytest

from arxjit.errors import LoweringError
from arxjit.lowering import _ASTX_TYPES, _location, lower
from arxjit.source import ExtractedSource, extract_source
from arxjit.types import Signature, SigType, bool_, f32, f64, i32, i64
from astx.base import NO_SOURCE_LOCATION

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
    ("literal", "expected", "value"),
    [
        ("1", astx.LiteralInt64, 1),
        ("1.5", astx.LiteralFloat64, 1.5),
        ("True", astx.LiteralBoolean, True),
        ("False", astx.LiteralBoolean, False),
    ],
)
def test_literals_lower_by_their_own_python_type(
    literal: str,
    expected: type[astx.Literal],
    value: object,
) -> None:
    """
    title: Each supported literal maps to the matching astx literal class.
    summary: >-
      True and False are covered separately from the integers because bool is a
      subclass of int in Python: a boolean matches the int check too, so an
      unordered mapping would lower it as an integer.
    parameters:
      literal:
        type: str
      expected:
        type: type[astx.Literal]
      value:
        type: object
    """
    source = f"def sample():\n    return {literal}\n"
    definition = _from_source(source, i64())
    (returned,) = definition.body.nodes
    assert isinstance(returned, astx.FunctionReturn)
    assert isinstance(returned.value, expected)
    assert returned.value.value == value


def test_a_boolean_literal_is_not_lowered_as_an_integer() -> None:
    """
    title: A bool literal never lowers to an integer literal.
    summary: >-
      Pins the ordering of the literal table directly rather than only through
      the class assertion above: isinstance(True, int) is true, so a table
      checked in the wrong order silently produces LiteralInt64(True), which
      compares equal to LiteralInt64(1) on value alone.
    """
    definition = _from_source("def sample():\n    return True\n", bool_())
    (returned,) = definition.body.nodes
    assert isinstance(returned, astx.FunctionReturn)
    assert not isinstance(returned.value, astx.LiteralInt64)


def test_the_declared_type_does_not_narrow_a_literal() -> None:
    """
    title: An i32 signature still yields a 64-bit literal.
    summary: >-
      Pins the documented division of labour: lowering states what the source
      says and IRx owns conversion, so the literal keeps the only width Python
      can express rather than being narrowed to match the signature.
    """
    definition = _from_source("def sample():\n    return 7\n", i32())
    (returned,) = definition.body.nodes
    assert isinstance(returned, astx.FunctionReturn)
    assert isinstance(returned.value, astx.LiteralInt64)
    assert isinstance(definition.prototype.return_type, astx.Int32)


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
    assert _location(extracted, ast.Pass()) is NO_SOURCE_LOCATION


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
    """
    source = "def sample(x):\n    return x\n"
    with pytest.raises(LoweringError) as excinfo:
        _from_source(source, i64(i64))
    assert "cannot lower a Name expression" in str(excinfo.value)


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
def test_every_sig_type_has_an_astx_class(sig_type: SigType) -> None:
    """
    title: Every exported signature type can be lowered.
    summary: >-
      The table is keyed by name, so a SigType added to the public type API
      without an entry here would only fail when someone first used it. The
      parametrization is checked against the module below so this list cannot
      fall behind either.
    parameters:
      sig_type:
        type: SigType
    """
    assert sig_type.astx_name in _ASTX_TYPES


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
    assert exported == set(_ASTX_TYPES)
