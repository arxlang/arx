"""
title: Frontend-independent trusted table calls and checked cast lowering.
"""

from typing import Literal, cast
from unittest.mock import patch

import astx
import pytest

from irx.analysis import ParsedModule, SemanticError, analyze_modules
from irx.analysis.extensions.calls import default_analysis_configuration
from irx.analysis.extensions.records import CALL_PLAN
from irx.analysis.facts import SemanticFacts
from irx.analysis.resolved_nodes import OwnershipKind, SemanticInfo
from irx.analysis.table_io import TableIOCall
from irx.builder import Builder
from irx.builder.extensions.calls import (
    LoweringCall,
    default_lowering_configuration,
)
from irx.builder.lowering.table_io import emit_table_io
from irx.diagnostics import LoweringError
from irx.extensions import ConfigurationError, HandlerConfiguration, contribute
from irx.native import NativeBinding, TableIOOperation
from irx.typecheck import typechecked
from llvmlite import binding as llvm

from ..conftest import StaticImportResolver


def io_module(
    format_: Literal["csv", "parquet"],
    keywords: tuple[astx.KeywordArgument, ...] = (),
    positional: tuple[astx.DataType, ...] | None = None,
    *,
    configured: bool = False,
) -> tuple[ParsedModule, astx.FunctionCall]:
    """
    title: Supply actual native declarations without importing an Arx frontend.
    parameters:
      format_:
        type: Literal[csv, parquet]
      keywords:
        type: tuple[astx.KeywordArgument, Ellipsis]
      positional:
        type: tuple[astx.DataType, Ellipsis] | None
      configured:
        type: bool
    returns:
      type: tuple[ParsedModule, astx.FunctionCall]
    """
    frame = astx.DataFrameType()
    reader = astx.FunctionPrototype(
        "host_read",
        astx.Arguments(astx.Argument("path", astx.String())),
        frame,
    )
    writer = astx.FunctionPrototype(
        "host_write",
        astx.Arguments(
            astx.Argument("frame", frame), astx.Argument("path", astx.String())
        ),
        astx.NoneType(),
    )
    setattr(reader, "is_extern", True)
    setattr(writer, "is_extern", True)
    read = astx.FunctionCall(
        "host_read",
        (astx.LiteralString("input"),) if positional is None else positional,
        keywords=keywords,
    )
    body = astx.Block()
    body.append(astx.VariableDeclaration("loaded", frame, value=read))
    target = astx.DataFrameType([astx.DataFrameColumn("id", astx.Int64())])
    body.append(
        astx.VariableDeclaration(
            "checked",
            target,
            value=astx.Cast(astx.Identifier("loaded"), target),
        )
    )
    settings: tuple[astx.KeywordArgument, ...] = (
        (
            (
                astx.KeywordArgument("delimiter", astx.LiteralString(";")),
                astx.KeywordArgument("header", astx.LiteralBoolean(False)),
            )
            if format_ == "csv"
            else (
                astx.KeywordArgument(
                    "compression", astx.LiteralString("zstd")
                ),
                astx.KeywordArgument("atomic", astx.LiteralBoolean(True)),
                astx.KeywordArgument("row_group_size", astx.LiteralInt32(2)),
                astx.KeywordArgument(
                    "partition_columns",
                    astx.LiteralList([astx.LiteralString("group")]),
                ),
            )
        )
        if configured
        else ()
    )
    body.append(
        astx.FunctionCall(
            "host_write",
            [],
            keywords=(
                astx.KeywordArgument("path", astx.LiteralString("output")),
                astx.KeywordArgument("frame", astx.Identifier("checked")),
                *settings,
            ),
        )
    )
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module = astx.Module()
    module.block.extend(
        [
            reader,
            writer,
            astx.FunctionDef(
                astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
                body,
            ),
        ]
    )
    feature = "record_batch" if format_ == "csv" else "parquet"
    return ParsedModule(
        "host",
        module,
        native_bindings=(
            NativeBinding(
                reader,
                (feature,),
                table_io=cast(TableIOOperation, "read_" + format_),
            ),
            NativeBinding(
                writer,
                (feature,),
                table_io=cast(TableIOOperation, "write_" + format_),
            ),
        ),
    ), read


