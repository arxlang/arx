"""
title: Test code generation to file object.
"""

import os
import shutil
import subprocess

from pathlib import Path
from textwrap import dedent
from typing import Literal, cast

import astx
import pytest

from arx import codegen as codegen_module
from arx.codegen import ArxBuilder, ArxVisitor
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser
from irx.builder.runtime.registry import RuntimeFeatureState
from llvmlite import binding as llvm

TMP_PATH = Path("/tmp/arxtmp")
TMP_PATH.mkdir(exist_ok=True)
HAS_CLANG = shutil.which("clang") is not None

_MIN_MAIN = "fn main() -> i32:\n  return 0\n"


class DummyTargetMachine:
    """
    title: Test double for LLVM target emission.
    """

    def emit_object(self, module: object) -> bytes:
        """
        title: Return a stable object payload for tests.
        parameters:
          module:
            type: object
        returns:
          type: bytes
        """
        assert module == "parsed-module"
        return b"OBJ"


class DummyRuntimeFeatures:
    """
    title: Test double for runtime feature metadata.
    """

    def native_artifacts(self) -> tuple[str, ...]:
        """
        title: Return sentinel native artifacts.
        returns:
          type: tuple[str, Ellipsis]
        """
        return ("artifact",)

    def linker_flags(self) -> tuple[str, ...]:
        """
        title: Return sentinel linker flags.
        returns:
          type: tuple[str, Ellipsis]
        """
        return ("-lm",)


class DummyTranslator(ArxVisitor):
    """
    title: Test double for the IRx translator surface.
    summary: >-
      Supplies only the target machine and runtime-feature access used by
      ArxBuilder build-path tests.
    attributes:
      target_machine:
        type: DummyTargetMachine
      runtime_features:
        type: RuntimeFeatureState
    """

    def __init__(self) -> None:
        """
        title: Initialize the dummy translator.
        """
        self.target_machine: DummyTargetMachine = DummyTargetMachine()
        self.runtime_features: RuntimeFeatureState = cast(
            RuntimeFeatureState,
            DummyRuntimeFeatures(),
        )


def _parse_min_module(code: str = _MIN_MAIN) -> astx.Module:
    """
    title: Parse a minimal module for codegen tests.
    parameters:
      code:
        type: str
    returns:
      type: astx.Module
    """
    ArxIO.string_to_buffer(code)
    tree = Parser().parse(Lexer().lex())
    assert isinstance(tree, astx.Module)
    return tree


@pytest.mark.parametrize(
    "code",
    [
        "fn main() -> i32:\n  print(1.0 + 1.0)\n  return 0",
        "fn main() -> i32:\n  print(1.0 + 2.0 * (3.0 - 2.0))\n  return 0",
        # "fn main():\n  if (1 < 2):\n    return 3\nelse:\n    return 2\n",
    ],
)
@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for object build")
def test_object_generation(code: str) -> None:
    """
    title: Test object generation.
    parameters:
      code:
        type: str
    """
    lexer = Lexer()
    parser = Parser()
    ir = ArxBuilder()

    ArxIO.string_to_buffer(code)
    module_ast = parser.parse(lexer.lex())

    bin_path = TMP_PATH / "testtmp"
    ir.build(module_ast, str(bin_path))
    bin_path.unlink()


