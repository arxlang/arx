# mypy: disable-error-code=no-redef

"""
title: Check local moves and lexical loans across control-flow paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import astx

from plum import dispatch
from public import private

from irx.analysis.borrows import positions_may_overlap
from irx.analysis.class_lifecycle import lifecycle_children
from irx.analysis.context import BorrowAccessCheck
from irx.analysis.flow import FlowOutcome, flow_outcomes
from irx.analysis.ownership import resource_ownership
from irx.analysis.resolved_nodes import (
    ResolvedBorrow,
    ResourceKind,
    ResourceOwnership,
    SemanticInfo,
)
from irx.diagnostics import DiagnosticBag, DiagnosticCodes
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True)
class OwnershipState:
    """
    title: Possible ownership states at a control-flow point.
    attributes:
      moved: Bindings moved on any incoming path.
      loans: Active loans keyed by their declaration or retarget site.
    """

    moved: frozenset[str] = frozenset()
    loans: dict[int, ResolvedBorrow] = field(default_factory=dict)

    def join(self, other: OwnershipState) -> OwnershipState:
        """
        title: Keep all moves and loans that may reach a common point.
        parameters:
          other: State on another incoming path.
        returns: Union of the incoming states.
        """
        return OwnershipState(
            self.moved | other.moved, self.loans | other.loans
        )

    def leave_scope(self, entry: OwnershipState) -> OwnershipState:
        """
        title: End loans declared within the scope on every exit.
        parameters:
          entry: State immediately before entering the scope.
        returns: State retaining only loans of the enclosing scopes.
        """
        if not self.loans:
            return self
        outer = {loan.target.symbol_id for loan in entry.loans.values()}
        return replace(
            self,
            loans={
                site: loan
                for site, loan in self.loans.items()
                if loan.target.symbol_id in outer
            },
        )


Paths = dict[FlowOutcome, OwnershipState]


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
def leave_block(
    node: astx.Block, paths: Paths, entry: OwnershipState
) -> Paths:
    """
    title: End local loans and account for fallible destruction on exit.
    parameters:
      node: Block declaring the scoped resources.
      paths: Completions that are leaving this scope.
      entry: State immediately before entering the scope.
    returns: Outgoing states after scope cleanup.
    """
    outgoing = {
        outcome: state.leave_scope(entry) for outcome, state in paths.items()
    }
    for child in node.nodes:
        declaration = (
            child.initializer
            if isinstance(child, astx.ForCountLoopStmt)
            else child
        )
        if not isinstance(
            declaration,
            (astx.VariableDeclaration, astx.InlineVariableDeclaration),
        ):
            continue
        resource = resource_ownership(declaration)
        if resource is not None and resource.resource_kind in {
            ResourceKind.CLASS,
            ResourceKind.FILE,
        }:
            add_cleanup_failures(outgoing)
            break
    return outgoing


@private
@typechecked
def merge_paths(into: Paths, other: Paths) -> None:
    """
    title: Join incoming ownership states separately for each completion.
    parameters:
      into: Destination paths.
      other: Paths joining the destination.
    """
    for outcome, state in other.items():
        previous = into.get(outcome)
        into[outcome] = state if previous is None else previous.join(state)


@private
@typechecked
def add_cleanup_failures(paths: Paths) -> None:
    """
    title: Add exceptions raised after an outgoing state has been reached.
    parameters:
      paths: Outgoing states before a potentially fallible cleanup.
    """
    for state in tuple(paths.values()):
        merge_paths(paths, {FlowOutcome.RAISE: state})


@private
@typechecked
class LocalOwnershipCheck:
    """
    title: Check storage accesses against moves and active lexical loans.
    attributes:
      diagnostics: Diagnostic sink for invalid uses.
      accesses: Resolved lexical loan checks keyed by source node identity.
      reported: Source nodes that already have an ownership diagnostic.
    """

    def __init__(
        self,
        diagnostics: DiagnosticBag,
        accesses: dict[int, list[BorrowAccessCheck]],
    ) -> None:
        """
        title: Initialize an ownership flow check.
        parameters:
          diagnostics: Diagnostic sink for invalid uses.
          accesses: Resolved accesses to check against each state's loans.
        """
        self.diagnostics: DiagnosticBag = diagnostics
        self.accesses: dict[int, list[BorrowAccessCheck]] = accesses
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

    def check_borrows(self, node: astx.AST, state: OwnershipState) -> None:
        """
        title: Reject an access if it overlaps any possible live loan.
        parameters:
          node: Syntax with resolved storage accesses.
          state: Incoming ownership state.
        """
        if not state.loans:
            return
        for access in self.accesses.get(id(node), ()):
            for loan in state.loans.values():
                exclusive = loan.access is astx.BorrowAccess.exclusive
                if (
                    loan.target is access.retarget
                    or loan.place.root is not access.root
                    or not (access.write or exclusive)
                    or (exclusive and access.read_checked)
                    or not positions_may_overlap(
                        access.position, loan.place.constant_index
                    )
                ):
                    continue
                source, borrower = access.root.name, loan.target.name
                if access.formation:
                    message = (
                        f"cannot borrow '{source}' while "
                        f"'{borrower}' has a conflicting borrow"
                    )
                else:
                    action = "write" if access.write else "read"
                    message = (
                        f"cannot {action} '{source}' while it is borrowed "
                        f"by '{borrower}'"
                    )
                self.report(access.node, message)
                return

    def reads(
        self,
        node: astx.AST,
        state: OwnershipState,
        *,
        standalone: bool = False,
    ) -> None:
        """
        title: Check reads within an expression or statement header.
        parameters:
          node: Syntax node to process.
          state: Incoming ownership state.
          standalone: Whether this is the statement's outermost expression.
        """
        self.check_borrows(node, state)
        if isinstance(node, astx.Identifier):
            info = getattr(node, "semantic", None)
            symbol = (
                info.resolved_symbol
                if isinstance(info, SemanticInfo)
                else None
            )
            if symbol is not None and symbol.symbol_id in state.moved:
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
                not standalone
                and store is not None
                and store.source_symbol_id is not None
                and store.source_symbol_id != store.owner_symbol_id
            ):
                self.report(node, "move a list in a standalone assignment")
            if isinstance(node.lhs, astx.Identifier):
                self.check_borrows(node.lhs, state)
            else:
                self.reads(node.lhs, state)
            self.reads(node.rhs, state)
            return
        for child in lifecycle_children(node):
            self.reads(child, state)

    def commit(self, node: astx.AST, state: OwnershipState) -> OwnershipState:
        """
        title: Apply the ownership effect of a successful store.
        parameters:
          node: Store site.
          state: State before committing the store.
        returns: State after the store.
        """
        store = list_store(node)
        info = getattr(node, "semantic", None)
        moved = state.moved
        if isinstance(info, SemanticInfo) and info.resolved_borrow is not None:
            borrow = info.resolved_borrow
            loans = {
                site: loan
                for site, loan in state.loans.items()
                if loan.target is not borrow.target
            }
            loans[id(node)] = borrow
            return replace(state, loans=loans)
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
            if isinstance(info, SemanticInfo) and info.resolved_symbol:
                moved = moved - {info.resolved_symbol.symbol_id}
        return state if moved == state.moved else replace(state, moved=moved)

    @dispatch
    def visit(self, node: astx.AST, state: OwnershipState) -> Paths:
        """
        title: Check an ordinary statement before applying its store.
        parameters:
          node: Statement to process.
          state: Incoming ownership state.
        returns: Ownership state for each reachable completion.
        """
        self.reads(node, state, standalone=True)
        paths = {outcome: state for outcome in flow_outcomes(node)}
        store = list_store(node)
        if store is not None and store.source_symbol_id is not None:
            # Loading and moving a validated local descriptor cannot raise.
            paths.pop(FlowOutcome.RAISE, None)
        info = getattr(node, "semantic", None)
        if isinstance(info, SemanticInfo) and info.resolved_borrow is not None:
            place = info.resolved_borrow.place
            if place.index is None and place.field is None:
                # Obtaining a named scalar address cannot fail.
                paths.pop(FlowOutcome.RAISE, None)
        if FlowOutcome.NORMAL in paths:
            paths[FlowOutcome.NORMAL] = self.commit(node, state)
        return paths

    @dispatch
    def visit(self, node: astx.Block, state: OwnershipState) -> Paths:
        """
        title: End local loans as the block exits in any way.
        parameters:
          node: Block to process.
          state: Incoming ownership state.
        returns: Ownership state for each reachable completion.
        """
        return leave_block(node, self.block_paths(node, state), state)

    def block_paths(self, node: astx.Block, state: OwnershipState) -> Paths:
        """
        title: Pass reachable normal completion to the next statement.
        parameters:
          node: Block to process.
          state: Incoming ownership state.
        returns: Ownership state for each completion before scope cleanup.
        """
        paths = {FlowOutcome.NORMAL: state}
        for child in node.nodes:
            current = paths.pop(FlowOutcome.NORMAL, None)
            if current is None:
                break
            merge_paths(paths, self.visit(child, current))
        return paths

    @dispatch
    def visit(self, node: astx.IfStmt, state: OwnershipState) -> Paths:
        """
        title: Merge reachable conditional arms by completion kind.
        parameters:
          node: Conditional statement.
          state: Incoming ownership state.
        returns: Ownership state for each reachable completion.
        """
        self.reads(node.condition, state)
        paths = {FlowOutcome.RAISE: state}
        known = (
            node.condition.value
            if isinstance(node.condition, astx.LiteralBoolean)
            else None
        )
        if known is not False:
            merge_paths(paths, self.visit(node.then, state))
        if known is not True:
            other = (
                self.visit(node.else_, state)
                if node.else_ is not None
                else {FlowOutcome.NORMAL: state}
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
        state: OwnershipState,
    ) -> Paths:
        """
        title: Join loop entry and repeat paths to a fixed point.
        parameters:
          node: Loop to check.
          state: Incoming ownership state.
        returns: Ownership state for loop exits.
        """
        paths: Paths = {}
        if isinstance(node, astx.ForCountLoopStmt):
            paths = self.visit(node.initializer, state)
            initial = paths.pop(FlowOutcome.NORMAL, None)
            if initial is None:
                return paths
            state = initial
        elif isinstance(node, astx.ForInLoopStmt):
            self.reads(node.iterable, state)
            paths[FlowOutcome.RAISE] = state
        elif isinstance(node, astx.ForRangeLoopStmt):
            for bound in (node.start, node.end, node.step):
                self.reads(bound, state)
            paths[FlowOutcome.RAISE] = state

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
        head = state
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
            repeat = body.pop(FlowOutcome.NORMAL, None)
            continued = body.pop(FlowOutcome.CONTINUE, None)
            if continued is not None:
                repeat = (
                    continued if repeat is None else repeat.join(continued)
                )
            merge_paths(paths, body)
            if repeat is None:
                return paths

            back = repeat
            if isinstance(node, astx.ForCountLoopStmt):
                update = self.visit(node.update, back)
                after = update.pop(FlowOutcome.NORMAL)
                if list_store(node) is not None:
                    after = self.commit(node, after)
                merge_paths(paths, update)
                back = after
            new_head = head.join(back)
            if head == new_head:
                return paths
            head = new_head

    @dispatch
    def visit(self, node: astx.WithStmt, state: OwnershipState) -> Paths:
        """
        title: Check the body and account for failures entering or exiting.
        parameters:
          node: With statement.
          state: Incoming ownership state.
        returns: Ownership state for each reachable completion.
        """
        self.reads(node.manager, state)
        info = getattr(node.target, "semantic", None)
        start = (
            replace(
                state, moved=state.moved - {info.resolved_symbol.symbol_id}
            )
            if isinstance(info, SemanticInfo) and info.resolved_symbol
            else state
        )
        paths = self.visit(node.body, start)
        add_cleanup_failures(paths)
        merge_paths(paths, {FlowOutcome.RAISE: state})
        return paths

    @dispatch
    def visit(
        self, node: astx.ExceptionHandlerStmt, state: OwnershipState
    ) -> Paths:
        """
        title: Track ownership through handlers, else, and finalizers.
        parameters:
          node: Protected statement.
          state: Incoming ownership state.
        returns: Ownership state for each reachable completion.
        """
        protected = self.block_paths(node.body, state)
        normal = protected.pop(FlowOutcome.NORMAL, None)
        # The try scope stays live through else. Handlers see only the
        # exceptional exits from the protected body, after its locals expire.
        paths = leave_block(node.body, protected, state)
        raised = paths.get(FlowOutcome.RAISE)
        if any(handler.types is None for handler in node.handlers):
            paths.pop(FlowOutcome.RAISE, None)
        if normal is not None:
            completed = (
                self.visit(node.else_body, normal)
                if node.else_body is not None
                else {FlowOutcome.NORMAL: normal}
            )
            merge_paths(paths, leave_block(node.body, completed, state))
        if raised is not None:
            for handler in node.handlers:
                caught = self.visit(handler.body, raised)
                # Releasing the handled exception can invoke its destructor.
                add_cleanup_failures(caught)
                merge_paths(paths, caught)
        if node.finally_handler is None:
            return paths

        final_paths: Paths = {}
        for outcome, incoming in paths.items():
            final = self.visit(node.finally_handler.body, incoming)
            if FlowOutcome.NORMAL in final:
                merge_paths(
                    final_paths, {outcome: final.pop(FlowOutcome.NORMAL)}
                )
            if outcome is FlowOutcome.RAISE:
                # An abrupt finalizer may discard a fallible payload.
                add_cleanup_failures(final)
            merge_paths(final_paths, final)
        return final_paths
