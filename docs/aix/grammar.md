# AIX MVP grammar

This EBNF describes the subset accepted by the current recursive-descent parser.
Newlines are ordinary whitespace; `;` can separate statements.

```ebnf
program          ::= separator* item* EOF ;
item             ::= metadata_block? definition separator* ;
metadata_block   ::= "κ" "⟦" metadata_content "⟧" ;

definition       ::= function_definition | constant_definition ;
function_definition
                  ::= "∴" identifier parameter_block return_clause? block ;
constant_definition
                  ::= "∴" identifier ":" type "≔" expression "∎"? ;

parameter_block  ::= "⟦" parameter_list? "⟧" ;
parameter_list   ::= parameter ("," parameter)* ","? ;
parameter        ::= identifier ":" type ;
return_clause    ::= ("→" | "->") type ;

block            ::= statement* "∎"
                   | "{" separator* statement_list? "}" ;
statement_list   ::= statement (separator+ statement)* separator* ;
separator        ::= ";" ;

statement        ::= return_statement
                   | conditional_return
                   | binding
                   | assignment
                   | emit
                   | expression ;
return_statement ::= "⊢" expression ;
conditional_return
                  ::= "⊢" expression "⇒" expression ;
binding          ::= "⌁" identifier (":" type)? "≔" expression ;
assignment       ::= identifier "≔" expression ;
emit             ::= "⟣" expression ;

expression       ::= precedence-climbing binary expression ;
unary            ::= ("-" | "¬") unary | postfix ;
postfix          ::= primary call_suffix* ;
call_suffix      ::= "⟦" argument_list? "⟧" ;
argument_list    ::= expression ("," expression)* ","? ;
primary          ::= integer | float | string | boolean | "∅"
                   | identifier | "(" expression ")" ;
```

The expression operators and primitive spellings are listed in
[`syntax.md`](syntax.md). Some tokens recognized by the lexer are deliberately
outside this grammar and produce explicit unsupported-feature errors.
