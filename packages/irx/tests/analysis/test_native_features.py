"""
title: Host-supplied native capabilities and compilation isolation.
"""

from pathlib import Path
from typing import cast

import astx
import pyarrow as pa
import pytest

from irx.analysis import ParsedModule, SemanticError, analyze_modules
from irx.analysis.compute import ComputeOperation, ComputePlan
from irx.analysis.extensions.records import CALL_PLAN
from irx.analysis.resolved_nodes import SemanticInfo
from irx.builder import Builder
from irx.builder.runtime.registry import get_default_runtime_feature_registry
from irx.diagnostics import DiagnosticCodes
from irx.native import (
    ComputeKernel,
    NativeArtifact,
    NativeBinding,
    NativeFeature,
)
from llvmlite import binding as llvm
from typeguard import TypeCheckError

from ..conftest import StaticImportResolver


def unavailable(
    requesting: str,
    node: astx.ImportStmt | astx.ImportFromStmt,
    specifier: str,
) -> ParsedModule:
    """
    title: Reject unexpected graph expansion in single-module host fixtures.
    parameters:
      requesting: Requesting.
      node: Syntax node to process.
      specifier: Specifier.
    returns: 'Result of this operation: reject unexpected graph expansion
      in single-module host fixtures.'
    """
    raise LookupError(
        f"unexpected import {requesting}: {specifier}: {type(node)}"
    )


def compute_modules(
    kernel: ComputeKernel, type_: astx.DataType
) -> tuple[ParsedModule, StaticImportResolver, astx.FunctionCall]:
    """
    title: Reexport a trusted unary declaration without any frontend hooks.
    parameters:
      kernel: Kernel.
      type_: Type expression to process.
    returns: 'Result of this operation: reexport a trusted unary declaration
      without any frontend hooks.'
    """
    bound = astx.UnionType(
        [
            astx.Float64(),
            astx.NullableType(astx.Float64()),
            astx.SeriesType(astx.Float64()),
            astx.SeriesType(astx.Float64(), nullable=True),
        ]
    )
    variable = astx.TemplateTypeVar("T", bound=bound)
    prototype = astx.FunctionPrototype(
        "host_math", astx.Arguments(astx.Argument("value", variable)), variable
    )
    astx.set_template_params(prototype, (astx.TemplateParam("T", bound),))
    prototype.is_extern = True
    provider = astx.Module()
    provider.block.append(prototype)
    parsed = ParsedModule(
        "provider",
        provider,
        native_bindings=(
            NativeBinding(prototype, ("arrow_compute",), compute=kernel),
        ),
    )
    bridge = astx.Module()
    bridge.block.append(
        astx.ImportFromStmt(
            names=[astx.AliasExpr("host_math", "exported")],
            module="provider",
        )
    )
    call = astx.FunctionCall("local_math", [astx.Identifier("input")])
    body = astx.Block()
    body.append(call)
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    root = astx.Module()
    root.block.append(
        astx.ImportFromStmt(
            names=[astx.AliasExpr("exported", "local_math")],
            module="bridge",
        )
    )
    root.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype(
                "consumer",
                astx.Arguments(astx.Argument("input", type_)),
                astx.Int32(),
            ),
            body,
        )
    )
    return (
        ParsedModule("root", root),
        StaticImportResolver(
            {
                "provider": parsed,
                "bridge": ParsedModule("bridge", bridge),
            }
        ),
        call,
    )


