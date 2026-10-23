```
title: Shared Arrow example dataset
summary: Numeric and Boolean columns constructed entirely by compiled Arx.
```
import (Schema, BatchBuilder, RecordBatch) from stdlib.arrow

fn make_batch() -> RecordBatch:
  ```
  title: make_batch
  summary: Produces two rows with exact non-nullable Arrow types.
  ```
  var schema: Schema = Schema()
  schema.add("id", "int64")
  schema.add("score", "float64")
  schema.add("active", "bool")
  var builder: BatchBuilder = BatchBuilder(schema)
  builder.append_i64(0, 42)
  builder.append_i64(0, 7)
  builder.append_f64(1, 1.5)
  builder.append_f64(1, 2.5)
  builder.append_bool(2, true)
  builder.append_bool(2, false)
  return builder.finish()

fn verify(batch: RecordBatch) -> none:
  ```
  title: verify
  summary: Checks the full schema, row count and every value.
  ```
  var expected: RecordBatch = make_batch()
  assert batch.schema().equals(expected.schema())
  assert batch.nrows() == 2
  assert batch.get_i64(0, 0) == 42
  assert batch.get_i64(0, 1) == 7
  assert batch.get_f64(1, 0) == 1.5
  assert batch.get_f64(1, 1) == 2.5
  assert batch.get_bool(2, 0)
  assert batch.get_bool(2, 1) == false
  return none
