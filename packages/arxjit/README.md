# ArxJIT

ArxJIT is the planned Numba-style route from a restricted subset of pure Python
to ASTx, IRx, LLVM, and native callable code.

> **Important:** native JIT compilation is not implemented yet. A decorated
> function currently executes the original Python function.

## Current API

```python
from arxjit import i64, jit


@jit(signature=i64(i64, i64), cache=True)
def add(left, right):
    return left + right


assert add(20, 22) == 42  # Python fallback today
```

Implemented foundations:

- `@jit` and the `JitFunction` wrapper
- scalar signatures: `i32`, `i64`, `f32`, `f64`, and `bool_`
- robust function-source extraction with real-file locations
- validation for the proposed scalar Python subset
- signature reconciliation from explicit signatures or scalar annotations
- initial fail-closed ASTx lowering for function shells and straight-line scalar
  expressions
- structured diagnostics and public error types

The validator accepts typed scalar arguments, arithmetic/comparison/Boolean
expressions, single-target assignments, `if`/`else`, `while`, `for` over the
builtin `range`, and `return`. It rejects unsupported constructs with one
diagnostic per violation.

Not implemented:

- ASTx lowering for assignments, short-circuit Boolean expressions, chained
  comparisons, and control flow
- IRx compilation or native function calls
- runtime argument/result marshalling
- signature inference and artifact caching
- array, Tensor, or Apache Arrow signatures

See the [staged design](https://arxlang.org/arxjit/design.html) for the
Python-to-ASTx pipeline.

License: Apache-2.0.
