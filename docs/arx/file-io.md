# Text File I/O

`File` is a builtin reference-managed class for a deliberately small native,
POSIX text-file interface. `open(...)` is a compiler-backed factory adapter to
`File(...)`: both create the same class object through one checked construction
path. Both are available without an import and use C stdio, not Python or Arrow.
Lowercase `file` remains a compatibility spelling for the builtin `File` type.

The default is a strict UTF-8 text read. Use `mode="w"` to create/truncate or
`mode="a"` to append. Only the path and mode can be runtime strings; other
Python-shaped settings accept only the implemented default profile. Nondefault
buffering, encodings, error policies, newline handling, descriptors, and openers
are rejected rather than ignored. Options are checked before I/O; a dynamic mode
is checked before opening or truncating a path.

Paths are relative to the running program's working directory, not its source
file.

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
  var output: File = File("message.txt", mode="w", encoding="utf-8")
  var alias: file = output
  assert alias.write("hello\n") == 6
  output.close()
  alias.close()
  var source: file = open(file="message.txt")
  var text: str = source.read()
  source.close()
  print(text)
  return 0
````

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
wrapper once, even if the stream was explicitly closed earlier. Read strings own
independent memory and can outlive the file. See [Classes](classes.md).

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

Direct creation and I/O failures report `ARX-RUNTIME-FILE-001` and exit nonzero.
Class allocation, empty-reference, and class-release failures use
`ARX-RUNTIME-CLASS-001`. Checked native creation failures preserve active local
constructor rollback and completed-base cleanup. Fatal errors in arbitrary user
calls still do not unwind caller frames or provide catchable exceptions.
Explicit close/flush are recommended to observe write errors before later work.
`with`, iteration, seek/tell, binary I/O, and extra file properties are
deferred.

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
