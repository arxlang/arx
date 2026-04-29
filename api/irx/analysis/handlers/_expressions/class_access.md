---
title: irx.analysis.handlers._expressions.class_access
---

# `irx.analysis.handlers._expressions.class_access`

Source: `packages/irx/src/irx/analysis/handlers/_expressions/class_access.py`

```yaml
title: Expression class-access visitors.
summary: >-
  Handle class construction, method calls, and field access using the shared
  class-resolution helpers.
```

## Classes

### `ExpressionClassAccessVisitorMixin(ExpressionClassSupportVisitorMixin)`

```yaml
title: Expression class-access visitors.
```

#### Methods

##### `visit(self, node: astx.ClassConstruct) -> None`

```yaml
title: Visit ClassConstruct nodes.
parameters:
  node:
    type: astx.ClassConstruct
```

##### `visit(self, node: astx.MethodCall) -> None`

```yaml
title: Visit MethodCall nodes.
parameters:
  node:
    type: astx.MethodCall
```

##### `visit(self, node: astx.BaseMethodCall) -> None`

```yaml
title: Visit BaseMethodCall nodes.
parameters:
  node:
    type: astx.BaseMethodCall
```

##### `visit(self, node: astx.StaticMethodCall) -> None`

```yaml
title: Visit StaticMethodCall nodes.
parameters:
  node:
    type: astx.StaticMethodCall
```

##### `visit(self, node: astx.BaseFieldAccess) -> None`

```yaml
title: Visit BaseFieldAccess nodes.
parameters:
  node:
    type: astx.BaseFieldAccess
```

##### `visit(self, node: astx.StaticFieldAccess) -> None`

```yaml
title: Visit StaticFieldAccess nodes.
parameters:
  node:
    type: astx.StaticFieldAccess
```

##### `visit(self, node: astx.FieldAccess) -> None`

```yaml
title: Visit FieldAccess nodes.
parameters:
  node:
    type: astx.FieldAccess
```
