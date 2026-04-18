"""
title: Parse and validate ``.arxproject.toml`` project settings.
"""

from __future__ import annotations

import json
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
    """

    name: str
    version: str
    edition: str | None = None
    description: str | None = None
    license: str | None = None
    authors: tuple[Author, ...] = ()


@dataclass(frozen=True)
class Environment:
    """
    title: Parsed environment section of .arxproject.toml.
    attributes:
      kind:
        type: str | None
      name:
        type: str | None
    """

    kind: str | None = None
    name: str | None = None


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
    title: One dependency group under ``[arxpm.*]``.
    attributes:
      dependencies:
        type: tuple[str, Ellipsis]
    """

    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class Arxpm:
    """
    title: Parsed arxpm section plus known dependency subtables.
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
      arxpm:
        type: Arxpm | None
      source_path:
        type: Path | None
    """

    project: Project
    environment: Environment | None = None
    build: Build | None = None
    toolchain: Toolchain | None = None
    arxpm: Arxpm | None = None
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
    )


def _build_dependency_group(
    data: dict[str, Any] | None,
) -> ArxpmDependencyGroup | None:
    """
    title: Build one dependency group from its validated mapping.
    parameters:
      data:
        type: dict[str, Any] | None
    returns:
      type: ArxpmDependencyGroup | None
    """
    if data is None:
        return None
    return ArxpmDependencyGroup(
        dependencies=tuple(data.get("dependencies", ())),
    )


def _build_arxpm(data: dict[str, Any] | None) -> Arxpm | None:
    """
    title: Build the Arxpm dataclass from its validated mapping.
    parameters:
      data:
        type: dict[str, Any] | None
    returns:
      type: Arxpm | None
    """
    if data is None:
        return None
    known_keys = {"dependencies", "dependencies-dev"}
    extras = {k: v for k, v in data.items() if k not in known_keys}
    return Arxpm(
        dependencies=_build_dependency_group(data.get("dependencies")),
        dependencies_dev=_build_dependency_group(data.get("dependencies-dev")),
        extras=extras,
    )


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
        arxpm=_build_arxpm(data.get("arxpm")),
        source_path=source_path,
    )


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

    try:
        validate(instance=data, schema=_schema())
    except ValidationError as err:
        raise ArxProjectError(
            f".arxproject.toml failed schema validation: {err.message}"
        ) from err

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
