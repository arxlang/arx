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
    _UNSUPPORTED_MESSAGES,
    _bound_names,
    _char_column,
    _SubsetValidator,
    validate,
)

PyFunc = Callable[..., Any]

# except* parses only on Python 3.11+; the validator guards its table entry
# the same way, so the matrix below has to agree with whichever it is.
_TRY_STAR = getattr(ast, "TryStar", None)


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

    diagnostics = _rejected(sample)
    assert any("for-loop targets" in d.message for d in diagnostics)


def test_for_else_clause_is_rejected() -> None:
    """
    title: A for-else clause is rejected.
    summary: >-
      The loop else pairs with break, which is outside the subset, so it is
      rejected rather than silently accepted and left for lowering.
    """

    def sample(x: int) -> int:
        """
        title: Attach an else clause to a for loop.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        total = 0
        for i in range(x):
            total = total + i
        else:  # noqa: PLW0120
            total = 0
        return total

    (diagnostic,) = _rejected(sample)
    assert "for-else clauses are not supported" in diagnostic.message


def test_while_else_clause_is_rejected() -> None:
    """
    title: A while-else clause is rejected.
    """

    def sample(x: int) -> int:
        """
        title: Attach an else clause to a while loop.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        while x > 0:
            x = x - 1
        else:  # noqa: PLW0120
            x = 0
        return x

    (diagnostic,) = _rejected(sample)
    assert "while-else clauses are not supported" in diagnostic.message


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


def test_free_variable_read_is_rejected() -> None:
    """
    title: Reading a name that is neither an argument nor a local is rejected.
    summary: >-
      The extracted node of a nested function keeps its free variables as plain
      ast.Name loads; without binding analysis a closure capture would pass
      validation, so this pins that a free read is rejected.
    """

    def sample(x: int) -> int:
        """
        title: Multiply by an undefined free variable.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        return x * scale  # noqa: F821

    (diagnostic,) = _rejected(sample)
    assert "'scale'" in diagnostic.message
    assert "closures and globals are not supported" in diagnostic.message


def test_global_read_is_rejected() -> None:
    """
    title: Reading a module global is rejected like a closure capture.
    """

    def sample(x: int) -> int:
        """
        title: Multiply by a module-level constant.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        return x * _SAMPLE_GLOBAL

    (diagnostic,) = _rejected(sample)
    assert "'_SAMPLE_GLOBAL'" in diagnostic.message


def test_shadowed_range_is_rejected() -> None:
    """
    title: A range shadowed by an argument is not treated as the builtin.
    """

    def sample(range: int) -> int:
        """
        title: Loop over a parameter named range.
        parameters:
          range:
            type: int
        returns:
          type: int
        """
        total = 0
        for i in range(3):
            total = total + i
        return total

    (diagnostic,) = _rejected(sample)
    assert "range is shadowed" in diagnostic.message


def test_closure_captured_range_shadow_is_rejected() -> None:
    """
    title: A range captured from an enclosing scope is rejected.
    summary: >-
      An enclosing function's local shadows the builtin for the whole nested
      function, which Python resolves through the closure (a TypeError when it
      is not callable). The capture is a plain Name load in the extracted AST,
      indistinguishable from the builtin, so the captured names carried by
      extraction are what reveal it.
    """

    def outer() -> PyFunc:
        """
        title: Return a kernel that captures a local named range.
        returns:
          type: PyFunc
        """
        range = 5

        def kernel(n: int) -> int:
            """
            title: Loop over the captured range.
            parameters:
              n:
                type: int
            returns:
              type: int
            """
            total = 0
            for i in range(n):
                total = total + i
            return total

        return kernel

    (diagnostic,) = _rejected(outer())
    assert "enclosing function's variable" in diagnostic.message


