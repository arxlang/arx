"""
title: Tests for Arx dataframe helpers and parser paths.
"""

from __future__ import annotations

from textwrap import dedent

import astx
import pytest

from arx.exceptions import ParserException
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser


def _parse_module(code: str) -> astx.Module:
    """
    title: Parse one Arx module snippet.
    parameters:
      code:
        type: str
    returns:
      type: astx.Module
    """
    ArxIO.string_to_buffer(dedent(code).lstrip())
    return Parser().parse(Lexer().lex())


def test_parse_dataframe_type_constructor_and_column_access() -> None:
    """
    title: Parse DataFrame types, constructor calls, and both access styles.
    """
    tree = _parse_module(
        """
        fn main() -> i32:
          rows: dataframe[id: i32, score: f64] = dataframe({
            id: [1, 2, 3],
            score: [0.5, 0.8, 1.0],
          })
          score: series[f64] = rows.score
          ids: series[i32] = rows["id"]
          return cast(rows.nrows(), i32)
        """
    )

    function = tree.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    rows = function.body.nodes[0]
    assert isinstance(rows, astx.VariableDeclaration)
    assert isinstance(rows.type_, astx.DataFrameType)
    assert [column.name for column in rows.type_.columns or ()] == [
        "id",
        "score",
    ]
    assert isinstance(rows.value, astx.DataFrameLiteral)

    score = function.body.nodes[1]
    assert isinstance(score, astx.VariableDeclaration)
    assert isinstance(score.type_, astx.SeriesType)
    assert isinstance(score.value, astx.DataFrameColumnAccess)
    assert score.value.column_name == "score"

    ids = function.body.nodes[2]
    assert isinstance(ids, astx.VariableDeclaration)
    assert isinstance(ids.type_, astx.SeriesType)
    assert isinstance(ids.value, astx.DataFrameStringColumnAccess)
    assert ids.value.column_name == "id"


@pytest.mark.parametrize(
    "operation, positional, keywords, templated",
    [
        ("nrows()", 0, 0, False),
        ("ncols(1)", 1, 0, False),
        ("nrows(ignored=1)", 0, 1, False),
        ("ncols<i32>()", 0, 0, True),
    ],
)
def test_metadata_calls_preserve_generic_syntax(
    operation: str, positional: int, keywords: int, templated: bool
) -> None:
    """
    title: Metadata signature validity never depends on a parser type guess.
    parameters:
      operation:
        type: str
      positional:
        type: int
      keywords:
        type: int
      templated:
        type: bool
    """
    source = (
        "fn frame() -> dataframe[x:i32]:\n  return dataframe({x:[1]})\n"
        "fn main() -> i32:\n"
        "  typed: dataframe[x:i32] = frame()\n"
        "  inferred: auto = frame()\n"
        f"  typed.{operation}\n  inferred.{operation}\n"
        "  return 0\n"
    )
    module = _parse_module(source)
    function = module.nodes[-1]
    assert isinstance(function, astx.FunctionDef)
    method = operation.partition("(")[0].partition("<")[0]
    for line, receiver, call in zip(
        (6, 7), ("typed", "inferred"), function.body.nodes[2:4]
    ):
        assert isinstance(call, astx.MethodCall)
        assert isinstance(call.receiver, astx.Identifier)
        assert call.receiver.name == receiver
        assert call.method_name == method
        assert len(call.args) == positional
        assert len(call.keywords) == keywords
        if positional:
            assert isinstance(call.args[0], astx.LiteralInteger)
            assert call.args[0].value == 1
        if keywords:
            assert call.keywords[0].name == "ignored"
            assert isinstance(call.keywords[0].value, astx.LiteralInteger)
            assert call.keywords[0].value.value == 1
        arguments = astx.get_template_args(call)
        if templated:
            assert arguments is not None and len(arguments) == 1
            assert isinstance(arguments[0], astx.Int32)
        else:
            assert arguments is None
        assert call.loc.line == line
        assert (
            call.loc.col
            == source.splitlines()[line - 1].index(call.method_name) + 1
        )


def test_parse_runtime_schema_dataframe_annotations() -> None:
    """
    title: Runtime schemas support owned conversions but not untyped literals.
    """
    tree = _parse_module(
        """
        extern sink(rows: dataframe[...]) -> none

        fn accept(rows: dataframe[...]) -> i32:
          return cast(rows.nrows(), i32)
        """
    )

    extern = tree.nodes[0]
    assert isinstance(extern, astx.FunctionPrototype)
    extern_type = extern.args.nodes[0].type_
    assert isinstance(extern_type, astx.DataFrameType)
    assert extern_type.columns is None

    function = tree.nodes[1]
    assert isinstance(function, astx.FunctionDef)
    arg_type = function.prototype.args.nodes[0].type_
    assert isinstance(arg_type, astx.DataFrameType)
    assert arg_type.columns is None
    returned = function.body.nodes[0]
    assert isinstance(returned, astx.FunctionReturn)
    assert isinstance(returned.value, astx.Cast)
    assert isinstance(returned.value.value, astx.MethodCall)
    assert returned.value.value.method_name == "nrows"


def test_metadata_names_remain_columns_when_not_called() -> None:
    """
    title: Metadata method names do not steal non-call column access.
    """
    module = _parse_module(
        "fn main() -> i32:\n"
        "  frame: dataframe[nrows:i32, ncols:i32] = "
        "dataframe({nrows:[1], ncols:[2]})\n"
        "  frame.nrows\n  frame.ncols\n  frame.nrows()\n  return 0\n"
    )
    main = module.nodes[0]
    assert isinstance(main, astx.FunctionDef)
    for name, access in zip(("nrows", "ncols"), main.body.nodes[1:3]):
        assert isinstance(access, astx.DataFrameColumnAccess)
        assert access.column_name == name
    assert isinstance(main.body.nodes[3], astx.MethodCall)


