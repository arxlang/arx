# Text File I/O

`open` provides a deliberately small, native, POSIX text-file interface. It is
available without an import and uses C stdio, not Python execution or Arrow.

```text
open(file, mode="r", buffering=-1, encoding=none, errors=none,
     newline=none, closefd=true, opener=none) -> file
```

| Parameter   | Supported values                                                 |
| ----------- | ---------------------------------------------------------------- |
| `file`      | String path, relative to the running program's working directory |
| `mode`      | `"r"`, `"w"`, `"a"`, `"rt"`, `"wt"`, `"at"`; default `"r"`       |
| `buffering` | Constant `-1` (C stdio defaults)                                 |
| `encoding`  | `none` or constant `"utf-8"`                                     |
| `errors`    | `none` or constant `"strict"`                                    |
| `newline`   | `none`                                                           |
| `closefd`   | Constant `true`                                                  |
| `opener`    | `none`                                                           |

The first two arguments may be runtime string expressions. All other arguments
must be supported constants. Positional arguments and keywords may be mixed;
keywords are currently supported only for this builtin. Invalid options are
rejected before compilation can execute file I/O; dynamic modes are checked
before opening or truncating a path.

Reading requires an existing file. Writing creates or truncates it. Appending
creates it if necessary and writes at the end. No binary/update/exclusive modes,
file descriptors, callbacks, or custom buffering are supported yet.

## Example

Run this in a scratch directory: the example creates/truncates `message.txt`.

````arx
```
title: Native text file example
```
fn main() -> i32:
  ```
  title: main
  ```
  var output: file = open("message.txt", mode="w", encoding="utf-8")
  assert output.write("hello\n") == 6
  output.close()
  var source: file = open(file="message.txt")
  var text: str = source.read()
  source.close()
  print(text)
  return 0
````

## Methods and lifetime

- `read()` returns all remaining text, or `""` at EOF. It has no size argument.
  CRLF and CR become LF. Malformed UTF-8 and embedded NUL are rejected; Arx's
  current C-string ABI cannot represent file text containing NUL safely.
- `write(text)` returns an `i64` Unicode character count, not UTF-8 byte count.
- `flush()` checks buffered writes; it does not guarantee durable storage.
- `close()` is idempotent. Other operations on a closed file fail.

Each `file` local must be initialized directly with `open`. It is one owner, not
an integer descriptor or a freely copyable pointer. Copies, reassignment, file
parameters/returns, fields, containers, globals, and generator storage are
rejected. Locals and discarded temporaries are released on ordinary scope exit
and function return. Explicitly closing a stream does not double-free its
wrapper when that automatic release occurs. Read results own their memory
independently of the stream and may use the existing string return/cleanup
rules.

I/O failures report `ARX-RUNTIME-FILE-001` and exit nonzero. Fatal errors do not
unwind caller frames or provide catchable exceptions; explicit close/flush are
recommended where write errors must be observed before later work. `with`,
iteration, seek/tell, and shared ownership are not implemented.

This is a Python-like subset: parameter names/order/default spellings follow
[Python's interface](https://docs.python.org/3.14/library/functions.html#open),
but UTF-8 replaces locale-dependent encoding, and NUL-containing text and many
optional settings are intentionally unsupported. Existing user/imported
functions named `open` retain normal positional-call resolution. A local
non-callable `open` shadows the builtin and produces an error when called.
