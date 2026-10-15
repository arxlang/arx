"""
title: Logical schema validation, canonicalization and conversion tests.
"""

import subprocess
import sys

from dataclasses import replace

import astx
import pytest

from irx.analysis import SemanticError, analyze
from irx.analysis.schema import (
    MAX_SCHEMA_DEPTH,
    SchemaError,
    canonical_logical_type,
    canonical_schema,
)
from irx.analysis.schema_conversions import (
    SchemaConversion,
    logical_conversion,
    schema_conversion,
)
from irx.analysis.schema_types import resolve_logical_type
from irx.analysis.types import clone_type, same_type
from irx.builtins.collections.tensor import tensor_primitive_type_name

from ..schema_cases import logical_type_cases


@pytest.mark.parametrize(
    "type_", logical_type_cases(), ids=lambda value: value.kind.value
)
def test_every_logical_type_has_canonical_physical_descriptor(
    type_: astx.LogicalType,
) -> None:
    """
    title: All logical families resolve without consulting a backend object.
    parameters:
      type_:
        type: astx.LogicalType
    """
    resolved = resolve_logical_type(type_)
    assert resolved.c_format
    assert resolved.logical_type == canonical_logical_type(
        resolved.logical_type
    )
    assert resolved.required_features == ("core", "array")


def test_schema_identity_preserves_fields_and_normalizes_metadata() -> None:
    """
    title: >-
      Ordered fields and unordered binary metadata have distinct identity
      rules.
    """
    field = astx.SchemaField(
        "a",
        astx.LogicalType(astx.LogicalKind.INT32),
        metadata=((b"z", b"\x00"), (b"a", b"\xff")),
    )
    other = replace(field, name="b")
    schema = astx.Schema((field, other))
    canonical = canonical_schema(schema)
    assert canonical.fields[0].metadata == ((b"a", b"\xff"), (b"z", b"\x00"))
    assert canonical_schema(canonical) == canonical
    assert schema_conversion(schema, canonical) is SchemaConversion.EXACT
    assert (
        schema_conversion(schema, astx.Schema((other, field)))
        is SchemaConversion.INCOMPATIBLE
    )


@pytest.mark.parametrize(
    "metadata",
    [((b"a", b"x"), (b"a", b"y")), ((b"ARROW:extension:name", b"bad"),)],
)
def test_invalid_field_metadata_is_not_silently_discarded(
    metadata: tuple[tuple[bytes, bytes], ...],
) -> None:
    """
    title: Duplicate and conflicting metadata is rejected with a field path.
    parameters:
      metadata:
        type: tuple[tuple[bytes, bytes], Ellipsis]
    """
    field = astx.SchemaField(
        "child", astx.LogicalType(astx.LogicalKind.INT32), metadata=metadata
    )
    with pytest.raises(SchemaError) as error:
        canonical_schema(astx.Schema((field,)))
    assert error.value.path == ("child",)


def test_duplicate_names_and_excessive_nesting_are_rejected() -> None:
    """
    title: Nested schemas fail closed on ambiguity and recursive depth limits.
    """
    child = astx.LogicalType(astx.LogicalKind.INT32)
    field = astx.SchemaField("duplicate", child)
    with pytest.raises(SchemaError, match="duplicate field names"):
        canonical_schema(astx.Schema((field, field)))
    for _ in range(MAX_SCHEMA_DEPTH + 1):
        child = astx.LogicalType(
            astx.LogicalKind.LIST, fields=(astx.SchemaField("item", child),)
        )
    with pytest.raises(SchemaError, match="maximum nesting"):
        canonical_logical_type(child)


