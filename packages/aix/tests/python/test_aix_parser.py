# ruff: noqa: RUF001
"""
title: AIX parser tests.
"""

from __future__ import annotations

import astx
import pytest

from aix.exceptions import ParserException
from aix.lexer import Lexer
from aix.parser import Parser


def parse(source: str) -> astx.Module:
    """
    title: Parse source into an AIX AST module.
    parameters:
      source:
        type: str
    returns:
      type: astx.Module
    """
    return Parser().parse(Lexer(source).tokenize())


def test_parse_hello_program() -> None:
    module = parse('∴ main ⟦⟧ → ∅\n  ⟣ "hello"\n∎')
    assert len(module.nodes) == 1
    function = module.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    assert function.prototype.name == "main"
    assert len(function.body.nodes) == 1


def test_parse_pretty_fibonacci() -> None:
    module = parse(
        "∴ fib ⟦ n:ℕ ⟧ → ℕ\n  ⊢ n ≤ 1 ⇒ n\n  ⊢ fib⟦n - 1⟧ + fib⟦n - 2⟧\n∎"
    )
    function = module.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    assert function.prototype.name == "fib"
    assert len(function.prototype.args.nodes) == 1
    assert len(function.body.nodes) == 2
    assert isinstance(function.body.nodes[0], astx.IfStmt)
    assert isinstance(function.body.nodes[1], astx.FunctionReturn)


def test_parse_compact_fibonacci() -> None:
    module = parse("∴fib⟦n:ℕ⟧→ℕ{⊢n≤1⇒n;⊢fib⟦n-1⟧+fib⟦n-2⟧}")
    function = module.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    assert len(function.body.nodes) == 2


def test_parse_metadata_and_binding() -> None:
    module = parse(
        "κ⟦ι: hello.v1, χ: example⟧\n"
        "∴ main ⟦⟧ → ∅\n"
        "  ⌁ answer:ℕ ≔ 42\n"
        "  ⟣ answer\n"
        "∎"
    )
    function = module.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    assert isinstance(function.body.nodes[0], astx.VariableDeclaration)


def test_parse_constant_definition() -> None:
    module = parse("∴ answer:ℕ ≔ 42 ∎")
    assert isinstance(module.nodes[0], astx.VariableDeclaration)


def test_missing_end_error() -> None:
    with pytest.raises(ParserException, match="missing block terminator"):
        parse("∴ main ⟦⟧ → ∅ ⟣ 1")


def test_missing_parameter_type_error() -> None:
    with pytest.raises(ParserException, match="expected ':'"):
        parse("∴ id ⟦ value ⟧ → ℕ ⊢ value ∎")


def test_unsupported_reserved_operator_error() -> None:
    with pytest.raises(
        ParserException,
        match="unsupported reserved operator '⍴'",
    ):
        parse("∴ main ⟦⟧ → ∅ ⟣ ⍴ 1 ∎")
