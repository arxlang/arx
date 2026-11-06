"""
title: Template-specialization build helpers.
summary: >-
  Construct concrete template specializations and their substituted semantic
  argument metadata.
"""

from __future__ import annotations

import copy

from dataclasses import replace

import astx

from public import private

from irx.analysis.dependencies.template_build import (
    TemplateBuildAnalysisServices,
)
from irx.analysis.handlers._templates.state import (
    _OWNER_MODULE_ATTR,
)
from irx.analysis.resolved_nodes import (
    SemanticFunction,
    SemanticSymbol,
    TemplateArgumentBinding,
)
from irx.analysis.types import clone_type
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@private
@typechecked
class TemplateBuildAnalysis:
    """
    title: Template-specialization construction helpers
    attributes:
      services:
        type: TemplateBuildAnalysisServices
    """

    services: TemplateBuildAnalysisServices

    def __init__(self, services: TemplateBuildAnalysisServices) -> None:
        """
        title: Bind one feature to explicit compilation-owned dependencies.
        parameters:
          services:
            type: TemplateBuildAnalysisServices
        """
        self.services = services

    def _specialized_function_args(
        self,
        function: SemanticFunction,
        definition: astx.FunctionDef,
        bindings: dict[str, astx.DataType],
    ) -> tuple[SemanticSymbol, ...]:
        """
        title: Return substituted semantic argument symbols.
        parameters:
          function:
            type: SemanticFunction
          definition:
            type: astx.FunctionDef
          bindings:
            type: dict[str, astx.DataType]
        returns:
          type: tuple[SemanticSymbol, Ellipsis]
        """
        visible_args = tuple(definition.prototype.args.nodes)
        hidden_count = len(function.args) - len(visible_args)
        return tuple(
            self.services.factory.make_variable_symbol(
                function.module_key,
                arg_symbol.name,
                self.services.substitute_type(arg_symbol.type_, bindings),
                is_mutable=arg_symbol.is_mutable,
                declaration=(
                    definition
                    if index < hidden_count
                    else visible_args[index - hidden_count]
                ),
                kind=arg_symbol.kind,
            )
            for index, arg_symbol in enumerate(function.args)
        )

    def _build_template_specialization(
        self,
        function: SemanticFunction,
        concrete_args: tuple[astx.DataType, ...],
    ) -> SemanticFunction | None:
        """
        title: Build or reuse one concrete specialization for a template func.
        parameters:
          function:
            type: SemanticFunction
          concrete_args:
            type: tuple[astx.DataType, Ellipsis]
        returns:
          type: SemanticFunction | None
        """
        key = self.services.template_specialization_key(
            function, concrete_args
        )
        existing = function.specializations.get(key)
        if existing is not None:
            return existing
        if function.definition is None:
            self.services.context.diagnostics.add(
                f"Template function '{function.name}' must have a definition",
                node=function.prototype,
                code=DiagnosticCodes.SEMANTIC_DUPLICATE_DECLARATION,
            )
            return None
        owner_module = self.services.function_owner_module(function)
        if owner_module is None:
            raise TypeError(
                "template specialization requires an owning module"
            )

        bindings = self.services.template_bindings_map(function, concrete_args)
        clone_def = copy.deepcopy(function.definition)
        self.services.clear_semantic_sidecars(clone_def)
        specialization_name = self.services.template_specialization_name(
            function,
            concrete_args,
        )
        specialization_symbol_name = (
            self.services.template_specialization_symbol_name(
                function,
                concrete_args,
            )
        )
        clone_def.prototype.name = specialization_name
        setattr(clone_def, _OWNER_MODULE_ATTR, owner_module)
        setattr(clone_def.prototype, _OWNER_MODULE_ATTR, owner_module)
        astx.set_template_params(clone_def, ())
        astx.set_template_params(clone_def.prototype, ())
        astx.mark_template_specialization(clone_def, specialization_name)
        astx.mark_template_specialization(
            clone_def.prototype,
            specialization_name,
        )
        self.services.substitute_declared_types(clone_def, bindings)

        signature = replace(
            function.signature,
            name=specialization_name,
            parameters=tuple(
                replace(
                    parameter,
                    type_=self.services.substitute_type(
                        parameter.type_, bindings
                    ),
                )
                for parameter in function.signature.parameters
            ),
            return_type=self.services.substitute_type(
                function.signature.return_type,
                bindings,
            ),
            symbol_name=specialization_symbol_name,
        )
        specialized_function = self.services.factory.make_function(
            function.module_key,
            clone_def.prototype,
            signature=signature,
            definition=clone_def,
            args=self._specialized_function_args(
                function,
                clone_def,
                bindings,
            ),
        )
        specialized_function = replace(
            specialized_function,
            qualified_name=(
                f"{function.qualified_name}::specialization::"
                f"{'__'.join(key.arg_type_names)}"
            ),
            template_bindings=tuple(
                TemplateArgumentBinding(param.name, clone_type(argument))
                for param, argument in zip(
                    function.template_params,
                    concrete_args,
                )
            ),
            template_definition=function,
            specialization_key=key,
        )
        function.specializations[key] = specialized_function
        self.services.context.register_function(specialized_function)
        self.services.set_function(clone_def.prototype, specialized_function)
        self.services.set_function(clone_def, specialized_function)
        self.services.set_type(clone_def.prototype, None)
        self.services.set_type(clone_def, None)
        astx.add_generated_template_node(owner_module, clone_def)
        return specialized_function
