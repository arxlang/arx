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
from irx.builder.runtime.assertions import parse_assert_failure_output
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
    llvm.parse_assembly(builder.translate_modules(root, resolver)).verify()
    binary = tmp_path / "helpers"
    builder.build_modules(root, resolver, str(binary))

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


@pytest.mark.parametrize(
    "start,stop,step",
    [
        pytest.param(0, 4, None, id="default-step"),
        pytest.param(2, 8, 2, id="positive-step"),
        pytest.param(5, 0, -1, id="negative-step"),
        pytest.param(8, 2, -2, id="descending-exclusive-stop"),
        pytest.param(0, 0, None, id="equal-default"),
        pytest.param(7, 7, -1, id="equal-descending"),
        pytest.param(5, 0, 1, id="wrong-direction-positive"),
        pytest.param(0, 5, -1, id="wrong-direction-negative"),
        pytest.param(I32_MAX - 3, I32_MAX, 1, id="maximum-stop"),
        pytest.param(I32_MIN + 3, I32_MIN, -1, id="minimum-stop"),
        pytest.param(I32_MIN, I32_MIN + 1, 1, id="minimum-start"),
        pytest.param(I32_MAX, I32_MAX - 1, -1, id="maximum-start"),
        pytest.param(I32_MAX - 1, I32_MAX, 2, id="overshoot-maximum"),
        pytest.param(I32_MIN + 1, I32_MIN, -2, id="overshoot-minimum"),
        pytest.param(1, I32_MAX, I32_MAX, id="maximum-step-overshoot"),
        pytest.param(I32_MIN, I32_MAX, I32_MAX, id="full-width-ascending"),
        pytest.param(I32_MAX, I32_MIN, I32_MIN, id="full-width-descending"),
        pytest.param(I32_MAX, I32_MAX, I32_MIN, id="equal-maximum"),
        pytest.param(I32_MIN, I32_MIN, I32_MAX, id="equal-minimum"),
    ],
)
def test_range_matches_python(
    tmp_path: Path, start: int, stop: int, step: int | None
) -> None:
    """
    title: Compare complete eager i32 results to Python exclusive-stop ranges.
    parameters:
      tmp_path:
        type: Path
      start:
        type: int
      stop:
        type: int
      step:
        type: int | None
    """
    arguments = f"start={i32_expression(start)}, stop={i32_expression(stop)}"
    if step is not None:
        arguments += f", step={i32_expression(step)}"
    result = run_helpers(
        tmp_path,
        f"var values: list[i32] = range({arguments})\n"
        "for value in values:\n"
        "  print(value)",
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    expected = range(start, stop, 1 if step is None else step)
    assert result.stdout == "".join(f"{value}\n" for value in expected)


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
            "abs() result is out of range for i32",
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
    failure = parse_assert_failure_output(result.stderr)
    assert failure is not None, result.stderr
    assert failure.message == message
    assert failure.line > 0
    assert failure.col > 0
