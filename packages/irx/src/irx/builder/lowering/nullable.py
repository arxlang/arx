# mypy: disable-error-code=no-redef
# mypy: disable-error-code=untyped-decorator
"""
title: Lower language-owned nullable aggregates without Arrow C++ layouts.
"""

from __future__ import annotations

import astx

from llvmlite import ir

from irx.analysis.nullability import managed_nullable
from irx.analysis.resolved_nodes import SemanticInfo
from irx.builder.core import VisitorCore
from irx.builder.diagnostics import raise_lowering_internal_error
from irx.builder.protocols import VisitorMixinBase
from irx.builder.runtime import safe_pop
from irx.typecheck import typechecked


@typechecked
class NullableLoweringMixin(VisitorMixinBase):
    """
    title: Consume resolved query metadata and guard every payload unwrap.
    """

    @VisitorCore.visit.dispatch  # type: ignore[attr-defined]
    def visit(self, node: astx.NullableQuery) -> None:
        """
        title: Inspect validity before extracting a requested payload.
        parameters:
          node:
            type: astx.NullableQuery
        """
        semantic = getattr(node, "semantic", None)
        if (
            not isinstance(semantic, SemanticInfo)
            or semantic.resolved_nullable_query is None
        ):
            raise_lowering_internal_error(
                "missing resolved nullable query", node=node
            )
        resolved = semantic.resolved_nullable_query
        self.visit_child(node.operand)
        value = safe_pop(self.result_stack)
        if value is None:
            raise_lowering_internal_error(
                "nullable operand produced no aggregate", node=node.operand
            )
        builder = self._llvm.ir_builder
        pointer_payload = managed_nullable(
            astx.NullableType(resolved.payload_type)
        )
        valid = (
            builder.icmp_unsigned("!=", value, ir.Constant(value.type, None))
            if pointer_payload
            else builder.extract_value(value, 0, name="nullable.valid")
        )
        if resolved.operation is astx.NullableOperation.IS_VALID:
            self.result_stack.append(valid)
            return
        if resolved.operation is astx.NullableOperation.IS_NULL:
            self.result_stack.append(builder.not_(valid, "nullable.is_null"))
            return
        if resolved.operation is not astx.NullableOperation.EXPECT_VALID:
            raise_lowering_internal_error(
                "unknown resolved nullable operation", node=node
            )
        self._guard_runtime_condition(
            node,
            valid,
            code="ARX-RUNTIME-NULL-001",
            message="expect_valid received a null value",
            block_name="nullable.unwrap",
        )
        # The guard leaves the builder in its success block. Never extract a
        # payload on the failure path, even though null storage is zero-filled.
        self.result_stack.append(
            value
            if pointer_payload
            else builder.extract_value(value, 1, name="nullable.payload")
        )