@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for object build")
def test_class_program_builds_and_runs(tmp_path: Path) -> None:
    """
    title: Class-heavy programs should survive full build and execution.
    parameters:
      tmp_path:
        type: Path
    """
    module_ast = _parse_min_module(
        dedent(
            """
            class BaseCounter:
              @[public, mutable]
              value: int32 = 4

            class Counter(BaseCounter):
              @[public, static, constant]
              version: int32 = 3

              @[private, mutable]
              internal: int32 = 5

              fn get(self) -> int32:
                return self.value

              fn read_internal(self) -> int32:
                return self.internal

            class CounterFactory:
              @[public, static]
              fn make() -> Counter:
                return Counter()

              @[public, static]
              fn version_value() -> int32:
                return Counter.version

            fn main() -> int32:
              var built: Counter = CounterFactory.make()
              return (built.get() + built.value) + (
                built.read_internal() + CounterFactory.version_value()
              )
            """
        ).lstrip()
    )

    bin_path = tmp_path / "classes_program"
    ArxBuilder().build(module_ast, str(bin_path))

    result = subprocess.run(
        [str(bin_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 16
    assert result.stdout == ""
    assert result.stderr == ""


def test_build_without_link_writes_object_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    title: Build should write raw object bytes when linking is disabled.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    ir = ArxBuilder()
    ir.translator = DummyTranslator()

    monkeypatch.setattr(ir, "translate", lambda node: "llvm-ir")
    monkeypatch.setattr(
        llvm,
        "parse_assembly",
        lambda ir_text: "parsed-module",
    )

    link_calls: list[tuple[object, ...]] = []
    chmod_calls: list[tuple[object, ...]] = []

    def fake_link_executable(*args: object, **kwargs: object) -> None:
        """
        title: Fail if link_executable is called unexpectedly.
        parameters:
          args:
            type: object
            variadic: positional
          kwargs:
            type: object
            variadic: keyword
        """
        link_calls.append((*args, kwargs))

    monkeypatch.setattr(
        codegen_module, "link_executable", fake_link_executable
    )
    monkeypatch.setattr(
        os,
        "chmod",
        lambda *args: chmod_calls.append(args),
    )

    output_file = tmp_path / "module.o"
    ir.build(astx.Module(), str(output_file), link=False)

    assert output_file.read_bytes() == b"OBJ"
    assert link_calls == []
    assert chmod_calls == []


def test_build_rejects_unknown_link_mode(tmp_path: Path) -> None:
    """
    title: Unknown link_mode raises before invoking the linker.
    parameters:
      tmp_path:
        type: Path
    """
    module_ast = _parse_min_module()

    with pytest.raises(ValueError, match="Invalid link mode"):
        ArxBuilder().build(
            module_ast,
            str(tmp_path / "never"),
            link=True,
            link_mode=cast(
                Literal["auto", "pie", "no-pie"],
                "not-a-link-mode",
            ),
        )


@pytest.mark.parametrize(
    ("link_mode", "expected_flags"),
    [
        ("auto", ("-lm",)),
        ("pie", ("-lm", "-pie")),
        ("no-pie", ("-lm", "-no-pie")),
    ],
)
def test_linked_build_forwards_runtime_link_inputs(
    link_mode: str,
    expected_flags: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    title: Linked builds should forward runtime artifacts and link flags.
    parameters:
      link_mode:
        type: str
      expected_flags:
        type: tuple[str, Ellipsis]
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    ir = ArxBuilder()
    ir.translator = DummyTranslator()

    monkeypatch.setattr(ir, "translate", lambda node: "llvm-ir")
    monkeypatch.setattr(
        llvm,
        "parse_assembly",
        lambda ir_text: "parsed-module",
    )

    captured: dict[str, object] = {}
    chmod_calls: list[tuple[object, ...]] = []

    def fake_link_executable(
        primary_object: Path,
        output_file: Path,
        artifacts: tuple[str, ...],
        linker_flags: tuple[str, ...],
    ) -> None:
        """
        title: Record the linker inputs forwarded by ArxBuilder.
        parameters:
          primary_object:
            type: Path
          output_file:
            type: Path
          artifacts:
            type: tuple[str, Ellipsis]
          linker_flags:
            type: tuple[str, Ellipsis]
        """
        captured["primary_object"] = primary_object
        captured["output_file"] = output_file
        captured["artifacts"] = artifacts
        captured["linker_flags"] = linker_flags
        output_file.write_bytes(b"BIN")

    monkeypatch.setattr(
        codegen_module, "link_executable", fake_link_executable
    )
    monkeypatch.setattr(
        os,
        "chmod",
        lambda *args: chmod_calls.append(args),
    )

    output_file = tmp_path / "program"
    ir.build(
        astx.Module(),
        str(output_file),
        link=True,
        link_mode=cast(
            Literal["auto", "pie", "no-pie"],
            link_mode,
        ),
    )

    assert captured["artifacts"] == ("artifact",)
    assert captured["linker_flags"] == expected_flags
    assert isinstance(captured["primary_object"], Path)
    assert captured["primary_object"].name == "arx_module.o"
    assert captured["output_file"] == output_file
    assert output_file.read_bytes() == b"BIN"
    assert chmod_calls == [(str(output_file), 0o755)]
