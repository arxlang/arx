"""
title: Shared parser core.
summary: >-
  Hold parser state, scope bookkeeping, token helpers, and module-level
  orchestration for the concern-grouped parser mixins.
"""

from __future__ import annotations

import copy

from typing import cast

import astx

from arx.dataframe import DataFrameBinding
from arx.docstrings import validate_docstring
from arx.exceptions import ParserException
from arx.lexer import Token, TokenKind, TokenList
from arx.parser.base import ParserMixinBase
from arx.tensor import TensorBinding


class ParserCore(ParserMixinBase):
    """
    title: Shared parser state and orchestration.
    attributes:
      bin_op_precedence:
        type: dict[str, int]
      indent_level:
        type: int
      list_scopes:
        type: list[set[str]]
      known_class_names:
        type: set[str]
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

    bin_op_precedence: dict[str, int] = {}
    indent_level: int = 0
    list_scopes: list[set[str]]
    known_class_names: set[str]
    tensor_scopes: list[dict[str, TensorBinding | None]]
    dataframe_scopes: list[dict[str, DataFrameBinding | None]]
    return_type_scopes: list[astx.DataType]
    template_type_scopes: list[dict[str, astx.DataType]]
    type_aliases: dict[str, astx.DataType]
    value_scopes: list[set[str]]
    tokens: TokenList

    def __init__(self, tokens: TokenList = TokenList([])) -> None:
        """
        title: Instantiate the Parser object.
        parameters:
          tokens:
            type: TokenList
        """
        self.bin_op_precedence = {
            "=": 2,
            "||": 5,
            "or": 5,
            "&&": 6,
            "and": 6,
            "==": 10,
            "!=": 10,
            "<": 10,
            ">": 10,
            "<=": 10,
            ">=": 10,
            "+": 20,
            "-": 20,
            "*": 40,
            "/": 40,
        }
        self.indent_level = 0
        self.list_scopes = [set()]
        self.known_class_names = set()
        self.tensor_scopes = [{}]
        self.dataframe_scopes = [{}]
        self.return_type_scopes = []
        self.template_type_scopes = []
        self.type_aliases = {}
        self.value_scopes = [set()]
        self.tokens = tokens

    def clean(self) -> None:
        """
        title: Reset the Parser static variables.
        """
        self.indent_level = 0
        self.list_scopes = [set()]
        self.known_class_names = set()
        self.tensor_scopes = [{}]
        self.dataframe_scopes = [{}]
        self.return_type_scopes = []
        self.template_type_scopes = []
        self.type_aliases = {}
        self.value_scopes = [set()]
        self.tokens = TokenList([])

    def parse(
        self, tokens: TokenList, module_name: str = "main"
    ) -> astx.Module:
        """
        title: Parse the input code.
        parameters:
          tokens:
            type: TokenList
          module_name:
            type: str
        returns:
          type: astx.Module
        """
        self.clean()
        self.known_class_names = self._collect_class_names(tokens)
        self.tokens = tokens

        tree: astx.Module = astx.Module(module_name)
        self.tokens.get_next_token()

        if self.tokens.cur_tok.kind == TokenKind.not_initialized:
            self.tokens.get_next_token()

        allow_module_docstring = True
        while True:
            if self.tokens.cur_tok.kind == TokenKind.eof:
                break
            if self.tokens.cur_tok.kind == TokenKind.docstring:
                if (
                    allow_module_docstring
                    and self.tokens.cur_tok.location.line == 0
                    and self.tokens.cur_tok.location.col == 1
                ):
                    try:
                        validate_docstring(self.tokens.cur_tok.value)
                    except ValueError as err:
                        raise ParserException(
                            f"Invalid module docstring: {err}"
                        ) from err
                    self.tokens.get_next_token()
                    allow_module_docstring = False
                    continue
                raise ParserException(
                    "Module docstrings are only allowed as the first "
                    "statement starting at line 1, column 1."
                )

            if self._is_operator(";"):
                self.tokens.get_next_token()
                allow_module_docstring = False
                continue

            if self._is_operator("@"):
                prefixes = self.parse_declaration_prefixes()
                if self.tokens.cur_tok.kind == TokenKind.kw_class:
                    if prefixes.template_params:
                        raise ParserException(
                            "template parameter blocks are only allowed "
                            "before functions or methods"
                        )
                    tree.nodes.append(
                        self.parse_class_decl(prefixes.modifiers)
                    )
                    allow_module_docstring = False
                    continue

                if prefixes.modifiers is not None:
                    raise ParserException(
                        "annotation must be followed by a declaration"
                    )
                if prefixes.template_params:
                    if self.tokens.cur_tok.kind != TokenKind.kw_function:
                        raise ParserException(
                            "template parameter blocks are only allowed "
                            "before functions or methods"
                        )
                    tree.nodes.append(
                        self.parse_function(prefixes.template_params)
                    )
                    allow_module_docstring = False
                    continue

                raise ParserException(
                    "annotation must be followed by a declaration"
                )

            if self.tokens.cur_tok.kind == TokenKind.kw_import:
                tree.nodes.append(self.parse_import_stmt())
                allow_module_docstring = False
                continue

            if self.is_type_alias_decl_start():
                self.parse_type_alias_decl()
                allow_module_docstring = False
                continue

            if self.tokens.cur_tok.kind == TokenKind.kw_function:
                tree.nodes.append(self.parse_function())
                allow_module_docstring = False
                continue

            if self.tokens.cur_tok.kind == TokenKind.kw_extern:
                tree.nodes.append(self.parse_extern())
                allow_module_docstring = False
                continue

            if self.tokens.cur_tok.kind == TokenKind.kw_class:
                tree.nodes.append(self.parse_class_decl())
                allow_module_docstring = False
                continue

            tree.nodes.append(self.parse_expression())
            allow_module_docstring = False

        return tree

    def _push_value_scope(
        self,
        declared_names: tuple[str, ...] = (),
        declared_lists: tuple[str, ...] = (),
        declared_tensors: dict[str, TensorBinding | None] | None = None,
        declared_dataframes: (
            dict[str, DataFrameBinding | None] | None
        ) = None,
    ) -> None:
        """
        title: Push one visible-name scope for expression disambiguation.
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
        self.value_scopes.append(set(declared_names))
        self.list_scopes.append(set(declared_lists))
        self.tensor_scopes.append(dict(declared_tensors or {}))
        self.dataframe_scopes.append(dict(declared_dataframes or {}))

    def _pop_value_scope(self) -> None:
        """
        title: Pop the most recent visible-name scope.
        """
        self.value_scopes.pop()
        self.list_scopes.pop()
        self.tensor_scopes.pop()
        self.dataframe_scopes.pop()

    def _declare_value_name(self, name: str) -> None:
        """
        title: Record one visible value name in the current scope.
        parameters:
          name:
            type: str
        """
        self.value_scopes[-1].add(name)

    def _name_is_shadowed(self, name: str) -> bool:
        """
        title: Return whether a visible value binding shadows a class name.
        parameters:
          name:
            type: str
        returns:
          type: bool
        """
        for value_scope in reversed(self.value_scopes):
            if name in value_scope:
                return True
        return False

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
        self.tensor_scopes[-1][name] = binding

    def _is_tensor_name(self, name: str) -> bool:
        """
        title: Return whether one visible name is declared as a tensor.
        parameters:
          name:
            type: str
        returns:
          type: bool
        """
        for value_scope, tensor_scope in zip(
            reversed(self.value_scopes),
            reversed(self.tensor_scopes),
            strict=True,
        ):
            if name in tensor_scope:
                return True
            if name in value_scope:
                return False
        return False

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
        self.dataframe_scopes[-1][name] = binding

    def _is_dataframe_name(self, name: str) -> bool:
        """
        title: Return whether one visible name is declared as a DataFrame.
        parameters:
          name:
            type: str
        returns:
          type: bool
        """
        for value_scope, dataframe_scope in zip(
            reversed(self.value_scopes),
            reversed(self.dataframe_scopes),
            strict=True,
        ):
            if name in dataframe_scope:
                return True
            if name in value_scope:
                return False
        return False

    def _declare_list_name(self, name: str) -> None:
        """
        title: Record one visible list binding in the current scope.
        parameters:
          name:
            type: str
        """
        self.list_scopes[-1].add(name)

    def _is_list_name(self, name: str) -> bool:
        """
        title: Return whether one visible name is declared as a list.
        parameters:
          name:
            type: str
        returns:
          type: bool
        """
        for value_scope, list_scope in zip(
            reversed(self.value_scopes),
            reversed(self.list_scopes),
            strict=True,
        ):
            if name in list_scope:
                return True
            if name in value_scope:
                return False
        return False

    def _lookup_tensor_binding(self, name: str) -> TensorBinding | None:
        """
        title: Return one visible tensor binding by name.
        parameters:
          name:
            type: str
        returns:
          type: TensorBinding | None
        """
        for value_scope, tensor_scope in zip(
            reversed(self.value_scopes),
            reversed(self.tensor_scopes),
            strict=True,
        ):
            if name in tensor_scope:
                return tensor_scope[name]
            if name in value_scope:
                return None
        return None

    def _lookup_dataframe_binding(
        self,
        name: str,
    ) -> DataFrameBinding | None:
        """
        title: Return one visible DataFrame binding by name.
        parameters:
          name:
            type: str
        returns:
          type: DataFrameBinding | None
        """
        for value_scope, dataframe_scope in zip(
            reversed(self.value_scopes),
            reversed(self.dataframe_scopes),
            strict=True,
        ):
            if name in dataframe_scope:
                return dataframe_scope[name]
            if name in value_scope:
                return None
        return None

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
        self.template_type_scopes.append(
            {
                param.name: copy.deepcopy(param.bound)
                for param in template_params
            }
        )

    def _pop_template_scope(self) -> None:
        """
        title: Pop the most recent template-type scope.
        """
        self.template_type_scopes.pop()

    def _lookup_template_bound(self, name: str) -> astx.DataType | None:
        """
        title: Look up one visible template-type bound by name.
        parameters:
          name:
            type: str
        returns:
          type: astx.DataType | None
        """
        for scope in reversed(self.template_type_scopes):
            bound = scope.get(name)
            if bound is not None:
                return copy.deepcopy(bound)
        return None

    def _push_return_type_scope(self, return_type: astx.DataType) -> None:
        """
        title: Push one active function return type.
        parameters:
          return_type:
            type: astx.DataType
        """
        self.return_type_scopes.append(return_type)

    def _pop_return_type_scope(self) -> None:
        """
        title: Pop the most recent active function return type.
        """
        self.return_type_scopes.pop()

    def _current_return_type(self) -> astx.DataType | None:
        """
        title: Return the active function return type when one exists.
        returns:
          type: astx.DataType | None
        """
        if not self.return_type_scopes:
            return None
        return self.return_type_scopes[-1]

    def _collect_class_names(self, tokens: TokenList) -> set[str]:
        """
        title: Collect declared class names from the token stream.
        parameters:
          tokens:
            type: TokenList
        returns:
          type: set[str]
        """
        class_names: set[str] = set()
        for index, token in enumerate(tokens.tokens[:-1]):
            if token.kind != TokenKind.kw_class:
                continue
            next_token = tokens.tokens[index + 1]
            if next_token.kind == TokenKind.identifier:
                class_names.add(cast(str, next_token.value))
        return class_names

    def _class_name_from_expr(self, expr: astx.AST) -> str | None:
        """
        title: Return the referenced class name for static access candidates.
        parameters:
          expr:
            type: astx.AST
        returns:
          type: str | None
        """
        if not isinstance(expr, astx.Identifier):
            return None
        if expr.name not in self.known_class_names:
            return None
        if self._name_is_shadowed(expr.name):
            return None
        return expr.name

    def _is_operator(self, value: str) -> bool:
        """
        title: Check whether the current token matches an operator.
        parameters:
          value:
            type: str
        returns:
          type: bool
        """
        return self.tokens.cur_tok == Token(
            kind=TokenKind.operator, value=value
        )

    def _consume_operator(self, value: str) -> None:
        """
        title: Consume the expected operator token.
        parameters:
          value:
            type: str
        """
        if not self._is_operator(value):
            raise ParserException(
                f"Expected operator '{value}', got '{self.tokens.cur_tok}'."
            )
        self.tokens.get_next_token()

    def _is_identifier_value(self, value: str) -> bool:
        """
        title: Return whether the current token matches one identifier value.
        parameters:
          value:
            type: str
        returns:
          type: bool
        """
        return (
            self.tokens.cur_tok.kind == TokenKind.identifier
            and self.tokens.cur_tok.value == value
        )

    def _consume_identifier_value(self, value: str) -> None:
        """
        title: Consume one contextual identifier token.
        parameters:
          value:
            type: str
        """
        if not self._is_identifier_value(value):
            raise ParserException(
                f"Expected '{value}', got '{self.tokens.cur_tok}'."
            )
        self.tokens.get_next_token()

    def _skip_import_layout(self) -> None:
        """
        title: Consume indentation tokens used only for grouped imports.
        """
        while self.tokens.cur_tok.kind == TokenKind.indent:
            self.tokens.get_next_token()

    def _skip_template_layout(self) -> None:
        """
        title: Consume indentation tokens used only inside template blocks.
        """
        while self.tokens.cur_tok.kind == TokenKind.indent:
            self.tokens.get_next_token()

    def _peek_token(self, offset: int = 0) -> Token:
        """
        title: Peek one token ahead without consuming it.
        parameters:
          offset:
            type: int
        returns:
          type: Token
        """
        index = self.tokens.position + offset
        if index >= len(self.tokens.tokens):
            return Token(TokenKind.eof, "")
        return self.tokens.tokens[index]

    def _token_starts_expression(self, token: Token) -> bool:
        """
        title: Return whether one token can start an expression.
        parameters:
          token:
            type: Token
        returns:
          type: bool
        """
        if token.kind in {
            TokenKind.identifier,
            TokenKind.int_literal,
            TokenKind.float_literal,
            TokenKind.string_literal,
            TokenKind.char_literal,
            TokenKind.bool_literal,
            TokenKind.none_literal,
            TokenKind.kw_if,
            TokenKind.kw_while,
            TokenKind.kw_for,
            TokenKind.kw_var,
            TokenKind.kw_assert,
            TokenKind.kw_return,
        }:
            return True

        return token.kind == TokenKind.operator and token.value in {
            "(",
            "[",
            "+",
            "-",
            "!",
            "++",
            "--",
            ";",
        }

    def _lookahead_template_argument_call(
        self,
    ) -> tuple[tuple[astx.DataType, ...], Token] | None:
        """
        title: Speculatively parse one explicit template-argument list.
        returns:
          type: tuple[tuple[astx.DataType, Ellipsis], Token] | None
        """
        if not self._is_operator("<"):
            return None

        saved_position = self.tokens.position
        saved_token = self.tokens.cur_tok
        try:
            template_args = self.parse_template_argument_list()
            return template_args, self.tokens.cur_tok
        except ParserException:
            return None
        finally:
            self.tokens.position = saved_position
            self.tokens.cur_tok = saved_token

    def _parse_template_args_for_call(
        self,
    ) -> tuple[astx.DataType, ...] | None:
        """
        title: Parse explicit template arguments only for call syntax.
        returns:
          type: tuple[astx.DataType, Ellipsis] | None
        """
        lookahead = self._lookahead_template_argument_call()
        if lookahead is None:
            return None

        _, follow_token = lookahead
        if follow_token != Token(TokenKind.operator, "("):
            if self._token_starts_expression(follow_token):
                return None
            raise ParserException(
                "explicit template arguments are only allowed on call "
                "expressions"
            )
        return self.parse_template_argument_list()

    def get_tok_precedence(self) -> int:
        """
        title: Get the precedence of the pending binary operator token.
        returns:
          type: int
        """
        return self.bin_op_precedence.get(self.tokens.cur_tok.value, -1)
