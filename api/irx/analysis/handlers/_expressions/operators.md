---
title: irx.analysis.handlers._expressions.operators
---

# `irx.analysis.handlers._expressions.operators`

Source: `packages/irx/src/irx/analysis/handlers/_expressions/operators.py`

```yaml
title: Expression operator visitors.
summary: >-
  Analyze unary, binary, cast, and print expressions plus their assignment-like
  operator behavior.
```

## Classes

### `ExpressionOperatorVisitorMixin(SemanticVisitorMixinBase)`

```yaml
title: Expression visitors for unary, binary, cast, and print operations
```

#### Methods

##### `visit(self, node: astx.UnaryOp) -> None`

```yaml
title: Visit UnaryOp nodes.
parameters:
  node:
    type: astx.UnaryOp
```

##### `visit(self, node: astx.BinaryOp) -> None`

```yaml
title: Visit BinaryOp nodes.
parameters:
  node:
    type: astx.BinaryOp
```

##### `visit(self, node: astx.Cast) -> None`

```yaml
title: Visit Cast nodes.
parameters:
  node:
    type: astx.Cast
```

##### `visit(self, node: astx.IsInstanceExpr) -> None`

```yaml
title: Visit IsInstanceExpr nodes.
parameters:
  node:
    type: astx.IsInstanceExpr
```

##### `visit(self, node: astx.PrintExpr) -> None`

```yaml
title: Visit PrintExpr nodes.
parameters:
  node:
    type: astx.PrintExpr
```

##### `visit(self, node: astx.TypeOfExpr) -> None`

```yaml
title: Visit TypeOfExpr nodes.
parameters:
  node:
    type: astx.TypeOfExpr
```