def test_module_level_range_shadow_is_rejected() -> None:
    """
    title: A module-global that shadows range is rejected.
    summary: >-
      A module-level ``range = 42`` makes the call a TypeError in Python, so
      compiling it as the range intrinsic would silently change behavior. The
      shadowing is invisible in the AST, so the defining module's namespace
      carried by extraction is what reveals it.
    """
    source = (
        "def kernel(n: int) -> int:\n"
        "    total = 0\n"
        "    for i in range(n):\n"
        "        total = total + i\n"
        "    return total\n"
    )
    extracted = ExtractedSource(
        filename="<shadowed>",
        source=source,
        lineno=1,
        node=ast.parse(source).body[0],  # type: ignore[arg-type]
        globalns={"range": 42},
    )
    with pytest.raises(UnsupportedSyntaxError) as caught:
        validate(extracted)
    (diagnostic,) = caught.value.diagnostics
    assert "shadowed by a module-level name" in diagnostic.message


def test_module_namespace_without_shadowing_is_accepted() -> None:
    """
    title: A module namespace that leaves range alone validates cleanly.
    summary: >-
      Covers both an unrelated global and the builtin bound explicitly under
      its own name, neither of which shadows the intrinsic.
    """
    source = (
        "def kernel(n: int) -> int:\n"
        "    total = 0\n"
        "    for i in range(n):\n"
        "        total = total + i\n"
        "    return total\n"
    )
    for namespace in ({"other": 1}, {"range": range}, None):
        extracted = ExtractedSource(
            filename="<clean>",
            source=source,
            lineno=1,
            node=ast.parse(source).body[0],  # type: ignore[arg-type]
            globalns=namespace,
        )
        validate(extracted)


def test_nested_scope_binding_does_not_leak_outward() -> None:
    """
    title: A name assigned in a nested scope is not a binding of this one.
    summary: >-
      Regression test: collecting bindings with ast.walk descended into the
      nested function and treated its ``range`` local as shadowing the builtin
      in the outer scope, producing a misleading diagnostic. Only the nested
      definition itself should be reported.
    """

    def sample(n: int) -> int:
        """
        title: Loop over range while a nested helper binds the name range.
        parameters:
          n:
            type: int
        returns:
          type: int
        """

        def helper() -> int:
            """
            title: Bind and return a local named range.
            returns:
              type: int
            """
            range = 10
            return range

        total = 0
        for i in range(n):
            total = total + i
        return total

    diagnostics = _rejected(sample)
    messages = [d.message for d in diagnostics]
    assert any("nested function definitions" in m for m in messages)
    assert not any("range is shadowed" in m for m in messages)


def test_nested_scope_binding_does_not_hide_a_free_variable() -> None:
    """
    title: A nested scope's local does not mask an outer free-variable read.
    summary: >-
      Regression test for the collect-all-at-once guarantee: the nested
      function's ``scale`` local made the outer read of ``scale`` look bound,
      so only one of the two problems was reported.
    """

    def sample() -> int:
        """
        title: Read a name that only a nested helper binds.
        returns:
          type: int
        """

        def helper() -> int:
            """
            title: Bind and return a local named scale.
            returns:
              type: int
            """
            scale = 2
            return scale

        return scale  # noqa: F821

    diagnostics = _rejected(sample)
    messages = [d.message for d in diagnostics]
    assert any("nested function definitions" in m for m in messages)
    assert any("'scale'" in m for m in messages)


def test_range_with_too_many_arguments_is_rejected() -> None:
    """
    title: A range() call with four arguments is rejected.
    """

    def sample(n: int) -> int:
        """
        title: Loop over range with four arguments.
        parameters:
          n:
            type: int
        returns:
          type: int
        """
        total = 0
        for i in range(1, 2, 3, 4):
            total = total + i
        return total

    (diagnostic,) = _rejected(sample)
    assert "one to three positional arguments" in diagnostic.message


