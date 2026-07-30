"""
title: Tests for signature reconciliation.
"""

import ast

from typing import Any, Callable

import pytest

from arxjit.diagnostics import Diagnostic, DiagnosticSeverity
from arxjit.reconcile import resolve_signature
from arxjit.source import ExtractedSource, extract_source
from arxjit.types import Signature, bool_, f64, i64

PyFunc = Callable[..., Any]


def _resolve(
    fn: PyFunc,
    explicit: Signature | None = None,
) -> tuple[Signature | None, list[Diagnostic]]:
    """
    title: Extract a function and resolve its signature (test helper).
    parameters:
      fn:
        type: PyFunc
      explicit:
        type: Signature | None
    returns:
      type: tuple[Signature | None, list[Diagnostic]]
    """
    return resolve_signature(extract_source(fn), explicit)


def test_annotations_map_to_scalar_types() -> None:
    """
    title: int, float and bool annotations map to i64, f64 and bool_.
    """

    def sample(a: int, b: float, c: bool) -> float:
        """
        title: Combine three scalars.
        parameters:
          a:
            type: int
          b:
            type: float
          c:
            type: bool
        returns:
          type: float
        """
        if c:
            return a + b
        return b

    signature, diagnostics = _resolve(sample)
    assert diagnostics == []
    assert signature == f64(i64, f64, bool_)


def test_explicit_signature_short_circuits() -> None:
    """
    title: An explicit signature is returned as-is with no diagnostics.
    summary: >-
      The annotations are not read at all, so even a function that could not
      produce a signature on its own resolves cleanly.
    """

    def sample(a, b):  # type: ignore[no-untyped-def]
        """
        title: Add two values of unknown type.
        parameters:
          a:
            description: The left operand, deliberately unannotated.
          b:
            description: The right operand, deliberately unannotated.
        returns:
          type: object
        """
        return a + b

    explicit = i64(i64, i64)
    signature, diagnostics = _resolve(sample, explicit)
    assert signature is explicit
    assert diagnostics == []


def test_positional_only_parameters_are_included() -> None:
    """
    title: Positional-only parameters appear in the derived signature.
    summary: >-
      Validation permits them, so reconciliation must not silently drop them
      from the argument list.
    """

    def sample(a: int, /, b: float) -> float:
        """
        title: Add a positional-only and an ordinary parameter.
        parameters:
          a:
            type: int
          b:
            type: float
        returns:
          type: float
        """
        return a + b

    signature, diagnostics = _resolve(sample)
    assert diagnostics == []
    assert signature == f64(i64, f64)


@pytest.mark.parametrize(
    "source",
    [
        "def sample(*args: int) -> int:\n    return 1\n",
        "def sample(**kwargs: int) -> int:\n    return 1\n",
        "def sample(*, a: int) -> int:\n    return a\n",
        "def sample(a: int, *rest: int) -> int:\n    return a\n",
    ],
    ids=["vararg", "kwarg", "kwonly", "positional-and-vararg"],
)
def test_non_positional_shape_cannot_derive_a_signature(source: str) -> None:
    """
    title: An argument shape a positional signature cannot express is refused.
    summary: >-
      Validation rejects these shapes first, so this is unreachable through
      @jit, but resolve_signature is public: without the check it would leave
      the parameters out and return a signature that is quietly wrong, such as
      i64() for a function taking *args.
    parameters:
      source:
        type: str
    """
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    extracted = ExtractedSource(
        filename="<test>", source=source, lineno=1, node=node
    )
    signature, (diagnostic,) = resolve_signature(extracted)
    assert signature is None
    assert "only positional parameters are supported" in diagnostic.message
    assert diagnostic.severity is DiagnosticSeverity.ERROR


def test_zero_parameter_function_resolves() -> None:
    """
    title: A function with no parameters resolves from its return annotation.
    """

    def sample() -> int:
        """
        title: Return a constant.
        returns:
          type: int
        """
        return 1

    signature, diagnostics = _resolve(sample)
    assert diagnostics == []
    assert signature == i64()


