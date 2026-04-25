```
title: Tensor example
summary: Demonstrates builtin tensors and multidimensional indexing.
```

fn pick(grid: tensor[i32, 2, 2]) -> i32:
  ```
  title: pick
  summary: Returns the lower-left element plus the upper-right element.
  ```
  return grid[1, 0] + grid[0, 1]

fn main() -> i32:
  ```
  title: main
  summary: Builds fixed-shape tensor values and indexes them.
  ```
  var grid: tensor[i32, 2, 2] = [[1, 2], [3, 4]]
  var ids: tensor[i32, 4] = [5, 6, 7, 8]
  return pick(grid) + ids[2]
