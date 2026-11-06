# mypy: disable-error-code=no-redef

"""
title: Declaration block visitors.
summary: >-
  Handle modules, blocks, and local variable declarations during declaration
  analysis.
"""

from __future__ import annotations

import astx

from plum import dispatch
from public import private

from irx.analysis.dependencies.declaration_block import (
    DeclarationBlockAnalysisServices,
)
from irx.analysis.flow import flow_outcomes
from irx.analysis.numeric_literals import contextualize_literal
from irx.analysis.ownership import (
    list_resource_ownership,
    resource_ownership,
    string_resource_ownership,
    symbol_resource_ownership,
    transfer_resource_ownership,
)
from irx.analysis.resolved_nodes import (
    OwnershipKind,
    OwnershipTransferKind,
    ResolvedGeneratorFunction,
    ResourceKind,
    ResourceOwnership,
    SemanticSymbol,
)
from irx.analysis.types import (
    is_boolean_type,
    is_numeric_type,
    is_sequence_element,
    is_string_type,
)
from irx.analysis.validation import validate_assignment
from irx.diagnostics import DiagnosticCodes
from irx.extensions.handlers import configuration_error
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class DeclarationBlockAnalysis:
    """
    title: Declaration visitors for modules, blocks, and local declarations
    attributes:
      services:
        type: DeclarationBlockAnalysisServices
    """

    services: DeclarationBlockAnalysisServices

    def __init__(self, services: DeclarationBlockAnalysisServices) -> None:
        """
        title: Bind one feature to explicit compilation-owned dependencies.
        parameters:
          services:
            type: DeclarationBlockAnalysisServices
        """
        self.services = services

    def _resolve_local_resource_ownership(
        self,
        node: astx.VariableDeclaration | astx.InlineVariableDeclaration,
        symbol: SemanticSymbol,
    ) -> None:
        """
        title: Attach the ownership contract for one local declaration.
        parameters:
          node:
            type: astx.VariableDeclaration | astx.InlineVariableDeclaration
          symbol:
            type: SemanticSymbol
        """
        self.services.semantic(node).resource_ownership = None
        function = self.services.context.current_function
        if (
            function is not None
            and isinstance(
                function.signature.metadata.get("generator"),
                ResolvedGeneratorFunction,
            )
            and not (
                is_numeric_type(node.type_)
                or is_boolean_type(node.type_)
                or is_sequence_element(node.type_)
                or isinstance(
                    node.type_, (astx.ListType, astx.Bytes, astx.GeneratorType)
                )
                or is_string_type(node.type_)
            )
        ):
            self.services.context.diagnostics.add(
                "non-scalar locals in generators require lifecycle cleanup",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        if isinstance(node.type_, astx.DataFrameType | astx.SeriesType):
            self.services.free_arrow_local(node, symbol)
            return
        if isinstance(node.type_, astx.ClassType):
            self.services.free_class_local(node, symbol)
            return
        if isinstance(node.type_, astx.FileType):
            self.services.free_resolve_file_local(node, symbol)
            return
        if is_string_type(node.type_):
            self._resolve_local_string_ownership(node, symbol)
            return
        if isinstance(node.type_, astx.GeneratorType):
            ownership = resource_ownership(node.value)
            function = self.services.context.current_function
            if (
                ownership is None
                or ownership.kind is not OwnershipKind.OWNED
                or function is None
                or isinstance(
                    function.signature.metadata.get("generator"),
                    ResolvedGeneratorFunction,
                )
            ):
                self.services.context.diagnostics.add(
                    "generator locals require a fresh owned iterator "
                    "in an ordinary function",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                )
                return
            assert node.value is not None
            self.services.set_resource_ownership(
                node.value,
                transfer_resource_ownership(
                    ownership,
                    owner_symbol_id=symbol.symbol_id,
                    transfer_kind=OwnershipTransferKind.MOVE,
                ),
            )
            self.services.set_resource_ownership(
                node,
                ResourceOwnership(
                    ResourceKind.GENERATOR,
                    OwnershipKind.OWNED,
                    owner_symbol_id=symbol.symbol_id,
                ),
            )
            return
        if not isinstance(node.type_, (astx.ListType, astx.Bytes)):
            return
        if isinstance(node.type_, astx.ListType) and any(
            isinstance(element_type, (astx.ListType, astx.Bytes))
            for element_type in node.type_.element_types
        ):
            self.services.context.diagnostics.add(
                f"list '{node.name}' cannot own dynamic-list elements "
                "because nested ownership and destruction are not supported",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return

        function = self.services.context.current_function
        if function is None:
            self.services.context.diagnostics.add(
                f"module-level owned list '{node.name}' requires module "
                "lifecycle cleanup, which is not supported yet",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        generator = function.signature.metadata.get("generator")
        is_generator = isinstance(generator, ResolvedGeneratorFunction)

        value = node.value
        if value is None or isinstance(value, astx.Undefined):
            if is_generator:
                self.services.context.diagnostics.add(
                    "owned list locals in generators require generator "
                    "lifecycle cleanup, which is not supported yet",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                )
                return
            self.services.set_resource_ownership(
                node,
                list_resource_ownership(
                    OwnershipKind.OWNED,
                    owner_symbol_id=symbol.symbol_id,
                ),
            )
            return

        initializer_ownership = resource_ownership(value)
        if initializer_ownership is None:
            self.services.context.diagnostics.add(
                f"list initializer for '{node.name}' is missing ownership "
                "metadata",
                node=value,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        if initializer_ownership.kind is OwnershipKind.BORROWED:
            self.services.context.diagnostics.add(
                f"list initializer for '{node.name}' would copy borrowed "
                "storage; local list copies are not supported",
                node=value,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                notes=(
                    "create a new list or return a freshly owned list from a "
                    "function",
                ),
            )
            return
        if initializer_ownership.kind is OwnershipKind.STATIC:
            self.services.context.diagnostics.add(
                f"static list storage cannot initialize dynamic list local "
                f"'{node.name}'",
                node=value,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                notes=(
                    "use the literal directly for indexing or iteration, or "
                    "initialize the local from a dynamic list producer",
                ),
            )
            return
        if is_generator:
            self.services.context.diagnostics.add(
                "owned list locals in generators require generator "
                "lifecycle cleanup, which is not supported yet",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return

        self.services.set_resource_ownership(
            value,
            transfer_resource_ownership(
                initializer_ownership,
                owner_symbol_id=symbol.symbol_id,
                transfer_kind=OwnershipTransferKind.MOVE,
            ),
        )
        self.services.set_resource_ownership(
            node,
            list_resource_ownership(
                OwnershipKind.OWNED,
                owner_symbol_id=symbol.symbol_id,
            ),
        )

    def _resolve_local_string_ownership(
        self,
        node: astx.VariableDeclaration | astx.InlineVariableDeclaration,
        symbol: SemanticSymbol,
    ) -> None:
        """
        title: Attach the ownership contract for one local string declaration.
        parameters:
          node:
            type: astx.VariableDeclaration | astx.InlineVariableDeclaration
          symbol:
            type: SemanticSymbol
        """
        value = node.value
        if value is None or isinstance(value, astx.Undefined):
            self.services.set_resource_ownership(
                node,
                string_resource_ownership(
                    OwnershipKind.STATIC,
                    owner_symbol_id=symbol.symbol_id,
                ),
            )
            return

        initializer_ownership = resource_ownership(value)
        if initializer_ownership is None:
            self.services.context.diagnostics.add(
                f"string initializer for '{node.name}' is missing ownership "
                "metadata",
                node=value,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        if initializer_ownership.kind is OwnershipKind.BORROWED:
            source_symbol = getattr(
                getattr(value, "semantic", None),
                "resolved_symbol",
                None,
            )
            source_ownership = (
                symbol_resource_ownership(source_symbol)
                if isinstance(source_symbol, SemanticSymbol)
                else None
            )
            if (
                isinstance(source_symbol, SemanticSymbol)
                and source_ownership is not None
                and source_ownership.kind is OwnershipKind.STATIC
            ):
                self.services.set_resource_ownership(
                    node,
                    string_resource_ownership(
                        OwnershipKind.STATIC,
                        owner_symbol_id=symbol.symbol_id,
                        source_symbol_id=source_symbol.symbol_id,
                    ),
                )
                return
            self.services.context.diagnostics.add(
                f"string initializer for '{node.name}' would alias borrowed "
                "storage; borrowed string copies are not supported",
                node=value,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                notes=(
                    "initialize from a literal or a freshly allocated string",
                ),
            )
            return
        if initializer_ownership.kind is OwnershipKind.STATIC:
            self.services.set_resource_ownership(
                node,
                string_resource_ownership(
                    OwnershipKind.STATIC,
                    owner_symbol_id=symbol.symbol_id,
                    source_symbol_id=initializer_ownership.source_symbol_id,
                ),
            )
            return

        function = self.services.context.current_function
        if function is None:
            self.services.context.diagnostics.add(
                f"module-level owned string '{node.name}' requires module "
                "lifecycle cleanup, which is not supported yet",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        generator = function.signature.metadata.get("generator")
        if isinstance(generator, ResolvedGeneratorFunction):
            self.services.context.diagnostics.add(
                "owned string locals in generators require generator "
                "lifecycle cleanup, which is not supported yet",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return

        self.services.set_resource_ownership(
            value,
            transfer_resource_ownership(
                initializer_ownership,
                owner_symbol_id=symbol.symbol_id,
                transfer_kind=OwnershipTransferKind.MOVE,
            ),
        )
        self.services.set_resource_ownership(
            node,
            string_resource_ownership(
                OwnershipKind.OWNED,
                owner_symbol_id=symbol.symbol_id,
            ),
        )

    @dispatch
    def visit(self, node: astx.AST) -> None:
        """
        title: Reject an input outside this feature's explicit support.
        parameters:
          node:
            type: astx.AST
        """
        raise configuration_error(
            f"unsupported {type(node).__name__} in DeclarationBlockAnalysis"
        )

    @dispatch
    def visit(self, module: astx.Module) -> None:
        """
        title: Visit Module nodes.
        parameters:
          module:
            type: astx.Module
        """
        with self.services.context.in_module(module.name):
            self.services.visit_module(module, predeclared=False)

    @dispatch
    def visit(self, block: astx.Block) -> None:
        """
        title: Visit Block nodes.
        parameters:
          block:
            type: astx.Block
        """
        self.services.set_type(block, None)
        self.services.predeclare_block_structs(block)
        for node in block.nodes:
            self.services.visit(node)
        self.services.semantic(block).flow_outcomes = flow_outcomes(block)

    @dispatch
    def visit(self, node: astx.VariableDeclaration) -> None:
        """
        title: Visit VariableDeclaration nodes.
        parameters:
          node:
            type: astx.VariableDeclaration
        """
        self.services.resolve_declared_type(node.type_, node=node)
        if isinstance(node.type_, astx.NullableType) and isinstance(
            node.value, astx.LiteralNone
        ):
            node.value = astx.Cast(node.value, node.type_)
            node.value.loc = node.value.value.loc
        if node.value is not None and not isinstance(
            node.value, astx.Undefined
        ):
            contextualize_literal(node.value, node.type_)
            self.services.visit(node.value)
            if self.services.require_value_expression(
                node.value,
                context=f"Initializer for '{node.name}'",
            ):
                validate_assignment(
                    self.services.context.diagnostics,
                    target_name=node.name,
                    target_type=node.type_,
                    value_type=self.services.expr_type(node.value),
                    node=node,
                )
        symbol = self.services.registry.declare_local(
            node.name,
            node.type_,
            is_mutable=node.mutability != astx.MutabilityKind.constant,
            declaration=node,
        )
        self.services.set_symbol(node, symbol)
        self._resolve_local_resource_ownership(node, symbol)
        self.services.free_resolve_nullable_global(node)

    @dispatch
    def visit(self, node: astx.InlineVariableDeclaration) -> None:
        """
        title: Visit InlineVariableDeclaration nodes.
        parameters:
          node:
            type: astx.InlineVariableDeclaration
        """
        self.services.resolve_declared_type(node.type_, node=node)
        if isinstance(node.type_, astx.NullableType) and isinstance(
            node.value, astx.LiteralNone
        ):
            node.value = astx.Cast(node.value, node.type_)
            node.value.loc = node.value.value.loc
        if node.value is not None and not isinstance(
            node.value, astx.Undefined
        ):
            contextualize_literal(node.value, node.type_)
            self.services.visit(node.value)
            if self.services.require_value_expression(
                node.value,
                context=f"Initializer for '{node.name}'",
            ):
                validate_assignment(
                    self.services.context.diagnostics,
                    target_name=node.name,
                    target_type=node.type_,
                    value_type=self.services.expr_type(node.value),
                    node=node,
                )
        symbol = self.services.registry.declare_local(
            node.name,
            node.type_,
            is_mutable=node.mutability != astx.MutabilityKind.constant,
            declaration=node,
        )
        self.services.set_symbol(node, symbol)
        self._resolve_local_resource_ownership(node, symbol)
        self.services.free_resolve_nullable_global(node)

    def node_handlers(self) -> tuple[NodeHandler, ...]:
        """
        title: Export this feature's supported nominal node signatures.
        returns:
          type: tuple[NodeHandler, Ellipsis]
        """
        return tuple(
            contribute_node(
                "irx.analysis.declaration_block." + node_type.__name__,
                "irx.analysis.declaration_block",
                "analysis",
                node_type,
                self.visit,
                source=__name__ + ".DeclarationBlockAnalysis.visit",
            )
            for node_type in (
                astx.Module,
                astx.Block,
                astx.VariableDeclaration,
                astx.InlineVariableDeclaration,
            )
        )
