"""
title: Test parser methods.
"""

from textwrap import dedent

import astx
import astx as irx_astx
import pytest

from arx.exceptions import ParserException
from arx.io import ArxIO
from arx.lexer import Lexer, TokenList
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
    assert parser.bin_op_precedence["%"] == 40


@pytest.mark.parametrize(
    "source,grouped",
    [
        ("not a == b", "!(a == b)"),
        ("not a < b + c", "!(a < (b + c))"),
        ("not a and b or c", "((!a) and b) or c"),
        ("a and not b == c", "a and (!(b == c))"),
        ("a || not b && c", "a || ((!b) && c)"),
        ("not not a", "!(!a)"),
        ("!a == b", "(!a) == b"),
        ("a = not b == c", "a = (!(b == c))"),
        ("a + b % c * d / e", "a + (((b % c) * d) / e)"),
        ("-a % b", "(-a) % b"),
        ("a * b % c", "(a * b) % c"),
        ("a + +b", "a + (+b)"),
        ("a - -b", "a - (-b)"),
        ("a + ++b", "a + (++b)"),
        ("a - --b", "a - (--b)"),
    ],
)
def test_prefix_and_remainder_grouping(source: str, grouped: str) -> None:
    """
    title: Word negation binds comparisons while remainder associates left.
    parameters:
      source:
        type: str
      grouped:
        type: str
    """
    expressions: list[astx.AST] = []
    for code in (source, grouped):
        ArxIO.string_to_buffer(code)
        parser = Parser(Lexer().lex())
        parser.tokens.get_next_token()
        expressions.append(parser.parse_expression())
    assert expressions[0].get_struct(simplified=True) == expressions[
        1
    ].get_struct(simplified=True)


@pytest.mark.parametrize(
    "source,message",
    [
        ("a + not b", "Parenthesize 'not'"),
        ("a == not b", "Parenthesize 'not'"),
        ("!not b", "Parenthesize 'not'"),
        ("% a", "requires a left operand"),
        ("a % % b", "requires a left operand"),
        (
            "++return 0",
            "Unary operator '\\+\\+' requires an expression operand",
        ),
        ("--return 0", "Unary operator '--' requires an expression operand"),
    ],
)
def test_invalid_prefix_operand(source: str, message: str) -> None:
    """
    title: Reject misplaced word negation and missing remainder operands.
    parameters:
      source:
        type: str
      message:
        type: str
    """
    ArxIO.string_to_buffer(source)
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match=message):
        parser.parse_expression()


@pytest.mark.parametrize("operator", ["++", "--"])
@pytest.mark.parametrize(
    "source",
    [
        "x{operator}",
        "x{operator}\n",
        "x  {operator}",
        "print(x{operator})",
        "(x){operator}",
        "x{operator} + 1",
        "1 + x{operator}",
        "object.value{operator}",
        "values[0]{operator}",
        "object.method()[0].value{operator}",
        "café{operator}",
        "call(\nx\n){operator}",
        "for i: i32 = 0; i < 3; i{operator}:\n  print(i)\n",
        "fn main() -> i32:\n  x: i32 = 3\n  x{operator}\n  return x\n",
    ],
)
def test_postfix_mutation_reports_operator(source: str, operator: str) -> None:
    """
    title: Unsupported postfix mutation fails at its own operator token.
    parameters:
      source:
        type: str
      operator:
        type: str
    """
    code = source.format(operator=operator)
    before_operator = code.split(operator, 1)[0]
    with pytest.raises(ParserException) as captured:
        _parse_module(code)

    error = captured.value
    assert error.code == "ARX-PARSE-001"
    assert f"Postfix '{operator}' is not supported" in error.message
    assert f"'{operator}x'" in error.message
    assert f"'x = x {operator[0]} 1'" in error.message
    assert error.location is not None
    assert error.location.line == before_operator.count("\n") + 1
    assert error.location.col == len(before_operator.rsplit("\n", 1)[-1]) + 1


