# mypy: disable-error-code=no-redef
# mypy: disable-error-code=untyped-decorator
"""
title: Resolve explicit nullable validity and checked payload operations.
"""

from __future__ import annotations

from dataclasses import replace

import astx

from public import public

from irx.analysis.handlers.base import (
    SemanticAnalyzerCore,
    SemanticVisitorMixinBase,
)
from irx.analysis.normalization import normalize_flags
from irx.analysis.nullability import ResolvedNullableQuery, nullable_diagnostic
from irx.analysis.nullable_operators import resolve_nullable_operator
from irx.analysis.ownership import resource_ownership
from irx.analysis.resolved_nodes import OwnershipKind
from irx.analysis.types import clone_type
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@public
@typechecked
def analyze_nullable_operator(
    analyzer: SemanticAnalyzerCore, node: astx.BinaryOp | astx.UnaryOp
) -> None:
    """
    title: Attach a closed nullable operator contract or diagnose its operands.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.BinaryOp | astx.UnaryOp
    """
    lhs = analyzer._expr_type(
        node.lhs if isinstance(node, astx.BinaryOp) else node.operand
    )
    rhs = (
        analyzer._expr_type(node.rhs)
        if isinstance(node, astx.BinaryOp)
        else None
    )
    resolved = (
        resolve_nullable_operator(node.op_code, lhs, rhs)
        if lhs is not None
        else None
    )
    flags = normalize_flags(node, lhs_type=lhs, rhs_type=rhs)
    if (
        flags.fast_math
        or flags.fma
        or flags.fma_rhs is not None
        or getattr(node, "unsigned", None) is not None
    ):
        analyzer.context.diagnostics.add(
            "nullable operators do not accept explicit arithmetic flags",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        analyzer._set_type(node, None)
        return
    if resolved is None:
        analyzer.context.diagnostics.add(
            "nullable operator requires compatible primitive operands; "
            "use is_null for null tests and assignment for mutation",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        analyzer._set_type(node, None)
        return
    analyzer._semantic(node).resolved_nullable_operator = resolved
    analyzer._set_type(node, astx.NullableType(resolved.payload_type))


@typechecked
class NullableVisitorMixin(SemanticVisitorMixinBase):
    """
    title: Keep payload validity requirements in semantic analysis.
    """

    @SemanticAnalyzerCore.visit.dispatch  # type: ignore[attr-defined]
    def visit(self, node: astx.NullableQuery) -> None:
        """
        title: Resolve a query on one explicitly typed nullable operand.
        parameters:
          node:
            type: astx.NullableQuery
        """
        self.visit(node.operand)
        if isinstance(node.operand, astx.Identifier):
            info = self._semantic(node.operand)
            if info.nullable_refined and info.resolved_symbol is not None:
                # Validity queries inspect storage even in a refined region.
                info.nullable_refined = False
                self._set_type(node.operand, info.resolved_symbol.type_)
        operand_type = self._expr_type(node.operand)
        error = (
            nullable_diagnostic(operand_type)
            if isinstance(operand_type, astx.NullableType)
            else f"{node.operation.value} requires a typed nullable value"
        )
        if error is not None:
            self.context.diagnostics.add(
                error, node=node, code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH
            )
            self._set_type(node, None)
            return
        assert isinstance(operand_type, astx.NullableType)
        payload = clone_type(operand_type.payload_type)
        self._semantic(node).resolved_nullable_query = ResolvedNullableQuery(
            node.operation, payload
        )
        self._set_type(
            node,
            payload
            if node.operation is astx.NullableOperation.EXPECT_VALID
            else astx.Boolean(),
        )
        ownership = resource_ownership(node.operand)
        if (
            node.operation is astx.NullableOperation.EXPECT_VALID
            and ownership is not None
        ):
            self._set_resource_ownership(
                node,
                replace(
                    ownership,
                    kind=OwnershipKind.BORROWED,
                    nullable_aggregate=False,
                ),
            )
