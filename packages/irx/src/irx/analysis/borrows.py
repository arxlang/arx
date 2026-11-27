"""
title: Validate lexical and call-scoped access to borrowed places.
"""

from collections.abc import Iterator

import astx

from public import private

from irx.analysis.class_lifecycle import lifecycle_children
from irx.analysis.context import SemanticContext
from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.numeric_literals import numeric_constant
from irx.analysis.ownership import symbol_resource_ownership
from irx.analysis.resolved_nodes import (
    FailedInferenceType,
    OwnershipKind,
    ParameterPassingKind,
    ResolvedBorrow,
    ResolvedBorrowPlace,
    SemanticInfo,
    SemanticSymbol,
)
from irx.analysis.types import (
    bit_width,
    is_boolean_type,
    is_integer_type,
    is_numeric_type,
)
from irx.builtins.collections.list import list_element_type
from irx.diagnostics import DiagnosticBag, DiagnosticCodes
from irx.typecheck import typechecked

LIST_INDEX_WIDTH = 64


@private
@typechecked
def analyze_list_index_base(
    analyzer: SemanticAnalyzerCore, base: astx.AST
) -> SemanticSymbol | None:
    """
    title: Resolve a list receiver whose element is checked separately.
    parameters:
      analyzer: Active semantic analyzer.
      base: Indexed receiver expression.
    returns: Named list storage, if the receiver designates it directly.
    """
    context = analyzer.context
    symbol = (
        context.scopes.resolve(base.name)
        if isinstance(base, astx.Identifier)
        else None
    )
    if not isinstance(base, astx.Identifier) or not (
        symbol is not None and isinstance(symbol.type_, astx.ListType)
    ):
        analyzer.visit(base)
        return None
    previous = context.list_index_base
    context.list_index_base = base
    try:
        analyzer.visit(base)
    finally:
        context.list_index_base = previous
    return symbol


@private
@typechecked
def known_list_position(index: astx.AST | None) -> int | None:
    """
    title: Recognize a literal index that reaches the list ABI unchanged.
    parameters:
      index: Analyzed index expression, if any.
    returns: A known nonnegative signed 64-bit position or unknown overlap.
    """
    value = (
        numeric_constant(index) if isinstance(index, astx.Literal) else None
    )
    upper = 1 << (LIST_INDEX_WIDTH - 1)
    return value if isinstance(value, int) and 0 <= value < upper else None


@private
@typechecked
def conflicting_borrow(
    context: SemanticContext,
    root: SemanticSymbol,
    *,
    write: bool,
    position: int | None,
    retarget: SemanticSymbol | None = None,
) -> ResolvedBorrow | None:
    """
    title: Find a live loan of storage that may overlap the requested access.
    parameters:
      context: Active semantic context.
      root: Binding that owns or pins the storage.
      write: Whether the new access needs exclusive permission.
      position: Known index, or unknown or whole-place access.
      retarget: Existing loan released after the new place is prepared.
    returns: First conflicting loan, if any.
    """
    for scope in context.scopes.function_scopes:
        for borrow in scope.borrows.values():
            if borrow.target is retarget or borrow.place.root is not root:
                continue
            existing = borrow.place.constant_index
            if position is not None and existing is not None:
                if position != existing:
                    continue
            if write or borrow.access is astx.BorrowAccess.exclusive:
                return borrow
    return None


