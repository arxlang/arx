```
title: Pure-Arx scalar and shared Series compute consumers
summary: This package supplies no native artifacts or compiler build hooks.
```
import (sqrt as arrow_sqrt, exp as arrow_exp) from stdlib.math

@<T: f64 | nullable[f64] | series[f64] | series[nullable[f64]]>
fn rooted(value: T) -> T:
  return arrow_sqrt(value=value)

@<T: f64 | nullable[f64] | series[f64] | series[nullable[f64]]>
fn exponentiated(value: T) -> T:
  return arrow_exp(value)
