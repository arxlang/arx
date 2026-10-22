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
    "irx/builder/runtime/arrow/native/irx_arrow_series.h",
    "irx/builder/runtime/arrow/native/irx_arrow_c_abi.h",
    "irx/builder/runtime/arrow/native/irx_record_batch.cpp",
    "irx/builder/runtime/arrow/native/irx_record_batch.h",
    "irx/builder/runtime/arrow/native/irx_record_batch_api.cc",
    "irx/builder/runtime/arrow/native/irx_record_batch_api.h",
    "irx/builder/runtime/arrow/native/irx_batch_writer.h",
    "irx/builder/runtime/arrow/native/irx_parquet_io.h",
    "irx/builder/runtime/arrow/native/irx_parquet_options.h",
    "irx/builder/runtime/arrow/native/irx_parquet_commit.h",
    "irx/builder/runtime/parquet.py",
    "irx/builder/runtime/arrow/native/irx_parquet_bridge.cc",
    "irx/builder/runtime/arrow/native/irx_parquet_api.cc",
    "irx/builder/runtime/arrow/native/irx_record_batch_internal.h",
    "irx/builder/runtime/arrow/native/irx_record_batch_api_internal.h",
    "irx/parquet_options.py",
    "irx/builder/runtime/arrow/native/irx_parquet_io.cc",
    "irx/builder/runtime/list/native/irx_list_runtime.c",
    "irx/builder/runtime/list/native/irx_list_runtime.h",
    "irx/builder/runtime/errors/native/irx_error_runtime.c",
    "irx/builder/runtime/file/native/irx_file_runtime.c",
    "irx/builder/runtime/file/native/irx_file_runtime.h",
    "irx/builder/runtime/classes/native/irx_class_runtime.c",
    "irx/builder/runtime/classes/native/irx_class_runtime.h",
)

SCALAR_MODULE = """```
title: Installed wheel scalar smoke
```
import answer from support

fn main() -> i32:
  ```
  title: main
  ```
  return answer(value=0)
"""

SUPPORT_MODULE = """```
title: Installed wheel support module
```
fn answer(value: i32 = 0) -> i32:
  ```
  title: answer
  ```
  return value
"""

CLASS_MODULE = """```
title: Installed wheel class lifecycle smoke
```
class Counter:
  ```
  title: Counter
  ```
  value: i32 = 0
  @[public, static, mutable]
  destroyed: i32 = 0

  fn __init__(self, value: i32 = 1) -> none:
    ```
    title: __init__
    ```
    self.value = value
    return none

  fn __del__(self) -> none:
    ```
    title: __del__
    ```
    Counter.destroyed = Counter.destroyed + 1
    return none

fn make() -> Counter:
  ```
  title: make
  ```
  return Counter(value=7)

fn use() -> none:
  ```
  title: use
  ```
  var counter: Counter = make()
  var alias: Counter = counter
  counter = Counter()
  assert alias.value == 7
  return none

fn main() -> i32:
  ```
  title: main
  ```
  use()
  return Counter.destroyed - 2
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

FILE_MODULE = """```
title: Installed wheel file I/O smoke
```
fn main() -> i32:
  ```
  title: main
  ```
  var output: File = File("file-smoke.txt", mode="w")
  var alias: file = output
  assert alias.write(text="hello") == 5
  output.close()
  var input: file = open(file="file-smoke.txt")
  assert input.read() == "hello"
  return 0
"""

NATIVE_MODULE = """```
title: Installed external native package smoke
```
import Resource from native_fixture.owned
fn write_payload() -> none:
  ```
  title: write_payload
  ```
  var resource: Resource = Resource(size=1)
  assert resource.note(label="wheel π", value=cast(2, f64)) == 0
  assert resource.write(path="native-smoke.jpg") == 0
  return none
fn main() -> i32:
  ```
  title: main
  ```
  write_payload()
  return 0
"""

CSV_MODULE = """```
title: Stream CSV through checked DataFrame conversions
summary: Run from the repository root; input and output must be distinct files.
```
import (Schema, RecordBatch, CSV) from stdlib.arrow

