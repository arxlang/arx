"""
title: Drop feature facts before analyzing a reused syntax tree.
"""

import astx

from public import private

from irx.analysis.facts import SemanticFacts
from irx.analysis.resolved_nodes import SemanticInfo
from irx.typecheck import typechecked


@private
@typechecked
def invalidate_facts(root: astx.AST) -> None:
    """
    title: Clear one generation without following old semantic or parent edges.
    parameters:
      root:
        type: astx.AST
    """
    pending: list[object] = [root]
    seen: set[int] = set()
    while pending:
        value = pending.pop()
        if id(value) in seen:
            continue
        seen.add(id(value))
        if isinstance(value, astx.AST):
            info = getattr(value, "semantic", None)
            if isinstance(info, SemanticInfo):
                info.facts.invalidate(value)
                info.facts = SemanticFacts()
            pending.extend(
                child
                for name, child in vars(value).items()
                if name not in {"parent", "semantic", "irx_owner_module"}
            )
        elif isinstance(value, (tuple, list, set, frozenset)):
            pending.extend(value)
        elif isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
