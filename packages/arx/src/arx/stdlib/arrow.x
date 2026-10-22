```
title: Apache Arrow interoperability
summary: RecordBatches, CSV and Parquet files, IPC, TCP and C Data.
```

extern irx_rb_api_schema_new() -> ArrowSchemaHandle
extern irx_rb_api_batch_new() -> ArrowBatchHandle
extern irx_rb_api_reader_new() -> ArrowReaderHandle
extern irx_rb_api_builder_new(schema: ArrowSchemaHandle) -> ArrowBuilderHandle
extern irx_rb_api_writer_new(schema: ArrowSchemaHandle) -> ArrowWriterHandle
extern irx_rb_api_schema_destroy(box: ArrowSchemaHandle) -> none
extern irx_rb_api_schema_close(box: ArrowSchemaHandle) -> none
extern irx_rb_api_batch_destroy(box: ArrowBatchHandle) -> none
extern irx_rb_api_batch_close(box: ArrowBatchHandle) -> none
extern irx_rb_api_builder_destroy(box: ArrowBuilderHandle) -> none
extern irx_rb_api_builder_close(box: ArrowBuilderHandle) -> none
extern irx_rb_api_reader_destroy(box: ArrowReaderHandle) -> none
extern irx_rb_api_reader_close(box: ArrowReaderHandle) -> none
extern irx_rb_api_writer_destroy(box: ArrowWriterHandle) -> none
extern irx_rb_api_writer_close(box: ArrowWriterHandle) -> none
extern irx_rb_api_schema_add(box: ArrowSchemaHandle, name: str, type: i32, nullable: i32) -> none
extern irx_rb_api_schema_count(box: ArrowSchemaHandle) -> i32
extern irx_rb_api_schema_name(box: ArrowSchemaHandle, col: i32) -> str
extern irx_rb_api_schema_type(box: ArrowSchemaHandle, col: i32) -> i32
extern irx_rb_api_schema_nullable(box: ArrowSchemaHandle, col: i32) -> i32
extern irx_rb_api_schema_type_name(box: ArrowSchemaHandle, col: i32) -> str
extern irx_rb_api_schema_equal(box: ArrowSchemaHandle, other: ArrowSchemaHandle) -> i32
extern irx_rb_api_builder_finish(box: ArrowBuilderHandle, out: ArrowBatchHandle) -> none
extern irx_rb_api_batch_rows(box: ArrowBatchHandle) -> i64
extern irx_rb_api_batch_columns(box: ArrowBatchHandle) -> i32
extern irx_rb_api_batch_schema(box: ArrowBatchHandle, out: ArrowSchemaHandle) -> none
extern irx_rb_api_batch_null(box: ArrowBatchHandle, col: i32, row: i64) -> i32
extern irx_rb_api_append_i8(box: ArrowBuilderHandle, col: i32, value: i8) -> none
extern irx_rb_api_get_i8(box: ArrowBatchHandle, col: i32, row: i64) -> i8
extern irx_rb_api_append_i16(box: ArrowBuilderHandle, col: i32, value: i16) -> none
extern irx_rb_api_get_i16(box: ArrowBatchHandle, col: i32, row: i64) -> i16
extern irx_rb_api_append_i32(box: ArrowBuilderHandle, col: i32, value: i32) -> none
extern irx_rb_api_get_i32(box: ArrowBatchHandle, col: i32, row: i64) -> i32
extern irx_rb_api_append_i64(box: ArrowBuilderHandle, col: i32, value: i64) -> none
extern irx_rb_api_get_i64(box: ArrowBatchHandle, col: i32, row: i64) -> i64
extern irx_rb_api_append_f32(box: ArrowBuilderHandle, col: i32, value: f32) -> none
extern irx_rb_api_get_f32(box: ArrowBatchHandle, col: i32, row: i64) -> f32
extern irx_rb_api_append_f64(box: ArrowBuilderHandle, col: i32, value: f64) -> none
extern irx_rb_api_get_f64(box: ArrowBatchHandle, col: i32, row: i64) -> f64
extern irx_rb_api_append_bool(box: ArrowBuilderHandle, col: i32, value: i32) -> none
extern irx_rb_api_get_bool(box: ArrowBatchHandle, col: i32, row: i64) -> i32
extern irx_rb_api_append_date(box: ArrowBuilderHandle, col: i32, value: i64) -> none
extern irx_rb_api_get_date(box: ArrowBatchHandle, col: i32, row: i64) -> i64
extern irx_rb_api_append_timestamp(box: ArrowBuilderHandle, col: i32, value: i64) -> none
extern irx_rb_api_get_timestamp(box: ArrowBatchHandle, col: i32, row: i64) -> i64
extern irx_rb_api_append_time(box: ArrowBuilderHandle, col: i32, value: i64) -> none
extern irx_rb_api_get_time(box: ArrowBatchHandle, col: i32, row: i64) -> i64
extern irx_rb_api_append_utf8(box: ArrowBuilderHandle, col: i32, value: str) -> none
extern irx_rb_api_get_utf8(box: ArrowBatchHandle, col: i32, row: i64) -> str
extern irx_rb_api_append_null(box: ArrowBuilderHandle, col: i32) -> none
extern irx_rb_api_reader_file(box: ArrowReaderHandle, path: str) -> none
extern irx_rb_api_reader_stream(box: ArrowReaderHandle, path: str) -> none
extern irx_rb_api_reader_tcp(box: ArrowReaderHandle, host: str, port: i32, timeout: i32) -> none
extern irx_rb_api_writer_file(box: ArrowWriterHandle, path: str) -> none
extern irx_rb_api_writer_stream(box: ArrowWriterHandle, path: str) -> none
extern irx_rb_api_writer_tcp(box: ArrowWriterHandle, host: str, port: i32, timeout: i32) -> none
extern irx_rb_api_writer_write(box: ArrowWriterHandle, batch: ArrowBatchHandle) -> none
extern irx_rb_api_reader_next(box: ArrowReaderHandle) -> i32
extern irx_rb_api_reader_batch(box: ArrowReaderHandle, out: ArrowBatchHandle) -> none
extern irx_rb_api_reader_schema(box: ArrowReaderHandle, out: ArrowSchemaHandle) -> none
extern irx_rb_api_batch_export_stream(box: ArrowBatchHandle, address: i64) -> i32
extern irx_rb_api_batch_export(box: ArrowBatchHandle, array: i64, schema: i64) -> i32
extern irx_rb_api_batch_import(box: ArrowBatchHandle, array: i64, schema: i64) -> none
extern irx_rb_api_reader_import(box: ArrowReaderHandle, address: i64) -> none

