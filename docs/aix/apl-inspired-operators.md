# Reserved APL-inspired operators

AIX reserves a vocabulary for future array-oriented syntax, but reserving a
glyph is not an implementation claim.

| Reserved glyph | Conventional inspiration only          |
| -------------- | -------------------------------------- |
| `⍴`            | shape/reshape                          |
| `⍳`            | index generation                       |
| `¨`            | each/map                               |
| `∘`            | composition/outer product              |
| `↑`, `↓`       | take/drop                              |
| `⍋`, `⍒`       | grade up/down                          |
| `∊`            | membership/enlist                      |
| `∪`            | unique/union                           |
| `∑`, `∫`, `∂`  | aggregate/calculus-inspired operations |

The lexer emits these as symbolic-operator tokens. The parser then raises a
located error explaining that the operator is unsupported. No elementwise,
shape, reduction, Arrow, or IRx lowering semantics are assigned yet.

This explicit rejection prevents programs from silently receiving semantics
borrowed from APL or another array language. Each operator needs a documented
type rule, ASTx representation, and IRx lowering before it becomes executable.
