```
title: Apache Arrow interoperability
summary: RecordBatches, schemas, IPC, TCP and C Data interoperability.
```

irx_rb_api_schema_new: extern :: fn() -> ArrowSchemaHandle
irx_rb_api_batch_new: extern :: fn() -> ArrowBatchHandle
irx_rb_api_reader_new: extern :: fn() -> ArrowReaderHandle
irx_rb_api_builder_new: extern :: fn(schema: ArrowSchemaHandle) -> ArrowBuilderHandle
irx_rb_api_writer_new: extern :: fn(schema: ArrowSchemaHandle) -> ArrowWriterHandle
irx_rb_api_schema_destroy: extern :: fn(box: ArrowSchemaHandle) -> none
irx_rb_api_schema_close: extern :: fn(box: ArrowSchemaHandle) -> none
irx_rb_api_batch_destroy: extern :: fn(box: ArrowBatchHandle) -> none
irx_rb_api_batch_close: extern :: fn(box: ArrowBatchHandle) -> none
irx_rb_api_builder_destroy: extern :: fn(box: ArrowBuilderHandle) -> none
irx_rb_api_builder_close: extern :: fn(box: ArrowBuilderHandle) -> none
irx_rb_api_reader_destroy: extern :: fn(box: ArrowReaderHandle) -> none
irx_rb_api_reader_close: extern :: fn(box: ArrowReaderHandle) -> none
irx_rb_api_writer_destroy: extern :: fn(box: ArrowWriterHandle) -> none
irx_rb_api_writer_close: extern :: fn(box: ArrowWriterHandle) -> none
irx_rb_api_schema_add_name: extern :: fn(box: ArrowSchemaHandle, name: str, type: str, nullable: i32) -> none
irx_rb_api_schema_count: extern :: fn(box: ArrowSchemaHandle) -> i32
irx_rb_api_schema_name: extern :: fn(box: ArrowSchemaHandle, col: i32) -> str
irx_rb_api_schema_type: extern :: fn(box: ArrowSchemaHandle, col: i32) -> i32
irx_rb_api_schema_nullable: extern :: fn(box: ArrowSchemaHandle, col: i32) -> i32
irx_rb_api_schema_type_name: extern :: fn(box: ArrowSchemaHandle, col: i32) -> str
irx_rb_api_schema_equal: extern :: fn(box: ArrowSchemaHandle, other: ArrowSchemaHandle) -> i32
irx_rb_api_builder_finish: extern :: fn(box: ArrowBuilderHandle, out: ArrowBatchHandle) -> none
irx_rb_api_batch_rows: extern :: fn(box: ArrowBatchHandle) -> i64
irx_rb_api_batch_columns: extern :: fn(box: ArrowBatchHandle) -> i32
irx_rb_api_batch_schema: extern :: fn(box: ArrowBatchHandle, out: ArrowSchemaHandle) -> none
irx_rb_api_batch_null: extern :: fn(box: ArrowBatchHandle, col: i32, row: i64) -> i32
irx_rb_api_append_u8: extern :: fn(box: ArrowBuilderHandle, col: i32, value: u8) -> none
irx_rb_api_get_u8: extern :: fn(box: ArrowBatchHandle, col: i32, row: i64) -> u8
irx_rb_api_append_u16: extern :: fn(box: ArrowBuilderHandle, col: i32, value: u16) -> none
irx_rb_api_get_u16: extern :: fn(box: ArrowBatchHandle, col: i32, row: i64) -> u16
irx_rb_api_append_u32: extern :: fn(box: ArrowBuilderHandle, col: i32, value: u32) -> none
irx_rb_api_get_u32: extern :: fn(box: ArrowBatchHandle, col: i32, row: i64) -> u32
irx_rb_api_append_u64: extern :: fn(box: ArrowBuilderHandle, col: i32, value: u64) -> none
irx_rb_api_get_u64: extern :: fn(box: ArrowBatchHandle, col: i32, row: i64) -> u64
irx_rb_api_append_i8: extern :: fn(box: ArrowBuilderHandle, col: i32, value: i8) -> none
irx_rb_api_get_i8: extern :: fn(box: ArrowBatchHandle, col: i32, row: i64) -> i8
irx_rb_api_append_i16: extern :: fn(box: ArrowBuilderHandle, col: i32, value: i16) -> none
irx_rb_api_get_i16: extern :: fn(box: ArrowBatchHandle, col: i32, row: i64) -> i16
irx_rb_api_append_i32: extern :: fn(box: ArrowBuilderHandle, col: i32, value: i32) -> none
irx_rb_api_get_i32: extern :: fn(box: ArrowBatchHandle, col: i32, row: i64) -> i32
irx_rb_api_append_i64: extern :: fn(box: ArrowBuilderHandle, col: i32, value: i64) -> none
irx_rb_api_get_i64: extern :: fn(box: ArrowBatchHandle, col: i32, row: i64) -> i64
irx_rb_api_append_f32: extern :: fn(box: ArrowBuilderHandle, col: i32, value: f32) -> none
irx_rb_api_get_f32: extern :: fn(box: ArrowBatchHandle, col: i32, row: i64) -> f32
irx_rb_api_append_f64: extern :: fn(box: ArrowBuilderHandle, col: i32, value: f64) -> none
irx_rb_api_get_f64: extern :: fn(box: ArrowBatchHandle, col: i32, row: i64) -> f64
irx_rb_api_append_bool: extern :: fn(box: ArrowBuilderHandle, col: i32, value: i32) -> none
irx_rb_api_get_bool: extern :: fn(box: ArrowBatchHandle, col: i32, row: i64) -> i32
irx_rb_api_append_date: extern :: fn(box: ArrowBuilderHandle, col: i32, value: i64) -> none
irx_rb_api_get_date: extern :: fn(box: ArrowBatchHandle, col: i32, row: i64) -> i64
irx_rb_api_append_timestamp: extern :: fn(box: ArrowBuilderHandle, col: i32, value: i64) -> none
irx_rb_api_get_timestamp: extern :: fn(box: ArrowBatchHandle, col: i32, row: i64) -> i64
irx_rb_api_append_time: extern :: fn(box: ArrowBuilderHandle, col: i32, value: i64) -> none
irx_rb_api_get_time: extern :: fn(box: ArrowBatchHandle, col: i32, row: i64) -> i64
irx_rb_api_append_utf8: extern :: fn(box: ArrowBuilderHandle, col: i32, value: str) -> none
irx_rb_api_get_utf8: extern :: fn(box: ArrowBatchHandle, col: i32, row: i64) -> str
irx_rb_api_append_null: extern :: fn(box: ArrowBuilderHandle, col: i32) -> none
irx_rb_api_reader_file: extern :: fn(box: ArrowReaderHandle, path: str) -> none
irx_rb_api_reader_stream: extern :: fn(box: ArrowReaderHandle, path: str) -> none
irx_rb_api_reader_tcp: extern :: fn(box: ArrowReaderHandle, host: str, port: i32, timeout: i32) -> none
irx_rb_api_writer_file: extern :: fn(box: ArrowWriterHandle, path: str) -> none
irx_rb_api_writer_stream: extern :: fn(box: ArrowWriterHandle, path: str) -> none
irx_rb_api_writer_tcp: extern :: fn(box: ArrowWriterHandle, host: str, port: i32, timeout: i32) -> none
irx_rb_api_writer_write: extern :: fn(box: ArrowWriterHandle, batch: ArrowBatchHandle) -> none
irx_rb_api_reader_next: extern :: fn(box: ArrowReaderHandle) -> i32
irx_rb_api_reader_batch: extern :: fn(box: ArrowReaderHandle, out: ArrowBatchHandle) -> none
irx_rb_api_reader_schema: extern :: fn(box: ArrowReaderHandle, out: ArrowSchemaHandle) -> none
irx_rb_api_batch_export_stream: extern :: fn(box: ArrowBatchHandle, address: i64) -> i32
irx_rb_api_batch_export: extern :: fn(box: ArrowBatchHandle, array: i64, schema: i64) -> i32
irx_rb_api_batch_import: extern :: fn(box: ArrowBatchHandle, array: i64, schema: i64) -> none
irx_rb_api_reader_import: extern :: fn(box: ArrowReaderHandle, address: i64) -> none

