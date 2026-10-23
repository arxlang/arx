```
title: CSV files
summary: Native Arrow-backed file I/O and scoped streaming.
```

import (Schema, RecordBatch) from stdlib.arrow

extern irx_rb_api_csv_frame(box: ArrowCsvHandle) -> dataframe[...]
extern irx_rb_api_csv_write_frame(box: ArrowCsvHandle, frame: dataframe[...]) -> none
extern read_csv(path: str) -> dataframe[...]
extern write_csv(frame: dataframe[...], path: str) -> none

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

class CSVStream:
  ```
  title: CSVStream
  summary: Scoped owner for incremental reading or writing in one active mode.
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

  fn frame(self) -> dataframe[...]:
    ```
    title: Return an independently owned DataFrame for the current batch.
    ```
    return irx_rb_api_csv_frame(self.handle)

  fn write(self, frame: dataframe[...]) -> none:
    ```
    title: Write every chunk without consuming or mutating the DataFrame.
    ```
    irx_rb_api_csv_write_frame(self.handle, frame)
    return none