class Schema:
  ```
  title: Schema
  summary: Scoped owner of a native Arrow schema.
  ```
  @[private]
  handle: ArrowSchemaHandle

  fn __init__(self) -> none:
    ```
    title: __init__
    summary: Creates one native owner.
    ```
    self.handle = irx_rb_api_schema_new()
    return none

  fn __del__(self) -> none:
    ```
    title: __del__
    summary: Releases the native box at the last class reference.
    ```
    irx_rb_api_schema_destroy(self.handle)
    return none

  fn close(self) -> none:
    ```
    title: close
    summary: Releases native resources idempotently; aliases observe closure.
    ```
    irx_rb_api_schema_close(self.handle)
    return none

  fn native_handle(self) -> ArrowSchemaHandle:
    ```
    title: native_handle
    summary: Borrows the opaque handle for trusted native integrations only.
    ```
    return self.handle

  fn add(self, name: str, type_id: i32, nullable: bool = false) -> none:
    ```
    title: add
    summary: Adds a field using the IrxColumnType identifier.
    ```
    irx_rb_api_schema_add(self.handle, name, type_id, cast(nullable, i32))
    return none

  fn nfields(self) -> i32:
    ```
    title: nfields
    summary: Returns the field count.
    ```
    return irx_rb_api_schema_count(self.handle)

  fn name(self, col: i32) -> str:
    ```
    title: name
    summary: Inspects one field without erasing Arrow type information.
    ```
    return irx_rb_api_schema_name(self.handle, col)

  fn type(self, col: i32) -> i32:
    ```
    title: type
    summary: Inspects one field without erasing Arrow type information.
    ```
    return irx_rb_api_schema_type(self.handle, col)

  fn type_name(self, col: i32) -> str:
    ```
    title: type_name
    summary: Inspects one field without erasing Arrow type information.
    ```
    return irx_rb_api_schema_type_name(self.handle, col)

  fn nullable(self, col: i32) -> bool:
    ```
    title: nullable
    summary: Returns whether the schema permits null values.
    ```
    return irx_rb_api_schema_nullable(self.handle, col) != 0

  fn equals(self, other: Schema) -> bool:
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
  @[private]
  handle: ArrowBatchHandle

  fn __init__(self) -> none:
    ```
    title: __init__
    summary: Creates one native owner.
    ```
    self.handle = irx_rb_api_batch_new()
    return none

  fn __del__(self) -> none:
    ```
    title: __del__
    summary: Releases the native box at the last class reference.
    ```
    irx_rb_api_batch_destroy(self.handle)
    return none

  fn close(self) -> none:
    ```
    title: close
    summary: Releases native resources idempotently; aliases observe closure.
    ```
    irx_rb_api_batch_close(self.handle)
    return none

  fn native_handle(self) -> ArrowBatchHandle:
    ```
    title: native_handle
    summary: Borrows the opaque handle for trusted native integrations only.
    ```
    return self.handle

  fn nrows(self) -> i64:
    ```
    title: nrows
    summary: Returns the row count.
    ```
    return irx_rb_api_batch_rows(self.handle)

  fn ncols(self) -> i32:
    ```
    title: ncols
    summary: Returns the column count.
    ```
    return irx_rb_api_batch_columns(self.handle)

  fn schema(self) -> Schema:
    ```
    title: schema
    summary: Returns an independently owned schema snapshot.
    ```
    var result: Schema = Schema()
    irx_rb_api_batch_schema(self.handle, result.native_handle())
    return result

  fn is_null(self, col: i32, row: i64) -> bool:
    ```
    title: is_null
    summary: Checks validity before using a typed getter.
    ```
    return irx_rb_api_batch_null(self.handle, col, row) != 0

  fn get_i8(self, col: i32, row: i64) -> i8:
    ```
    title: get_i8
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_i8(self.handle, col, row)

  fn get_i16(self, col: i32, row: i64) -> i16:
    ```
    title: get_i16
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_i16(self.handle, col, row)

  fn get_i32(self, col: i32, row: i64) -> i32:
    ```
    title: get_i32
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_i32(self.handle, col, row)

  fn get_i64(self, col: i32, row: i64) -> i64:
    ```
    title: get_i64
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_i64(self.handle, col, row)

  fn get_f32(self, col: i32, row: i64) -> f32:
    ```
    title: get_f32
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_f32(self.handle, col, row)

  fn get_f64(self, col: i32, row: i64) -> f64:
    ```
    title: get_f64
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_f64(self.handle, col, row)

  fn get_bool(self, col: i32, row: i64) -> bool:
    ```
    title: get_bool
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_bool(self.handle, col, row) != 0

  fn get_date(self, col: i32, row: i64) -> i64:
    ```
    title: get_date
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_date(self.handle, col, row)

  fn get_timestamp(self, col: i32, row: i64) -> i64:
    ```
    title: get_timestamp
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_timestamp(self.handle, col, row)

  fn get_time(self, col: i32, row: i64) -> i64:
    ```
    title: get_time
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_time(self.handle, col, row)

  fn get_utf8(self, col: i32, row: i64) -> str:
    ```
    title: get_utf8
    summary: Reads a non-null value with a checked Arrow type and bounds.
    ```
    return irx_rb_api_get_utf8(self.handle, col, row)

  fn export_stream(self, address: i64) -> i32:
    ```
    title: export_stream
    summary: Exports to a caller-owned ArrowArrayStream address; returns native status.
    ```
    return irx_rb_api_batch_export_stream(self.handle, address)

  fn export_c(self, array: i64, schema: i64) -> i32:
    ```
    title: export_c
    summary: Exports to caller-owned C Data structs; returns native status.
    ```
    return irx_rb_api_batch_export(self.handle, array, schema)

  fn import_c(self, array: i64, schema: i64) -> none:
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
  @[private]
  handle: ArrowBuilderHandle

  fn __init__(self, schema: Schema) -> none:
    ```
    title: __init__
    summary: Creates one native owner.
    ```
    self.handle = irx_rb_api_builder_new(schema.native_handle())
    return none

  fn __del__(self) -> none:
    ```
    title: __del__
    summary: Releases the native box at the last class reference.
    ```
    irx_rb_api_builder_destroy(self.handle)
    return none

  fn close(self) -> none:
    ```
    title: close
    summary: Releases native resources idempotently; aliases observe closure.
    ```
    irx_rb_api_builder_close(self.handle)
    return none

  fn native_handle(self) -> ArrowBuilderHandle:
    ```
    title: native_handle
    summary: Borrows the opaque handle for trusted native integrations only.
    ```
    return self.handle

  fn append_i8(self, col: i32, value: i8) -> none:
    ```
    title: append_i8
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_i8(self.handle, col, value)
    return none

  fn append_i16(self, col: i32, value: i16) -> none:
    ```
    title: append_i16
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_i16(self.handle, col, value)
    return none

  fn append_i32(self, col: i32, value: i32) -> none:
    ```
    title: append_i32
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_i32(self.handle, col, value)
    return none

  fn append_i64(self, col: i32, value: i64) -> none:
    ```
    title: append_i64
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_i64(self.handle, col, value)
    return none

  fn append_f32(self, col: i32, value: f32) -> none:
    ```
    title: append_f32
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_f32(self.handle, col, value)
    return none

  fn append_f64(self, col: i32, value: f64) -> none:
    ```
    title: append_f64
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_f64(self.handle, col, value)
    return none

  fn append_bool(self, col: i32, value: bool) -> none:
    ```
    title: append_bool
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_bool(self.handle, col, cast(value, i32))
    return none

  fn append_date(self, col: i32, value: i64) -> none:
    ```
    title: append_date
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_date(self.handle, col, value)
    return none

  fn append_timestamp(self, col: i32, value: i64) -> none:
    ```
    title: append_timestamp
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_timestamp(self.handle, col, value)
    return none

  fn append_time(self, col: i32, value: i64) -> none:
    ```
    title: append_time
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_time(self.handle, col, value)
    return none

  fn append_utf8(self, col: i32, value: str) -> none:
    ```
    title: append_utf8
    summary: Appends a value with exact Arrow type validation.
    ```
    irx_rb_api_append_utf8(self.handle, col, value)
    return none

  fn append_null(self, col: i32) -> none:
    ```
    title: append_null
    summary: Appends null only to a nullable field.
    ```
    irx_rb_api_append_null(self.handle, col)
    return none

  fn finish(self) -> RecordBatch:
    ```
    title: finish
    summary: Finishes equal-length columns and resets the builder for reuse.
    ```
    var result: RecordBatch = RecordBatch()
    irx_rb_api_builder_finish(self.handle, result.native_handle())
    return result


