```
title: Bundled generators builtin module
summary: >-
  Compiler-provided generator-adjacent helpers shipped inside the Arx package.
```

# TODO: Expand this module when iterable generators and `yield` land.
fn range(stop: i32) -> list[i32]:
  ```
  title: range
  summary: >-
    Returns the integer values from zero up to but not including `stop`.
  ```
  var values: list[i32]
  for var current: i32 = 0; current < stop; current + 1:
    values.append(current)
  return values
