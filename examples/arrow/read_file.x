```
title: PyArrow to Arx IPC file
summary: Compile and run beside a Python-produced python.arrow file.
```
import IPCReader from stdlib.arrow
import verify from data

fn main() -> i32:
  ```
  title: main
  summary: Checks the Python-produced schema and values in compiled code.
  ```
  var reader: IPCReader = IPCReader()
  reader.open_file("python.arrow")
  assert reader.next()
  verify(reader.batch())
  assert reader.next() == false
  return 0
