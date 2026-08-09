"""
title: Tests for signature reconciliation.
"""

import ast
import importlib.util
import pathlib

from typing import Any, Callable, cast

import pytest

from arxjit.diagnostics import Diagnostic, DiagnosticSeverity
from arxjit.reconcile import _ANNOTATION_TYPES, resolve_signature
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


def test_explicit_signature_arity_must_match_the_function() -> None:
    """
    title: An explicit signature cannot declare a different argument count.
    summary: >-
      The explicit signature decides types, which is the caller's choice, but
      how many parameters the function has is a fact of the definition. A
      signature that disagrees would compile to a calling convention Python
      cannot satisfy.
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

    signature, (diagnostic,) = _resolve(sample, i64(i64))
    assert signature is None
    assert diagnostic.message == (
        "signature declares 1 argument but 'sample' takes 2"
    )
    assert diagnostic.severity is DiagnosticSeverity.ERROR


def test_arity_message_pluralizes_the_declared_count() -> None:
    """
    title: The mismatch message agrees in number with the declared count.
    summary: >-
      The singular case is covered above; this pins the other side, which line
      coverage cannot distinguish because both sit on one conditional
      expression.
    """

    def sample(x: int) -> int:
        """
        title: Return the argument unchanged.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        return x

    signature, (diagnostic,) = _resolve(sample, i64(i64, i64))
    assert signature is None
    assert diagnostic.message == (
        "signature declares 2 arguments but 'sample' takes 1"
    )


def test_explicit_signature_with_matching_arity_is_accepted() -> None:
    """
    title: A correctly sized explicit signature still short-circuits.
    summary: >-
      The arity check must not disturb the rule that an explicit signature
      wins: the annotations here say float and are still not consulted.
    """

    def sample(x: float) -> float:
        """
        title: Return the argument unchanged.
        parameters:
          x:
            type: float
        returns:
          type: float
        """
        return x

    explicit = i64(i64)
    signature, diagnostics = _resolve(sample, explicit)
    assert signature is explicit
    assert diagnostics == []


def test_explicit_signature_does_not_bypass_the_shape_check() -> None:
    """
    title: A non-positional shape is rejected even with an explicit signature.
    summary: >-
      The structural checks run before the explicit signature is accepted, so
      passing one cannot skip them. Only the shape is reported: counting the
      positional parameters of a *args function would give a number that means
      nothing to the caller.
    """
    source = "def sample(*args: int) -> int:\n    return 1\n"
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    extracted = ExtractedSource(
        filename="<test>", source=source, lineno=1, node=node
    )
    signature, (diagnostic,) = resolve_signature(extracted, i64(i64))
    assert signature is None
    assert "only positional parameters are supported" in diagnostic.message


def test_zero_argument_explicit_signature_matches_a_bare_function() -> None:
    """
    title: An empty explicit signature fits a function with no parameters.
    """

    def sample() -> int:
        """
        title: Return a constant.
        returns:
          type: int
        """
        return 1

    explicit = i64()
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


_REBOUND_THEN_RESTORED = """import builtins

int = str


def kernel(x: int) -> int:
    return x


int = builtins.int
"""

_REBOUND_AFTER_DEF = """def kernel(x: int) -> int:
    return x


int = str
"""


def _module_function(tmp_path: pathlib.Path, name: str, source: str) -> PyFunc:
    """
    title: Import a written-out module and return its kernel (test helper).
    summary: >-
      A real module is needed rather than a hand-built ExtractedSource: the
      point of these cases is what the module's live globals do after the
      function is defined, which only a real import reproduces.
    parameters:
      tmp_path:
        type: pathlib.Path
      name:
        type: str
      source:
        type: str
    returns:
      type: PyFunc
    """
    path = tmp_path / f"{name}.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(PyFunc, module.kernel)


@pytest.mark.parametrize("name", ["int", "float", "bool"])
def test_reserved_spelling_wins_over_the_defining_namespace(
    name: str,
) -> None:
    """
    title: A rebound builtin name still denotes the reserved scalar type.
    summary: >-
      int, float and bool are reserved annotation spellings, so a module that
      rebinds one does not change what the annotation means to the compiler.
      The namespace is deliberately not consulted; see _annotation_type for why
      resolving through it cannot be made sound.
    parameters:
      name:
        type: str
    """
    source = f"def sample(value: {name}) -> {name}:\n    return value\n"
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    extracted = ExtractedSource(
        filename="<test>",
        source=source,
        lineno=1,
        node=node,
        globalns={name: str},
    )
    signature, diagnostics = resolve_signature(extracted)
    assert diagnostics == []
    assert (
        str(signature)
        == f"{_ANNOTATION_TYPES[name]}({_ANNOTATION_TYPES[name]})"
    )


def test_rebinding_restored_after_definition_still_resolves(
    tmp_path: pathlib.Path,
) -> None:
    """
    title: A name rebound at definition and restored after resolves the same.
    summary: >-
      One of the two directions live globals get wrong: __annotations__ records
      str, because that was the binding when the def ran, but the module now
      says int is the builtin. A namespace-based check would answer from the
      restored binding and derive a signature the annotation never meant. The
      reserved spelling answers the same either way.
    parameters:
      tmp_path:
        type: pathlib.Path
    """
    kernel = _module_function(
        tmp_path, "rebound_restored", _REBOUND_THEN_RESTORED
    )
    # What __annotations__ reports is itself version-dependent, which is the
    # point: up to 3.13 it holds the object captured when the def ran, while
    # 3.14 defers evaluation (PEP 649) and resolves on first access against
    # the module as it is by then. The resolver must not vary with either.
    assert kernel.__annotations__["x"] in (int, str)
    signature, diagnostics = _resolve(kernel)
    assert diagnostics == []
    assert signature == i64(i64)


def test_rebinding_after_definition_still_resolves(
    tmp_path: pathlib.Path,
) -> None:
    """
    title: A name rebound only after the def resolves the same.
    summary: >-
      The other direction: the annotation genuinely denoted the builtin when
      the function was defined, and a namespace-based check would reject it
      because the module was rebound afterwards. Nothing about the function
      changed, so nothing about its signature does.
    parameters:
      tmp_path:
        type: pathlib.Path
    """
    kernel = _module_function(tmp_path, "rebound_after", _REBOUND_AFTER_DEF)
    # What __annotations__ reports is itself version-dependent, which is the
    # point: up to 3.13 it holds the object captured when the def ran, while
    # 3.14 defers evaluation (PEP 649) and resolves on first access against
    # the module as it is by then. The resolver must not vary with either.
    assert kernel.__annotations__["x"] in (int, str)
    signature, diagnostics = _resolve(kernel)
    assert diagnostics == []
    assert signature == i64(i64)


def test_enclosing_scope_rebinding_still_resolves() -> None:
    """
    title: A name rebound by an enclosing function resolves the same.
    summary: >-
      The annotation here denotes str, as __annotations__ confirms, and under
      the reserved-spelling contract that does not matter: the spelling is what
      selects the type. This was previously pinned as a limitation of the
      namespace check; it is now an instance of the rule.
    """

    def outer() -> PyFunc:
        """
        title: Return a function annotated against a rebound builtin.
        returns:
          type: PyFunc
        """
        int = str

        def kernel(x: int) -> int:
            """
            title: Return the argument unchanged.
            parameters:
              x:
                type: int
            returns:
              type: int
            """
            return x

        return kernel

    kernel = outer()
    assert kernel.__annotations__ == {"x": str, "return": str}
    signature, diagnostics = _resolve(kernel)
    assert diagnostics == []
    assert signature == i64(i64)


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
