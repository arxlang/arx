"""
title: Deterministic built-in feature selection and phase-lazy composition.
summary: >-
  Only modules in irx.extensions.builtin are enumerated. Their descriptor
  factories must be lightweight and side-effect free. Implementation factories
  load only when a selected phase is composed; neither discovery nor selection
  activates native code. This catalog covers migrated call handlers, not every
  language capability. Installed third-party entry points are not discovered.
"""

from __future__ import annotations

import inspect

from dataclasses import dataclass, field
from functools import lru_cache
from importlib import import_module
from pkgutil import iter_modules

from public import private, public

from irx.extensions.handlers import (
    HandlerConfiguration,
    HandlerContribution,
    Phase,
    configuration_error,
)
from irx.typecheck import typechecked

CONTRACT_REVISION = 1


@private
@typechecked
def validate_names(names: tuple[str, ...], label: str) -> None:
    """
    title: Require nonempty unique identifiers, checking every item.
    parameters:
      names:
        type: tuple[str, Ellipsis]
      label:
        type: str
    """
    if any(not name or name.strip() != name for name in names):
        raise configuration_error(f"{label}: identifiers must be nonempty")
    if len(set(names)) != len(names):
        raise configuration_error(f"{label}: duplicate identifiers")


@private
@typechecked
def validate_reference(reference: str) -> None:
    """
    title: Require a qualified module and top-level factory name.
    parameters:
      reference:
        type: str
    """
    module, separator, name = reference.partition(":")
    if (
        not separator
        or not name.isidentifier()
        or not all(part.isidentifier() for part in module.split("."))
    ):
        raise configuration_error(f"invalid provider reference: {reference!r}")


@public
@typechecked
@dataclass(frozen=True)
class PhaseProvider:
    """
    title: Lazy factory and the exact handler identities it promises.
    summary: Factories take no arguments and return checked contributions.
    attributes:
      phase:
        type: Phase
      factory:
        type: str
      provides:
        type: tuple[str, Ellipsis]
    """

    phase: Phase
    factory: str
    provides: tuple[str, ...]

    def __post_init__(self) -> None:
        """
        title: Validate generated constructor fields at runtime.
        """
        validate_provider(self.phase, self.factory, self.provides)


@private
@typechecked
def validate_provider(
    phase: Phase, factory: str, provides: tuple[str, ...]
) -> None:
    """
    title: Validate a phase promise without importing its implementation.
    parameters:
      phase:
        type: Phase
      factory:
        type: str
      provides:
        type: tuple[str, Ellipsis]
    """
    validate_reference(factory)
    validate_names(provides, f"{phase} provider {factory}")
    if not provides:
        raise configuration_error(
            f"{factory}: at least one handler is required"
        )


@public
@typechecked
@dataclass(frozen=True)
class FeatureDescriptor:
    """
    title: Immutable metadata for one built-in compiler feature.
    summary: >-
      Identity is also the owner of every exported contribution. Revision names
      this compiler-side contract, not the package or native ABI version.
      Backend availability applies to the complete feature, including analysis.
    attributes:
      identity:
        type: str
      providers:
        type: tuple[PhaseProvider, Ellipsis]
      source:
        type: str
      dependencies:
        type: tuple[str, Ellipsis]
      backends:
        type: tuple[str, Ellipsis]
      revision:
        type: int
    """

    identity: str
    providers: tuple[PhaseProvider, ...]
    source: str
    dependencies: tuple[str, ...] = ()
    backends: tuple[str, ...] = ("llvm",)
    revision: int = CONTRACT_REVISION

    def __post_init__(self) -> None:
        """
        title: Check fields and duplicate phase promises before selection.
        """
        validate_descriptor(
            self.identity,
            self.providers,
            self.source,
            self.dependencies,
            self.backends,
            self.revision,
        )


@private
@typechecked
def validate_descriptor(
    identity: str,
    providers: tuple[PhaseProvider, ...],
    source: str,
    dependencies: tuple[str, ...],
    backends: tuple[str, ...],
    revision: int,
) -> None:
    """
    title: Validate all descriptor collection members without loading code.
    parameters:
      identity:
        type: str
      providers:
        type: tuple[PhaseProvider, Ellipsis]
      source:
        type: str
      dependencies:
        type: tuple[str, Ellipsis]
      backends:
        type: tuple[str, Ellipsis]
      revision:
        type: int
    """
    validate_names((identity,), "feature")
    validate_reference(source)
    validate_names(dependencies, identity)
    validate_names(backends, identity)
    validate_names(tuple(p.phase for p in providers), identity)
    if revision != CONTRACT_REVISION:
        raise configuration_error(
            f"{identity}: unsupported contract revision {revision}; "
            f"expected {CONTRACT_REVISION}"
        )
    if not backends or not providers:
        raise configuration_error(
            f"{identity}: providers and backends required"
        )