@pytest.mark.parametrize("operator", ["++", "--"])
@pytest.mark.parametrize("separator", ["; ", "\n", " # comment\n\n"])
def test_prefix_mutation_after_statement_separator(
    operator: str, separator: str
) -> None:
    """
    title: A new statement's prefix is not the prior expression's postfix.
    parameters:
      operator:
        type: str
      separator:
        type: str
    """
    tree = _parse_module(f"x{separator}{operator}y")
    assert len(tree.nodes) == 2
    assert isinstance(tree.nodes[0], astx.Identifier)
    mutation = tree.nodes[1]
    assert isinstance(mutation, astx.UnaryOp)
    assert mutation.op_code == operator
    assert isinstance(mutation.operand, astx.Identifier)
    assert mutation.operand.name == "y"


@pytest.mark.parametrize("operator", ["+=", "-=", "*=", "/=", "%="])
def test_compound_statement_locations_and_precedence(operator: str) -> None:
    """
    title: Compound statements retain operand locations and normal precedence.
    parameters:
      operator:
        type: str
    """
    tree = _parse_module(f"café {operator} 2 + 3 * 4\n")
    node = tree.nodes[0]
    assert isinstance(node, astx.AugAssign)
    assert node.op_code == operator
    assert node.target.name == "café"
    assert (node.loc.line, node.loc.col) == (1, 6)
    assert (node.target.loc.line, node.target.loc.col) == (1, 1)
    assert isinstance(node.value, astx.BinaryOp)
    assert node.value.op_code == "+"
    assert node.value.lhs.loc.col == 9
    assert isinstance(node.value.rhs, astx.BinaryOp)
    assert node.value.rhs.op_code == "*"


@pytest.mark.parametrize("text", ["+=", ";", ":"])
def test_compound_operator_detection_ignores_literal_contents(
    text: str,
) -> None:
    """
    title: Literal text cannot be consumed as an operator or a missing operand.
    parameters:
      text:
        type: str
    """
    tree = _parse_module(f'x\n"{text}"\n')
    assert len(tree.nodes) == 2
    assert isinstance(tree.nodes[1], astx.LiteralString)
    tree = _parse_module(f'x += "{text}"\n')
    node = tree.nodes[0]
    assert isinstance(node, astx.AugAssign)
    assert isinstance(node.value, astx.LiteralString)


def test_compound_count_update_and_statement_separators() -> None:
    """
    title: Count updates and semicolon-separated statements admit AugAssign.
    """
    tree = _parse_module(
        "fn main() -> i32:\n"
        "  total: i32 = 0\n"
        "  for i: i32 = 0; i < 3; i += 1:\n"
        "    total += i; total *= 2\n"
        "  total %= 5\n"
        "  return total\n"
    )
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    loop = fn.body.nodes[1]
    assert isinstance(loop, astx.ForCountLoopStmt)
    assert isinstance(loop.update, astx.AugAssign)
    assert loop.update.target.name == "i"
    assert all(isinstance(node, astx.AugAssign) for node in loop.body.nodes)
    assert len(loop.body.nodes) == 2
    assert isinstance(fn.body.nodes[2], astx.AugAssign)


@pytest.mark.parametrize(
    "source",
    [
        "obj.field += 1",
        "items[0] += 1",
        "(x) += 1",
        "1 += 2",
        "x + y += 1",
        "f(x += 1)",
        "[x += 1]",
        "return x += 1",
        "if x += 1:\n  0",
        "y: i32 = x += 1",
        "x = y += 1",
        "x += y += 1",
        "x += y = 1",
        "x += (y = 1)",
        "x +=",
        "x +=\ny",
        "x\n+= 1",
        "x +=; y",
        "x += return 1",
        "+= 1",
        "for i: i32 = 0; i += 1; i + 1:\n  0",
    ],
)
def test_compound_assignment_rejects_invalid_surface_contexts(
    source: str,
) -> None:
    """
    title: Unsupported targets and expression contexts fail before analysis.
    parameters:
      source:
        type: str
    """
    with pytest.raises(ParserException) as captured:
        _parse_module(source)
    assert "compound assignment" in captured.value.message.lower()
    assert captured.value.code == "ARX-PARSE-001"
    assert captured.value.location is not None


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
    assert isinstance(expr, astx.LiteralFloat)
    assert expr.value == 1.0

    expr = parser.parse_float_expr()
    assert expr
    assert isinstance(expr, astx.LiteralFloat)
    assert expr.value == 2.5

    ArxIO.string_to_buffer("3.25")
    parser = Parser(lexer.lex())

    parser.tokens.get_next_token()
    expr = parser.parse_float_expr()
    assert expr
    assert isinstance(expr, astx.LiteralFloat)
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
    assert isinstance(expr, astx.LiteralInteger)
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


