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
