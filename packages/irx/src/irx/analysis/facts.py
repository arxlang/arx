"""
title: Typed, immutable semantic attachments owned by an analysis generation.
summary: >-
  Keys pair a nominal record type with its provider owner. A record type cannot
  be claimed by two owners in one store. Updates return a new store;
  replacement is explicit. Records validate their full payload and expose
  dependency edges. Analysis entry points invalidate old records before
  traversal. External snapshots retain their records deliberately; compiler
  state retains no old generation through this store. deepcopy follows normal
  AST memoization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, TypeVar, cast

import astx

from public import private, public

from irx.diagnostics import (
    Diagnostic,
    DiagnosticCodes,
    IRxDiagnosticError,
    LoweringError,
)
from irx.typecheck import TypeCheckError, typechecked

RecordT = TypeVar("RecordT", bound="SemanticFact")


@public
@typechecked
class SemanticFact:
    """
    title: >-
      Nominal extension contract for checked, traversable semantic records.
    """

    def validate(self) -> None:
        """
        title: >-
          Validate all fields and collection members at the store boundary.
        """
        raise NotImplementedError("semantic facts must validate their payload")

    def dependencies(self) -> tuple[object, ...]:
        """
        title: >-
          Expose all declaration and expression dependencies to reachability.
        returns:
          type: tuple[object, Ellipsis]
        """
        raise NotImplementedError("semantic facts must expose dependencies")

    def invalidate(self, node: astx.AST) -> None:
        """
        title: >-
          Clear any companion facts owned by this record before reanalysis.
        parameters:
          node:
            type: astx.AST
        """


@public
@typechecked
@dataclass(frozen=True)
class FactKey(Generic[RecordT]):
    """
    title: Provider-owned nominal key with an invariant static record type.
    attributes:
      owner:
        type: str
      record_type:
        type: type[RecordT]
    """

    owner: str
    record_type: type[RecordT]

    def __post_init__(self) -> None:
        """
        title: Validate key ownership and the nominal record contract.
        """
        validate_key(self.owner, self.record_type)


@private
@typechecked
def validate_key(owner: str, record_type: type[SemanticFact]) -> None:
    """
    title: Reject empty owners and non-record key types.
    parameters:
      owner:
        type: str
      record_type:
        type: type[SemanticFact]
    """
    if not owner:
        raise ValueError("a semantic fact key requires a provider owner")


@private
@typechecked
@dataclass(frozen=True)
class FactEntry:
    """
    title: Checked heterogeneous storage, not a public lookup interface.
    attributes:
      owner:
        type: str
      record_type:
        type: type[SemanticFact]
      value:
        type: SemanticFact
    """

    owner: str
    record_type: type[SemanticFact]
    value: SemanticFact

    def __post_init__(self) -> None:
        """
        title: Validate generated dataclass arguments before storage.
        """
        validate_entry(self.owner, self.record_type, self.value)


@private
@typechecked
def validate_entry(
    owner: str, record_type: type[SemanticFact], value: SemanticFact
) -> None:
    """
    title: Validate nominal agreement and recursively checked record fields.
    parameters:
      owner:
        type: str
      record_type:
        type: type[SemanticFact]
      value:
        type: SemanticFact
    """
    validate_key(owner, record_type)
    if not isinstance(value, record_type):
        raise TypeError(f"{owner}: expected {record_type.__name__}")
    value.validate()


@public
@typechecked
@dataclass(frozen=True)
class SemanticFacts:
    """
    title: >-
      Persistent typed attachments; optional lookup never hides corruption.
    attributes:
      entries:
        type: tuple[FactEntry, Ellipsis]
    """

    entries: tuple[FactEntry, ...] = ()

    def __post_init__(self) -> None:
        """
        title: Validate all entries including stores reconstructed by callers.
        """
        validate_entries(self.entries)

    def with_fact(
        self, key: FactKey[RecordT], value: RecordT, *, replace: bool = False
    ) -> SemanticFacts:
        """
        title: >-
          Return a checked update, rejecting accidental record replacement.
        parameters:
          key:
            type: FactKey[RecordT]
          value:
            type: RecordT
          replace:
            type: bool
        returns:
          type: SemanticFacts
        """
        previous = self.get(key)
        if previous is not None and not replace:
            raise ValueError(f"duplicate semantic fact: {key.owner}")
        entry = FactEntry(key.owner, key.record_type, value)
        return SemanticFacts(
            (
                *(
                    e
                    for e in self.entries
                    if e.record_type is not key.record_type
                ),
                entry,
            )
        )

    def get(self, key: FactKey[RecordT]) -> RecordT | None:
        """
        title: >-
          Return the requested record type or None, checking owner identity.
        parameters:
          key:
            type: FactKey[RecordT]
        returns:
          type: RecordT | None
        """
        for entry in self.entries:
            if entry.record_type is not key.record_type:
                continue
            if entry.owner != key.owner:
                raise ValueError(
                    f"semantic fact ownership collision: {key.owner}"
                )
            validate_entry(entry.owner, entry.record_type, entry.value)
            # The only heterogeneous-storage cast, after nominal validation.
            return cast(RecordT, entry.value)
        return None

    def require(
        self,
        key: FactKey[RecordT],
        *,
        node: astx.AST | None = None,
        phase: Literal["analysis", "lowering"] = "lowering",
    ) -> RecordT:
        """
        title: >-
          Diagnose missing or corrupted required facts at a phase boundary.
        parameters:
          key:
            type: FactKey[RecordT]
          node:
            type: astx.AST | None
          phase:
            type: Literal[analysis, lowering]
        returns:
          type: RecordT
        """
        error_type = (
            LoweringError if phase == "lowering" else IRxDiagnosticError
        )
        code = (
            DiagnosticCodes.LOWERING_MISSING_SEMANTIC_METADATA
            if phase == "lowering"
            else DiagnosticCodes.SEMANTIC_MISSING_METADATA
        )
        try:
            value = self.get(key)
        except (TypeError, ValueError, TypeCheckError) as exc:
            raise error_type(
                Diagnostic(
                    message=f"invalid semantic fact {key.owner}: {exc}",
                    phase=phase,
                    code=code,
                    node=node,
                    cause=exc,
                )
            ) from exc
        if value is None:
            raise error_type(
                Diagnostic(
                    message=(
                        f"missing semantic fact "
                        f"{key.owner}/{key.record_type.__name__}"
                    ),
                    phase=phase,
                    code=code,
                    node=node,
                )
            )
        return value

    def dependencies(self) -> tuple[object, ...]:
        """
        title: Expose record-owned edges without exposing storage internals.
        returns:
          type: tuple[object, Ellipsis]
        """
        return tuple(
            edge
            for entry in self.entries
            for edge in entry.value.dependencies()
        )

    def invalidate(self, node: astx.AST) -> None:
        """
        title: Clear companion metadata before the owner drops this generation.
        parameters:
          node:
            type: astx.AST
        """
        for entry in self.entries:
            entry.value.invalidate(node)


@private
@typechecked
def validate_entries(entries: tuple[FactEntry, ...]) -> None:
    """
    title: Check every nested record and reject duplicate nominal keys.
    parameters:
      entries:
        type: tuple[FactEntry, Ellipsis]
    """
    seen: set[type[SemanticFact]] = set()
    for entry in entries:
        validate_entry(entry.owner, entry.record_type, entry.value)
        if entry.record_type in seen:
            raise ValueError("duplicate nominal semantic fact key")
        seen.add(entry.record_type)
