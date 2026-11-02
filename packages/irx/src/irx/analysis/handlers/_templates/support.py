"""
title: Template-specialization support helpers.
summary: >-
  Provide shared type identity, substitution, and binding-formatting helpers
  for template specialization.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable, cast

import astx

from irx.analysis.handlers.base import SemanticVisitorMixinBase
from irx.analysis.module_symbols import specialized_function_basename
from irx.analysis.resolved_nodes import (
    SemanticFunction,
    TemplateArgumentBinding,
    TemplateSpecializationKey,
)
from irx.analysis.types import (
    clone_type,
    display_type_name,
    same_type,
    substitute_type,
)
from irx.typecheck import typechecked


@typechecked
class TemplateSupportVisitorMixin(SemanticVisitorMixinBase):
    """
    title: Template-specialization support helpers
    """

    def _type_identity_name(self, type_: astx.DataType) -> str:
        """
        title: Return one deterministic type identity string.
        parameters:
          type_:
            type: astx.DataType
        returns:
          type: str
        """
        if isinstance(type_, astx.StructType):
            return type_.qualified_name or type_.name
        if isinstance(type_, astx.ClassType):
            return type_.qualified_name or type_.name
        if isinstance(type_, astx.NamespaceType):
            return type_.module_key
        if isinstance(type_, astx.OpaqueHandleType):
            return type_.handle_name
        if isinstance(type_, astx.UnionType):
            if type_.alias_name is not None:
                return type_.alias_name
            return "_or_".join(
                self._type_identity_name(member) for member in type_.members
            )
        if isinstance(type_, astx.TemplateTypeVar):
            return type_.name
        if isinstance(type_, (astx.ListType, astx.TupleType)):
            members = "_".join(
                self._type_identity_name(cast(astx.DataType, item))
                for item in type_.element_types
            )
            size = getattr(type_, "size", None)
            return f"{type(type_).__name__}_{members}_{size}"
        if isinstance(type_, astx.NullableType):
            return "Nullable_" + self._type_identity_name(type_.value_type)
        if isinstance(type_, astx.GeneratorType):
            return "Generator_" + self._type_identity_name(type_.yield_type)
        if isinstance(
            type_,
            (
                astx.SequenceType,
                astx.SeriesType,
                astx.TensorType,
                astx.BufferViewType,
            ),
        ):
            element = type_.element_type
            member = (
                "Any" if element is None else self._type_identity_name(element)
            )
            return (
                f"{type(type_).__name__}_{member}_"
                f"{getattr(type_, 'nullable', False)}_"
                f"{getattr(type_, 'shape', None)}_"
                f"{getattr(type_, 'size', None)}"
            )
        if isinstance(type_, astx.PointerType):
            return "Pointer_" + (
                "Any"
                if type_.pointee_type is None
                else self._type_identity_name(type_.pointee_type)
            )
        return str(type_.__class__.__name__)

    def _template_specialization_key(
        self,
        function: SemanticFunction,
        concrete_args: tuple[astx.DataType, ...],
    ) -> TemplateSpecializationKey:
        """
        title: Return one stable specialization key for a template function.
        parameters:
          function:
            type: SemanticFunction
          concrete_args:
            type: tuple[astx.DataType, Ellipsis]
        returns:
          type: TemplateSpecializationKey
        """
        return TemplateSpecializationKey(
            qualified_name=function.qualified_name,
            arg_type_names=tuple(
                self._type_identity_name(type_) for type_ in concrete_args
            ),
        )

    def _template_specialization_name(
        self,
        function: SemanticFunction,
        concrete_args: tuple[astx.DataType, ...],
    ) -> str:
        """
        title: Return one deterministic specialization function basename.
        parameters:
          function:
            type: SemanticFunction
          concrete_args:
            type: tuple[astx.DataType, Ellipsis]
        returns:
          type: str
        """
        key = self._template_specialization_key(function, concrete_args)
        return specialized_function_basename(function.name, key.arg_type_names)

    def _template_specialization_symbol_name(
        self,
        function: SemanticFunction,
        concrete_args: tuple[astx.DataType, ...],
    ) -> str:
        """
        title: Return one deterministic lowered specialization symbol name.
        parameters:
          function:
            type: SemanticFunction
          concrete_args:
            type: tuple[astx.DataType, Ellipsis]
        returns:
          type: str
        """
        key = self._template_specialization_key(function, concrete_args)
        base_name = function.signature.symbol_name or function.name
        return specialized_function_basename(base_name, key.arg_type_names)

    def _template_param_domain(
        self,
        param: astx.TemplateParam,
    ) -> tuple[astx.DataType, ...]:
        """
        title: Return the finite admissible type domain for one template param.
        parameters:
          param:
            type: astx.TemplateParam
        returns:
          type: tuple[astx.DataType, Ellipsis]
        """
        bound = param.bound
        if isinstance(bound, astx.UnionType):
            return tuple(clone_type(member) for member in bound.members)
        return (clone_type(bound),)

    def _type_within_template_bound(
        self,
        type_: astx.DataType,
        bound: astx.DataType,
    ) -> bool:
        """
        title: Return whether one concrete type satisfies one template bound.
        parameters:
          type_:
            type: astx.DataType
          bound:
            type: astx.DataType
        returns:
          type: bool
        """
        if isinstance(bound, astx.UnionType):
            return any(
                self._type_within_template_bound(type_, member)
                for member in bound.members
            )
        return same_type(type_, bound)

    def _substitute_type(
        self,
        type_: astx.DataType,
        bindings: dict[str, astx.DataType],
    ) -> astx.DataType:
        """
        title: Substitute template variables inside one type.
        parameters:
          type_:
            type: astx.DataType
          bindings:
            type: dict[str, astx.DataType]
        returns:
          type: astx.DataType
        """
        return substitute_type(type_, bindings)

    def _template_bindings_map(
        self,
        function: SemanticFunction,
        concrete_args: tuple[astx.DataType, ...],
    ) -> dict[str, astx.DataType]:
        """
        title: Return the concrete binding map for one specialization.
        parameters:
          function:
            type: SemanticFunction
          concrete_args:
            type: tuple[astx.DataType, Ellipsis]
        returns:
          type: dict[str, astx.DataType]
        """
        return {
            param.name: clone_type(argument)
            for param, argument in zip(function.template_params, concrete_args)
        }

    def _specialization_bindings_map(
        self,
        function: SemanticFunction,
    ) -> dict[str, astx.DataType]:
        """
        title: Return the concrete binding map stored on one specialization.
        parameters:
          function:
            type: SemanticFunction
        returns:
          type: dict[str, astx.DataType]
        """
        return {
            binding.name: clone_type(binding.type_)
            for binding in function.template_bindings
        }

    def _specialize_signature(
        self,
        function: SemanticFunction,
        bindings: dict[str, astx.DataType],
    ) -> SemanticFunction:
        """
        title: Return one visible callable wrapper with substituted types.
        parameters:
          function:
            type: SemanticFunction
          bindings:
            type: dict[str, astx.DataType]
        returns:
          type: SemanticFunction
        """
        signature = replace(
            function.signature,
            parameters=tuple(
                replace(
                    parameter,
                    type_=self._substitute_type(parameter.type_, bindings),
                )
                for parameter in function.signature.parameters
            ),
            return_type=self._substitute_type(
                function.signature.return_type,
                bindings,
            ),
        )
        return replace(
            function,
            return_type=clone_type(signature.return_type),
            signature=signature,
        )

    def _format_template_bindings(
        self,
        bindings: Iterable[TemplateArgumentBinding],
    ) -> str:
        """
        title: Render one template-binding set for diagnostics.
        parameters:
          bindings:
            type: Iterable[TemplateArgumentBinding]
        returns:
          type: str
        """
        return ", ".join(
            f"{binding.name} = {display_type_name(binding.type_)}"
            for binding in bindings
        )
