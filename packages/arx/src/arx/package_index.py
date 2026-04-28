"""
title: Discover installed Arx source packages.
summary: >-
  Build a scoped index of Arx packages installed as Python distributions.
"""

from __future__ import annotations

import re
import sys

from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

from arx import builtins as arx_builtins
from arx import settings as arx_settings

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

_ARX_MODULE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DEPENDENCY_NAME_PATTERN = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
)
_DISTRIBUTION_NORMALIZE_PATTERN = re.compile(r"[-_.]+")
_RESERVED_MODULE_NAMES = frozenset(
    {
        "stdlib",
        arx_builtins.BUILTIN_NAMESPACE,
    }
)
_SOURCE_SUFFIXES = frozenset({".x"})


@dataclass(frozen=True)
class InstalledArxPackage:
    """
    title: One installed Arx source package.
    attributes:
      module_name:
        type: str
      source_root:
        type: Path
      distribution_name:
        type: str
    """

    module_name: str
    source_root: Path
    distribution_name: str


@dataclass(frozen=True)
class InstalledArxPackageIndex:
    """
    title: Indexed installed Arx source packages.
    attributes:
      packages:
        type: dict[str, InstalledArxPackage]
      missing_distributions:
        type: frozenset[str]
      conflicts:
        type: dict[str, tuple[InstalledArxPackage, Ellipsis]]
    """

    packages: dict[str, InstalledArxPackage] = field(default_factory=dict)
    missing_distributions: frozenset[str] = frozenset()
    conflicts: dict[str, tuple[InstalledArxPackage, ...]] = field(
        default_factory=dict
    )

    def missing_distribution_for_module(self, module_name: str) -> str | None:
        """
        title: Return a missing distribution matching one import head.
        parameters:
          module_name:
            type: str
        returns:
          type: str | None
        """
        normalized = normalize_distribution_name(module_name)
        for distribution_name in self.missing_distributions:
            if normalize_distribution_name(distribution_name) == normalized:
                return distribution_name
        return None


def normalize_distribution_name(name: str) -> str:
    """
    title: Normalize a Python distribution name for comparisons.
    parameters:
      name:
        type: str
    returns:
      type: str
    """
    return _DISTRIBUTION_NORMALIZE_PATTERN.sub("-", name).lower()


def extract_dependency_name(dependency: str) -> str | None:
    """
    title: Extract the distribution name from one dependency string.
    parameters:
      dependency:
        type: str
    returns:
      type: str | None
    """
    match = _DEPENDENCY_NAME_PATTERN.match(dependency)
    if match is None:
        return None
    return match.group("name")


def discover_installed_arx_packages(
    start: Path | None = None,
) -> InstalledArxPackageIndex:
    """
    title: Discover installed Arx packages from project dependencies.
    parameters:
      start:
        type: Path | None
    returns:
      type: InstalledArxPackageIndex
    """
    config = arx_settings.find_config_file(start=start)
    if config is None:
        return InstalledArxPackageIndex()

    try:
        settings = arx_settings.load_settings(config)
    except arx_settings.ArxProjectError:
        return InstalledArxPackageIndex()

    return discover_installed_arx_packages_from_dependencies(
        settings.project.dependencies
    )


def discover_installed_arx_packages_from_dependencies(
    dependencies: Iterable[str],
) -> InstalledArxPackageIndex:
    """
    title: Discover installed Arx packages from dependency strings.
    parameters:
      dependencies:
        type: Iterable[str]
    returns:
      type: InstalledArxPackageIndex
    """
    package_entries: dict[str, InstalledArxPackage] = {}
    conflict_entries: dict[str, tuple[InstalledArxPackage, ...]] = {}
    missing_distributions: set[str] = set()
    pending = [
        dependency_name
        for dependency in dependencies
        if (dependency_name := extract_dependency_name(dependency)) is not None
    ]
    visited: set[str] = set()

    while pending:
        dependency_name = pending.pop(0)
        normalized_name = normalize_distribution_name(dependency_name)
        if normalized_name in visited:
            continue
        visited.add(normalized_name)

        try:
            distribution = importlib_metadata.distribution(dependency_name)
        except importlib_metadata.PackageNotFoundError:
            missing_distributions.add(dependency_name)
            continue

        for package in _arx_packages_from_distribution(distribution):
            _add_package(package_entries, conflict_entries, package)

        for requirement in distribution.requires or ():
            requirement_name = extract_dependency_name(requirement)
            if requirement_name is None:
                continue
            if normalize_distribution_name(requirement_name) in visited:
                continue
            pending.append(requirement_name)

    return InstalledArxPackageIndex(
        packages=package_entries,
        missing_distributions=frozenset(missing_distributions),
        conflicts=conflict_entries,
    )


