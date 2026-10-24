"""
title: Exact rich literal encoding and responsible semantic diagnostics.
"""

from decimal import Decimal

import astx
import pyarrow as pa
import pytest

from irx.analysis import SemanticError
from irx.analysis.dataframe_literals import dataframe_literal_ipc, literal_cell
from irx.builder import Builder

from .conftest import assert_ir_parses, make_main_module


@pytest.mark.parametrize(
    "type_,node,expected",
    [
        (pa.decimal128(8, 2), astx.LiteralString("1.25"), Decimal("1.25")),
        (pa.binary(2), astx.LiteralString("ab"), b"ab"),
        (pa.timestamp("ns", tz="UTC"), astx.LiteralInt64(123), 123),
        (pa.bool_(), astx.LiteralBoolean(True), True),
        (pa.float64(), astx.LiteralFloat64(1.5), 1.5),
        (pa.string(), astx.LiteralString("λ"), "λ"),
        (pa.int32(), astx.LiteralNone(), None),
        (pa.dictionary(pa.int8(), pa.string()), astx.LiteralString("x"), "x"),
        (
            pa.list_(pa.int32()),
            astx.LiteralTuple((astx.LiteralInt32(1), astx.LiteralNone())),
            [1, None],
        ),
        (
            pa.struct([("x", pa.int32())]),
            astx.LiteralTuple((astx.LiteralInt32(1),)),
            {"x": 1},
        ),
        (
            pa.map_(pa.string(), pa.int32()),
            astx.LiteralTuple(
                (
                    astx.LiteralTuple(
                        (astx.LiteralString("k"), astx.LiteralInt32(1))
                    ),
                )
            ),
            [("k", 1)],
        ),
    ],
)
def test_literal_cells(
    type_: pa.DataType, node: astx.AST, expected: object
) -> None:
    """
    title: Decode supported literal cells without losing precision or shape.
    parameters:
      type_:
        type: pa.DataType
      node:
        type: astx.AST
      expected:
        type: object
    """
    assert literal_cell(node, pa.field("x", type_), "x") == expected


@pytest.mark.parametrize(
    "type_,node,message",
    [
        (pa.decimal128(8, 2), astx.LiteralFloat64(1.5), "exact strings"),
        (pa.decimal128(8, 2), astx.LiteralString("bad"), "invalid decimal"),
        (pa.binary(), astx.LiteralInt32(1), "UTF-8 strings"),
        (pa.timestamp("ns"), astx.LiteralString("today"), "integer storage"),
        (pa.bool_(), astx.LiteralInt32(1), "bool literal"),
        (pa.int32(), astx.LiteralFloat64(1.5), "integer literal"),
        (pa.float64(), astx.LiteralBoolean(True), "numeric literal"),
        (pa.string(), astx.LiteralInt32(1), "string literal"),
        (
            pa.list_(pa.int32(), 2),
            astx.LiteralTuple((astx.LiteralInt32(1),)),
            "incorrect length",
        ),
        (pa.struct([("x", pa.int32())]), astx.LiteralTuple(()), "field count"),
        (
            pa.map_(pa.string(), pa.int32()),
            astx.LiteralTuple((astx.LiteralInt32(1),)),
            "pairs",
        ),
        (pa.int32(), astx.LiteralTuple(()), "nested literal"),
        (pa.null(), astx.LiteralInt32(1), "unsupported literal"),
        (
            pa.list_(pa.field("item", pa.int32(), nullable=False)),
            astx.LiteralTuple((astx.LiteralNone(),)),
            "nullable field",
        ),
    ],
)
def test_invalid_literal_cells(
    type_: pa.DataType, node: astx.AST, message: str
) -> None:
    """
    title: >-
      Fail at the exact nested field instead of coercing unsupported input.
    parameters:
      type_:
        type: pa.DataType
      node:
        type: astx.AST
      message:
        type: str
    """
    with pytest.raises(ValueError, match=message):
        literal_cell(node, pa.field("x", type_), "x")


def rich_literal(value: str) -> astx.DataFrameLiteral:
    """
    title: Build one declared decimal column independently of Arx parsing.
    parameters:
      value:
        type: str
    returns:
      type: astx.DataFrameLiteral
    """
    type_ = astx.DataFrameType(
        [astx.DataFrameColumn("x", astx.ColumnType("decimal128", (8, 2)))]
    )
    return astx.DataFrameLiteral(
        [astx.DataFrameLiteralColumn("x", (astx.LiteralString(value),))],
        type_=type_,
    )


def test_rich_literal_semantics_and_lowering() -> None:
    """
    title: Lower only validated IPC literal metadata into an owned Arrow table.
    """
    literal = rich_literal("1.25")
    payload = dataframe_literal_ipc(literal)
    with pa.ipc.open_stream(payload) as reader:
        assert reader.read_all()["x"].to_pylist() == [Decimal("1.25")]
    module = make_main_module(
        astx.VariableDeclaration("frame", literal.type_, value=literal),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )
    text = Builder().translate(module)
    assert_ir_parses(text)
    assert "irx_arrow_table_from_ipc" in text
    bad = rich_literal("1.234")
    with pytest.raises(SemanticError, match="DataFrame column 'x'"):
        Builder().translate(
            make_main_module(
                astx.VariableDeclaration("frame", bad.type_, value=bad)
            )
        )


def test_exact_float_literal_rounds_before_arrow_serialization() -> None:
    """
    title: >-
      Arrow IPC receives the resolved binary value, not a host-rounded decimal.
    """
    exact = Decimal("1.000000059604644830901776231257827021181583404541015625")
    cell = astx.LiteralFloat(exact)
    expected = 1.00000011920928955078125
    type_ = astx.DataFrameType([astx.DataFrameColumn("x", astx.Float32())])
    literal = astx.DataFrameLiteral(
        [astx.DataFrameLiteralColumn("x", (cell,))], type_=type_
    )
    with pa.ipc.open_stream(dataframe_literal_ipc(literal)) as reader:
        assert reader.read_all()["x"].to_pylist() == [expected]
    assert cell.value == exact
    assert type(cell.type_) is astx.DataType
