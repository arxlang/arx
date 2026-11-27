"""
title: AST classes and functions.
attributes:
  PrimitivesStruct: Primitives struct.
  DataTypesStruct: Data types struct.
  DictDataTypesStruct: Dict data types struct.
  ReprStruct: Repr struct.
"""

from __future__ import annotations

import json

from abc import abstractmethod
from enum import Enum
from hashlib import sha256
from typing import (
    Any,
    ClassVar,
    Generic,
    Iterator,
    Optional,
    TypeAlias,
    cast,
)

import yaml

from public import public
from typing_extensions import TypeVar

from astx.tools.typing import typechecked

ASTType = TypeVar("ASTType", bound="AST", default="AST")


__all__ = [
    "DataTypesStruct",
    "DictDataTypesStruct",
    "ExprType",
    "PrimitivesStruct",
    "ReprStruct",
]


def is_using_jupyter_notebook() -> bool:
    """
    title: Check if it is executed in a jupyter notebook.
    returns: 'Result of this operation: check if it is executed in a jupyter
      notebook.'
    """
    try:
        from IPython import get_ipython

        if "IPKernelApp" in get_ipython().config:
            return True
    except Exception:
        pass
    return False


@public
@typechecked
class SourceLocation:
    """
    title: Source coordinates attached to AST nodes.
    attributes:
      line: Source line coordinate.
      col: Source column coordinate.
    """

    line: int
    col: int

    def __init__(self, line: int, col: int) -> None:
        """
        title: Initialize the source location.
        parameters:
          line: Source line coordinate.
          col: Source column or column selector.
        """
        self.line = line
        self.col = col

    def __str__(self) -> str:
        """
        title: Return a string representation of the source location.
        returns: String representation of this instance.
        """
        return "{" + f"line: {self.line}, col: {self.col}" + "}"

    def __repr__(self) -> str:
        """
        title: Return a representation of the source location.
        returns: Printable representation of this instance.
        """
        return str(self)


NO_SOURCE_LOCATION = SourceLocation(-1, -1)


