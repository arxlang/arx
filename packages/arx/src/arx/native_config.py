"""
title: Typed declarative native package configuration.
"""

from __future__ import annotations

import json

from dataclasses import dataclass
from typing import Mapping, cast

from irx.native import NativeArtifactKind


def toml_native_value(value: str | tuple[str, ...]) -> str:
    """
    title: Quote native TOML values without invalid Unicode surrogate escapes.
    parameters:
      value:
        type: str | tuple[str, Ellipsis]
    returns:
      type: str
    """
    return json.dumps(value, ensure_ascii=False)


@dataclass(frozen=True)
class NativeArtifactConfig:
    """
    title: One package-relative native build input.
    attributes:
      kind:
        type: NativeArtifactKind
      path:
        type: str
      include_dirs:
        type: tuple[str, Ellipsis]
    """

    kind: NativeArtifactKind
    path: str
    include_dirs: tuple[str, ...] = ()


@dataclass(frozen=True)
class NativeFeatureConfig:
    """
    title: Native artifacts and system libraries for one local feature.
    attributes:
      artifacts:
        type: tuple[NativeArtifactConfig, Ellipsis]
      libraries:
        type: tuple[str, Ellipsis]
    """

    artifacts: tuple[NativeArtifactConfig, ...] = ()
    libraries: tuple[str, ...] = ()


@dataclass(frozen=True)
class NativeConfig:
    """
    title: Versioned native features and exact module bindings.
    attributes:
      version:
        type: int
      features:
        type: Mapping[str, NativeFeatureConfig]
      modules:
        type: Mapping[str, tuple[str, Ellipsis]]
    """

    version: int
    features: Mapping[str, NativeFeatureConfig]
    modules: Mapping[str, tuple[str, ...]]

    @classmethod
    def from_data(cls, data: Mapping[str, object]) -> NativeConfig:
        """
        title: Build typed records after whole-manifest schema validation.
        parameters:
          data:
            type: Mapping[str, object]
        returns:
          type: NativeConfig
        """
        features = cast(Mapping[str, Mapping[str, object]], data["features"])
        modules = cast(Mapping[str, Mapping[str, object]], data["modules"])
        result: dict[str, NativeFeatureConfig] = {}
        for name, feature in features.items():
            artifacts = cast(
                list[Mapping[str, object]], feature.get("artifacts", [])
            )
            result[name] = NativeFeatureConfig(
                artifacts=tuple(
                    NativeArtifactConfig(
                        kind=cast(NativeArtifactKind, artifact["kind"]),
                        path=cast(str, artifact["path"]),
                        include_dirs=tuple(
                            cast(list[str], artifact.get("include_dirs", []))
                        ),
                    )
                    for artifact in artifacts
                ),
                libraries=tuple(cast(list[str], feature.get("libraries", []))),
            )
        return cls(
            version=cast(int, data["version"]),
            features=result,
            modules={
                name: tuple(cast(list[str], module["features"]))
                for name, module in modules.items()
            },
        )

    def to_data(self) -> dict[str, object]:
        """
        title: Serialize native configuration for validation and persistence.
        returns:
          type: dict[str, object]
        """
        return {
            "version": self.version,
            "features": {
                name: {
                    "artifacts": [
                        {
                            "kind": artifact.kind,
                            "path": artifact.path,
                            "include_dirs": list(artifact.include_dirs),
                        }
                        for artifact in feature.artifacts
                    ],
                    "libraries": list(feature.libraries),
                }
                for name, feature in self.features.items()
            },
            "modules": {
                name: {"features": list(features)}
                for name, features in self.modules.items()
            },
        }

    def append_toml(self, lines: list[str]) -> None:
        """
        title: Write a canonical native table without build-script hooks.
        parameters:
          lines:
            type: list[str]
        """
        lines.extend(["", "[native]", f"version = {self.version}"])
        for name, feature in self.features.items():
            prefix = f"native.features.{toml_native_value(name)}"
            lines.extend(
                [
                    "",
                    f"[{prefix}]",
                    f"libraries = {toml_native_value(feature.libraries)}",
                ]
            )
            for artifact in feature.artifacts:
                includes = toml_native_value(artifact.include_dirs)
                lines.extend(
                    [
                        "",
                        f"[[{prefix}.artifacts]]",
                        f"kind = {toml_native_value(artifact.kind)}",
                        f"path = {toml_native_value(artifact.path)}",
                        f"include_dirs = {includes}",
                    ]
                )
        for name, features in self.modules.items():
            lines.extend(
                [
                    "",
                    f"[native.modules.{toml_native_value(name)}]",
                    f"features = {toml_native_value(features)}",
                ]
            )
