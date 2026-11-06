"""
title: >-
  Typed semantic attachments, generation replacement, and dependency edges.
"""

import copy
import gc
import subprocess
import sys
import weakref

from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import astx
import pytest

from astx.binary_op import SPECIALIZED_BINARY_OP_EXTRA
from irx.analysis import SemanticAnalyzer, analyze, analyze_modules
from irx.analysis.extensions.records import CALL_PLAN
from irx.analysis.facts import FactKey, SemanticFact, SemanticFacts
from irx.analysis.reachability import (
    DeclarationReachability,
    plan_declarations,
)
from irx.analysis.resolved_nodes import SemanticInfo
from irx.analysis.table_io import TableIOArgument, TableIOCall
from irx.analysis.types import clone_type
from irx.diagnostics import DiagnosticCodes, IRxDiagnosticError
from irx.typecheck import typechecked
from public import private
from typeguard import TypeCheckError

from ..conftest import StaticImportResolver, make_parsed_module
from .test_table_io import io_module


def test_static_fact_contracts_reject_record_mismatches(
    tmp_path: Path,
) -> None:
    """
    title: Strict mypy preserves typed fact insertion and retrieval boundaries.
    parameters:
      tmp_path:
        type: Path
    """
    source = """
from irx.analysis.facts import FactKey, SemanticFact, SemanticFacts
class Value(SemanticFact):
    pass
class Other(SemanticFact):
    pass
key = FactKey("test", Value)
facts = SemanticFacts().with_fact(key, Value())
value: Value = facts.require(key)
"""
    positive = tmp_path / "positive.py"
    positive.write_text(source, encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "mypy",
        "--strict",
        "--follow-imports=silent",
        "--python-version",
        f"{sys.version_info.major}.{sys.version_info.minor}",
    ]
    accepted = subprocess.run(
        [*command, str(positive)], capture_output=True, text=True, check=False
    )
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    negative = tmp_path / "negative.py"
    negative.write_text(
        source
        + """facts.with_fact(key, Other())
wrong: Other = facts.require(key)
""",
        encoding="utf-8",
    )
    rejected = subprocess.run(
        [*command, str(negative)], capture_output=True, text=True, check=False
    )
    assert rejected.returncode == 1, rejected.stdout + rejected.stderr
    expected_errors = 2
    assert rejected.stdout.count("error:") == expected_errors, rejected.stdout


@private
@typechecked
@dataclass(frozen=True)
class DeclarationFact(SemanticFact):
    """
    title: Keep a declaration reachable only through a feature attachment.
    attributes:
      declaration:
        type: astx.AST
    """

    declaration: astx.AST

    def validate(self) -> None:
        """
        title: Validate the record payload at the store boundary.
        """
        if not isinstance(self.declaration, astx.AST):
            raise TypeError("declaration must be an AST node")

    def dependencies(self) -> tuple[astx.AST, ...]:
        """
        title: Expose the declaration dependency without exposing its storage.
        returns:
          type: tuple[astx.AST, Ellipsis]
        """
        return (self.declaration,)


def test_fact_keys_replacement_and_required_diagnostics() -> None:
    """
    title: Lookup remains typed and ownership collisions never alias records.
    """
    key = FactKey("provider", DeclarationFact)
    empty = SemanticFacts()
    assert empty.get(key) is None
    with pytest.raises(
        IRxDiagnosticError, match="missing semantic fact"
    ) as failure:
        empty.require(key)
    assert failure.value.diagnostic.phase == "lowering"
    fact = DeclarationFact(astx.LiteralInt32(1))
    populated = empty.with_fact(key, fact)
    assert populated.require(key) is fact
    assert empty.get(key) is None
    with pytest.raises(ValueError, match="duplicate"):
        populated.with_fact(key, fact)
    with pytest.raises(ValueError, match="ownership collision"):
        populated.get(FactKey("other", DeclarationFact))
    with pytest.raises(IRxDiagnosticError, match="invalid semantic fact"):
        populated.require(FactKey("other", DeclarationFact))
    with pytest.raises(IRxDiagnosticError) as missing:
        empty.require(key, phase="analysis")
    assert missing.value.diagnostic.phase == "analysis"
    assert (
        missing.value.diagnostic.code
        == DiagnosticCodes.SEMANTIC_MISSING_METADATA
    )
    replacement = DeclarationFact(astx.LiteralInt32(2))
    assert (
        populated.with_fact(key, replacement, replace=True).require(key)
        is replacement
    )
    assert populated.require(key) is fact
    with pytest.raises((TypeError, TypeCheckError)):
        empty.with_fact(key, object())  # type: ignore[type-var]
    with pytest.raises((TypeError, TypeCheckError)):
        empty.with_fact(CALL_PLAN, TableIOCall("read_csv", (object(),)))  # type: ignore[arg-type]
    with pytest.raises((TypeError, TypeCheckError)):
        invalid = TableIOArgument(
            "columns", astx.LiteralList([]), "texts", literals=("id", object())
        )  # type: ignore[arg-type]
        empty.with_fact(CALL_PLAN, TableIOCall("read_csv", (invalid,)))
    with pytest.raises(TypeError, match="integer literals"):
        TableIOArgument(
            "row_groups", astx.LiteralList([]), "ints", literals=(1, "two")
        )
    with pytest.raises(TypeError, match="string literals"):
        TableIOArgument(
            "columns", astx.LiteralList([]), "texts", literals=("id", 2)
        )