@pytest.mark.parametrize("format_", ["csv", "parquet"])
@pytest.mark.parametrize("configured", [False, True])
def test_host_table_io_translate(
    format_: Literal["csv", "parquet"],
    configured: bool,
) -> None:
    """
    title: >-
      Explicit capabilities resolve arguments and lower verified native IR.
    parameters:
      format_:
        type: Literal[csv, parquet]
      configured:
        type: bool
    """
    settings: tuple[astx.KeywordArgument, ...] = (
        (
            astx.KeywordArgument(
                "columns", astx.LiteralList([astx.LiteralString("id")])
            ),
            astx.KeywordArgument(
                "block_size" if format_ == "csv" else "batch_size",
                astx.LiteralInt32(32),
            ),
        )
        if configured
        else ()
    )
    if configured and format_ == "csv":
        settings += (
            astx.KeywordArgument("null_values", astx.LiteralList([])),
        )
    if configured and format_ == "parquet":
        settings += (
            astx.KeywordArgument(
                "row_groups",
                astx.LiteralList([astx.LiteralInt32(0), astx.LiteralInt32(1)]),
            ),
        )
    root, read = io_module(format_, settings, configured=configured)
    builder = Builder()
    text = builder.translate_modules(root, StaticImportResolver({}))
    llvm.parse_assembly(text).verify()
    plan = cast(SemanticInfo, getattr(read, "semantic")).facts.require(
        CALL_PLAN
    )
    assert isinstance(plan, TableIOCall)
    assert plan.operation == "read_" + format_
    assert plan.arguments[0].name == "path"
    assert "irx_rb_api_table_cast" in text
    assert "irx_rb_api_read_" + format_ in text
    assert "irx_rb_api_write_" + format_ in text
    assert "host_read" not in text
    if format_ == "csv":
        assert "parquet" not in (
            builder.translator.runtime_features.active_feature_names()
        )


@pytest.mark.parametrize(
    "name,value",
    [
        ("unknown", astx.LiteralBoolean(True)),
        ("path", astx.LiteralString("duplicate")),
        ("columns", astx.LiteralString("id")),
        ("columns", astx.LiteralList([])),
        ("columns", astx.LiteralList([astx.LiteralInt32(1)])),
        (
            "columns",
            astx.LiteralList(
                [astx.LiteralString("id"), astx.LiteralString("id")]
            ),
        ),
        ("columns", astx.LiteralList([astx.LiteralString("bad\0")])),
        ("header", astx.LiteralInt32(1)),
        ("block_size", astx.LiteralBoolean(True)),
        ("delimiter", astx.LiteralString("bad\0")),
        ("schema", astx.LiteralInt32(1)),
    ],
)
def test_host_table_io_rejects_invalid_arguments(
    name: str,
    value: astx.DataType,
) -> None:
    """
    title: Semantic errors precede native calls and generic FFI classification.
    parameters:
      name:
        type: str
      value:
        type: astx.DataType
    """
    root, _ = io_module("csv", (astx.KeywordArgument(name, value),))
    with pytest.raises(SemanticError):
        analyze_modules(root, StaticImportResolver({}))


@pytest.mark.parametrize("arguments", [(), (astx.LiteralInt32(1),)])
def test_host_table_io_requires_path(
    arguments: tuple[astx.DataType, ...],
) -> None:
    """
    title: Missing and incorrectly typed required arguments fail in analysis.
    parameters:
      arguments:
        type: tuple[astx.DataType, Ellipsis]
    """
    root, _ = io_module("csv", positional=arguments)
    with pytest.raises(SemanticError):
        analyze_modules(root, StaticImportResolver({}))


