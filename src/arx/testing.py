"""
title: Arx compiled test runner helpers.
"""

from __future__ import annotations

import fnmatch
import importlib
import sys
import tempfile

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from irx import astx
from irx.analysis.module_interfaces import ParsedModule
from irx.builder.base import CommandResult

from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.main import FileImportResolver, get_module_name_from_file_path
from arx.parser import Parser

DEFAULT_TEST_PATHS: tuple[str, ...] = ("tests",)
DEFAULT_TEST_FILE_PATTERN = "test_*.x"
DEFAULT_TEST_FUNCTION_PATTERN = "test_*"
ASSERT_FAILURE_PREFIX = "ARX_ASSERT_FAIL"
ASSERT_FAILURE_FIELD_COUNT = 5

ALLOWED_SHARED_TOP_LEVEL_NODES = (
    astx.ClassDefStmt,
    astx.FunctionPrototype,
    astx.ImportFromStmt,
    astx.ImportStmt,
)
SUPPORTED_SHARED_TOP_LEVEL_SUMMARY = (
    "imports, extern declarations, class declarations, and helper functions"
)

LinkMode = Literal["auto", "pie", "no-pie"]


@dataclass(frozen=True)
class AssertionFailureReport:
    """
    title: Parsed machine-readable assertion failure report.
    attributes:
      source:
        type: str
      line:
        type: int
      col:
        type: int
      message:
        type: str
    """

    source: str
    line: int
    col: int
    message: str


@dataclass(frozen=True)
class DiscoveredTestCase:
    """
    title: One discovered compiled test case.
    attributes:
      name:
        type: str
      function_name:
        type: str
      file:
        type: Path
    """

    name: str
    function_name: str
    file: Path


@dataclass(frozen=True)
class TestExecutionResult:
    """
    title: Result from running one compiled test case.
    attributes:
      name:
        type: str
      passed:
        type: bool
      returncode:
        type: int
      stdout:
        type: str
      stderr:
        type: str
      assertion_failure:
        type: AssertionFailureReport | None
      artifact_dir:
        type: Path | None
    """

    name: str
    passed: bool
    returncode: int
    stdout: str
    stderr: str
    assertion_failure: AssertionFailureReport | None
    artifact_dir: Path | None = None


@dataclass(frozen=True)
class TestRunSummary:
    """
    title: Summary for one `arx test` session.
    attributes:
      selected:
        type: int
      executed:
        type: int
      passed:
        type: int
      failed:
        type: int
      exit_code:
        type: int
      results:
        type: tuple[TestExecutionResult, Ellipsis]
    """

    selected: int
    executed: int
    passed: int
    failed: int
    exit_code: int
    results: tuple[TestExecutionResult, ...]


class TestRunError(RuntimeError):
    """
    title: Internal error raised while collecting or running compiled tests.
    attributes:
      artifact_dir:
        type: Path | None
    """

    artifact_dir: Path | None

    def __init__(
        self,
        message: str,
        artifact_dir: Path | None = None,
    ) -> None:
        """
        title: Initialize TestRunError.
        parameters:
          message:
            type: str
          artifact_dir:
            type: Path | None
        """
        super().__init__(message)
        self.artifact_dir: Path | None = artifact_dir


def _decode_assert_failure_field(text: str) -> str:
    """
    title: Decode one escaped assertion failure protocol field.
    parameters:
      text:
        type: str
    returns:
      type: str
    """
    decoded: list[str] = []
    index = 0
    escapes = {
        "\\": "\\",
        "n": "\n",
        "p": "|",
        "r": "\r",
        "t": "\t",
    }

    while index < len(text):
        char = text[index]
        if char != "\\":
            decoded.append(char)
            index += 1
            continue

        if index + 1 >= len(text):
            decoded.append("\\")
            break

        escaped = text[index + 1]
        replacement = escapes.get(escaped)
        if replacement is None:
            decoded.append("\\")
            decoded.append(escaped)
        else:
            decoded.append(replacement)
        index += 2

    return "".join(decoded)


