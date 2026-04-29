---
title: irx.analysis.handlers._expressions.modules
---

# `irx.analysis.handlers._expressions.modules`

Source: `packages/irx/src/irx/analysis/handlers/_expressions/modules.py`

```yaml
title: Expression module-namespace helpers.
summary: >-
  Resolve module namespaces, namespace member access, and direct function calls
  in expression analysis.
```

## Classes

### `ExpressionModuleVisitorMixin(SemanticVisitorMixinBase)`

```yaml
title: Expression helpers for module namespaces and function calls
```

#### Methods

##### `visit(self, node: astx.Identifier) -> None`

```yaml
title: Visit Identifier nodes.
parameters:
  node:
    type: astx.Identifier
```

##### `visit(self, node: astx.FunctionCall) -> None`

```yaml
title: Visit FunctionCall nodes.
parameters:
  node:
    type: astx.FunctionCall
```
