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
