# mypy: disable-error-code=no-redef

"""
title: Resolve owned list expressions and explicitly contextual tensor storage.
"""

from __future__ import annotations

import astx

from plum import dispatch
from public import private

from irx.analysis.dependencies.expression_list import (
    ExpressionListAnalysisServices,
)
from irx.analysis.numeric_literals import contextualize_literal
from irx.analysis.ownership import list_resource_ownership
from irx.analysis.resolved_nodes import (
    OwnershipKind,
    ResolvedGeneratorFunction,
)
from irx.analysis.types import (
    is_assignable,
    is_numeric_type,
    is_string_type,
    same_type,
)
from irx.analysis.validation import validate_assignment
from irx.builtins.collections.list import (
    list_element_type,
    list_supports_owned_element,
)
from irx.diagnostics import DiagnosticCodes
from irx.extensions.handlers import configuration_error
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
def flatten_collection(
    node: astx.ListExpr,
) -> tuple[tuple[int, ...], list[astx.Expr]]:
    """
    title: Flatten rectangular syntax only under an explicit tensor context.
    parameters:
      node:
        type: astx.ListExpr
    returns:
      type: tuple[tuple[int, Ellipsis], list[astx.Expr]]
    """
    shapes: list[tuple[int, ...]] = []
    values: list[astx.Expr] = []
    for item in node.elements:
        if isinstance(item, astx.ListExpr):
            shape, children = flatten_collection(item)
            shapes.append(shape)
            values.extend(children)
        else:
            shapes.append(())
            values.append(item)
    if shapes and any(shape != shapes[0] for shape in shapes):
        raise ValueError("tensor initializer must have a rectangular shape")
    return (len(node.elements), *(shapes[0] if shapes else ())), values


@private
@typechecked
def infer_list_element(types: list[astx.DataType]) -> astx.DataType | None:
    """
    title: Choose an order-independent lossless domain for all elements.
    parameters:
      types:
        type: list[astx.DataType]
    returns:
      type: astx.DataType | None
    """
    if not types:
        return None
    if all(same_type(types[0], item) for item in types):
        return types[0]
    if all(is_string_type(item) for item in types):
        return astx.String()
    if not all(is_numeric_type(item) for item in types):
        return None
    for candidate in (
        astx.Int8(),
        astx.UInt8(),
        astx.Int16(),
        astx.UInt16(),
        astx.Int32(),
        astx.UInt32(),
        astx.Int64(),
        astx.UInt64(),
        astx.Float16(),
        astx.Float32(),
        astx.Float64(),
    ):
        if all(is_assignable(candidate, item) for item in types):
            return candidate
    return None


@private
@typechecked
class ExpressionListAnalysis:
    """
    title: Resolve list element domains and ownership before lowering.
    attributes:
      services:
        type: ExpressionListAnalysisServices
    """

    services: ExpressionListAnalysisServices

    def __init__(self, services: ExpressionListAnalysisServices) -> None:
        """
        title: Bind one feature to explicit compilation-owned dependencies.
        parameters:
          services:
            type: ExpressionListAnalysisServices
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
            f"unsupported {type(node).__name__} in ExpressionListAnalysis"
        )

    @dispatch
    def visit(self, node: astx.ListExpr) -> None:
        """
        title: Analyze elements in evaluation order.
        parameters:
          node:
            type: astx.ListExpr
        """
        info = self.services.semantic(node)
        info.collection_tensor = None
        info.tensor_temporary_owner = False
        info.resource_ownership = None
        self.services.set_type(node, None)
        target = info.literal_context
        info.literal_context = None
        if isinstance(target, astx.TensorType):
            if target.element_type is None:
                self.services.context.diagnostics.add(
                    "tensor initializer needs a concrete element type",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
                return
            try:
                shape, values = flatten_collection(node)
                if target.shape is None:
                    raise ValueError(
                        "tensor initialization needs a fixed-shape target"
                    )
                if shape != target.shape:
                    raise ValueError(
                        f"tensor initializer has shape {shape}, "
                        f"expected {target.shape}"
                    )
            except ValueError as error:
                self.services.context.diagnostics.add(
                    str(error),
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
                return
            tensor = astx.TensorLiteral(
                values,
                element_type=target.element_type,
                shape=shape,
            )
            tensor.loc = node.loc
            self.services.visit(tensor)
            info.collection_tensor = tensor
            info.tensor_temporary_owner = True
            self.services.set_type(node, self.services.expr_type(tensor))
            return
        element_type = list_element_type(target)
        types: list[astx.DataType] = []
        for item in node.elements:
            contextualize_literal(item, element_type)
            self.services.visit(item)
            self.services.require_value_expression(
                item, context="list element"
            )
            item_type = self.services.expr_type(item)
            if item_type is not None:
                types.append(item_type)
        if element_type is None:
            element_type = infer_list_element(types)
        if element_type is None:
            self.services.context.diagnostics.add(
                "list expression needs a concrete element type; "
                "annotate empty "
                "lists or explicitly cast incompatible elements",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        if not list_supports_owned_element(element_type):
            self.services.context.diagnostics.add(
                "owned lists support numeric, Boolean, and string elements "
                "only; "
                "nested owned containers are unsupported",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        for item in node.elements:
            validate_assignment(
                self.services.context.diagnostics,
                target_name="list element",
                target_type=element_type,
                value_type=self.services.expr_type(item),
                node=item,
            )
        function = self.services.context.current_function
        if function is not None and isinstance(
            function.signature.metadata.get("generator"),
            ResolvedGeneratorFunction,
        ):
            self.services.context.diagnostics.add(
                "owned list expressions in generators require "
                "generator lifecycle cleanup",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
        self.services.set_type(node, astx.ListType([element_type]))
        self.services.set_resource_ownership(
            node, list_resource_ownership(OwnershipKind.OWNED)
        )

    def node_handlers(self) -> tuple[NodeHandler, ...]:
        """
        title: Export this feature's supported nominal node signatures.
        returns:
          type: tuple[NodeHandler, Ellipsis]
        """
        return tuple(
            contribute_node(
                "irx.analysis.expression_list." + node_type.__name__,
                "irx.analysis.expression_list",
                "analysis",
                node_type,
                self.visit,
                source=__name__ + ".ExpressionListAnalysis.visit",
            )
            for node_type in (astx.ListExpr,)
        )
