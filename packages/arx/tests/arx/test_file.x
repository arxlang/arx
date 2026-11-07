```
title: Compiled public File regression
summary: Verifies the builtin class, factory adapter, aliases, and lowercase type.
```

make_file: fn(path: str) -> File:
  ```
  title: make_file
  ```
  return File(file=path, mode="w", encoding="utf-8")

test_file: fn() -> none:
  ```
  title: test_file
  ```
  output: File = make_file("file-class-test.txt")
  alias: file = output
  assert output == alias
  assert alias.write("hello") == 5
  alias.close()
  output.close()
  source: file = open("file-class-test.txt")
  assert source.read() == "hello"
