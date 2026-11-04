"""
title: Checked nominal dispatch with configuration-local contribution catalogs.
summary: >-
  Contributions contain stateless implementations, not compilation services.
  Derivation names replacements explicitly and never edits its parent. Each
  compiler instance constructs a fresh Plum Function using only public APIs;
  its lazy method/cache state is not shared across compilers. A dispatcher is
  reentrant, but simultaneous use of one mutable compiler is not supported.
  Signatures contain two ordinary nominal classes. Crossed subtype signatures
  are rejected; overlaps introduced by future multiple-inheritance types are
  diagnosed by Plum at invocation rather than guessed by another resolver.
"""

import inspect

from dataclasses import dataclass
from functools import wraps
from types import MethodType
from typing import Callable, Literal, TypeVar, get_type_hints

from plum import AmbiguousLookupError, Function, Signature
from public import private, public

from irx.diagnostics import Diagnostic, DiagnosticCodes, IRxDiagnosticError
from irx.typecheck import typechecked

Phase = Literal["analysis", "lowering"]
ValueT = TypeVar("ValueT")
ContextT = TypeVar("ContextT")


@public
@typechecked
class ConfigurationError(IRxDiagnosticError):
    """
    title: Invalid compiler composition or an unresolved registered dispatch.
    """


@private
@typechecked
def configuration_error(message: str) -> ConfigurationError:
    """
    title: Report configuration errors without inventing source attribution.
    parameters:
      message:
        type: str
    returns:
      type: ConfigurationError
    """
    return ConfigurationError(
        Diagnostic(
            message=message,
            code=DiagnosticCodes.CONFIGURATION_INVALID,
            phase="configuration",
        )
    )


@public
@typechecked
@dataclass(frozen=True)
class HandlerContribution:
    """
    title: Immutable registration metadata produced by contribute.
    summary: >-
      Identity, provider, phase, callable provenance, and the exact nominal
      signature remain inspectable. The adapter retains callable annotations
      and checks both nominal arguments before calling the implementation.
    attributes:
      identity:
        type: str
      owner:
        type: str
      phase:
        type: Phase
      signature:
        type: tuple[type[object], type[object]]
      implementation:
        type: Callable[[object, object], None]
      source:
        type: str
      replaces:
        type: str | None
    """

    identity: str
    owner: str
    phase: Phase
    signature: tuple[type[object], type[object]]
    implementation: Callable[[object, object], None]
    source: str
    replaces: str | None = None

    def __post_init__(self) -> None:
        """
        title: Validate generated constructor arguments and callable contracts.
        """
        validate_contribution(
            self.identity,
            self.owner,
            self.phase,
            self.signature,
            self.implementation,
            self.source,
            self.replaces,
        )


@private
@typechecked
def validate_contribution(
    identity: str,
    owner: str,
    phase: Phase,
    signature: tuple[type[object], type[object]],
    implementation: Callable[[object, object], None],
    source: str,
    replaces: str | None,
) -> None:
    """
    title: Require annotated positional handlers over ordinary nominal classes.
    parameters:
      identity:
        type: str
      owner:
        type: str
      phase:
        type: Phase
      signature:
        type: tuple[type[object], type[object]]
      implementation:
        type: Callable[[object, object], None]
      source:
        type: str
      replaces:
        type: str | None
    """
    if not identity or not owner or not source or replaces == "":
        raise configuration_error(
            "handler identity, owner and source are required"
        )
    if any(type(item) is not type for item in signature):
        raise configuration_error(
            f"{identity}: only ordinary nominal classes are supported"
        )
    try:
        parameters = tuple(
            inspect.signature(implementation).parameters.values()
        )
        annotations = get_type_hints(implementation)
    except (TypeError, ValueError, NameError) as exc:
        raise configuration_error(
            f"{owner}/{identity} ({source}): invalid handler contract: {exc}"
        ) from exc
    if (
        len(parameters) != len(signature)
        or any(
            p.kind not in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            or p.default is not p.empty
            for p in parameters
        )
        or tuple(annotations.get(p.name) for p in parameters) != signature
        or annotations.get("return") is not type(None)
    ):
        raise configuration_error(
            f"{owner}/{identity} ({source}): expected {signature} -> None"
        )


