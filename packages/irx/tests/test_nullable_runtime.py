"""
title: >-
  Nullable normalization, semantic boundaries and native aggregate storage.
"""

from __future__ import annotations

import subprocess

from pathlib import Path

import astx
import pytest

from irx.analysis import analyze
from irx.analysis.nullability import PRIMITIVE_PAYLOADS, normalize_nullable
from irx.analysis.schema_types import columnar_type_diagnostic
from irx.analysis.types import clone_type, is_assignable, same_type
from irx.builder import Builder
from irx.builder.backend import Visitor
from irx.diagnostics import LoweringError, SemanticError
from llvmlite import binding as llvm


def module_with(*nodes: astx.AST) -> astx.Module:
    """
    title: Wrap nullable regressions in a native entry point.
    parameters:
      nodes:
        type: astx.AST
        variadic: positional
    returns:
      type: astx.Module
    """
    body = astx.Block()
    for node in nodes:
        body.append(node)
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module = astx.Module()
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
            body,
        )
    )
    return module


def query(name: str, operation: astx.NullableOperation) -> astx.NullableQuery:
    """
    title: Build a validity operation on one local binding.
    parameters:
      name:
        type: str
      operation:
        type: astx.NullableOperation
    returns:
      type: astx.NullableQuery
    """
    return astx.NullableQuery(operation, astx.Identifier(name))


@pytest.mark.parametrize("payload_class", PRIMITIVE_PAYLOADS)
def test_normalized_nullable_is_order_independent(
    payload_class: type[astx.DataType],
) -> None:
    """
    title: Normalize primitive unions, aliases, duplicate members and clones.
    parameters:
      payload_class:
        type: type[astx.DataType]
    """
    original = astx.UnionType(
        (astx.NoneType(), payload_class(), payload_class()), alias_name="Maybe"
    )
    normalized = normalize_nullable(original)
    assert isinstance(normalized, astx.NullableType)
    assert normalized.alias_name == "Maybe"
    assert columnar_type_diagnostic(normalized) is None
    copied = clone_type(original)
    assert isinstance(copied, astx.NullableType)
    assert copied.payload_type is not normalized.payload_type
    assert same_type(copied, astx.NullableType(payload_class()))
    assert is_assignable(copied, astx.NoneType())
    assert is_assignable(copied, payload_class())
    assert not is_assignable(payload_class(), copied)


def test_nullable_widening_is_lossless_and_one_way() -> None:
    """
    title: Preserve whole-domain primitive conversion rules around validity.
    """
    narrow = astx.NullableType(astx.Int32())
    wide = astx.NullableType(astx.Int64())
    assert is_assignable(wide, narrow)
    assert not is_assignable(narrow, wide)
    assert is_assignable(
        astx.NullableType(astx.Int32()), astx.NullableType(astx.UInt16())
    )
    assert not is_assignable(
        astx.NullableType(astx.Int32()), astx.NullableType(astx.UInt32())
    )
    assert not is_assignable(astx.Int64(), narrow)
    nested = astx.UnionType((astx.UnionType((astx.NoneType(), astx.Int32())),))
    assert same_type(narrow, normalize_nullable(nested))
    general = astx.UnionType((astx.Int32(), astx.Float64()))
    assert normalize_nullable(general) is general


@pytest.mark.parametrize(
    "payload",
    [
        astx.NullableType(astx.Int32()),
    ],
)
def test_managed_or_nested_payloads_fail_in_analysis(
    payload: astx.DataType,
) -> None:
    """
    title: Reject unsupported nullable payload ownership before LLVM emission.
    parameters:
      payload:
        type: astx.DataType
    """
    declaration = astx.VariableDeclaration(
        "value", astx.NullableType(payload), value=astx.LiteralNone()
    )
    with pytest.raises(SemanticError, match="primitive numeric or Boolean"):
        analyze(module_with(declaration))


def test_uninitialized_and_inline_nullable_storage() -> None:
    """
    title: >-
      Direct ASTx locals initialize null storage and support inline values.
    """
    declaration = astx.VariableDeclaration(
        "value", astx.NullableType(astx.Int32())
    )
    inline = astx.InlineVariableDeclaration(
        "inline", astx.NullableType(astx.Int32()), value=astx.LiteralNone()
    )
    module = module_with(
        declaration,
        astx.AssertStmt(query("value", astx.NullableOperation.IS_NULL)),
        astx.AssertStmt(
            astx.NullableQuery(astx.NullableOperation.IS_NULL, inline)
        ),
    )
    output = Builder().translate(module)
    llvm.parse_assembly(output).verify()
    assert "{i1, i32}" in output


def test_missing_nullable_resolution_fails_closed() -> None:
    """
    title: Lowering cannot infer nullable meaning from the syntax node alone.
    """
    node = astx.NullableQuery(
        astx.NullableOperation.IS_NULL, astx.LiteralNone()
    )
    with pytest.raises(LoweringError, match="missing resolved nullable query"):
        Visitor().visit(node)