@pytest.mark.parametrize("kernel", ["sqrt", "exp"])
@pytest.mark.parametrize(
    "type_",
    [
        astx.Float64(),
        astx.NullableType(astx.Float64()),
        astx.SeriesType(astx.Float64(), size=0),
        astx.SeriesType(astx.Float64(), nullable=True, size=3),
    ],
)
def test_compute_plan_identity_and_reanalysis(
    kernel: ComputeKernel, type_: astx.DataType
) -> None:
    """
    title: Imported aliases retain typed shape/ownership without AST mutation.
    parameters:
      kernel: Kernel.
      type_: Type expression to process.
    """
    root, resolver, call = compute_modules(kernel, type_)
    astx.set_template_args(call, (type_,))
    for _ in range(2):
        session = analyze_modules(root, resolver)
        info = cast(SemanticInfo, call.semantic)
        plan = info.facts.get(CALL_PLAN)
        assert isinstance(plan, ComputePlan)
        assert plan.operation.kernel == kernel
        assert plan.operation.arrow_version == "26.0.1"
        assert plan.operation.operation_id == (1 if kernel == "sqrt" else 2)
        assert plan.function.module_key == "provider"
        assert plan.function.signature.required_runtime_features == (
            "arrow_compute",
        )
        assert plan.argument is call.args[0]
        assert plan.shape == (
            "series"
            if isinstance(type_, astx.SeriesType)
            else "nullable_scalar"
            if isinstance(type_, astx.NullableType)
            else "scalar"
        )
        assert (plan.ownership is not None) == isinstance(
            type_, astx.SeriesType
        )
        if isinstance(plan.result_type, astx.SeriesType):
            assert isinstance(type_, astx.SeriesType)
            assert plan.result_type.size == type_.size
            assert plan.result_type.nullable == type_.nullable
        assert tuple(session.native_compute.values()) == (kernel,)
    builder = Builder()
    text = builder.translate_modules(root, resolver)
    llvm.parse_assembly(text).verify()
    assert 'call i32 @"irx_arrow_compute"' in text
    assert 'call i32 @"irx_arrow_compute_abi_version"' in text
    features = builder.translator.runtime_features.active_feature_names()
    assert "arrow_compute" in features
    assert "libm" not in features
    if not isinstance(type_, astx.SeriesType):
        assert "dataframe" not in features
    call.keywords = [astx.KeywordArgument("options", astx.LiteralInt32(1))]
    with pytest.raises(SemanticError, match="unknown argument 'options'"):
        analyze_modules(root, resolver)
    assert cast(SemanticInfo, call.semantic).facts.get(CALL_PLAN) is None


@pytest.mark.parametrize(
    "type_",
    [
        astx.Float32(),
        astx.Int64(),
        astx.TensorType(astx.Float64(), shape=(2,)),
    ],
)
def test_compute_rejects_unsupported_shape(type_: astx.DataType) -> None:
    """
    title: Existing storage support never implies a math capability or cast.
    parameters:
      type_: Type expression to process.
    """
    root, resolver, call = compute_modules("sqrt", type_)
    with pytest.raises(SemanticError, match="supported f64 scalar/Series"):
        analyze_modules(root, resolver)
    assert cast(SemanticInfo, call.semantic).facts.get(CALL_PLAN) is None


def test_compute_capability_validation() -> None:
    """
    title: Reject arbitrary kernels, malformed bindings and runtime values.
    """
    prototype = astx.FunctionPrototype(
        "sqrt",
        astx.Arguments(astx.Argument("value", astx.Float32())),
        astx.Float32(),
    )
    prototype.is_extern = True
    with pytest.raises(TypeCheckError):
        ComputeOperation("unknown")  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        NativeBinding(
            prototype,
            ("arrow_compute",),
            compute="unknown",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="only the arrow_compute feature"):
        NativeBinding(prototype, ("libc",), compute="sqrt")
    module = astx.Module()
    module.block.append(prototype)
    with pytest.raises(ValueError, match="only f64 shapes"):
        ParsedModule(
            "bad",
            module,
            native_bindings=(
                NativeBinding(prototype, ("arrow_compute",), compute="sqrt"),
            ),
        )


def test_compute_shadowing_and_ffi_are_independent() -> None:
    """
    title: Local names and ordinary C sqrt never acquire a compute capability.
    """
    root, resolver, call = compute_modules("sqrt", astx.Float64())
    consumer = root.ast.nodes[1]
    assert isinstance(consumer, astx.FunctionDef)
    consumer.body.nodes.insert(
        0,
        astx.VariableDeclaration(
            "local_math", astx.Int32(), value=astx.LiteralInt32(1)
        ),
    )
    with pytest.raises(SemanticError, match="does not resolve to a function"):
        analyze_modules(root, resolver)
    consumer.body.nodes.pop(0)
    external = astx.FunctionPrototype(
        "sqrt",
        astx.Arguments(astx.Argument("value", astx.Float64())),
        astx.Float64(),
    )
    external.is_extern = True
    root.ast.block.insert(0, external)
    call.fn = "sqrt"
    analyze_modules(root, resolver)
    info = cast(SemanticInfo, call.semantic)
    assert info.facts.get(CALL_PLAN) is None
    assert info.resolved_function is not None
    assert info.resolved_function.signature.operation is None


