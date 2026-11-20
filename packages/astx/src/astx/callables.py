"""
title: Module for callable ASTx.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, cast

from public import private, public

from astx.base import (
    NO_SOURCE_LOCATION,
    ASTKind,
    ASTNodes,
    DataType,
    Expr,
    ReprStruct,
    SourceLocation,
    StatementType,
    Undefined,
)
from astx.blocks import Block
from astx.data import Variable
from astx.modifiers import MutabilityKind, ScopeKind, VisibilityKind
from astx.tools.typing import typechecked
from astx.types import AnyType

UNDEFINED = Undefined()


@public
@typechecked
class Argument(Variable):
    """
    title: AST class for argument definition.
    attributes:
      kind: Kind of value or operation.
      mutability: Mutability.
      name: Name identifying this declaration.
      type_: Type associated with this expression.
      default: Default used when no value is supplied.
    """

    kind: ASTKind

    mutability: MutabilityKind
    name: str
    type_: DataType
    default: Expr

    def __init__(
        self,
        name: str,
        type_: DataType,
        mutability: MutabilityKind = MutabilityKind.constant,
        default: Expr = UNDEFINED,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the VarExprAST instance.
        parameters:
          name: Name identifying the declaration or operation.
          type_: Type expression to process.
          mutability: Mutability.
          default: Default used when no value is supplied.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(name=name, loc=loc, parent=parent)
        self.mutability = mutability
        self.type_ = type_
        self.default = default
        self.kind = ASTKind.ArgumentKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        type_ = self.type_.__class__.__name__
        return f"Argument[{self.name}, {type_}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"Argument[{self.name}, {self.type_}] = {self.default}"
        value = self.default.get_struct()
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class Arguments(ASTNodes[Argument]):
    """
    title: AST class for argument definition.
    """

    def __init__(self, *args: Argument, **kwargs: Any) -> None:
        """
        title: Initialize the arguments collection.
        parameters:
          args:
            variadic: positional
            description: Positional arguments.
          kwargs:
            variadic: keyword
            description: Keyword arguments.
        """
        super().__init__(**kwargs)
        for arg in args:
            self.append(arg)

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        return f"Arguments({len(self.nodes)})"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        args_nodes = []

        for node in self.nodes:
            args_nodes.append(node.get_struct(simplified))

        key = str(self)
        value = cast(ReprStruct, args_nodes)
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class KeywordArgument(Expr):
    """
    title: One named call argument, preserving its source expression.
    attributes:
      name: Name identifying this declaration.
      value: Stored value.
    """

    name: str
    value: DataType

    def __init__(
        self,
        name: str,
        value: DataType,
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize a named argument.
        parameters:
          name: Name identifying the declaration or operation.
          value: Value to process.
          loc: Source coordinates associated with the node.
        """
        super().__init__(loc=loc)
        self.name = name
        self.value = value

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Render the named argument and its value.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        return self._prepare_struct(
            f"KEYWORD[{self.name}]",
            self.value.get_struct(simplified),
            simplified,
        )


@private
@typechecked
def materialize_call_operands(
    args: Iterable[DataType],
) -> tuple[DataType, ...]:
    """
    title: Snapshot and validate iterable call operands, including generators.
    parameters:
      args: Arguments supplied to the operation.
    returns: 'Result of this operation: snapshot and validate iterable call
      operands, including generators.'
    """
    return tuple(args)


