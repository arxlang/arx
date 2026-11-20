"""
title: Helpers for the bundled AIX lexer syntax manifest.
"""

from __future__ import annotations

import json

from dataclasses import dataclass
from importlib import resources
from typing import Any


@dataclass(frozen=True)
class SyntaxManifest:
    """
    title: Loaded syntax manifest facade.
    attributes:
      data: Data to process.
      line_comment_delimiters: Line comment delimiters.
      reserved_operators: Reserved operators.
      types: Types.
    """

    data: dict[str, Any]

    @property
    def line_comment_delimiters(self) -> tuple[str, ...]:
        """
        title: Return configured line comment delimiters.
        returns: Configured line comment delimiters.
        """
        comments = self.data.get("comments", {})
        line = comments.get("line", "⍝")
        if isinstance(line, str):
            return (line,)
        return tuple(line)

    @property
    def reserved_operators(self) -> set[str]:
        """
        title: Return reserved AIX operator symbols.
        returns: Reserved AIX operator symbols.
        """
        return set(self.data.get("reserved_operators", []))

    @property
    def types(self) -> set[str]:
        """
        title: Return primitive type spellings.
        returns: Primitive type spellings.
        """
        return set(self.data.get("types", []))


def load_syntax_manifest() -> SyntaxManifest:
    """
    title: Load the lexer syntax manifest bundled with AIX.
    returns: Loaded the lexer syntax manifest bundled with AIX.
    """
    manifest = resources.files("aix.lexer").joinpath("syntax.json")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return SyntaxManifest(data)
