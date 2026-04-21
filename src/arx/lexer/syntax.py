from __future__ import annotations

import json

from dataclasses import dataclass
from importlib import resources
from typing import Any


@dataclass(frozen=True)
class SyntaxManifest:
    data: dict[str, Any]

    @property
    def reserved_keywords(self) -> set[str]:
        """
        title: Return the set of reserved keywords from the manifest.
        returns:
          type: set[str]
        """
        return set(self.data.get("keywords", {}).get("reserved", []))

    @property
    def contextual_keywords(self) -> set[str]:
        """
        title: Return the set of contextual keywords from the manifest.
        returns:
          type: set[str]
        """
        return set(self.data.get("keywords", {}).get("contextual", []))

    @property
    def literal_keywords(self) -> dict[str, Any]:
        """
        title: Return literal keywords mapped to their token values.
        returns:
          type: dict[str, Any]
          description: Mapping from literal keyword name to its Python value.
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
        returns:
          type: tuple[str, Ellipsis]
        """
        comment = self.data.get("comment", {})
        line = comment.get("line", {})
        return tuple(line.get("delimiters", ["#"]))

    @property
    def operator_symbols(self) -> set[str]:
        """
        title: Return the set of operator symbols declared in the manifest.
        returns:
          type: set[str]
        """
        operators = self.data.get("operators", {})
        return set(operators.get("symbols", []))

    @property
    def multi_char_operators(self) -> set[str]:
        """
        title: >-
          Return the set of multi-character operators recognized by the lexer.
        returns:
          type: set[str]
        """
        # Manifest is behind implementation today,
        # so keep compatibility defaults.
        defaults = {"==", "!=", ">=", "<=", "->", "&&", "||", "++", "--"}
        operators = self.data.get("operators", {})
        notes = operators.get("notes", [])
        _ = notes  # kept only as a reminder that the manifest still has TODOs
        return defaults


def load_syntax_manifest() -> SyntaxManifest:
    """
    title: Load the lexer syntax manifest bundled with the package.
    returns:
      type: SyntaxManifest
    """
    manifest = resources.files("arx.lexer").joinpath("syntax.json")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return SyntaxManifest(data)
