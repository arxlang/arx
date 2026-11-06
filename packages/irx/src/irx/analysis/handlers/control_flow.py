# mypy: disable-error-code=no-redef

"""
title: Control-flow semantic visitors.
summary: >-
  Handle returns, loops, and branch-level validation while using shared
  registry helpers for lexical declarations introduced by loops.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import astx

from astx.types import AnyType as AstxAnyType
from plum import dispatch
from public import private

from irx.analysis.arrow_conversion import arrow_ownership
from irx.analysis.class_lifecycle import (
    CONTEXT_ENTER_HOOK,
    CONTEXT_EXIT_HOOK,
    class_ownership,
)
from irx.analysis.dependencies.control_flow import ControlFlowAnalysisServices
from irx.analysis.iterables import resolve_iteration_capability
from irx.analysis.normalization import normalize_flags, normalize_operator
from irx.analysis.numeric_literals import contextualize_literal
from irx.analysis.ownership import (
    list_resource_ownership,
    resource_ownership,
    string_resource_ownership,
    symbol_resource_ownership,
    transfer_resource_ownership,
)
from irx.analysis.resolved_nodes import (
    ImplicitConversion,
    MethodDispatchKind,
    OwnershipEscapeKind,
    OwnershipKind,
    OwnershipTransferKind,
    ResolvedContextManager,
    ResolvedGeneratorFunction,
    ResolvedMethodCall,
    ResolvedYield,
    SemanticClass,
    SemanticSymbol,
)
from irx.analysis.types import (
    display_type_name,
    is_assignable,
    is_boolean_type,
    is_float_type,
    is_integer_type,
    is_none_type,
    is_string_type,
)
from irx.analysis.validation import (
    resolve_return,
    validate_assignment,
    validate_call,
)
from irx.diagnostics import DiagnosticCodes
from irx.extensions.handlers import configuration_error
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class ControlFlowAnalysis:
    """
    title: Process control flow in the current compilation phase.
    attributes:
      services:
        type: ControlFlowAnalysisServices
    """

    services: ControlFlowAnalysisServices

    def __init__(self, services: ControlFlowAnalysisServices) -> None:
        """
        title: Bind one feature to explicit compilation-owned dependencies.
        parameters:
          services:
            type: ControlFlowAnalysisServices
        """
        self.services = services

    def _resolve_return_resource_ownership(
        self,
        node: astx.FunctionReturn,
    ) -> None:
        """
        title: Resolve ownership transfer for one list-valued return.
        parameters:
          node:
            type: astx.FunctionReturn
        """
        self.services.semantic(node).resource_ownership = None
        if self.services.context.current_function is None:
            return
        if node.value is None:
            return
        return_type = (
            self.services.context.current_function.signature.return_type
        )
        if isinstance(return_type, astx.DataFrameType | astx.SeriesType):
            self.services.set_resource_ownership(
                node,
                arrow_ownership(
                    return_type,
                    OwnershipKind.OWNED,
                    transfer=OwnershipTransferKind.COPY,
                ),
            )
            return
        if isinstance(return_type, astx.ClassType):
            self.services.set_resource_ownership(
                node,
                class_ownership(
                    OwnershipKind.OWNED,
                    transfer=OwnershipTransferKind.COPY,
                    escape=OwnershipEscapeKind.RETURN,
                ),
            )
            return
        if is_string_type(return_type):
            self._resolve_string_return_resource_ownership(node)
            return
        if isinstance(return_type, astx.GeneratorType):
            ownership = resource_ownership(node.value)
            if ownership is None or ownership.kind is not OwnershipKind.OWNED:
                self.services.context.diagnostics.add(
                    "return a freshly owned generator, "
                    "not a borrowed iterator",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                )
                return
            moved = transfer_resource_ownership(
                ownership,
                transfer_kind=OwnershipTransferKind.MOVE,
                escape_kind=OwnershipEscapeKind.RETURN,
            )
            self.services.set_resource_ownership(node.value, moved)
            self.services.set_resource_ownership(node, moved)
            return
        if not isinstance(return_type, (astx.ListType, astx.Bytes)):
            return

        value_ownership = resource_ownership(node.value)
        if value_ownership is None:
            self.services.context.diagnostics.add(
                "list return expression is missing ownership metadata",
                node=node.value,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return

        source_symbol = getattr(
            getattr(node.value, "semantic", None),
            "resolved_symbol",
            None,
        )
        source_ownership = (
            symbol_resource_ownership(source_symbol)
            if isinstance(source_symbol, SemanticSymbol)
            else None
        )
        source_symbol_id: str | None
        if value_ownership.kind is OwnershipKind.BORROWED:
            if (
                not isinstance(source_symbol, SemanticSymbol)
                or source_ownership is None
                or source_ownership.kind is not OwnershipKind.OWNED
            ):
                self.services.context.diagnostics.add(
                    "cannot return a borrowed list as an owned result",
                    node=node.value,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                    notes=(
                        "return a locally owned list or a freshly owned list "
                        "expression",
                    ),
                )
                return
            source_symbol_id = source_symbol.symbol_id
            moved = list_resource_ownership(
                OwnershipKind.OWNED,
                owner_symbol_id=source_symbol_id,
                source_symbol_id=source_symbol_id,
                transfer_kind=OwnershipTransferKind.MOVE,
                escape_kind=OwnershipEscapeKind.RETURN,
            )
        elif value_ownership.kind is OwnershipKind.OWNED:
            source_symbol_id = value_ownership.source_symbol_id
            moved = transfer_resource_ownership(
                value_ownership,
                transfer_kind=OwnershipTransferKind.MOVE,
                escape_kind=OwnershipEscapeKind.RETURN,
            )
        else:
            self.services.context.diagnostics.add(
                "cannot return static list storage as an owned result",
                node=node.value,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return

        self.services.set_resource_ownership(node.value, moved)
        self.services.set_resource_ownership(
            node,
            list_resource_ownership(
                OwnershipKind.OWNED,
                source_symbol_id=source_symbol_id,
                transfer_kind=OwnershipTransferKind.MOVE,
                escape_kind=OwnershipEscapeKind.RETURN,
            ),
        )

    def _resolve_string_return_resource_ownership(
        self,
        node: astx.FunctionReturn,
    ) -> None:
        """
        title: Resolve ownership transfer for one string-valued return.
        parameters:
          node:
            type: astx.FunctionReturn
        """
        if node.value is None:
            return
        value_ownership = resource_ownership(node.value)
        if value_ownership is None:
            self.services.context.diagnostics.add(
                "string return expression is missing ownership metadata",
                node=node.value,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return

        source_symbol = getattr(
            getattr(node.value, "semantic", None),
            "resolved_symbol",
            None,
        )
        source_ownership = (
            symbol_resource_ownership(source_symbol)
            if isinstance(source_symbol, SemanticSymbol)
            else None
        )
        source_symbol_id: str | None = None
        if value_ownership.kind is OwnershipKind.BORROWED:
            if (
                isinstance(source_symbol, SemanticSymbol)
                and source_ownership is not None
                and source_ownership.kind is OwnershipKind.STATIC
            ):
                moved = string_resource_ownership(
                    OwnershipKind.OWNED,
                    source_symbol_id=source_symbol.symbol_id,
                    transfer_kind=OwnershipTransferKind.COPY,
                    escape_kind=OwnershipEscapeKind.RETURN,
                )
            elif (
                isinstance(source_symbol, SemanticSymbol)
                and source_ownership is not None
                and source_ownership.kind is OwnershipKind.OWNED
            ):
                source_symbol_id = source_symbol.symbol_id
                moved = string_resource_ownership(
                    OwnershipKind.OWNED,
                    owner_symbol_id=source_symbol_id,
                    source_symbol_id=source_symbol_id,
                    transfer_kind=OwnershipTransferKind.MOVE,
                    escape_kind=OwnershipEscapeKind.RETURN,
                )
            else:
                self.services.context.diagnostics.add(
                    "cannot return a borrowed string as an owned result",
                    node=node.value,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                    notes=(
                        "return a literal, a locally owned string, or a "
                        "freshly allocated string expression",
                    ),
                )
                return
        elif value_ownership.kind is OwnershipKind.STATIC:
            moved = string_resource_ownership(
                OwnershipKind.OWNED,
                transfer_kind=OwnershipTransferKind.COPY,
                escape_kind=OwnershipEscapeKind.RETURN,
            )
        else:
            source_symbol_id = value_ownership.source_symbol_id
            moved = transfer_resource_ownership(
                value_ownership,
                transfer_kind=OwnershipTransferKind.MOVE,
                escape_kind=OwnershipEscapeKind.RETURN,
            )

        self.services.set_resource_ownership(node.value, moved)
        self.services.set_resource_ownership(
            node,
            string_resource_ownership(
                OwnershipKind.OWNED,
                source_symbol_id=source_symbol_id,
                transfer_kind=moved.transfer_kind,
                escape_kind=OwnershipEscapeKind.RETURN,
            ),
        )

    def _current_generator(
        self,
        node: astx.AST,
    ) -> ResolvedGeneratorFunction | None:
        """
        title: Return the active generator metadata, if any.
        parameters:
          node:
            type: astx.AST
        returns:
          type: ResolvedGeneratorFunction | None
        """
        function = self.services.context.current_function
        if function is None:
            self.services.context.diagnostics.add(
                "Yield statement outside function.",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_CONTROL_FLOW,
            )
            return None

        generator = function.signature.metadata.get("generator")
        if isinstance(generator, ResolvedGeneratorFunction):
            return generator

        self.services.context.diagnostics.add(
            f"Function '{function.name}' must declare GeneratorType[...] "
            "to use yield",
            node=node,
            code=DiagnosticCodes.SEMANTIC_INVALID_CONTROL_FLOW,
        )
        return None

    def _yield_value_type(self, value: astx.AST | None) -> astx.DataType:
        """
        title: Analyze and return one yielded value type.
        parameters:
          value:
            type: astx.AST | None
        returns:
          type: astx.DataType
        """
        if value is None:
            return astx.NoneType()
        self.services.visit(value)
        value_type = self.services.expr_type(value)
        return value_type if value_type is not None else astx.NoneType()

    def _resolve_yield(
        self,
        node: astx.AST,
        value: astx.AST | None,
    ) -> ResolvedYield | None:
        """
        title: Resolve one yield statement or expression.
        parameters:
          node:
            type: astx.AST
          value:
            type: astx.AST | None
        returns:
          type: ResolvedYield | None
        """
        generator = self._current_generator(node)
        value_type = self._yield_value_type(value)
        if generator is None:
            self.services.set_type(node, None)
            return None

        conversion = None
        if not is_assignable(generator.yield_type, value_type):
            self.services.context.diagnostics.add(
                "yield expects "
                f"{display_type_name(generator.yield_type)} but got "
                f"{display_type_name(value_type)}",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        elif not is_none_type(value_type):
            conversion = ImplicitConversion(
                source_type=value_type,
                target_type=generator.yield_type,
            )

        try:
            site_index = generator.yield_nodes.index(node)
        except ValueError:
            site_index = -1

        resolved = ResolvedYield(
            generator=generator,
            expected_type=generator.yield_type,
            value_type=value_type,
            site_index=site_index,
            implicit_conversion=conversion,
        )
        self.services.set_yield(node, resolved)
        return resolved

    def _resolve_context_method(
        self,
        node: astx.WithStmt,
        class_: SemanticClass,
        method_name: str,
        manager_type: astx.DataType,
    ) -> ResolvedMethodCall | None:
        """
        title: Resolve one context-manager protocol method.
        parameters:
          node:
            type: astx.WithStmt
          class_:
            type: SemanticClass
          method_name:
            type: str
          manager_type:
            type: astx.DataType
        returns:
          type: ResolvedMethodCall | None
        """
        resolved_overload = self.services.resolve_method_overload(
            class_,
            method_name,
            [],
            is_static=False,
            node=node,
        )
        if resolved_overload is None:
            return None

        member, candidates = resolved_overload
        function = member.lowered_function
        if function is None:
            raise TypeError(
                f"context manager method '{method_name}' must have a "
                "lowered function"
            )

        visible_function = self.services.visible_method_function(
            class_,
            member,
        )
        if function.template_params:
            specialized_function = (
                self.services.resolve_template_method_call_target(
                    function,
                    visible_function,
                    [],
                    node,
                )
            )
            if specialized_function is None:
                return None
            visible_function = self.services.specialize_signature(
                visible_function,
                self.services.specialization_bindings_map(
                    specialized_function
                ),
            )
            function = specialized_function

        call_resolution = validate_call(
            self.services.context.diagnostics,
            function=visible_function,
            arg_types=[],
            node=node,
            binding_function=function,
        )
        dispatch_kind = MethodDispatchKind.DIRECT
        if member.dispatch_slot is not None:
            dispatch_kind = MethodDispatchKind.INDIRECT

        return ResolvedMethodCall(
            class_=class_,
            member=member,
            function=function,
            overload_key=(member.signature_key or member.qualified_name),
            dispatch_kind=dispatch_kind,
            call=call_resolution,
            candidates=candidates,
            receiver_type=manager_type,
            receiver_class=class_,
            slot_index=member.dispatch_slot,
        )

    def _declare_context_target(
        self,
        target: astx.AST,
        enter_type: astx.DataType,
    ) -> SemanticSymbol | None:
        """
        title: Declare one with-statement target binding.
        parameters:
          target:
            type: astx.AST
          enter_type:
            type: astx.DataType
        returns:
          type: SemanticSymbol | None
        """
        if is_none_type(enter_type):
            self.services.context.diagnostics.add(
                "with target requires __enter__ to return a value",
                node=target,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return None

        if isinstance(target, astx.Identifier):
            symbol = self.services.registry.declare_local(
                target.name,
                enter_type,
                is_mutable=False,
                declaration=target,
                kind="with",
            )
            self.services.set_symbol(target, symbol)
            return symbol

        if not isinstance(
            target,
            (astx.InlineVariableDeclaration, astx.VariableDeclaration),
        ):
            self.services.context.diagnostics.add(
                "with target must be an identifier or inline variable "
                "declaration",
                node=target,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return None

        if target.value is not None and not isinstance(
            target.value,
            astx.Undefined,
        ):
            self.services.context.diagnostics.add(
                "with target declaration must not define an initializer",
                node=target,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )

        if isinstance(target.type_, AstxAnyType):
            target.type_ = enter_type
        else:
            self.services.resolve_declared_type(target.type_, node=target)
            if not is_assignable(target.type_, enter_type):
                self.services.context.diagnostics.add(
                    "with target "
                    f"'{target.name}' expects "
                    f"{display_type_name(target.type_)} but __enter__ "
                    f"returns {display_type_name(enter_type)}",
                    node=target,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )

        symbol = self.services.registry.declare_local(
            target.name,
            target.type_,
            is_mutable=target.mutability != astx.MutabilityKind.constant,
            declaration=target,
            kind="with",
        )
        self.services.set_symbol(target, symbol)
        return symbol

    def _validate_boolean_condition(
        self,
        condition: astx.AST,
        *,
        label: str,
    ) -> None:
        """
        title: Validate a control-flow condition is Boolean.
        parameters:
          condition:
            type: astx.AST
          label:
            type: str
        """
        if not self.services.require_value_expression(
            condition, context=label
        ):
            return
        condition_type = self.services.expr_type(condition)
        if condition_type is None or is_boolean_type(condition_type):
            return
        self.services.context.diagnostics.add(
            f"{label} condition must be Boolean, got "
            f"{display_type_name(condition_type)}",
            node=condition,
            code=DiagnosticCodes.SEMANTIC_INVALID_CONDITION,
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
            f"unsupported {type(node).__name__} in ControlFlowAnalysis"
        )

    @dispatch
    def visit(self, node: astx.AssertStmt) -> None:
        """
        title: Visit AssertStmt nodes.
        parameters:
          node:
            type: astx.AssertStmt
        """
        self.services.visit(node.condition)
        self._validate_boolean_condition(node.condition, label="assert")

        if node.message is not None:
            self.services.visit(node.message)
            if self.services.require_value_expression(
                node.message,
                context="AssertStmt message",
            ):
                message_type = self.services.expr_type(node.message)
                if not (
                    is_string_type(message_type)
                    or is_integer_type(message_type)
                    or is_float_type(message_type)
                    or is_boolean_type(message_type)
                ):
                    self.services.context.diagnostics.add(
                        "unsupported AssertStmt message type "
                        f"{display_type_name(message_type)}",
                        node=node.message,
                        code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                    )

        self.services.set_type(node, None)

    @dispatch
    def visit(self, node: astx.FunctionReturn) -> None:
        """
        title: Visit FunctionReturn nodes.
        parameters:
          node:
            type: astx.FunctionReturn
        """
        if self.services.context.current_function is None:
            self.services.context.diagnostics.add(
                "Return statement outside function.",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_RETURN,
            )
            return
        expected = self.services.context.current_function.signature.return_type
        if isinstance(expected, astx.NullableType) and isinstance(
            node.value, astx.LiteralNone
        ):
            node.value = astx.Cast(node.value, expected)
            node.value.loc = node.value.value.loc
        generator = (
            self.services.context.current_function.signature.metadata.get(
                "generator"
            )
        )
        if isinstance(generator, ResolvedGeneratorFunction):
            if node.value is not None:
                self.services.visit(node.value)
            value_type = self.services.expr_type(node.value)
            if node.value is not None and not is_none_type(value_type):
                self.services.context.diagnostics.add(
                    "generator functions may only use bare return or "
                    "return None in this phase",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_INVALID_RETURN,
                )
            self.services.set_type(node, None)
            return
        if node.value is not None:
            contextualize_literal(node.value, expected)
            self.services.visit(node.value)
        return_resolution = resolve_return(
            self.services.context.diagnostics,
            function=self.services.context.current_function,
            value=node.value,
            value_type=self.services.expr_type(node.value),
            node=node,
        )
        self.services.set_return(node, return_resolution)
        self.services.set_type(node, return_resolution.expected_type)
        self._resolve_return_resource_ownership(node)

    @dispatch
    def visit(self, node: astx.YieldStmt) -> None:
        """
        title: Visit YieldStmt nodes.
        parameters:
          node:
            type: astx.YieldStmt
        """
        self._resolve_yield(node, node.value)
        self.services.set_type(node, None)

    @dispatch
    def visit(self, node: astx.YieldExpr) -> None:
        """
        title: Visit YieldExpr nodes.
        parameters:
          node:
            type: astx.YieldExpr
        """
        self._resolve_yield(node, node.value)
        self.services.set_type(node, astx.NoneType())

    @dispatch
    def visit(self, node: astx.YieldFromExpr) -> None:
        """
        title: Visit YieldFromExpr nodes.
        parameters:
          node:
            type: astx.YieldFromExpr
        """
        self.services.context.diagnostics.add(
            "yield from is not supported yet",
            node=node,
            code=DiagnosticCodes.SEMANTIC_INVALID_CONTROL_FLOW,
        )
        self.services.visit(node.value)
        self.services.set_type(node, astx.NoneType())

    @dispatch
    def visit(self, node: astx.IfStmt) -> None:
        """
        title: Visit IfStmt nodes.
        parameters:
          node:
            type: astx.IfStmt
        """
        self.services.visit(node.condition)
        self._validate_boolean_condition(node.condition, label="if")
        known = (
            node.condition.value
            if isinstance(node.condition, astx.LiteralBoolean)
            else None
        )
        with self.services.context.constant_diagnostics(known is True):
            self.services.visit(node.then)
        if node.else_ is not None:
            with self.services.context.constant_diagnostics(known is False):
                self.services.visit(node.else_)
        self.services.set_type(node, None)

    @dispatch
    def visit(self, node: astx.WhileStmt) -> None:
        """
        title: Visit WhileStmt nodes.
        parameters:
          node:
            type: astx.WhileStmt
        """
        self.services.visit(node.condition)
        self._validate_boolean_condition(node.condition, label="while")
        with self.services.context.in_loop():
            with self.services.context.constant_diagnostics(False):
                self.services.visit(node.body)
        self.services.set_type(node, None)

    @dispatch
    def visit(self, node: astx.ForCountLoopStmt) -> None:
        """
        title: Visit ForCountLoopStmt nodes.
        parameters:
          node:
            type: astx.ForCountLoopStmt
        """
        with self.services.context.scope("for-count"):
            if node.initializer.value is not None:
                contextualize_literal(
                    node.initializer.value, node.initializer.type_
                )
                self.services.visit(node.initializer.value)
            symbol = self.services.registry.declare_local(
                node.initializer.name,
                node.initializer.type_,
                is_mutable=(
                    node.initializer.mutability != astx.MutabilityKind.constant
                ),
                declaration=node.initializer,
            )
            self.services.set_symbol(node.initializer, symbol)
            self.services.visit(node.condition)
            self._validate_boolean_condition(
                node.condition,
                label="for-count loop",
            )
            with self.services.context.constant_diagnostics(False):
                self.services.visit(node.update)
            if isinstance(node.update, astx.AugAssign):
                plan = self.services.semantic(
                    node.update
                ).resolved_aug_assignment
                if (
                    plan is not None
                    and plan.target.symbol_id != symbol.symbol_id
                ):
                    self.services.context.diagnostics.add(
                        "compound count-loop update must target "
                        "the induction binding",
                        node=node.update,
                        code=DiagnosticCodes.SEMANTIC_INVALID_ASSIGNMENT_TARGET,
                    )
            with self.services.context.in_loop():
                with self.services.context.constant_diagnostics(False):
                    self.services.visit(node.body)
        self.services.set_type(node, None)

    @dispatch
    def visit(self, node: astx.ForRangeLoopStmt) -> None:
        """
        title: Visit ForRangeLoopStmt nodes.
        parameters:
          node:
            type: astx.ForRangeLoopStmt
        """
        loop_type = node.variable.type_
        self.services.resolve_declared_type(loop_type, node=node.variable)
        if not (is_integer_type(loop_type) or is_float_type(loop_type)):
            self.services.context.diagnostics.add(
                "for-range requires a numeric variable", node=node
            )
            return
        self.services.set_operator(
            node,
            normalize_operator(
                "+",
                result_type=loop_type,
                lhs_type=loop_type,
                rhs_type=loop_type,
                flags=normalize_flags(
                    node, lhs_type=loop_type, rhs_type=loop_type
                ),
            ),
        )
        with self.services.context.scope("for-range"):
            for value in (node.start, node.end, node.step):
                if isinstance(value, astx.LiteralNone):
                    continue
                contextualize_literal(value, loop_type)
                self.services.visit(value)
                validate_assignment(
                    self.services.context.diagnostics,
                    target_name="range variable",
                    target_type=loop_type,
                    value_type=self.services.expr_type(value),
                    node=value,
                )
            symbol = self.services.registry.declare_local(
                node.variable.name,
                node.variable.type_,
                is_mutable=(
                    node.variable.mutability != astx.MutabilityKind.constant
                ),
                declaration=node.variable,
            )
            self.services.set_symbol(node.variable, symbol)
            with self.services.context.in_loop():
                with self.services.context.constant_diagnostics(False):
                    self.services.visit(node.body)
        self.services.set_type(node, None)

    @dispatch
    def visit(self, node: astx.ForInLoopStmt) -> None:
        """
        title: Visit ForInLoopStmt nodes.
        parameters:
          node:
            type: astx.ForInLoopStmt
        """
        with self.services.context.scope("for-in"):
            self.services.visit(node.iterable)
            iterable_type = self.services.expr_type(node.iterable)
            iteration = resolve_iteration_capability(
                node.iterable,
                iterable_type,
            )
            if iteration is None:
                self.services.context.diagnostics.add(
                    "for-in requires an iterable value, got "
                    f"{display_type_name(iterable_type)}",
                    node=node.iterable,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
                self.services.set_iteration(node, None)
                self.services.set_type(node, None)
                return

            symbol = self.services.declare_iteration_target(
                node.target,
                iteration.element_type,
                kind="for-in",
                iteration_kind=iteration.kind,
            )
            resolved_iteration = replace(iteration, target_symbol=symbol)
            self.services.set_iteration(node.iterable, resolved_iteration)
            self.services.set_iteration(node, resolved_iteration)
            with (
                self.services.context.in_loop(),
                self.services.context.list_iteration(
                    iteration.borrowed_owner_symbol_id
                ),
            ):
                with self.services.context.constant_diagnostics(False):
                    self.services.visit(node.body)
        self.services.set_type(node, None)

    @dispatch
    def visit(self, node: astx.WithStmt) -> None:
        """
        title: Visit WithStmt nodes.
        parameters:
          node:
            type: astx.WithStmt
        """
        self.services.visit(node.manager)
        if not self.services.require_value_expression(
            node.manager,
            context="with manager",
        ):
            self.services.set_type(node, None)
            return

        manager_type = self.services.expr_type(node.manager)
        class_ = self.services.resolve_class_from_type(
            manager_type,
            node=node.manager,
            unknown_message="with manager uses unknown class '{name}'",
        )
        if class_ is None:
            if not isinstance(manager_type, astx.ClassType):
                self.services.context.diagnostics.add(
                    "with manager requires a class value, got "
                    f"{display_type_name(manager_type)}",
                    node=node.manager,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
            with self.services.context.scope("with"):
                with self.services.context.constant_diagnostics(False):
                    self.services.visit(node.body)
            self.services.set_type(node, None)
            return

        resolved_manager_type = cast(astx.DataType, manager_type)
        enter = self._resolve_context_method(
            node,
            class_,
            CONTEXT_ENTER_HOOK.name,
            resolved_manager_type,
        )
        exit_ = self._resolve_context_method(
            node,
            class_,
            CONTEXT_EXIT_HOOK.name,
            resolved_manager_type,
        )

        target_symbol = None
        with self.services.context.scope("with"):
            if node.target is not None and enter is not None:
                target_symbol = self._declare_context_target(
                    node.target,
                    enter.call.result_type,
                )
            with self.services.context.constant_diagnostics(False):
                self.services.visit(node.body)

        if enter is not None and exit_ is not None:
            self.services.set_context_manager(
                node,
                ResolvedContextManager(
                    class_=class_,
                    manager_type=resolved_manager_type,
                    enter=enter,
                    exit=exit_,
                    target_symbol=target_symbol,
                ),
            )
        else:
            self.services.set_context_manager(node, None)
        self.services.set_type(node, None)

    @dispatch
    def visit(self, node: astx.BreakStmt) -> None:
        """
        title: Visit BreakStmt nodes.
        parameters:
          node:
            type: astx.BreakStmt
        """
        if self.services.context.loop_depth <= 0:
            self.services.context.diagnostics.add(
                "Break statement outside loop.",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_CONTROL_FLOW,
            )
        self.services.set_type(node, None)

    @dispatch
    def visit(self, node: astx.ContinueStmt) -> None:
        """
        title: Visit ContinueStmt nodes.
        parameters:
          node:
            type: astx.ContinueStmt
        """
        if self.services.context.loop_depth <= 0:
            self.services.context.diagnostics.add(
                "Continue statement outside loop.",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_CONTROL_FLOW,
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
                "irx.analysis.control_flow." + node_type.__name__,
                "irx.analysis.control_flow",
                "analysis",
                node_type,
                self.visit,
                source=__name__ + ".ControlFlowAnalysis.visit",
            )
            for node_type in (
                astx.AssertStmt,
                astx.FunctionReturn,
                astx.YieldStmt,
                astx.YieldExpr,
                astx.YieldFromExpr,
                astx.IfStmt,
                astx.WhileStmt,
                astx.ForCountLoopStmt,
                astx.ForRangeLoopStmt,
                astx.ForInLoopStmt,
                astx.WithStmt,
                astx.BreakStmt,
                astx.ContinueStmt,
            )
        )
