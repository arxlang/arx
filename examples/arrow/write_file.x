```
title: Arx to PyArrow IPC file
summary: Compile and run in the directory where arx.arrow should be written.
```
import IPCWriter from stdlib.arrow
import make_batch from data

fn main() -> i32:
  ```
  title: main
  summary: Writes a real Arrow IPC file without Python serialization.
  ```
  var writer: IPCWriter = IPCWriter(make_batch().schema())
  writer.open_file("arx.arrow")
  writer.write(make_batch())
  writer.close()
  return 0
