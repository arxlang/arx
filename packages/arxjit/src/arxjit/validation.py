# mypy: disable-error-code=no-redef
"""
title: Python-subset validation for arxjit.
summary: >-
  Second stage of the arxjit pipeline: walk the ast node produced by
  arxjit.source and check it only uses the v1 supported subset of pure Python
  (typed scalar arguments, arithmetic/comparison/boolean expressions, single-
  target local assignments, if/else, while, for over range, return). Dispatch
  is by node type via plum, matching the visitor convention used across the Arx
  packages. Every rejected construct is collected into its own Diagnostic so a
  function using several unsupported constructs reports all of them at once via
  UnsupportedSyntaxError; lowering the accepted subset to astx is a later stage
  and is not done here.
"""

from __future__ import annotations

import ast
import builtins

from plum import dispatch

from arxjit.diagnostics import Diagnostic, DiagnosticSeverity
from arxjit.errors import UnsupportedSyntaxError
from arxjit.source import ExtractedSource

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef

# Nodes that open a new scope: their bodies hold their own locals, so the
# binding collector records their name but does not descend into them.
_SCOPE_NODES: tuple[type[ast.AST], ...] = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.ClassDef,
)

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
    ast.Break: "break statements are not supported",
    ast.Continue: "continue statements are not supported",
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
      location when the node carries none. node.lineno is a real file line
      number (extract_source already shifted it), while extracted.source is
      indexed from its own first line, so the node's line is looked up at
      splitlines()[lineno - extracted.lineno] rather than lineno - 1.
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


def _target_names(target: ast.expr) -> set[str]:
    """
    title: Collect the names bound by an assignment or loop target.
    summary: >-
      Handles the tuple, list, and starred forms as well as a plain name, so a
      target the subset rejects still registers its bindings and does not also
      produce a spurious free-variable diagnostic for the same name.
    parameters:
      target:
        type: ast.expr
    returns:
      type: set[str]
    """
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for element in target.elts:
            names |= _target_names(element)
        return names
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    return set()


def _parameter_names(args: ast.arguments) -> set[str]:
    """
    title: Collect the names bound by a function's parameter list.
    summary: >-
      Includes the parameter kinds the subset rejects (variadic and keyword-
      only), so a rejected signature does not also report its own parameters as
      free variables.
    parameters:
      args:
        type: ast.arguments
    returns:
      type: set[str]
    """
    names = {
        arg.arg for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs)
    }
    for variadic in (args.vararg, args.kwarg):
        if variadic is not None:
            names.add(variadic.arg)
    return names


def _statement_bindings(node: ast.AST) -> set[str]:
    """
    title: Collect the names a single statement or expression binds.
    summary: >-
      Covers ordinary and loop assignment as well as the annotated, augmented,
      and walrus forms the subset rejects, so a rejected statement does not
      also produce a free-variable diagnostic for the name it binds.
    parameters:
      node:
        type: ast.AST
    returns:
      type: set[str]
    """
    if isinstance(node, ast.Assign):
        names: set[str] = set()
        for target in node.targets:
            names |= _target_names(target)
        return names
    if isinstance(
        node,
        (
            ast.For,
            ast.AsyncFor,
            ast.AnnAssign,
            ast.AugAssign,
            ast.NamedExpr,
        ),
    ):
        return _target_names(node.target)
    return set()


def _bound_names(node: FunctionNode) -> set[str]:
    """
    title: Collect every name bound as a local of the function's own scope.
    summary: |-
      A name is bound if it is a parameter or is assigned in the body. Any name
      read but not bound is a free variable (a closure capture) or a module
      global, both outside the pure v1 subset. Assignments in never-executed
      branches still bind, matching Python's rule that any assigned name is a
      local.
      Nested scopes are deliberately not descended into: a nested function,
      lambda, or class has its own locals, so collecting them here would both
      mask free-variable reads in this scope and misreport a nested binding as
      shadowing an outer name. The nested definition's own name does bind in
      this scope, so it is collected while its body is skipped.
    parameters:
      node:
        type: FunctionNode
    returns:
      type: set[str]
    """
    names = _parameter_names(node.args)
    pending: list[ast.AST] = list(node.body)
    while pending:
        current = pending.pop()
        if isinstance(current, _SCOPE_NODES):
            # A nested scope: its name binds here, its body does not.
            nested_name = getattr(current, "name", None)
            if isinstance(nested_name, str):
                names.add(nested_name)
            continue
        names |= _statement_bindings(current)
        pending.extend(ast.iter_child_nodes(current))
    return names


