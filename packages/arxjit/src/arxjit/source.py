"""
title: Source extraction for @jit-decorated Python functions.
summary: >-
  First stage of the arxjit pipeline: retrieve the source of a decorated
  function, parse it with Python's built-in ast module, and drop the
  decorators. The source text is never modified: an indented definition (a
  nested function or a method) is parsed inside a synthetic "if True:" wrapper
  instead of being dedented, which preserves string literal content and keeps
  every node's line and column pointing into the real file. Every failure
  raises SourceExtractionError carrying structured diagnostics; validating the
  parsed body against the supported Python subset is a later stage and is not
  done here.
"""

from __future__ import annotations

import ast
import inspect
import tokenize

from dataclasses import dataclass
from typing import Any, Callable, cast

from arxjit.diagnostics import Diagnostic, DiagnosticSeverity
from arxjit.errors import SourceExtractionError

PyFunc = Callable[..., Any]

_WRAPPER = "if True:\n"
_WRAPPER_LINES = 1


def _filename_of(fn: PyFunc) -> str:
    """
    title: Return the filename a function was defined in.
    summary: >-
      Follows __wrapped__ chains first, because inspect.getsourcelines does the
      same and the filename must match the source it returns; a JitFunction
      wrapper is therefore attributed to the file of the function it wraps.
      Reads the unwrapped function's code object; falls back to "<unknown>" for
      objects without one (for example C builtins).
    parameters:
      fn:
        type: PyFunc
    returns:
      type: str
    """
    try:
        fn = inspect.unwrap(fn)
    except ValueError:
        # A __wrapped__ cycle: attribute the wrapper itself and let the
        # source retrieval report the cycle.
        pass
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


def _retrieval_reason(exc: Exception) -> str:
    """
    title: Return a clean, location-free message for a retrieval failure.
    summary: >-
      inspect.getsourcelines can fail with exception types whose str() embeds a
      location: a tokenize.TokenError carries a (message, position) tuple, and
      a SyntaxError appends its own line number. No reliable file location
      exists at retrieval time (it fails before the block's start line is
      known), so only the human-readable message is used, never an embedded
      position.
    parameters:
      exc:
        type: Exception
    returns:
      type: str
    """
    if isinstance(exc, tokenize.TokenError):
        return str(exc.args[0]) if exc.args else str(exc)
    if isinstance(exc, SyntaxError):
        return exc.msg or str(exc)
    return str(exc)


def _column_of(exc: SyntaxError, text: str) -> int | None:
    """
    title: Return the validated one-based column of a syntax error.
    summary: >-
      SyntaxError.offset is a one-based character column, but it does not
      always point into the parsed source: for malformed f-string replacement
      fields, Python 3.10 and 3.11 report an offset into a synthetic string
      built from the replacement expression. The offset is therefore only
      trusted when the error's reported text matches the parsed line it claims
      to come from; otherwise, and when there is no usable offset at all, None
      is returned.
    parameters:
      exc:
        type: SyntaxError
      text:
        type: str
        description: The exact text that was passed to ast.parse.
    returns:
      type: int | None
    """
    if not exc.offset or exc.lineno is None or exc.text is None:
        return None
    lines = text.splitlines()
    if not 1 <= exc.lineno <= len(lines):
        return None
    if exc.text.rstrip("\r\n") != lines[exc.lineno - 1]:
        return None
    return exc.offset


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


def _parse_block(
    fn: PyFunc,
    text: str,
    filename: str,
    line_delta: int,
) -> ast.Module:
    """
    title: Parse source text, translating parse failures.
    summary: >-
      Wraps ast.parse so that every parse failure becomes a
      SourceExtractionError with a located diagnostic. SyntaxError locations
      are shifted by line_delta to point at the real file line; the column is
      only kept when _column_of can validate it. Python 3.10 raises ValueError
      instead of SyntaxError for source containing a null byte, which carries
      no location attributes at all.
    parameters:
      fn:
        type: PyFunc
        description: The function being extracted, used for the message.
      text:
        type: str
        description: The exact text to parse.
      filename:
        type: str
      line_delta:
        type: int
        description: Shift from text line numbers to real file lines.
    returns:
      type: ast.Module
    """
    try:
        return ast.parse(text, filename=filename)
    except SyntaxError as exc:
        message = f"cannot parse source of {_name_of(fn)!r}: {exc.msg}"
        line = None
        if exc.lineno is not None:
            line = exc.lineno + line_delta
        # The text is parsed with its original indentation, so a trusted
        # offset points into the real file line; _column_of rejects
        # offsets that do not (for example synthetic f-string locations).
        column = _column_of(exc, text)
        raise SourceExtractionError(
            message,
            diagnostics=[_error(message, filename, line, column)],
        ) from exc
    except ValueError as exc:
        message = f"cannot parse source of {_name_of(fn)!r}: {exc}"
        raise SourceExtractionError(
            message,
            diagnostics=[_error(message, filename)],
        ) from exc


