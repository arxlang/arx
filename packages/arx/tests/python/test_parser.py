"""
title: Test parser methods.
"""

from textwrap import dedent

import astx
import astx as irx_astx
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


def test_parse_assert_stmt() -> None:
    """
    title: Test parsing `assert <expr>` into astx.AssertStmt.
    """
    tree = _parse_module(
        dedent(
            """
            fn test_ok() -> none:
              assert 1 == 1
              return none
            """
        ).lstrip()
    )

    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    statement = fn.body.nodes[0]
    assert isinstance(statement, irx_astx.AssertStmt)
    assert isinstance(statement.condition, astx.BinaryOp)
    assert statement.message is None


def test_parse_assert_stmt_with_string_message() -> None:
    """
    title: Test parsing `assert <expr>, <string>` messages.
    """
    tree = _parse_module(
        dedent(
            """
            fn test_ok() -> none:
              assert 1 == 1, "still ok"
              return none
            """
        ).lstrip()
    )

    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    statement = fn.body.nodes[0]
    assert isinstance(statement, irx_astx.AssertStmt)
    assert isinstance(statement.message, astx.LiteralString)
    assert statement.message.value == "still ok"


def test_parse_assert_stmt_rejects_non_string_message() -> None:
    """
    title: Test assertion messages remain string-literal-only in Arx v1.
    """
    with pytest.raises(
        ParserException,
        match="Assertion messages must be string literals",
    ):
        _parse_module(
            dedent(
                """
                fn test_bad() -> none:
                  assert 1 == 1, 42
                  return none
                """
            ).lstrip()
        )


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
    (
        "code",
        "stmt_type",
        "expected_module",
        "expected_level",
        "expected_names",
    ),
    [
        (
            "import std.math\n",
            irx_astx.ImportStmt,
            None,
            0,
            [("std.math", "")],
        ),
        (
            "import std.math as math\n",
            irx_astx.ImportStmt,
            None,
            0,
            [("std.math", "math")],
        ),
        (
            "import sin from std.math\n",
            irx_astx.ImportFromStmt,
            "std.math",
            0,
            [("sin", "")],
        ),
        (
            "import sin as sine from std.math\n",
            irx_astx.ImportFromStmt,
            "std.math",
            0,
            [("sin", "sine")],
        ),
        (
            "import (sin, cos) from std.math\n",
            irx_astx.ImportFromStmt,
            "std.math",
            0,
            [("sin", ""), ("cos", "")],
        ),
        (
            "import (sin, cos, tan as tangent) from std.math\n",
            irx_astx.ImportFromStmt,
            "std.math",
            0,
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
            0,
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
            0,
            [("sin", ""), ("cos", "")],
        ),
        (
            "import sum2 from .stats\n",
            irx_astx.ImportFromStmt,
            "stats",
            1,
            [("sum2", "")],
        ),
        (
            "import (sum2, mean2) from ..math.stats\n",
            irx_astx.ImportFromStmt,
            "math.stats",
            2,
            [("sum2", ""), ("mean2", "")],
        ),
    ],
)
def test_parse_import_statements(
    code: str,
    stmt_type: type[astx.AST],
    expected_module: str | None,
    expected_level: int,
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
      expected_level:
        type: int
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
        assert node.level == expected_level
    else:
        assert expected_module is None
        assert expected_level == 0


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
            "import sum2 from .\n",
            "Relative imports require a module path after leading '.'.",
        ),
        (
            "import sum2 from ..\n",
            "Relative imports require a module path after leading '.'.",
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


def test_parse_module_namespace_member_reference() -> None:
    """
    title: Namespace-style member references parse as field access.
    """
    tree = _parse_module(
        dedent(
            """
            import samplepkg.stats as stats

            fn main() -> f64:
              return stats.sum2
            """
        ).lstrip()
    )

    assert isinstance(tree.nodes[0], irx_astx.ImportStmt)
    import_stmt = tree.nodes[0]
    assert import_stmt.names[0].name == "samplepkg.stats"
    assert import_stmt.names[0].asname == "stats"

    fn = tree.nodes[1]
    assert isinstance(fn, astx.FunctionDef)
    result = fn.body.nodes[0]
    assert isinstance(result, astx.FunctionReturn)
    assert isinstance(result.value, irx_astx.FieldAccess)
    assert isinstance(result.value.value, astx.Identifier)
    assert result.value.value.name == "stats"
    assert result.value.field_name == "sum2"


def test_parse_module_namespace_member_call() -> None:
    """
    title: Namespace-style member calls parse as method calls.
    """
    tree = _parse_module(
        dedent(
            """
            import samplepkg.stats as stats

            fn main() -> f64:
              return stats.sum2(1.0, 2.0)
            """
        ).lstrip()
    )

    assert isinstance(tree.nodes[0], irx_astx.ImportStmt)
    import_stmt = tree.nodes[0]
    assert import_stmt.names[0].name == "samplepkg.stats"
    assert import_stmt.names[0].asname == "stats"

    fn = tree.nodes[1]
    assert isinstance(fn, astx.FunctionDef)
    result = fn.body.nodes[0]
    assert isinstance(result, astx.FunctionReturn)
    assert isinstance(result.value, irx_astx.MethodCall)
    assert isinstance(result.value.receiver, astx.Identifier)
    assert result.value.receiver.name == "stats"
    assert result.value.method_name == "sum2"
    assert len(result.value.args) == 2
    assert isinstance(result.value.args[0], astx.LiteralFloat32)
    assert isinstance(result.value.args[1], astx.LiteralFloat32)


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


def test_parse_for_range_builtin_call() -> None:
    """
    title: Test for-in parsing with builtin range calls.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n  for j in range(0, 5):\n    return j\n"
    )
    lexer = Lexer()
    parser = Parser()

    tree = parser.parse(lexer.lex())
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    loop = fn.body.nodes[0]
    assert isinstance(loop, irx_astx.ForInLoopStmt)
    assert isinstance(loop.target, astx.Identifier)
    assert loop.target.name == "j"
    assert isinstance(loop.iterable, astx.FunctionCall)
    assert loop.iterable.fn == "range"
    assert isinstance(loop.body.nodes[0], astx.FunctionReturn)
    assert isinstance(loop.body.nodes[0].value, astx.Identifier)
    assert loop.body.nodes[0].value.name == "j"


def test_parse_for_in_list_variable() -> None:
    """
    title: Test generic for-in parsing with one list variable.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n"
        "  var xs: list[i32] = range(0, 3)\n"
        "  for value in xs:\n"
        "    return value\n"
        "  return 0\n"
    )
    lexer = Lexer()
    parser = Parser()

    tree = parser.parse(lexer.lex())
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    assert isinstance(fn.body.nodes[1], irx_astx.ForInLoopStmt)

    loop = fn.body.nodes[1]
    assert isinstance(loop, irx_astx.ForInLoopStmt)
    assert isinstance(loop.target, astx.Identifier)
    assert loop.target.name == "value"
    assert isinstance(loop.iterable, astx.Identifier)
    assert loop.iterable.name == "xs"
    assert isinstance(loop.body.nodes[0], astx.FunctionReturn)
    assert isinstance(loop.body.nodes[0].value, astx.Identifier)
    assert loop.body.nodes[0].value.name == "value"


