"""
title: >-
  Public File construction and reference ownership across the host pipeline.
"""

import shutil

from pathlib import Path

import astx
import pytest

from arx.io import ArxIO
from arx.lexer import Lexer
from arx.main import inject_ambient_builtin_imports
from arx.parser import Parser
from arxpy import ArtifactKind, CompileError, Compiler, ParseError
from irx.analysis.resolved_nodes import ResourceKind, SemanticInfo
from irx.builder.runtime.errors import parse_runtime_failure_output
from llvmlite import binding as llvm

MODULE_DOC = "```\ntitle: Public File regression\n```\n"


@pytest.mark.parametrize("factory", ["open", "File"])
def test_public_file_aliases_and_return(tmp_path: Path, factory: str) -> None:
    """
    title: Both factories return a shared class object through ordinary calls.
    parameters:
      tmp_path:
        type: Path
      factory:
        type: str
    """
    if shutil.which("clang") is None:
        pytest.skip("native File tests require clang")
    path = tmp_path / "message.txt"
    source = f'''```
title: Public File ownership
```
fn make(path: str) -> File:
  return {factory}(file=path, mode="w", encoding="utf-8")
fn write(output: file) -> none:
  output.write("hello")
  return none
fn main() -> i32:
  var output: File = make("{path}")
  var alias: file = output
  assert output == alias
  write(alias)
  output = File("{tmp_path / "other.txt"}", "w")
  assert output != alias
  alias.close()
  alias.close()
  return 0
'''
    compiler = Compiler()
    artifact = compiler.compile(
        compiler.parse_string(source), output=tmp_path / "program"
    )
    result = compiler.run(artifact)
    assert result.exit_code == 0, result.stderr
    assert path.read_text() == "hello"


@pytest.mark.parametrize("factory", ["open", "File"])
def test_factories_resolve_to_class_initialization(factory: str) -> None:
    """
    title: Public factories initialize one private field in a real class.
    parameters:
      factory:
        type: str
    """
    compiler = Compiler()
    parsed = compiler.parse_string(
        MODULE_DOC + "fn main() -> i32:\n"
        f'  var stream: file = {factory}("x", mode="w")\n  return 0\n'
    )
    compiler.check(parsed)
    main = next(
        node
        for node in parsed.module.nodes
        if isinstance(node, astx.FunctionDef)
    )
    declaration = main.body.nodes[0]
    assert isinstance(declaration, astx.VariableDeclaration)
    info = declaration.value.semantic
    assert isinstance(info, SemanticInfo)
    assert info.resolved_file_open is None
    construction = info.resolved_class_construction
    assert construction is not None and construction.native_file is not None
    assert construction.class_.module_key == "builtins.files"
    field = construction.native_file.field
    assert field.member.visibility is astx.VisibilityKind.private
    assert isinstance(info.resolved_type, astx.ClassType)
    assert info.resource_ownership is not None
    assert info.resource_ownership.resource_kind is ResourceKind.CLASS


@pytest.mark.parametrize("factory", ["open", "File"])
@pytest.mark.parametrize(
    "arguments",
    [
        '"x"',
        'file="x"',
        '"x", "r", -1, none, none, none, true, none',
        'mode="rt", file="x", encoding="utf-8", errors="strict",',
    ],
)
def test_file_constructor_argument_forms(factory: str, arguments: str) -> None:
    """
    title: Both entry points accept the same argument profile.
    parameters:
      factory:
        type: str
      arguments:
        type: str
    """
    compiler = Compiler()
    artifact = compiler.compile(
        compiler.parse_string(
            MODULE_DOC + "fn main() -> i32:\n"
            f"  var stream: File = {factory}({arguments})\n  return 0\n"
        ),
        kind=ArtifactKind.LLVM_IR,
    )
    assert artifact.llvm_ir is not None
    llvm.parse_assembly(artifact.llvm_ir).verify()