@public
@typechecked
def contribute(
    identity: str,
    owner: str,
    phase: Phase,
    value_type: type[ValueT],
    context_type: type[ContextT],
    implementation: Callable[[ValueT, ContextT], None],
    *,
    replaces: str | None = None,
) -> HandlerContribution:
    """
    title: Export a typed function or bound provider method explicitly.
    summary: >-
      Providers may inherit implementations and export overridden methods with
      replaces naming the parent contribution. No class dictionary is scanned.
      Providers must not capture compilation state; services arrive at
      invocation.
    parameters:
      identity:
        type: str
      owner:
        type: str
      phase:
        type: Phase
      value_type:
        type: type[ValueT]
      context_type:
        type: type[ContextT]
      implementation:
        type: Callable[[ValueT, ContextT], None]
      replaces:
        type: str | None
    returns:
      type: HandlerContribution
    """
    if not (
        inspect.isfunction(implementation) or inspect.ismethod(implementation)
    ):
        raise configuration_error(
            f"{owner}/{identity}: expected an annotated function or bound "
            f"method, got {type(implementation).__qualname__}"
        )
    source = f"{implementation.__module__}.{implementation.__qualname__}"
    try:
        annotations = get_type_hints(implementation)
        signature = inspect.signature(implementation)
    except (TypeError, ValueError, NameError) as exc:
        raise configuration_error(
            f"{owner}/{identity} ({source}): invalid handler contract: {exc}"
        ) from exc
    checked: Callable[[ValueT, ContextT], None]
    if inspect.ismethod(implementation):
        checked = MethodType(
            typechecked(implementation.__func__), implementation.__self__
        )
    else:
        checked = typechecked(implementation)

    @wraps(implementation)
    def invoke(value: object, context: object) -> None:
        """
        title: Check the erased dispatch boundary before entering typed code.
        parameters:
          value:
            type: object
          context:
            type: object
        """
        if not isinstance(value, value_type) or not isinstance(
            context, context_type
        ):
            raise TypeError(
                f"invalid arguments for handler {owner}/{identity}"
            )
        checked(value, context)

    invoke.__annotations__ = annotations
    setattr(
        invoke,
        "__signature__",
        signature.replace(
            parameters=[
                p.replace(annotation=annotations.get(p.name, p.annotation))
                for p in signature.parameters.values()
            ],
            return_annotation=annotations.get(
                "return", signature.return_annotation
            ),
        ),
    )
    return HandlerContribution(
        identity,
        owner,
        phase,
        (value_type, context_type),
        invoke,
        source,
        replaces,
    )


@public
@typechecked
@dataclass(frozen=True)
class HandlerConfiguration:
    """
    title: Validated frozen phase catalog with explicit parent derivation.
    summary: >-
      Construct a base from contributions without replacement intents. derive
      accepts additions and named replacements; the effective tuple preserves
      registration provenance. No runtime service or dispatcher is cached here.
    attributes:
      phase:
        type: Phase
      contributions:
        type: tuple[HandlerContribution, Ellipsis]
      parent:
        type: HandlerConfiguration | None
    """

    phase: Phase
    contributions: tuple[HandlerContribution, ...]
    parent: "HandlerConfiguration | None" = None

    def __post_init__(self) -> None:
        """
        title: Validate every contribution and freeze the effective catalog.
        """
        effective = compose(self.phase, self.contributions, self.parent)
        object.__setattr__(self, "contributions", effective)

    def derive(self, *changes: HandlerContribution) -> "HandlerConfiguration":
        """
        title: Return an isolated derived configuration.
        parameters:
          changes:
            type: HandlerContribution
            variadic: positional
        returns:
          type: HandlerConfiguration
        """
        return HandlerConfiguration(self.phase, changes, self)

    def validate_contract(
        self,
        phase: Phase,
        value_type: type[object],
        context_type: type[object],
    ) -> None:
        """
        title: >-
          Reject handlers requiring unavailable phase arguments or services.
        parameters:
          phase:
            type: Phase
          value_type:
            type: type[object]
          context_type:
            type: type[object]
        """
        if self.phase != phase:
            raise configuration_error(f"expected {phase}, got {self.phase}")
        for item in self.contributions:
            if not issubclass(item.signature[0], value_type) or not issubclass(
                context_type, item.signature[1]
            ):
                raise configuration_error(
                    f"{item.owner}/{item.identity}: "
                    "unavailable phase dependencies "
                    f"for {item.signature} ({item.source})"
                )

    def inspect(self) -> dict[str, object]:
        """
        title: Return a fresh stable snapshot of effective handler provenance.
        summary: Replacements name their predecessor; no handler is executed.
        returns:
          type: dict[str, object]
        """
        return {
            "schema_version": 1,
            "phase": self.phase,
            "handlers": [
                {
                    "identity": item.identity,
                    "owner": item.owner,
                    "source": item.source,
                    "signature": [
                        f"{t.__module__}.{t.__qualname__}"
                        for t in item.signature
                    ],
                    "replaces": item.replaces,
                }
                for item in sorted(
                    self.contributions, key=lambda c: c.identity
                )
            ],
        }

    def explain(
        self, value_type: type[object], context_type: type[object]
    ) -> HandlerContribution:
        """
        title: Explain Plum's selection for one concrete nominal signature.
        summary: >-
          Uses a fresh dispatcher and public Plum resolution, not a second
          specificity algorithm. Never executes a handler or changes compiler
          dispatch state. Missing and ambiguous signatures are configuration
          errors, just as at invocation.
        parameters:
          value_type:
            type: type[object]
          context_type:
            type: type[object]
        returns:
          type: HandlerContribution
        """
        if any(type(t) is not type for t in (value_type, context_type)):
            raise configuration_error("explanation requires nominal classes")
        dispatcher = ScopedDispatch(self)
        function = dispatcher.function
        if not isinstance(function, Function):
            raise configuration_error("expected an isolated Plum function")
        try:
            implementation, _ = function.resolve_method(
                Signature(value_type, context_type)
            )
        except AmbiguousLookupError as exc:
            raise configuration_error(
                f"ambiguous {self.phase} dispatch: {exc}"
            ) from exc
        for contribution in self.contributions:
            if contribution.implementation is implementation:
                return contribution
        raise configuration_error(
            f"no {self.phase} handler for "
            f"({value_type.__name__}, {context_type.__name__})"
        )


