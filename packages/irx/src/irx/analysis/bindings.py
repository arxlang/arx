"""
title: Module-visible binding tables.
summary: Own the per-module namespace that imports and top-level declarations
  expose, keeping visible-name lookup separate from lexical scope resolution.
"""

from __future__ import annotations

import astx

from public import public

from irx.analysis.context import SemanticContext
from irx.analysis.factories import SemanticEntityFactory
from irx.analysis.module_interfaces import ModuleKey
from irx.analysis.resolved_nodes import (
    SemanticBinding,
    SemanticClass,
    SemanticFunction,
    SemanticModule,
    SemanticStruct,
)
from irx.typecheck import typechecked


@public
@typechecked
class VisibleBindings:
    """
    title: Module-visible binding manager.
    summary: Track top-level and imported names that are visible within each
      module namespace and enforce conflicts independently from lexical scopes.
    attributes:
      context: Context for the operation.
      factory: Factory.
      _bindings: Bindings.
      tables: Tables.
    """

    context: SemanticContext
    factory: SemanticEntityFactory
    _bindings: dict[ModuleKey, dict[str, SemanticBinding]]

    def __init__(
        self,
        *,
        context: SemanticContext,
        factory: SemanticEntityFactory,
        bindings: dict[ModuleKey, dict[str, SemanticBinding]] | None = None,
    ) -> None:
        """
        title: Initialize VisibleBindings.
        parameters:
          context: Context for the operation.
          factory: Factory.
          bindings: Bindings.
        """
        self.context = context
        self.factory = factory
        self._bindings = bindings or {}

    @property
    def tables(self) -> dict[ModuleKey, dict[str, SemanticBinding]]:
        """
        title: Return the backing binding tables.
        returns: The backing binding tables.
        """
        return self._bindings

    def _current_module_key(
        self,
        module_key: ModuleKey | None = None,
    ) -> ModuleKey:
        """
        title: Return the active or explicit module key.
        parameters:
          module_key: Canonical module identity.
        returns: The active or explicit module key.
        """
        return module_key or self.context.current_module_key or "<root>"

    def bindings_for(
        self,
        module_key: ModuleKey | None = None,
    ) -> dict[str, SemanticBinding]:
        """
        title: Return one module's visible binding table.
        parameters:
          module_key: Canonical module identity.
        returns: One module's visible binding table.
        """
        current_module_key = self._current_module_key(module_key)
        return self._bindings.setdefault(current_module_key, {})

    def binding_conflicts(
        self,
        existing: SemanticBinding,
        new_binding: SemanticBinding,
    ) -> bool:
        """
        title: Return True when two bindings disagree.
        parameters:
          existing: Existing.
          new_binding: New binding.
        returns: True when two bindings disagree.
        """
        return (
            existing.kind != new_binding.kind
            or existing.qualified_name != new_binding.qualified_name
        )

    def bind(
        self,
        local_name: str,
        binding: SemanticBinding,
        *,
        node: astx.AST,
        module_key: ModuleKey | None = None,
    ) -> SemanticBinding:
        """
        title: Bind one visible name in a module namespace.
        parameters:
          local_name: Name of local.
          binding: Resolved binding for the operation.
          node: Syntax node to process.
          module_key: Canonical module identity.
        returns: 'Result of this operation: bind one visible name in a
          module namespace.'
        """
        bindings = self.bindings_for(module_key)
        existing = bindings.get(local_name)
        if existing is not None and self.binding_conflicts(existing, binding):
            self.context.diagnostics.add(
                f"Conflicting binding for '{local_name}'",
                node=node,
            )
            return binding
        bindings[local_name] = binding
        return binding

    def bind_function(
        self,
        local_name: str,
        function: SemanticFunction,
        *,
        node: astx.AST,
        module_key: ModuleKey | None = None,
    ) -> SemanticBinding:
        """
        title: Bind a function in a module namespace.
        parameters:
          local_name: Name of local.
          function: Function to process.
          node: Syntax node to process.
          module_key: Canonical module identity.
        returns: 'Result of this operation: bind a function in a
          module namespace.'
        """
        return self.bind(
            local_name,
            self.factory.make_function_binding(function),
            node=node,
            module_key=module_key,
        )

    def bind_struct(
        self,
        local_name: str,
        struct: SemanticStruct,
        *,
        node: astx.AST,
        module_key: ModuleKey | None = None,
    ) -> SemanticBinding:
        """
        title: Bind a struct in a module namespace.
        parameters:
          local_name: Name of local.
          struct: Struct.
          node: Syntax node to process.
          module_key: Canonical module identity.
        returns: 'Result of this operation: bind a struct in a module
          namespace.'
        """
        return self.bind(
            local_name,
            self.factory.make_struct_binding(struct),
            node=node,
            module_key=module_key,
        )

    def bind_class(
        self,
        local_name: str,
        class_: SemanticClass,
        *,
        node: astx.AST,
        module_key: ModuleKey | None = None,
    ) -> SemanticBinding:
        """
        title: Bind a class in a module namespace.
        parameters:
          local_name: Name of local.
          class_: Class being processed.
          node: Syntax node to process.
          module_key: Canonical module identity.
        returns: 'Result of this operation: bind a class in a module
          namespace.'
        """
        return self.bind(
            local_name,
            self.factory.make_class_binding(class_),
            node=node,
            module_key=module_key,
        )

    def bind_module(
        self,
        local_name: str,
        module: SemanticModule,
        *,
        node: astx.AST,
        module_key: ModuleKey | None = None,
    ) -> SemanticBinding:
        """
        title: Bind an imported module in a module namespace.
        parameters:
          local_name: Name of local.
          module: Module to process.
          node: Syntax node to process.
          module_key: Canonical module identity.
        returns: 'Result of this operation: bind an imported module in
          a module namespace.'
        """
        return self.bind(
            local_name,
            self.factory.make_module_binding(module),
            node=node,
            module_key=module_key,
        )

    def resolve(
        self,
        name: str,
        *,
        module_key: ModuleKey | None = None,
    ) -> SemanticBinding | None:
        """
        title: Resolve one visible binding by name.
        parameters:
          name: Name identifying the declaration or operation.
          module_key: Canonical module identity.
        returns: Resolved one visible binding by name.
        """
        current_module_key = self._current_module_key(module_key)
        bindings = self._bindings.get(current_module_key, {})
        return bindings.get(name)

    def allows_function_access(
        self, binding: SemanticBinding, requesting_module_key: ModuleKey
    ) -> bool:
        """
        title: Enforce module-local function visibility without changing
          linkage.
        summary: Public functions may cross module boundaries. A private
          function is accessible only from its defining module, including
          through aliases. Other binding kinds retain their existing access
          rules.
        parameters:
          binding: Resolved binding for the operation.
          requesting_module_key: Requesting module key.
        returns: 'Result of this operation: enforce module-local function
          visibility without changing linkage.'
        """
        function = binding.function
        return (
            function is None
            or function.visibility is astx.VisibilityKind.public
            or function.module_key == requesting_module_key
        )
