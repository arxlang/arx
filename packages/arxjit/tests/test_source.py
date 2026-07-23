"""
title: Tests for source extraction.
"""

import ast
import dataclasses
import functools
import importlib.util
import inspect
import linecache
import pathlib
import sys
import tokenize

from typing import Any, Callable

import arxjit
import pytest

from arxjit.core import JitFunction, jit
from arxjit.diagnostics import DiagnosticSeverity
from arxjit.errors import SourceExtractionError
from arxjit.source import (
    ExtractedSource,
    _column_of,
    _retrieval_reason,
    extract_source,
)

PyFunc = Callable[..., Any]


def _passthrough(fn: PyFunc) -> PyFunc:
    """
    title: Return the decorated function unchanged.
    parameters:
      fn:
        type: PyFunc
    returns:
      type: PyFunc
    """
    return fn


def _configured(**_options: Any) -> Callable[[PyFunc], PyFunc]:
    """
    title: Return a passthrough decorator built from keyword options.
    parameters:
      _options:
        type: Any
        variadic: keyword
    returns:
      type: Callable[[PyFunc], PyFunc]
    """
    return _passthrough


def sample_add(a: int, b: int) -> int:
    """
    title: Add two integers.
    parameters:
      a:
        type: int
      b:
        type: int
    returns:
      type: int
    """
    return a + b


@_passthrough
@_passthrough
def sample_decorated(x: int) -> int:
    """
    title: Double an integer, behind two stacked decorators.
    parameters:
      x:
        type: int
    returns:
      type: int
    """
    return x * 2


@_configured(
    cache=True,
    strict=False,
)
def sample_multiline_decorated(x: int) -> int:
    """
    title: Negate an integer, behind a multi-line decorator call.
    parameters:
      x:
        type: int
    returns:
      type: int
    """
    return -x


async def sample_async(x: int) -> int:
    """
    title: Return the argument, asynchronously.
    parameters:
      x:
        type: int
    returns:
      type: int
    """
    return x


sample_lambda = lambda x: x * x  # noqa: E731


def _file_line(lineno: int) -> str:
    """
    title: Return the given one-based line of this test file.
    parameters:
      lineno:
        type: int
    returns:
      type: str
    """
    with open(__file__, encoding="utf-8") as stream:
        return stream.readlines()[lineno - 1]


def test_plain_function_is_extracted() -> None:
    """
    title: A plain module-level function extracts cleanly.
    """
    extracted = extract_source(sample_add)
    assert isinstance(extracted, ExtractedSource)
    assert extracted.filename == __file__
    assert extracted.source.startswith("def sample_add(")
    assert extracted.node.name == "sample_add"
    assert "def sample_add(" in _file_line(extracted.lineno)


def test_node_line_numbers_match_the_file() -> None:
    """
    title: Line numbers on the parsed node point into the real file.
    """
    extracted = extract_source(sample_add)
    assert extracted.node.lineno == extracted.lineno
    returns = [
        stmt
        for stmt in ast.walk(extracted.node)
        if isinstance(stmt, ast.Return)
    ]
    assert len(returns) == 1
    assert "return a + b" in _file_line(returns[0].lineno)


def test_decorator_lines_are_removed() -> None:
    """
    title: Stacked decorator lines are stripped from source and node.
    """
    extracted = extract_source(sample_decorated)
    assert extracted.source.startswith("def sample_decorated(")
    assert extracted.node.decorator_list == []
    assert "def sample_decorated(" in _file_line(extracted.lineno)


def test_multiline_decorator_is_removed() -> None:
    """
    title: A multi-line decorator call is stripped entirely.
    """
    extracted = extract_source(sample_multiline_decorated)
    assert extracted.source.startswith("def sample_multiline_decorated(")
    assert "cache=True" not in extracted.source
    assert "def sample_multiline_decorated(" in _file_line(extracted.lineno)