def test_table_io_reanalysis_replaces_operands_after_failure() -> None:
    """
    title: Failed reanalysis drops the old plan and retry preserves omission.
    """
    columns = astx.LiteralList([astx.LiteralString("id")])
    root, read = io_module("csv", (astx.KeywordArgument("columns", columns),))
    resolver = StaticImportResolver({})
    first_session = analyze_modules(root, resolver)
    info = cast(SemanticInfo, getattr(read, "semantic"))
    first_function = info.resolved_function
    first_plan = info.facts.require(CALL_PLAN)
    assert isinstance(first_plan, TableIOCall)
    assert first_plan.arguments[1].expression is columns
    assert first_plan.arguments[1].literals == ("id",)

    read.keywords = (
        astx.KeywordArgument("block_size", astx.LiteralString("invalid")),
    )
    with pytest.raises(SemanticError, match="block_size"):
        analyze_modules(root, resolver)
    assert (
        cast(SemanticInfo, getattr(read, "semantic")).facts.get(CALL_PLAN)
        is None
    )
    assert info.resource_ownership is None
    assert info.resolved_class is None

    read.keywords = ()
    second_session = analyze_modules(root, resolver)
    info = cast(SemanticInfo, getattr(read, "semantic"))
    plan = info.facts.require(CALL_PLAN)
    assert isinstance(plan, TableIOCall)
    assert plan is not first_plan
    assert [argument.name for argument in plan.arguments] == ["path"]
    assert plan.arguments[0].expression is next(iter(read.args))
    assert info.resolved_function is not first_function
    assert second_session is not first_session
    assert info.resource_ownership is not None
    assert info.resource_ownership.kind is OwnershipKind.OWNED


def test_reused_builder_does_not_retain_table_runtime_features() -> None:
    """
    title: A Parquet compilation cannot activate Parquet in a later CSV module.
    """
    builder = Builder()
    resolver = StaticImportResolver({})
    parquet, _ = io_module("parquet")
    csv, _ = io_module("csv")
    for root, uses_parquet in ((parquet, True), (csv, False), (parquet, True)):
        text = builder.translate_modules(root, resolver)
        llvm.parse_assembly(text).verify()
        features = builder.translator.runtime_features.active_feature_names()
        assert "record_batch" in features
        assert ("parquet" in features) is uses_parquet
        assert ("irx_rb_api_read_parquet" in text) is uses_parquet
        assert ("irx_rb_api_read_csv" in text) is not uses_parquet


def test_second_table_operation_composes_without_driver_changes() -> None:
    """
    title: Adding the real write provider completes a read-only configuration.
    """
    complete = default_analysis_configuration()
    read_only = HandlerConfiguration(
        "analysis",
        tuple(
            item
            for item in complete.contributions
            if item.identity != "table.write"
        ),
    )
    root, read = io_module("csv")
    resolver = StaticImportResolver({})
    with pytest.raises(ConfigurationError, match="WriteTableOperation"):
        analyze_modules(root, resolver, configuration=read_only)
    writer = next(
        item
        for item in complete.contributions
        if item.identity == "table.write"
    )
    extended = read_only.derive(writer)
    text = Builder(analysis_configuration=extended).translate_modules(
        root, resolver
    )
    llvm.parse_assembly(text).verify()
    plan = cast(SemanticInfo, getattr(read, "semantic")).facts.require(
        CALL_PLAN
    )
    assert isinstance(plan, TableIOCall) and plan.operation == "read_csv"
    assert "irx_rb_api_write_csv" in text
    assert all(
        item.identity != "table.write" for item in read_only.contributions
    )


@typechecked
def alternate_emission(plan: TableIOCall, call: LoweringCall) -> None:
    """
    title: >-
      A stateless replacement uses only the public narrow service contract.
    parameters:
      plan:
        type: TableIOCall
      call:
        type: LoweringCall
    """
    call.services.text("alternate-provider")
    emit_table_io(plan, call)


