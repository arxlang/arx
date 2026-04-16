"""
title: Test parser methods.
"""

from textwrap import dedent

import astx
import irx.astx as irx_astx
import pytest

from arx.exceptions import ParserException
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser


def _parse_module(code: str, module_name: str = "main") -> astx.Module:
    """
    title: Parse one module-sized source snippet.
    parameters:
      code:
        type: str
      module_name:
        type: str
    returns:
      type: astx.Module
    """
    ArxIO.string_to_buffer(code)
    tree = Parser().parse(Lexer().lex(), module_name)
    assert isinstance(tree, astx.Module)
    return tree


def test_binop_precedence() -> None:
    """
    title: Test BinOp precedence.
    """
    lexer = Lexer()
    parser = Parser(lexer.lex())

    assert parser.bin_op_precedence["="] == 2
    assert parser.bin_op_precedence["<"] == 10
    assert parser.bin_op_precedence[">"] == 10
    assert parser.bin_op_precedence["<="] == 10
    assert parser.bin_op_precedence[">="] == 10
    assert parser.bin_op_precedence["=="] == 10
    assert parser.bin_op_precedence["!="] == 10
    assert parser.bin_op_precedence["+"] == 20
    assert parser.bin_op_precedence["-"] == 20
    assert parser.bin_op_precedence["*"] == 40
    assert parser.bin_op_precedence["/"] == 40


def test_parse_float_expr() -> None:
    """
    title: Test gettok for main tokens.
    """
    ArxIO.string_to_buffer("1.0 2.5")
    lexer = Lexer()
    parser = Parser(lexer.lex())

    parser.tokens.get_next_token()
    expr = parser.parse_float_expr()
    assert expr
    assert isinstance(expr, astx.LiteralFloat32)
    assert expr.value == 1.0

    expr = parser.parse_float_expr()
    assert expr
    assert isinstance(expr, astx.LiteralFloat32)
    assert expr.value == 2.5

    ArxIO.string_to_buffer("3.25")
    parser = Parser(lexer.lex())

    parser.tokens.get_next_token()
    expr = parser.parse_float_expr()
    assert expr
    assert isinstance(expr, astx.LiteralFloat32)
    assert expr.value == 3.25


def test_parse_int_expr() -> None:
    """
    title: Test integer literal parsing.
    """
    ArxIO.string_to_buffer("7")
    lexer = Lexer()
    parser = Parser(lexer.lex())

    parser.tokens.get_next_token()
    expr = parser.parse_int_expr()
    assert isinstance(expr, astx.LiteralInt32)
    assert expr.value == 7


def test_parse() -> None:
    """
    title: Test gettok for main tokens.
    """
    ArxIO.string_to_buffer(
        "if 1 > 2:\n" + "  a = 1\n" + "else:\n" + "  a = 2\n"
    )
    lexer = Lexer()
    parser = Parser()

    expr = parser.parse(lexer.lex())
    assert expr
    assert isinstance(expr, astx.Module)


def test_parse_if_stmt() -> None:
    """
    title: Test gettok for main tokens.
    """
    ArxIO.string_to_buffer(
        "if 1 > 2:\n" + "  a = 1\n" + "else:\n" + "  a = 2\n"
    )

    lexer = Lexer()
    parser = Parser(lexer.lex())

    parser.tokens.get_next_token()
    expr = parser.parse_primary()
    assert expr
    assert isinstance(expr, astx.IfStmt)
    assert isinstance(expr.condition, astx.BinaryOp)
    assert isinstance(expr.then, astx.Block)
    assert isinstance(expr.then.nodes[0], astx.BinaryOp)
    assert isinstance(expr.else_, astx.Block)
    assert isinstance(expr.else_.nodes[0], astx.BinaryOp)


def test_parse_fn() -> None:
    """
    title: Test gettok for main tokens.
    """
    ArxIO.string_to_buffer(
        "fn math(x: i32) -> i32:\n"
        + "  if 1 > 2:\n"
        + "    a = 1\n"
        + "  else:\n"
        + "    a = 2\n"
        + "  return a\n"
    )

    lexer = Lexer()
    parser = Parser(lexer.lex())

    parser.tokens.get_next_token()
    expr = parser.parse_function()
    assert expr
    assert isinstance(expr, astx.FunctionDef)
    assert isinstance(expr.prototype, astx.FunctionPrototype)
    assert isinstance(expr.prototype.args[0], astx.Argument)
    assert isinstance(expr.prototype.args[0].type_, astx.Int32)
    assert isinstance(expr.body, astx.Block)
    assert isinstance(expr.body.nodes[0], astx.IfStmt)
    assert isinstance(expr.body.nodes[0].condition, astx.BinaryOp)
    assert isinstance(expr.body.nodes[0].then, astx.Block)
    assert isinstance(expr.body.nodes[0].then.nodes[0], astx.BinaryOp)
    assert isinstance(expr.body.nodes[0].else_, astx.Block)
    assert isinstance(expr.body.nodes[0].else_.nodes[0], astx.BinaryOp)
    assert isinstance(expr.body.nodes[1], astx.FunctionReturn)
    assert isinstance(expr.body.nodes[1].value, astx.Identifier)
    assert expr.body.nodes[1].value.name == "a"