def test_nested_function_is_extracted_verbatim() -> None:
    """
    title: A function defined inside another parses without dedenting.
    summary: >-
      The source keeps its original indentation, and the def line of the
      returned verbatim text is exactly the line found in the real file.
    """

    def nested(x: int) -> int:
        """
        title: Increment an integer.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        return x + 1

    extracted = extract_source(nested)
    assert extracted.node.name == "nested"
    assert extracted.source.lstrip().startswith("def nested(")
    assert extracted.source.splitlines()[0] + "\n" == _file_line(
        extracted.lineno
    )


def test_nested_function_with_multiline_string_is_extracted() -> None:
    """
    title: Zero-indent lines inside string literals do not break parsing.
    summary: >-
      textwrap.dedent would compute a common indentation of zero for this block
      and the parse would fail with IndentationError; parsing the unmodified
      block inside the synthetic wrapper succeeds and preserves the string
      content verbatim.
    """

    def nested() -> str:
        """
        title: Return a two-line string.
        returns:
          type: str
        """
        value = """first
second
"""
        return value

    extracted = extract_source(nested)
    assert extracted.node.name == "nested"
    constants = [
        item.value
        for item in ast.walk(extracted.node)
        if isinstance(item, ast.Constant)
        and isinstance(item.value, str)
        and "second" in item.value
    ]
    assert constants == ["first\nsecond\n"]


def test_column_offsets_point_into_the_real_file() -> None:
    """
    title: Column offsets on nested-function nodes are file-true.
    summary: >-
      The source is parsed without removing indentation, so col_offset values
      index into the real file line (as byte offsets) and need no indentation
      correction at the diagnostic boundary.
    """

    def nested(x: int) -> int:
        """
        title: Increment an integer.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        return x + 1

    extracted = extract_source(nested)
    returns = [
        stmt
        for stmt in ast.walk(extracted.node)
        if isinstance(stmt, ast.Return)
    ]
    assert len(returns) == 1
    line = _file_line(returns[0].lineno)
    assert line[returns[0].col_offset :].startswith("return x + 1")
    assert line[returns[0].col_offset : returns[0].end_col_offset] == (
        "return x + 1"
    )


def test_extracted_source_reparses_standalone() -> None:
    """
    title: The decorator-free source parses as a standalone module.
    """
    extracted = extract_source(sample_decorated)
    module = ast.parse(extracted.source)
    assert len(module.body) == 1
    function = module.body[0]
    assert isinstance(function, ast.FunctionDef)
    assert function.name == "sample_decorated"


def test_async_function_is_extracted() -> None:
    """
    title: An async function extracts; rejecting it is validation's job.
    """
    extracted = extract_source(sample_async)
    assert isinstance(extracted.node, ast.AsyncFunctionDef)
    assert extracted.source.startswith("async def sample_async(")