def test_parse_truncated_function_reports_located_parser_error() -> None:
    """
    title: Truncated signatures fail with a located parser diagnostic.
    """
    ArxIO.string_to_buffer("fn main( -> i32:\n  return 0\n")

    with pytest.raises(ParserException) as exc_info:
        Parser().parse(Lexer().lex())

    assert exc_info.value.code == "ARX-PARSE-001"
    assert exc_info.value.location is not None
    assert "Expected argument name" in str(exc_info.value)


def test_parse_empty_token_list_is_an_empty_module() -> None:
    """
    title: A manually empty token stream does not crash the parser.
    """
    module = Parser().parse(TokenList([]))
    assert isinstance(module, astx.Module)
    assert module.nodes == []


def test_parse_empty_source_is_an_empty_module() -> None:
    """
    title: Empty source is accepted deterministically rather than crashing.
    """
    module = _parse_module("")
    assert module.nodes == []


def test_parser_location_uses_unicode_code_point_columns() -> None:
    """
    title: Parser diagnostics preserve one-based Unicode lexer columns.
    """
    ArxIO.string_to_buffer("fn α( -> i32:\n  return 0\n")  # noqa: RUF001
    with pytest.raises(ParserException) as captured:
        Parser().parse(Lexer().lex())
    assert captured.value.location is not None
    assert captured.value.location.line == 1
    assert captured.value.location.col == 7


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


@pytest.mark.parametrize("with_else", [False, True])
def test_parse_elif_chain(with_else: bool) -> None:
    """
    title: Elif chains use nested IfStmt nodes with real keyword locations.
    parameters:
      with_else:
        type: bool
    """
    source = "if a:\n  first\nelif b:\n  second\nelif café:\n  third\n"
    if with_else:
        source += "else:\n  last\n"
    tree = _parse_module(source + "after\n")
    assert len(tree.nodes) == 2
    node = tree.nodes[0]
    for index, (condition, body) in enumerate(
        [("a", "first"), ("b", "second"), ("café", "third")]
    ):
        assert isinstance(node, astx.IfStmt)
        assert (node.loc.line, node.loc.col) == (index * 2 + 1, 1)
        assert isinstance(node.condition, astx.Identifier)
        assert node.condition.name == condition
        assert len(node.then.nodes) == 1
        assert isinstance(node.then.nodes[0], astx.Identifier)
        assert node.then.nodes[0].name == body
        assert node.else_ is not None
        if index < 2:
            assert len(node.else_.nodes) == 1
            node = node.else_.nodes[0]
    assert isinstance(node, astx.IfStmt)
    assert node.else_ is not None
    if with_else:
        assert len(node.else_.nodes) == 1
        assert isinstance(node.else_.nodes[0], astx.Identifier)
        assert node.else_.nodes[0].name == "last"
    else:
        assert node.else_.nodes == []
    assert isinstance(tree.nodes[1], astx.Identifier)
    assert tree.nodes[1].name == "after"


def test_long_elif_chain_parses_iteratively() -> None:
    """
    title: Sibling elif clauses do not consume recursive parser depth.
    """
    tree = _parse_module("if false:\n  0\n" + "elif false:\n  0\n" * 256)
    node = tree.nodes[0]
    for index in range(257):
        assert isinstance(node, astx.IfStmt)
        assert node.loc.line == 2 * index + 1
        assert node.else_ is not None
        if index < 256:
            assert len(node.else_.nodes) == 1
            node = node.else_.nodes[0]
        else:
            assert node.else_.nodes == []


