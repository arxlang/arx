"""
title: parser module gather all functions and classes for parsing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from astx import SourceLocation
from astx.types import AnyType
from irx import astx

from arx import builtins
from arx.docstrings import validate_docstring
from arx.exceptions import ParserException
from arx.lexer import Token, TokenKind, TokenList

INDENT_SIZE = 2


@dataclass(frozen=True)
class ParsedAnnotation:
    """
    title: Parsed modifier annotation attached to the next declaration.
    attributes:
      modifiers:
        type: tuple[str, Ellipsis]
      loc:
        type: SourceLocation
    """

    modifiers: tuple[str, ...]
    loc: SourceLocation


SUPPORTED_MODIFIERS = frozenset(
    {
        "public",
        "private",
        "protected",
        "static",
        "constant",
        "mutable",
        "abstract",
        "extern",
    }
)

VISIBILITY_MODIFIERS = frozenset({"public", "private", "protected"})
FIELD_MUTABILITY_MODIFIERS = frozenset({"constant", "mutable"})

CLASS_ALLOWED_MODIFIERS = frozenset(
    {"public", "private", "protected", "abstract"}
)
FIELD_ALLOWED_MODIFIERS = frozenset(
    {"public", "private", "protected", "static", "constant", "mutable"}
)
METHOD_ALLOWED_MODIFIERS = frozenset(
    {"public", "private", "protected", "static", "abstract", "extern"}
)

VISIBILITY_NAME_MAP = {
    "public": astx.VisibilityKind.public,
    "private": astx.VisibilityKind.private,
    "protected": astx.VisibilityKind.protected,
}
MUTABILITY_NAME_MAP = {
    "constant": astx.MutabilityKind.constant,
    "mutable": astx.MutabilityKind.mutable,
}


class Parser:
    """
    title: Parser class.
    attributes:
      bin_op_precedence:
        type: dict[str, int]
      indent_level:
        type: int
      known_class_names:
        type: set[str]
      tokens:
        type: TokenList
    """

    bin_op_precedence: dict[str, int] = {}
    indent_level: int = 0
    known_class_names: set[str]
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
        self.known_class_names = set()
        self.tokens = tokens

    def clean(self) -> None:
        """
        title: Reset the Parser static variables.
        """
        self.indent_level = 0
        self.known_class_names = set()
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
                annotations = self.parse_modifier_list()
                if cast(TokenKind, self.tokens.cur_tok.kind) == TokenKind.eof:
                    raise ParserException(
                        "annotation must be followed by a declaration"
                    )
                if self.tokens.cur_tok.location.line == annotations.loc.line:
                    raise ParserException(
                        "annotation must appear on its own line "
                        "before a declaration"
                    )
                if self.tokens.cur_tok.kind != TokenKind.kw_class:
                    raise ParserException(
                        "annotation must be followed by a declaration"
                    )
                tree.nodes.append(self.parse_class_decl(annotations))
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
        return cast(str, expr.name)

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

    def get_tok_precedence(self) -> int:
        """
        title: Get the precedence of the pending binary operator token.
        returns:
          type: int
        """
        return self.bin_op_precedence.get(self.tokens.cur_tok.value, -1)

    def parse_function(self) -> astx.FunctionDef:
        """
        title: Parse the function definition expression.
        returns:
          type: astx.FunctionDef
        """
        self.tokens.get_next_token()  # eat fn
        proto = self.parse_prototype(expect_colon=True)
        body = self.parse_block(allow_docstring=True)
        return astx.FunctionDef(proto, body)

    def parse_extern(self) -> astx.FunctionPrototype:
        """
        title: Parse the extern expression.
        returns:
          type: astx.FunctionPrototype
        """
        self.tokens.get_next_token()  # eat extern
        prototype = self.parse_prototype(expect_colon=False)
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

            modifiers: ParsedAnnotation | None = None
            if self._is_operator("@"):
                modifiers = self.parse_modifier_list()
                if cast(TokenKind, self.tokens.cur_tok.kind) == TokenKind.eof:
                    raise ParserException(
                        "annotation must be followed by a declaration"
                    )
                if self.tokens.cur_tok.location.line == modifiers.loc.line:
                    raise ParserException(
                        "annotation must appear on its own line "
                        "before a declaration"
                    )
                if (
                    cast(TokenKind, self.tokens.cur_tok.kind)
                    == TokenKind.indent
                ):
                    next_indent = self.tokens.cur_tok.value
                    if next_indent < cur_indent:
                        raise ParserException(
                            "annotation must be followed by a declaration"
                        )
                    if next_indent > cur_indent:
                        raise ParserException("Indentation not allowed here.")
                    self.tokens.get_next_token()

            if self.tokens.cur_tok.kind == TokenKind.docstring:
                raise ParserException(
                    "Docstrings are not allowed in class bodies."
                )

            if self.tokens.cur_tok.kind == TokenKind.kw_function:
                methods.append(self.parse_method_decl(modifiers))
            elif self.tokens.cur_tok.kind == TokenKind.identifier:
                attributes.append(self.parse_field_decl(modifiers))
            else:
                if modifiers is not None:
                    raise ParserException(
                        "annotation must be followed by a declaration"
                    )
                raise ParserException(
                    "Expected a field or method declaration in class body."
                )

            while self._is_operator(";"):
                self.tokens.get_next_token()

            if cast(TokenKind, self.tokens.cur_tok.kind) != TokenKind.indent:
                break

        self.indent_level = prev_indent
        return attributes, methods

    def parse_field_decl(
        self,
        modifiers: ParsedAnnotation | None = None,
    ) -> astx.VariableDeclaration:
        """
        title: Parse one class field declaration.
        parameters:
          modifiers:
            type: ParsedAnnotation | None
        returns:
          type: astx.VariableDeclaration
        """
        field_loc = self.tokens.cur_tok.location
        self._validate_modifier_target(
            modifiers, FIELD_ALLOWED_MODIFIERS, "field"
        )

        name = cast(str, self.tokens.cur_tok.value)
        self.tokens.get_next_token()  # eat field name

        if not self._is_operator(":"):
            raise ParserException(
                f"Parser: Expected type annotation for field '{name}'."
            )

        self._consume_operator(":")
        field_type = self.parse_type()

        initializer: astx.Expr | None = None
        if self._is_operator("="):
            self._consume_operator("=")
            initializer = cast(astx.Expr, self.parse_expression())

        field_kwargs: dict[str, object] = {
            "mutability": self._resolve_field_mutability(modifiers),
            "visibility": self._resolve_visibility(modifiers),
            "loc": field_loc,
        }
        if initializer is not None:
            field_kwargs["value"] = initializer

        field = astx.VariableDeclaration(
            name,
            field_type,
            **field_kwargs,
        )
        self._apply_field_modifiers(field, modifiers)
        return field

    def parse_method_decl(
        self,
        modifiers: ParsedAnnotation | None = None,
    ) -> astx.FunctionDef:
        """
        title: Parse one class method declaration.
        parameters:
          modifiers:
            type: ParsedAnnotation | None
        returns:
          type: astx.FunctionDef
        """
        method_loc = self.tokens.cur_tok.location
        self._validate_modifier_target(
            modifiers, METHOD_ALLOWED_MODIFIERS, "method"
        )
        self.tokens.get_next_token()  # eat fn

        is_static = self._has_modifier(modifiers, "static")
        prototype = self.parse_method_signature(allow_receiver=not is_static)
        prototype.visibility = self._resolve_visibility(modifiers)

        if self._is_operator(":"):
            if self._has_modifier(modifiers, "abstract"):
                raise ParserException("abstract method cannot define a body")
            if self._has_modifier(modifiers, "extern"):
                raise ParserException("extern method cannot define a body")
            self._consume_operator(":")
            body = self.parse_block(allow_docstring=True)
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

        method = astx.FunctionDef(prototype, body, loc=method_loc)
        self._apply_method_modifiers(method, modifiers)
        return method

    def parse_method_signature(
        self,
        *,
        allow_receiver: bool,
    ) -> astx.FunctionPrototype:
        """
        title: Parse one class method signature.
        parameters:
          allow_receiver:
            type: bool
        returns:
          type: astx.FunctionPrototype
        """
        if self.tokens.cur_tok.kind != TokenKind.identifier:
            raise ParserException("Parser: Expected method name in prototype")

        method_name = cast(str, self.tokens.cur_tok.value)
        method_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat method name

        self._consume_operator("(")

        args = astx.Arguments()
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
                else:
                    if not self._is_operator(":"):
                        raise ParserException(
                            "Parser: Expected type annotation for argument "
                            f"'{param_name}'."
                        )

                    self._consume_operator(":")
                    param_type = self.parse_type()
                    args.append(
                        astx.Argument(param_name, param_type, loc=param_loc)
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
        return_type = self.parse_type()
        return astx.FunctionPrototype(
            method_name,
            args,
            cast(AnyType, return_type),
            loc=method_loc,
        )

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
            if self.tokens.cur_tok.kind != TokenKind.identifier:
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
            name for name in modifiers if name in FIELD_MUTABILITY_MODIFIERS
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

    def _resolve_field_mutability(
        self,
        modifiers: ParsedAnnotation | None,
    ) -> astx.MutabilityKind:
        """
        title: Resolve field mutability defaults.
        parameters:
          modifiers:
            type: ParsedAnnotation | None
        returns:
          type: astx.MutabilityKind
        """
        if modifiers is None:
            return astx.MutabilityKind.mutable
        for modifier in modifiers.modifiers:
            if modifier in FIELD_MUTABILITY_MODIFIERS:
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
            if modifier in FIELD_MUTABILITY_MODIFIERS:
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

    def parse_primary(self) -> astx.AST:
        """
        title: Parse the primary expression.
        returns:
          type: astx.AST
        """
        if self._is_operator("@"):
            raise ParserException(
                "Annotations are only allowed before declarations."
            )
        if self.tokens.cur_tok.kind == TokenKind.kw_class:
            raise ParserException(
                "Class declarations are only allowed at module scope."
            )
        if self.tokens.cur_tok.kind == TokenKind.identifier:
            return self.parse_identifier_expr()
        if self.tokens.cur_tok.kind == TokenKind.int_literal:
            return self.parse_int_expr()
        if self.tokens.cur_tok.kind == TokenKind.float_literal:
            return self.parse_float_expr()
        if self.tokens.cur_tok.kind == TokenKind.string_literal:
            return self.parse_string_expr()
        if self.tokens.cur_tok.kind == TokenKind.char_literal:
            return self.parse_char_expr()
        if self.tokens.cur_tok.kind == TokenKind.bool_literal:
            return self.parse_bool_expr()
        if self.tokens.cur_tok.kind == TokenKind.none_literal:
            return self.parse_none_expr()
        if self._is_operator("("):
            return self.parse_paren_expr()
        if self._is_operator("["):
            return self.parse_list_expr()
        if self.tokens.cur_tok.kind == TokenKind.kw_if:
            return self.parse_if_stmt()
        if self.tokens.cur_tok.kind == TokenKind.kw_while:
            return self.parse_while_stmt()
        if self.tokens.cur_tok.kind == TokenKind.kw_for:
            return self.parse_for_stmt()
        if self.tokens.cur_tok.kind == TokenKind.kw_var:
            return self.parse_var_expr()
        if self._is_operator(";"):
            self.tokens.get_next_token()
            return self.parse_primary()
        if self.tokens.cur_tok.kind == TokenKind.kw_return:
            return self.parse_return_function()
        if self.tokens.cur_tok.kind == TokenKind.indent:
            return self.parse_block()
        if self.tokens.cur_tok.kind == TokenKind.docstring:
            raise ParserException(
                "Docstrings are only allowed at module start or as the "
                "first statement inside a function body."
            )

        msg = (
            "Parser: Unknown token when expecting an expression: "
            f"'{self.tokens.cur_tok.get_name()}'."
        )
        self.tokens.get_next_token()
        raise ParserException(msg)

    def parse_postfix(self) -> astx.AST:
        """
        title: Parse postfix member access and method calls.
        returns:
          type: astx.AST
        """
        expr = self.parse_primary()

        while self._is_operator("."):
            self._consume_operator(".")

            if self.tokens.cur_tok.kind != TokenKind.identifier:
                raise ParserException(
                    "Parser: Expected member name after '.'."
                )

            member_name = cast(str, self.tokens.cur_tok.value)
            self.tokens.get_next_token()

            if self._is_operator("("):
                self._consume_operator("(")
                args: list[astx.DataType] = []
                if not self._is_operator(")"):
                    while True:
                        args.append(
                            cast(astx.DataType, self.parse_expression())
                        )

                        if self._is_operator(")"):
                            break

                        self._consume_operator(",")

                self._consume_operator(")")
                class_name = self._class_name_from_expr(expr)
                if class_name is not None:
                    expr = astx.StaticMethodCall(
                        class_name,
                        member_name,
                        args,
                    )
                else:
                    expr = astx.MethodCall(
                        expr,
                        member_name,
                        args,
                    )
                continue

            class_name = self._class_name_from_expr(expr)
            if class_name is not None:
                expr = astx.StaticFieldAccess(class_name, member_name)
            else:
                expr = astx.FieldAccess(expr, member_name)

        return expr

    def parse_block(self, allow_docstring: bool = False) -> astx.Block:
        """
        title: Parse a block of nodes.
        parameters:
          allow_docstring:
            type: bool
        returns:
          type: astx.Block
        """
        start_token = self.tokens.cur_tok
        if start_token.kind != TokenKind.indent:
            raise ParserException("Expected indentation to start a block.")

        cur_indent = start_token.value
        prev_indent = self.indent_level

        if cur_indent <= prev_indent:
            raise ParserException("There is no new block to be parsed.")

        self.indent_level = cur_indent
        self.tokens.get_next_token()  # eat indentation

        block = astx.Block()
        docstring_allowed_here = allow_docstring

        while True:
            # Indentation tokens are line markers. Consume same-level markers
            # (including comment/blank lines), stop on dedent, and reject
            # unexpected over-indentation at this parsing level.
            if self.tokens.cur_tok.kind == TokenKind.indent:
                new_indent = self.tokens.cur_tok.value
                if new_indent < cur_indent:
                    break
                if new_indent > cur_indent:
                    raise ParserException("Indentation not allowed here.")
                self.tokens.get_next_token()  # eat same-level indentation
                continue

            if self.tokens.cur_tok.kind == TokenKind.docstring:
                if not docstring_allowed_here:
                    raise ParserException(
                        "Docstrings are only allowed as the first statement "
                        "inside a function body."
                    )
                try:
                    validate_docstring(self.tokens.cur_tok.value)
                except ValueError as err:
                    raise ParserException(
                        f"Invalid function docstring: {err}"
                    ) from err
                self.tokens.get_next_token()
                docstring_allowed_here = False
            else:
                node = self.parse_expression()
                block.nodes.append(node)
                docstring_allowed_here = False

            while self._is_operator(";"):
                self.tokens.get_next_token()

            next_kind: TokenKind = self.tokens.cur_tok.kind
            if next_kind not in {
                TokenKind.indent,
                TokenKind.docstring,
            }:
                break

        self.indent_level = prev_indent
        return block

    def parse_expression(self) -> astx.AST:
        """
        title: Parse an expression.
        returns:
          type: astx.AST
        """
        lhs = self.parse_unary()
        return self.parse_bin_op_rhs(0, lhs)

    def parse_if_stmt(self) -> astx.IfStmt:
        """
        title: Parse the `if` expression.
        returns:
          type: astx.IfStmt
        """
        if_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat if

        cond = self.parse_expression()
        self._consume_operator(":")

        then_block = self.parse_block()

        if self.tokens.cur_tok.kind == TokenKind.indent:
            self.tokens.get_next_token()

        else_block = astx.Block()
        if self.tokens.cur_tok.kind == TokenKind.kw_else:
            self.tokens.get_next_token()  # eat else
            self._consume_operator(":")
            else_block = self.parse_block()

        return astx.IfStmt(
            cast(astx.Expr, cond), then_block, else_block, loc=if_loc
        )

    def parse_while_stmt(self) -> astx.WhileStmt:
        """
        title: Parse the `while` expression.
        returns:
          type: astx.WhileStmt
        """
        while_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat while

        condition = self.parse_expression()
        self._consume_operator(":")
        body = self.parse_block()

        return astx.WhileStmt(cast(astx.Expr, condition), body, loc=while_loc)

    def parse_int_expr(self) -> astx.LiteralInt32:
        """
        title: Parse the integer expression.
        returns:
          type: astx.LiteralInt32
        """
        result = astx.LiteralInt32(self.tokens.cur_tok.value)
        self.tokens.get_next_token()
        return result

    def parse_float_expr(self) -> astx.LiteralFloat32:
        """
        title: Parse the float expression.
        returns:
          type: astx.LiteralFloat32
        """
        result = astx.LiteralFloat32(self.tokens.cur_tok.value)
        self.tokens.get_next_token()
        return result

    def parse_string_expr(self) -> astx.LiteralString:
        """
        title: Parse the string expression.
        returns:
          type: astx.LiteralString
        """
        result = astx.LiteralString(self.tokens.cur_tok.value)
        self.tokens.get_next_token()
        return result

    def parse_char_expr(self) -> astx.LiteralUTF8Char:
        """
        title: Parse the char expression.
        returns:
          type: astx.LiteralUTF8Char
        """
        result = astx.LiteralUTF8Char(self.tokens.cur_tok.value)
        self.tokens.get_next_token()
        return result

    def parse_bool_expr(self) -> astx.LiteralBoolean:
        """
        title: Parse the bool expression.
        returns:
          type: astx.LiteralBoolean
        """
        result = astx.LiteralBoolean(self.tokens.cur_tok.value)
        self.tokens.get_next_token()
        return result

    def parse_none_expr(self) -> astx.LiteralNone:
        """
        title: Parse the none expression.
        returns:
          type: astx.LiteralNone
        """
        result = astx.LiteralNone()
        self.tokens.get_next_token()
        return result

    def parse_paren_expr(self) -> astx.AST:
        """
        title: Parse the parenthesis expression.
        returns:
          type: astx.AST
        """
        self._consume_operator("(")
        expr = self.parse_expression()
        self._consume_operator(")")
        return expr

    def parse_list_expr(self) -> astx.LiteralList:
        """
        title: Parse list literals.
        returns:
          type: astx.LiteralList
        """
        self._consume_operator("[")

        elements: list[astx.Literal] = []
        if not self._is_operator("]"):
            while True:
                elem = self.parse_expression()
                if not isinstance(elem, astx.Literal):
                    raise ParserException(
                        "List literals currently support only literal "
                        "elements."
                    )
                elements.append(elem)

                if self._is_operator("]"):
                    break

                self._consume_operator(",")

        self._consume_operator("]")
        return astx.LiteralList(elements)

    def parse_identifier_expr(self) -> astx.AST:
        """
        title: Parse the identifier expression.
        returns:
          type: astx.AST
        """
        id_name = cast(str, self.tokens.cur_tok.value)
        id_loc = self.tokens.cur_tok.location

        self.tokens.get_next_token()  # eat identifier

        if not self._is_operator("("):
            return astx.Identifier(id_name, loc=id_loc)

        self._consume_operator("(")

        if id_name == builtins.BUILTIN_CAST:
            value_expr = self.parse_expression()
            self._consume_operator(",")
            target_type = self.parse_type()
            self._consume_operator(")")
            return builtins.build_cast(
                cast(astx.DataType, value_expr), target_type
            )

        if id_name == builtins.BUILTIN_PRINT:
            message = self.parse_expression()
            self._consume_operator(")")
            return builtins.build_print(cast(astx.Expr, message))

        if id_name in {"datetime", "timestamp"}:
            arg = self.parse_expression()
            self._consume_operator(")")
            if not isinstance(arg, astx.LiteralString):
                raise ParserException(
                    f"Builtin '{id_name}' expects a string literal argument."
                )
            if id_name == "datetime":
                return astx.LiteralDateTime(arg.value, loc=id_loc)
            return astx.LiteralTimestamp(arg.value, loc=id_loc)

        args: list[astx.DataType] = []
        if not self._is_operator(")"):
            while True:
                args.append(cast(astx.DataType, self.parse_expression()))

                if self._is_operator(")"):
                    break

                self._consume_operator(",")

        self._consume_operator(")")
        if id_name in self.known_class_names:
            if args:
                raise ParserException(
                    "class construction does not accept arguments"
                )
            return astx.ClassConstruct(id_name)
        return astx.FunctionCall(id_name, args, loc=id_loc)

    def parse_for_stmt(self) -> astx.AST:
        """
        title: Parse for-loop expressions.
        returns:
          type: astx.AST
        """
        for_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat for

        if self.tokens.cur_tok.kind == TokenKind.kw_var:
            return self.parse_for_count_stmt(for_loc)

        if self.tokens.cur_tok.kind != TokenKind.identifier:
            raise ParserException("Parser: Expected identifier after for")

        var_name = cast(str, self.tokens.cur_tok.value)
        var_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat identifier

        if self.tokens.cur_tok != Token(TokenKind.kw_in, "in"):
            raise ParserException("Parser: Expected 'in' after loop variable.")

        self.tokens.get_next_token()  # eat in
        self._consume_operator("(")

        # Slice-like range header: (start:end:step)
        start = self.parse_expression()
        self._consume_operator(":")
        end = self.parse_expression()

        step: astx.AST = astx.LiteralInt32(1)
        if self._is_operator(":"):
            self._consume_operator(":")
            step = self.parse_expression()

        self._consume_operator(")")
        self._consume_operator(":")
        body = self.parse_block()

        variable = astx.InlineVariableDeclaration(
            name=var_name,
            type_=astx.Int32(),
            loc=var_loc,
        )
        return astx.ForRangeLoopStmt(
            variable,
            cast(astx.Expr, start),
            cast(astx.Expr, end),
            cast(astx.Expr, step),
            body,
            loc=for_loc,
        )

    def parse_for_count_stmt(
        self, for_loc: SourceLocation
    ) -> astx.ForCountLoopStmt:
        """
        title: Parse count-style for loop.
        parameters:
          for_loc:
            type: SourceLocation
        returns:
          type: astx.ForCountLoopStmt
        """
        initializer = self.parse_inline_var_declaration()
        self._consume_operator(";")

        condition = self.parse_expression()
        self._consume_operator(";")

        update = self.parse_expression()
        self._consume_operator(":")

        body = self.parse_block()
        return astx.ForCountLoopStmt(
            initializer,
            cast(astx.Expr, condition),
            cast(astx.Expr, update),
            body,
            loc=for_loc,
        )

    def parse_inline_var_declaration(self) -> astx.InlineVariableDeclaration:
        """
        title: Parse inline variable declaration used by count-style for loops.
        returns:
          type: astx.InlineVariableDeclaration
        """
        if self.tokens.cur_tok.kind != TokenKind.kw_var:
            raise ParserException("Parser: Expected 'var' in for initializer")

        var_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat var

        cur_kind: TokenKind = self.tokens.cur_tok.kind
        if cur_kind != TokenKind.identifier:
            raise ParserException("Parser: Expected identifier after var")

        name = cast(str, self.tokens.cur_tok.value)
        self.tokens.get_next_token()  # eat identifier

        if not self._is_operator(":"):
            raise ParserException(
                "Parser: Expected type annotation for inline variable "
                f"'{name}'."
            )

        self._consume_operator(":")
        var_type = self.parse_type()

        self._consume_operator("=")
        value = self.parse_expression()

        return astx.InlineVariableDeclaration(
            name=name,
            type_=var_type,
            value=cast(astx.Expr, value),
            loc=var_loc,
        )

    def parse_var_expr(self) -> astx.VariableDeclaration:
        """
        title: Parse typed variable declarations.
        returns:
          type: astx.VariableDeclaration
        """
        var_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat var

        if self.tokens.cur_tok.kind != TokenKind.identifier:
            raise ParserException("Parser: Expected identifier after var")

        name = cast(str, self.tokens.cur_tok.value)
        self.tokens.get_next_token()  # eat identifier

        if not self._is_operator(":"):
            raise ParserException(
                f"Parser: Expected type annotation for variable '{name}'."
            )

        self._consume_operator(":")
        var_type = self.parse_type()

        value: astx.Expr | None = None
        if self._is_operator("="):
            self._consume_operator("=")
            value = cast(astx.Expr, self.parse_expression())

        if self.tokens.cur_tok == Token(TokenKind.kw_in, "in"):
            raise ParserException(
                "Legacy 'var ... in ...' syntax is not "
                "supported in this parser."
            )

        if value is None:
            value = self._default_value_for_type(var_type)

        return astx.VariableDeclaration(
            name=name,
            type_=var_type,
            value=value,
            loc=var_loc,
        )

    def _default_value_for_type(self, data_type: astx.DataType) -> astx.Expr:
        """
        title: Build a default initializer for typed declarations.
        parameters:
          data_type:
            type: astx.DataType
        returns:
          type: astx.Expr
        """
        if isinstance(data_type, astx.Float16):
            return astx.LiteralFloat16(0.0)
        if isinstance(data_type, astx.Float32):
            return astx.LiteralFloat32(0.0)
        if isinstance(
            data_type, (astx.Int8, astx.Int16, astx.Int32, astx.Int64)
        ):
            return astx.LiteralInt32(0)
        if isinstance(data_type, astx.Boolean):
            return astx.LiteralBoolean(False)
        if isinstance(data_type, astx.String):
            return astx.LiteralString("")
        if isinstance(data_type, astx.NoneType):
            return astx.LiteralNone()
        if isinstance(data_type, astx.DateTime):
            return astx.LiteralDateTime("1970-01-01T00:00:00")
        if isinstance(data_type, astx.Timestamp):
            return astx.LiteralTimestamp("1970-01-01T00:00:00")
        if isinstance(data_type, astx.Date):
            return astx.LiteralDate("1970-01-01")
        if isinstance(data_type, astx.Time):
            return astx.LiteralTime("00:00:00")

        raise ParserException(
            f"Parser: No default value defined for type "
            f"'{type(data_type).__name__}'. "
            f"An explicit initializer is required."
        )

    def parse_type(self) -> astx.DataType:
        """
        title: Parse a type annotation.
        returns:
          type: astx.DataType
        """
        if self.tokens.cur_tok.kind == TokenKind.none_literal:
            self.tokens.get_next_token()  # eat none
            return astx.NoneType()

        if self.tokens.cur_tok.kind != TokenKind.identifier:
            raise ParserException("Parser: Expected a type name")

        type_name = cast(str, self.tokens.cur_tok.value)

        if type_name == "list":
            self.tokens.get_next_token()  # eat list
            self._consume_operator("[")
            elem_type = self.parse_type()
            self._consume_operator("]")
            return astx.ListType([cast(astx.ExprType, elem_type)])

        type_map: dict[str, astx.DataType] = {
            "i8": astx.Int8(),
            "i16": astx.Int16(),
            "i32": astx.Int32(),
            "i64": astx.Int64(),
            "int8": astx.Int8(),
            "int16": astx.Int16(),
            "int32": astx.Int32(),
            "int64": astx.Int64(),
            "f16": astx.Float16(),
            "f32": astx.Float32(),
            "f64": astx.Float64(),
            "float16": astx.Float16(),
            "float32": astx.Float32(),
            "float64": astx.Float64(),
            "bool": astx.Boolean(),
            "boolean": astx.Boolean(),
            "none": astx.NoneType(),
            "str": astx.String(),
            "string": astx.String(),
            "char": astx.Int8(),
            "datetime": astx.DateTime(),
            "timestamp": astx.Timestamp(),
            "date": astx.Date(),
            "time": astx.Time(),
        }

        self.tokens.get_next_token()  # eat type identifier
        if type_name in type_map:
            return type_map[type_name]
        if type_name in self.known_class_names:
            return astx.ClassType(type_name)
        raise ParserException(f"Parser: Unknown type '{type_name}'.")

    def parse_unary(self) -> astx.AST:
        """
        title: Parse a unary expression.
        returns:
          type: astx.AST
        """
        if self._is_operator("@"):
            raise ParserException(
                "Annotations are only allowed before declarations."
            )

        if (
            self.tokens.cur_tok.kind != TokenKind.operator
            or self.tokens.cur_tok.value in ("(", "[", ",", ":", ")", "]", ";")
        ):
            return self.parse_postfix()

        op_code = cast(str, self.tokens.cur_tok.value)
        self.tokens.get_next_token()
        operand = self.parse_unary()
        unary = astx.UnaryOp(op_code, cast(astx.DataType, operand))
        unary.type_ = cast(
            astx.ExprType,
            getattr(operand, "type_", astx.ExprType()),
        )
        return unary

    def parse_bin_op_rhs(self, expr_prec: int, lhs: astx.AST) -> astx.AST:
        """
        title: Parse a binary expression rhs.
        parameters:
          expr_prec:
            type: int
          lhs:
            type: astx.AST
        returns:
          type: astx.AST
        """
        while True:
            cur_prec = self.get_tok_precedence()
            if cur_prec < expr_prec:
                return lhs

            bin_op = cast(str, self.tokens.cur_tok.value)
            bin_loc = self.tokens.cur_tok.location
            self.tokens.get_next_token()  # eat operator

            rhs = self.parse_unary()

            next_prec = self.get_tok_precedence()
            if cur_prec < next_prec:
                rhs = self.parse_bin_op_rhs(cur_prec + 1, rhs)

            lhs = astx.BinaryOp(
                bin_op,
                cast(astx.DataType, lhs),
                cast(astx.DataType, rhs),
                loc=bin_loc,
            )

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

        fn_name = cast(str, self.tokens.cur_tok.value)
        fn_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat function name

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
                arg_type = self.parse_type()

                args.append(astx.Argument(arg_name, arg_type, loc=arg_loc))

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
        ret_type = self.parse_type()

        if expect_colon:
            self._consume_operator(":")

        return astx.FunctionPrototype(
            fn_name, args, cast(AnyType, ret_type), loc=fn_loc
        )

    def parse_return_function(self) -> astx.FunctionReturn:
        """
        title: Parse the return expression.
        returns:
          type: astx.FunctionReturn
        """
        return_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat return
        value = self.parse_expression()
        return astx.FunctionReturn(cast(astx.DataType, value), loc=return_loc)