def test_jit_function_is_extracted_with_filename() -> None:
    """
    title: Extracting an actual @jit result keeps the real filename.
    summary: >-
      JitFunction sets __wrapped__ via functools.update_wrapper, so both the
      source retrieval and the filename attribution must resolve to the wrapped
      function; the extraction also strips the @jit decorator line.
    """

    @jit
    def doubled(x: int) -> int:
        """
        title: Double an integer.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        return x * 2

    assert isinstance(doubled, JitFunction)
    extracted = extract_source(doubled)
    assert extracted.filename == __file__
    assert extracted.node.name == "doubled"
    assert extracted.node.decorator_list == []
    assert extracted.source.lstrip().startswith("def doubled(")
    assert "def doubled(" in _file_line(extracted.lineno)


def test_wrapped_function_is_attributed_to_the_original_file() -> None:
    """
    title: A wraps-style wrapper extracts the original, filename included.
    summary: >-
      inspect.getsourcelines follows __wrapped__, so the extracted source is
      the original function's; the reported filename must belong to the same
      function, even when the wrapper's own code lives in another file.
    """
    namespace: dict[str, Any] = {
        "functools": functools,
        "sample_add": sample_add,
    }
    exec(
        compile(
            "@functools.wraps(sample_add)\n"
            "def wrapper(*args, **kwargs):\n"
            "    return sample_add(*args, **kwargs)\n",
            "<wrapper>",
            "exec",
        ),
        namespace,
    )
    extracted = extract_source(namespace["wrapper"])
    assert extracted.filename == __file__
    assert extracted.node.name == "sample_add"
    assert "def sample_add(" in _file_line(extracted.lineno)


def test_lambda_is_rejected() -> None:
    """
    title: A lambda raises SourceExtractionError with one diagnostic.
    """
    with pytest.raises(SourceExtractionError) as caught:
        extract_source(sample_lambda)
    assert "not a single function definition" in str(caught.value)
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.severity is DiagnosticSeverity.ERROR
    assert diagnostic.filename == __file__
    assert diagnostic.line is not None


def test_builtin_is_rejected() -> None:
    """
    title: A C builtin has no source and raises SourceExtractionError.
    """
    with pytest.raises(SourceExtractionError) as caught:
        extract_source(len)
    assert isinstance(caught.value.__cause__, TypeError)
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.filename == "<unknown>"
    assert "cannot extract source of 'len'" in diagnostic.message


def test_exec_defined_function_is_rejected() -> None:
    """
    title: An exec-defined function raises SourceExtractionError.
    """
    namespace: dict[str, Any] = {}
    exec(
        compile("def made(x):\n    return x\n", "<string>", "exec"),
        namespace,
    )
    with pytest.raises(SourceExtractionError) as caught:
        extract_source(namespace["made"])
    assert isinstance(caught.value.__cause__, OSError)
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.filename == "<string>"
    assert diagnostic.line is None


def test_self_wrapped_function_is_rejected() -> None:
    """
    title: A __wrapped__ cycle raises SourceExtractionError, not ValueError.
    """

    def looped(x: int) -> int:
        """
        title: Return the argument.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        return x

    looped.__wrapped__ = looped  # type: ignore[attr-defined]
    with pytest.raises(SourceExtractionError) as caught:
        extract_source(looped)
    assert isinstance(caught.value.__cause__, ValueError)
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.filename == __file__


def test_unparsable_source_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: A source block that fails ast.parse raises with a location.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """

    def fake_getsourcelines(fn: Any) -> tuple[list[str], int]:
        """
        title: Return a syntactically broken source block.
        parameters:
          fn:
            type: Any
        returns:
          type: tuple[list[str], int]
        """
        return (["def broken(:\n"], 7)

    monkeypatch.setattr(inspect, "getsourcelines", fake_getsourcelines)
    with pytest.raises(SourceExtractionError) as caught:
        extract_source(sample_add)
    assert isinstance(caught.value.__cause__, SyntaxError)
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.message.startswith("cannot parse source of")
    assert diagnostic.line == 7


def test_indented_unparsable_source_maps_to_file_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: A broken indented block reports the file line, not the wrapped one.
    summary: >-
      An indented block is parsed inside the synthetic wrapper, which shifts
      SyntaxError line numbers by one; the diagnostic must still point at the
      real file line.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """

    def fake_getsourcelines(fn: Any) -> tuple[list[str], int]:
        """
        title: Return a broken source block indented like a method.
        parameters:
          fn:
            type: Any
        returns:
          type: tuple[list[str], int]
        """
        return (["    def broken(:\n"], 10)

    monkeypatch.setattr(inspect, "getsourcelines", fake_getsourcelines)
    with pytest.raises(SourceExtractionError) as caught:
        extract_source(sample_add)
    assert isinstance(caught.value.__cause__, SyntaxError)
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.line == 10


