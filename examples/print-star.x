```
title: Print star example
summary: Emits star characters using the builtin print function.
```
fn print_star(n: i32) -> none:
  ```
  title: print_star
  summary: Prints stars in a loop by calling print.
  ```
  for i in (0:n:1):
    print("*");
  return none