def test_range_with_no_arguments_is_rejected() -> None:
    """
    title: A range() call with no arguments is rejected.
    """

    def sample(n: int) -> int:
        """
        title: Loop over range with no arguments.
        parameters:
          n:
            type: int
        returns:
          type: int
        """
        total = 0
        for i in range():
            total = total + i
        return total

    (diagnostic,) = _rejected(sample)
    assert "one to three positional arguments" in diagnostic.message


def test_range_with_keyword_argument_is_rejected() -> None:
    """
    title: A keyword-argument call to range(...) is rejected.
    """

    def sample(n: int) -> int:
        """
        title: Call range with a keyword argument.
        parameters:
          n:
            type: int
        returns:
          type: int
        """
        total = 0
        for i in range(stop=n):
            total = total + i
        return total

    (diagnostic,) = _rejected(sample)
    assert "does not accept keyword arguments" in diagnostic.message


def test_binding_collector_handles_every_target_shape() -> None:
    """
    title: The binding collector records each binding form of one scope.
    summary: >-
      Tuple, list, and starred targets each bind their names, while an
      attribute or subscript target binds none. The annotated, augmented, and
      walrus forms bind their target even though the subset rejects the
      statements themselves, so a rejected statement does not also report a
      spurious free variable. A nested scope contributes its own name but never
      its locals.
    """
    source = (
        "def kernel(a, /, b, *args, c=1, **kwargs):\n"
        "    first, *rest = b\n"
        "    [second, third] = b\n"
        "    holder.attr = b\n"
        "    holder[0] = b\n"
        "    annotated: int = b\n"
        "    counter = 0\n"
        "    counter += 1\n"
        "    while (walrus := b):\n"
        "        pass\n"
        "    for i in range(3):\n"
        "        pass\n"
        "    def nested():\n"
        "        hidden = 1\n"
        "        return hidden\n"
        "    class Local:\n"
        "        member = 1\n"
        "    return a\n"
    )
    node = ast.parse(source).body[0]
    assert _bound_names(node) == {  # type: ignore[arg-type]
        "a",
        "b",
        "args",
        "c",
        "kwargs",
        "first",
        "rest",
        "second",
        "third",
        "annotated",
        "counter",
        "walrus",
        "i",
        "nested",
        "Local",
    }