@pytest.mark.parametrize("factory", ["open", "File"])
@pytest.mark.parametrize(
    "arguments",
    [
        "",
        "1",
        '"x", "wb"',
        '"x", buffering=0',
        '"x", encoding="latin-1"',
        '"x", errors="ignore"',
        '"x", newline=""',
        '"x", closefd=false',
        '"x", opener=1',
        '"x", file="y"',
        '"x", other=1',
        '"x", mode="r", mode="w"',
    ],
)
def test_file_constructor_rejects_unsupported_arguments(
    factory: str, arguments: str
) -> None:
    """
    title: Both entry points reject unsupported options before native effects.
    parameters:
      factory:
        type: str
      arguments:
        type: str
    """
    compiler = Compiler()
    with pytest.raises(CompileError):
        compiler.check(
            compiler.parse_string(
                MODULE_DOC + "fn main() -> i32:\n"
                f"  {factory}({arguments})\n  return 0\n"
            )
        )


@pytest.mark.parametrize(
    "declarations, call",
    [
        ("import File as F from builtins.files\n", 'F(file="x", mode="w")'),
        ("import builtins.files as io\n", 'io.File(mode="w", file="x")'),
        ("import builtins.files\n", 'builtins.files.File("x", mode="w")'),
    ],
)
def test_builtin_imports_and_aliases(declarations: str, call: str) -> None:
    """
    title: Qualified builtin constructors need no filesystem origin.
    parameters:
      declarations:
        type: str
      call:
        type: str
    """
    compiler = Compiler()
    artifact = compiler.compile(
        compiler.parse_string(
            MODULE_DOC + declarations + "fn main() -> i32:\n"
            f"  {call}.close()\n  return 0\n"
        ),
        kind=ArtifactKind.LLVM_IR,
    )
    assert artifact.llvm_ir is not None
    llvm.parse_assembly(artifact.llvm_ir).verify()


@pytest.mark.parametrize(
    "body",
    [
        'var File: i32 = 1\nFile("x")',
        'var stream: File = File("x")\nstream.handle',
        "var stream: NativeFileHandle",
    ],
)
def test_file_privilege_and_shadow_boundaries(body: str) -> None:
    """
    title: Raw type spellings and shadowed names grant no native privilege.
    parameters:
      body:
        type: str
    """
    compiler = Compiler()
    with pytest.raises((CompileError, ParseError)):
        program = compiler.parse_string(
            MODULE_DOC
            + "fn main() -> i32:\n"
            + "\n".join("  " + line for line in body.splitlines())
            + "\n  return 0\n"
        )
        compiler.check(program)


def test_user_file_class_does_not_replace_lowercase_alias() -> None:
    """
    title: Lowercase file remains canonical beside a user-defined File.
    """
    compiler = Compiler()
    artifact = compiler.compile(
        compiler.parse_string(
            MODULE_DOC
            + """class File:
  value: i32 = 7
fn main() -> i32:
  var custom: File = File()
  assert custom.value == 7
  var stream: file = open("x", "w")
  stream.close()
  return 0
"""
        ),
        kind=ArtifactKind.LLVM_IR,
    )
    assert artifact.llvm_ir is not None
    llvm.parse_assembly(artifact.llvm_ir).verify()


def test_builtin_subclasses_are_explicitly_rejected() -> None:
    """
    title: Native File does not inherit an accidentally unopened constructor.
    """
    compiler = Compiler()
    with pytest.raises(CompileError) as failure:
        compiler.check(
            compiler.parse_string(
                MODULE_DOC
                + """class Derived(File):
  value: i32 = 0
fn main() -> i32:
  return 0
"""
            )
        )
    assert any(
        "subclassing builtin File" in item.message
        for item in failure.value.diagnostics
    )


@pytest.mark.parametrize(
    "declaration", ["", "class File:\n  value: i32 = 0\n"]
)
def test_file_dependency_injection_is_idempotent(declaration: str) -> None:
    """
    title: Repeated host analysis does not accumulate synthetic imports.
    parameters:
      declaration:
        type: str
    """
    ArxIO.string_to_buffer(
        MODULE_DOC + declaration + "fn main() -> i32:\n"
        '  var stream: file = open("x")\n  return 0\n'
    )
    module = Parser().parse(Lexer().lex())
    inject_ambient_builtin_imports(module)
    imports = [
        node for node in module.nodes if isinstance(node, astx.ImportFromStmt)
    ]
    inject_ambient_builtin_imports(module)
    assert imports == [
        node for node in module.nodes if isinstance(node, astx.ImportFromStmt)
    ]


