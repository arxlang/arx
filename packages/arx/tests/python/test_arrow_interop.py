"""
title: Compiled public Arx Arrow API end-to-end regressions.
"""

import shutil
import socket
import subprocess
import sys

from pathlib import Path
from textwrap import dedent

import pyarrow as pa
import pytest

from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.main import FileImportResolver
from arx.parser import Parser
from irx.analysis.module_interfaces import ParsedModule
from irx.builder.runtime.errors import parse_runtime_failure_output
from llvmlite import binding as llvm

ROOT = Path(__file__).resolve().parents[4]
HAS_NATIVE = (
    shutil.which("clang") is not None and shutil.which("c++") is not None
)
pytestmark = pytest.mark.skipif(
    not HAS_NATIVE, reason="native compiler required"
)

ROUNDTRIP = """
import (IPCReader, IPCWriter, RecordBatch, Schema) from stdlib.arrow

fn check_id(batch: RecordBatch, row: i64) -> none:
  if batch.ncols() == 0:
    return none
  else:
    if batch.is_null(0, row):
      return none
    else:
      assert batch.get_i64(0, row) == 42
      return none

fn check_text(batch: RecordBatch, row: i64) -> none:
  if batch.ncols() < 2:
    return none
  else:
    if batch.is_null(1, row):
      return none
    else:
      assert batch.get_utf8(1, row) == "λ"
      return none

fn check_rows(batch: RecordBatch) -> none:
  var row: i64 = 0
  while row < batch.nrows():
    check_id(batch, row)
    check_text(batch, row)
    row = row + 1
  return none

fn main() -> i32:
  var reader: IPCReader = IPCReader()
  reader.open_FORMAT("input.arrow")
  var schema: Schema = reader.schema()
  var writer: IPCWriter = IPCWriter(schema)
  writer.open_FORMAT("output.arrow")
  while reader.next():
    var batch: RecordBatch = reader.batch()
    assert batch.schema().equals(schema)
    print(batch.nrows())
    check_rows(batch)
    writer.write(batch)
  writer.close()
  writer.close()
  reader.close()
  reader.close()
  return 0
"""


