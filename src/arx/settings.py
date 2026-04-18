"""
title: Parse and validate ``.arxproject.toml`` project settings.
"""

from __future__ import annotations

import json
import re
import sys

from dataclasses import dataclass, field
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

from jsonschema import ValidationError, validate

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

DEFAULT_CONFIG_FILENAME = ".arxproject.toml"
_DEPENDENCY_PATTERN = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?: @ (?P<location>\S+))?$"
)
_DEPENDENCY_GROUP_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_DEPENDENCY_GROUP_NORMALIZE_PATTERN = re.compile(r"[-_.]+")


class ArxProjectError(Exception):
    """
    title: Raised when ``.arxproject.toml`` cannot be loaded or validated.
    """


@dataclass(frozen=True)
class Author:
    """
    title: One author entry declared in ``[project].authors``.
    attributes:
      name:
        type: str
      email:
        type: str | None
    """

    name: str
    email: str | None = None


@dataclass(frozen=True)
class Project:
    """
    title: Parsed project section of .arxproject.toml.
    attributes:
      name:
        type: str
      version:
        type: str
      edition:
        type: str | None
      description:
        type: str | None
      license:
        type: str | None
      authors:
        type: tuple[Author, Ellipsis]
      dependencies:
        type: tuple[str, Ellipsis]
    """

    name: str
    version: str
    edition: str | None = None
    description: str | None = None
    license: str | None = None
    authors: tuple[Author, ...] = ()
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class DependencyGroupInclude:
    """
    title: Include one named dependency group inside another group.
    attributes:
      include_group:
        type: str
    """

    include_group: str


DependencyGroupEntry = str | DependencyGroupInclude


@dataclass(frozen=True)
class Environment:
    """
    title: Parsed environment section of .arxproject.toml.
    attributes:
      kind:
        type: str | None
      name:
        type: str | None
      path:
        type: str | None
    """

    kind: str | None = None
    name: str | None = None
    path: str | None = None


@dataclass(frozen=True)
class Build:
    """
    title: Parsed build section of .arxproject.toml.
    attributes:
      src_dir:
        type: str | None
      entry:
        type: str | None
      out_dir:
        type: str | None
    """

    src_dir: str | None = None
    entry: str | None = None
    out_dir: str | None = None


@dataclass(frozen=True)
class Toolchain:
    """
    title: Parsed toolchain section of .arxproject.toml.
    attributes:
      compiler:
        type: str | None
      linker:
        type: str | None
    """

    compiler: str | None = None
    linker: str | None = None


@dataclass(frozen=True)
class ArxpmDependencyGroup:
    """
    title: Legacy placeholder for removed ``[arxpm.*]`` sections.
    attributes:
      dependencies:
        type: tuple[str, Ellipsis]
    """

    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class Arxpm:
    """
    title: Legacy placeholder for the removed ``[arxpm]`` section.
    attributes:
      dependencies:
        type: ArxpmDependencyGroup | None
      dependencies_dev:
        type: ArxpmDependencyGroup | None
      extras:
        type: dict[str, Any]
    """

    dependencies: ArxpmDependencyGroup | None = None
    dependencies_dev: ArxpmDependencyGroup | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Tests:
    """
    title: Parsed tests section of .arxproject.toml.
    attributes:
      paths:
        type: tuple[str, Ellipsis] | None
      exclude:
        type: tuple[str, Ellipsis] | None
      file_pattern:
        type: str | None
      function_pattern:
        type: str | None
    """

    paths: tuple[str, ...] | None = None
    exclude: tuple[str, ...] | None = None
    file_pattern: str | None = None
    function_pattern: str | None = None


