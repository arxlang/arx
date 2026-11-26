"""
title: Keep native UTF-8 query metadata within a single binding's lifetime.
"""

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import SemanticInfo
from irx.builder.core import VisitorCore
from irx.builder.state import CleanupAction
from irx.typecheck import typechecked


@private
@typechecked
def bind_text_query_cache(
    visitor: VisitorCore, node: astx.AST, storage: ir.Value
) -> None:
    """
    title: Register an analyzed binding's cache and its lexical cleanup.
    summary: Initialize at entry so conservative invalidation can visit slots
      from inactive branches. Drop metadata even if the string moves out.
    parameters:
      visitor: Visitor performing lowering.
      node: Binding declaration.
      storage: Address of the string pointer.
    """
    info = getattr(node, "semantic", None)
    if not isinstance(info, SemanticInfo) or not info.text_query_cache:
        return
    builder = visitor._llvm.ir_builder
    block = builder.block
    pointer = visitor._llvm.INT8_TYPE.as_pointer()
    cache = visitor.create_entry_block_alloca("text.query.cache", pointer)
    initializer = ir.IRBuilder(builder.function.entry_basic_block)
    initializer.position_after(cache)
    initializer.store(ir.Constant(pointer, None), cache)
    builder.position_at_end(block)
    visitor.text_query_slots.setdefault(builder.function, {})[storage] = cache
    clear = visitor.require_runtime_symbol("text", "irx_text_cache_clear")

    def release() -> None:
        """
        title: Release metadata independently of its source string.
        """
        visitor._llvm.ir_builder.call(clear, [cache])

    visitor.cleanup_stack.append(
        CleanupAction(release, fallible=False, lexical=True)
    )


@private
@typechecked
def clear_text_query_caches(
    visitor: VisitorCore, storage: ir.Value | None = None
) -> None:
    """
    title: Discard one replaced binding or the current frame's caches.
    summary: A resolved call can forward text to foreign code, so invalidate
      before the call and before any exceptional continuation it can take.
    parameters:
      visitor: Visitor performing lowering.
      storage: Address of a replaced binding. None clears all frame caches.
    """
    builder = visitor._llvm.ir_builder
    slots = visitor.text_query_slots.get(builder.function, {})
    if storage is not None:
        slot = slots.get(storage)
        if slot is None:
            return
        active = (slot,)
    else:
        active = tuple(slots.values())
    if active:
        clear = visitor.require_runtime_symbol("text", "irx_text_cache_clear")
        for cache in active:
            builder.call(clear, [cache])
