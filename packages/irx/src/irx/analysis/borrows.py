"""
title: Validate lexical and call-scoped access to borrowed places.
"""

from collections.abc import Iterator

import astx

from public import private

from irx.analysis.class_lifecycle import lifecycle_children
from irx.analysis.context import BorrowAccessCheck, SemanticContext
from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.numeric_literals import numeric_constant
from irx.analysis.ownership import symbol_resource_ownership
from irx.analysis.resolved_nodes import (
    FailedInferenceType,
    OwnershipKind,
    ParameterPassingKind,
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
def named_list_projection(
    node: astx.AST,
) -> tuple[astx.Identifier, astx.AST] | None:
    """
    title: Recognize a single-element projection of a named list candidate.
    parameters:
      node: Source expression.
    returns: Named receiver and index, if present.
    """
    if isinstance(node, astx.ListIndex) and isinstance(
        node.base, astx.Identifier
    ):
        return node.base, node.index
    if (
        isinstance(node, astx.SubscriptExpr)
        and not node.is_slice
        and isinstance(node.value, astx.Identifier)
    ):
        return node.value, node.index
    return None


@private
@typechecked
def positions_may_overlap(left: int | None, right: int | None) -> bool:
    """
    title: Treat a whole place or unknown element as overlapping any position.
    parameters:
      left: First statically known position, if any.
      right: Second statically known position, if any.
    returns: Whether the positions can refer to the same storage.
    """
    return left is None or right is None or left == right


@private
@typechecked
def record_borrow_access(
    context: SemanticContext,
    root: SemanticSymbol,
    node: astx.AST,
    *,
    write: bool,
    position: int | None,
    read_checked: bool = False,
    formation: bool = False,
    retarget: SemanticSymbol | None = None,
) -> None:
    """
    title: Record an access wherever a lexical loan may be live.
    parameters:
      context: Active semantic context.
      root: Binding that owns or pins the storage.
      node: Syntax designating the accessed place.
      write: Whether the new access needs exclusive permission.
      position: Known index, or unknown or whole-place access.
      read_checked: Whether the same target already checked a read.
      formation: Whether this access creates a borrow.
      retarget: Existing loan released after the new place is prepared.
    """
    if any(scope.borrows for scope in context.scopes.function_scopes):
        context.borrow_accesses.setdefault(id(node), []).append(
            BorrowAccessCheck(
                node,
                root,
                position,
                write,
                read_checked=read_checked,
                formation=formation,
                retarget=retarget,
            )
        )


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
    title: Validate a local scalar place before creating a borrow.
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
    projection = named_list_projection(place)
    field = place if isinstance(place, astx.FieldAccess) else None
    if field is not None:
        receiver = field.value
        if not isinstance(receiver, astx.Identifier):
            context.diagnostics.add(
                "a class field borrow requires a named receiver",
                node=receiver,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return None
        root, index = receiver, None
    elif isinstance(place, astx.Identifier):
        root = place
        index = None
    elif projection is not None:
        root, index = projection
    else:
        context.diagnostics.add(
            "a local borrow requires a scalar variable or named list element, "
            "or a const scalar field",
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
    depth = next(
        (
            index
            for index, scope in enumerate(scopes)
            if scope.symbols.get(root.name) is source
        ),
        None,
    )
    if depth is None:
        context.diagnostics.add(
            "a local borrow requires storage declared in this function",
            node=root,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return None
    if retarget is not None and not any(
        scope.symbols.get(retarget.name) is retarget
        for scope in scopes[: depth + 1]
    ):
        context.diagnostics.add(
            f"'{source.name}' must outlive borrow binding '{retarget.name}'",
            node=root,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return None
    if field is not None:
        resolved = resolve_const_field_place(analyzer, field, source, access)
        if resolved is None:
            return None
    elif index is not None:
        resolved = resolve_list_element_place(analyzer, root, source, index)
        if resolved is None:
            return None
    elif not (
        isinstance(
            source.declaration,
            (
                astx.VariableDeclaration,
                astx.InlineVariableDeclaration,
                astx.Argument,
            ),
        )
        and source.kind in {"variable", "argument"}
        and (is_numeric_type(source.type_) or is_boolean_type(source.type_))
    ):
        context.diagnostics.add(
            "a scalar borrow requires a numeric or Boolean variable "
            "or parameter",
            node=place,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return None
    else:
        resolved = ResolvedBorrowPlace(source, source.type_)
        analyzer._set_symbol(root, source)
        analyzer._set_type(root, source.type_)
    exclusive = access is astx.BorrowAccess.exclusive
    if exclusive and not check_borrow_source_writable(
        context, resolved, place
    ):
        return None
    record_borrow_access(
        context,
        source,
        place,
        write=exclusive,
        position=resolved.constant_index,
        formation=True,
        retarget=retarget,
    )
    return resolved


@private
@typechecked
def resolve_const_field_place(
    analyzer: SemanticAnalyzerCore,
    field: astx.FieldAccess,
    root: SemanticSymbol,
    access: astx.BorrowAccess,
) -> ResolvedBorrowPlace | None:
    """
    title: Borrow an immutable scalar field through a live class binding.
    parameters:
      analyzer: Active semantic analyzer.
      field: Instance field syntax.
      root: Resolved receiver symbol.
      access: Requested loan mode.
    returns: Validated immutable field address plan.
    """
    analyzer.visit(field)
    field_type = analyzer._expr_type(field)
    if field_type is None or isinstance(field_type, FailedInferenceType):
        return None
    resolved = analyzer._semantic(field).resolved_class_field_access
    if (
        resolved is None
        or resolved.member.is_mutable
        or not (is_numeric_type(field_type) or is_boolean_type(field_type))
    ):
        message = (
            "a field borrow requires a const numeric or Boolean instance field"
        )
    elif analyzer._semantic(field.value).lifecycle_self:
        message = "a lifecycle hook cannot borrow a field of self"
    elif access is astx.BorrowAccess.exclusive:
        message = "const instance fields only support read-only borrows"
    else:
        return ResolvedBorrowPlace(root, field_type, field=field)
    analyzer.context.diagnostics.add(
        message, node=field, code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP
    )
    return None


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
    if (
        isinstance(declaration, astx.Argument)
        and declaration.borrow_access is not None
    ):
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
    title: Check borrow mode and register access for ownership flow analysis.
    parameters:
      context: Active semantic context.
      symbol: Binding being read or written.
      node: Syntax that accesses the binding.
      write: Whether the access can mutate storage.
      read_checked: Whether the same target already performed a read check.
      index: Evaluated list projection index, if this is an element access.
    returns: Whether the access is permitted by the binding's declared mode.
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
    record_borrow_access(
        context,
        symbol,
        node,
        write=write,
        position=known_list_position(index),
        read_checked=read_checked,
    )
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
def analyze_call_borrow_operand(
    analyzer: SemanticAnalyzerCore, operand: astx.BorrowArgument
) -> None:
    """
    title: Resolve the storage of a borrow at a checked call boundary.
    parameters:
      analyzer: Active semantic analyzer.
      operand: Explicit borrow operand.
    """
    info = analyzer._semantic(operand)
    info.call_borrow_place = None
    info.resolved_symbol = None
    source = operand.source
    symbol = (
        analyzer.context.scopes.resolve(source.name)
        if isinstance(source, astx.Identifier)
        else None
    )
    if symbol is not None and isinstance(symbol.type_, astx.ListType):
        analyzer.visit(source)
        root = resolve_list_call_borrow(analyzer.context, operand)
        place = (
            ResolvedBorrowPlace(root, root.type_) if root is not None else None
        )
    elif isinstance(
        source,
        (
            astx.Identifier,
            astx.ListIndex,
            astx.SubscriptExpr,
            astx.FieldAccess,
        ),
    ):
        place = resolve_borrow_source(analyzer, source, operand.access)
    else:
        analyzer.context.diagnostics.add(
            "a borrow requires a named local list, scalar variable, "
            "list element, or const scalar field",
            node=operand,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        place = None
    if place is None:
        analyzer._set_type(operand, FailedInferenceType())
        return
    info.call_borrow_place = place
    if place.index is None and place.field is None:
        analyzer._set_symbol(operand, place.root)
    analyzer._set_type(operand, place.type_)


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
def overlaps_call_operand(
    node: astx.AST,
    place: ResolvedBorrowPlace,
    *,
    compatible_shared_loan: bool = False,
) -> bool:
    """
    title: Detect an operand access that might overlap an active call loan.
    parameters:
      node: Operand or evaluated child expression.
      place: Source place of the loan being checked.
      compatible_shared_loan: Whether the direct operand has a shared loan.
    returns: Whether an access might overlap the loan.
    """
    info = getattr(node, "semantic", None)
    if isinstance(node, astx.BorrowArgument) and isinstance(
        info, SemanticInfo
    ):
        other = info.call_borrow_place
        if other is not None:
            return (
                not compatible_shared_loan
                and other.root.symbol_id == place.root.symbol_id
                and positions_may_overlap(
                    place.constant_index, other.constant_index
                )
            ) or (
                other.index is not None
                and overlaps_call_operand(other.index, place)
            )
    if isinstance(node, astx.Identifier):
        # Reading a class handle cannot mutate its immutable field. Rebinding
        # the receiver is checked below as an assignment to its root.
        return (
            place.field is None
            and isinstance(info, SemanticInfo)
            and info.resolved_symbol is not None
            and info.resolved_symbol.symbol_id == place.root.symbol_id
        )
    projection = named_list_projection(node)
    if projection is not None:
        base, index = projection
        if overlaps_call_operand(base, place):
            return positions_may_overlap(
                place.constant_index, known_list_position(index)
            ) or overlaps_call_operand(index, place)
    if isinstance(info, SemanticInfo) and (
        isinstance(node, astx.VariableAssignment)
        or (isinstance(node, astx.BinaryOp) and node.op_code == "=")
    ):
        assignment = info.resolved_assignment
        if (
            assignment is not None
            and assignment.target.symbol_id == place.root.symbol_id
        ):
            return True
    return any(
        overlaps_call_operand(child, place)
        for child in lifecycle_children(node)
    )


@private
@typechecked
def call_operand_loans(
    node: astx.AST, *, direct: bool
) -> Iterator[tuple[ResolvedBorrowPlace, astx.BorrowAccess]]:
    """
    title: Find call loans that can conflict across operand evaluation.
    summary: A nested exclusive loan can mutate a location or invalidate
      a view held by a sibling operand. A direct loan lasts through the call.
    parameters:
      node: Analyzed operand or descendant.
      direct: Whether the node is a direct operand of the call being checked.
    returns: Potentially conflicting places and loan modes.
    """
    if isinstance(node, astx.BorrowArgument):
        info = getattr(node, "semantic", None)
        if (
            isinstance(info, SemanticInfo)
            and info.call_borrow_place is not None
        ):
            if direct or node.access is astx.BorrowAccess.exclusive:
                yield info.call_borrow_place, node.access
    for child in lifecycle_children(node):
        yield from call_operand_loans(child, direct=False)


@private
@typechecked
def check_call_borrows(
    diagnostics: DiagnosticBag, arguments: tuple[astx.AST, ...]
) -> None:
    """
    title: Reject conflicting access to borrowed places across call operands.
    summary: The receiver precedes the explicit arguments. Compatible direct
      shared loans can overlap. A nested exclusive loan can invalidate an
      earlier operand, including a list-backed sequence view.
    parameters:
      diagnostics: Collected semantic diagnostics.
      arguments: Operands in source order, including any receiver.
    """
    if len(arguments) <= 1:
        return
    for index, operand in enumerate(arguments):
        for place, access in call_operand_loans(operand, direct=True):
            for other_index, other in enumerate(arguments):
                if other_index == index:
                    continue
                compatible_shared_loan = (
                    isinstance(operand, astx.BorrowArgument)
                    and isinstance(other, astx.BorrowArgument)
                    and access is other.access is astx.BorrowAccess.read_only
                )
                if overlaps_call_operand(
                    other, place, compatible_shared_loan=compatible_shared_loan
                ):
                    kind = (
                        "list"
                        if isinstance(place.root.type_, astx.ListType)
                        else "scalar"
                    )
                    name = place.root.name
                    if place.field is not None:
                        kind = "field"
                        name += f".{place.field.field_name}"
                    diagnostics.add(
                        f"call operands overlap a loan of {kind} '{name}'",
                        node=other,
                        code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                    )
                    return
