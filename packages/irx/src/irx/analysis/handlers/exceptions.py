# mypy: disable-error-code=attr-defined
# mypy: disable-error-code=untyped-decorator
# mypy: disable-error-code=no-redef
"""
title: Nominal exception statements and lexical handler bindings.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

import astx

from public import private

from irx.analysis.class_lifecycle import class_ownership, lifecycle_children
from irx.analysis.exception_types import exception_class_type, exception_error
from irx.analysis.flow import flow_outcomes
from irx.analysis.handlers.base import (
    SemanticAnalyzerCore,
    SemanticVisitorMixinBase,
)
from irx.analysis.resolved_nodes import (
    ExceptionCauseMode,
    OwnershipKind,
    ResolvedExceptionHandler,
    ResolvedExceptionType,
    ResolvedRaise,
    ResolvedTry,
    SemanticClass,
)
from irx.typecheck import typechecked


@private
@typechecked
def exception_source_nodes(node: astx.AST) -> Iterator[astx.AST]:
    """
    title: Inspect one exceptional region without crossing nested functions.
    parameters:
      node:
        type: astx.AST
    returns:
      type: Iterator[astx.AST]
    """
    if isinstance(node, astx.FunctionDef):
        return
    yield node
    for child in lifecycle_children(node):
        yield from exception_source_nodes(child)


@private
@typechecked
class ExceptionVisitorMixin(SemanticVisitorMixinBase):
    """
    title: Resolve exception statements before backend control-flow emission.
    """

    def reject_exception_references(
        self, node: astx.AST, symbols: set[str], message: str
    ) -> None:
        """
        title: Reject exceptional-path accesses to unavailable owned bindings.
        parameters:
          node:
            type: astx.AST
          symbols:
            type: set[str]
          message:
            type: str
        """
        for child in exception_source_nodes(node):
            if isinstance(child, astx.Identifier):
                symbol = self._semantic(child).resolved_symbol
            elif isinstance(child, astx.VariableAssignment):
                assignment = self._semantic(child).resolved_assignment
                symbol = assignment.target if assignment is not None else None
            else:
                continue
            if symbol is not None and symbol.symbol_id in symbols:
                exception_error(
                    cast(SemanticAnalyzerCore, self), child, message
                )

    def exception_value(self, node: astx.Expr) -> ResolvedExceptionType | None:
        """
        title: Require an ordinary instance of a registered exception subtype.
        parameters:
          node:
            type: astx.Expr
        returns:
          type: ResolvedExceptionType | None
        """
        self.visit(node)
        value_type = self._expr_type(node)
        if isinstance(value_type, astx.ClassType):
            class_ = self.context.get_class(
                value_type.module_key
                or self.context.current_module_key
                or "main",
                value_type.resolved_name or value_type.name,
            )
            if class_ is not None and class_.exception_type is not None:
                return class_.exception_type
        exception_error(
            cast(SemanticAnalyzerCore, self),
            node,
            "raised value or cause must be an exception instance",
        )
        return None

    def handler_type(self, node: astx.Expr) -> ResolvedExceptionType | None:
        """
        title: Resolve nominal type references using ordinary lexical bindings.
        parameters:
          node:
            type: astx.Expr
        returns:
          type: ResolvedExceptionType | None
        """
        class_: SemanticClass | None = None
        if isinstance(node, astx.Identifier):
            local = self.context.scopes.resolve(node.name)
            binding = self.bindings.resolve(node.name)
            if local is None and binding is not None:
                class_ = binding.class_
        elif isinstance(node, astx.FieldAccess):
            self.visit(node)
            info = self._semantic(node)
            member = info.resolved_module_member_access
            if member is not None:
                class_ = member.binding.class_
        if class_ is not None:
            class_ = self._resolve_class_definition(class_)
            canonical = self.context.get_class(class_.module_key, class_.name)
            if canonical is not None and canonical.exception_type is not None:
                self._set_class(node, canonical)
                return canonical.exception_type
        exception_error(
            cast(SemanticAnalyzerCore, self),
            node,
            "handler type must name an exception class",
        )
        return None

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.ThrowStmt) -> None:
        """
        title: Resolve explicit raises and dynamic bare re-raises.
        parameters:
          node:
            type: astx.ThrowStmt
        """
        info = self._semantic(node)
        info.resolved_raise = None
        self._set_type(node, None)
        self._semantic(node).flow_outcomes = flow_outcomes(node)
        if self.context.current_function is None:
            exception_error(
                cast(SemanticAnalyzerCore, self),
                node,
                "raise requires a function body",
            )
        exception_type = (
            self.exception_value(node.exception)
            if node.exception is not None
            else None
        )
        mode = ExceptionCauseMode.IMPLICIT
        cause_type = None
        if node.cause is not None:
            if node.exception is None:
                exception_error(
                    cast(SemanticAnalyzerCore, self),
                    node,
                    "bare raise cannot specify a cause",
                )
            if isinstance(node.cause, astx.LiteralNone):
                self.visit(node.cause)
                mode = ExceptionCauseMode.SUPPRESS
            else:
                mode = ExceptionCauseMode.EXPLICIT
                cause_type = self.exception_value(node.cause)
        info.resolved_raise = ResolvedRaise(exception_type, mode, cause_type)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.CatchHandlerStmt) -> None:
        """
        title: Bind a handler-local owned reference and validate its body.
        parameters:
          node:
            type: astx.CatchHandlerStmt
        """
        info = self._semantic(node)
        info.resolved_exception_handler = None
        self._set_type(node, None)
        self._semantic(node).flow_outcomes = flow_outcomes(node)
        if not getattr(self.context, "exception_region_depth", 0):
            exception_error(
                cast(SemanticAnalyzerCore, self),
                node,
                "except requires an enclosing try statement",
            )
        resolved: list[ResolvedExceptionType] = []
        if node.types is not None:
            if not node.types.nodes:
                exception_error(
                    cast(SemanticAnalyzerCore, self),
                    node,
                    "handler type list cannot be empty",
                )
            for reference in node.types:
                item = self.handler_type(reference)
                if item is not None:
                    resolved.append(item)
        root = self.context.runtime_exception_types.get("BaseException")
        if root is None:
            exception_error(
                cast(SemanticAnalyzerCore, self),
                node,
                "exception handlers require registered BaseException",
            )
            return
        binding = root
        if resolved:
            shared = next(
                (
                    name
                    for name in resolved[0].ancestry
                    if all(name in item.ancestry for item in resolved)
                ),
                root.class_.qualified_name,
            )
            shared_class = next(
                (
                    item
                    for item in self.context.classes.values()
                    if item.qualified_name == shared
                ),
                root.class_,
            )
            binding = shared_class.exception_type or root
        binding_type = exception_class_type(binding.class_)
        with self.context.scope("except"):
            symbol = None
            if node.name is not None:
                symbol = self.factory.make_variable_symbol(
                    self.context.current_module_key or "main",
                    node.name.name,
                    binding_type,
                    is_mutable=False,
                    declaration=node,
                    kind="exception",
                )
                self.context.scopes.declare(symbol)
                self._set_symbol(node.name, symbol)
                self._set_type(node.name, binding_type)
                self._set_resource_ownership(
                    node, class_ownership(OwnershipKind.OWNED)
                )
            info.resolved_exception_handler = ResolvedExceptionHandler(
                tuple(resolved), symbol, binding_type
            )
            self.visit(node.body)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.FinallyHandlerStmt) -> None:
        """
        title: Validate a finalizer in its own lexical initialization scope.
        parameters:
          node:
            type: astx.FinallyHandlerStmt
        """
        self._set_type(node, None)
        self._semantic(node).flow_outcomes = flow_outcomes(node)
        if not self.context.exception_region_depth:
            exception_error(
                cast(SemanticAnalyzerCore, self),
                node,
                "finally requires an enclosing try statement",
            )
        with self.context.scope("finally"):
            self.visit(node.body)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.ExceptionHandlerStmt) -> None:
        """
        title: Validate ordered handlers and isolated exceptional scopes.
        parameters:
          node:
            type: astx.ExceptionHandlerStmt
        """
        info = self._semantic(node)
        info.resolved_try = None
        self._set_type(node, None)
        self._semantic(node).flow_outcomes = flow_outcomes(node)
        core = cast(SemanticAnalyzerCore, self)
        if self.context.current_function is None:
            exception_error(core, node, "try requires a function body")
        from irx.analysis.handlers._declarations.functions import (  # noqa: PLC0415
            _nested_yield_nodes,
        )

        if _nested_yield_nodes(node):
            exception_error(
                core,
                node,
                "generator suspension in protected regions is unsupported",
            )
        if not node.handlers.nodes and node.finally_handler is None:
            exception_error(core, node, "try requires except or finally")
        if node.else_body is not None and not node.handlers.nodes:
            exception_error(core, node, "try else requires an except handler")
        self.context.exception_region_depth += 1
        plans: list[ResolvedExceptionHandler] = []
        try:
            with self.context.scope("try"):
                self.visit(node.body)
                if node.else_body is not None:
                    scope = self.context.scopes.current
                    direct = {id(child) for child in node.body.nodes}
                    conditional = (
                        {
                            symbol.symbol_id
                            for symbol in scope.symbols.values()
                            if id(symbol.declaration) not in direct
                        }
                        if scope is not None
                        else set()
                    )
                    with self.context.scope("else"):
                        self.visit(node.else_body)
                        self.reject_exception_references(
                            node.else_body,
                            conditional,
                            "try local is not definitely initialized and "
                            "owned across normal completion",
                        )
            for index, handler in enumerate(node.handlers):
                if (
                    handler.types is None
                    and index != len(node.handlers.nodes) - 1
                ):
                    exception_error(core, handler, "bare except must be last")
                self.visit(handler)
                plan = self._semantic(handler).resolved_exception_handler
                if plan is not None:
                    plans.append(plan)
            if node.finally_handler is not None:
                self.visit(node.finally_handler)
                protected: list[astx.AST] = [node.body, *node.handlers]
                if node.else_body is not None:
                    protected.append(node.else_body)
                moved_lists: set[str] = set()
                for region in protected:
                    for child in exception_source_nodes(region):
                        if not isinstance(child, astx.FunctionReturn):
                            continue
                        if child.value is None or not isinstance(
                            self._expr_type(child.value), astx.ListType
                        ):
                            continue
                        ownership = self._semantic(child).resource_ownership
                        if (
                            ownership is not None
                            and ownership.source_symbol_id is not None
                        ):
                            moved_lists.add(ownership.source_symbol_id)
                self.reject_exception_references(
                    node.finally_handler,
                    moved_lists,
                    "finally cannot reuse a list moved by a pending return; "
                    "use a fresh owned list instead",
                )
        finally:
            self.context.exception_region_depth -= 1
        info.resolved_try = ResolvedTry(tuple(plans))
