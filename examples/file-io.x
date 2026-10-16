```
title: Native text file I/O
summary: Creates file-io-example.txt in the running program's working directory.
```
fn main() -> i32:
  ```
  title: main
  summary: Writes UTF-8 text and reads it back with explicit close.
  ```
  var output: File = File("file-io-example.txt", mode="w")
  assert output.write("hello\n") == 6
  output.close()
  var source: file = open(file="file-io-example.txt")
  var text: str = source.read()
  source.close()
  assert text == "hello\n"
  return 0
