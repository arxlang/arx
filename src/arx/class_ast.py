"""
title: Arx surface AST nodes for annotation-based class declarations.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterator, TypeAlias, cast

import astx

from astx.base import NO_SOURCE_LOCATION, ReprStruct, SourceLocation
from astx.types import AnyType


class ModifierKind(Enum):
    """
    title: Structured modifier kinds supported by Arx class syntax.
    """

    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    STATIC = "static"
    CONSTANT = "constant"
    MUTABLE = "mutable"
    OVERRIDE = "override"
    ABSTRACT = "abstract"
    VIRTUAL = "virtual"
    FINAL = "final"
    INLINE = "inline"
    EXTERN = "extern"
    SEALED = "sealed"
    READONLY = "readonly"

    @property
    def surface_name(self) -> str:
        """
        title: Return the surface-language spelling for the modifier.
        returns:
          type: str
        """
        return self.value


MODIFIER_NAME_MAP: dict[str, ModifierKind] = {
    kind.surface_name: kind for kind in ModifierKind
}

VISIBILITY_MODIFIERS = frozenset(
    {
        ModifierKind.PUBLIC,
        ModifierKind.PRIVATE,
        ModifierKind.PROTECTED,
    }
)

FIELD_MUTABILITY_MODIFIERS = frozenset(
    {
        ModifierKind.CONSTANT,
        ModifierKind.MUTABLE,
        ModifierKind.READONLY,
    }
)

FIELD_ALLOWED_MODIFIERS = frozenset(
    {
        ModifierKind.PUBLIC,
        ModifierKind.PRIVATE,
        ModifierKind.PROTECTED,
        ModifierKind.STATIC,
        ModifierKind.CONSTANT,
        ModifierKind.MUTABLE,
        ModifierKind.READONLY,
    }
)

METHOD_ALLOWED_MODIFIERS = frozenset(
    {
        ModifierKind.PUBLIC,
        ModifierKind.PRIVATE,
        ModifierKind.PROTECTED,
        ModifierKind.STATIC,
        ModifierKind.OVERRIDE,
        ModifierKind.ABSTRACT,
        ModifierKind.VIRTUAL,
        ModifierKind.FINAL,
        ModifierKind.INLINE,
        ModifierKind.EXTERN,
    }
)

CLASS_ALLOWED_MODIFIERS = frozenset(
    {
        ModifierKind.PUBLIC,
        ModifierKind.PRIVATE,
        ModifierKind.PROTECTED,
        ModifierKind.ABSTRACT,
        ModifierKind.FINAL,
        ModifierKind.SEALED,
    }
)


def modifier_to_visibility_kind(kind: ModifierKind) -> astx.VisibilityKind:
    """
    title: Map one Arx visibility modifier to ASTx visibility.
    parameters:
      kind:
        type: ModifierKind
    returns:
      type: astx.VisibilityKind
    """
    mapping = {
        ModifierKind.PUBLIC: astx.VisibilityKind.public,
        ModifierKind.PRIVATE: astx.VisibilityKind.private,
        ModifierKind.PROTECTED: astx.VisibilityKind.protected,
    }
    return mapping[kind]


def modifier_to_mutability_kind(kind: ModifierKind) -> astx.MutabilityKind:
    """
    title: Map one Arx mutability modifier to ASTx mutability.
    parameters:
      kind:
        type: ModifierKind
    returns:
      type: astx.MutabilityKind
    """
    mapping = {
        ModifierKind.CONSTANT: astx.MutabilityKind.constant,
        ModifierKind.MUTABLE: astx.MutabilityKind.mutable,
        ModifierKind.READONLY: astx.MutabilityKind.constant,
    }
    return mapping[kind]


class ModifierList(astx.AST):
    """
    title: Explicit annotation-line modifier list.
    attributes:
      kinds:
        type: tuple[ModifierKind, Ellipsis]
    """

    kinds: tuple[ModifierKind, ...]

    def __init__(
        self,
        kinds: list[ModifierKind] | tuple[ModifierKind, ...],
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize one modifier list.
        parameters:
          kinds:
            type: list[ModifierKind] | tuple[ModifierKind, Ellipsis]
          loc:
            type: SourceLocation
        """
        super().__init__(loc=loc)
        self.kinds = tuple(kinds)

    def __iter__(self) -> Iterator[ModifierKind]:
        """
        title: Iterate over explicit modifier kinds.
        returns:
          type: Iterator[ModifierKind]
        """
        return iter(self.kinds)

    def __contains__(self, modifier: object) -> bool:
        """
        title: Return whether a modifier is present.
        parameters:
          modifier:
            type: object
        returns:
          type: bool
        """
        return modifier in self.kinds

    def names(self) -> tuple[str, ...]:
        """
        title: Return explicit surface modifier names.
        returns:
          type: tuple[str, Ellipsis]
        """
        return tuple(kind.surface_name for kind in self.kinds)

    def resolved_visibility(
        self,
        default: ModifierKind = ModifierKind.PUBLIC,
    ) -> ModifierKind:
        """
        title: Resolve explicit visibility or return the default.
        parameters:
          default:
            type: ModifierKind
        returns:
          type: ModifierKind
        """
        for kind in self.kinds:
            if kind in VISIBILITY_MODIFIERS:
                return kind
        return default

    def resolved_mutability(
        self,
        default: ModifierKind = ModifierKind.MUTABLE,
    ) -> ModifierKind:
        """
        title: Resolve explicit field mutability or return the default.
        parameters:
          default:
            type: ModifierKind
        returns:
          type: ModifierKind
        """
        for kind in self.kinds:
            if kind in FIELD_MUTABILITY_MODIFIERS:
                return kind
        return default

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return a structure representation for one modifier list.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            "MODIFIERS",
            cast(ReprStruct, list(self.names())),
            simplified,
        )


