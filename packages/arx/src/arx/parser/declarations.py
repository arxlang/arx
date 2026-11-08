"""
title: Declaration parser mixin.
summary: >-
  Parse functions, classes, templates, modifiers, and related declaration
  constructs.
"""

from __future__ import annotations

from typing import cast

import astx

from astx import SourceLocation
from astx.types import AnyType

from arx.dataframe import (
    DataFrameBinding,
    is_dataframe_type,
)
from arx.dataframe import (
    binding_from_type as dataframe_binding_from_type,
)
from arx.dataframe import (
    coerce_expression as coerce_dataframe_expression,
)
from arx.docstrings import validate_docstring
from arx.exceptions import ParserException
from arx.lexer import Token, TokenKind
from arx.parser.base import ParserMixinBase
from arx.parser.state import (
    BINDING_MUTABILITY_MODIFIERS,
    CLASS_ALLOWED_MODIFIERS,
    FIELD_ALLOWED_MODIFIERS,
    METHOD_ALLOWED_MODIFIERS,
    MUTABILITY_NAME_MAP,
    SUPPORTED_MODIFIERS,
    VISIBILITY_MODIFIERS,
    VISIBILITY_NAME_MAP,
    ParsedAnnotation,
    ParsedDeclarationPrefixes,
    TypeUseContext,
)
from arx.tensor import (
    TensorBinding,
    binding_from_type,
    is_tensor_type,
)