class Schema:
  ```
  title: Schema
  summary: Scoped owner of a native Arrow schema.
  ```
  handle: private :: ArrowSchemaHandle

  __init__: fn(self) -> none:
    ```
    title: __init__
    summary: Creates one native owner.
    ```
    self.handle = irx_rb_api_schema_new()
    return none

  __del__: fn(self) -> none:
    ```
    title: __del__
    summary: Releases the native box at the last class reference.
    ```
    irx_rb_api_schema_destroy(self.handle)
    return none

  close: fn(self) -> none:
    ```
    title: close
    summary: Releases native resources idempotently; aliases observe closure.
    ```
    irx_rb_api_schema_close(self.handle)
    return none

  native_handle: fn(self) -> ArrowSchemaHandle:
    ```
    title: native_handle
    summary: Borrows the opaque handle for trusted native integrations only.
    ```
    return self.handle

  add: fn(self, name: str, type_name: str, nullable: bool = false) -> none:
    ```
    title: add
    summary: Adds a field using a checked Arrow scalar type name.
    ```
    irx_rb_api_schema_add_name(self.handle, name, type_name, cast(nullable, i32))
    return none

  nfields: fn(self) -> i32:
    ```
    title: nfields
    summary: Returns the field count.
    ```
    return irx_rb_api_schema_count(self.handle)

  name: fn(self, col: i32) -> str:
    ```
    title: name
    summary: Inspects one field without erasing Arrow type information.
    ```
    return irx_rb_api_schema_name(self.handle, col)

  type: fn(self, col: i32) -> i32:
    ```
    title: type
    summary: Inspects one field without erasing Arrow type information.
    ```
    return irx_rb_api_schema_type(self.handle, col)

  type_name: fn(self, col: i32) -> str:
    ```
    title: type_name
    summary: Inspects one field without erasing Arrow type information.
    ```
    return irx_rb_api_schema_type_name(self.handle, col)

  nullable: fn(self, col: i32) -> bool:
    ```
    title: nullable
    summary: Returns whether the schema permits null values.
    ```
    return irx_rb_api_schema_nullable(self.handle, col) != 0

  equals: fn(self, other: Schema) -> bool:
    ```
    title: equals
    summary: Compares names, types, nullability and metadata exactly.
    ```
    return irx_rb_api_schema_equal(self.handle, other.native_handle()) != 0


