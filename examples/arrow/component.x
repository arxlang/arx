```
title: Arx-backed C Data and C Stream producer and consumer
summary: Host pointers are trusted addresses of caller-owned standard C structs.
```
import (RecordBatch, IPCReader) from stdlib.arrow
import (make_batch, verify) from data

fn produce_stream(address: i64) -> i32:
  ```
  title: produce_stream
  summary: The exported batch remains valid after all Arx locals are destroyed.
  ```
  return make_batch().export_stream(address)

fn produce_array(array: i64, schema: i64) -> i32:
  ```
  title: produce_array
  summary: Returns a C Data pair with independent release callbacks.
  ```
  return make_batch().export_c(array, schema)

fn consume_stream(address: i64) -> i32:
  ```
  title: consume_stream
  summary: Takes ownership of the supplied stream and validates one batch.
  ```
  var reader: IPCReader = IPCReader()
  reader.import_stream(address)
  assert reader.next()
  verify(reader.batch())
  assert reader.next() == false
  return 0

fn consume_array(array: i64, schema: i64) -> i32:
  ```
  title: consume_array
  summary: Moves the C Data pair and checks its contents without IPC.
  ```
  var batch: RecordBatch = RecordBatch()
  batch.import_c(array, schema)
  verify(batch)
  return 0

fn receive_tcp(host: str, port: i32) -> i32:
  ```
  title: receive_tcp
  summary: Native embedding boundary for a streaming TCP consumer.
  ```
  var reader: IPCReader = IPCReader()
  reader.connect(host, port, timeout_ms=1000)
  while reader.next():
    verify(reader.batch())
  return 0
