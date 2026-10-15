"""
title: Fail-closed signatures for primitive arrays and unique builders.
"""

from __future__ import annotations

import astx
import pytest

from irx.analysis.array_queries import resolve_query
from typeguard import TypeCheckError


def test_query_signature_rejects_empty_arguments() -> None:
    """
    title: Direct signature resolution reports invalid arity before indexing.
    """
    with pytest.raises(ValueError, match="argument count"):
        resolve_query(astx.ArrayOperation.LENGTH, ())


def test_query_signature_checks_collection_members() -> None:
    """
    title: Runtime validation checks collection items at the semantic API.
    """
    with pytest.raises(TypeCheckError):
        resolve_query(astx.ArrayOperation.LENGTH, (1,))  # type: ignore[arg-type]


def test_builder_and_chunk_contracts_do_not_alias() -> None:
    """
    title: Reject nullable append and cross-container equality mismatches.
    """
    logical = astx.LogicalType(astx.LogicalKind.INT32)
    with pytest.raises(ValueError, match="incompatible"):
        resolve_query(
            astx.ArrayOperation.APPEND,
            (
                astx.ArrayBuilderType(logical),
                astx.NoneType(),
            ),
        )
    with pytest.raises(ValueError, match="matching element"):
        resolve_query(
            astx.ArrayOperation.EQUAL,
            (
                astx.ArrayType(logical),
                astx.ChunkedArrayType(logical),
            ),
        )
