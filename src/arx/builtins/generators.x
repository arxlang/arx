```
title: Bundled generators builtin module
summary: >-
  Compiler-provided generator-adjacent helpers shipped inside the Arx package.
```

# TODO: Expand this module when iterable generators and `yield` land.
fn range(stop: i32) -> i32:
  ```
  title: range
  summary: >-
    Returns the exclusive stop bound for the current generator MVP while the
    callable `range(...)` API is staged in source form.
  ```
  return stop
