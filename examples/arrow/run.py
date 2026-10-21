"""
title: Execute compiled Arx interoperability examples against PyArrow.
summary: Run with --directory pointing to a writable build directory.
"""

from __future__ import annotations

import argparse
import ctypes
import gc
import socket
import subprocess

from pathlib import Path

import pyarrow as pa

from pyarrow.cffi import ffi

from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.main import FileImportResolver
from arx.parser import Parser
from irx.analysis.module_interfaces import ParsedModule
from irx.builder.runtime.linking import compile_native_artifacts

EXAMPLES = Path(__file__).resolve().parent
EXPECTED_BATCHES = 2


def build(source: Path, output: Path, shared: bool = False) -> Path:
    """
    title: Compile actual Arx source and its registered runtime artifacts.
    parameters:
      source:
        type: Path
      output:
        type: Path
      shared:
        type: bool
    returns:
      type: Path
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    ArxIO.file_to_buffer(str(source))
    module = Parser().parse(Lexer().lex(), source.stem)
    data_source = source.parent / "data.x"
    if not data_source.is_file():
        data_source = EXAMPLES / "data.x"
    resolver = FileImportResolver((str(source), str(data_source)))
    builder = ArxBuilder()
    object_path = output.with_suffix(".o") if shared else output
    builder.build_modules(
        ParsedModule(module.name, module, origin=str(source)),
        resolver,
        str(object_path),
        link=not shared,
    )
    if shared:
        features = builder.translator.runtime_features
        (output.parent / "native").mkdir(parents=True, exist_ok=True)
        native = compile_native_artifacts(
            features.native_artifacts(), output.parent / "native"
        )
        subprocess.run(
            [
                "c++",
                "-shared",
                "-o",
                str(output),
                str(object_path),
                *(str(path) for path in native.objects),
                *native.linker_flags,
                *features.linker_flags(),
            ],
            check=True,
        )
    return output


def expected_batch() -> pa.RecordBatch:
    """
    title: Construct the independently declared Python-side dataset.
    returns:
      type: pa.RecordBatch
    """
    schema = pa.schema(
        [
            pa.field("id", pa.int64(), nullable=False),
            pa.field("score", pa.float64(), nullable=False),
            pa.field("active", pa.bool_(), nullable=False),
        ]
    )
    return pa.RecordBatch.from_arrays(
        [pa.array([42, 7]), pa.array([1.5, 2.5]), pa.array([True, False])],
        schema=schema,
    )


def files(directory: Path) -> None:
    """
    title: Run separate-process IPC file exchange in both directions.
    parameters:
      directory:
        type: Path
    """
    writer = build(EXAMPLES / "write_file.x", directory / "write_file")
    subprocess.run([str(writer)], cwd=directory, check=True, timeout=30)
    reader = pa.ipc.open_file(str(directory / "arx.arrow"))
    assert reader.get_batch(0).equals(expected_batch(), check_metadata=True)
    with pa.ipc.new_file(
        str(directory / "python.arrow"), expected_batch().schema
    ) as output:
        output.write_batch(expected_batch())
    consumer = build(EXAMPLES / "read_file.x", directory / "read_file")
    subprocess.run([str(consumer)], cwd=directory, check=True, timeout=30)
    typed = build(EXAMPLES / "types.x", directory / "types")
    subprocess.run([str(typed)], cwd=directory, check=True, timeout=30)
    batches = list(pa.ipc.open_stream(str(directory / "typed.arrow")))
    assert [batch.num_rows for batch in batches] == [1, 0, 1]
    assert all(column.null_count == 1 for column in batches[2].columns)
    print("IPC files: both directions passed")


def c_interfaces(directory: Path) -> None:
    """
    title: Share buffers produced by real compiled Arx in the Python process.
    parameters:
      directory:
        type: Path
    """
    library = ctypes.CDLL(
        str(build(EXAMPLES / "component.x", directory / "component.so", True))
    )
    for name, arity in (
        ("produce_stream", 1),
        ("produce_array", 2),
        ("consume_stream", 1),
        ("consume_array", 2),
    ):
        function = getattr(library, f"component__{name}")
        setattr(library, name, function)
        function.argtypes = [ctypes.c_int64] * arity
        function.restype = ctypes.c_int32
    stream = ffi.new("struct ArrowArrayStream *")
    stream_address = int(ffi.cast("uintptr_t", stream))
    assert library.produce_stream(stream_address) == 0
    # Arx locals have already gone out of scope before PyArrow imports.
    reader = pa.RecordBatchReader._import_from_c(stream_address)
    gc.collect()
    assert reader.read_next_batch().equals(expected_batch())
    assert list(reader) == []
    reader.close()
    assert stream.release == ffi.NULL
    array = ffi.new("struct ArrowArray *")
    schema = ffi.new("struct ArrowSchema *")
    array_address = int(ffi.cast("uintptr_t", array))
    schema_address = int(ffi.cast("uintptr_t", schema))
    assert library.produce_array(array_address, schema_address) == 0
    batch = pa.RecordBatch._import_from_c(array_address, schema_address)
    gc.collect()
    assert batch.equals(expected_batch(), check_metadata=True)
    expected_batch()._export_to_c(array_address, schema_address)
    assert library.consume_array(array_address, schema_address) == 0
    assert array.release == ffi.NULL
    assert schema.release == ffi.NULL
    pa.RecordBatchReader.from_batches(
        expected_batch().schema, [expected_batch()]
    )._export_to_c(stream_address)
    assert library.consume_stream(stream_address) == 0
    assert stream.release == ffi.NULL
    print("C Data/C Stream: compiled producer and consumer passed")


def tcp(directory: Path) -> None:
    """
    title: Run both TCP directions with ephemeral ports and separate processes.
    parameters:
      directory:
        type: Path
    """
    for direction in ("send", "receive"):
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            server.settimeout(30)
            port = server.getsockname()[1]
            source = directory / f"tcp_{direction}.x"
            # Generated launcher is ordinary Arx; serialization stays native.
            source.write_text(
                "```\ntitle: TCP example launcher\n```\n"
                f"import {direction} from tcp\n"
                "fn main() -> i32:\n"
                f'  return {direction}("127.0.0.1", {port})\n',
                encoding="utf-8",
            )
            (directory / "tcp.x").write_bytes(
                (EXAMPLES / "tcp.x").read_bytes()
            )
            (directory / "data.x").write_bytes(
                (EXAMPLES / "data.x").read_bytes()
            )
            binary = build(source, directory / f"tcp_{direction}")
            process = subprocess.Popen([str(binary)], cwd=directory)
            try:
                connection, _ = server.accept()
                # Arrow needs full reads/writes; raw sockets may transfer less
                # than requested. Closing this wrapper flushes before wait().
                with connection, connection.makefile("rwb") as io:
                    connection.settimeout(30)
                    if direction == "send":
                        batches = list(pa.ipc.open_stream(io))
                        assert len(batches) == EXPECTED_BATCHES
                        assert all(
                            batch.equals(expected_batch()) for batch in batches
                        )
                    else:
                        with pa.ipc.new_stream(
                            io, expected_batch().schema
                        ) as out:
                            out.write_batch(expected_batch())
                            out.write_batch(expected_batch())
                assert process.wait(timeout=30) == 0
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
    print("TCP: multiple batches in both directions passed")


def main() -> None:
    """
    title: Run one or all interoperability demonstrations.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument(
        "--scenario", choices=("all", "files", "c", "tcp"), default="all"
    )
    args = parser.parse_args()
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    for name, run in (("files", files), ("c", c_interfaces), ("tcp", tcp)):
        if args.scenario in ("all", name):
            run(directory)


if __name__ == "__main__":
    main()
