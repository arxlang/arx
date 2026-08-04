# ArxJIT

ArxJIT is a developing Numba-style decorator path from a restricted subset of
pure Python to ASTx, IRx, LLVM, and native callable code.

> **Current behavior:** decorated calls execute the original Python function.
> Native lowering and compilation have not landed.

## Implemented foundations

- `@jit` and `JitFunction`
- explicit scalar signatures using `i32`, `i64`, `f32`, `f64`, and `bool_`
- function-source extraction with corrected real-file source locations
- structured errors when source cannot be retrieved or parsed
- exhaustive validation and diagnostics for the proposed Python subset

```python
from arxjit import i64, jit


@jit(signature=i64(i64, i64), cache=True)
def add(left, right):
    return left + right


assert add(20, 22) == 42  # Python fallback in the current implementation
```

The current validator accepts scalar expressions, assignments, `if`/`else`,
`while`, `for` over the unshadowed builtin `range`, and returns. Collections,
closures, imports, methods, async code, generators, exceptions, attributes, and
subscripting are rejected.

## Deferred pipeline

```text
Python function
  -> source extraction       implemented
  -> Python AST validation   implemented
  -> ASTx lowering           not implemented
  -> IRx native compilation  not implemented
  -> Python-callable bridge  not implemented
```

Arrow-backed arrays and tensors are intentionally deferred until scalar
compilation and runtime marshalling are stable.

See the [Python-to-ASTx design](design.md) for the implemented frontend stages
and remaining compilation work.
