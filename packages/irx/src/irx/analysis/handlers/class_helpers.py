"""
title: Shared class-member semantic helpers.
summary: >-
  Provide reusable class-member formatting and owner-resolution helpers for
  declaration and expression visitor mixins.
"""

from __future__ import annotations

from public import private

from irx.analysis.dependencies.class_member_formatting import (
    ClassMemberFormattingAnalysisServices,
)
from irx.analysis.resolved_nodes import SemanticClass, SemanticClassMember
from irx.analysis.types import display_type_name
from irx.typecheck import typechecked

CLASS_QUALIFIED_NAME_SEPARATOR = "::class::"


@private
@typechecked
class ClassMemberFormattingAnalysis:
    """
    title: Shared class-member semantic helpers.
    attributes:
      services:
        type: ClassMemberFormattingAnalysisServices
    """

    services: ClassMemberFormattingAnalysisServices

    def __init__(
        self, services: ClassMemberFormattingAnalysisServices
    ) -> None:
        """
        title: Bind one feature to explicit compilation-owned dependencies.
        parameters:
          services:
            type: ClassMemberFormattingAnalysisServices
        """
        self.services = services

    def _member_owner_module_key(
        self,
        member: SemanticClassMember,
    ) -> str:
        """
        title: Return the module key for one declaring class member.
        parameters:
          member:
            type: SemanticClassMember
        returns:
          type: str
        """
        return member.owner_qualified_name.partition(
            CLASS_QUALIFIED_NAME_SEPARATOR
        )[0]

    def _member_declaring_class(
        self,
        member: SemanticClassMember,
    ) -> SemanticClass | None:
        """
        title: Return the declaring class for one resolved class member.
        parameters:
          member:
            type: SemanticClassMember
        returns:
          type: SemanticClass | None
        """
        return self.services.context.get_class(
            self._member_owner_module_key(member),
            member.owner_name,
        )

    def _member_display_name(
        self,
        member: SemanticClassMember,
    ) -> str:
        """
        title: Return one class member name with its declaring owner.
        parameters:
          member:
            type: SemanticClassMember
        returns:
          type: str
        """
        return f"{member.owner_name}.{member.name}"

    def _format_method_signature(
        self,
        member: SemanticClassMember,
    ) -> str:
        """
        title: Return one human-facing method signature string.
        parameters:
          member:
            type: SemanticClassMember
        returns:
          type: str
        """
        if member.signature is None:
            return member.name
        parameters = ", ".join(
            display_type_name(parameter.type_)
            for parameter in member.signature.parameters
        )
        suffix = " static" if member.is_static else ""
        return (
            f"{member.name}({parameters}) -> "
            f"{display_type_name(member.signature.return_type)}{suffix}"
        )
