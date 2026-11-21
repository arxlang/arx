"""
title: Exception nodes must not slip through the generic semantic fallback.
"""

import astx
import pytest

from irx.analysis import analyze
from irx.builder import Visitor
from irx.diagnostics import SemanticError


@pytest.mark.parametrize(
    "node",
    [
        astx.ThrowStmt(astx.LiteralInt32(1)),
        astx.ThrowStmt(astx.Identifier("missing")),
        astx.CatchHandlerStmt(astx.Block()),
        astx.ExceptionHandlerStmt(astx.Block(), []),
        astx.FinallyHandlerStmt(astx.Block()),
    ],
)
def test_exception_nodes_fail_before_lowering(
    node: astx.AST, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    title: Invalid direct trees fail at the semantic boundary.
    parameters:
      node: Syntax node to process.
      monkeypatch: Fixture for temporarily replacing dependencies and settings.
    """
    with pytest.raises(
        SemanticError,
        match=r"requires|cannot resolve",
    ):
        analyze(node)
    visitor = Visitor()

    def unexpected_lowering(node: astx.AST) -> None:
        """
        title: Record accidental entry into backend dispatch.
        parameters:
          node: Syntax node to process.
        """
        pytest.fail(f"lowering was entered for {type(node).__name__}")

    monkeypatch.setattr(visitor, "visit", unexpected_lowering)
    with pytest.raises(
        SemanticError,
        match=r"requires|cannot resolve",
    ):
        visitor.translate(node)
