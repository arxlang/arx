# Reserved APL-inspired operators

AIX reserves symbols such as `⍴`, `⍳`, `¨`, `∘`, `↑`, `↓`, `⍋`, `⍒`, `∊`, and
`∪`. The lexer recognizes these symbols, but the parser raises a clear
unsupported-feature error in the MVP.
