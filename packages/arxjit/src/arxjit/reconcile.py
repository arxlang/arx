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
import builtins

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


def _arity_mismatch(
    extracted: ExtractedSource,
    explicit: Signature,
) -> list[Diagnostic]:
    """
    title: Reject an explicit signature that describes a different function.
    summary: >-
      An explicit signature overrides which *types* the compiler uses, because
      that is a choice the caller is entitled to make. How many parameters the
      function has is not a choice: it is a fact of the definition, readable
      without consulting a single annotation. A signature that disagrees would
      compile to a calling convention Python cannot satisfy, so it is rejected
      rather than trusted.
    parameters:
      extracted:
        type: ExtractedSource
      explicit:
        type: Signature
    returns:
      type: list[Diagnostic]
    """
    declared = len(explicit.arg_types)
    actual = len(_parameters(extracted.node.args))
    if declared == actual:
        return []
    plural = "" if declared == 1 else "s"
    return [
        diagnostic(
            extracted,
            extracted.node,
            f"signature declares {declared} argument{plural} but"
            f" {extracted.node.name!r} takes {actual}",
        )
    ]


def _structural_diagnostics(
    extracted: ExtractedSource,
    explicit: Signature | None,
) -> list[Diagnostic]:
    """
    title: Check the facts about a function that no signature may override.
    summary: >-
      Runs before the explicit signature is accepted, so both paths are held to
      the same structural rules. An explicit signature decides types only; the
      argument shape and the number of parameters are read from the definition
      and are not the caller's to restate differently. An unsupported shape
      stops the check there: counting the positional parameters of a function
      that also takes *args would report a count no caller could act on.
    parameters:
      extracted:
        type: ExtractedSource
      explicit:
        type: Signature | None
    returns:
      type: list[Diagnostic]
    """
    shape = _unsupported_shape(extracted, extracted.node.args)
    if shape:
        return shape
    if explicit is None:
        return []
    return _arity_mismatch(extracted, explicit)


def _annotation_shadow(
    extracted: ExtractedSource,
    name: str,
) -> str | None:
    """
    title: Return what shadows a builtin annotation name, or None.
    summary: |-
      An annotation is matched by spelling, so ``int`` must still resolve to
      builtins.int for that match to mean anything; rebinding the name makes
      the annotation denote something else entirely. Only the defining module's
      namespace is consulted. A function's own locals cannot apply, because
      annotations are evaluated in the enclosing scope when the def executes.
      When the namespace is unavailable (only for a hand-built ExtractedSource;
      extract_source always provides it for a real function) shadowing cannot
      be observed and the name is taken to be the builtin, matching how
      validation treats a shadowed range.
      Rebinding by an enclosing *function* is a documented limitation: such a
      function derives a signature from the builtin its annotation is spelled
      after, with no diagnostic, even though the annotation denotes the rebound
      value. Nothing extraction carries can reveal it, because the binding is
      not a module global and freevars records only the names the body reads,
      which an annotation is not. Reading __annotations__ instead would not
      settle it: under "from __future__ import annotations" they hold strings,
      and inspect.get_annotations(eval_str=True) evaluates those against
      __globals__, which cannot see an enclosing scope, so it answers with the
      builtin on every supported CPython.
    parameters:
      extracted:
        type: ExtractedSource
      name:
        type: str
    returns:
      type: str | None
    """
    namespace = extracted.globalns
    if namespace is None:
        return None
    # Every key of _ANNOTATION_TYPES names a builtin, and this is only
    # reached for a name already found there, so the lookup cannot fail. A
    # default would be worse than an error: with one, a name absent from
    # builtins would compare unequal to itself and report every module that
    # merely defines it as shadowing.
    builtin = getattr(builtins, name)
    if namespace.get(name, builtin) is not builtin:
        return "a module-level name"
    return None


def _resolve_annotation(
    extracted: ExtractedSource,
    annotation: ast.expr | None,
) -> tuple[SigType | None, str | None]:
    """
    title: Resolve an annotation to a scalar type, or say why it cannot be.
    summary: >-
      Returns the type and no reason, or no type and the reason to report. An
      annotation has to clear two hurdles: it must be a bare name this package
      maps, and that name must still refer to the builtin it is spelled after.
      Only a bare name is accepted, which is what int, float and bool parse to;
      anything else (a subscript such as list[int], an attribute such as
      np.float64, or a string) is refused against its own location.
    parameters:
      extracted:
        type: ExtractedSource
      annotation:
        type: ast.expr | None
    returns:
      type: tuple[SigType | None, str | None]
    """
    if not isinstance(annotation, ast.Name):
        return None, _SUPPORTED
    sig_type = _ANNOTATION_TYPES.get(annotation.id)
    if sig_type is None:
        return None, _SUPPORTED
    shadow = _annotation_shadow(extracted, annotation.id)
    if shadow is not None:
        return None, (
            f"{annotation.id!r} is bound to {shadow} here, so it does not"
            " refer to the builtin"
        )
    return sig_type, None


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
        arg_type, reason = _resolve_annotation(extracted, parameter.annotation)
        if arg_type is None:
            diagnostics.append(
                diagnostic(
                    extracted,
                    parameter.annotation,
                    f"unsupported type annotation for parameter"
                    f" {parameter.arg!r}: {reason}",
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
    return_type, reason = _resolve_annotation(extracted, node.returns)
    if return_type is None:
        return None, [
            diagnostic(
                extracted,
                node.returns,
                f"unsupported return type annotation: {reason}",
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
      An explicit signature decides the argument and return *types* outright
      and the annotations are not even read, so a function may annotate freely
      (or not at all) without having to agree with it; there is deliberately no
      type-mismatch error. It does not override the structure of the
      definition: the argument shape and the number of parameters are checked
      against the function first, on both paths, because those are facts rather
      than choices. Without an explicit signature, the annotations are used;
      see _annotation_shadow for the one rebinding of a builtin annotation name
      that this cannot detect. The returned signature is None exactly when the
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
    structural = _structural_diagnostics(extracted, explicit)
    if structural:
        return None, structural
    if explicit is not None:
        return explicit, []
    return _from_annotations(extracted)


__all__ = ["resolve_signature"]
