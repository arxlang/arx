```
title: Tensor example
summary: Demonstrates builtin tensors and multidimensional indexing.
```

pick: fn(grid: tensor[i32, 2, 2]) -> i32:
  ```
  title: pick
  summary: Returns the lower-left element plus the upper-right element.
  ```
  return grid[1, 0] + grid[0, 1]

accept_runtime_shape: fn(values: tensor[i32, ...]) -> none:
  ```
  title: accept_runtime_shape
  summary: Accepts a tensor whose shape is supplied at runtime.
  ```
  return none

main: fn() -> i32:
  ```
  title: main
  summary: Builds fixed-shape tensor values and indexes them.
  ```
  grid: tensor[i32, 2, 2] = [[1, 2], [3, 4]]
  ids: tensor[i32, 4] = [5, 6, 7, 8]
  return pick(grid) + ids[2]