extern irx_rb_api_reader_csv(box: ArrowReaderHandle, path: str, delimiter: str, header: i32, block_size: i32) -> none
extern irx_rb_api_reader_csv_as(box: ArrowReaderHandle, path: str, schema: ArrowSchemaHandle, delimiter: str, header: i32, block_size: i32) -> none
extern irx_rb_api_writer_csv(box: ArrowWriterHandle, path: str, delimiter: str, header: i32) -> none

class IPCReader:
  ```
  title: IPCReader
  summary: Scoped owner of a native Arrow reader.
  ```
  @[private]
  handle: ArrowReaderHandle

  fn __init__(self) -> none:
    ```
    title: __init__
    summary: Creates one native owner.
    ```
    self.handle = irx_rb_api_reader_new()
    return none

  fn __del__(self) -> none:
    ```
    title: __del__
    summary: Releases the native box at the last class reference.
    ```
    irx_rb_api_reader_destroy(self.handle)
    return none

  fn close(self) -> none:
    ```
    title: close
    summary: Releases native resources idempotently; aliases observe closure.
    ```
    irx_rb_api_reader_close(self.handle)
    return none

  fn native_handle(self) -> ArrowReaderHandle:
    ```
    title: native_handle
    summary: Borrows the opaque handle for trusted native integrations only.
    ```
    return self.handle

  fn open_file(self, path: str) -> none:
    ```
    title: open_file
    summary: Opens Arrow IPC file format at a filesystem path.
    ```
    irx_rb_api_reader_file(self.handle, path)
    return none

  fn open_stream(self, path: str) -> none:
    ```
    title: open_stream
    summary: Opens Arrow IPC stream format at a filesystem path.
    ```
    irx_rb_api_reader_stream(self.handle, path)
    return none

  fn connect(self, host: str, port: i32, timeout_ms: i32 = 30000) -> none:
    ```
    title: connect
    summary: Connects to a numeric IP address for IPC streaming over TCP.
    ```
    irx_rb_api_reader_tcp(self.handle, host, port, timeout_ms)
    return none

  fn next(self) -> bool:
    ```
    title: next
    summary: Advances one batch; false means an orderly end, not an empty batch.
    ```
    return irx_rb_api_reader_next(self.handle) == 0

  fn batch(self) -> RecordBatch:
    ```
    title: batch
    summary: Returns an independently owned snapshot.
    ```
    var result: RecordBatch = RecordBatch()
    irx_rb_api_reader_batch(self.handle, result.native_handle())
    return result

  fn schema(self) -> Schema:
    ```
    title: schema
    summary: Returns an independently owned snapshot.
    ```
    var result: Schema = Schema()
    irx_rb_api_reader_schema(self.handle, result.native_handle())
    return result

  fn import_stream(self, address: i64) -> none:
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
  @[private]
  handle: ArrowWriterHandle

  fn __init__(self, schema: Schema) -> none:
    ```
    title: __init__
    summary: Creates one native owner.
    ```
    self.handle = irx_rb_api_writer_new(schema.native_handle())
    return none

  fn __del__(self) -> none:
    ```
    title: __del__
    summary: Releases the native box at the last class reference.
    ```
    irx_rb_api_writer_destroy(self.handle)
    return none

  fn close(self) -> none:
    ```
    title: close
    summary: Releases native resources idempotently; aliases observe closure.
    ```
    irx_rb_api_writer_close(self.handle)
    return none

  fn native_handle(self) -> ArrowWriterHandle:
    ```
    title: native_handle
    summary: Borrows the opaque handle for trusted native integrations only.
    ```
    return self.handle

  fn open_file(self, path: str) -> none:
    ```
    title: open_file
    summary: Opens Arrow IPC file format at a filesystem path.
    ```
    irx_rb_api_writer_file(self.handle, path)
    return none

  fn open_stream(self, path: str) -> none:
    ```
    title: open_stream
    summary: Opens Arrow IPC stream format at a filesystem path.
    ```
    irx_rb_api_writer_stream(self.handle, path)
    return none

  fn connect(self, host: str, port: i32, timeout_ms: i32 = 30000) -> none:
    ```
    title: connect
    summary: Connects to a numeric IP address for IPC streaming over TCP.
    ```
    irx_rb_api_writer_tcp(self.handle, host, port, timeout_ms)
    return none

  fn write(self, batch: RecordBatch) -> none:
    ```
    title: write
    summary: Writes one batch with exact schema validation.
    ```
    irx_rb_api_writer_write(self.handle, batch.native_handle())
    return none