@private
@typechecked
def compose(
    phase: Phase,
    changes: tuple[HandlerContribution, ...],
    parent: HandlerConfiguration | None,
) -> tuple[HandlerContribution, ...]:
    """
    title: Validate duplicates, replacement intent, and known crossed subtypes.
    parameters:
      phase:
        type: Phase
      changes:
        type: tuple[HandlerContribution, Ellipsis]
      parent:
        type: HandlerConfiguration | None
    returns:
      type: tuple[HandlerContribution, Ellipsis]
    """
    if parent is not None and parent.phase != phase:
        raise configuration_error("cannot derive a different phase")
    effective = list(parent.contributions) if parent is not None else []
    replaced: set[str] = set()
    for item in changes:
        if item.signature == (object, object):
            raise configuration_error(
                f"{item.owner}/{item.identity}: the universal fallback "
                "cannot be replaced"
            )
        if item.phase != phase:
            raise configuration_error(
                f"{item.identity}: wrong phase {item.phase}"
            )
        if item.replaces is None:
            effective.append(item)
            continue
        previous = next(
            (c for c in effective if c.identity == item.replaces), None
        )
        if parent is None or previous is None or item.replaces in replaced:
            raise configuration_error(
                f"{item.identity}: invalid replacement {item.replaces}"
            )
        if (
            previous not in parent.contributions
            or item.signature != previous.signature
        ):
            raise configuration_error(
                f"{item.identity}: replacement must preserve "
                "the parent signature"
            )
        replaced.add(item.replaces)
        effective[effective.index(previous)] = item
    for index, item in enumerate(effective):
        for previous in effective[:index]:
            label = (
                f"{previous.owner}/{previous.identity} and "
                f"{item.owner}/{item.identity}"
            )
            if (
                item.identity == previous.identity
                or item.signature == previous.signature
            ):
                raise configuration_error(
                    f"duplicate handlers: {label} {item.signature}"
                )
            left = tuple(
                issubclass(a, b)
                for a, b in zip(item.signature, previous.signature)
            )
            right = tuple(
                issubclass(b, a)
                for a, b in zip(item.signature, previous.signature)
            )
            if (
                not all(left)
                and not all(right)
                and all(a or b for a, b in zip(left, right))
            ):
                raise configuration_error(
                    f"ambiguous crossed signatures: {label}: "
                    f"{previous.signature} ({previous.source}) and "
                    f"{item.signature} ({item.source})"
                )
    return tuple(effective)


@public
@typechecked
class ScopedDispatch:
    """
    title: Per-compiler Plum dispatch and cache, separate from frozen metadata.
    attributes:
      configuration:
        type: HandlerConfiguration
      function:
        type: Function
    """

    configuration: HandlerConfiguration
    function: Function

    def __init__(self, configuration: HandlerConfiguration) -> None:
        """
        title: Construct fresh dispatch state with a typed failing fallback.
        parameters:
          configuration:
            type: HandlerConfiguration
        """
        self.configuration = configuration
        self.function = Function(self.reject)
        self.function.register(self.reject, Signature(object, object))
        for item in configuration.contributions:
            self.function.register(
                item.implementation, Signature(*item.signature)
            )

    def reject(self, value: object, context: object) -> None:
        """
        title: Fail explicitly for an unregistered nominal signature.
        parameters:
          value:
            type: object
          context:
            type: object
        """
        raise configuration_error(
            f"no {self.configuration.phase} handler for "
            f"({type(value).__name__}, {type(context).__name__})"
        )

    def visit(self, value: object, context: object) -> None:
        """
        title: >-
          Invoke Plum specificity rules and translate unresolved ambiguity.
        parameters:
          value:
            type: object
          context:
            type: object
        """
        try:
            self.function(value, context)
        except AmbiguousLookupError as exc:
            raise configuration_error(
                f"ambiguous {self.configuration.phase} dispatch: {exc}"
            ) from exc
