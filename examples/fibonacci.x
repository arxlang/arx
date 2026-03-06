```
title: Fibonacci example
summary: Computes Fibonacci numbers recursively.
```
fn fib(x: i32) -> i32:
  ```
  title: fib
  summary: Returns the Fibonacci number for the input index.
  ```
  if x < 3:
    return 1
  else:
    return fib(x-1)+fib(x-2)


fn main() -> i32:
  ```
  title: main
  summary: Runs the fibonacci demo and exits with status 0.
  ```
  print(fib(10))
  return 0
