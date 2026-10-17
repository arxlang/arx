"""
title: Constructors, references, and resource-owning class execution.
"""

import shutil
import subprocess

from pathlib import Path

import astx
import pytest

from arx.codegen import ArxBuilder
from arx.exceptions import ParserException
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser
from irx.analysis import SemanticError
from llvmlite import binding as llvm

from .file_support import analyze_arx as analyze

COUNTER = """class Counter:
  value: i32 = 0
  fn __init__(self, value: i32 = 3) -> none:
    self.value = value
    return none
  fn __del__(self) -> none:
    print(self.value)
    return none
"""


def parsed(declarations: str, body: str) -> astx.Module:
    """
    title: Parse a documented lifecycle regression.
    parameters:
      declarations:
        type: str
      body:
        type: str
    returns:
      type: astx.Module
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Class lifecycle regression\n```\n"
        + declarations
        + "\nfn main() -> i32:\n"
        + "\n".join("  " + line for line in body.splitlines())
        + "\n  return 0\n"
    )
    return Parser().parse(Lexer().lex())


def run_class(
    tmp_path: Path, declarations: str, body: str
) -> subprocess.CompletedProcess[str]:
    """
    title: Verify LLVM and run native lifecycle behavior.
    parameters:
      tmp_path:
        type: Path
      declarations:
        type: str
      body:
        type: str
    returns:
      type: subprocess.CompletedProcess[str]
    """
    if shutil.which("clang") is None:
        pytest.skip("native lifecycle execution requires clang")
    module = parsed(declarations, body)
    builder = ArxBuilder()
    llvm.parse_assembly(builder.translate(module)).verify()
    output = tmp_path / "program"
    builder.build(module, str(output))
    return subprocess.run(
        [str(output)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )


@pytest.mark.parametrize("arguments", ["", "7", "value=7", "value=7,"])
def test_constructor_forms(tmp_path: Path, arguments: str) -> None:
    """
    title: Constructor defaults and positional/named arguments share one hook.
    parameters:
      tmp_path:
        type: Path
      arguments:
        type: str
    """
    result = run_class(
        tmp_path, COUNTER, f"var value: Counter = Counter({arguments})"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ("3\n" if not arguments else "7\n")


@pytest.mark.parametrize(
    "arguments",
    [
        "1, 2",
        "unknown=1",
        "self=1",
        "1, value=2",
        "value=1, value=2",
        'value="wrong"',
    ],
)
def test_constructor_binding_errors(arguments: str) -> None:
    """
    title: Invalid constructor bindings fail before execution.
    parameters:
      arguments:
        type: str
    """
    with pytest.raises(SemanticError, match="constructor"):
        analyze(parsed(COUNTER, f"Counter({arguments})"))


def test_missing_constructor_parameter() -> None:
    """
    title: Required constructor parameters cannot be silently omitted.
    """
    declarations = COUNTER.replace("value: i32 = 3", "value: i32")
    with pytest.raises(SemanticError, match="missing constructor"):
        analyze(parsed(declarations, "Counter()"))


def test_alias_replacement_and_borrowed_return(tmp_path: Path) -> None:
    """
    title: Aliases and identity returns preserve lifetime and identity.
    parameters:
      tmp_path:
        type: Path
    """
    declarations = (
        COUNTER
        + """fn identity(value: Counter) -> Counter:
  return value
fn produce() -> Counter:
  var local: Counter = Counter(value=4)
  return identity(local)
"""
    )
    result = run_class(
        tmp_path,
        declarations,
        """var first: Counter = produce()
var alias: Counter = first
first = first
first = Counter(value=8)
assert alias.value == 4
print("alive")""",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "alive\n4\n8\n"


def test_keyword_evaluation_order(tmp_path: Path) -> None:
    """
    title: Constructor keyword order is evaluation order, not parameter order.
    parameters:
      tmp_path:
        type: Path
    """
    declarations = """class Pair:
  sum: i32 = 0
  fn __init__(self, first: i32, second: i32 = 2) -> none:
    self.sum = first + second
    return none
