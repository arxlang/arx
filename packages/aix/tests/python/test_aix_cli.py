"""
title: AIX CLI tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aix.cli import app

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        app(["--help"])
    assert excinfo.value.code == 0
    assert "AIX compiler frontend" in capsys.readouterr().out


def test_cli_show_tokens(capsys: pytest.CaptureFixture[str]) -> None:
    app(["--show-tokens", str(EXAMPLES / "hello.aix")])
    assert "define" in capsys.readouterr().out


def test_cli_show_ast(capsys: pytest.CaptureFixture[str]) -> None:
    app(["--show-ast", str(EXAMPLES / "hello.aix")])
    assert "main" in capsys.readouterr().out


def test_cli_show_llvm_ir_adapts_unit_main(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app(["--show-llvm-ir", str(EXAMPLES / "hello.aix")])
    output = capsys.readouterr().out
    assert 'define i32 @"main"()' in output
    assert "ret i32 0" in output


def test_cli_test_list(capsys: pytest.CaptureFixture[str]) -> None:
    tests_dir = Path(__file__).resolve().parents[1] / "aix"
    app(["test", "--list", str(tests_dir)])
    assert "test_hello.aix" in capsys.readouterr().out


def test_cli_test_list_honors_name_filter(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
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
