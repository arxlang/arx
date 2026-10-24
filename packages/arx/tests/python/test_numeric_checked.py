"""
title: >-
  Checked numeric source contracts at semantic, LLVM, and native boundaries.
"""

from __future__ import annotations

import shutil
import subprocess

from pathlib import Path

import astx
import pytest

from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.main import FileImportResolver, inject_ambient_builtin_imports
from arx.parser import Parser
from irx.analysis import SemanticError, analyze
from irx.analysis.module_interfaces import ParsedModule
from irx.builder.runtime.exceptions import parse_exception_output
from llvmlite import binding as llvm
from public import private


@private
def numeric_program(body: str, definitions: str = "") -> str:
    """
    title: Build a documented source program with a dynamic main body.
    parameters:
      body:
        type: str
      definitions:
        type: str
    returns:
      type: str
    """
    return (
        "```\ntitle: Checked numeric acceptance\n```\n"
        + definitions
        + "fn main() -> i32:\n"
        + "\n".join("  " + line for line in body.splitlines())
        + "\n  return 0\n"
    )


@private
def translate_numeric(source: str) -> tuple[ArxBuilder, str]:
    """
    title: >-
      Translate through the normal frontend, module resolver, and analyzer.
    parameters:
      source:
        type: str
    returns:
      type: tuple[ArxBuilder, str]
    """
    ArxIO.string_to_buffer(source)
    module = Parser().parse(Lexer().lex(), "numeric_é")
    root = ParsedModule("numeric_é", inject_ambient_builtin_imports(module))
    builder = ArxBuilder()
    text = builder.translate_modules(root, FileImportResolver(()))
    llvm.parse_assembly(text).verify()
    return builder, text


