"""
title: Variable-symbol helpers for semantic analysis.
summary: Build variable-like semantic symbols that need local-style qualified
  names.
"""

from __future__ import annotations

import astx

from public import public

from irx.analysis.module_interfaces import ModuleKey
from irx.analysis.module_symbols import qualified_local_name
from irx.analysis.resolved_nodes import SemanticSymbol
from irx.typecheck import typechecked


@public
@typechecked
def variable_symbol(
    symbol_id: str,
    module_key: ModuleKey,
    name: str,
    type_: astx.DataType,
    *,
    is_mutable: bool,
    declaration: astx.AST | None,
    kind: str = "variable",
) -> SemanticSymbol:
    """
    title: Create a variable-like symbol.
    parameters:
      symbol_id: Identifier for symbol.
      module_key: Canonical module identity.
      name: Name identifying the declaration or operation.
      type_: Type expression to process.
      is_mutable: Whether is mutable.
      declaration: Declaration being processed.
      kind: Kind of value or operation.
    returns: Created a variable-like symbol.
    """
    return SemanticSymbol(
        symbol_id=symbol_id,
        name=name,
        type_=type_,
        is_mutable=is_mutable,
        kind=kind,
        declaration=declaration,
        module_key=module_key,
        qualified_name=qualified_local_name(module_key, kind, name, symbol_id),
    )
