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

from typing import cast

import astx

from irx.analysis.arrow_conversion import arrow_local
from irx.analysis.class_lifecycle import class_local
from irx.analysis.file_io import resolve_file_local
from irx.analysis.flow import flow_outcomes
from irx.analysis.handlers.base import (
    SemanticAnalyzerCore,
    SemanticVisitorMixinBase,
)
from irx.analysis.inference import resolve_initializer_type
from irx.analysis.module_storage import resolve_module_storage
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
        self._semantic(node).resource_ownership = None
        function = self.context.current_function
        if (
            function is not None
            and isinstance(
                function.signature.metadata.get("generator"),
                ResolvedGeneratorFunction,
            )
            and not (
                is_numeric_type(symbol.type_)
                or is_boolean_type(symbol.type_)
                or is_sequence_element(symbol.type_)
                or isinstance(
                    symbol.type_,
                    (astx.ListType, astx.Bytes, astx.GeneratorType),
                )
                or is_string_type(symbol.type_)
            )
        ):
            self.context.diagnostics.add(
                "non-scalar locals in generators require lifecycle cleanup",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        if isinstance(symbol.type_, astx.DataFrameType | astx.SeriesType):
            arrow_local(cast(SemanticAnalyzerCore, self), node, symbol)
            return
        if isinstance(symbol.type_, astx.ClassType):
            class_local(cast(SemanticAnalyzerCore, self), node, symbol)
            return
        if isinstance(symbol.type_, astx.FileType):
            resolve_file_local(cast(SemanticAnalyzerCore, self), node, symbol)
            return
        if is_string_type(symbol.type_):
            self._resolve_local_string_ownership(node, symbol)
            return
        if isinstance(symbol.type_, astx.GeneratorType):
            ownership = resource_ownership(node.value)
            function = self.context.current_function
            if (
                ownership is None
                or ownership.kind is not OwnershipKind.OWNED
                or function is None
                or isinstance(
                    function.signature.metadata.get("generator"),
                    ResolvedGeneratorFunction,
                )
            ):
                self.context.diagnostics.add(
                    "generator locals require a fresh owned iterator "
                    "in an ordinary function",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                )
                return
            assert node.value is not None
            self._set_resource_ownership(
                node.value,
                transfer_resource_ownership(
                    ownership,
                    owner_symbol_id=symbol.symbol_id,
                    transfer_kind=OwnershipTransferKind.MOVE,
                ),
            )
            self._set_resource_ownership(
                node,
                ResourceOwnership(
                    ResourceKind.GENERATOR,
                    OwnershipKind.OWNED,
                    owner_symbol_id=symbol.symbol_id,
                ),
            )
            return
        if not isinstance(symbol.type_, (astx.ListType, astx.Bytes)):
            return
        if isinstance(symbol.type_, astx.ListType) and any(
            isinstance(element_type, (astx.ListType, astx.Bytes))
            for element_type in symbol.type_.element_types
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
        self._semantic(block).flow_outcomes = flow_outcomes(block)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(
        self, node: astx.VariableDeclaration | astx.InlineVariableDeclaration
    ) -> None:
        """
        title: Resolve declaration types before storage publication.
        parameters:
          node:
            type: astx.VariableDeclaration | astx.InlineVariableDeclaration
        """
        resolved_type = resolve_initializer_type(self, node)
        if resolved_type is None:
            return
        symbol = self.registry.declare_local(
            node.name,
            resolved_type,
            is_mutable=node.mutability != astx.MutabilityKind.constant,
            declaration=node,
        )
        self._set_symbol(node, symbol)
        self._resolve_local_resource_ownership(node, symbol)
        resolve_module_storage(self, node, symbol)
