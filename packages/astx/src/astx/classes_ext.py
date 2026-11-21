"""
title: ASTx class AST nodes.
summary: Provide explicit class-type references and class-definition nodes
  that host compilers can use before higher-level surface syntax exists in
  Arx.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

import astx

from astx.base import NO_SOURCE_LOCATION
from astx.classes import StructDeclStmt
from astx.modifiers import VisibilityKind
from astx.tools.typing import typechecked
from astx.types import AnyType


@typechecked
class ClassType(AnyType):
    """
    title: Named class type reference.
    attributes:
      name: Name identifying this declaration.
      resolved_name: Name of resolved.
      module_key: Canonical module identity.
      qualified_name: Name of qualified.
      ancestor_qualified_names: Ancestor qualified names.
    """

    name: str
    resolved_name: str | None
    module_key: str | None
    qualified_name: str | None
    ancestor_qualified_names: tuple[str, ...]

    def __init__(
        self,
        name: str,
        *,
        resolved_name: str | None = None,
        module_key: str | None = None,
        qualified_name: str | None = None,
        ancestor_qualified_names: tuple[str, ...] = (),
    ) -> None:
        """
        title: Initialize one named class type reference.
        parameters:
          name: Name identifying the declaration or operation.
          resolved_name: Name of resolved.
          module_key: Canonical module identity.
          qualified_name: Name of qualified.
          ancestor_qualified_names: Ancestor qualified names.
        """
        super().__init__()
        self.name = name
        self.resolved_name = resolved_name
        self.module_key = module_key
        self.qualified_name = qualified_name
        self.ancestor_qualified_names = ancestor_qualified_names

    def __str__(self) -> str:
        """
        title: Render one class type reference as text.
        returns: String representation of this instance.
        """
        return f"ClassType[{self.name}]"

    def get_struct(self, simplified: bool = False) -> astx.base.ReprStruct:
        """
        title: Build one repr structure for a class type reference.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"CLASS-TYPE[{self.name}]"
        value = self.qualified_name or self.name
        return self._prepare_struct(key, value, simplified)


@typechecked
class ClassDefStmt(StructDeclStmt):
    """
    title: Explicit class definition statement.
    summary: Represent one top-level class declaration with explicit base-class
      references and inherited struct-like member containers.
    attributes:
      bases: Bases.
      is_abstract: Whether is abstract.
      kind: Kind of value or operation.
    """

    bases: astx.ASTNodes[ClassType]
    is_abstract: bool
    kind: astx.ASTKind

    def __init__(
        self,
        name: str,
        *,
        bases: Iterable[ClassType] | astx.ASTNodes[ClassType] = (),
        attributes: (
            Iterable[astx.VariableDeclaration]
            | astx.ASTNodes[astx.VariableDeclaration]
        ) = (),
        decorators: Iterable[astx.Expr] | astx.ASTNodes[astx.Expr] = (),
        methods: Iterable[astx.FunctionDef]
        | astx.ASTNodes[astx.FunctionDef] = (),
        visibility: VisibilityKind = VisibilityKind.public,
        is_abstract: bool = False,
        loc: astx.SourceLocation = NO_SOURCE_LOCATION,
        parent: astx.ASTNodes[astx.AST] | None = None,
    ) -> None:
        """
        title: Initialize one class definition statement.
        parameters:
          name: Name identifying the declaration or operation.
          bases: Bases.
          attributes: Attributes.
          decorators: Decorators.
          methods: Methods.
          visibility: Visibility.
          is_abstract: Whether is abstract.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(
            name=name,
            attributes=attributes,
            decorators=decorators,
            methods=methods,
            visibility=visibility,
            loc=loc,
            parent=parent,
        )
        self.is_abstract = is_abstract
        if isinstance(bases, astx.ASTNodes):
            self.bases = bases
        else:
            self.bases = astx.ASTNodes[ClassType]()
            for base in bases:
                self.bases.append(base)
        self.kind = astx.ASTKind.StructDefStmtKind

    def __str__(self) -> str:
        """
        title: Render one class definition as text.
        returns: String representation of this instance.
        """
        decorators_str = "".join(
            f"@{decorator}\n" for decorator in self.decorators
        )
        modifiers: list[str] = []
        if self.visibility != VisibilityKind.public:
            modifiers.append(self.visibility.name.lower())
        if self.is_abstract:
            modifiers.append("abstract")
        bases_str = ""
        if self.bases:
            bases_str = "(" + ", ".join(base.name for base in self.bases) + ")"
        modifier_prefix = " ".join(modifiers)
        if modifier_prefix:
            modifier_prefix = f"{modifier_prefix} "
        class_header = f"{modifier_prefix}class {self.name}{bases_str}"
        member_lines = [str(attribute) for attribute in self.attributes] + [
            str(method) for method in self.methods
        ]
        members_str = "\n    ".join(member_lines)
        return f"{decorators_str}{class_header} {{\n    {members_str}\n}}"

    def get_struct(self, simplified: bool = False) -> astx.base.ReprStruct:
        """
        title: Build one repr structure for a class definition.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        vis = dict(zip(("public", "private", "protected"), ("+", "-", "#")))
        key = f"CLASS-DEF[{vis[self.visibility.name]}{self.name}]"

        bases_dict: astx.base.ReprStruct = {}
        if self.bases:
            bases_dict = {"bases": self.bases.get_struct(simplified)}

        decorators_dict: astx.base.ReprStruct = {}
        if self.decorators:
            decorators_dict = {
                "decorators": self.decorators.get_struct(simplified)
            }

        abstract_dict: astx.base.ReprStruct = {}
        if self.is_abstract:
            abstract_dict = {"abstract": self.is_abstract}

        attrs_dict: astx.base.ReprStruct = {}
        if self.attributes:
            attrs_dict = {"attributes": self.attributes.get_struct(simplified)}

        methods_dict: astx.base.ReprStruct = {}
        if self.methods:
            methods_dict = {"methods": self.methods.get_struct(simplified)}

        value = {
            **cast(dict[str, astx.base.ReprStruct], bases_dict),
            **cast(dict[str, astx.base.ReprStruct], decorators_dict),
            **cast(dict[str, astx.base.ReprStruct], abstract_dict),
            **cast(dict[str, astx.base.ReprStruct], attrs_dict),
            **cast(dict[str, astx.base.ReprStruct], methods_dict),
        }
        return self._prepare_struct(
            key,
            cast(astx.base.ReprStruct, value),
            simplified,
        )


