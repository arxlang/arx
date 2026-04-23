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
    advancing by `step`. Positive steps count up, negative steps count down,
    and zero step is rejected.
  ```
  assert step != 0, "range() step must not be 0"
  var values: list[i32]
  var current: i32 = start
  if step > 0:
    while current < stop:
      values.append(current)
      current = current + step
  else:
    while current > stop:
      values.append(current)
      current = current + step
  return values
