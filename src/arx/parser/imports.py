"""
title: Import parser mixin.
summary: >-
  Parse import statements and grouped import syntax while reusing the shared
  parser core helpers.
"""

from __future__ import annotations

from typing import cast

from irx import astx

from arx.exceptions import ParserException
from arx.lexer import TokenKind
from arx.parser.base import ParserMixinBase


class ImportParserMixin(ParserMixinBase):
    """
    title: Import parser mixin.
    """

    def parse_import_stmt(self) -> astx.ImportStmt | astx.ImportFromStmt:
        """
        title: Parse one import statement.
        returns:
          type: astx.ImportStmt | astx.ImportFromStmt
        """
        import_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat import

        if self._is_operator("("):
            names = self.parse_grouped_import_names()
            if not self._is_identifier_value("from"):
                raise ParserException(
                    "Grouped imports require 'from <module.path>'."
                )
            self._consume_identifier_value("from")
            level, module_path = self.parse_import_from_module_path()
            return astx.ImportFromStmt(
                names=names,
                module=module_path,
                level=level,
                loc=import_loc,
            )

        if self._is_identifier_value("from"):
            raise ParserException(
                "Expected module path or imported name after 'import'."
            )

        if self._is_identifier_value("as"):
            raise ParserException(
                "alias requires an import target before 'as'"
            )

        if self.tokens.cur_tok.kind != TokenKind.identifier:
            raise ParserException(
                "Expected module path or imported name after 'import'."
            )

        target_name = cast(str, self.tokens.cur_tok.value)
        target_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()

        if self._is_operator("."):
            module_path = self.parse_module_path(prefix=target_name)
            alias_name = self.parse_import_alias()
            if self._is_identifier_value("from"):
                raise ParserException("Module imports do not use 'from'.")
            return astx.ImportStmt(
                [
                    astx.AliasExpr(
                        module_path,
                        asname=alias_name,
                        loc=target_loc,
                    )
                ],
                loc=import_loc,
            )

        alias_name = self.parse_import_alias()
        if self._is_identifier_value("from"):
            self._consume_identifier_value("from")
            level, module_path = self.parse_import_from_module_path()
            return astx.ImportFromStmt(
                names=[
                    astx.AliasExpr(
                        target_name,
                        asname=alias_name,
                        loc=target_loc,
                    )
                ],
                module=module_path,
                level=level,
                loc=import_loc,
            )

        if self._is_operator(","):
            raise ParserException("Grouped imports require parentheses.")

        if self._is_operator("("):
            raise ParserException(
                "Parentheses are only supported for grouped named imports."
            )

        return astx.ImportStmt(
            [astx.AliasExpr(target_name, asname=alias_name, loc=target_loc)],
            loc=import_loc,
        )

    def parse_grouped_import_names(self) -> list[astx.AliasExpr]:
        """
        title: Parse grouped named imports.
        returns:
          type: list[astx.AliasExpr]
        """
        self._consume_operator("(")
        self._skip_import_layout()

        if self._is_operator(")"):
            raise ParserException("empty grouped imports are not allowed")

        names: list[astx.AliasExpr] = []
        while True:
            if self._is_identifier_value("as"):
                raise ParserException(
                    "alias requires an import target before 'as'"
                )
            if self.tokens.cur_tok.kind != TokenKind.identifier:
                raise ParserException(
                    "Expected imported name in grouped import list."
                )

            name = cast(str, self.tokens.cur_tok.value)
            name_loc = self.tokens.cur_tok.location
            self.tokens.get_next_token()
            alias_name = self.parse_import_alias()
            names.append(astx.AliasExpr(name, asname=alias_name, loc=name_loc))

            self._skip_import_layout()
            if self._is_operator(")"):
                break

            self._consume_operator(",")
            self._skip_import_layout()
            if self._is_operator(")"):
                break

        self._consume_operator(")")
        return names

    def parse_import_alias(self) -> str:
        """
        title: Parse one optional import alias.
        returns:
          type: str
        """
        if not self._is_identifier_value("as"):
            return ""

        self._consume_identifier_value("as")
        if self.tokens.cur_tok.kind != TokenKind.identifier:
            raise ParserException("Expected alias name after 'as'.")

        alias_name = cast(str, self.tokens.cur_tok.value)
        self.tokens.get_next_token()
        return alias_name

    def parse_module_path(self, prefix: str | None = None) -> str:
        """
        title: Parse one dotted module path.
        parameters:
          prefix:
            type: str | None
        returns:
          type: str
        """
        parts: list[str] = []
        if prefix is not None:
            parts.append(prefix)
        else:
            if self.tokens.cur_tok.kind != TokenKind.identifier:
                raise ParserException("Expected module path.")
            parts.append(cast(str, self.tokens.cur_tok.value))
            self.tokens.get_next_token()

        while self._is_operator("."):
            self._consume_operator(".")
            if self.tokens.cur_tok.kind != TokenKind.identifier:
                raise ParserException(
                    "Expected identifier after '.' in module path."
                )
            parts.append(cast(str, self.tokens.cur_tok.value))
            self.tokens.get_next_token()

        return ".".join(parts)

    def parse_import_from_module_path(self) -> tuple[int, str]:
        """
        title: Parse one absolute or relative module path for from-imports.
        returns:
          type: tuple[int, str]
        """
        level = 0
        while self._is_operator("."):
            self._consume_operator(".")
            level += 1

        if level > 0 and self.tokens.cur_tok.kind != TokenKind.identifier:
            raise ParserException(
                "Relative imports require a module path after leading '.'."
            )

        return level, self.parse_module_path()
