```
title: Owned Unicode input parsing
summary: Parse synthetic direction records without libc workarounds.
```

fn moves(text: str) -> i64:
  ```
  title: Parse signed direction records with whitespace defaults
  ```
  total: i64 = 0
  for record in text.split():
    amount: i64 = int(record[1:])
    if record[0] == "L":
      total = total - amount
    else:
      assert record[0] == "R"
      total = total + amount
  return total

fn words_from_file(path: str) -> list[str]:
  ```
  title: Return independent words after releasing a text file and its contents
  ```
  source: file = open(path)
  text: str = source.read()
  source.close()
  return text.split()

fn normalize(text: str) -> str:
  ```
  title: Return an independently owned stripped substring
  ```
  return text.strip()[1:]

class TextTrace:
  ```
  title: Mutate a receiver during argument evaluation
  ```
  text: public var :: str = "left,right,tail"
  order: public var :: i32 = 0

fn separator(trace: TextTrace) -> str:
  ```
  title: Replace source storage while recording argument order
  ```
  trace.text = "changed" + "!"
  trace.order = trace.order * 10 + 1
  return ","

fn limit(trace: TextTrace) -> i64:
  ```
  title: Record evaluation before a differently ordered named argument
  ```
  trace.order = trace.order * 10 + 2
  return 1

fn test_text_parsing() -> none:
  ```
  title: Common input parsing and code-point operations
  ```
  assert moves(" L68\nR-12\tL+5 ") == -85
  assert moves("") == 0
  assert len("é😀é") == 4
  assert "é😀é"[1] == "😀"
  assert ord("😀") == 128512
  assert ord('A') == 65
  assert int("7f", base=16) == 127
  assert int(" -9223372036854775808 ") == -9223372036854775808
  assert normalize(" L68 ") == "68"
  assert "word"[:] == "word"
  assert "word"[:2] == "wo"
  assert "word"[2:999:1] == "rd"
  assert "word"[3:1] == ""
  assert "word"[99:] == ""
  assert "word"[cast(255, u8):] == ""
  assert "xytextyx".strip(chars="xy") == "text"
  fields: list[str] = "a,,b,".split(sep=",")
  assert len(fields) == 4
  assert fields[1] == ""
  assert fields[3] == ""
  assert " a  b  ".split(maxsplit=0)[0] == "a  b  "
  assert " a  b  ".split(none, maxsplit=1)[1] == "b  "
  saved: str = fields[0]
  fields = []
  assert saved == "a"

fn test_text_argument_order() -> none:
  ```
  title: Preserve receiver storage and evaluate named arguments in source order
  ```
  trace: TextTrace = TextTrace()
  fields: list[str] = trace.text.split(maxsplit=limit(trace), sep=separator(trace))
  assert trace.order == 21
  assert trace.text == "changed!"
  assert fields[0] == "left"
  assert fields[1] == "right,tail"

fn checked_text_width(text: str) -> i64:
  ```
  title: Check repeated queries on a borrowed function argument
  ```
  i: i64 = 0
  while i < len(text):
    assert text[i] != ""
    i += 1
  return i

fn test_text_queries_after_reassignment() -> none:
  ```
  title: Rebuild cached metadata on replacement and keep independent results
  ```
  text: str = "abc"
  at: i64 = 1
  first: str = text[at]
  assert len(text) == 3
  text = "é" + "😀"
  assert len(text) == 2
  assert text[at] == "😀"
  assert text[0] == "é"
  assert first == "b"
  assert checked_text_width(text) == 2
  text = ""
  assert len(text) == 0
  source: str = "aé" + "😀"
  for count in [1, 2, 3]:
    prefix: str = source[:count]
    assert len(prefix) == cast(count, i64)
    assert prefix[0] == "a"
  hits: i32 = 0
  for item: str = "a"; len(item) < 2; "bb":
    hits += 1
    if hits == 2:
      break
  assert hits == 1

fn rebuilt_row(reset: bool) -> str:
  ```
  title: Return either a static or heap-backed string generation
  ```
  row: str = ""
  row = row + "@"
  if reset:
    row = "reset"
  return row

fn count_until_update(replacement: str) -> i32:
  ```
  title: Copy a borrowed value into the count-loop binding
  ```
  count: i32 = 0
  for item: str = "x"; len(item) < 2; replacement:
    count += 1
    if count == 2:
      break
  return count

fn test_resource_reassignment() -> none:
  ```
  title: Replace owned strings and move rebuilt list storage repeatedly
  ```
  assert rebuilt_row(false) == "@"
  assert rebuilt_row(true) == "reset"
  assert count_until_update("xx") == 1
  row: str = ""
  grid: list[str] = "a\nb".split("\n")
  next: list[str] = []
  next.append("c")
  count: i32 = 0
  while count < 16:
    row = row + "@"
    saved: str = row
    row = ""
    assert saved == "@"
    grid = next
    grid = grid
    moved: list[str] = grid
    grid = moved
    assert len(grid) == 1
    assert grid[0] == "c"
    next = []
    next.append("c")
    count += 1

fn test_text_failures() -> none:
  ```
  title: Checked failures preserve owners and remain recoverable
  ```
  saved: str = "unchanged".strip()
  fields: list[str] = ["saved"]
  caught: i32 = 0
  negative: i64 = -1
  try:
    saved = "abc"[negative]
  except IndexError:
    caught = caught + 1
  try:
    saved = "abc"[negative:]
  except ValueError:
    caught = caught + 1
  try:
    saved = "abc"[::2]
  except ValueError:
    caught = caught + 1
  try:
    int("9223372036854775808")
  except OverflowError:
    caught = caught + 1
  try:
    int("12junk")
  except ValueError:
    caught = caught + 1
  try:
    fields = "a".split("")
  except ValueError:
    caught = caught + 1
  try:
    ord("ab")
  except ValueError:
    caught = caught + 1
  assert caught == 7
  assert saved == "unchanged"
  assert fields[0] == "saved"
