"""
title: Test code generation AST output.
"""

from textwrap import dedent

import pytest

from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
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


def test_assertion_reports_before_owner_cleanup() -> None:
    """
    title: Translate source assertions with safe fatal-path string cleanup.
    """
    source = dedent(
        """\
        ```
        title: Assertion ownership regression
        ```
        fn main() -> i32:
          var message: str = "owned " + "message"
          assert false, "assertion failed"
          return 0
        """
    )
    ArxIO.string_to_buffer(source)
    module = Parser().parse(Lexer().lex())
    ir_text = ArxBuilder().translate(module)
    llvm.parse_assembly(ir_text).verify()
    report = ir_text.index('call void @"__arx_assert_report"')
    cleanup = ir_text.index('call void @"free"', report)
    terminate = ir_text.index('call void @"exit"', cleanup)
    assert report < cleanup < terminate


def test_descriptor_literals_use_resolved_native_operations() -> None:
    """
    title: Translate builtin descriptors with checked opaque native calls.
    """
    source = dedent(
        """\
        ```
        title: Descriptor translation regression
        ```
        fn main() -> i32:
          var layout: schema = schema[id: i64 | none]
          var column: field = schema_field(layout, 0)
          assert field_nullable(column)
          assert type_bit_width(field_type(column)) == 64
          return 0
        """
    )
    ArxIO.string_to_buffer(source)
    module = Parser().parse(Lexer().lex())
    ir_text = ArxBuilder().translate(module)
    llvm.parse_assembly(ir_text).verify()
    assert 'call i32 @"irx_arrow_schema_import_copy"' in ir_text
    assert 'call i32 @"irx_arrow_field_release"' in ir_text
    assert 'call i32 @"irx_arrow_runtime_has_feature"' in ir_text


def test_nullable_payload_reads_follow_validity_checks() -> None:
    """
    title: >-
      Translate normalized nullable storage without sentinel payload reads.
    """
    source = (
        "```\ntitle: Nullable translation\n```\n"
        "fn widen(value: i32 | none) -> i64 | none:\n"
        "  return value\n"
        "fn main() -> i32:\n"
        "  var value: i32 | none = none\n"
        "  value = 0\n"
        "  assert expect_valid(widen(value)) == 0\n"
        "  return 0\n"
    )
    ArxIO.string_to_buffer(source)
    module = Parser().parse(Lexer().lex())
    output = ArxBuilder().translate(module)
    llvm.parse_assembly(output).verify()
    assert "irx_arrow_" not in output
    assert "{i1, i32}" in output
    assert "nullable.convert.valid:" in output
    assert "nullable.unwrap.pass:" in output


def test_numeric_prefix_and_fallthrough_return() -> None:
    """
    title: Lower resolved scalar signs after a non-exhaustive source branch.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Scalar prefix and branch regression\n```\n"
        "fn choose(flag: bool) -> i32:\n"
        "  if flag:\n"
        "    return -1\n"
        "  return +2\n"
        "fn main() -> i32:\n"
        "  var real: f32 = -0.5\n"
        "  assert real < 0.0\n"
        "  assert choose(true) < 0\n"
        "  return choose(false)\n"
    )
    output = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(output).verify()
    assert "fneg float" in output
    assert "sub i32 0," in output


def test_array_scalar_payload_load_is_validity_dominated() -> None:
    """
    title: Keep typed native output reads behind status and validity branches.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Array scalar output ordering\n```\n"
        "fn main() -> i32:\n"
        "  var values: array[i32 | none] = array[i32 | none](none)\n"
        "  var item: i32 | none = array_at(values, 0)\n"
        "  if is_valid(item):\n    return item\n"
        "  return 0\n"
    )
    output = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(output).verify()
    assert 'call i32 @"irx_arrow_array_get_int"' in output
    payload_load = output.index('load i64, i64* %"array.scalar.payload"')
    assert output.index("array.scalar.present:") < payload_load
    assert "nullable.proven_payload" in output


def test_repeated_unicode_literals_have_unique_llvm_globals() -> None:
    """
    title: Temporary UTF-8 lowering nodes cannot collide through reused ids.
    """
    body = '  assert "λ" == "λ"\n' * 20
    ArxIO.string_to_buffer(
        "```\ntitle: Repeated UTF-8 literals\n```\n"
        f"fn main() -> i32:\n{body}  return 0\n"
    )
    module = Parser().parse(Lexer().lex())
    output = ArxBuilder().translate(module)
    llvm.parse_assembly(output).verify()


def test_nullable_list_payload_mutation_preserves_validity() -> None:
    """
    title: Refined list mutation lowers through the aggregate payload slot.
    """
    ArxIO.string_to_buffer(
        "fn empty() -> list[i32]:\n  var values: list[i32]\n"
        "  return values\nfn main() -> i32:\n"
        "  var values: list[i32] | none = empty()\n"
        "  if is_valid(values):\n    values.append(7)\n"
        "    assert values[0] == 7\n  return 0\n"
    )
    module = Parser().parse(Lexer().lex())
    text = ArxBuilder().translate(module)
    llvm.parse_assembly(text).verify()
    assert "irx_list_append" in text
    assert "irx_list_destroy" in text
    assert "ARX-RUNTIME-LIST-003" in text
