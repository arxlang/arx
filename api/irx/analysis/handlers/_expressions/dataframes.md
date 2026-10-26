---
title: irx.analysis.handlers._expressions.dataframes
---

# `irx.analysis.handlers._expressions.dataframes`

Source: `packages/irx/src/irx/analysis/handlers/_expressions/dataframes.py`

```yaml
title: Expression DataFrame visitors.
summary: >-
  Handle DataFrame literals, column access, metadata queries, and lifetime
  helper expressions.
```

## Classes

### `ExpressionDataFrameVisitorMixin(SemanticVisitorMixinBase)`

```yaml
title: Expression DataFrame visitors.
```

#### Methods

##### `visit(self, node: astx.NullCheck) -> None`

```yaml
title: Resolve a scalar validity test or an owned Series null mask.
parameters:
  node:
    type: astx.NullCheck
```

##### `visit(self, node: astx.NullFill) -> None`

```yaml
title: Resolve eager same-type scalar null replacement.
parameters:
  node:
    type: astx.NullFill
```

##### `visit(self, node: astx.SeriesReduction) -> None`

```yaml
title: Resolve an explicitly named null-skipping Series reduction.
parameters:
  node:
    type: astx.SeriesReduction
```

##### `visit(self, node: astx.DataFrameLiteral) -> None`

```yaml
title: Visit DataFrameLiteral nodes.
parameters:
  node:
    type: astx.DataFrameLiteral
```

##### `visit(self, node: astx.DataFrameColumnAccess) -> None`

```yaml
title: Visit DataFrameColumnAccess nodes.
parameters:
  node:
    type: astx.DataFrameColumnAccess
```

##### `visit(self, node: astx.DataFrameStringColumnAccess) -> None`

```yaml
title: Visit DataFrameStringColumnAccess nodes.
parameters:
  node:
    type: astx.DataFrameStringColumnAccess
```

##### `visit(self, node: astx.DataFrameRowCount) -> None`

```yaml
title: Visit DataFrameRowCount nodes.
parameters:
  node:
    type: astx.DataFrameRowCount
```

##### `visit(self, node: astx.DataFrameColumnCount) -> None`

```yaml
title: Visit DataFrameColumnCount nodes.
parameters:
  node:
    type: astx.DataFrameColumnCount
```

##### `visit(self, node: astx.DataFrameRetain) -> None`

```yaml
title: Visit DataFrameRetain nodes.
parameters:
  node:
    type: astx.DataFrameRetain
```

##### `visit(self, node: astx.DataFrameRelease) -> None`

```yaml
title: Visit DataFrameRelease nodes.
parameters:
  node:
    type: astx.DataFrameRelease
```

##### `visit(self, node: astx.SeriesRetain) -> None`

```yaml
title: Visit SeriesRetain nodes.
parameters:
  node:
    type: astx.SeriesRetain
```

##### `visit(self, node: astx.SeriesRelease) -> None`

```yaml
title: Visit SeriesRelease nodes.
parameters:
  node:
    type: astx.SeriesRelease
```
