"""
title: Shared parser state declarations.
summary: >-
  Define parser prefix records and modifier constants shared across the
  concern-grouped parser modules.
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
    summary: >-
      Describe where a parsed type annotation appears so surface types can
      decide whether runtime-layout forms are allowed.
    """

    GENERAL = "general"
    PARAMETER = "function parameter"
    RETURN = "function return"
    VARIABLE = "variable"
    INLINE_VARIABLE = "inline variable"
    FIELD = "field"
    EXPRESSION = "expression"
    TEMPLATE_BOUND = "template bound"
    TEMPLATE_ARGUMENT = "template argument"
    NESTED = "nested type"

    @property
    def allows_runtime_layout(self) -> bool:
        """
        title: Return whether runtime-layout collection forms are allowed.
        returns:
          type: bool
        """
        return self is TypeUseContext.PARAMETER


@dataclass(frozen=True)
class ParsedAnnotation:
    """
    title: Parsed modifier annotation attached to the next declaration.
    attributes:
      modifiers:
        type: tuple[str, Ellipsis]
      loc:
        type: SourceLocation
    """

    modifiers: tuple[str, ...]
    loc: SourceLocation


@dataclass
class ParsedDeclarationPrefixes:
    """
    title: Parsed declaration prefixes attached to one declaration.
    attributes:
      modifiers:
        type: ParsedAnnotation | None
      template_params:
        type: tuple[astx.TemplateParam, Ellipsis]
      loc:
        type: SourceLocation | None
      description:
        type: str
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
        "constant",
        "mutable",
        "abstract",
        "extern",
    }
)

VISIBILITY_MODIFIERS = frozenset({"public", "private", "protected"})
FIELD_MUTABILITY_MODIFIERS = frozenset({"constant", "mutable"})

CLASS_ALLOWED_MODIFIERS = frozenset(
    {"public", "private", "protected", "abstract"}
)
FIELD_ALLOWED_MODIFIERS = frozenset(
    {"public", "private", "protected", "static", "constant", "mutable"}
)
METHOD_ALLOWED_MODIFIERS = frozenset(
    {"public", "private", "protected", "static", "abstract", "extern"}
)

VISIBILITY_NAME_MAP = {
    "public": astx.VisibilityKind.public,
    "private": astx.VisibilityKind.private,
    "protected": astx.VisibilityKind.protected,
}
MUTABILITY_NAME_MAP = {
    "constant": astx.MutabilityKind.constant,
    "mutable": astx.MutabilityKind.mutable,
}

__all__ = [
    "CLASS_ALLOWED_MODIFIERS",
    "FIELD_ALLOWED_MODIFIERS",
    "FIELD_MUTABILITY_MODIFIERS",
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