@pytest.mark.parametrize(
    ("kind", "parameter", "value"),
    [
        (astx.LogicalKind.DECIMAL32, astx.ParameterKind.PRECISION, 10),
        (astx.LogicalKind.DECIMAL64, astx.ParameterKind.PRECISION, 19),
        (astx.LogicalKind.DECIMAL128, astx.ParameterKind.PRECISION, 39),
        (astx.LogicalKind.DECIMAL256, astx.ParameterKind.PRECISION, 77),
        (astx.LogicalKind.DECIMAL128, astx.ParameterKind.SCALE, 2**31),
        (astx.LogicalKind.DECIMAL128, astx.ParameterKind.PRECISION, True),
        (
            astx.LogicalKind.TIME32,
            astx.ParameterKind.TIME_UNIT,
            astx.TimeUnit.NANOSECOND,
        ),
        (
            astx.LogicalKind.TIME64,
            astx.ParameterKind.TIME_UNIT,
            astx.TimeUnit.SECOND,
        ),
        (
            astx.LogicalKind.TIMESTAMP,
            astx.ParameterKind.TIMEZONE,
            "not/a/timezone",
        ),
        (astx.LogicalKind.FIXED_LIST, astx.ParameterKind.LIST_SIZE, -1),
        (astx.LogicalKind.FIXED_BINARY, astx.ParameterKind.BYTE_WIDTH, -1),
        (astx.LogicalKind.SPARSE_UNION, astx.ParameterKind.TYPE_CODES, (3, 3)),
        (
            astx.LogicalKind.DENSE_UNION,
            astx.ParameterKind.TYPE_CODES,
            (0, 128),
        ),
        (astx.LogicalKind.EXTENSION, astx.ParameterKind.EXTENSION_NAME, ""),
    ],
)
def test_invalid_parameter_domains(
    kind: astx.LogicalKind, parameter: astx.ParameterKind, value: object
) -> None:
    """
    title: Invalid parameter domains never reach Arrow assertions or LLVM.
    parameters:
      kind:
        type: astx.LogicalKind
      parameter:
        type: astx.ParameterKind
      value:
        type: object
    """
    original = next(item for item in logical_type_cases() if item.kind is kind)
    parameters = tuple(
        astx.LogicalParameter(item.kind, value)
        if item.kind is parameter
        else item
        for item in original.parameters
    )
    with pytest.raises(SchemaError):
        canonical_logical_type(replace(original, parameters=parameters))


@pytest.mark.parametrize(
    ("source", "target", "expected"),
    [
        (
            astx.LogicalKind.INT8,
            astx.LogicalKind.INT64,
            SchemaConversion.LOSSLESS,
        ),
        (
            astx.LogicalKind.INT64,
            astx.LogicalKind.INT8,
            SchemaConversion.EXPLICIT,
        ),
        (
            astx.LogicalKind.UINT32,
            astx.LogicalKind.INT64,
            SchemaConversion.LOSSLESS,
        ),
        (
            astx.LogicalKind.INT32,
            astx.LogicalKind.UINT64,
            SchemaConversion.EXPLICIT,
        ),
        (
            astx.LogicalKind.INT32,
            astx.LogicalKind.FLOAT32,
            SchemaConversion.EXPLICIT,
        ),
        (
            astx.LogicalKind.INT32,
            astx.LogicalKind.FLOAT64,
            SchemaConversion.LOSSLESS,
        ),
        (
            astx.LogicalKind.UINT64,
            astx.LogicalKind.FLOAT64,
            SchemaConversion.EXPLICIT,
        ),
        (
            astx.LogicalKind.STRING,
            astx.LogicalKind.LARGE_STRING,
            SchemaConversion.LOSSLESS,
        ),
        (
            astx.LogicalKind.STRING,
            astx.LogicalKind.INT32,
            SchemaConversion.INCOMPATIBLE,
        ),
    ],
)
def test_lossless_numeric_domains(
    source: astx.LogicalKind,
    target: astx.LogicalKind,
    expected: SchemaConversion,
) -> None:
    """
    title: Implicit compatibility requires whole-domain representability.
    parameters:
      source:
        type: astx.LogicalKind
      target:
        type: astx.LogicalKind
      expected:
        type: SchemaConversion
    """
    assert (
        logical_conversion(astx.LogicalType(source), astx.LogicalType(target))
        is expected
    )


