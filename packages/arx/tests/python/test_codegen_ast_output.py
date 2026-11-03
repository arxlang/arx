"""
title: Test code generation AST output.
"""

import shutil
import subprocess
import sys

from pathlib import Path
from textwrap import dedent

import pytest

from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.main import FileImportResolver, inject_ambient_builtin_imports
from arx.parser import Parser
from irx.analysis.module_interfaces import ParsedModule
from irx.diagnostics import SemanticError
from llvmlite import binding as llvm
from llvmlite import ir

from .test_file_class_native import build_audited_file_program


def test_scalar_remainder_and_word_not_translate() -> None:
    """
    title: Surface operators reach checked remainder and Boolean LLVM plans.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Scalar operators\n```\n"
        "extern getchar() -> i32\n"
        "fn main() -> i32:\n"
        "  var value: i32 = getchar()\n"
        "  assert not value % 3 == 2\n"
        "  return value % 3\n"
    )
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert "srem i32" in text
    assert "xor i1" in text
    assert "ARX-RUNTIME-ARITHMETIC-001" in text


@pytest.mark.parametrize(
    "body",
    [
        "  if value < 0:\n"
        "    return -1\n"
        "  elif value == 0:\n"
        "    return 0\n"
        "  else:\n"
        "    return 1\n",
        "  var result: i32 = 9\n"
        "  if value < 0:\n"
        "    return -1\n"
        "  elif value == 0:\n"
        "    result = 0\n"
        "  elif value == 1:\n"
        "    print(value)\n"
        "  return result\n",
    ],
    ids=["all-returning", "mixed-fallthrough-without-else"],
)
def test_elif_chain_translate(body: str) -> None:
    """
    title: Elif lowering preserves terminators and statement result stacks.
    parameters:
      body:
        type: str
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Conditional chains\n```\n"
        "fn choose(value: i32) -> i32:\n" + body + "\n"
        "fn main() -> i32:\n  return choose(0)\n"
    )
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    # Top-level definitions produce functions, not leftover branch values.
    assert all(
        isinstance(value, ir.Function)
        for value in builder.translator.result_stack
    )


def test_elif_condition_requires_boolean() -> None:
    """
    title: Elif conditions retain IRx Boolean validity rather than truthiness.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Invalid elif condition\n```\n"
        "fn main() -> i32:\n"
        "  if false:\n    return 0\n"
        "  elif 1:\n    return 1\n"
        "  return 2\n"
    )
    with pytest.raises(SemanticError, match="condition must be Boolean"):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.mark.parametrize("expression", ["café[0]", "café[:1]", "42[0]"])
def test_unsupported_subscript_reports_its_source(expression: str) -> None:
    """
    title: Unsupported subscripts diagnose the bracket, including Unicode.
    parameters:
      expression:
        type: str
    """
    line = f"  print({expression})"
    source = (
        "```\ntitle: Unsupported indexing\n```\n"
        "fn main() -> i32:\n"
        "  var café: i32 = 42\n"
        f"{line}\n"
        "  return 0\n"
    )
    ArxIO.string_to_buffer(source)
    with pytest.raises(SemanticError) as error:
        ArxBuilder().translate(Parser().parse(Lexer().lex()))
    first = error.value.diagnostics.diagnostics[0]
    assert "subscript access is not supported" in first.message
    location = first.resolved_source()
    assert location is not None
    assert (location.line, location.col) == (6, line.index("[") + 1)


