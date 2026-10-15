"""
title: Nullable class fields and unique builder ownership through native Arx.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from irx.analysis import analyze
from irx.diagnostics import SemanticError

from .test_nullable_operations import execute, parse


def test_nullable_class_fields(tmp_path: Path) -> None:
    """
    title: Default, initialize, replace and release optional instance fields.
    parameters:
      tmp_path:
        type: Path
    """
    result = execute(
        """type Maybe = i32 | none
class Box:
  @[public, mutable]
  count: Maybe = none
  @[public, mutable]
  defaulted: i64 | none
  @[public, mutable]
  values: array[i32] | none = none
  @[public, mutable]
  descriptor: datatype | none = datatype[i32]
  @[public, mutable]
  builder: array_builder[i32] | none = none
fn make() -> array[i32] | none:
  var box: Box = Box()
  assert is_null(box.count)
  assert is_null(box.defaulted)
  assert is_null(box.values)
  box.count = 3
  assert expect_valid(box.count) == 3
  box.values = array[i32](1, 2)
  box.values = box.values
  box.descriptor = none
  box.builder = array_builder[i32]()
  builder_append(expect_valid(box.builder), 7)
  assert array_length(builder_finish(expect_valid(box.builder))) == 1
  box.builder = none
  return box.values
fn main() -> i32:
  var result: array[i32] | none = make()
  assert array_length(expect_valid(result)) == 2
  var box: Box = Box()
  box.values = result
  result = none
  assert expect_valid(array_at(expect_valid(box.values), 1)) == 2
  assert type_bit_width(expect_valid(box.descriptor)) == 32
  box.count = none
  assert is_null(box.count)
  assert is_null(box.defaulted)
  return 0
""",
        tmp_path / "nullable-fields",
    )
    assert result.returncode == 0, result.stderr


def test_nullable_unique_builder(tmp_path: Path) -> None:
    """
    title: Move optional unique owners on return and borrow without copying.
    parameters:
      tmp_path:
        type: Path
    """
    result = execute(
        """fn make(present: bool) -> array_builder[i32] | none:
  if present:
    var value: array_builder[i32] | none = array_builder[i32]()
    return value
  return none
fn append(value: array_builder[i32] | none) -> i32:
  if is_valid(value):
    builder_append(value, 4)
    return 1
  return 0
fn main() -> i32:
  var builder: array_builder[i32] | none = make(true)
  assert append(builder) == 1
  assert builder_length(expect_valid(builder)) == 1
  assert expect_valid(array_at(builder_finish(expect_valid(builder)), 0)) == 4
  builder = none
  assert append(builder) == 0
  builder = make(false)
  assert is_null(builder)
  return 0
""",
        tmp_path / "nullable-builder",
    )
    assert result.returncode == 0, result.stderr


def test_nullable_unique_owner_cannot_be_copied() -> None:
    """
    title: Preserve unique ownership even when a value can be absent.
    """
    with pytest.raises(SemanticError, match=r"borrowed|unique"):
        analyze(
            parse(
                "fn main() -> i32:\n"
                "  var owner: array_builder[i32] | none = none\n"
                "  var alias: array_builder[i32] | none = owner\n"
                "  return 0\n"
            )
        )


def test_static_nullable_fields_remain_rejected() -> None:
    """
    title: Reject static nullable state until module initialization is defined.
    """
    with pytest.raises(SemanticError, match="static nullable fields"):
        analyze(
            parse(
                "class Box:\n  @[public, static, mutable]\n"
                "  value: i32 | none = none\n"
            )
        )
