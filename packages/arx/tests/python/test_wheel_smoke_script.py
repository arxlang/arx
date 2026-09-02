"""
title: Safety tests for installed-wheel smoke tooling.
"""

from __future__ import annotations

import importlib.util
import sys

from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[4] / "scripts" / "test_wheels.py"
)
SCRIPT_SPEC = importlib.util.spec_from_file_location(
    "arx_test_wheels_script",
    SCRIPT_PATH,
)
if SCRIPT_SPEC is None or SCRIPT_SPEC.loader is None:
    raise RuntimeError(f"could not load wheel smoke script at {SCRIPT_PATH}")
wheel_smoke = importlib.util.module_from_spec(SCRIPT_SPEC)
sys.modules[SCRIPT_SPEC.name] = wheel_smoke
SCRIPT_SPEC.loader.exec_module(wheel_smoke)
if not isinstance(wheel_smoke, ModuleType):  # pragma: no cover
    raise RuntimeError("wheel smoke script did not load as a module")


def test_run_smoke_uses_and_removes_only_a_tool_owned_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    title: Wheel smoke execution preserves every pre-existing directory.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    caller_directory = tmp_path / "caller-data"
    caller_directory.mkdir()
    caller_sentinel = caller_directory / "keep.txt"
    caller_sentinel.write_text("keep", encoding="utf-8")

    smoke_root = tmp_path / ".tmp" / "wheel-smoke"
    existing_directory = smoke_root / "existing"
    existing_directory.mkdir(parents=True)
    existing_sentinel = existing_directory / "keep.txt"
    existing_sentinel.write_text("keep", encoding="utf-8")

    install = Mock(return_value=(Path(sys.executable), {}))
    execute = Mock()
    monkeypatch.setattr(wheel_smoke, "_install_wheels", install)
    monkeypatch.setattr(wheel_smoke.subprocess, "run", execute)

    wheel_smoke.run_smoke(tmp_path, (), False)

    work_dir = install.call_args.args[1]
    assert isinstance(work_dir, Path)
    assert work_dir.parent == smoke_root
    assert work_dir.name.startswith("run-")
    assert not work_dir.exists()
    assert execute.call_args.kwargs["cwd"] == work_dir
    assert caller_sentinel.read_text(encoding="utf-8") == "keep"
    assert existing_sentinel.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize("unsafe_path", [".", "..", "/tmp"])
def test_cli_rejects_caller_controlled_work_directories(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    unsafe_path: str,
) -> None:
    """
    title: The CLI has no option that accepts a deletion destination.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
      unsafe_path:
        type: str
    """
    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["test_wheels.py", "--work-dir", unsafe_path],
    )

    with pytest.raises(SystemExit) as captured:
        wheel_smoke.main()

    assert captured.value.code == 2
    assert sentinel.read_text(encoding="utf-8") == "keep"