def test_normalized_type_has_independent_attachment_slot() -> None:
    """
    title: Type normalization shares immutable records, not the sidecar slot.
    """
    source = astx.UnionType((astx.Int32(), astx.Float32()))
    key = FactKey("provider", DeclarationFact)
    info = SemanticInfo()
    info.facts = info.facts.with_fact(key, DeclarationFact(source.members[0]))
    setattr(source, "semantic", info)
    normalized = clone_type(source)
    cloned_info = getattr(normalized, "semantic")
    assert isinstance(cloned_info, SemanticInfo)
    assert cloned_info is not info
    assert cloned_info.facts.require(key) is info.facts.require(key)
    cloned_info.facts = SemanticFacts()
    assert info.facts.get(key) is not None


def test_normalized_expression_keeps_one_semantic_identity() -> None:
    """
    title: Normalized operator aliases share facts and invalidate together.
    """
    expression = astx.BinaryOp("+", astx.LiteralInt32(1), astx.LiteralInt32(2))
    analyze(expression)
    info = cast(SemanticInfo, getattr(expression, "semantic"))
    normalized = info.extras[SPECIALIZED_BINARY_OP_EXTRA]
    assert normalized is not expression
    assert getattr(normalized, "semantic") is info
    key = FactKey("provider", DeclarationFact)
    info.facts = info.facts.with_fact(key, DeclarationFact(expression.lhs))
    analyze(expression)
    assert info.facts.get(key) is None


@pytest.mark.parametrize("module_attachment", [False, True])
def test_attachment_edges_participate_in_declaration_reachability(
    module_attachment: bool,
) -> None:
    """
    title: A lazy declaration reachable only through a record is retained.
    parameters:
      module_attachment:
        type: bool
    """
    body = astx.Block()
    body.append(astx.FunctionReturn(astx.LiteralInt32(7)))
    declaration = astx.FunctionDef(
        astx.FunctionPrototype("kept", astx.Arguments(), astx.Int32()), body
    )
    library = make_parsed_module("library", declaration)
    library = replace(library, lazy_declarations=True)
    expression = astx.LiteralInt32(0)
    root = make_parsed_module(
        "root",
        astx.ImportFromStmt(module="library", names=[astx.AliasExpr("kept")]),
        expression,
    )
    session = analyze_modules(root, StaticImportResolver({"library": library}))
    assert session.lowering_declarations is not None
    assert id(declaration) not in session.lowering_declarations
    owner = root.ast if module_attachment else expression
    info = cast(SemanticInfo, getattr(owner, "semantic"))
    info.facts = info.facts.with_fact(
        FactKey("provider", DeclarationFact), DeclarationFact(declaration)
    )
    reachable = plan_declarations(session)
    assert reachable is not None and id(declaration) in reachable


@pytest.mark.parametrize("with_construction", [False, True])
def test_table_dependencies_expose_source_order_ast_nodes(
    with_construction: bool,
) -> None:
    """
    title: Operand wrappers and absent constructions are not dependency edges.
    parameters:
      with_construction:
        type: bool
    """
    path = astx.LiteralString("input.csv")
    columns = astx.LiteralList([astx.LiteralString("id")])
    construction = astx.ClassConstruct("Frame") if with_construction else None
    plan = TableIOCall(
        "read_csv",
        (
            TableIOArgument("path", path, "text"),
            TableIOArgument("columns", columns, "texts", literals=("id",)),
        ),
        construction,
    )
    expected: tuple[astx.AST, ...] = (path, columns)
    if construction is not None:
        expected = (*expected, construction)
    dependencies = plan.dependencies()
    assert len(dependencies) == len(expected)
    assert all(left is right for left, right in zip(dependencies, expected))


def test_dependency_boundary_rejects_non_ast_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: An unchecked provider cannot hide invalid edges after valid nodes.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """

    def invalid_dependencies(self: DeclarationFact) -> tuple[object, ...]:
        """
        title: Simulate an unchecked provider returning an invalid second edge.
        parameters:
          self:
            type: DeclarationFact
        returns:
          type: tuple[object, Ellipsis]
        """
        return (self.declaration, object())

    facts = SemanticFacts().with_fact(
        FactKey("provider", DeclarationFact),
        DeclarationFact(astx.LiteralInt32(1)),
    )
    monkeypatch.setattr(DeclarationFact, "dependencies", invalid_dependencies)
    with pytest.raises(TypeCheckError):
        facts.dependencies()


def test_reachability_rejects_non_ast_roots() -> None:
    """
    title: Reachability accepts only AST roots and checks every root.
    """
    root = make_parsed_module("root", astx.LiteralInt32(0))
    session = analyze_modules(root, StaticImportResolver({}))
    with pytest.raises(TypeCheckError):
        DeclarationReachability(session).collect(
            [root.ast, object()]  # type: ignore[list-item]
        )


def test_table_fact_copy_and_reanalysis_release_old_generation() -> None:
    """
    title: >-
      Copied operands follow AST memoization and old plans are not retained.
    """
    root, read = io_module("csv")
    resolver = StaticImportResolver({})
    session = analyze_modules(root, resolver)
    info = cast(SemanticInfo, getattr(read, "semantic"))
    plan = info.facts.require(CALL_PLAN)
    old_plan = weakref.ref(plan)
    old_session = weakref.ref(session)
    cloned = copy.deepcopy(read)
    copied = cast(SemanticInfo, getattr(cloned, "semantic")).facts.require(
        CALL_PLAN
    )
    assert isinstance(copied, TableIOCall)
    assert copied is not plan
    assert copied.arguments[0].expression is next(iter(cloned.args))
    assert copied.arguments[0].expression is not next(iter(read.args))
    SemanticAnalyzer()._clear_semantic_sidecars(cloned)
    assert not hasattr(cloned, "semantic")
    assert not hasattr(next(iter(cloned.args)), "semantic")
    analyze_modules(root, resolver)
    assert info.facts.require(CALL_PLAN) is not plan
    del plan, session
    gc.collect()
    assert old_plan() is None
    assert old_session() is None
