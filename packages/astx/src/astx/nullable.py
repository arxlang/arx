"""
title: Reusable nullable value types and explicit validity expressions.
"""

from __future__ import annotations

from enum import Enum

from public import public

from astx.base import DataType, Expr, ReprStruct, SourceLocation
from astx.tools.typing import typechecked
from astx.types import AnyType, Boolean


@public
@typechecked
class NullableType(AnyType):
    """
    title: A value with validity independent of its payload type.
    attributes:
      payload_type:
        type: DataType
      alias_name:
        type: str | None
    """

    payload_type: DataType
    alias_name: str | None

    def __init__(
        self, payload_type: DataType, *, alias_name: str | None = None
    ) -> None:
        """
        title: Model nullability without selecting a runtime representation.
        parameters:
          payload_type:
            type: DataType
          alias_name:
            type: str | None
        """
        super().__init__()
        self.payload_type = payload_type
        self.alias_name = alias_name

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Preserve the nullable payload in structural representations.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            "NullableType",
            self.payload_type.get_struct(simplified),
            simplified,
        )


@public
@typechecked
class NullableOperation(Enum):
    """
    title: Closed validity operations, independent of native symbols.
    """

    IS_NULL = "is_null"
    IS_VALID = "is_valid"
    EXPECT_VALID = "expect_valid"


@public
@typechecked
class NullableQuery(DataType):
    """
    title: Inspect validity or explicitly request a checked payload.
    attributes:
      operation:
        type: NullableOperation
      operand:
        type: Expr
      type_:
        type: DataType
      loc:
        type: SourceLocation
    """

    operation: NullableOperation
    operand: Expr
    type_: DataType
    loc: SourceLocation

    def __init__(
        self,
        operation: NullableOperation,
        operand: Expr,
        loc: SourceLocation | None = None,
    ) -> None:
        """
        title: Model one query without performing semantic type resolution.
        parameters:
          operation:
            type: NullableOperation
          operand:
            type: Expr
          loc:
            type: SourceLocation | None
        """
        super().__init__()
        if loc is not None:
            self.loc = loc
        self.operation = operation
        self.operand = operand
        # ASTx binary nodes require a DataType before semantic analysis. The
        # unwrap payload is deliberately unknown until IRx resolves it.
        self.type_ = (
            AnyType()
            if operation is NullableOperation.EXPECT_VALID
            else Boolean()
        )

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Preserve the typed operation and its operand.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            f"NullableQuery[{self.operation.value}]",
            self.operand.get_struct(simplified),
            simplified,
        )
