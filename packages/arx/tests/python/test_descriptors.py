"""
title: Arrow-core descriptor lexer, parser and native Arx integration.
"""

from __future__ import annotations

import subprocess

from pathlib import Path

import astx
import pytest

from arx.codegen import ArxBuilder
from arx.exceptions import ParserException, SourceError
from arx.io import ArxIO
from arx.lexer import Lexer, TokenKind
from arx.lexer.syntax import load_syntax_manifest
from arx.parser import Parser
from irx.analysis import SemanticError, analyze
from llvmlite import binding as llvm

FRAGMENTS = {
    **{kind.value: kind.value for kind in astx.LogicalKind},
    **{
        kind: f"{kind}(precision=9, scale=-2)"
        for kind in ("decimal32", "decimal64", "decimal128", "decimal256")
    },
    **{kind: f'{kind}(unit="ns")' for kind in ("time64", "duration")},
    "time32": 'time32(unit="s")',
    "timestamp": 'timestamp(unit="us", timezone="UTC")',
    "fixed_binary": "fixed_binary(byte_width=16)",
    **{
        kind: f"{kind}[item: i32 | none]"
        for kind in ("list", "large_list", "list_view", "large_list_view")
    },
    "fixed_list": "fixed_list(list_size=3)[item: i32 | none]",
    "struct": "struct[number: i32, text: string | none]",
    "map": (
        "map(keys_sorted=true)[entries: struct["
        "key: string, value: i32 | none]]"
    ),
    "sparse_union": (
        "sparse_union(type_codes=[3,127])[number: i32, text: string]"
    ),
    "dense_union": (
        "dense_union(type_codes=[3,127])[number: i32, text: string]"
    ),
    "dictionary": "dictionary(ordered=true)[indices: u16, values: string]",
    "run_end_encoded": "run_end_encoded[run_ends: i32, values: string | none]",
    "extension": (
        'extension(extension_name="arx.example", '
        'extension_metadata="opaque")[storage: binary]'
    ),
}


def parse(source: str) -> astx.Module:
    """
    title: Parse a complete source module using standard Arx entry points.
    parameters:
      source:
        type: str
    returns:
      type: astx.Module
    """
    ArxIO.string_to_buffer(source)
    return Parser().parse(Lexer().lex())


def body_source(body: str) -> str:
    """
    title: Wrap a test body in a valid documented source module.
    parameters:
      body:
        type: str
    returns:
      type: str
    """
    return (
        "```\ntitle: Descriptor regression\n```\nfn main() -> i32:\n"
        + body
        + "\n  return 0\n"
    )


@pytest.mark.parametrize("kind,fragment", FRAGMENTS.items())
def test_all_logical_families_parse_and_analyze(
    kind: str, fragment: str
) -> None:
    """
    title: >-
      All logical families have descriptor syntax, not general value syntax.
    parameters:
      kind:
        type: str
      fragment:
        type: str
    """
    module = parse(body_source(f"  var t: datatype = datatype[{fragment}]"))
    analyze(module)
    function = next(
        node for node in module.block if isinstance(node, astx.FunctionDef)
    )
    literal = function.body.nodes[0].value
    assert isinstance(literal, astx.TypeDescriptorLiteral)
    assert literal.value.kind.value == kind
    assert literal.semantic.resolved_descriptor.literal.physical.c_format


def test_descriptor_builtin_manifest_and_tokens() -> None:
    """
    title: >-
      New descriptor names remain contextual identifiers advertised to editors.
    """
    manifest = load_syntax_manifest().data["builtins"]
    assert {"datatype", "field", "schema"} <= set(manifest["types"])
    queries = {operation.value for operation in astx.DescriptorOperation}
    assert queries <= set(manifest["functions"])
    ArxIO.string_to_buffer(
        "datatype field schema " + " ".join(sorted(queries))
    )
    tokens = Lexer().lex()
    assert all(
        token.kind in {TokenKind.identifier, TokenKind.eof}
        for token in tokens.tokens
    )


@pytest.mark.parametrize(
    "literal",
    [
        "datatype[unknown]",
        "datatype[int32(unknown=2)]",
        "field[x: int32 | string]",
        "schema[x int32]",
        "datatype[]",
    ],
)
def test_malformed_descriptor_syntax_fails_early(literal: str) -> None:
    """
    title: >-
      Malformed literal grammar reports a parser error, not a backend failure.
    parameters:
      literal:
        type: str
    """
    with pytest.raises(ParserException):
        parse(body_source(f"  {literal}"))


