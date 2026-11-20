# ruff: noqa: RUF001
"""
title: AIX CLI tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aix.cli import app

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    """
    title: Verify CLI help.
    parameters:
      capsys: Fixture capturing standard output and error streams.
    """
    with pytest.raises(SystemExit) as excinfo:
        app(["--help"])
    assert excinfo.value.code == 0
    assert "AIX compiler frontend" in capsys.readouterr().out


def test_cli_show_tokens(capsys: pytest.CaptureFixture[str]) -> None:
    """
    title: Verify CLI token display.
    parameters:
      capsys: Fixture capturing standard output and error streams.
    """
    app(["--show-tokens", str(EXAMPLES / "hello.aix")])
    assert "define" in capsys.readouterr().out


def test_cli_show_ast(capsys: pytest.CaptureFixture[str]) -> None:
    """
    title: Verify CLI AST display.
    parameters:
      capsys: Fixture capturing standard output and error streams.
    """
    app(["--show-ast", str(EXAMPLES / "hello.aix")])
    assert "main" in capsys.readouterr().out


def test_cli_show_llvm_ir_adapts_unit_main(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    title: Verify LLVM IR adapts a unit-returning main.
    parameters:
      capsys: Fixture capturing standard output and error streams.
    """
    app(["--show-llvm-ir", str(EXAMPLES / "hello.aix")])
    output = capsys.readouterr().out
    assert 'define i32 @"main"()' in output
    assert "ret i32 0" in output


def test_cli_test_list(capsys: pytest.CaptureFixture[str]) -> None:
    """
    title: Verify compiled-test discovery.
    parameters:
      capsys: Fixture capturing standard output and error streams.
    """
    tests_dir = Path(__file__).resolve().parents[1] / "aix"
    app(["test", "--list", str(tests_dir)])
    assert "test_hello.aix" in capsys.readouterr().out


def test_cli_test_list_honors_name_filter(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    title: Verify test name filtering.
    parameters:
      tmp_path: Temporary directory for this test.
      capsys: Fixture capturing standard output and error streams.
    """
    (tmp_path / "test_alpha.aix").write_text(
        '∴ main ⟦⟧ → ∅\n  ⟣ "alpha"\n∎\n',
        encoding="utf-8",
    )
    (tmp_path / "test_beta.aix").write_text(
        '∴ main ⟦⟧ → ∅\n  ⟣ "beta"\n∎\n',
        encoding="utf-8",
    )

    app(["test", "--list", "-k", "beta", str(tmp_path)])
    output = capsys.readouterr().out
    assert "test_beta.aix" in output
    assert "test_alpha.aix" not in output


def test_cli_show_llvm_ir_lowers_logical_not(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    title: Verify LLVM IR lowers logical negation.
    parameters:
      tmp_path: Temporary directory for this test.
      capsys: Fixture capturing standard output and error streams.
    """
    source = tmp_path / "logical_not.aix"
    source.write_text(
        "∴ main ⟦⟧ → ∅\n  ⌁ flag:𝔹 ≔ ⊤\n  ⟣ ¬flag\n∎\n",
        encoding="utf-8",
    )
    app(["--show-llvm-ir", str(source)])
    output = capsys.readouterr().out
    assert "xor i1" in output
