"""
title: Tests for template parsing.
"""

from __future__ import annotations

from textwrap import dedent

import pytest

from arx.exceptions import ParserException
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser
from irx import astx


def _parse(code: str) -> astx.Module:
    """
    title: Parse one source snippet into a module.
    parameters:
      code:
        type: str
    returns:
      type: astx.Module
    """
    ArxIO.string_to_buffer(code)
    tree = Parser().parse(Lexer().lex())
    assert isinstance(tree, astx.Module)
    return tree


def test_parse_template_function_metadata_and_calls() -> None:
    """
    title: Parse one template function plus inferred and explicit calls.
    """
    tree = _parse(
        dedent(
            """
            @<
              T: i32 | f64
            >
            fn add(lhs: T, rhs: T) -> T:
              return lhs + rhs

            fn main() -> i32:
              var whole: i32 = add(1, 2)
              var decimal: f64 = add<f64>(1.5, 2.5)
              print(decimal)
              return whole
            """
        ).lstrip()
    )

    function = tree.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    assert astx.is_template_node(function)
    assert astx.is_template_node(function.prototype)

    template_params = astx.get_template_params(function.prototype)
    assert len(template_params) == 1
    assert template_params[0].name == "T"
    assert isinstance(template_params[0].bound, astx.UnionType)
    assert [type(member) for member in template_params[0].bound.members] == [
        astx.Int32,
        astx.Float64,
    ]

    lhs = function.prototype.args.nodes[0]
    rhs = function.prototype.args.nodes[1]
    assert isinstance(lhs.type_, astx.TemplateTypeVar)
    assert isinstance(rhs.type_, astx.TemplateTypeVar)
    assert lhs.type_.name == "T"
    assert rhs.type_.name == "T"
    assert isinstance(function.prototype.return_type, astx.TemplateTypeVar)
    assert function.prototype.return_type.name == "T"

    main = tree.nodes[1]
    assert isinstance(main, astx.FunctionDef)
    whole_decl = main.body.nodes[0]
    assert isinstance(whole_decl, astx.VariableDeclaration)
    inferred_call = whole_decl.value
    assert isinstance(inferred_call, astx.FunctionCall)
    assert astx.get_template_args(inferred_call) is None

    decimal_decl = main.body.nodes[1]
    assert isinstance(decimal_decl, astx.VariableDeclaration)
    explicit_call = decimal_decl.value
    assert isinstance(explicit_call, astx.FunctionCall)
    explicit_args = astx.get_template_args(explicit_call)
    assert explicit_args is not None
    assert len(explicit_args) == 1
    assert isinstance(explicit_args[0], astx.Float64)


def test_parse_template_method_with_mixed_prefix_order() -> None:
    """
    title: Parse one template method with modifiers and explicit call args.
    """
    tree = _parse(
        dedent(
            """
            class Math:
              @<T: i32 | f64>
              @[public, static]
              fn identity(value: T) -> T:
                return value

            fn main() -> i32:
              var decimal: f64 = Math.identity<f64>(1.5)
              print(decimal)
              return 0
            """
        ).lstrip()
    )

    class_def = tree.nodes[0]
    assert isinstance(class_def, astx.ClassDefStmt)
    method = class_def.methods.nodes[0]
    assert isinstance(method, astx.FunctionDef)
    assert astx.is_template_node(method)
    assert astx.is_template_node(method.prototype)
    assert getattr(method.prototype, "is_static", False) is True

    template_params = astx.get_template_params(method.prototype)
    assert len(template_params) == 1
    assert template_params[0].name == "T"
    assert isinstance(template_params[0].bound, astx.UnionType)
    assert isinstance(
        method.prototype.args.nodes[0].type_,
        astx.TemplateTypeVar,
    )
    assert isinstance(method.prototype.return_type, astx.TemplateTypeVar)

    main = tree.nodes[1]
    assert isinstance(main, astx.FunctionDef)
    decimal_decl = main.body.nodes[0]
    assert isinstance(decimal_decl, astx.VariableDeclaration)
    call = decimal_decl.value
    assert isinstance(call, astx.StaticMethodCall)
    template_args = astx.get_template_args(call)
    assert template_args is not None
    assert len(template_args) == 1
    assert isinstance(template_args[0], astx.Float64)


@pytest.mark.parametrize(
    "code, expected",
    [
        (
            "@<T>\nfn add(value: i32) -> i32:\n  return value\n",
            "template parameter 'T' must declare a bound",
        ),
        (
            "@<T: i32 | f64> fn add(value: T) -> T:\n  return value\n",
            "template parameter block must appear on its own line",
        ),
        (
            "@<T: i32 | f64>\nclass Math:\n  value: int32 = 1\n",
            "template parameter blocks are only allowed "
            "before functions or methods",
        ),
        (
            dedent(
                """
                class Math:
                  @<T: i32 | f64>
                  value: int32 = 1
                """
            ).lstrip(),
            "template parameter blocks are only allowed "
            "before functions or methods",
        ),
        (
            "@<T: i32 | f64>\nextern add(value: i32) -> i32\n",
            "template parameter blocks are only allowed "
            "before functions or methods",
        ),
        (
            "fn main() -> i32:\n  foo<i32>\n",
            "explicit template arguments are only allowed on call expressions",
        ),
        (
            "fn main() -> i32:\n  value.method<i32>\n",
            "explicit template arguments are only allowed on call expressions",
        ),
        (
            "fn main() -> i32:\n  Math.identity<f64>\n",
            "explicit template arguments are only allowed on call expressions",
        ),
    ],
)
def test_parse_template_error_paths(code: str, expected: str) -> None:
    """
    title: Reject unsupported template syntax placements and forms.
    parameters:
      code:
        type: str
      expected:
        type: str
    """
    with pytest.raises(ParserException, match=expected):
        _parse(code)


def test_parse_class_construction_rejects_template_arguments() -> None:
    """
    title: Class construction does not accept explicit template arguments.
    """
    with pytest.raises(
        ParserException,
        match="class construction does not accept template arguments",
    ):
        _parse(
            dedent(
                """
                class Counter:
                  value: int32 = 1

                fn main() -> int32:
                  var counter: Counter = Counter<i32>()
                  return 0
                """
            ).lstrip()
        )


def test_parse_incomplete_template_call_syntax_raises_parser_error() -> None:
    """
    title: Incomplete explicit template-call syntax must fail cleanly.
    """
    with pytest.raises(ParserException):
        _parse("fn main() -> i32:\n  foo<\n")


def test_parse_comparisons_do_not_trigger_template_call_handling() -> None:
    """
    title: Comparison operators should not be mistaken for template calls.
    """
    tree = _parse(
        dedent(
            """
            fn main() -> i32:
              var a32: i32 = 32
              var ok: bool = (a32 > 0) && (a32 < 100)
              return 0
            """
        ).lstrip()
    )

    assert isinstance(tree.nodes[0], astx.FunctionDef)
