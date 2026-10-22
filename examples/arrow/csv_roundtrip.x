```
title: Stream CSV through checked DataFrame conversions
summary: Run from the repository root; input and output must be distinct files.
```
import (Schema, RecordBatch, CSV) from stdlib.arrow

fn main() -> i32:
  ```
  title: Convert every CSV batch without discarding rows
  ```
  var schema: Schema = Schema()
  schema.add("id", 3, false)
  var reader: CSV = CSV()
  reader.open_read_as("examples/arrow/input.csv", schema)
  var writer: CSV = CSV()
  writer.open_write("output.csv", schema)
  while reader.next():
    var batch: RecordBatch = reader.batch()
    var frame: dataframe[id: i64] = cast(batch, dataframe[id: i64])
    var output: RecordBatch = cast(frame, RecordBatch)
    writer.write(output)
  writer.close()
  reader.close()
  return 0
