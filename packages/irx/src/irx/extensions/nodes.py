"""
title: Compiler-local nominal AST dispatch through public Plum APIs.
summary: >-
  Feature implementations export bound handlers explicitly rather than
  registering methods on a shared visitor. Bindings belong to one compiler;
  immutable provider descriptors must never retain them. Each dispatcher owns
  bindings and a resolution cache. Identical nominal signature shapes share
  only sealed, stateless Plum selector metadata; no compilation is retained by
  Plum's global Function list. Plum remains the sole subtype resolver. The
  phase owns its typed rejection policy for unknown syntax.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from inspect import Parameter
from inspect import Signature as CallableSignature
from types import MappingProxyType, MethodType
from typing import Callable, TypeVar

import astx

from plum import AmbiguousLookupError, Function, NotFoundLookupError, Signature
from public import private, public

from irx.extensions.handlers import Phase, configuration_error
from irx.typecheck import typechecked

NodeT = TypeVar("NodeT", bound=astx.AST)


NODE_METHODS: dict[
    tuple[Function, type[object], type[astx.AST]],
    Callable[[object, astx.AST], None],
] = {}


@private
@typechecked
def resolve_node_method(
    function: Function,
    receiver_type: type[object],
    node_type: type[astx.AST],
) -> Callable[[object, astx.AST], None]:
    """
    title: Cache only immutable unbound method selection for a declared family.
    summary: >-
      A family is defined before compiler construction; its exported method set
      is not mutated afterwards. Cache keys contain nominal classes and their
      class-local dispatcher, never a provider instance, compilation, AST
      value, services, or semantic facts. Each binding later supplies its own
      receiver. Runtime traversal does not use the class dispatcher cache.
    parameters:
      function:
        type: Function
      receiver_type:
        type: type[object]
      node_type:
        type: type[astx.AST]
    returns:
      type: Callable[[object, astx.AST], None]
    """
    key = (function, receiver_type, node_type)
    cached = NODE_METHODS.get(key)
    if cached is not None:
        return cached
    selected, _ = function.resolve_method(Signature(receiver_type, node_type))
    try:
        fallback, _ = function.resolve_method(
            Signature(receiver_type, astx.AST)
        )
    except NotFoundLookupError:
        fallback = None
    if selected is fallback:
        raise configuration_error(
            f"provider {receiver_type.__qualname__} has no implementation "
            f"for promised {node_type.__name__}"
        )
    NODE_METHODS[key] = selected
    return selected


@public
@typechecked
@dataclass(frozen=True)
class NodeHandler:
    """
    title: An explicit feature binding owned by one compiler instance.
    summary: >-
      This is invocation state, not a reusable provider descriptor. A bound
      implementation may retain its feature services and state. The signature
      and provenance remain immutable and inspectable.
    attributes:
      identity:
        type: str
      owner:
        type: str
      phase:
        type: Phase
      node_type:
        type: type[astx.AST]
      implementation:
        type: Callable[[astx.AST], None]
      source:
        type: str
    """

    identity: str
    owner: str
    phase: Phase
    node_type: type[astx.AST]
    implementation: Callable[[astx.AST], None]
    source: str

    def __post_init__(self) -> None:
        """
        title: Validate generated constructor arguments before dispatch.
        """
        validate_handler(
            self.identity,
            self.owner,
            self.phase,
            self.node_type,
            self.implementation,
            self.source,
        )


@private
@typechecked
def validate_handler(
    identity: str,
    owner: str,
    phase: Phase,
    node_type: type[astx.AST],
    implementation: Callable[[astx.AST], None],
    source: str,
) -> None:
    """
    title: Check nominal selection and required registration provenance.
    parameters:
      identity:
        type: str
      owner:
        type: str
      phase:
        type: Phase
      node_type:
        type: type[astx.AST]
      implementation:
        type: Callable[[astx.AST], None]
      source:
        type: str
    """
    del phase, implementation
    if not identity or not owner or not source:
        raise configuration_error(
            "node handler identity, owner and source required"
        )
    if not isinstance(node_type, type) or node_type is astx.AST:
        raise configuration_error(
            f"{owner}/{identity}: use a concrete nominal AST signature; "
            "the phase owns its rejection fallback"
        )


@public
@typechecked
def contribute_node(
    identity: str,
    owner: str,
    phase: Phase,
    node_type: type[NodeT],
    implementation: Callable[[NodeT], None],
    *,
    source: str,
) -> NodeHandler:
    """
    title: Bind one supported nominal node without mutating any global visitor.
    summary: >-
      Implementations may be ordinary typed functions or bound feature methods,
      including a feature-local Plum visit family. Export each supported
      nominal signature explicitly; no class dictionary or Plum private
      registry is scanned.
    parameters:
      identity:
        type: str
      owner:
        type: str
      phase:
        type: Phase
      node_type:
        type: type[NodeT]
      implementation:
        type: Callable[[NodeT], None]
      source:
        type: str
    returns:
      type: NodeHandler
    """

    execute = implementation
    if isinstance(implementation, MethodType):
        receiver: object = implementation.__self__
        function = getattr(type(receiver), implementation.__name__, None)
        if isinstance(function, Function):
            try:
                selected = resolve_node_method(
                    function, type(receiver), node_type
                )
            except (AmbiguousLookupError, NotFoundLookupError) as exc:
                raise configuration_error(
                    f"{owner}/{identity}: invalid node binding "
                    f"({source}): {exc}"
                ) from exc

            def bound_node(node: NodeT) -> None:
                """
                title: >-
                  Invoke the selected method without shared runtime dispatch.
                parameters:
                  node:
                    type: NodeT
                """
                selected(receiver, node)

            execute = bound_node

    def invoke(node: astx.AST) -> None:
        """
        title: Check the nominal binding before entering the feature.
        parameters:
          node:
            type: astx.AST
        """
        if not isinstance(node, node_type):
            raise TypeError(f"invalid node for handler {owner}/{identity}")
        execute(node)

    invoke.__annotations__ = {"node": node_type, "return": type(None)}
    setattr(
        invoke,
        "__signature__",
        CallableSignature(
            [
                Parameter(
                    "node",
                    Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=node_type,
                )
            ],
            return_annotation=type(None),
        ),
    )
    return NodeHandler(identity, owner, phase, node_type, invoke, source)


NO_NODE_HANDLER = -1


@private
@typechecked
def no_node_handler(node: astx.AST) -> int:
    """
    title: Select phase rejection without retaining a compiler callback.
    parameters:
      node:
        type: astx.AST
    returns:
      type: int
    """
    return NO_NODE_HANDLER


no_node_handler.__annotations__ = {"node": astx.AST, "return": int}


@private
@typechecked
def node_slot(
    node_type: type[astx.AST], index: int
) -> Callable[[astx.AST], int]:
    """
    title: Create immutable nominal selection metadata, never bound execution.
    parameters:
      node_type:
        type: type[astx.AST]
      index:
        type: int
    returns:
      type: Callable[[astx.AST], int]
    """

    def select(node: astx.AST) -> int:
        """
        title: Return the slot selected by Plum's nominal resolver.
        parameters:
          node:
            type: astx.AST
        returns:
          type: int
        """
        return index

    select.__annotations__ = {"node": node_type, "return": int}
    setattr(
        select,
        "__signature__",
        CallableSignature(
            [
                Parameter(
                    "node",
                    Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=node_type,
                )
            ],
            return_annotation=int,
        ),
    )
    return select


@private
@typechecked
@dataclass(frozen=True, init=False)
class NominalNodeSelector:
    """
    title: Sealed stateless Plum selection metadata for one signature shape.
    summary: >-
      Register once before publication. Public Plum resolution may update its
      own metadata cache, but never receives nodes, callbacks or compiler
      state. Identical compiler shapes share this metadata to avoid retaining a
      Function per compilation in Plum's process-global instance list.
    attributes:
      function:
        type: Function
      slots:
        type: Mapping[Callable[[astx.AST], int], int]
    """

    function: Function
    slots: Mapping[Callable[[astx.AST], int], int]

    def __init__(self, node_types: tuple[type[astx.AST], ...]) -> None:
        """
        title: Register the complete nominal shape before publishing it.
        parameters:
          node_types:
            type: tuple[type[astx.AST], Ellipsis]
        """
        function = Function(no_node_handler)
        function.register(no_node_handler, Signature(astx.AST))
        slots: dict[Callable[[astx.AST], int], int] = {
            no_node_handler: NO_NODE_HANDLER
        }
        for index, node_type in enumerate(node_types):
            slot = node_slot(node_type, index)
            function.register(slot, Signature(node_type))
            slots[slot] = index
        object.__setattr__(self, "function", function)
        object.__setattr__(self, "slots", MappingProxyType(slots))

    def resolve(self, node_type: type[astx.AST]) -> int:
        """
        title: Let Plum resolve specificity and return its immutable slot.
        parameters:
          node_type:
            type: type[astx.AST]
        returns:
          type: int
        """
        implementation, _ = self.function.resolve_method(Signature(node_type))
        return self.slots[implementation]


NODE_SELECTORS: dict[tuple[type[astx.AST], ...], NominalNodeSelector] = {}


@private
@typechecked
def node_selector(
    node_types: tuple[type[astx.AST], ...],
) -> NominalNodeSelector:
    """
    title: Reuse only complete immutable nominal selection metadata.
    parameters:
      node_types:
        type: tuple[type[astx.AST], Ellipsis]
    returns:
      type: NominalNodeSelector
    """
    selector = NODE_SELECTORS.get(node_types)
    if selector is None:
        selector = NominalNodeSelector(node_types)
        NODE_SELECTORS[node_types] = selector
    return selector


@public
@typechecked
class ScopedNodeDispatch:
    """
    title: Fresh bindings and cache backed by stateless Plum selectors.
    summary: >-
      Duplicate identities and exact nominal signatures fail at construction.
      Subclasses use Plum specificity. Future multiple-inheritance ambiguities
      fail explicitly during resolution; a second subtype resolver is not used.
      Reentrant traversal is supported; simultaneous use of one mutable
      compiler remains unsupported.
    attributes:
      phase:
        type: Phase
      handlers:
        type: tuple[NodeHandler, Ellipsis]
      selector:
        type: NominalNodeSelector
      fallback:
        type: Callable[[astx.AST], None]
      cache:
        type: dict[type[astx.AST], int]
    """

    phase: Phase
    handlers: tuple[NodeHandler, ...]
    selector: NominalNodeSelector
    fallback: Callable[[astx.AST], None]
    cache: dict[type[astx.AST], int]

    def __init__(
        self,
        phase: Phase,
        handlers: tuple[NodeHandler, ...],
        fallback: Callable[[astx.AST], None],
    ) -> None:
        """
        title: Validate explicit bindings and create isolated dispatch state.
        parameters:
          phase:
            type: Phase
          handlers:
            type: tuple[NodeHandler, Ellipsis]
          fallback:
            type: Callable[[astx.AST], None]
        """
        identities: set[str] = set()
        signatures: set[type[astx.AST]] = set()
        for handler in handlers:
            if handler.phase != phase:
                raise configuration_error(
                    f"{handler.owner}/{handler.identity}: "
                    f"wrong phase {handler.phase}"
                )
            if (
                handler.identity in identities
                or handler.node_type in signatures
            ):
                raise configuration_error(
                    f"duplicate {phase} node handler: "
                    f"{handler.owner}/{handler.identity} ({handler.source})"
                )
            identities.add(handler.identity)
            signatures.add(handler.node_type)
        self.phase = phase
        self.handlers = handlers

        self.fallback = fallback
        self.selector = node_selector(tuple(h.node_type for h in handlers))
        self.cache = {}

    def resolve(self, node_type: type[astx.AST]) -> int:
        """
        title: Cache Plum's selection locally without another subtype resolver.
        parameters:
          node_type:
            type: type[astx.AST]
        returns:
          type: int
        """
        cached = self.cache.get(node_type)
        if cached is not None:
            return cached
        try:
            selected = self.selector.resolve(node_type)
        except AmbiguousLookupError as exc:
            raise configuration_error(
                f"ambiguous {self.phase} node dispatch: {exc}"
            ) from exc
        self.cache[node_type] = selected
        return selected

    def visit(self, node: astx.AST) -> None:
        """
        title: Dispatch one node without sharing another compiler's cache.
        parameters:
          node:
            type: astx.AST
        """
        selected = self.resolve(type(node))
        if selected == NO_NODE_HANDLER:
            self.fallback(node)
            return
        self.handlers[selected].implementation(node)

    def explain(self, node_type: type[astx.AST]) -> NodeHandler | None:
        """
        title: >-
          Explain one concrete selection without running its implementation.
        summary: None means that the phase's rejection fallback was selected.
        parameters:
          node_type:
            type: type[astx.AST]
        returns:
          type: NodeHandler | None
        """
        if not isinstance(node_type, type):
            raise configuration_error(
                "node explanation requires a nominal class"
            )
        selected = self.resolve(node_type)
        return None if selected == NO_NODE_HANDLER else self.handlers[selected]
