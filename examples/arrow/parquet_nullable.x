```
title: Nullable DataFrames with atomic Parquet output and a filtered scan
summary: Creates its input locally and uses the native Arrow Dataset scanner.
```
import (Parquet, ParquetOptions, where) from stdlib.parquet
import RecordBatch from stdlib.arrow

fn main() -> i32:
  ```
  title: Write nullable columns and select a projected result
  ```
  var frame: dataframe[id:i64 | none, label:str | none, day:date | none] = dataframe({
    id: [1, none, 3],
    label: ["alpha", none, "gamma"],
    day: [date("2026-01-01"), none, date("2026-01-03")],
  })
  var batch: RecordBatch = cast(frame, RecordBatch)
  var options: ParquetOptions = ParquetOptions()
  options.set_int("atomic", 1)
  options.set_int("durable", 1)
  var file: Parquet = Parquet()
  file.open_write_options("nullable.parquet", batch.schema(), options)
  file.write(batch)
  file.close()
  var scan: ParquetOptions = ParquetOptions()
  scan.set_text("column", "label")
  scan.set_filters(where("id", ">", 1))
  file.open_read_options("nullable.parquet", scan)
  var rows: i64 = 0
  while file.next():
    var dynamic: dataframe[...] = cast(file.batch(), dataframe[...])
    rows = rows + dynamic.nrows()
  file.close()
  assert rows == 1
  return 0
