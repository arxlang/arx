"""
title: Exception semantics across Arx, ASTx, IRx, and the native executable.
"""

import shutil
import subprocess

from pathlib import Path

import pytest

from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.main import FileImportResolver, inject_ambient_builtin_imports
from arx.parser import Parser
from irx.analysis.module_interfaces import ParsedModule
from irx.builder.runtime.exceptions import parse_exception_output
from llvmlite import binding as llvm
from public import private


@private
def exception_source(body: str, definitions: str = "") -> str:
    """
    title: Build a documented exception acceptance program.
    parameters:
      body:
        type: str
      definitions:
        type: str
    returns:
      type: str
    """
    return (
        "```\ntitle: Native exception acceptance\n```\n"
        + definitions
        + "fn main() -> i32:\n"
        + "\n".join("  " + line for line in body.splitlines())
        + "\n  return 0\n"
    )


@private
def run_exception(
    tmp_path: Path,
    body: str,
    definitions: str = "",
    optimization: int = 0,
) -> subprocess.CompletedProcess[str]:
    """
    title: Verify optimized LLVM and run it with bounded execution time.
    parameters:
      tmp_path:
        type: Path
      body:
        type: str
      definitions:
        type: str
      optimization:
        type: int
    returns:
      type: subprocess.CompletedProcess[str]
    """
    if shutil.which("clang") is None:
        pytest.skip("native exception acceptance requires clang")
    ArxIO.string_to_buffer(exception_source(body, definitions))
    tree = Parser().parse(Lexer().lex(), "exceptions_é")
    root = ParsedModule("exceptions_é", inject_ambient_builtin_imports(tree))
    builder = ArxBuilder()
    text = builder.translate_modules(root, FileImportResolver(()))
    module = llvm.parse_assembly(text)
    module.verify()
    tuning = llvm.create_pipeline_tuning_options(speed_level=optimization)
    with llvm.create_pass_builder(
        builder.translator.target_machine, tuning
    ) as passes:
        with passes.getModulePassManager() as manager:
            manager.run(module, passes)
    module.verify()
    executable = tmp_path / "exceptions"
    builder._build_from_ir_result(str(module), str(executable), True, "auto")
    return subprocess.run(
        [str(executable)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


@pytest.mark.parametrize("optimization", [0, 3])
def test_exception_common_workflow(tmp_path: Path, optimization: int) -> None:
    """
    title: Catch a helper's builtin exception and run only the finalizer.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    result = run_exception(
        tmp_path,
        "try:\n"
        "  print(positive_count(-1))\n"
        "except ValueError as error:\n"
        "  print(error.message)\n"
        "else:\n"
        '  print("accepted")\n'
        "finally:\n"
        '  print("finished")',
        "fn positive_count(value: i32) -> i32:\n"
        "  if value < 0:\n"
        '    raise ValueError("count must be nonnegative")\n'
        "  return value\n",
        optimization,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "count must be nonnegative",
        "finished",
    ]
    assert result.stderr == ""


@pytest.mark.parametrize("optimization", [0, 3])
@pytest.mark.parametrize(
    ("body", "output"),
    [
        (
            'try:\n  print("body")\nexcept Exception:\n'
            '  print("handler")\nelse:\n  print("else")\n'
            'finally:\n  print("finally")',
            ["body", "else", "finally"],
        ),
        (
            'try:\n  raise ValueError("bad")\nexcept TypeError:\n'
            '  print("wrong")\nexcept (OSError, ValueError):\n'
            '  print("tuple")\nexcept Exception:\n  print("wrong")',
            ["tuple"],
        ),
        (
            'try:\n  try:\n    raise ValueError("one")\n'
            '  except ValueError:\n    raise TypeError("two")\n'
            '  except TypeError:\n    print("wrong")\n'
            '  finally:\n    print("inner-finally")\n'
            "except TypeError as error:\n  print(error.message)",
            ["inner-finally", "two"],
        ),
        (
            'try:\n  try:\n    print("body")\n'
            '  except OSError:\n    print("wrong")\n'
            '  else:\n    raise OSError("else-failure")\n'
            "except OSError as error:\n  print(error.message)",
            ["body", "else-failure"],
        ),
        (
            'try:\n  raise\nexcept RuntimeError:\n  print("no-active")',
            ["no-active"],
        ),
        (
            'try:\n  raise BaseException("root")\n'
            'except Exception:\n  print("wrong")\n'
            'except:\n  print("bare")',
            ["bare"],
        ),
        (
            'try:\n  try:\n    raise ValueError("old")\n'
            '  finally:\n    raise TypeError("new")\n'
            "except TypeError as error:\n  print(error.message)",
            ["new"],
        ),
    ],
)
def test_exception_region_ordering(
    tmp_path: Path, optimization: int, body: str, output: list[str]
) -> None:
    """
    title: Native handlers and finalizers obey lexical exception regions.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
      body:
        type: str
      output:
        type: list[str]
    """
    result = run_exception(tmp_path, body, optimization=optimization)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == output
    assert result.stderr == ""


@pytest.mark.parametrize("optimization", [0, 3])
def test_finally_replaces_pending_return(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: Finalization can replace returns and pending exceptions.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    result = run_exception(
        tmp_path,
        "print(replace_return())\nprint(replace_error())",
        "fn replace_return() -> i32:\n"
        "  try:\n    return 1\n  finally:\n    return 2\n"
        "fn replace_error() -> i32:\n"
        '  try:\n    raise ValueError("suppressed")\n'
        "  finally:\n    return 3\n",
        optimization,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["2", "3"]
    assert result.stderr == ""


@pytest.mark.parametrize("optimization", [0, 3])
def test_bare_raise_uses_dynamic_handler_state(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: A helper re-raises the outer error after an inner handler exits.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    result = run_exception(
        tmp_path,
        "try:\n"
        "  try:\n"
        '    raise ValueError("outer")\n'
        "  except ValueError:\n"
        "    try:\n"
        '      raise TypeError("inner")\n'
        "    except TypeError:\n"
        '      print("inner-handled")\n'
        "    again()\n"
        "except ValueError as error:\n"
        "  print(error.message)",
        "fn again() -> none:\n  raise\n",
        optimization,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["inner-handled", "outer"]
    assert result.stderr == ""


@pytest.mark.parametrize("optimization", [0, 3])
def test_custom_exception_inherits_constructor(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: A custom nominal subtype keeps its fields through a base handler.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    result = run_exception(
        tmp_path,
        "try:\n"
        '  raise ConfigError(message="configuration missing")\n'
        "except ConfigError as error:\n"
        "  print(error.message)\n"
        "  print(error.code)",
        "class ConfigError(Exception):\n"
        "  ```\n  title: Configuration failure\n  ```\n"
        "  @[public, constant]\n  code: i32 = 7\n",
        optimization,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["configuration missing", "7"]
    assert result.stderr == ""


@pytest.mark.parametrize("optimization", [0, 3])
@pytest.mark.parametrize(
    ("operation", "type_name"),
    [
        ("var value: i8 = 127\nvalue + 1", "OverflowError"),
        ("var divisor: i32 = 0\n7 / divisor", "ZeroDivisionError"),
        ("var value: i32 = 300\ncast(value, i8)", "OverflowError"),
        ("var zero: f64 = 0.0\ncast(zero / zero, i32)", "ValueError"),
        ("var zero: f64 = 0.0\ncast(1.0 / zero, i32)", "OverflowError"),
        ('assert false, "bad assertion"', "AssertionError"),
        ('open("absent-file")', "OSError"),
    ],
)
def test_runtime_failure_can_recover(
    tmp_path: Path, optimization: int, operation: str, type_name: str
) -> None:
    """
    title: Checked failures become catchable without exiting the process.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
      operation:
        type: str
      type_name:
        type: str
    """
    body = (
        "try:\n"
        + "\n".join("  " + line for line in operation.splitlines())
        + '\n  print("unreachable")\n'
        + f"except {type_name}:\n"
        + '  print("caught")\nprint("continued")'
    )
    result = run_exception(tmp_path, body, optimization=optimization)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["caught", "continued"]
    assert result.stderr == ""


@pytest.mark.parametrize("optimization", [0, 3])
def test_exception_unwinds_owned_class_before_caller_handler(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: The throwing frame releases its class owner before caller recovery.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    result = run_exception(
        tmp_path,
        'try:\n  fail()\nexcept ValueError:\n  print("caught")',
        "class Resource:\n"
        "  ```\n  title: Tracked owner\n  ```\n"
        "  marker: i32 = 0\n"
        "  fn __del__(self) -> none:\n"
        "    ```\n    title: Release tracked owner\n    ```\n"
        '    print("released")\n    return none\n'
        "fn fail() -> none:\n"
        "  var resource: Resource = Resource()\n"
        '  raise ValueError("failure")\n',
        optimization,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["released", "caught"]
    assert result.stderr == ""


@pytest.mark.parametrize("optimization", [0, 3])
def test_finally_releases_abandoned_owned_return(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: A finalizer exception releases an evaluated but unpublished return.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    result = run_exception(
        tmp_path,
        'try:\n  produce()\nexcept ValueError:\n  print("caught")',
        "class Resource:\n"
        "  ```\n  title: Returned owner\n  ```\n"
        "  marker: i32 = 0\n"
        "  fn __del__(self) -> none:\n"
        "    ```\n    title: Release abandoned result\n    ```\n"
        '    print("released")\n    return none\n'
        "fn produce() -> Resource:\n"
        "  try:\n    return Resource()\n"
        '  finally:\n    raise ValueError("replacement")\n',
        optimization,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["released", "caught"]
    assert result.stderr == ""


@pytest.mark.parametrize("optimization", [0, 3])
def test_recursive_exception_propagation(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: Recursive calls propagate without publishing a fake result.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    result = run_exception(
        tmp_path,
        'try:\n  print(descend(4))\nexcept ValueError:\n  print("caught")',
        "fn descend(depth: i32) -> i32:\n"
        "  try:\n"
        "    if depth == 0:\n"
        '      raise ValueError("bottom")\n'
        "    return descend(depth - 1)\n"
        "  finally:\n    print(depth)\n",
        optimization,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["0", "1", "2", "3", "4", "caught"]
    assert result.stderr == ""


@pytest.mark.parametrize("optimization", [0, 3])
def test_failing_argument_stops_later_evaluations(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: A failed first argument prevents later operands and the call itself.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    result = run_exception(
        tmp_path,
        "try:\n  consume(fail(), later())\n"
        'except ValueError:\n  print("caught")',
        "fn fail() -> i32:\n"
        '  raise ValueError("first")\n'
        "fn later() -> i32:\n"
        '  print("wrong-later")\n  return 2\n'
        "fn consume(first: i32, second: i32) -> none:\n"
        '  print("wrong-call")\n  return none\n',
        optimization,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["caught"]
    assert result.stderr == ""


@pytest.mark.parametrize("optimization", [0, 3])
@pytest.mark.parametrize("chain", ["implicit", "cause", "suppressed"])
def test_uncaught_exception_chaining(
    tmp_path: Path, optimization: int, chain: str
) -> None:
    """
    title: Report explicit causes, implicit contexts, and suppressed contexts.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
      chain:
        type: str
    """
    suffix = {
        "implicit": "",
        "cause": " from first",
        "suppressed": " from none",
    }
    result = run_exception(
        tmp_path,
        "fail()",
        "fn fail() -> none:\n"
        '  try:\n    raise ValueError("original|é")\n'
        "  except ValueError as first:\n"
        '    raise TypeError("replacement")' + suffix[chain] + "\n",
        optimization,
    )
    assert result.returncode != 0
    report = parse_exception_output(result.stderr)
    assert report is not None, result.stderr
    assert report.type_name.endswith("::class::TypeError")
    assert report.message == "replacement"
    assert report.line > 0 and report.col > 0
    assert report.frames
    assert all(frame.line > 0 and frame.col > 0 for frame in report.frames)
    if chain == "suppressed":
        assert report.related == ()
    else:
        related = report.related[0]
        assert related.role == ("context" if chain == "implicit" else "cause")
        assert related.message == "original|é"
        assert related.type_name.endswith("::class::ValueError")


@pytest.mark.parametrize("optimization", [0, 3])
def test_caught_exception_alias_outlives_binding(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: An owned alias survives automatic removal of the handler binding.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    result = run_exception(
        tmp_path,
        'var saved: Exception = Exception("initial")\n'
        'try:\n  raise ValueError("retained")\n'
        "except ValueError as caught:\n  saved = caught\n"
        "try:\n  raise saved\nexcept ValueError as again:\n"
        "  print(again.message)",
        optimization=optimization,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["retained"]


@pytest.mark.parametrize("optimization", [0, 3])
@pytest.mark.parametrize("kind", ["str", "list[i32]"])
def test_finally_replaces_moved_return(
    tmp_path: Path, optimization: int, kind: str
) -> None:
    """
    title: Replacing a moved return neither double-frees nor publishes it.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
      kind:
        type: str
    """
    initializer = '"temporary"' if kind == "str" else "range(0, 3)"
    result = run_exception(
        tmp_path,
        'try:\n  make()\nexcept ValueError:\n  print("caught")',
        f"fn make() -> {kind}:\n"
        f"  var value: {kind} = {initializer}\n"
        "  try:\n    return value\n"
        '  finally:\n    raise ValueError("replacement")\n',
        optimization,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["caught"]


@pytest.mark.parametrize("optimization", [0, 3])
def test_cleanup_failure_preserves_primary_exception(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: An implicit destructor failure is secondary to an existing failure.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    result = run_exception(
        tmp_path,
        "fail()",
        "class Resource:\n  ```\n  title: Fallible destructor\n  ```\n"
        "  value: i32 = 1\n"
        "  fn __del__(self) -> none:\n"
        '    print("release")\n    raise TypeError("secondary")\n'
        "fn fail() -> none:\n  var owner: Resource = Resource()\n"
        '  raise ValueError("primary")\n',
        optimization,
    )
    assert result.returncode != 0
    assert result.stdout.splitlines() == ["release"]
    report = parse_exception_output(result.stderr)
    assert report is not None, result.stderr
    assert report.message == "primary"
    assert report.type_name.endswith("::class::ValueError")
    assert any(
        item.role == "cleanup" and item.message == "secondary"
        for item in report.related
    )


@pytest.mark.parametrize("optimization", [0, 3])
def test_native_list_and_csv_recovery(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: List bounds and missing CSV input use typed recoverable failures.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    result = run_exception(
        tmp_path,
        "var values: list[i32] = range(0, 2)\n"
        "try:\n  print(values[5])\nexcept IndexError:\n"
        '  print("bounds")\n'
        'try:\n  read_csv("missing.csv")\nexcept OSError:\n'
        '  print("io")\nprint(values[1])',
        "import (read_csv) from stdlib.csv\n",
        optimization,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["bounds", "io", "1"]


@pytest.mark.parametrize("optimization", [0, 3])
def test_failed_constructor_rolls_back_initialized_fields(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: Constructor failure releases fields without destroying partial self.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    result = run_exception(
        tmp_path,
        'try:\n  Container()\nexcept ValueError:\n  print("caught")',
        "class Resource:\n  ```\n  title: Initialized child\n  ```\n"
        "  value: i32 = 1\n"
        '  fn __del__(self) -> none:\n    print("child")\n'
        "class Container:\n  ```\n  title: Partial owner\n  ```\n"
        "  child: Resource = Resource()\n"
        '  fn __init__(self) -> none:\n    raise ValueError("init")\n'
        '  fn __del__(self) -> none:\n    print("wrong-parent")\n',
        optimization,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["child", "caught"]


@pytest.mark.parametrize("optimization", [0, 3])
@pytest.mark.parametrize("kind", ["str", "Resource"])
def test_finalizer_local_catch_preserves_pending_return(
    tmp_path: Path, optimization: int, kind: str
) -> None:
    """
    title: A catch inside finally does not abandon an outer pending return.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
      kind:
        type: str
    """
    definitions = (
        "class Resource:\n  ```\n  title: Returned owner\n  ```\n"
        "  @[public]\n  marker: i32 = 7\n"
        '  fn __del__(self) -> none:\n    print("released")\n'
        if kind == "Resource"
        else ""
    )
    initializer = "Resource()" if kind == "Resource" else '"retained"'
    definitions += (
        f"fn make() -> {kind}:\n"
        f"  var value: {kind} = {initializer}\n"
        "  try:\n    return value\n"
        '  finally:\n    try:\n      raise ValueError("handled")\n'
        '    except ValueError:\n      print("recovered")\n'
    )
    field = ".marker" if kind == "Resource" else ""
    result = run_exception(
        tmp_path,
        f"var value: {kind} = make()\nprint(value{field})",
        definitions,
        optimization,
    )
    assert result.returncode == 0, result.stderr
    expected = (
        ["recovered", "7", "released"]
        if kind == "Resource"
        else ["recovered", "retained"]
    )
    assert result.stdout.splitlines() == expected


@pytest.mark.parametrize("optimization", [0, 3])
@pytest.mark.parametrize("kind", ["str", "ValueError", "Resource"])
def test_try_local_owner_survives_else(
    tmp_path: Path, optimization: int, kind: str
) -> None:
    """
    title: A successful try owner remains alive throughout its else suite.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
      kind:
        type: str
    """
    definitions = (
        "class Resource:\n  ```\n  title: Else owner\n  ```\n"
        "  @[public]\n  marker: i32 = 7\n"
        '  fn __del__(self) -> none:\n    print("released")\n'
        if kind == "Resource"
        else ""
    )
    initializer, field = {
        "str": ('"kept"', ""),
        "ValueError": ('ValueError("kept")', ".message"),
        "Resource": ("Resource()", ".marker"),
    }[kind]
    result = run_exception(
        tmp_path,
        f"try:\n  var value: {kind} = {initializer}\n"
        'except Exception:\n  print("wrong")\n'
        f"else:\n  print(value{field})",
        definitions,
        optimization,
    )
    assert result.returncode == 0, result.stderr
    expected = ["7", "released"] if kind == "Resource" else ["kept"]
    assert result.stdout.splitlines() == expected


@pytest.mark.parametrize("optimization", [0, 3])
def test_return_cleanup_failure_preserves_outer_handler_owners(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: An inner release failure enters its handler before outer cleanup.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    result = run_exception(
        tmp_path,
        "print(run())",
        "class Outer:\n  ```\n  title: Handler owner\n  ```\n"
        "  @[public]\n  marker: i32 = 7\n"
        '  fn __del__(self) -> none:\n    print("outer")\n'
        "class Inner:\n  ```\n  title: Failing cleanup\n  ```\n"
        "  marker: i32 = 0\n"
        '  fn __del__(self) -> none:\n    print("inner")\n'
        '    raise TypeError("cleanup")\n'
        "fn run() -> i32:\n  var outer: Outer = Outer()\n"
        "  try:\n    var inner: Inner = Inner()\n    return 1\n"
        "  except TypeError:\n    print(outer.marker)\n"
        "  return 2\n",
        optimization,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["inner", "7", "outer", "2"]


@pytest.mark.parametrize("optimization", [0, 3])
def test_cleanup_after_try_cannot_reenter_completed_handler(
    tmp_path: Path, optimization: int
) -> None:
    """
    title: A failure outside a completed try cannot jump back to its handler.
    parameters:
      tmp_path:
        type: Path
      optimization:
        type: int
    """
    result = run_exception(
        tmp_path,
        'try:\n  run()\nexcept TypeError:\n  print("caught")',
        "class Resource:\n  ```\n  title: Outer cleanup\n  ```\n"
        "  marker: i32 = 0\n"
        '  fn __del__(self) -> none:\n    print("release")\n'
        '    raise TypeError("cleanup")\n'
        "fn run() -> none:\n  var owner: Resource = Resource()\n"
        "  try:\n    return none\n"
        '  except TypeError:\n    print("wrong")\n'
        '  finally:\n    print("finally")\n',
        optimization,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["finally", "release", "caught"]
