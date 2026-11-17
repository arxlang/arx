```
title: Pure-Arx scalar and shared Series compute consumers
summary: This package supplies no native artifacts or compiler build hooks.
```
import square as integer_square from stdlib.math

fn squared(value: i64) -> i64:
  return integer_square(value)

fn shifted(values: series[f64], amount: f64) -> series[f64]:
  return values + amount

fn scaled(values: series[f64], factor: f64) -> series[f64]:
  return values * factor
