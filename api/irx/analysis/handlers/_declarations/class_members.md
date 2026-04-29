---
title: irx.analysis.handlers._declarations.class_members
---

# `irx.analysis.handlers._declarations.class_members`

Source: `packages/irx/src/irx/analysis/handlers/_declarations/class_members.py`

```yaml
title: Declaration class-member resolution helpers.
summary: >-
  Resolve declared and effective class members, then finish class-definition
  analysis from the normalized declaration metadata.
```

## Classes

### `DeclarationClassMemberVisitorMixin(DeclarationClassMethodVisitorMixin)`

```yaml
title: Declaration class-member resolution helpers.
```

#### Methods

##### `visit(self, node: astx.ClassDefStmt) -> None`

```yaml
title: Visit ClassDefStmt nodes.
parameters:
  node:
    type: astx.ClassDefStmt
```