def _parse_assert_failure_line(line: str) -> AssertionFailureReport | None:
    """
    title: Parse one machine-readable assertion failure line.
    parameters:
      line:
        type: str
    returns:
      type: AssertionFailureReport | None
    """
    stripped = line.strip()
    prefix = f"{ASSERT_FAILURE_PREFIX}|"
    if not stripped.startswith(prefix):
        return None

    parts = stripped.split("|", ASSERT_FAILURE_FIELD_COUNT - 1)
    if len(parts) != ASSERT_FAILURE_FIELD_COUNT:
        return None

    _, source, line_text, col_text, message = parts
    try:
        line_number = int(line_text)
        col_number = int(col_text)
    except ValueError:
        return None

    return AssertionFailureReport(
        source=_decode_assert_failure_field(source),
        line=line_number,
        col=col_number,
        message=_decode_assert_failure_field(message),
    )


def _parse_assert_failure_output_fallback(
    stderr: str,
) -> AssertionFailureReport | None:
    """
    title: Parse the first assertion failure from stderr using fallback logic.
    parameters:
      stderr:
        type: str
    returns:
      type: AssertionFailureReport | None
    """
    for line in stderr.splitlines():
        parsed = _parse_assert_failure_line(line)
        if parsed is not None:
            return parsed
    return None


def _parse_assert_failure_output(
    stderr: str,
) -> AssertionFailureReport | None:
    """
    title: Parse one assertion failure report from stderr.
    parameters:
      stderr:
        type: str
    returns:
      type: AssertionFailureReport | None
    """
    try:
        runtime_module = importlib.import_module(
            "irx.builder.runtime.assertions"
        )
    except ImportError:
        return _parse_assert_failure_output_fallback(stderr)

    parsed = runtime_module.parse_assert_failure_output(stderr)
    if parsed is None:
        return None

    return AssertionFailureReport(
        source=parsed.source,
        line=parsed.line,
        col=parsed.col,
        message=parsed.message,
    )


def _sanitize_name(text: str) -> str:
    """
    title: Convert one free-form test name into a file-safe identifier.
    parameters:
      text:
        type: str
    returns:
      type: str
    """
    sanitized = "".join(
        char if char.isalnum() else "_" for char in text
    ).strip("_")
    return sanitized or "test"