@dataclass(frozen=True)
class ArxProject:
    """
    title: Full parsed ``.arxproject.toml`` document.
    attributes:
      project:
        type: Project
      environment:
        type: Environment | None
      build:
        type: Build | None
      toolchain:
        type: Toolchain | None
      dependency_groups:
        type: dict[str, tuple[DependencyGroupEntry, Ellipsis]]
      arxpm:
        type: Arxpm | None
      tests:
        type: Tests | None
      source_path:
        type: Path | None
    """

    project: Project
    environment: Environment | None = None
    build: Build | None = None
    toolchain: Toolchain | None = None
    dependency_groups: dict[str, tuple[DependencyGroupEntry, ...]] = field(
        default_factory=dict
    )
    arxpm: Arxpm | None = None
    tests: Tests | None = None
    source_path: Path | None = None


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    """
    title: Load and cache the ``.arxproject.toml`` JSON schema.
    returns:
      type: dict[str, Any]
    """
    with (
        files("arx.schema")
        .joinpath("arxproject.json")
        .open(encoding="utf-8") as fh
    ):
        return cast(dict[str, Any], json.load(fh))


def _build_author(data: dict[str, Any]) -> Author:
    """
    title: Build one Author dataclass from its validated mapping.
    parameters:
      data:
        type: dict[str, Any]
    returns:
      type: Author
    """
    return Author(name=data["name"], email=data.get("email"))


def _build_project(data: dict[str, Any]) -> Project:
    """
    title: Build the Project dataclass from its validated mapping.
    parameters:
      data:
        type: dict[str, Any]
    returns:
      type: Project
    """
    authors = tuple(_build_author(entry) for entry in data.get("authors", []))
    return Project(
        name=data["name"],
        version=data["version"],
        edition=data.get("edition"),
        description=data.get("description"),
        license=data.get("license"),
        authors=authors,
        dependencies=tuple(data.get("dependencies", ())),
    )


def _build_dependency_group_entry(
    data: str | dict[str, Any],
) -> DependencyGroupEntry:
    """
    title: Build one dependency-group entry from validated manifest data.
    parameters:
      data:
        type: str | dict[str, Any]
    returns:
      type: DependencyGroupEntry
    """
    if isinstance(data, str):
        return data
    return DependencyGroupInclude(include_group=data["include-group"])


def _build_dependency_groups(
    data: dict[str, Any] | None,
) -> dict[str, tuple[DependencyGroupEntry, ...]]:
    """
    title: Build dependency groups from their validated mapping.
    parameters:
      data:
        type: dict[str, Any] | None
    returns:
      type: dict[str, tuple[DependencyGroupEntry, Ellipsis]]
    """
    if data is None:
        return {}

    return {
        name: tuple(_build_dependency_group_entry(entry) for entry in entries)
        for name, entries in data.items()
    }


def _build_tests(data: dict[str, Any] | None) -> Tests | None:
    """
    title: Build the Tests dataclass from its validated mapping.
    parameters:
      data:
        type: dict[str, Any] | None
    returns:
      type: Tests | None
    """
    if data is None:
        return None
    raw_paths = data.get("paths")
    raw_exclude = data.get("exclude")
    return Tests(
        paths=tuple(raw_paths) if raw_paths is not None else None,
        exclude=tuple(raw_exclude) if raw_exclude is not None else None,
        file_pattern=data.get("file_pattern"),
        function_pattern=data.get("function_pattern"),
    )


def _reject_arxpm_sections(data: dict[str, Any]) -> None:
    """
    title: Reject removed ``[arxpm]`` manifest sections with a clear error.
    parameters:
      data:
        type: dict[str, Any]
    """
    if "arxpm" not in data:
        return
    raise ArxProjectError(
        ".arxproject.toml does not support [arxpm] sections. "
        "Declare dependencies in [project] using "
        'dependencies = ["name", "name @ ../path"].'
    )


def _validate_dependency(value: str, location: str) -> None:
    """
    title: Validate one dependency entry from ``.arxproject.toml``.
    parameters:
      value:
        type: str
      location:
        type: str
    """
    if _DEPENDENCY_PATTERN.fullmatch(value) is not None:
        return
    raise ArxProjectError(
        f".arxproject.toml {location} must be either a package name "
        'like "http" or a direct reference like "mylib @ ../mylib".'
    )


