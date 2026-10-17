"""
title: Keyword argument binding, effects, defaults, and resource lifetimes.
"""

import shutil

from pathlib import Path

import astx
import pytest

from arxpy import ArtifactKind, CompileError, Compiler, ParseError
from irx.analysis.resolved_nodes import SemanticInfo
from llvmlite import binding as llvm

DOC = "```\ntitle: Keyword call regression\n```\n"


def execute(tmp_path: Path, source: str) -> str:
    """
    title: Compile and run a documented keyword-call program.
    parameters:
      tmp_path:
        type: Path
      source:
        type: str
    returns:
      type: str
    """
    if shutil.which("clang") is None:
        pytest.skip("native keyword-call tests require clang")
    compiler = Compiler()
    program = compiler.parse_string(DOC + source)
    artifact = compiler.compile(program, output=tmp_path / "program")
    result = compiler.run(artifact, cwd=tmp_path, timeout=10)
    assert result.exit_code == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize(
    "call",
    [
        "f(a=2, c=9)",
        "f(c=9, a=2)",
        "f(2, c=9)",
        "f(c=9, a=2,)",
    ],
)
def test_keyword_binding_and_middle_defaults(
    tmp_path: Path, call: str
) -> None:
    """
    title: Explicit later parameters leave default holes, not a default suffix.
    parameters:
      tmp_path:
        type: Path
      call:
        type: str
    """
    execute(
        tmp_path,
        f"""fn f(a: i32, b: i32 = a + 1, c: i32 = b + 1) -> i32:
  return a * 100 + b * 10 + c
fn main() -> i32:
  assert {call} == 239
  assert f(a=4) == 456
  return 0
""",
    )


def test_keyword_metadata_preserves_source_order() -> None:
    """
    title: The semantic plan maps source evaluations to ABI positions.
    """
    compiler = Compiler()
    parsed = compiler.parse_string(
        DOC
        + """fn f(a: i32, b: i32 = 3, c: i32 = 4) -> i32:
  return a + b + c
fn main() -> i32:
  return f(c=9, a=2)
"""
    )
    compiler.check(parsed)
    main = next(
        node
        for node in parsed.module.nodes
        if isinstance(node, astx.FunctionDef) and node.name == "main"
    )
    call = main.body.nodes[0].value
    assert isinstance(call.semantic, SemanticInfo)
    assert call.semantic.resolved_call is not None
    plan = call.semantic.resolved_call.arguments
    assert plan is not None
    assert plan.indices == (2, 0)
    assert [value.value for value in plan.evaluations] == [9, 2]
    assert [default.index for default in plan.defaults] == [1]
    artifact = compiler.compile(parsed, kind=ArtifactKind.LLVM_IR)
    assert artifact.llvm_ir is not None
    llvm.parse_assembly(artifact.llvm_ir).verify()


def test_keyword_and_default_evaluation_order(tmp_path: Path) -> None:
    """
    title: >-
      Explicit source order precedes exactly-once declaration-order defaults.
    parameters:
      tmp_path:
        type: Path
    """
    stdout = execute(
        tmp_path,
        """fn mark(value: i32) -> i32:
  print(value)
  return value
fn f(a: i32, b: i32 = mark(a + 1), c: i32 = mark(b + 1)) -> i32:
  return a * 100 + b * 10 + c
fn main() -> i32:
  assert f(c=mark(9), a=mark(2)) == 239
  assert f(a=mark(4)) == 456
  return 0
""",
    )
    assert stdout == "9\n2\n3\n4\n5\n6\n"


def test_method_keywords_defaults_templates_and_overloads(
    tmp_path: Path,
) -> None:
    """
    title: >-
      Ordinary, static, inherited, template and overloaded calls bind names.
    parameters:
      tmp_path:
        type: Path
    """
    execute(
        tmp_path,
        """class Base:
  value: i32 = 4
  fn read(self, a: i32 = self.value, b: i32 = a + 1) -> i32:
    return a * 10 + b
class Derived(Base):
  fn read(self, renamed: i32 = 8, other: i32 = 9) -> i32:
    return renamed * 10 + other
class Math:
  @[static]
  fn combine(a: i32, b: i32 = 3) -> i32:
    return a * 10 + b
  fn choose(self, whole: i32) -> i32:
    return whole
  fn choose(self, decimal: f64) -> i32:
    return 9
  @<T: i32 | f64>
  fn echo(self, value: T, copy: T = value, marker: i32 = 0) -> T:
    return copy
@<T: i32 | f64>
fn first(a: T, b: i32, c: T = a) -> T:
  return c
fn main() -> i32:
  var base: Base = Derived()
  assert base.read(b=7) == 47
  var normal: Base = Base()
  assert normal.read(b=9) == 49
  assert Math.combine(b=5, a=2) == 25
  var math: Math = Math()
  assert math.choose(whole=7) == 7
  assert math.choose(decimal=cast(1.0, f64)) == 9
  assert math.echo(value=3) == 3
  assert math.echo<f64>(value=2.0) == 2.0
  assert first(b=3, a=7) == 7
  assert first(b=3, a=cast(1.0, f64)) == 1.0
  assert first<f64>(b=3, a=1.0) == 1.0
  return 0
""",
    )


@pytest.mark.parametrize(
    "arguments",
    [
        "a=1, a=2",
        "1, a=2",
        "unknown=1",
        "c=2",
        "a=true",
        "1, 2, 3, 4",
    ],
)
def test_invalid_keywords_fail_semantically(arguments: str) -> None:
    """
    title: Binding errors never reach native execution.
    parameters:
      arguments:
        type: str
    """
    compiler = Compiler()
    program = compiler.parse_string(
        DOC
        + f"""fn f(a: i32, b: i32 = 2, c: i32 = 3) -> i32:
  return a
fn main() -> i32:
  return f({arguments})
"""
    )
    with pytest.raises(CompileError):
        compiler.check(program)


