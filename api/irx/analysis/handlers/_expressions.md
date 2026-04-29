---
title: irx.analysis.handlers._expressions
---

# `irx.analysis.handlers._expressions`

Source: `packages/irx/src/irx/analysis/handlers/_expressions/__init__.py`

```yaml
title: Expression-oriented semantic visitors.
summary: >-
  Resolve lexical identifiers, visible function names, and expression typing
  rules while delegating the implementation to smaller concern-focused mixins.
```

## Classes

### `ExpressionVisitorMixin(ExpressionModuleVisitorMixin, ExpressionMutationVisitorMixin, ExpressionClassVisitorMixin, ExpressionDataFrameVisitorMixin, ExpressionOperatorVisitorMixin, ExpressionArrayVisitorMixin, ExpressionTensorBufferVisitorMixin, ExpressionLiteralVisitorMixin)`

```yaml
title: Expression-oriented semantic visitors.
summary: >-
  Compose the expression-focused semantic mixins so the analyzer keeps the
  same visitor surface while the implementation stays split by concern.
```