class CSVReader:
  ```
  title: CSVReader
  summary: Scoped owner of a native Arrow reader.
  ```
  @[private]
  handle: ArrowReaderHandle

  fn __init__(self) -> none:
    ```
    title: __init__
    summary: Creates one native owner.
    ```
    self.handle = irx_rb_api_reader_new()
    return none

  fn __del__(self) -> none:
    ```
    title: __del__
    summary: Releases the native box at the last class reference.
    ```
    irx_rb_api_reader_destroy(self.handle)
    return none

  fn close(self) -> none:
    ```
    title: close
    summary: Releases native resources idempotently; aliases observe closure.
    ```
    irx_rb_api_reader_close(self.handle)
    return none

  fn native_handle(self) -> ArrowReaderHandle:
    ```
    title: native_handle
    summary: Borrows the opaque handle for trusted native integrations only.
    ```
    return self.handle

  fn open_file(self, path: str, delimiter: str = ",", header: bool = true, block_size: i32 = 1048576) -> none:
    ```
    title: open_file
    summary: Streams UTF-8 CSV with first-block inference and a frozen schema.
    ```
    irx_rb_api_reader_csv(self.handle, path, delimiter, cast(header, i32), block_size)
    return none

  fn open_file_as(self, path: str, schema: Schema, delimiter: str = ",", header: bool = true, block_size: i32 = 1048576) -> none:
    ```
    title: open_file_as
    summary: Streams CSV with exact column order and explicit physical types.
    ```
    irx_rb_api_reader_csv_as(self.handle, path, schema.native_handle(), delimiter, cast(header, i32), block_size)
    return none

  fn next(self) -> bool:
    ```
    title: next
    summary: Advances one batch; false means an orderly end, not an empty batch.
    ```
    return irx_rb_api_reader_next(self.handle) == 0

  fn batch(self) -> RecordBatch:
    ```
    title: batch
    summary: Returns an independently owned snapshot.
    ```
    var result: RecordBatch = RecordBatch()
    irx_rb_api_reader_batch(self.handle, result.native_handle())
    return result

  fn schema(self) -> Schema:
    ```
    title: schema
    summary: Returns an independently owned snapshot.
    ```
    var result: Schema = Schema()
    irx_rb_api_reader_schema(self.handle, result.native_handle())
    return result

