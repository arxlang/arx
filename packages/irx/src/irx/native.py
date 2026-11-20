"""
title: Declarative native capabilities supplied by compiler hosts.
"""

from __future__ import annotations

import re

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping, get_args

import astx

from public import private, public

from irx.typecheck import typechecked

NativeArtifactKind = Literal[
    "c_source", "cxx_source", "object", "static_library"
]

ComputeKernel = Literal["sqrt", "exp"]


# Pure immutable names: analysis never imports LLVM or the builder registry.
# The default lowering registry verifies this exact contract before use.
BUILTIN_RUNTIME_FEATURES = frozenset(
    {
        "array",
        "arrow_compute",
        "buffer",
        "class",
        "dataframe",
        "errors",
        "exceptions",
        "file",
        "libc",
        "libm",
        "list",
        "parquet",
        "record_batch",
        "tensor",
        "text",
    }
)


@private
@typechecked
@dataclass(frozen=True)
class ComputeCapability:
    """
    title: One closed shared semantic/native compute contract.
    attributes:
      operation_id:
        type: int
      arity:
        type: int
      domain:
        type: str
      result:
        type: str
      max_ulps:
        type: int
    """

    operation_id: int
    arity: int
    domain: str
    result: str
    max_ulps: int


@private
@typechecked
def read_compute_catalog() -> Mapping[str, ComputeCapability]:
    """
    title: Read and validate the native operation table without loading LLVM.
    returns:
      type: Mapping[str, ComputeCapability]
    """
    path = (
        Path(__file__).parent
        / "builder/runtime/arrow/native"
        / "irx_arrow_compute_catalog.h"
    )
    operations: dict[str, ComputeCapability] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("//"):
            continue
        match = re.fullmatch(
            r"IRX_COMPUTE_OPERATION\(([A-Z_]+), ([1-9][0-9]*), "
            r"([a-z_]+), ([12]), (F64|NUMERIC|PRIMITIVE|BOOL|ANY), "
            r"(SAME|BOOL|SUM|MINMAX|MEAN|COUNT|BOOL_REDUCE), ([0-9]+)\)",
            line,
        )
        if match is None:
            raise ValueError("invalid native compute catalog entry")
        symbol, identifier, name, arity, domain, result, ulps = match.groups()
        if symbol != name.upper() or name in operations:
            raise ValueError("duplicate or mismatched compute operation")
        if int(identifier) > 2**31 - 1:
            raise ValueError("compute operation ID exceeds the native ABI")
        operations[name] = ComputeCapability(
            int(identifier), int(arity), domain, result, int(ulps)
        )
    identifiers = [value.operation_id for value in operations.values()]
    if not set(get_args(ComputeKernel)).issubset(operations) or len(
        identifiers
    ) != len(set(identifiers)):
        raise ValueError("native compute catalog disagrees with semantic API")
    return MappingProxyType(operations)


COMPUTE_CATALOG = read_compute_catalog()


@private
@typechecked
def validate_compute_kernel(kernel: ComputeKernel) -> None:
    """
    title: Enforce the closed catalog even without developer type checking.
    parameters:
      kernel:
        type: ComputeKernel
    """
    if kernel not in get_args(ComputeKernel):
        raise ValueError("unsupported compute kernel")


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
      compute:
        type: ComputeKernel | None
    """

    declaration: astx.FunctionPrototype
    features: tuple[str, ...]
    table_io: TableIOOperation | None = None
    compute: ComputeKernel | None = None

    def __init__(
        self,
        declaration: astx.FunctionPrototype,
        features: tuple[str, ...],
        table_io: TableIOOperation | None = None,
        compute: ComputeKernel | None = None,
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
          compute:
            type: ComputeKernel | None
        """
        if not features or any(not name.strip() for name in features):
            raise ValueError("native bindings require nonempty feature names")
        if len(features) != len(set(features)):
            raise ValueError("duplicate native binding features")
        if compute is not None:
            validate_compute_kernel(compute)
        if compute is not None and (
            table_io is not None or features != ("arrow_compute",)
        ):
            raise ValueError(
                "compute bindings require only the arrow_compute feature "
                "and cannot also bind table I/O"
            )
        object.__setattr__(self, "declaration", declaration)
        object.__setattr__(self, "features", features)
        object.__setattr__(self, "table_io", table_io)
        object.__setattr__(self, "compute", compute)
