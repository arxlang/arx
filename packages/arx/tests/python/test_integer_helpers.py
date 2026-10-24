"""
title: Compile and execute integer helper boundaries with bounded resources.
"""

import shutil
import subprocess
import sys

from pathlib import Path

import pytest

from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.main import FileImportResolver, inject_ambient_builtin_imports
from arx.parser import Parser
from irx.analysis.module_interfaces import ParsedModule
from irx.builder.runtime.exceptions import parse_exception_output
from llvmlite import binding as llvm
from public import private

I32_MIN = -(2**31)
I32_MAX = 2**31 - 1
pytestmark = pytest.mark.skipif(
    shutil.which("clang") is None, reason="native helpers require clang"
)


@private
def i32_expression(value: int) -> str:
    """
    title: Spell boundary inputs without an out-of-range positive i32 token.
    parameters:
      value:
        type: int
    returns:
      type: str
    """
    if value >= 0:
        return str(value)
    return f"(0 - {-value - 1} - 1)"


@private
def signed_limits(width: int) -> str:
    """
    title: Declare typed limits using only representable i32 literal tokens.
    parameters:
      width:
        type: int
    returns:
      type: str
    """
    type_ = f"i{width}"
    maximum = f"cast({2 ** (width - 1) - 1}, {type_})"
    if width == 64:
        maximum = (
            "cast(2147483647, i64) * 65536 * 65536"
            " + cast(65535, i64) * 65536 + 65535"
        )
    return (
        f"var zero: {type_} = cast(0, {type_})\n"
        f"var one: {type_} = cast(1, {type_})\n"
        f"var maximum: {type_} = {maximum}\n"
        f"var minimum: {type_} = zero - maximum - one\n"
    )


