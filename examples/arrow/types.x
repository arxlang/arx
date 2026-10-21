```
title: Typed nullable RecordBatch API
summary: Exercise every Arx scalar accessor, schema inspection and builder reuse.
```
import (Schema, BatchBuilder, RecordBatch, IPCWriter) from stdlib.arrow

fn main() -> i32:
  ```
  title: main
  summary: Writes a value batch, empty batch and null batch to typed.arrow.
  ```
  var schema: Schema = Schema()
  schema.add("col0", 0, nullable=true)
  schema.add("col1", 1, nullable=true)
  schema.add("col2", 2, nullable=true)
  schema.add("col3", 3, nullable=true)
  schema.add("col4", 8, nullable=true)
  schema.add("col5", 9, nullable=true)
  schema.add("col6", 10, nullable=true)
  schema.add("col7", 11, nullable=true)
  schema.add("col8", 12, nullable=true)
  schema.add("col9", 13, nullable=true)
  schema.add("col10", 14, nullable=true)
  schema.add("col11", 17, nullable=true)
  schema.add("col12", 21, nullable=true)
  var builder: BatchBuilder = BatchBuilder(schema)
  builder.append_i8(0, cast(42, i8))
  builder.append_i16(1, cast(42, i16))
  builder.append_i32(2, 42)
  builder.append_i64(3, 42)
  builder.append_f32(4, cast(1.5, f32))
  builder.append_f64(5, 1.5)
  builder.append_bool(6, true)
  builder.append_utf8(7, "λ")
  builder.append_utf8(8, "λ")
  builder.append_date(9, 12)
  builder.append_date(10, 86400000)
  builder.append_timestamp(11, 123)
  builder.append_time(12, 123)
  var batch: RecordBatch = builder.finish()
  assert batch.get_i8(0, 0) == 42
  assert batch.get_i16(1, 0) == 42
  assert batch.get_i32(2, 0) == 42
  assert batch.get_i64(3, 0) == 42
  assert batch.get_f32(4, 0) == 1.5
  assert batch.get_f64(5, 0) == 1.5
  assert batch.get_bool(6, 0) == true
  assert batch.get_utf8(7, 0) == "λ"
  assert batch.get_utf8(8, 0) == "λ"
  assert batch.get_date(9, 0) == 12
  assert batch.get_date(10, 0) == 86400000
  assert batch.get_timestamp(11, 0) == 123
  assert batch.get_time(12, 0) == 123
  assert schema.nfields() == 13
  assert schema.name(0) == "col0"
  assert schema.type(0) == 0
  assert schema.type_name(11) == "timestamp[us]"
  assert schema.nullable(0)
  var writer: IPCWriter = IPCWriter(schema)
  schema.close()
  schema.close()
  writer.open_stream("typed.arrow")
  writer.write(batch)
  batch.close()
  batch.close()
  writer.write(builder.finish())
  builder.append_null(0)
  builder.append_null(1)
  builder.append_null(2)
  builder.append_null(3)
  builder.append_null(4)
  builder.append_null(5)
  builder.append_null(6)
  builder.append_null(7)
  builder.append_null(8)
  builder.append_null(9)
  builder.append_null(10)
  builder.append_null(11)
  builder.append_null(12)
  var nulls: RecordBatch = builder.finish()
  assert nulls.is_null(0, 0)
  writer.write(nulls)
  writer.close()
  builder.close()
  builder.close()
  return 0