@pytest.mark.parametrize(
    "body",
    [
        "f(a=1, 2)",
        "f(*args)",
        "f(**args)",
        "print(message=1)",
        "var values: list[i32]\nvalues.append(1, ignored=2)",
        "var rows = dataframe({value: [1]})\nrows.nrows(ignored=1)",
    ],
)
def test_invalid_keyword_syntax_and_intrinsics(body: str) -> None:
    """
    title: Unsupported intrinsic keywords are rejected, never silently dropped.
    parameters:
      body:
        type: str
    """
    compiler = Compiler()
    source = (
        DOC
        + "fn main() -> i32:\n"
        + "\n".join("  " + line for line in body.splitlines())
        + "\n  return 0\n"
    )
    with pytest.raises((ParseError, CompileError)):
        compiler.check(compiler.parse_string(source))


def test_imported_keywords_and_declaration_default_scope(
    tmp_path: Path,
) -> None:
    """
    title: Imported defaults resolve in their declaration, not the caller.
    parameters:
      tmp_path:
        type: Path
    """
    (tmp_path / "helper.x").write_text(
        DOC
        + """fn seed() -> i32:
  return 4
fn combine(a: i32, b: i32 = seed(), c: i32 = b + 1) -> i32:
  return a * 100 + b * 10 + c
"""
    )
    source = tmp_path / "main.x"
    source.write_text(
        DOC
        + """import combine as f from helper
import helper as helpers
fn seed() -> i32:
  return 9
fn main() -> i32:
  assert f(c=8, a=2) == 248
  assert helpers.combine(c=9, a=3) == 349
  var values: list[i32] = range(stop=3, start=0)
  assert values[2] == 2
  return 0
"""
    )
    if shutil.which("clang") is None:
        pytest.skip("native keyword-call tests require clang")
    compiler = Compiler()
    artifact = compiler.compile(
        compiler.parse_file(source), output=tmp_path / "program"
    )
    result = compiler.run(artifact, cwd=tmp_path, timeout=10)
    assert result.exit_code == 0, result.stderr


def test_file_keywords_pin_receiver_and_snapshot_strings(
    tmp_path: Path,
) -> None:
    """
    title: Native File keywords and class arguments retain borrowed owners.
    parameters:
      tmp_path:
        type: Path
    """
    execute(
        tmp_path,
        """class Owner:
  stream: File = File("first", "w")
  text: str = "original"
  fn replace(self) -> str:
    self.stream = open("second", "w")
    self.text = "changed"
    return "saved"
fn prepare(owner: Owner) -> File:
  owner.text = "after"
  return owner.stream
fn write(stream: File, text: str) -> none:
  stream.write(text=text)
  return none
fn main() -> i32:
  var owner: Owner = Owner()
  owner.stream.write(text=owner.replace())
  write(text=owner.text, stream=prepare(owner=owner))
  assert owner.text == "after"
  owner.stream.close()
  assert File("first").read() == "saved"
  assert open("second").read() == "changed"
  return 0
""",
    )


def test_extern_fixed_keyword(tmp_path: Path) -> None:
    """
    title: Extern keywords bind only the declared fixed ABI parameters.
    parameters:
      tmp_path:
        type: Path
    """
    execute(
        tmp_path,
        """extern abs(value: i32) -> i32
fn main() -> i32:
  assert abs(value=5) == 5
  return 0
""",
    )


def test_keyword_function_lookup_keeps_visible_namespace(
    tmp_path: Path,
) -> None:
    """
    title: Named calls preserve separate callable and lexical-value lookup.
    parameters:
      tmp_path:
        type: Path
    """
    execute(
        tmp_path,
        """fn f(value: i32) -> i32:
  return value
fn main() -> i32:
  var f: i32 = 1
  assert f(value=2) == 2
  assert f == 1
  return 0
""",
    )


def test_nested_default_bindings_restore_caller_parameters(
    tmp_path: Path,
) -> None:
    """
    title: >-
      Recursive calls restore the lexical parameter slots used by defaults.
    parameters:
      tmp_path:
        type: Path
    """
    execute(
        tmp_path,
        """fn f(a: i32, b: i32 = a + 1, c: i32 = b + 1) -> i32:
  if a == 2:
    assert f(c=9, a=4) == 459
    return a * 100 + b * 10 + c
  else:
    return a * 100 + b * 10 + c
fn main() -> i32:
  assert f(c=9, a=2) == 239
  return 0
""",
    )


def test_default_class_argument_survives_later_default_effects(
    tmp_path: Path,
) -> None:
    """
    title: >-
      A default class reference stays pinned when a later default replaces it.
    parameters:
      tmp_path:
        type: Path
    """
    execute(
        tmp_path,
        """class Owner:
  stream: File = File("first", "w")
  fn swap(self) -> i32:
    self.stream = File("second", "w")
    return 7
  fn write(self, s: File = self.stream, i: i32 = self.swap()) -> none:
    s.write(text="default")
    return none
fn main() -> i32:
  var owner: Owner = Owner()
  owner.write()
  assert File("first").read() == "default"
  return 0
""",
    )


def test_file_method_keywords_use_declared_binding_errors() -> None:
    """
    title: >-
      The native method bridge retains ordinary named-argument diagnostics.
    """
    compiler = Compiler()
    with pytest.raises(CompileError) as error:
        compiler.check(
            compiler.parse_string(
                DOC
                + """fn main() -> i32:
  var stream: File = File("unused")
  stream.write("first", text="duplicate")
  return 0
"""
            )
        )
    assert any(
        "duplicate argument 'text'" in item.message
        for item in error.value.diagnostics
    )
