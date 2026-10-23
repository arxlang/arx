"""
title: Test code generation AST output.
"""

import shutil

from pathlib import Path
from textwrap import dedent

import pytest

from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.main import FileImportResolver
from arx.parser import Parser
from irx.analysis.module_interfaces import ParsedModule
from irx.diagnostics import SemanticError
from llvmlite import binding as llvm


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


@pytest.mark.parametrize(
    "module_name,class_name", [("csv", "CSV"), ("parquet", "Parquet")]
)
def test_legacy_format_class_names_are_not_exported(
    module_name: str, class_name: str
) -> None:
    """
    title: Removed format class names do not acquire compatibility aliases.
    parameters:
      module_name:
        type: str
      class_name:
        type: str
    """
    ArxIO.string_to_buffer(
        f"import {class_name} from stdlib.{module_name}\n"
        "fn main() -> i32:\n  return 0\n"
    )
    module = Parser().parse(Lexer().lex(), "legacy_format")
    with pytest.raises(
        SemanticError, match=f"Imported symbol '{class_name}' was not found"
    ):
        ArxBuilder().translate_modules(
            ParsedModule("legacy_format", module), FileImportResolver(())
        )


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
