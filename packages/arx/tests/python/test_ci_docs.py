"""
title: Keep the temporary DoukiMD CI bypass narrow and publication fail-closed.
"""

import os
import subprocess
import sys

from pathlib import Path
from typing import cast

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize("workflow", ["docs.yaml", "release.yaml"])
@pytest.mark.parametrize(
    ("message", "exit_code", "skipped"),
    [
        ("Documentation built", 0, False),
        (
            "Error: [api] Unresolved re-export: irx.typecheck.typechecked",
            1,
            True,
        ),
        (
            "Error: [api] Unresolved re-export: arxpy.typecheck.typechecked",
            1,
            True,
        ),
        (
            "Error: [api] Unresolved re-export: irx.other.symbol",
            1,
            False,
        ),
        (
            "Error: [output] Refusing to replace an unmanaged directory",
            1,
            False,
        ),
        (
            "Error: [api] Unresolved re-export: irx.typecheck.typechecked\n"
            "Error: [api] Another documentation failure",
            1,
            False,
        ),
    ],
)
def test_ci_docs_only_skip_known_reexports(
    tmp_path: Path,
    workflow: str,
    message: str,
    exit_code: int,
    skipped: bool,
) -> None:
    """
    title: Execute the real workflow shell with controlled build outcomes.
    parameters:
      tmp_path:
        type: Path
      workflow:
        type: str
      message:
        type: str
      exit_code:
        type: int
      skipped:
        type: bool
    """
    config = yaml.safe_load(
        (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    )
    steps = cast(list[dict[str, object]], config["jobs"]["release"]["steps"])
    build = next(step for step in steps if step.get("id") == "docs")
    publish = next(
        step for step in steps if step.get("name") == "GitHub Pages action"
    )
    assert "steps.docs.outputs.built == 'true'" in str(publish["if"])
    assert "github.event_name == 'workflow_dispatch'" in str(publish["if"])

    command = tmp_path / "makim"
    command.write_text(
        f"#!{sys.executable}\nimport sys\n"
        f"print({message!r}, file=sys.stderr)\nsys.exit({exit_code})\n",
        encoding="utf-8",
    )
    command.chmod(0o755)
    output_file = tmp_path / "github-output"
    output_file.touch()
    result = subprocess.run(
        ["bash", "-c", str(build["run"])],
        env={
            **os.environ,
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(output_file),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (0 if exit_code == 0 or skipped else 1)
    assert message in result.stdout
    assert ("::warning::Skipping documentation:" in result.stdout) is skipped
    assert output_file.read_text(encoding="utf-8") == (
        "built=true\n" if exit_code == 0 else ""
    )
