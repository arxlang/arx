"""
title: Tests for the runtime feature registry and activation state.
"""

from __future__ import annotations

import subprocess

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

import astx
import pytest

from irx.builder import Builder, Visitor
from irx.builder.runtime.arrow_compute import COMPUTE_SIGNATURES
from irx.builder.runtime.errors.feature import build_runtime_failure_feature
from irx.builder.runtime.features import (
    ExternalSymbolSpec,
    NativeArtifact,
    RuntimeFeature,
    declare_external_function,
)
from irx.builder.runtime.linking import (
    compile_native_artifacts,
    link_executable,
)
from irx.builder.runtime.list.feature import build_list_runtime_feature
from irx.builder.runtime.registry import (
    RuntimeFeatureRegistry,
    RuntimeFeatureState,
    get_default_runtime_feature_registry,
)
from irx.diagnostics import (
    LinkingError,
    NativeCompileError,
    RuntimeFeatureError,
)
from irx.native import BUILTIN_RUNTIME_FEATURES, NativeFeature
from irx.system import PrintExpr
from llvmlite import binding as llvm
from llvmlite import ir

if TYPE_CHECKING:
    from irx.builder.protocols import VisitorProtocol


def _declare_dummy_symbol(visitor: "VisitorProtocol") -> ir.Function:
    """
    title: Declare dummy symbol.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    fn_type = ir.FunctionType(visitor._llvm.INT32_TYPE, [])
    return declare_external_function(visitor._llvm.module, "dummy_rt", fn_type)


def _main_return_zero_module() -> astx.Module:
    """
    title: Main return zero module.
    returns:
      type: astx.Module
    """
    module = astx.Module()
    main_proto = astx.FunctionPrototype(
        "main", args=astx.Arguments(), return_type=astx.Int32()
    )
    body = astx.Block()
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module.block.append(astx.FunctionDef(prototype=main_proto, body=body))
    return module


def _extern_prototype(
    name: str,
    *args: astx.Argument,
    return_type: astx.DataType,
    runtime_feature: str | None = None,
) -> astx.FunctionPrototype:
    """
    title: Build one explicit extern prototype.
    parameters:
      name:
        type: str
      return_type:
        type: astx.DataType
      runtime_feature:
        type: str | None
      args:
        type: astx.Argument
        variadic: positional
    returns:
      type: astx.FunctionPrototype
    """
    prototype = astx.FunctionPrototype(
        name,
        args=astx.Arguments(*args),
        return_type=return_type,
    )
    prototype.is_extern = True
    prototype.calling_convention = "c"
    prototype.symbol_name = name
    if runtime_feature is not None:
        prototype.runtime_feature = runtime_feature
    return prototype


def test_runtime_feature_registry_rejects_duplicate_names() -> None:
    """
    title: Runtime feature registry should reject duplicate feature names.
    """
    registry = RuntimeFeatureRegistry()
    feature = RuntimeFeature(name="dummy")

    registry.register(feature)

    with pytest.raises(ValueError, match="already exists"):
        registry.register(feature)


def test_runtime_feature_state_reuses_symbol_declarations() -> None:
    """
    title: >-
      Runtime feature state should reuse one external declaration per module.
    """
    registry = RuntimeFeatureRegistry()
    registry.register(
        RuntimeFeature(
            name="dummy",
            symbols={
                "dummy_rt": ExternalSymbolSpec(
                    "dummy_rt",
                    _declare_dummy_symbol,
                )
            },
        )
    )
    visitor = Visitor()
    state = RuntimeFeatureState(visitor, registry)

    fn_first = state.require_symbol("dummy", "dummy_rt")
    fn_second = state.require_symbol("dummy", "dummy_rt")

    assert fn_first is fn_second
    assert state.active_feature_names() == ("dummy",)


def test_builtin_capabilities_are_immutable() -> None:
    """
    title: Analysis and lowering share closed names and copied symbol maps.
    """
    registry = get_default_runtime_feature_registry()
    assert frozenset(registry.names()) == BUILTIN_RUNTIME_FEATURES
    with pytest.raises(ValueError, match="immutable"):
        registry.register(RuntimeFeature("extra"))
    with pytest.raises(ValueError, match="already exists"):
        registry.with_native_features((NativeFeature("arrow_compute"),))
    symbols = {
        "dummy_rt": ExternalSymbolSpec("dummy_rt", _declare_dummy_symbol)
    }
    feature = RuntimeFeature("owned", symbols=symbols)
    symbols.clear()
    assert tuple(feature.symbols) == ("dummy_rt",)
    with pytest.raises(TypeError):
        feature.symbols["bad"] = feature.symbols["dummy_rt"]


def test_focused_compute_feature(tmp_path: Path) -> None:
    """
    title: Compile and run the C-only ABI without DataFrame or Parquet glue.
    parameters:
      tmp_path:
        type: Path
    """
    registry = get_default_runtime_feature_registry()
    visitor = Visitor()
    state = RuntimeFeatureState(visitor, registry)
    for name in COMPUTE_SIGNATURES:
        state.require_symbol("arrow_compute", name)
    llvm.parse_assembly(str(visitor._llvm.module)).verify()
    assert state.active_feature_names() == ("arrow_compute",)
    artifacts = state.native_artifacts()
    assert [item.path.name for item in artifacts] == ["irx_arrow_compute.cc"]
    assert not any("parquet" in flag for flag in state.linker_flags())
    source = tmp_path / "compute.c"
    source.write_text("""#include "irx_arrow_compute.h"
