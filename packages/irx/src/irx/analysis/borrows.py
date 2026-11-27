"""
title: Validate lexical and call-scoped access to borrowed places.
"""

from collections.abc import Iterator

import astx

from public import private

from irx.analysis.class_lifecycle import lifecycle_children
from irx.analysis.context import SemanticContext
from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.ownership import symbol_resource_ownership
from irx.analysis.resolved_nodes import (
    FailedInferenceType,
    OwnershipKind,
    ParameterPassingKind,
    SemanticInfo,
    SemanticSymbol,
)
from irx.analysis.types import is_boolean_type, is_numeric_type
from irx.diagnostics import DiagnosticBag, DiagnosticCodes
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
    if write and (
        (symbol.kind == "borrow" and not symbol.is_mutable)
        or (
            isinstance(symbol.declaration, astx.Argument)
            and symbol.declaration.borrow_access is astx.BorrowAccess.read_only
        )
    ):
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


@private
@typechecked
def resolve_list_call_borrow(
    context: SemanticContext, operand: astx.BorrowArgument
) -> SemanticSymbol | None:
    """
    title: Validate named dynamic list storage for a call-scoped loan.
    parameters:
      context: Active semantic context.
      operand: Explicitly borrowed call argument.
    returns: The local storage binding if access is permitted.
    """
    source = operand.source
    info = getattr(source, "semantic", None)
    symbol = info.resolved_symbol if isinstance(info, SemanticInfo) else None
    function = context.current_function
    if (
        not isinstance(source, astx.Identifier)
        or symbol is None
        or not isinstance(symbol.type_, astx.ListType)
        or not any(
            scope.symbols.get(source.name) is symbol
            for scope in context.scopes.function_scopes
        )
        or function is None
        or function.signature.metadata.get("generator") is not None
    ):
        context.diagnostics.add(
            "a list borrow requires a named local list or borrowed parameter",
            node=operand,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return None

    declaration = symbol.declaration
    forwarded = (
        declaration.borrow_access
        if isinstance(declaration, astx.Argument)
        else None
    )
    ownership = symbol_resource_ownership(symbol)
    if forwarded is None and (
        ownership is None or ownership.kind is not OwnershipKind.OWNED
    ):
        context.diagnostics.add(
            "a list borrow requires dynamically owned list storage",
            node=operand,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return None
    if operand.access is astx.BorrowAccess.exclusive and (
        (forwarded is None and not symbol.is_mutable)
        or forwarded is astx.BorrowAccess.read_only
        or symbol.symbol_id in context.active_list_iteration_owners
    ):
        context.diagnostics.add(
            f"cannot exclusively borrow '{symbol.name}': requires writable "
            "storage outside active iteration",
            node=operand,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return None
    return symbol


@private
@typechecked
def analyze_list_call_operand(
    analyzer: SemanticAnalyzerCore, operand: astx.BorrowArgument
) -> None:
    """
    title: Resolve the storage of a borrow at a checked call boundary.
    parameters:
      analyzer: Active semantic analyzer.
      operand: Explicit borrow operand.
    """
    analyzer.visit(operand.source)
    source = resolve_list_call_borrow(analyzer.context, operand)
    analyzer._semantic(operand).resolved_symbol = None
    if source is None:
        analyzer._set_type(operand, FailedInferenceType())
        return
    analyzer._set_symbol(operand, source)
    analyzer._set_type(operand, source.type_)


@private
@typechecked
def call_operand_mode(operand: astx.AST) -> ParameterPassingKind:
    """
    title: Return the passing mode requested by an operand.
    parameters:
      operand: Call operand.
    returns: Explicit borrow mode or the ordinary passing mode.
    """
    return ParameterPassingKind.from_access(
        operand.access if isinstance(operand, astx.BorrowArgument) else None
    )


@private
@typechecked
def validate_call_operand_mode(
    diagnostics: DiagnosticBag,
    operand: astx.AST,
    expected: ParameterPassingKind,
    *,
    label: str,
) -> None:
    """
    title: Diagnose a mismatched parameter and operand access mode.
    parameters:
      diagnostics: Collected semantic diagnostics.
      operand: Call operand.
      expected: Parameter passing mode.
      label: Human-facing argument description.
    """
    if call_operand_mode(operand) is expected:
        return
    prefix = expected.borrow_prefix
    message = (
        f"{label} requires an explicit '{prefix}' borrow"
        if prefix
        else f"{label} does not accept a borrow"
    )
    diagnostics.add(
        message, node=operand, code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP
    )


@private
@typechecked
def mentions_list_binding(node: astx.AST, symbol: SemanticSymbol) -> bool:
    """
    title: Find an evaluated operand access to the same named storage.
    parameters:
      node: Operand or child expression.
      symbol: Borrowed list binding.
    returns: Whether the expression accesses the binding.
    """
    if isinstance(node, astx.Identifier):
        info = getattr(node, "semantic", None)
        return (
            isinstance(info, SemanticInfo)
            and info.resolved_symbol is not None
            and info.resolved_symbol.symbol_id == symbol.symbol_id
        )
    return any(
        mentions_list_binding(child, symbol)
        for child in lifecycle_children(node)
    )


@private
@typechecked
def list_loan_sources(
    node: astx.AST, *, include_shared: bool
) -> Iterator[SemanticSymbol]:
    """
    title: Find named storage loaned during one operand's evaluation.
    summary: Only exclusive nested loans can invalidate a sibling operand.
    parameters:
      node: Analyzed operand or descendant.
      include_shared: Whether the operand itself can hold a shared loan.
    returns: Storage bindings loaned in this operand.
    """
    if isinstance(node, astx.BorrowArgument):
        if include_shared or node.access is astx.BorrowAccess.exclusive:
            info = getattr(node, "semantic", None)
            if isinstance(info, SemanticInfo) and info.resolved_symbol:
                yield info.resolved_symbol
        return
    for child in lifecycle_children(node):
        yield from list_loan_sources(child, include_shared=False)


@private
@typechecked
def check_list_call_borrows(
    diagnostics: DiagnosticBag, arguments: tuple[astx.AST, ...]
) -> None:
    """
    title: Reject overlapping list storage across call operands.
    summary: Compatible shared loans can coexist. Reject a nested exclusive
      loan even in a call with no borrowed parameters because an earlier
      list or sequence operand may hold a view of the backing allocation.
    parameters:
      diagnostics: Collected semantic diagnostics.
      arguments: Explicit operands in source order, including a receiver.
    """
    if len(arguments) <= 1:
        return
    for index, operand in enumerate(arguments):
        for source in list_loan_sources(operand, include_shared=True):
            for other_index, other in enumerate(arguments):
                if other_index == index:
                    continue
                if (
                    isinstance(operand, astx.BorrowArgument)
                    and isinstance(other, astx.BorrowArgument)
                    and operand.access
                    is other.access
                    is astx.BorrowAccess.read_only
                ):
                    continue
                if mentions_list_binding(other, source):
                    diagnostics.add(
                        "call operands overlap a loan of "
                        f"list '{source.name}'",
                        node=other,
                        code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                    )
                    return
