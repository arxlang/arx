"""
title: Shared parser state declarations.
summary: >-
  Define parser prefix records and modifier constants shared across the
  concern-grouped parser modules.
"""

from __future__ import annotations

import copy

from dataclasses import dataclass

from astx import SourceLocation
from irx import astx

INDENT_SIZE = 2


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


@dataclass(frozen=True)
class SyntheticForInBinding:
    """
    title: Synthetic for-in element binding.
    summary: >-
      Represent one parser-only loop variable that should read through a hidden
      index into one iterable expression instead of allocating standalone
      storage.
    attributes:
      iterable:
        type: astx.Expr
      index_name:
        type: str
    """

    iterable: astx.Expr
    index_name: str

    def element_expr(self, loc: SourceLocation) -> astx.ListIndex:
        """
        title: Build one element access expression for the current index.
        parameters:
          loc:
            type: SourceLocation
        returns:
          type: astx.ListIndex
        """
        return astx.ListIndex(
            copy.deepcopy(self.iterable),
            astx.Identifier(self.index_name, loc=loc),
        )

    def length_expr(self) -> astx.ListLength:
        """
        title: Build one list-length expression for the iterable.
        returns:
          type: astx.ListLength
        """
        return astx.ListLength(copy.deepcopy(self.iterable))


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
    "SyntheticForInBinding",
]
