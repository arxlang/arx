"""
title: Exact numeric sequence semantics and shared consumer lowering.
"""

import shutil
import subprocess

from collections.abc import Callable
from pathlib import Path
from typing import cast

import astx
import pytest

from irx.analysis import SemanticError, analyze
from irx.analysis.types import contains_template_variables, same_type
from irx.builder import Builder

from .conftest import assert_ir_parses, make_main_module

SCALARS: tuple[
    tuple[astx.DataType, Callable[[int], astx.DataType], int], ...
] = (
    (astx.Int8(), astx.LiteralInt8, -128),
    (astx.Int16(), astx.LiteralInt16, -32768),
    (astx.Int32(), astx.LiteralInt32, -(2**31)),
    (astx.Int64(), astx.LiteralInt64, 2**53 + 1),
    (astx.UInt8(), astx.LiteralUInt8, 255),
    (astx.UInt16(), astx.LiteralUInt16, 65535),
    (astx.UInt32(), astx.LiteralUInt32, 2**32 - 1),
    (astx.UInt64(), astx.LiteralUInt64, 2**64 - 1),
    (astx.Float32(), lambda n: astx.LiteralFloat32(float(n)), 7),
    (astx.Float64(), lambda n: astx.LiteralFloat64(float(n)), 7),
)


def block(*nodes: astx.AST) -> astx.Block:
    """
    title: Build a block in source evaluation order.
    parameters:
      nodes:
        type: astx.AST
        variadic: positional
    returns:
      type: astx.Block
    """
    result = astx.Block()
    for node in nodes:
        result.append(node)
    return result


def consumer() -> astx.FunctionDef:
    """
    title: Build one generic consumer, shared by every adapter and width.
    returns:
      type: astx.FunctionDef
    """
    bound = astx.UnionType(tuple(type_ for type_, _, _ in SCALARS))
    variable = astx.TemplateTypeVar("T", bound=bound)
    prototype = astx.FunctionPrototype(
        "consume",
        astx.Arguments(astx.Argument("values", astx.SequenceType(variable))),
        return_type=variable,
    )
    astx.set_template_params(prototype, (astx.TemplateParam("T", bound),))
    source = astx.Identifier("values")
    return astx.FunctionDef(
        prototype,
        block(
            astx.VariableDeclaration(
                "index",
                astx.Int64(),
                value=astx.LiteralInt64(0),
                mutability=astx.MutabilityKind.mutable,
            ),
            astx.ForInLoopStmt(
                astx.InlineVariableDeclaration("item", variable),
                source,
                block(
                    astx.AssertStmt(
                        astx.BinaryOp(
                            "==",
                            astx.Identifier("item"),
                            astx.SubscriptExpr(
                                source, astx.Identifier("index")
                            ),
                        )
                    ),
                    astx.VariableAssignment(
                        "index",
                        astx.BinaryOp(
                            "+", astx.Identifier("index"), astx.LiteralInt64(1)
                        ),
                    ),
                ),
            ),
            astx.AssertStmt(
                astx.BinaryOp(
                    "==",
                    astx.Identifier("index"),
                    astx.CollectionLength(source),
                )
            ),
            astx.FunctionReturn(
                astx.SubscriptExpr(source, astx.LiteralInt32(1))
            ),
        ),
    )


def matrix_module() -> astx.Module:
    """
    title: Exercise inferred and explicit calls with exact scalar metadata.
    returns:
      type: astx.Module
    """
    body: list[astx.AST] = []
    for number, (type_, literal, maximum) in enumerate(SCALARS):
        name = f"frame{number}"
        frame_type = astx.DataFrameType([astx.DataFrameColumn("x", type_)])
        body.append(
            astx.VariableDeclaration(
                name,
                frame_type,
                value=astx.DataFrameLiteral(
                    [
                        astx.DataFrameLiteralColumn(
                            "x", (literal(0), literal(maximum))
                        )
                    ],
                    type_=frame_type,
                ),
            )
        )
        sources = (
            astx.ListExpr([literal(0), literal(maximum)]),
            astx.LiteralList(
                [
                    cast(astx.Literal, literal(0)),
                    cast(astx.Literal, literal(maximum)),
                ]
            ),
            astx.TensorLiteral(
                [literal(0), literal(maximum)], element_type=type_, shape=(2,)
            ),
            astx.DataFrameColumnAccess(astx.Identifier(name), "x"),
        )
        for source in sources:
            for explicit in (False, True):
                call = astx.FunctionCall(
                    "consume", [cast(astx.DataType, source)]
                )
                if explicit:
                    astx.set_template_args(call, (type_,))
                body.append(
                    astx.AssertStmt(
                        astx.BinaryOp("==", call, literal(maximum))
                    )
                )
    module = make_main_module(*body, astx.FunctionReturn(astx.LiteralInt32(0)))
    module.block.insert(0, consumer())
    return module


