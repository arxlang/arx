"""
title: Tests for the Arx compiled test runner.
"""

from __future__ import annotations

import shutil

from pathlib import Path
from textwrap import dedent

import pytest

from arx.testing import ArxTestRunner
from irx.analysis.module_interfaces import ParsedModule
from irx.builder.base import CommandResult

HAS_CLANG = shutil.which("clang") is not None


def test_arx_test_runner_lists_matching_tests(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    title: Test `--list` style discovery and substring filtering.
    parameters:
      tmp_path:
        type: Path
      capsys:
        type: pytest.CaptureFixture[str]
    """
    entry = tmp_path / "main.x"
    entry.write_text(
        dedent(
            """
            fn helper() -> i32:
              return 1

            fn test_alpha() -> none:
              return none

            fn test_beta() -> none:
              return none
            """
        ).lstrip(),
        encoding="utf-8",
    )

    summary = ArxTestRunner(
        entry_file=str(entry),
        name_filter="alpha",
        list_only=True,
    ).run()

    out = capsys.readouterr().out
    assert "test_alpha" in out
    assert "test_beta" not in out
    assert summary.exit_code == 0


def test_arx_test_runner_rejects_invalid_test_signature(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    title: Test collection rejects tests with parameters in v1.
    parameters:
      tmp_path:
        type: Path
      capsys:
        type: pytest.CaptureFixture[str]
    """
    entry = tmp_path / "main.x"
    entry.write_text(
        dedent(
            """
            fn test_bad(value: i32) -> none:
              return none
            """
        ).lstrip(),
        encoding="utf-8",
    )

    summary = ArxTestRunner(entry_file=str(entry)).run()

    assert summary.exit_code == 2
    assert "must not accept parameters" in capsys.readouterr().err


def test_arx_test_runner_builds_one_wrapper_per_selected_test(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    title: Test wrapper generation keeps only one selected test plus main.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    entry = tmp_path / "main.x"
    entry.write_text(
        dedent(
            """
            fn helper() -> i32:
              return 1

            fn test_first() -> none:
              helper()
              return none

            fn test_second() -> none:
              helper()
              return none
            """
        ).lstrip(),
        encoding="utf-8",
    )

    captured_wrappers: list[list[str]] = []

    class DummyBuilder:
        """
        title: Dummy builder for test-runner orchestration coverage.
        """

        output_file = ""

        def build_modules(
            self,
            root: ParsedModule,
            resolver: object,
            output_file: str,
            link: bool,
            link_mode: str,
        ) -> None:
            """
            title: Record synthetic wrapper contents.
            parameters:
              root:
                type: ParsedModule
              resolver:
                type: object
              output_file:
                type: str
              link:
                type: bool
              link_mode:
                type: str
            """
            del resolver
            del link
            del link_mode
            self.output_file = output_file
            module = root.ast
            captured_wrappers.append(
                [
                    getattr(node.prototype, "name", type(node).__name__)
                    for node in module.nodes
                ]
            )

        def run(
            self,
            *,
            capture_stderr: bool = True,
            raise_on_error: bool = True,
        ) -> CommandResult:
            """
            title: Return a passing command result.
            parameters:
              capture_stderr:
                type: bool
              raise_on_error:
                type: bool
            returns:
              type: CommandResult
            """
            del capture_stderr
            del raise_on_error
            return CommandResult(
                stdout="",
                stderr="",
                returncode=0,
                command=[self.output_file],
            )

    monkeypatch.setattr("arx.testing.ArxBuilder", DummyBuilder)

    summary = ArxTestRunner(entry_file=str(entry)).run()

    assert summary.exit_code == 0
    assert summary.passed == 2
    expected = [
        ["helper", "test_first", "main"],
        ["helper", "test_second", "main"],
    ]
    assert captured_wrappers == expected


def test_arx_test_runner_reports_machine_readable_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    title: Test failure rendering decodes escaped IRx assertion reports.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
      capsys:
        type: pytest.CaptureFixture[str]
    """
    entry = tmp_path / "main.x"
    entry.write_text(
        dedent(
            """
            fn test_fail() -> none:
              return none
            """
        ).lstrip(),
        encoding="utf-8",
    )

    class DummyBuilder:
        """
        title: Dummy builder that returns one assertion failure report.
        """

        output_file = ""

        def build_modules(
            self,
            root: object,
            resolver: object,
            output_file: str,
            link: bool,
            link_mode: str,
        ) -> None:
            """
            title: Capture the output path and ignore compile inputs.
            parameters:
              root:
                type: object
              resolver:
                type: object
              output_file:
                type: str
              link:
                type: bool
              link_mode:
                type: str
            """
            del root
            del resolver
            del link
            del link_mode
            self.output_file = output_file

        def run(
            self,
            *,
            capture_stderr: bool = True,
            raise_on_error: bool = True,
        ) -> CommandResult:
            """
            title: Return one failing command result with escaped protocol.
            parameters:
              capture_stderr:
                type: bool
              raise_on_error:
                type: bool
            returns:
              type: CommandResult
            """
            del capture_stderr
            del raise_on_error
            return CommandResult(
                stdout="",
                stderr=(
                    "ARX_ASSERT_FAIL|tests/main.x|12|3|"
                    "bad\\nmessage\\pwith pipe\\\\slash\n"
                ),
                returncode=1,
                command=[self.output_file],
            )

    monkeypatch.setattr("arx.testing.ArxBuilder", DummyBuilder)

    summary = ArxTestRunner(entry_file=str(entry)).run()

    out = capsys.readouterr().out
    assert summary.exit_code == 1
    assert summary.failed == 1
    assert "tests/main.x:12:3: bad" in out
    assert "message|with pipe\\slash" in out


@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for arx test")
def test_arx_test_runner_end_to_end_with_assertions(
    tmp_path: Path,
) -> None:
    """
    title: Test end-to-end compiled execution for passing and failing asserts.
    parameters:
      tmp_path:
        type: Path
    """
    entry = tmp_path / "main.x"
    entry.write_text(
        dedent(
            r"""
            fn helper(value: i32) -> i32:
              return value

            fn test_pass() -> none:
              assert helper(1) == 1
              return none

            fn test_fail() -> none:
              assert helper(2) == 3, "bad\nmessage|with pipe\\slash"
              return none
            """
        ).lstrip(),
        encoding="utf-8",
    )

    summary = ArxTestRunner(entry_file=str(entry)).run()

    assert summary.exit_code == 1
    assert summary.passed == 1
    assert summary.failed == 1
    failure = summary.results[1].assertion_failure
    assert failure is not None
    assert failure.source == str(entry)
    assert failure.message == "bad\nmessage|with pipe\\slash"