class CSVWriter:
  ```
  title: CSVWriter
  summary: Scoped owner of a native Arrow writer.
  ```
  @[private]
  handle: ArrowWriterHandle

  fn __init__(self, schema: Schema) -> none:
    ```
    title: __init__
    summary: Creates one native owner.
    ```
    self.handle = irx_rb_api_writer_new(schema.native_handle())
    return none

  fn __del__(self) -> none:
    ```
    title: __del__
    summary: Releases the native box at the last class reference.
    ```
    irx_rb_api_writer_destroy(self.handle)
    return none

  fn close(self) -> none:
    ```
    title: close
    summary: Releases native resources idempotently; aliases observe closure.
    ```
    irx_rb_api_writer_close(self.handle)
    return none

  fn native_handle(self) -> ArrowWriterHandle:
    ```
    title: native_handle
    summary: Borrows the opaque handle for trusted native integrations only.
    ```
    return self.handle

  fn open_file(self, path: str, delimiter: str = ",", header: bool = true) -> none:
    ```
    title: open_file
    summary: Creates or truncates CSV after validating the schema and options.
    ```
    irx_rb_api_writer_csv(self.handle, path, delimiter, cast(header, i32))
    return none

  fn write(self, batch: RecordBatch) -> none:
    ```
    title: write
    summary: Writes one batch with exact schema validation.
    ```
    irx_rb_api_writer_write(self.handle, batch.native_handle())
    return none

