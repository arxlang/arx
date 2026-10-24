"""
title: Bundled stdlib resolution and packaging tests.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import astx as irx_astx
import pytest

from arx import main as main_module
from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser
from irx.analysis.module_interfaces import ParsedModule
from irx.diagnostics import SemanticError

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


def test_bundled_stdlib_package_data_is_present() -> None:
    """
    title: >-
      Bundled stdlib sources are present on disk and included in packaging.
    """
    stdlib_root = main_module.get_bundled_stdlib_root()
    assert (
        stdlib_root
        == (Path(main_module.__file__).resolve().parent / "stdlib").resolve()
    )
    assert (stdlib_root / "__init__.x").is_file()
    assert (stdlib_root / "math.x").is_file()

    pyproject = tomllib.loads(
        Path("packages/arx/pyproject.toml").read_text("utf-8")
    )
    includes = pyproject["tool"]["poetry"]["include"]
    assert "src/arx/stdlib/**/*.x" in includes

    # Check every declaration's bound once instead of rejecting every type
    # through the entire module pipeline for each helper separately.
    ArxIO.file_to_buffer(str(stdlib_root / "math.x"))
    module = Parser().parse(Lexer().lex(), "math")
    helpers = {
        node.prototype.name: node
        for node in module.nodes
        if isinstance(node, irx_astx.FunctionDef)
    }
    for name in ("abs", "min", "max", "clamp", "square"):
        (parameter,) = irx_astx.get_template_params(helpers[name])
        assert isinstance(parameter.bound, irx_astx.UnionType)
        assert {type(member) for member in parameter.bound.members} == {
            irx_astx.Int8,
            irx_astx.Int16,
            irx_astx.Int32,
            irx_astx.Int64,
        }


def test_file_import_resolver_loads_stdlib_from_bundled_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Stdlib imports resolve from the installed arx package location.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "main.x"
    source.write_text("import math from stdlib\n", encoding="utf-8")

    resolver = main_module.FileImportResolver((str(source),))
    import_node = irx_astx.ImportFromStmt(
        [irx_astx.AliasExpr("math")],
        module="stdlib",
        level=0,
    )

    parent = resolver("main", import_node, "stdlib")
    child = resolver("main", import_node, "stdlib.math")
    stdlib_root = main_module.get_bundled_stdlib_root()

    assert parent.key == "stdlib"
    assert parent.origin is not None
    assert Path(parent.origin) == (stdlib_root / "__init__.x").resolve()

    assert child.key == "stdlib.math"
    assert child.origin is not None
    assert Path(child.origin) == (stdlib_root / "math.x").resolve()


def test_arxmain_compiles_program_using_bundled_stdlib(
    tmp_path: Path,
) -> None:
    """
    title: >-
      Programs can compile against the bundled stdlib without local copies.
    parameters:
      tmp_path:
        type: Path
    """
    source = tmp_path / "main.x"
    source.write_text(
        dedent(
            """
            import math from stdlib

            fn main() -> i32:
              return math.square(4) + math.clamp(0 - 3, 0, 2)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    output_file = tmp_path / "main.o"
    app = main_module.ArxMain(
        input_files=[str(source)],
        output_file=str(output_file),
        is_lib=True,
    )

    emits_executable = app.compile()

    assert emits_executable is False
    assert output_file.is_file()
    assert output_file.stat().st_size > 0


def test_arxmain_rejects_local_stdlib_shadowing(tmp_path: Path) -> None:
    """
    title: Local user modules cannot shadow the reserved stdlib namespace.
    parameters:
      tmp_path:
        type: Path
    """
    local_stdlib = tmp_path / "stdlib"
    local_stdlib.mkdir()
    (local_stdlib / "math.x").write_text(
        "fn square(value: i32) -> i32:\n  return value\n",
        encoding="utf-8",
    )

    source = tmp_path / "main.x"
    source.write_text(
        dedent(
            """
            import math from stdlib

            fn main() -> i32:
              return math.square(4)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    output_file = tmp_path / "main.o"
    app = main_module.ArxMain(
        input_files=[str(source)],
        output_file=str(output_file),
        is_lib=True,
    )

    with pytest.raises(
        SemanticError,
        match="reserved stdlib namespace 'stdlib' cannot be shadowed",
    ):
        app.compile()


@pytest.mark.parametrize(
    "helper,arity,type_,value",
    [
        ("abs", 1, "f32", "1.0"),
        ("min", 2, "f64", "1.0"),
        ("max", 2, "u8", "cast(1, u8)"),
        ("clamp", 3, "u64", "cast(1, u64)"),
        ("square", 1, "bool", "True"),
        ("abs", 1, "nullable[i32]", "none"),
        ("min", 2, "str", '"1"'),
    ],
)
@pytest.mark.parametrize("explicit", [False, True])
def test_math_templates_reject_unsupported_types(
    helper: str, arity: int, type_: str, value: str, explicit: bool
) -> None:
    """
    title: Reject types outside the shared signed bound before LLVM lowering.
    summary: >-
      Cover every helper, rejected type, and inferred/explicit call form
      without repeating the shared SignedInteger bound's Cartesian product.
    parameters:
      helper:
        type: str
      arity:
        type: int
      type_:
        type: str
      value:
        type: str
      explicit:
        type: bool
    """
    specialization = f"<{type_}>" if explicit else ""
    arguments = ", ".join(["value"] * arity)
    ArxIO.string_to_buffer(
        "```\ntitle: Unsupported math specialization\n```\n"
        "import math from stdlib\n"
        "fn main() -> i32:\n"
        f"  var value: {type_} = {value}\n"
        f"  math.{helper}{specialization}({arguments})\n"
        "  return 0\n"
    )
    module = Parser().parse(Lexer().lex(), "unsupported_math")
    root = ParsedModule("unsupported_math", module)
    with pytest.raises(SemanticError, match="does not satisfy bound"):
        ArxBuilder().translate_modules(
            root, main_module.FileImportResolver(())
        )


@pytest.mark.parametrize(
    "call",
    ["min(small, wide)", "max(small, wide)", "clamp(small, small, wide)"],
)
def test_math_templates_require_consistent_inference(call: str) -> None:
    """
    title: Do not silently promote mixed-width arguments during inference.
    parameters:
      call:
        type: str
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Mixed-width math inference\n```\n"
        "import math from stdlib\n"
        "fn main() -> i32:\n"
        "  var small: i8 = cast(1, i8)\n"
        "  var wide: i64 = cast(2, i64)\n"
        f"  math.{call}\n"
        "  return 0\n"
    )
    module = Parser().parse(Lexer().lex(), "mixed_math")
    root = ParsedModule("mixed_math", module)
    with pytest.raises(SemanticError, match="Conflicting inferences"):
        ArxBuilder().translate_modules(
            root, main_module.FileImportResolver(())
        )