def _add_package(
    packages: dict[str, InstalledArxPackage],
    conflicts: dict[str, tuple[InstalledArxPackage, ...]],
    package: InstalledArxPackage,
) -> None:
    """
    title: Add one package to the mutable package index.
    parameters:
      packages:
        type: dict[str, InstalledArxPackage]
      conflicts:
        type: dict[str, tuple[InstalledArxPackage, Ellipsis]]
      package:
        type: InstalledArxPackage
    """
    conflict = conflicts.get(package.module_name)
    if conflict is not None:
        conflicts[package.module_name] = (*conflict, package)
        return

    existing = packages.get(package.module_name)
    if existing is None:
        packages[package.module_name] = package
        return

    del packages[package.module_name]
    conflicts[package.module_name] = (existing, package)


def _arx_packages_from_distribution(
    distribution: importlib_metadata.Distribution,
) -> tuple[InstalledArxPackage, ...]:
    """
    title: Extract Arx package roots from one installed distribution.
    parameters:
      distribution:
        type: importlib_metadata.Distribution
    returns:
      type: tuple[InstalledArxPackage, Ellipsis]
    """
    files = distribution.files
    if files is None:
        return ()

    distribution_name = _distribution_name(distribution)
    packages: list[InstalledArxPackage] = []
    for distribution_file in files:
        if distribution_file.name != arx_settings.DEFAULT_CONFIG_FILENAME:
            continue

        manifest_path = Path(
            str(distribution.locate_file(distribution_file))
        ).resolve()
        if not manifest_path.is_file():
            continue

        source_root = manifest_path.parent
        if not _has_arx_sources(source_root):
            continue

        module_name = _module_name_from_manifest(manifest_path, source_root)
        if module_name is None or module_name in _RESERVED_MODULE_NAMES:
            continue

        packages.append(
            InstalledArxPackage(
                module_name=module_name,
                source_root=source_root,
                distribution_name=distribution_name,
            )
        )

    return tuple(packages)


def _distribution_name(
    distribution: importlib_metadata.Distribution,
) -> str:
    """
    title: Return the canonical display name for one distribution.
    parameters:
      distribution:
        type: importlib_metadata.Distribution
    returns:
      type: str
    """
    try:
        return str(distribution.metadata["Name"])
    except KeyError:
        return str(distribution)


def _has_arx_sources(source_root: Path) -> bool:
    """
    title: Return whether one package root contains Arx source files.
    parameters:
      source_root:
        type: Path
    returns:
      type: bool
    """
    for source_path in source_root.rglob("*"):
        if source_path.suffix in _SOURCE_SUFFIXES and source_path.is_file():
            return True
    return False


def _module_name_from_manifest(
    manifest_path: Path,
    source_root: Path,
) -> str | None:
    """
    title: Derive the top-level Arx module name for an installed package.
    parameters:
      manifest_path:
        type: Path
      source_root:
        type: Path
    returns:
      type: str | None
    """
    data = _load_manifest_data(manifest_path)
    if data is None:
        return None

    module_name = _manifest_package_name(data)
    if module_name is None:
        module_name = source_root.name

    if _ARX_MODULE_NAME_PATTERN.fullmatch(module_name) is None:
        return None
    return module_name


def _load_manifest_data(manifest_path: Path) -> dict[str, Any] | None:
    """
    title: Load a packaged manifest without full project validation.
    parameters:
      manifest_path:
        type: Path
    returns:
      type: dict[str, Any] | None
    """
    try:
        data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None

    if not isinstance(data, dict):
        return None
    return data


def _manifest_package_name(data: dict[str, Any]) -> str | None:
    """
    title: Extract an optional ``[build].package`` value.
    parameters:
      data:
        type: dict[str, Any]
    returns:
      type: str | None
    """
    build = data.get("build")
    if not isinstance(build, dict):
        return None

    package_name = build.get("package")
    if not isinstance(package_name, str):
        return None
    return package_name
