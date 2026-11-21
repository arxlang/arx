"""
title: Parse and validate ``.arxproject.toml`` project settings.
"""

from __future__ import annotations

import json
import re
import tomllib

from dataclasses import dataclass, field
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

from jsonschema import ValidationError, validate
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name

DEFAULT_CONFIG_FILENAME = ".arxproject.toml"
_DEPENDENCY_GROUP_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_DEPENDENCY_GROUP_NORMALIZE_PATTERN = re.compile(r"[-_.]+")
_DEFAULT_SRC_DIR = "src"
_ARXLANG_DISTRIBUTION_NAME = "arxlang"


def _default_build_system_dependency(requires_arx: str | None) -> str:
    """
    title: Build the default Arx compiler dependency requirement.
    parameters:
      requires_arx: Requires arx.
    returns: Constructed the default Arx compiler dependency requirement.
    """
    if requires_arx is None:
        return _ARXLANG_DISTRIBUTION_NAME
    return f"{_ARXLANG_DISTRIBUTION_NAME}{requires_arx.strip()}"


def _requirement_name(value: str) -> str | None:
    """
    title: Parse and return one requirement distribution name.
    parameters:
      value: Value to process.
    returns: Parsed and return one requirement distribution name.
    """
    try:
        return Requirement(value).name
    except InvalidRequirement:
        return None


def _has_arxlang_dependency(dependencies: tuple[str, ...]) -> bool:
    """
    title: Return whether dependencies already include ``arxlang``.
    parameters:
      dependencies: Dependencies.
    returns: Whether dependencies already include ``arxlang``.
    """
    arxlang_name = canonicalize_name(_ARXLANG_DISTRIBUTION_NAME)
    for dependency in dependencies:
        name = _requirement_name(dependency)
        if name is None:
            continue
        if canonicalize_name(name) == arxlang_name:
            return True
    return False


def _normalize_build_system_dependencies(
    dependencies: tuple[str, ...],
    requires_arx: str | None,
) -> tuple[str, ...]:
    """
    title: Ensure build-system dependencies include the Arx compiler package.
    parameters:
      dependencies: Dependencies.
      requires_arx: Requires arx.
    returns: 'Result of this operation: ensure build-system dependencies
      include the Arx compiler package.'
    """
    if _has_arxlang_dependency(dependencies):
        return dependencies
    return (_default_build_system_dependency(requires_arx), *dependencies)


class ArxProjectError(Exception):
    """
    title: Raised when ``.arxproject.toml`` cannot be loaded or validated.
    """


@dataclass(frozen=True)
class Author:
    """
    title: One author entry declared in ``[project].authors``.
    attributes:
      name: Name identifying this declaration.
      email: Email.
    """

    name: str
    email: str | None = None


@dataclass(frozen=True)
class Project:
    """
    title: Parsed project section of .arxproject.toml.
    attributes:
      name: Name identifying this declaration.
      version: Package version metadata.
      edition: Edition.
      description: Description.
      license: License.
      authors: Authors.
      dependencies: Dependencies.
      requires_arx: Requires arx.
    """

    name: str
    version: str
    edition: str | None = None
    description: str | None = None
    license: str | None = None
    authors: tuple[Author, ...] = ()
    dependencies: tuple[str, ...] = ()
    requires_arx: str | None = None


@dataclass(frozen=True)
class DependencyGroupInclude:
    """
    title: Include one named dependency group inside another group.
    attributes:
      include_group: Include group.
    """

    include_group: str


DependencyGroupEntry = str | DependencyGroupInclude


@dataclass(frozen=True)
class Environment:
    """
    title: Parsed environment section of .arxproject.toml.
    attributes:
      kind: Kind of value or operation.
      name: Name identifying this declaration.
      path: Path to the input or output resource.
    """

    kind: str | None = None
    name: str | None = None
    path: str | None = None


