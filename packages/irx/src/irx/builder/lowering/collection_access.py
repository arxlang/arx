"""
title: Lower semantically normalized collection access.
"""

import astx

from public import private

from irx.analysis.resolved_nodes import SemanticInfo
from irx.builder.core import VisitorCore
from irx.typecheck import typechecked


@private
@typechecked
def lower_collection_access(visitor: VisitorCore, node: astx.AST) -> bool:
    """
    title: Emit an analyzed collection operation without type rediscovery.
    parameters:
      visitor: Visitor performing the traversal or lowering.
      node: Syntax node to process.
    returns: 'Result of this operation: emit an analyzed collection operation
      without type rediscovery.'
    """
    info = getattr(node, "semantic", None)
    if (
        not isinstance(info, SemanticInfo)
        or info.normalized_collection is None
    ):
        return False
    visitor.visit_child(info.normalized_collection)
    return True
