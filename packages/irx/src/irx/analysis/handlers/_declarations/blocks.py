# mypy: disable-error-code=no-redef
# mypy: disable-error-code=attr-defined
# mypy: disable-error-code=untyped-decorator

"""
title: Declaration block visitors.
summary: >-
  Handle modules, blocks, and local variable declarations during declaration
  analysis.
"""

from __future__ import annotations

import astx

from irx.analysis.handlers.base import (
    SemanticAnalyzerCore,
    SemanticVisitorMixinBase,
)
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
    SemanticSymbol,
)
from irx.analysis.types import is_string_type
from irx.analysis.validation import validate_assignment
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@typechecked
class DeclarationBlockVisitorMixin(SemanticVisitorMixinBase):
    """
    title: Declaration visitors for modules, blocks, and local declarations
    """

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
        if is_string_type(node.type_):
            self._resolve_local_string_ownership(node, symbol)
            return
        if not isinstance(node.type_, astx.ListType):
            return
        if any(
            isinstance(element_type, astx.ListType)
            for element_type in node.type_.element_types
        ):
            self.context.diagnostics.add(
                f"list '{node.name}' cannot own dynamic-list elements "
                "because nested ownership and destruction are not supported",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return

        function = self.context.current_function
        if function is None:
            self.context.diagnostics.add(
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
                self.context.diagnostics.add(
                    "owned list locals in generators require generator "
                    "lifecycle cleanup, which is not supported yet",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                )
                return
            self._set_resource_ownership(
                node,
                list_resource_ownership(
                    OwnershipKind.OWNED,
                    owner_symbol_id=symbol.symbol_id,
                ),
            )
            return

        initializer_ownership = resource_ownership(value)
        if initializer_ownership is None:
            self.context.diagnostics.add(
                f"list initializer for '{node.name}' is missing ownership "
                "metadata",
                node=value,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        if initializer_ownership.kind is OwnershipKind.BORROWED:
            self.context.diagnostics.add(
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
            self.context.diagnostics.add(
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
            self.context.diagnostics.add(
                "owned list locals in generators require generator "
                "lifecycle cleanup, which is not supported yet",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return

        self._set_resource_ownership(
            value,
            transfer_resource_ownership(
                initializer_ownership,
                owner_symbol_id=symbol.symbol_id,
                transfer_kind=OwnershipTransferKind.MOVE,
            ),
        )
        self._set_resource_ownership(
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
            self._set_resource_ownership(
                node,
                string_resource_ownership(
                    OwnershipKind.STATIC,
                    owner_symbol_id=symbol.symbol_id,
                ),
            )
            return

        initializer_ownership = resource_ownership(value)
        if initializer_ownership is None:
            self.context.diagnostics.add(
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
                self._set_resource_ownership(
                    node,
                    string_resource_ownership(
                        OwnershipKind.STATIC,
                        owner_symbol_id=symbol.symbol_id,
                        source_symbol_id=source_symbol.symbol_id,
                    ),
                )
                return
            self.context.diagnostics.add(
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
            self._set_resource_ownership(
                node,
                string_resource_ownership(
                    OwnershipKind.STATIC,
                    owner_symbol_id=symbol.symbol_id,
                    source_symbol_id=initializer_ownership.source_symbol_id,
                ),
            )
            return

        function = self.context.current_function
        if function is None:
            self.context.diagnostics.add(
                f"module-level owned string '{node.name}' requires module "
                "lifecycle cleanup, which is not supported yet",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        generator = function.signature.metadata.get("generator")
        if isinstance(generator, ResolvedGeneratorFunction):
            self.context.diagnostics.add(
                "owned string locals in generators require generator "
                "lifecycle cleanup, which is not supported yet",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return

        self._set_resource_ownership(
            value,
            transfer_resource_ownership(
                initializer_ownership,
                owner_symbol_id=symbol.symbol_id,
                transfer_kind=OwnershipTransferKind.MOVE,
            ),
        )
        self._set_resource_ownership(
            node,
            string_resource_ownership(
                OwnershipKind.OWNED,
                owner_symbol_id=symbol.symbol_id,
            ),
        )

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, module: astx.Module) -> None:
        """
        title: Visit Module nodes.
        parameters:
          module:
            type: astx.Module
        """
        with self.context.in_module(module.name):
            self._visit_module(module, predeclared=False)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, block: astx.Block) -> None:
        """
        title: Visit Block nodes.
        parameters:
          block:
            type: astx.Block
        """
        self._set_type(block, None)
        self._predeclare_block_structs(block)
        for node in block.nodes:
            self.visit(node)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.VariableDeclaration) -> None:
        """
        title: Visit VariableDeclaration nodes.
        parameters:
          node:
            type: astx.VariableDeclaration
        """
        self._resolve_declared_type(node.type_, node=node)
        if node.value is not None and not isinstance(
            node.value, astx.Undefined
        ):
            self.visit(node.value)
            if self._require_value_expression(
                node.value,
                context=f"Initializer for '{node.name}'",
            ):
                validate_assignment(
                    self.context.diagnostics,
                    target_name=node.name,
                    target_type=node.type_,
                    value_type=self._expr_type(node.value),
                    node=node,
                )
        symbol = self.registry.declare_local(
            node.name,
            node.type_,
            is_mutable=node.mutability != astx.MutabilityKind.constant,
            declaration=node,
        )
        self._set_symbol(node, symbol)
        self._resolve_local_resource_ownership(node, symbol)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.InlineVariableDeclaration) -> None:
        """
        title: Visit InlineVariableDeclaration nodes.
        parameters:
          node:
            type: astx.InlineVariableDeclaration
        """
        self._resolve_declared_type(node.type_, node=node)
        if node.value is not None and not isinstance(
            node.value, astx.Undefined
        ):
            self.visit(node.value)
            if self._require_value_expression(
                node.value,
                context=f"Initializer for '{node.name}'",
            ):
                validate_assignment(
                    self.context.diagnostics,
                    target_name=node.name,
                    target_type=node.type_,
                    value_type=self._expr_type(node.value),
                    node=node,
                )
        symbol = self.registry.declare_local(
            node.name,
            node.type_,
            is_mutable=node.mutability != astx.MutabilityKind.constant,
            declaration=node,
        )
        self._set_symbol(node, symbol)
        self._resolve_local_resource_ownership(node, symbol)
