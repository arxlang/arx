# mypy: disable-error-code=no-redef

"""
title: Check ownership of list bindings across control-flow paths.
"""

from __future__ import annotations

import astx

from plum import dispatch
from public import private

from irx.analysis.class_lifecycle import lifecycle_children
from irx.analysis.flow import FlowOutcome, flow_outcomes
from irx.analysis.resolved_nodes import (
    ResourceKind,
    ResourceOwnership,
    SemanticInfo,
)
from irx.diagnostics import DiagnosticBag, DiagnosticCodes
from irx.typecheck import typechecked

Moved = frozenset[str]
Paths = dict[FlowOutcome, Moved]


@private
@typechecked
def list_store(node: astx.AST) -> ResourceOwnership | None:
    """
    title: Read the resolved plan for a local list store, if present.
    parameters:
      node: Syntax node to process.
    returns: Resolved list store.
    """
    info = getattr(node, "semantic", None)
    if isinstance(info, SemanticInfo):
        store = info.resolved_resource_store
        if store is not None and store.resource_kind is ResourceKind.LIST:
            return store
    return None


@private
@typechecked
def merge_paths(into: Paths, other: Paths) -> None:
    """
    title: Keep bindings moved on any path reaching each completion.
    parameters:
      into: Destination paths.
      other: Paths joining the destination.
    """
    for outcome, moved in other.items():
        into[outcome] = into.get(outcome, frozenset()) | moved


