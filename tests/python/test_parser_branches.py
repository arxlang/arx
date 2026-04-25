"""
title: Additional parser branch coverage tests.
"""

from __future__ import annotations

from typing import cast

import pytest

from arx.exceptions import ParserException
from arx.io import ArxIO
from arx.lexer import Lexer, Token, TokenKind, TokenList
from arx.parser import Parser
from arx.tensor import tensor_shape, tensor_type
from irx import astx


def _parse(code: str) -> astx.Module:
    """
    title: Parse source text into an AST module.
    parameters:
      code:
        type: str
    returns:
      type: astx.Module
    """
    ArxIO.string_to_buffer(code)
    return Parser().parse(Lexer().lex())


def test_parse_literal_kinds_and_list_literal() -> None:
    """
    title: Parse string/char/bool/none and list literals.
    """
    tree = _parse(
        "fn main() -> list[i32]:\n"
        '  var s: str = "abc"\n'
        "  var c: char = 'A'\n"
        "  var b: bool = true\n"
        "  var n: none = none\n"
        "  return [1, 2, 3]\n"
    )

    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    ret = fn.body.nodes[-1]
    assert isinstance(ret, astx.FunctionReturn)
    assert isinstance(ret.value, astx.LiteralList)


def test_parse_list_literal_rejects_non_literal_elements() -> None:
    """
    title: List literals reject non-literal values.
    """
    with pytest.raises(
        ParserException,
        match=(
            r"(only literal elements|"
            r"Unknown token when expecting an expression)"
        ),
    ):
        _parse("fn main() -> list[i32]:\n  return [foo]\n")


def test_parse_datetime_and_timestamp_builtins() -> None:
    """
    title: Parse datetime/timestamp builtin literals.
    """
    tree = _parse(
        "fn dt() -> datetime:\n"
        '  return datetime("2026-01-01T00:00:00")\n'
        "fn ts() -> timestamp:\n"
        '  return timestamp("2026-01-01T00:00:00Z")\n'
    )

    fn_dt = tree.nodes[0]
    fn_ts = tree.nodes[1]
    assert isinstance(fn_dt, astx.FunctionDef)
    assert isinstance(fn_ts, astx.FunctionDef)
    assert isinstance(fn_dt.body.nodes[0], astx.FunctionReturn)
    assert isinstance(fn_ts.body.nodes[0], astx.FunctionReturn)
    assert isinstance(fn_dt.body.nodes[0].value, astx.LiteralDateTime)
    assert isinstance(fn_ts.body.nodes[0].value, astx.LiteralTimestamp)


def test_parse_datetime_requires_string_literal() -> None:
    """
    title: Datetime builtin expects a string literal.
    """
    with pytest.raises(ParserException, match="expects a string literal"):
        _parse("fn main() -> datetime:\n  return datetime(1)\n")


def test_parse_block_keeps_return_after_loop_semicolon() -> None:
    """
    title: Loop body semicolons do not eject following statements from blocks.
    """
    tree = _parse(
        "fn print_star(n: i32) -> none:\n"
        "  for i in range(0, n):\n"
        '    print("*");\n'
        "  return none\n"
    )

    assert len(tree.nodes) == 1
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    assert len(fn.body.nodes) == 2
    assert isinstance(fn.body.nodes[0], astx.ForInLoopStmt)
    assert isinstance(fn.body.nodes[1], astx.FunctionReturn)


@pytest.mark.parametrize(
    "code, expected",
    [
        (
            "fn main() -> i32:\n  for 1 in range(0, 1):\n    return 1\n",
            "identifier",
        ),
        (
            "fn main() -> i32:\n  for i range(0, 1):\n    return i\n",
            "Expected 'in'",
        ),
    ],
)
def test_parse_for_error_paths(code: str, expected: str) -> None:
    """
    title: For-loop parser errors.
    parameters:
      code:
        type: str
      expected:
        type: str
    """
    with pytest.raises(ParserException, match=expected):
        _parse(code)


def test_parse_inline_var_declaration_error_paths() -> None:
    """
    title: Parse inline var declaration errors.
    """
    ArxIO.string_to_buffer("x")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Expected 'var'"):
        parser.parse_inline_var_declaration()

    ArxIO.string_to_buffer("var 1")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="identifier after var"):
        parser.parse_inline_var_declaration()

    ArxIO.string_to_buffer("var i = 0")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="type annotation"):
        parser.parse_inline_var_declaration()