def _validate_project(data: dict[str, Any]) -> None:
    """
    title: Validate project-only settings rules after schema validation.
    parameters:
      data:
        type: dict[str, Any]
    """
    for index, value in enumerate(data.get("dependencies", ())):
        _validate_dependency(value, f"project.dependencies[{index}]")


def _validate_dependency_group_name(name: str, location: str) -> None:
    """
    title: Validate one dependency-group name.
    parameters:
      name:
        type: str
      location:
        type: str
    """
    if _DEPENDENCY_GROUP_NAME_PATTERN.fullmatch(name) is not None:
        return
    raise ArxProjectError(
        f".arxproject.toml {location} must use only letters, numbers, "
        '".", "_" or "-", and start with a letter or number.'
    )


def _normalize_dependency_group_name(name: str) -> str:
    """
    title: Normalize one dependency-group name for semantic comparison.
    parameters:
      name:
        type: str
    returns:
      type: str
    """
    return _DEPENDENCY_GROUP_NORMALIZE_PATTERN.sub("-", name).lower()


def _dependency_group_name_mapping(
    dependency_groups: dict[str, list[Any]],
) -> dict[str, str]:
    """
    title: Map normalized dependency-group names to their declared names.
    parameters:
      dependency_groups:
        type: dict[str, list[Any]]
    returns:
      type: dict[str, str]
    """
    normalized_names: dict[str, str] = {}
    for name in dependency_groups:
        normalized_name = _normalize_dependency_group_name(name)
        existing_name = normalized_names.get(normalized_name)
        if existing_name is not None:
            raise ArxProjectError(
                ".arxproject.toml [dependency-groups] names "
                f'"{existing_name}" and "{name}" normalize to the '
                f'same name "{normalized_name}".'
            )
        normalized_names[normalized_name] = name
    return normalized_names


def _dependency_group_includes(entries: list[Any]) -> tuple[str, ...]:
    """
    title: Collect included group names from raw dependency-group entries.
    parameters:
      entries:
        type: list[Any]
    returns:
      type: tuple[str, Ellipsis]
    """
    includes: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        include_group = entry.get("include-group")
        if isinstance(include_group, str):
            includes.append(include_group)
    return tuple(includes)


def _detect_dependency_group_cycles(
    dependency_groups: dict[str, list[Any]],
    normalized_names: dict[str, str],
) -> None:
    """
    title: Reject dependency-group include cycles.
    parameters:
      dependency_groups:
        type: dict[str, list[Any]]
      normalized_names:
        type: dict[str, str]
    """
    visited: set[str] = set()

    def visit(name: str, ancestry: list[str]) -> None:
        """
        title: Visit one dependency group while checking for include cycles.
        parameters:
          name:
            type: str
          ancestry:
            type: list[str]
        """
        if name in ancestry:
            cycle_start = ancestry.index(name)
            cycle = [*ancestry[cycle_start:], name]
            cycle_text = " -> ".join(cycle)
            raise ArxProjectError(
                ".arxproject.toml dependency-groups includes must not "
                f"form cycles ({cycle_text})."
            )

        if name in visited:
            return

        ancestry.append(name)
        for included_name in _dependency_group_includes(
            dependency_groups[name]
        ):
            resolved_name = normalized_names[
                _normalize_dependency_group_name(included_name)
            ]
            visit(resolved_name, ancestry)
        ancestry.pop()
        visited.add(name)

    for name in dependency_groups:
        visit(name, [])


