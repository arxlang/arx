"""
title: Shared parser mixin base.
summary: >-
  Declare parser state and cross-mixin method contracts so the parser can be
  split by concern while keeping the public Parser API stable.
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
      bin_op_precedence:
        type: dict[str, int]
      indent_level:
        type: int
      list_scopes:
        type: list[set[str]]
      known_class_names:
        type: set[str]
      imported_type_names:
        type: set[str]
      namespace_roots:
        type: set[str]
      builtin_type_bindings:
        type: dict[str, astx.DataType]
      tensor_scopes:
        type: list[dict[str, TensorBinding | None]]
      dataframe_scopes:
        type: list[dict[str, DataFrameBinding | None]]
      return_type_scopes:
        type: list[astx.DataType]
      template_type_scopes:
        type: list[dict[str, astx.DataType]]
      type_aliases:
        type: dict[str, astx.DataType]
      value_scopes:
        type: list[set[str]]
      tokens:
        type: TokenList
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
          target:
            type: str
        """
        del target
        raise NotImplementedError

    def parse_statement(self) -> astx.AST:
        """
        title: Parse a statement without admitting it as an expression operand.
        returns:
          type: astx.AST
        """
        raise NotImplementedError

    def parse_loop_transfer(self) -> astx.BreakStmt | astx.ContinueStmt:
        """
        title: Parse a statement-only transfer to the enclosing loop.
        returns:
          type: astx.BreakStmt | astx.ContinueStmt
        """
        raise NotImplementedError

    def parse_with_stmt(self) -> astx.WithStmt:
        """
        title: Parse a resource scope with an optional entered-value binding.
        returns:
          type: astx.WithStmt
        """
        raise NotImplementedError

    def parse_assignment_or_expression(self) -> astx.AST:
        """
        title: Parse a compound statement or ordinary count-loop expression.
        returns:
          type: astx.AST
        """
        raise NotImplementedError

    def match_clause(self, kind: TokenKind, indentation: int) -> bool:
        """
        title: Match a clause without consuming an unrelated line marker.
        parameters:
          kind:
            type: TokenKind
          indentation:
            type: int
        returns:
          type: bool
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
          declared_names:
            type: tuple[str, Ellipsis]
          declared_lists:
            type: tuple[str, Ellipsis]
          declared_tensors:
            type: dict[str, TensorBinding | None] | None
          declared_dataframes:
            type: dict[str, DataFrameBinding | None] | None
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
          name:
            type: str
        """
        del name
        raise NotImplementedError

    def _name_is_shadowed(self, name: str) -> bool:
        """
        title: Return whether one visible value name shadows one class name.
        parameters:
          name:
            type: str
        returns:
          type: bool
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
          name:
            type: str
          binding:
            type: TensorBinding | None
        """
        del name
        del binding
        raise NotImplementedError

    def _is_tensor_name(self, name: str) -> bool:
        """
        title: Return whether one visible name is declared as a tensor.
        parameters:
          name:
            type: str
        returns:
          type: bool
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
          name:
            type: str
          binding:
            type: DataFrameBinding | None
        """
        del name
        del binding
        raise NotImplementedError

    def _is_dataframe_name(self, name: str) -> bool:
        """
        title: Return whether one visible name is declared as a DataFrame.
        parameters:
          name:
            type: str
        returns:
          type: bool
        """
        del name
        raise NotImplementedError

    def _declare_list_name(self, name: str) -> None:
        """
        title: Record one visible list binding in the current scope.
        parameters:
          name:
            type: str
        """
        del name
        raise NotImplementedError

    def _is_list_name(self, name: str) -> bool:
        """
        title: Return whether one visible name is declared as a list.
        parameters:
          name:
            type: str
        returns:
          type: bool
        """
        del name
        raise NotImplementedError

    def _lookup_tensor_binding(self, name: str) -> TensorBinding | None:
        """
        title: Look up one visible tensor binding by name.
        parameters:
          name:
            type: str
        returns:
          type: TensorBinding | None
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
          name:
            type: str
        returns:
          type: DataFrameBinding | None
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
          template_params:
            type: tuple[astx.TemplateParam, Ellipsis]
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
          name:
            type: str
        returns:
          type: astx.DataType | None
        """
        del name
        raise NotImplementedError

    def _push_return_type_scope(self, return_type: astx.DataType) -> None:
        """
        title: Push one active function return type.
        parameters:
          return_type:
            type: astx.DataType
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
        returns:
          type: astx.DataType | None
        """
        raise NotImplementedError

    def _class_name_from_expr(self, expr: astx.AST) -> str | None:
        """
        title: Return one class name for a static access candidate.
        parameters:
          expr:
            type: astx.AST
        returns:
          type: str | None
        """
        del expr
        raise NotImplementedError

    def _is_operator(self, value: str) -> bool:
        """
        title: Return whether the current token matches one operator.
        parameters:
          value:
            type: str
        returns:
          type: bool
        """
        del value
        raise NotImplementedError

    def _consume_operator(self, value: str) -> None:
        """
        title: Consume one expected operator token.
        parameters:
          value:
            type: str
        """
        del value
        raise NotImplementedError

    def _is_identifier_value(self, value: str) -> bool:
        """
        title: Return whether the current token matches one identifier value.
        parameters:
          value:
            type: str
        returns:
          type: bool
        """
        del value
        raise NotImplementedError

    def _consume_identifier_value(self, value: str) -> None:
        """
        title: Consume one expected contextual identifier.
        parameters:
          value:
            type: str
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
          offset:
            type: int
        returns:
          type: Token
        """
        del offset
        raise NotImplementedError

    def _token_starts_expression(self, token: Token) -> bool:
        """
        title: Return whether one token can start one expression.
        parameters:
          token:
            type: Token
        returns:
          type: bool
        """
        del token
        raise NotImplementedError

    def _lookahead_template_argument_call(
        self,
    ) -> tuple[tuple[astx.DataType, ...], Token] | None:
        """
        title: Speculatively parse one explicit template-argument list.
        returns:
          type: tuple[tuple[astx.DataType, Ellipsis], Token] | None
        """
        raise NotImplementedError

    def _parse_template_args_for_call(
        self,
    ) -> tuple[astx.DataType, ...] | None:
        """
        title: Parse explicit template arguments only for call syntax.
        returns:
          type: tuple[astx.DataType, Ellipsis] | None
        """
        raise NotImplementedError

    def get_tok_precedence(self) -> int:
        """
        title: Get the precedence of the pending binary operator token.
        returns:
          type: int
        """
        raise NotImplementedError

    def parse_expression(self) -> astx.AST:
        """
        title: Parse one expression.
        returns:
          type: astx.AST
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
          allow_docstring:
            type: bool
          declared_names:
            type: tuple[str, Ellipsis]
          declared_lists:
            type: tuple[str, Ellipsis]
          declared_tensors:
            type: dict[str, TensorBinding | None] | None
          declared_dataframes:
            type: dict[str, DataFrameBinding | None] | None
        returns:
          type: astx.Block
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
        type_context: TypeUseContext = TypeUseContext.GENERAL,
    ) -> astx.DataType:
        """
        title: Parse one type annotation.
        parameters:
          allow_template_vars:
            type: bool
          allow_union:
            type: bool
          type_context:
            type: TypeUseContext
        returns:
          type: astx.DataType
        """
        del allow_template_vars, allow_union, type_context
        raise NotImplementedError

    def is_type_alias_decl_start(self) -> bool:
        """
        title: Return whether the current token starts a type alias.
        returns:
          type: bool
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
          template_params:
            type: tuple[astx.TemplateParam, Ellipsis]
        returns:
          type: astx.FunctionDef
        """
        del template_params
        raise NotImplementedError

    def parse_import_stmt(
        self,
    ) -> astx.ImportStmt | astx.ImportFromStmt:
        """
        title: Parse one import statement.
        returns:
          type: astx.ImportStmt | astx.ImportFromStmt
        """
        raise NotImplementedError

    def parse_class_decl(
        self,
        annotations: ParsedAnnotation | None = None,
    ) -> astx.ClassDefStmt:
        """
        title: Parse one class declaration.
        parameters:
          annotations:
            type: ParsedAnnotation | None
        returns:
          type: astx.ClassDefStmt
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
          body_indent:
            type: int | None
        returns:
          type: ParsedDeclarationPrefixes
        """
        del body_indent
        raise NotImplementedError

    def parse_template_argument_list(
        self,
    ) -> tuple[astx.DataType, ...]:
        """
        title: Parse one explicit template-argument list.
        returns:
          type: tuple[astx.DataType, Ellipsis]
        """
        raise NotImplementedError

    def parse_if_stmt(self) -> astx.IfStmt:
        """
        title: Parse an if statement.
        returns:
          type: astx.IfStmt
        """
        raise NotImplementedError

    def parse_while_stmt(self) -> astx.WhileStmt:
        """
        title: Parse a while statement.
        returns:
          type: astx.WhileStmt
        """
        raise NotImplementedError

    def parse_for_stmt(self) -> astx.AST:
        """
        title: Parse a for statement.
        returns:
          type: astx.AST
        """
        raise NotImplementedError

    def parse_var_expr(
        self, name_token: Token, modifiers: ParsedAnnotation | None
    ) -> astx.VariableDeclaration:
        """
        title: Parse typed variable declarations.
        parameters:
          name_token:
            type: Token
          modifiers:
            type: ParsedAnnotation | None
        returns:
          type: astx.VariableDeclaration
        """
        del name_token, modifiers
        raise NotImplementedError

    def parse_assert_stmt(self) -> astx.AssertStmt:
        """
        title: Parse one fatal assertion statement.
        returns:
          type: astx.AssertStmt
        """
        raise NotImplementedError

    def parse_return_function(self) -> astx.FunctionReturn:
        """
        title: Parse a return statement.
        returns:
          type: astx.FunctionReturn
        """
        raise NotImplementedError

    def parse_prototype(self, expect_colon: bool) -> astx.FunctionPrototype:
        """
        title: Parse function/extern prototypes.
        parameters:
          expect_colon:
            type: bool
        returns:
          type: astx.FunctionPrototype
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
          data_type:
            type: astx.DataType
        returns:
          type: astx.Expr
        """
        del data_type
        raise NotImplementedError

    def is_declaration_start(self) -> bool:
        """
        title: Recognize a same-line name-first declaration.
        returns:
          type: bool
        """
        raise NotImplementedError

    def parse_inline_modifiers(
        self, *, allow_layout: bool = False
    ) -> ParsedAnnotation | None:
        """
        title: Parse optional whitespace-separated declaration modifiers.
        summary: >-
          Keep declaration policy outside the type. Reject unknown, repeated,
          conflicting, and unterminated groups without accepting ignored flags.
        parameters:
          allow_layout:
            type: bool
        returns:
          type: ParsedAnnotation | None
        """
        del allow_layout
        raise NotImplementedError

    def parse_declaration_head(self) -> tuple[Token, ParsedAnnotation | None]:
        """
        title: Consume a declaration name, colon, and optional modifier group.
        returns:
          type: tuple[Token, ParsedAnnotation | None]
        """
        raise NotImplementedError

    def parse_named_declaration(self) -> astx.VariableDeclaration:
        """
        title: Parse a name-first variable declaration without function syntax.
        returns:
          type: astx.VariableDeclaration
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
          modifiers:
            type: ParsedAnnotation | None
          allowed:
            type: frozenset[str]
          target:
            type: str
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
          modifiers:
            type: ParsedAnnotation | None
          expected:
            type: str
        returns:
          type: bool
        """
        del modifiers, expected
        raise NotImplementedError

    def resolve_binding_mutability(
        self,
        modifiers: ParsedAnnotation | None,
    ) -> astx.MutabilityKind:
        """
        title: >-
          Resolve Arx binding mutability for variables, fields, and parameters.
        parameters:
          modifiers:
            type: ParsedAnnotation | None
        returns:
          type: astx.MutabilityKind
        """
        del modifiers
        raise NotImplementedError

    def parse_extern(self) -> astx.FunctionPrototype:
        """
        title: Parse an extern declaration.
        returns:
          type: astx.FunctionPrototype
        """
        raise NotImplementedError