@public
@typechecked
class ASTKind(Enum):
    """
    title: The expression kind class used for downcasting.
    """

    GenericKind = -100
    ModuleKind = -101
    ParenthesizedExprKind = -102

    # variables
    ArgumentKind = -200
    ArgumentsKind = -201
    VariableKind = -202
    VarDeclKind = -203
    VarsDeclKind = -204
    VariableAssignmentKind = -205
    VarsAssignKind = -206
    DeleteStmtKind = -207
    BorrowDeclarationKind = -208
    BorrowRetargetKind = -209

    # operators
    UnaryOpKind = -300
    BinaryOpKind = -301
    WalrusOpKind = -302
    AssignmentExprKind = -303
    AugmentedAssignKind = -304
    CompareOpKind = -305
    StarredKind = -306

    # functions
    PrototypeKind = -400
    FunctionDefKind = -401
    CallKind = -402
    ReturnKind = -403
    LambdaExprKind = -404
    FunctionAsyncDefKind = -405
    AwaitExprKind = -406
    YieldExprKind = -407
    YieldFromExprKind = -408
    ComprehensionKind = -409
    ListComprehensionKind = -410
    SetComprehensionKind = -411
    YieldStmtKind = -412

    # control flow
    IfStmtKind = -500
    ForCountLoopStmtKind = -501
    ForRangeLoopStmtKind = -502
    WhileStmtKind = -503
    ForRangeLoopExprKind = -504
    ForCountLoopExprKind = -505
    WhileExprKind = -506
    IfExprKind = -507
    CaseStmtKind = -508
    SwitchStmtKind = -509
    GotoStmtKind = -511
    WithStmtKind = -512
    AsyncRangeLoopStmtKind = -513
    AsyncRangeLoopExprKind = -514
    DoWhileStmtKind = -515
    DoWhileExprKind = -516
    GeneratorExprKind = -517
    BreakStmtKind = -518
    ContinueStmtKind = -519

    # data types
    NullDTKind = -600
    BooleanDTKind = -601
    Int8DTKind = -602
    UInt8DTKind = -603
    Int16DTKind = -604
    UInt16DTKind = -605
    Int32DTKind = -606
    UInt32DTKind = -607
    Int64DTKind = -608
    UInt64DTKind = -609
    FloatDTKind = -610
    DoubleDTKind = -611
    BinaryDTKind = -612
    StringDTKind = -613
    FixedSizeBinaryDTKind = -614
    Date32DTKind = -615
    Date64DTKind = -616
    TimestampDTKind = -617
    Time32DTKind = -618
    Time64DTKind = -619
    Decimal128DTKind = -620
    Decimal256DTKind = -621
    UTF8CharDTKind = -622
    UTF8StringDTKind = -623
    TimeDTKind = -624
    DateDTKind = -625
    DateTimeDTKind = -626

    # imports(packages)
    ImportStmtKind = -700
    ImportFromStmtKind = -701
    AliasExprKind = -702
    ImportExprKind = -800
    ImportFromExprKind = -801

    TypeCastExprKind = -809

    # classes
    ClassDefStmtKind = -900
    ClassDeclStmtKind = -901
    EnumDeclStmtKind = -902
    StructDeclStmtKind = -903
    StructDefStmtKind = -904

    # subscrpts
    SubscriptExprKind = -1000
    EllipsisKind = -1001

    # exceptions
    ThrowStmtKind = -1100
    CatchHandlerStmtKind = -1101
    ExceptionHandlerStmtKind = -1102
    FinallyHandlerStmtKind = -1103

    # boolops
    AndOpKind = -1200
    OrOpKind = -1201
    XorOpKind = -1202
    NandOpKind = -1203
    NorOpKind = -1204
    XnorOpKind = -1205
    NotOpKind = -1206


class ASTMeta(type):
    """
    title: Display AST classes by their unqualified names.
    """

    def __str__(cls) -> str:
        """
        title: Return an string that represents the object.
        returns: String representation of this instance.
        """
        return cls.__name__