def _validate_dependency_groups(data: dict[str, Any]) -> None:
    """
    title: Validate dependency-group rules after schema validation.
    parameters:
      data:
        type: dict[str, Any]
    """
    raw_dependency_groups = data.get("dependency-groups")
    if raw_dependency_groups is None:
        return

    dependency_groups = cast(dict[str, list[Any]], raw_dependency_groups)

    for name in dependency_groups:
        _validate_dependency_group_name(
            name,
            f'[dependency-groups] key "{name}"',
        )

    normalized_names = _dependency_group_name_mapping(dependency_groups)

    for name, entries in dependency_groups.items():
        for index, entry in enumerate(entries):
            if isinstance(entry, str):
                _validate_dependency(
                    entry,
                    f"dependency-groups.{name}[{index}]",
                )
                continue

            if not isinstance(entry, dict):
                raise ArxProjectError(
                    ".arxproject.toml dependency-groups."
                    f"{name}[{index}] must be a dependency string or "
                    '{ include-group = "name" }.'
                )

            keys = set(entry)
            if keys != {"include-group"}:
                raise ArxProjectError(
                    ".arxproject.toml dependency-groups."
                    f"{name}[{index}] must be exactly "
                    '{ include-group = "name" }.'
                )

            include_group = entry.get("include-group")
            if not isinstance(include_group, str):
                raise ArxProjectError(
                    ".arxproject.toml dependency-groups."
                    f"{name}[{index}].include-group must be a string."
                )

            _validate_dependency_group_name(
                include_group,
                (f"dependency-groups.{name}[{index}].include-group"),
            )

            normalized_include_group = _normalize_dependency_group_name(
                include_group
            )
            if normalized_include_group not in normalized_names:
                raise ArxProjectError(
                    ".arxproject.toml dependency-groups."
                    f"{name}[{index}] includes unknown group "
                    f'"{include_group}".'
                )

    _detect_dependency_group_cycles(dependency_groups, normalized_names)


def _reject_legacy_environment_kind(data: dict[str, Any] | None) -> None:
    """
    title: Reject removed environment kinds with a migration hint.
    parameters:
      data:
        type: dict[str, Any] | None
    """
    if data is None:
        return

    kind = data.get("kind")
    if kind not in {"managed-venv", "existing-venv"}:
        return

    raise ArxProjectError(
        f'[environment] kind="{kind}" is no longer supported. '
        'Use kind="venv" instead.'
    )


def _validate_environment(data: dict[str, Any] | None) -> None:
    """
    title: Validate environment-only settings rules after schema validation.
    parameters:
      data:
        type: dict[str, Any] | None
    """
    if data is None:
        return

    kind = data["kind"]
    if kind == "venv":
        if "name" not in data:
            return
        raise ArxProjectError(
            '[environment] kind="venv" does not support "name".'
        )

    if kind == "system":
        unsupported = [
            field_name for field_name in ("name", "path") if field_name in data
        ]
        if not unsupported:
            return
        fields = ", ".join(f'"{field_name}"' for field_name in unsupported)
        raise ArxProjectError(
            f'[environment] kind="system" does not support {fields}.'
        )

    if kind == "conda":
        if "name" in data or "path" in data:
            return
        raise ArxProjectError(
            '[environment] kind="conda" requires at least one of '
            '"name" or "path".'
        )


def _validate_data(data: dict[str, Any]) -> None:
    """
    title: Validate parsed ``.arxproject.toml`` data before building models.
    parameters:
      data:
        type: dict[str, Any]
    """
    _reject_arxpm_sections(data)
    _reject_legacy_environment_kind(data.get("environment"))

    try:
        validate(instance=data, schema=_schema())
    except ValidationError as err:
        raise ArxProjectError(
            f".arxproject.toml failed schema validation: {err.message}"
        ) from err

    _validate_project(data["project"])
    _validate_dependency_groups(data)
    _validate_environment(data.get("environment"))


def _build_arx_project(
    data: dict[str, Any],
    source_path: Path | None,
) -> ArxProject:
    """
    title: Build the ArxProject dataclass from its validated mapping.
    parameters:
      data:
        type: dict[str, Any]
      source_path:
        type: Path | None
    returns:
      type: ArxProject
    """
    environment_data = data.get("environment")
    build_data = data.get("build")
    toolchain_data = data.get("toolchain")
    return ArxProject(
        project=_build_project(data["project"]),
        environment=(
            Environment(**environment_data)
            if environment_data is not None
            else None
        ),
        build=Build(**build_data) if build_data is not None else None,
        toolchain=(
            Toolchain(**toolchain_data) if toolchain_data is not None else None
        ),
        dependency_groups=_build_dependency_groups(
            data.get("dependency-groups")
        ),
        tests=_build_tests(data.get("tests")),
        source_path=source_path,
    )


