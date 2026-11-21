"""
title: Module for subscripts definitions/declarations.
"""

from typing import Optional, cast

from public import public

from astx.base import (
    NO_SOURCE_LOCATION,
    ASTKind,
    ASTNodes,
    DataType,
    DictDataTypesStruct,
    Expr,
    ReprStruct,
    SourceLocation,
)
from astx.literals import LiteralNone
from astx.tools.typing import typechecked
from astx.types.base import AnyType


@public
@typechecked
class SubscriptExpr(DataType):
    """
    title: AST class for subscript expressions.
    attributes:
      kind: Kind of value or operation.
      type_: Type associated with this expression.
      value: Stored value.
      index: Index selecting the item.
      lower: Lower bound.
      upper: Upper bound.
      step: Iteration stride.
      is_slice: Distinguish omitted slice bounds from an explicit none index.
    """

    kind: ASTKind
    type_: DataType

    value: Expr
    index: Expr
    lower: Expr
    upper: Expr
    step: Expr
    is_slice: bool

    def __init__(
        self,
        value: Expr,
        index: Optional[Expr] = None,
        lower: Optional[Expr] = None,
        upper: Optional[Expr] = None,
        step: Optional[Expr] = None,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the SubscriptExpr instance.
        summary: >2-

          Parameters

          ----------

          value: Expr

          The expression representing the object being indexed (e.g.,

          an array or list).

          index (optional): Expr

          The index of the variable.

          lower (optional): Expr

          The lower bound of the slice (inclusive).

          upper (optional): Expr

          The upper bound of the slice (exclusive).

          step (optional): Expr

          The step size for the slice.

          loc: SourceLocation

          The source location of the expression.

          parent (optional): ASTNodes

          The parent AST node.
        parameters:
          value: Value to process.
          index: Index selecting the item.
          lower: Lower bound.
          upper: Upper bound.
          step: Iteration stride.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.is_slice = index is None or any(
            bound is not None for bound in (lower, upper, step)
        )
        if (
            self.is_slice
            and index is not None
            and not isinstance(index, LiteralNone)
        ):
            raise ValueError(
                "subscripts cannot combine an index and slice bounds"
            )
        self.type_ = AnyType()
        self.value: Expr = value if value is not None else LiteralNone()
        self.index: Expr = index if index is not None else LiteralNone()
        self.lower: Expr = lower if lower is not None else LiteralNone()
        self.upper: Expr = upper if upper is not None else LiteralNone()
        self.step: Expr = step if step is not None else LiteralNone()
        self.kind = ASTKind.SubscriptExprKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        if not self.is_slice:
            return f"SubscriptExpr({self.value}[{self.index}])"
        lower_str = (
            str(self.lower) if not isinstance(self.lower, LiteralNone) else ""
        )

        upper_str = (
            ":" + str(self.upper)
            if not isinstance(self.upper, LiteralNone)
            else ":"
        )
        step_str = (
            ":" + str(self.step)
            if not isinstance(self.step, LiteralNone)
            else ""
        )
        return f"SubscriptExpr({self.value}[{lower_str}{upper_str}{step_str}])"

    def _get_struct_wrapper(self, simplified: bool) -> DictDataTypesStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: The AST structure of the object.
        """
        value_dict: ReprStruct = {"indexed": self.value.get_struct(simplified)}

        lower_key = "lower" if self.is_slice else "index"
        lower_value = (
            self.index.get_struct(simplified)
            if not self.is_slice
            else self.lower.get_struct(simplified)
        )
        lower_dict: ReprStruct = {lower_key: lower_value}

        upper_dict: ReprStruct = {}
        if not isinstance(self.upper, LiteralNone):
            upper_dict = {"upper": self.upper.get_struct(simplified)}

        step_dict: ReprStruct = {}
        if not isinstance(self.step, LiteralNone):
            step_dict = {"step": self.step.get_struct(simplified)}

        value: DictDataTypesStruct = {
            **cast(DictDataTypesStruct, value_dict),
            **cast(DictDataTypesStruct, lower_dict),
            **cast(DictDataTypesStruct, upper_dict),
            **cast(DictDataTypesStruct, step_dict),
        }
        return value

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = "SubscriptExpr"
        value = self._get_struct_wrapper(simplified)

        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class Ellipsis(Expr):
    """
    title: AST class for Ellipsis expressions.
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
        title: Initialize the ellipsis expression.
        parameters:
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.kind = ASTKind.EllipsisKind

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = str(self)
        value: DictDataTypesStruct = {}
        return self._prepare_struct(key, value, simplified)