def test_null_byte_source_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Source containing a null byte raises SourceExtractionError.
    summary: >-
      Python 3.10 raises ValueError (not SyntaxError) from ast.parse for source
      containing null bytes; later versions raise SyntaxError. Either way the
      failure must be translated, never leaked raw.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """

    def fake_getsourcelines(fn: Any) -> tuple[list[str], int]:
        """
        title: Return a source block containing a null byte.
        parameters:
          fn:
            type: Any
        returns:
          type: tuple[list[str], int]
        """
        return (["def broken():\n", "    return '\0'\n"], 3)

    monkeypatch.setattr(inspect, "getsourcelines", fake_getsourcelines)
    with pytest.raises(SourceExtractionError) as caught:
        extract_source(sample_add)
    assert isinstance(caught.value.__cause__, (ValueError, SyntaxError))
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.message.startswith("cannot parse source of")
    assert "null byte" in diagnostic.message


def test_malformed_fstring_column_is_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: A malformed f-string never yields a misleading column.
    summary: >-
      On Python 3.10 and 3.11 the parser reports f-string errors against a
      synthetic string built from the replacement expression, so the offset
      does not point into the real source line and the diagnostic column must
      fall back to None; newer versions report real file locations and keep a
      column.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """

    def fake_getsourcelines(fn: Any) -> tuple[list[str], int]:
        """
        title: Return a source block with a malformed f-string.
        parameters:
          fn:
            type: Any
        returns:
          type: tuple[list[str], int]
        """
        return (['x = f"prefix {a b}"\n'], 5)

    monkeypatch.setattr(inspect, "getsourcelines", fake_getsourcelines)
    with pytest.raises(SourceExtractionError) as caught:
        extract_source(sample_add)
    assert isinstance(caught.value.__cause__, SyntaxError)
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.line == 5
    if sys.version_info < (3, 12):
        assert diagnostic.column is None
    elif sys.version_info >= (3, 13):
        assert diagnostic.column is not None
    else:
        # 3.12 straddles the PEP 701 transition; either a validated
        # column or the None fallback is acceptable, never a bogus one.
        assert diagnostic.column is None or diagnostic.column <= len(
            'x = f"prefix {a b}"'
        )


