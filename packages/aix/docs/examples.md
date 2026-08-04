# AIX examples

Runnable samples live in [`packages/aix/examples`](../examples). From the
repository root, inspect or execute them with:

```bash
aix --show-tokens packages/aix/examples/hello.aix
aix --show-ast packages/aix/examples/fib.aix
aix --show-llvm-ir packages/aix/examples/fib.aix
aix --run packages/aix/examples/fib.aix
```

| File              | Demonstrates                                                 |
| ----------------- | ------------------------------------------------------------ |
| `hello.aix`       | Unit-returning `main` and `⟣` output                         |
| `bindings.aix`    | Typed local binding                                          |
| `fib.aix`         | Metadata, typed functions, recursion, and conditional return |
| `compact_fib.aix` | Brace blocks and semicolon-separated compact layout          |
| `metadata.aix`    | Balanced metadata accepted and skipped by the parser         |

The `aix test` command currently discovers and **parses** matching `.aix` test
files. It reports syntax/frontend failures but does not yet execute assertions
or compiled test functions:

```bash
aix test packages/aix/tests/aix
aix test packages/aix/tests/aix --list
```
