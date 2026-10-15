"""
title: Generated ownership programs for native sanitizer gates.
summary: >-
  These ASTx programs exercise IRx capabilities. They are not claims of Arx
  parser support for user-defined generators.
"""

from __future__ import annotations

from pathlib import Path

import astx

from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser


def block(*nodes: astx.AST) -> astx.Block:
    """
    title: Build a fresh statement block without shared AST nodes.
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


def tensor(value: int) -> astx.TensorLiteral:
    """
    title: Build a small Arrow-backed managed value.
    parameters:
      value:
        type: int
    returns:
      type: astx.TensorLiteral
    """
    return astx.TensorLiteral(
        (astx.LiteralInt32(value),), element_type=astx.Int32(), shape=(1,)
    )


def main_function(body: astx.Block) -> astx.FunctionDef:
    """
    title: Wrap one native sanitizer program entry point.
    parameters:
      body:
        type: astx.Block
    returns:
      type: astx.FunctionDef
    """
    return astx.FunctionDef(
        astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()), body
    )


def class_program() -> astx.Module:
    """
    title: Exercise shared class owners, Arrow field replacement and return.
    returns:
      type: astx.Module
    """
    module = astx.Module()
    module.block.append(
        astx.ClassDefStmt(
            name="Box",
            attributes=[
                astx.VariableDeclaration(
                    "values",
                    astx.TensorType(astx.Int32(), shape=(1,)),
                    mutability=astx.MutabilityKind.mutable,
                    value=tensor(7),
                ),
                astx.VariableDeclaration(
                    "maybe",
                    astx.NullableType(
                        astx.ArrayType(
                            astx.LogicalType(astx.LogicalKind.INT32)
                        )
                    ),
                    mutability=astx.MutabilityKind.mutable,
                    value=astx.ArrayLiteral(
                        astx.ArrayType(
                            astx.LogicalType(astx.LogicalKind.INT32)
                        ),
                        (astx.LiteralInt32(2),),
                    ),
                ),
                astx.VariableDeclaration(
                    "builder",
                    astx.NullableType(
                        astx.ArrayBuilderType(
                            astx.LogicalType(astx.LogicalKind.INT32)
                        )
                    ),
                    value=astx.ArrayLiteral(
                        astx.ArrayBuilderType(
                            astx.LogicalType(astx.LogicalKind.INT32)
                        ),
                        (),
                    ),
                ),
            ],
        )
    )
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype(
                "make_box", astx.Arguments(), astx.ClassType("Box")
            ),
            block(astx.FunctionReturn(astx.ClassConstruct("Box"))),
        )
    )
    module.block.append(
        main_function(
            block(
                astx.VariableDeclaration(
                    "first",
                    astx.ClassType("Box"),
                    value=astx.FunctionCall("make_box", []),
                ),
                astx.VariableDeclaration(
                    "second",
                    astx.ClassType("Box"),
                    value=astx.Identifier("first"),
                ),
                astx.BinaryOp(
                    "=",
                    astx.FieldAccess(astx.Identifier("second"), "values"),
                    tensor(9),
                ),
                astx.BinaryOp(
                    "=",
                    astx.FieldAccess(astx.Identifier("second"), "maybe"),
                    astx.LiteralNone(),
                ),
                astx.FunctionReturn(astx.LiteralInt32(0)),
            )
        )
    )
    return module


def generator_program(
    *, early_close: bool, fail_after_resume: bool
) -> astx.Module:
    """
    title: Exercise suspended owners on exhaustion, early close and failure.
    parameters:
      early_close:
        type: bool
      fail_after_resume:
        type: bool
    returns:
      type: astx.Module
    """
    module = astx.Module()
    body = block(
        astx.VariableDeclaration(
            "before",
            astx.String(),
            value=astx.BinaryOp(
                "+", astx.LiteralString("owned"), astx.LiteralString(" before")
            ),
        ),
        astx.VariableDeclaration(
            "data",
            astx.TensorType(astx.Int32(), shape=(1,)),
            value=tensor(3),
        ),
        astx.VariableDeclaration(
            "layout", astx.SchemaType(), value=descriptor_schema()
        ),
        astx.YieldStmt(astx.LiteralInt32(1)),
        astx.VariableDeclaration(
            "after",
            astx.String(),
            value=astx.BinaryOp(
                "+", astx.LiteralString("owned"), astx.LiteralString(" after")
            ),
        ),
    )
    if fail_after_resume:
        body.append(astx.AssertStmt(astx.LiteralBoolean(False)))
    body.append(astx.YieldStmt(astx.LiteralInt32(2)))
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype(
                "values", astx.Arguments(), astx.GeneratorType(astx.Int32())
            ),
            body,
        )
    )
    loop_body = block(astx.BreakStmt()) if early_close else block()
    module.block.append(
        main_function(
            block(
                astx.ForInLoopStmt(
                    astx.Identifier("item"),
                    astx.FunctionCall("values", []),
                    loop_body,
                ),
                astx.FunctionReturn(astx.LiteralInt32(0)),
            )
        )
    )
    return module


def descriptor_schema() -> astx.SchemaLiteral:
    """
    title: Build a recursive schema owner for lifecycle sanitizer probes.
    returns:
      type: astx.SchemaLiteral
    """
    return astx.SchemaLiteral(
        astx.Schema(
            (
                astx.SchemaField(
                    "name", astx.LogicalType(astx.LogicalKind.STRING)
                ),
            )
        )
    )


def descriptor_program(*, fail: bool) -> astx.Module:
    """
    title: >-
      Exercise descriptor class fields, projection and independent strings.
    parameters:
      fail:
        type: bool
    returns:
      type: astx.Module
    """
    module = astx.Module()
    module.block.append(
        astx.ClassDefStmt(
            name="Layout",
            attributes=[
                astx.VariableDeclaration(
                    "schema",
                    astx.SchemaType(),
                    mutability=astx.MutabilityKind.mutable,
                    value=descriptor_schema(),
                )
            ],
        )
    )
    owner = astx.FieldAccess(astx.Identifier("box"), "schema")
    field = astx.DescriptorQuery(
        astx.DescriptorOperation.SCHEMA_FIELD,
        (owner, astx.LiteralInt32(-1 if fail else 0)),
    )
    body = block(
        astx.VariableDeclaration(
            "box",
            astx.ClassType("Layout"),
            value=astx.ClassConstruct("Layout"),
        ),
        astx.VariableDeclaration("field", astx.FieldType(), value=field),
        astx.VariableDeclaration(
            "name",
            astx.String(),
            value=astx.DescriptorQuery(
                astx.DescriptorOperation.FIELD_NAME,
                (astx.Identifier("field"),),
            ),
        ),
        astx.BinaryOp(
            "=",
            astx.FieldAccess(astx.Identifier("box"), "schema"),
            descriptor_schema(),
        ),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )
    module.block.append(main_function(body))
    return module


def nullable_failure_program() -> astx.Module:
    """
    title: Clean Arrow descriptor and string owners on a fatal nullable unwrap.
    returns:
      type: astx.Module
    """
    module = astx.Module()
    module.block.append(
        main_function(
            block(
                astx.VariableDeclaration(
                    "layout", astx.SchemaType(), value=descriptor_schema()
                ),
                astx.VariableDeclaration(
                    "text",
                    astx.String(),
                    value=astx.BinaryOp(
                        "+",
                        astx.LiteralString("owned "),
                        astx.LiteralString("text"),
                    ),
                ),
                astx.VariableDeclaration(
                    "missing",
                    astx.NullableType(astx.Int32()),
                    value=astx.LiteralNone(),
                ),
                astx.FunctionReturn(
                    astx.NullableQuery(
                        astx.NullableOperation.EXPECT_VALID,
                        astx.Identifier("missing"),
                    )
                ),
            )
        )
    )
    return module


def array_program(*, fail: bool) -> astx.Module:
    """
    title: Exercise typed array owners, slices and failed nullable extraction.
    parameters:
      fail:
        type: bool
    returns:
      type: astx.Module
    """
    type_ = astx.ArrayType(
        astx.LogicalType(astx.LogicalKind.INT32), nullable=True
    )
    module = astx.Module()
    body = block(
        astx.VariableDeclaration(
            "values",
            type_,
            value=astx.ArrayLiteral(
                type_,
                (astx.LiteralInt32(1), astx.LiteralNone()),
            ),
        ),
        astx.VariableDeclaration(
            "view",
            type_,
            value=astx.ArrayQuery(
                astx.ArrayOperation.SLICE,
                (
                    astx.Identifier("values"),
                    astx.LiteralInt32(1),
                    astx.LiteralInt32(1),
                ),
            ),
        ),
        astx.VariableDeclaration(
            "copy",
            type_,
            value=astx.ArrayQuery(
                astx.ArrayOperation.COPY,
                (astx.Identifier("view"),),
            ),
        ),
    )
    if fail:
        body.append(
            astx.FunctionReturn(
                astx.NullableQuery(
                    astx.NullableOperation.EXPECT_VALID,
                    astx.ArrayQuery(
                        astx.ArrayOperation.AT,
                        (
                            astx.Identifier("view"),
                            astx.LiteralInt32(0),
                        ),
                    ),
                )
            )
        )
    else:
        body.append(
            astx.AssertStmt(
                astx.ArrayQuery(
                    astx.ArrayOperation.EQUAL,
                    (astx.Identifier("view"), astx.Identifier("copy")),
                )
            )
        )
        body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module.block.append(main_function(body))
    return module


def container_owners_program(*, fail: bool) -> astx.Module:
    """
    title: Exercise unique builders, chunks and nullable shared owner cleanup.
    parameters:
      fail:
        type: bool
    returns:
      type: astx.Module
    """
    logical = astx.LogicalType(astx.LogicalKind.INT32)
    array = astx.ArrayType(logical)
    builder = astx.ArrayBuilderType(logical)
    chunked = astx.ChunkedArrayType(logical)
    optional = astx.NullableType(chunked)
    body = block(
        astx.VariableDeclaration(
            "b", builder, value=astx.ArrayLiteral(builder, ())
        ),
        astx.ArrayQuery(
            astx.ArrayOperation.APPEND,
            (astx.Identifier("b"), astx.LiteralInt32(3)),
        ),
        astx.VariableDeclaration(
            "a",
            array,
            value=astx.ArrayQuery(
                astx.ArrayOperation.FINISH, (astx.Identifier("b"),)
            ),
        ),
        astx.VariableDeclaration(
            "c",
            optional,
            value=astx.ArrayLiteral(chunked, (astx.Identifier("a"),)),
            mutability=astx.MutabilityKind.mutable,
        ),
        astx.VariableDeclaration(
            "alias", optional, value=astx.Identifier("c")
        ),
        astx.BinaryOp("=", astx.Identifier("c"), astx.LiteralNone()),
        astx.VariableDeclaration(
            "present",
            chunked,
            value=astx.NullableQuery(
                astx.NullableOperation.EXPECT_VALID, astx.Identifier("alias")
            ),
        ),
    )
    if fail:
        body.append(
            astx.NullableQuery(
                astx.NullableOperation.EXPECT_VALID, astx.Identifier("c")
            )
        )
    else:
        body.append(
            astx.AssertStmt(
                astx.BinaryOp(
                    "==",
                    astx.ArrayQuery(
                        astx.ArrayOperation.LENGTH,
                        (astx.Identifier("present"),),
                    ),
                    astx.LiteralInt64(1),
                )
            )
        )
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module = astx.Module()
    module.block.append(main_function(body))
    return module


def tabular_owners_program(*, fail: bool) -> astx.Module:
    """
    title: Exercise tabular conversion, optional parents and detached children.
    parameters:
      fail:
        type: bool
    returns:
      type: astx.Module
    """
    logical = astx.LogicalType(astx.LogicalKind.INT32)
    schema = astx.Schema((astx.SchemaField("a", logical, nullable=False),))
    batch_type = astx.RecordBatchType(schema)
    optional = astx.NullableType(astx.TableType(schema))
    array = astx.ArrayLiteral(astx.ArrayType(logical), (astx.LiteralInt32(7),))
    body = block(
        astx.VariableDeclaration(
            "batch",
            batch_type,
            value=astx.TabularLiteral(
                batch_type, (astx.LiteralInt64(1), array)
            ),
        ),
        astx.VariableDeclaration(
            "table",
            optional,
            value=astx.TabularQuery(
                astx.TabularOperation.TO_TABLE, (astx.Identifier("batch"),)
            ),
            mutability=astx.MutabilityKind.mutable,
        ),
        astx.VariableDeclaration(
            "kept",
            astx.ChunkedArrayType(logical),
            value=astx.TabularQuery(
                astx.TabularOperation.COLUMN,
                (
                    astx.NullableQuery(
                        astx.NullableOperation.EXPECT_VALID,
                        astx.Identifier("table"),
                    ),
                    astx.LiteralString("a"),
                ),
            ),
        ),
        astx.BinaryOp("=", astx.Identifier("table"), astx.LiteralNone()),
        astx.ArrayQuery(
            astx.ArrayOperation.AT,
            (astx.Identifier("kept"), astx.LiteralInt64(0)),
        ),
    )
    if fail:
        body.append(
            astx.TabularQuery(
                astx.TabularOperation.SLICE,
                (
                    astx.Identifier("batch"),
                    astx.LiteralInt64(0),
                    astx.LiteralInt64(2),
                ),
            )
        )
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module = astx.Module()
    module.block.append(main_function(body))
    return module


def scalar_owners_program(*, fail: bool) -> astx.Module:
    """
    title: Exercise nullable scalar copies, array parents and failure cleanup.
    parameters:
      fail:
        type: bool
    returns:
      type: astx.Module
    """
    logical = astx.LogicalType(astx.LogicalKind.STRING)
    scalar = astx.ScalarType(logical)
    optional = astx.NullableType(scalar)
    array = astx.ArrayType(logical, nullable=True)
    body = block(
        astx.VariableDeclaration(
            "parent",
            astx.NullableType(array),
            value=astx.ArrayLiteral(
                array,
                (
                    astx.ScalarLiteral(scalar, (astx.LiteralString("owned"),)),
                    astx.LiteralNone(),
                ),
            ),
            mutability=astx.MutabilityKind.mutable,
        ),
        astx.VariableDeclaration(
            "child",
            optional,
            value=astx.ArrayQuery(
                astx.ArrayOperation.AT,
                (
                    astx.NullableQuery(
                        astx.NullableOperation.EXPECT_VALID,
                        astx.Identifier("parent"),
                    ),
                    astx.LiteralInt64(0),
                ),
            ),
            mutability=astx.MutabilityKind.mutable,
        ),
        astx.VariableDeclaration(
            "kept", optional, value=astx.Identifier("child")
        ),
        astx.BinaryOp("=", astx.Identifier("child"), astx.LiteralNone()),
        astx.BinaryOp("=", astx.Identifier("parent"), astx.LiteralNone()),
        astx.AssertStmt(
            astx.BinaryOp(
                "==",
                astx.ScalarQuery(
                    astx.ScalarOperation.TEXT,
                    (
                        astx.NullableQuery(
                            astx.NullableOperation.EXPECT_VALID,
                            astx.Identifier("kept"),
                        ),
                    ),
                ),
                astx.LiteralString("owned"),
            )
        ),
    )
    if fail:
        body.append(
            astx.NullableQuery(
                astx.NullableOperation.EXPECT_VALID, astx.Identifier("child")
            )
        )
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module = astx.Module()
    module.block.append(main_function(body))
    return module


def source_ownership_program(name: str) -> astx.Module:
    """
    title: Parse a committed source example for the native lifecycle gate.
    parameters:
      name:
        type: str
    returns:
      type: astx.Module
    """
    path = Path(__file__).resolve().parents[1] / "examples" / f"{name}.x"
    ArxIO.string_to_buffer(path.read_text())
    return Parser().parse(Lexer().lex())


def ownership_programs() -> tuple[tuple[str, astx.Module, int], ...]:
    """
    title: Return independent generated programs and expected exit statuses.
    returns:
      type: tuple[tuple[str, astx.Module, int], Ellipsis]
    """
    return (
        *(
            (name, source_ownership_program(name), 0)
            for name in (
                "nullable_strings",
                "nullable_collections",
                "extension_values",
                "columnar_interchange",
                "dataframe_adapters",
            )
        ),
        ("scalar_owners", scalar_owners_program(fail=False), 0),
        ("scalar_failure", scalar_owners_program(fail=True), 1),
        ("tabular_owners", tabular_owners_program(fail=False), 0),
        ("tabular_failure", tabular_owners_program(fail=True), 1),
        ("container_owners", container_owners_program(fail=False), 0),
        ("container_failure", container_owners_program(fail=True), 1),
        ("array_owners", array_program(fail=False), 0),
        ("array_failure", array_program(fail=True), 1),
        ("class_owners", class_program(), 0),
        ("descriptor_owners", descriptor_program(fail=False), 0),
        ("descriptor_failure", descriptor_program(fail=True), 1),
        ("nullable_failure", nullable_failure_program(), 1),
        (
            "generator_exhaustion",
            generator_program(early_close=False, fail_after_resume=False),
            0,
        ),
        (
            "generator_early_close",
            generator_program(early_close=True, fail_after_resume=False),
            0,
        ),
        (
            "generator_failure",
            generator_program(early_close=False, fail_after_resume=True),
            1,
        ),
    )
