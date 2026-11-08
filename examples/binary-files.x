```
title: Bounded binary file IO without text conversion
summary: Creates binary-output.dat, replacing any existing content.
```

fn read_prefix(path: str, size: i64) -> bytes:
  ```
  title: Return owned bytes that outlive the local File.
  ```
  source: File = open(path, "rb")
  data: bytes = source.read_bytes(size)
  return data

fn main() -> i32:
  ```
  title: Round-trip every byte, then append an independent copy.
  ```
  data: bytes = bytes(range(0, 256))
  output: File = open("binary-output.dat", "wb")
  assert output.write_bytes(bytes()) == 0
  assert output.write_bytes(data) == 256
  output.flush()
  output.close()
  loaded: bytes = read_prefix("binary-output.dat", 300)
  assert len(loaded) == 256
  index: i64 = 0
  for value in loaded:
    assert value == index
    assert value == data[index]
    index = index + 1
  source: File = open("binary-output.dat", "rb")
  assert len(source.read_bytes(size=0)) == 0
  prefix: bytes = source.read_bytes(13)
  assert len(prefix) == 13
  assert source.read_bytes(1)[0] == 13
  assert len(source.read_bytes(300)) == 242
  assert len(source.read_bytes(1)) == 0
  alias: File = source
  alias.close()
  try:
    source.read_bytes(0)
    return 1
  except ValueError:
    assert len(prefix) == 13
  assert prefix[12] == 12
  empty: File = open("binary-empty.dat", "wb")
  assert empty.write_bytes(bytes()) == 0
  empty.close()
  empty = open("binary-empty.dat", "rb")
  assert len(empty.read_bytes(1)) == 0
  copied: bytes = bytes(loaded)
  loaded = bytes([])
  assert len(loaded) == 0
  mode: str = "ab"
  output = File("binary-output.dat", mode)
  assert output.write_bytes(data=copied) == 256
  output.close()
  return 0
