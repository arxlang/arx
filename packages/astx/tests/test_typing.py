"""
title: Import-time runtime-checking policy for the compiler stack.
"""

import json
import os
import subprocess
import sys

from pathlib import Path

import pytest

POLICY_PROBE = """
import json
import os

from astx.tools.typing import typechecked
from typeguard import TypeCheckError

# The mode is fixed at import, even for definitions decorated after a change.
os.environ["ARX_RUNTIME_TYPECHECK"] = "0"


def accept(values: list[int]) -> list[int]:
    return values


def bad_return() -> int:
    return "invalid"


class Validator:
    def accept(self, values: list[int]) -> list[int]:
        return values


original = accept
original_method = Validator.accept
accept = typechecked(accept)
bad_return = typechecked(bad_return)
Validator = typechecked(Validator)

rejected = 0
for call in (
    lambda: accept([1, "invalid"]),
    bad_return,
    lambda: Validator().accept([1, "invalid"]),
):
    try:
        call()
    except TypeCheckError:
        rejected += 1
print(json.dumps([accept is original, Validator.accept is original_method,
                  rejected]))
"""


@pytest.mark.parametrize("setting", [None, "0", "1"])
def test_runtime_checking_is_opt_in(
    setting: str | None, tmp_path: Path
) -> None:
    """
    title: Default-off decoration has no wrappers; opt-in checks all items.
    parameters:
      setting:
        type: str | None
      tmp_path:
        type: Path
    """
    probe = tmp_path / "policy_probe.py"
    probe.write_text(POLICY_PROBE, encoding="utf-8")
    env = os.environ.copy()
    env.pop("ARX_RUNTIME_TYPECHECK", None)
    if setting is not None:
        env["ARX_RUNTIME_TYPECHECK"] = setting
    result = subprocess.run(
        [sys.executable, str(probe)],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    enabled = setting == "1"
    assert json.loads(result.stdout) == [
        not enabled,
        not enabled,
        3 if enabled else 0,
    ]


def test_invalid_runtime_checking_setting_is_rejected() -> None:
    """
    title: A misspelled opt-in cannot silently disable checking.
    """
    result = subprocess.run(
        [sys.executable, "-c", "import astx.tools.typing"],
        env={**os.environ, "ARX_RUNTIME_TYPECHECK": "yes"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "ARX_RUNTIME_TYPECHECK must be '0' or '1'" in result.stderr
