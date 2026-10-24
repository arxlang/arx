"""
title: Compositional statement completion outcomes.
summary: >-
  Keep fallthrough distinct from every abrupt transfer. A finalizer replaces
  prior completions only on its own abrupt paths; a falling-through finalizer
  resumes the saved completion. Potential expression failures remain possible.
"""

from __future__ import annotations

from enum import Enum

import astx

from public import public

from irx.typecheck import typechecked


@public
@typechecked
class FlowOutcome(str, Enum):
    """
    title: The five distinct ways a statement region can complete.
    """

    NORMAL = "normal"
    RETURN = "return"
    RAISE = "raise"
    BREAK = "break"
    CONTINUE = "continue"


@public
@typechecked
def flow_outcomes(node: astx.AST) -> frozenset[FlowOutcome]:
    """
    title: Compose conservative outcomes without conflating raise and return.
    parameters:
      node:
        type: astx.AST
    returns:
      type: frozenset[FlowOutcome]
    """
    normal, raised = FlowOutcome.NORMAL, FlowOutcome.RAISE
    if isinstance(node, astx.FunctionReturn):
        return frozenset({FlowOutcome.RETURN, raised})
    if isinstance(node, astx.ThrowStmt):
        return frozenset({raised})
    if isinstance(node, astx.BreakStmt):
        return frozenset({FlowOutcome.BREAK})
    if isinstance(node, astx.ContinueStmt):
        return frozenset({FlowOutcome.CONTINUE})
    if isinstance(node, astx.Block):
        outcomes = {normal}
        for child in node.nodes:
            if normal not in outcomes:
                break
            outcomes.remove(normal)
            outcomes.update(flow_outcomes(child))
        return frozenset(outcomes)
    if isinstance(node, astx.IfStmt):
        alternatives = flow_outcomes(node.then)
        other = (
            flow_outcomes(node.else_) if node.else_ else frozenset({normal})
        )
        return alternatives | other | {raised}
    if isinstance(node, astx.WithStmt):
        return flow_outcomes(node.body) | {raised}
    if isinstance(node, (astx.FinallyHandlerStmt, astx.CatchHandlerStmt)):
        return flow_outcomes(node.body)
    if isinstance(
        node,
        (
            astx.WhileStmt,
            astx.ForCountLoopStmt,
            astx.ForRangeLoopStmt,
            astx.ForInLoopStmt,
        ),
    ):
        return (
            flow_outcomes(node.body)
            - {
                FlowOutcome.BREAK,
                FlowOutcome.CONTINUE,
            }
        ) | {normal, raised}
    if isinstance(node, astx.ExceptionHandlerStmt):
        outcomes = set(flow_outcomes(node.body))
        body_raises = raised in outcomes
        if normal in outcomes and node.else_body is not None:
            outcomes.remove(normal)
            outcomes.update(flow_outcomes(node.else_body))
        if body_raises:
            for handler in node.handlers:
                outcomes.update(flow_outcomes(handler.body))
        if node.finally_handler is not None:
            final = set(flow_outcomes(node.finally_handler.body))
            if normal not in final:
                outcomes = final
            else:
                outcomes.update(final - {normal})
        return frozenset(outcomes)
    return frozenset({normal, raised})
