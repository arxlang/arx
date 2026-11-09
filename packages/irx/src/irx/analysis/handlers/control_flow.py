# mypy: disable-error-code=no-redef

"""
title: Control-flow semantic visitors.
summary: >-
  Handle returns, loops, and branch-level validation while using shared
  registry helpers for lexical declarations introduced by loops.
"""

from __future__ import annotations

from dataclasses import replace

import astx

from astx.types import AnyType as AstxAnyType

from irx.analysis.arrow_conversion import arrow_ownership
from irx.analysis.class_lifecycle import (
    CONTEXT_ENTER_HOOK,
    CONTEXT_EXIT_HOOK,
    class_ownership,
)
from irx.analysis.handlers.base import (
    SemanticAnalyzerCore,
    SemanticVisitorMixinBase,
)
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
    OwnershipEscapeKind,
    OwnershipKind,
    OwnershipTransferKind,
    ResolvedContextManager,
    ResolvedGeneratorFunction,
    ResolvedYield,
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
)
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@typechecked
class ControlFlowVisitorMixin(SemanticVisitorMixinBase):
    """
    title: Process control flow in the current compilation phase.
    """

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
        self._semantic(node).resource_ownership = None
        if self.context.current_function is None:
            return
        if node.value is None:
            return
        return_type = self.context.current_function.signature.return_type
        if isinstance(return_type, astx.DataFrameType | astx.SeriesType):
            self._set_resource_ownership(
                node,
                arrow_ownership(
                    return_type,
                    OwnershipKind.OWNED,
                    transfer=OwnershipTransferKind.COPY,
                ),
            )
            return
        if isinstance(return_type, astx.ClassType):
            self._set_resource_ownership(
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
                self.context.diagnostics.add(
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
            self._set_resource_ownership(node.value, moved)
            self._set_resource_ownership(node, moved)
            return
        if not isinstance(return_type, (astx.ListType, astx.Bytes)):
            return

        value_ownership = resource_ownership(node.value)
        if value_ownership is None:
            self.context.diagnostics.add(
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
                self.context.diagnostics.add(
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
            self.context.diagnostics.add(
                "cannot return static list storage as an owned result",
                node=node.value,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return

        self._set_resource_ownership(node.value, moved)
        self._set_resource_ownership(
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
            self.context.diagnostics.add(
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
                self.context.diagnostics.add(
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

        self._set_resource_ownership(node.value, moved)
        self._set_resource_ownership(
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
        function = self.context.current_function
        if function is None:
            self.context.diagnostics.add(
                "Yield statement outside function.",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_CONTROL_FLOW,
            )
            return None

        generator = function.signature.metadata.get("generator")
        if isinstance(generator, ResolvedGeneratorFunction):
            return generator

        self.context.diagnostics.add(
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
        self.visit(value)
        value_type = self._expr_type(value)
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
            self._set_type(node, None)
            return None

        conversion = None
        if not is_assignable(generator.yield_type, value_type):
            self.context.diagnostics.add(
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
        self._set_yield(node, resolved)
        return resolved

    def _declare_context_target(
        self,
        node: astx.WithStmt,
        enter_call: astx.MethodCall,
    ) -> astx.VariableDeclaration | None:
        """
        title: Bind an already analyzed enter result with ordinary ownership.
        summary: >-
          Even an ignored owning result needs a local owner. Source targets
          retain their declared type and mutability; identifier targets are
          immutable bindings, not immutable objects.
        parameters:
          node:
            type: astx.WithStmt
          enter_call:
            type: astx.MethodCall
        returns:
          type: astx.VariableDeclaration | None
        """
        enter_type = self._expr_type(enter_call)
        if enter_type is None:
            return None
        target = node.target
        if is_none_type(enter_type):
            if target is not None:
                self.context.diagnostics.add(
                    "with target requires __enter__ to return a value",
                    node=target,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
            return None

        name = "$with.value"
        type_ = enter_type
        mutability = astx.MutabilityKind.constant
        if isinstance(target, astx.Identifier):
            name = target.name
        elif isinstance(
            target, (astx.VariableDeclaration, astx.InlineVariableDeclaration)
        ):
            if target.value is not None and not isinstance(
                target.value, astx.Undefined
            ):
                self.context.diagnostics.add(
                    "with target declaration must not define an initializer",
                    node=target,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
                return None
            name = target.name
            mutability = target.mutability
            if type(target.type_) is not AstxAnyType and not isinstance(
                target.type_, astx.InferredType
            ):
                type_ = target.type_
                self._resolve_declared_type(type_, node=target)
                validate_assignment(
                    self.context.diagnostics,
                    target_name=name,
                    target_type=type_,
                    value_type=enter_type,
                    node=target,
                )
        elif target is not None:
            self.context.diagnostics.add(
                "with target must be an identifier or inline variable "
                "declaration",
                node=target,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return None

        binding = astx.VariableDeclaration(
            name,
            type_,
            mutability=mutability,
            value=enter_call,
            loc=node.loc if target is None else target.loc,
        )
        symbol = self.registry.declare_local(
            name,
            type_,
            is_mutable=mutability != astx.MutabilityKind.constant,
            declaration=binding,
            kind="with",
        )
        self._set_symbol(binding, symbol)
        self._resolve_local_resource_ownership(binding, symbol)
        if target is not None:
            self._set_symbol(target, symbol)
            self._set_resource_ownership(target, resource_ownership(binding))
        return binding

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
        if not self._require_value_expression(condition, context=label):
            return
        condition_type = self._expr_type(condition)
        if condition_type is None or is_boolean_type(condition_type):
            return
        self.context.diagnostics.add(
            f"{label} condition must be Boolean, got "
            f"{display_type_name(condition_type)}",
            node=condition,
            code=DiagnosticCodes.SEMANTIC_INVALID_CONDITION,
        )

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.AssertStmt) -> None:
        """
        title: Visit AssertStmt nodes.
        parameters:
          node:
            type: astx.AssertStmt
        """
        self.visit(node.condition)
        self._validate_boolean_condition(node.condition, label="assert")

        if node.message is not None:
            self.visit(node.message)
            if self._require_value_expression(
                node.message,
                context="AssertStmt message",
            ):
                message_type = self._expr_type(node.message)
                if not (
                    is_string_type(message_type)
                    or is_integer_type(message_type)
                    or is_float_type(message_type)
                    or is_boolean_type(message_type)
                ):
                    self.context.diagnostics.add(
                        "unsupported AssertStmt message type "
                        f"{display_type_name(message_type)}",
                        node=node.message,
                        code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                    )

        self._set_type(node, None)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.FunctionReturn) -> None:
        """
        title: Visit FunctionReturn nodes.
        parameters:
          node:
            type: astx.FunctionReturn
        """
        if self.context.current_function is None:
            self.context.diagnostics.add(
                "Return statement outside function.",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_RETURN,
            )
            return
        expected = self.context.current_function.signature.return_type
        if isinstance(expected, astx.NullableType) and isinstance(
            node.value, astx.LiteralNone
        ):
            node.value = astx.Cast(node.value, expected)
            node.value.loc = node.value.value.loc
        generator = self.context.current_function.signature.metadata.get(
            "generator"
        )
        if isinstance(generator, ResolvedGeneratorFunction):
            if node.value is not None:
                self.visit(node.value)
            value_type = self._expr_type(node.value)
            if node.value is not None and not is_none_type(value_type):
                self.context.diagnostics.add(
                    "generator functions may only use bare return or "
                    "return None in this phase",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_INVALID_RETURN,
                )
            self._set_type(node, None)
            return
        if node.value is not None:
            contextualize_literal(node.value, expected)
            self.visit(node.value)
        return_resolution = resolve_return(
            self.context.diagnostics,
            function=self.context.current_function,
            value=node.value,
            value_type=self._expr_type(node.value),
            node=node,
        )
        self._set_return(node, return_resolution)
        self._set_type(node, return_resolution.expected_type)
        self._resolve_return_resource_ownership(node)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.YieldStmt) -> None:
        """
        title: Visit YieldStmt nodes.
        parameters:
          node:
            type: astx.YieldStmt
        """
        self._resolve_yield(node, node.value)
        self._set_type(node, None)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.YieldExpr) -> None:
        """
        title: Visit YieldExpr nodes.
        parameters:
          node:
            type: astx.YieldExpr
        """
        self._resolve_yield(node, node.value)
        self._set_type(node, astx.NoneType())

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.YieldFromExpr) -> None:
        """
        title: Visit YieldFromExpr nodes.
        parameters:
          node:
            type: astx.YieldFromExpr
        """
        self.context.diagnostics.add(
            "yield from is not supported yet",
            node=node,
            code=DiagnosticCodes.SEMANTIC_INVALID_CONTROL_FLOW,
        )
        self.visit(node.value)
        self._set_type(node, astx.NoneType())

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.IfStmt) -> None:
        """
        title: Visit IfStmt nodes.
        parameters:
          node:
            type: astx.IfStmt
        """
        self.visit(node.condition)
        self._validate_boolean_condition(node.condition, label="if")
        known = (
            node.condition.value
            if isinstance(node.condition, astx.LiteralBoolean)
            else None
        )
        with self.context.constant_diagnostics(known is True):
            self.visit(node.then)
        if node.else_ is not None:
            with self.context.constant_diagnostics(known is False):
                self.visit(node.else_)
        self._set_type(node, None)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.WhileStmt) -> None:
        """
        title: Visit WhileStmt nodes.
        parameters:
          node:
            type: astx.WhileStmt
        """
        self.visit(node.condition)
        self._validate_boolean_condition(node.condition, label="while")
        with self.context.in_loop():
            with self.context.constant_diagnostics(False):
                self.visit(node.body)
        self._set_type(node, None)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.ForCountLoopStmt) -> None:
        """
        title: Visit ForCountLoopStmt nodes.
        parameters:
          node:
            type: astx.ForCountLoopStmt
        """
        with self.context.scope("for-count"):
            self.visit(node.initializer)
            symbol = self._semantic(node.initializer).resolved_symbol
            if symbol is None:
                return
            self.visit(node.condition)
            self._validate_boolean_condition(
                node.condition,
                label="for-count loop",
            )
            with self.context.constant_diagnostics(False):
                self.visit(node.update)
            if isinstance(node.update, astx.AugAssign):
                plan = self._semantic(node.update).resolved_aug_assignment
                if (
                    plan is not None
                    and plan.target.symbol_id != symbol.symbol_id
                ):
                    self.context.diagnostics.add(
                        "compound count-loop update must target "
                        "the induction binding",
                        node=node.update,
                        code=DiagnosticCodes.SEMANTIC_INVALID_ASSIGNMENT_TARGET,
                    )
            with self.context.in_loop():
                with self.context.constant_diagnostics(False):
                    self.visit(node.body)
        self._set_type(node, None)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.ForRangeLoopStmt) -> None:
        """
        title: Visit ForRangeLoopStmt nodes.
        parameters:
          node:
            type: astx.ForRangeLoopStmt
        """
        loop_type = node.variable.type_
        self._resolve_declared_type(loop_type, node=node.variable)
        if not (is_integer_type(loop_type) or is_float_type(loop_type)):
            self.context.diagnostics.add(
                "for-range requires a numeric variable", node=node
            )
            return
        self._set_operator(
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
        with self.context.scope("for-range"):
            for value in (node.start, node.end, node.step):
                if isinstance(value, astx.LiteralNone):
                    continue
                contextualize_literal(value, loop_type)
                self.visit(value)
                validate_assignment(
                    self.context.diagnostics,
                    target_name="range variable",
                    target_type=loop_type,
                    value_type=self._expr_type(value),
                    node=value,
                )
            symbol = self.registry.declare_local(
                node.variable.name,
                node.variable.type_,
                is_mutable=(
                    node.variable.mutability != astx.MutabilityKind.constant
                ),
                declaration=node.variable,
            )
            self._set_symbol(node.variable, symbol)
            with self.context.in_loop():
                with self.context.constant_diagnostics(False):
                    self.visit(node.body)
        self._set_type(node, None)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.ForInLoopStmt) -> None:
        """
        title: Visit ForInLoopStmt nodes.
        parameters:
          node:
            type: astx.ForInLoopStmt
        """
        with self.context.scope("for-in"):
            self.visit(node.iterable)
            iterable_type = self._expr_type(node.iterable)
            iteration = resolve_iteration_capability(
                node.iterable,
                iterable_type,
            )
            if iteration is None:
                self.context.diagnostics.add(
                    "for-in requires an iterable value, got "
                    f"{display_type_name(iterable_type)}",
                    node=node.iterable,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
                self._set_iteration(node, None)
                self._set_type(node, None)
                return

            symbol = self._declare_iteration_target(
                node.target,
                iteration.element_type,
                kind="for-in",
                iteration_kind=iteration.kind,
            )
            resolved_iteration = replace(iteration, target_symbol=symbol)
            self._set_iteration(node.iterable, resolved_iteration)
            self._set_iteration(node, resolved_iteration)
            with (
                self.context.in_loop(),
                self.context.list_iteration(
                    iteration.borrowed_owner_symbol_id
                ),
            ):
                with self.context.constant_diagnostics(False):
                    self.visit(node.body)
        self._set_type(node, None)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.WithStmt) -> None:
        """
        title: Resolve a pinned manager, owning enter result, and checked exit.
        summary: >-
          __enter__ is called without explicit arguments using normal defaults.
          __exit__ takes exactly one Boolean completion argument and returns
          none. Manager and entered-value lifetimes use ordinary local stores;
          each source manager and enter call is analyzed once.
        parameters:
          node:
            type: astx.WithStmt
        """
        self._set_context_manager(node, None)
        self._set_type(node, None)
        if self.context.current_function is None:
            self.context.diagnostics.add(
                "with scopes require a function body",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_CONTROL_FLOW,
            )
            return
        errors_before = len(self.context.diagnostics.diagnostics)
        with self.context.scope("with"):
            self.visit(node.manager)
            if not self._require_value_expression(
                node.manager, context="with manager"
            ):
                return
            manager_type = self._expr_type(node.manager)
            if manager_type is None:
                return
            class_ = self._resolve_class_from_type(
                manager_type,
                node=node.manager,
                unknown_message="with manager uses unknown class '{name}'",
            )
            if class_ is None:
                if not isinstance(manager_type, astx.ClassType):
                    self.context.diagnostics.add(
                        "with manager requires a class value, got "
                        f"{display_type_name(manager_type)}",
                        node=node.manager,
                        code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                    )
                return

            manager_binding = astx.VariableDeclaration(
                "$with.manager",
                manager_type,
                mutability=astx.MutabilityKind.constant,
                value=node.manager,
                loc=node.manager.loc,
            )
            manager_symbol = self.registry.declare_local(
                manager_binding.name,
                manager_type,
                is_mutable=False,
                declaration=manager_binding,
            )
            self._set_symbol(manager_binding, manager_symbol)
            self._resolve_local_resource_ownership(
                manager_binding, manager_symbol
            )
            enter_call = astx.MethodCall(
                astx.Identifier(manager_binding.name, loc=node.manager.loc),
                CONTEXT_ENTER_HOOK.name,
                [],
            )
            enter_call.loc = node.loc
            self.visit(enter_call)
            enter = self._semantic(enter_call).resolved_method_call
            if enter is None:
                return
            value_binding = self._declare_context_target(node, enter_call)
            success_binding = astx.VariableDeclaration(
                "$with.success",
                astx.Boolean(),
                mutability=astx.MutabilityKind.constant,
                value=astx.LiteralBoolean(False),
                loc=node.loc,
            )
            self.visit(success_binding)
            exit_call = astx.MethodCall(
                astx.Identifier(manager_binding.name, loc=node.manager.loc),
                CONTEXT_EXIT_HOOK.name,
                [astx.Identifier(success_binding.name, loc=node.loc)],
            )
            exit_call.loc = node.loc
            self.visit(exit_call)
            exit_ = self._semantic(exit_call).resolved_method_call
            if exit_ is None:
                return
            signature = exit_.call.signature
            if (
                len(signature.parameters) != 1
                or not is_boolean_type(signature.parameters[0].type_)
                or not is_none_type(signature.return_type)
                or signature.is_variadic
            ):
                self.context.diagnostics.add(
                    "context __exit__ must take exactly one bool completion "
                    "argument and return none; exception suppression is "
                    "unsupported",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
            with self.context.constant_diagnostics(False):
                self.visit(node.body)
            if len(self.context.diagnostics.diagnostics) != errors_before:
                return
            target_symbol = (
                None
                if node.target is None
                else self._semantic(node.target).resolved_symbol
            )
            self._set_context_manager(
                node,
                ResolvedContextManager(
                    class_=class_,
                    manager_type=manager_type,
                    enter=enter,
                    exit=exit_,
                    manager_binding=manager_binding,
                    enter_call=enter_call,
                    value_binding=value_binding,
                    success_binding=success_binding,
                    exit_call=exit_call,
                    target_symbol=target_symbol,
                ),
            )

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.BreakStmt) -> None:
        """
        title: Visit BreakStmt nodes.
        parameters:
          node:
            type: astx.BreakStmt
        """
        if self.context.loop_depth <= 0:
            self.context.diagnostics.add(
                "Break statement outside loop.",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_CONTROL_FLOW,
            )
        self._set_type(node, None)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.ContinueStmt) -> None:
        """
        title: Visit ContinueStmt nodes.
        parameters:
          node:
            type: astx.ContinueStmt
        """
        if self.context.loop_depth <= 0:
            self.context.diagnostics.add(
                "Continue statement outside loop.",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_CONTROL_FLOW,
            )
        self._set_type(node, None)