fn value(number: i32) -> i32:
  print(number)
  return number
"""
    result = run_class(
        tmp_path,
        declarations,
        "var p: Pair = Pair(second=value(2), first=value(1))\n"
        "assert p.sum == 3",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "2\n1\n"


def test_inheritance_drop_order(tmp_path: Path) -> None:
    """
    title: Shared ancestors initialize once and drop in reverse storage order.
    parameters:
      tmp_path:
        type: Path
    """
    declarations = """class Root:
  fn __init__(self) -> none:
    print("root init")
    return none
  fn __del__(self) -> none:
    print("root drop")
    return none
class Left(Root):
  fn __del__(self) -> none:
    print("left drop")
    return none
class Right(Root):
  fn __del__(self) -> none:
    print("right drop")
    return none
class Child(Left, Right):
  fn __del__(self) -> none:
    print("child drop")
    return none
fn produce() -> Root:
  return Child()
"""
    result = run_class(tmp_path, declarations, "var value: Root = produce()")
    assert result.returncode == 0, result.stderr
    assert (
        result.stdout
        == "root init\nchild drop\nright drop\nleft drop\nroot drop\n"
    )


def test_receiver_pin_before_later_argument_effects(tmp_path: Path) -> None:
    """
    title: Evaluated receivers survive later argument effects.
    parameters:
      tmp_path:
        type: Path
    """
    declarations = (
        COUNTER.replace(
            "  fn __del__",
            """  fn read(self, offset: i32) -> i32:
    return self.value + offset
  fn __del__""",
        )
        + """class Holder:
  child: Counter
  fn __init__(self) -> none:
    self.child = Counter(value=1)
    return none
fn replace_child(holder: Holder) -> i32:
  holder.child = Counter(value=9)
  return 0
"""
    )
    result = run_class(
        tmp_path,
        declarations,
        "var holder: Holder = Holder()\n"
        "assert holder.child.read(replace_child(holder)) == 1",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "1\n9\n"


RESOURCE = """class Log:
  path: str = ""
  handle: file
  fn __init__(self, path: str, mode: str = "w") -> none:
    self.path = path
    self.handle = open(self.path, mode=mode)
    return none
  fn write(self, text: str) -> i64:
    return self.handle.write(text)
  fn close(self) -> none:
    self.handle.close()
    return none
fn create(path: str) -> Log:
  var local: Log = Log(mode="w", path=path)
  return local
fn write_file() -> none:
  var log: Log = create("data" + ".txt")
  assert log.write("saved") == 5
  return none
"""


def test_owned_file_and_string_fields(tmp_path: Path) -> None:
    """
    title: Final class release closes files before the caller's next operation.
    parameters:
      tmp_path:
        type: Path
    """
    result = run_class(
        tmp_path,
        RESOURCE,
        """write_file()
