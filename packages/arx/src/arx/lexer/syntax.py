"""
title: Access the canonical lexical syntax manifest.
"""

from __future__ import annotations

import json

from dataclasses import dataclass
from importlib import resources
from typing import Any


@dataclass(frozen=True)
class SyntaxManifest:
    """
    title: Access the canonical lexical syntax manifest.
    attributes:
      data: Data to process.
      word_operators: Word operators.
      reserved_keywords: Reserved keywords.
      contextual_keywords: Contextual keywords.
      literal_keywords: Literal keywords.
      line_comment_delimiters: Line comment delimiters.
      operator_symbols: Operator symbols.
      multi_char_operators: Multi char operators.
    """

    data: dict[str, Any]

    @property
    def word_operators(self) -> set[str]:
        """
        title: Return word operators recognized before ordinary identifiers.
        returns: Word operators recognized before ordinary identifiers.
        """
        return set(self.data.get("operators", {}).get("word_operators", []))

    @property
    def reserved_keywords(self) -> set[str]:
        """
        title: Return the set of reserved keywords from the manifest.
        returns: The set of reserved keywords from the manifest.
        """
        return set(self.data.get("keywords", {}).get("reserved", []))

    @property
    def contextual_keywords(self) -> set[str]:
        """
        title: Return the set of contextual keywords from the manifest.
        returns: The set of contextual keywords from the manifest.
        """
        return set(self.data.get("keywords", {}).get("contextual", []))

    @property
    def literal_keywords(self) -> dict[str, Any]:
        """
        title: Return literal keywords mapped to their token values.
        returns: Mapping from literal keyword name to its Python value.
        """
        literals = self.data.get("literals", {})
        keywords = literals.get("keywords", [])
        booleans = literals.get("booleans", {})
        none_value = literals.get("none", {}).get("token_value", None)
        result: dict[str, Any] = {}
        for name in keywords:
            if name in booleans:
                result[name] = booleans[name]
            elif name == "none":
                result[name] = none_value
        return result

    @property
    def line_comment_delimiters(self) -> tuple[str, ...]:
        """
        title: Return the tuple of line comment delimiters.
        returns: The tuple of line comment delimiters.
        """
        comment = self.data.get("comment", {})
        line = comment.get("line", {})
        return tuple(line.get("delimiters", ["#"]))

    @property
    def operator_symbols(self) -> set[str]:
        """
        title: Return the set of operator symbols declared in the manifest.
        returns: The set of operator symbols declared in the manifest.
        """
        operators = self.data.get("operators", {})
        return set(operators.get("symbols", []))

    @property
    def multi_char_operators(self) -> set[str]:
        """
        title: Return the set of multi-character operators recognized by
          the lexer.
        returns: The set of multi-character operators recognized by the lexer.
        """
        return set(self.data["operators"]["multi_char"])


def load_syntax_manifest() -> SyntaxManifest:
    """
    title: Load the lexer syntax manifest bundled with the package.
    returns: Loaded the lexer syntax manifest bundled with the package.
    """
    manifest = resources.files("arx.lexer").joinpath("syntax.json")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return SyntaxManifest(data)
