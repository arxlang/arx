"""
title: Consistent parameter ownership in ordinary and specialized bodies.
"""

import astx

from public import private

from irx.analysis.arrow_conversion import arrow_ownership
from irx.analysis.class_lifecycle import class_ownership
from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.ownership import (
    list_resource_ownership,
    string_resource_ownership,
)
from irx.analysis.resolved_nodes import (
    OwnershipKind,
    OwnershipTransferKind,
    ResourceKind,
    ResourceOwnership,
    SemanticSymbol,
)
from irx.analysis.types import is_string_type
from irx.typecheck import typechecked


@private
@typechecked
def resolve_parameter_ownership(
    analyzer: SemanticAnalyzerCore,
    arg_node: astx.Argument,
    arg_symbol: SemanticSymbol,
) -> None:
    """
    title: Attach the same borrow or retained-copy contract to every parameter.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      arg_node:
        type: astx.Argument
      arg_symbol:
        type: SemanticSymbol
    """
    analyzer._semantic(arg_node).resource_ownership = None
    if isinstance(arg_symbol.type_, astx.ClassType):
        analyzer._set_resource_ownership(
            arg_node,
            class_ownership(
                OwnershipKind.OWNED,
                symbol=arg_symbol.symbol_id,
                transfer=OwnershipTransferKind.COPY,
            ),
        )
    elif isinstance(arg_symbol.type_, astx.DataFrameType | astx.SeriesType):
        analyzer._set_resource_ownership(
            arg_node,
            arrow_ownership(
                arg_symbol.type_,
                OwnershipKind.OWNED,
                arg_symbol.symbol_id,
                OwnershipTransferKind.COPY,
            ),
        )
    elif isinstance(arg_symbol.type_, astx.GeneratorType):
        analyzer._set_resource_ownership(
            arg_node,
            ResourceOwnership(
                ResourceKind.GENERATOR,
                OwnershipKind.BORROWED,
                source_symbol_id=arg_symbol.symbol_id,
                transfer_kind=OwnershipTransferKind.BORROW,
            ),
        )
    elif isinstance(arg_symbol.type_, astx.ListType):
        analyzer._set_resource_ownership(
            arg_node,
            list_resource_ownership(
                OwnershipKind.BORROWED,
                source_symbol_id=arg_symbol.symbol_id,
                transfer_kind=OwnershipTransferKind.BORROW,
            ),
        )
    elif is_string_type(arg_symbol.type_):
        analyzer._set_resource_ownership(
            arg_node,
            string_resource_ownership(
                OwnershipKind.BORROWED,
                source_symbol_id=arg_symbol.symbol_id,
                transfer_kind=OwnershipTransferKind.BORROW,
            ),
        )
