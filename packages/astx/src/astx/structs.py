"""
title: ASTx struct AST nodes.
"""

from __future__ import annotations

import astx

from astx.tools.typing import typechecked
from astx.types import AnyType


@typechecked
class StructType(AnyType):
    """
    title: Named struct type reference.
    attributes:
      name: Name identifying this declaration.
      resolved_name: Name of resolved.
      module_key: Canonical module identity.
      qualified_name: Name of qualified.
    """

    name: str
    resolved_name: str | None
    module_key: str | None
    qualified_name: str | None

    def __init__(
        self,
        name: str,
        *,
        resolved_name: str | None = None,
        module_key: str | None = None,
        qualified_name: str | None = None,
    ) -> None:
        """
        title: Initialize one named struct type reference.
        parameters:
          name: Name identifying the declaration or operation.
          resolved_name: Name of resolved.
          module_key: Canonical module identity.
          qualified_name: Name of qualified.
        """
        super().__init__()
        self.name = name
        self.resolved_name = resolved_name
        self.module_key = module_key
        self.qualified_name = qualified_name

    def __str__(self) -> str:
        """
        title: Render one struct type reference as text.
        returns: String representation of this instance.
        """
        return f"StructType[{self.name}]"

    def get_struct(self, simplified: bool = False) -> astx.base.ReprStruct:
        """
        title: Build one repr structure for a struct type reference.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"STRUCT-TYPE[{self.name}]"
        value = self.qualified_name or self.name
        return self._prepare_struct(key, value, simplified)


@typechecked
class FieldAccess(astx.DataType):
    """
    title: Field access expression.
    attributes:
      value: Stored value.
      field_name: Name of field.
      type_: Type associated with this expression.
    """

    value: astx.AST
    field_name: str
    type_: AnyType

    def __init__(self, value: astx.AST, field_name: str) -> None:
        """
        title: Initialize one field access expression.
        parameters:
          value: Value to process.
          field_name: Name of field.
        """
        super().__init__()
        self.value = value
        self.field_name = field_name
        self.type_ = AnyType()

    def __str__(self) -> str:
        """
        title: Render one field access expression as text.
        returns: String representation of this instance.
        """
        return f"FieldAccess[{self.field_name}]"

    def get_struct(self, simplified: bool = False) -> astx.base.ReprStruct:
        """
        title: Build one repr structure for a field access expression.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"FIELD-ACCESS[{self.field_name}]"
        value = self.value.get_struct(simplified)
        return self._prepare_struct(key, value, simplified)


__all__ = ["FieldAccess", "StructType"]