def _author_to_mapping(author: Author) -> dict[str, str]:
    """
    title: Convert one Author dataclass into a TOML-safe mapping.
    parameters:
      author:
        type: Author
    returns:
      type: dict[str, str]
    """
    data = {"name": author.name}
    if author.email is not None:
        data["email"] = author.email
    return data


def _settings_to_data(settings: ArxProject) -> dict[str, Any]:
    """
    title: Convert settings dataclasses into raw manifest data.
    parameters:
      settings:
        type: ArxProject
    returns:
      type: dict[str, Any]
    """
    if settings.arxpm is not None:
        raise ArxProjectError(
            "ArxProject.arxpm is no longer supported. "
            "Declare dependencies in project.dependencies instead."
        )

    project: dict[str, Any] = {
        "name": settings.project.name,
        "version": settings.project.version,
    }
    if settings.project.edition is not None:
        project["edition"] = settings.project.edition
    if settings.project.description is not None:
        project["description"] = settings.project.description
    if settings.project.license is not None:
        project["license"] = settings.project.license
    if settings.project.dependencies:
        project["dependencies"] = list(settings.project.dependencies)
    if settings.project.authors:
        project["authors"] = [
            _author_to_mapping(author) for author in settings.project.authors
        ]

    data: dict[str, Any] = {"project": project}

    if settings.dependency_groups:
        dependency_groups: dict[str, list[str | dict[str, str]]] = {}
        for group_name, entries in settings.dependency_groups.items():
            if not isinstance(group_name, str):
                raise ArxProjectError(
                    "ArxProject.dependency_groups keys must be strings."
                )

            dependency_groups[group_name] = []
            for index, entry in enumerate(entries):
                if isinstance(entry, str):
                    dependency_groups[group_name].append(entry)
                    continue

                if isinstance(entry, DependencyGroupInclude):
                    dependency_groups[group_name].append(
                        {"include-group": entry.include_group}
                    )
                    continue

                raise ArxProjectError(
                    "ArxProject.dependency_groups."
                    f"{group_name}[{index}] must be a string or "
                    "DependencyGroupInclude."
                )

        data["dependency-groups"] = dependency_groups

    if settings.environment is not None:
        environment: dict[str, Any] = {}
        if settings.environment.kind is not None:
            environment["kind"] = settings.environment.kind
        if settings.environment.name is not None:
            environment["name"] = settings.environment.name
        if settings.environment.path is not None:
            environment["path"] = settings.environment.path
        data["environment"] = environment

    if settings.build is not None:
        build: dict[str, Any] = {}
        if settings.build.src_dir is not None:
            build["src_dir"] = settings.build.src_dir
        if settings.build.entry is not None:
            build["entry"] = settings.build.entry
        if settings.build.out_dir is not None:
            build["out_dir"] = settings.build.out_dir
        data["build"] = build

    if settings.toolchain is not None:
        toolchain: dict[str, Any] = {}
        if settings.toolchain.compiler is not None:
            toolchain["compiler"] = settings.toolchain.compiler
        if settings.toolchain.linker is not None:
            toolchain["linker"] = settings.toolchain.linker
        data["toolchain"] = toolchain

    if settings.tests is not None:
        tests: dict[str, Any] = {}
        if settings.tests.paths is not None:
            tests["paths"] = list(settings.tests.paths)
        if settings.tests.exclude is not None:
            tests["exclude"] = list(settings.tests.exclude)
        if settings.tests.file_pattern is not None:
            tests["file_pattern"] = settings.tests.file_pattern
        if settings.tests.function_pattern is not None:
            tests["function_pattern"] = settings.tests.function_pattern
        data["tests"] = tests

    return data


def _format_toml_string(value: str) -> str:
    """
    title: Quote one TOML basic string with JSON-compatible escapes.
    parameters:
      value:
        type: str
    returns:
      type: str
    """
    return json.dumps(value, ensure_ascii=False)