@pytest.fixture(scope="module")
def literal_loop_ir() -> tuple[ArxBuilder, str]:
    """
    title: Translate list loop paths once for safety regressions.
    returns:
      type: tuple[ArxBuilder, str]
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Bounded literal loop storage\n```\n"
        "extern getchar() -> i32\n"
        "fn main() -> i32:\n"
        "  var count: i32 = getchar() * 200\n"
        "  var numbers: list[i32] = range(0, count)\n"
        "  var total: i32 = 0\n"
        "  var j: i32 = 1\n"
        "  for number in numbers:\n"
        "    total = total + [1, 2, 3][j]\n"
        "    assert ![true, false, true][j]\n"
        "    for value in [1, 2]:\n"
        "      total = total + value\n"
        "  assert total == count * 5\n"
        "  return 0\n"
    )
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    return builder, text


def test_literal_loop_allocations_are_in_entry(
    literal_loop_ir: tuple[ArxBuilder, str],
) -> None:
    """
    title: Loop scratch slots cannot accumulate on back edges.
    parameters:
      literal_loop_ir:
        type: tuple[ArxBuilder, str]
    """
    _, text = literal_loop_ir
    module = llvm.parse_assembly(text)
    tested = {"irx.entry.main", "builtins__generators__range"}
    found: set[str] = set()
    for function in module.functions:
        if function.name not in tested:
            continue
        found.add(function.name)
        entry = next(iter(function.blocks))
        for block in function.blocks:
            for instruction in block.instructions:
                if instruction.opcode == "alloca":
                    assert block == entry, (function.name, str(instruction))
    assert found == tested
    assert "irx_list_destroy" in text


@pytest.fixture(scope="module", params=[0, 3])
def literal_loop_binary(
    literal_loop_ir: tuple[ArxBuilder, str],
    tmp_path_factory: pytest.TempPathFactory,
    request: pytest.FixtureRequest,
) -> Path:
    """
    title: Separate compilation setup from repeated constrained execution.
    parameters:
      literal_loop_ir:
        type: tuple[ArxBuilder, str]
      tmp_path_factory:
        type: pytest.TempPathFactory
      request:
        type: pytest.FixtureRequest
    returns:
      type: Path
    """
    builder, text = literal_loop_ir
    module = llvm.parse_assembly(text)
    tuning = llvm.create_pipeline_tuning_options(speed_level=request.param)
    with llvm.create_pass_builder(
        builder.translator.target_machine, tuning
    ) as passes:
        with passes.getModulePassManager() as manager:
            manager.run(module, passes)
    module.verify()
    executable = tmp_path_factory.mktemp("literal-loop") / "probe"
    builder._build_from_ir_result(str(module), str(executable), True, "auto")
    return executable


@pytest.mark.skipif(
    sys.platform != "linux" or shutil.which("clang") is None,
    reason="Linux resource limits and native compiler required",
)
def test_literal_loop_runs_with_bounded_stack(
    literal_loop_binary: Path,
) -> None:
    """
    title: Reuse each optimized binary for short and long small-stack runs.
    parameters:
      literal_loop_binary:
        type: Path
    """
    launcher = (
        "import os, resource, sys; "
        "resource.setrlimit(resource.RLIMIT_CORE, (0, 0)); "
        "resource.setrlimit(resource.RLIMIT_STACK, (524288, 524288)); "
        "os.execv(sys.argv[1], [sys.argv[1]])"
    )
    for count in (1, 50):
        result = subprocess.run(
            [sys.executable, "-c", launcher, str(literal_loop_binary)],
            input=bytes([count]),
            capture_output=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == result.stderr == b""


@pytest.mark.parametrize(
    "code",
    [
        dedent(
            """
            fn main() -> i32:
              print(0.0 + 1.0)
              return 0
            """
        ).lstrip(),
        dedent(
            """
            fn main() -> i32:
              print(1.0 + 2.0 * (3.0 - 2.0))
              return 0
            """
        ).lstrip(),
        dedent(
            """
            fn main() -> i32:
              print(42)
              return 0
            """
        ).lstrip(),
        dedent(
            """
            fn main() -> i32:
              print(3.5)
              return 0
            """
        ).lstrip(),
        dedent(
            """
            fn average(x: f32, y: f32) -> f32:
              return (x + y) * 0.5

            fn main() -> i32:
              print(average(10.0, 20.0))
              return 0
            """
        ).lstrip(),
        dedent(
            """
            fn fib(x: i32) -> i32:
              if x < 3:
                return 1
              else:
                return fib(x-1)+fib(x-2)

            fn main() -> i32:
              print(fib(10))
              return 0
            """
        ).lstrip(),
        dedent(
            """
            @<T: i32 | f64>
            fn add(x: T, y: T) -> T:
              return x + y

            fn main() -> i32:
              print(add(1, 2))
              print(add<f64>(1.0, 2.0))
              return 0
            """
        ).lstrip(),
        dedent(
            """
            type Number = i32 | i64

            fn identity(value: Number) -> Number:
              return value

            fn main() -> i32:
              var value: i64 = identity(5)
              var ok: bool = isinstance(value, Number)
              var name: str = type(value)
              print(name)
              if ok:
                return cast(value, i32)
              else:
                return 1
            """
        ).lstrip(),
        dedent(
            """
            class BaseCounter:
              @[public, mutable]
              value: int32 = 41

              @[protected]
              fn read_seed(self) -> int32:
                return self.value

            class Counter(BaseCounter):
              @[public, static, constant]
              version: int32 = 3

              @[private, mutable]
              internal: int32 = 5

              @[protected]
              fn internal_total(self) -> int32:
                return self.internal + self.value

              fn get(self) -> int32:
                return self.value

              fn read_internal(self) -> int32:
                return self.internal_total()

            class CounterFactory:
              @[public, static]
              fn make() -> Counter:
                return Counter()

              @[public, static]
              fn version_value() -> int32:
                return Counter.version

            fn take_counter(counter: Counter) -> int32:
              return counter.get() + counter.value + counter.read_internal()

            fn main() -> i32:
              var direct: Counter = Counter()
              var built: Counter = CounterFactory.make()
              print(take_counter(direct) + built.get())
              return CounterFactory.version_value() + Counter.version
            """
        ).lstrip(),
        dedent(
            """
            fn pick(grid: tensor[i32, 2, 2]) -> i32:
              return grid[1, 0] + grid[0, 1]

            fn main() -> i32:
              var grid: tensor[i32, 2, 2] = [[1, 2], [3, 4]]
              return pick(grid)
            """
        ).lstrip(),
        dedent(
            """
            fn accept(values: tensor[i32, ...]) -> i32:
              return 0

            fn main() -> i32:
              var values: tensor[i32, 2] = [1, 2]
              return accept(values)
            """
        ).lstrip(),
    ],
)
def test_ast_to_output(code: str) -> None:
    """
    title: Test AST to output.
    parameters:
      code:
        type: str
    """
    lexer = Lexer()
    parser = Parser()
    ir = ArxBuilder()

    ArxIO.string_to_buffer(code)

    module_ast = parser.parse(lexer.lex())

    result = ir.translate(module_ast)
    assert result


@pytest.mark.parametrize("factory", ["open", "File"])
def test_file_operations_translate_with_checked_cleanup(factory: str) -> None:
    """
    title: The public translate path emits status guards and lexical release.
    parameters:
      factory:
        type: str
    """
    ArxIO.string_to_buffer(
        "```\ntitle: File translate regression\n```\n"
        "fn main() -> i32:\n"
        f'  var output: File = {factory}("output.txt", mode="w")\n'
        '  output.write("ok")\n'
        "  output.close()\n"
        "  return 0\n"
    )
    builder = ArxBuilder()
    result = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(result).verify()
    assert "irx_class_create" in result
    assert "irx_file_open" in result
    assert "irx_file_release" in result
    assert "ARX-RUNTIME-FILE-001" in result


def test_numeric_operand_plans_translate_mixed_widths() -> None:
    """
    title: Translate analyzed scalar conversions for arithmetic and comparison.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Numeric operand plan translation\n```\n"
        "fn combine(small: i8, large: i16) -> i16:\n"
        "  var ordered: bool = small < large\n"
        "  return small + large\n"
        "fn main() -> i32:\n"
        "  return combine(cast(1, i8), cast(2, i16))\n"
    )
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert "sext i8" in text
    assert "icmp slt i16" in text
    assert "llvm.sadd.with.overflow.i16" in text
    assert any(
        'call i32 @"main__combine"' in line and "i16*" in line
        for line in text.splitlines()
    )


def test_numeric_union_comparison_has_a_resolved_storage_plan() -> None:
    """
    title: >-
      Numeric unions retain comparison support without a raw LLVM fallback.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Numeric union comparison translation\n```\n"
        "type Number = i32 | i64\n"
        "fn compare(a: Number, b: i32) -> bool:\n"
        "  return a < b\n"
        "fn main() -> i32:\n"
        "  var result: bool = compare(1, 2)\n"
        "  return 0\n"
    )
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert "sext i32" in text
    assert "icmp slt i64" in text