@private
@typechecked
def invoke_factory(reference: str) -> object:
    """
    title: Load an explicit factory, attributing failures to its reference.
    parameters:
      reference:
        type: str
    returns:
      type: object
    """
    validate_reference(reference)
    module, name = reference.split(":")
    try:
        factory = getattr(import_module(module), name)
        if not callable(factory):
            raise TypeError("factory is not callable")
        inspect.signature(factory).bind()
        result: object = factory()
        return result
    except Exception as exc:
        raise configuration_error(
            f"{reference}: provider failed: {exc}"
        ) from exc


@public
@typechecked
def discover_builtin_features() -> tuple[FeatureDescriptor, ...]:
    """
    title: Discover descriptors from the installed built-in package namespace.
    summary: >-
      Each direct module exports descriptor(). No working-directory scan,
      recursive package imports, entry points, or automatic public exports.
      Enumeration works for source, wheel installs, and zip-importable
      packages.
    returns:
      type: tuple[FeatureDescriptor, Ellipsis]
    """
    from irx.extensions import builtin  # noqa: PLC0415

    descriptors = []
    for module in sorted(iter_modules(builtin.__path__), key=lambda m: m.name):
        if module.ispkg:
            raise configuration_error(
                f"{builtin.__name__}.{module.name}: "
                "expected a descriptor module"
            )
        reference = f"{builtin.__name__}.{module.name}:descriptor"
        descriptor = invoke_factory(reference)
        if not isinstance(descriptor, FeatureDescriptor):
            raise configuration_error(
                f"{reference}: expected FeatureDescriptor"
            )
        if descriptor.source != reference:
            raise configuration_error(
                f"{reference}: incorrect descriptor source"
            )
        descriptors.append(descriptor)
    result = tuple(sorted(descriptors, key=lambda d: d.identity))
    validate_names(tuple(d.identity for d in result), "built-in features")
    return result


@public
@typechecked
@dataclass(frozen=True)
class FeatureConfiguration:
    """
    title: Frozen selection shared by phase composition and inspection.
    summary: >-
      None selects all available features except explicitly disabled ones; an
      empty tuple selects none. Dependencies are enabled transitively, never
      silently overriding a disable. Stable dependency-first ordering ignores
      discovery and caller order. phase() validates factories before returning
      a compiler-ready catalog; disabled factories are never imported. Mutable
      dispatch and compilation state are not cached in this record.
    attributes:
      available:
        type: tuple[FeatureDescriptor, Ellipsis]
      selected:
        type: tuple[str, Ellipsis] | None
      disabled:
        type: tuple[str, Ellipsis]
      backend:
        type: str
      enabled:
        type: tuple[str, Ellipsis]
    """

    available: tuple[FeatureDescriptor, ...]
    selected: tuple[str, ...] | None = None
    disabled: tuple[str, ...] = ()
    backend: str = "llvm"
    enabled: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        """
        title: Validate and freeze a deterministic dependency closure.
        """
        enabled = select_features(
            self.available, self.selected, self.disabled, self.backend
        )
        object.__setattr__(self, "enabled", enabled)
        object.__setattr__(
            self,
            "available",
            tuple(sorted(self.available, key=lambda d: d.identity)),
        )
        object.__setattr__(self, "disabled", tuple(sorted(self.disabled)))
        if self.selected is not None:
            object.__setattr__(self, "selected", tuple(sorted(self.selected)))

    def phase(self, phase: Phase) -> HandlerConfiguration:
        """
        title: Load only enabled providers for one phase and validate promises.
        summary: >-
          Checks ownership, exact promised identities, duplicate signatures,
          and phase service contracts before any AST is compiled. Replacements
          remain explicit HandlerConfiguration.derive operations.
        parameters:
          phase:
            type: Phase
        returns:
          type: HandlerConfiguration
        """
        descriptors = {d.identity: d for d in self.available}
        contributions: list[HandlerContribution] = []
        for identity in self.enabled:
            descriptor = descriptors[identity]
            for provider in descriptor.providers:
                if provider.phase == phase:
                    contributions.extend(load_provider(descriptor, provider))
        configuration = HandlerConfiguration(phase, tuple(contributions))
        validate_phase(configuration)
        return configuration

    def selection_reason(self, identity: str) -> str:
        """
        title: Explain one available feature using the validated selection.
        parameters:
          identity:
            type: str
        returns:
          type: str
        """
        if identity not in {d.identity for d in self.available}:
            raise configuration_error(f"unknown feature: {identity}")
        if identity in self.disabled:
            return "disabled"
        if self.selected is None:
            return "default"
        if identity in self.selected:
            return "explicit"
        if identity in self.enabled:
            return "dependency"
        return "available"

    def inspect(self) -> dict[str, object]:
        """
        title: >-
          Return a fresh JSON-compatible metadata snapshot without loading
          providers.
        summary: >-
          Native activation is not observed by configuration inspection; only a
          compilation's runtime state can report it. Available but unselected
          features are included. Other visitor families are not inventoried.
        returns:
          type: dict[str, object]
        """
        return {
            "schema_version": 1,
            "scope": "composed call handlers",
            "backend": self.backend,
            "enabled": list(self.enabled),
            "native_activation": None,
            "features": [
                {
                    "identity": d.identity,
                    "revision": d.revision,
                    "source": d.source,
                    "dependencies": list(d.dependencies),
                    "backends": list(d.backends),
                    "selection": self.selection_reason(d.identity),
                    "providers": [
                        {
                            "phase": p.phase,
                            "factory": p.factory,
                            "provides": list(p.provides),
                        }
                        for p in sorted(d.providers, key=lambda p: p.phase)
                    ],
                }
                for d in self.available
            ],
        }


