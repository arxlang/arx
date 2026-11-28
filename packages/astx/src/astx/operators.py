"""
title: ASTx classes for the operators.
attributes:
  OpCodeAugAssign: Op code aug assign.
  OpCodeCompare: Spelling of a scalar comparison operator.
"""

from __future__ import annotations

from typing import Iterable, Literal, Optional, cast

from public import public
from typing_extensions import TypeAlias

from astx.base import (
    NO_SOURCE_LOCATION,
    ASTKind,
    ASTNodes,
    DataType,
    DictDataTypesStruct,
    Expr,
    ReprStruct,
    SourceLocation,
    StatementType,
)
from astx.data import Identifier, Variable
from astx.tools.typing import typechecked


@public
@typechecked
class WalrusOp(DataType):
    """
    title: AST class for the Walrus (assignment expression) operator.
    attributes:
      lhs: Left operand.
      rhs: Right operand.
      kind: Kind of value or operation.
    """

    lhs: Variable
    rhs: DataType
    kind: ASTKind

    def __init__(
        self,
        lhs: Variable,
        rhs: DataType,
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize the WalrusOp instance.
        parameters:
          lhs: Left operand.
          rhs: Right operand.
          loc: Source coordinates associated with the node.
        """
        super().__init__(loc=loc)
        self.lhs = lhs
        self.rhs = rhs
        self.kind = ASTKind.WalrusOpKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        return f"WalrusOp[:=]({self.lhs} := {self.rhs})"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure that represents the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = "WALRUS[:=]"
        lhs = {"lhs": self.lhs.get_struct(simplified)}
        rhs = {"rhs": self.rhs.get_struct(simplified)}

        content: ReprStruct = {**lhs, **rhs}
        return self._prepare_struct(key, content, simplified)


@public
@typechecked
class AssignmentExpr(Expr):
    """
    title: AST class for assignment expressions.
    attributes:
      kind: Kind of value or operation.
      targets: Targets.
      value: Stored value.
    """

    kind: ASTKind

    targets: ASTNodes[Expr]
    value: Expr

    def __init__(
        self,
        targets: Iterable[Expr] | ASTNodes[Expr],
        value: Expr,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the assignment expression.
        parameters:
          targets: Targets.
          value: Value to process.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)

        if isinstance(targets, ASTNodes):
            self.targets = targets
        else:
            self.targets = ASTNodes()
            for target in targets:
                self.targets.append(target)

        self.value = value
        self.kind = ASTKind.AssignmentExprKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        return f"AssignmentExpr[{self.value}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = "ASSIGNMENT-EXPR"
        targets_dict = {"targets": self.targets.get_struct(simplified)}
        value_dict = {"value": self.value.get_struct(simplified)}

        value = {
            **cast(DictDataTypesStruct, targets_dict),
            **cast(DictDataTypesStruct, value_dict),
        }

        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class VariableAssignment(StatementType):
    """
    title: AST class for variable declaration.
    attributes:
      loc: Source coordinates attached to this node.
      kind: Kind of value or operation.
      name: Name identifying this declaration.
      value: Stored value.
    """

    loc: SourceLocation
    kind: ASTKind

    name: str
    value: Expr

    def __init__(
        self,
        name: str,
        value: Expr,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the VarExprAST instance.
        parameters:
          name: Name identifying the declaration or operation.
          value: Value to process.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.loc = loc
        self.name = name
        self.value = value
        self.kind = ASTKind.VariableAssignmentKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        return f"VariableAssignment[{self.name}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = str(self)
        value = self.value.get_struct(simplified)
        return self._prepare_struct(key, value, simplified)


OpCodeAugAssign: TypeAlias = Literal[
    "+=",
    "-=",
    "*=",
    "/=",
    "//=",
    "%=",
    "**=",
    "&=",
    "|=",
    "^=",
    "<<=",
    ">>=",
]


@public
@typechecked
class AugAssign(DataType):
    """
    title: AST class for augmented assignment.
    summary: Model a single identifier target and RHS value. The
      operation yields the stored value internally; frontends may
      restrict it to statement contexts. Operator modeling does
      not imply backend support. Numeric, mutability, conversion,
      and failure rules belong to semantic analysis and lowering.
    attributes:
      kind: Kind of value or operation.
      target: Destination of the operation.
      op_code: Operator spelling.
      value: Stored value.
    """

    kind: ASTKind

    target: Identifier
    op_code: OpCodeAugAssign
    value: DataType

    def __init__(
        self,
        target: Identifier,
        op_code: OpCodeAugAssign,
        value: DataType,
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize the augmented assignment.
        parameters:
          target: Destination of the operation.
          op_code: Operator spelling.
          value: Value to process.
          loc: Source coordinates associated with the node.
        """
        super().__init__(loc=loc)
        self.target = target
        self.op_code = op_code
        self.value = value
        self.kind = ASTKind.AugmentedAssignKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the augmented assignment object.
        returns: String representation of this instance.
        """
        return f"AugAssign[{self.op_code}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = str(self)
        value: ReprStruct = {
            "target": self.target.get_struct(simplified),
            "value": self.value.get_struct(simplified),
        }
        return self._prepare_struct(key, value, simplified)


OpCodeCompare: TypeAlias = Literal["==", "!=", "<", ">", "<=", ">="]


@public
@typechecked
class CompareOp(DataType):
    """
    title: Represent adjacent comparisons over a sequence of operands.
    attributes:
      ops: Ops.
      comparators: Comparators.
      operator_locations: Source locations of the comparison operators.
      left: Left operand.
      kind: Kind of value or operation.
    """

    ops: list[OpCodeCompare]
    comparators: list[DataType]
    operator_locations: list[SourceLocation]
    left: DataType
    kind: ASTKind

    def __init__(
        self,
        left: DataType,
        ops: Iterable[OpCodeCompare],
        comparators: Iterable[DataType],
        loc: SourceLocation = NO_SOURCE_LOCATION,
        *,
        operator_locations: Iterable[SourceLocation] | None = None,
    ) -> None:
        """
        title: Initialize the CompareOp instance.
        parameters:
          left: Left operand.
          ops: Ops.
          comparators: Comparators.
          loc: Source coordinates associated with the node.
          operator_locations: Per-operator locations, when available.
        """
        super().__init__(loc=loc)
        self.ops = list(ops)
        self.comparators = list(comparators)
        self.operator_locations = (
            list(operator_locations)
            if operator_locations is not None
            else [loc] * len(self.ops)
        )
        if len(self.ops) != len(self.comparators):
            raise ValueError(
                "Number of operators must equal number of comparators."
            )
        if len(self.ops) != len(self.operator_locations):
            raise ValueError("Each comparison operator needs a location.")
        for op in self.ops:
            if op not in ["==", "!=", "<", ">", "<=", ">="]:
                raise ValueError(f"Invalid comparison operator: {op}")
        self.left = left
        self.kind = ASTKind.CompareOpKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        ops_str = ", ".join(self.ops)
        return f"Compare[{ops_str}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure that represents the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        ops_str = ", ".join(self.ops)
        key = f"COMPARE[{ops_str}]"
        content: ReprStruct = {
            "left": self.left.get_struct(simplified),
            "comparators": [
                comp.get_struct(simplified) for comp in self.comparators
            ],
        }
        return self._prepare_struct(key, content, simplified)


@public
@typechecked
class Starred(Expr):
    """
    title: AST class for starred expressions (*expr).
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
        title: Initialize the starred expression.
        parameters:
          value: Value to process.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.value = value
        self.kind = ASTKind.StarredKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        return f"Starred[*]({self.value})"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure that represents the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = "STARRED[*]"
        content: ReprStruct = {"value": self.value.get_struct(simplified)}
        return self._prepare_struct(key, content, simplified)
