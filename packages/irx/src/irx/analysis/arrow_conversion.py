"""
title: Checked Arrow container conversions and reference ownership.
"""

from dataclasses import dataclass, replace

import astx

from public import private

from irx.analysis.class_lifecycle import class_ownership, lifecycle_error
from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.ownership import resource_ownership
from irx.analysis.resolved_nodes import (
    OwnershipKind,
    OwnershipTransferKind,
    ResolvedClassConstruction,
    ResourceKind,
    ResourceOwnership,
    SemanticClass,
    SemanticSymbol,
)
from irx.builtins.collections.dataframe import (
    DATAFRAME_SCHEMA_EXTRA,
    dataframe_record_batch_type_id,
    schema_from_type,
)
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked

ARROW_CONVERSION = "arrow_conversion"
ARROW_RESOURCES = frozenset({ResourceKind.DATAFRAME, ResourceKind.SERIES})


@private
@typechecked
@dataclass(frozen=True)
class ArrowConversion:
    """
    title: Resolved native conversion plan; no lookup remains for lowering.
    attributes:
      to_dataframe:
        type: bool
      class_:
        type: SemanticClass
      handle_index:
        type: int
      columns:
        type: tuple[tuple[str, int, bool], Ellipsis]
    """

    to_dataframe: bool
    class_: SemanticClass
    handle_index: int
    columns: tuple[tuple[str, int, bool], ...]


@private
@typechecked
def arrow_ownership(
    type_: astx.DataType,
    kind: OwnershipKind,
    symbol: str | None = None,
    transfer: OwnershipTransferKind = OwnershipTransferKind.NONE,
) -> ResourceOwnership:
    """
    title: Describe a native table or column reference.
    parameters:
      type_:
        type: astx.DataType
      kind:
        type: OwnershipKind
      symbol:
        type: str | None
      transfer:
        type: OwnershipTransferKind
    returns:
      type: ResourceOwnership
    """
    if not isinstance(type_, astx.DataFrameType | astx.SeriesType):
        raise TypeError("Arrow ownership requires a DataFrame or Series")
    return ResourceOwnership(
        ResourceKind.DATAFRAME
        if isinstance(type_, astx.DataFrameType)
        else ResourceKind.SERIES,
        kind,
        owner_symbol_id=symbol if kind is OwnershipKind.OWNED else None,
        source_symbol_id=symbol,
        transfer_kind=transfer,
    )


@private
@typechecked
def arrow_local(
    analyzer: SemanticAnalyzerCore,
    node: astx.VariableDeclaration | astx.InlineVariableDeclaration,
    symbol: SemanticSymbol,
) -> None:
    """
    title: Acquire an independently owned reference for a local binding.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.VariableDeclaration | astx.InlineVariableDeclaration
      symbol:
        type: SemanticSymbol
    """
    function = analyzer.context.current_function
    if (
        function is None
        or node.scope is not astx.ScopeKind.local
        or function.signature.metadata.get("generator") is not None
    ):
        lifecycle_error(
            analyzer,
            node,
            "owned Arrow globals and generator locals are unsupported",
        )
        return
    if node.value is None or isinstance(node.value, astx.Undefined):
        lifecycle_error(analyzer, node, "Arrow locals require an initializer")
        return
    ownership = resource_ownership(node.value)
    operation = OwnershipTransferKind.COPY
    if ownership is not None and ownership.kind is OwnershipKind.OWNED:
        operation = OwnershipTransferKind.MOVE
        analyzer._set_resource_ownership(
            node.value, replace(ownership, transfer_kind=operation)
        )
    analyzer._set_resource_ownership(
        node,
        arrow_ownership(
            node.type_, OwnershipKind.OWNED, symbol.symbol_id, operation
        ),
    )


