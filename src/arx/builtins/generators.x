```
title: Bundled generators builtin module
summary: >-
  Compiler-provided generator-adjacent helpers shipped inside the Arx package.
```

# TODO: Expand this module when iterable generators and `yield` land.
fn range(start: i32, stop: i32, step: i32) -> list[i32]:
  ```
  title: range
  summary: >-
    Returns the integer values from `start` up to but not including `stop`,
    advancing by `step`.
  ```
  var values: list[i32]
  for var current: i32 = start; current < stop; current + step:
    values.append(current)
  return values
