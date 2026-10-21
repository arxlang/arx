```
title: Stream CSV through checked DataFrame conversions
summary: Run from the repository root; input and output must be distinct files.
```
import (Schema, RecordBatch, CSVReader, CSVWriter) from stdlib.arrow

fn main() -> i32:
  ```
  title: Convert every CSV batch without discarding rows
  ```
  var schema: Schema = Schema()
  schema.add("id", 3, false)
  var reader: CSVReader = CSVReader()
  reader.open_file_as("examples/arrow/input.csv", schema)
  var writer: CSVWriter = CSVWriter(schema)
  writer.open_file("output.csv")
  while reader.next():
    var batch: RecordBatch = reader.batch()
    var frame: dataframe[id: i64] = cast(batch, dataframe[id: i64])
    var output: RecordBatch = cast(frame, RecordBatch)
    writer.write(output)
  writer.close()
  reader.close()
  return 0