def compile_program(source: str, path: Path) -> None:
    """
    title: Exercise parsing, module semantics, LLVM verification and linking.
    parameters:
      source:
        type: str
      path:
        type: Path
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Arrow integration test\n```\n" + source
    )
    module = Parser().parse(Lexer().lex(), "arrow_test")
    builder = ArxBuilder()
    root = ParsedModule("arrow_test", module)
    resolver = FileImportResolver(())
    llvm.parse_assembly(builder.translate_modules(root, resolver)).verify()
    assert (
        "record_batch"
        in builder.translator.runtime_features.active_feature_names()
    )
    builder.build_modules(root, resolver, str(path))


@pytest.fixture(scope="module", params=("file", "stream"))
def roundtrip(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> tuple[str, Path]:
    """
    title: Compile one binary for each standard Arrow IPC format.
    parameters:
      request:
        type: pytest.FixtureRequest
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: tuple[str, Path]
    """
    format_name = str(request.param)
    path = tmp_path_factory.mktemp(f"arrow-{format_name}") / "roundtrip"
    compile_program(ROUNDTRIP.replace("FORMAT", format_name), path)
    return format_name, path


def run_roundtrip(
    roundtrip: tuple[str, Path], tmp_path: Path, batches: list[pa.RecordBatch]
) -> subprocess.CompletedProcess[str]:
    """
    title: Write PyArrow input and run a standalone Arx consumer and producer.
    parameters:
      roundtrip:
        type: tuple[str, Path]
      tmp_path:
        type: Path
      batches:
        type: list[pa.RecordBatch]
    returns:
      type: subprocess.CompletedProcess[str]
    """
    format_name, executable = roundtrip
    new_writer = (
        pa.ipc.new_file if format_name == "file" else pa.ipc.new_stream
    )
    with new_writer(
        str(tmp_path / "input.arrow"), batches[0].schema
    ) as writer:
        for batch in batches:
            writer.write_batch(batch)
    return subprocess.run(
        [str(executable)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_public_roundtrip_nullable_metadata_and_empty_batches(
    roundtrip: tuple[str, Path], tmp_path: Path
) -> None:
    """
    title: Preserve schema metadata, timezone, nulls and batch boundaries.
    parameters:
      roundtrip:
        type: tuple[str, Path]
      tmp_path:
        type: Path
    """
    schema = pa.schema(
        [
            pa.field("id", pa.int64(), metadata={b"unit": b"count"}),
            pa.field("text", pa.string()),
            pa.field("time", pa.timestamp("ns", tz="Europe/Paris")),
        ],
        metadata={b"binary": b"\x00\xff"},
    )
    batch = pa.RecordBatch.from_arrays(
        [
            pa.array([42, None]),
            pa.array(["λ", None]),
            pa.array([123, None], type=schema.field(2).type),
        ],
        schema=schema,
    )
    expected = [batch.slice(0, 0), batch, batch]
    result = run_roundtrip(roundtrip, tmp_path, expected)
    assert result.returncode == 0, result.stderr
    format_name, _ = roundtrip
    if format_name == "file":
        reader = pa.ipc.open_file(str(tmp_path / "output.arrow"))
        actual = [
            reader.get_batch(i) for i in range(reader.num_record_batches)
        ]
    else:
        actual = list(pa.ipc.open_stream(str(tmp_path / "output.arrow")))
    assert len(actual) == len(expected)
    assert all(
        got.equals(want, check_metadata=True)
        for got, want in zip(actual, expected)
    )


def test_public_zero_columns_with_rows(
    roundtrip: tuple[str, Path], tmp_path: Path
) -> None:
    """
    title: Zero-column schemas do not erase nonzero Arrow row counts.
    parameters:
      roundtrip:
        type: tuple[str, Path]
      tmp_path:
        type: Path
    """
    batch = pa.RecordBatch.from_struct_array(
        pa.array([{}, {}], type=pa.struct([]))
    )
    result = run_roundtrip(roundtrip, tmp_path, [batch])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "2"


@pytest.mark.parametrize("failure", ("type", "unsupported", "nul"))
def test_public_input_errors(
    roundtrip: tuple[str, Path], tmp_path: Path, failure: str
) -> None:
    """
    title: Reject wrong types and text that Arx str cannot represent.
    parameters:
      roundtrip:
        type: tuple[str, Path]
      tmp_path:
        type: Path
      failure:
        type: str
    """
    if failure == "type":
        arrays = [pa.array([42], type=pa.int32())]
    elif failure == "unsupported":
        arrays = [pa.array([b"binary"])]
    else:
        arrays = [pa.array([42]), pa.array(["λ\x00hidden"])]
    batch = pa.record_batch(
        arrays, names=[f"col{i}" for i in range(len(arrays))]
    )
    result = run_roundtrip(roundtrip, tmp_path, [batch])
    assert result.returncode == 1
    report = parse_runtime_failure_output(result.stderr)
    assert report is not None
    assert report.code == "ARX-RUNTIME-ARROW-001"
    assert report.line == 0


@pytest.mark.parametrize("payload", (b"not arrow", b""))
def test_public_corrupt_input(
    roundtrip: tuple[str, Path], tmp_path: Path, payload: bytes
) -> None:
    """
    title: Corrupt and empty files produce structured runtime diagnostics.
    parameters:
      roundtrip:
        type: tuple[str, Path]
      tmp_path:
        type: Path
      payload:
        type: bytes
    """
    (tmp_path / "input.arrow").write_bytes(payload)
    result = subprocess.run(
        [str(roundtrip[1])],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert "ARX-RUNTIME-ARROW-001" in result.stderr


@pytest.fixture(scope="module")
def demonstrations(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    title: Build and execute every checked-in Arx/PyArrow demonstration.
    parameters:
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: Path
    """
    directory = tmp_path_factory.mktemp("arrow-examples")
    for scenario in ("files", "c"):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "examples/arrow/run.py"),
                "--directory",
                str(directory),
                "--scenario",
                scenario,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    return directory