def test_file_type_and_constructor_parse_without_reserving_the_name() -> None:
    """
    title: Parsing preserves canonical types and keyword operand order.
    """
    ArxIO.string_to_buffer(
        MODULE_DOC + "fn main() -> i32:\n"
        '  var stream: File = File(mode="w", file="x")\n  return 0\n'
    )
    module = Parser().parse(Lexer().lex())
    main = module.nodes[0]
    assert isinstance(main, astx.FunctionDef)
    declaration = main.body.nodes[0]
    assert isinstance(declaration, astx.VariableDeclaration)
    assert isinstance(declaration.type_, astx.ClassType)
    assert declaration.type_.name == "File"
    call = declaration.value
    assert isinstance(call, astx.FunctionCall)
    assert [argument.name for argument in call.keywords] == ["mode", "file"]
    ArxIO.string_to_buffer("File")
    assert Lexer().get_token().value == "File"


def test_file_method_pins_receiver_across_argument_effects(
    tmp_path: Path,
) -> None:
    """
    title: Later arguments cannot release the receiver of an in-flight write.
    parameters:
      tmp_path:
        type: Path
    """
    if shutil.which("clang") is None:
        pytest.skip("native File tests require clang")
    source = (
        MODULE_DOC
        + """class Owner:
  stream: File = File("first", "w")
  fn replace(self) -> str:
    self.stream = open("second", "w")
    return "saved"
fn main() -> i32:
  var owner: Owner = Owner()
  assert owner.stream.write(owner.replace()) == 5
  owner.stream.write("replacement")
  return 0
"""
    )
    compiler = Compiler()
    artifact = compiler.compile(
        compiler.parse_string(source), output=tmp_path / "program"
    )
    result = compiler.run(artifact, cwd=tmp_path)
    assert result.exit_code == 0, result.stderr
    assert (tmp_path / "first").read_text() == "saved"
    assert (tmp_path / "second").read_text() == "replacement"


@pytest.mark.parametrize("factory", ["open", "File"])
def test_file_constructor_snapshots_path_before_mode_effects(
    tmp_path: Path, factory: str
) -> None:
    """
    title: A field path snapshot survives replacement in a later mode argument.
    parameters:
      tmp_path:
        type: Path
      factory:
        type: str
    """
    if shutil.which("clang") is None:
        pytest.skip("native File tests require clang")
    source = (
        MODULE_DOC
        + f"""class Options:
  path: str = "first"
  fn mode(self) -> str:
    self.path = "second"
    return "w"
fn main() -> i32:
  var options: Options = Options()
  var stream: File = {factory}(file=options.path, mode=options.mode())
  stream.write("snapshot")
  return 0
"""
    )
    compiler = Compiler()
    artifact = compiler.compile(
        compiler.parse_string(source), output=tmp_path / "program"
    )
    result = compiler.run(artifact, cwd=tmp_path)
    assert result.exit_code == 0, result.stderr
    assert (tmp_path / "first").read_text() == "snapshot"
    assert not (tmp_path / "second").exists()


def test_public_aliases_share_cursor_and_closed_state(tmp_path: Path) -> None:
    """
    title: Aliases neither duplicate file descriptors nor reset their cursor.
    parameters:
      tmp_path:
        type: Path
    """
    if shutil.which("clang") is None:
        pytest.skip("native File tests require clang")
    (tmp_path / "source").write_text("shared")
    source = (
        MODULE_DOC
        + """fn main() -> i32:
  var stream: File = File("source")
  var alias: file = stream
  assert stream.read() == "shared"
  assert alias.read() == ""
  alias.close()
  stream.read()
  return 0
"""
    )
    compiler = Compiler()
    artifact = compiler.compile(
        compiler.parse_string(source), output=tmp_path / "program"
    )
    result = compiler.run(artifact, cwd=tmp_path)
    assert result.exit_code == 1
    failure = parse_runtime_failure_output(result.stderr)
    assert failure is not None
    assert failure.code == "ARX-RUNTIME-FILE-001"
    assert "closed" in failure.message
