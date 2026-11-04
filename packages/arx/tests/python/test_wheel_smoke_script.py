"""
title: Artifact contract and safety tests for installed-wheel smoke tooling.
"""

from __future__ import annotations

import importlib.util
import io
import sys
import tarfile

from pathlib import Path
from types import ModuleType
from unittest.mock import Mock
from zipfile import ZipFile

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


@pytest.fixture
def artifact_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """
    title: Create minimal artifacts with an arbitrary Python requirement.
    summary: >-
      A synthetic future requirement proves the audit reads configuration
      rather than copying the repository's current support range.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    returns:
      type: Path
    """
    package = wheel_smoke.PackageArtifact("sample", "sample", "sample")
    monkeypatch.setattr(wheel_smoke, "PACKAGES", (package,))
    package_dir = tmp_path / "packages" / "sample"
    dist = package_dir / "dist"
    dist.mkdir(parents=True)
    manifest = '[project]\nrequires-python = ">=3.99,<4"\n'
    (tmp_path / "pyproject.toml").write_text(manifest, encoding="utf-8")
    (package_dir / "pyproject.toml").write_text(manifest, encoding="utf-8")
    license_text = b"test license\n"
    (tmp_path / "LICENSE").write_bytes(license_text)
    with ZipFile(dist / "sample-1.0-py3-none-any.whl", "w") as archive:
        archive.writestr(
            "sample-1.0.dist-info/METADATA",
            "Name: sample\nVersion: 1.0\nRequires-Python: >=3.99,<4\n",
        )
        archive.writestr("sample-1.0.dist-info/licenses/LICENSE", license_text)
        archive.writestr("sample/py.typed", "")
    with tarfile.open(dist / "sample-1.0.tar.gz", "w:gz") as archive:
        member = tarfile.TarInfo("sample-1.0/LICENSE")
        member.size = len(license_text)
        archive.addfile(member, io.BytesIO(license_text))
    return tmp_path


def test_audit_reads_python_requirement_from_manifests(
    artifact_workspace: Path,
) -> None:
    """
    title: Artifact checks follow the declared requirement without a code edit.
    parameters:
      artifact_workspace:
        type: Path
    """
    (wheel,) = wheel_smoke.audit_artifacts(artifact_workspace)
    assert wheel.name == "sample-1.0-py3-none-any.whl"


def test_python_requirement_rejects_non_string_metadata(
    tmp_path: Path,
) -> None:
    """
    title: Reject malformed Python requirements rather than auditing them.
    parameters:
      tmp_path:
        type: Path
    """
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = [">=3.99"]\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="requires-python must be a string"):
        wheel_smoke.python_requirement(tmp_path)


@pytest.mark.parametrize("changed", ["root", "package", "wheel"])
def test_audit_rejects_inconsistent_python_requirements(
    artifact_workspace: Path,
    changed: str,
) -> None:
    """
    title: Root, package, and wheel Python requirements must agree.
    parameters:
      artifact_workspace:
        type: Path
      changed:
        type: str
    """
    package_dir = artifact_workspace / "packages" / "sample"
    if changed == "wheel":
        wheel = next((package_dir / "dist").glob("*.whl"))
        with ZipFile(wheel, "w") as archive:
            archive.writestr(
                "sample-1.0.dist-info/METADATA",
                "Name: sample\nVersion: 1.0\nRequires-Python: >=3.98,<4\n",
            )
    else:
        directory = artifact_workspace if changed == "root" else package_dir
        (directory / "pyproject.toml").write_text(
            '[project]\nrequires-python = ">=3.98,<4"\n',
            encoding="utf-8",
        )

    with pytest.raises(RuntimeError, match="Requires-Python"):
        wheel_smoke.audit_artifacts(artifact_workspace)


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
    monkeypatch.setattr(
        wheel_smoke,
        "build_native_fixture_wheel",
        Mock(return_value=tmp_path / "fixture.whl"),
    )
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
