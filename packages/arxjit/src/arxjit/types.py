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
class SigType:
    """
    title: A type usable in an arxjit signature.
    summary: >-
      Scalar today (e.g. ``i64``); the name is kept element-vs-array neutral so
      array forms such as ``i64[2, 2]`` can be added later via subscripting
      without renaming the public type.
    attributes:
      name:
        type: str
        description: The arxjit-facing name, e.g. ``i64``.
      astx_name:
        type: str
        description: The astx class this type lowers to, e.g. ``Int64``.
    """

    name: str
    astx_name: str

    def __call__(self, *arg_types: SigType) -> Signature:
        """
        title: Build a Signature using this type as the return type.
        parameters:
          arg_types:
            type: SigType
            description: The positional argument types, in order.
            variadic: positional
        returns:
          type: Signature
        """
        return Signature(return_type=self, arg_types=arg_types)

    def __str__(self) -> str:
        """
        title: Return the arxjit name of the type.
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
        type: SigType
        description: The type returned by the compiled function.
      arg_types:
        type: tuple[SigType, Ellipsis]
        description: The positional argument types, in order.
    """

    return_type: SigType
    arg_types: tuple[SigType, ...]

    def __str__(self) -> str:
        """
        title: Render the signature as ``ret(arg, arg)``.
        returns:
          type: str
        """
        args = ", ".join(str(arg) for arg in self.arg_types)
        return f"{self.return_type}({args})"


i32 = SigType("i32", "Int32")
i64 = SigType("i64", "Int64")
f32 = SigType("f32", "Float32")
f64 = SigType("f64", "Float64")
# Exported as ``bool_`` to avoid shadowing the ``bool`` builtin, but the
# user-facing type name (used in signature rendering) stays ``bool``.
bool_ = SigType("bool", "Boolean")
