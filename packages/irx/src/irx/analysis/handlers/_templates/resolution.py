"""
title: Template-specialization resolution helpers.
summary: >-
  Resolve template arguments and map function or method calls onto concrete
  specializations.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import astx

from public import private

from irx.analysis.call_arguments import argument_slots
from irx.analysis.dependencies.template_resolution import (
    TemplateResolutionAnalysisServices,
)
from irx.analysis.handlers._templates.state import (
    _SPECIALIZATION_ANALYZED_ATTR,
)
from irx.analysis.resolved_nodes import SemanticFunction
from irx.analysis.types import (
    clone_type,
    display_type_name,
    same_type,
    sequence_element_type,
)
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@private
@typechecked
class TemplateResolutionAnalysis:
    """
    title: Template-specialization argument and call-target resolution helpers
    attributes:
      services:
        type: TemplateResolutionAnalysisServices
    """

    services: TemplateResolutionAnalysisServices

    def __init__(self, services: TemplateResolutionAnalysisServices) -> None:
        """
        title: Bind one feature to explicit compilation-owned dependencies.
        parameters:
          services:
            type: TemplateResolutionAnalysisServices
        """
        self.services = services

    def _collect_inferred_template_bindings(
        self,
        expected_type: astx.DataType,
        actual_type: astx.DataType | None,
        inferred: dict[str, astx.DataType],
        *,
        function: SemanticFunction,
        node: astx.AST,
        diagnose: bool = True,
    ) -> bool:
        """
        title: Collect inferred template arguments from one parameter pair.
        parameters:
          expected_type:
            type: astx.DataType
          actual_type:
            type: astx.DataType | None
          inferred:
            type: dict[str, astx.DataType]
          function:
            type: SemanticFunction
          node:
            type: astx.AST
          diagnose:
            type: bool
        returns:
          type: bool
        """
        if isinstance(expected_type, astx.TemplateTypeVar):
            if actual_type is None:
                if diagnose:
                    self.services.context.diagnostics.add(
                        "Cannot infer template argument "
                        f"'{expected_type.name}' "
                        f"for call to '{function.name}'",
                        node=node,
                        code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                    )
                return False
            previous = inferred.get(expected_type.name)
            if previous is None:
                inferred[expected_type.name] = actual_type
                return True
            if same_type(previous, actual_type):
                return True
            if diagnose:
                self.services.context.diagnostics.add(
                    "Conflicting inferences for template argument "
                    f"'{expected_type.name}' in call to '{function.name}'",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
            return False
        if isinstance(expected_type, astx.ListType) and isinstance(
            actual_type, astx.ListType
        ):
            if len(expected_type.element_types) != len(
                actual_type.element_types
            ):
                return False
            return all(
                self._collect_inferred_template_bindings(
                    cast(astx.DataType, expected),
                    cast(astx.DataType, actual),
                    inferred,
                    function=function,
                    node=node,
                    diagnose=diagnose,
                )
                for expected, actual in zip(
                    expected_type.element_types, actual_type.element_types
                )
            )
        if isinstance(expected_type, astx.SequenceType):
            return self._collect_inferred_template_bindings(
                expected_type.element_type,
                sequence_element_type(actual_type),
                inferred,
                function=function,
                node=node,
                diagnose=diagnose,
            )
        if isinstance(expected_type, astx.NullableType) and isinstance(
            actual_type, astx.NullableType
        ):
            return self._collect_inferred_template_bindings(
                expected_type.value_type,
                actual_type.value_type,
                inferred,
                function=function,
                node=node,
                diagnose=diagnose,
            )
        if isinstance(expected_type, astx.SeriesType) and isinstance(
            actual_type, astx.SeriesType
        ):
            if (
                expected_type.element_type is None
                or actual_type.element_type is None
            ):
                return True
            return self._collect_inferred_template_bindings(
                expected_type.element_type,
                actual_type.element_type,
                inferred,
                function=function,
                node=node,
                diagnose=diagnose,
            )
        if isinstance(expected_type, astx.PointerType) and isinstance(
            actual_type,
            astx.PointerType,
        ):
            if (
                expected_type.pointee_type is None
                or actual_type.pointee_type is None
            ):
                return True
            return self._collect_inferred_template_bindings(
                expected_type.pointee_type,
                actual_type.pointee_type,
                inferred,
                function=function,
                node=node,
                diagnose=diagnose,
            )
        if isinstance(expected_type, astx.BufferViewType) and isinstance(
            actual_type,
            astx.BufferViewType,
        ):
            if (
                expected_type.element_type is None
                or actual_type.element_type is None
            ):
                return True
            return self._collect_inferred_template_bindings(
                expected_type.element_type,
                actual_type.element_type,
                inferred,
                function=function,
                node=node,
                diagnose=diagnose,
            )
        if isinstance(expected_type, astx.TensorType) and isinstance(
            actual_type,
            astx.TensorType,
        ):
            if (
                expected_type.element_type is None
                or actual_type.element_type is None
            ):
                return True
            return self._collect_inferred_template_bindings(
                expected_type.element_type,
                actual_type.element_type,
                inferred,
                function=function,
                node=node,
                diagnose=diagnose,
            )
        return True

    def _resolve_template_arguments(
        self,
        function: SemanticFunction,
        arg_types: list[astx.DataType | None],
        node: astx.AST,
        *,
        diagnose: bool = True,
    ) -> tuple[astx.DataType, ...] | None:
        """
        title: Resolve explicit or inferred template arguments for one call.
        parameters:
          function:
            type: SemanticFunction
          arg_types:
            type: list[astx.DataType | None]
          node:
            type: astx.AST
          diagnose:
            type: bool
        returns:
          type: tuple[astx.DataType, Ellipsis] | None
        """
        explicit_args = astx.get_template_args(node)
        params = function.template_params
        if explicit_args is not None:
            if len(explicit_args) != len(params):
                if diagnose:
                    self.services.context.diagnostics.add(
                        f"Call to '{function.name}' supplies "
                        f"{len(explicit_args)} template arguments but expects "
                        f"{len(params)}",
                        node=node,
                        code=DiagnosticCodes.SEMANTIC_CALL_ARITY,
                    )
                return None
            concrete_args = tuple(clone_type(arg) for arg in explicit_args)
        else:
            inferred: dict[str, astx.DataType] = {}
            slots = argument_slots(
                function,
                node,
                self.services.context.diagnostics if diagnose else None,
            )
            if slots is None:
                return None
            for slot, arg_type in zip(slots, arg_types):
                if slot >= len(function.signature.parameters):
                    continue
                parameter = function.signature.parameters[slot]
                if not self._collect_inferred_template_bindings(
                    parameter.type_,
                    arg_type,
                    inferred,
                    function=function,
                    node=node,
                    diagnose=diagnose,
                ):
                    return None
            missing = [
                param.name for param in params if param.name not in inferred
            ]
            if missing:
                if diagnose:
                    missing_text = ", ".join(missing)
                    self.services.context.diagnostics.add(
                        f"Cannot infer template argument(s) {missing_text} "
                        f"for call to '{function.name}'",
                        node=node,
                        code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                    )
                return None
            concrete_args = tuple(
                clone_type(inferred[param.name]) for param in params
            )

        for param, argument in zip(params, concrete_args):
            if self.services.type_within_template_bound(argument, param.bound):
                continue
            if diagnose:
                self.services.context.diagnostics.add(
                    f"Template argument '{display_type_name(argument)}' does "
                    f"not satisfy bound '{display_type_name(param.bound)}' "
                    f"for parameter '{param.name}' in '{function.name}'",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
            return None
        return concrete_args

    def _resolve_template_call_target(
        self,
        function: SemanticFunction,
        arg_types: list[astx.DataType | None],
        node: astx.AST,
    ) -> SemanticFunction | None:
        """
        title: Resolve one template function call to a concrete specialization.
        parameters:
          function:
            type: SemanticFunction
          arg_types:
            type: list[astx.DataType | None]
          node:
            type: astx.AST
        returns:
          type: SemanticFunction | None
        """
        concrete_args = self._resolve_template_arguments(
            function,
            arg_types,
            node,
        )
        if concrete_args is None:
            return None
        specialization = self.services.build_template_specialization(
            function,
            concrete_args,
        )
        if specialization is None:
            return None
        definition = specialization.definition
        if definition is not None and not getattr(
            definition,
            _SPECIALIZATION_ANALYZED_ATTR,
            False,
        ):
            analyze_prepared = getattr(
                self,
                "_analyze_prepared_template_specialization",
                None,
            )
            if callable(analyze_prepared):
                analyze_prepared(specialization)
        return specialization

    def _resolve_template_method_call_target(
        self,
        function: SemanticFunction,
        visible_function: SemanticFunction,
        arg_types: list[astx.DataType | None],
        node: astx.AST,
    ) -> SemanticFunction | None:
        """
        title: Resolve one template method call to a concrete specialization.
        parameters:
          function:
            type: SemanticFunction
          visible_function:
            type: SemanticFunction
          arg_types:
            type: list[astx.DataType | None]
          node:
            type: astx.AST
        returns:
          type: SemanticFunction | None
        """
        visible_template = replace(
            visible_function,
            template_params=function.template_params,
        )
        concrete_args = self._resolve_template_arguments(
            visible_template,
            arg_types,
            node,
        )
        if concrete_args is None:
            return None
        specialization = self.services.build_template_specialization(
            function,
            concrete_args,
        )
        if specialization is None:
            return None
        definition = specialization.definition
        if definition is not None and not getattr(
            definition,
            _SPECIALIZATION_ANALYZED_ATTR,
            False,
        ):
            analyze_prepared = getattr(
                self,
                "_analyze_prepared_template_specialization",
                None,
            )
            if callable(analyze_prepared):
                analyze_prepared(specialization)
        return specialization
