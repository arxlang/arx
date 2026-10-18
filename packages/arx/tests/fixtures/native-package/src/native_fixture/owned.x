```
title: External native token lifetime fixture
summary: A normal Arx class owns one checked native token, not a raw pointer.
```
import (fixture_create, fixture_note, fixture_write, fixture_release) from .bridge

class Resource:
  ```
  title: Resource
  summary: Releases its native token on the final ordinary class-reference exit.
  ```
  @[private]
  token: i64 = 0

  fn __init__(self, size: i32 = 1) -> none:
    ```
    title: __init__
    ```
    self.token = fixture_create(size=size)
    assert self.token > 0
    return none

  fn __del__(self) -> none:
    ```
    title: __del__
    ```
    assert fixture_release(token=self.token) == 0
    return none

  fn note(self, value: f64, label: str) -> i32:
    ```
    title: note
    ```
    return fixture_note(label=label, token=self.token, value=value)

  fn write(self, path: str, kind: i32 = 0) -> i32:
    ```
    title: write
    ```
    return fixture_write(kind=kind, token=self.token, path=path)
