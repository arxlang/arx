```
title: Nullable strings and independently owned class string fields
```
class TextBox:
  @[public, mutable]
  text: str = "initial"
  @[public, mutable]
  empty: str
  @[public, mutable]
  optional: str | none = none
fn identity(value: str | none) -> str | none:
  return value
fn text(value: str | none) -> str:
  return expect_valid(value)
fn make() -> str | none:
  var box: TextBox = TextBox()
  assert box.empty == ""
  var local: str = "heap" + " value"
  box.text = local
  box.optional = box.text
  local = "replaced"
  box.text = box.text
  assert box.text == "heap value"
  return box.optional
fn main() -> i32:
  var value: str | none = none
  assert is_null(identity(value))
  value = ""
  assert is_valid(value)
  var kept: str | none = identity(value)
  value = make()
  assert expect_valid(value) == "heap value"
  var copied: str = text(value)
  value = none
  assert copied == "heap value"
  assert expect_valid(kept) == ""
  var defaulted: str
  assert defaulted == ""
  var i: i32 = 0
  while i < 3:
    var loop: str | none = copied
    assert expect_valid(loop) == "heap value"
    i = i + 1
  return 0
