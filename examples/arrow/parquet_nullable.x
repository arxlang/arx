```
title: Nullable DataFrames with atomic Parquet output and a filtered scan
summary: Creates its input locally and uses the native Arrow Dataset scanner.
```
import (Parquet, ParquetOptions, RecordBatch) from stdlib.arrow

fn main() -> i32:
  ```
  title: Write nullable columns and select a projected result
  ```
  var frame: dataframe[id:i64 | none, label:str | none] = dataframe({id: [1, none, 3], label: ["alpha", none, "gamma"]})
  var batch: RecordBatch = cast(frame, RecordBatch)
  var options: ParquetOptions = ParquetOptions()
  options.set_int("atomic", 1)
  var file: Parquet = Parquet()
  file.open_write_options("nullable.parquet", batch.schema(), options)
  file.write(batch)
  file.close()
  var scan: ParquetOptions = ParquetOptions()
  scan.set_text("column", "label")
  scan.where("id", "gt", "1", "int64")
  file.open_read_options("nullable.parquet", scan)
  var rows: i64 = 0
  while file.next():
    rows = rows + file.batch().nrows()
  file.close()
  assert rows == 1
  return 0