def _append_string_array(
    lines: list[str],
    key: str,
    values: tuple[str, ...] | list[str],
) -> None:
    """
    title: Append a canonical multiline string array to TOML output.
    parameters:
      lines:
        type: list[str]
      key:
        type: str
      values:
        type: tuple[str, Ellipsis] | list[str]
    """
    lines.append(f"{key} = [")
    for value in values:
        lines.append(f"  {_format_toml_string(value)},")
    lines.append("]")


def _append_dependency_group_array(
    lines: list[str],
    key: str,
    values: tuple[DependencyGroupEntry, ...],
) -> None:
    """
    title: Append one dependency-group entry array to TOML output.
    parameters:
      lines:
        type: list[str]
      key:
        type: str
      values:
        type: tuple[DependencyGroupEntry, Ellipsis]
    """
    lines.append(f"{_format_toml_string(key)} = [")
    for value in values:
        if isinstance(value, str):
            lines.append(f"  {_format_toml_string(value)},")
            continue

        lines.append(
            "  { include-group = "
            f"{_format_toml_string(value.include_group)} }},"
        )
    lines.append("]")


def _append_project(lines: list[str], project: Project) -> None:
    """
    title: Append the canonical ``[project]`` section.
    parameters:
      lines:
        type: list[str]
      project:
        type: Project
    """
    lines.append("[project]")
    lines.append(f"name = {_format_toml_string(project.name)}")
    lines.append(f"version = {_format_toml_string(project.version)}")
    if project.edition is not None:
        lines.append(f"edition = {_format_toml_string(project.edition)}")
    if project.description is not None:
        lines.append(
            f"description = {_format_toml_string(project.description)}"
        )
    if project.license is not None:
        lines.append(f"license = {_format_toml_string(project.license)}")
    if project.dependencies:
        _append_string_array(lines, "dependencies", project.dependencies)
    if project.authors:
        lines.append("authors = [")
        for author in project.authors:
            entries = [f"name = {_format_toml_string(author.name)}"]
            if author.email is not None:
                entries.append(f"email = {_format_toml_string(author.email)}")
            lines.append(f"  {{ {', '.join(entries)} }},")
        lines.append("]")


def _append_dependency_groups(
    lines: list[str],
    dependency_groups: dict[str, tuple[DependencyGroupEntry, ...]],
) -> None:
    """
    title: Append the canonical ``[dependency-groups]`` section.
    parameters:
      lines:
        type: list[str]
      dependency_groups:
        type: dict[str, tuple[DependencyGroupEntry, Ellipsis]]
    """
    if not dependency_groups:
        return

    lines.extend(("", "[dependency-groups]"))
    for name, entries in dependency_groups.items():
        _append_dependency_group_array(lines, name, entries)


def _append_environment(
    lines: list[str],
    environment: Environment | None,
) -> None:
    """
    title: Append the canonical ``[environment]`` section when present.
    parameters:
      lines:
        type: list[str]
      environment:
        type: Environment | None
    """
    if environment is None:
        return
    lines.extend(("", "[environment]"))
    if environment.kind is not None:
        lines.append(f"kind = {_format_toml_string(environment.kind)}")
    if environment.name is not None:
        lines.append(f"name = {_format_toml_string(environment.name)}")
    if environment.path is not None:
        lines.append(f"path = {_format_toml_string(environment.path)}")


def _append_build(lines: list[str], build: Build | None) -> None:
    """
    title: Append the canonical ``[build]`` section when present.
    parameters:
      lines:
        type: list[str]
      build:
        type: Build | None
    """
    if build is None:
        return
    lines.extend(("", "[build]"))
    if build.src_dir is not None:
        lines.append(f"src_dir = {_format_toml_string(build.src_dir)}")
    if build.entry is not None:
        lines.append(f"entry = {_format_toml_string(build.entry)}")
    if build.out_dir is not None:
        lines.append(f"out_dir = {_format_toml_string(build.out_dir)}")


