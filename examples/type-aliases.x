```
title: Type aliases and type-aware builtins
summary: Demonstrates union aliases, isinstance, type, and cast.
```

type Number = i32 | i64

fn identity(value: Number) -> Number:
  ```
  title: identity
  summary: Returns a numeric union value.
  ```
  return value

fn main() -> i32:
  ```
  title: main
  summary: Calls type-aware builtins with a union alias.
  ```
  var value: i64 = identity(5)
  var ok: bool = isinstance(value, Number)
  var name: str = type(value)
  if ok:
    return cast(value, i32)
  else:
    return 1
