"""
title: Resolve native package metadata at the Arx host boundary.
"""

from __future__ import annotations

import sys

from pathlib import Path, PureWindowsPath

import astx

from irx.analysis.module_interfaces import ParsedModule
from irx.native import NativeArtifact, NativeBinding, NativeFeature
from packaging.utils import canonicalize_name

from arx import settings
from arx.native_config import NativeFeatureConfig

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def package_path(root: Path, value: str, *, directory: bool = False) -> Path:
    """
    title: Resolve a contained package file or directory, including symlinks.
    parameters:
      root:
        type: Path
      value:
        type: str
      directory:
        type: bool
    returns:
      type: Path
    """
    path = Path(value)
    if path.is_absolute() or PureWindowsPath(value).is_absolute():
        raise settings.ArxProjectError("native paths must be package-relative")
    if "\x00" in value or "\\" in value or ".." in path.parts:
        raise settings.ArxProjectError("invalid native package path")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise settings.ArxProjectError("native path escapes its package root")
    exists = resolved.is_dir() if directory else resolved.is_file()
    if not exists:
        raise settings.ArxProjectError(
            f"native package input not found: {value}"
        )
    return resolved


def resolve_feature(
    name: str, config: NativeFeatureConfig, root: Path
) -> NativeFeature:
    """
    title: Convert validated configuration to resolved IRx native inputs.
    parameters:
      name:
        type: str
      config:
        type: NativeFeatureConfig
      root:
        type: Path
    returns:
      type: NativeFeature
    """
    return NativeFeature(
        name,
        artifacts=tuple(
            NativeArtifact(
                kind=artifact.kind,
                path=package_path(root, artifact.path),
                include_dirs=tuple(
                    package_path(root, path, directory=True)
                    for path in artifact.include_dirs
                ),
            )
            for artifact in config.artifacts
        ),
        linker_flags=tuple(f"-l{library}" for library in config.libraries),
    )


def native_project(manifest: Path) -> settings.ArxProject | None:
    """
    title: Load native settings without changing legacy source-only manifests.
    parameters:
      manifest:
        type: Path
    returns:
      type: settings.ArxProject | None
    """
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Legacy import-root probing tolerates invalid non-native manifests.
        return None
    if "native" not in data:
        return None
    return settings.load_settings(manifest)


def prepare_module(
    module: astx.Module,
    key: str,
    origin: Path,
    *,
    manifest: Path | None = None,
    owner: str | None = None,
    package_name: str | None = None,
    source_root: Path | None = None,
) -> ParsedModule:
    """
    title: Attach native capabilities only to a module's actual package origin.
    parameters:
      module:
        type: astx.Module
      key:
        type: str
      origin:
        type: Path
      manifest:
        type: Path | None
      owner:
        type: str | None
      package_name:
        type: str | None
      source_root:
        type: Path | None
    returns:
      type: ParsedModule
    """
    manifest = manifest or settings.find_config_file(origin.parent)
    project = native_project(manifest) if manifest is not None else None
    if project is None or project.native is None or manifest is None:
        return ParsedModule(key, module, key, str(origin))
    native = project.native
    package_name = package_name or (
        project.build.package
        if project.build is not None and project.build.package is not None
        else project.project.name.replace("-", "_")
    )
    if any(
        name != package_name and not name.startswith(f"{package_name}.")
        for name in native.modules
    ):
        raise settings.ArxProjectError(
            "native modules must belong to their declaring package "
            f"'{package_name}'"
        )
    features = native.modules.get(key)
    if features is None:
        return ParsedModule(key, module, key, str(origin))
    if source_root is None:
        root = settings.resolve_source_root(project)
        candidate = root / package_name
        source_root = candidate if candidate.is_dir() else root
    if not source_root.resolve().is_relative_to(manifest.parent.resolve()):
        raise settings.ArxProjectError(
            "native source root escapes its package"
        )
    parts = key.split(".")[1:]
    base = source_root.joinpath(*parts)
    expected = (
        (base.with_suffix(".x"), base / "__init__.x")
        if parts
        else (source_root / "__init__.x",)
    )
    if origin.resolve() not in tuple(path.resolve() for path in expected):
        raise settings.ArxProjectError(
            f"native module '{key}' origin does not match its package mapping"
        )
    if not origin.resolve().is_relative_to(source_root.resolve()):
        raise settings.ArxProjectError("native module escapes its source root")
    identity = canonicalize_name(owner or project.project.name)
    qualified = tuple(
        f"package:{identity}:{package_name}:{name}" for name in features
    )
    declarations = tuple(
        node
        for node in module.nodes
        if isinstance(node, astx.FunctionPrototype)
        and getattr(node, "is_extern", False)
    )
    if not declarations:
        raise settings.ArxProjectError(
            f"native module '{key}' has no extern declarations"
        )
    return ParsedModule(
        key,
        module,
        key,
        str(origin),
        native_features=tuple(
            resolve_feature(
                qualified_name, native.features[name], manifest.parent
            )
            for name, qualified_name in zip(features, qualified)
        ),
        native_bindings=tuple(
            NativeBinding(node, qualified) for node in declarations
        ),
    )
