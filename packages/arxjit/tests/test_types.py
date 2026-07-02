"""
title: Tests for the arxjit scalar type and signature API.
"""

import dataclasses

import arxjit
import astx
import pytest

from arxjit.types import ScalarType, Signature, bool_, f32, f64, i32, i64


def test_call_builds_signature() -> None:
    """
    title: Calling a return type with arg types builds a Signature.
    """
    sig = i64(i64, i64)
    assert isinstance(sig, Signature)
    assert sig.return_type is i64
    assert sig.arg_types == (i64, i64)


def test_zero_argument_signature() -> None:
    """
    title: A return type called with no args yields an empty arg list.
    """
    sig = i64()
    assert sig.return_type is i64
    assert sig.arg_types == ()


def test_scalar_str() -> None:
    """
    title: A scalar type stringifies to its arxjit name.
    """
    assert str(i64) == "i64"
    assert str(f64) == "f64"
    assert str(bool_) == "bool"


def test_signature_str() -> None:
    """
    title: A signature renders as ``ret(arg, arg)``.
    """
    assert str(i64(i64, i64)) == "i64(i64, i64)"
    assert str(f64(i32)) == "f64(i32)"
    assert str(i64()) == "i64()"


def test_scalar_types_map_to_real_astx_classes() -> None:
    """
    title: Each scalar's astx_name resolves to a real astx class.
    """
    for scalar in (i32, i64, f32, f64, bool_):
        astx_cls = getattr(astx, scalar.astx_name)
        assert isinstance(astx_cls, type)


def test_scalar_type_equality_by_value() -> None:
    """
    title: ScalarType compares equal by value (frozen dataclass).
    """
    assert i64 == ScalarType("i64", "Int64")
    assert i64 != i32


def test_signature_equality_and_hashability() -> None:
    """
    title: Equal signatures compare equal and share a hash (cache keys).
    """
    assert i64(i64, i64) == i64(i64, i64)
    assert i64(i64, i64) != i64(i64)
    assert i64(i64) != f64(i64)
    assert hash(i64(i64, i64)) == hash(i64(i64, i64))
    assert len({i64(i64), i64(i64), f64(i64)}) == 2


def test_scalar_type_is_immutable() -> None:
    """
    title: ScalarType instances cannot be mutated.
    """
    with pytest.raises(dataclasses.FrozenInstanceError):
        i64.name = "changed"  # type: ignore[misc]


def test_types_are_exported_from_package() -> None:
    """
    title: The scalar types and Signature are exported from arxjit.
    """
    assert arxjit.i64 is i64
    assert arxjit.Signature is Signature
    for name in ("i32", "i64", "f32", "f64", "bool_", "ScalarType"):
        assert name in arxjit.__all__
