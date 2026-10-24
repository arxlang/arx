```
title: Compiled exception workflows
summary: Catch nominal failures across calls and finalize every exit.
```

class ConfigError(ValueError):
  ```
  title: Invalid application configuration
  ```

fn require_positive(value: i32) -> i32:
  ```
  title: Require a positive setting
  ```
  if value <= 0:
    raise ConfigError(message="expected a positive setting")
  return value

fn test_catch_and_finalize() -> none:
  ```
  title: Catch a custom subtype and finalize after recovery
  ```
  var state: i32 = 0
  try:
    require_positive(0)
  except (OSError, ValueError) as error:
    assert error.message == "expected a positive setting"
    state = 1
  else:
    state = 10
  finally:
    state = state + 1
  assert state == 2

fn replacement() -> i32:
  ```
  title: A finalizer replaces a pending exception with a return
  ```
  try:
    raise ValueError("discarded")
  finally:
    return 7

fn test_finalizer_return() -> none:
  ```
  title: Finalization can replace completion
  ```
  assert replacement() == 7

fn test_runtime_recovery() -> none:
  ```
  title: Dynamic arithmetic failures are catchable
  ```
  var divisor: i32 = 0
  var caught: bool = false
  try:
    print(4 / divisor)
  except ZeroDivisionError:
    caught = true
  assert caught