@typechecked
class ClassConstruct(astx.DataType):
    """
    title: Class construction with ordered positional and keyword expressions.
    attributes:
      class_name: Name of class.
      type_: Type associated with this expression.
      args: Declared or supplied call arguments.
      keywords: Keywords.
    """

    class_name: str
    type_: AnyType
    args: tuple[astx.DataType, ...]
    keywords: tuple[astx.KeywordArgument, ...]

    def __init__(
        self,
        class_name: str,
        args: tuple[astx.DataType, ...] = (),
        *,
        keywords: tuple[astx.KeywordArgument, ...] = (),
        loc: astx.SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize one default class construction expression.
        parameters:
          class_name: Name of class.
          args: Arguments supplied to the operation.
          keywords: Keywords.
          loc: Source coordinates associated with the node.
        """
        super().__init__(loc=loc)
        self.class_name = class_name
        self.args = args
        self.keywords = keywords
        self.type_ = AnyType()

    def __str__(self) -> str:
        """
        title: Render one class construction expression as text.
        returns: String representation of this instance.
        """
        if not self.args and not self.keywords:
            return f"ClassConstruct[{self.class_name}]"
        values = [str(value) for value in self.args]
        values.extend(f"{item.name}={item.value}" for item in self.keywords)
        return f"ClassConstruct[{self.class_name}: {', '.join(values)}]"

    def get_struct(self, simplified: bool = False) -> astx.base.ReprStruct:
        """
        title: Build one repr structure for class construction.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"CLASS-CONSTRUCT[{self.class_name}]"
        if not self.args and not self.keywords:
            return self._prepare_struct(key, self.class_name, simplified)
        return self._prepare_struct(
            key,
            {
                "args": [value.get_struct(simplified) for value in self.args],
                "keywords": [
                    item.get_struct(simplified) for item in self.keywords
                ],
            },
            simplified,
        )


@typechecked
class MethodCall(astx.DataType):
    """
    title: Instance method call expression.
    attributes:
      receiver: Receiver.
      method_name: Name of method.
      args: Declared or supplied call arguments.
      keywords: Keywords.
      type_: Type associated with this expression.
    """

    receiver: astx.AST
    method_name: str
    args: tuple[astx.DataType, ...]
    keywords: tuple[astx.KeywordArgument, ...]
    type_: AnyType

    def __init__(
        self,
        receiver: astx.AST,
        method_name: str,
        args: Iterable[astx.DataType],
        *,
        keywords: tuple[astx.KeywordArgument, ...] = (),
    ) -> None:
        """
        title: Initialize one instance method call expression.
        parameters:
          receiver: Receiver.
          method_name: Name of method.
          args: Arguments supplied to the operation.
          keywords: Keywords.
        """
        super().__init__()
        self.receiver = receiver
        self.method_name = method_name
        self.args = tuple(args)
        self.keywords = keywords
        self.type_ = AnyType()

    def __str__(self) -> str:
        """
        title: Render one instance method call expression as text.
        returns: String representation of this instance.
        """
        return f"MethodCall[{self.method_name}]"

    def get_struct(self, simplified: bool = False) -> astx.base.ReprStruct:
        """
        title: Build one repr structure for an instance method call.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"METHOD-CALL[{self.method_name}]"
        arg_nodes = astx.ASTNodes[astx.DataType]("args")
        for arg in self.args:
            arg_nodes.append(arg)
        value = {
            "receiver": self.receiver.get_struct(simplified),
            "args": arg_nodes.get_struct(simplified),
        }
        if self.keywords:
            keyword_nodes = astx.ASTNodes[astx.KeywordArgument]("keywords")
            for keyword in self.keywords:
                keyword_nodes.append(keyword)
            value["keywords"] = keyword_nodes.get_struct(simplified)
        return self._prepare_struct(
            key,
            cast(astx.base.ReprStruct, value),
            simplified,
        )


@typechecked
class StaticMethodCall(astx.DataType):
    """
    title: Class-scoped static method call expression.
    attributes:
      class_name: Name of class.
      method_name: Name of method.
      args: Declared or supplied call arguments.
      keywords: Keywords.
      type_: Type associated with this expression.
    """

    class_name: str
    method_name: str
    args: tuple[astx.DataType, ...]
    keywords: tuple[astx.KeywordArgument, ...]
    type_: AnyType

    def __init__(
        self,
        class_name: str,
        method_name: str,
        args: Iterable[astx.DataType],
        *,
        keywords: tuple[astx.KeywordArgument, ...] = (),
    ) -> None:
        """
        title: Initialize one static method call expression.
        parameters:
          class_name: Name of class.
          method_name: Name of method.
          args: Arguments supplied to the operation.
          keywords: Keywords.
        """
        super().__init__()
        self.class_name = class_name
        self.method_name = method_name
        self.keywords = keywords
        self.args = tuple(args)
        self.type_ = AnyType()

    def __str__(self) -> str:
        """
        title: Render one static method call expression as text.
        returns: String representation of this instance.
        """
        return f"StaticMethodCall[{self.class_name}.{self.method_name}]"

    def get_struct(self, simplified: bool = False) -> astx.base.ReprStruct:
        """
        title: Build one repr structure for a static method call.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"STATIC-METHOD-CALL[{self.class_name}.{self.method_name}]"
        arg_nodes = astx.ASTNodes[astx.DataType]("args")
        for arg in self.args:
            arg_nodes.append(arg)
        value = {
            "args": arg_nodes.get_struct(simplified),
        }
        if self.keywords:
            named = astx.ASTNodes[astx.KeywordArgument]("keywords")
            for keyword in self.keywords:
                named.append(keyword)
            value["keywords"] = named.get_struct(simplified)
        return self._prepare_struct(
            key,
            cast(astx.base.ReprStruct, value),
            simplified,
        )


@typechecked
class StaticFieldAccess(astx.DataType):
    """
    title: Class-scoped static field access expression.
    attributes:
      class_name: Name of class.
      field_name: Name of field.
      type_: Type associated with this expression.
    """

    class_name: str
    field_name: str
    type_: AnyType

    def __init__(
        self,
        class_name: str,
        field_name: str,
    ) -> None:
        """
        title: Initialize one static field access expression.
        parameters:
          class_name: Name of class.
          field_name: Name of field.
        """
        super().__init__()
        self.class_name = class_name
        self.field_name = field_name
        self.type_ = AnyType()

    def __str__(self) -> str:
        """
        title: Render one static field access expression as text.
        returns: String representation of this instance.
        """
        return f"StaticFieldAccess[{self.class_name}.{self.field_name}]"

    def get_struct(self, simplified: bool = False) -> astx.base.ReprStruct:
        """
        title: Build one repr structure for a static field access.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"STATIC-FIELD-ACCESS[{self.class_name}.{self.field_name}]"
        return self._prepare_struct(
            key,
            f"{self.class_name}.{self.field_name}",
            simplified,
        )


@typechecked
class BaseFieldAccess(astx.DataType):
    """
    title: Explicit base-qualified instance field access expression.
    attributes:
      receiver: Receiver.
      base_class_name: Name of base class.
      field_name: Name of field.
      type_: Type associated with this expression.
    """

    receiver: astx.AST
    base_class_name: str
    field_name: str
    type_: AnyType

    def __init__(
        self,
        receiver: astx.AST,
        base_class_name: str,
        field_name: str,
    ) -> None:
        """
        title: Initialize one base-qualified field access expression.
        parameters:
          receiver: Receiver.
          base_class_name: Name of base class.
          field_name: Name of field.
        """
        super().__init__()
        self.receiver = receiver
        self.base_class_name = base_class_name
        self.field_name = field_name
        self.type_ = AnyType()

    def __str__(self) -> str:
        """
        title: Render one base-qualified field access expression as text.
        returns: String representation of this instance.
        """
        return f"BaseFieldAccess[{self.base_class_name}.{self.field_name}]"

    def get_struct(self, simplified: bool = False) -> astx.base.ReprStruct:
        """
        title: Build one repr structure for a base-qualified field access.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"BASE-FIELD-ACCESS[{self.base_class_name}.{self.field_name}]"
        value = {
            "receiver": self.receiver.get_struct(simplified),
        }
        return self._prepare_struct(
            key,
            cast(astx.base.ReprStruct, value),
            simplified,
        )


@typechecked
class BaseMethodCall(astx.DataType):
    """
    title: Explicit base-qualified instance method call expression.
    attributes:
      receiver: Receiver.
      base_class_name: Name of base class.
      method_name: Name of method.
      args: Declared or supplied call arguments.
      keywords: Keywords.
      type_: Type associated with this expression.
    """

    receiver: astx.AST
    base_class_name: str
    method_name: str
    args: tuple[astx.DataType, ...]
    keywords: tuple[astx.KeywordArgument, ...]
    type_: AnyType

    def __init__(
        self,
        receiver: astx.AST,
        base_class_name: str,
        method_name: str,
        args: Iterable[astx.DataType],
        *,
        keywords: tuple[astx.KeywordArgument, ...] = (),
    ) -> None:
        """
        title: Initialize one base-qualified method call expression.
        parameters:
          receiver: Receiver.
          base_class_name: Name of base class.
          method_name: Name of method.
          args: Arguments supplied to the operation.
          keywords: Keywords.
        """
        super().__init__()
        self.receiver = receiver
        self.base_class_name = base_class_name
        self.method_name = method_name
        self.keywords = keywords
        self.args = tuple(args)
        self.type_ = AnyType()

    def __str__(self) -> str:
        """
        title: Render one base-qualified method call expression as text.
        returns: String representation of this instance.
        """
        return f"BaseMethodCall[{self.base_class_name}.{self.method_name}]"

    def get_struct(self, simplified: bool = False) -> astx.base.ReprStruct:
        """
        title: Build one repr structure for a base-qualified method call.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"BASE-METHOD-CALL[{self.base_class_name}.{self.method_name}]"
        arg_nodes = astx.ASTNodes[astx.DataType]("args")
        for arg in self.args:
            arg_nodes.append(arg)
        value = {
            "receiver": self.receiver.get_struct(simplified),
            "args": arg_nodes.get_struct(simplified),
        }
        if self.keywords:
            named = astx.ASTNodes[astx.KeywordArgument]("keywords")
            for keyword in self.keywords:
                named.append(keyword)
            value["keywords"] = named.get_struct(simplified)
        return self._prepare_struct(
            key,
            cast(astx.base.ReprStruct, value),
            simplified,
        )


__all__ = [
    "BaseFieldAccess",
    "BaseMethodCall",
    "ClassConstruct",
    "ClassDefStmt",
    "ClassType",
    "MethodCall",
    "StaticFieldAccess",
    "StaticMethodCall",
]
