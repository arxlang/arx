"""
title: Validate lexical access to local scalar places.
"""

import astx

from public import private

from irx.analysis.context import SemanticContext
from irx.analysis.resolved_nodes import SemanticSymbol
from irx.analysis.types import is_boolean_type, is_numeric_type
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@private
@typechecked
def resolve_borrow_source(
    context: SemanticContext,
    place: astx.Expr,
    access: astx.BorrowAccess,
    *,
    retarget: SemanticSymbol | None = None,
) -> SemanticSymbol | None:
    """
    title: Validate one local scalar place before installing a borrow.
    parameters:
      context: Active semantic context.
      place: Expression designating the original binding.
      access: Access requested by the new borrow.
      retarget: Optional existing borrower whose old loan is ending.
    returns: Source binding if the requested access is available.
    """
    function = context.current_function
    scopes = context.scopes.function_scopes
    if (
        function is None
        or not scopes
        or (function.signature.metadata.get("generator") is not None)
    ):
        context.diagnostics.add(
            "borrows require a local scope in a non-generator function",
            node=place,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return None
    if not isinstance(place, astx.Identifier):
        context.diagnostics.add(
            "a local borrow requires a scalar variable as its source",
            node=place,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return None
    source = context.scopes.resolve(place.name)
    if source is None:
        context.diagnostics.add(
            f"cannot resolve name '{place.name}'",
            node=place,
            code=DiagnosticCodes.SEMANTIC_UNRESOLVED_NAME,
        )
        return None
    if (
        source.kind != "variable"
        or not isinstance(
            source.declaration,
            (astx.VariableDeclaration, astx.InlineVariableDeclaration),
        )
        or not any(scope.symbols.get(place.name) is source for scope in scopes)
        or not (is_numeric_type(source.type_) or is_boolean_type(source.type_))
    ):
        context.diagnostics.add(
            "a local borrow requires an owning numeric or Boolean variable",
            node=place,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return None
    if access is astx.BorrowAccess.exclusive and not source.is_mutable:
        context.diagnostics.add(
            f"cannot exclusively borrow constant '{source.name}'",
            node=place,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return None
    for scope in scopes:
        for borrow in scope.borrows.values():
            if borrow.target is retarget or borrow.source is not source:
                continue
            if (
                access is astx.BorrowAccess.exclusive
                or borrow.access is astx.BorrowAccess.exclusive
            ):
                context.diagnostics.add(
                    f"cannot borrow '{source.name}' while "
                    f"'{borrow.target.name}' has a conflicting borrow",
                    node=place,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                )
                return None
    return source


@private
@typechecked
def check_borrow_access(
    context: SemanticContext,
    symbol: SemanticSymbol,
    node: astx.AST,
    *,
    write: bool = False,
    read_checked: bool = False,
) -> bool:
    """
    title: Enforce exclusive access and forbid writes through shared borrows.
    parameters:
      context: Active semantic context.
      symbol: Binding being read or written.
      node: Syntax that accesses the binding.
      write: Whether the access can mutate storage.
      read_checked: Whether the same target already performed a read check.
    returns: Whether the access is allowed.
    """
    if write and symbol.kind == "borrow" and not symbol.is_mutable:
        context.diagnostics.add(
            f"cannot write through read-only borrow '{symbol.name}'",
            node=node,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return False
    for scope in context.scopes.function_scopes:
        for borrow in scope.borrows.values():
            exclusive = borrow.access is astx.BorrowAccess.exclusive
            if borrow.source is not symbol or not (write or exclusive):
                continue
            if not (exclusive and read_checked):
                action = "write" if write else "read"
                context.diagnostics.add(
                    f"cannot {action} '{symbol.name}' while it is borrowed "
                    f"by '{borrow.target.name}'",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                )
            return False
    return True