def test_nested_elif_clauses_preserve_enclosing_blocks() -> None:
    """
    title: Nested chains and loops leave outer clauses and statements intact.
    """
    tree = _parse_module(
        "if outer:\n"
        "  while running:\n"
        "    if inner:\n"
        "      first\n"
        "    elif next:\n"
        "      second\n"
        "elif fallback:\n"
        "  third\n"
        "else:\n"
        "  last\n"
        "after\n"
    )
    assert len(tree.nodes) == 2
    outer = tree.nodes[0]
    assert isinstance(outer, astx.IfStmt)
    loop = outer.then.nodes[0]
    assert isinstance(loop, astx.WhileStmt)
    assert len(loop.body.nodes) == 1
    inner = loop.body.nodes[0]
    assert isinstance(inner, astx.IfStmt)
    assert inner.else_ is not None
    inner_elif = inner.else_.nodes[0]
    assert isinstance(inner_elif, astx.IfStmt)
    assert (inner_elif.loc.line, inner_elif.loc.col) == (5, 5)
    assert inner_elif.else_ is not None
    assert inner_elif.else_.nodes == []
    assert outer.else_ is not None
    outer_elif = outer.else_.nodes[0]
    assert isinstance(outer_elif, astx.IfStmt)
    assert (outer_elif.loc.line, outer_elif.loc.col) == (7, 1)
    assert outer_elif.else_ is not None
    assert isinstance(outer_elif.else_.nodes[0], astx.Identifier)
    assert outer_elif.else_.nodes[0].name == "last"


def test_elif_branch_bindings_do_not_leak() -> None:
    """
    title: Parser collection bindings remain local to each conditional body.
    """
    tree = _parse_module(
        "if first:\n"
        "  values: list[i32] = [1]\n"
        "  values.append(2)\n"
        "elif second:\n"
        "  values.append(3)\n"
        "else:\n"
        "  values.append(4)\n"
        "values.append(5)\n"
    )
    branch = tree.nodes[0]
    assert isinstance(branch, astx.IfStmt)
    assert isinstance(branch.then.nodes[1], astx.ListAppend)
    assert branch.else_ is not None
    alternative = branch.else_.nodes[0]
    assert isinstance(alternative, astx.IfStmt)
    assert isinstance(alternative.then.nodes[0], astx.MethodCall)
    assert alternative.else_ is not None
    assert isinstance(alternative.else_.nodes[0], astx.MethodCall)
    assert isinstance(tree.nodes[1], astx.MethodCall)


@pytest.mark.parametrize(
    "source, message, line, column",
    [
        ("elif true:\n  x\n", "same indentation", 1, 1),
        ("else:\n  x\n", "matching 'if' or 'try'", 1, 1),
        ("if true:\n  x\n  elif false:\n    y\n", "same indentation", 3, 3),
        ("if true:\n  x\n elif false:\n   y\n", "same indentation", 3, 2),
        ("if true:\n  x\nelif:\n  y\n", "Expected a condition", 3, 5),
        ("if true:\n  x\nelif\nfalse:\n  y\n", "Expected a condition", 4, 1),
        (
            "if true:\n  x\nelif return 1:\n  y\n",
            "Expected an expression condition",
            3,
            6,
        ),
        (
            "if true:\n  x\nelif false then\n  y\n",
            "Expected operator ':'",
            3,
            12,
        ),
        (
            "if true:\n  x\nelif false:\nelse:\n  y\n",
            "Expected indentation",
            4,
            1,
        ),
        ("if true:\n  x\nelif false:\n", "Expected indentation", 4, 1),
        ("if true:\n  x\nelse if false:\n  y\n", "use 'elif'", 3, 6),
        (
            "if true:\n  x\nelse:\n  y\nelif false:\n  z\n",
            "must be last",
            5,
            1,
        ),
        (
            "if true:\n  x\nelse:\n  y\nelse:\n  z\n",
            "must be last",
            5,
            1,
        ),
        ("var elif: i32 = 1\n", "Leading variable declaration keywords", 1, 1),
    ],
)
def test_invalid_elif_chain(
    source: str, message: str, line: int, column: int
) -> None:
    """
    title: Malformed clauses fail at the parser boundary with real locations.
    parameters:
      source:
        type: str
      message:
        type: str
      line:
        type: int
      column:
        type: int
    """
    with pytest.raises(ParserException) as captured:
        _parse_module(source)
    error = captured.value
    assert error.code == "ARX-PARSE-001"
    assert message in error.message
    assert error.location is not None
    assert (error.location.line, error.location.col) == (line, column)


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

    with pytest.raises(ParserException) as captured:
        parser.parse(lexer.lex())
    assert captured.value.code == "ARX-PARSE-DOCSTRING-001"


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

    with pytest.raises(
        ParserException,
        match="Invalid module docstring",
    ) as captured:
        parser.parse(lexer.lex())
    assert captured.value.code == "ARX-PARSE-DOCSTRING-001"


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
    assert isinstance(result.value.args[0], astx.LiteralFloat)
    assert isinstance(result.value.args[1], astx.LiteralFloat)


