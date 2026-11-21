"""
title: Shared parser state declarations.
summary: Define parser prefix records and modifier constants shared
  across the concern-grouped parser modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import astx

from astx import SourceLocation

INDENT_SIZE = 2


class TypeUseContext(Enum):
    """
    title: Type annotation use context.
    summary: Describe where a parsed type annotation appears so surface types
      can decide whether runtime-layout forms are allowed.
    attributes:
      allows_runtime_layout: Whether to use allows runtime layout.
    """

    GENERAL = "general"
    PARAMETER = "function parameter"
    RETURN = "function return"
    VARIABLE = "variable"
    INLINE_VARIABLE = "inline variable"
    FIELD = "field"
    EXPRESSION = "expression"
    TYPE_ALIAS = "type alias"
    TEMPLATE_BOUND = "template bound"
    TEMPLATE_ARGUMENT = "template argument"
    NESTED = "nested type"

    @property
    def allows_runtime_layout(self) -> bool:
        """
        title: Return whether runtime-layout collection forms are allowed.
        returns: Whether runtime-layout collection forms are allowed.
        """
        return self is TypeUseContext.PARAMETER


@dataclass(frozen=True)
class ParsedAnnotation:
    """
    title: Parsed declaration modifiers with their source location.
    summary: Shared payload for an annotation prefix and an inline declaration
      modifier group; this record does not distinguish their surface spelling.
    attributes:
      modifiers: Modifiers.
      loc: Source coordinates attached to this node.
    """

    modifiers: tuple[str, ...]
    loc: SourceLocation


@dataclass
class ParsedDeclarationPrefixes:
    """
    title: Parsed declaration prefixes attached to one declaration.
    attributes:
      modifiers: Modifiers.
      template_params: Template parameters declared by the callable.
      loc: Source coordinates attached to this node.
      description: Description.
    """

    modifiers: ParsedAnnotation | None = None
    template_params: tuple[astx.TemplateParam, ...] = ()
    loc: SourceLocation | None = None
    description: str = "declaration prefix"


SUPPORTED_MODIFIERS = frozenset(
    {
        "public",
        "private",
        "protected",
        "static",
        "const",
        "var",
        "abstract",
        "extern",
    }
)

VISIBILITY_MODIFIERS = frozenset({"public", "private", "protected"})
BINDING_MUTABILITY_MODIFIERS = frozenset({"const", "var"})

CLASS_ALLOWED_MODIFIERS = frozenset(
    {"public", "private", "protected", "abstract"}
)
FIELD_ALLOWED_MODIFIERS = frozenset(
    {"public", "private", "protected", "static", "const", "var"}
)
FUNCTION_ALLOWED_MODIFIERS = frozenset({"public", "private"})
METHOD_ALLOWED_MODIFIERS = frozenset(
    {"public", "private", "protected", "static", "abstract", "extern"}
)

VISIBILITY_NAME_MAP = {
    "public": astx.VisibilityKind.public,
    "private": astx.VisibilityKind.private,
    "protected": astx.VisibilityKind.protected,
}
MUTABILITY_NAME_MAP = {
    "const": astx.MutabilityKind.constant,
    "var": astx.MutabilityKind.mutable,
}

__all__ = [
    "BINDING_MUTABILITY_MODIFIERS",
    "CLASS_ALLOWED_MODIFIERS",
    "FIELD_ALLOWED_MODIFIERS",
    "FUNCTION_ALLOWED_MODIFIERS",
    "INDENT_SIZE",
    "METHOD_ALLOWED_MODIFIERS",
    "MUTABILITY_NAME_MAP",
    "SUPPORTED_MODIFIERS",
    "VISIBILITY_MODIFIERS",
    "VISIBILITY_NAME_MAP",
    "ParsedAnnotation",
    "ParsedDeclarationPrefixes",
    "TypeUseContext",
]