def test_nullable_and_metadata_changes_require_explicit_checks() -> None:
    """
    title: Nullability may widen implicitly; removal and metadata loss may not.
    """
    field = astx.SchemaField("x", astx.LogicalType(astx.LogicalKind.INT32))
    source = astx.Schema((field,))
    nullable = astx.Schema((replace(field, nullable=True),))
    assert schema_conversion(source, nullable) is SchemaConversion.LOSSLESS
    assert schema_conversion(nullable, source) is SchemaConversion.EXPLICIT
    assert (
        schema_conversion(
            astx.Schema((field,), metadata=((b"x", b"y"),)), source
        )
        is SchemaConversion.EXPLICIT
    )


def test_current_builder_mapping_does_not_claim_future_support() -> None:
    """
    title: Descriptor support must not silently enable an absent builder.
    """
    assert tensor_primitive_type_name(astx.Int32()) == "int32"
    assert tensor_primitive_type_name(astx.Float16()) is None
    assert tensor_primitive_type_name(astx.String()) is None
    assert (
        resolve_logical_type(astx.LogicalType(astx.LogicalKind.BOOL)).bit_width
        == 1
    )


def test_modeled_container_types_have_structural_identity_and_fail_early() -> (
    None
):
    """
    title: Modeling a container must not silently claim native value lowering.
    """
    first = astx.ArrayType(astx.LogicalType(astx.LogicalKind.INT32))
    second = astx.ArrayType(astx.LogicalType(astx.LogicalKind.STRING))
    assert same_type(first, clone_type(first))
    assert not same_type(first, second)
    assert not same_type(astx.TableType(), astx.TableType(astx.Schema()))
    module = astx.Module()
    module.block.append(
        astx.FunctionPrototype(
            "future",
            astx.Arguments(astx.Argument("values", astx.StreamType())),
            return_type=astx.Int32(),
        )
    )
    with pytest.raises(
        SemanticError,
        match=r"native value construction|array owners|column requires",
    ):
        analyze(module)


@pytest.mark.parametrize(
    "kind",
    [
        astx.LogicalKind.MAP,
        astx.LogicalKind.RUN_END_ENCODED,
        astx.LogicalKind.DICTIONARY,
    ],
)
def test_synthetic_children_reject_metadata_that_arrow_would_drop(
    kind: astx.LogicalKind,
) -> None:
    """
    title: Synthetic Arrow type children must never silently lose metadata.
    parameters:
      kind:
        type: astx.LogicalKind
    """
    original = next(item for item in logical_type_cases() if item.kind is kind)
    child = replace(original.fields[0], metadata=((b"must", b"survive"),))
    with pytest.raises(SchemaError):
        canonical_logical_type(
            replace(original, fields=(child, *original.fields[1:]))
        )


def test_map_keys_dictionary_indices_and_run_ends_are_checked() -> None:
    """
    title: Invalid nested storage fails before a C++ constructor is invoked.
    """
    cases = {item.kind: item for item in logical_type_cases()}
    map_type = cases[astx.LogicalKind.MAP]
    entry = map_type.fields[0]
    key, value = entry.type_.fields
    bad_map = replace(
        map_type,
        fields=(
            replace(
                entry,
                type_=replace(
                    entry.type_,
                    fields=(replace(key, nullable=True), value),
                ),
            ),
        ),
    )
    dictionary = cases[astx.LogicalKind.DICTIONARY]
    bad_dictionary = replace(
        dictionary,
        fields=(
            replace(
                dictionary.fields[0],
                type_=astx.LogicalType(astx.LogicalKind.FLOAT64),
            ),
            dictionary.fields[1],
        ),
    )
    run_end = cases[astx.LogicalKind.RUN_END_ENCODED]
    bad_run_end = replace(
        run_end,
        fields=(
            replace(
                run_end.fields[0],
                type_=astx.LogicalType(astx.LogicalKind.UINT32),
            ),
            run_end.fields[1],
        ),
    )
    for invalid in (bad_map, bad_dictionary, bad_run_end):
        with pytest.raises(SchemaError):
            canonical_logical_type(invalid)


