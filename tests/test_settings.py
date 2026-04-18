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
    Author,
    Build,
    Environment,
    Project,
    Toolchain,
    dump_settings,
    find_config_file,
    load_settings,
    load_settings_from_text,
    write_settings,
)
from arx.settings import (
    Tests as SettingsTests,
)

EXAMPLE_TOML = dedent(
    """
    [project]
    name = "sciarx"
    version = "0.1.0"
    edition = "2026"
    dependencies = [
      "http",
      "mylib @ ../mylib",
    ]
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

    [toolchain]
    compiler = "arx"
    linker = "clang"

    [tests]
    paths = ["tests"]
    exclude = ["tests/slow_*.x"]
    """
).lstrip()


def _project_toml(extra: str = "") -> str:
    """
    title: Build a minimal project TOML snippet for settings tests.
    parameters:
      extra:
        type: str
    returns:
      type: str
    """
    return f'[project]\nname = "demo"\nversion = "0.1.0"\n{extra}'


def test_load_settings_from_text_full_example() -> None:
    """
    title: Parse the documented example into an ArxProject.
    """
    settings = load_settings_from_text(EXAMPLE_TOML)

    assert isinstance(settings, ArxProject)
    assert settings.project.name == "sciarx"
    assert settings.project.version == "0.1.0"
    assert settings.project.edition == "2026"
    assert settings.project.dependencies == (
        "http",
        "mylib @ ../mylib",
    )
    assert settings.project.authors[0].name == "Ivan Ogasawara"
    assert settings.project.authors[0].email == "ivan.ogasawara@gmail.com"

    assert settings.environment is not None
    assert settings.environment.kind == "conda"
    assert settings.environment.name == "sciarx"
    assert settings.environment.path is None

    assert settings.build is not None
    assert settings.build.src_dir == "src"
    assert settings.build.entry == "sciarx.x"
    assert settings.build.out_dir == "build"

    assert settings.toolchain is not None
    assert settings.toolchain.compiler == "arx"
    assert settings.toolchain.linker == "clang"

    assert settings.tests is not None
    assert settings.tests.paths == ("tests",)
    assert settings.tests.exclude == ("tests/slow_*.x",)
    assert settings.arxpm is None


def test_load_settings_from_text_minimal() -> None:
    """
    title: Validate a minimal project-only ``.arxproject.toml``.
    """
    settings = load_settings_from_text(_project_toml())

    assert settings.project.name == "demo"
    assert settings.project.dependencies == ()
    assert settings.environment is None
    assert settings.build is None
    assert settings.toolchain is None
    assert settings.arxpm is None
    assert settings.project.authors == ()


@pytest.mark.parametrize(
    "dependency",
    [
        "http",
        "mylib @ ../mylib",
        "utils @ git+https://example.com/utils.git",
    ],
    ids=["registry", "path", "git"],
)
def test_project_dependencies_support_canonical_strings(
    dependency: str,
) -> None:
    """
    title: Parse supported dependency strings from ``project.dependencies``.
    parameters:
      dependency:
        type: str
    """
    content = _project_toml(f'dependencies = ["{dependency}"]\n')

    settings = load_settings_from_text(content)
    assert settings.project.dependencies == (dependency,)


def test_managed_venv_environment_is_valid() -> None:
    """
    title: Managed virtual environments allow only the kind field.
    """
    settings = load_settings_from_text(
        _project_toml('\n[environment]\nkind = "managed-venv"\n')
    )

    assert settings.environment == Environment(kind="managed-venv")


def test_managed_venv_rejects_extra_fields() -> None:
    """
    title: Managed virtual environments reject unsupported fields.
    """
    content = _project_toml(
        '\n[environment]\nkind = "managed-venv"\nname = "demo"\n'
    )

    with pytest.raises(ArxProjectError, match="managed-venv"):
        load_settings_from_text(content)


def test_existing_venv_environment_is_valid() -> None:
    """
    title: Existing virtual environments require a path.
    """
    settings = load_settings_from_text(
        _project_toml(
            '\n[environment]\nkind = "existing-venv"\npath = ".venv"\n'
        )
    )

    assert settings.environment == Environment(
        kind="existing-venv",
        path=".venv",
    )


def test_existing_venv_missing_path_raises() -> None:
    """
    title: Existing virtual environments must declare a path.
    """
    content = _project_toml('\n[environment]\nkind = "existing-venv"\n')

    with pytest.raises(ArxProjectError, match='requires "path"'):
        load_settings_from_text(content)


def test_conda_environment_with_name_is_valid() -> None:
    """
    title: Conda environments accept a name.
    """
    settings = load_settings_from_text(
        _project_toml('\n[environment]\nkind = "conda"\nname = "demo"\n')
    )

    assert settings.environment == Environment(kind="conda", name="demo")


def test_conda_environment_with_path_is_valid() -> None:
    """
    title: Conda environments accept a path.
    """
    settings = load_settings_from_text(
        _project_toml(
            '\n[environment]\nkind = "conda"\npath = ".conda/envs/demo"\n'
        )
    )

    assert settings.environment == Environment(
        kind="conda",
        path=".conda/envs/demo",
    )


def test_conda_environment_missing_name_and_path_raises() -> None:
    """
    title: Conda environments must declare a name or a path.
    """
    content = _project_toml('\n[environment]\nkind = "conda"\n')

    with pytest.raises(
        ArxProjectError,
        match='requires at least one of "name" or "path"',
    ):
        load_settings_from_text(content)


def test_rejects_legacy_arxpm_dependency_tables() -> None:
    """
    title: Reject removed package-manager-specific dependency tables.
    """
    content = _project_toml(
        '\n[arxpm.dependencies]\ndependencies = ["http"]\n'
    )

    with pytest.raises(ArxProjectError, match=r"\[arxpm\]"):
        load_settings_from_text(content)


def test_dump_and_write_settings_round_trip(tmp_path: Path) -> None:
    """
    title: Serialize and reload the canonical manifest structure.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / DEFAULT_CONFIG_FILENAME
    settings = ArxProject(
        project=Project(
            name="demo",
            version="0.1.0",
            description="demo project",
            authors=(
                Author(
                    name="Arx Maintainer",
                    email="maintainer@example.com",
                ),
            ),
            dependencies=(
                "http",
                "mylib @ ../mylib",
                "utils @ git+https://example.com/utils.git",
            ),
        ),
        environment=Environment(kind="conda", path=".conda/envs/demo"),
        build=Build(src_dir="src", entry="main.x", out_dir="build"),
        toolchain=Toolchain(compiler="arx", linker="clang"),
        tests=SettingsTests(
            paths=("tests",),
            exclude=("tests/slow_*.x",),
            file_pattern="test_*.x",
            function_pattern="test_*",
        ),
    )

    rendered = dump_settings(settings)
    assert "[arxpm" not in rendered
    assert "dependencies = [" in rendered

    written_path = write_settings(settings, path)
    assert written_path == path

    loaded = load_settings(path)
    assert loaded == ArxProject(
        project=settings.project,
        environment=settings.environment,
        build=settings.build,
        toolchain=settings.toolchain,
        tests=settings.tests,
        source_path=path,
    )


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