var input: file = open("data.txt")
assert input.read() == "saved"
var log: Log = create("explicit.txt")
log.close()""",
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "data.txt").read_bytes() == b"saved"


@pytest.mark.parametrize(
    "constructor",
    [
        "return none",
        'self.handle = open("x", "w")\n'
        'self.handle = open("y", "w")\nreturn none',
        'self.handle.read()\nself.handle = open("x", "w")\nreturn none',
    ],
)
def test_public_file_fields_use_class_initialization(
    tmp_path: Path, constructor: str
) -> None:
    """
    title: >-
      Public file references may be empty or replaced, but not dereferenced
      empty.
    parameters:
      tmp_path:
        type: Path
      constructor:
        type: str
    """
    declarations = (
        "class Log:\n  handle: file\n  fn __init__(self) -> none:\n"
        + "\n".join("    " + line for line in constructor.splitlines())
        + "\n"
    )
    result = run_class(tmp_path, declarations, "Log()")
    assert result.returncode == (1 if "read()" in constructor else 0), (
        result.stderr
    )
    if "read()" in constructor:
        assert "ARX-RUNTIME-CLASS-001" in result.stderr


@pytest.mark.parametrize("body", ["value.__init__()", "value.__del__()"])
def test_hooks_cannot_be_called_explicitly(body: str) -> None:
    """
    title: Source cannot reinitialize or manually destroy class objects.
    parameters:
      body:
        type: str
    """
    with pytest.raises(SemanticError, match="explicitly"):
        analyze(parsed(COUNTER, "var value: Counter = Counter()\n" + body))


@pytest.mark.parametrize("name", ["__inti__", "__str__", "__new__"])
def test_unsupported_dunder_methods_fail_in_analysis(name: str) -> None:
    """
    title: Parse ordinary identifiers but reject unsupported class protocols.
    parameters:
      name:
        type: str
    """
    declarations = (
        f"class Value:\n  fn {name}(self) -> none:\n    return none\n"
    )
    with pytest.raises(
        SemanticError, match="dunder method names are reserved"
    ):
        analyze(parsed(declarations, "Value()"))


@pytest.mark.parametrize(
    "name", ["init", "deinit", "_helper", "__helper", "helper__"]
)
def test_non_protocol_method_names_remain_ordinary(
    tmp_path: Path, name: str
) -> None:
    """
    title: Old hook names and partial underscore prefixes are ordinary APIs.
    parameters:
      tmp_path:
        type: Path
      name:
        type: str
    """
    declarations = f"""class Value:
  value: i32 = 0
  fn {name}(self, value: i32) -> i32:
    self.value = value
    return self.value
"""
    result = run_class(
        tmp_path,
        declarations,
        "var value: Value = Value()\nassert value.value == 0\n"
        f"assert value.{name}(7) == 7",
    )
    assert result.returncode == 0, result.stderr
    with pytest.raises(SemanticError, match="constructor"):
        analyze(parsed(declarations, "Value(7)"))


@pytest.mark.parametrize(
    "declarations",
    [
        "class Node:\n  child: Node\n",
        "class A:\n  child: B\nclass B:\n  child: A\n",
        "class Base:\n  value: i32 = 0\nclass Node(Base):\n  child: Base\n",
    ],
)
def test_ownership_cycles_are_rejected(declarations: str) -> None:
    """
    title: Ownership graphs reject recursive and subtype cycles.
    parameters:
      declarations:
        type: str
    """
    with pytest.raises(SemanticError, match="cyclic"):
        analyze(parsed(declarations, "return 0"))


def test_null_class_reference_is_checked(tmp_path: Path) -> None:
    """
    title: Empty class slots fail diagnostically instead of dereferencing null.
    parameters:
      tmp_path:
        type: Path
    """
    declarations = COUNTER + "class Holder:\n  child: Counter\n"
    result = run_class(
        tmp_path,
        declarations,
        "var value: Holder = Holder()\nprint(value.child.value)",
    )
    assert result.returncode == 1
    assert "ARX-RUNTIME-CLASS-001" in result.stderr


def test_ordinary_keyword_calls_parse() -> None:
    """
    title: Ordinary method keywords preserve their value expressions.
    """
    module = parsed(COUNTER, "var c: Counter = Counter()\nc.read(offset=1)")
    main = module.nodes[-1]
    assert isinstance(main, astx.FunctionDef)
    call = main.body.nodes[1]
    assert isinstance(call, astx.MethodCall)
    assert [keyword.name for keyword in call.keywords] == ["offset"]


def test_nonprefix_base_fields_in_hooks(tmp_path: Path) -> None:
    """
    title: Base hooks and base views address the concrete object's own fields.
    parameters:
      tmp_path:
        type: Path
    """
    declarations = """class Left:
  left: i32 = 11
