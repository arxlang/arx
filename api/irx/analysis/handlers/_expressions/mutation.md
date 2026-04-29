---
title: irx.analysis.handlers._expressions.mutation
---

# `irx.analysis.handlers._expressions.mutation`

Source: `packages/irx/src/irx/analysis/handlers/_expressions/mutation.py`

```yaml
title: Expression mutation helpers.
summary: >-
  Resolve assignment and mutation targets, including class-field mutation
  handling.
```

## Classes

### `ExpressionMutationVisitorMixin(ClassMemberFormattingVisitorMixin)`

```yaml
title: Expression helpers for assignment and mutation targets
```

#### Methods

##### `visit(self, node: astx.VariableAssignment) -> None`

```yaml
title: Visit VariableAssignment nodes.
parameters:
  node:
    type: astx.VariableAssignment
```