@private
def run_helpers(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    """
    title: Verify helper LLVM and execute without unbounded time or allocation.
    parameters:
      tmp_path:
        type: Path
      body:
        type: str
    returns:
      type: subprocess.CompletedProcess[str]
    """
    source = (
        "```\ntitle: Integer helper boundary regression\n```\n"
        "import math from stdlib\n"
        "fn main() -> i32:\n"
        + "\n".join("  " + line for line in body.splitlines())
        + "\n  return 0\n"
    )
    ArxIO.string_to_buffer(source)
    module = Parser().parse(Lexer().lex(), "integer_helpers")
    root = ParsedModule(
        "integer_helpers", inject_ambient_builtin_imports(module)
    )
    resolver = FileImportResolver(())
    builder = ArxBuilder()
    text = builder.translate_modules(root, resolver)
    llvm.parse_assembly(text).verify()
    binary = tmp_path / "helpers"
    builder._build_from_ir_result(text, str(binary), True, "auto")

    command = [str(binary)]
    if sys.platform == "linux":
        # A wrapping range can exhaust memory before the timeout. Set a child
        # limit without preexec_fn, which is unsafe in multithreaded parents.
        command = [
            sys.executable,
            "-c",
            "import os, resource, sys; "
            "resource.setrlimit(resource.RLIMIT_AS, (134217728, 134217728)); "
            "os.execv(sys.argv[1], sys.argv[1:])",
            str(binary),
        ]
    return subprocess.run(
        command,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )


def test_range_matches_python(tmp_path: Path) -> None:
    """
    title: Compare all eager range boundaries in one bounded native program.
    parameters:
      tmp_path:
        type: Path
    """
    cases: list[tuple[int, int, int | None, str]] = [
        (0, 4, None, "default-step"),
        (2, 8, 2, "positive-step"),
        (5, 0, -1, "negative-step"),
        (8, 2, -2, "descending-exclusive-stop"),
        (0, 0, None, "equal-default"),
        (7, 7, -1, "equal-descending"),
        (5, 0, 1, "wrong-direction-positive"),
        (0, 5, -1, "wrong-direction-negative"),
        (I32_MAX - 3, I32_MAX, 1, "maximum-stop"),
        (I32_MIN + 3, I32_MIN, -1, "minimum-stop"),
        (I32_MIN, I32_MIN + 1, 1, "minimum-start"),
        (I32_MAX, I32_MAX - 1, -1, "maximum-start"),
        (I32_MAX - 1, I32_MAX, 2, "overshoot-maximum"),
        (I32_MIN + 1, I32_MIN, -2, "overshoot-minimum"),
        (1, I32_MAX, I32_MAX, "maximum-step-overshoot"),
        (I32_MIN, I32_MAX, I32_MAX, "full-width-ascending"),
        (I32_MAX, I32_MIN, I32_MIN, "full-width-descending"),
        (I32_MAX, I32_MAX, I32_MIN, "equal-maximum"),
        (I32_MIN, I32_MIN, I32_MAX, "equal-minimum"),
    ]
    body: list[str] = []
    expected: list[str] = []
    for index, (start, stop, step, label) in enumerate(cases):
        arguments = (
            f"start={i32_expression(start)}, stop={i32_expression(stop)}"
        )
        if step is not None:
            arguments += f", step={i32_expression(step)}"
        body.extend(
            [
                f'print("{label}")',
                f"var values{index}: list[i32] = range({arguments})",
                f"for value in values{index}:\n  print(value)",
            ]
        )
        expected.append(label)
        expected.extend(
            str(value)
            for value in range(start, stop, 1 if step is None else step)
        )
    result = run_helpers(tmp_path, "\n".join(body))
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.splitlines() == expected


@pytest.mark.parametrize("width", [8, 16, 32, 64])
def test_math_preserves_signed_integer_types(
    tmp_path: Path, width: int
) -> None:
    """
    title: Preserve each signed width through arithmetic and boundary cases.
    parameters:
      tmp_path:
        type: Path
      width:
        type: int
    """
    type_ = f"i{width}"
    body = signed_limits(width)
    for helper, arguments in (
        ("abs", "zero - maximum"),
        ("min", "maximum, minimum"),
        ("max", "minimum, maximum"),
        ("clamp", "value=zero, upper=maximum, lower=minimum"),
        ("square", "one"),
    ):
        body += f"assert isinstance(math.{helper}({arguments}), {type_})\n"
    body += (
        "assert math.abs(zero) == zero\n"
        "assert math.abs(one) == one\n"
        "assert math.abs(zero - one) == one\n"
        "assert math.abs(maximum) == maximum\n"
        "assert math.abs(minimum + one) == maximum\n"
        "assert math.min(maximum, minimum) == minimum\n"
        "assert math.min(minimum, maximum) == minimum\n"
        "assert math.min(one, one) == one\n"
        "assert math.max(minimum, maximum) == maximum\n"
        "assert math.max(maximum, minimum) == maximum\n"
        "assert math.max(one, one) == one\n"
        "assert math.clamp(minimum, minimum, maximum) == minimum\n"
        "assert math.clamp(maximum, minimum, maximum) == maximum\n"
        "assert math.clamp(zero, minimum, maximum) == zero\n"
        "assert math.clamp(minimum, maximum, maximum) == maximum\n"
        "assert math.clamp(maximum, minimum, minimum) == minimum\n"
        "assert math.square(zero) == zero\n"
        "assert math.square(zero - one) == one\n"
        "assert wrapping_mul(maximum, maximum) == one\n"
        "assert wrapping_mul(minimum, minimum) == zero\n"
        f"assert math.square(cast(0 - 5, {type_})) == 25\n"
        "print(maximum)\n"
        "print(minimum)\n"
    )
    result = run_helpers(tmp_path, body)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == f"{2 ** (width - 1) - 1}\n{-(2 ** (width - 1))}\n"


@pytest.mark.parametrize("width", [8, 16, 32, 64])
@pytest.mark.parametrize(
    "expression,message",
    [
        (
            "math.abs(minimum)",
            "integer arithmetic result is out of range",
        ),
        *[
            (
                f"math.clamp({value}, maximum, minimum)",
                "clamp() lower bound must not exceed upper bound",
            )
            for value in ("minimum", "zero", "maximum")
        ],
    ],
)
def test_templated_math_checks_each_width(
    tmp_path: Path, width: int, expression: str, message: str
) -> None:
    """
    title: Fail before returning a value for every signed-width specialization.
    parameters:
      tmp_path:
        type: Path
      width:
        type: int
      expression:
        type: str
      message:
        type: str
    """
    result = run_helpers(
        tmp_path, signed_limits(width) + f"print({expression})\nprint(123)"
    )
    assert result.returncode == 1, result.stderr
    assert result.stdout == ""
    failure = parse_exception_output(result.stderr)
    assert failure is not None, result.stderr
    assert failure.message == message
    assert failure.line > 0
    assert failure.col > 0


@pytest.mark.parametrize(
    "statement,message",
    [
        (
            "var values: list[i32] = range(0, 4, 0)",
            "range() step must not be 0",
        ),
        (
            "var values: list[i32] = range(4, 4, 0)",
            "range() step must not be 0",
        ),
        (
            "var values: list[i32] = range(4, 0, 0)",
            "range() step must not be 0",
        ),
        (
            "print(math.abs((0 - 2147483647) - 1))",
            "integer arithmetic result is out of range",
        ),
        (
            "print(math.clamp(0, 1, 0))",
            "clamp() lower bound must not exceed upper bound",
        ),
        (
            "print(math.clamp(1, 1, 0))",
            "clamp() lower bound must not exceed upper bound",
        ),
        (
            "print(math.clamp(2, 1, 0))",
            "clamp() lower bound must not exceed upper bound",
        ),
        (
            "print(math.clamp(0, 2147483647, (0 - 2147483647) - 1))",
            "clamp() lower bound must not exceed upper bound",
        ),
        (
            "print(math.clamp(upper=0, value=1, lower=2))",
            "clamp() lower bound must not exceed upper bound",
        ),
    ],
)
def test_invalid_helper_arguments_fail(
    tmp_path: Path, statement: str, message: str
) -> None:
    """
    title: Reject invalid arguments before producing a wrapped or bogus result.
    parameters:
      tmp_path:
        type: Path
      statement:
        type: str
      message:
        type: str
    """
    result = run_helpers(tmp_path, statement + "\nprint(123)")
    assert result.returncode == 1, result.stderr
    assert result.stdout == ""
    failure = parse_exception_output(result.stderr)
    assert failure is not None, result.stderr
    assert failure.message == message
    assert failure.line > 0
    assert failure.col > 0
