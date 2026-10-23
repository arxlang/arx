```
title: Bundled generators builtin module
summary: >-
  Compiler-provided generator-adjacent helpers shipped inside the Arx package.
```

# TODO: Expand this module when iterable generators and `yield` land.
fn range(start: i32, stop: i32, step: i32 = 1) -> list[i32]:
  ```
  title: range
  summary: >-
    Returns an owned, eagerly allocated list of i32 values from `start` up to
    but not including `stop`, advancing by `step` without endpoint wraparound.
    Positive steps count up and negative steps count down; equal endpoints or
    a wrong-direction step return an empty list. Zero step fails an assertion,
    even for an empty interval. Unlike Python, start is required and inputs
    are i32; storage grows with the number of results rather than staying lazy.
  ```
  assert step != 0, "range() step must not be 0"
  var values: list[i32]
  # The final step may cross an i32 endpoint; keep it wide until the next test.
  var current: i64 = cast(start, i64)
  var limit: i64 = cast(stop, i64)
  var stride: i64 = cast(step, i64)
  if step > 0:
    while current < limit:
      values.append(cast(current, i32))
      current = current + stride
  else:
    while current > limit:
      values.append(cast(current, i32))
      current = current + stride
  return values
