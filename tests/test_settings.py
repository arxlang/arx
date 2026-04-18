"""
title: Tests for the ``arx.settings`` module.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from arx.settings import (
    DEFAULT_CONFIG_FILENAME,
    ArxProject,
    ArxProjectError,
    find_config_file,
    load_settings,
    load_settings_from_text,
)

EXAMPLE_TOML = dedent(
    """
    [project]
    name = "sciarx"
    version = "0.1.0"
    edition = "2026"
    authors = [
      { name = "Ivan Ogasawara", email = "ivan.ogasawara@gmail.com" }
    ]

    [environment]
    kind = "conda"
    name = "sciarx"

    [build]
    src_dir = "src"
    entry = "sciarx.x"
    out_dir = "build"

    [arxpm.dependencies-dev]
    dependencies = [
      "makim",
      "pre-commit",
    ]

    [toolchain]
    compiler = "arx"
    linker = "clang"
    """
).lstrip()


def test_load_settings_from_text_full_example() -> None:
    """
    title: Round-trip the documented example into an ArxProject.
    """
    settings = load_settings_from_text(EXAMPLE_TOML)

    assert isinstance(settings, ArxProject)
    assert settings.project.name == "sciarx"
    assert settings.project.version == "0.1.0"
    assert settings.project.edition == "2026"
    assert settings.project.authors[0].name == "Ivan Ogasawara"
    assert settings.project.authors[0].email == "ivan.ogasawara@gmail.com"

    assert settings.environment is not None
    assert settings.environment.kind == "conda"
    assert settings.environment.name == "sciarx"

    assert settings.build is not None
    assert settings.build.src_dir == "src"
    assert settings.build.entry == "sciarx.x"
    assert settings.build.out_dir == "build"

    assert settings.toolchain is not None
    assert settings.toolchain.compiler == "arx"
    assert settings.toolchain.linker == "clang"

    assert settings.arxpm is not None
    assert settings.arxpm.dependencies_dev is not None
    assert settings.arxpm.dependencies_dev.dependencies == (
        "makim",
        "pre-commit",
    )
    assert settings.arxpm.dependencies is None


def test_load_settings_from_text_minimal() -> None:
    """
    title: Validate a minimal project-only ``.arxproject.toml``.
    """
    settings = load_settings_from_text(
        '[project]\nname = "tiny"\nversion = "0.0.1"\n'
    )
    assert settings.project.name == "tiny"
    assert settings.environment is None
    assert settings.build is None
    assert settings.toolchain is None
    assert settings.arxpm is None
    assert settings.project.authors == ()


def test_load_settings_discovers_file_in_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Test find_config_file walks upward from cwd.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    config = tmp_path / DEFAULT_CONFIG_FILENAME
    config.write_text(EXAMPLE_TOML, encoding="utf-8")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    found = find_config_file()
    assert found == config.resolve()

    settings = load_settings()
    assert settings.project.name == "sciarx"
    assert settings.source_path == config.resolve()


def test_find_config_file_returns_none_when_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Test find_config_file returns None when no file is present.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    monkeypatch.chdir(tmp_path)
    assert find_config_file(tmp_path) is None


def test_load_settings_without_file_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Test load_settings raises when no config file can be found.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "arx.settings.find_config_file", lambda start=None: None
    )
    with pytest.raises(ArxProjectError, match="could not find"):
        load_settings()


def test_load_settings_with_explicit_missing_path_raises(
    tmp_path: Path,
) -> None:
    """
    title: Explicit path that does not exist raises ``ArxProjectError``.
    parameters:
      tmp_path:
        type: Path
    """
    with pytest.raises(ArxProjectError, match="not found"):
        load_settings(tmp_path / "does-not-exist.toml")


def test_invalid_toml_raises() -> None:
    """
    title: Invalid TOML content produces a wrapped ``ArxProjectError``.
    """
    with pytest.raises(ArxProjectError, match="Invalid TOML") as excinfo:
        load_settings_from_text("this = is = not = toml\n")
    assert excinfo.value.__cause__ is not None


def test_missing_required_field_raises() -> None:
    """
    title: A missing required schema field yields a validation error.
    """
    with pytest.raises(ArxProjectError, match="schema validation"):
        load_settings_from_text('[project]\nversion = "0.1.0"\n')


def test_unknown_top_level_section_raises() -> None:
    """
    title: Unknown top-level sections are rejected by the schema.
    """
    with pytest.raises(ArxProjectError, match="schema validation"):
        load_settings_from_text(
            '[project]\nname = "x"\nversion = "0.1.0"\n\n[unknown]\nkey = 1\n'
        )


def test_tests_section_parses_all_fields() -> None:
    """
    title: Parse ``[tests]`` with all four supported fields.
    """
    content = dedent(
        """
        [project]
        name = "t"
        version = "0.0.1"

        [tests]
        paths = ["tests", "integration"]
        exclude = ["tests/slow_*.x"]
        file_pattern = "check_*.x"
        function_pattern = "check_*"
        """
    ).lstrip()

    settings = load_settings_from_text(content)
    assert settings.tests is not None
    assert settings.tests.paths == ("tests", "integration")
    assert settings.tests.exclude == ("tests/slow_*.x",)
    assert settings.tests.file_pattern == "check_*.x"
    assert settings.tests.function_pattern == "check_*"


def test_tests_section_is_optional() -> None:
    """
    title: Tests section is optional and defaults to None on the dataclass.
    """
    settings = load_settings_from_text(
        '[project]\nname = "t"\nversion = "0.0.1"\n'
    )
    assert settings.tests is None
