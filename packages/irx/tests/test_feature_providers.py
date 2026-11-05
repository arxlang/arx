"""
title: Built-in discovery, phase isolation, and compiler selection contracts.
"""

from __future__ import annotations

import json
import sys

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import cast

import pytest

from irx.analysis.extensions.calls import AnalysisCall
from irx.analysis.extensions.records import CallOperation
from irx.extensions import (
    ConfigurationError,
    FeatureConfiguration,
    FeatureDescriptor,
    HandlerContribution,
    PhaseProvider,
    contribute,
    default_feature_configuration,
    discover_builtin_features,
)
from irx.typecheck import typechecked
from typeguard import TypeCheckError


@typechecked
def visit(operation: CallOperation, call: AnalysisCall) -> None:
    """
    title: Fail if an inspection accidentally executes an implementation.
    parameters:
      operation:
        type: CallOperation
      call:
        type: AnalysisCall
    """
    raise AssertionError("inspection executed a handler")


def contributions() -> tuple[HandlerContribution, ...]:
    """
    title: Export a valid synthetic call provider using real phase contracts.
    returns:
      type: tuple[HandlerContribution, Ellipsis]
    """
    return (
        contribute(
            "a.call", "a", "analysis", CallOperation, AnalysisCall, visit
        ),
    )


def conflicting() -> tuple[HandlerContribution, ...]:
    """
    title: Export a different owner with a conflicting nominal signature.
    returns:
      type: tuple[HandlerContribution, Ellipsis]
    """
    return (
        contribute(
            "b.call", "b", "analysis", CallOperation, AnalysisCall, visit
        ),
    )


def malformed() -> tuple[object, ...]:
    """
    title: Exercise validation of every exported collection member.
    returns:
      type: tuple[object, Ellipsis]
    """
    return (*contributions(), object())


def feature(
    identity: str, dependencies: tuple[str, ...] = ()
) -> FeatureDescriptor:
    """
    title: Create lightweight metadata whose factory need not be imported.
    parameters:
      identity:
        type: str
      dependencies:
        type: tuple[str, Ellipsis]
    returns:
      type: FeatureDescriptor
    """
    return FeatureDescriptor(
        identity,
        (
            PhaseProvider(
                "analysis", f"{__name__}:contributions", (f"{identity}.call",)
            ),
        ),
        f"{__name__}:feature",
        dependencies=dependencies,
    )


def test_selection_is_deterministic_inspectable_and_isolated() -> None:
    """
    title: >-
      Dependencies, defaults, explicit roots, and disables remain distinct.
    """
    a, b, c = feature("a"), feature("b", ("a",)), feature("c")
    selected = FeatureConfiguration((c, b, a), selected=("b",))
    assert selected.enabled == ("a", "b")
    assert (
        selected.inspect()
        == FeatureConfiguration((a, b, c), selected=("b",)).inspect()
    )
    report = selected.inspect()
    rows = cast(list[dict[str, object]], report["features"])
    assert [row["selection"] for row in rows] == [
        "dependency",
        "explicit",
        "available",
    ]
    assert report["native_activation"] is None
    assert FeatureConfiguration((a, b), disabled=("b",)).enabled == ("a",)
    assert FeatureConfiguration((a, b), selected=()).enabled == ()
    rows.clear()
    assert len(cast(list[object], selected.inspect()["features"])) == len(
        selected.available
    )
    with pytest.raises(FrozenInstanceError):
        setattr(selected, "enabled", ())


@pytest.mark.parametrize(
    ("available", "selected", "disabled", "message"),
    [
        ((feature("a"), feature("a")), None, (), "duplicate"),
        ((feature("a", ("missing",)),), None, (), "missing"),
        (
            (feature("a", ("b",)), feature("b", ("a",))),
            None,
            (),
            "a -> b -> a",
        ),
        ((feature("a"),), ("missing",), (), "unknown"),
        ((feature("a"),), None, ("missing",), "unknown"),
        ((feature("a"),), ("a", "a"), (), "duplicate"),
        ((feature("a"),), ("a",), ("a",), "disabled"),
        ((feature("a"), feature("b", ("a",))), ("b",), ("a",), "b: required"),
    ],
)
def test_invalid_selection_fails_before_provider_import(
    available: tuple[FeatureDescriptor, ...],
    selected: tuple[str, ...] | None,
    disabled: tuple[str, ...],
    message: str,
) -> None:
    """
    title: Reject invalid dependency graphs and contradictory selections.
    parameters:
      available:
        type: tuple[FeatureDescriptor, Ellipsis]
      selected:
        type: tuple[str, Ellipsis] | None
      disabled:
        type: tuple[str, Ellipsis]
      message:
        type: str
    """
    with pytest.raises(ConfigurationError, match=message):
        FeatureConfiguration(available, selected, disabled)


