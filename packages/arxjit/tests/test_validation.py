"""
title: Tests for Python-subset validation.
"""

import ast

from typing import Any, Callable

import pytest

from arxjit.diagnostics import DiagnosticSeverity
from arxjit.errors import UnsupportedSyntaxError
from arxjit.source import ExtractedSource, extract_source
from arxjit.validation import (
    _char_column,
    _is_range_call,
    _SubsetValidator,
    validate,
)

PyFunc = Callable[..., Any]


def _rejected(fn: PyFunc) -> list[Any]:
    """
    title: Extract, validate, and return the diagnostics of a rejection.
    summary: >-
      Asserts the function is rejected and returns its diagnostics, so
      individual tests can focus on which messages and locations matter.
    parameters:
      fn:
        type: PyFunc
    returns:
      type: list[Any]
    """
    extracted = extract_source(fn)
    with pytest.raises(UnsupportedSyntaxError) as caught:
        validate(extracted)
    return caught.value.diagnostics


def sample_valid(count: int, flag: bool) -> int:
    """
    title: Exercise the entire v1-supported subset in one function.
    parameters:
      count:
        type: int
      flag:
        type: bool
    returns:
      type: int
    """
    total = 0
    if flag:
        step = 1
    else:
        step = -1
    i = 0
    while i < count:
        if i % 2 == 0 and i > 0:
            total = total + i * step
        elif i == 0:
            pass
        else:
            total = total - 1
        i = i + 1
    for j in range(count):
        total = total + j
    return total


def test_supported_subset_passes_validation() -> None:
    """
    title: A function using only the v1 subset validates cleanly.
    """
    extracted = extract_source(sample_valid)
    validate(extracted)


def test_chained_comparison_is_accepted() -> None:
    """
    title: A chained comparison (a < b < c) is a single valid Compare node.
    """

    def sample(a: int, b: int, c: int) -> bool:
        """
        title: Check a is strictly between b and c.
        parameters:
          a:
            type: int
          b:
            type: int
          c:
            type: int
        returns:
          type: bool
        """
        return b < a < c

    extracted = extract_source(sample)
    validate(extracted)


def test_async_function_is_rejected() -> None:
    """
    title: An async top-level function is rejected as a whole.
    """

    async def sample(x: int) -> int:
        """
        title: Return the argument, asynchronously.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        return x

    (diagnostic,) = _rejected(sample)
    assert "async function definitions" in diagnostic.message
    assert diagnostic.severity is DiagnosticSeverity.ERROR


def test_list_literal_is_rejected() -> None:
    """
    title: A list literal is rejected.
    """

    def sample(x: int) -> int:
        """
        title: Build a list.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        values = [x, 1]
        return values[0]

    diagnostics = _rejected(sample)
    assert any("list literals" in d.message for d in diagnostics)


def test_yield_statement_gets_the_generators_message() -> None:
    """
    title: A bare "yield x" gets the specific generators message.
    summary: >-
      Regression test: visit_Expr must delegate Yield/YieldFrom to the generic
      unsupported-construct lookup instead of reporting the generic "standalone
      expression statements" message.
    """

    def sample(x: int) -> int:
        """
        title: Yield the argument, making this a generator function.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        yield x

    (diagnostic,) = _rejected(sample)
    assert "generators" in diagnostic.message
    assert "standalone expression" not in diagnostic.message


def test_bare_call_expression_is_rejected() -> None:
    """
    title: A bare call statement (not assigned or returned) is rejected.
    """

    def sample(x: int) -> int:
        """
        title: Call a builtin and discard its result.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        abs(x)
        return x

    (diagnostic,) = _rejected(sample)
    assert "standalone expression statements" in diagnostic.message


