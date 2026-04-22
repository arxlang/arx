"""
title: Test code generation AST output.
"""

from textwrap import dedent

import pytest

from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser


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
            fn pick(grid: ndarray[i32, 2, 2]) -> i32:
              return grid[1, 0] + grid[0, 1]

            fn main() -> i32:
              var grid: ndarray[i32, 2, 2] = [[1, 2], [3, 4]]
              return pick(grid)
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
