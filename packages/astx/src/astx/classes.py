"""
title: Module for classes definitions/declarations.
"""

from __future__ import annotations

import copy

from typing import Iterable, Optional, cast

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
from astx.callables import FunctionDef
from astx.data import VariableDeclaration
from astx.modifiers import VisibilityKind
from astx.tools.typing import typechecked


@public
@typechecked
class ClassDeclStmt(StatementType):
    """
    title: AST class for class declaration.
    attributes:
      kind: Kind of value or operation.
      name: Name identifying this declaration.
      bases: Bases.
      decorators: Decorators.
      visibility: Visibility.
      is_abstract: Whether is abstract.
      metaclass: Metaclass.
      attributes: Attributes.
      methods: Methods.
    """

    kind: ASTKind

    name: str
    bases: ASTNodes[Expr]
    decorators: ASTNodes[Expr]
    visibility: VisibilityKind
    is_abstract: bool
    metaclass: Optional[Expr]
    attributes: ASTNodes[VariableDeclaration]
    methods: ASTNodes[FunctionDef]

    def __init__(
        self,
        name: str,
        bases: Iterable[Expr] | ASTNodes[Expr] = [],
        decorators: Iterable[Expr] | ASTNodes[Expr] = [],
        visibility: VisibilityKind = VisibilityKind.public,
        is_abstract: bool = False,
        metaclass: Optional[Expr] = None,
        attributes: Iterable[VariableDeclaration]
        | ASTNodes[VariableDeclaration] = [],
        methods: Iterable[FunctionDef] | ASTNodes[FunctionDef] = [],
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize ClassDeclStmt instance.
        parameters:
          name: Name identifying the declaration or operation.
          bases: Bases.
          decorators: Decorators.
          visibility: Visibility.
          is_abstract: Whether is abstract.
          metaclass: Metaclass.
          attributes: Attributes.
          methods: Methods.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.name = name

        if isinstance(bases, ASTNodes):
            self.bases = bases
        else:
            self.bases = ASTNodes()
            for base in bases:
                self.bases.append(base)

        if isinstance(decorators, ASTNodes):
            self.decorators = decorators
        else:
            self.decorators = ASTNodes[Expr]()
            for decorator in decorators:
                self.decorators.append(decorator)

        if isinstance(attributes, ASTNodes):
            self.attributes = attributes
        else:
            self.attributes = ASTNodes[VariableDeclaration]()
            for a in attributes:
                self.attributes.append(a)

        if isinstance(methods, ASTNodes):
            self.methods = methods
        else:
            self.methods = ASTNodes[FunctionDef]()
            for m in methods:
                self.methods.append(m)

        self.visibility = visibility
        self.is_abstract = is_abstract
        self.metaclass = metaclass
        self.kind = ASTKind.ClassDeclStmtKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        modifiers = []
        if self.visibility != VisibilityKind.public:
            modifiers.append(self.visibility.name)
        if self.is_abstract:
            modifiers.append("abstract")
        modifiers_str = " ".join(modifiers)
        bases_str = (
            ", ".join(str(base) for base in self.bases) if self.bases else ""
        )
        decorators_str = "".join(
            f"@{decorator}\n" for decorator in self.decorators
        )
        metaclass_str = (
            f" metaclass={self.metaclass}" if self.metaclass else ""
        )
        class_str = f"class {self.name}"
        if bases_str:
            class_str += f"({bases_str})"
        class_str += f"{metaclass_str}"
        return f"{decorators_str}{modifiers_str} {class_str}".strip()

    def _get_struct_wrapper(self, simplified: bool) -> DictDataTypesStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: The AST structure of the object.
        """
        bases_dict: ReprStruct = {}
        decors_dict: ReprStruct = {}
        metaclass_dict: ReprStruct = {}
        attrs_dict: ReprStruct = {}
        methods_dict: ReprStruct = {}

        if self.bases:
            bases_dict = {"bases": self.bases.get_struct(simplified)}

        if self.decorators:
            decors_dict = {
                "decorators": self.decorators.get_struct(simplified)
            }

        if self.metaclass:
            metaclass_dict = {
                "metaclass": self.metaclass.get_struct(simplified)
            }

        if self.attributes:
            attrs_dict = {"attributes": self.attributes.get_struct(simplified)}

        if self.methods:
            methods_dict = {"methods": self.methods.get_struct(simplified)}

        value: DictDataTypesStruct = {
            **cast(DictDataTypesStruct, bases_dict),
            **cast(DictDataTypesStruct, decors_dict),
            **cast(DictDataTypesStruct, metaclass_dict),
            **cast(DictDataTypesStruct, attrs_dict),
            **cast(DictDataTypesStruct, methods_dict),
        }
        return value

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        vis = dict(zip(("public", "private", "protected"), ("+", "-", "#")))
        abstract = ", abstract" if self.is_abstract else ""

        key = f"CLASS-DECL[{vis[self.visibility.name]}{self.name}{abstract}]"
        value = self._get_struct_wrapper(simplified)

        return self._prepare_struct(key, value, simplified)


CLASS_BODY_DEFAULT = Block(name="class_body")


@public
@typechecked
class ClassDefStmt(ClassDeclStmt):
    """
    title: AST class for class definition, including attributes and methods.
    attributes:
      name: Name identifying this declaration.
      bases: Bases.
      decorators: Decorators.
      visibility: Visibility.
      is_abstract: Whether is abstract.
      metaclass: Metaclass.
      attributes: Attributes.
      methods: Methods.
      kind: Kind of value or operation.
      body: Statements forming the body.
    """

    kind: ASTKind

    body: Block

    def __init__(
        self,
        name: str,
        bases: Iterable[Expr] | ASTNodes[Expr] = [],
        decorators: Iterable[Expr] | ASTNodes[Expr] = [],
        body: Block = CLASS_BODY_DEFAULT,
        visibility: VisibilityKind = VisibilityKind.public,
        is_abstract: bool = False,
        metaclass: Optional[Expr] = None,
        attributes: Iterable[VariableDeclaration]
        | ASTNodes[VariableDeclaration] = [],
        methods: Iterable[FunctionDef] | ASTNodes[FunctionDef] = [],
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize ClassDefStmt instance.
        parameters:
          name: Name identifying the declaration or operation.
          bases: Bases.
          decorators: Decorators.
          body: Statements forming the body.
          visibility: Visibility.
          is_abstract: Whether is abstract.
          metaclass: Metaclass.
          attributes: Attributes.
          methods: Methods.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(
            name=name,
            bases=bases,
            decorators=decorators,
            visibility=visibility,
            is_abstract=is_abstract,
            metaclass=metaclass,
            attributes=attributes,
            methods=methods,
            loc=loc,
            parent=parent,
        )

        if body != CLASS_BODY_DEFAULT:
            self.body = body
        else:
            self.body = copy.deepcopy(body)
            self.body.name = f"{name}_body"
        self.kind = ASTKind.ClassDefStmtKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        class_decl_str = super().__str__()
        if not self.body.nodes:
            body_str = "    pass"
        else:
            body_str = "\n    ".join(str(stmt) for stmt in self.body.nodes)
        return f"{class_decl_str}:\n    {body_str}"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        vis = dict(zip(("public", "private", "protected"), ("+", "-", "#")))
        abstract = ", abstract" if self.is_abstract else ""

        key = f"CLASS-DEF[{vis[self.visibility.name]}{self.name}{abstract}]"
        value = self._get_struct_wrapper(simplified)

        if self.body != CLASS_BODY_DEFAULT:
            value["body"] = self.body.get_struct(simplified)

        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class EnumDeclStmt(StatementType):
    """
    title: AST class for enum declaration.
    attributes:
      kind: Kind of value or operation.
      name: Name identifying this declaration.
      attributes: Attributes.
      visibility: Visibility.
    """

    kind: ASTKind

    name: str
    attributes: ASTNodes[VariableDeclaration]
    visibility: VisibilityKind

    def __init__(
        self,
        name: str,
        attributes: Iterable[VariableDeclaration]
        | ASTNodes[VariableDeclaration] = [],
        visibility: VisibilityKind = VisibilityKind.public,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize EnumDeclStmt instance.
        parameters:
          name: Name identifying the declaration or operation.
          attributes: Attributes.
          visibility: Visibility.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.name = name

        if isinstance(attributes, ASTNodes):
            self.attributes = attributes
        else:
            self.attributes = ASTNodes[VariableDeclaration]()
            for a in attributes:
                self.attributes.append(a)

        self.visibility = visibility
        self.kind = ASTKind.EnumDeclStmtKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        visibility_str = (
            self.visibility.name.lower()
            if self.visibility != VisibilityKind.public
            else ""
        )
        enum_header = f"{visibility_str} enum {self.name}".strip()
        attrs_str = ",\n    ".join(f"{attr}" for attr in self.attributes)

        return f"{enum_header} {{\n    {attrs_str}\n}}"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        vis = dict(zip(("public", "private", "protected"), ("+", "-", "#")))
        key = f"ENUM-DECL[{vis[self.visibility.name]}{self.name}]"

        attrs_dict: ReprStruct = {}
        if self.attributes:
            attrs_dict = {"attributes": self.attributes.get_struct(simplified)}

        value = {
            **cast(DictDataTypesStruct, attrs_dict),
        }
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class StructDeclStmt(StatementType):
    """
    title: AST class for struct declaration.
    attributes:
      kind: Kind of value or operation.
      name: Name identifying this declaration.
      attributes: Attributes.
      visibility: Visibility.
      decorators: Decorators.
      methods: Methods.
    """

    kind: ASTKind

    name: str
    attributes: ASTNodes[VariableDeclaration]
    visibility: VisibilityKind
    decorators: ASTNodes[Expr]
    methods: ASTNodes[FunctionDef]

    def __init__(
        self,
        name: str,
        attributes: Iterable[VariableDeclaration]
        | ASTNodes[VariableDeclaration] = [],
        decorators: Iterable[Expr] | ASTNodes[Expr] = [],
        methods: Iterable[FunctionDef] | ASTNodes[FunctionDef] = [],
        visibility: VisibilityKind = VisibilityKind.public,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize StructDeclStmt instance.
        parameters:
          name: Name identifying the declaration or operation.
          attributes: Attributes.
          decorators: Decorators.
          methods: Methods.
          visibility: Visibility.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.name = name

        if isinstance(attributes, ASTNodes):
            self.attributes = attributes
        else:
            self.attributes = ASTNodes[VariableDeclaration]()
            for a in attributes:
                self.attributes.append(a)

        if isinstance(decorators, ASTNodes):
            self.decorators = decorators
        else:
            self.decorators = ASTNodes[Expr]()
            for decorator in decorators:
                self.decorators.append(decorator)

        if isinstance(methods, ASTNodes):
            self.methods = methods
        else:
            self.methods = ASTNodes[FunctionDef]()
            for m in methods:
                self.methods.append(m)

        self.visibility = visibility
        self.kind = ASTKind.StructDeclStmtKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        decorators_str = "".join(
            f"@{decorator}\n" for decorator in self.decorators
        )
        visibility_str = (
            self.visibility.name.lower()
            if self.visibility != VisibilityKind.public
            else ""
        )
        struct_header = f"{visibility_str} struct {self.name}".strip()
        attributes_str = "\n    ".join(str(attr) for attr in self.attributes)
        return f"{decorators_str}{struct_header} {{\n    {attributes_str}\n}}"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        vis = dict(zip(("public", "private", "protected"), ("+", "-", "#")))
        key = f"STRUCT-DECL[{vis[self.visibility.name]}{self.name}]"

        decors_dict: ReprStruct = {}
        if self.decorators:
            decors_dict = {
                "decorators": self.decorators.get_struct(simplified)
            }

        attrs_dict: ReprStruct = {}
        if self.attributes:
            attrs_dict = {"attributes": self.attributes.get_struct(simplified)}

        methods_dict: ReprStruct = {}
        if self.methods:
            methods_dict = {"methods": self.methods.get_struct(simplified)}

        value: DictDataTypesStruct = {
            **cast(DictDataTypesStruct, decors_dict),
            **cast(DictDataTypesStruct, attrs_dict),
            **cast(DictDataTypesStruct, methods_dict),
        }

        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class StructDefStmt(StructDeclStmt):
    """
    title: AST class for struct definition.
    attributes:
      name: Name identifying this declaration.
      attributes: Attributes.
      visibility: Visibility.
      decorators: Decorators.
      methods: Methods.
      kind: Kind of value or operation.
    """

    kind: ASTKind

    def __init__(
        self,
        name: str,
        attributes: Iterable[VariableDeclaration]
        | ASTNodes[VariableDeclaration] = [],
        decorators: Iterable[Expr] | ASTNodes[Expr] = [],
        methods: Iterable[FunctionDef] | ASTNodes[FunctionDef] = [],
        visibility: VisibilityKind = VisibilityKind.public,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize StructDefStmt instance.
        parameters:
          name: Name identifying the declaration or operation.
          attributes: Attributes.
          decorators: Decorators.
          methods: Methods.
          visibility: Visibility.
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
        self.kind = ASTKind.StructDefStmtKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        decorators_str = "".join(
            f"@{decorator}\n" for decorator in self.decorators
        )
        visibility_str = (
            self.visibility.name.lower()
            if self.visibility != VisibilityKind.public
            else ""
        )
        struct_header = f"{visibility_str} struct {self.name}".strip()
        attributes_str = "\n    ".join(str(attr) for attr in self.attributes)
        return f"{decorators_str}{struct_header} {{\n    {attributes_str}\n}}"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        vis = dict(zip(("public", "private", "protected"), ("+", "-", "#")))
        key = f"STRUCT-DEF[{vis[self.visibility.name]}{self.name}]"

        decors_dict: ReprStruct = {}
        if self.decorators:
            decors_dict = {
                "decorators": self.decorators.get_struct(simplified)
            }

        attrs_dict: ReprStruct = {}
        if self.attributes:
            attrs_dict = {"attributes": self.attributes.get_struct(simplified)}

        methods_dict: ReprStruct = {}
        if self.methods:
            methods_dict = {"methods": self.methods.get_struct(simplified)}

        value: DictDataTypesStruct = {
            **cast(DictDataTypesStruct, decors_dict),
            **cast(DictDataTypesStruct, attrs_dict),
            **cast(DictDataTypesStruct, methods_dict),
        }

        return self._prepare_struct(key, value, simplified)