class _SubsetValidator:
    """
    title: Collect one diagnostic per construct outside the v1 subset.
    summary: >-
      Dispatches by node type via plum: each accepted construct has its own
      visit overload, and the ast.AST overload is the fail-closed default that
      rejects everything else, so a known-unsupported construct (with a
      specific message) or a future Python node this pass was not updated for
      both fail safe. A rejected node's children are not descended into, so one
      bad subtree yields one diagnostic; independent sibling statements are
      each validated in full.
    attributes:
      extracted:
        description: The extracted source being validated.
      bound:
        description: Names bound as locals or arguments of the function.
      diagnostics:
        type: list[Diagnostic]
        description: One entry per rejected construct.
    """

    def __init__(self, extracted: ExtractedSource, bound: set[str]) -> None:
        """
        title: Initialize the validator for one function's source.
        parameters:
          extracted:
            type: ExtractedSource
          bound:
            type: set[str]
        """
        self.extracted = extracted
        self.bound = bound
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

    def _range_is_builtin(self) -> bool:
        """
        title: Return whether range resolves to the builtin at module level.
        summary: >-
          Checks the defining module's namespace, which extraction carries
          alongside the source. When that namespace is unavailable (only for a
          hand-built ExtractedSource; extract_source always provides it for a
          real function) module-level shadowing cannot be observed and the name
          is taken to be the builtin.
        returns:
          type: bool
        """
        namespace = self.extracted.globalns
        if namespace is None:
            return True
        return namespace.get("range", builtins.range) is builtins.range

    def visit_all(self, statements: list[ast.stmt]) -> None:
        """
        title: Visit each statement in a block in order.
        parameters:
          statements:
            type: list[ast.stmt]
        """
        for statement in statements:
            self.visit(statement)

    @dispatch
    def visit(self, node: ast.AST) -> None:
        """
        title: Reject any node with no accepting overload (fail closed).
        summary: >-
          Reaching this default means the node is a known-unsupported construct
          (looked up for a specific message) or one this validator does not
          recognize at all; both are rejected so new or unhandled syntax fails
          closed instead of silently passing.
        parameters:
          node:
            type: ast.AST
        """
        message = _UNSUPPORTED_MESSAGES.get(
            type(node), f"{type(node).__name__} is not supported"
        )
        self._reject(node, message)

    @dispatch
    def visit(self, node: ast.Return) -> None:
        """
        title: Validate a return statement's value, if any.
        parameters:
          node:
            type: ast.Return
        """
        if node.value is not None:
            self.visit(node.value)

    @dispatch
    def visit(self, node: ast.Assign) -> None:
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

    @dispatch
    def visit(self, node: ast.If) -> None:
        """
        title: Validate an if/else statement and both branches.
        parameters:
          node:
            type: ast.If
        """
        self.visit(node.test)
        self.visit_all(node.body)
        self.visit_all(node.orelse)

    @dispatch
    def visit(self, node: ast.While) -> None:
        """
        title: Validate a while loop and its body.
        summary: >-
          The loop's else clause is rejected: it only runs when the loop exits
          without break, and break is itself outside the subset, so a while-
          else is dead and needlessly complicates lowering.
        parameters:
          node:
            type: ast.While
        """
        self.visit(node.test)
        if node.orelse:
            self._reject(
                node.orelse[0], "while-else clauses are not supported"
            )
        self.visit_all(node.body)

    @dispatch
    def visit(self, node: ast.For) -> None:
        """
        title: Validate a for loop, restricted to iterating over range().
        summary: >-
          The iterable must be a call to the builtin range with one to three
          positional arguments and no keywords; a range shadowed by a local or
          argument is rejected, as is a loop else clause.
        parameters:
          node:
            type: ast.For
        """
        if not isinstance(node.target, ast.Name):
            self._reject(
                node.target,
                "for-loop targets must be a single local variable",
            )
        self._visit_for_iter(node.iter)
        if node.orelse:
            self._reject(node.orelse[0], "for-else clauses are not supported")
        self.visit_all(node.body)

    def _visit_for_iter(self, iterable: ast.expr) -> None:
        """
        title: Validate a for loop's iterable as a builtin range() call.
        summary: >-
          The callee must resolve to the builtin range, so it is rejected when
          shadowed by a local or argument and when shadowed by a module-level
          name in the defining module's namespace, which the AST alone cannot
          reveal. Compiling a shadowed range as the range intrinsic would
          silently disagree with the Python fallback.
        parameters:
          iterable:
            type: ast.expr
        """
        if not (
            isinstance(iterable, ast.Call)
            and isinstance(iterable.func, ast.Name)
            and iterable.func.id == "range"
        ):
            self._reject(
                iterable,
                "for loops are only supported over range(...)",
            )
            return
        if "range" in self.bound:
            self._reject(
                iterable,
                "range is shadowed by a local variable or argument",
            )
            return
        if not self._range_is_builtin():
            self._reject(
                iterable,
                "range is shadowed by a module-level name, so it is not"
                " the builtin range",
            )
            return
        if iterable.keywords:
            self._reject(iterable, "range() does not accept keyword arguments")
            return
        if not 1 <= len(iterable.args) <= 3:
            self._reject(
                iterable,
                "range() takes one to three positional arguments",
            )
            return
        for argument in iterable.args:
            self.visit(argument)

    @dispatch
    def visit(self, node: ast.Expr) -> None:
        """
        title: Accept a standalone string literal, reject anything else.
        summary: >-
          A bare string statement (a docstring, or a no-op string) has no
          compilable effect and is allowed. A bare yield is delegated to the
          default so it gets the specific generators message; any other
          standalone expression computes a value that is discarded and is
          rejected directly.
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

    @dispatch
    def visit(self, node: ast.Pass) -> None:
        """
        title: Accept a pass statement; it has no effect.
        parameters:
          node:
            type: ast.Pass
        """

    @dispatch
    def visit(self, node: ast.Name) -> None:
        """
        title: Accept a bound variable reference, reject a free one.
        summary: >-
          Only names read in an expression reach this overload (assignment and
          loop targets are checked without being visited). A name that is not
          bound as a local or argument is a closure capture or a module global,
          both outside the pure subset.
        parameters:
          node:
            type: ast.Name
        """
        if isinstance(node.ctx, ast.Load) and node.id not in self.bound:
            self._reject(
                node,
                f"reference to {node.id!r}, which is not a local variable"
                " or argument (closures and globals are not supported)",
            )

    @dispatch
    def visit(self, node: ast.Constant) -> None:
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

    @dispatch
    def visit(self, node: ast.BinOp) -> None:
        """
        title: Validate an arithmetic binary expression.
        parameters:
          node:
            type: ast.BinOp
        """
        if not isinstance(node.op, _ALLOWED_BINOPS):
            self._reject(
                node,
                f"the {type(node.op).__name__} operator is not supported",
            )
        self.visit(node.left)
        self.visit(node.right)

    @dispatch
    def visit(self, node: ast.UnaryOp) -> None:
        """
        title: Validate a unary expression.
        parameters:
          node:
            type: ast.UnaryOp
        """
        if not isinstance(node.op, _ALLOWED_UNARYOPS):
            self._reject(
                node,
                f"the {type(node.op).__name__} operator is not supported",
            )
        self.visit(node.operand)

    @dispatch
    def visit(self, node: ast.BoolOp) -> None:
        """
        title: Validate a boolean and/or expression's operands.
        summary: >-
          Python has only ``and`` and ``or`` as boolean operators, both
          supported, so only the operands need validation.
        parameters:
          node:
            type: ast.BoolOp
        """
        for value in node.values:
            self.visit(value)

    @dispatch
    def visit(self, node: ast.Compare) -> None:
        """
        title: Validate a (possibly chained) comparison expression.
        parameters:
          node:
            type: ast.Compare
        """
        for operator in node.ops:
            if not isinstance(operator, _ALLOWED_COMPAREOPS):
                self._reject(
                    node,
                    f"the {type(operator).__name__} comparison is not"
                    " supported",
                )
        self.visit(node.left)
        for comparator in node.comparators:
            self.visit(comparator)

    @dispatch
    def visit(self, node: ast.Call) -> None:
        """
        title: Reject a function call.
        summary: >-
          Only reachable for calls that are not a for loop's range(...)
          iterator, which _visit_for_iter special-cases before it ever reaches
          the generic expression walk.
        parameters:
          node:
            type: ast.Call
        """
        self._reject(
            node,
            "calling functions is not supported (only range() in a for loop)",
        )


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
      Rejects async definitions and generic (PEP 695) type parameters, checks
      the argument shape, then walks the body collecting one diagnostic per
      rejected construct, including free-variable reads (closures and globals).
      A function with several unsupported constructs is reported in a single
      UnsupportedSyntaxError carrying all of them, so a user fixes everything
      in one pass.
    parameters:
      extracted:
        type: ExtractedSource
        description: The result of arxjit.source.extract_source.
    raises:
      UnsupportedSyntaxError: >-
        If the function is async or generic, has an unsupported argument shape,
        reads a free variable, or its body uses any construct outside the v1
        subset.
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
    if getattr(node, "type_params", ()):
        diagnostics.append(
            _diagnostic(
                extracted,
                node,
                "generic functions (type parameters) are not supported",
            )
        )

    diagnostics.extend(_validate_arguments(extracted, node.args))

    visitor = _SubsetValidator(extracted, _bound_names(node))
    visitor.visit_all(node.body)
    diagnostics.extend(visitor.diagnostics)

    if diagnostics:
        raise UnsupportedSyntaxError(
            f"{node.name!r} uses Python constructs outside the"
            " supported subset",
            diagnostics=diagnostics,
        )


__all__ = ["validate"]