@dataclass(frozen=True)
class ExtractedSource:
    """
    title: The extracted source of a decorated function.
    attributes:
      filename:
        type: str
        description: The file defining the function, or "<unknown>".
      source:
        type: str
        description: >-
          Verbatim file text of the function definition with the decorator
          lines removed; the first line is the def statement, and the original
          indentation is preserved so string literals are untouched.
      lineno:
        type: int
        description: One-based line of the def statement in ``filename``.
      node:
        type: ast.FunctionDef | ast.AsyncFunctionDef
        description: >-
          The parsed function definition with an empty decorator list. Line
          numbers match ``filename``, so they can be reported in diagnostics
          directly. Column offsets are raw ast ``col_offset`` values (zero-
          based UTF-8 byte offsets) that point into the real file line, because
          the source is parsed without modifying its indentation; only the
          byte-to-character conversion is needed at the boundary that produces
          a diagnostic.
    """

    filename: str
    source: str
    lineno: int
    node: ast.FunctionDef | ast.AsyncFunctionDef


def extract_source(fn: PyFunc) -> ExtractedSource:
    """
    title: Extract and parse the source of a decorated function.
    summary: >-
      Retrieves the source block with inspect.getsourcelines (which follows
      __wrapped__, so a JitFunction resolves to the function it wraps) and
      parses it with ast.parse. An indented block is parsed inside a synthetic
      "if True:" wrapper rather than dedented, so the text is never modified
      and every node keeps real file lines and columns. The decorators are
      dropped from the returned node and source; async definitions are
      extracted here and left for the validation stage to accept or reject.
    parameters:
      fn:
        type: PyFunc
        description: The Python function to extract.
    returns:
      type: ExtractedSource
    raises:
      SourceExtractionError: >-
        If the source cannot be retrieved (REPL- or exec-defined functions, C
        builtins, self-referential wrappers, or a corrupted or since-modified
        source file), cannot be parsed (including source containing null
        bytes), or is not a single function definition (for example a lambda).
    """
    filename = _filename_of(fn)
    try:
        block_lines, block_start = inspect.getsourcelines(fn)
    except (
        OSError,
        TypeError,
        ValueError,
        SyntaxError,
        tokenize.TokenError,
    ) as exc:
        # inspect.getsourcelines tokenizes the file, so a corrupted or
        # since-modified source (for example an unterminated triple-quoted
        # string) can surface a raw tokenize.TokenError or SyntaxError from
        # retrieval, before block_start is known. No reliable file location
        # exists at this point, so the diagnostic carries none.
        reason = _retrieval_reason(exc)
        message = f"cannot extract source of {_name_of(fn)!r}: {reason}"
        raise SourceExtractionError(
            message,
            diagnostics=[_error(message, filename)],
        ) from exc

    block = "".join(block_lines)
    indented = block_lines[0] != block_lines[0].lstrip()

    if indented:
        text = _WRAPPER + block
        line_delta = block_start - _WRAPPER_LINES - 1
    else:
        text = block
        line_delta = block_start - 1
    module = _parse_block(fn, text, filename, line_delta)
    if indented:
        body = cast("ast.If", module.body[0]).body
    else:
        body = module.body

    node = body[0] if len(body) == 1 else None
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        message = (
            f"source of {_name_of(fn)!r} is not a single function"
            " definition (lambdas are not supported)"
        )
        raise SourceExtractionError(
            message,
            diagnostics=[_error(message, filename, block_start)],
        )

    ast.increment_lineno(node, line_delta)
    node.decorator_list = []
    def_lineno = node.lineno
    source = "".join(block_lines[def_lineno - block_start :])
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