def test_unrecognized_node_type_falls_back_to_a_generic_message() -> None:
    """
    title: >-
      A node type absent from the whitelist and the message table still gets a
      rejection, not a silent pass.
    summary: >-
      Exercises the fail-closed ast.AST dispatch fallback directly, covering
      any future Python syntax this validator was not updated for, without
      depending on a version-gated construct being available.
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
    validator = _SubsetValidator(extracted, set())
    validator.visit(_Unknown())
    (diagnostic,) = validator.diagnostics
    assert "_Unknown is not supported" in diagnostic.message


def test_generic_function_is_rejected() -> None:
    """
    title: A PEP 695 generic function (type parameters) is rejected.
    summary: >-
      The type-parameter syntax parses only on Python 3.12+, so rather than
      version-gate the test, type_params is set on a parsed node directly
      (validate only checks that the list is non-empty); this exercises the
      rejection on every supported Python version.
    """
    source = "def identity(x: int) -> int:\n    return x\n"
    node = ast.parse(source).body[0]
    node.type_params = ["T"]  # type: ignore[attr-defined,list-item]
    extracted = ExtractedSource(
        filename="<generic>",
        source=source,
        lineno=1,
        node=node,  # type: ignore[arg-type]
    )
    with pytest.raises(UnsupportedSyntaxError) as caught:
        validate(extracted)
    assert any(
        "generic functions" in d.message for d in caught.value.diagnostics
    )


def test_method_is_rejected() -> None:
    """
    title: A function defined in a class body is rejected as a method.
    """

    class Calc:
        """
        title: Hold a method to validate (test helper).
        """

        def scaled(self, x: int) -> int:
            """
            title: Double the argument.
            parameters:
              x:
                type: int
            returns:
              type: int
            """
            return x * 2

    (diagnostic,) = _rejected(Calc.scaled)
    assert "methods are not supported" in diagnostic.message


def test_nested_function_is_not_treated_as_a_method() -> None:
    """
    title: A function nested in another function is not a method.
    summary: >-
      Both are dotted qualified names; only a method's has a class as its
      second-to-last part, where a nested function has "<locals>".
    """

    def sample(x: int) -> int:
        """
        title: Double the argument.
        parameters:
          x:
            type: int
        returns:
          type: int
        """
        return x * 2

    assert "<locals>" in sample.__qualname__
    validate(extract_source(sample))


# Every construct outside the v1 subset, paired with the smallest function
# body that produces it. The parametrized test below asserts each one is
# routed to its own entry in _UNSUPPORTED_MESSAGES rather than to a more
# general one, and test_every_unsupported_message_has_a_case asserts this
# list stays exhaustive as the table grows.
_UNSUPPORTED_CASES: list[tuple[type[ast.AST], str]] = [
    (ast.ClassDef, "class C:\n    pass"),
    (ast.Lambda, "f = lambda: 1"),
    (ast.FunctionDef, "def inner():\n    return 1"),
    (ast.AsyncFunctionDef, "async def inner():\n    return 1"),
    (ast.AsyncFor, "async for i in x:\n    pass"),
    (ast.AsyncWith, "async with x:\n    pass"),
    (ast.With, "with x:\n    pass"),
    (ast.Try, "try:\n    pass\nexcept Exception:\n    pass"),
    (ast.Raise, "raise ValueError"),
    (ast.Assert, "assert x"),
    (ast.Import, "import math"),
    (ast.ImportFrom, "from math import sqrt"),
    (ast.Global, "global g"),
    (ast.Nonlocal, "nonlocal n"),
    (ast.Yield, "yield x"),
    (ast.YieldFrom, "yield from x"),
    (ast.List, "v = [1]"),
    (ast.Dict, "v = {1: 2}"),
    (ast.Set, "v = {1}"),
    (ast.Tuple, "v = (1, 2)"),
    (ast.ListComp, "v = [i for i in range(x)]"),
    (ast.DictComp, "v = {i: i for i in range(x)}"),
    (ast.SetComp, "v = {i for i in range(x)}"),
    (ast.GeneratorExp, "v = (i for i in range(x))"),
    (ast.Break, "while x:\n    break"),
    (ast.Continue, "while x:\n    continue"),
    (ast.Delete, "del x"),
    (ast.AnnAssign, "v: int = 1"),
    (ast.AugAssign, "x += 1"),
    (ast.JoinedStr, 'v = f"{x}"'),
    (ast.NamedExpr, "if (v := x):\n    pass"),
    (ast.Attribute, "v = x.real"),
    (ast.Subscript, "v = x[0]"),
    (ast.Match, "match x:\n    case 1:\n        pass"),
    # Await and Starred are shadowed in the positions one reaches for first:
    # a bare "await x" is an expression statement and "[*x]" is a list
    # literal, so each reports the enclosing construct instead. These are the
    # positions where the node itself is what gets rejected.
    (ast.Await, "v = await x"),
    (ast.Starred, "for i in range(*x):\n    pass"),
]

if _TRY_STAR is not None:  # pragma: no cover - version dependent
    _UNSUPPORTED_CASES.append(
        (_TRY_STAR, "try:\n    pass\nexcept* Exception:\n    pass")
    )

# ast.Slice has a message in the table but no reachable position: a slice can
# only appear inside a Subscript, and Subscript is rejected without descending
# into it. The entry is kept as a safety net in case that ever changes, and is
# named here so the exhaustiveness test stays honest about it.
_SHADOWED_MESSAGES: frozenset[type[ast.AST]] = frozenset({ast.Slice})

_ASYNC_ONLY: tuple[type[ast.AST], ...] = (
    ast.Await,
    ast.AsyncFor,
    ast.AsyncWith,
)


def _validate_snippet(body: str, is_async: bool = False) -> list[str]:
    """
    title: Validate a function built around a body snippet (test helper).
    summary: >-
      Builds the smallest function containing the snippet, hand-constructs an
      ExtractedSource around it, and returns the rejection messages. The source
      is built as text rather than as a real nested function so that a lint
      autofix cannot rewrite the construct under test, which has happened
      before with unused in-function imports.
    parameters:
      body:
        type: str
        description: The statements to place in the function body.
      is_async:
        type: bool
        description: Whether the containing function must be async.
    returns:
      type: list[str]
    """
    prefix = "async def" if is_async else "def"
    indented = "\n".join(
        f"    {line}" if line else "" for line in body.splitlines()
    )
    source = f"{prefix} sample(x: int) -> int:\n{indented}\n    return x\n"
    node = ast.parse(source).body[0]
    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    extracted = ExtractedSource(
        filename="<test>", source=source, lineno=1, node=node
    )
    with pytest.raises(UnsupportedSyntaxError) as caught:
        validate(extracted)
    return [d.message for d in caught.value.diagnostics]


@pytest.mark.parametrize(
    ("node_type", "body"),
    _UNSUPPORTED_CASES,
    ids=[node_type.__name__ for node_type, _ in _UNSUPPORTED_CASES],
)
def test_unsupported_construct_uses_its_own_message(
    node_type: type[ast.AST],
    body: str,
) -> None:
    """
    title: Every unsupported construct reports its own diagnostic message.
    summary: >-
      Guards against a construct being swallowed by a more general rule: the
      message produced must be the one the table assigns to that node type, not
      one belonging to an enclosing node.
    parameters:
      node_type:
        type: type[ast.AST]
      body:
        type: str
    """
    messages = _validate_snippet(body, is_async=node_type in _ASYNC_ONLY)
    assert _UNSUPPORTED_MESSAGES[node_type] in messages


def test_every_unsupported_message_has_a_case() -> None:
    """
    title: The rejection matrix covers every entry in the message table.
    summary: >-
      Adding a message to _UNSUPPORTED_MESSAGES without a matching case here
      fails this test, so the matrix cannot quietly fall behind the validator.
    """
    covered = {node_type for node_type, _ in _UNSUPPORTED_CASES}
    assert covered | _SHADOWED_MESSAGES == set(_UNSUPPORTED_MESSAGES)


def test_walrus_does_not_also_report_a_free_variable() -> None:
    """
    title: A rejected walrus binds its name, so it reports exactly once.
    summary: >-
      The binding collector records NamedExpr targets precisely so a rejected
      statement does not also emit a spurious free-variable read for the name
      it introduces.
    """
    messages = _validate_snippet("if (v := x):\n    pass\nv = v + 1")
    assert messages == ["walrus assignment expressions are not supported"]


def test_annotated_assignment_does_not_also_report_a_free_variable() -> None:
    """
    title: A rejected annotated assignment binds its target.
    """
    messages = _validate_snippet("v: int = 1\nv = v + 1")
    assert messages == ["annotated assignments are not supported"]


def test_augmented_assignment_does_not_also_report_a_free_variable() -> None:
    """
    title: A rejected augmented assignment binds its target.
    """
    messages = _validate_snippet("v = 1\nv += 1\nv = v + 1")
    assert messages == ["augmented assignment (e.g. +=) is not supported"]


def test_call_nested_inside_range_args_is_rejected() -> None:
    """
    title: A non-range call inside range(...)'s arguments is rejected.
    summary: >-
      range() itself is the one permitted call, so its arguments still have to
      be walked rather than trusted.
    """
    messages = _validate_snippet("for i in range(abs(x)):\n    pass")
    assert messages == [
        "calling functions is not supported (only range() in a for loop)"
    ]


_SAMPLE_GLOBAL = 2
