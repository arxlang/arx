"""
title: Template-specialization analysis helpers.
summary: >-
  Prepare generated specializations and analyze their concrete function bodies
  during template processing.
"""

from __future__ import annotations

from itertools import product

import astx

from public import private

from irx.analysis.dependencies.template_analysis import (
    TemplateAnalysisAnalysisServices,
)
from irx.analysis.handlers._templates.state import (
    _OWNER_MODULE_ATTR,
    _SPECIALIZATION_ANALYZED_ATTR,
)
from irx.analysis.resolved_nodes import SemanticFunction
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@private
@typechecked
class TemplateAnalysisAnalysis:
    """
    title: Template-specialization preparation and semantic-analysis helpers
    attributes:
      services:
        type: TemplateAnalysisAnalysisServices
    """

    services: TemplateAnalysisAnalysisServices

    def __init__(self, services: TemplateAnalysisAnalysisServices) -> None:
        """
        title: Bind one feature to explicit compilation-owned dependencies.
        parameters:
          services:
            type: TemplateAnalysisAnalysisServices
        """
        self.services = services

    def _prepare_function_template_specializations(
        self,
        function: SemanticFunction,
    ) -> None:
        """
        title: Materialize all concrete specializations for one template func.
        parameters:
          function:
            type: SemanticFunction
        """
        if (
            not function.template_params
            or function.template_definition is not None
        ):
            return
        if function.definition is None:
            self.services.context.diagnostics.add(
                f"Template function '{function.name}' must have a definition",
                node=function.prototype,
                code=DiagnosticCodes.SEMANTIC_DUPLICATE_DECLARATION,
            )
            return
        if self.services.template_specializations_prepared(function):
            return
        domains = tuple(
            self.services.template_param_domain(param)
            for param in function.template_params
        )
        for concrete_args in product(*domains):
            self.services.build_template_specialization(
                function, concrete_args
            )
        self.services.mark_template_specializations_prepared(function)

    def _prepare_template_specialization_skeletons(
        self,
        module: astx.Module,
    ) -> None:
        """
        title: Materialize specialization skeletons for module templates.
        parameters:
          module:
            type: astx.Module
        """
        for node in module.nodes:
            if isinstance(node, astx.FunctionPrototype):
                setattr(node, _OWNER_MODULE_ATTR, module)
                function = self.services.context.get_function(
                    self.services.current_module_key(),
                    node.name,
                )
                if (
                    function is not None
                    and function.template_params
                    and function.definition is None
                ):
                    self.services.context.diagnostics.add(
                        f"Template function '{function.name}' must have a "
                        "definition",
                        node=node,
                        code=DiagnosticCodes.SEMANTIC_DUPLICATE_DECLARATION,
                    )
                continue
            if not isinstance(node, astx.FunctionDef):
                continue
            setattr(node, _OWNER_MODULE_ATTR, module)
            setattr(node.prototype, _OWNER_MODULE_ATTR, module)
            function = self.services.context.get_function(
                self.services.current_module_key(),
                node.name,
            )
            if function is None:
                continue
            self._prepare_function_template_specializations(function)

    def _analyze_specialized_function_body(
        self,
        function: SemanticFunction,
    ) -> None:
        """
        title: Analyze one generated concrete specialization body.
        parameters:
          function:
            type: SemanticFunction
        """
        definition = function.definition
        if definition is None:
            raise TypeError("template specialization requires a definition")
        for argument in definition.prototype.args.nodes:
            self.services.resolve_declared_type(argument.type_, node=argument)
        self.services.resolve_declared_type(
            definition.prototype.return_type,
            node=definition,
        )
        self.services.set_function(definition.prototype, function)
        self.services.set_function(definition, function)
        self.services.set_type(definition.prototype, None)
        self.services.set_type(definition, None)
        hidden_parameter_count = len(function.args) - len(
            definition.prototype.args.nodes
        )
        with self.services.context.in_function(function):
            self.services.analyze_parameter_defaults(function)
            with self.services.context.scope("function"):
                for index, arg_symbol in enumerate(function.args):
                    self.services.context.scopes.declare(arg_symbol)
                    if index < hidden_parameter_count:
                        continue
                    arg_node = definition.prototype.args.nodes[
                        index - hidden_parameter_count
                    ]
                    self.services.set_symbol(arg_node, arg_symbol)
                    self.services.set_type(arg_node, arg_symbol.type_)
                    self.services.free_resolve_parameter_ownership(
                        arg_node, arg_symbol
                    )
                self.services.visit(definition.body)
        if not isinstance(
            function.return_type, astx.NoneType
        ) and not self.services.guarantees_return(definition.body):
            self.services.context.diagnostics.add(
                f"Function '{function.name}' with return type "
                f"'{function.return_type}' is missing a return statement",
                node=definition,
            )

    def _analyze_prepared_template_specialization(
        self,
        function: SemanticFunction,
    ) -> None:
        """
        title: Analyze one prepared concrete specialization once.
        parameters:
          function:
            type: SemanticFunction
        """
        definition = function.definition
        if definition is None:
            raise TypeError(
                "prepared template specialization lacks definition"
            )
        if getattr(definition, _SPECIALIZATION_ANALYZED_ATTR, False):
            return
        diagnostic_count_before = len(
            self.services.context.diagnostics.diagnostics
        )
        self._analyze_specialized_function_body(function)
        setattr(definition, _SPECIALIZATION_ANALYZED_ATTR, True)
        if (
            len(self.services.context.diagnostics.diagnostics)
            == diagnostic_count_before
        ):
            return
        template_definition = function.template_definition
        if template_definition is None:
            return
        bindings_text = self.services.format_template_bindings(
            function.template_bindings
        )
        self.services.context.diagnostics.add(
            f"Template function '{template_definition.name}' is invalid for "
            f"{bindings_text}",
            node=(
                template_definition.definition or template_definition.prototype
            ),
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )

    def _analyze_function_template_specializations(
        self,
        function: SemanticFunction,
    ) -> None:
        """
        title: Analyze all prepared specializations for one template function.
        parameters:
          function:
            type: SemanticFunction
        """
        for specialization in tuple(function.specializations.values()):
            self._analyze_prepared_template_specialization(specialization)

    def _analyze_prepared_template_specializations(
        self,
        module: astx.Module,
    ) -> None:
        """
        title: Analyze the generated specializations attached to one module.
        parameters:
          module:
            type: astx.Module
        """
        for node in astx.generated_template_nodes(module):
            semantic = getattr(node, "semantic", None)
            function = getattr(semantic, "resolved_function", None)
            if not isinstance(function, SemanticFunction):
                continue
            self._analyze_prepared_template_specialization(function)
