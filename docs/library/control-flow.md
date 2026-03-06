# Control Flow

Arx currently supports `if`/`else`, `while`, and two `for` loop styles.

## If / Else

````arx
```
title: If/else example
summary: Branches based on a comparison.
```
fn abs_value(x: i32) -> i32:
  ```
  title: abs_value
  summary: Returns absolute value of x.
  ```
  if x < 0:
    return 0 - x
  else:
    return x
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

## For Loop (Range Style)

Range-style loops use the slice-like header:

`for i in (start:end:step):`

````arx
```
title: Range-style for loop
summary: Iterates from start to end with step.
```
fn range_loop(n: i32) -> i32:
  ```
  title: range_loop
  summary: Sums values produced by a range loop.
  ```
  var total: i32 = 0
  for i in (0:n:1):
    total = total + i
  return total
````

Tuple-style range headers such as `(0, 5, 1)` are not supported.

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
  for var i: i32 = 0; i < 5; i = i + 1:
    total = total + i
  return total
````

## Return Statements

- `return expr` returns a value from the current function.
- `return none` is used for `none`-returning functions.

## Indentation Rules

- Blocks start after `:`.
- The next logical line must be indented by one level (2 spaces in Arx style).
- Misaligned indentation is treated as a parser error.
