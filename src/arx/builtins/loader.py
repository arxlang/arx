"""
title: Bundled builtin-module resource loader.
summary: >-
  Expose compiler-facing helpers for discovering and reading pure-Arx builtin
  modules shipped inside the installed ``arx`` Python package.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import cast

BUILTIN_NAMESPACE = "builtins"
BUILTIN_SOURCE_EXTENSION = ".x"
_BUILTIN_RESOURCE_PACKAGE = "arx.builtins"


@dataclass(frozen=True)
class BuiltinModuleAsset:
    """
    title: One bundled builtin module asset.
    attributes:
      logical_name:
        type: str
      specifier:
        type: str
      origin:
        type: str
      source:
        type: str
      is_package:
        type: bool
    """

    logical_name: str
    specifier: str
    origin: str
    source: str
    is_package: bool


def is_builtin_module_specifier(specifier: str) -> bool:
    """
    title: Return whether one specifier targets the bundled builtins.
    parameters:
      specifier:
        type: str
    returns:
      type: bool
    """
    return specifier == BUILTIN_NAMESPACE or specifier.startswith(
        f"{BUILTIN_NAMESPACE}."
    )


def list_builtin_modules() -> tuple[str, ...]:
    """
    title: List bundled builtin module names.
    returns:
      type: tuple[str, Ellipsis]
    """
    module_names: list[str] = []
    seen: set[str] = set()

    for module_name in _iter_builtin_modules(_builtin_root()):
        if module_name in seen:
            raise LookupError(
                f"ambiguous builtin module '{module_name}' in package data"
            )
        seen.add(module_name)
        module_names.append(module_name)

    return tuple(module_names)


def resolve_builtin_resource(module_name: str) -> Traversable:
    """
    title: Resolve one builtin logical module name to a packaged resource.
    parameters:
      module_name:
        type: str
    returns:
      type: Traversable
    """
    resource, _relative_path, _is_package = _resolve_builtin_module_entry(
        module_name
    )
    return resource


def get_builtin_source(module_name: str) -> str:
    """
    title: Return the bundled source text for one builtin module.
    parameters:
      module_name:
        type: str
    returns:
      type: str
    """
    return cast(
        str,
        resolve_builtin_resource(module_name).read_text(encoding="utf-8"),
    )


def load_builtin_module(specifier: str) -> BuiltinModuleAsset:
    """
    title: Load one builtin module from packaged resources.
    parameters:
      specifier:
        type: str
    returns:
      type: BuiltinModuleAsset
    """
    if specifier == BUILTIN_NAMESPACE:
        resource = _join_resource(_builtin_root(), "__init__.x")
        if not resource.is_file():
            raise LookupError(specifier)
        relative_path = "__init__.x"
        logical_name = ""
        is_package = True
    else:
        if not is_builtin_module_specifier(specifier):
            raise LookupError(specifier)
        logical_name = specifier.removeprefix(f"{BUILTIN_NAMESPACE}.")
        resource, relative_path, is_package = _resolve_builtin_module_entry(
            logical_name
        )

    return BuiltinModuleAsset(
        logical_name=logical_name,
        specifier=specifier,
        origin=f"{_BUILTIN_RESOURCE_PACKAGE}:{relative_path}",
        source=cast(str, resource.read_text(encoding="utf-8")),
        is_package=is_package,
    )


def _builtin_root() -> Traversable:
    """
    title: Return the package-resource root for bundled builtin assets.
    returns:
      type: Traversable
    """
    return files(_BUILTIN_RESOURCE_PACKAGE)


def _iter_builtin_modules(
    directory: Traversable,
    prefix: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """
    title: Recursively collect bundled builtin module names.
    parameters:
      directory:
        type: Traversable
      prefix:
        type: tuple[str, Ellipsis]
    returns:
      type: tuple[str, Ellipsis]
    """
    module_names: list[str] = []

    for child in sorted(directory.iterdir(), key=lambda entry: entry.name):
        if child.name.startswith(".") or child.name == "__pycache__":
            continue

        child_prefix = (*prefix, child.name)
        if child.is_dir():
            package_name = ".".join(child_prefix)
            init_resource = child.joinpath("__init__.x")
            if init_resource.is_file():
                module_names.append(package_name)
            module_names.extend(_iter_builtin_modules(child, child_prefix))
            continue

        if child.name == "__init__.x":
            continue
        if not child.name.endswith(BUILTIN_SOURCE_EXTENSION):
            continue

        module_names.append(
            ".".join(
                (*prefix, child.name.removesuffix(BUILTIN_SOURCE_EXTENSION))
            )
        )

    return tuple(module_names)


def _resolve_builtin_module_entry(
    module_name: str,
) -> tuple[Traversable, str, bool]:
    """
    title: Resolve one builtin logical module entry.
    parameters:
      module_name:
        type: str
    returns:
      type: tuple[Traversable, str, bool]
    """
    parts = _split_module_name(module_name)
    file_parts = (*parts[:-1], f"{parts[-1]}{BUILTIN_SOURCE_EXTENSION}")
    init_parts = (*parts, "__init__.x")

    root = _builtin_root()
    file_resource = _join_resource(root, *file_parts)
    init_resource = _join_resource(root, *init_parts)
    file_relative = "/".join(file_parts)
    init_relative = "/".join(init_parts)

    has_file = file_resource.is_file()
    has_init = init_resource.is_file()

    if has_file and has_init:
        raise LookupError(
            "ambiguous builtin module "
            f"'{module_name}': both '{file_relative}' and "
            f"'{init_relative}' exist"
        )
    if has_init:
        return init_resource, init_relative, True
    if has_file:
        return file_resource, file_relative, False
    raise LookupError(module_name)


def _join_resource(root: Traversable, *parts: str) -> Traversable:
    """
    title: Join one package resource path from traversable parts.
    parameters:
      root:
        type: Traversable
      parts:
        type: str
        variadic: positional
    returns:
      type: Traversable
    """
    resource = root
    for part in parts:
        resource = resource.joinpath(part)
    return resource


def _split_module_name(module_name: str) -> tuple[str, ...]:
    """
    title: Validate and split one dotted builtin module name.
    parameters:
      module_name:
        type: str
    returns:
      type: tuple[str, Ellipsis]
    """
    if (
        not module_name
        or module_name.startswith(".")
        or module_name.endswith(".")
        or ".." in module_name
    ):
        raise LookupError(module_name)
    return tuple(module_name.split("."))