@private
@typechecked
def resolve_borrow_source(
    analyzer: SemanticAnalyzerCore,
    place: astx.Expr,
    access: astx.BorrowAccess,
    *,
    retarget: SemanticSymbol | None = None,
) -> ResolvedBorrowPlace | None:
    """
    title: Validate a local scalar place before installing its lexical borrow.
    parameters:
      analyzer: Active semantic analyzer.
      place: Expression designating the original storage.
      access: Access requested by the new borrow.
      retarget: Optional existing borrower whose old loan is ending.
    returns: Resolved place if the requested access is available.
    """
    context = analyzer.context
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
    if isinstance(place, astx.Identifier):
        root = place
        index = None
    elif isinstance(place, astx.ListIndex) and isinstance(
        place.base, astx.Identifier
    ):
        root = place.base
        index = place.index
    elif (
        isinstance(place, astx.SubscriptExpr)
        and not place.is_slice
        and isinstance(place.value, astx.Identifier)
    ):
        root = place.value
        index = place.index
    else:
        context.diagnostics.add(
            "a local borrow requires a scalar variable or named list element",
            node=place,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return None
    source = context.scopes.resolve(root.name)
    if source is None:
        context.diagnostics.add(
            f"cannot resolve name '{root.name}'",
            node=root,
            code=DiagnosticCodes.SEMANTIC_UNRESOLVED_NAME,
        )
        return None
    if not any(scope.symbols.get(root.name) is source for scope in scopes):
        context.diagnostics.add(
            "a local borrow requires storage declared in this function",
            node=root,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return None
    if index is not None:
        resolved = resolve_list_element_place(analyzer, root, source, index)
        if resolved is None:
            return None
    elif source.kind != "variable" or not (
        isinstance(
            source.declaration,
            (astx.VariableDeclaration, astx.InlineVariableDeclaration),
        )
        and (is_numeric_type(source.type_) or is_boolean_type(source.type_))
    ):
        context.diagnostics.add(
            "a local borrow requires an owning numeric or Boolean variable",
            node=place,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return None
    else:
        resolved = ResolvedBorrowPlace(source, source.type_)
        analyzer._set_symbol(root, source)
    exclusive = access is astx.BorrowAccess.exclusive
    if exclusive and not check_borrow_source_writable(
        context, resolved, place
    ):
        return None
    conflict = conflicting_borrow(
        context,
        source,
        write=exclusive,
        position=resolved.constant_index,
        retarget=retarget,
    )
    if conflict is not None:
        context.diagnostics.add(
            f"cannot borrow '{source.name}' while "
            f"'{conflict.target.name}' has a conflicting borrow",
            node=place,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return None
    return resolved


@private
@typechecked
def resolve_list_element_place(
    analyzer: SemanticAnalyzerCore,
    base: astx.Identifier,
    source: SemanticSymbol,
    index: astx.AST,
) -> ResolvedBorrowPlace | None:
    """
    title: Resolve a list projection with stable storage and an exact type.
    parameters:
      analyzer: Active semantic analyzer.
      base: Identifier naming the list.
      source: Resolved binding of the identifier.
      index: Index expression selecting an element.
    returns: Validated element place.
    """
    ownership = symbol_resource_ownership(source)
    element = list_element_type(source.type_)
    if element is None or not (
        is_numeric_type(element) or is_boolean_type(element)
    ):
        analyzer.context.diagnostics.add(
            "an element borrow requires a list of numeric or Boolean values",
            node=base,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return None
    if not (
        (ownership is not None and ownership.kind is OwnershipKind.OWNED)
        or (
            isinstance(source.declaration, astx.Argument)
            and source.declaration.borrow_access is not None
        )
    ):
        analyzer.context.diagnostics.add(
            "an element borrow requires an owned local list or list borrow "
            "parameter",
            node=base,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return None
    analyze_list_index_base(analyzer, base)
    analyzer.visit(index)
    index_type = analyzer._expr_type(index)
    if isinstance(index_type, FailedInferenceType):
        return None
    if (
        not is_integer_type(index_type)
        or bit_width(index_type) > LIST_INDEX_WIDTH
    ):
        analyzer.context.diagnostics.add(
            "a list element borrow requires an integer index up to 64 bits",
            node=index,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return None
    return ResolvedBorrowPlace(
        source, element, index, known_list_position(index)
    )


@private
@typechecked
def check_borrow_source_writable(
    context: SemanticContext, place: ResolvedBorrowPlace, node: astx.AST
) -> bool:
    """
    title: Verify that the original storage grants mutable access.
    parameters:
      context: Active semantic context.
      place: Validated source place.
      node: Source syntax for diagnostics.
    returns: Whether the source is writable and free of active iteration.
    """
    root = place.root
    declaration = root.declaration
    if isinstance(declaration, astx.Argument):
        writable = declaration.borrow_access is astx.BorrowAccess.exclusive
        message = f"cannot exclusively borrow through read-only '{root.name}'"
    else:
        writable = root.is_mutable
        message = f"cannot exclusively borrow constant '{root.name}'"
    if writable and root.symbol_id in context.active_list_iteration_owners:
        writable = False
        message = f"cannot exclusively borrow '{root.name}' during iteration"
    if not writable:
        context.diagnostics.add(
            message, node=node, code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP
        )
    return writable


@private
@typechecked
def check_borrow_access(
    context: SemanticContext,
    symbol: SemanticSymbol,
    node: astx.AST,
    *,
    write: bool = False,
    read_checked: bool = False,
    index: astx.AST | None = None,
) -> bool:
    """
    title: Enforce exclusive access and forbid writes through shared borrows.
    parameters:
      context: Active semantic context.
      symbol: Binding being read or written.
      node: Syntax that accesses the binding.
      write: Whether the access can mutate storage.
      read_checked: Whether the same target already performed a read check.
      index: Evaluated list projection index, if this is an element access.
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
    borrow = conflicting_borrow(
        context, symbol, write=write, position=known_list_position(index)
    )
    if borrow is None:
        return True
    if not (borrow.access is astx.BorrowAccess.exclusive and read_checked):
        action = "write" if write else "read"
        context.diagnostics.add(
            f"cannot {action} '{symbol.name}' while it is borrowed "
            f"by '{borrow.target.name}'",
            node=node,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
    return False


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
    if (
        operand.access is astx.BorrowAccess.exclusive
        and not check_borrow_access(
            context, symbol, operand, write=True, read_checked=True
        )
    ):
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
