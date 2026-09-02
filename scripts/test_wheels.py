#!/usr/bin/env python3
"""
title: Audit and smoke-test built package artifacts.
summary: |-

  The default mode creates an isolated virtual environment and lets pip resolve
  third-party dependencies. `--current-environment` is a local/offline aid: it
  installs the six wheels into a clean target directory without dependencies
  and uses the caller's existing third-party packages. CI and release
  rehearsals
  must use the default isolated mode.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tarfile
import tempfile
import venv

from dataclasses import dataclass
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile


@dataclass(frozen=True)
class PackageArtifact:
    """
    title: Describe one package artifact contract.
    attributes:
      directory:
        type: str
      distribution:
        type: str
      import_name:
        type: str
    """

    directory: str
    distribution: str
    import_name: str


PACKAGES = (
    PackageArtifact("astx", "astx", "astx"),
    PackageArtifact("irx", "pyirx", "irx"),
    PackageArtifact("arx", "arxlang", "arx"),
    PackageArtifact("arxpy", "arxpy", "arxpy"),
    PackageArtifact("aix", "airx", "aix"),
    PackageArtifact("arxjit", "arxjit", "arxjit"),
)

REQUIRED_IRX_NATIVE_ASSETS = (
    "irx/builder/runtime/arrow/native/irx_arrow_runtime.cc",
    "irx/builder/runtime/arrow/native/irx_arrow_c_abi.h",
    "irx/builder/runtime/arrow/native/irx_record_batch.cpp",
    "irx/builder/runtime/arrow/native/irx_record_batch.h",
    "irx/builder/runtime/list/native/irx_list_runtime.c",
    "irx/builder/runtime/list/native/irx_list_runtime.h",
    "irx/builder/runtime/errors/native/irx_error_runtime.c",
)

SCALAR_MODULE = """```
title: Installed wheel scalar smoke
```
import answer from support

fn main() -> i32:
  ```
  title: main
  ```
  return answer()
"""

SUPPORT_MODULE = """```
title: Installed wheel support module
```
fn answer() -> i32:
  ```
  title: answer
  ```
  return 0
"""

CLASS_MODULE = """```
title: Installed wheel class smoke
```
class Counter:
  ```
  title: Counter
  ```
  @[public, mutable]
  value: i32 = 1

  fn get(self) -> i32:
    ```
    title: get
    ```
    return self.value

fn main() -> i32:
  ```
  title: main
  ```
  var counter: Counter = Counter()
  return counter.get() - 1
"""

LIST_MODULE = """```
title: Installed wheel list smoke
```
fn main() -> i32:
  ```
  title: main
  ```
  var values: list[i32] = range(0, 1)
  return values[0]
"""

TENSOR_MODULE = """```
title: Installed wheel tensor smoke
```
fn main() -> i32:
  ```
  title: main
  ```
  var values: tensor[i32, 2] = [4, 5]
  return values[1] - 5
"""

SMOKE_DRIVER = r"""
from pathlib import Path

import aix
import arx
import arxjit
import astx
import irx
import pyarrow as pa

from arxpy import Compiler
from irx.record_batch import (
    IrxColumnType,
    RecordBatchBuilder,
    RecordBatchSchema,
    RecordBatchStreamWriter,
)

root = Path.cwd()
compiler = Compiler()
for source_name in (
    "main.x",
    "class_smoke.x",
    "list_smoke.x",
    "tensor_smoke.x",
):
    artifact = compiler.compile_file(
        root / source_name,
        output=root / source_name.removesuffix(".x"),
    )
    result = compiler.run(artifact, timeout=30)
    if result.exit_code != 0:
        raise RuntimeError(
            f"{source_name} returned {result.exit_code}: {result.stderr}"
        )

schema = RecordBatchSchema()
schema.add_field("value", IrxColumnType.INT32, nullable=False)
builder = RecordBatchBuilder(schema)
builder.append_int32(0, 42)
batch = builder.finish()
writer = RecordBatchStreamWriter.open_buffer(schema)
writer.write_batch(batch)
writer.close()
data = writer.buffer_data()
table = pa.ipc.open_stream(pa.py_buffer(data)).read_all()
if table.column("value").to_pylist() != [42]:
    raise RuntimeError("RecordBatch/PyArrow wheel smoke returned wrong data")
