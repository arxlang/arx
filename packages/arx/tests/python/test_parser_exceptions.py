"""
title: Exception syntax, clause boundaries, and semantic resolution.
"""

from pathlib import Path

import astx
import pytest

from arx.exceptions import ParserException
from arx.io import ArxIO
from arx.lexer import Lexer, TokenKind
from arx.main import FileImportResolver, inject_ambient_builtin_imports
from arx.parser import Parser
from irx.analysis import ParsedModule, analyze_modules
from public import private


@private
def parse_exception_source(body: str) -> astx.Module:
    """
    title: Parse a documented exception function.
    parameters:
      body:
        type: str
    returns:
      type: astx.Module
    """
    source = (
        "```\ntitle: Exception syntax fixture\n```\n"
        "fn main() -> i32:\n"
        + "\n".join("  " + line for line in body.splitlines())
        + "\n"
    )
    ArxIO.string_to_buffer(source)
    return Parser().parse(Lexer().lex(), "exceptions")


@private
def function_statements(module: astx.Module) -> list[astx.AST]:
    """
    title: Require a parsed function before inspecting its body.
    parameters:
      module:
        type: astx.Module
    returns:
      type: list[astx.AST]
    """
    function = module.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    return list(function.body.nodes)


@pytest.mark.parametrize(
    ("word", "kind"),
    [
        ("try", TokenKind.kw_try),
        ("except", TokenKind.kw_except),
        ("finally", TokenKind.kw_finally),
        ("raise", TokenKind.kw_raise),
        ("from", TokenKind.identifier),
        ("as", TokenKind.identifier),
        ("Exception", TokenKind.identifier),
        ("ValueError", TokenKind.identifier),
        ("raised", TokenKind.identifier),
    ],
)
def test_exception_lexical_contract(word: str, kind: TokenKind) -> None:
    """
    title: Reserve statements without reserving exception class names.
    parameters:
      word:
        type: str
      kind:
        type: TokenKind
    """
    ArxIO.string_to_buffer(word)
    assert Lexer().get_token().kind is kind


def test_try_preserves_clause_order_and_locations() -> None:
    """
    title: The parser retains types, causes, bindings, and each clause body.
    """
    module = parse_exception_source(
        "try:\n"
        '  raise ValueError("bad") from none\n'
        "except (ValueError, errors.Problem) as érror:\n"
        "  raise\n"
        "else:\n"
        "  return 1\n"
        "finally:\n"
        "  print(2)\n"
        "return 0"
    )
    statements = function_statements(module)
    assert len(statements) == 2
    node = statements[0]
    assert isinstance(node, astx.ExceptionHandlerStmt)
    assert (node.loc.line, node.loc.col) == (5, 3)
    raised = node.body.nodes[0]
    assert isinstance(raised, astx.ThrowStmt)
    assert isinstance(raised.cause, astx.LiteralNone)
    assert raised.loc.col == 5
    handler = node.handlers.nodes[0]
    assert handler.name is not None
    assert handler.name.name == "érror"
    assert handler.types is not None
    assert len(handler.types.nodes) == 2
    assert isinstance(handler.types.nodes[1], astx.FieldAccess)
    reraised = handler.body.nodes[0]
    assert isinstance(reraised, astx.ThrowStmt)
    assert reraised.exception is None
    assert node.else_body is not None
    assert node.finally_handler is not None
    assert node.get_struct()


@pytest.mark.parametrize(
    "body",
    [
        "raise\nreturn 0",
        "raise; return 0",
        "raise # keep the next statement\nreturn 0",
        'raise ValueError("bad")\nreturn 0',
        'raise ValueError("bad") from previous\nreturn 0',
    ],
)
def test_raise_does_not_consume_next_statement(body: str) -> None:
    """
    title: Bare and explicit raises stop at their statement boundary.
    parameters:
      body:
        type: str
    """
    statements = function_statements(parse_exception_source(body))
    assert len(statements) == 2
    assert isinstance(statements[0], astx.ThrowStmt)
    assert isinstance(statements[1], astx.FunctionReturn)


def test_nested_try_and_if_attach_clauses_by_indentation() -> None:
    """
    title: Inner if and outer try clauses cannot steal each other's else.
    """
    module = parse_exception_source(
        "try:\n"
        "  if true:\n"
        "    try:\n"
        "      raise\n"
        "    finally:\n"
        "      print(1)\n"
        "  else:\n"
        "    print(2)\n"
        "except Exception:\n"
        "  print(3)\n"
        "else:\n"
        "  print(4)\n"
        "return 0"
    )
    node = function_statements(module)[0]
    assert isinstance(node, astx.ExceptionHandlerStmt)
    branch = node.body.nodes[0]
    assert isinstance(branch, astx.IfStmt)
    inner = branch.then.nodes[0]
    assert isinstance(inner, astx.ExceptionHandlerStmt)
    assert inner.finally_handler is not None
    assert not inner.handlers.nodes
    assert len(node.handlers.nodes) == 1
    assert node.else_body is not None


