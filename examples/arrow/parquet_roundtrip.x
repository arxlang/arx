```
title: Native Parquet roundtrip with checked DataFrame conversion
summary: Creates local input and output files and processes every batch.
```
import Parquet from stdlib.parquet
import (BatchBuilder, RecordBatch, Schema) from stdlib.arrow

fn main() -> i32:
  ```
  title: Write input, convert batches and verify output
  ```
  var schema: Schema = Schema()
  schema.add("id", "int64", false)
  var builder: BatchBuilder = BatchBuilder(schema)
  builder.append_i64(0, 1)
  builder.append_i64(0, 2)
  builder.append_i64(0, 3)
  var file: Parquet = Parquet()
  file.open_write("parquet-input.parquet", schema, row_group_size=2)
  file.write(builder.finish())
  file.close()
  file.open_read_as("parquet-input.parquet", schema, batch_size=1)
  var output: Parquet = Parquet()
  output.open_write("parquet-output.parquet", schema)
  while file.next():
    var batch: RecordBatch = file.batch()
    var frame: dataframe[id: i64] = cast(batch, dataframe[id: i64])
    var copy: RecordBatch = cast(frame, RecordBatch)
    output.write(copy)
  file.close()
  output.close()
  output.open_read_as("parquet-output.parquet", schema)
  var rows: i64 = 0
  while output.next():
    rows = rows + output.batch().nrows()
  assert rows == 3
  output.close()
  return 0
