"""
title: Tests for source extraction.
"""

import ast
import dataclasses

from typing import Any, Callable

import arxjit
import pytest

from arxjit.diagnostics import DiagnosticSeverity
from arxjit.errors import SourceExtractionError
from arxjit.source import ExtractedSource, extract_source

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


def test_nested_function_is_dedented() -> None:
    """
    title: A function defined inside another parses after dedenting.
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
    assert extracted.source.startswith("def nested(")
    assert extracted.node.name == "nested"


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