def test_parameter_presence_duplicates_and_irrelevance_are_checked() -> None:
    """
    title: Descriptors cannot omit required parameters or attach ignored ones.
    """
    precision = astx.LogicalParameter(astx.ParameterKind.PRECISION, 10)
    cases = (
        astx.LogicalType(astx.LogicalKind.DECIMAL128),
        astx.LogicalType(astx.LogicalKind.INT32, parameters=(precision,)),
        astx.LogicalType(
            astx.LogicalKind.DECIMAL128, parameters=(precision, precision)
        ),
    )
    for invalid in cases:
        with pytest.raises(SchemaError):
            canonical_logical_type(invalid)


def test_dictionary_temporal_and_decimal_changes_are_classified() -> None:
    """
    title: Re-encoding and temporal rescaling require explicit conversion.
    """
    cases = {item.kind: item for item in logical_type_cases()}
    dictionary = cases[astx.LogicalKind.DICTIONARY]
    widened = replace(
        dictionary,
        fields=(
            replace(
                dictionary.fields[0],
                type_=astx.LogicalType(astx.LogicalKind.UINT32),
            ),
            dictionary.fields[1],
        ),
    )
    assert logical_conversion(dictionary, widened) is SchemaConversion.EXPLICIT
    timestamp = cases[astx.LogicalKind.TIMESTAMP]
    rescaled = replace(
        timestamp,
        parameters=(
            astx.LogicalParameter(
                astx.ParameterKind.TIME_UNIT, astx.TimeUnit.MICROSECOND
            ),
            astx.LogicalParameter(astx.ParameterKind.TIMEZONE, "UTC"),
        ),
    )
    assert logical_conversion(timestamp, rescaled) is SchemaConversion.EXPLICIT
    decimal = cases[astx.LogicalKind.DECIMAL32]
    more_precision = replace(decimal, kind=astx.LogicalKind.DECIMAL128)
    assert (
        logical_conversion(decimal, more_precision)
        is SchemaConversion.LOSSLESS
    )


@pytest.mark.parametrize("wrapper", ["list", "tensor", "dataframe", "pointer"])
def test_modeled_only_types_are_rejected_inside_annotations(
    wrapper: str,
) -> None:
    """
    title: A compound annotation must not bypass the modeled-only type guard.
    parameters:
      wrapper:
        type: str
    """
    value = astx.ArrayType(astx.LogicalType(astx.LogicalKind.INT32))
    type_: astx.DataType
    if wrapper == "list":
        type_ = astx.ListType([value])
    elif wrapper == "tensor":
        type_ = astx.TensorType(value, shape=(1,))
    elif wrapper == "dataframe":
        type_ = astx.DataFrameType((astx.DataFrameColumn("values", value),))
    else:
        type_ = astx.PointerType(value)
    module = astx.Module()
    module.block.append(
        astx.FunctionPrototype(
            "future",
            astx.Arguments(astx.Argument("values", type_)),
            astx.Int32(),
        )
    )
    with pytest.raises(
        SemanticError,
        match=r"native value construction|array owners|column requires",
    ):
        analyze(module)


def test_null_field_conversion_and_reserved_schema_metadata() -> None:
    """
    title: >-
      Null-only fields may widen; reserved metadata cannot be misinterpreted.
    """
    source = astx.Schema(
        (
            astx.SchemaField(
                "x",
                astx.LogicalType(astx.LogicalKind.NULL),
                nullable=True,
            ),
        )
    )
    target = astx.Schema(
        (
            astx.SchemaField(
                "x",
                astx.LogicalType(astx.LogicalKind.INT32),
                nullable=True,
            ),
        )
    )
    assert schema_conversion(source, target) is SchemaConversion.LOSSLESS
    with pytest.raises(SchemaError, match="reserved extension keys"):
        canonical_schema(
            astx.Schema(metadata=((b"ARROW:extension:name", b"arrow.json"),))
        )


@pytest.mark.parametrize(
    "module_name",
    [
        "irx.builtins.collections.tensor",
        "irx.builtins.collections.dataframe",
        "irx.analysis.schema_types",
        "irx.schema_interop",
    ],
)
def test_schema_mapping_modules_support_independent_imports(
    module_name: str,
) -> None:
    """
    title: Shared scalar mappings must not create analyzer import cycles.
    parameters:
      module_name:
        type: str
    """
    completed = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