fn main() -> i32:
  ```
  title: Convert every CSV batch without discarding rows
  ```
  var schema: Schema = Schema()
  schema.add("id", 3, false)
  var reader: CSV = CSV()
  reader.open_read_as("input.csv", schema)
  var writer: CSV = CSV()
  writer.open_write("compiled.csv", schema)
  while reader.next():
    var batch: RecordBatch = reader.batch()
    var frame: dataframe[id: i64] = cast(batch, dataframe[id: i64])
    var output: RecordBatch = cast(frame, RecordBatch)
    writer.write(output)
  writer.close()
  reader.close()
  return 0
"""

PARQUET_MODULE = """```
title: Installed Parquet interoperability and DataFrame smoke
```
import (Parquet, RecordBatch, Schema) from stdlib.arrow

fn main() -> i32:
  ```
  title: Convert all Python-produced Parquet batches in compiled Arx
  ```
  var reader: Parquet = Parquet()
  reader.open_read("python.parquet", batch_size=1)
  var schema: Schema = Schema()
  schema.add("id", 3, false)
  var writer: Parquet = Parquet()
  writer.open_write("compiled.parquet", schema, row_group_size=2)
  while reader.next():
    var batch: RecordBatch = reader.batch()
    var frame: dataframe[id: i64] = cast(batch, dataframe[id: i64])
    var copy: RecordBatch = cast(frame, RecordBatch)
    writer.write(copy)
  writer.close()
  reader.close()
  return 0
"""

NULLABLE_MODULE = """```
title: Installed wheel nullable Series smoke
```
fn main() -> i32:
  var frame: dataframe[x:i32 | none] = dataframe({x:[1, none]})
  var values: series[i32 | none] = frame.x + frame.x
  assert is_null(values[1])
  assert fill_null(values[0], 0) == 2
  var reversed: series[i32 | none] = values[::-1]
  assert is_null(reversed[0])
  assert fill_null(series_sum(values), cast(0, i64)) == 2
  values[1] = 4
  assert fill_null(values[1], 0) == 4
  var absent: nullable[i32] = none
  assert is_null(absent)
  var rich: dataframe[amount:decimal128[8,2]] = dataframe({amount:["1.25"]})
  assert rich.nrows() == 1
  return 0
"""

SMOKE_DRIVER = r"""
from pathlib import Path
from importlib import metadata

import aix
import arx
import arxjit
import astx
import irx
import pyarrow as pa
import pyarrow.parquet as pq

from arxpy import Compiler
from irx.record_batch import (
    CSV,
    Parquet,
    ParquetOptions,
    ParquetPredicate,
    RecordBatch,
    IrxColumnType,
    RecordBatchBuilder,
    RecordBatchSchema,
    RecordBatchStreamWriter,
    RecordBatchStreamReader,
)

