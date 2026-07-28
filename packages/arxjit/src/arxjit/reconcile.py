"""
title: Signature reconciliation for arxjit.
summary: >-
  Third stage of the arxjit pipeline: decide which Signature a validated
  function will be compiled against. An explicit signature= passed to @jit is
  the source of truth and wins outright; otherwise the signature is derived
  from the function's Python annotations; a function with neither is reported
  and stays interpreted. Annotations are read from the ast rather than from
  __annotations__ so that a module using "from __future__ import annotations"
  behaves identically, and so every diagnostic can point at the exact
  annotation that caused it.
"""

from __future__ import annotations

import ast

from arxjit.diagnostics import Diagnostic, DiagnosticSeverity
from arxjit.locations import diagnostic
from arxjit.source import ExtractedSource
from arxjit.types import Signature, SigType, bool_, f64, i64

# Only the Python builtins with an unambiguous scalar meaning are mapped.
# Note that this can never produce i32/f32: Python has no annotation that
# distinguishes widths, so the narrow types stay explicit-signature only.
_ANNOTATION_TYPES: dict[str, SigType] = {
    "bool": bool_,
    "float": f64,
    "int": i64,
}

_SUPPORTED = "only int, float and bool are supported"


def _parameters(args: ast.arguments) -> list[ast.arg]:
    """
    title: Return the positional parameters of a function.
    summary: >-
      Positional-only parameters are included because validation permits them:
      they are ordinary positional arguments to a compiled function. Anything
      that is not positional is reported by _unsupported_shape rather than
      being silently left out of the signature.
    parameters:
      args:
        type: ast.arguments
    returns:
      type: list[ast.arg]
    """
    return [*args.posonlyargs, *args.args]


def _unsupported_shape(
    extracted: ExtractedSource,
    args: ast.arguments,
) -> list[Diagnostic]:
    """
    title: Reject an argument shape a positional signature cannot express.
    summary: >-
      A Signature is a fixed list of positional argument types, so a variadic
      or keyword-only parameter has nowhere to go. Validation already rejects
      these shapes, which makes this unreachable through @jit, but
      resolve_signature is public: without the check it would drop the
      parameters and return a signature that is quietly wrong (i64() for a
      function taking *args) rather than saying it cannot derive one.
    parameters:
      extracted:
        type: ExtractedSource
      args:
        type: ast.arguments
    returns:
      type: list[Diagnostic]
    """
    offender = next(
        (
            node
            for node in (args.vararg, args.kwarg, *args.kwonlyargs)
            if node is not None
        ),
        None,
    )
    if offender is None:
        return []
    return [
        diagnostic(
            extracted,
            offender,
            "cannot derive a signature: only positional parameters are"
            " supported, not variadic or keyword-only ones",
        )
    ]


def _annotation_type(annotation: ast.expr | None) -> SigType | None:
    """
    title: Map an annotation expression to a supported scalar type.
    summary: >-
      Only a bare name is accepted, which is what int, float and bool parse to.
      Anything else (a subscript such as list[int], an attribute such as
      np.float64, a string, or an alias bound to a supported builtin) yields
      None, so the caller reports it against the annotation's own location.
    parameters:
      annotation:
        type: ast.expr | None
    returns:
      type: SigType | None
    """
    if not isinstance(annotation, ast.Name):
        return None
    return _ANNOTATION_TYPES.get(annotation.id)


