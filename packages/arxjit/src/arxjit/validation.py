"""
title: Python-subset validation for arxjit.
summary: >-
  Second stage of the arxjit pipeline: walk the ast node produced by
  arxjit.source and check it only uses the v1 supported subset of pure Python
  (typed scalar arguments, arithmetic/comparison/boolean expressions, local
  assignments, if/while, for over range, return). Every rejected construct is
  collected into its own Diagnostic so a function using several unsupported
  constructs reports all of them at once via UnsupportedSyntaxError; lowering
  the accepted subset to astx is a later stage and is not done here.
"""

from __future__ import annotations

import ast

from typing import cast

from arxjit.diagnostics import Diagnostic, DiagnosticSeverity
from arxjit.errors import UnsupportedSyntaxError
from arxjit.source import ExtractedSource

_ALLOWED_BINOPS: tuple[type[ast.operator], ...] = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
)
_ALLOWED_UNARYOPS: tuple[type[ast.unaryop], ...] = (
    ast.UAdd,
    ast.USub,
    ast.Not,
)
_ALLOWED_BOOLOPS: tuple[type[ast.boolop], ...] = (ast.And, ast.Or)
_ALLOWED_COMPAREOPS: tuple[type[ast.cmpop], ...] = (
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)

_UNSUPPORTED_MESSAGES: dict[type[ast.AST], str] = {
    ast.ClassDef: "class definitions are not supported",
    ast.Lambda: "lambda expressions are not supported",
    ast.FunctionDef: (
        "nested function definitions (closures) are not supported"
    ),
    ast.AsyncFunctionDef: "async function definitions are not supported",
    ast.AsyncFor: "async for loops are not supported",
    ast.AsyncWith: "with statements are not supported",
    ast.With: "with statements are not supported",
    ast.Try: "try/except is not supported",
    ast.Raise: "raise statements are not supported",
    ast.Assert: "assert statements are not supported",
    ast.Import: "import statements are not supported",
    ast.ImportFrom: "import statements are not supported",
    ast.Global: "global declarations are not supported",
    ast.Nonlocal: "nonlocal declarations are not supported",
    ast.Yield: "generators (yield) are not supported",
    ast.YieldFrom: "generators (yield) are not supported",
    ast.Await: "await expressions are not supported",
    ast.List: "list literals are not supported",
    ast.Dict: "dict literals are not supported",
    ast.Set: "set literals are not supported",
    ast.Tuple: "tuple literals are not supported",
    ast.ListComp: "comprehensions are not supported",
    ast.DictComp: "comprehensions are not supported",
    ast.SetComp: "comprehensions are not supported",
    ast.GeneratorExp: "generator expressions are not supported",
    ast.Delete: "del statements are not supported",
    ast.AnnAssign: "annotated assignments are not supported",
    ast.AugAssign: "augmented assignment (e.g. +=) is not supported",
    ast.JoinedStr: "f-strings are not supported",
    ast.NamedExpr: "walrus assignment expressions are not supported",
    ast.Starred: "starred expressions are not supported",
    ast.Attribute: "attribute access is not supported",
    ast.Subscript: "subscripting is not supported",
    ast.Slice: "slicing is not supported",
    ast.Match: "match statements are not supported",
}
# TryStar (except*) was added in Python 3.11; guard the reference so this
# module still imports cleanly on 3.10.
if (_try_star := getattr(ast, "TryStar", None)) is not None:
    _UNSUPPORTED_MESSAGES[_try_star] = "try/except* is not supported"


def _is_range_call(node: ast.expr) -> bool:
    """
    title: Return whether a node is a call to the builtin range().
    summary: >-
      Only the exact shape range(...) with no keyword arguments is accepted;
      range is looked up by name only, so a shadowed or attribute-qualified
      "range" is rejected like any other call.
    parameters:
      node:
        type: ast.expr
    returns:
      type: bool
    """
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "range"
        and not node.keywords
    )


def _char_column(line: str, byte_offset: int) -> int:
    """
    title: Convert a zero-based UTF-8 byte offset to a one-based column.
    summary: >-
      ast column offsets are zero-based UTF-8 byte offsets into their source
      line, but Diagnostic.column is documented as a one-based Unicode
      character column. Decoding the byte prefix back to text and measuring its
      length performs the conversion exactly, including when multi-byte
      characters appear before the target column.
    parameters:
      line:
        type: str
        description: The real source line the offset was reported against.
      byte_offset:
        type: int
    returns:
      type: int
    """
    prefix = line.encode("utf-8")[:byte_offset]
    return len(prefix.decode("utf-8", errors="replace")) + 1