@private
def run_numeric(
    tmp_path: Path, body: str, optimization: int = 0, definitions: str = ""
) -> subprocess.CompletedProcess[str]:
    """
    title: >-
      Execute verified LLVM with bounded time at the requested optimization.
    parameters:
      tmp_path:
        type: Path
      body:
        type: str
      optimization:
        type: int
      definitions:
        type: str
    returns:
      type: subprocess.CompletedProcess[str]
    """
    if shutil.which("clang") is None:
        pytest.skip("native numeric checks require clang")
    builder, text = translate_numeric(numeric_program(body, definitions))
    module = llvm.parse_assembly(text)
    tuning = llvm.create_pipeline_tuning_options(speed_level=optimization)
    with llvm.create_pass_builder(
        builder.translator.target_machine, tuning
    ) as passes:
        with passes.getModulePassManager() as manager:
            manager.run(module, passes)
    module.verify()
    executable = tmp_path / "numeric"
    builder._build_from_ir_result(str(module), str(executable), True, "auto")
    return subprocess.run(
        [str(executable)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )


@pytest.mark.parametrize("optimization", [0, 3])
@pytest.mark.parametrize("width", [8, 16, 32, 64])
@pytest.mark.parametrize("unsigned", [False, True])
@pytest.mark.parametrize("operator", ["+", "-", "*"])
def test_native_integer_overflow(
    tmp_path: Path,
    optimization: int,
    width: int,
    unsigned: bool,
    operator: str,
) -> None:
    """
    title: >-
      Every supported width fails before publication in optimized builds too.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
      width:
        type: int
      unsigned:
        type: bool
      operator:
        type: str
    """
    name = f"{'u' if unsigned else 'i'}{width}"
    maximum = (1 << (width if unsigned else width - 1)) - 1
    minimum = 0 if unsigned else -(1 << (width - 1))
    left = minimum if operator == "-" else maximum
    right = 2 if operator == "*" else 1
    result = run_numeric(
        tmp_path,
        f"var left: {name} = {left}\nvar right: {name} = {right}\n"
        f"left {operator} right\nprint(777)",
        optimization,
    )
    assert result.returncode != 0
    report = parse_exception_output(result.stderr)
    assert report is not None
    assert report.code == "ARX-RUNTIME-ARITHMETIC-001"
    assert report.type_name == "builtins.exceptions::class::OverflowError"
    assert report.source == "numeric_é"
    assert "777" not in result.stdout


@pytest.mark.parametrize("optimization", [0, 3])
@pytest.mark.parametrize(
    "body",
    [
        "var value: i8 = -128\n-value",
        "var value: u8 = 1\n-value",
        "var value: u64 = 18446744073709551615\n++value",
        "var value: i8 = 127\n++value",
        "var value: u8 = 0\n--value",
        "var value: i64 = -9223372036854775808\nvalue / -1",
        "var value: i32 = 1\nvalue / 0",
        "var value: i8 = -12\nmath.square(value)",
        "var value: i8 = -12\ncast(math.square(value), i64)",
        "var value: i32 = 46341\nmath.square(value)",
        "var value: i64 = -9223372036854775808\nmath.abs(value)",
    ],
)
def test_native_arithmetic_failures(
    tmp_path: Path, optimization: int, body: str
) -> None:
    """
    title: >-
      Negation, mutation, division, and generic calls preserve checked intent.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
      body:
        type: str
    """
    result = run_numeric(
        tmp_path, body, optimization, "import math from stdlib\n"
    )
    assert result.returncode != 0
    assert "ARX-RUNTIME-ARITHMETIC-001" in result.stderr


@pytest.mark.parametrize("optimization", [0, 3])
@pytest.mark.parametrize(
    "body",
    [
        "var value: i32 = 128\ncast(value, i8)",
        "var value: i8 = -1\ncast(value, u8)",
        "var value: u64 = 18446744073709551615\ncast(value, i64)",
        "var value: f64 = 9223372036854775808.0\ncast(value, i64)",
        "var value: f64 = 18446744073709551616.0\ncast(value, u64)",
        "var value: f64 = -1.0\ncast(value, u64)",
        "var value: f64 = 0.0 / 0.0\ncast(value, i32)",
        "var value: f64 = 1.0 / 0.0\ncast(value, i64)",
        "var value: f64 = 10000000000000000000000000000000000000000.0\n"
        "cast(value, f32)",
        "var value: u16 = 65535\ncast(value, f16)",
    ],
)
def test_native_conversion_failures(
    tmp_path: Path, optimization: int, body: str
) -> None:
    """
    title: >-
      Narrowing and floating conversions fail before unsafe LLVM instructions.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
      body:
        type: str
    """
    result = run_numeric(tmp_path, body, optimization)
    assert result.returncode != 0
    assert "ARX-RUNTIME-CONVERSION-001" in result.stderr


@pytest.mark.parametrize("optimization", [0, 3])
def test_numeric_common_and_advanced_workflows(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: >-
      Widen before math, opt into wrapping, and use contextual generic
      literals.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    body = """var narrow: i8 = -12
assert math.square<i16>(narrow) == 144
assert math.square<int64>(narrow) == 144
assert math.square(cast(narrow, i64)) == 144
assert wrapping_mul(narrow, narrow) == -112
assert wrapping_cast(300, u8) == 44
assert wrapping_cast(-1, u64) == 18446744073709551615
assert wrapping_add<i8>(127, 1) == -128
assert wrapping_sub<u8>(0, 1) == 255
assert math.min(1, narrow) == -12
assert math.min(narrow, 1) == -12
assert math.min(rhs=1, lhs=narrow) == -12
var negative: i32 = -1
var positive: u32 = 1
assert negative < positive
var precise: f64 = 1.0000000000000002
assert precise > 1.0
var fraction: f64 = -0.5
assert cast(fraction, u64) == 0
var near: f64 = 9223372036854774784.0
assert cast(near, i64) == 9223372036854774784
var half: f16 = cast(32767, f16)
assert half == 32768.0
var small: i8 = 3
assert choose(small) == 3
assert choose(value=small, other=2) == 2
"""
    definitions = """import math from stdlib
@<T: i8 | i16 | i32 | i64>
fn choose(value: T, other: T = 3) -> T:
  return math.min(value, other)
"""
    result = run_numeric(tmp_path, body, optimization, definitions)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "body",
    [
        "var x: i8 = 128",
        "var x: u8 = -1",
        "var x: i64 = 9223372036854775808",
        "var x: f32 = 16777217",
        "var x: i64 = 1\nvar y: f64 = 2.0\nx + y",
        "var x: i64 = -1\nvar y: u64 = 1\nx < y",
        "var x: i8 = 1\nx + 200",
        "2147483647 + 1",
        "cast(2147483647 + 1, i64)",
        "cast(300, i8)",
        "wrapping_cast(1.0, i8)",
        "wrapping_add(true, false)",
        "var a: i8 = 1\nvar b: i16 = 2\nmath.min(a,b)",
    ],
)
def test_invalid_numeric_source_is_rejected(body: str) -> None:
    """
    title: >-
      Invalid domains and evaluated constant overflow fail during analysis.
    parameters:
      body:
        type: str
    """
    with pytest.raises(SemanticError):
        translate_numeric(numeric_program(body, "import math from stdlib\n"))


@pytest.mark.parametrize("value", [-129, 128])
def test_typed_ast_literals_do_not_become_contextual(value: int) -> None:
    """
    title: Direct ASTx clients cannot smuggle invalid concrete typed constants.
    parameters:
      value:
        type: int
    """
    with pytest.raises(SemanticError, match="not representable"):
        analyze(astx.LiteralInt8(value))


@pytest.mark.parametrize("optimization", [0, 3])
def test_unevaluated_operations_do_not_fail(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: >-
      Optimizers neither speculate failures nor discard failing evaluations.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    result = run_numeric(
        tmp_path,
        """var flag: bool = false
var unused: bool = flag and ((2147483647 + 1) == 0)
if flag:
  2147483647 + 1
else:
  print(42)
""",
        optimization,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "42"


@pytest.mark.parametrize("optimization", [0, 3])
def test_nullable_and_floating_conversion_contracts(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: >-
      Nullable conversions skip null payloads and floating casts preserve IEEE
      values.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    result = run_numeric(
        tmp_path,
        """
var missing: nullable[i64] = cast(none, nullable[i64])
var narrowed: nullable[i8] = cast(missing, nullable[i8])
assert is_null(narrowed)
var present: nullable[i64] = 127
assert fill_null(cast(present, nullable[i8]), 0) == 127
var infinity: f64 = 1.0 / 0.0
var small_infinity: f32 = cast(infinity, f32)
assert small_infinity > 0.0
var nan: f64 = 0.0 / 0.0
var small_nan: f32 = cast(nan, f32)
assert !(small_nan == small_nan)
var zero: f64 = -0.0
var negative_zero: f32 = cast(zero, f32)
assert (1.0 / negative_zero) < 0.0
""".strip(),
        optimization,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("optimization", [0, 3])
def test_nullable_conversion_rejects_present_overflow(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: A present nullable payload receives the scalar conversion guard.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    result = run_numeric(
        tmp_path,
        "var present: nullable[i64] = 128\n"
        "var narrow: nullable[i8] = cast(present, nullable[i8])\n"
        "print(123)",
        optimization,
    )
    assert result.returncode != 0
    assert "ARX-RUNTIME-CONVERSION-001" in result.stderr
    assert result.stdout == ""


def test_contextual_mutation_and_container_literals(tmp_path: Path) -> None:
    """
    title: Literal contexts apply to assignments and list append.
    parameters:
      tmp_path:
        type: Path
    """
    result = run_numeric(
        tmp_path,
        "var value: i8 = 1\n"
        "value = 127\n"
        "var items: list[i8]\n"
        "items.append(127)\n"
        "assert items[0] == value",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "body",
    [
        "var value: i64 | f64 = 1",
        "var source: series[i8] = series[i8]([1])\n"
        "var target: series[i64] = cast(source, series[i64])",
    ],
)
def test_unsupported_storage_conversions_are_semantic_errors(
    body: str,
) -> None:
    """
    title: >-
      Reject lossy union storage and unsupported collection casts before LLVM.
    parameters:
      body:
        type: str
    """
    with pytest.raises(SemanticError):
        translate_numeric(numeric_program(body))


@pytest.mark.parametrize(
    "body",
    [
        "var frame: dataframe[x:i8] = dataframe({x:[128]})",
        "var frame: dataframe[x:f32] = dataframe({x:[16777217]})",
        "if true:\n  2147483647 + 1",
        "true && (2147483647 + 1 == 0)",
    ],
)
def test_evaluated_constant_and_column_range_errors(body: str) -> None:
    """
    title: >-
      Statically evaluated constants and column literals use scalar range
      rules.
    parameters:
      body:
        type: str
    """
    with pytest.raises(SemanticError):
        translate_numeric(numeric_program(body))


def test_generic_union_bound_needs_no_runtime_storage(tmp_path: Path) -> None:
    """
    title: >-
      Generic membership accepts domains that cannot share a runtime union.
    parameters:
      tmp_path:
        type: Path
    """
    result = run_numeric(
        tmp_path,
        "assert identity<i64>(9223372036854775807) == 9223372036854775807\n"
        "assert identity<f64>(1.0000000000000002) > 1.0",
        definitions="type Number = i64 | f64\n@<T: Number>\n"
        "fn identity(value: T) -> T:\n  return value\n",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("optimization", [0, 3])
def test_exact_decimal_literals_across_contexts(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: >-
      Exact decimals round once through scalar, container and generic paths.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    exact = "1.000000059604644830901776231257827021181583404541015625"
    definitions = (
        "type Floating = f32 | f64\n"
        "@<T: Floating>\n"
        "fn precise() -> T:\n"
        f"  return {exact}\n"
        "fn default_value(value: f32 = " + exact + ") -> f32:\n"
        "  return value\n"
        "class Constants:\n"
        "  @[public, static, constant]\n"
        f"  value: f32 = {exact}\n"
        "class Values:\n"
        "  tiny: i8 = 7\n"
        f"  wide: f64 = {exact}\n"
        f"  fn __init__(self, tiny: i8 = 9, wide: f64 = {exact}) -> none:\n"
        "    assert self.tiny == 7\n"
        "    assert self.wide == wide\n"
        "    self.tiny = tiny\n"
        "    return none\n"
    )
    body = f"""var value: f32 = {exact}
assert value > 1.0
var negative: f32 = -{exact}
assert negative < -1.0
var half: f16 = 1.00048828125000000000000000000001
assert half > 1.0
var present: nullable[f32] = {exact}
assert fill_null(present, 0.0) == value
var items: list[f32]
items.append({exact})
assert items[0] == value
var vector: tensor[f32, 1] = [{exact}]
assert vector[0] == value
assert Constants.value == value
assert default_value() == value
assert precise<f32>() == value
var wide: f64 = precise<f64>()
assert wide < cast(value, f64)
var instance: Values = Values()
assert instance.tiny == 9
assert instance.wide == wide
var negzero: f32 = -0.0
assert (1.0 / negzero) < 0.0"""
    result = run_numeric(tmp_path, body, optimization, definitions)
    assert result.returncode == 0, result.stderr