class Right:
  right: i32 = 0
  fn __init__(self, value: i32 = 23) -> none:
    self.right = value
    return none
  fn __del__(self) -> none:
    print(self.right)
    return none
class Child(Left, Right):
  child: i32 = 31
fn produce() -> Right:
  return Child()
"""
    result = run_class(
        tmp_path,
        declarations,
        "var base: Right = produce()\n"
        "assert base.right == 23\nbase.right = 29",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "29\n"


def test_owned_field_initializers(tmp_path: Path) -> None:
    """
    title: Declaration initializers bind self and independently own resources.
    parameters:
      tmp_path:
        type: Path
    """
    declarations = (
        COUNTER
        + """class Log:
  path: str = "owned.txt"
  handle: file = open(self.path, mode="w")
  child: Counter = Counter(value=17)
fn write() -> none:
  var log: Log = Log()
  assert log.handle.write("saved") == 5
  log.path = "changed"
  log.path = log.path
  return none
"""
    )
    result = run_class(
        tmp_path,
        declarations,
        "write()\n"
        'var input: file = open("owned.txt")\nassert input.read() == "saved"',
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "17\n"


def test_partial_constructor_drops_only_completed_hooks(
    tmp_path: Path,
) -> None:
    """
    title: Checked failure rolls back resources but skips incomplete hooks.
    parameters:
      tmp_path:
        type: Path
    """
    declarations = """class Base:
  name: str = "base"
  fn __del__(self) -> none:
    print(self.name)
    return none
class Child(Base):
  handle: file
  fn __init__(self) -> none:
    self.handle = open("missing-directory/file.txt", "w")
    return none
  fn __del__(self) -> none:
    print("incomplete")
    return none
"""
    result = run_class(tmp_path, declarations, "Child()")
    assert result.returncode != 0
    assert "ARX-RUNTIME-FILE-001" in result.stderr
    assert result.stdout == "base\n"


@pytest.mark.parametrize(
    "body",
    [
        "var alias: Counter = self\n    return none",
        "self.read()\n    return none",
    ],
)
def test_lifecycle_self_cannot_escape(body: str) -> None:
    """
    title: Hook receivers cannot be aliased or invoke ordinary self methods.
    parameters:
      body:
        type: str
    """
    declaration = (
        """class Counter:
  fn read(self) -> i32:
    return 1
  fn __init__(self) -> none:
    """
        + body
        + "\n"
    )
    with pytest.raises(SemanticError, match="lifecycle self"):
        analyze(parsed(declaration, "Counter()"))


def test_required_base_arguments_are_rejected() -> None:
    """
    title: Implicit base construction never invents forwarding arguments.
    """
    declarations = COUNTER.replace("value: i32 = 3", "value: i32")
    declarations += "class Child(Counter):\n  other: i32 = 0\n"
    with pytest.raises(SemanticError, match="base constructor requires"):
        analyze(parsed(declarations, "Child()"))


def test_parameter_rebinding_keeps_caller_reference(tmp_path: Path) -> None:
    """
    title: Rebinding a parameter replaces only its independent local reference.
    parameters:
      tmp_path:
        type: Path
    """
    declarations = (
        COUNTER
        + """fn rebind(value: Counter) -> none:
  value = Counter(value=8)
  assert value.value == 8
  return none
"""
    )
    result = run_class(
        tmp_path,
        declarations,
        "var original: Counter = Counter(value=4)\nrebind(original)\n"
        "assert original.value == 4\nprint(1)",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "8\n1\n4\n"


def test_lexical_loop_and_early_return_cleanup(tmp_path: Path) -> None:
    """
    title: Loop-body and early-return owners release on their actual exits.
    parameters:
      tmp_path:
        type: Path
    """
    declarations = (
        COUNTER
        + """fn loop() -> none:
  for var number: i32 = 0; number < 3; number + 1:
    var value: Counter = Counter(value=number)
  return none