@public
@typechecked
class FunctionCall(DataType):
    """
    title: AST class for function call.
    attributes:
      kind: Kind of value or operation.
      keywords: Keywords.
      fn: Function to process.
      args: Declared or supplied call arguments.
      type_: Type associated with this expression.
    """

    kind: ASTKind

    keywords: tuple[KeywordArgument, ...]
    fn: str
    args: Iterable[DataType]
    type_: DataType = AnyType()

    def __init__(
        self,
        fn: FunctionDef | str,
        args: Iterable[DataType],
        type_: DataType = AnyType(),
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
        *,
        keywords: tuple[KeywordArgument, ...] = (),
    ) -> None:
        """
        title: Initialize the Call instance.
        parameters:
          fn: Function to process.
          args: Arguments supplied to the operation.
          type_: Type expression to process.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
          keywords: Keywords.
        """
        super().__init__(loc=loc, parent=parent)
        self.fn = fn if not isinstance(fn, FunctionDef) else fn.name
        self.args = materialize_call_operands(args)
        self.keywords = keywords
        self.kind = ASTKind.CallKind
        self.type_ = type_

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        args = [str(arg) for arg in self.args]
        args.extend(f"{item.name}={item.value}" for item in self.keywords)
        return f"Call[{self.fn}: {', '.join(args)}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        call_params = []

        for node in self.args:
            call_params.append(node.get_struct(simplified))

        key = f"FUNCTION-CALL[{self.fn}]"
        value = cast(
            ReprStruct,
            {
                f"Parameters ({len(call_params)})": {
                    f"param({idx})": param
                    for idx, param in enumerate(call_params)
                }
            },
        )

        if self.keywords and isinstance(value, dict):
            value["Keywords"] = [
                item.get_struct(simplified) for item in self.keywords
            ]
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class FunctionPrototype(StatementType):
    """
    title: AST class for function prototype declaration.
    attributes:
      loc: Source coordinates attached to this node.
      kind: Kind of value or operation.
      name: Name identifying this declaration.
      args: Declared or supplied call arguments.
      return_type: Declared result type.
      scope: Scope used to resolve names.
      visibility: Visibility.
    """

    loc: SourceLocation
    kind: ASTKind

    name: str
    args: Arguments
    return_type: AnyType
    scope: ScopeKind
    visibility: VisibilityKind

    def __init__(
        self,
        name: str,
        args: Arguments,
        return_type: AnyType,
        scope: ScopeKind = ScopeKind.global_,
        visibility: VisibilityKind = VisibilityKind.public,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the FunctionPrototype instance.
        parameters:
          name: Name identifying the declaration or operation.
          args: Arguments supplied to the operation.
          return_type: Declared result type.
          scope: Scope used to resolve names.
          visibility: Visibility.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.name = name
        self.args = args
        self.return_type = return_type
        self.loc = loc
        self.kind = ASTKind.PrototypeKind
        self.scope = scope
        self.visibility = visibility

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Get the AST structure that represent the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        raise Exception("Visitor method not necessary")


@public
@typechecked
class FunctionReturn(StatementType):
    """
    title: AST class for function `return` statement.
    attributes:
      kind: Kind of value or operation.
      value: Stored value.
    """

    kind: ASTKind

    value: DataType

    def __init__(
        self,
        value: DataType,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the Return instance.
        parameters:
          value: Value to process.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.value = value
        self.kind = ASTKind.ReturnKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return f"Return[{self.value}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = "RETURN"
        value = self.value.get_struct(simplified)
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class FunctionDef(StatementType):
    """
    title: AST class for function definition.
    attributes:
      kind: Kind of value or operation.
      prototype: Prototype.
      body: Statements forming the body.
      name: Name identifying this declaration.
    """

    kind: ASTKind

    prototype: FunctionPrototype
    body: Block

    def __init__(
        self,
        prototype: FunctionPrototype,
        body: Block,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the Function instance.
        parameters:
          prototype: Prototype.
          body: Statements forming the body.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.prototype = prototype
        self.body = body
        self.kind = ASTKind.FunctionDefKind

    @property
    def name(self) -> str:
        """
        title: Return the function prototype name.
        returns: The function prototype name.
        """
        return self.prototype.name

    def __str__(self) -> str:
        """
        title: Return a string that represent the object.
        returns: String representation of this instance.
        """
        return f"FunctionDef[{self.name}]"

    def __call__(
        self,
        args: tuple[DataType, ...],
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> FunctionCall:
        """
        title: Initialize the Call instance.
        parameters:
          args: Arguments supplied to the operation.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        returns: 'Result of this operation: initialize the Call instance.'
        """
        return FunctionCall(fn=self, args=args, loc=loc, parent=parent)

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Get the AST structure that represent the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        fn_args = self.prototype.args.get_struct(simplified)
        fn_body = self.body.get_struct(simplified)

        key = f"FUNCTION-DEF[{self.prototype.name}]"
        args_struct = {"args": fn_args}
        body_struct = {"body": fn_body}

        value: ReprStruct = {**args_struct, **body_struct}
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class LambdaExpr(Expr):
    """
    title: AST class for lambda expressions.
    attributes:
      kind: Kind of value or operation.
      params: Params.
      body: Statements forming the body.
    """

    kind: ASTKind

    params: Arguments = Arguments()
    body: Expr

    def __init__(
        self,
        body: Expr,
        params: Arguments = Arguments(),
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the lambda expression.
        parameters:
          body: Statements forming the body.
          params: Params.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.params = params
        self.body = body
        self.kind = ASTKind.LambdaExprKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the lambda expression.
        returns: String representation of this instance.
        """
        params_str = ", ".join(param.name for param in self.params)
        return f"lambda {params_str}: {self.body}"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the lambda expression.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = "LambdaExpr"
        value: ReprStruct = {
            "params": self.params.get_struct(simplified),
            "body": self.body.get_struct(simplified),
        }
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class FunctionAsyncDef(FunctionDef):
    """
    title: AST class for async function definition.
    attributes:
      kind: Kind of value or operation.
      prototype: Prototype.
      body: Statements forming the body.
      name: Name identifying this declaration.
    """

    kind: ASTKind

    prototype: FunctionPrototype
    body: Block

    def __init__(
        self,
        prototype: FunctionPrototype,
        body: Block,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the FunctionAsync instance.
        parameters:
          prototype: Prototype.
          body: Statements forming the body.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(
            loc=loc, parent=parent, body=body, prototype=prototype
        )
        self.kind = ASTKind.FunctionAsyncDefKind

    def __str__(self) -> str:
        """
        title: Return a string that represent the object.
        returns: String representation of this instance.
        """
        return f"FunctionAsyncDef[{self.name}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Get the AST structure that represent the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        fn_args = self.prototype.args.get_struct(simplified)
        fn_body = self.body.get_struct(simplified)

        key = f"FUNCTIONASYNC-DEF[{self.prototype.name}]"
        args_struct = {"args": fn_args}
        body_struct = {"body": fn_body}

        value: ReprStruct = {**args_struct, **body_struct}
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class AwaitExpr(Expr):
    """
    title: AST class for AwaitExpr.
    attributes:
      kind: Kind of value or operation.
      value: Stored value.
    """

    kind: ASTKind

    value: Optional[Expr]

    def __init__(
        self,
        value: Optional[Expr],
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the AwaitExpr instance.
        parameters:
          value: Value to process.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.value = value
        self.kind = ASTKind.AwaitExprKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return f"AwaitExpr[{self.value}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = "AWAIT-EXPR"
        value = {} if self.value is None else self.value.get_struct(simplified)
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class YieldExpr(Expr):
    """
    title: AST class for YieldExpr.
    attributes:
      kind: Kind of value or operation.
      value: Stored value.
    """

    kind: ASTKind

    value: Optional[Expr]

    def __init__(
        self,
        value: Optional[Expr],
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the YieldExpr instance.
        parameters:
          value: Value to process.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.value = value
        self.kind = ASTKind.YieldExprKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return f"YieldExpr[{self.value}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = "YIELD-EXPR"
        value = {} if self.value is None else self.value.get_struct(simplified)
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class YieldStmt(StatementType):
    """
    title: AST class for yield statement.
    attributes:
      kind: Kind of value or operation.
      value: Stored value.
    """

    kind: ASTKind

    value: Optional[Expr]

    def __init__(
        self,
        value: Optional[Expr] = None,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the YieldStmt instance.
        summary: >2-

          value: The expression to yield (optional)

          loc: Source location of the statement

          parent: Parent AST node
        parameters:
          value: Value to process.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.value = value
        self.kind = ASTKind.YieldStmtKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return (
            f"YieldStmt[{self.value}]"
            if self.value is not None
            else "YieldStmt"
        )

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"YIELD-STMT[{id(self)}]" if simplified else "YIELD-STMT"
        value = (
            self.value.get_struct(simplified) if self.value is not None else {}
        )
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class YieldFromExpr(Expr):
    """
    title: AST class for YieldFromExpr.
    attributes:
      kind: Kind of value or operation.
      value: Stored value.
    """

    kind: ASTKind

    value: Expr

    def __init__(
        self,
        value: Expr,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the YieldFromExpr instance.
        parameters:
          value: Value to process.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.value = value
        self.kind = ASTKind.YieldFromExprKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return f"YieldFromExpr[{self.value}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = "YIELDFROM-EXPR"
        value = self.value.get_struct(simplified)
        return self._prepare_struct(key, value, simplified)
