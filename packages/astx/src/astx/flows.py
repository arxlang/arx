"""
title: Module for controle flow AST.
"""

from __future__ import annotations

from typing import Optional, cast

from public import public

from astx.base import (
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
from astx.data import Identifier, InlineVariableDeclaration
from astx.tools.typing import typechecked


@public
@typechecked
class IfStmt(StatementType):
    """
    title: AST class for `if` statement.
    attributes:
      loc: Source coordinates attached to this node.
      kind: Kind of value or operation.
      condition: Condition controlling the operation.
      then: Then.
      else_: Else.
    """

    loc: SourceLocation
    kind: ASTKind

    condition: Expr
    then: Block
    else_: Optional[Block]

    def __init__(
        self,
        condition: Expr,
        then: Block,
        else_: Optional[Block] = None,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the IfStmt instance.
        parameters:
          condition: Condition controlling the operation.
          then: Then.
          else_: Else.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.loc = loc
        self.condition = condition
        self.then = then
        self.else_ = else_
        self.kind = ASTKind.IfStmtKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return f"IfStmt[{self.condition}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        if_condition = {"condition": self.condition.get_struct(simplified)}
        if_then = {"then-block": self.then.get_struct(simplified)}
        if_else: ReprStruct = {}

        if self.else_ is not None:
            if_else = {"else-block": self.else_.get_struct(simplified)}

        key = f"IF-STMT[{id(self)}]" if simplified else "IF-STMT"
        value: ReprStruct = {
            **cast(DictDataTypesStruct, if_condition),
            **cast(DictDataTypesStruct, if_then),
            **cast(DictDataTypesStruct, if_else),
        }

        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class IfExpr(Expr):
    """
    title: AST class for `if` expression.
    attributes:
      loc: Source coordinates attached to this node.
      kind: Kind of value or operation.
      condition: Condition controlling the operation.
      then: Then.
      else_: Else.
    """

    loc: SourceLocation
    kind: ASTKind

    condition: Expr
    then: Block
    else_: Optional[Block]

    def __init__(
        self,
        condition: Expr,
        then: Block,
        else_: Optional[Block] = None,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the IfExpr instance.
        parameters:
          condition: Condition controlling the operation.
          then: Then.
          else_: Else.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.loc = loc
        self.condition = condition
        self.then = then
        self.else_ = else_
        self.kind = ASTKind.IfExprKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return f"IfExpr[{self.condition}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        if_condition = {"condition": self.condition.get_struct(simplified)}
        if_then = {"then-block": self.then.get_struct(simplified)}
        if_else: ReprStruct = {}

        if self.else_ is not None:
            if_else = {"else-block": self.else_.get_struct(simplified)}

        key = "IF-EXPR"
        value: ReprStruct = {
            **cast(DictDataTypesStruct, if_condition),
            **cast(DictDataTypesStruct, if_then),
            **cast(DictDataTypesStruct, if_else),
        }

        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class ForRangeLoopStmt(StatementType):
    """
    title: AST class for `For` Range Statement.
    attributes:
      kind: Kind of value or operation.
      variable: Variable.
      start: Starting position.
      end: End.
      step: Iteration stride.
      body: Statements forming the body.
    """

    kind: ASTKind

    variable: InlineVariableDeclaration
    start: Expr
    end: Expr
    step: Expr
    body: Block

    def __init__(
        self,
        variable: InlineVariableDeclaration,
        start: Expr,
        end: Expr,
        step: Expr,
        body: Block,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the ForRangeLoopStmt instance.
        parameters:
          variable: Variable.
          start: Starting position.
          end: End.
          step: Iteration stride.
          body: Statements forming the body.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.variable = variable
        self.start = start
        self.end = end
        self.step = step
        self.body = body
        self.kind = ASTKind.ForRangeLoopStmtKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        start = self.start
        end = self.end
        step = self.step
        var_name = self.variable.name
        return f"ForRangeLoopStmt({var_name}=[{start}:{end}:{step}])"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        for_start = {"start": self.start.get_struct(simplified)}
        for_end = {"end": self.end.get_struct(simplified)}
        for_step = {"step": self.step.get_struct(simplified)}
        for_body = self.body.get_struct(simplified)

        key = (
            f"FOR-RANGE-LOOP-STMT[{id(self)}]"
            if simplified
            else "FOR-RANGE-LOOP-STMT"
        )
        value: ReprStruct = {
            **cast(DictDataTypesStruct, for_start),
            **cast(DictDataTypesStruct, for_end),
            **cast(DictDataTypesStruct, for_step),
            **cast(DictDataTypesStruct, for_body),
        }
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class ForRangeLoopExpr(Expr):
    """
    title: AST class for `For` Range Expression.
    attributes:
      kind: Kind of value or operation.
      variable: Variable.
      start: Starting position.
      end: End.
      step: Iteration stride.
      body: Statements forming the body.
    """

    kind: ASTKind

    variable: InlineVariableDeclaration
    start: Expr
    end: Expr
    step: Expr
    body: Block

    def __init__(
        self,
        variable: InlineVariableDeclaration,
        start: Expr,
        end: Expr,
        step: Expr,
        body: Block,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the ForRangeLoopExpr instance.
        parameters:
          variable: Variable.
          start: Starting position.
          end: End.
          step: Iteration stride.
          body: Statements forming the body.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.variable = variable
        self.start = start
        self.end = end
        self.step = step
        self.body = body
        self.kind = ASTKind.ForRangeLoopExprKind
        # self.step = step if step is not None else LiteralInt32(1)

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        var_name = self.variable.name
        # note: it would be nice to have the following structure
        #    ForRangeLoopExpr({var_name}=[{start}:{end}:{step}])
        #    but we would need to have first something like a resolver
        #    otherwise it could be a very large output
        return f"ForRangeLoopExpr[{var_name}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        for_var = {"var": self.variable.get_struct(simplified)}
        for_start = {"start": self.start.get_struct(simplified)}
        for_end = {"end": self.end.get_struct(simplified)}
        for_step = {"step": self.step.get_struct(simplified)}
        for_body = self.body.get_struct(simplified)

        key = "FOR-RANGE-LOOP-EXPR"
        value: ReprStruct = {
            **cast(DictDataTypesStruct, for_var),
            **cast(DictDataTypesStruct, for_start),
            **cast(DictDataTypesStruct, for_end),
            **cast(DictDataTypesStruct, for_step),
            **cast(DictDataTypesStruct, for_body),
        }
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class ForCountLoopStmt(StatementType):
    """
    title: AST class for a simple Count-Controlled `For` Loop statement.
    summary: >2-

      This is a very basic `for` loop, used by languages like C or C++.
    attributes:
      kind: Kind of value or operation.
      initializer: Expression providing the initial value.
      condition: Condition controlling the operation.
      update: Update.
      body: Statements forming the body.
    """

    kind: ASTKind

    initializer: InlineVariableDeclaration
    condition: Expr
    update: Expr
    body: Block

    def __init__(
        self,
        initializer: InlineVariableDeclaration,
        condition: Expr,
        update: Expr,
        body: Block,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the ForCountLoopStmt instance.
        parameters:
          initializer: Expression providing the initial value.
          condition: Condition controlling the operation.
          update: Update.
          body: Statements forming the body.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.initializer = initializer
        self.condition = condition
        self.update = update
        self.body = body
        self.kind = ASTKind.ForCountLoopStmtKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        init = self.initializer
        cond = self.condition
        update = self.update
        return f"ForCountLoopStmt({init};{cond};{update})"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        for_init = {"initialization": self.initializer.get_struct(simplified)}
        for_cond = {"condition": self.condition.get_struct(simplified)}
        for_update = {"update": self.update.get_struct(simplified)}
        for_body = self.body.get_struct(simplified)

        key = f"FOR-COUNT-STMT[{id(self)}]" if simplified else "FOR-COUNT-STMT"
        value: ReprStruct = {
            **cast(DictDataTypesStruct, for_init),
            **cast(DictDataTypesStruct, for_cond),
            **cast(DictDataTypesStruct, for_update),
            **cast(DictDataTypesStruct, for_body),
        }

        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class ForCountLoopExpr(Expr):
    """
    title: AST class for a simple Count-Controlled `For` Loop expression.
    summary: >2-

      This is a very basic `for` loop, used by languages like C or C++.
    attributes:
      kind: Kind of value or operation.
      initializer: Expression providing the initial value.
      condition: Condition controlling the operation.
      update: Update.
      body: Statements forming the body.
    """

    kind: ASTKind

    initializer: InlineVariableDeclaration
    condition: Expr
    update: Expr
    body: Block

    def __init__(
        self,
        initializer: InlineVariableDeclaration,
        condition: Expr,
        update: Expr,
        body: Block,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the ForLoopCountExpr instance.
        parameters:
          initializer: Expression providing the initial value.
          condition: Condition controlling the operation.
          update: Update.
          body: Statements forming the body.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.initializer = initializer
        self.condition = condition
        self.update = update
        self.body = body
        self.kind = ASTKind.ForCountLoopExprKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        init = self.initializer
        cond = self.condition
        update = self.update
        return f"ForCountLoopExpr({init};{cond};{update})"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        for_init = {"initialization": self.initializer.get_struct(simplified)}
        for_cond = {"condition": self.condition.get_struct(simplified)}
        for_update = {"update": self.update.get_struct(simplified)}
        for_body = self.body.get_struct(simplified)

        key = "FOR-COUNT-EXPR"
        value: ReprStruct = {
            **cast(DictDataTypesStruct, for_init),
            **cast(DictDataTypesStruct, for_cond),
            **cast(DictDataTypesStruct, for_update),
            **cast(DictDataTypesStruct, for_body),
        }
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class AsyncForRangeLoopStmt(StatementType):
    """
    title: AST class for asynchronous `For` Range Statement.
    attributes:
      kind: Kind of value or operation.
      variable: Variable.
      start: Starting position.
      end: End.
      step: Iteration stride.
      body: Statements forming the body.
    """

    kind: ASTKind

    variable: InlineVariableDeclaration
    start: Optional[Expr]
    end: Expr
    step: Optional[Expr]
    body: Block

    def __init__(
        self,
        variable: InlineVariableDeclaration,
        start: Optional[Expr],
        end: Expr,
        step: Optional[Expr],
        body: Block,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the AsyncForRangeLoopStmt instance.
        parameters:
          variable: Variable.
          start: Starting position.
          end: End.
          step: Iteration stride.
          body: Statements forming the body.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.variable = variable
        self.start = start
        self.end = end
        self.step = step
        self.body = body
        self.kind = ASTKind.AsyncRangeLoopStmtKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        start = self.start
        end = self.end
        step = self.step
        var_name = self.variable.name
        return f"AsyncForRangeLoopStmt({var_name}=[{start}:{end}:{step}])"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        for_start = {
            "start": {}
            if self.start is None
            else self.start.get_struct(simplified)
        }
        for_end = {"end": self.end.get_struct(simplified)}
        for_step = {
            "step": {}
            if self.step is None
            else self.step.get_struct(simplified)
        }
        for_body = self.body.get_struct(simplified)

        key = "ASYNC-FOR-RANGE-LOOP-STMT"
        value: ReprStruct = {
            **cast(DictDataTypesStruct, for_start),
            **cast(DictDataTypesStruct, for_end),
            **cast(DictDataTypesStruct, for_step),
            **cast(DictDataTypesStruct, for_body),
        }
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class AsyncForRangeLoopExpr(Expr):
    """
    title: AST class for asynchronous `For` Range Expression.
    attributes:
      kind: Kind of value or operation.
      variable: Variable.
      start: Starting position.
      end: End.
      step: Iteration stride.
      body: Statements forming the body.
    """

    kind: ASTKind

    variable: InlineVariableDeclaration
    start: Optional[Expr]
    end: Expr
    step: Optional[Expr]
    body: Block

    def __init__(
        self,
        variable: InlineVariableDeclaration,
        start: Optional[Expr],
        end: Expr,
        step: Optional[Expr],
        body: Block,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the AsyncForRangeLoopExpr instance.
        parameters:
          variable: Variable.
          start: Starting position.
          end: End.
          step: Iteration stride.
          body: Statements forming the body.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.variable = variable
        self.start = start
        self.end = end
        self.step = step
        self.body = body
        self.kind = ASTKind.AsyncRangeLoopExprKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        var_name = self.variable.name
        return f"AsyncForRangeLoopExpr[{var_name}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        for_var = {"var": self.variable.get_struct(simplified)}
        for_start = {
            "start": {}
            if self.start is None
            else self.start.get_struct(simplified)
        }
        for_end = {"end": self.end.get_struct(simplified)}
        for_step = {
            "step": {}
            if self.step is None
            else self.step.get_struct(simplified)
        }
        for_body = self.body.get_struct(simplified)

        key = "ASYNC-FOR-RANGE-LOOP-EXPR"
        value: ReprStruct = {
            **cast(DictDataTypesStruct, for_var),
            **cast(DictDataTypesStruct, for_start),
            **cast(DictDataTypesStruct, for_end),
            **cast(DictDataTypesStruct, for_step),
            **cast(DictDataTypesStruct, for_body),
        }
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class BreakStmt(StatementType):
    """
    title: AST class for break statement.
    attributes:
      kind: Kind of value or operation.
    """

    kind: ASTKind

    def __init__(
        self,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the BreakStmt instance.
        parameters:
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.kind = ASTKind.BreakStmtKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return "BreakStmt"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = "BREAK-STMT"
        value: DictDataTypesStruct = {}
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class ContinueStmt(StatementType):
    """
    title: AST class for continue statement.
    attributes:
      kind: Kind of value or operation.
    """

    kind: ASTKind

    def __init__(
        self,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the ContinueStmt instance.
        parameters:
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.kind = ASTKind.ContinueStmtKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return "ContinueStmt"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = "CONTINUE-STMT"
        value: DictDataTypesStruct = {}
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class WhileStmt(StatementType):
    """
    title: AST class for `while` statement.
    attributes:
      kind: Kind of value or operation.
      condition: Condition controlling the operation.
      body: Statements forming the body.
    """

    kind: ASTKind

    condition: Expr
    body: Block

    def __init__(
        self,
        condition: Expr,
        body: Block,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the WhileStmt instance.
        parameters:
          condition: Condition controlling the operation.
          body: Statements forming the body.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.condition = condition
        self.body = body
        self.kind = ASTKind.WhileStmtKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return f"WhileStmt[{self.condition}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        while_condition = self.condition.get_struct(simplified)
        while_body = self.body.get_struct(simplified)

        key = f"WHILE-STMT[{id(self)}]" if simplified else "WHILE-STMT"
        value: ReprStruct = {
            **cast(DictDataTypesStruct, while_condition),
            **cast(DictDataTypesStruct, while_body),
        }

        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class WhileExpr(Expr):
    """
    title: AST class for `while` expression.
    attributes:
      kind: Kind of value or operation.
      condition: Condition controlling the operation.
      body: Statements forming the body.
    """

    kind: ASTKind

    condition: Expr
    body: Block

    def __init__(
        self,
        condition: Expr,
        body: Block,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the WhileExpr instance.
        parameters:
          condition: Condition controlling the operation.
          body: Statements forming the body.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.condition = condition
        self.body = body
        self.kind = ASTKind.WhileExprKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return f"WhileExpr[{self.condition}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        while_condition = self.condition.get_struct(simplified)
        while_body = self.body.get_struct(simplified)

        key = "WHILE-EXPR"
        value: ReprStruct = {
            **cast(DictDataTypesStruct, while_condition),
            **cast(DictDataTypesStruct, while_body),
        }

        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class CaseStmt(StatementType):
    """
    title: AST class for a case in a Switch statement.
    attributes:
      kind: Kind of value or operation.
      condition: Condition controlling the operation.
      body: Statements forming the body.
      default: Default used when no value is supplied.
    """

    kind: ASTKind

    condition: Optional[Expr] = None
    body: Block
    default: bool = False

    def __init__(
        self,
        body: Block,
        condition: Optional[Expr] = None,
        default: bool = False,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the CaseStmt instance.
        parameters:
          body: Statements forming the body.
          condition: Condition controlling the operation.
          default: Default used when no value is supplied.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.condition = condition
        self.body = body
        self.default = default
        self.kind = ASTKind.CaseStmtKind

        if self.default is False and self.condition is None:
            raise ValueError(
                "Condition must be provided for non-default branches."
            )

        if self.default is True and self.condition is not None:
            raise ValueError(
                "Condition must NOT be provided for default branches."
            )

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return (
            f"CaseStmt[{self.condition}]"
            if self.condition
            else "CaseStmt[default]"
        )

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        default_case = "default" if self.condition is None else ""
        default_only = "[default]" if self.condition is None else ""
        id_str = f"{id(self)}" if simplified else ""

        key = (
            f"CASE-STMT[{id_str}{default_case}]"
            if simplified and self.condition is not None
            else f"CASE-STMT[{id_str}, {default_case}]"
            if simplified
            else f"CASE-STMT{default_only}"
        )

        condition_dict = (
            {}
            if self.condition is None
            else {"condition": self.condition.get_struct(simplified)}
        )
        value = {
            **cast(DictDataTypesStruct, condition_dict),
            "body": self.body.get_struct(simplified),
        }
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class SwitchStmt(StatementType):
    """
    title: AST class for Switch statements based on Rust's match syntax.
    attributes:
      kind: Kind of value or operation.
      value: Stored value.
      cases: Cases.
    """

    kind: ASTKind

    value: Expr
    cases: ASTNodes[CaseStmt]

    def __init__(
        self,
        value: Expr,
        cases: list[CaseStmt] | ASTNodes[CaseStmt],
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the SwitchStmt instance.
        parameters:
          value: Value to process.
          cases: Cases.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.value = value

        if isinstance(cases, ASTNodes):
            self.cases = cases
        else:
            self.cases = ASTNodes[CaseStmt]()
            for case in cases:
                self.cases.append(case)

        self.kind = ASTKind.SwitchStmtKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return f"SwitchStmt[{len(self.cases)}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"SWITCH-STMT[{id(self)}]" if simplified else "SWITCH-STMT"
        case_dict = {}
        for d in range(len(self.cases)):
            case_dict[f"case_{d}"] = self.cases[d].get_struct(simplified)

        value: DictDataTypesStruct = {
            "value": self.value.get_struct(simplified),
            **cast(DictDataTypesStruct, {"cases": case_dict}),
        }
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class GotoStmt(StatementType):
    """
    title: AST class for function `Goto` statement.
    attributes:
      kind: Kind of value or operation.
      label: Label.
    """

    kind: ASTKind

    label: Identifier

    def __init__(
        self,
        label: Identifier,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the Return instance.
        parameters:
          label: Label.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.label = label
        self.kind = ASTKind.GotoStmtKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return f"Goto[{self.label.name}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"GOTO-STMT[{self.label.name}]"
        value: DictDataTypesStruct = {}
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class DoWhileStmt(WhileStmt):
    """
    title: AST class for `do-while` statement.
    attributes:
      condition: Condition controlling the operation.
      body: Statements forming the body.
      kind: Kind of value or operation.
    """

    kind: ASTKind

    def __init__(
        self,
        condition: Expr,
        body: Block,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the DoWhileStmt instance.
        parameters:
          condition: Condition controlling the operation.
          body: Statements forming the body.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(
            condition=condition, body=body, loc=loc, parent=parent
        )
        self.kind = ASTKind.DoWhileStmtKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return f"DoWhileStmt[{self.condition}]"


@public
@typechecked
class DoWhileExpr(WhileExpr):
    """
    title: AST class for `do-while` expression.
    attributes:
      condition: Condition controlling the operation.
      body: Statements forming the body.
      kind: Kind of value or operation.
    """

    kind: ASTKind

    def __init__(
        self,
        condition: Expr,
        body: Block,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the DoWhileExpr instance.
        parameters:
          condition: Condition controlling the operation.
          body: Statements forming the body.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(
            condition=condition, body=body, loc=loc, parent=parent
        )
        self.kind = ASTKind.DoWhileExprKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return f"DoWhileExpr[{self.condition}]"
