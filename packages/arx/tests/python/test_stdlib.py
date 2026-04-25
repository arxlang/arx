"""
title: Bundled stdlib resolution and packaging tests.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from arx import main as main_module
from irx import astx as irx_astx

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

    pyproject = tomllib.loads(Path("pyproject.toml").read_text("utf-8"))
    includes = pyproject["tool"]["poetry"]["include"]
    assert "src/arx/stdlib/**/*.x" in includes


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
        ValueError,
        match="reserved stdlib namespace 'stdlib' cannot be shadowed",
    ):
        app.compile()