def _diagnostic(
    extracted: ExtractedSource,
    node: ast.AST,
    message: str,
) -> Diagnostic:
    """
    title: Build an ERROR diagnostic located at an ast node.
    summary: >-
      Reads the node's lineno/col_offset when present and converts the column
      to the one-based character contract via _char_column; falls back to no
      location when the node carries none (rare for real parsed nodes, but kept
      safe for synthetic ones). node.lineno is a real file line number
      (extract_source already shifted it), while extracted.source is indexed
      from its own first line, so the node's line is looked up at
      extracted.source.splitlines()[lineno - extracted.lineno] rather than
      lineno - 1.
    parameters:
      extracted:
        type: ExtractedSource
      node:
        type: ast.AST
      message:
        type: str
    returns:
      type: Diagnostic
    """
    lineno = getattr(node, "lineno", None)
    col_offset = getattr(node, "col_offset", None)
    column = None
    if lineno is not None and col_offset is not None:
        lines = extracted.source.splitlines()
        index = lineno - extracted.lineno
        if 0 <= index < len(lines):
            column = _char_column(lines[index], col_offset)
    return Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        message=message,
        filename=extracted.filename,
        line=lineno,
        column=column,
    )


class _SubsetValidator(ast.NodeVisitor):
    """
    title: Collect one diagnostic per Python construct outside the v1 subset.
    summary: >-
      A rejected node's children are not descended into, so a single bad
      expression tree reports one diagnostic rather than one per nested node;
      independent sibling statements (including inside if/while/for bodies) are
      still each visited and validated in full.
    attributes:
      extracted:
        description: The extracted source being validated.
      diagnostics:
        type: list[Diagnostic]
        description: One entry per rejected construct.
    """

    def __init__(self, extracted: ExtractedSource) -> None:
        """
        title: Initialize the validator for one function's source.
        parameters:
          extracted:
            type: ExtractedSource
        """
        self.extracted = extracted
        self.diagnostics: list[Diagnostic] = []

    def _reject(self, node: ast.AST, message: str) -> None:
        """
        title: Record a diagnostic for an unsupported node.
        parameters:
          node:
            type: ast.AST
          message:
            type: str
        """
        self.diagnostics.append(_diagnostic(self.extracted, node, message))

    # -- statements --------------------------------------------------

    def visit_Return(self, node: ast.Return) -> None:
        """
        title: Validate a return statement's value, if any.
        parameters:
          node:
            type: ast.Return
        """
        if node.value is not None:
            self.visit(node.value)

    def visit_Assign(self, node: ast.Assign) -> None:
        """
        title: Validate a single-target local variable assignment.
        parameters:
          node:
            type: ast.Assign
        """
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            self._reject(
                node,
                "only assignment to a single local variable is supported",
            )
        self.visit(node.value)

    def visit_If(self, node: ast.If) -> None:
        """
        title: Validate an if/else statement and both branches.
        parameters:
          node:
            type: ast.If
        """
        self.visit(node.test)
        for stmt in (*node.body, *node.orelse):
            self.visit(stmt)

    def visit_While(self, node: ast.While) -> None:
        """
        title: Validate a while loop and its body.
        parameters:
          node:
            type: ast.While
        """
        self.visit(node.test)
        for stmt in (*node.body, *node.orelse):
            self.visit(stmt)

    def visit_For(self, node: ast.For) -> None:
        """
        title: Validate a for loop, restricted to iterating over range().
        parameters:
          node:
            type: ast.For
        """
        if not isinstance(node.target, ast.Name):
            self._reject(
                node.target,
                "for-loop targets must be a single local variable",
            )
        if _is_range_call(node.iter):
            for arg in cast(ast.Call, node.iter).args:
                self.visit(arg)
        else:
            self._reject(
                node.iter,
                "for loops are only supported over range(...)",
            )
        for stmt in (*node.body, *node.orelse):
            self.visit(stmt)

    def visit_Expr(self, node: ast.Expr) -> None:
        """
        title: Accept a standalone string literal, reject anything else.
        summary: >-
          A bare string statement (a docstring, or a no-op string anywhere in
          the body) has no compilable effect and is silently allowed. A bare
          "yield x" is the common generator-function form and is delegated to
          the generic unsupported-construct lookup so it gets the specific
          generators message instead of a generic one; any other standalone
          expression statement computes a value that is immediately discarded
          and is rejected directly.
        parameters:
          node:
            type: ast.Expr
        """
        if isinstance(node.value, ast.Constant) and isinstance(
            node.value.value, str
        ):
            return
        if isinstance(node.value, (ast.Yield, ast.YieldFrom)):
            self.visit(node.value)
            return
        self._reject(
            node, "standalone expression statements are not supported"
        )

    def visit_Pass(self, node: ast.Pass) -> None:
        """
        title: Accept a pass statement; it has no effect.
        parameters:
          node:
            type: ast.Pass
        """

    # -- expressions -------------------------------------------------

    def visit_Name(self, node: ast.Name) -> None:
        """
        title: Accept a variable reference.
        parameters:
          node:
            type: ast.Name
        """

    def visit_Constant(self, node: ast.Constant) -> None:
        """
        title: Accept only int, float, and bool literals.
        parameters:
          node:
            type: ast.Constant
        """
        if isinstance(node.value, (bool, int, float)):
            return
        kind = type(node.value).__name__
        self._reject(node, f"{kind} literals are not supported")

    def visit_BinOp(self, node: ast.BinOp) -> None:
        """
        title: Validate an arithmetic binary expression.
        parameters:
          node:
            type: ast.BinOp
        """
        if not isinstance(node.op, _ALLOWED_BINOPS):
            kind = type(node.op).__name__
            self._reject(node, f"the {kind} operator is not supported")
        self.visit(node.left)
        self.visit(node.right)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        """
        title: Validate a unary expression.
        parameters:
          node:
            type: ast.UnaryOp
        """
        if not isinstance(node.op, _ALLOWED_UNARYOPS):
            kind = type(node.op).__name__
            self._reject(node, f"the {kind} operator is not supported")
        self.visit(node.operand)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        """
        title: Validate a boolean and/or expression.
        parameters:
          node:
            type: ast.BoolOp
        """
        if not isinstance(node.op, _ALLOWED_BOOLOPS):  # pragma: no cover
            # And and Or are the only boolean operators, so this guard is
            # unreachable today; it is kept for parity with the other
            # operator visitors and to fail closed if Python adds one.
            kind = type(node.op).__name__
            self._reject(node, f"the {kind} operator is not supported")
        for value in node.values:
            self.visit(value)

    def visit_Compare(self, node: ast.Compare) -> None:
        """
        title: Validate a (possibly chained) comparison expression.
        parameters:
          node:
            type: ast.Compare
        """
        for op in node.ops:
            if not isinstance(op, _ALLOWED_COMPAREOPS):
                kind = type(op).__name__
                self._reject(node, f"the {kind} comparison is not supported")
        self.visit(node.left)
        for comparator in node.comparators:
            self.visit(comparator)

    def visit_Call(self, node: ast.Call) -> None:
        """
        title: Reject a function call.
        summary: >-
          Only reachable for calls that are not a for-loop's range(...)
          iterator, which visit_For special-cases before it ever reaches the
          generic expression visitor.
        parameters:
          node:
            type: ast.Call
        """
        self._reject(
            node,
            "calling functions is not supported (only range() in a for loop)",
        )

    def generic_visit(self, node: ast.AST) -> None:
        """
        title: Reject any node with no explicit visit_* handler.
        summary: >-
          Every accepted statement and expression kind has its own visit_*
          method above; reaching this method means the node is either a known-
          unsupported construct (looked up for a specific message) or one this
          validator does not recognize at all, which is rejected the same way
          so new Python syntax fails closed instead of silently passing
          through.
        parameters:
          node:
            type: ast.AST
        """
        message = _UNSUPPORTED_MESSAGES.get(type(node))
        if message is None:
            message = f"{type(node).__name__} is not supported"
        self._reject(node, message)