def test_parse_for_removed_colon_range_syntax_is_rejected() -> None:
    """
    title: Removed colon range syntax must be rejected with guidance.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n  for j in (0:5:1):\n    return j\n"
    )
    lexer = Lexer()
    parser = Parser()

    with pytest.raises(
        ParserException,
        match="Colon range syntax was removed",
    ):
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


def test_parse_type_alias_and_union_signature() -> None:
    """
    title: Type aliases should resolve in union signatures.
    """
    tree = _parse_module(
        "type Number = i32 | i64\n"
        "fn widen(x: Number) -> i32 | i64:\n"
        "  return x\n"
    )

    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    arg_type = fn.prototype.args[0].type_
    ret_type = fn.prototype.return_type
    assert isinstance(arg_type, astx.UnionType)
    assert arg_type.alias_name == "Number"
    assert [type(member) for member in arg_type.members] == [
        astx.Int32,
        astx.Int64,
    ]
    assert isinstance(ret_type, astx.UnionType)


def test_parse_type_alias_with_cast_isinstance_and_typeof() -> None:
    """
    title: Type aliases should work with type-aware builtins.
    """
    tree = _parse_module(
        "type Int = i32\n"
        "fn main() -> i32:\n"
        "  var x: Int = cast(0.0, Int)\n"
        "  var ok: bool = isinstance(x, Int)\n"
        "  var name: str = type(x)\n"
        "  return x\n"
    )

    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    cast_decl = fn.body.nodes[0]
    assert isinstance(cast_decl, astx.VariableDeclaration)
    assert isinstance(cast_decl.value, irx_astx.Cast)
    isinstance_decl = fn.body.nodes[1]
    assert isinstance(isinstance_decl, astx.VariableDeclaration)
    assert isinstance(isinstance_decl.value, irx_astx.IsInstanceExpr)
    type_decl = fn.body.nodes[2]
    assert isinstance(type_decl, astx.VariableDeclaration)
    assert isinstance(type_decl.value, irx_astx.TypeOfExpr)


def test_parse_type_alias_rejects_builtin_shadowing() -> None:
    """
    title: Type aliases should not shadow parser-level builtins.
    """
    with pytest.raises(ParserException, match="shadows a built-in"):
        _parse_module("type cast = i32\n")


def test_parse_cast_rejects_union_target() -> None:
    """
    title: Cast should reject union target types until runtime unions exist.
    """
    with pytest.raises(ParserException, match="union target types"):
        _parse_module(
            "type Number = i32 | i64\n"
            "fn main() -> i32:\n"
            "  var x: Number = cast(0.0, Number)\n"
            "  return 0\n"
        )


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
