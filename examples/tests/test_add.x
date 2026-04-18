```
title: Example compiled test module
summary: Demonstrates Arx assertions and the `arx test` runner.
```
fn add(a: i32, b: i32) -> i32:
  return a + b

fn test_add() -> none:
  assert add(1, 2) == 3
  assert add(2, 2) == 4, "add(2, 2) should be 4"
  return none