@pytest.fixture(scope="module")
def sequence_matrix_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    title: Compile one generic definition for all numeric source families.
    parameters:
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: Path
    """
    if shutil.which("clang") is None:
        pytest.skip("native sequence checks require clang")
    module = matrix_module()
    builder = Builder()
    text = builder.translate(module)
    generated = astx.generated_template_nodes(module)
    assert len(generated) == len(SCALARS)
    for definition in generated:
        assert isinstance(definition, astx.FunctionDef)
        element = definition.prototype.return_type
        assert not contains_template_variables(element)
        loop = definition.body.nodes[1]
        assert isinstance(loop, astx.ForInLoopStmt)
        assert same_type(loop.target.type_, element)
        assert same_type(
            loop.semantic.resolved_iteration.element_type, element
        )
    assert_ir_parses(text)
    assert "irx_arrow_sequence_snapshot" in text
    assert "irx_arrow_series_slice" not in text
    executable = tmp_path_factory.mktemp("sequence-matrix") / "probe"
    builder._build_from_ir(text, str(executable))
    return executable


def test_sequence_matrix_semantics_and_execution(
    sequence_matrix_binary: Path,
) -> None:
    """
    title: Execute all widths and source kinds using one verified artifact.
    parameters:
      sequence_matrix_binary:
        type: Path
    """
    result = subprocess.run(
        [str(sequence_matrix_binary)], capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "source_type",
    [
        astx.ListType([astx.Boolean()]),
        astx.ListType([astx.Float64()]),
        astx.TensorType(astx.Int64(), shape=(2, 2)),
        astx.SeriesType(astx.Int64(), nullable=True),
        astx.DataFrameType(),
        astx.GeneratorType(astx.Int64()),
    ],
)
def test_sequence_rejects_implicit_conversion(
    source_type: astx.DataType,
) -> None:
    """
    title: >-
      Reject Boolean, widening, nullable erasure, flattening and iterators.
    parameters:
      source_type:
        type: astx.DataType
    """
    target = astx.FunctionDef(
        astx.FunctionPrototype(
            "target",
            astx.Arguments(
                astx.Argument("x", astx.SequenceType(astx.Int64()))
            ),
            return_type=astx.Int64(),
        ),
        block(
            astx.FunctionReturn(
                astx.SubscriptExpr(astx.Identifier("x"), astx.LiteralInt32(0))
            )
        ),
    )
    caller = astx.FunctionDef(
        astx.FunctionPrototype(
            "caller",
            astx.Arguments(astx.Argument("source", source_type)),
            return_type=astx.Int64(),
        ),
        block(
            astx.FunctionReturn(
                astx.FunctionCall("target", [astx.Identifier("source")])
            )
        ),
    )
    module = astx.Module()
    module.block.append(target)
    module.block.append(caller)
    with pytest.raises(SemanticError, match=r"expects|sequence"):
        analyze(module)


@pytest.mark.parametrize(
    "storage",
    [
        astx.SequenceType(astx.Int64()),
        astx.ListType([astx.SequenceType(astx.Int64())]),
        astx.NullableType(astx.SequenceType(astx.Int64())),
    ],
)
def test_sequence_borrows_cannot_escape(storage: astx.DataType) -> None:
    """
    title: Reject sequence descriptors in locals, returns, and containers.
    parameters:
      storage:
        type: astx.DataType
    """
    module = make_main_module(
        astx.VariableDeclaration("escape", storage),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )
    with pytest.raises(SemanticError, match="sequence borrows"):
        analyze(module)


@pytest.mark.parametrize(
    "keywords,message",
    [
        ((), "requires max_items"),
        (
            (astx.KeywordArgument("limit", astx.LiteralInt32(2)),),
            "list expects",
        ),
        (
            (astx.KeywordArgument("max_items", astx.LiteralInt32(-1)),),
            "nonnegative",
        ),
        (
            (astx.KeywordArgument("max_items", astx.LiteralFloat64(2.0)),),
            "representable in i64",
        ),
        (
            (
                astx.KeywordArgument(
                    "max_items", astx.LiteralUInt64(2**64 - 1)
                ),
            ),
            "representable in i64",
        ),
    ],
)
def test_materialization_validates_unsized_bounds(
    keywords: tuple[astx.KeywordArgument, ...], message: str
) -> None:
    """
    title: Reject missing, unknown, negative, and inexact iterator bounds.
    parameters:
      keywords:
        type: tuple[astx.KeywordArgument, Ellipsis]
      message:
        type: str
    """
    function = astx.FunctionDef(
        astx.FunctionPrototype(
            "copy",
            astx.Arguments(
                astx.Argument("source", astx.GeneratorType(astx.Int32()))
            ),
            return_type=astx.ListType([astx.Int32()]),
        ),
        block(
            astx.FunctionReturn(
                astx.FunctionCall(
                    "list", [astx.Identifier("source")], keywords=keywords
                )
            )
        ),
    )
    module = astx.Module()
    module.block.append(function)
    with pytest.raises(SemanticError, match=message):
        analyze(module)


@pytest.mark.parametrize("empty", [False, True])
def test_bytes_materialization_metadata(empty: bool) -> None:
    """
    title: >-
      Reanalysis preserves checked octet construction and read-only access.
    parameters:
      empty:
        type: bool
    """
    source = astx.FunctionCall(
        "bytes", [] if empty else [astx.ListExpr([astx.LiteralInt64(255)])]
    )
    value = astx.Identifier("octets")
    index = astx.SubscriptExpr(value, astx.LiteralInt64(0))
    length = astx.CollectionLength(value)
    module = make_main_module(
        astx.VariableDeclaration("octets", astx.Bytes(), value=source),
        length,
        *([] if empty else [index]),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )
    for _ in range(2):
        analyze(module)
        assert isinstance(source.semantic.resolved_type, astx.Bytes)
        assert source.semantic.materialization.checked_bytes
        assert isinstance(length.semantic.resolved_type, astx.Int64)
        if not empty:
            assert isinstance(index.semantic.resolved_type, astx.UInt8)
    assert_ir_parses(Builder().translate(module))
    assert not same_type(astx.Bytes(), astx.ListType([astx.UInt8()]))
    assert not same_type(astx.Bytes(), astx.ColumnType("binary"))
