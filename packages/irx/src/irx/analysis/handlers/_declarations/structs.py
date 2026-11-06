# mypy: disable-error-code=no-redef

"""
title: Declaration struct visitors.
summary: >-
  Resolve struct field metadata and reject invalid by-value recursive struct
  definitions.
"""

from __future__ import annotations

from dataclasses import replace

import astx

from plum import dispatch
from public import private

from irx.analysis.dependencies.declaration_struct import (
    DeclarationStructAnalysisServices,
)
from irx.analysis.resolved_nodes import SemanticStruct, SemanticStructField
from irx.analysis.types import clone_type
from irx.diagnostics import DiagnosticCodes
from irx.extensions.handlers import configuration_error
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked

DIRECT_STRUCT_CYCLE_LENGTH = 2


@private
@typechecked
class DeclarationStructAnalysis:
    """
    title: Declaration visitors for struct fields and recursion checks
    attributes:
      services:
        type: DeclarationStructAnalysisServices
    """

    services: DeclarationStructAnalysisServices

    def __init__(self, services: DeclarationStructAnalysisServices) -> None:
        """
        title: Bind one feature to explicit compilation-owned dependencies.
        parameters:
          services:
            type: DeclarationStructAnalysisServices
        """
        self.services = services

    def _resolve_struct_fields(
        self,
        struct: SemanticStruct,
    ) -> SemanticStruct:
        """
        title: Resolve one struct's ordered field metadata.
        parameters:
          struct:
            type: SemanticStruct
        returns:
          type: SemanticStruct
        """
        seen: set[str] = set()
        fields: list[SemanticStructField] = []

        if len(list(struct.declaration.attributes)) == 0:
            self.services.context.diagnostics.add(
                f"Struct '{struct.name}' must declare at least one field",
                node=struct.declaration,
                code=DiagnosticCodes.FFI_INVALID_SIGNATURE,
            )

        for index, attr in enumerate(struct.declaration.attributes):
            if attr.name in seen:
                self.services.context.diagnostics.add(
                    f"Struct field '{attr.name}' already defined.",
                    node=attr,
                    code=DiagnosticCodes.SEMANTIC_DUPLICATE_DECLARATION,
                )
            seen.add(attr.name)
            self.services.resolve_declared_type(
                attr.type_,
                node=attr,
                unknown_message="Unknown field type '{name}'",
            )
            if isinstance(attr.type_, astx.ClassType):
                self.services.context.diagnostics.add(
                    "class references in struct fields are unsupported",
                    node=attr,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                )
            if isinstance(attr.type_, astx.DataFrameType | astx.SeriesType):
                self.services.context.diagnostics.add(
                    "Arrow fields require unsupported aggregate destruction",
                    node=attr,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                )
            if isinstance(attr.type_, astx.FileType):
                self.services.context.diagnostics.add(
                    "file fields require unsupported aggregate destruction",
                    node=attr,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                )
            if isinstance(attr.type_, (astx.ListType, astx.Bytes)):
                self.services.context.diagnostics.add(
                    f"struct field '{struct.name}.{attr.name}' cannot own "
                    "dynamic list storage because struct destruction is not "
                    "supported",
                    node=attr,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                )
            fields.append(
                SemanticStructField(
                    name=attr.name,
                    index=index,
                    type_=clone_type(attr.type_),
                    declaration=attr,
                )
            )

        updated = replace(
            struct,
            fields=tuple(fields),
            field_indices={field.name: field.index for field in fields},
        )
        self.services.context.register_struct(updated)
        self.services.bindings.bind_struct(
            updated.name,
            updated,
            node=updated.declaration,
        )
        self.services.set_struct(updated.declaration, updated)
        return updated

    def _find_struct_cycle(
        self,
        root: SemanticStruct,
        current: SemanticStruct,
        path: tuple[SemanticStruct, ...],
    ) -> tuple[SemanticStruct, ...] | None:
        """
        title: Find one by-value recursive struct cycle.
        parameters:
          root:
            type: SemanticStruct
          current:
            type: SemanticStruct
          path:
            type: tuple[SemanticStruct, Ellipsis]
        returns:
          type: tuple[SemanticStruct, Ellipsis] | None
        """
        seen = {struct.qualified_name for struct in path}
        for attr in current.declaration.attributes:
            field_struct = self.services.resolve_struct_from_type(
                attr.type_,
                node=attr,
                unknown_message="Unknown field type '{name}'",
            )
            if field_struct is None:
                continue
            if field_struct.qualified_name == root.qualified_name:
                return (*path, field_struct)
            if field_struct.qualified_name in seen:
                continue
            cycle = self._find_struct_cycle(
                root,
                field_struct,
                (*path, field_struct),
            )
            if cycle is not None:
                return cycle
        return None

    def _validate_struct_cycles(self, struct: SemanticStruct) -> None:
        """
        title: Reject by-value recursive struct layouts.
        parameters:
          struct:
            type: SemanticStruct
        """
        cycle = self._find_struct_cycle(struct, struct, (struct,))
        if cycle is None:
            return

        if len(cycle) == DIRECT_STRUCT_CYCLE_LENGTH:
            self.services.context.diagnostics.add(
                (
                    "direct by-value recursive struct "
                    f"'{struct.name}' is forbidden"
                ),
                node=struct.declaration,
            )
            return

        cycle_names = " -> ".join(item.name for item in cycle)
        self.services.context.diagnostics.add(
            f"mutual by-value recursive structs are forbidden: {cycle_names}",
            node=struct.declaration,
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
            f"unsupported {type(node).__name__} in DeclarationStructAnalysis"
        )

    @dispatch
    def visit(self, node: astx.StructDefStmt) -> None:
        """
        title: Visit StructDefStmt nodes.
        parameters:
          node:
            type: astx.StructDefStmt
        """
        struct = self.services.registry.register_struct(node)
        self.services.bindings.bind_struct(node.name, struct, node=node)
        struct = self._resolve_struct_fields(struct)
        self.services.set_struct(node, struct)
        self._validate_struct_cycles(struct)
        self.services.set_type(node, None)

    def node_handlers(self) -> tuple[NodeHandler, ...]:
        """
        title: Export this feature's supported nominal node signatures.
        returns:
          type: tuple[NodeHandler, Ellipsis]
        """
        return tuple(
            contribute_node(
                "irx.analysis.declaration_struct." + node_type.__name__,
                "irx.analysis.declaration_struct",
                "analysis",
                node_type,
                self.visit,
                source=__name__ + ".DeclarationStructAnalysis.visit",
            )
            for node_type in (astx.StructDefStmt,)
        )
