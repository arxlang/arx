```
title: Compiled exception workflows
summary: Catch nominal failures across calls and finalize every exit.
```

class ConfigError(ValueError):
  ```
  title: Invalid application configuration
  ```

require_positive: fn(value: i32) -> i32:
  ```
  title: Require a positive setting
  ```
  if value <= 0:
    raise ConfigError(message="expected a positive setting")
  return value

test_catch_and_finalize: fn() -> none:
  ```
  title: Catch a custom subtype and finalize after recovery
  ```
  state: i32 = 0
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

replacement: fn() -> i32:
  ```
  title: A finalizer replaces a pending exception with a return
  ```
  try:
    raise ValueError("discarded")
  finally:
    return 7

test_finalizer_return: fn() -> none:
  ```
  title: Finalization can replace completion
  ```
  assert replacement() == 7

test_runtime_recovery: fn() -> none:
  ```
  title: Dynamic arithmetic failures are catchable
  ```
  divisor: i32 = 0
  caught: bool = false
  try:
    print(4 / divisor)
  except ZeroDivisionError:
    caught = true
  assert caught
