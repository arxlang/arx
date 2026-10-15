"""
title: Nullable source syntax, semantic failures, and linked execution.
"""

from __future__ import annotations

import subprocess

from pathlib import Path

import astx
import pytest

from arx.codegen import ArxBuilder
from arx.exceptions import ParserException
from arx.io import ArxIO
from arx.lexer import Lexer, TokenKind
from arx.lexer.syntax import load_syntax_manifest
from arx.parser import Parser
from irx.analysis import SemanticError, analyze
from llvmlite import binding as llvm


def parse(source: str) -> astx.Module:
    """
    title: Parse a documented nullable regression source.
    parameters:
      source:
        type: str
    returns:
      type: astx.Module
    """
    ArxIO.string_to_buffer("```\ntitle: Nullable regression\n```\n" + source)
    return Parser().parse(Lexer().lex())


def test_nullable_manifest_and_parser_nodes() -> None:
    """
    title: Advertise contextual builtin names and preserve raw union syntax.
    """
    names = {operation.value for operation in astx.NullableOperation}
    assert names <= set(load_syntax_manifest().data["builtins"]["functions"])
    ArxIO.string_to_buffer(" ".join(sorted(names)))
    assert all(
        token.kind in {TokenKind.identifier, TokenKind.eof}
        for token in Lexer().lex().tokens
    )
    module = parse(
        (
            "fn main() -> i32:\n"
            "  var x: i32 | none = none\n"
            "  assert is_null(x)\n"
            "  return 0\n"
        )
    )
    function = next(
        node for node in module.block if isinstance(node, astx.FunctionDef)
    )
    declaration = function.body.nodes[0]
    assert isinstance(declaration.type_, astx.UnionType)
    assertion = function.body.nodes[1]
    assert isinstance(assertion.condition, astx.NullableQuery)
    analyze(module)
    assert isinstance(declaration.semantic.resolved_type, astx.NullableType)
    assert assertion.condition.semantic.resolved_nullable_query is not None


@pytest.mark.parametrize(
    "expression", ["is_null()", "is_valid(1, 2)", "expect_valid<i32>(1)"]
)
def test_nullable_builtin_arity_errors(expression: str) -> None:
    """
    title: Reject malformed nullable intrinsics at the parser boundary.
    parameters:
      expression:
        type: str
    """
    with pytest.raises(ParserException, match="one value and no template"):
        parse(f"fn main() -> i32:\n  {expression}\n  return 0\n")


@pytest.mark.parametrize(
    "body,message",
    [
        ("var x: list[list[i32]] | none = none", "nested list owners"),
        ("var x: i32 | f32 | none = none", "one distinct non-none"),
        ("var x: list[i32 | none]", "nullable container elements"),
        ("assert is_null(none)", "typed nullable"),
        ("assert is_valid(1)", "typed nullable"),
        ("var x: i32 | none = none\n  var y: i32 = x", "cannot assign"),
        ("var x: i64 | none = none\n  var y: i32 | none = x", "cannot assign"),
        (
            "var x: i32 | none = none\n  var y: i32 = x + 1",
            "cannot assign",
        ),
        ("var x: i32 | none = none\n  assert x == none", "nullable operator"),
        ("var x: i32 | none = none\n  var y: i32 = -x", "cannot assign"),
        ("var x: bool | none = false\n  assert x", "Boolean"),
        (
            "var x: i32 | none = none\n  var y: i32 = cast(x, i32)",
            "nullable casts",
        ),
    ],
)
def test_nullable_unsupported_semantics(body: str, message: str) -> None:
    """
    title: Unsupported null operations fail before lowering or payload reads.
    parameters:
      body:
        type: str
      message:
        type: str
    """
    with pytest.raises(SemanticError, match=message):
        analyze(parse(f"fn main() -> i32:\n  {body}\n  return 0\n"))


@pytest.mark.parametrize(
    "source",
    [
        (
            "fn nothing() -> none:\n"
            "  return\n"
            "fn main() -> i32:\n"
            "  var x: i32 | none = nothing()\n"
            "  return 0\n"
        ),
        (
            "fn nothing() -> none:\n"
            "  return\n"
            "fn take(x: i32 | none) -> none:\n"
            "  return\n"
            "fn main() -> i32:\n"
            "  take(nothing())\n"
            "  return 0\n"
        ),
        (
            "fn nothing() -> none:\n"
            "  return\n"
            "fn value() -> i32 | none:\n"
            "  return nothing()\n"
        ),
        (
            "fn nothing() -> none:\n"
            "  return\n"
            "fn take(x: i32 | none = nothing()) -> none:\n"
            "  return\n"
        ),
    ],
)
def test_void_calls_are_not_null_values(source: str) -> None:
    """
    title: Void calls cannot masquerade as an explicit literal null.
    parameters:
      source:
        type: str
    """
    with pytest.raises(SemanticError, match="void call"):
        analyze(parse(source))


def test_bare_return_is_not_nullable_return() -> None:
    """
    title: >-
      Preserve void returns while requiring explicit return none for nulls.
    """
    with pytest.raises(SemanticError, match="must return"):
        analyze(parse("fn missing() -> i32 | none:\n  return\n"))
    analyze(parse("fn missing() -> i32 | none:\n  return none\n"))
    analyze(parse("fn nothing() -> none:\n  return\n"))


def test_nullable_example_builds_and_runs(tmp_path: Path) -> None:
    """
    title: Execute source-level nullable locals, defaults, calls and returns.
    parameters:
      tmp_path:
        type: Path
    """
    root = Path(__file__).resolve().parents[4]
    ArxIO.string_to_buffer((root / "examples/nullable_scalars.x").read_text())
    module = Parser().parse(Lexer().lex())
    executable = tmp_path / "nullable_example"
    ArxBuilder().build(module, str(executable))
    completed = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


def test_null_unwrap_reports_and_cleans_current_owners(tmp_path: Path) -> None:
    """
    title: >-
      Fatal null unwrap guards payload access and cleans local string owners.
    parameters:
      tmp_path:
        type: Path
    """
    module = parse(
        (
            "fn main() -> i32:\n"
            '  var text: string = "owned " + "text"\n'
            "  var x: i32 | none = none\n"
            "  return expect_valid(x)\n"
        )
    )
    builder = ArxBuilder()
    output = builder.translate(module)
    llvm.parse_assembly(output).verify()
    fail = output.index("nullable.unwrap.fail:")
    cleanup = output.index('call void @"free"', fail)
    report = output.index('call void @"__arx_runtime_fail"', cleanup)
    assert fail < cleanup < report
    executable = tmp_path / "null_unwrap"
    builder._build_from_ir(output, str(executable))
    completed = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )
    assert completed.returncode != 0
    assert "ARX-RUNTIME-NULL-001" in completed.stderr
    assert "expect_valid received a null value" in completed.stderr


def test_nullable_class_fields_resolve_aliases() -> None:
    """
    title: Normalize aliased nullable instance fields before layout.
    """
    source = (
        "type Maybe = i32 | none\n"
        "class Box:\n"
        "  @[public, mutable]\n"
        "  value: Maybe = none\n"
    )
    analyzed = analyze(parse(source))
    assert analyzed is not None


def test_nullable_ffi_signature_is_not_c_compatible() -> None:
    """
    title: >-
      The internal nullable aggregate is not implicitly a public C ABI type.
    """
    with pytest.raises(SemanticError, match="not FFI-safe"):
        analyze(parse("extern sink(value: i32 | none) -> none\n"))
