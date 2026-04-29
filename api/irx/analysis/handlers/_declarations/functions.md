---
title: irx.analysis.handlers._declarations.functions
---

# `irx.analysis.handlers._declarations.functions`

Source: `packages/irx/src/irx/analysis/handlers/_declarations/functions.py`

```yaml
title: Declaration function visitors.
summary: >-
  Resolve function declarations, synchronize normalized signatures, and analyze
  non-template function bodies.
```

## Classes

### `DeclarationFunctionVisitorMixin(SemanticVisitorMixinBase)`

```yaml
title: Declaration visitors for function signatures and bodies
```

#### Methods

##### `visit(self, node: astx.FunctionPrototype) -> None`

```yaml
title: Visit FunctionPrototype nodes.
parameters:
  node:
    type: astx.FunctionPrototype
```

##### `visit(self, node: astx.FunctionDef) -> None`

```yaml
title: Visit FunctionDef nodes.
parameters:
  node:
    type: astx.FunctionDef
```
