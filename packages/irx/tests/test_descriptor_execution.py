"""
title: Native descriptor semantics, LLVM lowering, and lifetime regressions.
"""

from __future__ import annotations

import ctypes
import subprocess

from collections.abc import Iterator
from pathlib import Path

import astx
import pyarrow as pa
import pytest

from irx.analysis import analyze
from irx.analysis.schema import canonical_schema
from irx.analysis.schema_types import resolve_logical_type
from irx.builder import Builder
from irx.diagnostics import LoweringError, SemanticError
from irx.schema_interop import schema_from_pyarrow, schema_to_pyarrow
from llvmlite import binding as llvm

from .schema_cases import logical_type_cases
from .test_arrow_runtime import (
    ArrowSchemaStruct,
    _assert_arrow_ok,
    _load_arrow_runtime_library,
    _release_c_schema,
)

NULL_POINTER = 101
TYPE_MISMATCH = 103
INDEX_OUT_OF_BOUNDS = 105
OUT_OF_MEMORY = 200
INT64_WIDTH = 64


@pytest.fixture(scope="module")
def descriptor_runtime() -> Iterator[ctypes.CDLL]:
    """
    title: Use generated ctypes signatures with test-only native failpoints.
    returns:
      type: Iterator[ctypes.CDLL]
    """
    with _load_arrow_runtime_library(failure_injection=True) as library:
        yield library


@pytest.mark.parametrize(
    "logical", logical_type_cases(), ids=lambda value: value.kind.value
)
def test_native_field_and_type_owners_preserve_metadata(
    descriptor_runtime: ctypes.CDLL,
    logical: astx.LogicalType,
) -> None:
    """
    title: Field/type copies, exports and retain tokens outlive their producer.
    parameters:
      descriptor_runtime:
        type: ctypes.CDLL
      logical:
        type: astx.LogicalType
    """
    lib = descriptor_runtime
    expected = canonical_schema(
        astx.Schema(
            (
                astx.SchemaField(
                    "λ",
                    logical,
                    nullable=True,
                    metadata=((b"field", b"\0\xff"),),
                ),
            )
        )
    )
    source = schema_to_pyarrow(expected).field(0)
    exported = ArrowSchemaStruct()
    source._export_to_c(ctypes.addressof(exported))
    original_release = exported.release
    field, retained, type_ = (
        ctypes.c_void_p(),
        ctypes.c_void_p(),
        ctypes.c_void_p(),
    )
    output = ArrowSchemaStruct()
    try:
        _assert_arrow_ok(
            lib,
            lib.irx_arrow_field_import_copy(
                ctypes.byref(exported), ctypes.byref(field)
            ),
        )
        assert exported.release == original_release
        _release_c_schema(exported)
        del source
        _assert_arrow_ok(
            lib, lib.irx_arrow_field_retain(field, ctypes.byref(retained))
        )
        _assert_arrow_ok(
            lib, lib.irx_arrow_field_type(field, ctypes.byref(type_))
        )
        _assert_arrow_ok(lib, lib.irx_arrow_field_release(ctypes.byref(field)))
        _assert_arrow_ok(
            lib, lib.irx_arrow_field_export(retained, ctypes.byref(output))
        )
        _assert_arrow_ok(
            lib, lib.irx_arrow_field_release(ctypes.byref(retained))
        )
        restored = pa.Field._import_from_c(ctypes.addressof(output))
        assert schema_from_pyarrow(pa.schema([restored])) == expected
        _assert_arrow_ok(
            lib, lib.irx_arrow_type_export(type_, ctypes.byref(output))
        )
        _assert_arrow_ok(lib, lib.irx_arrow_type_release(ctypes.byref(type_)))
        restored_type = pa.Field._import_from_c(ctypes.addressof(output))
        assert (
            schema_from_pyarrow(pa.schema([restored_type])).fields[0].type_
            == expected.fields[0].type_
        )
        assert restored_type.name == ""
        assert not restored_type.nullable
    finally:
        _release_c_schema(exported)
        _release_c_schema(output)
        lib.irx_arrow_field_release(ctypes.byref(field))
        lib.irx_arrow_field_release(ctypes.byref(retained))
        lib.irx_arrow_type_release(ctypes.byref(type_))