@public
@typechecked
class AST(metaclass=ASTMeta):
    """
    title: AST main expression class.
    attributes:
      loc: Source coordinates attached to this node.
      kind: Kind of value or operation.
      comment: Comment.
      parent: Parent node in the syntax tree.
      ref: Identifier associated with this node.
    """

    loc: SourceLocation
    kind: ASTKind
    comment: str
    parent: Optional[ASTNodes] = None
    ref: str

    def __init__(
        self,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the AST instance.
        parameters:
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        self.kind = ASTKind.GenericKind
        self.loc = loc
        self.ref = ""
        self.comment = ""
        self.parent = parent
        self._update_parent()

    def __hash__(self) -> int:
        """
        title: Return a stable hash for the AST structure.
        returns: Hash of this instance.
        """
        value = sha256(f"{self.get_struct()}".encode("utf8")).digest()
        return int.from_bytes(value, "big")

    def __str__(self) -> str:
        """
        title: Return an string that represents the object.
        returns: String representation of this instance.
        """
        return f"{self.__class__.__name__}"

    def __repr__(self) -> str:
        """
        title: Return an string that represents the object.
        returns: Printable representation of this instance.
        """
        if is_using_jupyter_notebook():
            return ""

        from astx.viz import visualize_ascii

        result = visualize_ascii(self.get_struct())

        return result

    def _repr_png_(self) -> None:
        """
        title: Return PNG representation of the Graphviz object.
        summary: >2-

          This method is specially recognized by Jupyter Notebook to display

          a Graphviz diagram inline.
        """
        # importing it here in order to avoid cyclic import issue
        from astx.viz import visualize_image

        visualize_image(self.get_struct(simplified=False))

    def _update_parent(self) -> None:
        """
        title: Update the parent node.
        """
        if self.parent is not None:
            self.parent.append(self)

    def _get_metadata(self) -> ReprStruct:
        """
        title: Return the metadata for the requested AST.
        returns: The metadata for the requested AST.
        """
        metadata = {
            "loc": {"line": self.loc.line, "col": self.loc.col},
            "comment": self.comment,
            "ref": self.ref,
            "kind": self.kind.value,
        }
        return cast(ReprStruct, metadata)

    def _prepare_struct(
        self,
        key: str,
        value: PrimitivesStruct | ReprStruct,
        simplified: bool,
    ) -> ReprStruct:
        """
        title: Prepare a representation structure for the node.
        parameters:
          key: Key selecting the entry.
          value: Value to process.
          simplified: Whether to request the compact representation.
        returns: 'Result of this operation: prepare a representation structure
          for the node.'
        """
        struct: ReprStruct = (
            {
                key: {
                    "content": value,
                    "metadata": self._get_metadata(),
                }
            }
            if not simplified
            else {key: value}
        )
        return struct

    @abstractmethod
    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return a structure that represents the node object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """

    def to_yaml(self, simplified: bool = False) -> str:
        """
        title: Return an yaml string that represents the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: An yaml string that represents the object.
        """
        return str(
            yaml.dump(self.get_struct(simplified=simplified), sort_keys=False)
        )

    def to_json(self, simplified: bool = False) -> str:
        """
        title: Return an json string that represents the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: An json string that represents the object.
        """
        return json.dumps(self.get_struct(simplified=simplified), indent=2)


@public
@typechecked
class ASTNodes(Generic[ASTType], AST):
    """
    title: AST with a list of nodes, supporting type-specific elements.
    attributes:
      loc: Source coordinates attached to this node.
      kind: Kind of value or operation.
      comment: Comment.
      parent: Parent node in the syntax tree.
      ref: Identifier associated with this node.
      name: Name identifying this declaration.
      nodes: Contained syntax nodes in order.
      position: Position.
    """

    name: str
    nodes: list[ASTType]
    position: int = 0

    def __init__(
        self,
        name: str = "entry",
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the AST instance.
        parameters:
          name: Name identifying the declaration or operation.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.name = name
        self.nodes: list[ASTType] = []
        self.position: int = 0

    def __iter__(self) -> Iterator[ASTType]:
        """
        title: Overload `iter` magic function.
        returns: Iterator over the contained items.
        """
        self.position = 0  # Reset position for fresh iteration
        return self

    def __next__(self) -> ASTType:
        """
        title: Overload `next` magic function.
        returns: Next item from the iterator.
        """
        if self.position >= len(self.nodes):
            self.position = 0
            raise StopIteration()

        i = self.position
        self.position += 1
        return self.nodes[i]

    def append(self, value: ASTType) -> None:
        """
        title: Append a new node to the stack.
        parameters:
          value: Value to process.
        """
        self.nodes.append(value)

    def __getitem__(self, index: int) -> ASTType:
        """
        title: Support subscripting to get nodes by index.
        parameters:
          index: Index selecting the item.
        returns: Item selected by the index.
        """
        return self.nodes[index]

    def __len__(self) -> int:
        """
        title: Return the number of nodes, supports len function.
        returns: Number of contained items.
        """
        return len(self.nodes)

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return a string that represents the object.
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
class Expr(AST):
    """
    title: AST main expression class.
    attributes:
      loc: Source coordinates attached to this node.
      kind: Kind of value or operation.
      comment: Comment.
      parent: Parent node in the syntax tree.
      ref: Identifier associated with this node.
      nbytes: Nbytes.
    """

    nbytes: int = 0


@public
@typechecked
class ExprType(Expr):
    """
    title: ExprType expression class.
    attributes:
      loc: Source coordinates attached to this node.
      kind: Kind of value or operation.
      comment: Comment.
      parent: Parent node in the syntax tree.
      ref: Identifier associated with this node.
      nbytes: Nbytes.
    """

    nbytes: int = 0

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return a structure that represents the node object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        return {"Type": self.__class__.__name__}


@public
@typechecked
class Undefined(Expr):
    """
    title: Undefined expression class.
    attributes:
      loc: Source coordinates attached to this node.
      kind: Kind of value or operation.
      comment: Comment.
      parent: Parent node in the syntax tree.
      ref: Identifier associated with this node.
      nbytes: Nbytes.
    """

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return a simple structure that represents the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        value = "UNDEFINED"
        key = "UNDEFINED"
        return self._prepare_struct(key, value, simplified)


PrimitivesStruct: TypeAlias = int | str | float | bool | Undefined
DataTypesStruct: TypeAlias = PrimitivesStruct | dict[str, Any] | list[Any]
DictDataTypesStruct: TypeAlias = dict[str, DataTypesStruct]
ReprStruct: TypeAlias = list[DataTypesStruct] | DictDataTypesStruct | Undefined


@public
@typechecked
class DataType(ExprType):
    """
    title: AST main expression class.
    attributes:
      loc: Source coordinates attached to this node.
      kind: Kind of value or operation.
      comment: Comment.
      parent: Parent node in the syntax tree.
      ref: Identifier associated with this node.
      nbytes: Nbytes.
      type_: Type associated with this expression.
      name: Name identifying this declaration.
      _tmp_id: Identifier for tmp.
    """

    type_: ExprType
    name: str
    _tmp_id: ClassVar[int] = 0

    def __init__(
        self,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the data type.
        parameters:
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.name = f"temp_{DataType._tmp_id}"
        DataType._tmp_id += 1
        # set it as a generic data type
        self.type_: ExprType = ExprType()

    def __str__(self) -> str:
        """
        title: Return an string that represents the object.
        returns: String representation of this instance.
        """
        return f"{self.__class__.__name__}: {self.name}"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return a simple structure that represents the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"DATA-TYPE[{self.__class__.__name__}]"
        value = self.name
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class OperatorType(DataType):
    """
    title: AST main expression class.
    attributes:
      loc: Source coordinates attached to this node.
      kind: Kind of value or operation.
      comment: Comment.
      parent: Parent node in the syntax tree.
      ref: Identifier associated with this node.
      nbytes: Nbytes.
      type_: Type associated with this expression.
      name: Name identifying this declaration.
      _tmp_id: Identifier for tmp.
    """


@public
@typechecked
class StatementType(AST):
    """
    title: AST main expression class.
    attributes:
      loc: Source coordinates attached to this node.
      kind: Kind of value or operation.
      comment: Comment.
      parent: Parent node in the syntax tree.
      ref: Identifier associated with this node.
    """


@public
@typechecked
class ParenthesizedExpr(DataType):
    """
    title: AST class for explicitly grouped expressions (parentheses retained).
    attributes:
      loc: Source coordinates attached to this node.
      comment: Comment.
      parent: Parent node in the syntax tree.
      ref: Identifier associated with this node.
      nbytes: Nbytes.
      name: Name identifying this declaration.
      _tmp_id: Identifier for tmp.
      type_: Type associated with this expression.
      kind: Kind of value or operation.
      value: Stored value.
    """

    type_: DataType
    kind: ASTKind

    value: Expr

    def __init__(
        self,
        value: Expr,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the ParenthesizedExpr instance.
        parameters:
          value: Value to process.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.type_ = getattr(value, "type_", DataType())
        self.value = value
        self.kind = ASTKind.ParenthesizedExprKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the object with parentheses.
        returns: String representation of this instance.
        """
        return f"ParenthesizedExpr({self.value})"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = "PARENTHESIZED-EXPR"
        value = self.value.get_struct(simplified)
        return self._prepare_struct(key, value, simplified)