def test_executable_demonstrations(demonstrations: Path) -> None:
    """
    title: Real compiled programs demonstrate IPC, C sharing and TCP.
    parameters:
      demonstrations:
        type: Path
    """
    assert (demonstrations / "component.so").is_file()


def test_schema_mismatch_example(demonstrations: Path, tmp_path: Path) -> None:
    """
    title: The independently developed Arx consumer rejects a wrong schema.
    parameters:
      demonstrations:
        type: Path
      tmp_path:
        type: Path
    """
    wrong = pa.record_batch([pa.array([42, 7])], names=["wrong"])
    with pa.ipc.new_file(
        str(tmp_path / "python.arrow"), wrong.schema
    ) as writer:
        writer.write_batch(wrong)
    result = subprocess.run(
        [str(demonstrations / "read_file")],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 1


@pytest.fixture(scope="module")
def tcp_available() -> None:
    """
    title: Report an explicit sandbox socket prohibition, not a transport pass.
    """
    try:
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
    except PermissionError as error:
        pytest.skip(f"loopback socket access prohibited: {error}")


def test_tcp_demonstration(demonstrations: Path, tcp_available: None) -> None:
    """
    title: Run compiled Arx multi-batch TCP exchange in both directions.
    parameters:
      demonstrations:
        type: Path
      tcp_available:
        type: None
    """
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples/arrow/run.py"),
            "--directory",
            str(demonstrations),
            "--scenario",
            "tcp",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "TCP: multiple batches in both directions passed" in result.stdout


@pytest.mark.parametrize("interruption", (False, True))
def test_compiled_tcp_failure(
    demonstrations: Path, interruption: bool, tcp_available: None
) -> None:
    """
    title: Connection refusal and stream interruption are runtime failures.
    parameters:
      demonstrations:
        type: Path
      interruption:
        type: bool
      tcp_available:
        type: None
    """
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        if interruption:
            server.listen(1)
            server.settimeout(30)
        command = dedent(
            f"""
            import ctypes
            lib = ctypes.CDLL({str(demonstrations / "component.so")!r})
            receive = lib.component__receive_tcp
            receive.argtypes = [ctypes.c_char_p, ctypes.c_int32]
            receive.restype = ctypes.c_int32
            receive(b"127.0.0.1", {port})
            """
        )
        process = subprocess.Popen(
            [sys.executable, "-c", command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            if interruption:
                connection, _ = server.accept()
                sink = pa.BufferOutputStream()
                schema = pa.schema([pa.field("id", pa.int64())])
                with pa.ipc.new_stream(sink, schema):
                    pass
                # Send a schema, then terminate without an IPC end marker.
                with connection:
                    connection.sendall(sink.getvalue().to_pybytes()[:-8])
            _, stderr = process.communicate(timeout=30)
            assert process.returncode == 1
            assert b"ARX-RUNTIME-ARROW-001" in stderr
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def test_tcp_sources_compile_without_network(tmp_path: Path) -> None:
    """
    title: Always verify TCP producer and consumer compile/link, even offline.
    parameters:
      tmp_path:
        type: Path
    """
    examples = ROOT / "examples/arrow"
    command = (
        "import sys; from pathlib import Path; "
        f"sys.path.insert(0, {str(examples)!r}); "
        "from run import build; "
        f"build(Path({str(examples / 'tcp.x')!r}), "
        f"Path({str(tmp_path / 'tcp.so')!r}), shared=True)"
    )
    result = subprocess.run(
        [sys.executable, "-c", command],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
