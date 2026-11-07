```
title: Parquet files
summary: Native Arrow-backed file I/O and scoped streaming.
```

import (Schema, RecordBatch) from stdlib.arrow

irx_rb_api_parquet_frame: extern :: fn(box: ArrowParquetHandle) -> dataframe[...]
irx_rb_api_parquet_write_frame: extern :: fn(box: ArrowParquetHandle, frame: dataframe[...]) -> none
read_parquet: extern :: fn(path: str) -> dataframe[...]
write_parquet: extern :: fn(frame: dataframe[...], path: str) -> none

irx_rb_api_parquet_new: extern :: fn() -> ArrowParquetHandle
irx_rb_api_parquet_destroy: extern :: fn(box: ArrowParquetHandle) -> none
irx_rb_api_parquet_close: extern :: fn(box: ArrowParquetHandle) -> none
irx_rb_api_parquet_next: extern :: fn(box: ArrowParquetHandle) -> i32
irx_rb_api_parquet_batch: extern :: fn(box: ArrowParquetHandle, out: ArrowBatchHandle) -> none
irx_rb_api_parquet_schema: extern :: fn(box: ArrowParquetHandle, out: ArrowSchemaHandle) -> none
irx_rb_api_parquet_write: extern :: fn(box: ArrowParquetHandle, batch: ArrowBatchHandle) -> none
irx_rb_api_parquet_open_read: extern :: fn(box: ArrowParquetHandle, path: str, batch_size: i64) -> none
irx_rb_api_parquet_open_read_as: extern :: fn(box: ArrowParquetHandle, path: str, schema: ArrowSchemaHandle, batch_size: i64) -> none
irx_rb_api_parquet_open_write: extern :: fn(box: ArrowParquetHandle, path: str, schema: ArrowSchemaHandle, compression: str, row_group_size: i64) -> none
irx_rb_api_options_new: extern :: fn() -> ArrowOptionsHandle
irx_rb_api_options_destroy: extern :: fn(box: ArrowOptionsHandle) -> none
irx_rb_api_options_int: extern :: fn(box: ArrowOptionsHandle, name: str, value: i64) -> none
irx_rb_api_options_text: extern :: fn(box: ArrowOptionsHandle, name: str, value: str) -> none
irx_rb_api_parquet_read_options: extern :: fn(box: ArrowParquetHandle, path: str, options: ArrowOptionsHandle) -> none
irx_rb_api_parquet_write_options: extern :: fn(box: ArrowParquetHandle, path: str, schema: ArrowSchemaHandle, options: ArrowOptionsHandle) -> none

where: extern :: fn(column: str, operation: str) -> ParquetFilter
irx_rb_api_options_filters: extern :: fn(box: ArrowOptionsHandle, filters: ArrowOptionsHandle) -> none
irx_rb_api_filter_i64: extern :: fn(out: ArrowOptionsHandle, source: ArrowOptionsHandle, column: str, operation: str, value: i64) -> none
irx_rb_api_filter_f64: extern :: fn(out: ArrowOptionsHandle, source: ArrowOptionsHandle, column: str, operation: str, value: f64) -> none
irx_rb_api_filter_bool: extern :: fn(out: ArrowOptionsHandle, source: ArrowOptionsHandle, column: str, operation: str, value: i32) -> none
irx_rb_api_filter_text: extern :: fn(out: ArrowOptionsHandle, source: ArrowOptionsHandle, column: str, operation: str, value: str) -> none
irx_rb_api_filter_null: extern :: fn(out: ArrowOptionsHandle, source: ArrowOptionsHandle, column: str, operation: str) -> none