@dataclass(frozen=True)
class Build:
    """
    title: Parsed build section of .arxproject.toml.
    attributes:
      src_dir: Src dir.
      package: Package.
      out_dir: Out dir.
      mode: Selected processing mode.
    """

    src_dir: str | None = None
    package: str | None = None
    out_dir: str | None = None
    mode: str | None = None


@dataclass(frozen=True)
class BuildSystem:
    """
    title: Parsed build-system section of .arxproject.toml.
    attributes:
      dependencies: Dependencies.
    """

    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArxpmDependencyGroup:
    """
    title: Legacy placeholder for removed ``[arxpm.*]`` sections.
    attributes:
      dependencies: Dependencies.
    """

    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class Arxpm:
    """
    title: Legacy placeholder for the removed ``[arxpm]`` section.
    attributes:
      dependencies: Dependencies.
      dependencies_dev: Dependencies dev.
      extras: Extras.
    """

    dependencies: ArxpmDependencyGroup | None = None
    dependencies_dev: ArxpmDependencyGroup | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Tests:
    """
    title: Parsed tests section of .arxproject.toml.
    attributes:
      paths: Paths to the input or output resources.
      exclude: Exclude.
      file_pattern: File pattern.
      function_pattern: Function pattern.
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
      project: Project.
      environment: Environment used by the subprocess or compiler.
      build: Build.
      build_system: Build system.
      dependency_groups: Dependency groups.
      arxpm: Arxpm.
      tests: Tests.
      source_path: Path to source.
    """

    project: Project
    environment: Environment | None = None
    build: Build | None = None
    build_system: BuildSystem = field(default_factory=BuildSystem)
    dependency_groups: dict[str, tuple[DependencyGroupEntry, ...]] = field(
        default_factory=dict
    )
    arxpm: Arxpm | None = None
    tests: Tests | None = None
    source_path: Path | None = None

    def __post_init__(self) -> None:
        """
        title: Normalize effective build-system defaults.
        """
        dependencies = _normalize_build_system_dependencies(
            self.build_system.dependencies,
            self.project.requires_arx,
        )
        object.__setattr__(
            self,
            "build_system",
            BuildSystem(dependencies=dependencies),
        )


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    """
    title: Load and cache the ``.arxproject.toml`` JSON schema.
    returns: Loaded and cache the ``.arxproject.toml`` JSON schema.
    """
    with (
        files("aix.schema")
        .joinpath("arxproject.json")
        .open(encoding="utf-8") as fh
    ):
        return cast(dict[str, Any], json.load(fh))


def _build_author(data: dict[str, Any]) -> Author:
    """
    title: Build one Author dataclass from its validated mapping.
    parameters:
      data: Data to process.
    returns: Constructed one Author dataclass from its validated mapping.
    """
    return Author(name=data["name"], email=data.get("email"))