#include <assert.h>
#include <string.h>
int main(void) {
  assert(irx_arrow_compute_abi_version() == IRX_COMPUTE_ABI_VERSION);
  for (int op = IRX_COMPUTE_SQRT; op <= IRX_COMPUTE_EXP; ++op) {
    irx_arrow_chunked_array_handle* output = 0;
    uint64_t input_bits, output_bits;
    int32_t valid;
    double value = 0.0, result;
    memcpy(&input_bits, &value, sizeof(value));
    assert(irx_arrow_compute(IRX_COMPUTE_ABI_VERSION, op, 1, 0,
        IRX_COMPUTE_F64,
        IRX_COMPUTE_SCALAR, IRX_COMPUTE_F64, 0, input_bits, 1,
        0, 0, 0, 0, IRX_COMPUTE_F64, &output,
        &output_bits, &valid) == IRX_OK);
    memcpy(&result, &output_bits, sizeof(result));
    assert(!output && valid == 1);
    assert(result == (op == IRX_COMPUTE_SQRT ? 0.0 : 1.0));
  }
}
""")
    primary = compile_native_artifacts(
        (NativeArtifact("c_source", source, (artifacts[0].path.parent,)),),
        tmp_path,
    ).objects[0]
    binary = tmp_path / "compute"
    link_executable(primary, binary, artifacts, state.linker_flags())
    subprocess.run([str(binary)], check=True)


def test_runtime_feature_state_collects_only_active_artifacts() -> None:
    """
    title: Native artifact resolution should include only active features.
    """
    registry = RuntimeFeatureRegistry()
    registry.register(
        RuntimeFeature(
            name="feature_a",
            artifacts=(
                NativeArtifact("c_source", Path(".tmp/tests/a.c")),
                NativeArtifact("object", Path(".tmp/tests/a.o")),
            ),
        )
    )
    registry.register(
        RuntimeFeature(
            name="feature_b",
            artifacts=(NativeArtifact("c_source", Path(".tmp/tests/b.c")),),
        )
    )
    visitor = Visitor()
    state = RuntimeFeatureState(
        visitor,
        registry,
        active_features={"feature_b"},
    )

    artifacts = state.native_artifacts()

    assert [artifact.path for artifact in artifacts] == [
        Path(".tmp/tests/b.c")
    ]


def test_print_expr_uses_libc_feature_without_array_runtime() -> None:
    """
    title: PrintExpr should activate libc without pulling in the array runtime.
    """
    builder = Builder()
    module = astx.Module()

    main_proto = astx.FunctionPrototype(
        "main", args=astx.Arguments(), return_type=astx.Int32()
    )
    body = astx.Block()
    body.append(PrintExpr(astx.LiteralInt32(7)))
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module.block.append(astx.FunctionDef(prototype=main_proto, body=body))

    ir_text = builder.translate(module)

    active_features = (
        builder.translator.runtime_features.active_feature_names()
    )

    assert "libc" in active_features
    assert "array" not in active_features
    assert '@"puts"' in ir_text
    assert '@"snprintf"' in ir_text


def test_simple_module_uses_only_scalar_context_runtime() -> None:
    """
    title: A simple module needs scalar context and class lifetime support.
    """
    builder = Builder()

    builder.translate(_main_return_zero_module())

    artifacts = builder.translator.runtime_features.native_artifacts()
    assert {artifact.path.name for artifact in artifacts} == {
        "irx_class_runtime.c",
        "irx_exception_runtime.c",
        "irx_error_runtime.c",
    }


def test_list_runtime_exposes_status_and_destroy_contract() -> None:
    """
    title: The list feature declares append checks and idempotent destruction.
    """
    feature = build_list_runtime_feature()

    assert set(feature.symbols) == {
        "irx_list_append",
        "irx_list_at",
        "irx_list_destroy",
        "irx_list_status_message",
        "irx_list_sequence_read",
    }
    assert "no destroy or release helper yet" not in feature.metadata.get(
        "limitations",
        (),
    )


def test_runtime_failure_feature_has_machine_protocol_and_native_source() -> (
    None
):
    """
    title: Fatal runtime errors use one registered machine-readable protocol.
    """
    feature = build_runtime_failure_feature()
    assert set(feature.symbols) == {"__arx_runtime_fail"}
    assert feature.metadata["exit_status"] == 1
    assert feature.artifacts[0].path.name == "irx_error_runtime.c"


def test_feature_backed_extern_collects_linker_flags() -> None:
    """
    title: Extern features add linker flags to the checked scalar ABI baseline.
    """
    builder = Builder()
    module = astx.Module()
    module.block.append(
        _extern_prototype(
            "sqrt",
            astx.Argument("value", astx.Float64()),
            return_type=astx.Float64(),
            runtime_feature="libm",
        )
    )
    main_proto = astx.FunctionPrototype(
        "main", args=astx.Arguments(), return_type=astx.Int32()
    )
    body = astx.Block()
    body.append(
        astx.FunctionReturn(
            astx.Cast(
                astx.FunctionCall("sqrt", [astx.LiteralFloat64(9.0)]),
                astx.Int32(),
            )
        )
    )
    module.block.append(astx.FunctionDef(prototype=main_proto, body=body))

    builder.translate(module)

    assert builder.translator.runtime_features.active_feature_names() == (
        "class",
        "errors",
        "exceptions",
        "libc",
        "libm",
    )
    assert builder.translator.runtime_features.linker_flags() == ("-lm",)
    artifacts = builder.translator.runtime_features.native_artifacts()
    assert {artifact.path.name for artifact in artifacts} == {
        "irx_class_runtime.c",
        "irx_exception_runtime.c",
        "irx_error_runtime.c",
    }


def test_runtime_feature_state_reports_unknown_feature_structurally() -> None:
    """
    title: Unknown runtime features should raise structured runtime errors.
    """
    state = RuntimeFeatureState(Visitor(), RuntimeFeatureRegistry())

    with pytest.raises(RuntimeFeatureError) as exc_info:
        state.activate("missing")

    formatted = str(exc_info.value)

    assert "IRX-R001" in formatted
    assert "runtime feature 'missing' is not registered" in formatted


def test_runtime_feature_state_reports_missing_symbol_structurally() -> None:
    """
    title: Missing runtime symbols should raise structured runtime errors.
    """
    registry = RuntimeFeatureRegistry()
    registry.register(RuntimeFeature(name="dummy"))
    state = RuntimeFeatureState(Visitor(), registry)

    with pytest.raises(RuntimeFeatureError) as exc_info:
        state.require_symbol("dummy", "dummy_symbol")

    formatted = str(exc_info.value)

    assert "IRX-R002" in formatted
    assert (
        "runtime feature 'dummy' does not declare symbol 'dummy_symbol'"
        in formatted
    )


def test_compile_native_artifact_failure_surfaces_compile_phase_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    title: Native compile failures should preserve command and phase context.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    artifact = NativeArtifact("c_source", tmp_path / "runtime.c")

    def _fail_compile(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        """
        title: Return a failing compiler result.
        parameters:
          args:
            type: object
            variadic: positional
          kwargs:
            type: object
            variadic: keyword
        returns:
          type: subprocess.CompletedProcess[str]
        """
        command = list(cast(Sequence[str], args[0])) if args else []
        _ = kwargs
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="fatal error: buffer_runtime.h not found",
        )

    monkeypatch.setattr(
        "irx.builder.runtime.linking.subprocess.run", _fail_compile
    )

    with pytest.raises(NativeCompileError) as exc_info:
        compile_native_artifacts([artifact], tmp_path)

    formatted = str(exc_info.value)

    assert "IRX-C001" in formatted
    assert "native-compile" in formatted
    assert str(artifact.path) in formatted
    assert "command:" in formatted
    assert "stderr: fatal error: buffer_runtime.h not found" in formatted


def test_link_failure_surfaces_link_phase_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    title: Link failures should preserve command and output context.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    primary_object = tmp_path / "main.o"

    def _fail_link(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        """
        title: Return a failing linker result.
        parameters:
          args:
            type: object
            variadic: positional
          kwargs:
            type: object
            variadic: keyword
        returns:
          type: subprocess.CompletedProcess[str]
        """
        command = list(cast(Sequence[str], args[0])) if args else []
        _ = kwargs
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="undefined reference to `sqrt'",
        )

    monkeypatch.setattr(
        "irx.builder.runtime.linking.subprocess.run", _fail_link
    )

    with pytest.raises(LinkingError) as exc_info:
        link_executable(primary_object, tmp_path / "demo", ())

    formatted = str(exc_info.value)

    assert "IRX-K001" in formatted
    assert "link failed while producing 'demo'" in formatted
    assert "command:" in formatted
    assert "stderr: undefined reference to `sqrt'" in formatted


def test_optional_feature_dependencies_and_availability() -> None:
    """
    title: >-
      Resolve dependencies atomically and fail only when unavailable work
      activates.
    """
    registry = RuntimeFeatureRegistry()
    registry.register(RuntimeFeature("base"))
    registry.register(RuntimeFeature("format", dependencies=("base",)))
    registry.register(
        RuntimeFeature(
            "missing",
            dependencies=("base",),
            unavailable_reason="install matching native libraries",
        )
    )
    state = RuntimeFeatureState(Visitor(), registry)
    with pytest.raises(RuntimeFeatureError, match="unavailable") as error:
        state.activate("missing")
    assert error.value.diagnostic.code == "R003"
    assert state.active_feature_names() == ()
    state.activate("format")
    assert state.active_feature_names() == ("base", "format")


def test_runtime_dependency_cycles_fail_without_activation() -> None:
    """
    title: >-
      Detect cycles instead of recurring forever or activating partial graphs.
    """
    registry = RuntimeFeatureRegistry()
    registry.register(RuntimeFeature("one", dependencies=("two",)))
    registry.register(RuntimeFeature("two", dependencies=("one",)))
    state = RuntimeFeatureState(Visitor(), registry)
    with pytest.raises(RuntimeFeatureError, match="cycle"):
        state.activate("one")
    assert state.active_feature_names() == ()
