"""
title: Frontend-independent nullable semantic plans and LLVM lowering.
"""

from collections.abc import Callable

import astx
import pytest

from irx.analysis import ParsedModule, SemanticError, analyze
from irx.builder import Builder

from .conftest import (
    StaticImportResolver,
    assert_ir_parses,
    build_and_run,
    make_main_module,
)


def frame(
    type_: astx.DataType, value: astx.DataType, nullable: bool = True
) -> astx.VariableDeclaration:
    """
    title: Construct a typed column AST without importing the Arx frontend.
    parameters:
      type_:
        type: astx.DataType
      value:
        type: astx.DataType
      nullable:
        type: bool
    returns:
      type: astx.VariableDeclaration
    """
    schema = astx.DataFrameType([astx.DataFrameColumn("x", type_, nullable)])
    values = (value, astx.LiteralNone()) if nullable else (value,)
    literal = astx.DataFrameLiteral(
        [astx.DataFrameLiteralColumn("x", values)], type_=schema
    )
    return astx.VariableDeclaration("frame", schema, value=literal)


def column() -> astx.DataFrameColumnAccess:
    """
    title: Construct an independently resolved column reference.
    returns:
      type: astx.DataFrameColumnAccess
    """
    return astx.DataFrameColumnAccess(astx.Identifier("frame"), "x")


@pytest.mark.parametrize(
    "literal",
    [
        astx.LiteralInt8,
        astx.LiteralInt16,
        astx.LiteralInt32,
        astx.LiteralInt64,
        astx.LiteralUInt8,
        astx.LiteralUInt16,
        astx.LiteralUInt32,
        astx.LiteralUInt64,
    ],
)
def test_integer_lowering(literal: Callable[[int], astx.DataType]) -> None:
    """
    title: Encode typed scalars and Series results for every integer width.
    parameters:
      literal:
        type: Callable[[int], astx.DataType]
    """
    value = literal(2)
    type_ = value.type_
    assert isinstance(type_, astx.DataType)
    result = astx.BinaryOp("+", column(), literal(3))
    optional = astx.SubscriptExpr(result, astx.LiteralInt32(0))
    expression = astx.NullFill(optional, literal(0))
    module = make_main_module(
        frame(type_, value),
        astx.FunctionReturn(astx.Cast(expression, astx.Int32())),
    )
    text = Builder().translate(module)
    assert_ir_parses(text)
    assert "irx_arrow_column_compute" in text
    assert "irx_arrow_series_index" in text


@pytest.mark.parametrize(
    "type_,literal",
    [
        (astx.Float32(), astx.LiteralFloat32),
        (astx.Float64(), astx.LiteralFloat64),
    ],
)
def test_float_lowering(
    type_: astx.DataType, literal: Callable[[float], astx.DataType]
) -> None:
    """
    title: Floating nullable scalars use bitcasts, not numeric conversions.
    parameters:
      type_:
        type: astx.DataType
      literal:
        type: Callable[[float], astx.DataType]
    """
    optional = astx.NullableType(type_)
    value = astx.Cast(literal(1.5), optional)
    added = astx.BinaryOp("+", value, literal(2.5))
    module = make_main_module(
        astx.FunctionReturn(
            astx.Cast(astx.NullFill(added, literal(0.0)), astx.Int32())
        )
    )
    text = Builder().translate(module)
    assert_ir_parses(text)
    assert "bitcast" in text


@pytest.mark.parametrize(
    "op", ["+", "-", "*", "/", "==", "!=", "<", "<=", ">", ">="]
)
def test_nullable_operators(op: str) -> None:
    """
    title: Resolve arithmetic and comparisons from ASTx nodes alone.
    parameters:
      op:
        type: str
    """
    optional = astx.NullableType(astx.Int32())
    left = astx.Cast(astx.LiteralNone(), optional)
    right = astx.Cast(astx.LiteralInt32(2), optional)
    check = astx.NullCheck(astx.BinaryOp(op, left, right))
    module = make_main_module(
        astx.FunctionReturn(astx.Cast(check, astx.Int32()))
    )
    assert_ir_parses(Builder().translate(module))


@pytest.mark.parametrize("op", ["&&", "||", "and", "or"])
def test_boolean_series(op: str) -> None:
    """
    title: Boolean Series use strict eager kernels rather than scalar branches.
    parameters:
      op:
        type: str
    """
    operation = astx.BinaryOp(op, column(), astx.LiteralBoolean(False))
    filled = astx.NullFill(operation, astx.LiteralBoolean(True))
    mask = astx.NullCheck(column())
    module = make_main_module(
        frame(astx.Boolean(), astx.LiteralBoolean(True)),
        astx.VariableDeclaration(
            "filled", astx.SeriesType(astx.Boolean()), value=filled
        ),
        astx.VariableDeclaration(
            "mask", astx.SeriesType(astx.Boolean()), value=mask
        ),
        astx.FunctionReturn(
            astx.Cast(
                astx.SubscriptExpr(
                    astx.Identifier("filled"), astx.LiteralInt32(1)
                ),
                astx.Int32(),
            )
        ),
    )
    assert_ir_parses(Builder().translate(module))