def test_parse_var_expr_error_paths() -> None:
    """
    title: Parse var expression errors.
    """
    ArxIO.string_to_buffer("var 1")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="identifier after var"):
        parser.parse_var_expr()

    ArxIO.string_to_buffer("var a: i32 in")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Legacy 'var"):
        parser.parse_var_expr()

    ArxIO.string_to_buffer("var a = 1")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="type annotation"):
        parser.parse_var_expr()


def test_parse_type_error_paths() -> None:
    """
    title: Parse type errors.
    """
    ArxIO.string_to_buffer("1")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Expected a type name"):
        parser.parse_type()

    ArxIO.string_to_buffer("unknown")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Unknown type"):
        parser.parse_type()


def test_parse_list_and_tensor_type_forms_and_default_values() -> None:
    """
    title: Parse list and tensor type forms plus default-value helper branches.
    """
    tree = _parse(
        "fn dynamic(arg: list[i32]) -> i32:\n"
        "  return 1\n"
        "fn vector(values: tensor[i32]) -> i32:\n"
        "  return values[0]\n"
        "fn fixed(values: tensor[i32, 4]) -> i32:\n"
        "  return values[0]\n"
        "fn grid(values: tensor[i32, 2, 3]) -> i32:\n"
        "  return values[1, 2]\n"
    )
    dynamic_fn = tree.nodes[0]
    vector_fn = tree.nodes[1]
    fixed_fn = tree.nodes[2]
    grid_fn = tree.nodes[3]
    assert isinstance(dynamic_fn, astx.FunctionDef)
    assert isinstance(dynamic_fn.prototype.args[0].type_, astx.ListType)
    assert isinstance(vector_fn, astx.FunctionDef)
    assert isinstance(vector_fn.prototype.args[0].type_, astx.TensorType)
    assert tensor_shape(vector_fn.prototype.args[0].type_) is None
    assert isinstance(
        cast(astx.FunctionReturn, vector_fn.body.nodes[0]).value,
        astx.TensorIndex,
    )
    assert isinstance(fixed_fn, astx.FunctionDef)
    assert isinstance(fixed_fn.prototype.args[0].type_, astx.TensorType)
    assert tensor_shape(fixed_fn.prototype.args[0].type_) == (4,)
    assert isinstance(grid_fn, astx.FunctionDef)
    assert isinstance(grid_fn.prototype.args[0].type_, astx.TensorType)
    assert tensor_shape(grid_fn.prototype.args[0].type_) == (2, 3)

    parser = Parser()
    assert isinstance(
        parser._default_value_for_type(astx.Float16()),
        astx.LiteralFloat16,
    )
    assert isinstance(
        parser._default_value_for_type(astx.Float32()),
        astx.LiteralFloat32,
    )
    assert isinstance(
        parser._default_value_for_type(astx.Int32()),
        astx.LiteralInt32,
    )
    assert isinstance(
        parser._default_value_for_type(astx.Boolean()),
        astx.LiteralBoolean,
    )
    assert isinstance(
        parser._default_value_for_type(astx.String()),
        astx.LiteralString,
    )
    assert isinstance(
        parser._default_value_for_type(astx.NoneType()),
        astx.LiteralNone,
    )
    assert isinstance(
        parser._default_value_for_type(astx.DateTime()), astx.LiteralDateTime
    )
    assert isinstance(
        parser._default_value_for_type(astx.Timestamp()), astx.LiteralTimestamp
    )
    assert isinstance(
        parser._default_value_for_type(astx.Date()), astx.LiteralDate
    )
    assert isinstance(
        parser._default_value_for_type(astx.Time()), astx.LiteralTime
    )

    with pytest.raises(ParserException, match="unsized tensor"):
        parser._default_value_for_type(tensor_type(astx.Int32()))

    list_default = parser._default_value_for_type(
        astx.ListType([astx.Int32()])
    )
    assert isinstance(list_default, astx.ListCreate)
    assert isinstance(list_default.type_, astx.ListType)


def test_parse_list_types_reject_shape_dimensions() -> None:
    """
    title: List types reject tensor-style shape dimensions.
    """
    ArxIO.string_to_buffer("list[i32, 4]")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="exactly one element type"):
        parser.parse_type()


