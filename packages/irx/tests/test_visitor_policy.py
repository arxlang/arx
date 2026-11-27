"""
title: Enforce the repository's visitor method naming convention.
"""

from __future__ import annotations

import ast

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_visitor_methods_use_the_visit_name() -> None:
    """
    title: Reject type-specific visit method names in project Python
      code.
    summary: Scan the syntax tree so comments, code samples, and
      local functions cannot be mistaken for methods.
    """
    paths = sorted(
        path
        for pattern in (
            "*.py",
            "packages/*/src/**/*.py",
            "packages/*/tests/**/*.py",
            "scripts/**/*.py",
            "examples/**/*.py",
        )
        for path in REPO_ROOT.glob(pattern)
    )
    assert paths, "Expected project Python files"

    violations: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_bytes(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            # Class-level conditionals share the class namespace. A method
            # body or a nested class starts a separate scope.
            statements: list[ast.AST] = list(node.body)
            while statements:
                member = statements.pop()
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if member.name.lstrip("_").startswith("visit_"):
                        violations.append(
                            f"{path.relative_to(REPO_ROOT)}:{member.lineno} "
                            f"{node.name}.{member.name}"
                        )
                elif not isinstance(member, ast.ClassDef):
                    statements.extend(ast.iter_child_nodes(member))

    assert not violations, (
        "Use visit overloads for type dispatch. Name helpers by what they "
        "do. Found visit_* methods:\n" + "\n".join(sorted(violations))
    )
