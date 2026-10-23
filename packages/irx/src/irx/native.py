"""
title: Declarative native capabilities supplied by compiler hosts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import astx

from public import public

from irx.typecheck import typechecked

NativeArtifactKind = Literal[
    "c_source", "cxx_source", "object", "static_library"
]

TableIOOperation = Literal[
    "read_csv",
    "write_csv",
    "read_parquet",
    "write_parquet",
    "where",
    "csv_frame",
    "parquet_frame",
    "csv_write_frame",
    "parquet_write_frame",
]


@public
@typechecked
@dataclass(frozen=True, init=False)
class NativeArtifact:
    """
    title: Describe one native artifact required by a runtime feature.
    attributes:
      kind:
        type: NativeArtifactKind
      path:
        type: Path
      include_dirs:
        type: tuple[Path, Ellipsis]
      compile_flags:
        type: tuple[str, Ellipsis]
      link_flags:
        type: tuple[str, Ellipsis]
    """

    kind: NativeArtifactKind
    path: Path
    include_dirs: tuple[Path, ...] = ()
    compile_flags: tuple[str, ...] = ()
    link_flags: tuple[str, ...] = ()

    def __init__(
        self,
        kind: NativeArtifactKind,
        path: Path,
        include_dirs: tuple[Path, ...] = (),
        compile_flags: tuple[str, ...] = (),
        link_flags: tuple[str, ...] = (),
    ) -> None:
        """
        title: Validate an artifact and all collection items.
        parameters:
          kind:
            type: NativeArtifactKind
          path:
            type: Path
          include_dirs:
            type: tuple[Path, Ellipsis]
          compile_flags:
            type: tuple[str, Ellipsis]
          link_flags:
            type: tuple[str, Ellipsis]
        """
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "include_dirs", include_dirs)
        object.__setattr__(self, "compile_flags", compile_flags)
        object.__setattr__(self, "link_flags", link_flags)


@public
@typechecked
@dataclass(frozen=True, init=False)
class NativeFeature:
    """
    title: Immutable native dependency without executable symbol factories.
    attributes:
      name:
        type: str
      artifacts:
        type: tuple[NativeArtifact, Ellipsis]
      linker_flags:
        type: tuple[str, Ellipsis]
    """

    name: str
    artifacts: tuple[NativeArtifact, ...]
    linker_flags: tuple[str, ...]

    def __init__(
        self,
        name: str,
        artifacts: tuple[NativeArtifact, ...] = (),
        linker_flags: tuple[str, ...] = (),
    ) -> None:
        """
        title: Validate one explicitly supplied native feature.
        parameters:
          name:
            type: str
          artifacts:
            type: tuple[NativeArtifact, Ellipsis]
          linker_flags:
            type: tuple[str, Ellipsis]
        """
        if not name or name.strip() != name:
            raise ValueError("native feature names must be nonempty")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "linker_flags", linker_flags)


@public
@typechecked
@dataclass(frozen=True, init=False)
class NativeBinding:
    """
    title: Associate native requirements with one actual extern declaration.
    attributes:
      declaration:
        type: astx.FunctionPrototype
      features:
        type: tuple[str, Ellipsis]
      table_io:
        type: TableIOOperation | None
    """

    declaration: astx.FunctionPrototype
    features: tuple[str, ...]
    table_io: TableIOOperation | None = None

    def __init__(
        self,
        declaration: astx.FunctionPrototype,
        features: tuple[str, ...],
        table_io: TableIOOperation | None = None,
    ) -> None:
        """
        title: Validate a declaration identity and its feature names.
        parameters:
          declaration:
            type: astx.FunctionPrototype
          features:
            type: tuple[str, Ellipsis]
          table_io:
            type: TableIOOperation | None
        """
        if not features or any(not name.strip() for name in features):
            raise ValueError("native bindings require nonempty feature names")
        if len(features) != len(set(features)):
            raise ValueError("duplicate native binding features")
        object.__setattr__(self, "declaration", declaration)
        object.__setattr__(self, "features", features)
        object.__setattr__(self, "table_io", table_io)
