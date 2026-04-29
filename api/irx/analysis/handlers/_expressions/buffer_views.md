---
title: irx.analysis.handlers._expressions.buffer_views
---

# `irx.analysis.handlers._expressions.buffer_views`

Source: `packages/irx/src/irx/analysis/handlers/_expressions/buffer_views.py`

```yaml
title: Expression buffer-view visitors.
summary: >-
  Handle buffer-view descriptors, indexing, writes, and lifetime helper
  expressions using the shared tensor-and-buffer support mixin.
```

## Classes

### `ExpressionBufferViewVisitorMixin(ExpressionTensorBufferSupportVisitorMixin)`

```yaml
title: Expression buffer-view visitors.
```

#### Methods

##### `visit(self, node: astx.BufferViewDescriptor) -> None`

```yaml
title: Visit BufferViewDescriptor nodes.
parameters:
  node:
    type: astx.BufferViewDescriptor
```

##### `visit(self, node: astx.BufferViewIndex) -> None`

```yaml
title: Visit BufferViewIndex nodes.
parameters:
  node:
    type: astx.BufferViewIndex
```

##### `visit(self, node: astx.BufferViewStore) -> None`

```yaml
title: Visit BufferViewStore nodes.
parameters:
  node:
    type: astx.BufferViewStore
```

##### `visit(self, node: astx.BufferViewWrite) -> None`

```yaml
title: Visit BufferViewWrite nodes.
parameters:
  node:
    type: astx.BufferViewWrite
```

##### `visit(self, node: astx.BufferViewRetain) -> None`

```yaml
title: Visit BufferViewRetain nodes.
parameters:
  node:
    type: astx.BufferViewRetain
```

##### `visit(self, node: astx.BufferViewRelease) -> None`

```yaml
title: Visit BufferViewRelease nodes.
parameters:
  node:
    type: astx.BufferViewRelease
```
