---
title: irx.analysis.handlers._expressions.class_support
---

# `irx.analysis.handlers._expressions.class_support`

Source: `packages/irx/src/irx/analysis/handlers/_expressions/class_support.py`

```yaml
title: Expression class-resolution helpers.
summary: >-
  Resolve class members, overload sets, and field metadata shared by the class-
  oriented expression visitors.
```

## Classes

### `ExpressionClassSupportVisitorMixin(ClassMemberFormattingVisitorMixin)`

```yaml
title: Expression class-resolution helpers.
```

#### Methods

##### `bound_method_matches(self, class_: SemanticClass, member: SemanticClassMember, arg_types: list[astx.DataType | None], node: astx.AST, *, exact: bool) -> bool`

```yaml
title: >-
  Match a candidate's own keyword names without speculative visits.
parameters:
  class_:
    type: SemanticClass
  member:
    type: SemanticClassMember
  arg_types:
    type: list[astx.DataType | None]
  node:
    type: astx.AST
  exact:
    type: bool
returns:
  type: bool
```