def module_with(*nodes: astx.AST) -> astx.Module:
    """
    title: Build an independent function body for each native regression.
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


def query(
    operation: astx.DescriptorOperation, *arguments: astx.Expr
) -> astx.DescriptorQuery:
    """
    title: Build a fresh focused descriptor query.
    parameters:
      operation:
        type: astx.DescriptorOperation
      arguments:
        type: astx.Expr
        variadic: positional
    returns:
      type: astx.DescriptorQuery
    """
    return astx.DescriptorQuery(operation, arguments)


def test_every_logical_family_builds_and_runs_native(tmp_path: Path) -> None:
    """
    title: >-
      All 45 logical families lower via resolved trees and execute natively.
    parameters:
      tmp_path:
        type: Path
    """
    nodes: list[astx.AST] = []
    for logical in logical_type_cases():
        literal = astx.TypeDescriptorLiteral(logical)
        nodes.append(
            astx.AssertStmt(
                query(
                    astx.DescriptorOperation.EQUAL,
                    literal,
                    astx.TypeDescriptorLiteral(logical),
                )
            )
        )
        physical = resolve_logical_type(logical)
        # Dictionary/extension bit widths describe their storage in the model;
        # Arrow's FixedWidthType query applies to the concrete Arrow type.
        if logical.kind not in {
            astx.LogicalKind.DICTIONARY,
            astx.LogicalKind.EXTENSION,
        }:
            nodes.append(
                astx.AssertStmt(
                    astx.BinaryOp(
                        "==",
                        query(
                            astx.DescriptorOperation.TYPE_BIT_WIDTH,
                            astx.TypeDescriptorLiteral(logical),
                        ),
                        astx.LiteralInt64(
                            physical.bit_width
                            if physical.bit_width is not None
                            else -1
                        ),
                    )
                )
            )
    builder = Builder()
    module = module_with(*nodes)
    ir_text = builder.translate(module)
    llvm.parse_assembly(ir_text).verify()
    assert "PyArrow" not in ir_text
    assert "irx_arrow_runtime_has_feature" in ir_text
    assert all(
        node.condition.arguments[
            0
        ].semantic.resolved_descriptor.literal.physical
        for node in nodes
        if isinstance(node.condition, astx.DescriptorQuery)
    )
    executable = tmp_path / "all-descriptors"
    builder.build(module, str(executable))
    result = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "operation,arguments",
    [
        (astx.DescriptorOperation.SCHEMA_FIELD_COUNT, ()),
        (astx.DescriptorOperation.SCHEMA_FIELD_COUNT, (astx.LiteralInt32(3),)),
        (
            astx.DescriptorOperation.FIELD_TYPE,
            (astx.SchemaLiteral(astx.Schema()),),
        ),
        (
            astx.DescriptorOperation.EQUAL,
            (
                astx.SchemaLiteral(astx.Schema()),
                astx.TypeDescriptorLiteral(
                    astx.LogicalType(astx.LogicalKind.INT32)
                ),
            ),
        ),
        (
            astx.DescriptorOperation.SCHEMA_FIELD,
            (astx.SchemaLiteral(astx.Schema()), astx.LiteralFloat32(1.0)),
        ),
    ],
)
def test_descriptor_invalid_operands_fail_in_analysis(
    operation: astx.DescriptorOperation, arguments: tuple[astx.Expr, ...]
) -> None:
    """
    title: Reject wrong arity and operand types before native lowering.
    parameters:
      operation:
        type: astx.DescriptorOperation
      arguments:
        type: tuple[astx.Expr, Ellipsis]
    """
    with pytest.raises(SemanticError, match="invalid operands"):
        analyze(module_with(astx.DescriptorQuery(operation, arguments)))


def test_descriptor_outputs_fail_closed_and_inputs_remain_valid(
    descriptor_runtime: ctypes.CDLL,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: >-
      Bounds, kind mismatches and allocation failures do not consume owners.
    parameters:
      descriptor_runtime:
        type: ctypes.CDLL
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    lib = descriptor_runtime
    producer = pa.schema([pa.field("x", pa.int64(), nullable=True)])
    c_schema = ArrowSchemaStruct()
    producer._export_to_c(ctypes.addressof(c_schema))
    schema, field, type_ = (
        ctypes.c_void_p(),
        ctypes.c_void_p(),
        ctypes.c_void_p(),
    )
    try:
        _assert_arrow_ok(
            lib,
            lib.irx_arrow_schema_import_copy(
                ctypes.byref(c_schema), ctypes.byref(schema)
            ),
        )
        field.value = 123
        assert (
            lib.irx_arrow_schema_field(schema, -1, ctypes.byref(field))
            == INDEX_OUT_OF_BOUNDS
        )
        assert field.value is None
        count = ctypes.c_int64(123)
        _assert_arrow_ok(
            lib, lib.irx_arrow_schema_num_fields(schema, ctypes.byref(count))
        )
        assert count.value == 1
        monkeypatch.setenv("IRX_ARROW_TEST_FAIL_OPERATION", "schema_field")
        assert (
            lib.irx_arrow_schema_field(schema, 0, ctypes.byref(field))
            == OUT_OF_MEMORY
        )
        assert field.value is None
        monkeypatch.delenv("IRX_ARROW_TEST_FAIL_OPERATION")
        _assert_arrow_ok(
            lib, lib.irx_arrow_schema_field(schema, 0, ctypes.byref(field))
        )
        original = field.value
        assert lib.irx_arrow_type_release(ctypes.byref(field)) == TYPE_MISMATCH
        assert field.value == original
        assert lib.irx_arrow_field_type(field, None) == NULL_POINTER
        _assert_arrow_ok(
            lib, lib.irx_arrow_field_type(field, ctypes.byref(type_))
        )
        output = ctypes.c_int32(123)
        assert (
            lib.irx_arrow_field_nullable(type_, ctypes.byref(output))
            == TYPE_MISMATCH
        )
        assert output.value == 0
        _assert_arrow_ok(
            lib, lib.irx_arrow_schema_release(ctypes.byref(schema))
        )
        _assert_arrow_ok(lib, lib.irx_arrow_field_release(ctypes.byref(field)))
        width = ctypes.c_int64()
        _assert_arrow_ok(
            lib, lib.irx_arrow_type_bit_width(type_, ctypes.byref(width))
        )
        assert width.value == INT64_WIDTH
        _assert_arrow_ok(lib, lib.irx_arrow_type_release(ctypes.byref(type_)))
        _assert_arrow_ok(lib, lib.irx_arrow_type_release(ctypes.byref(type_)))
    finally:
        _release_c_schema(c_schema)
        lib.irx_arrow_schema_release(ctypes.byref(schema))
        lib.irx_arrow_field_release(ctypes.byref(field))
        lib.irx_arrow_type_release(ctypes.byref(type_))


@pytest.mark.parametrize("kind", ["type", "field"])
def test_descriptor_import_failure_preserves_callbacks(
    descriptor_runtime: ctypes.CDLL,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    """
    title: >-
      Test-only entry failpoints clear outputs and preserve external C Data.
    parameters:
      descriptor_runtime:
        type: ctypes.CDLL
      monkeypatch:
        type: pytest.MonkeyPatch
      kind:
        type: str
    """
    producer = pa.field("x", pa.int64())
    exported = ArrowSchemaStruct()
    producer._export_to_c(ctypes.addressof(exported))
    callback = exported.release
    output = ctypes.c_void_p(123)
    try:
        monkeypatch.setenv(
            "IRX_ARROW_TEST_FAIL_OPERATION", f"{kind}_import_copy"
        )
        assert (
            getattr(descriptor_runtime, f"irx_arrow_{kind}_import_copy")(
                ctypes.byref(exported), ctypes.byref(output)
            )
            == OUT_OF_MEMORY
        )
        assert output.value is None and exported.release == callback
    finally:
        _release_c_schema(exported)


def test_conversion_classification_and_unresolved_lowering_fail_closed() -> (
    None
):
    """
    title: >-
      Conversion classification is semantic; missing sidecars fail in lowering.
    """
    conversion = astx.DescriptorCompatibility(
        astx.LogicalType(astx.LogicalKind.INT32),
        astx.LogicalType(astx.LogicalKind.INT64),
    )
    module = module_with(
        astx.AssertStmt(astx.BinaryOp("==", conversion, astx.LiteralInt32(1)))
    )
    text = Builder().translate(module)
    assert int(conversion.semantic.resolved_descriptor_conversion) == 1
    assert "irx_arrow_" not in text
    with pytest.raises(LoweringError, match="missing descriptor conversion"):
        Builder().translator.visit(
            astx.DescriptorCompatibility(astx.Schema(), astx.Schema())
        )
    with pytest.raises(SemanticError, match="matching descriptor kinds"):
        analyze(
            module_with(
                astx.DescriptorCompatibility(
                    astx.Schema(), astx.LogicalType(astx.LogicalKind.INT32)
                )
            )
        )


@pytest.mark.parametrize(
    "type_",
    [
        astx.ListType([astx.SchemaType()]),
        astx.TupleType([astx.FieldType()]),
        astx.GeneratorType(astx.TypeDescriptorType()),
        astx.PointerType(astx.FieldType()),
    ],
)
def test_descriptor_value_wrappers_fail_before_lowering(
    type_: astx.DataType,
) -> None:
    """
    title: Reject wrappers without implemented descriptor element lifetimes.
    parameters:
      type_:
        type: astx.DataType
    """
    module = module_with(astx.VariableDeclaration("unsupported", type_))
    with pytest.raises(
        SemanticError,
        match="descriptor values cannot be nested",
    ):
        analyze(module)


def test_inferred_descriptor_list_and_struct_fail_closed() -> None:
    """
    title: Unannotated containers and unmanaged structs cannot hide owners.
    """
    with pytest.raises(
        SemanticError, match="descriptor values cannot be nested"
    ):
        analyze(module_with(astx.ListCreate(astx.SchemaType())))
    module = module_with(astx.LiteralInt32(0))
    module.block.insert(
        0,
        astx.StructDefStmt(
            name="Unmanaged",
            attributes=[astx.VariableDeclaration("field", astx.FieldType())],
        ),
    )
    with pytest.raises(
        SemanticError, match="struct descriptor fields require"
    ):
        analyze(module)


def test_resolved_metadata_size_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Metadata lengths fail in analysis instead of overflowing lowering.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    monkeypatch.setattr("irx.analysis.schema_descriptors.INT32_MAX", 2)
    literal = astx.SchemaLiteral(astx.Schema(metadata=((b"key", b"value"),)))
    with pytest.raises(
        SemanticError, match="metadata exceeds C Data size limit"
    ):
        analyze(module_with(literal))
