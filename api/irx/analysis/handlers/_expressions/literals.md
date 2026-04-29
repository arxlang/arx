---
title: irx.analysis.handlers._expressions.literals
---

# `irx.analysis.handlers._expressions.literals`

Source: `packages/irx/src/irx/analysis/handlers/_expressions/literals.py`

```yaml
title: Expression literal visitors.
summary: >-
  Handle literal expressions, list operations, and generic subscript
  expressions during semantic analysis.
```

## Classes

### `ExpressionLiteralVisitorMixin(SemanticVisitorMixinBase)`

```yaml
title: Expression visitors for literals, list operations, and subscripts
```

#### Methods

##### `visit(self, node: astx.AliasExpr) -> None`

```yaml
title: Visit AliasExpr nodes.
parameters:
  node:
    type: astx.AliasExpr
```

##### `visit(self, node: astx.LiteralTime) -> None`

```yaml
title: Visit LiteralTime nodes.
parameters:
  node:
    type: astx.LiteralTime
```

##### `visit(self, node: astx.LiteralTimestamp) -> None`

```yaml
title: Visit LiteralTimestamp nodes.
parameters:
  node:
    type: astx.LiteralTimestamp
```

##### `visit(self, node: astx.LiteralDateTime) -> None`

```yaml
title: Visit LiteralDateTime nodes.
parameters:
  node:
    type: astx.LiteralDateTime
```

##### `visit(self, node: astx.CollectionLength) -> None`

```yaml
title: Visit CollectionLength nodes.
parameters:
  node:
    type: astx.CollectionLength
```

##### `visit(self, node: astx.CollectionIsEmpty) -> None`

```yaml
title: Visit CollectionIsEmpty nodes.
parameters:
  node:
    type: astx.CollectionIsEmpty
```

##### `visit(self, node: astx.CollectionContains) -> None`

```yaml
title: Visit CollectionContains nodes.
parameters:
  node:
    type: astx.CollectionContains
```

##### `visit(self, node: astx.CollectionIndex) -> None`

```yaml
title: Visit CollectionIndex nodes.
parameters:
  node:
    type: astx.CollectionIndex
```

##### `visit(self, node: astx.CollectionCount) -> None`

```yaml
title: Visit CollectionCount nodes.
parameters:
  node:
    type: astx.CollectionCount
```

##### `visit(self, node: astx.LiteralList) -> None`

```yaml
title: Visit LiteralList nodes.
parameters:
  node:
    type: astx.LiteralList
```

##### `visit(self, node: astx.LiteralTuple) -> None`

```yaml
title: Visit LiteralTuple nodes.
parameters:
  node:
    type: astx.LiteralTuple
```

##### `visit(self, node: astx.LiteralSet) -> None`

```yaml
title: Visit LiteralSet nodes.
parameters:
  node:
    type: astx.LiteralSet
```

##### `visit(self, node: astx.LiteralDict) -> None`

```yaml
title: Visit LiteralDict nodes.
parameters:
  node:
    type: astx.LiteralDict
```

##### `visit(self, node: astx.ListCreate) -> None`

```yaml
title: Visit ListCreate nodes.
parameters:
  node:
    type: astx.ListCreate
```

##### `visit(self, node: astx.ComprehensionClause) -> None`

```yaml
title: Visit ComprehensionClause nodes.
parameters:
  node:
    type: astx.ComprehensionClause
```

##### `visit(self, node: astx.ListComprehension) -> None`

```yaml
title: Visit ListComprehension nodes.
parameters:
  node:
    type: astx.ListComprehension
```

##### `visit(self, node: astx.GeneratorExpr) -> None`

```yaml
title: Visit GeneratorExpr nodes.
parameters:
  node:
    type: astx.GeneratorExpr
```

##### `visit(self, node: astx.SetComprehension) -> None`

```yaml
title: Visit SetComprehension nodes.
parameters:
  node:
    type: astx.SetComprehension
```

##### `visit(self, node: astx.DictComprehension) -> None`

```yaml
title: Visit DictComprehension nodes.
parameters:
  node:
    type: astx.DictComprehension
```

##### `visit(self, node: astx.ListIndex) -> None`

```yaml
title: Visit ListIndex nodes.
parameters:
  node:
    type: astx.ListIndex
```

##### `visit(self, node: astx.ListLength) -> None`

```yaml
title: Visit ListLength nodes.
parameters:
  node:
    type: astx.ListLength
```

##### `visit(self, node: astx.ListAppend) -> None`

```yaml
title: Visit ListAppend nodes.
parameters:
  node:
    type: astx.ListAppend
```

##### `visit(self, node: astx.SubscriptExpr) -> None`

```yaml
title: Visit SubscriptExpr nodes.
parameters:
  node:
    type: astx.SubscriptExpr
```
