"""
title: Source extraction for @jit-decorated Python functions.
summary: >-
  First stage of the arxjit pipeline: retrieve the source of a decorated
  function, normalize its indentation, drop the decorator lines, and parse the
  remaining function definition with Python's built-in ast module. A retrieved
  source that is not a single function definition raises SourceExtractionError
  carrying structured diagnostics; validating the parsed body against the
  supported Python subset is a later stage and is not done here.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

from dataclasses import dataclass
from typing import Any, Callable, cast

from arxjit.diagnostics import Diagnostic, DiagnosticSeverity
from arxjit.errors import SourceExtractionError

PyFunc = Callable[..., Any]


def _filename_of(fn: PyFunc) -> str:
    """
    title: Return the filename a function was defined in.
    summary: >-
      Reads the function's code object; falls back to "<unknown>" for objects
      without one (for example C builtins).
    parameters:
      fn:
        type: PyFunc
    returns:
      type: str
    """
    code = getattr(fn, "__code__", None)
    filename = getattr(code, "co_filename", None)
    return filename or "<unknown>"


def _name_of(fn: PyFunc) -> str:
    """
    title: Return a human-readable name for a function.
    parameters:
      fn:
        type: PyFunc
    returns:
      type: str
    """
    return cast(str, getattr(fn, "__qualname__", repr(fn)))


def _error(
    message: str,
    filename: str,
    line: int | None = None,
    column: int | None = None,
) -> Diagnostic:
    """
    title: Build an ERROR-severity diagnostic.
    parameters:
      message:
        type: str
      filename:
        type: str
      line:
        type: int | None
      column:
        type: int | None
    returns:
      type: Diagnostic
    """
    return Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        message=message,
        filename=filename,
        line=line,
        column=column,
    )


@dataclass(frozen=True)
class ExtractedSource:
    """
    title: The extracted, normalized source of a decorated function.
    attributes:
      filename:
        type: str
        description: The file defining the function, or "<unknown>".
      source:
        type: str
        description: >-
          Dedented source of the function definition with the decorator lines
          removed; its first line is the def statement.
      lineno:
        type: int
        description: One-based line of the def statement in ``filename``.
      node:
        type: ast.FunctionDef | ast.AsyncFunctionDef
        description: >-
          The parsed function definition. Line numbers are shifted to match
          ``filename``, so they can be reported in diagnostics directly. Column
          offsets are left as raw ast ``col_offset`` values (zero-based UTF-8
          byte offsets) and must be converted at the boundary that produces a
          diagnostic.
    """

    filename: str
    source: str
    lineno: int
    node: ast.FunctionDef | ast.AsyncFunctionDef


def extract_source(fn: PyFunc) -> ExtractedSource:
    """
    title: Extract and parse the source of a decorated function.
    summary: >-
      Retrieves the source block with inspect.getsourcelines, normalizes
      indentation with textwrap.dedent so nested functions and methods parse as
      top-level code, removes the decorator lines, and parses the function
      definition with ast.parse. The returned node keeps real file line
      numbers; async definitions are extracted here and left for the validation
      stage to accept or reject.
    parameters:
      fn:
        type: PyFunc
        description: The undecorated Python function to extract.
    returns:
      type: ExtractedSource
    raises:
      SourceExtractionError: >-
        If the retrieved source is not a single function definition (for
        example a lambda).
    """
    filename = _filename_of(fn)
    block_lines, block_start = inspect.getsourcelines(fn)
    block = textwrap.dedent("".join(block_lines))
    module = ast.parse(block, filename=filename)

    if len(module.body) != 1 or not isinstance(
        module.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)
    ):
        message = (
            f"source of {_name_of(fn)!r} is not a single function"
            " definition (lambdas are not supported)"
        )
        raise SourceExtractionError(
            message,
            diagnostics=[_error(message, filename, block_start)],
        )

    located = module.body[0]
    def_lineno = block_start + located.lineno - 1
    lines = block.splitlines(keepends=True)
    source = "".join(lines[located.lineno - 1 :])

    stripped = ast.parse(source, filename=filename)
    ast.increment_lineno(stripped, def_lineno - 1)
    # `source` starts at the def line, so the sole statement is the
    # function definition itself.
    node = cast("ast.FunctionDef | ast.AsyncFunctionDef", stripped.body[0])
    return ExtractedSource(
        filename=filename,
        source=source,
        lineno=def_lineno,
        node=node,
    )


__all__ = [
    "ExtractedSource",
    "extract_source",
]