class DeclarationParserMixin(ParserMixinBase):
    """
    title: Declaration parser mixin.
    """

    def is_declaration_start(self) -> bool:
        """
        title: Recognize a same-line name-first declaration.
        returns:
          type: bool
        """
        token = self.tokens.cur_tok
        following = self._peek_token()
        return (
            token.kind == TokenKind.identifier
            and following == Token(TokenKind.operator, ":")
            and following.location.line == token.location.line
        )

    def parse_inline_modifiers(self) -> ParsedAnnotation | None:
        """
        title: Parse optional whitespace-separated declaration modifiers.
        summary: >-
          Keep declaration policy outside the type. Reject unknown, repeated,
          conflicting, and unterminated groups without accepting ignored flags.
        returns:
          type: ParsedAnnotation | None
        """
        first = self.tokens.cur_tok
        if self._is_operator("::"):
            raise ParserException(
                "Empty modifier group before '::'.", first.location
            )
        index = self.tokens.position - 1
        tokens = self.tokens.tokens
        names: list[str] = []
        while index < len(tokens):
            token = tokens[index]
            if token.location.line != first.location.line:
                break
            if token == Token(TokenKind.operator, "::"):
                break
            if token.kind not in {
                TokenKind.identifier,
                TokenKind.kw_var,
                TokenKind.kw_const,
                TokenKind.kw_extern,
            }:
                break
            names.append(cast(str, token.value))
            index += 1
        found_separator = (
            index < len(tokens)
            and tokens[index] == Token(TokenKind.operator, "::")
            and tokens[index].location.line == first.location.line
        )
        if not found_separator:
            if first.kind in {
                TokenKind.kw_var,
                TokenKind.kw_const,
                TokenKind.kw_extern,
            }:
                raise ParserException(
                    "Expected '::' after declaration modifiers.",
                    first.location,
                )
            return None
        modifiers: list[str] = []
        for name in names:
            token = self.tokens.cur_tok
            if name not in SUPPORTED_MODIFIERS:
                raise ParserException(
                    f"unknown modifier '{name}'", token.location
                )
            if name in modifiers:
                raise ParserException(
                    f"duplicate modifier '{name}'", token.location
                )
            modifiers.append(name)
            self.tokens.get_next_token()
        self._consume_operator("::")
        self._validate_modifier_conflicts(modifiers)
        return ParsedAnnotation(tuple(modifiers), first.location)

    def parse_declaration_head(self) -> tuple[Token, ParsedAnnotation | None]:
        """
        title: Consume a declaration name, colon, and optional modifier group.
        returns:
          type: tuple[Token, ParsedAnnotation | None]
        """
        name = self.tokens.cur_tok
        if not self.is_declaration_start():
            raise ParserException(
                "Expected 'name: [modifiers ::] type'.", name.location
            )
        self.tokens.get_next_token()
        self._consume_operator(":")
        return name, self.parse_inline_modifiers()

    def parse_named_declaration(self) -> astx.VariableDeclaration:
        """
        title: Parse a name-first variable declaration without function syntax.
        returns:
          type: astx.VariableDeclaration
        """
        name, modifiers = self.parse_declaration_head()
        if self.tokens.cur_tok.kind == TokenKind.kw_function:
            raise ParserException(
                "Function declarations use 'fn name(...) -> type:'; "
                "put binding modifiers on parameters, not the function name.",
                name.location,
            )
        self._validate_modifier_target(
            modifiers, frozenset({"var", "const"}), "variable"
        )
        return self.parse_var_expr(name, modifiers)

    def _coerce_declared_expression(
        self,
        expr: astx.Expr,
        target_type: astx.DataType,
        *,
        context: str,
    ) -> astx.Expr:
        """
        title: Coerce one expression for declared collection target types.
        parameters:
          expr:
            type: astx.Expr
          target_type:
            type: astx.DataType
          context:
            type: str
        returns:
          type: astx.Expr
        """
        return coerce_dataframe_expression(
            expr,
            target_type,
            context=context,
        )

    def _parse_argument_default(
        self,
        arg_name: str,
        arg_type: astx.DataType,
    ) -> astx.Expr | None:
        """
        title: Parse one optional function argument default value.
        parameters:
          arg_name:
            type: str
          arg_type:
            type: astx.DataType
        returns:
          type: astx.Expr | None
        """
        if not self._is_operator("="):
            return None

        self._consume_operator("=")
        try:
            return self._coerce_declared_expression(
                cast(astx.Expr, self.parse_expression()),
                arg_type,
                context=f"default value for parameter '{arg_name}'",
            )
        except ValueError as err:
            raise ParserException(str(err)) from err

    def _append_argument(
        self,
        args: astx.Arguments,
        arg_name: str,
        arg_type: astx.DataType,
        arg_loc: SourceLocation,
        mutability: astx.MutabilityKind,
    ) -> None:
        """
        title: Append one parsed argument, including an optional default.
        parameters:
          args:
            type: astx.Arguments
          arg_name:
            type: str
          arg_type:
            type: astx.DataType
          arg_loc:
            type: SourceLocation
          mutability:
            type: astx.MutabilityKind
        """
        default = self._parse_argument_default(arg_name, arg_type)
        if default is None:
            args.append(
                astx.Argument(
                    arg_name, arg_type, mutability=mutability, loc=arg_loc
                )
            )
            return

        args.append(
            astx.Argument(
                arg_name,
                arg_type,
                default=default,
                mutability=mutability,
                loc=arg_loc,
            )
        )

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
        self.tokens.get_next_token()  # eat fn
        self._push_template_scope(template_params)
        pushed_return_type = False
        try:
            proto = self.parse_prototype(expect_colon=True)
            if template_params:
                astx.set_template_params(proto, template_params)
            self._push_return_type_scope(
                cast(astx.DataType, proto.return_type)
            )
            pushed_return_type = True
            body = self.parse_block(
                allow_docstring=True,
                declared_names=tuple(arg.name for arg in proto.args.nodes),
                declared_lists=self._list_names_for_arguments(
                    proto.args.nodes
                ),
                declared_tensors=self._tensor_bindings_for_arguments(
                    proto.args.nodes
                ),
                declared_dataframes=self._dataframe_bindings_for_arguments(
                    proto.args.nodes
                ),
            )
        finally:
            if pushed_return_type:
                self._pop_return_type_scope()
            self._pop_template_scope()

        function = astx.FunctionDef(proto, body)
        if template_params:
            astx.set_template_params(function, template_params)
        return function

    def parse_extern(self) -> astx.FunctionPrototype:
        """
        title: Parse an extern declaration.
        returns:
          type: astx.FunctionPrototype
        """
        self.tokens.get_next_token()  # eat extern
        prototype = self.parse_prototype(expect_colon=False)
        if self._is_operator(":"):
            raise ParserException(
                "extern function cannot define a body",
                self.tokens.cur_tok.location,
            )
        setattr(prototype, "is_extern", True)
        return prototype

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
        class_loc = self.tokens.cur_tok.location
        self._validate_modifier_target(
            annotations, CLASS_ALLOWED_MODIFIERS, "class"
        )
        self.tokens.get_next_token()  # eat class

        if self.tokens.cur_tok.kind != TokenKind.identifier:
            raise ParserException("Parser: Expected class name after 'class'.")

        self.validate_type_declaration_name("class")
        class_name = cast(str, self.tokens.cur_tok.value)
        self.tokens.get_next_token()  # eat class name

        bases: list[astx.ClassType] = []
        if self._is_operator("("):
            self._consume_operator("(")
            if self._is_operator(")"):
                raise ParserException("Parser: Expected base class name.")

            while True:
                if self.tokens.cur_tok.kind != TokenKind.identifier:
                    raise ParserException("Parser: Expected base class name.")
                bases.append(
                    astx.ClassType(cast(str, self.tokens.cur_tok.value))
                )
                self.tokens.get_next_token()

                if self._is_operator(")"):
                    break

                self._consume_operator(",")

            self._consume_operator(")")

        self._consume_operator(":")
        attributes, methods = self.parse_class_body()
        declaration = astx.ClassDefStmt(
            class_name,
            bases=bases,
            attributes=attributes,
            methods=methods,
            visibility=self._resolve_visibility(annotations),
            loc=class_loc,
        )
        self._apply_class_modifiers(declaration, annotations)
        return declaration

    def parse_class_body(
        self,
    ) -> tuple[list[astx.VariableDeclaration], list[astx.FunctionDef]]:
        """
        title: Parse a class body.
        returns:
          type: tuple[list[astx.VariableDeclaration], list[astx.FunctionDef]]
        """
        start_token = self.tokens.cur_tok
        if start_token.kind != TokenKind.indent:
            raise ParserException(
                "Expected indentation to start a class body."
            )

        cur_indent = start_token.value
        prev_indent = self.indent_level

        if cur_indent <= prev_indent:
            raise ParserException("There is no new class body to be parsed.")

        self.indent_level = cur_indent
        self.tokens.get_next_token()  # eat indentation

        attributes: list[astx.VariableDeclaration] = []
        methods: list[astx.FunctionDef] = []

        while True:
            if self.tokens.cur_tok.kind == TokenKind.indent:
                new_indent = self.tokens.cur_tok.value
                if new_indent < cur_indent:
                    break
                if new_indent > cur_indent:
                    raise ParserException("Indentation not allowed here.")
                self.tokens.get_next_token()
                continue

            if self.tokens.cur_tok.kind == TokenKind.docstring:
                try:
                    validate_docstring(cast(str, self.tokens.cur_tok.value))
                except ValueError as err:
                    raise ParserException(
                        f"Invalid class or member docstring: {err}",
                        code="ARX-PARSE-DOCSTRING-001",
                    ) from err
                self.tokens.get_next_token()
                # Docstrings may be the entire body of a nominal subclass.
                # Unlike declarations they do not consume a trailing newline.
                next_kind = cast(TokenKind, self.tokens.cur_tok.kind)
                if next_kind == TokenKind.eof or (
                    next_kind != TokenKind.indent
                    and self.tokens.cur_tok.location.col <= cur_indent
                ):
                    break
                continue

            prefixes = ParsedDeclarationPrefixes()
            if self._is_operator("@"):
                prefixes = self.parse_declaration_prefixes(
                    body_indent=cur_indent
                )

            if self.tokens.cur_tok.kind == TokenKind.kw_function:
                methods.append(
                    self.parse_method_decl(
                        prefixes.modifiers, prefixes.template_params
                    )
                )
            elif self.is_declaration_start():
                if prefixes.modifiers is not None:
                    raise ParserException(
                        "Field modifier annotations were replaced; "
                        "use 'name: modifiers :: type'.",
                        prefixes.modifiers.loc,
                    )
                if prefixes.template_params:
                    raise ParserException(
                        "template parameter blocks are only allowed "
                        "before functions or methods"
                    )
                name_token, modifiers = self.parse_declaration_head()
                if (
                    cast(TokenKind, self.tokens.cur_tok.kind)
                    == TokenKind.kw_function
                ):
                    raise ParserException(
                        "Method declarations use 'fn name(...) -> type:'.",
                        name_token.location,
                    )
                attributes.append(self.parse_field_decl(name_token, modifiers))
            else:
                raise ParserException(
                    "Expected a field or 'fn name(...)' method declaration "
                    "in class body.",
                    self.tokens.cur_tok.location,
                )

            while self._is_operator(";"):
                self.tokens.get_next_token()

            if cast(TokenKind, self.tokens.cur_tok.kind) != TokenKind.indent:
                break

        self.indent_level = prev_indent
        return attributes, methods

    def parse_field_decl(
        self,
        name_token: Token,
        modifiers: ParsedAnnotation | None = None,
    ) -> astx.VariableDeclaration:
        """
        title: Parse one class field declaration.
        parameters:
          name_token:
            type: Token
          modifiers:
            type: ParsedAnnotation | None
        returns:
          type: astx.VariableDeclaration
        """
        field_loc = name_token.location
        self._validate_modifier_target(
            modifiers, FIELD_ALLOWED_MODIFIERS, "field"
        )
        name = cast(str, name_token.value)
        field_type = self.parse_type(type_context=TypeUseContext.FIELD)

        initializer: astx.Expr | None = None
        if self._is_operator("="):
            self._consume_operator("=")
            try:
                initializer = self._coerce_declared_expression(
                    cast(astx.Expr, self.parse_expression()),
                    field_type,
                    context=f"field '{name}'",
                )
            except ValueError as err:
                raise ParserException(str(err)) from err
        elif is_tensor_type(field_type) and not self._has_modifier(
            modifiers, "const"
        ):
            try:
                initializer = self._default_value_for_type(field_type)
            except ValueError as err:
                raise ParserException(str(err)) from err

        if isinstance(field_type, astx.InferredType) and initializer is None:
            raise ParserException(
                f"Inferred field '{name}' requires an explicit initializer.",
                field_loc,
            )
        mutability = self.resolve_binding_mutability(modifiers)
        visibility = self._resolve_visibility(modifiers)
        if initializer is None:
            field = astx.VariableDeclaration(
                name,
                field_type,
                mutability=mutability,
                visibility=visibility,
                loc=field_loc,
            )
        else:
            field = astx.VariableDeclaration(
                name,
                field_type,
                mutability=mutability,
                visibility=visibility,
                value=initializer,
                loc=field_loc,
            )
        self._apply_field_modifiers(field, modifiers)
        return field

    def parse_method_decl(
        self,
        modifiers: ParsedAnnotation | None = None,
        template_params: tuple[astx.TemplateParam, ...] = (),
    ) -> astx.FunctionDef:
        """
        title: Parse one class method declaration.
        parameters:
          modifiers:
            type: ParsedAnnotation | None
          template_params:
            type: tuple[astx.TemplateParam, Ellipsis]
        returns:
          type: astx.FunctionDef
        """
        method_loc = self.tokens.cur_tok.location
        self._validate_modifier_target(
            modifiers, METHOD_ALLOWED_MODIFIERS, "method"
        )
        self.tokens.get_next_token()  # eat fn

        if template_params and (
            self._has_modifier(modifiers, "abstract")
            or self._has_modifier(modifiers, "extern")
        ):
            raise ParserException("template methods must define a body")

        is_static = self._has_modifier(modifiers, "static")
        self._push_template_scope(template_params)
        pushed_return_type = False
        try:
            prototype, receiver_name = self.parse_method_signature(
                allow_receiver=not is_static
            )
            if template_params:
                astx.set_template_params(prototype, template_params)
            prototype.visibility = self._resolve_visibility(modifiers)

            declared_names = tuple(arg.name for arg in prototype.args.nodes)
            if receiver_name is not None:
                declared_names = (receiver_name, *declared_names)

            if self._is_operator(":"):
                if self._has_modifier(modifiers, "extern"):
                    raise ParserException("extern method cannot define a body")
                self._consume_operator(":")
                if self._has_modifier(modifiers, "abstract"):
                    body = self.parse_block(
                        allow_docstring=True,
                        declared_names=declared_names,
                        declared_lists=self._list_names_for_arguments(
                            prototype.args.nodes
                        ),
                        declared_tensors=self._tensor_bindings_for_arguments(
                            prototype.args.nodes
                        ),
                        declared_dataframes=(
                            self._dataframe_bindings_for_arguments(
                                prototype.args.nodes
                            )
                        ),
                    )
                    if body.nodes:
                        raise ParserException(
                            "abstract method body may only contain a docstring"
                        )
                else:
                    self._push_return_type_scope(
                        cast(astx.DataType, prototype.return_type)
                    )
                    pushed_return_type = True
                    body = self.parse_block(
                        allow_docstring=True,
                        declared_names=declared_names,
                        declared_lists=self._list_names_for_arguments(
                            prototype.args.nodes
                        ),
                        declared_tensors=self._tensor_bindings_for_arguments(
                            prototype.args.nodes
                        ),
                        declared_dataframes=(
                            self._dataframe_bindings_for_arguments(
                                prototype.args.nodes
                            )
                        ),
                    )
            elif not (
                self._has_modifier(modifiers, "abstract")
                or self._has_modifier(modifiers, "extern")
            ):
                raise ParserException(
                    "method declaration without a body requires "
                    "'abstract' or 'extern'"
                )
            else:
                body = astx.Block()
        finally:
            if pushed_return_type:
                self._pop_return_type_scope()
            self._pop_template_scope()

        method = astx.FunctionDef(prototype, body, loc=method_loc)
        if template_params:
            astx.set_template_params(method, template_params)
        self._apply_method_modifiers(method, modifiers)
        return method

    def parse_method_signature(
        self,
        *,
        allow_receiver: bool,
    ) -> tuple[astx.FunctionPrototype, str | None]:
        """
        title: Parse one class method signature.
        parameters:
          allow_receiver:
            type: bool
        returns:
          type: tuple[astx.FunctionPrototype, str | None]
        """
        if self.tokens.cur_tok.kind != TokenKind.identifier:
            raise ParserException("Parser: Expected method name in prototype")
        name_token = self.tokens.cur_tok
        method_name = cast(str, name_token.value)
        method_loc = name_token.location
        self.tokens.get_next_token()
        self._consume_operator("(")

        args = astx.Arguments()
        implicit_receiver_name: str | None = None
        index = 0
        if not self._is_operator(")"):
            while True:
                if self.tokens.cur_tok.kind != TokenKind.identifier:
                    raise ParserException("Parser: Expected argument name")

                param_name = cast(str, self.tokens.cur_tok.value)
                param_loc = self.tokens.cur_tok.location
                self.tokens.get_next_token()  # eat arg name

                if (
                    index == 0
                    and param_name == "self"
                    and not self._is_operator(":")
                ):
                    if not allow_receiver:
                        raise ParserException(
                            "static method cannot declare implicit receiver "
                            "'self'"
                        )
                    implicit_receiver_name = param_name
                else:
                    if not self._is_operator(":"):
                        raise ParserException(
                            "Parser: Expected type annotation for argument "
                            f"'{param_name}'."
                        )

                    self._consume_operator(":")
                    param_modifiers = self.parse_inline_modifiers()
                    self._validate_modifier_target(
                        param_modifiers,
                        frozenset({"var", "const"}),
                        "parameter",
                    )
                    param_type = self.parse_type(
                        allow_union=True, type_context=TypeUseContext.PARAMETER
                    )
                    self._append_argument(
                        args,
                        param_name,
                        param_type,
                        param_loc,
                        self.resolve_binding_mutability(param_modifiers),
                    )

                index += 1

                if self._is_operator(","):
                    self._consume_operator(",")
                    continue

                break

        self._consume_operator(")")

        if not self._is_operator("->"):
            raise ParserException(
                "Parser: Expected return type annotation with '->'."
            )

        self._consume_operator("->")
        return_type = self.parse_type(
            allow_union=True,
            type_context=TypeUseContext.RETURN,
        )
        return (
            astx.FunctionPrototype(
                method_name,
                args,
                cast(AnyType, return_type),
                loc=method_loc,
            ),
            implicit_receiver_name,
        )

    def parse_declaration_prefixes(
        self,
        *,
        body_indent: int | None = None,
    ) -> ParsedDeclarationPrefixes:
        """
        title: Parse declaration prefixes that precede one declaration.
        parameters:
          body_indent:
            type: int | None
        returns:
          type: ParsedDeclarationPrefixes
        """
        prefixes = ParsedDeclarationPrefixes()

        while self._is_operator("@"):
            prefix = self.parse_declaration_prefix()
            if prefix.modifiers is not None:
                if prefixes.modifiers is not None:
                    raise ParserException("duplicate annotation block")
                prefixes.modifiers = prefix.modifiers
            if prefix.template_params:
                if prefixes.template_params:
                    raise ParserException("duplicate template parameter block")
                prefixes.template_params = prefix.template_params

            prefixes.loc = prefix.loc
            prefixes.description = prefix.description

            if self.tokens.cur_tok.kind == TokenKind.eof:
                raise ParserException(
                    f"{prefix.description} must be followed by a declaration"
                )
            if prefix.loc is not None and (
                self.tokens.cur_tok.location.line == prefix.loc.line
            ):
                raise ParserException(
                    f"{prefix.description} must appear on its own line "
                    "before a declaration"
                )

            if body_indent is None or (
                self.tokens.cur_tok.kind != TokenKind.indent
            ):
                continue

            next_indent = self.tokens.cur_tok.value
            if next_indent < body_indent:
                raise ParserException(
                    f"{prefix.description} must be followed by a declaration"
                )
            if next_indent > body_indent:
                raise ParserException("Indentation not allowed here.")
            self.tokens.get_next_token()

        return prefixes

    def parse_declaration_prefix(self) -> ParsedDeclarationPrefixes:
        """
        title: Parse one declaration prefix.
        returns:
          type: ParsedDeclarationPrefixes
        """
        next_token = self._peek_token()
        if next_token == Token(TokenKind.operator, "["):
            annotation = self.parse_modifier_list()
            return ParsedDeclarationPrefixes(
                modifiers=annotation,
                loc=annotation.loc,
                description="annotation",
            )

        if next_token == Token(TokenKind.operator, "<"):
            template_loc = self.tokens.cur_tok.location
            return ParsedDeclarationPrefixes(
                template_params=self.parse_template_param_block(),
                loc=template_loc,
                description="template parameter block",
            )

        raise ParserException("Expected '[' or '<' after '@'.")

    def parse_template_param_block(
        self,
    ) -> tuple[astx.TemplateParam, ...]:
        """
        title: Parse one template-parameter block.
        returns:
          type: tuple[astx.TemplateParam, Ellipsis]
        """
        self._consume_operator("@")
        self._consume_operator("<")
        self._skip_template_layout()

        if self._is_operator(">"):
            raise ParserException(
                "empty template parameter block is not allowed"
            )

        template_params: list[astx.TemplateParam] = []
        seen_names: set[str] = set()
        while True:
            if self.tokens.cur_tok.kind != TokenKind.identifier:
                raise ParserException(
                    "Parser: Expected template parameter name."
                )

            self.validate_type_declaration_name("template parameter")
            param_name = cast(str, self.tokens.cur_tok.value)
            param_loc = self.tokens.cur_tok.location
            if param_name in seen_names:
                raise ParserException(
                    f"duplicate template parameter '{param_name}'"
                )
            seen_names.add(param_name)
            self.tokens.get_next_token()

            if not self._is_operator(":"):
                raise ParserException(
                    f"template parameter '{param_name}' must declare a bound"
                )

            self._consume_operator(":")
            bound = self.parse_type(
                allow_template_vars=False,
                allow_union=True,
                type_context=TypeUseContext.TEMPLATE_BOUND,
            )
            template_params.append(
                astx.TemplateParam(param_name, bound, loc=param_loc)
            )

            self._skip_template_layout()
            if self._is_operator(">"):
                break

            self._consume_operator(",")
            self._skip_template_layout()
            if self._is_operator(">"):
                break

        self._consume_operator(">")
        return tuple(template_params)

    def parse_template_argument_list(
        self,
    ) -> tuple[astx.DataType, ...]:
        """
        title: Parse one explicit template-argument list.
        returns:
          type: tuple[astx.DataType, Ellipsis]
        """
        self._consume_operator("<")

        if self._is_operator(">"):
            raise ParserException(
                "empty template argument list is not allowed"
            )

        template_args: list[astx.DataType] = []
        while True:
            template_args.append(
                self.parse_type(
                    allow_template_vars=False,
                    allow_union=False,
                    type_context=TypeUseContext.TEMPLATE_ARGUMENT,
                )
            )

            if self._is_operator(">"):
                break

            self._consume_operator(",")

        self._consume_operator(">")
        return tuple(template_args)

    def parse_modifier_list(self) -> ParsedAnnotation:
        """
        title: Parse one annotation-line modifier list.
        returns:
          type: ParsedAnnotation
        """
        annotation_loc = self.tokens.cur_tok.location
        self._consume_operator("@")
        self._consume_operator("[")

        if self._is_operator("]"):
            raise ParserException("empty annotation is not allowed")

        modifiers: list[str] = []
        while True:
            if self.tokens.cur_tok.kind not in {
                TokenKind.identifier,
                TokenKind.kw_extern,
            }:
                raise ParserException("Parser: Expected modifier name.")

            modifier_name = cast(str, self.tokens.cur_tok.value)
            if modifier_name not in SUPPORTED_MODIFIERS:
                raise ParserException(f"unknown modifier '{modifier_name}'")
            if modifier_name in modifiers:
                raise ParserException(f"duplicate modifier '{modifier_name}'")

            modifiers.append(modifier_name)
            self.tokens.get_next_token()

            if self._is_operator("]"):
                break

            self._consume_operator(",")

        self._consume_operator("]")
        self._validate_modifier_conflicts(modifiers)
        return ParsedAnnotation(tuple(modifiers), annotation_loc)

    def _validate_modifier_conflicts(
        self,
        modifiers: list[str],
    ) -> None:
        """
        title: Validate duplicate-group modifier conflicts.
        parameters:
          modifiers:
            type: list[str]
        """
        visibility = [
            name for name in modifiers if name in VISIBILITY_MODIFIERS
        ]
        if len(visibility) > 1:
            raise ParserException(
                "conflicting visibility modifiers "
                f"'{visibility[0]}' and '{visibility[1]}'"
            )

        mutability = [
            name for name in modifiers if name in BINDING_MUTABILITY_MODIFIERS
        ]
        if len(mutability) > 1:
            raise ParserException(
                "conflicting mutability modifiers "
                f"'{mutability[0]}' and '{mutability[1]}'"
            )

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
        if modifiers is None:
            return

        for modifier in modifiers.modifiers:
            if modifier not in allowed:
                raise ParserException(f"{target} cannot use '{modifier}'")

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
        if modifiers is None:
            return False
        return expected in modifiers.modifiers

    def _resolve_visibility(
        self,
        modifiers: ParsedAnnotation | None,
    ) -> astx.VisibilityKind:
        """
        title: Resolve class/member visibility defaults.
        parameters:
          modifiers:
            type: ParsedAnnotation | None
        returns:
          type: astx.VisibilityKind
        """
        if modifiers is None:
            return astx.VisibilityKind.public
        for modifier in modifiers.modifiers:
            if modifier in VISIBILITY_MODIFIERS:
                return VISIBILITY_NAME_MAP[modifier]
        return astx.VisibilityKind.public

    def _explicit_visibility(
        self,
        modifiers: ParsedAnnotation | None,
    ) -> astx.VisibilityKind | None:
        """
        title: Return explicit visibility when one was written.
        parameters:
          modifiers:
            type: ParsedAnnotation | None
        returns:
          type: astx.VisibilityKind | None
        """
        if modifiers is None:
            return None
        for modifier in modifiers.modifiers:
            if modifier in VISIBILITY_MODIFIERS:
                return VISIBILITY_NAME_MAP[modifier]
        return None

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
        if modifiers is None:
            return astx.MutabilityKind.mutable
        for modifier in modifiers.modifiers:
            if modifier in BINDING_MUTABILITY_MODIFIERS:
                return MUTABILITY_NAME_MAP[modifier]
        return astx.MutabilityKind.mutable

    def _explicit_field_mutability(
        self,
        modifiers: ParsedAnnotation | None,
    ) -> astx.MutabilityKind | None:
        """
        title: Return explicit field mutability when one was written.
        parameters:
          modifiers:
            type: ParsedAnnotation | None
        returns:
          type: astx.MutabilityKind | None
        """
        if modifiers is None:
            return None
        for modifier in modifiers.modifiers:
            if modifier in BINDING_MUTABILITY_MODIFIERS:
                return MUTABILITY_NAME_MAP[modifier]
        return None

    def _apply_class_modifiers(
        self,
        declaration: astx.ClassDefStmt,
        modifiers: ParsedAnnotation | None,
    ) -> None:
        """
        title: Attach explicit class modifier metadata to the IRx node.
        parameters:
          declaration:
            type: astx.ClassDefStmt
          modifiers:
            type: ParsedAnnotation | None
        """
        explicit_visibility = self._explicit_visibility(modifiers)
        if explicit_visibility is not None:
            setattr(declaration, "explicit_visibility", explicit_visibility)
        if self._has_modifier(modifiers, "abstract"):
            setattr(declaration, "is_abstract", True)
            setattr(declaration, "explicit_is_abstract", True)

    def _apply_field_modifiers(
        self,
        declaration: astx.VariableDeclaration,
        modifiers: ParsedAnnotation | None,
    ) -> None:
        """
        title: Attach explicit field modifier metadata to the IRx node.
        parameters:
          declaration:
            type: astx.VariableDeclaration
          modifiers:
            type: ParsedAnnotation | None
        """
        explicit_visibility = self._explicit_visibility(modifiers)
        if explicit_visibility is not None:
            setattr(declaration, "explicit_visibility", explicit_visibility)
        explicit_mutability = self._explicit_field_mutability(modifiers)
        if explicit_mutability is not None:
            setattr(declaration, "explicit_mutability", explicit_mutability)
        if self._has_modifier(modifiers, "static"):
            setattr(declaration, "is_static", True)
            setattr(declaration, "explicit_is_static", True)

    def _apply_method_modifiers(
        self,
        declaration: astx.FunctionDef,
        modifiers: ParsedAnnotation | None,
    ) -> None:
        """
        title: Attach explicit method modifier metadata to the IRx node.
        parameters:
          declaration:
            type: astx.FunctionDef
          modifiers:
            type: ParsedAnnotation | None
        """
        explicit_visibility = self._explicit_visibility(modifiers)
        if explicit_visibility is not None:
            setattr(
                declaration.prototype,
                "explicit_visibility",
                explicit_visibility,
            )
        if self._has_modifier(modifiers, "static"):
            setattr(declaration.prototype, "is_static", True)
            setattr(declaration.prototype, "explicit_is_static", True)
        if self._has_modifier(modifiers, "abstract"):
            setattr(declaration.prototype, "is_abstract", True)
            setattr(declaration.prototype, "explicit_is_abstract", True)
        if self._has_modifier(modifiers, "extern"):
            setattr(declaration.prototype, "is_extern", True)
            setattr(declaration.prototype, "explicit_is_extern", True)

    def parse_prototype(self, expect_colon: bool) -> astx.FunctionPrototype:
        """
        title: Parse function/extern prototypes.
        parameters:
          expect_colon:
            type: bool
        returns:
          type: astx.FunctionPrototype
        """
        if self.tokens.cur_tok.kind != TokenKind.identifier:
            raise ParserException(
                "Parser: Expected function name in prototype"
            )
        name_token = self.tokens.cur_tok
        fn_name = cast(str, name_token.value)
        fn_loc = name_token.location
        self.tokens.get_next_token()
        self._consume_operator("(")

        args = astx.Arguments()
        if not self._is_operator(")"):
            while True:
                if self.tokens.cur_tok.kind != TokenKind.identifier:
                    raise ParserException("Parser: Expected argument name")

                arg_name = cast(str, self.tokens.cur_tok.value)
                arg_loc = self.tokens.cur_tok.location
                self.tokens.get_next_token()  # eat arg name

                if not self._is_operator(":"):
                    raise ParserException(
                        "Parser: Expected type annotation for argument "
                        f"'{arg_name}'."
                    )

                self._consume_operator(":")
                arg_modifiers = self.parse_inline_modifiers()
                self._validate_modifier_target(
                    arg_modifiers, frozenset({"var", "const"}), "parameter"
                )
                arg_type = self.parse_type(
                    allow_union=True, type_context=TypeUseContext.PARAMETER
                )

                self._append_argument(
                    args,
                    arg_name,
                    arg_type,
                    arg_loc,
                    self.resolve_binding_mutability(arg_modifiers),
                )

                if self._is_operator(","):
                    self._consume_operator(",")
                    continue

                break

        self._consume_operator(")")

        if not self._is_operator("->"):
            raise ParserException(
                "Parser: Expected return type annotation with '->'."
            )
        self._consume_operator("->")
        ret_type: astx.DataType = self.parse_type(
            allow_union=True, type_context=TypeUseContext.RETURN
        )

        if expect_colon:
            self._consume_operator(":")

        return astx.FunctionPrototype(
            fn_name, args, cast(AnyType, ret_type), loc=fn_loc
        )

    def _tensor_bindings_for_arguments(
        self,
        arguments: tuple[astx.Argument, ...] | list[astx.Argument],
    ) -> dict[str, TensorBinding | None]:
        """
        title: Build one tensor scope map for function arguments.
        parameters:
          arguments:
            type: tuple[astx.Argument, Ellipsis] | list[astx.Argument]
        returns:
          type: dict[str, TensorBinding | None]
        """
        bindings: dict[str, TensorBinding | None] = {}
        for argument in arguments:
            if not is_tensor_type(argument.type_):
                continue
            bindings[argument.name] = binding_from_type(argument.type_)
        return bindings

    def _dataframe_bindings_for_arguments(
        self,
        arguments: tuple[astx.Argument, ...] | list[astx.Argument],
    ) -> dict[str, DataFrameBinding | None]:
        """
        title: Build one DataFrame scope map for function arguments.
        parameters:
          arguments:
            type: tuple[astx.Argument, Ellipsis] | list[astx.Argument]
        returns:
          type: dict[str, DataFrameBinding | None]
        """
        bindings: dict[str, DataFrameBinding | None] = {}
        for argument in arguments:
            if not is_dataframe_type(argument.type_):
                continue
            bindings[argument.name] = dataframe_binding_from_type(
                argument.type_
            )
        return bindings

    def _list_names_for_arguments(
        self,
        arguments: tuple[astx.Argument, ...] | list[astx.Argument],
    ) -> tuple[str, ...]:
        """
        title: Return visible list-typed argument names.
        parameters:
          arguments:
            type: tuple[astx.Argument, Ellipsis] | list[astx.Argument]
        returns:
          type: tuple[str, Ellipsis]
        """
        return tuple(
            argument.name
            for argument in arguments
            if isinstance(argument.type_, astx.ListType)
        )
