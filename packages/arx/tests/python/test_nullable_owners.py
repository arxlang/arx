"""
title: Nullable shared owners across value, borrowing and return boundaries.
"""

from __future__ import annotations

from pathlib import Path

from .test_nullable_operations import execute


def test_nullable_array_owners(tmp_path: Path) -> None:
    """
    title: Keep valid empty owners distinct from null and retain borrowed data.
    parameters:
      tmp_path:
        type: Path
    """
    result = execute(
        """fn optional(make: bool) -> array[i32] | none:
  if make:
    return array[i32](1, 2)
  return none
fn identity(value: array[i32] | none) -> array[i32] | none:
  return value
fn unwrap(value: array[i32] | none) -> array[i32]:
  return expect_valid(value)
fn main() -> i32:
  var empty: array[i32] | none = array[i32]()
  assert is_valid(empty)
  assert array_length(expect_valid(empty)) == 0
  var missing: array[i32] | none = none
  var copied: array[i32] | none = identity(missing)
  assert is_null(copied)
  copied = optional(true)
  var kept: array[i32] = unwrap(copied)
  var alias: array[i32] | none = copied
  copied = none
  assert array_length(kept) == 2
  if is_valid(alias):
    assert array_length(alias) == 2
  else:
    assert false
  assert is_null(optional(false))
  var d: datatype | none = datatype[i32]
  assert type_bit_width(expect_valid(d)) == 32
  var dc: datatype | none = d
  d = none
  assert type_bit_width(expect_valid(dc)) == 32
  return 0
""",
        tmp_path / "nullable-owners",
    )
    assert result.returncode == 0, result.stderr


def test_nullable_descriptor_and_chunk_defaults(tmp_path: Path) -> None:
    """
    title: Handle absent borrowed defaults and independently owned descriptors.
    parameters:
      tmp_path:
        type: Path
    """
    result = execute(
        (
            "fn optional(value: chunked_array[i32] | none = none) ->"
            " chunked_array[i32] | none:\n"
            "  return value\n"
            "fn schema_copy(value: schema | none) -> schema | none:\n"
            "  return value\n"
            "fn main() -> i32:\n"
            "  var absent: chunked_array[i32] | none = optional()\n"
            "  assert is_null(absent)\n"
            "  var chunks: chunked_array[i32] | none ="
            " optional(chunked_array[i32](array[i32](3)))\n"
            "  var alias: chunked_array[i32] | none = chunks\n"
            "  chunks = none\n"
            "  assert array_length(expect_valid(alias)) == 1\n"
            "  var schema_value: schema | none = schema[a: i32]\n"
            "  var copied: schema | none = schema_copy(schema_value)\n"
            "  schema_value = none\n"
            "  assert schema_nfields(expect_valid(copied)) == 1\n"
            "  var member: field | none ="
            " schema_field(expect_valid(copied), 0)\n"
            "  copied = none\n"
            '  assert field_name(expect_valid(member)) == "a"\n'
            "  member = member\n"
            "  member = none\n"
            "  assert is_null(member)\n"
            "  return 0\n"
        ),
        tmp_path / "nullable-descriptors",
    )
    assert result.returncode == 0, result.stderr


def test_missing_owner_unwrap_fails(tmp_path: Path) -> None:
    """
    title: Fail before using a missing owner with all live resources cleaned.
    parameters:
      tmp_path:
        type: Path
    """
    result = execute(
        """fn main() -> i32:
  var kept: chunked_array[i32] = chunked_array[i32](array[i32](1))
  var absent: array[i32] | none = none
  array_length(expect_valid(absent))
  return 0
""",
        tmp_path / "nullable-owner-failure",
    )
    assert result.returncode != 0
    assert "ARX-RUNTIME-NULL-001" in result.stderr