@private
@typechecked
class ListMoveCheck:
    """
    title: Check uses against the possibly moved bindings at that point.
    attributes:
      diagnostics: Diagnostic sink for invalid uses.
      reported: Source nodes that already have a move diagnostic.
    """

    def __init__(self, diagnostics: DiagnosticBag) -> None:
        """
        title: Initialize an ownership flow check.
        parameters:
          diagnostics: Diagnostic sink for invalid uses.
        """
        self.diagnostics: DiagnosticBag = diagnostics
        self.reported: set[int] = set()

    def report(self, node: astx.AST, message: str) -> None:
        """
        title: Report one diagnostic per source use across all paths.
        parameters:
          node: Syntax node to process.
          message: Diagnostic text.
        """
        if id(node) not in self.reported:
            self.reported.add(id(node))
            self.diagnostics.add(
                message,
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )

    def reads(self, node: astx.AST, moved: Moved) -> None:
        """
        title: Check reads within an expression or statement header.
        parameters:
          node: Syntax node to process.
          moved: Bindings that may have been moved.
        """
        if isinstance(node, astx.Identifier):
            info = getattr(node, "semantic", None)
            symbol = (
                info.resolved_symbol
                if isinstance(info, SemanticInfo)
                else None
            )
            if symbol is not None and symbol.symbol_id in moved:
                self.report(
                    node,
                    f"cannot use list '{node.name}' after a move; "
                    "reinitialize it before use",
                )
            return
        if isinstance(node, astx.FunctionDef):
            return
        if isinstance(node, astx.BinaryOp) and node.op_code == "=":
            store = list_store(node)
            if (
                store is not None
                and store.source_symbol_id is not None
                and store.source_symbol_id != store.owner_symbol_id
            ):
                self.report(node, "move a list in a standalone assignment")
            if not isinstance(node.lhs, astx.Identifier):
                self.reads(node.lhs, moved)
            self.reads(node.rhs, moved)
            return
        for child in lifecycle_children(node):
            self.reads(child, moved)

    def commit(self, node: astx.AST, moved: Moved) -> Moved:
        """
        title: Update binding availability after a successful list store.
        parameters:
          node: Store site.
          moved: Bindings that may have been moved.
        returns: Moved bindings after the store.
        """
        store = list_store(node)
        if store is not None:
            source, target = store.source_symbol_id, store.owner_symbol_id
            if target is not None:
                moved = moved - {target}
            if source is not None and source != target:
                moved = moved | {source}
        elif isinstance(
            node, (astx.VariableDeclaration, astx.InlineVariableDeclaration)
        ):
            # A loop-local declaration creates a new owner each iteration.
            info = getattr(node, "semantic", None)
            if isinstance(info, SemanticInfo) and info.resolved_symbol:
                moved = moved - {info.resolved_symbol.symbol_id}
        return moved

    @dispatch
    def visit(self, node: astx.AST, moved: Moved) -> Paths:
        """
        title: Check an ordinary statement before applying its store.
        parameters:
          node: Statement to process.
          moved: Incoming moved bindings.
        returns: Moved bindings for each reachable completion.
        """
        if isinstance(node, astx.BinaryOp) and node.op_code == "=":
            if not isinstance(node.lhs, astx.Identifier):
                self.reads(node.lhs, moved)
            self.reads(node.rhs, moved)
        else:
            self.reads(node, moved)
        paths = {outcome: moved for outcome in flow_outcomes(node)}
        store = list_store(node)
        if store is not None and store.source_symbol_id is not None:
            # Loading and moving a validated local descriptor cannot raise.
            paths.pop(FlowOutcome.RAISE, None)
        if FlowOutcome.NORMAL in paths:
            paths[FlowOutcome.NORMAL] = self.commit(node, moved)
        return paths

    @dispatch
    def visit(self, node: astx.Block, moved: Moved) -> Paths:
        """
        title: Pass reachable normal completion to the next statement.
        parameters:
          node: Block to process.
          moved: Incoming moved bindings.
        returns: Moved bindings for each reachable completion.
        """
        paths = {FlowOutcome.NORMAL: moved}
        for child in node.nodes:
            current = paths.pop(FlowOutcome.NORMAL, None)
            if current is None:
                break
            merge_paths(paths, self.visit(child, current))
        return paths

    @dispatch
    def visit(self, node: astx.IfStmt, moved: Moved) -> Paths:
        """
        title: Merge reachable conditional arms by completion kind.
        parameters:
          node: Conditional statement.
          moved: Incoming moved bindings.
        returns: Moved bindings for each reachable completion.
        """
        self.reads(node.condition, moved)
        paths = {FlowOutcome.RAISE: moved}
        known = (
            node.condition.value
            if isinstance(node.condition, astx.LiteralBoolean)
            else None
        )
        if known is not False:
            merge_paths(paths, self.visit(node.then, moved))
        if known is not True:
            other = (
                self.visit(node.else_, moved)
                if node.else_ is not None
                else {FlowOutcome.NORMAL: moved}
            )
            merge_paths(paths, other)
        return paths

    @dispatch
    def visit(
        self,
        node: astx.WhileStmt
        | astx.ForCountLoopStmt
        | astx.ForInLoopStmt
        | astx.ForRangeLoopStmt,
        moved: Moved,
    ) -> Paths:
        """
        title: Join loop entry and repeat paths to a fixed point.
        parameters:
          node: Loop to check.
          moved: Incoming moved bindings.
        returns: Moved bindings for loop exits.
        """
        paths: Paths = {}
        if isinstance(node, astx.ForCountLoopStmt):
            paths = self.visit(node.initializer, moved)
            initial = paths.pop(FlowOutcome.NORMAL, None)
            if initial is None:
                return paths
            moved = initial
        elif isinstance(node, astx.ForInLoopStmt):
            self.reads(node.iterable, moved)
            paths[FlowOutcome.RAISE] = moved
        elif isinstance(node, astx.ForRangeLoopStmt):
            for bound in (node.start, node.end, node.step):
                self.reads(bound, moved)
            paths[FlowOutcome.RAISE] = moved

        condition = (
            node.condition
            if isinstance(node, (astx.WhileStmt, astx.ForCountLoopStmt))
            else None
        )
        known = (
            condition.value
            if isinstance(condition, astx.LiteralBoolean)
            else None
        )
        head = moved
        while True:
            if condition is not None:
                self.reads(condition, head)
                merge_paths(paths, {FlowOutcome.RAISE: head})
            if known is not True:
                merge_paths(paths, {FlowOutcome.NORMAL: head})
            if known is False:
                return paths

            body = self.visit(node.body, head)
            if FlowOutcome.BREAK in body:
                merge_paths(
                    paths, {FlowOutcome.NORMAL: body.pop(FlowOutcome.BREAK)}
                )
            repeat = set()
            has_repeat = False
            for outcome in (FlowOutcome.NORMAL, FlowOutcome.CONTINUE):
                if outcome in body:
                    repeat.update(body.pop(outcome))
                    has_repeat = True
            merge_paths(paths, body)
            if not has_repeat:
                return paths

            back = frozenset(repeat)
            if isinstance(node, astx.ForCountLoopStmt):
                update = self.visit(node.update, back)
                after = update.pop(FlowOutcome.NORMAL)
                if list_store(node) is not None:
                    after = self.commit(node, after)
                merge_paths(paths, update)
                back = after
            new_head = head | back
            if head == new_head:
                return paths
            head = new_head

    @dispatch
    def visit(self, node: astx.WithStmt, moved: Moved) -> Paths:
        """
        title: Check the body and account for failures entering or exiting.
        parameters:
          node: With statement.
          moved: Incoming moved bindings.
        returns: Moved bindings for each reachable completion.
        """
        self.reads(node.manager, moved)
        info = getattr(node.target, "semantic", None)
        start = (
            moved - {info.resolved_symbol.symbol_id}
            if isinstance(info, SemanticInfo) and info.resolved_symbol
            else moved
        )
        paths = self.visit(node.body, start)
        merge_paths(paths, {FlowOutcome.RAISE: moved.union(*paths.values())})
        return paths

    @dispatch
    def visit(self, node: astx.ExceptionHandlerStmt, moved: Moved) -> Paths:
        """
        title: Track ownership through handlers, else, and finalizers.
        parameters:
          node: Protected statement.
          moved: Incoming moved bindings.
        returns: Moved bindings for each reachable completion.
        """
        paths: Paths = self.visit(node.body, moved)
        raised = paths.get(FlowOutcome.RAISE)
        if any(handler.types is None for handler in node.handlers):
            paths.pop(FlowOutcome.RAISE, None)
        if node.else_body is not None and FlowOutcome.NORMAL in paths:
            normal = paths.pop(FlowOutcome.NORMAL)
            merge_paths(paths, self.visit(node.else_body, normal))
        if raised is not None:
            for handler in node.handlers:
                merge_paths(paths, self.visit(handler.body, raised))
        if node.finally_handler is None:
            return paths

        final_paths: Paths = {}
        for outcome, state in paths.items():
            final = self.visit(node.finally_handler.body, state)
            if FlowOutcome.NORMAL in final:
                merge_paths(
                    final_paths, {outcome: final.pop(FlowOutcome.NORMAL)}
                )
            merge_paths(final_paths, final)
        return final_paths
