"""
title: Define ASTx for more broader scope.
"""

from __future__ import annotations

import copy

from typing import Optional, cast

from public import public

from astx.base import (
    AST,
    NO_SOURCE_LOCATION,
    ASTKind,
    ASTNodes,
    Expr,
    ReprStruct,
    SourceLocation,
    StatementType,
)
from astx.blocks import Block
from astx.tools.typing import typechecked


@public
@typechecked
class Target(Expr):
    """
    title: Define the Architecture target for the program.
    attributes:
      datalayout: Datalayout.
      triple: Triple.
    """

    datalayout: str
    triple: str

    def __init__(self, datalayout: str, triple: str) -> None:
        """
        title: Initialize the AST instance.
        parameters:
          datalayout: Datalayout.
          triple: Triple.
        """
        super().__init__()
        self.datalayout = datalayout
        self.triple = triple

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = "TARGET"
        value = f"{self.datalayout}, {self.triple}"
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class Module(Block):
    """
    title: AST main expression class.
    attributes:
      kind: Kind of value or operation.
      name: Name identifying this declaration.
      block: Block of statements.
    """

    kind: ASTKind

    name: str

    def __init__(
        self,
        name: str = "main",
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize the AST instance.
        parameters:
          name: Name identifying the declaration or operation.
          loc: Source coordinates associated with the node.
        """
        super().__init__(name=name, loc=loc)
        self.kind = ASTKind.ModuleKind

    def __str__(self) -> str:
        """
        title: Return the string representation of the object.
        returns: String representation of this instance.
        """
        return f"Module[{self.name}]"

    @property
    def block(self) -> list[AST]:
        """
        title: Define an alias for self.nodes.
        returns: 'Result of this operation: define an alias for self.nodes.'
        """
        return self.nodes

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        block_node = []

        for node in self.nodes:
            block_node.append(node.get_struct(simplified))

        key = f"MODULE[{self.name}]"
        value = cast(ReprStruct, block_node)

        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class Package(ASTNodes):
    """
    title: AST class for Package.
    attributes:
      name: Name identifying this declaration.
      modules: Modules.
      packages: Packages.
    """

    name: str
    modules: list[Module]
    packages: list[Package]

    def __init__(
        self,
        name: str = "main",
        modules: list[Module] = [],
        packages: list[Package] = [],
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize the AST instance.
        parameters:
          name: Name identifying the declaration or operation.
          modules: Modules.
          packages: Packages.
          loc: Source coordinates associated with the node.
        """
        super().__init__(loc=loc)
        self.name = name
        self.modules = copy.deepcopy(modules)
        self.packages = copy.deepcopy(packages)

    def __str__(self) -> str:
        """
        title: Return the string representation of the object.
        returns: String representation of this instance.
        """
        return f"PACKAGE[{self.name}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        packages = []
        modules = []

        for package in self.packages:
            packages.append(package.get_struct(simplified))

        for module in self.modules:
            modules.append(module.get_struct(simplified))

        key = str(self)
        value = cast(
            ReprStruct,
            {
                "modules": modules,
                "packages": packages,
            },
        )

        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class Program(Package):
    """
    title: AST class for Program.
    attributes:
      name: Name identifying this declaration.
      modules: Modules.
      packages: Packages.
      target: Destination of the operation.
    """

    target: Target

    def __init__(
        self,
        name: str = "main",
        target: Target = Target("", ""),
        modules: list[Module] = [],
        packages: list[Package] = [],
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize the AST instance.
        parameters:
          name: Name identifying the declaration or operation.
          target: Destination of the operation.
          modules: Modules.
          packages: Packages.
          loc: Source coordinates associated with the node.
        """
        super().__init__(
            name=name, modules=modules, packages=packages, loc=loc
        )
        self.target = copy.deepcopy(target)

    def __str__(self) -> str:
        """
        title: Return the string representation of the object.
        returns: String representation of this instance.
        """
        return f"PROGRAM[{self.name}]"


@public
@typechecked
class AliasExpr(Expr):
    """
    title: Represents an alias in an import statement.
    attributes:
      kind: Kind of value or operation.
      name: Name identifying this declaration.
      asname: Asname.
    """

    kind: ASTKind

    name: str
    asname: str

    def __init__(
        self,
        name: str,
        asname: str = "",
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the alias expression.
        parameters:
          name: Name identifying the declaration or operation.
          asname: Asname.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.name = name
        self.asname = asname
        self.kind = ASTKind.AliasExprKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the alias.
        returns: String representation of this instance.
        """
        if self.asname:
            return f"{self.name} as {self.asname}"
        else:
            return self.name

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the alias.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        str_asname = f", {self.asname}" if self.asname else ""
        str_name_asname = f"[{self.name}{str_asname}]"
        key = f"Alias {str_name_asname}"
        value = ""

        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class ImportStmt(StatementType):
    """
    title: Represents an import statement.
    attributes:
      kind: Kind of value or operation.
      names: Names.
    """

    kind: ASTKind

    names: list[AliasExpr]

    def __init__(
        self,
        names: list[AliasExpr],
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the import statement.
        parameters:
          names: Names.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.names = names
        self.kind = ASTKind.ImportStmtKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the import statement.
        returns: String representation of this instance.
        """
        names_str = ", ".join(str(name) for name in self.names)
        return f"import {names_str}"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the import statement.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = "ImportStmt"
        value = cast(
            ReprStruct, [name.get_struct(simplified) for name in self.names]
        )
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class ImportFromStmt(StatementType):
    """
    title: Represents an import-from statement.
    attributes:
      kind: Kind of value or operation.
      module: Module to process.
      names: Names.
      level: Level.
    """

    kind: ASTKind

    module: Optional[str]
    names: list[AliasExpr]
    level: int

    def __init__(
        self,
        names: list[AliasExpr],
        module: str = "",
        level: int = 0,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the import-from statement.
        parameters:
          names: Names.
          module: Module to process.
          level: Level.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.module = module
        self.names = names
        self.level = level
        self.kind = ASTKind.ImportFromStmtKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the import-from statement.
        returns: String representation of this instance.
        """
        level_dots = "." * self.level
        module_str = (
            f"{level_dots}{self.module}" if self.module else level_dots
        )
        names_str = ", ".join(str(name) for name in self.names)
        return f"from {module_str} import {names_str}"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the import-from statement.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        level_dots = "." * self.level
        module_str = (
            f"{level_dots}{self.module}" if self.module else level_dots
        )

        key = f"ImportFromStmt [{module_str}]"
        value = cast(
            ReprStruct, [name.get_struct(simplified) for name in self.names]
        )

        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class ImportExpr(Expr):
    """
    title: Represents an import operation as an expression.
    attributes:
      kind: Kind of value or operation.
      names: Names.
    """

    kind: ASTKind

    names: list[AliasExpr]

    def __init__(
        self,
        names: list[AliasExpr],
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the import expression.
        parameters:
          names: Names.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.names = names
        self.kind = ASTKind.ImportExprKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the import expression.
        returns: String representation of this instance.
        """
        names_str = ", ".join(str(name) for name in self.names)
        return f"import {names_str}"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the import expression.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = "ImportExpr"
        value = cast(
            ReprStruct, [name.get_struct(simplified) for name in self.names]
        )
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class ImportFromExpr(Expr):
    """
    title: Represents a 'from ... import ...' operation as an expression.
    attributes:
      kind: Kind of value or operation.
      module: Module to process.
      names: Names.
      level: Level.
    """

    kind: ASTKind

    module: str
    names: list[AliasExpr]
    level: int  # Number of leading dots for relative imports

    def __init__(
        self,
        names: list[AliasExpr],
        module: str = "",
        level: int = 0,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the import-from expression.
        parameters:
          names: Names.
          module: Module to process.
          level: Level.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.names = names
        self.module = module
        self.level = level
        self.kind = ASTKind.ImportFromExprKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the import-from expression.
        returns: String representation of this instance.
        """
        level_dots = "." * self.level
        module_str = (
            f"{level_dots}{self.module}" if self.module else level_dots
        )
        names_str = ", ".join(str(name) for name in self.names)

        return f"from {module_str} import {names_str}"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the import-from expression.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        level_dots = "." * self.level
        module_str = (
            f"{level_dots}{self.module}" if self.module else level_dots
        )

        key = f"ImportFromExpr [{module_str}]"
        value = cast(
            ReprStruct, [name.get_struct(simplified) for name in self.names]
        )

        return self._prepare_struct(key, value, simplified)