@pytest.mark.parametrize(
    "call", ["frame.nrows(", "frame.nrows(ignored=1, 2)", "frame.ncols<i32()"]
)
def test_malformed_metadata_call_syntax_still_fails_in_parser(
    call: str,
) -> None:
    """
    title: >-
      Routing signature policy to IRx does not admit malformed call syntax.
    parameters:
      call:
        type: str
    """
    with pytest.raises(ParserException):
        _parse_module(
            "fn main() -> i32:\n"
            "  frame: dataframe[x:i32] = dataframe({x:[1]})\n"
            f"  {call}\n  return 0\n"
        )


@pytest.mark.parametrize(
    ("constructor", "value", "kind"),
    [
        ("date", "2026-01-01", astx.LiteralDate),
        ("time", "01:02:03", astx.LiteralTime),
    ],
)
def test_parse_temporal_constructors(
    constructor: str, value: str, kind: type[astx.AST]
) -> None:
    """
    title: Temporal constructors emit existing reusable ASTx nodes.
    parameters:
      constructor:
        type: str
      value:
        type: str
      kind:
        type: type[astx.AST]
    """
    tree = _parse_module(f'fn main() -> none:\n  {constructor}("{value}")\n')
    function = tree.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    assert isinstance(function.body.nodes[0], kind)


def test_reject_untyped_dataframe_literal() -> None:
    """
    title: A runtime schema does not infer heterogeneous literal columns.
    """

    with pytest.raises(ParserException, match=r"schema|columns"):
        _parse_module(
            """
            fn bad() -> none:
              rows: dataframe[...] = dataframe({id: [1]})
              return none
            """
        )


def test_dataframe_constructor_requires_declared_columns() -> None:
    """
    title: DataFrame literals are checked against the declared static schema.
    """
    with pytest.raises(ParserException, match="missing column 'score'"):
        _parse_module(
            """
            fn bad() -> none:
              rows: dataframe[id: i32, score: f64] = dataframe({
                id: [1, 2, 3],
              })
              return none
            """
        )


def test_dataframe_name_tracking_respects_inner_scope_shadowing() -> None:
    """
    title: Inner non-DataFrame variables shadow outer DataFrame bindings.
    """
    tree = _parse_module(
        """
        fn main() -> i32:
          rows: dataframe[id: i32] = dataframe({id: [1]})
          if true:
            rows: i32 = 1
            return rows.nrows()
          return 0
        """
    )

    function = tree.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    branch = function.body.nodes[1]
    assert isinstance(branch, astx.IfStmt)
    result = branch.then.nodes[1]
    assert isinstance(result, astx.FunctionReturn)
    assert isinstance(result.value, astx.MethodCall)
    assert not isinstance(result.value, astx.DataFrameRowCount)


def test_dataframe_string_and_nullable_columns() -> None:
    """
    title: DataFrame annotations model strings and nullable columns directly.
    """
    tree = _parse_module(
        """
        fn good() -> none:
          rows: dataframe[name:str | none] = dataframe({name: [none]})
          return none
        """
    )
    function = tree.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    rows = function.body.nodes[0]
    assert isinstance(rows, astx.VariableDeclaration)
    assert isinstance(rows.type_, astx.DataFrameType)
    assert rows.type_.columns is not None
    assert rows.type_.columns[0].nullable
    assert isinstance(rows.type_.columns[0].type_, astx.String)
    _parse_module("fn good(value: series[str]) -> none:\n  return none")


def test_dataframe_invalid_nullable_union() -> None:
    """
    title: >-
      Reject arbitrary unions rather than pretending they are nullable fields.
    """
    with pytest.raises(ParserException, match=r"type \| none"):
        _parse_module(
            "fn bad(value: dataframe[x:i64 | str]) -> none:\n  return none"
        )


@pytest.mark.parametrize(
    "annotation",
    [
        "decimal128[12, -2]",
        "decimal256[60, 3]",
        'timestamp["ns", "UTC"]',
        'time["ms"]',
        "binary[8]",
        "large_string",
        "large_binary",
        "arrow_list[nullable[i32]]",
        "large_list[i32]",
        "fixed_list[i64, 2]",
        "dictionary[i8, str]",
        "arrow_map[str, nullable[i32]]",
        "arrow_struct[x:nullable[i32], label:str]",
    ],
)
def test_parse_parameterized_columns(annotation: str) -> None:
    """
    title: Parse storage parameters without treating them as expressions.
    parameters:
      annotation:
        type: str
    """
    tree = _parse_module(
        f"fn accept(frame: dataframe[x:{annotation} | none]) -> i32:\n"
        "  return 0\n"
    )
    function = tree.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    frame = function.prototype.args.nodes[0].type_
    assert isinstance(frame, astx.DataFrameType) and frame.columns is not None
    assert isinstance(frame.columns[0].type_, astx.ColumnType)
    assert frame.columns[0].nullable


@pytest.mark.parametrize(
    "annotation",
    [
        'timestamp["hours"]',
        "decimal128[39, 0]",
        "fixed_list[i32, 0]",
        "arrow_struct[x:i32, x:i32]",
        "series[i32 | f32]",
        "binary[-1]",
        "decimal128[1099511627776, 0]",
        "binary[1099511627776]",
        "fixed_list[i32, 1099511627776]",
    ],
)
def test_reject_invalid_column_parameters(annotation: str) -> None:
    """
    title: Invalid column syntax and physical parameters fail actionably.
    parameters:
      annotation:
        type: str
    """
    with pytest.raises(ParserException):
        _parse_module(
            f"fn accept(frame: dataframe[x:{annotation}]) -> i32:\n"
            "  return 0\n"
        )