class MethodParam(astx.AST):
    """
    title: One Arx method parameter.
    attributes:
      name:
        type: str
      type_:
        type: astx.DataType | None
      is_self:
        type: bool
    """

    name: str
    type_: astx.DataType | None
    is_self: bool

    def __init__(
        self,
        name: str,
        type_: astx.DataType | None,
        *,
        is_self: bool = False,
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize one method parameter.
        parameters:
          name:
            type: str
          type_:
            type: astx.DataType | None
          is_self:
            type: bool
          loc:
            type: SourceLocation
        """
        super().__init__(loc=loc)
        self.name = name
        self.type_ = type_
        self.is_self = is_self

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return a structure representation for one method parameter.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        value = {
            "name": self.name,
            "type": None if self.type_ is None else str(self.type_),
            "is_self": self.is_self,
        }
        return self._prepare_struct(
            "METHOD-PARAM",
            cast(ReprStruct, value),
            simplified,
        )


class FieldDecl(astx.StatementType):
    """
    title: One annotation-based class field declaration.
    attributes:
      name:
        type: str
      type_:
        type: astx.DataType
      initializer:
        type: astx.AST | None
      modifiers:
        type: ModifierList | None
    """

    name: str
    type_: astx.DataType
    initializer: astx.AST | None
    modifiers: ModifierList | None

    def __init__(
        self,
        name: str,
        type_: astx.DataType,
        initializer: astx.AST | None = None,
        modifiers: ModifierList | None = None,
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize one field declaration.
        parameters:
          name:
            type: str
          type_:
            type: astx.DataType
          initializer:
            type: astx.AST | None
          modifiers:
            type: ModifierList | None
          loc:
            type: SourceLocation
        """
        super().__init__(loc=loc)
        self.name = name
        self.type_ = type_
        self.initializer = initializer
        self.modifiers = modifiers

    def resolved_visibility(self) -> ModifierKind:
        """
        title: Resolve field visibility with Arx defaults.
        returns:
          type: ModifierKind
        """
        if self.modifiers is None:
            return ModifierKind.PUBLIC
        return self.modifiers.resolved_visibility()

    def resolved_mutability(self) -> ModifierKind:
        """
        title: Resolve field mutability with Arx defaults.
        returns:
          type: ModifierKind
        """
        if self.modifiers is None:
            return ModifierKind.MUTABLE
        return self.modifiers.resolved_mutability()

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return a structure representation for one field declaration.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        value = {
            "name": self.name,
            "type": str(self.type_),
            "initializer": (
                None
                if self.initializer is None
                else self.initializer.get_struct(simplified)
            ),
            "modifiers": (
                None
                if self.modifiers is None
                else self.modifiers.get_struct(simplified)
            ),
        }
        return self._prepare_struct(
            "FIELD-DECL",
            cast(ReprStruct, value),
            simplified,
        )


class MethodDecl(astx.StatementType):
    """
    title: One annotation-based class method declaration.
    attributes:
      name:
        type: str
      params:
        type: tuple[MethodParam, Ellipsis]
      return_type:
        type: astx.DataType
      body:
        type: astx.Block | None
      modifiers:
        type: ModifierList | None
    """

    name: str
    params: tuple[MethodParam, ...]
    return_type: astx.DataType
    body: astx.Block | None
    modifiers: ModifierList | None

    def __init__(
        self,
        name: str,
        params: list[MethodParam] | tuple[MethodParam, ...],
        return_type: astx.DataType,
        body: astx.Block | None,
        modifiers: ModifierList | None = None,
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize one method declaration.
        parameters:
          name:
            type: str
          params:
            type: list[MethodParam] | tuple[MethodParam, Ellipsis]
          return_type:
            type: astx.DataType
          body:
            type: astx.Block | None
          modifiers:
            type: ModifierList | None
          loc:
            type: SourceLocation
        """
        super().__init__(loc=loc)
        self.name = name
        self.params = tuple(params)
        self.return_type = return_type
        self.body = body
        self.modifiers = modifiers

    def resolved_visibility(self) -> ModifierKind:
        """
        title: Resolve method visibility with Arx defaults.
        returns:
          type: ModifierKind
        """
        if self.modifiers is None:
            return ModifierKind.PUBLIC
        return self.modifiers.resolved_visibility()

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return a structure representation for one method declaration.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        value = {
            "name": self.name,
            "params": [param.get_struct(simplified) for param in self.params],
            "return_type": str(self.return_type),
            "body": (
                None if self.body is None else self.body.get_struct(simplified)
            ),
            "modifiers": (
                None
                if self.modifiers is None
                else self.modifiers.get_struct(simplified)
            ),
        }
        return self._prepare_struct(
            "METHOD-DECL",
            cast(ReprStruct, value),
            simplified,
        )


ClassMember: TypeAlias = FieldDecl | MethodDecl


class ClassDecl(astx.StatementType):
    """
    title: One annotation-based class declaration.
    attributes:
      name:
        type: str
      bases:
        type: tuple[str, Ellipsis]
      body:
        type: tuple[ClassMember, Ellipsis]
      annotations:
        type: ModifierList | None
    """

    name: str
    bases: tuple[str, ...]
    body: tuple[ClassMember, ...]
    annotations: ModifierList | None

    def __init__(
        self,
        name: str,
        bases: list[str] | tuple[str, ...],
        body: list[ClassMember] | tuple[ClassMember, ...],
        annotations: ModifierList | None = None,
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize one class declaration.
        parameters:
          name:
            type: str
          bases:
            type: list[str] | tuple[str, Ellipsis]
          body:
            type: list[ClassMember] | tuple[ClassMember, Ellipsis]
          annotations:
            type: ModifierList | None
          loc:
            type: SourceLocation
        """
        super().__init__(loc=loc)
        self.name = name
        self.bases = tuple(bases)
        self.body = tuple(body)
        self.annotations = annotations

    def resolved_visibility(self) -> ModifierKind:
        """
        title: Resolve class visibility with Arx defaults.
        returns:
          type: ModifierKind
        """
        if self.annotations is None:
            return ModifierKind.PUBLIC
        return self.annotations.resolved_visibility()

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return a structure representation for one class declaration.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        value = {
            "name": self.name,
            "bases": list(self.bases),
            "body": [member.get_struct(simplified) for member in self.body],
            "annotations": (
                None
                if self.annotations is None
                else self.annotations.get_struct(simplified)
            ),
        }
        return self._prepare_struct(
            "CLASS-DECL",
            cast(ReprStruct, value),
            simplified,
        )


class MemberAccessExpr(astx.DataType):
    """
    title: Dotted member access expression.
    attributes:
      receiver:
        type: astx.AST
      member_name:
        type: str
      type_:
        type: AnyType
    """

    receiver: astx.AST
    member_name: str
    type_: AnyType

    def __init__(
        self,
        receiver: astx.AST,
        member_name: str,
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize one member access expression.
        parameters:
          receiver:
            type: astx.AST
          member_name:
            type: str
          loc:
            type: SourceLocation
        """
        super().__init__(loc=loc)
        self.receiver = receiver
        self.member_name = member_name
        self.type_ = AnyType()

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return a structure representation for one member access.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        value = {
            "receiver": self.receiver.get_struct(simplified),
            "member_name": self.member_name,
        }
        return self._prepare_struct(
            "MEMBER-ACCESS",
            cast(ReprStruct, value),
            simplified,
        )


class MethodCallExpr(astx.DataType):
    """
    title: Dotted method call expression.
    attributes:
      receiver:
        type: astx.AST
      method_name:
        type: str
      args:
        type: tuple[astx.AST, Ellipsis]
      type_:
        type: AnyType
    """

    receiver: astx.AST
    method_name: str
    args: tuple[astx.AST, ...]
    type_: AnyType

    def __init__(
        self,
        receiver: astx.AST,
        method_name: str,
        args: list[astx.AST] | tuple[astx.AST, ...],
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize one method call expression.
        parameters:
          receiver:
            type: astx.AST
          method_name:
            type: str
          args:
            type: list[astx.AST] | tuple[astx.AST, Ellipsis]
          loc:
            type: SourceLocation
        """
        super().__init__(loc=loc)
        self.receiver = receiver
        self.method_name = method_name
        self.args = tuple(args)
        self.type_ = AnyType()

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return a structure representation for one method call.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        value = {
            "receiver": self.receiver.get_struct(simplified),
            "method_name": self.method_name,
            "args": [arg.get_struct(simplified) for arg in self.args],
        }
        return self._prepare_struct(
            "METHOD-CALL",
            cast(ReprStruct, value),
            simplified,
        )


__all__ = [
    "CLASS_ALLOWED_MODIFIERS",
    "FIELD_ALLOWED_MODIFIERS",
    "FIELD_MUTABILITY_MODIFIERS",
    "METHOD_ALLOWED_MODIFIERS",
    "MODIFIER_NAME_MAP",
    "VISIBILITY_MODIFIERS",
    "ClassDecl",
    "ClassMember",
    "FieldDecl",
    "MemberAccessExpr",
    "MethodCallExpr",
    "MethodDecl",
    "MethodParam",
    "ModifierKind",
    "ModifierList",
    "modifier_to_mutability_kind",
    "modifier_to_visibility_kind",
]