class RecordBatch:
  ```
  title: RecordBatch
  summary: Scoped owner of a native Arrow batch.
  ```
  handle: private :: ArrowBatchHandle

  __init__: fn(self) -> none:
    ```
    title: __init__
    summary: Creates one native owner.
    ```
    self.handle = irx_rb_api_batch_new()
    return none

  __del__: fn(self) -> none:
    ```
    title: __del__
    summary: Releases the native box at the last class reference.
    ```
    irx_rb_api_batch_destroy(self.handle)
    return none

  close: fn(self) -> none:
    ```
    title: close
    summary: Releases native resources idempotently; aliases observe closure.
    ```
    irx_rb_api_batch_close(self.handle)
    return none

  native_handle: fn(self) -> ArrowBatchHandle:
    ```
    title: native_handle
    summary: Borrows the opaque handle for trusted native integrations only.
    ```
    return self.handle

  nrows: fn(self) -> i64:
    ```
    title: nrows
    summary: Returns the row count.
    ```
    return irx_rb_api_batch_rows(self.handle)

  ncols: fn(self) -> i32:
    ```
    title: ncols
    summary: Returns the column count.
    ```
    return irx_rb_api_batch_columns(self.handle)

  schema: fn(self) -> Schema:
    ```
    title: schema
    summary: Returns an independently owned schema snapshot.
    ```
    result: Schema = Schema()
    irx_rb_api_batch_schema(self.handle, result.native_handle())
    return result

  is_null: fn(self, col: i32, row: i64) -> bool:
    ```
    title: is_null
    summary: Checks validity before using a typed getter.
    ```
    return irx_rb_api_batch_null(self.handle, col, row) != 0

  get_u8: fn(self, col: i32, row: i64) -> u8:
    ```
    title: Read an unsigned 8-bit value; reject null slots.
    ```
    return irx_rb_api_get_u8(self.handle, col, row)

  get_u16: fn(self, col: i32, row: i64) -> u16:
    ```
    title: Read an unsigned 16-bit value; reject null slots.
    ```
    return irx_rb_api_get_u16(self.handle, col, row)

  get_u32: fn(self, col: i32, row: i64) -> u32:
    ```
    title: Read an unsigned 32-bit value; reject null slots.
    ```
    return irx_rb_api_get_u32(self.handle, col, row)

  get_u64: fn(self, col: i32, row: i64) -> u64:
    ```
    title: Read an unsigned 64-bit value; reject null slots.
    ```
    return irx_rb_api_get_u64(self.handle, col, row)

  get_i8: fn(self, col: i32, row: i64) -> i8:
    ```
    title: get_i8
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_i8(self.handle, col, row)

  get_i16: fn(self, col: i32, row: i64) -> i16:
    ```
    title: get_i16
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_i16(self.handle, col, row)

  get_i32: fn(self, col: i32, row: i64) -> i32:
    ```
    title: get_i32
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_i32(self.handle, col, row)

  get_i64: fn(self, col: i32, row: i64) -> i64:
    ```
    title: get_i64
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_i64(self.handle, col, row)

  get_f32: fn(self, col: i32, row: i64) -> f32:
    ```
    title: get_f32
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_f32(self.handle, col, row)

  get_f64: fn(self, col: i32, row: i64) -> f64:
    ```
    title: get_f64
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_f64(self.handle, col, row)

  get_bool: fn(self, col: i32, row: i64) -> bool:
    ```
    title: get_bool
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_bool(self.handle, col, row) != 0

  get_date: fn(self, col: i32, row: i64) -> i64:
    ```
    title: get_date
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_date(self.handle, col, row)

  get_timestamp: fn(self, col: i32, row: i64) -> i64:
    ```
    title: get_timestamp
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_timestamp(self.handle, col, row)

  get_time: fn(self, col: i32, row: i64) -> i64:
    ```
    title: get_time
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_time(self.handle, col, row)

  get_utf8: fn(self, col: i32, row: i64) -> str:
    ```
    title: get_utf8
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_utf8(self.handle, col, row)

  export_stream: fn(self, address: i64) -> i32:
    ```
    title: export_stream
    summary: Exports to a caller-owned ArrowArrayStream address; returns native status.
    ```
    return irx_rb_api_batch_export_stream(self.handle, address)

  export_c: fn(self, array: i64, schema: i64) -> i32:
    ```
    title: export_c
    summary: Exports to caller-owned C Data structs; returns native status.
    ```
    return irx_rb_api_batch_export(self.handle, array, schema)

  import_c: fn(self, array: i64, schema: i64) -> none:
    ```
    title: import_c
    summary: Moves C Data from trusted addresses into this batch.
    ```
    irx_rb_api_batch_import(self.handle, array, schema)
    return none


class BatchBuilder:
  ```
  title: BatchBuilder
  summary: Scoped owner of a native Arrow builder.
  ```
  handle: private :: ArrowBuilderHandle

  __init__: fn(self, schema: Schema) -> none:
    ```
    title: __init__
    summary: Creates one native owner.
    ```
    self.handle = irx_rb_api_builder_new(schema.native_handle())
    return none

  __del__: fn(self) -> none:
    ```
    title: __del__
    summary: Releases the native box at the last class reference.
    ```
    irx_rb_api_builder_destroy(self.handle)
    return none

  close: fn(self) -> none:
    ```
    title: close
    summary: Releases native resources idempotently; aliases observe closure.
    ```
    irx_rb_api_builder_close(self.handle)
    return none

  native_handle: fn(self) -> ArrowBuilderHandle:
    ```
    title: native_handle
    summary: Borrows the opaque handle for trusted native integrations only.
    ```
    return self.handle

  append_u8: fn(self, col: i32, value: u8) -> none:
    ```
    title: Append an unsigned 8-bit value without signed narrowing.
    ```
    irx_rb_api_append_u8(self.handle, col, value)
    return none

  append_u16: fn(self, col: i32, value: u16) -> none:
    ```
    title: Append an unsigned 16-bit value without signed narrowing.
    ```
    irx_rb_api_append_u16(self.handle, col, value)
    return none

  append_u32: fn(self, col: i32, value: u32) -> none:
    ```
    title: Append an unsigned 32-bit value without signed narrowing.
    ```
    irx_rb_api_append_u32(self.handle, col, value)
    return none

  append_u64: fn(self, col: i32, value: u64) -> none:
    ```
    title: Append an unsigned 64-bit value without signed narrowing.
    ```
    irx_rb_api_append_u64(self.handle, col, value)
    return none

  append_i8: fn(self, col: i32, value: i8) -> none:
    ```
    title: append_i8
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_i8(self.handle, col, value)
    return none

  append_i16: fn(self, col: i32, value: i16) -> none:
    ```
    title: append_i16
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_i16(self.handle, col, value)
    return none

  append_i32: fn(self, col: i32, value: i32) -> none:
    ```
    title: append_i32
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_i32(self.handle, col, value)
    return none

  append_i64: fn(self, col: i32, value: i64) -> none:
    ```
    title: append_i64
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_i64(self.handle, col, value)
    return none

  append_f32: fn(self, col: i32, value: f32) -> none:
    ```
    title: append_f32
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_f32(self.handle, col, value)
    return none

  append_f64: fn(self, col: i32, value: f64) -> none:
    ```
    title: append_f64
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_f64(self.handle, col, value)
    return none

  append_bool: fn(self, col: i32, value: bool) -> none:
    ```
    title: append_bool
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_bool(self.handle, col, cast(value, i32))
    return none

  append_date: fn(self, col: i32, value: i64) -> none:
    ```
    title: append_date
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_date(self.handle, col, value)
    return none

  append_timestamp: fn(self, col: i32, value: i64) -> none:
    ```
    title: append_timestamp
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_timestamp(self.handle, col, value)
    return none

  append_time: fn(self, col: i32, value: i64) -> none:
    ```
    title: append_time
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_time(self.handle, col, value)
    return none

  append_utf8: fn(self, col: i32, value: str) -> none:
    ```
    title: append_utf8
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_utf8(self.handle, col, value)
    return none

  append_null: fn(self, col: i32) -> none:
    ```
    title: append_null
    summary: Appends null only to a nullable field.
    ```
    irx_rb_api_append_null(self.handle, col)
    return none

  finish: fn(self) -> RecordBatch:
    ```
    title: finish
    summary: Finishes equal-length columns and resets the builder for reuse.
    ```
    result: RecordBatch = RecordBatch()
    irx_rb_api_builder_finish(self.handle, result.native_handle())
    return result


