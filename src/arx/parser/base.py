"""
title: Shared parser mixin base.
summary: >-
  Declare parser state and cross-mixin method contracts so the parser can be
  split by concern while keeping the public Parser API stable.
"""

from __future__ import annotations

from irx import astx

from arx.lexer import Token, TokenList
from arx.ndarray import NDArrayBinding
from arx.parser.state import (
    ParsedAnnotation,
    ParsedDeclarationPrefixes,
)


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
      ndarray_scopes:
        type: list[dict[str, NDArrayBinding | None]]
      return_type_scopes:
        type: list[astx.DataType]
      template_type_scopes:
        type: list[dict[str, astx.DataType]]
      value_scopes:
        type: list[set[str]]
      tokens:
        type: TokenList
    """

    bin_op_precedence: dict[str, int]
    indent_level: int
    list_scopes: list[set[str]]
    known_class_names: set[str]
    ndarray_scopes: list[dict[str, NDArrayBinding | None]]
    return_type_scopes: list[astx.DataType]
    template_type_scopes: list[dict[str, astx.DataType]]
    value_scopes: list[set[str]]
    tokens: TokenList

    def _push_value_scope(
        self,
        declared_names: tuple[str, ...] = (),
        declared_lists: tuple[str, ...] = (),
        declared_ndarrays: dict[str, NDArrayBinding | None] | None = None,
    ) -> None:
        """
        title: Push one visible-name scope.
        parameters:
          declared_names:
            type: tuple[str, Ellipsis]
          declared_lists:
            type: tuple[str, Ellipsis]
          declared_ndarrays:
            type: dict[str, NDArrayBinding | None] | None
        """
        del declared_names
        del declared_lists
        del declared_ndarrays
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

    def _declare_ndarray_name(
        self,
        name: str,
        binding: NDArrayBinding | None,
    ) -> None:
        """
        title: Record one visible ndarray binding in the current scope.
        parameters:
          name:
            type: str
          binding:
            type: NDArrayBinding | None
        """
        del name
        del binding
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

    def _is_ndarray_name(self, name: str) -> bool:
        """
        title: Return whether one visible name is declared as an ndarray.
        parameters:
          name:
            type: str
        returns:
          type: bool
        """
        del name
        raise NotImplementedError

    def _lookup_ndarray_binding(self, name: str) -> NDArrayBinding | None:
        """
        title: Look up one visible ndarray binding by name.
        parameters:
          name:
            type: str
        returns:
          type: NDArrayBinding | None
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
        declared_ndarrays: dict[str, NDArrayBinding | None] | None = None,
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
          declared_ndarrays:
            type: dict[str, NDArrayBinding | None] | None
        returns:
          type: astx.Block
        """
        del allow_docstring, declared_names, declared_lists, declared_ndarrays
        raise NotImplementedError

    def parse_type(
        self,
        *,
        allow_template_vars: bool = True,
        allow_union: bool = False,
    ) -> astx.DataType:
        """
        title: Parse one type annotation.
        parameters:
          allow_template_vars:
            type: bool
          allow_union:
            type: bool
        returns:
          type: astx.DataType
        """
        del allow_template_vars, allow_union
        raise NotImplementedError

    def parse_function(
        self,
        template_params: tuple[astx.TemplateParam, ...] = (),
    ) -> astx.FunctionDef:
        """
        title: Parse one function definition.
        parameters:
          template_params:
            type: tuple[astx.TemplateParam, Ellipsis]
        returns:
          type: astx.FunctionDef
        """
        del template_params
        raise NotImplementedError

    def parse_extern(self) -> astx.FunctionPrototype:
        """
        title: Parse one extern declaration.
        returns:
          type: astx.FunctionPrototype
        """
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
        title: Parse one if expression.
        returns:
          type: astx.IfStmt
        """
        raise NotImplementedError

    def parse_while_stmt(self) -> astx.WhileStmt:
        """
        title: Parse one while expression.
        returns:
          type: astx.WhileStmt
        """
        raise NotImplementedError

    def parse_for_stmt(self) -> astx.AST:
        """
        title: Parse one for-loop expression.
        returns:
          type: astx.AST
        """
        raise NotImplementedError

    def parse_var_expr(self) -> astx.VariableDeclaration:
        """
        title: Parse one typed variable declaration.
        returns:
          type: astx.VariableDeclaration
        """
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
        title: Parse one return expression.
        returns:
          type: astx.FunctionReturn
        """
        raise NotImplementedError

    def parse_prototype(
        self,
        expect_colon: bool,
    ) -> astx.FunctionPrototype:
        """
        title: Parse one function or extern prototype.
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