def test_descriptor_runtime_and_backend_contracts() -> None:
    """
    title: Reject bad revisions, references, collection items, and backends.
    """
    a = feature("a")
    with pytest.raises(ConfigurationError, match="revision"):
        replace(a, revision=99)
    with pytest.raises(ConfigurationError, match="reference"):
        PhaseProvider("analysis", "not-a-module:factory", ("handler",))
    with pytest.raises(ConfigurationError, match="duplicate"):
        replace(a, providers=(*a.providers, *a.providers))
    with pytest.raises(ConfigurationError, match="backend"):
        FeatureConfiguration((a,), backend="unknown")
    with pytest.raises(ConfigurationError, match="unavailable"):
        FeatureConfiguration((replace(a, backends=("other",)),))
    with pytest.raises(TypeCheckError):
        replace(a, dependencies=("valid", 1))
    with pytest.raises(TypeCheckError):
        FeatureConfiguration((a, object()))  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        PhaseProvider("analysis", "valid:factory", ("valid", 1))  # type: ignore[arg-type]


def test_phase_promises_conflicts_and_disabled_factories() -> None:
    """
    title: >-
      Check promises against exports before exposing compiler-ready handlers.
    """
    a = feature("a")
    configuration = FeatureConfiguration((a,))
    phase = configuration.phase("analysis")
    assert phase.explain(CallOperation, AnalysisCall).identity == "a.call"
    assert configuration.phase("analysis") is not phase
    b = replace(
        feature("b"),
        providers=(
            PhaseProvider("analysis", f"{__name__}:conflicting", ("b.call",)),
        ),
    )
    with pytest.raises(ConfigurationError, match="duplicate handlers"):
        FeatureConfiguration((a, b)).phase("analysis")
    unavailable = replace(
        a,
        providers=(
            PhaseProvider(
                "analysis", "not_installed.provider:factory", ("a.call",)
            ),
        ),
    )
    assert (
        not FeatureConfiguration((unavailable,), selected=())
        .phase("analysis")
        .contributions
    )
    with pytest.raises(ConfigurationError, match=r"not_installed\.provider"):
        FeatureConfiguration((unavailable,)).phase("analysis")
    with pytest.raises(ConfigurationError, match="promised"):
        FeatureConfiguration(
            (
                replace(
                    a,
                    providers=(
                        replace(a.providers[0], provides=("missing",)),
                    ),
                ),
            )
        ).phase("analysis")
    with pytest.raises(ConfigurationError, match="wrong owner"):
        FeatureConfiguration((feature("b"),)).phase("analysis")
    with pytest.raises(ConfigurationError, match="invalid contribution"):
        FeatureConfiguration(
            (
                replace(
                    a,
                    providers=(
                        replace(
                            a.providers[0], factory=f"{__name__}:malformed"
                        ),
                    ),
                ),
            )
        ).phase("analysis")


def test_builtin_discovery_is_additive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    title: >-
      A new descriptor module is discovered without a central registry edit.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    from irx.extensions import builtin  # noqa: PLC0415

    name = "irx.extensions.builtin.example"
    (tmp_path / "example.py").write_text(
        "from irx.extensions import FeatureDescriptor, PhaseProvider\n"
        "def descriptor():\n"
        "    return FeatureDescriptor('example', "
        "(PhaseProvider('analysis', 'not_installed:factory', ('example',)),), "
        f"'{name}:descriptor')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        builtin, "__path__", [*builtin.__path__, str(tmp_path)]
    )
    try:
        found = discover_builtin_features()
        assert {d.identity for d in found} == {"example", "irx.table_io"}
        selected = FeatureConfiguration(found, selected=("irx.table_io",))
        assert selected.phase("analysis").contributions
    finally:
        sys.modules.pop(name, None)


def test_default_selection_matches_real_compiler_catalogs() -> None:
    """
    title: >-
      Inspection and compilation share the discovered selection and promises.
    """
    from irx.analysis.extensions.calls import (  # noqa: PLC0415
        default_analysis_configuration,
    )
    from irx.builder import Visitor  # noqa: PLC0415
    from irx.builder.extensions.calls import (  # noqa: PLC0415
        default_lowering_configuration,
    )

    configuration = default_feature_configuration()
    assert json.dumps(configuration.inspect(), sort_keys=True)
    for phase in (
        default_analysis_configuration(),
        default_lowering_configuration(),
    ):
        expected = configuration.phase(phase.phase)
        assert phase.inspect() == expected.inspect()
    assert Visitor().runtime_features.active_feature_names() == ()
