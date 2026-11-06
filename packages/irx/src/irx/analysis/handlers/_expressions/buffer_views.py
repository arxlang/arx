# mypy: disable-error-code=no-redef

"""
title: Expression buffer-view visitors.
summary: >-
  Handle buffer-view descriptors, indexing, writes, and lifetime helper
  expressions using the shared tensor-and-buffer support mixin.
"""

from __future__ import annotations

import astx

from plum import dispatch
from public import private

from irx.analysis.dependencies.expression_buffer_view import (
    ExpressionBufferViewAnalysisServices,
)
from irx.analysis.types import bit_width, is_integer_type
from irx.analysis.validation import validate_assignment
from irx.buffer import (
    BUFFER_VIEW_ELEMENT_TYPE_EXTRA,
    BUFFER_VIEW_METADATA_EXTRA,
    buffer_view_is_readonly,
    validate_buffer_view_metadata,
)
from irx.diagnostics import DiagnosticCodes
from irx.extensions.handlers import configuration_error
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked

RAW_BUFFER_BYTE_BITS = 8


@private
@typechecked
class ExpressionBufferViewAnalysis:
    """
    title: Expression buffer-view visitors.
    attributes:
      services:
        type: ExpressionBufferViewAnalysisServices
    """

    services: ExpressionBufferViewAnalysisServices

    def __init__(self, services: ExpressionBufferViewAnalysisServices) -> None:
        """
        title: Bind one feature to explicit compilation-owned dependencies.
        parameters:
          services:
            type: ExpressionBufferViewAnalysisServices
        """
        self.services = services

    @dispatch
    def visit(self, node: astx.AST) -> None:
        """
        title: Reject an input outside this feature's explicit support.
        parameters:
          node:
            type: astx.AST
        """
        raise configuration_error(
            f"unsupported {type(node).__name__} "
            "in ExpressionBufferViewAnalysis"
        )

    @dispatch
    def visit(self, node: astx.BufferViewDescriptor) -> None:
        """
        title: Visit BufferViewDescriptor nodes.
        parameters:
          node:
            type: astx.BufferViewDescriptor
        """
        for error in validate_buffer_view_metadata(node.metadata):
            self.services.context.diagnostics.add(error, node=node)
        self.services.semantic(node).extras[BUFFER_VIEW_METADATA_EXTRA] = (
            node.metadata
        )
        if node.type_.element_type is not None:
            self.services.semantic(node).extras[
                BUFFER_VIEW_ELEMENT_TYPE_EXTRA
            ] = node.type_.element_type
        self.services.set_type(node, node.type_)

    @dispatch
    def visit(self, node: astx.BufferViewIndex) -> None:
        """
        title: Visit BufferViewIndex nodes.
        parameters:
          node:
            type: astx.BufferViewIndex
        """
        self.services.visit(node.base)
        for index in node.indices:
            self.services.visit(index)
        element_type = self.services.validate_buffer_view_index_operation(
            node=node,
            base=node.base,
            indices=node.indices,
            is_store=False,
        )
        if element_type is not None:
            node.type_ = element_type
        self.services.set_type(node, element_type)

    @dispatch
    def visit(self, node: astx.BufferViewStore) -> None:
        """
        title: Visit BufferViewStore nodes.
        parameters:
          node:
            type: astx.BufferViewStore
        """
        self.services.visit(node.base)
        for index in node.indices:
            self.services.visit(index)
        self.services.visit(node.value)
        element_type = self.services.validate_buffer_view_index_operation(
            node=node,
            base=node.base,
            indices=node.indices,
            is_store=True,
        )
        if element_type is not None:
            validate_assignment(
                self.services.context.diagnostics,
                target_name="buffer view element",
                target_type=element_type,
                value_type=self.services.expr_type(node.value),
                node=node,
            )
        self.services.set_type(node, astx.Int32())

    @dispatch
    def visit(self, node: astx.BufferViewWrite) -> None:
        """
        title: Visit BufferViewWrite nodes.
        parameters:
          node:
            type: astx.BufferViewWrite
        """
        if node.byte_offset < 0:
            self.services.context.diagnostics.add(
                "buffer view write byte_offset must be non-negative",
                node=node,
                code=DiagnosticCodes.SEMANTIC_BUFFER_MISUSE,
            )

        self.services.visit(node.view)
        view_type = self.services.expr_type(node.view)
        if not isinstance(view_type, astx.BufferViewType):
            self.services.context.diagnostics.add(
                "buffer view write requires a BufferViewType view",
                node=node,
                code=DiagnosticCodes.SEMANTIC_BUFFER_MISUSE,
            )

        view_metadata = self.services.static_buffer_view_metadata(node.view)
        if view_metadata is not None and buffer_view_is_readonly(
            view_metadata.flags
        ):
            self.services.context.diagnostics.add(
                "cannot write through a readonly buffer view",
                node=node,
                code=DiagnosticCodes.SEMANTIC_BUFFER_MISUSE,
            )

        self.services.visit(node.value)
        value_type = self.services.expr_type(node.value)
        if (
            not is_integer_type(value_type)
            or bit_width(value_type) != RAW_BUFFER_BYTE_BITS
        ):
            self.services.context.diagnostics.add(
                "buffer view raw writes require an 8-bit integer value",
                node=node.value,
                code=DiagnosticCodes.SEMANTIC_BUFFER_MISUSE,
            )
        self.services.set_type(node, astx.Int32())

    @dispatch
    def visit(self, node: astx.BufferViewRetain) -> None:
        """
        title: Visit BufferViewRetain nodes.
        parameters:
          node:
            type: astx.BufferViewRetain
        """
        self.services.visit(node.view)
        if not isinstance(
            self.services.expr_type(node.view), astx.BufferViewType
        ):
            self.services.context.diagnostics.add(
                "buffer retain requires a BufferViewType view",
                node=node,
                code=DiagnosticCodes.SEMANTIC_BUFFER_MISUSE,
            )
        self.services.validate_buffer_lifetime_operation(
            node=node,
            view=node.view,
            operation="retain",
        )
        self.services.set_type(node, astx.Int32())

    @dispatch
    def visit(self, node: astx.BufferViewRelease) -> None:
        """
        title: Visit BufferViewRelease nodes.
        parameters:
          node:
            type: astx.BufferViewRelease
        """
        self.services.visit(node.view)
        if not isinstance(
            self.services.expr_type(node.view), astx.BufferViewType
        ):
            self.services.context.diagnostics.add(
                "buffer release requires a BufferViewType view",
                node=node,
                code=DiagnosticCodes.SEMANTIC_BUFFER_MISUSE,
            )
        self.services.validate_buffer_lifetime_operation(
            node=node,
            view=node.view,
            operation="release",
        )
        self.services.set_type(node, astx.Int32())

    def node_handlers(self) -> tuple[NodeHandler, ...]:
        """
        title: Export this feature's supported nominal node signatures.
        returns:
          type: tuple[NodeHandler, Ellipsis]
        """
        return tuple(
            contribute_node(
                "irx.analysis.expression_buffer_view." + node_type.__name__,
                "irx.analysis.expression_buffer_view",
                "analysis",
                node_type,
                self.visit,
                source=__name__ + ".ExpressionBufferViewAnalysis.visit",
            )
            for node_type in (
                astx.BufferViewDescriptor,
                astx.BufferViewIndex,
                astx.BufferViewStore,
                astx.BufferViewWrite,
                astx.BufferViewRetain,
                astx.BufferViewRelease,
            )
        )
