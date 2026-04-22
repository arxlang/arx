```
title: Repository ndarray tests
summary: Cover fixed-shape ndarray literals, indexing, and helpers.
```

fn pick(grid: ndarray[i32, 2, 2]) -> i32:
  ```
  title: pick
  summary: Returns the sum of one column-crossing pair of indices.
  ```
  return grid[1, 0] + grid[0, 1]

fn edge_sum(values: ndarray[i32, 4]) -> i32:
  ```
  title: edge_sum
  summary: Returns the sum of the first and last vector elements.
  ```
  return values[0] + values[3]

fn test_ndarray_grid_indexing() -> none:
  ```
  title: test_ndarray_grid_indexing
  summary: Verifies two-dimensional ndarray literals and indexing.
  ```
  var grid: ndarray[i32, 2, 2] = [[1, 2], [3, 4]]
  assert pick(grid) == 5

fn test_ndarray_vector_indexing() -> none:
  ```
  title: test_ndarray_vector_indexing
  summary: Verifies one-dimensional ndarray literals and indexing.
  ```
  var ids: ndarray[i32, 4] = [5, 6, 7, 8]
  assert edge_sum(ids) == 13
