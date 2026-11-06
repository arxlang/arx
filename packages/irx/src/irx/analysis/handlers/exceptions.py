# mypy: disable-error-code=no-redef
"""
title: Nominal exception statements and lexical handler bindings.
"""

from __future__ import annotations

from collections.abc import Iterator

import astx

from plum import dispatch
from public import private

from irx.analysis.class_lifecycle import class_ownership, lifecycle_children
from irx.analysis.dependencies.exception import ExceptionAnalysisServices
from irx.analysis.exception_types import exception_class_type
from irx.analysis.flow import flow_outcomes
from irx.analysis.resolved_nodes import (
    ExceptionCauseMode,
    OwnershipKind,
    ResolvedExceptionHandler,
    ResolvedExceptionType,
    ResolvedRaise,
    ResolvedTry,
    SemanticClass,
)
from irx.extensions.handlers import configuration_error
from irx.extensions.nodes import NodeHandler, contribute_node
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
class ExceptionAnalysis:
    """
    title: Resolve exception statements before backend control-flow emission.
    attributes:
      services:
        type: ExceptionAnalysisServices
    """

    services: ExceptionAnalysisServices

    def __init__(self, services: ExceptionAnalysisServices) -> None:
        """
        title: Bind one feature to explicit compilation-owned dependencies.
        parameters:
          services:
            type: ExceptionAnalysisServices
        """
        self.services = services

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
                symbol = self.services.semantic(child).resolved_symbol
            elif isinstance(child, astx.VariableAssignment):
                assignment = self.services.semantic(child).resolved_assignment
                symbol = assignment.target if assignment is not None else None
            else:
                continue
            if symbol is not None and symbol.symbol_id in symbols:
                self.services.free_exception_error(child, message)

    def exception_value(self, node: astx.Expr) -> ResolvedExceptionType | None:
        """
        title: Require an ordinary instance of a registered exception subtype.
        parameters:
          node:
            type: astx.Expr
        returns:
          type: ResolvedExceptionType | None
        """
        self.services.visit(node)
        value_type = self.services.expr_type(node)
        if isinstance(value_type, astx.ClassType):
            class_ = self.services.context.get_class(
                value_type.module_key
                or self.services.context.current_module_key
                or "main",
                value_type.resolved_name or value_type.name,
            )
            if class_ is not None and class_.exception_type is not None:
                return class_.exception_type
        self.services.free_exception_error(
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
            local = self.services.context.scopes.resolve(node.name)
            binding = self.services.bindings.resolve(node.name)
            if local is None and binding is not None:
                class_ = binding.class_
        elif isinstance(node, astx.FieldAccess):
            self.services.visit(node)
            info = self.services.semantic(node)
            member = info.resolved_module_member_access
            if member is not None:
                class_ = member.binding.class_
        if class_ is not None:
            class_ = self.services.resolve_class_definition(class_)
            canonical = self.services.context.get_class(
                class_.module_key, class_.name
            )
            if canonical is not None and canonical.exception_type is not None:
                self.services.set_class(node, canonical)
                return canonical.exception_type
        self.services.free_exception_error(
            node,
            "handler type must name an exception class",
        )
        return None

    @dispatch
    def visit(self, node: astx.AST) -> None:
        """
        title: Reject an input outside this feature's explicit support.
        parameters:
          node:
            type: astx.AST
        """
        raise configuration_error(
            f"unsupported {type(node).__name__} in ExceptionAnalysis"
        )

    @dispatch
    def visit(self, node: astx.ThrowStmt) -> None:
        """
        title: Resolve explicit raises and dynamic bare re-raises.
        parameters:
          node:
            type: astx.ThrowStmt
        """
        info = self.services.semantic(node)
        info.resolved_raise = None
        self.services.set_type(node, None)
        self.services.semantic(node).flow_outcomes = flow_outcomes(node)
        if self.services.context.current_function is None:
            self.services.free_exception_error(
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
                self.services.free_exception_error(
                    node,
                    "bare raise cannot specify a cause",
                )
            if isinstance(node.cause, astx.LiteralNone):
                self.services.visit(node.cause)
                mode = ExceptionCauseMode.SUPPRESS
            else:
                mode = ExceptionCauseMode.EXPLICIT
                cause_type = self.exception_value(node.cause)
        info.resolved_raise = ResolvedRaise(exception_type, mode, cause_type)

    @dispatch
    def visit(self, node: astx.CatchHandlerStmt) -> None:
        """
        title: Bind a handler-local owned reference and validate its body.
        parameters:
          node:
            type: astx.CatchHandlerStmt
        """
        info = self.services.semantic(node)
        info.resolved_exception_handler = None
        self.services.set_type(node, None)
        self.services.semantic(node).flow_outcomes = flow_outcomes(node)
        if not getattr(self.services.context, "exception_region_depth", 0):
            self.services.free_exception_error(
                node,
                "except requires an enclosing try statement",
            )
        resolved: list[ResolvedExceptionType] = []
        if node.types is not None:
            if not node.types.nodes:
                self.services.free_exception_error(
                    node,
                    "handler type list cannot be empty",
                )
            for reference in node.types:
                item = self.handler_type(reference)
                if item is not None:
                    resolved.append(item)
        root = self.services.context.runtime_exception_types.get(
            "BaseException"
        )
        if root is None:
            self.services.free_exception_error(
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
                    for item in self.services.context.classes.values()
                    if item.qualified_name == shared
                ),
                root.class_,
            )
            binding = shared_class.exception_type or root
        binding_type = exception_class_type(binding.class_)
        with self.services.context.scope("except"):
            symbol = None
            if node.name is not None:
                symbol = self.services.factory.make_variable_symbol(
                    self.services.context.current_module_key or "main",
                    node.name.name,
                    binding_type,
                    is_mutable=False,
                    declaration=node,
                    kind="exception",
                )
                self.services.context.scopes.declare(symbol)
                self.services.set_symbol(node.name, symbol)
                self.services.set_type(node.name, binding_type)
                self.services.set_resource_ownership(
                    node, class_ownership(OwnershipKind.OWNED)
                )
            info.resolved_exception_handler = ResolvedExceptionHandler(
                tuple(resolved), symbol, binding_type
            )
            self.services.visit(node.body)

    @dispatch
    def visit(self, node: astx.FinallyHandlerStmt) -> None:
        """
        title: Validate a finalizer in its own lexical initialization scope.
        parameters:
          node:
            type: astx.FinallyHandlerStmt
        """
        self.services.set_type(node, None)
        self.services.semantic(node).flow_outcomes = flow_outcomes(node)
        if not self.services.context.exception_region_depth:
            self.services.free_exception_error(
                node,
                "finally requires an enclosing try statement",
            )
        with self.services.context.scope("finally"):
            self.services.visit(node.body)

    @dispatch
    def visit(self, node: astx.ExceptionHandlerStmt) -> None:
        """
        title: Validate ordered handlers and isolated exceptional scopes.
        parameters:
          node:
            type: astx.ExceptionHandlerStmt
        """
        info = self.services.semantic(node)
        info.resolved_try = None
        self.services.set_type(node, None)
        self.services.semantic(node).flow_outcomes = flow_outcomes(node)

        if self.services.context.current_function is None:
            self.services.free_exception_error(
                node, "try requires a function body"
            )
        from irx.analysis.handlers._declarations.functions import (  # noqa: PLC0415
            _nested_yield_nodes,
        )

        if _nested_yield_nodes(node):
            self.services.free_exception_error(
                node,
                "generator suspension in protected regions is unsupported",
            )
        if not node.handlers.nodes and node.finally_handler is None:
            self.services.free_exception_error(
                node, "try requires except or finally"
            )
        if node.else_body is not None and not node.handlers.nodes:
            self.services.free_exception_error(
                node, "try else requires an except handler"
            )
        self.services.context.exception_region_depth += 1
        plans: list[ResolvedExceptionHandler] = []
        try:
            with self.services.context.scope("try"):
                self.services.visit(node.body)
                if node.else_body is not None:
                    scope = self.services.context.scopes.current
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
                    with self.services.context.scope("else"):
                        self.services.visit(node.else_body)
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
                    self.services.free_exception_error(
                        handler, "bare except must be last"
                    )
                self.services.visit(handler)
                plan = self.services.semantic(
                    handler
                ).resolved_exception_handler
                if plan is not None:
                    plans.append(plan)
            if node.finally_handler is not None:
                self.services.visit(node.finally_handler)
                protected: list[astx.AST] = [node.body, *node.handlers]
                if node.else_body is not None:
                    protected.append(node.else_body)
                moved_lists: set[str] = set()
                for region in protected:
                    for child in exception_source_nodes(region):
                        if not isinstance(child, astx.FunctionReturn):
                            continue
                        if child.value is None or not isinstance(
                            self.services.expr_type(child.value),
                            (astx.ListType, astx.Bytes),
                        ):
                            continue
                        ownership = self.services.semantic(
                            child
                        ).resource_ownership
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
            self.services.context.exception_region_depth -= 1
        info.resolved_try = ResolvedTry(tuple(plans))

    def node_handlers(self) -> tuple[NodeHandler, ...]:
        """
        title: Export this feature's supported nominal node signatures.
        returns:
          type: tuple[NodeHandler, Ellipsis]
        """
        return tuple(
            contribute_node(
                "irx.analysis.exception." + node_type.__name__,
                "irx.analysis.exception",
                "analysis",
                node_type,
                self.visit,
                source=__name__ + ".ExceptionAnalysis.visit",
            )
            for node_type in (
                astx.ThrowStmt,
                astx.CatchHandlerStmt,
                astx.FinallyHandlerStmt,
                astx.ExceptionHandlerStmt,
            )
        )