@dataclass
class ArxTestRunner:
    """
    title: Python-side compiled test runner for Arx.
    attributes:
      paths:
        type: tuple[str, Ellipsis]
      exclude:
        type: tuple[str, Ellipsis]
      file_pattern:
        type: str
      function_pattern:
        type: str
      name_filter:
        type: str
      fail_fast:
        type: bool
      keep_artifacts:
        type: bool
      list_only:
        type: bool
      link_mode:
        type: LinkMode
    """

    paths: tuple[str, ...] = DEFAULT_TEST_PATHS
    exclude: tuple[str, ...] = ()
    file_pattern: str = DEFAULT_TEST_FILE_PATTERN
    function_pattern: str = DEFAULT_TEST_FUNCTION_PATTERN
    name_filter: str = ""
    fail_fast: bool = False
    keep_artifacts: bool = False
    list_only: bool = False
    link_mode: LinkMode = "auto"

    def _parse_module(self, file: Path) -> astx.Module:
        """
        title: Parse one test source file into an IRx-backed module.
        parameters:
          file:
            type: Path
        returns:
          type: astx.Module
        """
        if not file.is_file():
            raise TestRunError(f"test entry file not found: {file}")

        ArxIO.file_to_buffer(str(file))
        module_name = get_module_name_from_file_path(str(file))
        module = Parser().parse(Lexer().lex(), module_name)
        if not isinstance(module, astx.Module):
            raise TestRunError(
                f"test file did not parse into a module: {file}"
            )
        return module

    def _display_path_prefix(self, file: Path) -> str:
        """
        title: Build a path-qualified display prefix for one test file.
        parameters:
          file:
            type: Path
        returns:
          type: str
        """
        try:
            rel = file.resolve().relative_to(Path.cwd().resolve())
        except ValueError:
            rel = Path(file)
        if rel.suffix:
            rel = rel.with_suffix("")
        return rel.as_posix()

    def _match_exclude(self, candidate: Path) -> bool:
        """
        title: Return whether one candidate file matches an exclude glob.
        parameters:
          candidate:
            type: Path
        returns:
          type: bool
        """
        if not self.exclude:
            return False

        candidates = {candidate.as_posix(), candidate.name}
        try:
            rel = candidate.resolve().relative_to(Path.cwd().resolve())
        except ValueError:
            rel = None
        if rel is not None:
            candidates.add(rel.as_posix())

        for pattern in self.exclude:
            for target in candidates:
                if fnmatch.fnmatchcase(target, pattern):
                    return True
        return False

    def _discover_test_files(self) -> tuple[Path, ...]:
        """
        title: Discover the ordered set of candidate test source files.
        returns:
          type: tuple[Path, Ellipsis]
        """
        discovered: list[Path] = []
        seen: set[Path] = set()

        for entry in self.paths:
            entry_path = Path(entry)
            if entry_path.is_file():
                candidates: list[Path] = [entry_path]
            elif entry_path.is_dir():
                candidates = sorted(entry_path.rglob(self.file_pattern))
            else:
                raise TestRunError(f"test path not found: {entry}")

            for candidate in candidates:
                resolved = candidate.resolve()
                if resolved in seen:
                    continue
                if self._match_exclude(candidate):
                    continue
                seen.add(resolved)
                discovered.append(candidate)

        return tuple(discovered)

    def _validate_test_function(self, node: astx.FunctionDef) -> None:
        """
        title: Validate the test-function signature contract.
        parameters:
          node:
            type: astx.FunctionDef
        """
        name = str(node.prototype.name)
        arg_count = len(node.prototype.args.nodes)
        if arg_count != 0:
            raise TestRunError(
                f"test '{name}' must take no parameters (got {arg_count})."
            )
        return_type = node.prototype.return_type
        if not isinstance(return_type, astx.NoneType):
            got = type(return_type).__name__
            raise TestRunError(
                f"test '{name}' must return none (got '{got}'); "
                f"declare it as `fn {name}() -> none:`."
            )

    def _top_level_node_error(self, node: astx.AST) -> str:
        """
        title: Build one runner error for an unsupported top-level node.
        parameters:
          node:
            type: astx.AST
        returns:
          type: str
        """
        if isinstance(node, astx.VariableDeclaration):
            return (
                "module-scope variable declaration "
                f"'{node.name}' is not supported by `arx test` yet; "
                "supported shared top-level items in v1 are "
                f"{SUPPORTED_SHARED_TOP_LEVEL_SUMMARY}."
            )
        return "module-level executable code is not supported by `arx test`"

    def _discover_tests(
        self,
        module: astx.Module,
        file: Path,
    ) -> tuple[DiscoveredTestCase, ...]:
        """
        title: Discover valid test functions from one parsed module.
        parameters:
          module:
            type: astx.Module
          file:
            type: Path
        returns:
          type: tuple[DiscoveredTestCase, Ellipsis]
        """
        discovered: list[DiscoveredTestCase] = []
        seen_names: set[str] = set()
        display_prefix = self._display_path_prefix(file)

        for node in module.nodes:
            if isinstance(node, astx.FunctionDef):
                name = str(node.prototype.name)
                if name == "main":
                    raise TestRunError(
                        "`arx test` entry files must not define `main`."
                    )
                if not fnmatch.fnmatchcase(name, self.function_pattern):
                    continue
                if name in seen_names:
                    raise TestRunError(
                        f"duplicate test function '{name}' in {file}"
                    )
                self._validate_test_function(node)
                seen_names.add(name)
                discovered.append(
                    DiscoveredTestCase(
                        name=f"{display_prefix}::{name}",
                        function_name=name,
                        file=file,
                    )
                )
                continue

            if isinstance(node, ALLOWED_SHARED_TOP_LEVEL_NODES):
                continue

            raise TestRunError(self._top_level_node_error(node))

        return tuple(discovered)

    def collect_tests(self) -> tuple[DiscoveredTestCase, ...]:
        """
        title: Collect and filter discovered tests across configured paths.
        returns:
          type: tuple[DiscoveredTestCase, Ellipsis]
        """
        files = self._discover_test_files()
        discovered: list[DiscoveredTestCase] = []
        seen_display_names: set[str] = set()

        for file in files:
            module = self._parse_module(file)
            for case in self._discover_tests(module, file):
                if case.name in seen_display_names:
                    raise TestRunError(
                        f"duplicate test name '{case.name}' "
                        f"across discovered files"
                    )
                seen_display_names.add(case.name)
                discovered.append(case)

        if not discovered:
            raise TestRunError(
                f"no tests matching '{self.function_pattern}' were found "
                f"in paths {list(self.paths)} "
                f"(file pattern: {self.file_pattern!r})"
            )

        if not self.name_filter:
            return tuple(discovered)

        filtered = tuple(
            test for test in discovered if self.name_filter in test.name
        )
        if filtered:
            return filtered

        raise TestRunError(
            f"no tests matched -k {self.name_filter!r} "
            f"in paths {list(self.paths)}"
        )

    def _build_wrapper_main(self, test_name: str) -> astx.FunctionDef:
        """
        title: Build the generated wrapper `main()` for one selected test.
        parameters:
          test_name:
            type: str
        returns:
          type: astx.FunctionDef
        """
        prototype = astx.FunctionPrototype(
            "main",
            astx.Arguments(),
            astx.Int32(),
        )
        body = astx.Block()
        body.nodes.append(astx.FunctionCall(test_name, []))
        body.nodes.append(astx.FunctionReturn(astx.LiteralInt32(0)))
        return astx.FunctionDef(prototype, body)

    def _build_wrapper_module(
        self,
        file: Path,
        function_name: str,
    ) -> astx.Module:
        """
        title: Build one synthetic module that runs exactly one selected test.
        parameters:
          file:
            type: Path
          function_name:
            type: str
        returns:
          type: astx.Module
        """
        module = self._parse_module(file)
        wrapper_name = (
            f"{module.name}__arx_test__{_sanitize_name(function_name)}"
        )
        wrapper = astx.Module(wrapper_name)
        selected_found = False

        for node in module.nodes:
            if isinstance(node, astx.FunctionDef):
                name = str(node.prototype.name)
                if name == "main":
                    raise TestRunError(
                        "`arx test` entry files must not define `main`."
                    )
                if fnmatch.fnmatchcase(name, self.function_pattern):
                    self._validate_test_function(node)
                    if name != function_name:
                        continue
                    selected_found = True
                wrapper.nodes.append(node)
                continue

            if isinstance(node, ALLOWED_SHARED_TOP_LEVEL_NODES):
                wrapper.nodes.append(node)
                continue

            raise TestRunError(self._top_level_node_error(node))

        if not selected_found:
            raise TestRunError(f"unknown test '{function_name}' in {file}")

        wrapper.nodes.append(self._build_wrapper_main(function_name))
        return wrapper

    def _write_wrapper_artifact(
        self,
        module: astx.Module,
        artifact_dir: Path,
    ) -> None:
        """
        title: Write a readable wrapper-module artifact for debugging.
        parameters:
          module:
            type: astx.Module
          artifact_dir:
            type: Path
        """
        text: str
        try:
            text = module.to_json()
        except Exception:
            try:
                text = repr(module)
            except Exception:
                text = str(module)
        (artifact_dir / "wrapper.ast.txt").write_text(
            text,
            encoding="utf-8",
        )

    def _compile_and_run_test(
        self,
        test_case: DiscoveredTestCase,
    ) -> TestExecutionResult:
        """
        title: Compile and execute one selected test case in isolation.
        parameters:
          test_case:
            type: DiscoveredTestCase
        returns:
          type: TestExecutionResult
        """
        temp_dir: tempfile.TemporaryDirectory[str] | None = None
        sanitized_name = _sanitize_name(test_case.name)

        if self.keep_artifacts:
            artifact_dir = Path(
                tempfile.mkdtemp(prefix=f"arx-test-{sanitized_name}-")
            )
        else:
            temp_dir = tempfile.TemporaryDirectory(
                prefix=f"arx-test-{sanitized_name}-"
            )
            artifact_dir = Path(temp_dir.name)

        try:
            module = self._build_wrapper_module(
                test_case.file,
                test_case.function_name,
            )
            self._write_wrapper_artifact(module, artifact_dir)

            output_file = artifact_dir / sanitized_name
            builder = ArxBuilder()
            root = ParsedModule(
                key=module.name,
                ast=module,
                display_name=str(test_case.file),
                origin=str(test_case.file.resolve()),
            )
            resolver = FileImportResolver((str(test_case.file),))
            builder.build_modules(
                root,
                resolver,
                output_file=str(output_file),
                link=True,
                link_mode=self.link_mode,
            )
            command_result = builder.run(
                capture_stderr=True,
                raise_on_error=False,
            )
        except TestRunError:
            raise
        except Exception as err:
            artifact_ref = artifact_dir if self.keep_artifacts else None
            raise TestRunError(
                f"failed to build test '{test_case.name}': {err}",
                artifact_dir=artifact_ref,
            ) from err
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()

        return self._build_execution_result(
            test_case=test_case,
            command_result=command_result,
            artifact_dir=artifact_dir if self.keep_artifacts else None,
        )

    def _build_execution_result(
        self,
        test_case: DiscoveredTestCase,
        command_result: CommandResult,
        artifact_dir: Path | None,
    ) -> TestExecutionResult:
        """
        title: Convert one command result into a stable test result object.
        parameters:
          test_case:
            type: DiscoveredTestCase
          command_result:
            type: CommandResult
          artifact_dir:
            type: Path | None
        returns:
          type: TestExecutionResult
        """
        assertion_failure = _parse_assert_failure_output(command_result.stderr)
        return TestExecutionResult(
            name=test_case.name,
            passed=command_result.success,
            returncode=command_result.returncode,
            stdout=command_result.stdout,
            stderr=command_result.stderr,
            assertion_failure=assertion_failure,
            artifact_dir=artifact_dir,
        )

    def _print_test_result(self, result: TestExecutionResult) -> None:
        """
        title: Print one human-readable test result line.
        parameters:
          result:
            type: TestExecutionResult
        """
        if result.passed:
            print(f"PASS {result.name}")
            return

        print(f"FAIL {result.name}")
        failure = result.assertion_failure
        if failure is not None:
            message_lines = failure.message.splitlines() or [""]
            print(
                f"  {failure.source}:{failure.line}:{failure.col}: "
                f"{message_lines[0]}"
            )
            for extra_line in message_lines[1:]:
                print(f"  {extra_line}")
        else:
            print(f"  exit code: {result.returncode}")
            if result.stderr.strip():
                print("  stderr:")
                for line in result.stderr.rstrip().splitlines():
                    print(f"    {line}")
            if result.stdout.strip():
                print("  stdout:")
                for line in result.stdout.rstrip().splitlines():
                    print(f"    {line}")

        if result.artifact_dir is not None:
            print(f"  artifacts: {result.artifact_dir}")

    def _print_summary(self, summary: TestRunSummary) -> None:
        """
        title: Print a concise human-readable session summary.
        parameters:
          summary:
            type: TestRunSummary
        """
        skipped = summary.selected - summary.executed
        parts = [
            f"{summary.passed} passed",
            f"{summary.failed} failed",
        ]
        if skipped:
            parts.append(f"{skipped} not run")
        print(", ".join(parts))

    def run(self) -> TestRunSummary:
        """
        title: Collect, compile, and execute the configured test selection.
        returns:
          type: TestRunSummary
        """
        try:
            selected_tests = self.collect_tests()
        except TestRunError as err:
            print(f"ERROR: {err}", file=sys.stderr)
            if err.artifact_dir is not None:
                print(
                    f"ERROR: artifacts kept in {err.artifact_dir}",
                    file=sys.stderr,
                )
            return TestRunSummary(
                selected=0,
                executed=0,
                passed=0,
                failed=0,
                exit_code=2,
                results=(),
            )

        if self.list_only:
            for test_case in selected_tests:
                print(test_case.name)
            return TestRunSummary(
                selected=len(selected_tests),
                executed=0,
                passed=0,
                failed=0,
                exit_code=0,
                results=(),
            )

        results: list[TestExecutionResult] = []
        for test_case in selected_tests:
            try:
                result = self._compile_and_run_test(test_case)
            except TestRunError as err:
                print(f"ERROR: {err}", file=sys.stderr)
                if err.artifact_dir is not None:
                    print(
                        f"ERROR: artifacts kept in {err.artifact_dir}",
                        file=sys.stderr,
                    )
                return TestRunSummary(
                    selected=len(selected_tests),
                    executed=len(results),
                    passed=sum(item.passed for item in results),
                    failed=sum(not item.passed for item in results),
                    exit_code=2,
                    results=tuple(results),
                )

            results.append(result)
            self._print_test_result(result)
            if self.fail_fast and not result.passed:
                break

        passed_count = sum(item.passed for item in results)
        failed_count = sum(not item.passed for item in results)
        exit_code = 0 if failed_count == 0 else 1
        summary = TestRunSummary(
            selected=len(selected_tests),
            executed=len(results),
            passed=passed_count,
            failed=failed_count,
            exit_code=exit_code,
            results=tuple(results),
        )
        self._print_summary(summary)
        return summary
