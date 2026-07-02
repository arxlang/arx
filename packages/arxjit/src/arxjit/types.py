"""
title: Scalar type and signature API for arxjit.
summary: >-
  Defines the built-in scalar types (``i64``, ``f64`` ...) that users reference
  in ``@jit`` signatures, and the ``Signature`` produced by calling a return
  type with argument types, e.g. ``i64(i64, i64)``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScalarType:
    """
    title: A built-in scalar type usable in arxjit signatures.
    attributes:
      name:
        type: str
        description: The arxjit-facing name, e.g. ``i64``.
      astx_name:
        type: str
        description: The astx class this scalar lowers to, e.g. ``Int64``.
    """

    name: str
    astx_name: str

    def __call__(self, *arg_types: ScalarType) -> Signature:
        """
        title: Build a Signature using this type as the return type.
        parameters:
          arg_types:
            type: ScalarType
            description: The positional argument types, in order.
            variadic: positional
        returns:
          type: Signature
        """
        return Signature(return_type=self, arg_types=arg_types)

    def __str__(self) -> str:
        """
        title: Return the arxjit name of the scalar type.
        returns:
          type: str
        """
        return self.name


@dataclass(frozen=True)
class Signature:
    """
    title: A compiled-function signature (return type and argument types).
    attributes:
      return_type:
        type: ScalarType
        description: The type returned by the compiled function.
      arg_types:
        type: tuple[ScalarType, Ellipsis]
        description: The positional argument types, in order.
    """

    return_type: ScalarType
    arg_types: tuple[ScalarType, ...]

    def __str__(self) -> str:
        """
        title: Render the signature as ``ret(arg, arg)``.
        returns:
          type: str
        """
        args = ", ".join(str(arg) for arg in self.arg_types)
        return f"{self.return_type}({args})"


i32 = ScalarType("i32", "Int32")
i64 = ScalarType("i64", "Int64")
f32 = ScalarType("f32", "Float32")
f64 = ScalarType("f64", "Float64")
# Exported as ``bool_`` to avoid shadowing the ``bool`` builtin, but the
# user-facing type name (used in signature rendering) stays ``bool``.
bool_ = ScalarType("bool", "Boolean")
