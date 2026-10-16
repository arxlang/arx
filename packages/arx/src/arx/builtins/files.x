```
title: Public native-backed text file class
summary: Construction is supplied by the compiler; fields have normal ownership.
```

class File:
  ```
  title: File
  summary: Owns one native UTF-8 text stream shared by its object references.
  ```
  @[private]
  handle: NativeFileHandle

  fn read(self) -> str:
    ```
    title: read
    summary: Returns all remaining text as an independent owned string.
    ```
    return self.handle.read()

  fn write(self, text: str) -> i64:
    ```
    title: write
    summary: Writes UTF-8 text and returns its Unicode character count.
    ```
    return self.handle.write(text)

  fn flush(self) -> none:
    ```
    title: flush
    summary: Checks buffered writes without promising durable storage.
    ```
    self.handle.flush()
    return none

  fn close(self) -> none:
    ```
    title: close
    summary: Closes the stream idempotently without freeing its owned wrapper.
    ```
    self.handle.close()
    return none
