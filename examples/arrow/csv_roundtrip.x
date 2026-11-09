```
title: Stream CSV through checked DataFrame conversions
summary: Run from the repository root; input and output must be distinct files.
```
import (Schema, RecordBatch) from stdlib.arrow
import CSVStream from stdlib.csv

fn main() -> i32:
  ```
  title: Convert every CSV batch without discarding rows
  ```
  schema: Schema = Schema()
  schema.add("id", "int64", false)
  reader: CSVStream = CSVStream()
  reader.open_read_as("examples/arrow/input.csv", schema)
  writer: CSVStream = CSVStream()
  writer.open_write("output.csv", schema)
  while reader.next():
    batch: RecordBatch = reader.batch()
    frame: dataframe[id: i64] = cast(batch, dataframe[id: i64])
    output: RecordBatch = cast(frame, RecordBatch)
    writer.write(output)
  writer.close()
  reader.close()
  return 0
