```
title: Public native-backed text and binary file class
summary: Construction is supplied by the compiler; fields have normal ownership.
```

class File:
  ```
  title: File
  summary: Owns one native text or binary stream shared by its object references.
  ```
  handle: private :: NativeFileHandle

  fn read(self) -> str:
    ```
    title: read
    summary: Requires readable text mode; returns all remaining text independently.
    ```
    return self.handle.read()

  fn write(self, text: str) -> i64:
    ```
    title: write
    summary: Requires writable text mode; writes UTF-8 and counts Unicode characters.
    ```
    return self.handle.write(text)

  fn read_bytes(self, size: i64) -> bytes:
    ```
    title: read_bytes
    summary: >-
      Reads at most size bytes into independent storage; size must be nonnegative.
      Binary readable mode is required even for zero, which does not advance.
      Empty means EOF. No decoding or newline conversion occurs.
    ```
    return self.handle.read_bytes(size)

  fn write_bytes(self, data: bytes) -> i64:
    ```
    title: write_bytes
    summary: >-
      Borrows data and returns its byte count only after writing all bytes.
      Requires writable binary mode. Errors may leave partial external writes;
      no rollback, atomic publication, or durability is promised.
    ```
    return self.handle.write_bytes(data)

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