class ParquetFilter:
  ```
  title: Independently owned typed AND predicate group.
  ```
  handle: private :: ArrowOptionsHandle

  __init__: fn(self) -> none:
    ```
    title: Create an empty predicate group.
    ```
    self.handle = irx_rb_api_options_new()
    return none

  __del__: fn(self) -> none:
    ```
    title: Release the predicate owner.
    ```
    irx_rb_api_options_destroy(self.handle)
    return none

  native_handle: fn(self) -> ArrowOptionsHandle:
    ```
    title: Borrow the handle for trusted operations.
    ```
    return self.handle

  and_where: fn(self, column: str, operation: str, value: i8) -> ParquetFilter:
    ```
    title: Compose a predicate using a lossless i8 promotion.
    ```
    return self.and_where(column, operation, cast(value, i64))

  and_where: fn(self, column: str, operation: str, value: i16) -> ParquetFilter:
    ```
    title: Compose a predicate using a lossless i16 promotion.
    ```
    return self.and_where(column, operation, cast(value, i64))

  and_where: fn(self, column: str, operation: str, value: i32) -> ParquetFilter:
    ```
    title: Compose a predicate using a lossless i32 promotion.
    ```
    return self.and_where(column, operation, cast(value, i64))

  and_where: fn(self, column: str, operation: str, value: f32) -> ParquetFilter:
    ```
    title: Compose a predicate using a lossless f32 promotion.
    ```
    return self.and_where(column, operation, cast(value, f64))

  and_where: fn(self, column: str, operation: str, value: i64) -> ParquetFilter:
    ```
    title: Return a new group with a checked i64 predicate.
    ```
    result: ParquetFilter = ParquetFilter()
    irx_rb_api_filter_i64(result.handle, self.handle, column, operation, value)
    return result

  and_where: fn(self, column: str, operation: str, value: f64) -> ParquetFilter:
    ```
    title: Return a new group with a checked f64 predicate.
    ```
    result: ParquetFilter = ParquetFilter()
    irx_rb_api_filter_f64(result.handle, self.handle, column, operation, value)
    return result

  and_where: fn(self, column: str, operation: str, value: bool) -> ParquetFilter:
    ```
    title: Return a new group with a checked bool predicate.
    ```
    result: ParquetFilter = ParquetFilter()
    irx_rb_api_filter_bool(result.handle, self.handle, column, operation, cast(value, i32))
    return result

  and_where: fn(self, column: str, operation: str, value: str) -> ParquetFilter:
    ```
    title: Return a new group with a checked text predicate.
    ```
    result: ParquetFilter = ParquetFilter()
    irx_rb_api_filter_text(result.handle, self.handle, column, operation, value)
    return result

  and_where: fn(self, column: str, operation: str) -> ParquetFilter:
    ```
    title: Return a new group with a checked null predicate.
    ```
    result: ParquetFilter = ParquetFilter()
    irx_rb_api_filter_null(result.handle, self.handle, column, operation)
    return result

class ParquetOptions:
  ```
  title: ParquetOptions
  summary: Checked configuration copied at open; aliases share this builder.
  ```
  handle: private :: ArrowOptionsHandle

  __init__: fn(self, batch_size: i64 = 65536, row_group_size: i64 = 1048576, data_page_size: i64 = 1048576, compression: str = "snappy", use_threads: bool = false, pre_buffer: bool = false, dataset: bool = false, hive: bool = false, unify: bool = false, normalize: bool = false, atomic: bool = false, durable: bool = false, reconstruct: bool = false, append: bool = false) -> none:
    ```
    title: Create checked options using named scalar settings.
    ```
    self.handle = irx_rb_api_options_new()
    irx_rb_api_options_int(self.handle, "batch_size", batch_size)
    irx_rb_api_options_int(self.handle, "row_group_size", row_group_size)
    irx_rb_api_options_int(self.handle, "data_page_size", data_page_size)
    irx_rb_api_options_text(self.handle, "compression", compression)
    irx_rb_api_options_int(self.handle, "use_threads", cast(use_threads, i64))
    irx_rb_api_options_int(self.handle, "pre_buffer", cast(pre_buffer, i64))
    irx_rb_api_options_int(self.handle, "dataset", cast(dataset, i64))
    irx_rb_api_options_int(self.handle, "hive", cast(hive, i64))
    irx_rb_api_options_int(self.handle, "unify", cast(unify, i64))
    irx_rb_api_options_int(self.handle, "normalize", cast(normalize, i64))
    irx_rb_api_options_int(self.handle, "atomic", cast(atomic, i64))
    irx_rb_api_options_int(self.handle, "durable", cast(durable, i64))
    irx_rb_api_options_int(self.handle, "reconstruct", cast(reconstruct, i64))
    irx_rb_api_options_int(self.handle, "append", cast(append, i64))
    return none

  __del__: fn(self) -> none:
    ```
    title: Release the native options owner.
    ```
    irx_rb_api_options_destroy(self.handle)
    return none

  native_handle: fn(self) -> ArrowOptionsHandle:
    ```
    title: Borrow options for trusted native calls.
    ```
    return self.handle

  set_int: fn(self, name: str, value: i64) -> none:
    ```
    title: Set a checked size, flag, compression level or row_group index.
    ```
    irx_rb_api_options_int(self.handle, name, value)
    return none

  set_text: fn(self, name: str, value: str) -> none:
    ```
    title: Set compression or add a projected column.
    ```
    irx_rb_api_options_text(self.handle, name, value)
    return none

  encryption_key_hex: fn(self, key: str) -> none:
    ```
    title: Configure a caller-supplied AES footer key without logging key bytes.
    summary: Use runtime-provided secrets, not keys committed in source code.
    ```
    irx_rb_api_options_text(self.handle, "encryption_key_hex", key)
    return none

  set_filters: fn(self, filters: ParquetFilter) -> none:
    ```
    title: Copy a typed predicate group without sharing mutable state.
    ```
    irx_rb_api_options_filters(self.handle, filters.native_handle())
    return none


