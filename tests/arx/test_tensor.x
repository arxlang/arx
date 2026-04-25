```
title: Repository tensor tests
summary: Cover fixed-shape tensor literals, indexing, and helpers.
```

fn pick(grid: tensor[i32, 2, 2]) -> i32:
  ```
  title: pick
  summary: Returns the sum of one column-crossing pair of indices.
  ```
  return grid[1, 0] + grid[0, 1]

fn edge_sum(values: tensor[i32, 4]) -> i32:
  ```
  title: edge_sum
  summary: Returns the sum of the first and last vector elements.
  ```
  return values[0] + values[3]

fn test_tensor_grid_indexing() -> none:
  ```
  title: test_tensor_grid_indexing
  summary: Verifies two-dimensional tensor literals and indexing.
  ```
  var grid: tensor[i32, 2, 2] = [[1, 2], [3, 4]]
  assert pick(grid) == 5

fn test_tensor_vector_indexing() -> none:
  ```
  title: test_tensor_vector_indexing
  summary: Verifies one-dimensional tensor literals and indexing.
  ```
  var ids: tensor[i32, 4] = [5, 6, 7, 8]
  assert edge_sum(ids) == 13