def _validate_arguments(
    extracted: ExtractedSource,
    args: ast.arguments,
) -> list[Diagnostic]:
    """
    title: Reject argument shapes outside the v1 subset.
    summary: >-
      Rejects *args, **kwargs, keyword-only arguments, and default values; does
      not check argument or return annotations, which is the reconciliation
      stage's job once a function has already passed validation.
    parameters:
      extracted:
        type: ExtractedSource
      args:
        type: ast.arguments
    returns:
      type: list[Diagnostic]
    """
    diagnostics: list[Diagnostic] = []
    if args.vararg is not None:
        diagnostics.append(
            _diagnostic(
                extracted,
                args.vararg,
                "variadic positional arguments (*args) are not supported",
            )
        )
    if args.kwarg is not None:
        diagnostics.append(
            _diagnostic(
                extracted,
                args.kwarg,
                "variadic keyword arguments (**kwargs) are not supported",
            )
        )
    if args.kwonlyargs:
        diagnostics.append(
            _diagnostic(
                extracted,
                args.kwonlyargs[0],
                "keyword-only arguments are not supported",
            )
        )
    default = next(
        (d for d in (*args.defaults, *args.kw_defaults) if d is not None),
        None,
    )
    if default is not None:
        diagnostics.append(
            _diagnostic(
                extracted,
                default,
                "default argument values are not supported",
            )
        )
    return diagnostics


def validate(extracted: ExtractedSource) -> None:
    """
    title: Validate that a function uses only the supported Python subset.
    summary: >-
      Checks the function's argument shape and walks its body, collecting one
      diagnostic per rejected construct. A function using several unsupported
      constructs is reported in a single UnsupportedSyntaxError carrying all of
      them, so a user fixes everything in one pass instead of one error at a
      time.
    parameters:
      extracted:
        type: ExtractedSource
        description: The result of arxjit.source.extract_source.
    raises:
      UnsupportedSyntaxError: >-
        If the function is async, has an unsupported argument shape, or its
        body uses any construct outside the v1 subset.
    """
    node = extracted.node
    diagnostics: list[Diagnostic] = []

    if isinstance(node, ast.AsyncFunctionDef):
        diagnostics.append(
            _diagnostic(
                extracted,
                node,
                "async function definitions are not supported",
            )
        )

    diagnostics.extend(_validate_arguments(extracted, node.args))

    visitor = _SubsetValidator(extracted)
    for stmt in node.body:
        visitor.visit(stmt)
    diagnostics.extend(visitor.diagnostics)

    if diagnostics:
        raise UnsupportedSyntaxError(
            f"{node.name!r} uses Python constructs outside the"
            " supported subset",
            diagnostics=diagnostics,
        )


__all__ = ["validate"]