irx_rb_api_reader_csv: extern :: fn(box: ArrowReaderHandle, path: str, delimiter: str, header: i32, block_size: i32) -> none
irx_rb_api_reader_csv_as: extern :: fn(box: ArrowReaderHandle, path: str, schema: ArrowSchemaHandle, delimiter: str, header: i32, block_size: i32) -> none
irx_rb_api_writer_csv: extern :: fn(box: ArrowWriterHandle, path: str, delimiter: str, header: i32) -> none

class IPCReader:
  ```
  title: IPCReader
  summary: Scoped owner of a native Arrow reader.
  ```
  handle: private :: ArrowReaderHandle

  __init__: fn(self) -> none:
    ```
    title: __init__
    summary: Creates one native owner.
    ```
    self.handle = irx_rb_api_reader_new()
    return none

  __del__: fn(self) -> none:
    ```
    title: __del__
    summary: Releases the native box at the last class reference.
    ```
    irx_rb_api_reader_destroy(self.handle)
    return none

  close: fn(self) -> none:
    ```
    title: close
    summary: Releases native resources idempotently; aliases observe closure.
    ```
    irx_rb_api_reader_close(self.handle)
    return none

  native_handle: fn(self) -> ArrowReaderHandle:
    ```
    title: native_handle
    summary: Borrows the opaque handle for trusted native integrations only.
    ```
    return self.handle

  open_file: fn(self, path: str) -> none:
    ```
    title: open_file
    summary: Opens Arrow IPC file format at a filesystem path.
    ```
    irx_rb_api_reader_file(self.handle, path)
    return none

  open_stream: fn(self, path: str) -> none:
    ```
    title: open_stream
    summary: Opens Arrow IPC stream format at a filesystem path.
    ```
    irx_rb_api_reader_stream(self.handle, path)
    return none

  connect: fn(self, host: str, port: i32, timeout_ms: i32 = 30000) -> none:
    ```
    title: connect
    summary: Connects to a numeric IP address for IPC streaming over TCP.
    ```
    irx_rb_api_reader_tcp(self.handle, host, port, timeout_ms)
    return none

  next: fn(self) -> bool:
    ```
    title: next
    summary: Advances one batch; false means an orderly end, not an empty batch.
    ```
    return irx_rb_api_reader_next(self.handle) == 0

  batch: fn(self) -> RecordBatch:
    ```
    title: batch
    summary: Returns an independently owned snapshot.
    ```
    result: RecordBatch = RecordBatch()
    irx_rb_api_reader_batch(self.handle, result.native_handle())
    return result

  schema: fn(self) -> Schema:
    ```
    title: schema
    summary: Returns an independently owned snapshot.
    ```
    result: Schema = Schema()
    irx_rb_api_reader_schema(self.handle, result.native_handle())
    return result

  import_stream: fn(self, address: i64) -> none:
    ```
    title: import_stream
    summary: Moves a caller-provided ArrowArrayStream into this reader.
    ```
    irx_rb_api_reader_import(self.handle, address)
    return none


