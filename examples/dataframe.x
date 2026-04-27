```
title: DataFrame example
summary: Demonstrates fixed-width Arrow-backed DataFrame syntax.
```

fn row_count(rows: dataframe[id: i32, score: f64]) -> i32:
  ```
  title: row_count
  summary: Returns the number of rows in a static-schema DataFrame.
  ```
  return cast(rows.nrows(), i32)

fn main() -> i32:
  ```
  title: main
  summary: Builds a DataFrame and accesses columns by name and string key.
  ```
  var rows: dataframe[id: i32, score: f64] = dataframe({
    id: [1, 2, 3],
    score: [0.5, 0.8, 1.0],
  })
  var scores: series[f64] = rows.score
  var ids: series[i32] = rows["id"]
  return row_count(rows)