@private
@typechecked
def select_features(
    available: tuple[FeatureDescriptor, ...],
    selected: tuple[str, ...] | None,
    disabled: tuple[str, ...],
    backend: str,
) -> tuple[str, ...]:
    """
    title: >-
      Validate selection and resolve dependencies without provider imports.
    parameters:
      available:
        type: tuple[FeatureDescriptor, Ellipsis]
      selected:
        type: tuple[str, Ellipsis] | None
      disabled:
        type: tuple[str, Ellipsis]
      backend:
        type: str
    returns:
      type: tuple[str, Ellipsis]
    """
    validate_names(tuple(d.identity for d in available), "features")
    validate_names(disabled, "disabled features")
    if selected is not None:
        validate_names(selected, "selected features")
    if backend != "llvm":
        raise configuration_error(f"unsupported compiler backend: {backend}")
    descriptors = {d.identity: d for d in available}
    roots = (
        set(descriptors).difference(disabled)
        if selected is None
        else set(selected)
    )
    unknown = (roots | set(disabled)).difference(descriptors)
    if unknown:
        raise configuration_error(
            f"unknown features: {', '.join(sorted(unknown))}"
        )
    enabled: list[str] = []
    visiting: list[str] = []

    def enable(identity: str) -> None:
        """
        title: >-
          Resolve one dependency path with deterministic cycle diagnostics.
        parameters:
          identity:
            type: str
        """
        if identity in visiting:
            raise configuration_error(
                "feature dependency cycle: "
                + " -> ".join([*visiting, identity])
            )
        if identity in enabled:
            return
        reason = visiting[-1] if visiting else "selection"
        if identity in disabled or identity not in descriptors:
            raise configuration_error(
                f"{reason}: required feature {identity} is disabled or missing"
            )
        descriptor = descriptors[identity]
        if backend not in descriptor.backends:
            raise configuration_error(
                f"{identity}: unavailable for backend {backend}"
            )
        visiting.append(identity)
        for dependency in sorted(descriptor.dependencies):
            enable(dependency)
        visiting.pop()
        enabled.append(identity)

    for identity in sorted(roots):
        enable(identity)
    return tuple(enabled)


@private
@typechecked
def load_provider(
    descriptor: FeatureDescriptor, provider: PhaseProvider
) -> tuple[HandlerContribution, ...]:
    """
    title: >-
      Require the provider's complete, correctly owned phase contribution set.
    parameters:
      descriptor:
        type: FeatureDescriptor
      provider:
        type: PhaseProvider
    returns:
      type: tuple[HandlerContribution, Ellipsis]
    """
    result = invoke_factory(provider.factory)
    if not isinstance(result, tuple):
        raise configuration_error(
            f"{provider.factory}: expected contribution tuple"
        )
    contributions = []
    for item in result:
        if not isinstance(item, HandlerContribution):
            raise configuration_error(
                f"{provider.factory}: invalid contribution "
                f"{type(item).__name__}"
            )
        if item.owner != descriptor.identity or item.phase != provider.phase:
            raise configuration_error(
                f"{provider.factory}: wrong owner or phase for {item.identity}"
            )
        contributions.append(item)
    identities = tuple(item.identity for item in contributions)
    validate_names(identities, provider.factory)
    if set(identities) != set(provider.provides):
        raise configuration_error(
            f"{provider.factory}: promised {provider.provides}, "
            f"got {identities}"
        )
    return tuple(contributions)


@private
@typechecked
def validate_phase(configuration: HandlerConfiguration) -> None:
    """
    title: Check the actual call-driver dependencies before exposing a phase.
    parameters:
      configuration:
        type: HandlerConfiguration
    """
    if configuration.phase == "analysis":
        from irx.analysis.extensions.calls import AnalysisCall  # noqa: PLC0415
        from irx.analysis.extensions.records import (  # noqa: PLC0415
            CallOperation,
        )

        configuration.validate_contract(
            "analysis", CallOperation, AnalysisCall
        )
        return
    from irx.analysis.extensions.records import CallPlan  # noqa: PLC0415
    from irx.builder.extensions.calls import LoweringCall  # noqa: PLC0415

    configuration.validate_contract("lowering", CallPlan, LoweringCall)


@public
@lru_cache(maxsize=1)
@typechecked
def default_feature_configuration() -> FeatureConfiguration:
    """
    title: >-
      Cache only immutable built-in descriptors and their validated selection.
    returns:
      type: FeatureConfiguration
    """
    return FeatureConfiguration(discover_builtin_features())