def _append_toolchain(
    lines: list[str],
    toolchain: Toolchain | None,
) -> None:
    """
    title: Append the canonical ``[toolchain]`` section when present.
    parameters:
      lines:
        type: list[str]
      toolchain:
        type: Toolchain | None
    """
    if toolchain is None:
        return
    lines.extend(("", "[toolchain]"))
    if toolchain.compiler is not None:
        lines.append(f"compiler = {_format_toml_string(toolchain.compiler)}")
    if toolchain.linker is not None:
        lines.append(f"linker = {_format_toml_string(toolchain.linker)}")


def _append_tests(lines: list[str], tests: Tests | None) -> None:
    """
    title: Append the canonical ``[tests]`` section when present.
    parameters:
      lines:
        type: list[str]
      tests:
        type: Tests | None
    """
    if tests is None:
        return
    lines.extend(("", "[tests]"))
    if tests.paths is not None:
        _append_string_array(lines, "paths", tests.paths)
    if tests.exclude is not None:
        _append_string_array(lines, "exclude", tests.exclude)
    if tests.file_pattern is not None:
        lines.append(
            f"file_pattern = {_format_toml_string(tests.file_pattern)}"
        )
    if tests.function_pattern is not None:
        lines.append(
            f"function_pattern = {_format_toml_string(tests.function_pattern)}"
        )


def dump_settings(settings: ArxProject) -> str:
    """
    title: Serialize settings into canonical ``.arxproject.toml`` text.
    parameters:
      settings:
        type: ArxProject
    returns:
      type: str
    """
    _validate_data(_settings_to_data(settings))

    lines: list[str] = []
    _append_project(lines, settings.project)
    _append_dependency_groups(lines, settings.dependency_groups)
    _append_environment(lines, settings.environment)
    _append_build(lines, settings.build)
    _append_toolchain(lines, settings.toolchain)
    _append_tests(lines, settings.tests)
    return "\n".join(lines) + "\n"


def write_settings(
    settings: ArxProject,
    path: str | Path = DEFAULT_CONFIG_FILENAME,
) -> Path:
    """
    title: Write canonical ``.arxproject.toml`` text to disk.
    parameters:
      settings:
        type: ArxProject
      path:
        type: str | Path
    returns:
      type: Path
    """
    target = Path(path)
    target.write_text(dump_settings(settings), encoding="utf-8")
    return target


def find_config_file(start: Path | None = None) -> Path | None:
    """
    title: Walk upward from ``start`` to locate ``.arxproject.toml``.
    parameters:
      start:
        type: Path | None
    returns:
      type: Path | None
    """
    current = (start or Path.cwd()).resolve()
    while True:
        candidate = current / DEFAULT_CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        if current.parent == current:
            return None
        current = current.parent


def load_settings_from_text(
    content: str,
    source_path: Path | None = None,
) -> ArxProject:
    """
    title: Parse and validate one ``.arxproject.toml`` string.
    parameters:
      content:
        type: str
      source_path:
        type: Path | None
    returns:
      type: ArxProject
    """
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as err:
        raise ArxProjectError(
            f"Invalid TOML in .arxproject.toml: {err}"
        ) from err

    _validate_data(data)
    return _build_arx_project(data, source_path)


def load_settings(path: str | Path | None = None) -> ArxProject:
    """
    title: Load and validate ``.arxproject.toml`` into a typed dataclass.
    parameters:
      path:
        type: str | Path | None
    returns:
      type: ArxProject
    """
    if path is None:
        discovered = find_config_file()
        if discovered is None:
            raise ArxProjectError(
                f"could not find {DEFAULT_CONFIG_FILENAME} in the current "
                "directory or any parent"
            )
        resolved = discovered
    else:
        resolved = Path(path)
        if not resolved.is_file():
            raise ArxProjectError(
                f"{DEFAULT_CONFIG_FILENAME} not found at {resolved}"
            )

    content = resolved.read_text(encoding="utf-8")
    return load_settings_from_text(content, source_path=resolved)