@pytest.mark.parametrize(
    "header", ["except:", "except Exception:", "except (A, B,):"]
)
def test_handler_forms(header: str) -> None:
    """
    title: Bare, single-type, and parenthesized handlers construct ASTx nodes.
    parameters:
      header:
        type: str
    """
    module = parse_exception_source(
        "try:\n  raise\n" + header + "\n  return 1\nreturn 0"
    )
    node = function_statements(module)[0]
    assert isinstance(node, astx.ExceptionHandlerStmt)
    assert len(node.handlers.nodes) == 1


@pytest.mark.parametrize(
    "body",
    [
        "try:\n  print(0)\nreturn 0",
        "try:\n  print(0)\nelse:\n  print(1)",
        "except Exception:\n  print(0)",
        "finally:\n  print(0)",
        "try:\n  raise\nexcept as error:\n  return 0",
        "try:\n  raise\nexcept ():\n  return 0",
        "try:\n  raise\nexcept* Exception:\n  return 0",
        "try:\n  raise\nexcept Exception() :\n  return 0",
        "try:\n  raise\nexcept A, B:\n  return 0",
        "try:\n  raise\nexcept A as 4:\n  return 0",
        "try:\n  raise\nexcept A.:\n  return 0",
        "try:\n  raise\nexcept:\n  return 1\nexcept A:\n  return 2",
        "try:\n  raise\nfinally:\n  print(0)\nexcept A:\n  return 1",
        "try:\n  raise\nfinally:\n  print(0)\nfinally:\n  print(1)",
        "try:\n  raise\nexcept A:\n  print(0)\nelse:\n  print(1)\n"
        "else:\n  print(2)",
        "try:\n  raise\n except A:\n  print(0)",
        "raise from none",
        "raise error from\nreturn 0",
        "raise error extra",
        "raise error from cause from other",
        "var value: i32 = raise error",
        "return raise error",
        "print(raise error)",
        "var value: i32 = try:\n  return 1\nfinally:\n  return 2",
    ],
)
def test_malformed_exception_statements_are_located(body: str) -> None:
    """
    title: Reject malformed clauses and statement use in expression positions.
    parameters:
      body:
        type: str
    """
    with pytest.raises(ParserException) as caught:
        parse_exception_source(body)
    assert caught.value.location is not None
    assert caught.value.location.line > 0
    assert caught.value.location.col > 0


def test_exception_source_receives_resolved_semantics() -> None:
    """
    title: Parsed exception syntax receives resolved propagation metadata.
    """
    module = parse_exception_source(
        "try:\n  raise\nexcept Exception:\n  return 1\nreturn 0"
    )
    region = function_statements(module)[0]
    analyze_modules(
        ParsedModule(module.name, inject_ambient_builtin_imports(module)),
        FileImportResolver(()),
    )
    assert region.semantic.resolved_try is not None
    assert region.body.nodes[0].semantic.resolved_raise is not None


def test_exception_fixture_resolves_nominal_types() -> None:
    """
    title: The documented fixture resolves type alternatives and cause mode.
    """
    fixture = Path(__file__).parents[1] / "fixtures" / "exceptions.x"
    ArxIO.string_to_buffer(fixture.read_text())
    module = Parser().parse(Lexer().lex(), "exceptions_fixture")
    assert len(module.nodes) == 2
    session = analyze_modules(
        ParsedModule(module.name, inject_ambient_builtin_imports(module)),
        FileImportResolver(()),
    )
    assert "ValueError" in session.runtime_exception_types


@pytest.mark.parametrize(
    "suffix", ["", "class Next:\n  ```\n  title: Next\n  ```\n"]
)
def test_docstring_only_exception_subclasses(suffix: str) -> None:
    """
    title: Nominal empty subclasses finish at either dedent or end of input.
    parameters:
      suffix:
        type: str
    """
    source = (
        "```\ntitle: Empty exception classes\n```\n"
        "class Problem(ValueError):\n  ```\n  title: Problem\n  ```\n" + suffix
    )
    ArxIO.string_to_buffer(source)
    module = Parser().parse(Lexer().lex(), "empty_exceptions")
    problem = module.nodes[0]
    assert isinstance(problem, astx.ClassDefStmt)
    assert not problem.attributes.nodes
    assert not problem.methods.nodes


def test_ambient_exception_annotations_resolve_nominally() -> None:
    """
    title: Annotated saved exceptions use ordinary nominal class resolution.
    """
    module = parse_exception_source(
        'var saved: Exception = ValueError("saved")\n'
        "try:\n  raise saved\nexcept Exception:\n  return 1"
    )
    analyze_modules(
        ParsedModule(module.name, inject_ambient_builtin_imports(module)),
        FileImportResolver(()),
    )