def test_every_primitive_nullable_executes_natively(tmp_path: Path) -> None:
    """
    title: >-
      Zero payloads remain valid in all twelve primitive storage
      representations.
    parameters:
      tmp_path:
        type: Path
    """
    nodes: list[astx.AST] = []
    for index, payload_class in enumerate(PRIMITIVE_PAYLOADS):
        name = f"value_{index}"
        payload = payload_class()
        literal: astx.Expr = astx.LiteralInt32(0)
        if isinstance(payload, astx.Boolean):
            literal = astx.LiteralBoolean(False)
        elif isinstance(payload, (astx.Float16, astx.Float32, astx.Float64)):
            literal = astx.Cast(astx.LiteralFloat32(0.0), payload_class())
        else:
            literal = astx.Cast(literal, payload_class())
        nodes.extend(
            [
                astx.VariableDeclaration(
                    name,
                    astx.NullableType(payload),
                    value=astx.LiteralNone(),
                    mutability=astx.MutabilityKind.mutable,
                ),
                astx.AssertStmt(query(name, astx.NullableOperation.IS_NULL)),
                astx.VariableAssignment(name, literal),
                astx.AssertStmt(query(name, astx.NullableOperation.IS_VALID)),
                astx.AssertStmt(
                    astx.BinaryOp(
                        "==",
                        query(name, astx.NullableOperation.EXPECT_VALID),
                        literal,
                    )
                ),
                astx.VariableAssignment(name, astx.LiteralNone()),
                astx.AssertStmt(query(name, astx.NullableOperation.IS_NULL)),
            ]
        )
    builder = Builder()
    output = builder.translate(module_with(*nodes))
    llvm.parse_assembly(output).verify()
    assert "irx_arrow_" not in output
    # Extracting an unwrapped payload must follow the guard's success block.
    assert output.index("nullable.unwrap.pass:") < output.index(
        '"nullable.payload" = extractvalue'
    )
    executable = tmp_path / "nullable_primitives"
    builder._build_from_ir(output, str(executable))
    completed = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


def test_nullable_struct_fields_have_native_layout(tmp_path: Path) -> None:
    """
    title: Copy primitive nullable fields by value without dropping validity.
    parameters:
      tmp_path:
        type: Path
    """

    def field() -> astx.FieldAccess:
        """
        title: Read the same struct slot using a fresh expression node.
        returns:
          type: astx.FieldAccess
        """
        return astx.FieldAccess(astx.Identifier("box"), "value")

    module = module_with(
        astx.VariableDeclaration(
            "box",
            astx.StructType("Box"),
            mutability=astx.MutabilityKind.mutable,
        ),
        astx.AssertStmt(
            astx.NullableQuery(astx.NullableOperation.IS_NULL, field())
        ),
        astx.BinaryOp("=", field(), astx.LiteralInt32(7)),
        astx.AssertStmt(
            astx.BinaryOp(
                "==",
                astx.NullableQuery(
                    astx.NullableOperation.EXPECT_VALID, field()
                ),
                astx.LiteralInt32(7),
            )
        ),
        astx.BinaryOp("=", field(), astx.LiteralNone()),
        astx.AssertStmt(
            astx.NullableQuery(astx.NullableOperation.IS_NULL, field())
        ),
    )
    module.block.insert(
        0,
        astx.StructDefStmt(
            name="Box",
            attributes=[
                astx.VariableDeclaration(
                    "value", astx.NullableType(astx.Int32())
                )
            ],
        ),
    )
    builder = Builder()
    text = builder.translate(module)
    llvm.parse_assembly(text).verify()
    executable = tmp_path / "nullable-struct"
    builder._build_from_ir(text, str(executable))
    completed = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize(
    "value", [astx.LiteralString("x"), astx.LiteralBoolean(True)]
)
def test_numeric_prefix_rejects_non_numeric_payload(
    value: astx.DataType,
) -> None:
    """
    title: >-
      Scalar prefix validation rejects unsupported payloads before lowering.
    parameters:
      value:
        type: astx.DataType
    """
    with pytest.raises(SemanticError, match="requires a numeric operand"):
        analyze(module_with(astx.UnaryOp("-", value)))


def test_numeric_prefix_requires_resolved_operator() -> None:
    """
    title: Scalar sign lowering must consume a resolved semantic operator.
    """
    with pytest.raises(LoweringError, match="no resolved operator"):
        Visitor().visit(astx.UnaryOp("-", astx.LiteralInt32(1)))


def test_missing_nullable_operator_resolution_fails_closed() -> None:
    """
    title: Do not rediscover null propagation from an operator AST in lowering.
    """
    operation = astx.BinaryOp(
        "+", astx.Identifier("value"), astx.LiteralInt32(1)
    )
    analyze(
        module_with(
            astx.VariableDeclaration(
                "value",
                astx.NullableType(astx.Int32()),
                value=astx.LiteralNone(),
            ),
            astx.VariableDeclaration(
                "result", astx.NullableType(astx.Int32()), value=operation
            ),
        )
    )
    operation.semantic.resolved_nullable_operator = None
    with pytest.raises(
        LoweringError, match="missing resolved nullable operator"
    ):
        Visitor().visit(operation)


def test_nullable_owner_validates_its_logical_parameters() -> None:
    """
    title: Nullable owner wrappers must not bypass logical type validation.
    """
    invalid = astx.ArrayType(
        astx.LogicalType(
            astx.LogicalKind.INT32,
            parameters=(
                astx.LogicalParameter(astx.ParameterKind.BYTE_WIDTH, 4),
            ),
        )
    )
    declaration = astx.VariableDeclaration(
        "value", astx.NullableType(invalid), value=astx.LiteralNone()
    )
    with pytest.raises(SemanticError, match="invalid columnar descriptor"):
        analyze(module_with(declaration))
