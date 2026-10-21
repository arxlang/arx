```
title: Bidirectional Arrow IPC over TCP
summary: A Python peer listens; each Arx function connects as a client.
```
import (IPCReader, IPCWriter) from stdlib.arrow
import (make_batch, verify) from data

fn send(host: str, port: i32) -> i32:
  ```
  title: send
  summary: Sends two batches and an explicit Arrow stream end marker.
  ```
  var writer: IPCWriter = IPCWriter(make_batch().schema())
  writer.connect(host, port)
  writer.write(make_batch())
  writer.write(make_batch())
  writer.close()
  return 0

fn receive(host: str, port: i32) -> i32:
  ```
  title: receive
  summary: Pulls and verifies batches without buffering the entire stream.
  ```
  var reader: IPCReader = IPCReader()
  reader.connect(host, port)
  var count: i32 = 0
  while reader.next():
    verify(reader.batch())
    count = count + 1
  assert count == 2
  return 0
