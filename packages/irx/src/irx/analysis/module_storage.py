"""
title: Static scalar initialization and module storage contracts.
"""

import astx

from public import private

from irx.analysis.float_literals import rounded_float
from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.numeric_literals import numeric_constant
from irx.analysis.numeric_policy import FLOAT_PRECISIONS, integer_bounds
from irx.analysis.resolved_nodes import ResolvedModuleStorage, SemanticSymbol
from irx.analysis.types import is_assignable
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@private
@typechecked
def resolve_module_storage(
    analyzer: SemanticAnalyzerCore,
    node: astx.VariableDeclaration | astx.InlineVariableDeclaration,
    symbol: SemanticSymbol,
) -> None:
    """
    title: Validate module scalar literals before authorizing static storage.
    summary: >-
      Ordinary mutable scalars default to zero; nullable scalars default to
      none. Constants require an initializer. Unsupported module storage and
      nonliteral initializers fail in analysis, including unused declarations.
      Clear old plans when a declaration is reanalyzed or becomes a local.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.VariableDeclaration | astx.InlineVariableDeclaration
      symbol:
        type: SemanticSymbol
    """
    info = analyzer._semantic(node)
    info.module_storage = None
    if (
        analyzer.context.current_function is not None
        or analyzer.context.current_class is not None
    ):
        return
    module = getattr(analyzer, "_current_ast_module", None)
    if not isinstance(module, astx.Module):
        # An independently analyzed AST fragment is not a module declaration.
        return
    if not any(declaration is node for declaration in module.nodes):
        analyzer.context.diagnostics.add(
            f"module variable '{node.name}' must be declared at module "
            "top level, not in a conditional block",
            node=node,
            code=DiagnosticCodes.SEMANTIC_UNSUPPORTED_NODE,
        )
        return
    nullable = isinstance(symbol.type_, astx.NullableType)
    scalar = (
        symbol.type_.value_type
        if isinstance(symbol.type_, astx.NullableType)
        else symbol.type_
    )
    if not (
        isinstance(scalar, astx.Boolean)
        or integer_bounds(scalar) is not None
        or type(scalar) in FLOAT_PRECISIONS
    ):
        analyzer.context.diagnostics.add(
            f"module-level variable '{node.name}' requires numeric/Boolean "
            "scalar storage; other module storage is unsupported",
            node=node,
            code=DiagnosticCodes.SEMANTIC_UNSUPPORTED_NODE,
            hint="move the declaration into a function",
        )
        return

    value = node.value
    missing = value is None or isinstance(value, astx.Undefined)
    if missing and not symbol.is_mutable:
        analyzer.context.diagnostics.add(
            f"module constant '{node.name}' requires a literal initializer",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return
    if isinstance(value, astx.Cast) and isinstance(
        value.value, astx.LiteralNone
    ):
        value = value.value
    if missing or (nullable and isinstance(value, astx.LiteralNone)):
        default: int | float | bool | None = 0
        if nullable:
            default = None
        elif isinstance(scalar, astx.Boolean):
            default = False
        elif type(scalar) in FLOAT_PRECISIONS:
            default = 0.0
        info.module_storage = ResolvedModuleStorage(symbol, default)
        return
    if not isinstance(value, astx.Literal):
        analyzer.context.diagnostics.add(
            f"module variable '{node.name}' requires a numeric/Boolean "
            "literal or nullable none initializer; runtime initialization "
            "is unsupported",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            hint="perform runtime initialization inside a function",
        )
        return
    if not is_assignable(symbol.type_, analyzer._expr_type(value)):
        return
    if isinstance(value, astx.LiteralBoolean):
        info.module_storage = ResolvedModuleStorage(symbol, value.value)
        return
    constant = numeric_constant(value)
    if constant is None:
        return
    if type(scalar) in FLOAT_PRECISIONS:
        constant = rounded_float(constant, scalar)
    info.module_storage = ResolvedModuleStorage(symbol, constant)