fn early(flag: bool) -> none:
  var value: Counter = Counter(value=9)
  if flag:
    return none
  else:
    return none
"""
    )
    result = run_class(
        tmp_path, declarations, "loop()\nearly(true)\nearly(false)"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "0\n1\n2\n9\n9\n"


def test_public_file_fields_can_share_one_object(tmp_path: Path) -> None:
    """
    title: >-
      Public class fields alias one stream without copying its native handle.
    parameters:
      tmp_path:
        type: Path
    """
    declarations = """class Log:
  first: file = open("log.txt", "w")
  second: file = self.first
"""
    result = run_class(
        tmp_path,
        declarations,
        'var log: Log = Log()\nlog.first.write("saved")\n'
        'log.second.write("!")',
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "log.txt").read_text() == "saved!"


def test_field_drop_failure_continues_other_fields(tmp_path: Path) -> None:
    """
    title: Native drop failure preserves its error and consumes later fields.
    parameters:
      tmp_path:
        type: Path
    """
    if not Path("/dev/full").exists():
        pytest.skip("requires the POSIX failing-write device")
    declarations = (
        COUNTER
        + """class Failing:
  first: Counter = Counter(value=1)
  handle: file = open("/dev/full", "w")
  second: Counter = Counter(value=2)
  fn __init__(self) -> none:
    self.handle.write("buffered")
    return none
"""
    )
    result = run_class(tmp_path, declarations, "Failing()")
    assert result.returncode != 0
    assert "ARX-RUNTIME-CLASS-001" in result.stderr
    assert result.stdout == "2\n1\n"


def test_base_defaults_use_abi_conversions(tmp_path: Path) -> None:
    """
    title: Default base-hook arguments use the declared ABI width.
    parameters:
      tmp_path:
        type: Path
    """
    declarations = """class Base:
  value: i64 = 0
  fn __init__(self, value: i64 = 7) -> none:
    self.value = value
    return none
class Child(Base):
  extra: i32 = 0
"""
    result = run_class(
        tmp_path,
        declarations,
        "var value: Child = Child()\nassert value.value == 7",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "declaration",
    [
        "class Item:\n  @[static]\n"
        "  fn __init__() -> none:\n    return none\n",
        "class Item:\n"
        "  fn __del__(self, value: i32) -> none:\n    return none\n",
        "class Item:\n  fn __init__(self) -> i32:\n    return 1\n",
        "class Item:\n  fn __init__(self) -> none:\n    return none\n"
        "  fn __init__(self, value: i32) -> none:\n    return none\n",
    ],
)
def test_invalid_hook_declarations(declaration: str) -> None:
    """
    title: Lifecycle hooks cannot acquire unsafe ordinary-method shapes.
    parameters:
      declaration:
        type: str
    """
    with pytest.raises(SemanticError, match="lifecycle hook"):
        analyze(parsed(declaration, ""))


def test_constructor_allocation_failure_releases_argument(
    tmp_path: Path,
) -> None:
    """
    title: Constructor allocation failure consumes its evaluated temporaries.
    parameters:
      tmp_path:
        type: Path
    """
    from irx.builder.runtime.features import (  # noqa: PLC0415
        NativeArtifact,
    )
    from irx.builder.runtime.linking import (  # noqa: PLC0415
        link_executable,
    )

    if shutil.which("clang") is None:
        pytest.skip("native fault injection requires clang")
    declarations = (
        COUNTER
        + """class Holder:
  child: Counter
  fn __init__(self, child: Counter) -> none:
    self.child = child
    return none
"""
    )
    builder = ArxBuilder()
    text = builder.translate(parsed(declarations, "Holder(child=Counter(7))"))
    module = llvm.parse_assembly(text)
    module.verify()
    primary = tmp_path / "module.o"
    primary.write_bytes(builder.translator.target_machine.emit_object(module))
    wrapper = tmp_path / "fault.c"
    wrapper.write_text(
        """#include <stddef.h>
