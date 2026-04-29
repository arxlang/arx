---
title: irx.analysis.handlers._declarations.structs
---

# `irx.analysis.handlers._declarations.structs`

Source: `packages/irx/src/irx/analysis/handlers/_declarations/structs.py`

```yaml
title: Declaration struct visitors.
summary: >-
  Resolve struct field metadata and reject invalid by-value recursive struct
  definitions.
```

## Classes

### `DeclarationStructVisitorMixin(SemanticVisitorMixinBase)`

```yaml
title: Declaration visitors for struct fields and recursion checks
```

#### Methods

##### `visit(self, node: astx.StructDefStmt) -> None`

```yaml
title: Visit StructDefStmt nodes.
parameters:
  node:
    type: astx.StructDefStmt
```