extern irx_rb_api_parquet_new() -> ArrowParquetHandle
extern irx_rb_api_parquet_destroy(box: ArrowParquetHandle) -> none
extern irx_rb_api_parquet_close(box: ArrowParquetHandle) -> none
extern irx_rb_api_parquet_next(box: ArrowParquetHandle) -> i32
extern irx_rb_api_parquet_batch(box: ArrowParquetHandle, out: ArrowBatchHandle) -> none
extern irx_rb_api_parquet_schema(box: ArrowParquetHandle, out: ArrowSchemaHandle) -> none
extern irx_rb_api_parquet_write(box: ArrowParquetHandle, batch: ArrowBatchHandle) -> none
extern irx_rb_api_parquet_open_read(box: ArrowParquetHandle, path: str, batch_size: i64) -> none
extern irx_rb_api_parquet_open_read_as(box: ArrowParquetHandle, path: str, schema: ArrowSchemaHandle, batch_size: i64) -> none
extern irx_rb_api_parquet_open_write(box: ArrowParquetHandle, path: str, schema: ArrowSchemaHandle, compression: str, row_group_size: i64) -> none
extern irx_rb_api_csv_new() -> ArrowCsvHandle
extern irx_rb_api_csv_destroy(box: ArrowCsvHandle) -> none
extern irx_rb_api_csv_close(box: ArrowCsvHandle) -> none
extern irx_rb_api_csv_next(box: ArrowCsvHandle) -> i32
extern irx_rb_api_csv_batch(box: ArrowCsvHandle, out: ArrowBatchHandle) -> none
extern irx_rb_api_csv_schema(box: ArrowCsvHandle, out: ArrowSchemaHandle) -> none
extern irx_rb_api_csv_write(box: ArrowCsvHandle, batch: ArrowBatchHandle) -> none
extern irx_rb_api_csv_open_read(box: ArrowCsvHandle, path: str, delimiter: str, header: i32, block_size: i32) -> none
extern irx_rb_api_csv_open_read_as(box: ArrowCsvHandle, path: str, schema: ArrowSchemaHandle, delimiter: str, header: i32, block_size: i32) -> none
extern irx_rb_api_csv_open_write(box: ArrowCsvHandle, path: str, schema: ArrowSchemaHandle, delimiter: str, header: i32) -> none

