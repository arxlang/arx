"""
title: Source-location helpers shared by the arxjit pipeline stages.
summary: >-
  Every stage that reports a problem against a parsed function has to turn an
  ast node back into a Diagnostic pointing at the user's real source. Both the
  conversion from ast's zero-based UTF-8 byte columns to the one-based Unicode
  character columns Diagnostic documents, and the mapping from a node's file
  line back into the extracted source text, live here so the validation and
  signature stages cannot drift apart on the column contract.
"""

from __future__ import annotations

import ast

from arxjit.diagnostics import Diagnostic, DiagnosticSeverity
from arxjit.source import ExtractedSource


def char_column(line: str, byte_offset: int) -> int:
    """
    title: Convert a zero-based UTF-8 byte offset to a one-based column.
    summary: >-
      ast column offsets are zero-based UTF-8 byte offsets into their source
      line, but Diagnostic.column is documented as a one-based Unicode
      character column. Decoding the byte prefix back to text and measuring its
      length performs the conversion exactly, including when multi-byte
      characters appear before the target column.
    parameters:
      line:
        type: str
        description: The real source line the offset was reported against.
      byte_offset:
        type: int
    returns:
      type: int
    """
    prefix = line.encode("utf-8")[:byte_offset]
    return len(prefix.decode("utf-8", errors="replace")) + 1


def diagnostic(
    extracted: ExtractedSource,
    node: ast.AST,
    message: str,
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR,
) -> Diagnostic:
    """
    title: Build a diagnostic located at an ast node.
    summary: >-
      Reads the node's lineno/col_offset when present and converts the column
      to the one-based character contract via char_column; falls back to no
      location when the node carries none. node.lineno is a real file line
      number (extract_source already shifted it), while extracted.source is
      indexed from its own first line, so the node's line is looked up at
      splitlines()[lineno - extracted.lineno] rather than lineno - 1.
    parameters:
      extracted:
        type: ExtractedSource
      node:
        type: ast.AST
      message:
        type: str
      severity:
        type: DiagnosticSeverity
        description: Defaults to ERROR, the severity of a rejection.
    returns:
      type: Diagnostic
    """
    lineno = getattr(node, "lineno", None)
    col_offset = getattr(node, "col_offset", None)
    column = None
    if lineno is not None and col_offset is not None:
        lines = extracted.source.splitlines()
        index = lineno - extracted.lineno
        if 0 <= index < len(lines):
            column = char_column(lines[index], col_offset)
    return Diagnostic(
        severity=severity,
        message=message,
        filename=extracted.filename,
        line=lineno,
        column=column,
    )


__all__ = [
    "char_column",
    "diagnostic",
]