@pytest.mark.parametrize(
    "literal",
    [
        "datatype[decimal128(precision=99, scale=2)]",
        'datatype[time32(unit="ns")]',
        "schema[x: i32, x: string]",
        "datatype[list[a: int32, b: int32]]",
        "datatype[map[entries: struct[key: i32 | none, value: i32]]]",
        "schema[x: i32 {key: one, key: two}]",
        "datatype[int32(precision=1)]",
    ],
)
def test_invalid_descriptor_meaning_fails_in_analysis(literal: str) -> None:
    """
    title: Semantic rules stay in IRx and reject unsafe descriptor meanings.
    parameters:
      literal:
        type: str
    """
    module = parse(body_source(f"  {literal}"))
    with pytest.raises(SemanticError):
        analyze(module)


SOURCE = """```
title: Builtin descriptor ownership across calls
```
fn layout() -> schema:
  return schema[count: i64 | none, text: string] {producer: "arx"}

fn first(value: schema) -> field:
  return schema_field(value, 0)

fn name() -> str:
  var s: schema = layout()
  return field_name(first(s))

fn main() -> i32:
  var s: schema = layout()
  var shared: schema = s
  var f: field = first(shared)
  var other: field = f
  other = field[replacement: i32]
  assert schema_nfields(s) == 2
  assert field_nullable(f)
  assert descriptor_equal(field_type(f), datatype[i64])
  assert field_name(other) == "replacement"
  assert name() == "count"
  assert type_bit_width(datatype[bool]) == 1
  assert type_nfields(datatype[list[item: string]]) == 1
  var child: field = type_field(datatype[list[item: string]], 0)
  assert descriptor_equal(child, field[item: string])
  assert descriptor_equal(schema[], schema[])
  assert descriptor_equal(schema[x: i32], schema[x: i32 | none]) == false
  assert conversion_kind(datatype[i32], datatype[i64]) == 1
  assert conversion_kind(datatype[i64], datatype[i8]) == 2
  assert conversion_kind(schema[x: i32], schema[x: i32 | none]) == 1
  return 0
"""


def test_descriptors_pass_return_copy_and_replace_natively(
    tmp_path: Path,
) -> None:
    """
    title: >-
      Real Arx source executes native descriptors and independent name owners.
    parameters:
      tmp_path:
        type: Path
    """
    module = parse(SOURCE)
    builder = ArxBuilder()
    ir_text = builder.translate(module)
    llvm.parse_assembly(ir_text).verify()
    for symbol in (
        "irx_arrow_schema_retain",
        "irx_arrow_field_retain",
        "irx_arrow_field_release",
        "irx_arrow_field_name_copy",
    ):
        assert symbol in ir_text
    executable = tmp_path / "descriptors"
    builder.build(module, str(executable))
    result = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("index", [-1, 0, 2**31])
def test_schema_projection_checks_runtime_bounds(
    tmp_path: Path, index: int
) -> None:
    """
    title: >-
      Empty schema projection fails through the checked native status path.
    parameters:
      tmp_path:
        type: Path
      index:
        type: int
    """
    # Large indices are built as i64 AST literals; Arx default literal widths
    # remain unchanged by the descriptor feature.
    value = astx.DescriptorQuery(
        astx.DescriptorOperation.SCHEMA_FIELD,
        (astx.SchemaLiteral(astx.Schema()), astx.LiteralInt64(index)),
    )
    module = parse(body_source("  var s: schema = schema[]"))
    next(
        node for node in module.block if isinstance(node, astx.FunctionDef)
    ).body.nodes.insert(1, value)
    builder = ArxBuilder()
    executable = tmp_path / "bounds"
    builder.build(module, str(executable))
    result = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 1
    assert "ARX-RUNTIME-ARROW-001" in result.stderr


@pytest.mark.parametrize(
    "literal",
    [
        'schema[] {key: "\ud800"}',
        'datatype[extension(extension_name="demo", '
        'extension_metadata="\ud800")[storage: i32]]',
    ],
)
def test_descriptor_source_metadata_rejects_invalid_unicode(
    literal: str,
) -> None:
    """
    title: Direct source buffers reject invalid UTF-8 at the source boundary.
    parameters:
      literal:
        type: str
    """
    with pytest.raises(SourceError, match="valid UTF-8"):
        parse(body_source("  " + literal))