def test_compute_monomorphic_nullable_conversion() -> None:
    """
    title: A nullable declaration preserves its result contract for f64 inputs.
    """
    root, resolver, call = compute_modules("sqrt", astx.Float64())
    provider = resolver("root", astx.ImportStmt([]), "provider")
    prototype = provider.native_bindings[0].declaration
    optional = astx.NullableType(astx.Float64())
    prototype.args.nodes[0].type_ = optional
    prototype.return_type = optional
    astx.set_template_params(prototype, ())
    analyze_modules(root, resolver)
    plan = cast(SemanticInfo, call.semantic).facts.get(CALL_PLAN)
    assert isinstance(plan, ComputePlan)
    assert plan.shape == "nullable_scalar"
    assert isinstance(plan.result_type, astx.NullableType)
    assert isinstance(plan.conversion.source_type, astx.Float64)
    assert isinstance(plan.conversion.target_type, astx.NullableType)


@pytest.mark.parametrize("attribute", ["__version__", "cpp_version"])
def test_compute_rejects_unqualified_runtime(
    attribute: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    title: Reject either runtime version mismatch before publishing a plan.
    parameters:
      attribute: Attribute.
      monkeypatch: Fixture for temporarily replacing dependencies and settings.
    """
    root, resolver, call = compute_modules("sqrt", astx.Float64())
    monkeypatch.setattr(pa, attribute, "26.0.0")
    with pytest.raises(
        SemanticError, match=r"matching Arrow 26\.0\.1"
    ) as captured:
        analyze_modules(root, resolver)
    assert captured.value.diagnostics.diagnostics[0].code == (
        DiagnosticCodes.RUNTIME_FEATURE_UNAVAILABLE
    )
    assert cast(SemanticInfo, call.semantic).facts.get(CALL_PLAN) is None


def native_module(name: str = "package:test:backend") -> ParsedModule:
    """
    title: Supply native metadata independently of Arx syntax or discovery.
    parameters:
      name: Name identifying the declaration or operation.
    returns: 'Result of this operation: supply native metadata independently
      of Arx syntax or discovery.'
    """
    prototype = astx.FunctionPrototype(
        "native_value", astx.Arguments(), astx.Int32()
    )
    prototype.is_extern = True
    module = astx.Module()
    module.name = "main"
    module.block.append(prototype)
    body = astx.Block()
    body.append(astx.FunctionReturn(astx.FunctionCall("native_value", [])))
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
            body,
        )
    )
    return ParsedModule(
        "main",
        module,
        native_features=(NativeFeature(name),),
        native_bindings=(NativeBinding(prototype, (name,)),),
    )


def test_native_capabilities_reach_lowering_without_global_mutation() -> None:
    """
    title: Semantic identities activate only the current compilation registry.
    """
    root = native_module()
    session = analyze_modules(root, unavailable)
    assert tuple(session.native_features) == ("package:test:backend",)
    builder = Builder()
    text = builder.translate_modules(root, unavailable)
    llvm.parse_assembly(text).verify()
    assert builder.translator.runtime_features.is_active(
        "package:test:backend"
    )
    assert (
        "package:test:backend"
        not in get_default_runtime_feature_registry().names()
    )
    builder.translate_modules(
        native_module("package:other:backend"), unavailable
    )
    assert not builder.translator.runtime_features.is_active(
        "package:test:backend"
    )


def test_native_binding_does_not_mutate_prototype() -> None:
    """
    title: Reanalysis binds host metadata without rewriting source prototypes.
    """
    root = native_module()
    for _ in range(2):
        analyze_modules(root, unavailable)
    assert not hasattr(root.native_bindings[0].declaration, "runtime_features")


def test_native_features_cannot_replace_builtins() -> None:
    """
    title: External capabilities cannot override builtin native definitions.
    """
    with pytest.raises(SemanticError, match="conflicts with a builtin"):
        analyze_modules(native_module("libc"), unavailable)


def test_native_bindings_require_available_features() -> None:
    """
    title: Unknown features fail semantically before lowering.
    """
    original = native_module()
    root = ParsedModule(
        "main", original.ast, native_bindings=original.native_bindings
    )
    with pytest.raises(SemanticError, match="unknown runtime feature"):
        analyze_modules(root, unavailable)


def test_native_registration_requires_declaration_identity() -> None:
    """
    title: Matching textual names do not authorize another AST declaration.
    """
    root = native_module()
    with pytest.raises(ValueError, match="belong"):
        ParsedModule(
            "other", astx.Module(), native_bindings=root.native_bindings
        )
    root.native_bindings[0].declaration.is_extern = False
    with pytest.raises(ValueError, match="extern"):
        ParsedModule("main", root.ast, native_bindings=root.native_bindings)


def test_native_records_validate_nonfirst_collection_items() -> None:
    """
    title: Runtime checks reject invalid capabilities and collection items.
    """
    with pytest.raises(TypeCheckError):
        NativeFeature("test", (NativeArtifact("c_source", Path("a.c")), 3))  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        NativeArtifact("c_source", Path("a.c"), (Path("include"), "bad"))  # type: ignore[arg-type]
    root = native_module()
    with pytest.raises(TypeCheckError):
        NativeBinding(root.native_bindings[0].declaration, ("test", 2))  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        ParsedModule(
            "main", root.ast, native_features=(NativeFeature("test"), 2)
        )  # type: ignore[arg-type]


def test_native_binding_rejects_duplicate_declarations() -> None:
    """
    title: Native registrations cannot contain contradictory duplicate entries.
    """
    root = native_module()
    with pytest.raises(ValueError, match="duplicate native extern"):
        ParsedModule(
            "main",
            root.ast,
            native_bindings=(*root.native_bindings, *root.native_bindings),
        )


def test_native_conflicts_across_modules_fail_semantically() -> None:
    """
    title: Extern C symbol requirements cannot conflict across module
      boundaries.
    """
    root = native_module()
    other = native_module("package:other:backend")
    other = ParsedModule(
        "other",
        other.ast,
        native_features=other.native_features,
        native_bindings=other.native_bindings,
    )
    root.ast.block.append(astx.ImportStmt([astx.AliasExpr("other")]))

    def resolver(
        requesting: str,
        node: astx.ImportStmt | astx.ImportFromStmt,
        specifier: str,
    ) -> ParsedModule:
        """
        title: Return a second module with a contradictory extern contract.
        parameters:
          requesting: Requesting.
          node: Syntax node to process.
          specifier: Specifier.
        returns: A second module with a contradictory extern contract.
        """
        if specifier == "other":
            return other
        return unavailable(requesting, node, specifier)

    with pytest.raises(SemanticError, match="Extern symbol"):
        analyze_modules(root, resolver)


def test_extern_rejects_known_nul_literal() -> None:
    """
    title: Native C strings cannot silently truncate known embedded NUL text.
    """
    prototype = astx.FunctionPrototype(
        "consume",
        astx.Arguments(astx.Argument("label", astx.String())),
        astx.Int32(),
    )
    prototype.is_extern = True
    module = astx.Module()
    module.block.append(prototype)
    body = astx.Block()
    body.append(
        astx.FunctionReturn(
            astx.FunctionCall("consume", [astx.LiteralString("bad\x00suffix")])
        )
    )
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
            body,
        )
    )
    with pytest.raises(SemanticError, match="cannot contain NUL"):
        analyze_modules(ParsedModule("main", module), unavailable)


def test_native_artifact_options_cannot_conflict() -> None:
    """
    title: Duplicate source paths cannot silently discard distinct build
      inputs.
    """
    root = native_module()
    feature = NativeFeature(
        "package:test:backend",
        (
            NativeArtifact("c_source", Path("input.c")),
            NativeArtifact("c_source", Path("input.c"), (Path("headers"),)),
        ),
    )
    root = ParsedModule(
        "main",
        root.ast,
        native_features=(feature,),
        native_bindings=root.native_bindings,
    )
    with pytest.raises(SemanticError, match="conflicting native artifact"):
        analyze_modules(root, unavailable)


def test_native_record_names_and_duplicates_are_rejected() -> None:
    """
    title: Empty names and duplicate capabilities are invalid host inputs.
    """
    root = native_module()
    with pytest.raises(ValueError):
        NativeFeature(" ")
    with pytest.raises(ValueError):
        NativeBinding(root.native_bindings[0].declaration, ("x", "x"))
    with pytest.raises(ValueError):
        ParsedModule(
            "main",
            root.ast,
            native_features=(*root.native_features, *root.native_features),
        )


@pytest.mark.parametrize("invalid", ["arity", "path_type", "result"])
def test_table_io_host_capability_validates_shape(invalid: str) -> None:
    """
    title: An explicit host cannot accidentally bypass FFI with an invalid ABI.
    parameters:
      invalid: Invalid.
    """
    args = astx.Arguments(astx.Argument("path", astx.String()))
    if invalid == "arity":
        args = astx.Arguments()
    if invalid == "path_type":
        args = astx.Arguments(astx.Argument("path", astx.Int32()))
    prototype = astx.FunctionPrototype(
        "custom_reader",
        args,
        astx.Int32() if invalid == "result" else astx.DataFrameType(),
    )
    prototype.is_extern = True
    module = astx.Module()
    module.block.append(prototype)
    with pytest.raises(ValueError, match="table I/O capability"):
        ParsedModule(
            "invalid",
            module,
            native_bindings=(
                NativeBinding(
                    prototype, ("record_batch",), table_io="read_csv"
                ),
            ),
        )