def test_parse_module_docstring() -> None:
    """
    title: Test module docstring placement and parser ignore behavior.
    """
    ArxIO.string_to_buffer(
        "```\n"
        "title: Module docs\n"
        "summary: Main module reference\n"
        "```\n"
        "fn main() -> i32:\n"
        "  return 1\n"
    )

    lexer = Lexer()
    parser = Parser()
    tree = parser.parse(lexer.lex())

    assert isinstance(tree, astx.Module)
    assert len(tree.nodes) == 1
    assert isinstance(tree.nodes[0], astx.FunctionDef)


def test_parse_module_docstring_must_start_first_line() -> None:
    """
    title: Test module docstring must start at line 1, column 1.
    """
    ArxIO.string_to_buffer(
        "  ```\n  title: module docs\n  ```\nfn main() -> i32:\n  return 1\n"
    )

    lexer = Lexer()
    parser = Parser()

    with pytest.raises(ParserException):
        parser.parse(lexer.lex())


def test_parse_function_docstring() -> None:
    """
    title: Test function docstring as first body statement.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n"
        "  ```\n"
        "  title: Function docs\n"
        "  summary: Function summary\n"
        "  ```\n"
        "  return 1\n"
    )

    lexer = Lexer()
    parser = Parser(lexer.lex())

    parser.tokens.get_next_token()
    expr = parser.parse_function()

    assert isinstance(expr, astx.FunctionDef)
    assert len(expr.body.nodes) == 1
    assert isinstance(expr.body.nodes[0], astx.FunctionReturn)


def test_parse_function_docstring_must_be_first_stmt() -> None:
    """
    title: Test function docstring invalid placement after expressions.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n  return 1\n  ```\n  title: Function docs\n  ```\n"
    )

    lexer = Lexer()
    parser = Parser()

    with pytest.raises(ParserException):
        parser.parse(lexer.lex())


def test_parse_module_docstring_invalid_douki_schema() -> None:
    """
    title: Test module docstring validation against Douki schema.
    """
    ArxIO.string_to_buffer(
        "```\nsummary: Missing required title\n```\n"
        "fn main() -> i32:\n"
        "  return 1\n"
    )

    lexer = Lexer()
    parser = Parser()

    with pytest.raises(ParserException, match="Invalid module docstring"):
        parser.parse(lexer.lex())


