---
title: irx.analysis.handlers._declarations.blocks
---

# `irx.analysis.handlers._declarations.blocks`

Source: `packages/irx/src/irx/analysis/handlers/_declarations/blocks.py`

```yaml
title: Declaration block visitors.
summary: >-
  Handle modules, blocks, and local variable declarations during declaration
  analysis.
```

## Classes

### `DeclarationBlockVisitorMixin(SemanticVisitorMixinBase)`

```yaml
title: Declaration visitors for modules, blocks, and local declarations
```

#### Methods

##### `visit(self, module: astx.Module) -> None`

```yaml
title: Visit Module nodes.
parameters:
  module:
    type: astx.Module
```

##### `visit(self, block: astx.Block) -> None`

```yaml
title: Visit Block nodes.
parameters:
  block:
    type: astx.Block
```

##### `visit(self, node: astx.VariableDeclaration) -> None`

```yaml
title: Visit VariableDeclaration nodes.
parameters:
  node:
    type: astx.VariableDeclaration
```

##### `visit(self, node: astx.InlineVariableDeclaration) -> None`

```yaml
title: Visit InlineVariableDeclaration nodes.
parameters:
  node:
    type: astx.InlineVariableDeclaration
```
