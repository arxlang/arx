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

##### `resolve_class_structure_in_module(self, class_: SemanticClass) -> SemanticClass`

```yaml
title: Resolve structural members in the declaring module's namespace.
parameters:
  class_:
    type: SemanticClass
returns:
  type: SemanticClass
```

##### `visit(self, node: astx.ClassDefStmt) -> None`

```yaml
title: Visit ClassDefStmt nodes.
parameters:
  node:
    type: astx.ClassDefStmt
```
