"""
title: Deterministic TCP example fragmentation tests without network access.
"""

import importlib.util
import io
import socket

from functools import partial
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pyarrow as pa
import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[4] / "examples/arrow/run.py"
SCRIPT_SPEC = importlib.util.spec_from_file_location(
    "arx_arrow_examples", SCRIPT_PATH
)
if SCRIPT_SPEC is None or SCRIPT_SPEC.loader is None:
    raise RuntimeError(f"could not load Arrow examples at {SCRIPT_PATH}")
examples = importlib.util.module_from_spec(SCRIPT_SPEC)
SCRIPT_SPEC.loader.exec_module(examples)


@pytest.mark.parametrize("fragment_size", [1, 7, 33])
def test_tcp_example_handles_fragmented_io(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fragment_size: int
) -> None:
    """
    title: Socket file wrappers complete short reads and writes in the demo.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
      fragment_size:
        type: int
    """
    batch = examples.expected_batch()
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, batch.schema) as writer:
        writer.write_batch(batch)
        writer.write_batch(batch)
    incoming = io.BytesIO(sink.getvalue().to_pybytes())
    outgoing = bytearray()

    def receive(buffer: bytearray | memoryview) -> int:
        """
        title: Simulate TCP segmentation independently of packet scheduling.
        parameters:
          buffer:
            type: bytearray | memoryview
        returns:
          type: int
        """
        data = incoming.read(min(len(buffer), fragment_size))
        buffer[: len(data)] = data
        return len(data)

    def send(data: bytes | memoryview) -> int:
        """
        title: Simulate partial socket sends without losing the remainder.
        parameters:
          data:
            type: bytes | memoryview
        returns:
          type: int
        """
        count = min(len(data), fragment_size)
        outgoing.extend(data[:count])
        return count

    connection = MagicMock(spec=socket.socket)
    connection.recv_into.side_effect = receive
    connection.send.side_effect = send
    # Exercise socket.makefile itself, not a fake buffering implementation.
    connection.makefile.side_effect = partial(
        socket.socket.makefile, connection
    )
    server = MagicMock(spec=socket.socket)
    server.__enter__.return_value = server
    server.getsockname.return_value = ("127.0.0.1", 12345)
    server.accept.return_value = (connection, ("127.0.0.1", 12346))
    monkeypatch.setattr(examples.socket, "socket", Mock(return_value=server))
    monkeypatch.setattr(
        examples, "build", Mock(return_value=tmp_path / "unused-program")
    )
    process = Mock()
    process.wait.return_value = 0
    process.poll.return_value = 0
    monkeypatch.setattr(
        examples.subprocess, "Popen", Mock(return_value=process)
    )

    examples.tcp(tmp_path)

    # Closing the file wrapper must flush a complete stream to the peer.
    batches = list(pa.ipc.open_stream(bytes(outgoing)))
    assert len(batches) == examples.EXPECTED_BATCHES
    assert all(item.equals(batch, check_metadata=True) for item in batches)
    assert connection.recv_into.call_count > 1
    assert connection.send.call_count > 1
    assert process.wait.call_count == 2
