# File I/O

`File` is a builtin reference-managed class for a deliberately small native,
POSIX text and binary file interface. `open(...)` is a compiler-backed factory
adapter to `File(...)`: both create the same class object through one checked
construction path. Both are available without an import and use C stdio, not
Python or Arrow. Lowercase `file` remains a compatibility spelling for the
builtin `File` type.

The default is a strict UTF-8 text read. Use `mode="w"` to create/truncate or
`mode="a"` to append. Only the path and mode can be runtime strings; other
Python-shaped settings accept only the implemented default profile. Nondefault
buffering, encodings, error policies, newline handling, descriptors, and openers
are rejected rather than ignored. Options are checked before I/O; a dynamic mode
is checked before opening or truncating a path.

Paths are relative to the running program's working directory, not its source
file.

Reading requires an existing file. Writing creates or truncates it. Appending
creates it if necessary and writes at the end. Update/exclusive modes, file
descriptors, callbacks, and custom buffering are unsupported. Binary modes are
`rb`, `wb`, and `ab`; non-`none` encoding, errors, or newline options are
rejected before creating/truncating a path, including when the mode is dynamic.

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
  with open("message.txt", mode="w", encoding="utf-8") as output:
    assert output.write("hello\n") == 6
  with open(file="message.txt") as source:
    print(source.read())
  return 0
````

## Checked resource scopes

Inside a function, `with manager [as name]:` evaluates one manager once. A
successful `__enter__` is followed by exactly one `__exit__` on fallthrough,
return, loop transfer, or failure. Failed acquisition does not call exit. The
optional name is scoped to the body and cannot be rebound; it does not freeze
the referenced object. Multiple managers and destructuring targets are
unsupported; nest scopes instead.

File entry returns the same reference and rejects an already-closed stream
without reading, writing, or flushing it. Exit performs checked close, including
buffered write errors; all retained aliases then refer to a closed stream.
Rebinding the original manager does not change which object gets closed.
Explicit close inside the body is safe because close is idempotent.

If both the body and implicit exit fail, the body error stays primary and the
exit error is retained as a secondary diagnostic. An exit-only failure is
catchable. Exit cannot suppress errors, unlike Python's protocol, and does not
have explicit `finally`'s completion-replacement behavior. Closure is not
rollback, atomic publication, or durability: writes may already be visible.

## Bounded binary workflow

Use `bytes([0, 255, 13, 10])` for octets, then `output.write_bytes(data)` on a
binary stream. `source.read_bytes(size)` reads at most a nonnegative `i64` byte
count; there is no read-all sentinel. It returns independently owned `bytes`,
including empty at EOF. Zero does not advance but still checks mode and closed
state. Text methods reject binary streams and byte methods reject text streams.
Nothing decodes, strips NUL, or translates newlines.

`examples/binary-files.x` is an executable round-trip and append example. It
creates/truncates `binary-output.dat` and `binary-empty.dat`; run it in a
scratch directory. Byte lengths and write counts are bytes, not characters.
Short writes that make progress are retried; no progress and I/O errors are
failures. Failure may leave a partially modified external file: there is no
rollback, atomicity, or durability promise. Checked scope exit or explicit
flush/close still matter for buffered errors.

See [byte values](built-in-types.md#byte-values) for immutable-buffer ownership.

## Text and lifetime safety

Reads consume all remaining text (not a size-limited chunk), returning an
independent string or `""` at EOF. CRLF and CR become LF; malformed UTF-8 and
embedded NUL fail. Write counts are Unicode characters, not bytes. Explicit
flush checks buffered writes without promising durability. Close is idempotent;
other operations on a closed file fail. Method signatures and concise contracts
live in `packages/arx/src/arx/builtins/files.x`.

Public `File` values follow ordinary acyclic class-reference ownership. Aliases
share one stream and cursor; closing through one reference closes it for all
references. References can be reassigned, passed to functions, returned, and
stored in class fields. Locals and discarded temporaries release their
references on ordinary lexical exits. The last reference releases the native
wrapper once, even if the stream was explicitly closed earlier. Read strings and
byte buffers own independent memory and can outlive the file. See
[Classes](classes.md).

Explicit casts to or from builtin `File`, including identity casts, remain
unsupported. Use ordinary assignment to create an alias instead.

Construction opens immediately: there is no public unopened constructor,
instance `open()` method, reopening, or builtin subclassing. A default-empty
`File` reference is not an unopened stream; dereferencing it raises the checked
class-reference error. Class containers/unions/struct fields, owned globals and
statics, generator capture, and external object ownership remain unsupported.

The class's native handle is private and uniquely owned. It cannot be extracted,
copied, returned, or replaced by user code; `NativeFileHandle` is not a public
Arx type. General class finalization owns its release, not a second manual
handle-freeing destructor.

Direct creation and I/O failures use `ARX-RUNTIME-FILE-001` and raise typed
exceptions (including `OSError` for operating-system failures). Class checks use
`ARX-RUNTIME-CLASS-001`; allocation failure remains unrecoverable. Failed
creation preserves constructor rollback and completed-base cleanup. See the
[exception boundary](../support-matrix.md#exception-capability-boundary). Use
checked scope exit or explicit close/flush to observe write errors before later
work. Iteration, seek/tell, and extra file properties are deferred.

For explicit imports, use `import File as TextFile from builtins.files` or
`import builtins.files as io` followed by `io.File(...)`. These resolve the same
canonical class, not an unrelated class with the same name. Existing user or
imported `File`/`open` bindings retain normal resolution; non-callable local
shadowing is an error. The lowercase `file` type always denotes the builtin.

This is a Python-like subset: parameter names/order/default spellings follow
[Python's interface](https://docs.python.org/3.14/library/functions.html#open),
but UTF-8 replaces locale-dependent encoding, and NUL-containing text and many
optional settings are intentionally unsupported. Existing user/imported
functions named `open` retain normal positional-call resolution. A local
non-callable `open` shadows the builtin and produces an error when called.