def _build_project(data: dict[str, Any]) -> Project:
    """
    title: Build the Project dataclass from its validated mapping.
    parameters:
      data: Data to process.
    returns: Constructed the Project dataclass from its validated mapping.
    """
    authors = tuple(_build_author(entry) for entry in data.get("authors", []))
    return Project(
        name=data["name"],
        version=data["version"],
        requires_arx=data.get("requires-arx"),
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
      data: Data to process.
    returns: Constructed one dependency-group entry from validated manifest
      data.
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
      data: Data to process.
    returns: Constructed dependency groups from their validated mapping.
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
      data: Data to process.
    returns: Constructed the Tests dataclass from its validated mapping.
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


def _build_build_system(
    data: dict[str, Any] | None,
    project: Project,
) -> BuildSystem:
    """
    title: Build the BuildSystem dataclass with effective defaults.
    parameters:
      data: Data to process.
      project: Project.
    returns: Constructed the BuildSystem dataclass with effective defaults.
    """
    if data is None:
        return BuildSystem(
            dependencies=(
                _default_build_system_dependency(project.requires_arx),
            )
        )

    dependencies = tuple(data.get("dependencies", ()))
    return BuildSystem(
        dependencies=_normalize_build_system_dependencies(
            dependencies,
            project.requires_arx,
        )
    )


def _resolved_src_dir(build: Build | None) -> str:
    """
    title: Resolve the effective source directory for one project.
    parameters:
      build: Build.
    returns: Resolved the effective source directory for one project.
    """
    if build is None or build.src_dir is None:
        return _DEFAULT_SRC_DIR
    return build.src_dir


def resolve_source_root(project: ArxProject) -> Path:
    """
    title: Resolve the effective source root from manifest defaults.
    parameters:
      project: Project.
    returns: Resolved the effective source root from manifest defaults.
    """
    if project.source_path is None:
        raise ArxProjectError(
            "cannot resolve the project source root without a manifest path"
        )
    return (
        project.source_path.parent / _resolved_src_dir(project.build)
    ).resolve()


def _reject_arxpm_sections(data: dict[str, Any]) -> None:
    """
    title: Reject removed ``[arxpm]`` manifest sections with a clear error.
    parameters:
      data: Data to process.
    """
    if "arxpm" not in data:
        return
    raise ArxProjectError(
        ".arxproject.toml does not support [arxpm] sections. "
        "Declare dependencies in [project] using "
        'dependencies = ["name", "name>=1.0,<2", "name @ ../path"].'
    )


def _reject_toolchain_sections(data: dict[str, Any]) -> None:
    """
    title: Reject removed ``[toolchain]`` manifest sections.
    parameters:
      data: Data to process.
    """
    if "toolchain" not in data:
        return
    raise ArxProjectError(
        ".arxproject.toml does not support [toolchain] sections. "
        "Declare compiler/build requirements in [build-system] using "
        'dependencies = ["arxlang..."].'
    )


def _validate_dependency(value: str, location: str) -> None:
    """
    title: Validate one dependency entry from ``.arxproject.toml``.
    parameters:
      value: Value to process.
      location: Source coordinates associated with the operation.
    """
    try:
        Requirement(value)
    except InvalidRequirement as err:
        raise ArxProjectError(
            f".arxproject.toml {location} must be a valid dependency "
            'requirement like "http", "sciarx>=0.0.3,<1", or '
            '"mylib @ ../mylib".'
        ) from err


def _validate_project(data: dict[str, Any]) -> None:
    """
    title: Validate project-only settings rules after schema validation.
    parameters:
      data: Data to process.
    """
    requires_arx = data.get("requires-arx")
    if requires_arx is not None:
        _validate_requires_arx(requires_arx)

    for index, value in enumerate(data.get("dependencies", ())):
        _validate_dependency(value, f"project.dependencies[{index}]")


def _validate_build_system_dependency(value: str, location: str) -> None:
    """
    title: Validate one installable build-system dependency requirement.
    parameters:
      value: Value to process.
      location: Source coordinates associated with the operation.
    """
    try:
        Requirement(value)
    except InvalidRequirement as err:
        raise ArxProjectError(
            f".arxproject.toml {location} must be a valid dependency "
            'requirement like "arxlang>=1.0,<2".'
        ) from err


def _validate_build_system(
    data: dict[str, Any] | None,
    project: dict[str, Any],
) -> None:
    """
    title: Validate build-system-only settings after schema validation.
    parameters:
      data: Data to process.
      project: Project.
    """
    raw_dependencies: tuple[str, ...] = ()
    if data is not None:
        raw_dependencies = tuple(cast(list[str], data.get("dependencies", ())))

    for index, value in enumerate(raw_dependencies):
        _validate_build_system_dependency(
            value,
            f"build-system.dependencies[{index}]",
        )

    if _has_arxlang_dependency(raw_dependencies):
        return

    _validate_build_system_dependency(
        _default_build_system_dependency(
            cast(str | None, project.get("requires-arx"))
        ),
        "build-system.dependencies default arxlang dependency",
    )


def _validate_requires_arx(value: str) -> None:
    """
    title: Validate a ``project.requires-arx`` version specifier.
    parameters:
      value: Value to process.
    """
    if not value.strip():
        raise ArxProjectError(
            ".arxproject.toml project.requires-arx must not be empty."
        )

    try:
        SpecifierSet(value)
    except InvalidSpecifier as err:
        raise ArxProjectError(
            ".arxproject.toml project.requires-arx must be a valid "
            'version specifier like ">=1.0,<2".'
        ) from err


def _validate_dependency_group_name(name: str, location: str) -> None:
    """
    title: Validate one dependency-group name.
    parameters:
      name: Name identifying the declaration or operation.
      location: Source coordinates associated with the operation.
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
      name: Name identifying the declaration or operation.
    returns: Normalized one dependency-group name for semantic comparison.
    """
    return _DEPENDENCY_GROUP_NORMALIZE_PATTERN.sub("-", name).lower()


def _dependency_group_name_mapping(
    dependency_groups: dict[str, list[Any]],
) -> dict[str, str]:
    """
    title: Map normalized dependency-group names to their declared names.
    parameters:
      dependency_groups: Dependency groups.
    returns: 'Result of this operation: map normalized dependency-group names
      to their declared names.'
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
      entries: Entries.
    returns: Collected included group names from raw dependency-group entries.
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
      dependency_groups: Dependency groups.
      normalized_names: Normalized names.
    """
    visited: set[str] = set()

    def visit(name: str, ancestry: list[str]) -> None:
        """
        title: Visit one dependency group while checking for include cycles.
        parameters:
          name: Name identifying the declaration or operation.
          ancestry: Ancestry.
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
      data: Data to process.
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
      data: Data to process.
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
      data: Data to process.
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
      data: Data to process.
    """
    _reject_arxpm_sections(data)
    _reject_toolchain_sections(data)
    _reject_legacy_environment_kind(data.get("environment"))

    try:
        validate(instance=data, schema=_schema())
    except ValidationError as err:
        raise ArxProjectError(
            f".arxproject.toml failed schema validation: {err.message}"
        ) from err

    _validate_project(data["project"])
    _validate_build_system(data.get("build-system"), data["project"])
    _validate_dependency_groups(data)
    _validate_environment(data.get("environment"))


def _build_arx_project(
    data: dict[str, Any],
    source_path: Path | None,
) -> ArxProject:
    """
    title: Build the ArxProject dataclass from its validated mapping.
    parameters:
      data: Data to process.
      source_path: Path to source.
    returns: Constructed the ArxProject dataclass from its validated mapping.
    """
    environment_data = data.get("environment")
    build_data = data.get("build")
    project = _build_project(data["project"])
    return ArxProject(
        project=project,
        environment=(
            Environment(**environment_data)
            if environment_data is not None
            else None
        ),
        build=Build(**build_data) if build_data is not None else None,
        build_system=_build_build_system(data.get("build-system"), project),
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
      author: Author.
    returns: Converted one Author dataclass into a TOML-safe mapping.
    """
    data = {"name": author.name}
    if author.email is not None:
        data["email"] = author.email
    return data


def _settings_to_data(settings: ArxProject) -> dict[str, Any]:
    """
    title: Convert settings dataclasses into raw manifest data.
    parameters:
      settings: Settings.
    returns: Converted settings dataclasses into raw manifest data.
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
    if settings.project.requires_arx is not None:
        project["requires-arx"] = settings.project.requires_arx
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

    default_build_system_dependencies = _normalize_build_system_dependencies(
        (),
        settings.project.requires_arx,
    )
    if settings.build_system.dependencies != default_build_system_dependencies:
        data["build-system"] = {
            "dependencies": list(settings.build_system.dependencies)
        }

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
        if settings.build.package is not None:
            build["package"] = settings.build.package
        if settings.build.out_dir is not None:
            build["out_dir"] = settings.build.out_dir
        if settings.build.mode is not None:
            build["mode"] = settings.build.mode
        data["build"] = build

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
      value: Value to process.
    returns: 'Result of this operation: quote one TOML basic string with
      JSON-compatible escapes.'
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
      lines: Source or output lines.
      key: Key selecting the entry.
      values: Values to process, in order.
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
      lines: Source or output lines.
      key: Key selecting the entry.
      values: Values to process, in order.
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
      lines: Source or output lines.
      project: Project.
    """
    lines.append("[project]")
    lines.append(f"name = {_format_toml_string(project.name)}")
    lines.append(f"version = {_format_toml_string(project.version)}")
    if project.requires_arx is not None:
        lines.append(
            f"requires-arx = {_format_toml_string(project.requires_arx)}"
        )
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
      lines: Source or output lines.
      dependency_groups: Dependency groups.
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
      lines: Source or output lines.
      environment: Environment used by the subprocess or compiler.
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
      lines: Source or output lines.
      build: Build.
    """
    if build is None:
        return
    lines.extend(("", "[build]"))
    if build.src_dir is not None:
        lines.append(f"src_dir = {_format_toml_string(build.src_dir)}")
    if build.package is not None:
        lines.append(f"package = {_format_toml_string(build.package)}")
    if build.out_dir is not None:
        lines.append(f"out_dir = {_format_toml_string(build.out_dir)}")
    if build.mode is not None:
        lines.append(f"mode = {_format_toml_string(build.mode)}")


def _append_build_system(
    lines: list[str],
    build_system: BuildSystem,
    project: Project,
) -> None:
    """
    title: Append the canonical ``[build-system]`` section when needed.
    parameters:
      lines: Source or output lines.
      build_system: Build system.
      project: Project.
    """
    default_dependencies = _normalize_build_system_dependencies(
        (),
        project.requires_arx,
    )
    if build_system.dependencies == default_dependencies:
        return
    lines.extend(("", "[build-system]"))
    _append_string_array(lines, "dependencies", build_system.dependencies)


def _append_tests(lines: list[str], tests: Tests | None) -> None:
    """
    title: Append the canonical ``[tests]`` section when present.
    parameters:
      lines: Source or output lines.
      tests: Tests.
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
    title: Serialize settings into canonical ``.arxproject.toml``
      text.
    parameters:
      settings: Settings.
    returns: 'Result of this operation: serialize settings into canonical
      ``.arxproject.toml`` text.'
    """
    _validate_data(_settings_to_data(settings))

    lines: list[str] = []
    _append_project(lines, settings.project)
    _append_build_system(lines, settings.build_system, settings.project)
    _append_dependency_groups(lines, settings.dependency_groups)
    _append_environment(lines, settings.environment)
    _append_build(lines, settings.build)
    _append_tests(lines, settings.tests)
    return "\n".join(lines) + "\n"


def write_settings(
    settings: ArxProject,
    path: str | Path = DEFAULT_CONFIG_FILENAME,
) -> Path:
    """
    title: Write canonical ``.arxproject.toml`` text to disk.
    parameters:
      settings: Settings.
      path: Path to the input or output resource.
    returns: 'Result of this operation: write canonical ``.arxproject.toml``
      text to disk.'
    """
    target = Path(path)
    target.write_text(dump_settings(settings), encoding="utf-8")
    return target


def find_config_file(start: Path | None = None) -> Path | None:
    """
    title: Walk upward from ``start`` to locate ``.arxproject.toml``.
    parameters:
      start: Starting position.
    returns: 'Result of this operation: walk upward from ``start``
      to locate ``.arxproject.toml``.'
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
      content: Content to process.
      source_path: Path to source.
    returns: Parsed and validate one ``.arxproject.toml`` string.
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
      path: Path to the input or output resource.
    returns: Loaded and validate ``.arxproject.toml`` into a typed dataclass.
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