def test_owned_series_and_scalar_execute() -> None:
    """
    title: Owned kernels, reassignment, scalar boxing and null tests execute.
    """
    optional = astx.NullableType(astx.Int32())
    sum_ = astx.BinaryOp("+", column(), column())
    module = make_main_module(
        frame(astx.Int32(), astx.LiteralInt32(2)),
        astx.VariableDeclaration(
            "sum", astx.SeriesType(astx.Int32(), nullable=True), value=sum_
        ),
        astx.VariableDeclaration(
            "scalar",
            optional,
            value=astx.LiteralInt32(1),
            mutability=astx.MutabilityKind.mutable,
        ),
        astx.BinaryOp(
            "=",
            astx.Identifier("scalar"),
            astx.Cast(astx.LiteralNone(), optional),
        ),
        astx.FunctionReturn(
            astx.NullFill(
                astx.SubscriptExpr(
                    astx.Identifier("sum"), astx.LiteralInt32(0)
                ),
                astx.LiteralInt32(0),
            )
        ),
    )
    builder = Builder()
    assert_ir_parses(builder.translate(module))
    result = build_and_run(builder, module)
    expected = 4
    assert result.returncode == expected, result.stderr


@pytest.mark.parametrize(
    "expression,message",
    [
        (
            lambda: astx.BinaryOp("%", column(), astx.LiteralInt32(1)),
            "supported operator",
        ),
        (
            lambda: astx.BinaryOp("+", column(), astx.LiteralFloat32(1.0)),
            "matching scalar types",
        ),
        (lambda: astx.BinaryOp("and", column(), column()), "require bool"),
        (lambda: astx.UnaryOp("-", column()), "Use binary arithmetic"),
        (lambda: astx.NullCheck(astx.LiteralInt32(0)), "is_null requires"),
        (
            lambda: astx.NullFill(column(), astx.LiteralBoolean(True)),
            "matching non-null",
        ),
        (
            lambda: astx.SubscriptExpr(column(), astx.LiteralFloat32(1.0)),
            "integer representable",
        ),
        (
            lambda: astx.SubscriptExpr(
                column(), astx.LiteralInt32(0), lower=astx.LiteralInt32(0)
            ),
            "slicing is unsupported",
        ),
    ],
)
def test_nullable_analysis_rejections(
    expression: Callable[[], astx.AST], message: str
) -> None:
    """
    title: Invalid operators and extraction requests fail before lowering.
    parameters:
      expression:
        type: Callable[[], astx.AST]
      message:
        type: str
    """
    module = make_main_module(
        frame(astx.Int32(), astx.LiteralInt32(1)),
        expression(),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )
    with pytest.raises(SemanticError, match=message):
        analyze(module)


def test_rich_storage_does_not_imply_scalar_operations() -> None:
    """
    title: Reject unsupported string extraction and Boolean arithmetic.
    """
    with pytest.raises(SemanticError, match="numeric and bool"):
        analyze(
            make_main_module(
                frame(astx.String(), astx.LiteralString("x")),
                astx.SubscriptExpr(column(), astx.LiteralInt32(0)),
            )
        )
    with pytest.raises(SemanticError, match="arithmetic requires numeric"):
        analyze(
            make_main_module(
                frame(astx.Boolean(), astx.LiteralBoolean(True)),
                astx.BinaryOp("+", column(), column()),
            )
        )


@pytest.mark.parametrize(
    "type_,message",
    [
        (astx.NullableType(astx.String()), "nullable scalars"),
        (astx.ColumnType("decimal128", (10, 2)), "require DataFrame/Series"),
        (
            astx.UnionType([astx.NullableType(astx.Int32()), astx.Int32()]),
            "inside unions",
        ),
        (
            astx.DataFrameType(
                [
                    astx.DataFrameColumn(
                        "x", astx.ColumnType("decimal128", (50, 0))
                    )
                ]
            ),
            "precision",
        ),
        (
            astx.SeriesType(astx.ColumnType("timestamp", ("hours",))),
            "temporal units",
        ),
    ],
)
def test_declared_storage_rejections(
    type_: astx.DataType, message: str
) -> None:
    """
    title: Direct AST hosts receive the same physical-type validation as Arx.
    parameters:
      type_:
        type: astx.DataType
      message:
        type: str
    """
    module = make_main_module(
        astx.VariableDeclaration("bad", type_),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )
    with pytest.raises(SemanticError, match=message):
        analyze(module)


def test_rich_recordbatch_cast_translate() -> None:
    """
    title: Host-registered capabilities lower serialized schemas without Arx.
    """
    batch = astx.ClassDefStmt(
        "Batch",
        attributes=[
            astx.VariableDeclaration(
                "handle",
                astx.OpaqueHandleType("IrxRbApiBatch"),
                visibility=astx.VisibilityKind.private,
                mutability=astx.MutabilityKind.mutable,
            )
        ],
    )
    target = astx.DataFrameType(
        [
            astx.DataFrameColumn(
                "amount",
                astx.ColumnType("decimal128", (12, 3)),
                True,
            )
        ]
    )
    body = astx.Block()
    body.append(
        astx.FunctionReturn(astx.Cast(astx.Identifier("batch"), target))
    )
    function = astx.FunctionDef(
        astx.FunctionPrototype(
            "convert",
            astx.Arguments(
                astx.Argument("batch", astx.ClassType("Batch")),
            ),
            target,
        ),
        body,
    )
    module = astx.Module()
    module.block.append(batch)
    module.block.append(function)
    builder = Builder()
    text = builder.translate_modules(
        ParsedModule("capability", module, native_record_batch_class=batch),
        StaticImportResolver({}),
    )
    assert_ir_parses(text)
    assert "irx_rb_api_schema_ipc" in text
    assert "irx_rb_api_batch_to_table" in text