def test_integer_helpers_translate_with_wide_range_arithmetic() -> None:
    """
    title: >-
      Range widens its counter but returns i32 values with checked helpers.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Integer helper translation\n```\n"
        "import math from stdlib\n"
        "fn main() -> i32:\n"
        "  var values: list[i32] = range(2147483646, 2147483647, 2)\n"
        "  return math.clamp(math.abs(values[0]), 0, math.square(46340))\n"
    )
    module = Parser().parse(Lexer().lex(), "integer_helpers")
    root = ParsedModule(
        "integer_helpers", inject_ambient_builtin_imports(module)
    )
    text = ArxBuilder().translate_modules(root, FileImportResolver(()))
    llvm.parse_assembly(text).verify()
    assert "llvm.sadd.with.overflow.i64" in text
    assert "trunc i64" in text
    assert "ARX-RUNTIME-ARITHMETIC-001" in text
    assert "clamp() lower bound must not exceed upper bound" in text


@pytest.mark.parametrize("width", [8, 16, 32, 64])
def test_math_templates_translate_concrete_widths(width: int) -> None:
    """
    title: >-
      Imported aliases lower inferred and explicit concrete template calls.
    parameters:
      width:
        type: int
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Signed math specialization translation\n```\n"
        "import math as arithmetic from stdlib\n"
        "import square as squared from stdlib.math\n"
        "fn main() -> i32:\n"
        f"  var value: i{width} = cast(0 - 3, i{width})\n"
        f"  var zero: i{width} = cast(0, i{width})\n"
        f"  var magnitude: i{width} = arithmetic.abs(value)\n"
        "  arithmetic.min(magnitude, value)\n"
        "  arithmetic.max(magnitude, value)\n"
        "  arithmetic.clamp(magnitude, zero, magnitude)\n"
        f"  squared<int{width}>(value=value)\n"
        "  return 0\n"
    )
    module = Parser().parse(Lexer().lex(), "typed_math")
    root = ParsedModule("typed_math", module)
    text = ArxBuilder().translate_modules(root, FileImportResolver(()))
    llvm.parse_assembly(text).verify()
    assert any(
        "call i32" in line and "square" in line and f"i{width}*" in line
        for line in text.splitlines()
    )
    assert f"llvm.ssub.with.overflow.i{width}" in text
    assert f"llvm.smul.with.overflow.i{width}" in text


def test_class_lifecycle_translate_verifies() -> None:
    """
    title: Constructor binding and lifetime callbacks produce valid LLVM.
    """
    ArxIO.string_to_buffer("""```
