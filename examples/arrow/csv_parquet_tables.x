```
title: CSV and Parquet DataFrame I/O
summary: Run from the repository root to copy the bundled CSV through Parquet.
```
import (read_csv, write_csv) from stdlib.csv
import (read_parquet, write_parquet) from stdlib.parquet

fn main() -> i32:
  ```
  title: Read every row without explicit sessions or RecordBatches
  ```
  var frame: dataframe[...] = read_csv("examples/arrow/input.csv")
  write_parquet(frame, "output.parquet", compression="zstd", atomic=true)
  var restored: dataframe[...] = read_parquet("output.parquet")
  assert restored.nrows() == frame.nrows()
  write_csv(restored, "output.csv")
  return 0
