```
title: Import syntax examples
summary: Demonstrates absolute, relative, and namespace import forms.
```
import toolkit.math
import toolkit.math as math

import sum from toolkit.math
import sum as add from toolkit.math

import (sum, mean as average) from toolkit.math

import sum from .math
import (sum, mean) from .stats
import helper from ..shared.helpers


fn use_namespace_import() -> none:
  ```
  title: Namespace import usage
  summary: Calls one imported module member through an alias.
  ```
  math.sum(1.0, 2.0)
  return none
