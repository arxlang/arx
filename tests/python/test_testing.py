"""
title: Tests for the Arx compiled test runner.
"""

from __future__ import annotations

import shutil

from pathlib import Path
from textwrap import dedent

import pytest

from arx.testing import ArxTestRunner
from irx import astx
from irx.analysis.module_interfaces import ImportResolver, ParsedModule
from irx.builder.base import CommandResult

HAS_CLANG = shutil.which("clang") is not None


def test_arx_test_runner_lists_matching_tests_across_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    title: Test multi-file discovery with `--list` and -k filtering.
    parameters:
      tmp_path:
        type: Path
      capsys:
        type: pytest.CaptureFixture[str]
    """
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_a.x").write_text(
        dedent(
            """
            fn test_alpha() -> none:
              return none
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (tests_dir / "test_b.x").write_text(
        dedent(
            """
            fn test_beta() -> none:
              return none
            """
        ).lstrip(),
        encoding="utf-8",
    )

    summary = ArxTestRunner(
        paths=(str(tests_dir),),
        list_only=True,
    ).run()

    out = capsys.readouterr().out
    assert "test_a::test_alpha" in out
    assert "test_b::test_beta" in out
    assert summary.exit_code == 0

    capsys.readouterr()
    summary = ArxTestRunner(
        paths=(str(tests_dir),),
        name_filter="alpha",
        list_only=True,
    ).run()

    out = capsys.readouterr().out
    assert "test_a::test_alpha" in out
    assert "test_beta" not in out
    assert summary.exit_code == 0