batch.release()
builder.release()
writer.release()
schema.release()
print("wheel smoke passed")
"""


def _single_artifact(directory: Path, pattern: str) -> Path:
    """
    title: Return exactly one artifact matching a package build pattern.
    parameters:
      directory:
        type: Path
      pattern:
        type: str
    returns:
      type: Path
    """
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one {pattern} in {directory}, found {len(matches)}"
        )
    return matches[0]


def audit_artifacts(workspace: Path) -> tuple[Path, ...]:
    """
    title: Validate artifact completeness and return the wheel paths.
    parameters:
      workspace:
        type: Path
    returns:
      type: tuple[Path, Ellipsis]
    """
    expected_license = (workspace / "LICENSE").read_bytes()
    wheels: list[Path] = []
    versions: set[str] = set()

    for package in PACKAGES:
        dist_dir = workspace / "packages" / package.directory / "dist"
        wheel = _single_artifact(dist_dir, "*.whl")
        sdist = _single_artifact(dist_dir, "*.tar.gz")
        wheels.append(wheel)

        with ZipFile(wheel) as archive:
            names = archive.namelist()
            metadata_name = next(
                name for name in names if name.endswith(".dist-info/METADATA")
            )
            metadata = BytesParser().parsebytes(archive.read(metadata_name))
            if metadata["Name"] != package.distribution:
                raise RuntimeError(
                    f"{wheel} has distribution name {metadata['Name']!r}"
                )
            versions.add(str(metadata["Version"]))
            if metadata["Requires-Python"] != ">=3.10,<4":
                raise RuntimeError(
                    f"{wheel} has unexpected Requires-Python "
                    f"{metadata['Requires-Python']!r}"
                )

            license_names = [
                name for name in names if name.endswith("/licenses/LICENSE")
            ]
            if len(license_names) != 1:
                raise RuntimeError(f"{wheel} must contain exactly one LICENSE")
            if archive.read(license_names[0]) != expected_license:
                raise RuntimeError(f"{wheel} contains a stale LICENSE")

            typed_marker = f"{package.import_name}/py.typed"
            if typed_marker not in names:
                raise RuntimeError(f"{wheel} is missing {typed_marker}")

            if package.directory == "irx":
                missing = [
                    asset
                    for asset in REQUIRED_IRX_NATIVE_ASSETS
                    if asset not in names
                ]
                if missing:
                    raise RuntimeError(
                        f"{wheel} is missing native source assets: {missing}"
                    )

        with tarfile.open(sdist, "r:gz") as archive:
            license_members = [
                member
                for member in archive.getmembers()
                if member.name.endswith("/LICENSE")
            ]
            if len(license_members) != 1:
                raise RuntimeError(f"{sdist} must contain exactly one LICENSE")
            extracted = archive.extractfile(license_members[0])
            if extracted is None or extracted.read() != expected_license:
                raise RuntimeError(f"{sdist} contains a stale LICENSE")

    if len(versions) != 1:
        raise RuntimeError(f"package artifacts are not lockstep: {versions}")
    return tuple(wheels)


def _venv_python(environment: Path) -> Path:
    """
    title: Return the Python executable inside a virtual environment.
    parameters:
      environment:
        type: Path
    returns:
      type: Path
    """
    if os.name == "nt":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def _install_wheels(
    wheels: tuple[Path, ...],
    work_dir: Path,
    current_environment: bool,
) -> tuple[Path, dict[str, str]]:
    """
    title: Install wheels and return the smoke Python plus environment.
    parameters:
      wheels:
        type: tuple[Path, Ellipsis]
      work_dir:
        type: Path
      current_environment:
        type: bool
    returns:
      type: tuple[Path, dict[str, str]]
    """
    env = dict(os.environ)
    if current_environment:
        target = work_dir / "installed"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-deps",
                "--target",
                str(target),
                *(str(wheel) for wheel in wheels),
            ],
            check=True,
        )
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(target) if not existing else f"{target}{os.pathsep}{existing}"
        )
        return Path(sys.executable), env

    environment = work_dir / "venv"
    venv.EnvBuilder(with_pip=True, clear=True).create(environment)
    python = _venv_python(environment)
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            *(str(wheel) for wheel in wheels),
        ],
        check=True,
    )
    env.pop("PYTHONPATH", None)
    return python, env


def run_smoke(
    workspace: Path,
    wheels: tuple[Path, ...],
    current_environment: bool,
) -> None:
    """
    title: Install and execute the wheel-only compiler and runtime smoke set.
    parameters:
      workspace:
        type: Path
      wheels:
        type: tuple[Path, Ellipsis]
      current_environment:
        type: bool
    """
    smoke_root = workspace / ".tmp" / "wheel-smoke"
    smoke_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="run-",
        dir=smoke_root,
    ) as temporary_path:
        work_dir = Path(temporary_path)
        python, env = _install_wheels(
            wheels,
            work_dir,
            current_environment,
        )

        sources = {
            "main.x": SCALAR_MODULE,
            "support.x": SUPPORT_MODULE,
            "class_smoke.x": CLASS_MODULE,
            "list_smoke.x": LIST_MODULE,
            "tensor_smoke.x": TENSOR_MODULE,
        }
        for name, content in sources.items():
            (work_dir / name).write_text(content, encoding="utf-8")
        driver = work_dir / "smoke.py"
        driver.write_text(SMOKE_DRIVER, encoding="utf-8")
        env["IRX_NATIVE_CACHE_DIR"] = str(work_dir / "native-cache")
        subprocess.run(
            [str(python), str(driver)],
            cwd=work_dir,
            env=env,
            check=True,
            timeout=300,
        )


def main() -> int:
    """
    title: Run artifact audits and the selected installed-wheel smoke mode.
    returns:
      type: int
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="inspect artifacts without installing or running them",
    )
    parser.add_argument(
        "--current-environment",
        action="store_true",
        help="reuse installed third-party dependencies (not for CI/release)",
    )
    args = parser.parse_args()

    workspace = Path(__file__).resolve().parents[1]
    wheels = audit_artifacts(workspace)
    if not args.audit_only:
        run_smoke(
            workspace,
            wheels,
            args.current_environment,
        )
    print("wheel artifact audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
