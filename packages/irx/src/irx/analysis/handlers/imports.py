# mypy: disable-error-code=no-redef

"""
title: Import and module-binding semantic visitors.
summary: >-
  Resolve host-provided imports into semantic module-visible bindings while
  keeping import coordination separate from declaration and expression rules.
"""

from __future__ import annotations

import astx

from plum import dispatch
from public import private

from irx.analysis.dependencies.imports import ImportAnalysisServices
from irx.extensions.handlers import configuration_error
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class ImportAnalysis:
    """
    title: Analyze imported module declarations.
    attributes:
      services:
        type: ImportAnalysisServices
    """

    services: ImportAnalysisServices

    def __init__(self, services: ImportAnalysisServices) -> None:
        """
        title: Bind one feature to explicit compilation-owned dependencies.
        parameters:
          services:
            type: ImportAnalysisServices
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
            f"unsupported {type(node).__name__} in ImportAnalysis"
        )

    @dispatch
    def visit(self, node: astx.ImportStmt) -> None:
        """
        title: Visit ImportStmt nodes.
        parameters:
          node:
            type: astx.ImportStmt
        """
        self.services.set_type(node, None)
        if not self.services.imports_supported_here(node):
            return

        session = self.services.session
        assert session is not None

        resolved_imports = []
        for alias in node.names:
            resolved = session.resolve_import_specifier(
                self.services.current_module_key(),
                node,
                alias.name,
            )
            if resolved is None:
                continue
            semantic_module = self.services.factory.make_module(
                resolved.key,
                display_name=resolved.display_name,
            )
            local_name = alias.asname or alias.name
            binding = self.services.bindings.bind_module(
                local_name,
                semantic_module,
                node=alias,
            )
            resolved_binding = self.services.factory.make_import_binding(
                local_name=local_name,
                requested_name=alias.name,
                source_module_key=resolved.key,
                binding=binding,
            )
            resolved_imports.append(resolved_binding)
            self.services.set_module(alias, semantic_module)
            self.services.set_imports(alias, (resolved_binding,))
        self.services.set_imports(node, tuple(resolved_imports))

    @dispatch
    def visit(self, node: astx.ImportFromStmt) -> None:
        """
        title: Visit ImportFromStmt nodes.
        parameters:
          node:
            type: astx.ImportFromStmt
        """
        self.services.set_type(node, None)
        if not self.services.imports_supported_here(node):
            return

        session = self.services.session
        assert session is not None

        requested_specifier = f"{'.' * node.level}{node.module or ''}"
        resolved_parent = session.resolve_import_specifier(
            self.services.current_module_key(),
            node,
            requested_specifier,
        )
        if resolved_parent is None:
            return

        parent_module = self.services.factory.make_module(
            resolved_parent.key,
            display_name=resolved_parent.display_name,
        )
        self.services.set_module(node, parent_module)
        resolved_imports = []

        for alias in node.names:
            if alias.name == "*":
                self.services.context.diagnostics.add(
                    "Wildcard imports are not supported in this MVP.",
                    node=alias,
                )
                continue

            target_binding, resolved_child = session.resolve_import_from_name(
                self.services.current_module_key(),
                node,
                resolved_parent.key,
                alias.name,
            )
            local_name = alias.asname or alias.name

            if target_binding is not None:
                binding = self.services.bindings.bind(
                    local_name,
                    target_binding,
                    node=alias,
                )
                resolved_binding = self.services.factory.make_import_binding(
                    local_name=local_name,
                    requested_name=alias.name,
                    source_module_key=resolved_parent.key,
                    binding=binding,
                )
                resolved_imports.append(resolved_binding)
                self.services.set_module(alias, parent_module)
                self.services.set_imports(alias, (resolved_binding,))
                if target_binding.function is not None:
                    self.services.set_function(alias, target_binding.function)
                if target_binding.struct is not None:
                    self.services.set_struct(alias, target_binding.struct)
                if target_binding.class_ is not None:
                    self.services.set_class(alias, target_binding.class_)
                continue

            if resolved_child is not None:
                child_module = self.services.factory.make_module(
                    resolved_child.key,
                    display_name=resolved_child.display_name,
                )
                binding = self.services.bindings.bind_module(
                    local_name,
                    child_module,
                    node=alias,
                )
                resolved_binding = self.services.factory.make_import_binding(
                    local_name=local_name,
                    requested_name=alias.name,
                    source_module_key=resolved_child.key,
                    binding=binding,
                )
                resolved_imports.append(resolved_binding)
                self.services.set_module(alias, child_module)
                self.services.set_imports(alias, (resolved_binding,))
                continue

            self.services.context.diagnostics.add(
                f"Imported symbol '{alias.name}' was not found in "
                f"module '{requested_specifier}'",
                node=alias,
            )

        self.services.set_imports(node, tuple(resolved_imports))

    @dispatch
    def visit(self, node: astx.ImportExpr) -> None:
        """
        title: Visit ImportExpr nodes.
        parameters:
          node:
            type: astx.ImportExpr
        """
        self.services.context.diagnostics.add(
            "Import expressions are not supported in this MVP.",
            node=node,
        )
        self.services.set_type(node, None)

    @dispatch
    def visit(self, node: astx.ImportFromExpr) -> None:
        """
        title: Visit ImportFromExpr nodes.
        parameters:
          node:
            type: astx.ImportFromExpr
        """
        self.services.context.diagnostics.add(
            "Import expressions are not supported in this MVP.",
            node=node,
        )
        self.services.set_type(node, None)

    def node_handlers(self) -> tuple[NodeHandler, ...]:
        """
        title: Export this feature's supported nominal node signatures.
        returns:
          type: tuple[NodeHandler, Ellipsis]
        """
        return tuple(
            contribute_node(
                "irx.analysis.imports." + node_type.__name__,
                "irx.analysis.imports",
                "analysis",
                node_type,
                self.visit,
                source=__name__ + ".ImportAnalysis.visit",
            )
            for node_type in (
                astx.ImportStmt,
                astx.ImportFromStmt,
                astx.ImportExpr,
                astx.ImportFromExpr,
            )
        )
