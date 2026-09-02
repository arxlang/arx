# mypy: disable-error-code=attr-defined
# mypy: disable-error-code=untyped-decorator

"""
title: Expression mutation helpers.
summary: >-
  Resolve assignment and mutation targets, including class-field mutation
  handling.
"""

from __future__ import annotations

from typing import cast

import astx

from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.handlers.class_helpers import (
    ClassMemberFormattingVisitorMixin,
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
    SemanticClassMember,
    SemanticInfo,
    SemanticSymbol,
)
from irx.analysis.types import is_string_type
from irx.analysis.validation import validate_assignment
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@typechecked
class ExpressionMutationVisitorMixin(ClassMemberFormattingVisitorMixin):
    """
    title: Expression helpers for assignment and mutation targets
    """

    def _class_member_target_symbol(
        self,
        target: astx.AST,
        member: SemanticClassMember,
        target_type: astx.DataType | None,
    ) -> SemanticSymbol:
        """
        title: >-
          Build one variable-like symbol for a resolved class field target.
        parameters:
          target:
            type: astx.AST
          member:
            type: SemanticClassMember
          target_type:
            type: astx.DataType | None
        returns:
          type: SemanticSymbol
        """
        declaring_class = self._member_declaring_class(member)
        module_key = (
            declaring_class.module_key
            if declaring_class is not None
            else self._member_owner_module_key(member)
        )
        symbol_type = member.type_ or cast(astx.DataType, target_type)
        symbol_kind = (
            "class_static_field" if member.is_static else "class_field"
        )
        return self.factory.make_variable_symbol(
            module_key,
            self._member_display_name(member),
            symbol_type,
            is_mutable=member.is_mutable,
            declaration=target,
            kind=symbol_kind,
        )

    def _resolve_mutation_target(
        self,
        target: astx.AST,
        *,
        node: astx.AST,
        action: str,
        invalid_message: str,
    ) -> tuple[SemanticSymbol, str, astx.DataType | None] | None:
        """
        title: >-
          Resolve one direct mutable target for assignment-like operations.
        parameters:
          target:
            type: astx.AST
          node:
            type: astx.AST
          action:
            type: str
          invalid_message:
            type: str
        returns:
          type: tuple[SemanticSymbol, str, astx.DataType | None] | None
        """
        target_type = self._expr_type(target)
        if isinstance(target, astx.Identifier):
            symbol = cast(
                SemanticInfo, getattr(target, "semantic", SemanticInfo())
            ).resolved_symbol
            if symbol is None:
                self.context.diagnostics.add(
                    invalid_message,
                    node=node,
                    code=(DiagnosticCodes.SEMANTIC_INVALID_ASSIGNMENT_TARGET),
                )
                return None
            target_name = symbol.name
            if not symbol.is_mutable:
                self.context.diagnostics.add(
                    f"Cannot {action} '{target_name}': declared as constant",
                    node=node,
                    code=(DiagnosticCodes.SEMANTIC_INVALID_ASSIGNMENT_TARGET),
                )
            return symbol, target_name, target_type

        if isinstance(target, astx.FieldAccess):
            semantic = getattr(target, "semantic", None)
            class_field_access = getattr(
                semantic,
                "resolved_class_field_access",
                None,
            )
            if class_field_access is not None:
                member = class_field_access.member
                target_name = self._member_display_name(member)
                symbol = self._class_member_target_symbol(
                    target,
                    member,
                    target_type,
                )
                if not member.is_mutable:
                    message = (
                        f"Cannot {action} '{target_name}': "
                        "declared as constant"
                    )
                    self.context.diagnostics.add(
                        message,
                        node=node,
                        code=(
                            DiagnosticCodes.SEMANTIC_INVALID_ASSIGNMENT_TARGET
                        ),
                    )
                return symbol, target_name, target_type

            if isinstance(
                target.value,
                (astx.BaseFieldAccess, astx.StaticFieldAccess),
            ):
                self.context.diagnostics.add(
                    invalid_message.replace(
                        "a variable or field",
                        "a direct variable or field",
                    ),
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_INVALID_ASSIGNMENT_TARGET,
                )
                return None

            symbol = self._root_assignment_symbol(target)
            target_name = target.field_name
            if symbol is None:
                self.context.diagnostics.add(
                    invalid_message,
                    node=node,
                    code=(DiagnosticCodes.SEMANTIC_INVALID_ASSIGNMENT_TARGET),
                )
                return None
            if not symbol.is_mutable:
                self.context.diagnostics.add(
                    f"Cannot {action} '{symbol.name}': declared as constant",
                    node=node,
                    code=(DiagnosticCodes.SEMANTIC_INVALID_ASSIGNMENT_TARGET),
                )
            return symbol, target_name, target_type

        if isinstance(target, astx.BaseFieldAccess):
            resolved_access = getattr(
                getattr(target, "semantic", None),
                "resolved_base_class_field_access",
                None,
            )
            if resolved_access is None:
                self.context.diagnostics.add(
                    invalid_message,
                    node=node,
                    code=(DiagnosticCodes.SEMANTIC_INVALID_ASSIGNMENT_TARGET),
                )
                return None
            member = resolved_access.member
            target_name = self._member_display_name(member)
            symbol = self._class_member_target_symbol(
                target,
                member,
                target_type,
            )
            if not member.is_mutable:
                self.context.diagnostics.add(
                    f"Cannot {action} '{target_name}': declared as constant",
                    node=node,
                    code=(DiagnosticCodes.SEMANTIC_INVALID_ASSIGNMENT_TARGET),
                )
            return symbol, target_name, target_type

        if isinstance(target, astx.StaticFieldAccess):
            resolved_access = getattr(
                getattr(target, "semantic", None),
                "resolved_static_class_field_access",
                None,
            )
            if resolved_access is None:
                self.context.diagnostics.add(
                    invalid_message,
                    node=node,
                    code=(DiagnosticCodes.SEMANTIC_INVALID_ASSIGNMENT_TARGET),
                )
                return None
            member = resolved_access.member
            target_name = self._member_display_name(member)
            symbol = self._class_member_target_symbol(
                target,
                member,
                target_type,
            )
            if not member.is_mutable:
                self.context.diagnostics.add(
                    f"Cannot {action} '{target_name}': declared as constant",
                    node=node,
                    code=(DiagnosticCodes.SEMANTIC_INVALID_ASSIGNMENT_TARGET),
                )
            return symbol, target_name, target_type

        self.context.diagnostics.add(
            invalid_message,
            node=node,
            code=DiagnosticCodes.SEMANTIC_INVALID_ASSIGNMENT_TARGET,
        )
        return None

    def _resolve_list_assignment_ownership(
        self,
        node: astx.AST,
        value: astx.AST,
        symbol: SemanticSymbol,
        *,
        target_name: str,
        target_type: astx.DataType | None,
        is_local: bool,
    ) -> None:
        """
        title: Validate and record one dynamic-list replacement transfer.
        parameters:
          node:
            type: astx.AST
          value:
            type: astx.AST
          symbol:
            type: SemanticSymbol
          target_name:
            type: str
          target_type:
            type: astx.DataType | None
          is_local:
            type: bool
        """
        if not isinstance(target_type, astx.ListType):
            return
        if not is_local:
            self.context.diagnostics.add(
                f"cannot assign list storage to field '{target_name}': "
                "object-field ownership and destruction are not supported",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return

        target_ownership = symbol_resource_ownership(symbol)
        value_ownership = resource_ownership(value)
        if (
            target_ownership is None
            or target_ownership.kind is not OwnershipKind.OWNED
        ):
            self.context.diagnostics.add(
                f"cannot replace list '{target_name}' because its storage "
                "is not locally owned",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        if (
            value_ownership is None
            or value_ownership.kind is not OwnershipKind.OWNED
        ):
            self.context.diagnostics.add(
                f"assignment to list '{target_name}' requires a freshly "
                "owned value; borrowed and static list copies are not "
                "supported",
                node=value,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return

        self._set_resource_ownership(
            value,
            transfer_resource_ownership(
                value_ownership,
                owner_symbol_id=symbol.symbol_id,
                transfer_kind=OwnershipTransferKind.MOVE,
            ),
        )
        self._set_resource_ownership(
            node,
            list_resource_ownership(
                OwnershipKind.OWNED,
                owner_symbol_id=symbol.symbol_id,
                transfer_kind=OwnershipTransferKind.MOVE,
            ),
        )

    def _resolve_string_assignment_ownership(
        self,
        node: astx.AST,
        value: astx.AST,
        symbol: SemanticSymbol,
        *,
        target_name: str,
        target_type: astx.DataType | None,
        is_local: bool,
    ) -> None:
        """
        title: Validate and record one string pointer replacement.
        parameters:
          node:
            type: astx.AST
          value:
            type: astx.AST
          symbol:
            type: SemanticSymbol
          target_name:
            type: str
          target_type:
            type: astx.DataType | None
          is_local:
            type: bool
        """
        if not is_string_type(target_type):
            return
        value_ownership = resource_ownership(value)
        if value_ownership is None:
            self.context.diagnostics.add(
                f"string assignment to '{target_name}' is missing value "
                "ownership metadata",
                node=value,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        value_kind = value_ownership.kind
        if value_kind is OwnershipKind.BORROWED:
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
                source_ownership is not None
                and source_ownership.kind is OwnershipKind.STATIC
            ):
                value_kind = OwnershipKind.STATIC
        if not is_local:
            if value_kind is OwnershipKind.OWNED:
                self.context.diagnostics.add(
                    f"cannot assign owned string storage to field "
                    f"'{target_name}': object-field destruction is not "
                    "supported",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                )
            return

        target_ownership = symbol_resource_ownership(symbol)
        if target_ownership is None:
            self.context.diagnostics.add(
                f"string target '{target_name}' is missing ownership metadata",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        if (
            target_ownership.kind is OwnershipKind.STATIC
            and value_kind is OwnershipKind.STATIC
        ):
            self._set_resource_ownership(
                node,
                string_resource_ownership(
                    OwnershipKind.STATIC,
                    owner_symbol_id=symbol.symbol_id,
                ),
            )
            return
        if (
            target_ownership.kind is not OwnershipKind.OWNED
            or value_kind is not OwnershipKind.OWNED
        ):
            self.context.diagnostics.add(
                f"assignment to string '{target_name}' must preserve its "
                "static or owned storage class; borrowed aliases and "
                "static/owned replacement are not supported",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return

        self._set_resource_ownership(
            value,
            transfer_resource_ownership(
                value_ownership,
                owner_symbol_id=symbol.symbol_id,
                transfer_kind=OwnershipTransferKind.MOVE,
            ),
        )
        self._set_resource_ownership(
            node,
            string_resource_ownership(
                OwnershipKind.OWNED,
                owner_symbol_id=symbol.symbol_id,
                transfer_kind=OwnershipTransferKind.MOVE,
            ),
        )

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.VariableAssignment) -> None:
        """
        title: Visit VariableAssignment nodes.
        parameters:
          node:
            type: astx.VariableAssignment
        """
        self.visit(node.value)
        symbol = self.context.scopes.resolve(node.name)
        if symbol is None:
            self.context.diagnostics.add(
                f"cannot assign to unresolved name '{node.name}'",
                node=node,
                code=DiagnosticCodes.SEMANTIC_UNRESOLVED_NAME,
            )
            return
        if not symbol.is_mutable:
            self.context.diagnostics.add(
                f"Cannot assign to '{node.name}': declared as constant",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_ASSIGNMENT_TARGET,
            )
        if self._require_value_expression(
            node.value,
            context=f"Assignment to '{node.name}'",
        ):
            validate_assignment(
                self.context.diagnostics,
                target_name=node.name,
                target_type=symbol.type_,
                value_type=self._expr_type(node.value),
                node=node,
            )
        self._set_symbol(node, symbol)
        self._set_assignment(node, symbol)
        self._set_type(node, symbol.type_)
        self._resolve_list_assignment_ownership(
            node,
            node.value,
            symbol,
            target_name=node.name,
            target_type=symbol.type_,
            is_local=True,
        )
        self._resolve_string_assignment_ownership(
            node,
            node.value,
            symbol,
            target_name=node.name,
            target_type=symbol.type_,
            is_local=True,
        )
