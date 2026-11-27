"""
title: Shared parser mixin base.
summary: Declare parser state and cross-mixin method contracts so the parser
  can be split by concern while keeping the public Parser API stable.
"""

from __future__ import annotations

import astx

from arx.dataframe import DataFrameBinding
from arx.lexer import Token, TokenKind, TokenList
from arx.parser.state import (
    ParsedAnnotation,
    ParsedDeclarationPrefixes,
    TypeUseContext,
)
from arx.tensor import TensorBinding


class ParserMixinBase:
    """
    title: Shared parser mixin contract.
    attributes:
      bin_op_precedence: Bin op precedence.
      indent_level: Indent level.
      list_scopes: List scopes.
      known_class_names: Known class names.
      imported_type_names: Imported type names.
      namespace_roots: Namespace roots.
      builtin_type_bindings: Builtin type bindings.
      tensor_scopes: Tensor scopes.
      dataframe_scopes: Dataframe scopes.
      return_type_scopes: Return type scopes.
      template_type_scopes: Template type scopes.
      type_aliases: Type aliases.
      value_scopes: Value scopes.
      tokens: Tokens in source order.
    """

    bin_op_precedence: dict[str, int]
    indent_level: int
    list_scopes: list[set[str]]
    known_class_names: set[str]
    imported_type_names: set[str]
    namespace_roots: set[str]
    builtin_type_bindings: dict[str, astx.DataType]
    tensor_scopes: list[dict[str, TensorBinding | None]]
    dataframe_scopes: list[dict[str, DataFrameBinding | None]]
    return_type_scopes: list[astx.DataType]
    template_type_scopes: list[dict[str, astx.DataType]]
    type_aliases: dict[str, astx.DataType]
    value_scopes: list[set[str]]
    tokens: TokenList

    def validate_type_declaration_name(self, target: str) -> None:
        """
        title: Reject inference markers as names of declared types.
        parameters:
          target: Destination of the operation.
        """
        del target
        raise NotImplementedError

    def parse_statement(self) -> astx.AST:
        """
        title: Parse a statement without admitting it as an expression operand.
        returns: Parsed a statement without admitting it as an expression
          operand.
        """
        raise NotImplementedError

    def parse_loop_transfer(self) -> astx.BreakStmt | astx.ContinueStmt:
        """
        title: Parse a statement-only transfer to the enclosing loop.
        returns: Parsed a statement-only transfer to the enclosing loop.
        """
        raise NotImplementedError

    def parse_with_stmt(self) -> astx.WithStmt:
        """
        title: Parse a resource scope with an optional entered-value
          binding.
        returns: Parsed a resource scope with an optional entered-value
          binding.
        """
        raise NotImplementedError

    def parse_assignment_or_expression(self) -> astx.AST:
        """
        title: Parse a compound statement or ordinary count-loop expression.
        returns: Parsed a compound statement or ordinary count-loop expression.
        """
        raise NotImplementedError

    def match_clause(self, kind: TokenKind, indentation: int) -> bool:
        """
        title: Match a clause without consuming an unrelated line marker.
        parameters:
          kind: Kind of value or operation.
          indentation: Indentation.
        returns: 'Result of this operation: match a clause without consuming
          an unrelated line marker.'
        """
        del kind
        del indentation
        raise NotImplementedError

    def _push_value_scope(
        self,
        declared_names: tuple[str, ...] = (),
        declared_lists: tuple[str, ...] = (),
        declared_tensors: dict[str, TensorBinding | None] | None = None,
        declared_dataframes: dict[str, DataFrameBinding | None] | None = None,
    ) -> None:
        """
        title: Push one visible-name scope.
        parameters:
          declared_names: Declared names.
          declared_lists: Declared lists.
          declared_tensors: Declared tensors.
          declared_dataframes: Declared dataframes.
        """
        del declared_names
        del declared_lists
        del declared_tensors
        del declared_dataframes
        raise NotImplementedError

    def _pop_value_scope(self) -> None:
        """
        title: Pop the most recent visible-name scope.
        """
        raise NotImplementedError

    def _declare_value_name(self, name: str) -> None:
        """
        title: Record one visible value name in the current scope.
        parameters:
          name: Name identifying the declaration or operation.
        """
        del name
        raise NotImplementedError

    def _name_is_shadowed(self, name: str) -> bool:
        """
        title: Return whether one visible value name shadows one class name.
        parameters:
          name: Name identifying the declaration or operation.
        returns: Whether one visible value name shadows one class name.
        """
        del name
        raise NotImplementedError

    def _declare_tensor_name(
        self,
        name: str,
        binding: TensorBinding | None,
    ) -> None:
        """
        title: Record one visible tensor binding in the current scope.
        parameters:
          name: Name identifying the declaration or operation.
          binding: Resolved binding for the operation.
        """
        del name
        del binding
        raise NotImplementedError

    def _is_tensor_name(self, name: str) -> bool:
        """
        title: Return whether one visible name is declared as a tensor.
        parameters:
          name: Name identifying the declaration or operation.
        returns: Whether one visible name is declared as a tensor.
        """
        del name
        raise NotImplementedError

    def _declare_dataframe_name(
        self,
        name: str,
        binding: DataFrameBinding | None,
    ) -> None:
        """
        title: Record one visible DataFrame binding in the current scope.
        parameters:
          name: Name identifying the declaration or operation.
          binding: Resolved binding for the operation.
        """
        del name
        del binding
        raise NotImplementedError

    def _is_dataframe_name(self, name: str) -> bool:
        """
        title: Return whether one visible name is declared as a DataFrame.
        parameters:
          name: Name identifying the declaration or operation.
        returns: Whether one visible name is declared as a DataFrame.
        """
        del name
        raise NotImplementedError

    def _declare_list_name(self, name: str) -> None:
        """
        title: Record one visible list binding in the current scope.
        parameters:
          name: Name identifying the declaration or operation.
        """
        del name
        raise NotImplementedError

    def _is_list_name(self, name: str) -> bool:
        """
        title: Return whether one visible name is declared as a list.
        parameters:
          name: Name identifying the declaration or operation.
        returns: Whether one visible name is declared as a list.
        """
        del name
        raise NotImplementedError

    def _lookup_tensor_binding(self, name: str) -> TensorBinding | None:
        """
        title: Look up one visible tensor binding by name.
        parameters:
          name: Name identifying the declaration or operation.
        returns: 'Result of this operation: look up one visible tensor binding
          by name.'
        """
        del name
        raise NotImplementedError

    def _lookup_dataframe_binding(
        self,
        name: str,
    ) -> DataFrameBinding | None:
        """
        title: Look up one visible DataFrame binding by name.
        parameters:
          name: Name identifying the declaration or operation.
        returns: 'Result of this operation: look up one visible DataFrame
          binding by name.'
        """
        del name
        raise NotImplementedError

    def _push_template_scope(
        self,
        template_params: tuple[astx.TemplateParam, ...] = (),
    ) -> None:
        """
        title: Push one template-type scope.
        parameters:
          template_params: Template parameters declared by the callable.
        """
        del template_params
        raise NotImplementedError

    def _pop_template_scope(self) -> None:
        """
        title: Pop the most recent template-type scope.
        """
        raise NotImplementedError

    def _lookup_template_bound(self, name: str) -> astx.DataType | None:
        """
        title: Look up one visible template bound by name.
        parameters:
          name: Name identifying the declaration or operation.
        returns: 'Result of this operation: look up one visible template
          bound by name.'
        """
        del name
        raise NotImplementedError

    def _push_return_type_scope(self, return_type: astx.DataType) -> None:
        """
        title: Push one active function return type.
        parameters:
          return_type: Declared result type.
        """
        del return_type
        raise NotImplementedError

    def _pop_return_type_scope(self) -> None:
        """
        title: Pop the most recent active function return type.
        """
        raise NotImplementedError

    def _current_return_type(self) -> astx.DataType | None:
        """
        title: Return the active function return type when one exists.
        returns: The active function return type when one exists.
        """
        raise NotImplementedError

    def _class_name_from_expr(self, expr: astx.AST) -> str | None:
        """
        title: Return one class name for a static access candidate.
        parameters:
          expr: Expression to process.
        returns: One class name for a static access candidate.
        """
        del expr
        raise NotImplementedError

    def _is_operator(self, value: str) -> bool:
        """
        title: Return whether the current token matches one operator.
        parameters:
          value: Value to process.
        returns: Whether the current token matches one operator.
        """
        del value
        raise NotImplementedError

    def _consume_operator(self, value: str) -> None:
        """
        title: Consume one expected operator token.
        parameters:
          value: Value to process.
        """
        del value
        raise NotImplementedError

    def _is_identifier_value(self, value: str) -> bool:
        """
        title: Return whether the current token matches one identifier value.
        parameters:
          value: Value to process.
        returns: Whether the current token matches one identifier value.
        """
        del value
        raise NotImplementedError

    def _consume_identifier_value(self, value: str) -> None:
        """
        title: Consume one expected contextual identifier.
        parameters:
          value: Value to process.
        """
        del value
        raise NotImplementedError

    def _skip_import_layout(self) -> None:
        """
        title: Consume indentation tokens used only for grouped imports.
        """
        raise NotImplementedError

    def _skip_template_layout(self) -> None:
        """
        title: Consume indentation tokens used only inside template blocks.
        """
        raise NotImplementedError

    def _peek_token(self, offset: int = 0) -> Token:
        """
        title: Peek one token ahead without consuming it.
        parameters:
          offset: Offset within the data.
        returns: 'Result of this operation: peek one token ahead without
          consuming it.'
        """
        del offset
        raise NotImplementedError

    def _token_starts_expression(self, token: Token) -> bool:
        """
        title: Return whether one token can start one expression.
        parameters:
          token: Token being processed.
        returns: Whether one token can start one expression.
        """
        del token
        raise NotImplementedError

    def _lookahead_template_argument_call(
        self,
    ) -> tuple[tuple[astx.DataType, ...], Token] | None:
        """
        title: Speculatively parse one explicit template-argument
          list.
        returns: 'Result of this operation: speculatively parse one
          explicit template-argument list.'
        """
        raise NotImplementedError

    def _parse_template_args_for_call(
        self,
    ) -> tuple[astx.DataType, ...] | None:
        """
        title: Parse explicit template arguments only for call syntax.
        returns: Parsed explicit template arguments only for call syntax.
        """
        raise NotImplementedError

    def get_tok_precedence(self) -> int:
        """
        title: Get the precedence of the pending binary operator token.
        returns: The precedence of the pending binary operator token.
        """
        raise NotImplementedError

    def parse_expression(self) -> astx.AST:
        """
        title: Parse one expression.
        returns: Parsed one expression.
        """
        raise NotImplementedError

    def parse_block(
        self,
        allow_docstring: bool = False,
        declared_names: tuple[str, ...] = (),
        declared_lists: tuple[str, ...] = (),
        declared_tensors: dict[str, TensorBinding | None] | None = None,
        declared_dataframes: dict[str, DataFrameBinding | None] | None = None,
    ) -> astx.Block:
        """
        title: Parse one block of nodes.
        parameters:
          allow_docstring: Whether to use allow docstring.
          declared_names: Declared names.
          declared_lists: Declared lists.
          declared_tensors: Declared tensors.
          declared_dataframes: Declared dataframes.
        returns: Parsed one block of nodes.
        """
        del (
            allow_docstring,
            declared_names,
            declared_lists,
            declared_tensors,
            declared_dataframes,
        )
        raise NotImplementedError

    def parse_type(
        self,
        *,
        allow_template_vars: bool = True,
        allow_union: bool = False,
        allow_nullable_union: bool = True,
        type_context: TypeUseContext = TypeUseContext.GENERAL,
    ) -> astx.DataType:
        """
        title: Parse one type annotation.
        parameters:
          allow_template_vars: Whether to use allow template vars.
          allow_union: Whether to consume unparenthesized union members.
          allow_nullable_union: Whether to consume nullable shorthand.
          type_context: Type context.
        returns: Parsed one type annotation.
        """
        del (
            allow_template_vars,
            allow_union,
            allow_nullable_union,
            type_context,
        )
        raise NotImplementedError

    def is_type_alias_decl_start(self) -> bool:
        """
        title: Return whether the current token starts a type alias.
        returns: Whether the current token starts a type alias.
        """
        raise NotImplementedError

    def parse_type_alias_decl(self) -> None:
        """
        title: Parse one top-level type alias declaration.
        """
        raise NotImplementedError

    def parse_function(
        self,
        template_params: tuple[astx.TemplateParam, ...] = (),
    ) -> astx.FunctionDef:
        """
        title: Parse a function definition.
        parameters:
          template_params: Template parameters declared by the callable.
        returns: Parsed a function definition.
        """
        del template_params
        raise NotImplementedError

    def parse_import_stmt(
        self,
    ) -> astx.ImportStmt | astx.ImportFromStmt:
        """
        title: Parse one import statement.
        returns: Parsed one import statement.
        """
        raise NotImplementedError

    def parse_class_decl(
        self,
        annotations: ParsedAnnotation | None = None,
    ) -> astx.ClassDefStmt:
        """
        title: Parse one class declaration.
        parameters:
          annotations: Annotations.
        returns: Parsed one class declaration.
        """
        del annotations
        raise NotImplementedError

    def parse_declaration_prefixes(
        self,
        *,
        body_indent: int | None = None,
    ) -> ParsedDeclarationPrefixes:
        """
        title: Parse declaration prefixes before one declaration.
        parameters:
          body_indent: Body indent.
        returns: Parsed declaration prefixes before one declaration.
        """
        del body_indent
        raise NotImplementedError

    def parse_template_argument_list(
        self,
    ) -> tuple[astx.DataType, ...]:
        """
        title: Parse one explicit template-argument list.
        returns: Parsed one explicit template-argument list.
        """
        raise NotImplementedError

    def parse_if_stmt(self) -> astx.IfStmt:
        """
        title: Parse an if statement.
        returns: Parsed an if statement.
        """
        raise NotImplementedError

    def parse_while_stmt(self) -> astx.WhileStmt:
        """
        title: Parse a while statement.
        returns: Parsed a while statement.
        """
        raise NotImplementedError

    def parse_for_stmt(self) -> astx.AST:
        """
        title: Parse a for statement.
        returns: Parsed a for statement.
        """
        raise NotImplementedError

    def parse_var_expr(
        self, name_token: Token, modifiers: ParsedAnnotation | None
    ) -> astx.VariableDeclaration:
        """
        title: Parse typed variable declarations.
        parameters:
          name_token: Name token.
          modifiers: Modifiers.
        returns: Parsed typed variable declarations.
        """
        del name_token, modifiers
        raise NotImplementedError

    def parse_assert_stmt(self) -> astx.AssertStmt:
        """
        title: Parse one fatal assertion statement.
        returns: Parsed one fatal assertion statement.
        """
        raise NotImplementedError

    def parse_return_function(self) -> astx.FunctionReturn:
        """
        title: Parse a return statement.
        returns: Parsed a return statement.
        """
        raise NotImplementedError

    def parse_prototype(self, expect_colon: bool) -> astx.FunctionPrototype:
        """
        title: Parse function/extern prototypes.
        parameters:
          expect_colon: Whether to use expect colon.
        returns: Parsed function/extern prototypes.
        """
        del expect_colon
        raise NotImplementedError

    def _default_value_for_type(
        self,
        data_type: astx.DataType,
    ) -> astx.Expr:
        """
        title: Build one default initializer for one typed declaration.
        parameters:
          data_type: Declared data type.
        returns: Constructed one default initializer for one typed declaration.
        """
        del data_type
        raise NotImplementedError

    def is_declaration_start(self) -> bool:
        """
        title: Recognize a same-line name-first declaration.
        returns: 'Result of this operation: recognize a same-line name-first
          declaration.'
        """
        raise NotImplementedError

    def parse_inline_modifiers(
        self, *, allow_layout: bool = False
    ) -> ParsedAnnotation | None:
        """
        title: Parse optional whitespace-separated declaration modifiers.
        summary: Keep declaration policy outside the type. Reject unknown,
          repeated, conflicting, and unterminated groups without accepting
          ignored flags.
        parameters:
          allow_layout: Whether to use allow layout.
        returns: Parsed optional whitespace-separated declaration modifiers.
        """
        del allow_layout
        raise NotImplementedError

    def parse_declaration_head(self) -> tuple[Token, ParsedAnnotation | None]:
        """
        title: Consume a declaration name, colon, and optional modifier group.
        returns: 'Result of this operation: consume a declaration name, colon,
          and optional modifier group.'
        """
        raise NotImplementedError

    def parse_named_declaration(self) -> astx.VariableDeclaration:
        """
        title: Parse a name-first variable declaration without function syntax.
        returns: Parsed a name-first variable declaration without function
          syntax.
        """
        raise NotImplementedError

    def _validate_modifier_target(
        self,
        modifiers: ParsedAnnotation | None,
        allowed: frozenset[str],
        target: str,
    ) -> None:
        """
        title: Validate one modifier list against a declaration target.
        parameters:
          modifiers: Modifiers.
          allowed: Allowed.
          target: Destination of the operation.
        """
        del modifiers, allowed, target
        raise NotImplementedError

    def _has_modifier(
        self,
        modifiers: ParsedAnnotation | None,
        expected: str,
    ) -> bool:
        """
        title: Return whether one modifier is present.
        parameters:
          modifiers: Modifiers.
          expected: Expected result for this case.
        returns: Whether one modifier is present.
        """
        del modifiers, expected
        raise NotImplementedError

    def resolve_binding_mutability(
        self,
        modifiers: ParsedAnnotation | None,
    ) -> astx.MutabilityKind:
        """
        title: Resolve Arx binding mutability for variables, fields, and
          parameters.
        parameters:
          modifiers: Modifiers.
        returns: Resolved arx binding mutability for variables, fields, and
          parameters.
        """
        del modifiers
        raise NotImplementedError

    def parse_extern(
        self, template_params: tuple[astx.TemplateParam, ...] = ()
    ) -> astx.FunctionPrototype:
        """
        title: Parse an extern declaration.
        parameters:
          template_params: Template parameters declared by the callable.
        returns: Parsed an extern declaration.
        """
        raise NotImplementedError
