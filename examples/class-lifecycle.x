```
title: Class lifecycle and owned text files
summary: Constructor keywords, reference aliases, and automatic field release.
```

class TextLog:
  ```
  title: TextLog
  summary: Owns its path string and native file stream.
  ```
  path: str = ""
  handle: File

  __init__: fn(self, path: str) -> none:
    ```
    title: __init__
    summary: Copies the path and opens exactly one owned stream.
    ```
    self.path = path
    self.handle = File(self.path, mode="w")
    return none

  __del__: fn(self) -> none:
    ```
    title: __del__
    summary: Observes fields before compiler-generated field cleanup.
    ```
    print(self.path)
    return none

  write: fn(self, text: str) -> none:
    ```
    title: write
    summary: Writes text through a borrowed receiver.
    ```
    self.handle.write(text)
    return none

write_log: fn() -> none:
  ```
  title: write_log
  summary: Both aliases share one object and one final destructor call.
  ```
  log: TextLog = TextLog(path="class-lifecycle.txt")
  alias: TextLog = log
  alias.write("hello\n")
  return none

main: fn() -> i32:
  ```
  title: main
  summary: Reads text after the final class reference has closed the writer.
  ```
  write_log()
  input: file = open("class-lifecycle.txt")
  assert input.read() == "hello\n"
  return 0