class IPCWriter:
  ```
  title: IPCWriter
  summary: Scoped owner of a native Arrow writer.
  ```
  handle: private :: ArrowWriterHandle

  __init__: fn(self, schema: Schema) -> none:
    ```
    title: __init__
    summary: Creates one native owner.
    ```
    self.handle = irx_rb_api_writer_new(schema.native_handle())
    return none

  __del__: fn(self) -> none:
    ```
    title: __del__
    summary: Releases the native box at the last class reference.
    ```
    irx_rb_api_writer_destroy(self.handle)
    return none

  close: fn(self) -> none:
    ```
    title: close
    summary: Releases native resources idempotently; aliases observe closure.
    ```
    irx_rb_api_writer_close(self.handle)
    return none

  native_handle: fn(self) -> ArrowWriterHandle:
    ```
    title: native_handle
    summary: Borrows the opaque handle for trusted native integrations only.
    ```
    return self.handle

  open_file: fn(self, path: str) -> none:
    ```
    title: open_file
    summary: Opens Arrow IPC file format at a filesystem path.
    ```
    irx_rb_api_writer_file(self.handle, path)
    return none

  open_stream: fn(self, path: str) -> none:
    ```
    title: open_stream
    summary: Opens Arrow IPC stream format at a filesystem path.
    ```
    irx_rb_api_writer_stream(self.handle, path)
    return none

  connect: fn(self, host: str, port: i32, timeout_ms: i32 = 30000) -> none:
    ```
    title: connect
    summary: Connects to a numeric IP address for IPC streaming over TCP.
    ```
    irx_rb_api_writer_tcp(self.handle, host, port, timeout_ms)
    return none

  write: fn(self, batch: RecordBatch) -> none:
    ```
    title: write
    summary: Writes one batch with exact schema validation.
    ```
    irx_rb_api_writer_write(self.handle, batch.native_handle())
    return none