root = Path.cwd()
compiler = Compiler()
pq.write_table(
    pa.table({"id": [1, 2, 3]}), root / "python.parquet", row_group_size=1
)
for source_name in (
    "main.x",
    "class_smoke.x",
    "list_smoke.x",
    "tensor_smoke.x",
    "file_smoke.x",
    "native_smoke.x",
    "csv_smoke.x",
    "parquet_smoke.x",
    "nullable_smoke.x",
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

if pq.read_table(root / "compiled.parquet").to_pydict() != {"id": [1, 2, 3]}:
    raise RuntimeError("Compiled Parquet wheel smoke returned wrong data")

dependency = metadata.distribution("arx-native-fixture")
expected = next(
    path for path in dependency.files if path.name == "expected.jpg"
)
if (root / "native-smoke.jpg").read_bytes() != Path(
    dependency.locate_file(expected)
).read_bytes():
    raise RuntimeError("external native wheel wrote unexpected JPEG bytes")

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
with RecordBatchStreamWriter.open_csv(schema, root / "python.csv") as csv:
    csv.write_batch(batch)
csv_reader = RecordBatchStreamReader.open_csv(
    root / "python.csv", schema=schema
)
with csv_reader as csv:
    csv_batch = csv.next_batch()
    if csv_batch is None or csv_batch.get_int32(0, 0) != 42:
        raise RuntimeError("CSV wheel smoke returned wrong data")
    csv_batch.release()
with CSV() as source, Parquet() as target:
    source.open_read(root / "python.csv", schema=schema)
    target.open_write(root / "facade.parquet", schema)
    for copied in source:
        target.write_batch(copied)
if pq.read_table(root / "facade.parquet").column("value").to_pylist() != [42]:
    raise RuntimeError("Unified CSV/Parquet wheel smoke returned wrong data")
batch.release()
builder.release()
writer.release()
schema.release()
rich = pa.record_batch(
    [pa.array([[b"a", None], None], type=pa.list_(pa.binary()))],
    names=["items"],
)
rich_schema = RecordBatchSchema.from_arrow(rich.schema)
rich_batch = RecordBatch.from_arrow(rich)
with Parquet() as target:
    target.open_write(root / "rich.parquet", rich_schema,
                      options=ParquetOptions(atomic=True))
    target.write_batch(rich_batch)
rich_batch.release()
rich_schema.release()
with Parquet() as source:
    source.open_read(root / "rich.parquet", options=ParquetOptions(
        columns=("items",),
        predicates=(ParquetPredicate("items", "is_valid"),),
    ))
    copied = source.next_batch()
    if copied is None or not copied.to_arrow().equals(rich.slice(0, 1)):
        raise RuntimeError("Rich Parquet wheel smoke returned wrong data")
    copied.release()
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

            if package.directory == "arx":
                if "arx/builtins/files.x" not in names:
                    raise RuntimeError(f"{wheel} is missing the File builtin")

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
            if package.directory == "arx" and not any(
                name.endswith("/src/arx/builtins/files.x")
                for name in archive.getnames()
            ):
                raise RuntimeError(f"{sdist} is missing the File builtin")
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


def build_native_fixture_wheel(workspace: Path, output: Path) -> Path:
    """
    title: Package the independent native test dependency without build hooks.
    parameters:
      workspace:
        type: Path
      output:
        type: Path
    returns:
      type: Path
    """
    fixture = workspace / "packages/arx/tests/fixtures/native-package"
    if not (fixture / ".arxproject.toml").is_file():
        raise FileNotFoundError(f"native wheel fixture is missing: {fixture}")
    wheel = output / "arx_native_fixture-0.0.0-py3-none-any.whl"
    info = "arx_native_fixture-0.0.0.dist-info"
    entries: dict[str, bytes] = {}
    for path in fixture.rglob("*"):
        if not path.is_file():
            continue
        name = f"native_fixture_data/{path.relative_to(fixture).as_posix()}"
        entries[name] = path.read_bytes()
    entries[f"{info}/METADATA"] = (
        b"Metadata-Version: 2.1\nName: arx-native-fixture\nVersion: 0.0.0\n"
    )
    entries[f"{info}/WHEEL"] = (
        b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    )
    entries[f"{info}/RECORD"] = "\n".join(
        f"{name},," for name in (*entries, f"{info}/RECORD")
    ).encode()
    with ZipFile(wheel, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return wheel


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
        dependency = build_native_fixture_wheel(workspace, work_dir)
        python, env = _install_wheels(
            (*wheels, dependency),
            work_dir,
            current_environment,
        )

        (work_dir / "input.csv").write_text("id\n1\n2\n3\n", encoding="utf-8")
        sources = {
            "main.x": SCALAR_MODULE,
            "support.x": SUPPORT_MODULE,
            "class_smoke.x": CLASS_MODULE,
            "list_smoke.x": LIST_MODULE,
            "tensor_smoke.x": TENSOR_MODULE,
            "file_smoke.x": FILE_MODULE,
            "native_smoke.x": NATIVE_MODULE,
            "csv_smoke.x": CSV_MODULE,
            "parquet_smoke.x": PARQUET_MODULE,
            "nullable_smoke.x": NULLABLE_MODULE,
        }
        (work_dir / ".arxproject.toml").write_text(
            '[project]\nname="wheel-consumer"\nversion="0"\n'
            'dependencies=["arx-native-fixture"]\n',
            encoding="utf-8",
        )
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
