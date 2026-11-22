"""
title: Bundled stdlib resolution and packaging tests.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib

from pathlib import Path
from textwrap import dedent
from typing import cast

import astx as irx_astx
import pytest

from arx import main as main_module
from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser
from arxpy import ArtifactKind, Compiler
from irx.analysis import analyze_modules
from irx.analysis.compute import ComputePlan
from irx.analysis.extensions.records import CALL_PLAN
from irx.analysis.module_interfaces import ParsedModule
from irx.analysis.resolved_nodes import SemanticInfo
from irx.analysis.types import same_type
from irx.diagnostics import SemanticError
from llvmlite import binding as llvm

from .test_app_paths import _write_installed_arx_distribution


def test_installed_generic_math_literal_inference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    title: Installed pure-Arx wrappers share math inference and specialization.
    parameters:
      tmp_path: Temporary installed package and compiled consumer.
      monkeypatch: Fixture for replacing installed-package discovery paths.
    """
    if shutil.which("clang") is None or shutil.which("c++") is None:
        pytest.skip("compiled math checks require native compilers")
    document = "```\ntitle: Installed generic math fixture\n```\n"
    site = tmp_path / "installed"
    package = _write_installed_arx_distribution(
        site,
        "arx-generic-math-fixture",
        "library",
        {
            "__init__.x": document + "import rooted from library.kernels\n",
            "kernels.x": document
            + (
                "import math from stdlib\n"
                "@<T: f64 | nullable[f64] | "
                "series[f64] | series[nullable[f64]]>\n"
                "fn rooted(value: T) -> T:\n"
                "  return math.sqrt(value)\n"
            ),
        },
    )
    assert all(
        path.suffix in {".x", ".toml"}
        for path in package.rglob("*")
        if path.is_file()
    )
    app = tmp_path / "app"
    app.mkdir()
    (app / ".arxproject.toml").write_text(
        '[project]\nname="consumer"\nversion="0"\n'
        'dependencies=["arx-generic-math-fixture"]\n',
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(site))
    monkeypatch.chdir(app)
    source = document + (
        "import math from stdlib\n"
        "import rooted from library\n"
        "import kernels from library\n"
        "fn main() -> i32:\n"
        "  direct: f64 = math.sqrt(9.0)\n"
        "  inferred: f64 = rooted(9.0)\n"
        "  expression: f64 = kernels.rooted(3.0 + 6.0)\n"
        "  value: f64 = 9.0\n"
        "  typed: f64 = rooted(value)\n"
        "  explicit: f64 = rooted<f64>(9.0)\n"
        "  lifted: nullable[f64] = rooted<nullable[f64]>(9.0)\n"
        "  assert inferred == direct\n"
        "  assert expression == direct\n"
        "  assert typed == direct\n"
        "  assert explicit == direct\n"
        "  assert not is_null(lifted)\n"
        "  assert fill_null(lifted, 0.0) == direct\n"
        "  missing: nullable[f64] = none\n"
        "  assert is_null(rooted(missing))\n"
        "  frame: dataframe[x:f64, y:f64 | none] = "
        "dataframe({x:[9.0, 4.0], y:[9.0, none]})\n"
        "  roots: series[f64] = rooted(frame.x)\n"
        "  optional_roots: series[nullable[f64]] = kernels.rooted(frame.y)\n"
        "  assert roots[0] == direct\n"
        "  assert roots[1] == 2.0\n"
        "  assert fill_null(optional_roots[0], 0.0) == direct\n"
        "  assert is_null(optional_roots[1])\n"
        "  return 0\n"
    )
    path = app / "main.x"
    path.write_text(source, encoding="utf-8")
    ArxIO.string_to_buffer(source)
    module = Parser().parse(Lexer().lex(), "main")
    root = ParsedModule(
        "main", main_module.inject_ambient_builtin_imports(module)
    )
    builder = ArxBuilder()
    text = builder.translate_modules(
        root, main_module.FileImportResolver((str(path),))
    )
    llvm.parse_assembly(text).verify()
    main = next(
        node
        for node in module.nodes
        if isinstance(node, irx_astx.FunctionDef) and node.name == "main"
    )
    calls = {
        node.name: cast(SemanticInfo, node.value.semantic)
        for node in main.body.nodes
        if isinstance(node, irx_astx.VariableDeclaration)
        and node.name
        in {"direct", "inferred", "expression", "typed", "explicit", "lifted"}
    }
    selected = calls["inferred"].resolved_function
    assert selected is not None and selected.specialization_key is not None
    for name in ("expression", "typed", "explicit"):
        assert calls[name].resolved_function is selected
    direct = calls["direct"].facts.get(CALL_PLAN)
    assert isinstance(direct, ComputePlan)
    assert same_type(calls["inferred"].resolved_type, direct.result_type)
    nullable = calls["lifted"].resolved_function
    assert nullable is not None
    assert nullable.specialization_key != selected.specialization_key
    binary = app / "program"
    builder._build_from_ir_result(text, str(binary), True, "auto")
    result = subprocess.run(
        [str(binary)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("kernel", ["sqrt", "exp"])
def test_math_compute_plans_through_source_reexports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kernel: str
) -> None:
    """
    title: Resolve installed source reexports and nullable shapes before LLVM.
    parameters:
      tmp_path: Temporary directory for this test.
      monkeypatch: Fixture for temporarily replacing dependencies and settings.
      kernel: Kernel.
    """
    document = "```\ntitle: Math semantic consumer\n```\n"
    site = tmp_path / "installed"
    package = _write_installed_arx_distribution(
        site,
        "arx-math-plan-fixture",
        "library",
        {
            "__init__.x": document
            + f"import {kernel} as forwarded from stdlib.math\n"
        },
    )
    assert all(
        path.suffix in {".x", ".toml"}
        for path in package.rglob("*")
        if path.is_file()
    )
    app = tmp_path / "app"
    app.mkdir()
    (app / ".arxproject.toml").write_text(
        '[project]\nname="consumer"\nversion="0"\n'
        'dependencies=["arx-math-plan-fixture"]\n',
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(site))
    monkeypatch.chdir(app)
    source = document + (
        "import forwarded as compute from library\n"
        f"import {kernel} as direct from stdlib.math\n"
        "type Number = f64\n"
        "fn scalar(value: Number) -> Number:\n"
        "  return compute(value=value)\n"
        "fn optional(value: Number) -> nullable[f64]:\n"
        "  return compute<nullable[f64]>(value)\n"
        "fn column(value: series[nullable[f64]]) "
        "-> series[nullable[f64]]:\n"
        "  return compute(value)\n"
        "fn direct_value(value: Number) -> Number:\n"
        "  return direct(value)\n"
    )
    path = app / "main.x"
    path.write_text(source, encoding="utf-8")
    ArxIO.string_to_buffer(source)
    module = Parser().parse(Lexer().lex(), "main")
    root = ParsedModule(
        "main", main_module.inject_ambient_builtin_imports(module)
    )
    resolver = main_module.FileImportResolver((str(path),))
    for _ in range(2):
        analyze_modules(root, resolver)
        plans = []
        for function in module.nodes:
            if not isinstance(function, irx_astx.FunctionDef):
                continue
            result = function.body.nodes[0]
            assert isinstance(result, irx_astx.FunctionReturn)
            info = cast(SemanticInfo, result.value.semantic)
            plan = info.facts.get(CALL_PLAN)
            assert isinstance(plan, ComputePlan)
            assert plan.operation.kernel == kernel
            assert plan.function.module_key == "stdlib.math"
            plans.append(plan)
        assert [plan.shape for plan in plans] == [
            "scalar",
            "nullable_scalar",
            "series",
            "scalar",
        ]
        assert isinstance(plans[2].result_type, irx_astx.SeriesType)
        assert plans[2].result_type.nullable
        assert isinstance(plans[1].conversion.source_type, irx_astx.Float64)
        assert isinstance(
            plans[1].conversion.target_type, irx_astx.NullableType
        )
        assert plans[0].function.prototype is plans[-1].function.prototype

    compiler = Compiler()
    checked = compiler.check(compiler.parse_file(path))
    artifact = compiler.compile(checked, kind=ArtifactKind.LLVM_IR)
    assert artifact.llvm_ir is not None
    llvm.parse_assembly(artifact.llvm_ir).verify()
    assert 'call i32 @"irx_arrow_compute"' in artifact.llvm_ir
    assert 'call double @"sqrt"' not in artifact.llvm_ir

    invalid = source.replace("value=value)", "value=value, options=1)")
    ArxIO.string_to_buffer(invalid)
    module = Parser().parse(Lexer().lex(), "main")
    with pytest.raises(
        SemanticError, match="unknown argument 'options'"
    ) as err:
        analyze_modules(
            ParsedModule(
                "main", main_module.inject_ambient_builtin_imports(module)
            ),
            resolver,
        )
    assert len(err.value.diagnostics.diagnostics) == 1


def test_bundled_stdlib_package_data_is_present() -> None:
    """
    title: Bundled stdlib sources are present on disk and included
      in packaging.
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
      tmp_path: Temporary directory for this test.
      monkeypatch: Fixture for temporarily replacing dependencies and settings.
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
    title: Programs can compile against the bundled stdlib without local
      copies.
    parameters:
      tmp_path: Temporary directory for this test.
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
      tmp_path: Temporary directory for this test.
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
    title: Reject types outside the shared signed bound before LLVM
      lowering.
    summary: Cover every helper, rejected type, and inferred/explicit
      call form without repeating the shared SignedInteger bound's
      Cartesian product.
    parameters:
      helper: Helper.
      arity: Number of explicit operands.
      type_: Type expression to process.
      value: Value to process.
      explicit: Whether to use explicit.
    """
    specialization = f"<{type_}>" if explicit else ""
    arguments = ", ".join(["value"] * arity)
    ArxIO.string_to_buffer(
        "```\ntitle: Unsupported math specialization\n```\n"
        "import math from stdlib\n"
        "fn main() -> i32:\n"
        f"  value: {type_} = {value}\n"
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
      call: Call being processed.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Mixed-width math inference\n```\n"
        "import math from stdlib\n"
        "fn main() -> i32:\n"
        "  small: i8 = cast(1, i8)\n"
        "  wide: i64 = cast(2, i64)\n"
        f"  math.{call}\n"
        "  return 0\n"
    )
    module = Parser().parse(Lexer().lex(), "mixed_math")
    root = ParsedModule("mixed_math", module)
    with pytest.raises(SemanticError, match="Conflicting inferences"):
        ArxBuilder().translate_modules(
            root, main_module.FileImportResolver(())
        )