def test_corrupted_source_file_is_rejected(
    tmp_path: pathlib.Path,
) -> None:
    """
    title: A file corrupted after import raises SourceExtractionError.
    summary: >-
      inspect.getsourcelines tokenizes the file, so a source that becomes
      unparseable after import (here an unterminated triple-quoted string)
      makes retrieval raise a raw tokenize.TokenError. It must be translated
      like every other extraction failure, with no misleading location.
    parameters:
      tmp_path:
        type: pathlib.Path
    """
    module_path = tmp_path / "corrupt_after_import.py"
    module_path.write_text("def valid_fn(x):\n    return x + 1\n")
    spec = importlib.util.spec_from_file_location(
        "corrupt_after_import", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with module_path.open("a") as stream:
        stream.write('    y = """unterminated\n')
    linecache.clearcache()

    with pytest.raises(SourceExtractionError) as caught:
        extract_source(module.valid_fn)
    assert isinstance(
        caught.value.__cause__, (tokenize.TokenError, SyntaxError)
    )
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.message.startswith("cannot extract source of")
    assert diagnostic.line is None
    assert diagnostic.column is None


def test_retrieval_token_error_is_translated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: A TokenError from retrieval becomes SourceExtractionError.
    summary: >-
      The diagnostic uses the tokenizer's own message rather than its raw
      (message, position) args tuple, and attaches no file location because
      retrieval fails before the block's start line is known.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """

    def fake_getsourcelines(fn: Any) -> tuple[list[str], int]:
        """
        title: Raise a TokenError like a truncated multi-line string.
        parameters:
          fn:
            type: Any
        returns:
          type: tuple[list[str], int]
        """
        raise tokenize.TokenError("EOF in multi-line string", (3, 8))

    monkeypatch.setattr(inspect, "getsourcelines", fake_getsourcelines)
    with pytest.raises(SourceExtractionError) as caught:
        extract_source(sample_add)
    assert isinstance(caught.value.__cause__, tokenize.TokenError)
    (diagnostic,) = caught.value.diagnostics
    assert "EOF in multi-line string" in diagnostic.message
    assert "(3, 8)" not in diagnostic.message
    assert diagnostic.line is None
    assert diagnostic.column is None


def test_retrieval_syntax_error_is_translated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: A SyntaxError from retrieval becomes SourceExtractionError.
    summary: >-
      inspect.getblock can re-raise a SyntaxError during retrieval; unlike a
      parse-time SyntaxError it arrives before the block's start line is known,
      so no file location is attached, and the message drops the block-relative
      position that str(SyntaxError) would otherwise embed.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """

    def fake_getsourcelines(fn: Any) -> tuple[list[str], int]:
        """
        title: Raise a located SyntaxError like a retrieval failure.
        parameters:
          fn:
            type: Any
        returns:
          type: tuple[list[str], int]
        """
        raise SyntaxError("bad token", ("<unknown>", 3, 5, "    bad\n"))

    monkeypatch.setattr(inspect, "getsourcelines", fake_getsourcelines)
    with pytest.raises(SourceExtractionError) as caught:
        extract_source(sample_add)
    assert isinstance(caught.value.__cause__, SyntaxError)
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.message.startswith("cannot extract source of")
    assert diagnostic.message.endswith("bad token")
    assert "line 3" not in diagnostic.message
    assert diagnostic.line is None
    assert diagnostic.column is None


def test_retrieval_reason_strips_embedded_locations() -> None:
    """
    title: The retrieval-reason helper keeps only the human message.
    summary: >-
      Exercises each branch directly: a TokenError's (message, position) tuple
      reduces to its message, a SyntaxError drops its location suffix, and any
      other exception falls back to str().
    """
    token_error = tokenize.TokenError("EOF in multi-line string", (3, 8))
    assert _retrieval_reason(token_error) == "EOF in multi-line string"

    syntax_error = SyntaxError("bad token", ("<unknown>", 3, 5, "    bad\n"))
    assert _retrieval_reason(syntax_error) == "bad token"

    assert _retrieval_reason(OSError("no source")) == "no source"


def test_parse_valueerror_is_translated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: A ValueError from ast.parse becomes SourceExtractionError.
    summary: >-
      Only Python 3.10 raises ValueError from ast.parse in practice (null
      bytes), so the translation is exercised deterministically on every
      version by stubbing the parser.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """

    def fake_parse(*_args: Any, **_kwargs: Any) -> Any:
        """
        title: Raise ValueError like ast.parse on a null byte.
        parameters:
          _args:
            type: Any
            variadic: positional
          _kwargs:
            type: Any
            variadic: keyword
        returns:
          type: Any
        """
        raise ValueError("source code string cannot contain null bytes")

    monkeypatch.setattr(ast, "parse", fake_parse)
    with pytest.raises(SourceExtractionError) as caught:
        extract_source(sample_add)
    assert isinstance(caught.value.__cause__, ValueError)
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.message.startswith("cannot parse source of")
    assert diagnostic.line is None
    assert diagnostic.column is None


def test_column_validation_of_syntax_errors() -> None:
    """
    title: The column validator trusts only offsets that match the text.
    summary: >-
      Exercises every rejection branch directly with synthetic SyntaxError
      instances, so the behavior is identical on all Python versions regardless
      of which parser errors each version produces.
    """
    text = "x = 1\n"

    def syntax_error(
        lineno: int | None,
        offset: int | None,
        error_text: str | None,
    ) -> SyntaxError:
        """
        title: Build a SyntaxError with the given location attributes.
        parameters:
          lineno:
            type: int | None
          offset:
            type: int | None
          error_text:
            type: str | None
        returns:
          type: SyntaxError
        """
        exc = SyntaxError("boom")
        exc.lineno = lineno
        exc.offset = offset
        exc.text = error_text
        return exc

    assert _column_of(syntax_error(1, 5, "x = 1\n"), text) == 5
    assert _column_of(syntax_error(1, 0, "x = 1\n"), text) is None
    assert _column_of(syntax_error(None, 5, "x = 1\n"), text) is None
    assert _column_of(syntax_error(1, 5, None), text) is None
    assert _column_of(syntax_error(99, 5, "x = 1\n"), text) is None
    assert _column_of(syntax_error(1, 2, "(a b)\n"), text) is None


def test_extracted_source_is_frozen() -> None:
    """
    title: ExtractedSource instances are immutable.
    """
    extracted = extract_source(sample_add)
    with pytest.raises(dataclasses.FrozenInstanceError):
        extracted.lineno = 1  # type: ignore[misc]


def test_extraction_is_exported_from_package() -> None:
    """
    title: The extraction API is exported from arxjit.
    """
    assert arxjit.extract_source is extract_source
    assert arxjit.ExtractedSource is ExtractedSource
    for name in ("ExtractedSource", "extract_source"):
        assert name in arxjit.__all__
