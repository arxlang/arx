```
title: CSV files
summary: Native Arrow-backed file I/O and scoped streaming.
```

import (Schema, RecordBatch) from stdlib.arrow

irx_rb_api_csv_frame: extern :: fn(box: ArrowCsvHandle) -> dataframe[...]
irx_rb_api_csv_write_frame: extern :: fn(box: ArrowCsvHandle, frame: dataframe[...]) -> none
read_csv: extern :: fn(path: str) -> dataframe[...]
write_csv: extern :: fn(frame: dataframe[...], path: str) -> none

irx_rb_api_csv_new: extern :: fn() -> ArrowCsvHandle
irx_rb_api_csv_destroy: extern :: fn(box: ArrowCsvHandle) -> none
irx_rb_api_csv_close: extern :: fn(box: ArrowCsvHandle) -> none
irx_rb_api_csv_next: extern :: fn(box: ArrowCsvHandle) -> i32
irx_rb_api_csv_batch: extern :: fn(box: ArrowCsvHandle, out: ArrowBatchHandle) -> none
irx_rb_api_csv_schema: extern :: fn(box: ArrowCsvHandle, out: ArrowSchemaHandle) -> none
irx_rb_api_csv_write: extern :: fn(box: ArrowCsvHandle, batch: ArrowBatchHandle) -> none
irx_rb_api_csv_open_read: extern :: fn(box: ArrowCsvHandle, path: str, delimiter: str, header: i32, block_size: i32) -> none
irx_rb_api_csv_open_read_as: extern :: fn(box: ArrowCsvHandle, path: str, schema: ArrowSchemaHandle, delimiter: str, header: i32, block_size: i32) -> none
irx_rb_api_csv_open_write: extern :: fn(box: ArrowCsvHandle, path: str, schema: ArrowSchemaHandle, delimiter: str, header: i32) -> none

class CSVStream:
  ```
  title: CSVStream
  summary: Scoped owner for incremental reading or writing in one active mode.
  ```
  handle: private :: ArrowCsvHandle

  __init__: fn(self) -> none:
    ```
    title: __init__
    summary: Creates a closed file owner.
    ```
    self.handle = irx_rb_api_csv_new()
    return none

  __del__: fn(self) -> none:
    ```
    title: __del__
    summary: Releases the session at the last class reference.
    ```
    irx_rb_api_csv_destroy(self.handle)
    return none

  close: fn(self) -> none:
    ```
    title: close
    summary: Closes the active session and checks finalization errors.
    ```
    irx_rb_api_csv_close(self.handle)
    return none

  open_read: fn(self, path: str, delimiter: str = ",", header: bool = true, block_size: i32 = 1048576) -> none:
    ```
    title: open_read
    summary: Opens a closed owner for reading with the file schema.
    ```
    irx_rb_api_csv_open_read(self.handle, path, delimiter, cast(header, i32), block_size)
    return none

  open_read_as: fn(self, path: str, schema: Schema, delimiter: str = ",", header: bool = true, block_size: i32 = 1048576) -> none:
    ```
    title: open_read_as
    summary: Parses text using explicit physical column types.
    ```
    irx_rb_api_csv_open_read_as(self.handle, path, schema.native_handle(), delimiter, cast(header, i32), block_size)
    return none

  open_write: fn(self, path: str, schema: Schema, delimiter: str = ",", header: bool = true) -> none:
    ```
    title: open_write
    summary: Validates options and schema before creating or truncating output.
    ```
    irx_rb_api_csv_open_write(self.handle, path, schema.native_handle(), delimiter, cast(header, i32))
    return none

  next: fn(self) -> bool:
    ```
    title: next
    summary: Advances in read mode; false means EOF, not an empty batch.
    ```
    return irx_rb_api_csv_next(self.handle) == 0

  batch: fn(self) -> RecordBatch:
    ```
    title: batch
    summary: Returns an independently owned current batch in read mode.
    ```
    result: RecordBatch = RecordBatch()
    irx_rb_api_csv_batch(self.handle, result.native_handle())
    return result

  schema: fn(self) -> Schema:
    ```
    title: schema
    summary: Returns an independent schema in either open mode.
    ```
    result: Schema = Schema()
    irx_rb_api_csv_schema(self.handle, result.native_handle())
    return result

  write: fn(self, batch: RecordBatch) -> none:
    ```
    title: write
    summary: Writes an exact-schema batch in write mode.
    ```
    irx_rb_api_csv_write(self.handle, batch.native_handle())
    return none

  frame: fn(self) -> dataframe[...]:
    ```
    title: Return an independently owned DataFrame for the current batch.
    ```
    return irx_rb_api_csv_frame(self.handle)

  write: fn(self, frame: dataframe[...]) -> none:
    ```
    title: Write every chunk without consuming or mutating the DataFrame.
    ```
    irx_rb_api_csv_write_frame(self.handle, frame)
    return none
