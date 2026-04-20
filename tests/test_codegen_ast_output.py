"""
title: Test code generation AST output.
"""

from pathlib import Path
from textwrap import dedent

import astx
import pytest

from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.main import FileImportResolver, get_module_name_from_file_path
from arx.parser import Parser
from irx.analysis.module_interfaces import ParsedModule
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


def test_translate_modules_supports_namespace_member_calls(
    tmp_path: Path,
) -> None:
    """
    title: Multi-module translation supports module namespace member calls.
    parameters:
      tmp_path:
        type: Path
    """
    project_root = tmp_path / "workspace"
    package_dir = project_root / "src" / "samplepkg"
    package_dir.mkdir(parents=True)

    (project_root / ".arxproject.toml").write_text(
        '[project]\nname = "samplepkg"\nversion = "0.1.0"\n'
        '[environment]\nkind = "conda"\nname = "samplepkg"\n'
        '[build]\nsrc_dir = "src"\nentry = "samplepkg/__init__.x"\n'
        'out_dir = "build"\n',
        encoding="utf-8",
    )
    (package_dir / "__init__.x").write_text(
        dedent(
            """
            import samplepkg.stats as stats

            fn main() -> i32:
              print(stats.sum2(1.0, 2.0))
              return 0
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (package_dir / "stats.x").write_text(
        dedent(
            """
            fn sum2(a: f64, b: f64) -> f64:
              return a + b
            """
        ).lstrip(),
        encoding="utf-8",
    )

    root_file = package_dir / "__init__.x"
    ArxIO.file_to_buffer(str(root_file))
    module_ast = Parser().parse(
        Lexer().lex(),
        get_module_name_from_file_path(str(root_file)),
    )
    assert isinstance(module_ast, astx.Module)

    root = ParsedModule(
        key=module_ast.name,
        ast=module_ast,
        display_name=module_ast.name,
        origin=str(root_file),
    )
    resolver = FileImportResolver((str(root_file),))

    ir_text = ArxBuilder().translate_modules(root, resolver)

    assert "sum2" in ir_text
    llvm.parse_assembly(ir_text)
