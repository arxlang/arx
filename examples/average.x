```
title: Average example
summary: Demonstrates a basic arithmetic average function.
```
fn average(x: f32, y: f32) -> f32:
  ```
  title: average
  summary: Returns the arithmetic mean of x and y.
  ```
  return (x + y) * 0.5;

fn main() -> i32:
  ```
  title: main
  summary: Runs the print_star demo with a fixed size and exits with status 0.
  ```
  print(average(10.0, 20.0))
  return 0
