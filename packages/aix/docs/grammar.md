# AIX MVP grammar

```ebnf
program ::= item* EOF ;
item ::= metadata_block? definition ;
definition ::= "∴" identifier "⟦" parameter_list? "⟧" "→" type block ;
block ::= statement* "∎" | "{" statement_list? "}" ;
statement ::= "⊢" expression | "⊢" expression "⇒" expression
            | "⌁" identifier (":" type)? "≔" expression
            | "⟣" expression | expression ;
```