class Parquet:
  ```
  title: Parquet
  summary: Scoped file owner with explicit read or write mode.
  ```
  @[private]
  handle: ArrowParquetHandle

  fn __init__(self) -> none:
    ```
    title: __init__
    summary: Creates a closed file owner.
    ```
    self.handle = irx_rb_api_parquet_new()
    return none

  fn __del__(self) -> none:
    ```
    title: __del__
    summary: Releases the session at the last class reference.
    ```
    irx_rb_api_parquet_destroy(self.handle)
    return none

  fn close(self) -> none:
    ```
    title: close
    summary: Closes the active session and checks finalization errors.
    ```
    irx_rb_api_parquet_close(self.handle)
    return none

  fn open_read(self, path: str, batch_size: i64 = 65536) -> none:
    ```
    title: open_read
    summary: Opens a closed owner for reading with the file schema.
    ```
    irx_rb_api_parquet_open_read(self.handle, path, batch_size)
    return none

  fn open_read_as(self, path: str, schema: Schema, batch_size: i64 = 65536) -> none:
    ```
    title: open_read_as
    summary: Opens with an exact expected schema.
    ```
    irx_rb_api_parquet_open_read_as(self.handle, path, schema.native_handle(), batch_size)
    return none

  fn open_write(self, path: str, schema: Schema, compression: str = "snappy", row_group_size: i64 = 1048576) -> none:
    ```
    title: open_write
    summary: Validates options and schema before creating or truncating output.
    ```
    irx_rb_api_parquet_open_write(self.handle, path, schema.native_handle(), compression, row_group_size)
    return none

  fn next(self) -> bool:
    ```
    title: next
    summary: Advances in read mode; false means EOF, not an empty batch.
    ```
    return irx_rb_api_parquet_next(self.handle) == 0

  fn batch(self) -> RecordBatch:
    ```
    title: batch
    summary: Returns an independently owned current batch in read mode.
    ```
    var result: RecordBatch = RecordBatch()
    irx_rb_api_parquet_batch(self.handle, result.native_handle())
    return result

  fn schema(self) -> Schema:
    ```
    title: schema
    summary: Returns an independent schema in either open mode.
    ```
    var result: Schema = Schema()
    irx_rb_api_parquet_schema(self.handle, result.native_handle())
    return result

  fn write(self, batch: RecordBatch) -> none:
    ```
    title: write
    summary: Writes an exact-schema batch in write mode.
    ```
    irx_rb_api_parquet_write(self.handle, batch.native_handle())
    return none

