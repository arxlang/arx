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
  var a: i32 = 0
  while a < 10:
    a = a + 1
  return a
````

## For Loop (For-In Style)

For-in loops iterate over list-valued expressions, including builtin
`range(start, stop[, step])`, list literals, and list variables:

`for i in <list-expression>:`

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
  var total: i32 = 0
  for i in range(0, n):
    total = total + i
  return total
````

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
  var values: list[i32] = range(0, 3)
  var total: i32 = 0
  for value in values:
    total = total + value
  for value in [3, 4]:
    total = total + value
  return total
````

The old colon range header syntax was removed. Use builtin `range(...)` or any
other list-valued expression instead.

## For Loop (Count Style)

Count-style loops follow:

`for var i: type = init; condition; update:`

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
  var total: i32 = 0
  for var i: i32 = 0; i < 5; i += 1:
    total += i
  return total
````

Compound updates write the induction variable themselves. Ordinary expression
updates such as `i + 1` remain supported; the loop stores their result into `i`.
See the [compound assignment contract](specification.md#compound-assignment).

## Return Statements

- `return expr` returns a value from the current function.
- Inside `none`-returning functions, use a bare `return`, `return none`, or omit
  the return statement entirely.

## Indentation Rules

- Blocks start after `:`.
- The next logical line must be indented by one level (2 spaces in Arx style).
- Misaligned indentation is treated as a parser error.
