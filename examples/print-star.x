```
title: Print star example
summary: Emits star characters using an external output function.
```
fn print_star(n: i32) -> none:
  ```
  title: print_star
  summary: Prints stars in a loop by calling putchard.
  ```
  for i in (0:n:1):
    putchard(42);  # ascii 42 = '*'
  return none