title: Lifecycle translate regression
```
class Counter:
  value: i32 = 0
  fn __init__(self, value: i32 = 1) -> none:
    self.value = value
    return none
  fn __del__(self) -> none:
    print(self.value)
    return none
fn main() -> i32:
  var first: Counter = Counter(value=7)
  var alias: Counter = first
  first = Counter()
  return alias.value - 7
""")
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    for symbol in (
        "irx_class_create",
        "irx_class_retain",
        "irx_class_release",
        "irx_class_complete",
    ):
        assert symbol in text
    assert "irx.drop." in text


def test_keyword_default_holes_translate_verifies() -> None:
    """
    title: Named calls with dependent default holes produce valid LLVM.
    """
    ArxIO.string_to_buffer("""```
title: Keyword translate regression
```
fn combine(a: i32, b: i32 = a + 1, c: i32 = b + 1) -> i32:
  return a * 100 + b * 10 + c
fn main() -> i32:
  return combine(c=9, a=2) - 239
""")
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert 'call i32 @"main__combine"' in text


def test_native_package_translate_verifies(tmp_path: Path) -> None:
    """
    title: The public translate path consumes resolved native package features.
    parameters:
      tmp_path:
        type: Path
    """
    fixture = Path(__file__).parents[1] / "fixtures" / "native-package"
    root_dir = tmp_path / "native"
    shutil.copytree(fixture, root_dir)
    path = root_dir / "src" / "main.x"
    source = (
        "```\ntitle: Native translate regression\n```\n"
        "import fixture_create from native_fixture.bridge\n"
        "fn main() -> i32:\n  return cast(fixture_create(size=1), i32)\n"
    )
    path.write_text(source)
    ArxIO.string_to_buffer(source)
    module = Parser().parse(Lexer().lex(), "main")
    resolver = FileImportResolver((str(path),))
    root = resolver.prepare_module(module, "main", str(path))
    builder = ArxBuilder()
    text = builder.translate_modules(root, resolver)
    llvm.parse_assembly(text).verify()
    artifacts = builder.translator.runtime_features.native_artifacts()
    assert any(artifact.path.name == "fixture.c" for artifact in artifacts)
    assert 'declare external i64 @"fixture_create"' in text


def test_arrow_stdlib_translate_uses_resolved_native_capabilities() -> None:
    """
    title: Ordinary Arrow classes lower through registered IRx native bindings.
    """
    ArxIO.string_to_buffer(
        "import (Schema, BatchBuilder) from stdlib.arrow\n"
        "fn main() -> i32:\n"
        "  var schema: Schema = Schema()\n"
        '  schema.add("id", "int64")\n'
        "  var builder: BatchBuilder = BatchBuilder(schema)\n"
        "  builder.append_i64(0, 42)\n"
        "  return cast(builder.finish().nrows(), i32)\n"
    )
    module = Parser().parse(Lexer().lex(), "arrow_translate")
    builder = ArxBuilder()
    ir = builder.translate_modules(
        ParsedModule("arrow_translate", module), FileImportResolver(())
    )
    llvm.parse_assembly(ir).verify()
    assert "irx_rb_api_builder_finish" in ir
    assert "irx_rb_api_batch_destroy" in ir
    assert "record_batch" in (
        builder.translator.runtime_features.active_feature_names()
    )
    assert "parquet" not in (
        builder.translator.runtime_features.active_feature_names()
    )
    assert "irx_rb_api_parquet" not in ir


def test_nullable_dataframe_translate_uses_checked_record_batch_abi() -> None:
    """
    title: >-
      Nullable literals produce verified LLVM without a Parquet dependency.
    """
    ArxIO.string_to_buffer(
        "type Frame = dataframe[id:i64 | none, label:str | none]\n"
        "fn main() -> i32:\n"
        '  var frame: Frame = dataframe({id: [1, none], label: ["a", none]})\n'
        "  return cast(frame.nrows(), i32)\n"
    )
    module = Parser().parse(Lexer().lex(), "nullable_translate")
    builder = ArxBuilder()
    text = builder.translate_modules(
        ParsedModule("nullable_translate", module), FileImportResolver(())
    )
    llvm.parse_assembly(text).verify()
    assert "irx_rb_api_append_i64" in text
    assert "irx_rb_api_append_null" in text
    assert "irx_rb_api_append_utf8" in text
    assert "parquet" not in (
        builder.translator.runtime_features.active_feature_names()
    )


def test_temporal_dataframe_translate_uses_semantic_epoch_values() -> None:
    """
    title: Temporal DataFrame literals lower to verified checked ABI calls.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n"
        "  var frame: dataframe[day:date, clock:time] = "
        'dataframe({day: [date("1969-12-31")], clock: [time("01:02:03")]})\n'
        "  return cast(frame.nrows(), i32)\n"
    )
    module = Parser().parse(Lexer().lex(), "temporal_translate")
    text = ArxBuilder().translate_modules(
        ParsedModule("temporal_translate", module), FileImportResolver(())
    )
    llvm.parse_assembly(text).verify()
    assert "irx_rb_api_append_date" in text
    assert "irx_rb_api_append_time" in text


def test_dynamic_dataframe_cannot_silently_narrow() -> None:
    """
    title: Runtime schemas cannot satisfy static contracts without checking.
    """
    ArxIO.string_to_buffer(
        "fn narrow(frame: dataframe[...]) -> dataframe[id:i64]:\n"
        "  return frame\n"
    )
    module = Parser().parse(Lexer().lex(), "unsafe_narrow")
    with pytest.raises(SemanticError):
        ArxBuilder().translate_modules(
            ParsedModule("unsafe_narrow", module), FileImportResolver(())
        )


def test_nullable_series_translate_verifies() -> None:
    """
    title: Nullable kernels consume semantic plans and produce valid LLVM.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n"
        "  var frame: dataframe[x:i32 | none] = dataframe({x:[1, none]})\n"
        "  var value: nullable[i32] = frame.x[0] + frame.x[1]\n"
        "  assert is_null(value)\n"
        "  return fill_null(value, 0)\n"
    )
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert "irx_arrow_column_compute" in text
    assert "irx_arrow_series_index" in text
    assert "column_valid" in text


@pytest.mark.parametrize(
    "body,message",
    [
        (
            "var bad: nullable[str] = cast(none, nullable[str])",
            "nullable scalars",
        ),
        ("var bad: i32 = frame.x[0]", "cannot assign"),
        (
            "var bad: nullable[i32] = frame.x[0] + true",
            "compatible scalar types",
        ),
        ("var bad: nullable[i32] = frame.x[-1.0]", "integer representable"),
        (
            "var bad: nullable[i32] = ++frame.x[0]",
            "unsupported nullable/Series unary",
        ),
        ("var bad: bool = is_null(1)", "is_null requires"),
        ("var bad: i32 = fill_null(frame.x[0], 1.5)", "matching non-null"),
        ("if frame.x[0]:\n    return 1", "condition must be Boolean"),
        ("var bad: series[i32] = frame.x", "cannot assign"),
        ("var bad: series[bool] = frame.x && frame.x", "require bool"),
    ],
)
def test_nullable_semantic_errors(body: str, message: str) -> None:
    """
    title: Unsupported operations fail in semantics, not during LLVM emission.
    parameters:
      body:
        type: str
      message:
        type: str
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n"
        "  var frame: dataframe[x:i32 | none] = dataframe({x:[1, none]})\n"
        f"  {body}\n  return 0\n"
    )
    with pytest.raises(SemanticError, match=message):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.mark.parametrize("namespace", [False, True])
def test_table_io_translate_uses_resolved_calls(namespace: bool) -> None:
    """
    title: CSV-only imported calls and direct casts emit verified native IR.
    parameters:
      namespace:
        type: bool
    """
    imports = (
        "import stdlib.csv as csv\n"
        if namespace
        else "import (read_csv, write_csv) from stdlib.csv\n"
    )
    prefix = "csv." if namespace else ""
    ArxIO.string_to_buffer(
        imports + "fn main() -> i32:\n"
        f'  var source: dataframe[...] = {prefix}read_csv("in.csv")\n'
        "  var frame: dataframe[id:i64] = cast(source, dataframe[id:i64])\n"
        f'  {prefix}write_csv(frame=frame, path="out.csv")\n'
        "  return 0\n"
    )
    module = Parser().parse(Lexer().lex(), "table_io")
    builder = ArxBuilder()
    text = builder.translate_modules(
        ParsedModule("table_io", module), FileImportResolver(())
    )
    llvm.parse_assembly(text).verify()
    assert "irx_rb_api_read_csv" in text
    assert "irx_rb_api_table_cast" in text
    assert "irx_rb_api_write_csv" in text
    assert (
        "parquet"
        not in builder.translator.runtime_features.active_feature_names()
    )


@pytest.mark.parametrize(
    "module_name,class_name",
    [("csv", "CSVStream"), ("parquet", "ParquetStream")],
)
@pytest.mark.parametrize("alias", [False, True])
def test_format_stream_imports_translate(
    module_name: str, class_name: str, alias: bool
) -> None:
    """
    title: Explicit stream types and import aliases retain native lifecycles.
    parameters:
      module_name:
        type: str
      class_name:
        type: str
      alias:
        type: bool
    """
    local_name = "Stream" if alias else class_name
    imported = f"{class_name} as Stream" if alias else class_name
    ArxIO.string_to_buffer(
        f"import {imported} from stdlib.{module_name}\n"
        "fn main() -> i32:\n"
        f"  var stream: {local_name} = {local_name}()\n"
        "  stream.close()\n"
        "  return 0\n"
    )
    module = Parser().parse(Lexer().lex(), "format_stream")
    builder = ArxBuilder()
    text = builder.translate_modules(
        ParsedModule("format_stream", module), FileImportResolver(())
    )
    llvm.parse_assembly(text).verify()
    for operation in ("new", "close", "destroy"):
        assert f"irx_rb_api_{module_name}_{operation}" in text
    features = builder.translator.runtime_features.active_feature_names()
    assert "record_batch" in features
    assert ("parquet" in features) == (module_name == "parquet")


def test_table_io_names_do_not_grant_capabilities() -> None:
    """
    title: Equally named user functions remain ordinary scalar functions.
    """
    ArxIO.string_to_buffer(
        "fn read_csv(path: i32) -> i32:\n  return path + 1\n"
        "fn write_parquet(frame: i32) -> i32:\n  return frame + 1\n"
        "fn main() -> i32:\n  return write_parquet(read_csv(0))\n"
    )
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert (
        "record_batch"
        not in builder.translator.runtime_features.active_feature_names()
    )
    assert (
        "parquet"
        not in builder.translator.runtime_features.active_feature_names()
    )


@pytest.fixture(scope="module")
def owned_list_ir() -> tuple[ArxBuilder, str]:
    """
    title: Reuse the compiled-language list workflow for translation tests.
    returns:
      type: tuple[ArxBuilder, str]
    """
    source = (Path(__file__).parents[1] / "arx" / "test_lists.x").read_text()
    source += (
        "\nfn main() -> i32:\n"
        "  test_owned_lists()\n"
        "  test_partial_construction()\n"
        "  test_owned_string_elements()\n"
        "  return 0\n"
    )
    ArxIO.string_to_buffer(source)
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    return builder, text


def test_owned_list_translation(owned_list_ir: tuple[ArxBuilder, str]) -> None:
    """
    title: Expression lists use owned storage and non-truncating shared length.
    parameters:
      owned_list_ir:
        type: tuple[ArxBuilder, str]
    """
    _, text = owned_list_ir
    assert 'call i32 @"irx_list_append"' in text
    assert 'call void @"irx_list_destroy"' in text
    assert "irx_collection_length_i64" in text
    assert "irx_collection_length_i32" not in text
    assert "irx_tensor" not in text


@pytest.mark.skipif(shutil.which("clang") is None, reason="clang required")
@pytest.mark.parametrize("optimization", [0, 3])
def test_owned_lists_build_and_run(
    owned_list_ir: tuple[ArxBuilder, str], tmp_path: Path, optimization: int
) -> None:
    """
    title: Native lists retain values through failures and transfers.
    parameters:
      owned_list_ir:
        type: tuple[ArxBuilder, str]
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    builder, text = owned_list_ir
    executable = tmp_path / "owned-lists"
    module = llvm.parse_assembly(text)
    tuning = llvm.create_pipeline_tuning_options(speed_level=optimization)
    with llvm.create_pass_builder(
        builder.translator.target_machine, tuning
    ) as passes:
        with passes.getModulePassManager() as manager:
            manager.run(module, passes)
    module.verify()
    builder._build_from_ir(str(module), str(executable))
    result = subprocess.run(
        [str(executable)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("fn main() -> i32:\n  return cast(len([]), i32)\n", "annotate empty"),
        (
            "fn main() -> i32:\n  return cast(len([[1], [2]]), i32)\n",
            "nested owned",
        ),
        (
            "fn main() -> i32:\n  var x: i8 = [128][0]\n  return 0\n",
            "representable",
        ),
        (
            "fn main() -> i32:\n  var x: i8 = [cast(1, i32)][0]\n  return 0\n",
            "type Int8",
        ),
        ("fn main() -> i32:\n  return len([1])\n", "expects Int32"),
        (
            "fn main() -> i32:\n  return cast(len(1), i32)\n",
            "requires a collection",
        ),
        (
            "fn main() -> i32:\n  return cast(len([1], [2]), i32)\n",
            "one positional",
        ),
        (
            "fn main() -> i32:\n  var len: i32 = 1\n  return len([1])\n",
            "does not resolve to a function",
        ),
        (
            "fn use(x: list[i64]) -> none:\n  return none\n"
            "fn main() -> i32:\n  var x: list[i32] = [1]\n"
            "  use(x)\n  return 0\n",
            "ListType",
        ),
        (
            "fn escape(x: list[i32]) -> list[i32]:\n  return x\n"
            "fn main() -> i32:\n  return 0\n",
            "borrowed",
        ),
        (
            "fn main() -> i32:\n"
            "  var t: tensor[i32, 2, 2] = [[1, 2], [3]]\n  return 0\n",
            "rectangular",
        ),
        (
            "fn main() -> i32:\n  var t: tensor[i32, 2] = [1]\n  return 0\n",
            "shape",
        ),
    ],
)
def test_owned_list_diagnostics(source: str, message: str) -> None:
    """
    title: Invalid collection domains and ownership fail before LLVM lowering.
    parameters:
      source:
        type: str
      message:
        type: str
    """
    ArxIO.string_to_buffer(source)
    with pytest.raises(SemanticError, match=message):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.mark.parametrize("name", ["len", "int", "ord"])
def test_text_builtins_can_be_shadowed_by_a_function(name: str) -> None:
    """
    title: Builtin spelling respects ordinary name resolution.
    parameters:
      name:
        type: str
    """
    ArxIO.string_to_buffer(
        f"fn {name}(value: i32) -> i32:\n  return value\n"
        f"fn main() -> i32:\n  return {name}(0)\n"
    )
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert "irx_collection_length" not in text
    assert "irx_text_" not in text


@pytest.mark.parametrize("name", ["len", "int", "ord"])
def test_local_text_builtin_shadow_is_not_callable(name: str) -> None:
    """
    title: Local values cannot fall through to intrinsic text names.
    parameters:
      name:
        type: str
    """
    ArxIO.string_to_buffer(
        f"fn main() -> i32:\n  var {name}: i32 = 0\n"
        f'  {name}("1")\n  return 0\n'
    )
    with pytest.raises(SemanticError, match="does not resolve to a function"):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.fixture(scope="module")
def text_operations_ir() -> tuple[ArxBuilder, str]:
    """
    title: Translate the Unicode workflow once for native optimization checks.
    returns:
      type: tuple[ArxBuilder, str]
    """
    source = (Path(__file__).parents[1] / "arx" / "test_text.x").read_text()
    source += (
        "\nfn main() -> i32:\n"
        "  test_text_parsing()\n"
        "  test_text_argument_order()\n"
        "  test_text_failures()\n"
        '  var words: list[str] = words_from_file("input.txt")\n'
        '  assert words[0] == "L68"\n'
        '  assert words[1] == "R-12"\n'
        "  return 0\n"
    )
    ArxIO.string_to_buffer(source)
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    return builder, text


def test_text_operations_translation(
    text_operations_ir: tuple[ArxBuilder, str],
) -> None:
    """
    title: Text lowering uses registered status/output APIs and valid LLVM.
    parameters:
      text_operations_ir:
        type: tuple[ArxBuilder, str]
    """
    builder, text = text_operations_ir
    for operation in ("len", "index", "slice", "split", "strip", "int", "ord"):
        assert f'call i32 @"irx_text_{operation}"' in text
    assert {"text", "list", "file"} <= set(
        builder.translator.runtime_features.active_feature_names()
    )
    assert "ARX-RUNTIME-TEXT-001" in text
    failure_blocks = [
        block
        for function in llvm.parse_assembly(text).functions
        for block in function.blocks
        if block.name.startswith("text.failure")
    ]
    assert failure_blocks
    assert all(
        instruction.opcode != "load"
        for block in failure_blocks
        for instruction in block.instructions
    )


@pytest.mark.skipif(shutil.which("clang") is None, reason="clang required")
@pytest.mark.parametrize("optimization", [0, 3])
def test_text_operations_build_and_run(
    text_operations_ir: tuple[ArxBuilder, str],
    tmp_path: Path,
    optimization: int,
) -> None:
    """
    title: Native text survives source release, mutation and checked failures.
    parameters:
      text_operations_ir:
        type: tuple[ArxBuilder, str]
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    builder, text = text_operations_ir
    executable = tmp_path / "text-operations"
    module = llvm.parse_assembly(text)
    tuning = llvm.create_pipeline_tuning_options(speed_level=optimization)
    with llvm.create_pass_builder(
        builder.translator.target_machine, tuning
    ) as passes:
        with passes.getModulePassManager() as manager:
            manager.run(module, passes)
    module.verify()
    builder._build_from_ir(str(module), str(executable))
    (tmp_path / "input.txt").write_text(" L68\nR-12\n", encoding="utf-8")
    result = subprocess.run(
        [str(executable)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""


def test_numeric_sequence_example(tmp_path: Path) -> None:
    """
    title: One generic consumer executes across all surface source families.
    parameters:
      tmp_path:
        type: Path
    """
    if shutil.which("clang") is None:
        pytest.skip("native sequence integration requires clang")
    source = (
        Path(__file__).resolve().parents[4] / "examples/numeric-sequences.x"
    )
    ArxIO.string_to_buffer(source.read_text())
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert "irx_buffer_checked_offset" in text
    executable = tmp_path / "sequences"
    builder._build_from_ir(text, str(executable))
    result = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope="module")
def numeric_bounds_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    title: Compile tensor and sequence boundary failures once.
    parameters:
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: Path
    """
    if shutil.which("clang") is None:
        pytest.skip("native bounds checks require clang")
    source = """
extern getchar() -> i32
fn runtime_read(values: tensor[i64, ...], index: i32) -> i64:
  return values[index]
fn borrowed_read(values: sequence[i64], index: i32) -> i64:
  return values[index]
fn runtime_borrow(values: tensor[i64, ...]) -> i64:
  return borrowed_read(values, 0)
fn main() -> i32:
  var mode: i32 = getchar()
  var index: i32 = getchar() - 1
  var values: tensor[i64, 2] = [7, 9]
  try:
    if mode == 0:
      return cast(values[index], i32)
    if mode == 1:
      return cast(runtime_read(values, index), i32)
    if mode == 2:
      return cast(borrowed_read([7, 9], index), i32)
    if mode == 3:
      var empty: list[i64] = []
      return cast(borrowed_read(empty, 0), i32)
    if mode == 4:
      var matrix: tensor[i64, 1, 2] = [[7, 9]]
      return cast(runtime_borrow(matrix), i32)
    var copied: list[i64] = list(values, max_items=index)
    return cast(len(copied), i32)
  except IndexError:
    return 10
  except ValueError:
    return 11
"""
    ArxIO.string_to_buffer(source)
    module = Parser().parse(Lexer().lex(), "numeric_bounds")
    builder = ArxBuilder()
    text = builder.translate_modules(
        ParsedModule("numeric_bounds", inject_ambient_builtin_imports(module)),
        FileImportResolver(()),
    )
    llvm.parse_assembly(text).verify()
    executable = tmp_path_factory.mktemp("numeric-bounds") / "probe"
    builder._build_from_ir(text, str(executable))
    return executable


@pytest.mark.parametrize(
    "mode,index,expected",
    [
        (0, 0, 7),
        (0, -1, 10),
        (0, 2, 10),
        (1, 1, 9),
        (1, -1, 10),
        (1, 2, 10),
        (2, 0, 7),
        (2, -1, 10),
        (2, 2, 10),
        (3, 0, 10),
        (4, 0, 11),
        (5, -1, 11),
        (5, 1, 11),
        (5, 2, 2),
    ],
)
def test_numeric_bounds_are_recoverable(
    numeric_bounds_binary: Path, mode: int, index: int, expected: int
) -> None:
    """
    title: Check rank, empty and signed bounds before reads or publication.
    parameters:
      numeric_bounds_binary:
        type: Path
      mode:
        type: int
      index:
        type: int
      expected:
        type: int
    """
    result = subprocess.run(
        [str(numeric_bounds_binary)],
        input=bytes([mode, index + 1]),
        capture_output=True,
        check=False,
    )
    assert result.returncode == expected, result.stderr


@pytest.mark.parametrize("arguments", ["[1], typed", "typed, [1]"])
def test_nested_template_literal_context(arguments: str) -> None:
    """
    title: Concrete siblings and explicit arguments contextualize list[T].
    parameters:
      arguments:
        type: str
    """
    parameters = (
        "values: list[T], seed: T"
        if arguments.startswith("[")
        else "seed: T, values: list[T]"
    )
    ArxIO.string_to_buffer(
        f"@<T: i32 | i64>\nfn pick({parameters}) -> T:\n"
        "  return values[0]\n"
        "fn main() -> i32:\n"
        "  var typed: i64 = 7\n"
        f"  assert pick({arguments}) == 1\n"
        f"  assert pick<i64>({arguments}) == 1\n"
        "  return 0\n"
    )
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert "irx_list_append" in text


@pytest.fixture(scope="module")
def binary_file_program(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    title: Verify and compile the byte workflow once without Arrow artifacts.
    parameters:
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: Path
    """
    if shutil.which("clang") is None:
        pytest.skip("binary file checks require clang")
    source = Path(__file__).parents[4] / "examples/binary-files.x"
    ArxIO.string_to_buffer(source.read_text())
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    artifacts = builder.translator.runtime_features.native_artifacts()
    assert all("arrow" not in str(artifact.path) for artifact in artifacts)
    assert "irx_file_read_bytes" in text and "irx_file_write_bytes" in text
    executable = tmp_path_factory.mktemp("binary-workflow") / "program"
    if sys.platform == "linux":
        return build_audited_file_program(builder, text, executable.parent)
    builder._build_from_ir(text, str(executable))
    return executable


def test_binary_file_roundtrip(
    binary_file_program: Path, tmp_path: Path
) -> None:
    """
    title: Independently inspect all bytes, append, empty writes and lifetimes.
    parameters:
      binary_file_program:
        type: Path
      tmp_path:
        type: Path
    """
    result = subprocess.run(
        [str(binary_file_program)],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    if sys.platform == "linux":
        assert b"AUDIT live=0 opened=6 released=6" in result.stderr
    assert (tmp_path / "binary-output.dat").read_bytes() == bytes(
        range(256)
    ) * 2
    assert (tmp_path / "binary-empty.dat").read_bytes() == b""