void* __real_calloc(size_t count, size_t size);
void* __wrap_calloc(size_t count, size_t size) {
  static int calls = 0;
  return ++calls == 3 ? NULL : __real_calloc(count, size);
}
""",
        encoding="utf-8",
    )
    program = tmp_path / "program"
    link_executable(
        primary_object=primary,
        output_file=program,
        artifacts=(
            *builder.translator.runtime_features.native_artifacts(),
            NativeArtifact("c_source", wrapper),
        ),
        linker_flags=("-Wl,--wrap=calloc",),
    )
    result = subprocess.run(
        [str(program)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode != 0
    assert "ARX-RUNTIME-CLASS-001" in result.stderr
    assert "allocation failed" in result.stderr
    assert result.stdout == "7\n"


def test_failed_replacement_rolls_back_current_field(tmp_path: Path) -> None:
    """
    title: A consuming release error cannot revisit the stale field generation.
    parameters:
      tmp_path:
        type: Path
    """
    if not Path("/dev/full").exists():
        pytest.skip("requires the POSIX failing-write device")
    declarations = """class Base:
  fn __del__(self) -> none:
    print("base")
    return none
class Failing(Base):
  handle: file = open("/dev/full", "w")
  fn __init__(self) -> none:
    self.handle.write("buffered")
    return none
class Holder:
  child: Base = Failing()
  fn __init__(self) -> none:
    self.child = Base()
    return none
"""
    result = run_class(tmp_path, declarations, "Holder()")
    assert result.returncode != 0
    assert "ARX-RUNTIME-CLASS-001" in result.stderr
    assert result.stdout == "base\nbase\n"


def test_class_literal_container_is_rejected() -> None:
    """
    title: Inferred literal storage cannot hide a strong class reference.
    """
    with pytest.raises(ParserException, match="literal elements"):
        parsed(COUNTER, "[Counter()]")


def test_constructor_in_hook_can_use_later_class(tmp_path: Path) -> None:
    """
    title: Hook construction uses predeclared layouts and dispatch tables.
    parameters:
      tmp_path:
        type: Path
    """
    declarations = """class Holder:
  child: Leaf
  fn __init__(self) -> none:
    self.child = Leaf(value=7)
    return none
class Leaf:
  value: i32 = 0
  fn __init__(self, value: i32) -> none:
    self.value = value
    return none
  fn read(self) -> i32:
    return self.value
"""
    result = run_class(
        tmp_path,
        declarations,
        "var holder: Holder = Holder()\nassert holder.child.read() == 7",
    )
    assert result.returncode == 0, result.stderr


def test_scalar_union_field_is_preserved(tmp_path: Path) -> None:
    """
    title: Resource exclusions do not reject existing scalar-union storage.
    parameters:
      tmp_path:
        type: Path
    """
    declarations = """type Number = i32 | i64
class Value:
  number: Number = 7
  @[private]
  init: i32 = 1
"""
    result = run_class(tmp_path, declarations, "var value: Value = Value()")
    assert result.returncode == 0, result.stderr


def test_string_field_reads_survive_later_replacement(tmp_path: Path) -> None:
    """
    title: Evaluated string fields snapshot their allocation generation.
    parameters:
      tmp_path:
        type: Path
    """
    declarations = """class Log:
  path: str = "old"
fn replace(log: Log) -> i32:
  log.path = "replacement with different storage"
  return 0
fn read(text: str, ignored: i32) -> none:
  assert text == "old"
  return none
"""
    result = run_class(
        tmp_path,
        declarations,
        """var log: Log = Log()
read(log.path, replace(log))
var snapshot: str = log.path
log.path = "third"
assert snapshot == "replacement with different storage"
assert log.path == "third"
""",
    )
    assert result.returncode == 0, result.stderr