def test_parse_array_type_is_rejected() -> None:
    """
    title: Legacy array type syntax is no longer accepted.
    """
    ArxIO.string_to_buffer("array[i32]")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Unknown type 'array'"):
        parser.parse_type()


def test_parse_tensor_type_literal_and_indexing() -> None:
    """
    title: Parse tensor declarations and multidimensional indexing.
    """
    tree = _parse(
        "fn pick(grid: tensor[i32, 2, 2]) -> i32:\n"
        "  return grid[1, 0]\n"
        "fn main() -> i32:\n"
        "  var grid: tensor[i32, 2, 2] = [[1, 2], [3, 4]]\n"
        "  var ids: tensor[i32, 4] = [1, 2, 3, 4]\n"
        "  return pick(grid) + ids[2]\n"
    )

    pick_fn = tree.nodes[0]
    main_fn = tree.nodes[1]
    assert isinstance(pick_fn, astx.FunctionDef)
    assert isinstance(main_fn, astx.FunctionDef)
    assert isinstance(pick_fn.prototype.args[0].type_, astx.TensorType)
    assert isinstance(main_fn.body.nodes[0], astx.VariableDeclaration)
    assert isinstance(main_fn.body.nodes[0].type_, astx.TensorType)
    assert isinstance(
        cast(astx.VariableDeclaration, main_fn.body.nodes[0]).value,
        astx.TensorLiteral,
    )
    assert isinstance(main_fn.body.nodes[1], astx.VariableDeclaration)
    assert isinstance(
        cast(astx.VariableDeclaration, main_fn.body.nodes[1]).type_,
        astx.TensorType,
    )
    assert isinstance(
        cast(astx.FunctionReturn, pick_fn.body.nodes[0]).value,
        astx.TensorIndex,
    )
    assert tensor_shape(pick_fn.prototype.args[0].type_) == (2, 2)
    assert tensor_shape(
        cast(astx.VariableDeclaration, main_fn.body.nodes[0]).type_
    ) == (2, 2)
    assert tensor_shape(
        cast(astx.VariableDeclaration, main_fn.body.nodes[1]).type_
    ) == (4,)


def test_parse_unsized_tensor_literal_init_and_indexing() -> None:
    """
    title: Unsized tensor declarations allow indexing without specialization.
    """
    tree = _parse(
        "fn main() -> i32:\n"
        "  var values: tensor[i32] = [1, 2, 3]\n"
        "  return values[1]\n"
    )
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    declaration = fn.body.nodes[0]
    assert isinstance(declaration, astx.VariableDeclaration)
    assert isinstance(declaration.type_, astx.TensorType)
    assert tensor_shape(declaration.type_) is None
    assert isinstance(declaration.value, astx.TensorLiteral)
    assert tensor_shape(declaration.value.type_) == (3,)

    ret = fn.body.nodes[1]
    assert isinstance(ret, astx.FunctionReturn)
    assert isinstance(ret.value, astx.TensorIndex)


def test_parse_unsized_tensor_indexing_skips_static_bounds_checks() -> None:
    """
    title: Unsized tensor indexing does not perform shaped static bound checks.
    """
    tree = _parse(
        "fn main() -> i32:\n"
        "  var values: tensor[i32] = [1, 2, 3]\n"
        "  return values[99]\n"
    )
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    ret = fn.body.nodes[1]
    assert isinstance(ret, astx.FunctionReturn)
    assert isinstance(ret.value, astx.TensorIndex)


def test_parse_list_default_init_and_append() -> None:
    """
    title: List declarations default to ListCreate and lower append calls.
    """
    tree = _parse(
        "fn build(stop: i32) -> list[i32]:\n"
        "  var values: list[i32]\n"
        "  for var current: i32 = 0; current < stop; current + 1:\n"
        "    values.append(current)\n"
        "  return values\n"
    )

    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)

    declaration = fn.body.nodes[0]
    assert isinstance(declaration, astx.VariableDeclaration)
    assert isinstance(declaration.type_, astx.ListType)
    assert isinstance(declaration.value, astx.ListCreate)

    loop = fn.body.nodes[1]
    assert isinstance(loop, astx.ForCountLoopStmt)
    assert len(loop.body.nodes) == 1
    assert isinstance(loop.body.nodes[0], astx.ListAppend)

    ret = fn.body.nodes[2]
    assert isinstance(ret, astx.FunctionReturn)
    assert isinstance(ret.value, astx.Identifier)