class ParquetStream:
  ```
  title: ParquetStream
  summary: Scoped owner for incremental reading or writing in one active mode.
  ```
  handle: private :: ArrowParquetHandle

  __init__: fn(self) -> none:
    ```
    title: __init__
    summary: Creates a closed file owner.
    ```
    self.handle = irx_rb_api_parquet_new()
    return none

  __del__: fn(self) -> none:
    ```
    title: __del__
    summary: Releases the session at the last class reference.
    ```
    irx_rb_api_parquet_destroy(self.handle)
    return none

  close: fn(self) -> none:
    ```
    title: close
    summary: Closes the active session and checks finalization errors.
    ```
    irx_rb_api_parquet_close(self.handle)
    return none

  open_read: fn(self, path: str, batch_size: i64 = 65536) -> none:
    ```
    title: open_read
    summary: Opens a closed owner for reading with the file schema.
    ```
    irx_rb_api_parquet_open_read(self.handle, path, batch_size)
    return none

  open_read_as: fn(self, path: str, schema: Schema, batch_size: i64 = 65536) -> none:
    ```
    title: open_read_as
    summary: Opens with an exact expected schema.
    ```
    irx_rb_api_parquet_open_read_as(self.handle, path, schema.native_handle(), batch_size)
    return none

  open_write: fn(self, path: str, schema: Schema, compression: str = "snappy", row_group_size: i64 = 1048576) -> none:
    ```
    title: open_write
    summary: Validates options and schema before creating or truncating output.
    ```
    irx_rb_api_parquet_open_write(self.handle, path, schema.native_handle(), compression, row_group_size)
    return none

  next: fn(self) -> bool:
    ```
    title: next
    summary: Advances in read mode; false means EOF, not an empty batch.
    ```
    return irx_rb_api_parquet_next(self.handle) == 0

  batch: fn(self) -> RecordBatch:
    ```
    title: batch
    summary: Returns an independently owned current batch in read mode.
    ```
    result: RecordBatch = RecordBatch()
    irx_rb_api_parquet_batch(self.handle, result.native_handle())
    return result

  schema: fn(self) -> Schema:
    ```
    title: schema
    summary: Returns an independent schema in either open mode.
    ```
    result: Schema = Schema()
    irx_rb_api_parquet_schema(self.handle, result.native_handle())
    return result

  write: fn(self, batch: RecordBatch) -> none:
    ```
    title: write
    summary: Writes an exact-schema batch in write mode.
    ```
    irx_rb_api_parquet_write(self.handle, batch.native_handle())
    return none

  open_read_options: fn(self, path: str, options: ParquetOptions) -> none:
    ```
    title: Open a configured file or dataset scan.
    ```
    irx_rb_api_parquet_read_options(self.handle, path, options.native_handle())
    return none

  open_write_options: fn(self, path: str, schema: Schema, options: ParquetOptions) -> none:
    ```
    title: Open configured output with checked normalization and commit policy.
    ```
    irx_rb_api_parquet_write_options(self.handle, path, schema.native_handle(), options.native_handle())
    return none

  frame: fn(self) -> dataframe[...]:
    ```
    title: Return an independently owned DataFrame for the current batch.
    ```
    return irx_rb_api_parquet_frame(self.handle)

  write: fn(self, frame: dataframe[...]) -> none:
    ```
    title: Write every chunk without consuming or mutating the DataFrame.
    ```
    irx_rb_api_parquet_write_frame(self.handle, frame)
    return none
