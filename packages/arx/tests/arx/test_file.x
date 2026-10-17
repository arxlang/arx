```
title: Compiled public File regression
summary: Verifies the builtin class, factory adapter, aliases, and lowercase type.
```

fn make_file(path: str) -> File:
  ```
  title: make_file
  ```
  return File(file=path, mode="w", encoding="utf-8")

fn test_file() -> none:
  ```
  title: test_file
  ```
  var output: File = make_file("file-class-test.txt")
  var alias: file = output
  assert output == alias
  assert alias.write("hello") == 5
  alias.close()
  output.close()
  var source: file = open("file-class-test.txt")
  assert source.read() == "hello"
