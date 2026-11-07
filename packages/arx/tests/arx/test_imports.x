```
title: Repository import tests
summary: Cover namespace, named, grouped, relative, and stdlib import paths.
```

import tests.arx.support.arithmetic as arithmetic
import add2 as plus from tests.arx.support.arithmetic
import (sum3, doubled as twice) from tests.arx.support.stats
import math as maths from stdlib

namespace_total: fn() -> i32:
  ```
  title: namespace_total
  summary: Uses one namespace import alias for nested helper calls.
  ```
  return arithmetic.add2(2, arithmetic.scale(3, 4))

test_namespace_import_alias: fn() -> none:
  ```
  title: test_namespace_import_alias
  summary: Verifies namespace imports with an alias remain callable.
  ```
  assert arithmetic.add2(1, 2) == 3
  assert arithmetic.scale(3, 4) == 12
  assert namespace_total() == 14

test_named_and_grouped_imports: fn() -> none:
  ```
  title: test_named_and_grouped_imports
  summary: Verifies named imports, grouped imports, and grouped aliases.
  ```
  assert plus(4, 5) == 9
  assert sum3(1, 2, 3) == 6
  assert twice(6) == 12

test_stdlib_import_alias: fn() -> none:
  ```
  title: test_stdlib_import_alias
  summary: Verifies stdlib imports support aliases and assertion messages.
  ```
  assert maths.abs(0 - 9) == 9, "stdlib alias imports should resolve"
  assert maths.square(6) == 36
  assert maths.clamp(7, 0, 5) == 5