def test_parse_function_and_extern_argument_defaults() -> None:
    """
    title: Function and extern arguments can declare default values.
    """
    tree = _parse(
        "extern seed(value: i32 = 3) -> i32\n"
        "fn add(value: i32, step: i32 = 1) -> i32:\n"
        "  return value + step\n"
    )

    extern = tree.nodes[0]
    fn = tree.nodes[1]
    assert isinstance(extern, astx.FunctionPrototype)
    assert isinstance(fn, astx.FunctionDef)

    extern_default = extern.args.nodes[0].default
    assert isinstance(extern_default, astx.LiteralInt32)
    assert extern_default.value == 3

    value_arg = fn.prototype.args.nodes[0]
    step_arg = fn.prototype.args.nodes[1]
    assert isinstance(value_arg.default, astx.Undefined)
    assert isinstance(step_arg.default, astx.LiteralInt32)
    assert step_arg.default.value == 1


def test_parse_method_argument_defaults() -> None:
    """
    title: Method arguments can declare default values.
    """
    tree = _parse(
        "class Counter:\n"
        "  fn add(self, amount: i32 = 1) -> i32:\n"
        "    return amount\n"
    )

    class_def = tree.nodes[0]
    assert isinstance(class_def, astx.ClassDefStmt)
    method = class_def.methods[0]
    amount_arg = method.prototype.args.nodes[0]
    assert isinstance(amount_arg.default, astx.LiteralInt32)
    assert amount_arg.default.value == 1


def test_parse_range_keeps_source_arguments() -> None:
    """
    title: Range calls keep source arity for IRx default arguments.
    """
    tree = _parse(
        "fn first() -> none:\n"
        "  var values: list[i32] = range(0, 4)\n"
        "  return none\n"
        "fn second() -> none:\n"
        "  var values: list[i32] = range(2, 8, 2)\n"
        "  return none\n"
    )

    first_fn = tree.nodes[0]
    second_fn = tree.nodes[1]
    assert isinstance(first_fn, astx.FunctionDef)
    assert isinstance(second_fn, astx.FunctionDef)

    first_decl = cast(astx.VariableDeclaration, first_fn.body.nodes[0])
    assert isinstance(first_decl.value, astx.FunctionCall)
    assert first_decl.value.fn == "range"
    assert len(first_decl.value.args) == 2

    second_decl = cast(astx.VariableDeclaration, second_fn.body.nodes[0])
    assert isinstance(second_decl.value, astx.FunctionCall)
    assert second_decl.value.fn == "range"
    assert len(second_decl.value.args) == 3
    assert isinstance(second_decl.value.args[2], astx.LiteralInt32)
    assert second_decl.value.args[2].value == 2


def test_parse_range_keeps_variable_stop_without_synthetic_step() -> None:
    """
    title: Range calls with variable stop do not synthesize a step argument.
    """
    tree = _parse(
        "fn build(n: i32) -> none:\n"
        "  var xs: list[i32] = range(0, n)\n"
        "  return none\n"
    )

    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)

    decl = cast(astx.VariableDeclaration, fn.body.nodes[0])
    assert isinstance(decl.value, astx.FunctionCall)
    assert decl.value.fn == "range"
    assert len(decl.value.args) == 2
    assert isinstance(decl.value.args[0], astx.LiteralInt32)
    assert decl.value.args[0].value == 0
    assert isinstance(decl.value.args[1], astx.Identifier)
    assert decl.value.args[1].name == "n"
    assert len(decl.value.args) == 2


def test_parse_for_in_list_literal_uses_for_in_node() -> None:
    """
    title: For-in over a list literal preserves one for-in AST node.
    """
    tree = _parse(
        "fn main() -> i32:\n"
        "  for value in [1, 2, 3]:\n"
        "    return value\n"
        "  return 0\n"
    )

    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)

    loop = fn.body.nodes[0]
    assert isinstance(loop, astx.ForInLoopStmt)
    assert isinstance(loop.target, astx.Identifier)
    assert loop.target.name == "value"
    assert isinstance(loop.iterable, astx.LiteralList)
    assert isinstance(loop.body.nodes[0], astx.FunctionReturn)
    assert isinstance(loop.body.nodes[0].value, astx.Identifier)
    assert loop.body.nodes[0].value.name == "value"


