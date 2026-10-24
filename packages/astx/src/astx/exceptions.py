"""
title: Module for Exceptions.
"""

from __future__ import annotations

from typing import Iterable, Optional, cast

from public import public

from astx.base import (
    AST,
    NO_SOURCE_LOCATION,
    ASTKind,
    ASTNodes,
    DictDataTypesStruct,
    Expr,
    ReprStruct,
    SourceLocation,
    StatementType,
)
from astx.blocks import Block
from astx.data import Identifier
from astx.tools.typing import typechecked


@public
@typechecked
class ThrowStmt(StatementType):
    """
    title: AST class for throw statements.
    summary: >-
      An absent exception models re-raising. An absent cause differs from an
      explicit LiteralNone, which suppresses implicit diagnostic context.
    attributes:
      kind:
        type: ASTKind
      exception:
        type: Optional[Expr]
      cause:
        type: Optional[Expr]
    """

    kind: ASTKind

    exception: Optional[Expr]
    cause: Optional[Expr]

    def __init__(
        self,
        exception: Optional[Expr] = None,
        parent: Optional[ASTNodes] = None,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        *,
        cause: Optional[Expr] = None,
    ) -> None:
        """
        title: Initialize the instance.
        parameters:
          exception:
            type: Optional[Expr]
          parent:
            type: Optional[ASTNodes]
          loc:
            type: SourceLocation
          cause:
            type: Optional[Expr]
        """
        super().__init__(loc=loc, parent=parent)
        self.exception = exception
        self.cause = cause
        self.kind = ASTKind.ThrowStmtKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns:
          type: str
        """
        throw_str = (
            f"ThrowStmt[{self.exception}]" if self.exception else "ThrowStmt"
        )
        return throw_str

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        key = f"THROW-STMT[{id(self)}]" if simplified else "THROW-STMT"
        value: DictDataTypesStruct = {}
        if self.exception is not None:
            value["exception"] = self.exception.get_struct(simplified)
        if self.cause is not None:
            value["cause"] = self.cause.get_struct(simplified)
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class CatchHandlerStmt(StatementType):
    """
    title: AST class for catch statements.
    summary: >-
      None means an untyped handler; an empty collection stays empty for
      semantic validation. Expressions allow qualified nominal references.
      Every supplied collection item is validated, including lazy iterables.
    attributes:
      kind:
        type: ASTKind
      body:
        type: Block[AST]
      name:
        type: Optional[Identifier]
      types:
        type: Optional[ASTNodes[Expr]]
    """

    kind: ASTKind

    body: Block[AST]
    name: Optional[Identifier]
    types: Optional[ASTNodes[Expr]]

    def __init__(
        self,
        body: Block[AST],
        name: Optional[Identifier] = None,
        types: Optional[Iterable[Expr] | ASTNodes[Expr]] = None,
        parent: Optional[ASTNodes] = None,
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize the instance.
        parameters:
          body:
            type: Block[AST]
          name:
            type: Optional[Identifier]
          types:
            type: Optional[Iterable[Expr] | ASTNodes[Expr]]
          parent:
            type: Optional[ASTNodes]
          loc:
            type: SourceLocation
        """
        super().__init__(loc=loc, parent=parent)
        self.body = body
        self.name = name

        if types is not None:
            if isinstance(types, ASTNodes):
                for item in types.nodes:
                    if not isinstance(item, Expr):
                        raise TypeError("handler types must be expressions")
                self.types = types
            else:
                self.types = ASTNodes[Expr]()
                for t in types:
                    if not isinstance(t, Expr):
                        raise TypeError("handler types must be expressions")
                    self.types.append(t)
        else:
            self.types = None

        self.kind = ASTKind.CatchHandlerStmtKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns:
          type: str
        """
        return f"CatchHandlerStmt[{self.name}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        key = (
            f"CATCH-HANDLER-STMT[{id(self)}]"
            if simplified
            else "CATCH-HANDLER-STMT"
        )
        body_dict = {"body": self.body.get_struct(simplified)}
        name_dict = (
            {"name": self.name.get_struct(simplified)} if self.name else {}
        )
        types_dict = (
            {"types": self.types.get_struct(simplified)}
            if self.types is not None
            else {}
        )

        value: DictDataTypesStruct = {
            **cast(DictDataTypesStruct, body_dict),
            **cast(DictDataTypesStruct, name_dict),
            **cast(DictDataTypesStruct, types_dict),
        }
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class ExceptionHandlerStmt(StatementType):
    """
    title: AST class for try statements.
    summary: >-
      Preserve protected, handler, normal-completion, and finalization suites
      as separate children. An absent else suite differs from an empty block.
      Clause validity and execution support belong to semantic analysis.
    attributes:
      kind:
        type: ASTKind
      body:
        type: Block[AST]
      handlers:
        type: ASTNodes[CatchHandlerStmt]
      finally_handler:
        type: Optional[FinallyHandlerStmt]
      else_body:
        type: Optional[Block[AST]]
    """

    kind: ASTKind

    body: Block[AST]
    handlers: ASTNodes[CatchHandlerStmt]
    finally_handler: Optional[FinallyHandlerStmt]
    else_body: Optional[Block[AST]]

    def __init__(
        self,
        body: Block[AST],
        handlers: Iterable[CatchHandlerStmt] | ASTNodes[CatchHandlerStmt],
        finally_handler: Optional[FinallyHandlerStmt] = None,
        parent: Optional[ASTNodes] = None,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        *,
        else_body: Optional[Block[AST]] = None,
    ) -> None:
        """
        title: Initialize the instance.
        parameters:
          body:
            type: Block[AST]
          handlers:
            type: Iterable[CatchHandlerStmt] | ASTNodes[CatchHandlerStmt]
          finally_handler:
            type: Optional[FinallyHandlerStmt]
          parent:
            type: Optional[ASTNodes]
          loc:
            type: SourceLocation
          else_body:
            type: Optional[Block[AST]]
        """
        super().__init__(loc=loc, parent=parent)
        self.body = body

        if isinstance(handlers, ASTNodes):
            for item in handlers.nodes:
                if not isinstance(item, CatchHandlerStmt):
                    raise TypeError("handlers must be CatchHandlerStmt nodes")
            self.handlers = handlers
        else:
            self.handlers = ASTNodes[CatchHandlerStmt]()
            for h in handlers:
                if not isinstance(h, CatchHandlerStmt):
                    raise TypeError("handlers must be CatchHandlerStmt nodes")
                self.handlers.append(h)

        self.finally_handler = finally_handler
        self.else_body = else_body

        self.kind = ASTKind.ExceptionHandlerStmtKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns:
          type: str
        """
        return "ExceptionHandlerStmt"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        key = (
            f"EXCEPTION-HANDLER-STMT[{id(self)}]"
            if simplified
            else "EXCEPTION-HANDLER-STMT"
        )

        body_dict = {"body": self.body.get_struct(simplified)}
        handlers_dict = {"handlers": self.handlers.get_struct(simplified)}
        finally_dict = (
            {"finally_handler": self.finally_handler.get_struct(simplified)}
            if self.finally_handler
            else {}
        )
        else_dict = (
            {"else_body": self.else_body.get_struct(simplified)}
            if self.else_body is not None
            else {}
        )

        value: DictDataTypesStruct = {
            **cast(DictDataTypesStruct, body_dict),
            **cast(DictDataTypesStruct, handlers_dict),
            **cast(DictDataTypesStruct, finally_dict),
            **cast(DictDataTypesStruct, else_dict),
        }
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class FinallyHandlerStmt(StatementType):
    """
    title: AST class for finally statements.
    attributes:
      kind:
        type: ASTKind
      body:
        type: Block[AST]
    """

    kind: ASTKind

    body: Block[AST]

    def __init__(
        self,
        body: Block[AST],
        parent: Optional[ASTNodes] = None,
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize the instance.
        parameters:
          body:
            type: Block[AST]
          parent:
            type: Optional[ASTNodes]
          loc:
            type: SourceLocation
        """
        super().__init__(loc=loc, parent=parent)
        self.body = body
        self.kind = ASTKind.FinallyHandlerStmtKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns:
          type: str
        """
        return "FinallyStmt"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        key = f"FINALLY-STMT[{id(self)}]" if simplified else "FINALLY-STMT"
        value: DictDataTypesStruct = {"body": self.body.get_struct(simplified)}

        return self._prepare_struct(key, value, simplified)