def test_docstring_is_not_rejected() -> None:
    """
    title: A function docstring does not count against the subset.
    """

    def sample(x: int) -> int:
        """
        title: Return the argument unchanged.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        return x

    extracted = extract_source(sample)
    validate(extracted)


def test_pass_is_not_rejected() -> None:
    """
    title: A pass statement is accepted as a no-op.
    """

    def sample(flag: bool) -> int:
        """
        title: Branch without doing anything in the else arm.
        parameters:
          flag:
            type: bool
        returns:
          type: int
        """
        if flag:
            pass
        else:
            pass
        return 0

    extracted = extract_source(sample)
    validate(extracted)


def test_bitwise_operator_is_rejected() -> None:
    """
    title: A bitwise operator is outside the v1 arithmetic subset.
    """

    def sample(x: int, y: int) -> int:
        """
        title: Bitwise-and two integers.
        parameters:
          x:
            type: int
          y:
            type: int
        returns:
          type: int
        """
        return x & y

    (diagnostic,) = _rejected(sample)
    assert "BitAnd" in diagnostic.message


def test_string_constant_is_rejected() -> None:
    """
    title: A non-scalar (string) literal used as a value is rejected.
    """

    def sample(flag: bool) -> str:
        """
        title: Return a fixed string.
        parameters:
          flag:
            type: bool
        returns:
          type: str
        """
        return "hello"

    (diagnostic,) = _rejected(sample)
    assert "str literals are not supported" in diagnostic.message


def test_multiple_violations_are_all_collected() -> None:
    """
    title: A function with several violations reports all of them at once.
    """

    def sample(x: int) -> int:
        """
        title: Combine three unsupported constructs.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        import math  # noqa: F401, PLC0415

        f = lambda y: y  # noqa: E731
        values = [x, 1]
        return f(values[0])

    diagnostics = _rejected(sample)
    messages = " | ".join(d.message for d in diagnostics)
    assert "lambda expressions" in messages
    assert "list literals" in messages
    assert "import statements" in messages
    assert len(diagnostics) >= 3


def test_multiple_assignment_targets_are_rejected() -> None:
    """
    title: A chained assignment (a = b = x) is rejected.
    """

    def sample(x: int) -> int:
        """
        title: Assign to two names at once.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        a = b = x
        return a + b

    (diagnostic,) = _rejected(sample)
    assert "single local variable" in diagnostic.message


def test_bitwise_not_is_rejected() -> None:
    """
    title: The unary bitwise-not operator is rejected.
    """

    def sample(x: int) -> int:
        """
        title: Bitwise-invert an integer.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        return ~x

    (diagnostic,) = _rejected(sample)
    assert "Invert" in diagnostic.message


def test_identity_comparison_is_rejected() -> None:
    """
    title: An identity comparison (is) is outside the comparison subset.
    """

    def sample(x: int, y: int) -> bool:
        """
        title: Compare two values by identity.
        parameters:
          x:
            type: int
          y:
            type: int
        returns:
          type: bool
        """
        return x is y

    (diagnostic,) = _rejected(sample)
    assert "Is comparison" in diagnostic.message


def test_for_over_non_range_is_rejected() -> None:
    """
    title: A for loop over something other than range(...) is rejected.
    """

    def sample(x: int) -> int:
        """
        title: Iterate over a bare name instead of range(...).
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        total = 0
        for i in x:
            total = total + i
        return total

    (diagnostic,) = _rejected(sample)
    assert "for loops are only supported over range" in diagnostic.message


def test_for_tuple_target_is_rejected() -> None:
    """
    title: A for-loop tuple-unpacking target is rejected.
    """

    def sample(x: int) -> int:
        """
        title: Unpack a tuple target in a for loop.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        total = 0
        for i, j in range(x):
            total = total + i
        return total

    (diagnostic,) = _rejected(sample)
    assert "for-loop targets" in diagnostic.message


def test_varargs_are_rejected() -> None:
    """
    title: A *args parameter is rejected.
    """

    def sample(*values: int) -> int:
        """
        title: Accept a variable number of positional arguments.
        parameters:
          values:
            type: int
            variadic: positional
        returns:
          type: int
        """
        return 0

    diagnostics = _rejected(sample)
    assert any(
        "variadic positional arguments" in d.message for d in diagnostics
    )


def test_kwargs_are_rejected() -> None:
    """
    title: A **kwargs parameter is rejected.
    """

    def sample(**values: int) -> int:
        """
        title: Accept a variable number of keyword arguments.
        parameters:
          values:
            type: int
            variadic: keyword
        returns:
          type: int
        """
        return 0

    diagnostics = _rejected(sample)
    assert any("variadic keyword arguments" in d.message for d in diagnostics)


def test_keyword_only_arguments_are_rejected() -> None:
    """
    title: A keyword-only argument is rejected.
    """

    def sample(x: int, *, y: int) -> int:
        """
        title: Accept a keyword-only argument.
        parameters:
          x:
            type: int
          y:
            type: int
        returns:
          type: int
        """
        return x + y

    (diagnostic,) = _rejected(sample)
    assert "keyword-only arguments" in diagnostic.message