def test_parse_while_stmt() -> None:
    """
    title: Test while statement parsing.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n"
        "  a: i32 = 0\n"
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
        "  for i: i32 = 0; i < 5; i = i + 1:\n"
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
        "  xs: list[i32] = range(0, 3)\n"
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


def test_parse_builtin_cast_and_print() -> None:
    """
    title: Test builtin cast and print node generation.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n  a: i32 = 1\n  print(cast(a, str))\n  return a\n"
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
        "  x: Int = cast(0.0, Int)\n"
        "  ok: bool = isinstance(x, Int)\n"
        "  name: str = type(x)\n"
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
            "  x: Number = cast(0.0, Number)\n"
            "  return 0\n"
        )


def test_cast_result_can_participate_in_binary_expression() -> None:
    """
    title: Cast results are value expressions accepted by binary operators.
    """
    tree = _parse_module(
        "fn main() -> bool:\n"
        "  return cast(2147483648, i32) == cast(2147483648, i32)\n"
    )
    function = tree.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    return_node = function.body.nodes[0]
    assert isinstance(return_node, astx.FunctionReturn)
    assert isinstance(return_node.value, astx.BinaryOp)


@pytest.mark.parametrize("suffix", ["", "\n  ", "\n      # final comment"])
def test_parse_block_with_comment_and_blank_lines(suffix: str) -> None:
    """
    title: Trivia cannot change block or clause attachment, including at EOF.
    parameters:
      suffix:
        type: str
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n"
        "  # section A\n"
        "\n"
        "  a: i32 = 1\n"
        "  if true:\n"
        "    a = 2\n"
        "# dedented comment\n"
        "      # over-indented comment\n"
        "  elif false:\n"
        "    a = 4\n"
        "\n"
        "# comment before final else\n"
        "  else:\n"
        "    a = 3\n"
        "  # section B\n"
        "  return a\n" + suffix
    )
    lexer = Lexer()
    parser = Parser()

    tree = parser.parse(lexer.lex())
    assert len(tree.nodes) == 1
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    assert len(fn.body.nodes) == 3
    assert isinstance(fn.body.nodes[0], astx.VariableDeclaration)
    branch = fn.body.nodes[1]
    assert isinstance(branch, astx.IfStmt)
    assert len(branch.then.nodes) == 1
    assert branch.else_ is not None
    assert len(branch.else_.nodes) == 1
    alternative = branch.else_.nodes[0]
    assert isinstance(alternative, astx.IfStmt)
    assert len(alternative.then.nodes) == 1
    assert alternative.else_ is not None
    assert len(alternative.else_.nodes) == 1
    assert isinstance(fn.body.nodes[2], astx.FunctionReturn)


@pytest.mark.parametrize("modifier", ["", "var :: ", "const :: "])
def test_name_first_binding_modifiers(modifier: str) -> None:
    """
    title: Explicit and implicit binding policies map to reusable ASTx nodes.
    parameters:
      modifier:
        type: str
    """
    module = _parse_module(f"value: {modifier}i32 = 1\n")
    declaration = module.nodes[0]
    assert isinstance(declaration, astx.VariableDeclaration)
    expected = (
        astx.MutabilityKind.constant
        if modifier.startswith("const")
        else astx.MutabilityKind.mutable
    )
    assert declaration.mutability is expected
    function = _parse_module(
        f"fn apply(value: {modifier}i32) -> i32:\n  return value\n"
    ).nodes[0]
    assert isinstance(function, astx.FunctionDef)
    assert function.prototype.args.nodes[0].mutability is expected
    external = _parse_module(
        f"extern apply(value: {modifier}i32) -> i32\n"
    ).nodes[0]
    assert isinstance(external, astx.FunctionPrototype)
    assert external.args.nodes[0].mutability is expected
    class_ = _parse_module(
        "class Operations:\n"
        "  @[public, static]\n"
        f"  fn apply(value: {modifier}i32) -> i32:\n    return value\n"
        "  @[abstract]\n"
        f"  fn abstract_apply(self, value: {modifier}i32) -> i32\n"
        "  @[extern]\n"
        f"  fn external_apply(self, value: {modifier}i32) -> i32\n"
    ).nodes[0]
    assert isinstance(class_, astx.ClassDefStmt)
    for method in class_.methods:
        assert method.prototype.args.nodes[0].mutability is expected
    assert getattr(class_.methods[0].prototype, "is_static", False) is True
    assert getattr(class_.methods[1].prototype, "is_abstract", False) is True
    assert getattr(class_.methods[2].prototype, "is_extern", False) is True


@pytest.mark.parametrize(
    "source, message",
    [
        ("value: const :: i32\n", "requires an explicit initializer"),
        ("value: var const :: i32 = 1\n", "conflicting mutability"),
        ("value: var var :: i32 = 1\n", "duplicate modifier"),
        ("value: typo :: i32 = 1\n", "unknown modifier"),
        ("value: readonly :: i32 = 1\n", "unknown modifier"),
        ("value: const i32 = 1\n", "Expected '::'"),
        ("value: :: i32 = 1\n", "Empty modifier group"),
        ("value: static :: i32 = 1\n", "variable cannot use 'static'"),
        (
            "apply: var :: fn() -> i32:\n  return 0\n",
            "Function declarations use",
        ),
        (
            "extern apply() -> i32:\n  return 0\n",
            "cannot define a body",
        ),
        (
            "fn outer() -> i32:\n  fn inner() -> i32:\n    return 0\n",
            "Nested functions",
        ),
        ("var value: i32 = 1\n", "Leading variable declaration keywords"),
        ("apply: fn() -> i32:\n  return 0\n", "Function declarations use"),
        (
            "apply: const :: fn() -> i32:\n  return 0\n",
            "Function declarations use",
        ),
        ("apply: extern :: fn() -> i32\n", "Function declarations use"),
        (
            "class C:\n  apply: fn(self) -> i32:\n    return 0\n",
            "Method declarations use",
        ),
        (
            "fn apply(value: static :: i32) -> i32:\n  return value\n",
            "parameter cannot use 'static'",
        ),
        ("class C:\n  @[constant]\n  value: i32 = 1\n", "unknown modifier"),
        (
            "class C:\n  @[public]\n  value: i32 = 1\n",
            "Field modifier annotations were replaced",
        ),
    ],
)
def test_name_first_declaration_errors(source: str, message: str) -> None:
    """
    title: Malformed and obsolete declaration forms fail closed.
    parameters:
      source:
        type: str
      message:
        type: str
    """
    with pytest.raises(ParserException, match=message):
        _parse_module(source)


@pytest.mark.parametrize(
    "source", ["x: auto", "x: const :: auto", "class C:\n  x: auto"]
)
def test_inferred_declaration_requires_initializer(source: str) -> None:
    """
    title: An inference request cannot be default-initialized.
    parameters:
      source:
        type: str
    """
    with pytest.raises(
        ParserException, match="requires an explicit initializer"
    ):
        _parse_module(source)


@pytest.mark.parametrize(
    "source",
    [
        "fn apply(x: auto) -> i32:\n  return 0",
        "fn apply() -> auto:\n  return 0",
        "x: list[auto] = []",
        "type Unknown = auto",
    ],
)
def test_auto_is_not_a_general_type(source: str) -> None:
    """
    title: Inference markers cannot appear in general type expressions.
    parameters:
      source:
        type: str
    """
    with pytest.raises(ParserException, match="only allowed on initialized"):
        _parse_module(source)


def test_contextual_modifier_names_remain_usable_as_types() -> None:
    """
    title: Only a double-colon group interprets contextual names as modifiers.
    """
    module = _parse_module(
        "type static = i32\n"
        "type public = i32\n"
        "fn apply(value: public) -> static:\n"
        "  result: static = value\n"
        "  return result\n"
    )
    function = module.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    assert isinstance(function.prototype.args.nodes[0].type_, astx.Int32)
    assert isinstance(function.prototype.return_type, astx.Int32)
    declaration = function.body.nodes[0]
    assert isinstance(declaration, astx.VariableDeclaration)
    assert isinstance(declaration.type_, astx.Int32)


@pytest.mark.parametrize("spacing", ["", " "])
def test_function_head_preserves_name_and_optional_spacing(
    spacing: str,
) -> None:
    """
    title: >-
      Function syntax stays keyword-first while arguments accept modifiers.
    parameters:
      spacing:
        type: str
    """
    function = _parse_module(
        f"fn distance{spacing}(record: const :: str) -> i64:\n"
        "  return len(record)\n"
    ).nodes[0]
    assert isinstance(function, astx.FunctionDef)
    assert function.prototype.name == "distance"
    assert function.prototype.args.nodes[0].name == "record"
    assert (
        function.prototype.args.nodes[0].mutability
        is astx.MutabilityKind.constant
    )


@pytest.mark.parametrize(
    "source, target, line, column",
    [
        ("class auto:\n  value: i32 = 0\n", "class", 1, 7),
        ("type auto = i32\n", "type alias", 1, 6),
        (
            "@<auto: i32>\nfn identity(value: i32) -> i32:\n  return value\n",
            "template parameter",
            1,
            3,
        ),
        (
            "@<Té: i32, auto: i32>\n"
            "fn identity(value: Té) -> Té:\n  return value\n",
            "template parameter",
            1,
            12,
        ),
    ],
)
def test_inference_marker_cannot_name_a_type(
    source: str, target: str, line: int, column: int
) -> None:
    """
    title: Type declarations cannot shadow inference, even when never used.
    parameters:
      source:
        type: str
      target:
        type: str
      line:
        type: int
      column:
        type: int
    """
    with pytest.raises(
        ParserException, match=f"cannot name a {target}"
    ) as err:
        _parse_module(source)
    assert err.value.code == "ARX-PARSE-TYPE-NAME-001"
    assert err.value.location is not None
    assert (err.value.location.line, err.value.location.col) == (line, column)


def test_auto_remains_a_value_identifier_and_inference_marker() -> None:
    """
    title: Restrict type names without reserving auto in value positions.
    """
    module = _parse_module(
        "class Auto:\n  auto: auto = 1\n"
        "type auto_type = i32\n"
        "@<auto_T: auto_type>\n"
        "fn identity(auto: auto_T) -> auto_T:\n  return auto\n"
        "fn auto(value: auto_type) -> auto_type:\n  return value\n"
        "fn apply() -> i32:\n  auto: auto = auto(1)\n  return auto\n"
    )
    class_ = module.nodes[0]
    assert isinstance(class_, astx.ClassDefStmt)
    assert class_.name == "Auto"
    assert class_.attributes[0].name == "auto"
    assert isinstance(class_.attributes[0].type_, astx.InferredType)
    identity = module.nodes[1]
    assert isinstance(identity, astx.FunctionDef)
    assert identity.prototype.args.nodes[0].name == "auto"
    assert isinstance(
        identity.prototype.args.nodes[0].type_, astx.TemplateTypeVar
    )
    function = module.nodes[2]
    assert isinstance(function, astx.FunctionDef)
    assert function.prototype.name == "auto"
    apply = module.nodes[3]
    assert isinstance(apply, astx.FunctionDef)
    declaration = apply.body.nodes[0]
    assert isinstance(declaration, astx.VariableDeclaration)
    assert declaration.name == "auto"
    assert isinstance(declaration.type_, astx.InferredType)