def test_arx_test_runner_honors_exclude_glob(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    title: Test discovery honors ``exclude`` glob patterns.
    parameters:
      tmp_path:
        type: Path
      capsys:
        type: pytest.CaptureFixture[str]
    """
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_keep.x").write_text(
        "fn test_keep_one() -> none:\n  return none\n",
        encoding="utf-8",
    )
    (tests_dir / "test_skip.x").write_text(
        "fn test_skip_one() -> none:\n  return none\n",
        encoding="utf-8",
    )

    summary = ArxTestRunner(
        paths=(str(tests_dir),),
        exclude=("*/test_skip.x",),
        list_only=True,
    ).run()

    out = capsys.readouterr().out
    assert "test_keep::test_keep_one" in out
    assert "test_skip" not in out
    assert summary.exit_code == 0


def test_arx_test_runner_honors_custom_patterns(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    title: Test discovery honors custom file/function patterns.
    parameters:
      tmp_path:
        type: Path
      capsys:
        type: pytest.CaptureFixture[str]
    """
    tests_dir = tmp_path / "checks"
    tests_dir.mkdir()
    (tests_dir / "check_math.x").write_text(
        dedent(
            """
            fn check_add() -> none:
              return none

            fn ignored() -> none:
              return none
            """
        ).lstrip(),
        encoding="utf-8",
    )

    summary = ArxTestRunner(
        paths=(str(tests_dir),),
        file_pattern="check_*.x",
        function_pattern="check_*",
        list_only=True,
    ).run()

    out = capsys.readouterr().out
    assert "check_math::check_add" in out
    assert "ignored" not in out
    assert summary.exit_code == 0


def test_arx_test_runner_uses_path_qualified_names_for_same_stem_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Test same-stem files in different dirs produce distinct IDs.
    parameters:
      tmp_path:
        type: Path
      capsys:
        type: pytest.CaptureFixture[str]
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    unit_dir = tmp_path / "unit"
    integration_dir = tmp_path / "integration"
    unit_dir.mkdir()
    integration_dir.mkdir()
    (unit_dir / "test_math.x").write_text(
        "fn test_add() -> none:\n  return none\n",
        encoding="utf-8",
    )
    (integration_dir / "test_math.x").write_text(
        "fn test_mul() -> none:\n  return none\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    summary = ArxTestRunner(
        paths=("unit", "integration"),
        list_only=True,
    ).run()

    out = capsys.readouterr().out
    assert "unit/test_math::test_add" in out
    assert "integration/test_math::test_mul" in out
    assert summary.exit_code == 0


def test_arx_test_runner_accepts_none_test_signatures(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Bare and explicit none-return forms are both accepted.
    parameters:
      tmp_path:
        type: Path
      capsys:
        type: pytest.CaptureFixture[str]
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_noneforms.x").write_text(
        dedent(
            """
            fn test_no_return() -> none:
              var x: i32 = 1

            fn test_bare_return() -> none:
              var x: i32 = 1
              return

            fn test_return_none() -> none:
              var x: i32 = 1
              return none
            """
        ).lstrip(),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    summary = ArxTestRunner(list_only=True).run()

    out = capsys.readouterr().out
    assert "tests/test_noneforms::test_no_return" in out
    assert "tests/test_noneforms::test_bare_return" in out
    assert "tests/test_noneforms::test_return_none" in out
    assert summary.exit_code == 0


def test_arx_test_runner_rejects_invalid_test_signature(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    title: Test collection rejects tests with parameters.
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

    summary = ArxTestRunner(paths=(str(entry),)).run()

    assert summary.exit_code == 2
    assert "must take no parameters" in capsys.readouterr().err


def test_arx_test_runner_rejects_non_none_return_type(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    title: Test collection rejects non-none return types with guidance.
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
            fn test_bad() -> i32:
              return 0
            """
        ).lstrip(),
        encoding="utf-8",
    )

    summary = ArxTestRunner(paths=(str(entry),)).run()

    err = capsys.readouterr().err
    assert summary.exit_code == 2
    assert "in v1" not in err
    assert "must return none" in err
    assert "fn test_bad() -> none:" in err


def test_arx_test_runner_rejects_module_scope_variable_declarations(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    title: >-
      Test collection reports unsupported module-scope declarations clearly.
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
            var seed: i32 = 1

            fn test_uses_seed() -> none:
              return none
            """
        ).lstrip(),
        encoding="utf-8",
    )

    summary = ArxTestRunner(paths=(str(entry),)).run()

    err = capsys.readouterr().err
    assert summary.exit_code == 2
    assert "module-scope variable declaration 'seed'" in err
    assert "supported shared top-level items in v1" in err


def test_arx_test_runner_rejects_module_level_executable_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    title: Test collection still rejects true module-level executable code.
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
            fn helper() -> none:
              return none

            helper()

            fn test_after() -> none:
              return none
            """
        ).lstrip(),
        encoding="utf-8",
    )

    summary = ArxTestRunner(paths=(str(entry),)).run()

    err = capsys.readouterr().err
    assert summary.exit_code == 2
    assert "module-level executable code is not supported by `arx test`" in err


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
            resolver: ImportResolver,
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
                type: ImportResolver
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

    summary = ArxTestRunner(paths=(str(entry),)).run()

    assert summary.exit_code == 0
    assert summary.passed == 2
    expected = [
        ["helper", "test_first", "main"],
        ["helper", "test_second", "main"],
    ]
    assert captured_wrappers == expected


def test_arx_test_runner_preserves_supported_shared_declarations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    title: Test wrappers keep supported shared top-level declarations.
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
            extern putchard(value: i32) -> i32

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

    def module_node_name(node: object) -> str:
        """
        title: Return one stable display name for a synthetic wrapper node.
        parameters:
          node:
            type: object
        returns:
          type: str
        """
        prototype = getattr(node, "prototype", None)
        if prototype is not None and hasattr(prototype, "name"):
            return str(prototype.name)
        name = getattr(node, "name", None)
        if isinstance(name, str):
            return name
        return type(node).__name__

    class DummyBuilder:
        """
        title: Dummy builder for declaration-preservation coverage.
        """

        output_file = ""

        def build_modules(
            self,
            root: ParsedModule,
            resolver: ImportResolver,
            output_file: str,
            link: bool,
            link_mode: str,
        ) -> None:
            """
            title: Record synthetic wrapper contents with shared declarations.
            parameters:
              root:
                type: ParsedModule
              resolver:
                type: ImportResolver
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
            captured_wrappers.append(
                [module_node_name(node) for node in root.ast.nodes]
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

    summary = ArxTestRunner(paths=(str(entry),)).run()

    assert summary.exit_code == 0
    expected = [
        ["putchard", "helper", "test_first", "main"],
        ["putchard", "helper", "test_second", "main"],
    ]
    assert captured_wrappers == expected


def test_arx_test_runner_supports_package_relative_imports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    title: Test runner build flow supports package files with relative imports.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    src_dir = tmp_path / "src"
    package_dir = src_dir / "samplepkg"
    tests_dir = tmp_path / "tests"
    package_dir.mkdir(parents=True)
    tests_dir.mkdir()

    (tmp_path / ".arxproject.toml").write_text(
        '[project]\nname = "samplepkg"\nversion = "0.1.0"\n'
        '[environment]\nkind = "conda"\nname = "samplepkg"\n'
        '[build]\nsrc_dir = "src"\n\n',
        encoding="utf-8",
    )
    (package_dir / "__init__.x").write_text(
        dedent(
            """
            import addtwo from .core
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (package_dir / "stats.x").write_text(
        dedent(
            """
            fn sum2() -> i32:
              return 2
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (package_dir / "core.x").write_text(
        dedent(
            """
            import sum2 from .stats

            fn addtwo() -> i32:
              return sum2()
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (tests_dir / "test_core.x").write_text(
        dedent(
            """
            import addtwo from samplepkg.core

            fn test_addtwo() -> none:
              addtwo()
              return none
            """
        ).lstrip(),
        encoding="utf-8",
    )

    class DummyBuilder:
        """
        title: Dummy builder that validates package import resolution.
        """

        output_file = ""

        def build_modules(
            self,
            root: ParsedModule,
            resolver: ImportResolver,
            output_file: str,
            link: bool,
            link_mode: str,
        ) -> None:
            """
            title: Resolve package imports during test wrapper build.
            parameters:
              root:
                type: ParsedModule
              resolver:
                type: ImportResolver
              output_file:
                type: str
              link:
                type: bool
              link_mode:
                type: str
            """
            del link
            del link_mode
            self.output_file = output_file
            assert isinstance(root.ast, astx.Module)
            root_import = next(
                node
                for node in root.ast.nodes
                if isinstance(node, astx.ImportFromStmt)
            )
            resolved_core = resolver(root.key, root_import, "samplepkg.core")
            assert resolved_core.key == "samplepkg.core"
            nested_import = next(
                node
                for node in resolved_core.ast.nodes
                if isinstance(node, astx.ImportFromStmt)
            )
            resolved_stats = resolver(
                resolved_core.key,
                nested_import,
                ".stats",
            )
            assert resolved_stats.key == "samplepkg.stats"

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

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("arx.testing.ArxBuilder", DummyBuilder)

    summary = ArxTestRunner().run()

    assert summary.exit_code == 0
    assert summary.passed == 1


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
            resolver: ImportResolver,
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
                type: ImportResolver
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

    summary = ArxTestRunner(paths=(str(entry),)).run()

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

    summary = ArxTestRunner(paths=(str(entry),)).run()

    assert summary.exit_code == 1
    assert summary.passed == 1
    assert summary.failed == 1
    failure = summary.results[1].assertion_failure
    assert failure is not None
    assert failure.source == str(entry)
    assert failure.message == "bad\nmessage|with pipe\\slash"
