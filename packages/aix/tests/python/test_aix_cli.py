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


def test_cli_test_list(capsys: pytest.CaptureFixture[str]) -> None:
    tests_dir = Path(__file__).resolve().parents[1] / "aix"
    app(["test", "--list", str(tests_dir)])
    assert "test_hello.aix" in capsys.readouterr().out
