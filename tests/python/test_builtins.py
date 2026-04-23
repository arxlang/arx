"""
title: Bundled builtin-module loading and resolution tests.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from arx import builtins
from arx import main as main_module
from irx import astx as irx_astx
from irx.diagnostics import SemanticError

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


def test_bundled_builtin_package_data_is_present() -> None:
    """
    title: Bundled builtin sources are present in package resources.
    """
    assert builtins.list_builtin_modules() == ("generators",)
    assert builtins.resolve_builtin_resource("generators").name == (
        "generators.x"
    )
    assert (
        "fn range(start: i32, stop: i32, step: i32) -> list[i32]:"
        in builtins.get_builtin_source("generators")
    )

    root_asset = builtins.load_builtin_module("builtins")
    child_asset = builtins.load_builtin_module("builtins.generators")
    assert root_asset.origin == "arx:builtins/__init__.x"
    assert root_asset.is_package is True
    assert child_asset.origin == "arx:builtins/generators.x"
    assert child_asset.is_package is False

    pyproject = tomllib.loads(Path("pyproject.toml").read_text("utf-8"))
    includes = pyproject["tool"]["poetry"]["include"]
    assert "src/arx/builtins/**/*.x" in includes


def test_file_import_resolver_loads_builtins_from_packaged_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Internal builtin resolution loads packaged compiler resources.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "main.x"
    source.write_text(
        "fn main() -> i32:\n  return 0\n",
        encoding="utf-8",
    )

    resolver = main_module.FileImportResolver((str(source),))
    root_import = irx_astx.ImportFromStmt(
        [irx_astx.AliasExpr("generators")],
        module="builtins",
        level=0,
    )
    child_import = irx_astx.ImportFromStmt(
        [irx_astx.AliasExpr("range")],
        module="builtins.generators",
        level=0,
    )

    parent = resolver("main", root_import, "builtins")
    child = resolver("main", child_import, "builtins.generators")

    assert parent.key == "builtins"
    assert parent.origin == "arx:builtins/__init__.x"

    assert child.key == "builtins.generators"
    assert child.origin == "arx:builtins/generators.x"


def test_file_import_resolver_injects_ambient_range_for_user_modules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Imported project modules receive the ambient range builtin.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "main.x"
    source.write_text(
        dedent(
            """
            import value from helper

            fn main() -> i32:
              return value()
            """
        ).lstrip(),
        encoding="utf-8",
    )
    helper = tmp_path / "helper.x"
    helper.write_text(
        dedent(
            """
            fn value() -> i32:
              var values: list[i32] = range(0, 4)
              return 2
            """
        ).lstrip(),
        encoding="utf-8",
    )

    resolver = main_module.FileImportResolver((str(source),))
    import_node = irx_astx.ImportFromStmt(
        [irx_astx.AliasExpr("value")],
        module="helper",
        level=0,
    )

    parsed = resolver("main", import_node, "helper")

    assert parsed.key == "helper"
    assert isinstance(parsed.ast.nodes[0], irx_astx.ImportFromStmt)
    assert parsed.ast.nodes[0].module == "builtins.generators"
    assert [alias.name for alias in parsed.ast.nodes[0].names] == ["range"]


def test_ambient_builtin_imports_expose_range_by_default() -> None:
    """
    title: Ambient builtin imports expose range outside its source module.
    """
    implicit_imports = builtins.get_ambient_builtin_imports("main")
    assert len(implicit_imports) == 1
    assert implicit_imports[0].module == "builtins.generators"
    assert [alias.name for alias in implicit_imports[0].names] == ["range"]

    source_module_imports = builtins.get_ambient_builtin_imports(
        "builtins.generators"
    )
    assert source_module_imports == ()


def test_arxmain_compiles_program_using_ambient_range_and_stdlib(
    tmp_path: Path,
) -> None:
    """
    title: Ambient builtins and stdlib remain distinct during compilation.
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
              return math.square(range(0, 4)[2])
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


def test_arxmain_compiles_imported_module_using_ambient_range(
    tmp_path: Path,
) -> None:
    """
    title: Imported project modules can call ambient range without imports.
    parameters:
      tmp_path:
        type: Path
    """
    helper = tmp_path / "helper.x"
    helper.write_text(
        dedent(
            """
            fn value() -> i32:
              var values: list[i32] = range(0, 4)
              return 2
            """
        ).lstrip(),
        encoding="utf-8",
    )
    source = tmp_path / "main.x"
    source.write_text(
        dedent(
            """
            import value from helper

            fn main() -> i32:
              return value()
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


def test_ambient_builtin_injection_rejects_local_range_definition(
    tmp_path: Path,
) -> None:
    """
    title: Ambient range names are reserved against local top-level rebinding.
    parameters:
      tmp_path:
        type: Path
    """
    source = tmp_path / "main.x"
    source.write_text(
        dedent(
            """
            fn range(start: i32, stop: i32) -> i32:
              return stop

            fn main() -> i32:
              return range(0, 4)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    app = main_module.ArxMain(
        input_files=[str(source)],
        output_file=str(tmp_path / "main.o"),
        is_lib=True,
    )

    with pytest.raises(
        ValueError,
        match="ambient builtin name 'range' is reserved",
    ):
        app._get_codegen_astx()


def test_ambient_builtin_injection_rejects_imported_range_binding(
    tmp_path: Path,
) -> None:
    """
    title: Ambient range names are reserved against imported top-level names.
    parameters:
      tmp_path:
        type: Path
    """
    helper = tmp_path / "helper.x"
    helper.write_text(
        dedent(
            """
            fn range(start: i32, stop: i32) -> i32:
              return stop
            """
        ).lstrip(),
        encoding="utf-8",
    )
    source = tmp_path / "main.x"
    source.write_text(
        dedent(
            """
            import range from helper

            fn main() -> i32:
              return 0
            """
        ).lstrip(),
        encoding="utf-8",
    )

    app = main_module.ArxMain(
        input_files=[str(source)],
        output_file=str(tmp_path / "main.o"),
        is_lib=True,
    )

    with pytest.raises(
        ValueError,
        match="ambient builtin name 'range' is reserved",
    ):
        app._get_codegen_astx()


def test_arxmain_rejects_local_builtin_shadowing(tmp_path: Path) -> None:
    """
    title: Local user modules cannot shadow the reserved builtin namespace.
    parameters:
      tmp_path:
        type: Path
    """
    local_builtins = tmp_path / "builtins"
    local_builtins.mkdir()
    (local_builtins / "__init__.x").write_text(
        dedent(
            """
            ```
            title: Local shadow package
            summary: Should never override compiler bundled builtins.
            ```
            """
        ).lstrip(),
        encoding="utf-8",
    )

    source = tmp_path / "main.x"
    source.write_text(
        dedent(
            """
            fn main() -> i32:
              print(range(0, 4)[0])
              return 0
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
        (SemanticError, ValueError),
        match="reserved builtin namespace 'builtins' cannot be shadowed",
    ):
        app.compile()
