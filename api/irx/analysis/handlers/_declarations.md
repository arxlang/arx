---
title: irx.analysis.handlers._declarations
---

# `irx.analysis.handlers._declarations`

Source: `packages/irx/src/irx/analysis/handlers/_declarations/__init__.py`

```yaml
title: Declaration-oriented semantic visitors.
summary: >-
  Handle modules, functions, structs, and lexical declarations while delegating
  semantic entity creation and registration to smaller concern-focused mixins.
```

## Classes

### `DeclarationVisitorMixin(DeclarationFunctionVisitorMixin, DeclarationStructVisitorMixin, DeclarationClassSupportVisitorMixin, DeclarationClassLayoutVisitorMixin, DeclarationClassMemberVisitorMixin, DeclarationBlockVisitorMixin)`

```yaml
title: Declaration-oriented semantic visitors.
summary: >-
  Compose the declaration-focused semantic mixins so the analyzer keeps the
  same visitor surface while the implementation stays split by concern.
```