def test_no_annotations_warns_once() -> None:
    """
    title: A wholly unannotated function yields a single WARNING.
    """

    def sample(a, b):  # type: ignore[no-untyped-def]
        """
        title: Add two values of unknown type.
        parameters:
          a:
            description: The left operand, deliberately unannotated.
          b:
            description: The right operand, deliberately unannotated.
        returns:
          type: object
        """
        return a + b

    signature, (diagnostic,) = _resolve(sample)
    assert signature is None
    assert diagnostic.severity is DiagnosticSeverity.WARNING
    assert "stays interpreted" in diagnostic.message


def test_missing_return_annotation_is_an_error() -> None:
    """
    title: Annotated parameters with no return annotation is an error.
    """

    def sample(a: int):  # type: ignore[no-untyped-def]
        """
        title: Return the argument unchanged.
        parameters:
          a:
            type: int
        returns:
          type: int
        """
        return a

    signature, (diagnostic,) = _resolve(sample)
    assert signature is None
    assert diagnostic.severity is DiagnosticSeverity.ERROR
    assert "has no return type annotation" in diagnostic.message


def test_unsupported_return_annotation_is_an_error() -> None:
    """
    title: A return annotation outside the supported scalars is rejected.
    """

    def sample(a: int) -> str:
        """
        title: Render the argument.
        parameters:
          a:
            type: int
        returns:
          type: str
        """
        return "x"

    signature, (diagnostic,) = _resolve(sample)
    assert signature is None
    assert "unsupported return type annotation" in diagnostic.message


def test_subscripted_annotation_is_rejected() -> None:
    """
    title: A subscripted annotation such as list[int] is not a scalar.
    """

    def sample(values: list[int]) -> int:
        """
        title: Return a constant, ignoring the argument.
        parameters:
          values:
            type: list[int]
        returns:
          type: int
        """
        return 1

    signature, (diagnostic,) = _resolve(sample)
    assert signature is None
    assert "unsupported type annotation for parameter 'values'" in (
        diagnostic.message
    )


def test_dotted_annotation_is_rejected() -> None:
    """
    title: A dotted annotation such as decimal.Decimal is not a scalar.
    """

    def sample(value: ast.AST) -> int:
        """
        title: Return a constant, ignoring the argument.
        parameters:
          value:
            type: ast.AST
        returns:
          type: int
        """
        return 1

    signature, (diagnostic,) = _resolve(sample)
    assert signature is None
    assert "unsupported type annotation for parameter 'value'" in (
        diagnostic.message
    )


def test_every_bad_parameter_is_reported() -> None:
    """
    title: Reconciliation collects all bad parameters, not just the first.
    """

    def sample(a: str, b, c: int) -> int:  # type: ignore[no-untyped-def]
        """
        title: Combine three values.
        parameters:
          a:
            type: str
          b:
            description: The middle operand, deliberately unannotated.
          c:
            type: int
        returns:
          type: int
        """
        return c

    signature, diagnostics = _resolve(sample)
    assert signature is None
    messages = [d.message for d in diagnostics]
    assert len(messages) == 2
    assert "parameter 'a'" in messages[0]
    assert "parameter 'b'" in messages[1]


def test_diagnostic_points_at_the_annotation() -> None:
    """
    title: An unsupported annotation is located at the annotation itself.
    """

    def sample(value: str) -> int:
        """
        title: Return a constant, ignoring the argument.
        parameters:
          value:
            type: str
        returns:
          type: int
        """
        return 1

    extracted = extract_source(sample)
    _, (diagnostic,) = resolve_signature(extracted)
    lines = extracted.source.splitlines()
    real_line = lines[diagnostic.line - extracted.lineno]
    assert diagnostic.column is not None
    assert real_line[diagnostic.column - 1 :].startswith("str")


def test_string_annotations_are_read_from_the_ast() -> None:
    """
    title: A quoted annotation resolves like an ordinary one.
    summary: >-
      "from __future__ import annotations" turns every annotation into a string
      at runtime; reading them from the ast instead of __annotations__ makes
      that irrelevant. A quoted annotation is the same situation written out by
      hand, and parses to a Constant rather than a Name, so it is reported
      rather than silently accepted.
    """
    source = 'def sample(x: "int") -> int:\n    return x\n'
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    extracted = ExtractedSource(
        filename="<test>", source=source, lineno=1, node=node
    )
    signature, (diagnostic,) = resolve_signature(extracted)
    assert signature is None
    assert "unsupported type annotation for parameter 'x'" in (
        diagnostic.message
    )
