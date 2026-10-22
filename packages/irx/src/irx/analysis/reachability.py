# mypy: disable-error-code=no-redef
"""
title: Conservative declaration reachability for opt-in library modules.
summary: >-
  Analyze every declaration for validity first. Retain whole referenced classes
  (including virtual methods and destructors), rather than pruning methods or
  guessing calls from syntax. Other modules retain their existing exported
  code.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, time
from enum import Enum
from typing import cast

import astx

from plum import dispatch
from public import private

from irx.analysis.session import CompilationSession
from irx.typecheck import typechecked


@private
@typechecked
class DeclarationReachability:
    """
    title: Follow resolved AST and semantic edges without name rediscovery.
    attributes:
      seen:
        type: set[int]
      pending:
        type: list[object]
      nominal:
        type: dict[str, astx.AST]
    """

    def __init__(self, session: CompilationSession) -> None:
        """
        title: Index resolved nominal type declarations from the session.
        parameters:
          session:
            type: CompilationSession
        """
        self.seen: set[int] = set()
        self.pending: list[object] = []
        self.nominal: dict[str, astx.AST] = {}
        for bindings in session.visible_bindings.values():
            for binding in bindings.values():
                if binding.class_ is not None:
                    self.nominal[binding.qualified_name] = (
                        binding.class_.declaration
                    )
                if binding.struct is not None:
                    self.nominal[binding.qualified_name] = (
                        binding.struct.declaration
                    )

    def collect(self, roots: list[astx.AST]) -> frozenset[int]:
        """
        title: Compute a cycle-safe closure of resolved declaration references.
        parameters:
          roots:
            type: list[astx.AST]
        returns:
          type: frozenset[int]
        """
        self.pending.extend(roots)
        while self.pending:
            value = self.pending.pop()
            if id(value) in self.seen:
                continue
            self.seen.add(id(value))
            self.visit(value)
        return frozenset(self.seen)

    @dispatch
    def visit(self, value: object) -> None:
        """
        title: Traverse semantic records and reject unknown dependency shapes.
        parameters:
          value:
            type: object
        """
        if is_dataclass(value) and not isinstance(value, type):
            for field in fields(value):
                self.pending.append(getattr(value, field.name))
            return
        if value is None or isinstance(
            value,
            (
                str,
                bytes,
                int,
                float,
                Enum,
                type,
                astx.SourceLocation,
                date,
                time,
            ),
        ):
            return
        raise TypeError(
            f"unsupported declaration dependency metadata: {type(value)}"
        )

    @dispatch
    def visit(self, value: astx.AST) -> None:
        """
        title: Walk children and sidecars, never parent links or import roots.
        parameters:
          value:
            type: astx.AST
        """
        if isinstance(value, (astx.ImportStmt, astx.ImportFromStmt)):
            return
        if isinstance(value, (astx.ClassType, astx.StructType)):
            declaration = self.nominal.get(value.qualified_name)
            if declaration is not None:
                self.pending.append(declaration)
        for name, item in vars(value).items():
            if name not in {"parent", "__orig_class__", "irx_owner_module"}:
                self.pending.append(cast(object, item))

    @dispatch
    def visit(
        self,
        value: list[object]
        | tuple[object, ...]
        | set[object]
        | frozenset[object],
    ) -> None:
        """
        title: Traverse dependency collections.
        parameters:
          value:
            type: >-
              list[object] | tuple[object, Ellipsis] | set[object] |
              frozenset[object]
        """
        self.pending.extend(value)

    @dispatch
    def visit(self, value: dict[object, object]) -> None:
        """
        title: Traverse sidecar maps and expression-bearing literal keys.
        parameters:
          value:
            type: dict[object, object]
        """
        self.pending.extend(value.keys())
        self.pending.extend(value.values())


@private
@typechecked
def plan_declarations(session: CompilationSession) -> frozenset[int] | None:
    """
    title: Keep eager module exports and their lazy-library dependencies.
    parameters:
      session:
        type: CompilationSession
    returns:
      type: frozenset[int] | None
    """
    if not any(item.lazy_declarations for item in session.modules.values()):
        return None
    roots: list[astx.AST] = []
    for module in session.ordered_modules():
        if module.key == session.root.key or not module.lazy_declarations:
            roots.extend(module.ast.nodes)
            roots.extend(astx.generated_template_nodes(module.ast))
    return DeclarationReachability(session).collect(roots)