def test_parse_function_docstring_invalid_douki_schema() -> None:
    """
    title: Test function docstring validation against Douki schema.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n"
        "  ```\n"
        "  bad_field: this is not allowed by schema\n"
        "  ```\n"
        "  return 1\n"
    )

    lexer = Lexer()
    parser = Parser()

    with pytest.raises(ParserException, match="Invalid function docstring"):
        parser.parse(lexer.lex())


def test_parse_typed_function_signature() -> None:
    """
    title: Test typed function signature parsing.
    """
    ArxIO.string_to_buffer(
        "fn main(arg1: i32, arg2: str) -> i32:\n  return arg1\n"
    )
    lexer = Lexer()
    parser = Parser(lexer.lex())

    parser.tokens.get_next_token()
    fn = parser.parse_function()

    assert isinstance(fn, astx.FunctionDef)
    assert isinstance(fn.prototype.args[0], astx.Argument)
    assert fn.prototype.args[0].name == "arg1"
    assert isinstance(fn.prototype.args[0].type_, astx.Int32)
    assert isinstance(fn.prototype.args[1].type_, astx.String)
    assert isinstance(fn.prototype.return_type, astx.Int32)


@pytest.mark.parametrize(
    ("code", "stmt_type", "expected_module", "expected_names"),
    [
        (
            "import std.math\n",
            irx_astx.ImportStmt,
            None,
            [("std.math", "")],
        ),
        (
            "import std.math as math\n",
            irx_astx.ImportStmt,
            None,
            [("std.math", "math")],
        ),
        (
            "import sin from std.math\n",
            irx_astx.ImportFromStmt,
            "std.math",
            [("sin", "")],
        ),
        (
            "import sin as sine from std.math\n",
            irx_astx.ImportFromStmt,
            "std.math",
            [("sin", "sine")],
        ),
        (
            "import (sin, cos) from std.math\n",
            irx_astx.ImportFromStmt,
            "std.math",
            [("sin", ""), ("cos", "")],
        ),
        (
            "import (sin, cos, tan as tangent) from std.math\n",
            irx_astx.ImportFromStmt,
            "std.math",
            [("sin", ""), ("cos", ""), ("tan", "tangent")],
        ),
        (
            dedent(
                """
                import (
                  sin,
                  cos,
                  tan as tangent,
                ) from std.math
                """
            ).lstrip(),
            irx_astx.ImportFromStmt,
            "std.math",
            [("sin", ""), ("cos", ""), ("tan", "tangent")],
        ),
        (
            dedent(
                """
                import (
                  sin,
                  cos,
                ) from std.math.trig
                """
            ).lstrip(),
            irx_astx.ImportFromStmt,
            "std.math.trig",
            [("sin", ""), ("cos", "")],
        ),
    ],
)
def test_parse_import_statements(
    code: str,
    stmt_type: type[astx.AST],
    expected_module: str | None,
    expected_names: list[tuple[str, str]],
) -> None:
    """
    title: Import syntax should build the expected IRx AST nodes.
    parameters:
      code:
        type: str
      stmt_type:
        type: type[astx.AST]
      expected_module:
        type: str | None
      expected_names:
        type: list[tuple[str, str]]
    """
    tree = _parse_module(code)

    assert len(tree.nodes) == 1
    node = tree.nodes[0]
    assert isinstance(node, stmt_type)
    assert isinstance(node, (irx_astx.ImportStmt, irx_astx.ImportFromStmt))
    assert [
        (alias.name, alias.asname) for alias in node.names
    ] == expected_names

    if isinstance(node, irx_astx.ImportFromStmt):
        assert node.module == expected_module
    else:
        assert expected_module is None


@pytest.mark.parametrize(
    ("code", "match"),
    [
        (
            "import () from std.math\n",
            "empty grouped imports are not allowed",
        ),
        (
            "import from std.math\n",
            "Expected module path or imported name after 'import'.",
        ),
        (
            "import as x from std.math\n",
            "alias requires an import target before 'as'",
        ),
        (
            "import (sin as) from std.math\n",
            "Expected alias name after 'as'.",
        ),
        (
            "import (sin, )\n",
            "Grouped imports require 'from <module.path>'.",
        ),
        (
            "import sin, cos from std.math\n",
            "Grouped imports require parentheses.",
        ),
        (
            "import std.\n",
            "Expected identifier after '.' in module path.",
        ),
        (
            "import std.math from other.module\n",
            "Module imports do not use 'from'.",
        ),
        (
            "fn main() -> i32:\n  import std.math\n  return 0\n",
            "Import statements are only allowed at module scope.",
        ),
    ],
)
def test_parse_invalid_import_syntax(code: str, match: str) -> None:
    """
    title: Invalid import syntax should raise clear parser errors.
    parameters:
      code:
        type: str
      match:
        type: str
    """
    with pytest.raises(ParserException, match=match):
        _parse_module(code)


def test_parse_while_stmt() -> None:
    """
    title: Test while statement parsing.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n"
        "  var a: i32 = 0\n"
        "  while a < 10:\n"
        "    a = a + 1\n"
        "  return a\n"
    )
    lexer = Lexer()
    parser = Parser()

    tree = parser.parse(lexer.lex())
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    assert isinstance(fn.body.nodes[1], astx.WhileStmt)


def test_parse_for_count_stmt() -> None:
    """
    title: Test count-style for parsing.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n"
        "  for var i: i32 = 0; i < 5; i = i + 1:\n"
        "    return i\n"
    )
    lexer = Lexer()
    parser = Parser()

    tree = parser.parse(lexer.lex())
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    assert isinstance(fn.body.nodes[0], astx.ForCountLoopStmt)


def test_parse_for_range_slice_style() -> None:
    """
    title: Test range-style for parsing with colon-separated bounds.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n  for j in (0:5:1):\n    return j\n"
    )
    lexer = Lexer()
    parser = Parser()

    tree = parser.parse(lexer.lex())
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    assert isinstance(fn.body.nodes[0], astx.ForRangeLoopStmt)


def test_parse_for_range_tuple_style_is_rejected() -> None:
    """
    title: Tuple-style for range must be rejected.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n  for j in (0, 5, 1):\n    return j\n"
    )
    lexer = Lexer()
    parser = Parser()

    with pytest.raises(ParserException):
        parser.parse(lexer.lex())


def test_parse_builtin_cast_and_print() -> None:
    """
    title: Test builtin cast and print node generation.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n"
        "  var a: i32 = 1\n"
        "  print(cast(a, str))\n"
        "  return a\n"
    )
    lexer = Lexer()
    parser = Parser()

    tree = parser.parse(lexer.lex())
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    assert isinstance(fn.body.nodes[1], irx_astx.PrintExpr)


def test_parse_block_with_comment_and_blank_lines() -> None:
    """
    title: Test block parsing across comment/blank lines.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n"
        "  # section A\n"
        "\n"
        "  var a: i32 = 1\n"
        "  # section B\n"
        "  return a\n"
    )
    lexer = Lexer()
    parser = Parser()

    tree = parser.parse(lexer.lex())
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    assert isinstance(fn.body.nodes[0], astx.VariableDeclaration)
    assert isinstance(fn.body.nodes[1], astx.FunctionReturn)
