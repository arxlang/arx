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
          var rows: dataframe[id: i32, score: f64] = dataframe({
            id: [1, 2, 3],
            score: [0.5, 0.8, 1.0],
          })
          var score: series[f64] = rows.score
          var ids: series[i32] = rows["id"]
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


def test_parse_runtime_schema_dataframe_only_for_parameters() -> None:
    """
    title: Runtime-schema dataframe annotations are parameter-only for now.
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

    with pytest.raises(ParserException, match="function parameter"):
        _parse_module(
            """
            fn bad() -> none:
              var rows: dataframe[...] = dataframe({id: [1]})
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
              var rows: dataframe[id: i32, score: f64] = dataframe({
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
          var rows: dataframe[id: i32] = dataframe({id: [1]})
          if true:
            var rows: i32 = 1
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
          var rows: dataframe[name:str | none] = dataframe({name: [none]})
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