def test_parse_for_in_list_variable_uses_for_in_node() -> None:
    """
    title: For-in over a list variable preserves one for-in AST node.
    """
    tree = _parse(
        "fn main() -> i32:\n"
        "  var xs: list[i32] = range(0, 3)\n"
        "  for value in xs:\n"
        "    return value\n"
        "  return 0\n"
    )

    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)

    loop = fn.body.nodes[1]
    assert isinstance(loop, astx.ForInLoopStmt)
    assert isinstance(loop.target, astx.Identifier)
    assert loop.target.name == "value"
    assert isinstance(loop.iterable, astx.Identifier)
    assert loop.iterable.name == "xs"
    assert isinstance(loop.body.nodes[0], astx.FunctionReturn)
    assert isinstance(loop.body.nodes[0].value, astx.Identifier)
    assert loop.body.nodes[0].value.name == "value"


def test_parse_for_in_function_call_preserves_iterable_call() -> None:
    """
    title: For-in over a function call keeps one iterable call expression.
    """
    tree = _parse(
        "fn make_values() -> list[i32]:\n"
        "  return range(0, 3)\n"
        "fn main() -> i32:\n"
        "  for value in make_values():\n"
        "    return value\n"
        "  return 0\n"
    )

    fn = tree.nodes[1]
    assert isinstance(fn, astx.FunctionDef)

    loop = fn.body.nodes[0]
    assert isinstance(loop, astx.ForInLoopStmt)
    assert isinstance(loop.iterable, astx.FunctionCall)
    assert loop.iterable.fn == "make_values"
    assert len(loop.iterable.args) == 0


def test_parse_for_in_target_is_visible_in_body() -> None:
    """
    title: For-in loop targets are visible identifiers inside the body.
    """
    tree = _parse(
        "fn main() -> i32:\n"
        "  var xs: list[i32] = range(0, 3)\n"
        "  for value in xs:\n"
        "    return value\n"
        "  return 0\n"
    )

    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)

    loop = fn.body.nodes[1]
    assert isinstance(loop, astx.ForInLoopStmt)
    assert isinstance(loop.body.nodes[0], astx.FunctionReturn)
    assert isinstance(loop.body.nodes[0].value, astx.Identifier)
    assert loop.body.nodes[0].value.name == "value"


@pytest.mark.parametrize(
    "code",
    [
        "import generators from builtins\n",
        "import builtins.generators as generators\n",
        "import range as rg from builtins.generators\n",
        "import (generators as g) from builtins\n",
        "import (range as rg) from builtins.generators\n",
    ],
)
def test_parse_builtin_imports_are_rejected(code: str) -> None:
    """
    title: User source cannot import internal builtin modules directly.
    parameters:
      code:
        type: str
    """
    with pytest.raises(
        ParserException,
        match="cannot be imported directly",
    ):
        _parse(code + "fn main() -> none:\n  return none\n")


def test_parse_range_leaves_arity_validation_to_builtins() -> None:
    """
    title: Range calls parse like ordinary calls before semantic analysis.
    """
    tree = _parse(
        "fn main() -> none:\n"
        "  var values: list[i32] = range(4)\n"
        "  return none\n"
    )
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    decl = cast(astx.VariableDeclaration, fn.body.nodes[0])
    call = decl.value
    assert isinstance(call, astx.FunctionCall)
    assert call.fn == "range"
    assert len(call.args) == 1


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (
            "fn main() -> i32:\n"
            "  var grid: tensor[i32, 2, 2] = [[1, 2], [3]]\n"
            "  return 0\n",
            "regular rectangular shape",
        ),
        (
            "fn main() -> i32:\n"
            "  var grid: tensor[i32, 2, 2] = [[1, 2, 3], [4, 5, 6]]\n"
            "  return 0\n",
            "declared tensor shape",
        ),
        (
            "fn main() -> i32:\n"
            "  var grid: tensor[i32, 2, 2] = [[1, 2], [3, 4]]\n"
            "  return grid[0]\n",
            "expects 2 indices",
        ),
        (
            "fn main() -> i32:\n"
            "  var grid: tensor[i32, 2, 2] = [[1, 2], [3, 4]]\n"
            "  return grid[2, 0]\n",
            "out of bounds",
        ),
        (
            "fn main() -> i32:\n"
            "  var grid: tensor[i32, size] = [1, 2]\n"
            "  return 0\n",
            "integer literals",
        ),
    ],
)
def test_parse_tensor_error_paths(code: str, expected: str) -> None:
    """
    title: Tensor parser diagnostics cover shape and indexing failures.
    parameters:
      code:
        type: str
      expected:
        type: str
    """
    with pytest.raises(ParserException, match=expected):
        _parse(code)


