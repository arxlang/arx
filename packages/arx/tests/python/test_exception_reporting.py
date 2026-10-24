"""
title: Compiled test runner consumption of typed exception diagnostics.
"""

from pathlib import Path

import pytest

from arx.testing import ArxTestRunner, DiscoveredTestCase
from irx.builder.base import CommandResult


def test_test_runner_preserves_exception_chain(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    title: Report a failure chain without losing the root exception category.
    parameters:
      tmp_path:
        type: Path
      capsys:
        type: pytest.CaptureFixture[str]
    """
    runner = ArxTestRunner(paths=(str(tmp_path),))
    case = DiscoveredTestCase("test_failure", "test_failure", tmp_path / "a.x")
    stderr = (
        "ARX_EXCEPTION|cause|IO|OSError|file.x|3|5|read failed\n"
        "ARX_EXCEPTION|root|USER|ConfigError|app.x|8|3|bad configuration\n"
        "ARX_EXCEPTION_FRAME|main.x|2|3\n"
    )
    result = runner._build_execution_result(
        case, CommandResult("", stderr, 1, ("program",)), None
    )
    assert not result.passed
    assert result.exception is not None
    assert result.exception.message == "bad configuration"
    assert result.exception.related[0].message == "read failed"
    runner._print_test_result(result)
    output = capsys.readouterr().out
    assert "ConfigError: bad configuration" in output
    assert "OSError: read failed" in output
    assert "at main.x:2:3" in output


def test_uncaught_assertion_keeps_assertion_classification(
    tmp_path: Path,
) -> None:
    """
    title: Classify an assertion after it reaches the host boundary.
    parameters:
      tmp_path:
        type: Path
    """
    runner = ArxTestRunner(paths=(str(tmp_path),))
    case = DiscoveredTestCase("test_failure", "test_failure", tmp_path / "a.x")
    stderr = (
        "ARX_EXCEPTION|root|ARX-RUNTIME-ASSERTION-001|AssertionError|"
        "test.x|5|3|expected true\n"
    )
    result = runner._build_execution_result(
        case, CommandResult("", stderr, 1, ("program",)), None
    )
    assert result.exception is not None
    assert result.assertion_failure is not None
    assert result.assertion_failure.message == "expected true"