def test_lowering_replacement_is_local_to_selected_builder() -> None:
    """
    title: Two live compilers select different implementations without leakage.
    """
    parent = default_lowering_configuration()
    original = Builder(lowering_configuration=parent)
    child = parent.derive(
        contribute(
            "alternate",
            "test",
            "lowering",
            TableIOCall,
            LoweringCall,
            alternate_emission,
            replaces="table.emit",
        )
    )
    selected = Builder(lowering_configuration=child)
    for builder, marker in (
        (selected, True),
        (original, False),
        (selected, True),
    ):
        root, _ = io_module("csv")
        text = builder.translate_modules(root, StaticImportResolver({}))
        llvm.parse_assembly(text).verify()
        assert ("alternate-provider" in text) is marker


def test_lowering_requires_registered_operation_plan() -> None:
    """
    title: >-
      Missing typed facts fail before falling back to ordinary FFI lowering.
    """
    root, read = io_module("csv")
    resolver = StaticImportResolver({})
    session = analyze_modules(root, resolver)
    cast(SemanticInfo, getattr(read, "semantic")).facts = SemanticFacts()
    with patch("irx.builder.core.analyze_modules", return_value=session):
        with pytest.raises(LoweringError, match="missing semantic fact"):
            Builder().translate_modules(root, resolver)


def test_reanalysis_does_not_retain_privilege_by_call_spelling() -> None:
    """
    title: >-
      Reused calls lose table facts when a new host resolves a user function.
    """
    root, read = io_module("csv")
    resolver = StaticImportResolver({})
    analyze_modules(root, resolver)
    body = astx.Block()
    body.append(astx.FunctionReturn(astx.LiteralInt32(7)))
    main = astx.Block()
    main.append(astx.FunctionReturn(read))
    ordinary = astx.Module()
    ordinary.block.extend(
        [
            astx.FunctionDef(
                astx.FunctionPrototype(
                    "host_read",
                    astx.Arguments(astx.Argument("path", astx.String())),
                    astx.Int32(),
                ),
                body,
            ),
            astx.FunctionDef(
                astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
                main,
            ),
        ]
    )
    builder = Builder()
    text = builder.translate_modules(
        ParsedModule("ordinary", ordinary), resolver
    )
    llvm.parse_assembly(text).verify()
    info = cast(SemanticInfo, getattr(read, "semantic"))
    assert info.facts.get(CALL_PLAN) is None
    assert info.resource_ownership is None
    assert "irx_rb_api_read_csv" not in text
    assert (
        "record_batch"
        not in builder.translator.runtime_features.active_feature_names()
    )


@pytest.mark.parametrize("static_overload", [False, True])
def test_streaming_style_overload_accepts_static_frames(
    static_overload: bool,
) -> None:
    """
    title: Runtime-schema parameters erase safely and exact overloads win.
    parameters:
      static_overload:
        type: bool
    """
    schema = astx.DataFrameType([astx.DataFrameColumn("id", astx.Int64())])
    types: list[astx.DataType] = [astx.DataFrameType(), astx.Int32()]
    if static_overload:
        types.append(schema)
    methods: list[astx.FunctionDef] = []
    for type_ in types:
        body = astx.Block()
        body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
        methods.append(
            astx.FunctionDef(
                astx.FunctionPrototype(
                    "write",
                    astx.Arguments(astx.Argument("frame", type_)),
                    astx.Int32(),
                ),
                body,
            )
        )
    call = astx.MethodCall(
        astx.ClassConstruct("Sink"), "write", [astx.Identifier("frame")]
    )
    body = astx.Block()
    body.append(astx.FunctionReturn(call))
    module = astx.Module()
    module.block.extend(
        [
            astx.ClassDefStmt("Sink", methods=methods),
            astx.FunctionDef(
                astx.FunctionPrototype(
                    "send",
                    astx.Arguments(astx.Argument("frame", schema)),
                    astx.Int32(),
                ),
                body,
            ),
        ]
    )
    text = Builder().translate_modules(
        ParsedModule("overloads", module), StaticImportResolver({})
    )
    llvm.parse_assembly(text).verify()
    resolved = cast(
        SemanticInfo, getattr(call, "semantic")
    ).resolved_method_call
    assert resolved is not None
    target = resolved.function.signature.parameters[-1].type_
    assert isinstance(target, astx.DataFrameType)
    assert (target.columns is not None) is static_overload