def _argument_types(
    extracted: ExtractedSource,
    parameters: list[ast.arg],
) -> tuple[list[SigType], list[Diagnostic]]:
    """
    title: Resolve every parameter annotation to a scalar type.
    summary: >-
      Collects one diagnostic per unusable parameter rather than stopping at
      the first, matching how validation reports the whole function at once. A
      missing annotation is reported against the parameter and an unsupported
      one against the annotation itself, so the caret lands on what to change.
    parameters:
      extracted:
        type: ExtractedSource
      parameters:
        type: list[ast.arg]
    returns:
      type: tuple[list[SigType], list[Diagnostic]]
    """
    arg_types: list[SigType] = []
    diagnostics: list[Diagnostic] = []
    for parameter in parameters:
        if parameter.annotation is None:
            diagnostics.append(
                diagnostic(
                    extracted,
                    parameter,
                    f"parameter {parameter.arg!r} has no type annotation",
                )
            )
            continue
        arg_type = _annotation_type(parameter.annotation)
        if arg_type is None:
            diagnostics.append(
                diagnostic(
                    extracted,
                    parameter.annotation,
                    f"unsupported type annotation for parameter"
                    f" {parameter.arg!r}: {_SUPPORTED}",
                )
            )
            continue
        arg_types.append(arg_type)
    return arg_types, diagnostics


def _return_type(
    extracted: ExtractedSource,
) -> tuple[SigType | None, list[Diagnostic]]:
    """
    title: Resolve the return annotation to a scalar type.
    parameters:
      extracted:
        type: ExtractedSource
    returns:
      type: tuple[SigType | None, list[Diagnostic]]
    """
    node = extracted.node
    if node.returns is None:
        return None, [
            diagnostic(
                extracted,
                node,
                f"{node.name!r} has no return type annotation",
            )
        ]
    return_type = _annotation_type(node.returns)
    if return_type is None:
        return None, [
            diagnostic(
                extracted,
                node.returns,
                f"unsupported return type annotation: {_SUPPORTED}",
            )
        ]
    return return_type, []


def _from_annotations(
    extracted: ExtractedSource,
) -> tuple[Signature | None, list[Diagnostic]]:
    """
    title: Derive a Signature from a function's Python annotations.
    summary: >-
      An argument shape a positional signature cannot express is reported on
      its own, because the annotation analysis below would be meaningless for
      it. A function with no annotations at all is not an error: nothing was
      requested, so it is reported at WARNING severity and stays interpreted.
      Once any annotation is present the function is treated as asking to be
      compiled, so every remaining gap is an ERROR.
    parameters:
      extracted:
        type: ExtractedSource
    returns:
      type: tuple[Signature | None, list[Diagnostic]]
    """
    node = extracted.node
    shape = _unsupported_shape(extracted, node.args)
    if shape:
        return None, shape

    parameters = _parameters(node.args)
    annotated = any(p.annotation is not None for p in parameters)
    if not annotated and node.returns is None:
        return None, [
            diagnostic(
                extracted,
                node,
                f"{node.name!r} stays interpreted: no signature= was given"
                " and it has no type annotations",
                DiagnosticSeverity.WARNING,
            )
        ]

    arg_types, diagnostics = _argument_types(extracted, parameters)
    return_type, return_diagnostics = _return_type(extracted)
    diagnostics.extend(return_diagnostics)
    if return_type is None or diagnostics:
        return None, diagnostics
    return Signature(return_type=return_type, arg_types=tuple(arg_types)), []


def resolve_signature(
    extracted: ExtractedSource,
    explicit: Signature | None = None,
) -> tuple[Signature | None, list[Diagnostic]]:
    """
    title: Decide the Signature a validated function compiles against.
    summary: >-
      An explicit signature wins outright and the annotations are not even
      read, so a function may annotate freely (or not at all) without having to
      agree with it; there is deliberately no mismatch error. Without one, the
      annotations are used. The returned signature is None exactly when the
      returned diagnostics are non-empty, which is the caller's signal that the
      function cannot be compiled.
    parameters:
      extracted:
        type: ExtractedSource
        description: A function that has already passed validation.
      explicit:
        type: Signature | None
        description: The signature= passed to @jit, when given.
    returns:
      type: tuple[Signature | None, list[Diagnostic]]
    """
    if explicit is not None:
        return explicit, []
    return _from_annotations(extracted)


__all__ = ["resolve_signature"]