def test_parse_unary_and_prototype_error_paths() -> None:
    """
    title: Parse unary expressions and prototype errors.
    """
    ArxIO.string_to_buffer("-1")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    expr = parser.parse_expression()
    assert isinstance(expr, astx.UnaryOp)
    assert isinstance(expr.type_, astx.DataType)

    ArxIO.string_to_buffer("(")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Expected function name"):
        parser.parse_prototype(expect_colon=False)

    ArxIO.string_to_buffer("f(1)")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Expected argument name"):
        parser.parse_prototype(expect_colon=False)

    ArxIO.string_to_buffer("f(x)")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Expected type annotation"):
        parser.parse_prototype(expect_colon=False)

    ArxIO.string_to_buffer("f(x: i32)")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Expected return type"):
        parser.parse_prototype(expect_colon=False)

    ArxIO.string_to_buffer("f(x: i32) ->")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Expected a type name"):
        parser.parse_prototype(expect_colon=False)


def test_parse_block_error_paths() -> None:
    """
    title: Parse block error branches.
    """
    ArxIO.string_to_buffer("1")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Expected indentation"):
        parser.parse_block()

    parser = Parser(
        TokenList([Token(TokenKind.indent, 0), Token(TokenKind.eof, "")])
    )
    parser.tokens.get_next_token()
    parser.indent_level = 0
    with pytest.raises(ParserException, match="There is no new block"):
        parser.parse_block()

    with pytest.raises(ParserException, match="Indentation not allowed here"):
        _parse("fn main() -> i32:\n  a = 1\n    b = 2\n")


def test_parse_primary_unknown_token_branch() -> None:
    """
    title: Parse unknown primary token branch.
    """
    parser = Parser(
        TokenList(
            [
                Token(TokenKind.kw_then, "then"),
                Token(TokenKind.eof, ""),
            ]
        )
    )
    parser.tokens.get_next_token()

    with pytest.raises(ParserException, match="Unknown token"):
        parser.parse_primary()


def test_parse_prototype_requires_explicit_return_type() -> None:
    """
    title: Omitting the return-type annotation is a parser error.
    """
    with pytest.raises(ParserException, match="Expected return type"):
        _parse("fn do_nothing():\n  return\n")


def test_parse_bare_return_produces_none_literal() -> None:
    """
    title: A bare `return` inside a none function emits LiteralNone.
    """
    tree = _parse("fn do_nothing() -> none:\n  return\n")

    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    ret = fn.body.nodes[0]
    assert isinstance(ret, astx.FunctionReturn)
    assert isinstance(ret.value, astx.LiteralNone)


def test_parse_function_without_return_statement() -> None:
    """
    title: A none-returning function may omit the `return` statement.
    """
    tree = _parse("fn do_nothing() -> none:\n  var x: i32 = 1\n")

    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    assert isinstance(fn.prototype.return_type, astx.NoneType)
    assert len(fn.body.nodes) == 1
    assert not isinstance(fn.body.nodes[0], astx.FunctionReturn)


def test_parse_explicit_return_none_value() -> None:
    """
    title: >-
      Explicit return of the none literal emits FunctionReturn with
      LiteralNone.
    """
    tree = _parse("fn do_nothing() -> none:\n  return none\n")

    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    ret = fn.body.nodes[0]
    assert isinstance(ret, astx.FunctionReturn)
    assert isinstance(ret.value, astx.LiteralNone)


def test_parse_none_type_is_recognized() -> None:
    """
    title: The none type name is recognized in function signatures.
    """
    tree = _parse("fn do_nothing() -> none:\n  return\n")

    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    assert isinstance(fn.prototype.return_type, astx.NoneType)
