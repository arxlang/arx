# Control Flow

Arx supports `if`/`elif`/`else`, `while`, and two `for` loop styles.

## If / Elif / Else

Conditions must be Boolean and are evaluated in order, stopping at the first
match. A chain may have any number of `elif` clauses and an optional final
`else`. Align every clause with its opening `if`; use `elif`, not `else if`.

````arx
```
title: Conditional chain example
summary: Classifies an integer using ordered comparisons.
```
fn classify(value: i32) -> i32:
  ```
  title: classify
  summary: Classifies one integer as negative, zero, or positive.
  ```
  if value < 0:
    return 0 - 1
  elif value == 0:
    return 0
  else:
    return 1
````

## While Loop

````arx
```
title: While loop example
summary: Repeats while condition is true.
```
fn count_to_ten() -> i32:
  ```
  title: count_to_ten
  summary: Increments value until it reaches ten.
  ```
  a: i32 = 0
  while a < 10:
    a = a + 1
  return a
````

## For Loop (For-In Style)

For-in loops iterate over ranges and supported sequences, including list
literals and list variables:

`for i in <iterable-expression>:`

````arx
```
title: Range-style for loop
summary: Iterates from start to end with the builtin range helper.
```
fn range_loop(n: i32) -> i32:
  ```
  title: range_loop
  summary: Sums values produced by a range loop.
  ```
  total: i32 = 0
  for i in range(0, n):
    total = total + i
  return total
````

`range(stop)` and `range(start, stop[, step])` produce immutable `range` values,
not lists. Named `start`, `stop`, and `step` are supported. Endpoints and
elements are `i32`; internal arithmetic and `len` use `i64`. Storage is
constant-size, and each iteration has an independent cursor. Rebinding the input
does not replace an active cursor's snapshot. Integer indexing is checked;
negative indices and slicing are unsupported. Zero step raises `AssertionError`,
even for an empty interval.

Request list storage explicitly with `list(values, max_items=N)`; exceeding the
bound raises `ValueError` without publishing a truncated prefix. There is no
implicit allocation when passing a range to a list or numeric-sequence consumer.

You can also iterate over a list literal or a list variable:

````arx
```
title: List for-in loop
summary: Iterates over one list variable and one list literal.
```
fn list_loop() -> i32:
  ```
  title: list_loop
  summary: Sums values from two list-valued loop inputs.
  ```
  values: list[i32] = list(range(3))
  total: i32 = 0
  for value in values:
    total = total + value
  for value in [3, 4]:
    total = total + value
  return total
````

The old colon range header syntax was removed. Use builtin `range(...)` or any
other supported iterable expression instead.

## For Loop (Count Style)

Count-style loops follow:

`for i: type = init; condition; update:`

````arx
```
title: Count-style for loop
summary: Uses initializer, condition, and update expressions.
```
fn count_loop() -> i32:
  ```
  title: count_loop
  summary: Sums numbers from 0 to 4.
  ```
  total: i32 = 0
  for i: i32 = 0; i < 5; i += 1:
    total += i
  return total
````

Compound updates write the induction variable themselves. Ordinary expression
updates such as `i + 1` remain supported; the loop stores their result into `i`.
See the [compound assignment contract](specification.md#compound-assignment).

## Break and Continue

`break` exits the nearest enclosing loop. `continue` starts its next iteration;
in a count loop it runs the update first. Both are operand-free statements and
are rejected outside loops. They work in `while`, count, and supported for-in
loops, including nested loops.

````arx
```
title: Skip values and stop early
```
fn main() -> i32:
  total: i32 = 0
  for value in range(1000000):
    if value == 0:
      continue
    if value == 4:
      break
    total += value
  assert total == 6
  return 0
````

Loop transfers release exited-scope owners and run `finally` before advancing or
leaving the loop. A cleanup failure cancels the transfer and propagates as an
exception; an explicit finalizer can replace it with another transfer, return,
or exception. Active iteration borrows end when their loop is exited.

## Return Statements

- `return expr` returns a value from the current function.
- Inside `none`-returning functions, use a bare `return`, `return none`, or omit
  the return statement entirely.

## Indentation Rules

- Blocks start after `:`.
- The next logical line must be indented by one level (2 spaces in Arx style).
- Misaligned indentation is treated as a parser error.
