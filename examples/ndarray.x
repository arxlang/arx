```
title: Ndarray example
summary: Demonstrates builtin shaped arrays and multidimensional indexing.
```

fn pick(grid: ndarray[i32, 2, 2]) -> i32:
  ```
  title: pick
  summary: Returns the lower-left element plus the upper-right element.
  ```
  return grid[1, 0] + grid[0, 1]

fn main() -> i32:
  ```
  title: main
  summary: Builds native array and ndarray values and indexes them.
  ```
  var grid: ndarray[i32, 2, 2] = [[1, 2], [3, 4]]
  var ids: array[i32, 4] = [5, 6, 7, 8]
  return pick(grid) + ids[2]
