```
title: Compiled public File regression
summary: Verifies the builtin class, factory adapter, aliases, and lowercase type.
```

fn make_file(path: str) -> File:
  ```
  title: make_file
  ```
  return File(file=path, mode="w", encoding="utf-8")

fn test_file() -> none:
  ```
  title: test_file
  ```
  output: File = make_file("file-class-test.txt")
  alias: file = output
  assert output == alias
  assert alias.write("hello") == 5
  alias.close()
  output.close()
  source: file = open("file-class-test.txt")
  assert source.read() == "hello"

class ScopeValue:
  ```
  title: Independently retained entered value.
  ```
  value: i32 = 41

class Scope:
  ```
  title: Count resource entry, completion, and manager destruction.
  ```
  entered: static :: i32 = 0
  exited: static :: i32 = 0
  failed: static :: i32 = 0
  dropped: static :: i32 = 0
  child: ScopeValue

  fn __init__(self) -> none:
    self.child = ScopeValue()

  fn __enter__(self) -> ScopeValue:
    Scope.entered = Scope.entered + 1
    return self.child

  fn __exit__(self, success: bool) -> none:
    Scope.exited = Scope.exited + 1
    if not success:
      Scope.failed = Scope.failed + 1

  fn __del__(self) -> none:
    Scope.dropped = Scope.dropped + 1

class FailedScope(Scope):
  ```
  title: Enter fails before exit may be scheduled.
  ```
  fn __enter__(self) -> ScopeValue:
    raise ValueError("enter failed")

class TextScope:
  ```
  title: Own a text result until checked exit or return transfer.
  ```
  fail: bool = false

  fn __init__(self, fail: bool) -> none:
    self.fail = fail

  fn __enter__(self) -> str:
    return " owned ".strip()

  fn __exit__(self, success: bool) -> none:
    if self.fail:
      raise ValueError("text exit failed")

class ListScope:
  ```
  title: Own a string list until checked exit or return transfer.
  ```
  fail: bool = false

  fn __init__(self, fail: bool) -> none:
    self.fail = fail

  fn __enter__(self) -> list[str]:
    return ["owned", "list"]

  fn __exit__(self, success: bool) -> none:
    if self.fail:
      raise ValueError("list exit failed")

fn scoped_value() -> ScopeValue:
  ```
  title: An entered class value survives exit and manager destruction.
  ```
  with Scope() as value:
    return value

fn scoped_text(fail: bool) -> str:
  ```
  title: A failed exit cancels a pending owned text return.
  ```
  with TextScope(fail) as value:
    return value

fn scoped_list(fail: bool) -> list[str]:
  ```
  title: A failed exit cancels a pending owned list return.
  ```
  with ListScope(fail) as value:
    return value

fn test_resource_scopes() -> none:
  ```
  title: Preserve entered identity, manager pins, and all-exit cleanup.
  ```
  manager: Scope = Scope()
  original: ScopeValue = manager.child
  value: i32 = 99
  with manager as value:
    assert value == original
    value.value = 42
  assert value == 99
  assert Scope.entered == 1
  assert Scope.exited == 1
  assert Scope.failed == 0

  with manager as value:
    manager = Scope()
    assert Scope.dropped == 0
    assert value == original
  assert Scope.dropped == 1
  assert original.value == 42

  before: i32 = Scope.exited
  drops: i32 = Scope.dropped
  for index in [0, 1, 2]:
    with Scope():
      if index < 2:
        continue
      break
  assert Scope.exited == before + 3
  assert Scope.dropped == drops + 3
  assert Scope.failed == 0
  assert scoped_value().value == 41

  before = Scope.exited
  try:
    with Scope() as value:
      raise ValueError("body failed")
  except ValueError as error:
    assert error.message == "body failed"
  assert Scope.exited == before + 1
  assert Scope.failed == 1
  before = Scope.exited
  try:
    with FailedScope():
      assert false, "failed enter must not execute the body"
  except ValueError as error:
    assert error.message == "enter failed"
  assert Scope.exited == before

  text: str = scoped_text(false)
  items: list[str] = scoped_list(false)
  assert text == "owned"
  assert items[1] == "list"
  with TextScope(false):
    with ListScope(false):
      assert true
  try:
    scoped_text(true)
    assert false, "exit failure must cancel the return"
  except ValueError as error:
    assert error.message == "text exit failed"
  try:
    scoped_list(true)
    assert false, "exit failure must cancel the return"
  except ValueError as error:
    assert error.message == "list exit failed"

fn scoped_file_workflow() -> none:
  ```
  title: Run checked File scope cases in an isolated caller directory.
  ```
  outside: File = open("scoped-file.txt", "w")
  with outside as output:
    assert output == outside
    output.write("hello")
  try:
    outside.write("closed alias")
    assert false, "scope exit must close aliases"
  except ValueError:
    assert true
  outside.close()
  try:
    with outside:
      assert false, "closed enter must fail before the body"
  except ValueError:
    assert true
  with open("scoped-file.txt") as source:
    assert source.read() == "hello"
    source.close()
  try:
    with open("missing/scoped-file.txt"):
      assert false, "failed acquisition must not execute the body"
  except OSError:
    assert true
