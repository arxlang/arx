"""
title: Compound validity proofs and explicit validity-preserving casts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from irx.analysis import analyze
from irx.diagnostics import SemanticError

from .test_nullable_operations import execute, parse


def test_compound_validity_proofs(tmp_path: Path) -> None:
    """
    title: Refine only facts guaranteed by all short-circuit condition paths.
    parameters:
      tmp_path:
        type: Path
    """
    result = execute(
        """fn main() -> i32:
  var x: i32 | none = 2
  var y: i32 | none = 3
  if is_valid(x) and is_valid(y):
    var sum: i32 = x + y
    assert sum == 5
  if !(is_null(x) or is_null(y)):
    var sum2: i32 = x + y
    assert sum2 == 5
  if (is_valid(x) and is_valid(y)) and x < y:
    var difference: i32 = y - x
    assert difference == 1
  if is_null(x) or is_null(y):
    assert false
  else:
    var sum3: i32 = x + y
    assert sum3 == 5
  if (is_valid(x) and true) or (is_valid(x) and false):
    var present: i32 = x
    assert present == 2
  return 0
""",
        tmp_path / "compound-proofs",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "body",
    [
        "if is_valid(x) or is_valid(y):\n    var value: i32 = x",
        "if is_valid(x) and is_valid(y):\n    x = none\n"
        "    var value: i32 = x",
        "if is_valid(x) and is_valid(y):\n    y = none\n"
        "    var value: i32 = y",
        "if is_valid(x) and is_valid(y):\n    assert true\n"
        "  var value: i32 = x",
    ],
)
def test_compound_proofs_do_not_escape(body: str) -> None:
    """
    title: Reject disjunctive, invalidated and non-dominating validity facts.
    parameters:
      body:
        type: str
    """
    module = parse(
        "fn main() -> i32:\n  var x: i32 | none = 1\n"
        "  var y: i32 | none = none\n  " + body + "\n  return 0\n"
    )
    with pytest.raises(SemanticError):
        analyze(module)


def test_nullable_numeric_casts(tmp_path: Path) -> None:
    """
    title: Narrow present primitive payloads without changing validity.
    parameters:
      tmp_path:
        type: Path
    """
    result = execute(
        """fn main() -> i32:
  var value: i64 | none = 258
  var narrowed: i8 | none = cast(value, i8 | none)
  assert expect_valid(narrowed) == 2
  var missing: f64 | none = none
  var absent: i32 | none = cast(missing, i32 | none)
  assert is_null(absent)
  assert is_null(cast(none, f32 | none))
  var injected: f64 | none = cast(7, f64 | none)
  assert expect_valid(injected) == 7.0
  var real: f64 | none = 3.75
  var integral: i32 | none = cast(real, i32 | none)
  assert expect_valid(integral) == 3
  return 0
""",
        tmp_path / "nullable-casts",
    )
    assert result.returncode == 0, result.stderr


def test_nullable_cast_does_not_unwrap() -> None:
    """
    title: Require explicit checked unwrap before casting away validity.
    """
    with pytest.raises(SemanticError, match="use expect_valid"):
        analyze(
            parse(
                "fn main() -> i32:\n  var value: i64 | none = none\n"
                "  return cast(value, i32)\n"
            )
        )
