---
title: irx.analysis.handlers._expressions.tensors
---

# `irx.analysis.handlers._expressions.tensors`

Source: `packages/irx/src/irx/analysis/handlers/_expressions/tensors.py`

```yaml
title: Expression Tensor visitors.
summary: >-
  Handle tensor literals, views, indexing, and lifetime helper expressions
  using the shared tensor-and-buffer support mixin.
```

## Classes

### `ExpressionTensorVisitorMixin(ExpressionTensorBufferSupportVisitorMixin)`

```yaml
title: Expression Tensor visitors.
```

#### Methods

##### `visit(self, node: astx.TensorLiteral) -> None`

```yaml
title: Visit TensorLiteral nodes.
parameters:
  node:
    type: astx.TensorLiteral
```

##### `visit(self, node: astx.TensorView) -> None`

```yaml
title: Visit TensorView nodes.
parameters:
  node:
    type: astx.TensorView
```

##### `visit(self, node: astx.TensorIndex) -> None`

```yaml
title: Visit TensorIndex nodes.
parameters:
  node:
    type: astx.TensorIndex
```

##### `visit(self, node: astx.TensorStore) -> None`

```yaml
title: Visit TensorStore nodes.
parameters:
  node:
    type: astx.TensorStore
```

##### `visit(self, node: astx.TensorNDim) -> None`

```yaml
title: Visit TensorNDim nodes.
parameters:
  node:
    type: astx.TensorNDim
```

##### `visit(self, node: astx.TensorShape) -> None`

```yaml
title: Visit TensorShape nodes.
parameters:
  node:
    type: astx.TensorShape
```

##### `visit(self, node: astx.TensorStride) -> None`

```yaml
title: Visit TensorStride nodes.
parameters:
  node:
    type: astx.TensorStride
```

##### `visit(self, node: astx.TensorElementCount) -> None`

```yaml
title: Visit TensorElementCount nodes.
parameters:
  node:
    type: astx.TensorElementCount
```

##### `visit(self, node: astx.TensorByteOffset) -> None`

```yaml
title: Visit TensorByteOffset nodes.
parameters:
  node:
    type: astx.TensorByteOffset
```

##### `visit(self, node: astx.TensorRetain) -> None`

```yaml
title: Visit TensorRetain nodes.
parameters:
  node:
    type: astx.TensorRetain
```

##### `visit(self, node: astx.TensorRelease) -> None`

```yaml
title: Visit TensorRelease nodes.
parameters:
  node:
    type: astx.TensorRelease
```