class CSV:
  ```
  title: CSV
  summary: Scoped file owner with explicit read or write mode.
  ```
  @[private]
  handle: ArrowCsvHandle

  fn __init__(self) -> none:
    ```
    title: __init__
    summary: Creates a closed file owner.
    ```
    self.handle = irx_rb_api_csv_new()
    return none

  fn __del__(self) -> none:
    ```
    title: __del__
    summary: Releases the session at the last class reference.
    ```
    irx_rb_api_csv_destroy(self.handle)
    return none

  fn close(self) -> none:
    ```
    title: close
    summary: Closes the active session and checks finalization errors.
    ```
    irx_rb_api_csv_close(self.handle)
    return none

  fn open_read(self, path: str, delimiter: str = ",", header: bool = true, block_size: i32 = 1048576) -> none:
    ```
    title: open_read
    summary: Opens a closed owner for reading with the file schema.
    ```
    irx_rb_api_csv_open_read(self.handle, path, delimiter, cast(header, i32), block_size)
    return none

  fn open_read_as(self, path: str, schema: Schema, delimiter: str = ",", header: bool = true, block_size: i32 = 1048576) -> none:
    ```
    title: open_read_as
    summary: Parses text using explicit physical column types.
    ```
    irx_rb_api_csv_open_read_as(self.handle, path, schema.native_handle(), delimiter, cast(header, i32), block_size)
    return none

  fn open_write(self, path: str, schema: Schema, delimiter: str = ",", header: bool = true) -> none:
    ```
    title: open_write
    summary: Validates options and schema before creating or truncating output.
    ```
    irx_rb_api_csv_open_write(self.handle, path, schema.native_handle(), delimiter, cast(header, i32))
    return none

  fn next(self) -> bool:
    ```
    title: next
    summary: Advances in read mode; false means EOF, not an empty batch.
    ```
    return irx_rb_api_csv_next(self.handle) == 0

  fn batch(self) -> RecordBatch:
    ```
    title: batch
    summary: Returns an independently owned current batch in read mode.
    ```
    var result: RecordBatch = RecordBatch()
    irx_rb_api_csv_batch(self.handle, result.native_handle())
    return result

  fn schema(self) -> Schema:
    ```
    title: schema
    summary: Returns an independent schema in either open mode.
    ```
    var result: Schema = Schema()
    irx_rb_api_csv_schema(self.handle, result.native_handle())
    return result

  fn write(self, batch: RecordBatch) -> none:
    ```
    title: write
    summary: Writes an exact-schema batch in write mode.
    ```
    irx_rb_api_csv_write(self.handle, batch.native_handle())
    return none
