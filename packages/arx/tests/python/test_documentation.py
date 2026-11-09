"""
title: Execute complete guide programs without maintaining copied fixtures.
"""

import re
import shutil
import subprocess

from pathlib import Path

import pyarrow as pa
import pytest

from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.main import FileImportResolver, inject_ambient_builtin_imports
from arx.parser import Parser
from irx.analysis.module_interfaces import ParsedModule
from llvmlite import binding as llvm
from public import private
from pyarrow import csv, parquet

ROOT = Path(__file__).resolve().parents[4]
HAS_NATIVE = (
    shutil.which("clang") is not None and shutil.which("c++") is not None
)


@private
def documented_program(page: str, title: str) -> str:
    """
    title: Read one complete quadruple-fenced program from its guide.
    parameters:
      page:
        type: str
      title:
        type: str
    returns:
      type: str
    """
    document = (ROOT / "docs" / page).read_text(encoding="utf-8")
    programs: list[str] = re.findall(
        r"^````arx\n(.*?)^````$", document, re.MULTILINE | re.DOTALL
    )
    matches = [
        source
        for source in programs
        if source.startswith(f"```\ntitle: {title}\n")
    ]
    assert len(matches) == 1, (page, title)
    return matches[0]


@pytest.mark.skipif(not HAS_NATIVE, reason="native compilers required")
@pytest.mark.parametrize(
    "page,title,stdout",
    [
        ("arx/getting-started.md", "Hello module", "42"),
        ("arx/getting-started.md", "Arrow-backed collections", ""),
        ("arx/functions.md", "Template function example", "3"),
        ("arx/control-flow.md", "Skip values and stop early", ""),
        ("arx/file-io.md", "Native text file example", "hello"),
        ("arx/collections.md", "Nullable column expressions", ""),
        ("arx/csv.md", "Copy a CSV file", ""),
        ("arx/parquet.md", "Filter and copy Parquet rows", ""),
        ("apache-arrow.md", "Write a RecordBatch", ""),
    ],
)
def test_documented_program(
    tmp_path: Path, page: str, title: str, stdout: str
) -> None:
    """
    title: Verify guide semantics, LLVM, linking, and execution.
    parameters:
      tmp_path:
        type: Path
      page:
        type: str
      title:
        type: str
      stdout:
        type: str
    """
    source = documented_program(page, title)
    ArxIO.string_to_buffer(source)
    module = Parser().parse(Lexer().lex(), "guide")
    root = ParsedModule("guide", inject_ambient_builtin_imports(module))
    resolver = FileImportResolver(())
    builder = ArxBuilder()
    text = builder.translate_modules(root, resolver)
    llvm.parse_assembly(text).verify()
    binary = tmp_path / "guide"
    builder._build_from_ir_result(text, str(binary), True, "auto")

    # All examples run in isolation, including their truncating file writes.
    if page == "arx/csv.md":
        (tmp_path / "input.csv").write_text(
            "id,name\n1,one\n2,two\n", encoding="utf-8"
        )
    if page == "arx/parquet.md":
        parquet.write_table(  # type: ignore[no-untyped-call]
            pa.table({"id": [5, 15, 20], "name": ["skip", "one", "two"]}),
            tmp_path / "events.parquet",
        )

    result = subprocess.run(
        [str(binary)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == stdout
    assert not result.stderr

    if page == "arx/file-io.md":
        assert (tmp_path / "message.txt").read_bytes() == b"hello\n"
    if page == "arx/csv.md":
        assert csv.read_csv(tmp_path / "output.csv").equals(  # type: ignore[attr-defined]
            csv.read_csv(tmp_path / "input.csv")  # type: ignore[attr-defined]
        )
    if page == "arx/parquet.md":
        assert parquet.read_table(  # type: ignore[no-untyped-call]
            tmp_path / "selected.parquet"
        ).equals(pa.table({"name": ["one", "two"]}))

    if page == "apache-arrow.md":
        with pa.ipc.open_file(tmp_path / "example.arrow") as reader:
            assert reader.read_all().equals(
                pa.table(
                    {"id": [42], "score": [1.5], "active": [True]},
                    schema=pa.schema(
                        [
                            pa.field("id", pa.int64(), nullable=False),
                            pa.field("score", pa.float64(), nullable=False),
                            pa.field("active", pa.bool_(), nullable=False),
                        ]
                    ),
                )
            )


@pytest.mark.parametrize(
    "page",
    [
        "docs/apache-arrow.md",
        "docs/arx/datatypes.md",
        "docs/index.md",
        "packages/arx/README.md",
    ],
)
def test_declaration_documentation_uses_supported_grammar(page: str) -> None:
    """
    title: Parse relevant Arx fences directly instead of grepping other syntax.
    parameters:
      page:
        type: str
    """
    document = (ROOT / page).read_text(encoding="utf-8")
    snippets = re.findall(
        r"^(`{3,4})arx\n(.*?)^\1$", document, re.MULTILINE | re.DOTALL
    )
    assert snippets, page
    for _, source in snippets:
        ArxIO.string_to_buffer(source)
        Parser().parse(Lexer().lex(), "documentation")