def test_default_argument_values_are_rejected() -> None:
    """
    title: A default argument value is rejected.
    """

    def sample(x: int, y: int = 1) -> int:
        """
        title: Accept an argument with a default value.
        parameters:
          x:
            type: int
          y:
            type: int
        returns:
          type: int
        """
        return x + y

    (diagnostic,) = _rejected(sample)
    assert "default argument values" in diagnostic.message


def test_column_points_at_the_real_file() -> None:
    """
    title: A diagnostic's line and column point at the real source file.
    summary: >-
      Regression test for the extracted-source line-offset fix: node.lineno is
      a real file line number, not an index into ExtractedSource.source, so the
      diagnostic must locate the correct real line before converting its
      column.
    """

    def sample(x: int) -> int:
        """
        title: Build an unsupported list literal.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        return [x, 1]

    (diagnostic,) = _rejected(sample)
    with open(__file__, encoding="utf-8") as stream:
        real_line = stream.readlines()[diagnostic.line - 1]
    assert "[x, 1]" in real_line
    assert diagnostic.column is not None
    assert real_line[diagnostic.column - 1 :].startswith("[x, 1]")


def test_nested_function_diagnostics_point_at_the_real_file() -> None:
    """
    title: Diagnostics from a non-module-level function are still file-true.
    summary: >-
      A function defined inside another starts partway through the file,
      exercising the extracted.lineno offset the module-level cases above do
      not.
    """

    def outer() -> PyFunc:
        """
        title: Define and return a nested function containing a violation.
        returns:
          type: PyFunc
        """

        def inner(x: int) -> int:
            """
            title: Build an unsupported list literal.
            parameters:
              x:
                type: int
            returns:
              type: int
            """
            return [x, 1]

        return inner

    (diagnostic,) = _rejected(outer())
    with open(__file__, encoding="utf-8") as stream:
        real_line = stream.readlines()[diagnostic.line - 1]
    assert "[x, 1]" in real_line
    assert real_line[diagnostic.column - 1 :].startswith("[x, 1]")


def test_char_column_converts_multibyte_prefixes() -> None:
    """
    title: _char_column converts a UTF-8 byte offset to a character column.
    summary: >-
      A non-ASCII character earlier on the line makes the byte offset diverge
      from the character index; this directly pins the conversion independent
      of the ast probing above.
    """
    line = '    x = "héllo" + [1, 2]'
    char_index = line.index("[")
    # ast reports col_offset as a UTF-8 byte offset; the two-byte "é"
    # makes it exceed the character index by exactly one.
    real_byte_offset = len(line[:char_index].encode("utf-8"))
    assert real_byte_offset == char_index + 1
    assert _char_column(line, real_byte_offset) == char_index + 1


def test_is_range_call_rejects_non_range_shapes() -> None:
    """
    title: _is_range_call only accepts a bare name call to range().
    """
    assert _is_range_call(ast.parse("range(5)", mode="eval").body)
    assert not _is_range_call(ast.parse("range(stop=5)", mode="eval").body)
    assert not _is_range_call(ast.parse("mod.range(5)", mode="eval").body)
    assert not _is_range_call(ast.parse("[1, 2]", mode="eval").body)
    assert not _is_range_call(ast.parse("x", mode="eval").body)


def test_unrecognized_node_type_falls_back_to_a_generic_message() -> None:
    """
    title: >-
      A node type absent from the whitelist and the message table still gets a
      rejection, not a silent pass.
    summary: >-
      Exercises generic_visit's fail-closed fallback directly, covering any
      future Python syntax this validator was not updated for, without
      depending on a specific version-gated construct being available.
    """

    class _Unknown(ast.AST):
        """
        title: A stand-in ast node type absent from every lookup table.
        attributes:
          _fields:
            type: tuple[str, Ellipsis]
        """

        _fields: tuple[str, ...] = ()
        lineno = 1
        col_offset = 0

    extracted = ExtractedSource(
        filename="synthetic.py",
        source="def f():\n    pass\n",
        lineno=1,
        node=ast.parse("def f():\n    pass\n").body[0],
    )
    validator = _SubsetValidator(extracted)
    validator.generic_visit(_Unknown())
    (diagnostic,) = validator.diagnostics
    assert "_Unknown is not supported" in diagnostic.message