@private
@typechecked
def resolve_arrow_cast(
    analyzer: SemanticAnalyzerCore, node: astx.Cast
) -> bool:
    """
    title: >-
      Resolve only host-registered RecordBatch conversions, not pointer casts.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.Cast
    returns:
      type: bool
    """
    info = analyzer._semantic(node)
    info.extras.pop(ARROW_CONVERSION, None)
    info.extras.pop(DATAFRAME_SCHEMA_EXTRA, None)
    analyzer._set_class(node, None)
    analyzer._set_class_construction(node, None)
    analyzer._set_resource_ownership(node, None)
    source = analyzer._expr_type(node.value)
    target = node.target_type
    to_dataframe = isinstance(target, astx.DataFrameType)
    dataframe: astx.DataFrameType
    if isinstance(target, astx.DataFrameType) and isinstance(
        source, astx.ClassType
    ):
        class_type = source
        dataframe = target
    elif isinstance(source, astx.DataFrameType) and isinstance(
        target, astx.ClassType
    ):
        class_type = target
        dataframe = source
    else:
        return False
    class_ = analyzer._resolve_class_from_type(
        class_type,
        node=node,
        unknown_message="conversion requires RecordBatch",
    )
    if (
        class_ is None
        or analyzer.session is None
        or not any(
            module.native_record_batch_class is class_.declaration
            for module in analyzer.session.modules.values()
        )
    ):
        return False
    layout = class_.layout
    initialization = class_.initialization
    fields = () if layout is None else layout.instance_fields
    valid = (
        not class_.bases
        and len(fields) == 1
        and initialization is not None
        and isinstance(fields[0].member.type_, astx.OpaqueHandleType)
        and fields[0].member.type_.handle_name == "IrxRbApiBatch"
        and fields[0].member.visibility is astx.VisibilityKind.private
    )
    if not valid:
        lifecycle_error(
            analyzer, node, "invalid native RecordBatch class layout"
        )
        return True
    assert initialization is not None
    function = analyzer.context.current_function
    if (
        function is None
        or function.signature.metadata.get("generator") is not None
    ):
        lifecycle_error(
            analyzer,
            node,
            "Arrow conversions require a non-generator function",
        )
        return True
    if to_dataframe and dataframe.row_count is not None:
        lifecycle_error(
            analyzer,
            node,
            "Arrow conversions do not support fixed row-count types",
        )
        return True
    if any(
        phase.initializer is not None
        and phase.initializer.prototype.args.nodes
        for phase in initialization.phases
    ):
        lifecycle_error(
            analyzer,
            node,
            "native RecordBatch requires a zero-argument initializer",
        )
        return True
    columns = dataframe.columns
    if not columns or any(
        dataframe_record_batch_type_id(c.type_) is None for c in columns
    ):
        analyzer.context.diagnostics.add(
            "DataFrame conversion requires a static nonempty schema of "
            "numeric, bool, string or temporal columns; "
            "keep other data as a RecordBatch",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return True
    analyzer._semantic(node).extras[ARROW_CONVERSION] = ArrowConversion(
        to_dataframe,
        class_,
        fields[0].storage_index,
        tuple(
            (
                c.name,
                int(dataframe_record_batch_type_id(c.type_) or 0),
                c.nullable,
            )
            for c in columns
        ),
    )
    analyzer._set_type(node, target)
    if to_dataframe:
        analyzer._semantic(node).extras[DATAFRAME_SCHEMA_EXTRA] = (
            schema_from_type(dataframe)
        )
        analyzer._set_resource_ownership(
            node, arrow_ownership(dataframe, OwnershipKind.OWNED)
        )
    else:
        analyzer._set_class(node, class_)
        analyzer._set_class_construction(
            node, ResolvedClassConstruction(class_, initialization)
        )
        analyzer._set_resource_ownership(
            node, class_ownership(OwnershipKind.OWNED)
        )
    return True


@private
@typechecked
def resolve_arrow_store(
    analyzer: SemanticAnalyzerCore, node: astx.BinaryOp, symbol: SemanticSymbol
) -> bool:
    """
    title: Resolve an owned Arrow local replacement without losing aliases.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.BinaryOp
      symbol:
        type: SemanticSymbol
    returns:
      type: bool
    """
    type_ = analyzer._expr_type(node.lhs)
    if not isinstance(type_, astx.DataFrameType | astx.SeriesType):
        return False
    if not isinstance(node.lhs, astx.Identifier):
        lifecycle_error(
            analyzer, node, "Arrow references require local storage"
        )
        return True
    ownership = resource_ownership(node.rhs)
    transfer = OwnershipTransferKind.COPY
    if ownership is not None and ownership.kind is OwnershipKind.OWNED:
        transfer = OwnershipTransferKind.MOVE
        analyzer._set_resource_ownership(
            node.rhs, replace(ownership, transfer_kind=transfer)
        )
    analyzer._semantic(node).resolved_resource_store = arrow_ownership(
        type_, OwnershipKind.OWNED, symbol.symbol_id, transfer
    )
    analyzer._set_resource_ownership(
        node, arrow_ownership(type_, OwnershipKind.BORROWED)
    )
    return True


@private
@typechecked
def contains_arrow(type_: astx.DataType | None) -> bool:
    """
    title: Detect Arrow ownership hidden in unsupported aggregate storage.
    parameters:
      type_:
        type: astx.DataType | None
    returns:
      type: bool
    """
    if isinstance(type_, astx.DataFrameType | astx.SeriesType):
        return True
    for name in (
        "element_types",
        "members",
        "element_type",
        "key_type",
        "value_type",
        "yield_type",
        "pointee_type",
        "bound",
    ):
        value = getattr(type_, name, None)
        if isinstance(value, astx.DataType) and contains_arrow(value):
            return True
        if isinstance(value, (tuple, list)) and any(
            isinstance(item, astx.DataType) and contains_arrow(item)
            for item in value
        ):
            return True
    return False
