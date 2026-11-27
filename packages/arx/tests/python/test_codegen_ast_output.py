"""
title: Test code generation AST output.
"""

import os
import shutil
import subprocess
import sys

from pathlib import Path
from textwrap import dedent, indent

import astx
import pytest

from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.main import FileImportResolver, inject_ambient_builtin_imports
from arx.parser import Parser
from irx.analysis.module_interfaces import ParsedModule
from irx.analysis.resolved_nodes import OwnershipTransferKind, SemanticInfo
from irx.analysis.types import same_type
from irx.builder.runtime.exceptions import parse_exception_output
from irx.builder.runtime.features import NativeArtifact
from irx.builder.runtime.linking import link_executable
from irx.diagnostics import DiagnosticCodes, SemanticError
from llvmlite import binding as llvm
from llvmlite import ir

from .test_file_class_native import build_audited_file_program


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("r: auto = &n\nr = 1", "cannot write through read-only borrow"),
        ("r: auto = &n\nn += 1", "cannot write 'n' while it is borrowed"),
        ("r: auto = &&n\nprint(n)", "cannot read 'n' while it is borrowed"),
        ("r: auto = &&n\n++n", "cannot read 'n' while it is borrowed"),
        ("r: auto = &n\nw: auto = &&n", "has a conflicting borrow"),
        (
            "r: auto = &n\nif true:\n  n: i32 = 2\n  r = &n",
            "must outlive borrow binding 'r'",
        ),
        (
            "r: auto = &&n\nif wide == 1:\n  r = &&other\nn = 0",
            "cannot read 'n' while it is borrowed",
        ),
        (
            "r: auto = &&n\nif wide == 1:\n  r = &&other\nprint(other)",
            "cannot read 'other' while it is borrowed",
        ),
        (
            "r: const :: auto = &&n\nr = &&other",
            "retargeting requires a mutable binding",
        ),
        ("r: auto = &&n\nr = &other", "the original borrow mode"),
        (
            "r: auto = &n + 1",
            "requires a scalar variable or named list element",
        ),
        ("r: &i64 = &n", "must have the exact type of its source"),
        ("r: auto = &n\nr = &wide", "requires the original source type"),
        ("n = &&other", "requires an existing borrow binding"),
        (
            "r: auto = &&n\nwhile other > 0:\n  r = &&other\n  continue",
            "cannot read 'other' while it is borrowed",
        ),
        (
            "r: auto = &&n\nwhile wide > 0:\n  r = &&other\n  break\nn = 0",
            "cannot read 'n' while it is borrowed",
        ),
    ],
)
def test_local_borrows_reject_invalid_access(body: str, message: str) -> None:
    """
    title: Reject conflicting or ill-typed accesses before LLVM lowering.
    parameters:
      body: Borrow operations to analyze.
      message: Expected semantic diagnostic.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n"
        "  n: i32 = 0\n"
        "  other: i32 = 1\n"
        "  wide: i64 = 1\n" + indent(body, "  ") + "\n  return 0\n"
    )
    with pytest.raises(SemanticError, match=message):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("a: auto = &values[0]\na = 1", "cannot write through read-only"),
        ("a: auto = &&values[0]\nprint(values[0])", "cannot read 'values'"),
        (
            "a: auto = &&values[0]\nprint(values[index])",
            "cannot read 'values'",
        ),
        (
            "a: auto = &values[index]\nb: auto = &&values[1]",
            "conflicting borrow",
        ),
        ("a: auto = &values[0]\nb: auto = &&values[0]", "conflicting borrow"),
        ("a: auto = &values[0]\nvalues.append(1)", "cannot write 'values'"),
        ("a: auto = &values[0]\nvalues = [1]", "cannot write 'values'"),
        (
            "a: auto = &values[0]\nb: list[i32] = values",
            "cannot write 'values'",
        ),
        ("a: auto = &values[0]\nother = values", "cannot write 'values'"),
        ("a: auto = &values[0]\nreturn values", "cannot write 'values'"),
        ("a: auto = &values[0]\ngrow(&&values)", "cannot write 'values'"),
        ("a: auto = &&values[0]\nsize(&values)", "cannot read 'values'"),
        (
            "a: auto = &values[0]\ntry:\n  a = &other[index]\n"
            "except IndexError:\n  values.append(1)",
            "cannot write 'values' while it is borrowed",
        ),
        (
            "try:\n  a: auto = &values[0]\nexcept IndexError:\n  return []\n"
            "else:\n  values.append(1)",
            "cannot write 'values' while it is borrowed",
        ),
        ("other = values\na: auto = &values[0]", "after a move"),
        (
            "other = values\na: auto = &other[0]\na = &values[0]",
            "after a move",
        ),
        ("a: auto = &values[true]", "requires an integer index"),
        ("a: &&i64 = &&values[0]", "must have the exact type"),
        ("a: auto = &&fixed[0]", "cannot exclusively borrow constant"),
        ("a: auto = &words[0]", "list of numeric or Boolean values"),
        (
            "a: auto = &[1][0]",
            "requires a scalar variable or named list element",
        ),
        (
            "a: auto = &values[:1]",
            "requires a scalar variable or named list element",
        ),
        (
            "for value in values:\n  a: auto = &&values[0]",
            "during iteration",
        ),
        (
            "a: auto = &&values[0]\nfor value in values:\n  print(value)",
            "cannot read 'values'",
        ),
    ],
)
def test_list_element_borrows_reject_invalid_access(
    body: str, message: str
) -> None:
    """
    title: Reject conflicting, invalidating and unsupported list element loans.
    parameters:
      body: Borrow operations to analyze.
      message: Expected semantic diagnostic.
    """
    ArxIO.string_to_buffer(
        "fn grow(values: &&list[i32]) -> none:\n"
        "  values.append(1)\n"
        "fn size(values: &list[i32]) -> i64:\n"
        "  return len(values)\n"
        "fn check(index: i32) -> list[i32]:\n"
        "  values: list[i32] = [1, 2]\n"
        "  other: list[i32] = [3, 4]\n"
        "  fixed: const :: list[i32] = [1]\n"
        '  words: list[str] = ["word"]\n'
        + indent(body, "  ")
        + ("" if body.endswith("return values") else "\n  return [1]")
        + "\nfn main() -> i32:\n  return 0\n"
    )
    with pytest.raises(SemanticError, match=message):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("grow(values)", "requires an explicit '&&' borrow"),
        ("grow(&values)", "requires an explicit '&&' borrow"),
        ("size(&&values)", "requires an explicit '&' borrow"),
        ("size(&[1])", "requires a named local list"),
        ("len(&values)", "borrow operands require an Arx function"),
        ("pair(&&values, &values)", "call operands overlap"),
        ("mixed(&values, size(&values))", "call operands overlap"),
        ("view(values, grow_and_count(&&values))", "call operands overlap"),
        (
            "next: list[i32] = list(values, "
            "max_items=grow_and_count(&&values))",
            "call operands overlap",
        ),
        (
            "for item in values:\n  grow(&&values)",
            "outside active iteration",
        ),
        (
            "next: list[i32] = values\nsize(&values)",
            "after a move",
        ),
    ],
)
def test_call_list_borrows_reject_invalid_operands(
    body: str, message: str
) -> None:
    """
    title: Reject invalid or overlapping call loans before LLVM lowering.
    parameters:
      body: Borrow operations to analyze.
      message: Expected semantic diagnostic.
    """
    ArxIO.string_to_buffer(
        "fn grow(values: &&list[i32]) -> none:\n"
        "  values.append(2)\n"
        "fn size(values: &list[i32]) -> i64:\n"
        "  return len(values)\n"
        "fn pair(left: &&list[i32], right: &list[i32]) -> none:\n"
        "  return none\n"
        "fn mixed(values: &list[i32], n: i64) -> none:\n"
        "  return none\n"
        "fn grow_and_count(values: &&list[i32]) -> i64:\n"
        "  grow(&&values)\n"
        "  return len(values)\n"
        "fn view(values: sequence[i32], n: i64) -> none:\n"
        "  return none\n"
        "fn main() -> i32:\n"
        "  values: list[i32] = [1]\n" + indent(body, "  ") + "\n  return 0\n"
    )
    with pytest.raises(SemanticError, match=message):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.mark.parametrize(
    ("signature", "body", "message"),
    [
        ("&list[i32]", "values.append(2)", "read-only borrow"),
        ("&&list[i32]", "values = [2]", "constant"),
        ("&list[i32]", "grow(&&values)", "cannot exclusively borrow"),
        (
            "&list[i32]",
            "alias: auto = &&values[0]",
            "cannot exclusively borrow through read-only",
        ),
        (
            "&&list[i32]",
            "for value in values:\n  grow(&&values)",
            "outside active iteration",
        ),
    ],
)
def test_borrowed_list_parameters_preserve_access(
    signature: str, body: str, message: str
) -> None:
    """
    title: Preserve borrowing permissions in the callee.
    parameters:
      signature: Borrowed parameter type syntax.
      body: Function body.
      message: Expected semantic diagnostic.
    """
    ArxIO.string_to_buffer(
        "fn grow(values: &&list[i32]) -> none:\n"
        "  values.append(1)\n"
        f"fn check(values: {signature}) -> none:\n"
        + indent(body, "  ")
        + "\nfn main() -> i32:\n  return 0\n"
    )
    with pytest.raises(SemanticError, match=message):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("edit(values[0], 2)", "requires an explicit '&&' borrow"),
        ("edit(&values[0], 2)", "requires an explicit '&&' borrow"),
        ("narrow(&&values[0])", "expects Int16 but got Int32"),
        ("pair(&&values[0], &values[0])", "call operands overlap"),
        ("pair(&&values[0], &values[index])", "call operands overlap"),
        ("edit(&&values[0], values[0])", "call operands overlap"),
        ("edit(&&values[0], edit(&&values[0], 2))", "call operands overlap"),
        ("edit(&&values[0], values.append(1))", "call operands overlap"),
        ("edit(&&values[0], grow(&&values))", "call operands overlap"),
        ("mixed(&&values, &values[0])", "call operands overlap"),
        (
            "observe(&values[0], &other[edit(&&values[0], 0)])",
            "call operands overlap",
        ),
        ("receiver(&values).edit(&&values[0])", "call operands overlap"),
        (
            "edit(&&[1][0], 2)",
            "requires a scalar variable or named list element",
        ),
        ("other = values\nedit(&&values[0], 2)", "after a move"),
        (
            "alias: auto = &values[0]\nedit(&&values[0], 2)",
            "conflicting borrow",
        ),
    ],
)
def test_call_element_borrows_reject_invalid_operands(
    body: str, message: str
) -> None:
    """
    title: Reject conflicting or incompatible loans before generating a call.
    parameters:
      body: Operation under test.
      message: Expected semantic diagnostic.
    """
    ArxIO.string_to_buffer(
        "fn edit(value: &&i32, n: i32) -> i32:\n  return n\n"
        "fn narrow(value: &&i16) -> none:\n  return none\n"
        "fn pair(first: &&i32, second: &i32) -> none:\n  return none\n"
        "fn observe(first: &i32, second: &i32) -> none:\n  return none\n"
        "fn mixed(first: &&list[i32], second: &i32) -> none:\n  return none\n"
        "fn grow(values: &&list[i32]) -> i32:\n"
        "  values.append(2)\n  return 2\n"
        "class Editor:\n"
        "  fn edit(self, value: &&i32) -> none:\n    return none\n"
        "fn receiver(values: &list[i32]) -> Editor:\n  return Editor()\n"
        "fn check(index: i32) -> none:\n"
        "  values: list[i32] = [1, 2]\n"
        "  other: list[i32] = [3]\n" + indent(body, "  ") + "\n"
    )
    with pytest.raises(SemanticError, match=message):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.mark.parametrize(
    ("signature", "body", "message"),
    [
        ("&i32", "value += 1", "cannot write through read-only borrow"),
        (
            "&i32",
            "take(&&value)",
            "cannot exclusively borrow through read-only",
        ),
        (
            "&&i32",
            "value = &&other",
            "retargeting requires an existing borrow binding",
        ),
        ("&str", "return none", "borrowed parameters require a fixed numeric"),
    ],
)
def test_scalar_borrow_parameter_permissions(
    signature: str, body: str, message: str
) -> None:
    """
    title: Enforce fixed scalar borrow parameters and access modes.
    parameters:
      signature: Parameter type and access mode.
      body: Operation under test.
      message: Expected semantic diagnostic.
    """
    ArxIO.string_to_buffer(
        "fn take(value: &&i32) -> none:\n  return none\n"
        f"fn check(value: {signature}) -> none:\n"
        "  other: i32 = 0\n" + indent(body, "  ") + "\n"
    )
    with pytest.raises(SemanticError, match=message):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("editor.grow(values)", "requires an explicit '&&' borrow"),
        ("editor.grow(&values)", "requires an explicit '&&' borrow"),
        ("editor.inspect(&&values)", "requires an explicit '&' borrow"),
        ("editor.mix(&values, &&values)", "call operands overlap"),
        ("get_editor(&values).grow(&&values)", "call operands overlap"),
        ("Editor(values, 0)", "constructor argument 'values' requires"),
        ("Editor(&&values, 0)", "constructor argument 'values' requires"),
        ("Editor(&values, editor.grow(&&values))", "call operands overlap"),
    ],
)
def test_method_list_borrows_reject_invalid_operands(
    body: str, message: str
) -> None:
    """
    title: Reject method and constructor access mismatches and overlap.
    parameters:
      body: Invalid borrow operation.
      message: Expected semantic diagnostic.
    """
    ArxIO.string_to_buffer(
        "class Editor:\n"
        "  fn __init__(self, values: &list[i32], size: i64) -> none:\n"
        "    return none\n"
        "  fn grow(self, values: &&list[i32]) -> i64:\n"
        "    values.append(2)\n"
        "    return len(values)\n"
        "  fn inspect(self, values: &list[i32]) -> i64:\n"
        "    return len(values)\n"
        "  fn mix(self, first: &list[i32], second: &&list[i32]) -> none:\n"
        "    return none\n"
        "fn get_editor(values: &list[i32]) -> Editor:\n"
        "  return Editor(&values, 0)\n"
        "fn main() -> i32:\n"
        "  values: list[i32] = [1]\n"
        "  editor: Editor = Editor(&values, 0)\n"
        f"  {body}\n"
        "  return 0\n"
    )
    with pytest.raises(SemanticError, match=message):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.mark.skipif(shutil.which("clang") is None, reason="requires clang")
def test_text_query_cache_handles_foreign_writes(tmp_path: Path) -> None:
    """
    title: Preserve snapshots and invalidate caches before native calls.
    parameters:
      tmp_path: Temporary directory for the linked test.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Foreign text mutation\n```\n"
        "extern erase_text(value: str) -> none\n"
        "fn erase_and_index(value: str) -> i64:\n"
        "  erase_text(value)\n"
        "  return 1\n"
        "fn main() -> i32:\n"
        '  text: str = "e" + "value"\n'
        "  assert len(text) == 6\n"
        '  assert text[5] == "e"\n'
        '  assert text[erase_and_index(text)] == "v"\n'
        "  assert len(text) == 0\n"
        "  return 0\n"
    )
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    for symbol in ("cached_len", "cached_index", "index"):
        assert f'call i32 @"irx_text_{symbol}"' in text
    module = llvm.parse_assembly(text)
    module.verify()
    object_path = tmp_path / "text.o"
    object_path.write_bytes(
        builder.translator.target_machine.emit_object(module)
    )
    helper = tmp_path / "erase.c"
    helper.write_text("void erase_text(char *s) { s[0] = 0; }\n")
    features = builder.translator.runtime_features
    binary = tmp_path / "text"
    link_executable(
        object_path,
        binary,
        (*features.native_artifacts(), NativeArtifact("c_source", helper)),
        features.linker_flags(),
    )
    subprocess.run([str(binary)], check=True, timeout=10)


@pytest.fixture(scope="module")
def compute_program(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    title: Verify and link cross-module math with boundary auditing.
    parameters:
      tmp_path_factory: Factory for shared temporary test directories.
    returns: 'Result of this operation: verify and link cross-module math
      with boundary auditing.'
    """
    if sys.platform != "linux":
        pytest.skip("compute boundary auditing requires ELF --wrap")
    work = tmp_path_factory.mktemp("compute")
    (work / "compute_bridge.x").write_text(
        "```\ntitle: Typed source-only compute bridge\n```\n"
        "import (sqrt as root, exp) from stdlib.math\n"
        "fn scalar(value: f64) -> f64:\n"
        "  return root(value)\n"
        "fn optional(value: nullable[f64]) -> nullable[f64]:\n"
        "  return root(value)\n"
        "fn series(value: series[nullable[f64]]) "
        "-> series[nullable[f64]]:\n"
        "  return root(exp(value))\n"
    )
    source = work / "main.x"
    source.write_text(
        "```\ntitle: Native compute transport and cleanup\n```\n"
        "import (scalar, optional, series) from compute_bridge\n"
        "import (sqrt as root, exp) from stdlib.math\n"
        "calls: i32 = 0\n"
        "fn value() -> f64:\n"
        "  calls += 1\n"
        "  return 4.0\n"
        "fn sqrt(value: f64) -> f64:\n"
        "  return -99.0\n"
        "fn escaped() -> series[nullable[f64]]:\n"
        "  frame: dataframe[x:f64 | none] = "
        "dataframe({x:[0.0, none, 4.0]})\n"
        "  return series(frame.x)\n"
        "fn main() -> i32:\n"
        "  assert scalar(value()) == 2.0\n"
        "  assert calls == 1\n"
        "  lifted: nullable[f64] = root<nullable[f64]>(value=value())\n"
        "  assert calls == 2\n"
        "  assert not is_null(lifted)\n"
        "  assert fill_null(lifted, 0.0) == 2.0\n"
        "  assert sqrt(4.0) == -99.0\n"
        "  assert root(root(16.0)) == 2.0\n"
        "  missing: nullable[f64] = none\n"
        "  assert is_null(optional(missing))\n"
        "  assert fill_null(optional(9.0), 0.0) == 3.0\n"
        "  wide: nullable[i64] = cast(9007199254740993, i64)\n"
        "  assert fill_null(wide, cast(0, i64)) == "
        "cast(9007199254740993, i64)\n"
        "  unsigned: nullable[u64] = cast(18446744073709551615, u64)\n"
        "  assert fill_null(unsigned, cast(0, u64)) == "
        "cast(18446744073709551615, u64)\n"
        "  flag: nullable[bool] = false\n"
        "  assert fill_null(flag, true) == false\n"
        "  negative: f64 = root(-1.0)\n"
        "  assert not (negative == negative)\n"
        "  single: dataframe[x:f64] = dataframe({x:[4.0]})\n"
        "  assert root(single.x)[0] == scalar(4.0)\n"
        "  values: series[nullable[f64]] = escaped()\n"
        "  assert fill_null(values[0], 0.0) == exp(0.0)\n"
        "  assert is_null(values[1])\n"
        "  assert fill_null(values[2], 0.0) > 7.0\n"
        "  copied: series[nullable[f64]] = root(values)\n"
        "  values[0] = 9.0\n"
        "  assert fill_null(copied[0], 0.0) == 1.0\n"
        "  root(root(copied))\n"
        "  return 0\n"
    )
    ArxIO.string_to_buffer(source.read_text())
    root = ParsedModule(
        "main", inject_ambient_builtin_imports(Parser().parse(Lexer().lex()))
    )
    builder = ArxBuilder()
    text = builder.translate_modules(root, FileImportResolver((str(source),)))
    module = llvm.parse_assembly(text)
    module.verify()
    assert "llvm.sqrt" not in text and 'call double @"sqrt"' not in text
    assert (
        "libm"
        not in builder.translator.runtime_features.active_feature_names()
    )
    for function in module.functions:
        for block in function.blocks:
            for instruction in block.instructions:
                if instruction.opcode == "load" and next(
                    iter(instruction.operands)
                ).name.startswith(
                    ("compute.bits", "compute.valid", "compute.column")
                ):
                    assert block.name.startswith("compute.success")
    primary = work / "main.o"
    primary.write_bytes(builder.translator.target_machine.emit_object(module))
    audit = work / "audit.c"
    audit.write_text(r"""#include "irx_arrow_compute.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void* owners[32];
static int references[32], series_calls;
static int find(void* value) {
  for (int i = 0; i < 32; ++i)
    if (references[i] && owners[i] == value) return i;
  return -1;
}
static int mode(const char* name) {
  const char* value = getenv("ARX_TEST_COMPUTE");
  return value && !strcmp(value, name);
}
uint32_t __real_irx_arrow_compute_abi_version(void);
uint32_t __wrap_irx_arrow_compute_abi_version(void) {
  // Fail only after the inner Series result exists, exercising rollback.
  return mode("abi") && series_calls == 2 ? 99 :
      __real_irx_arrow_compute_abi_version();
}
int32_t __real_irx_arrow_compute(uint32_t, int32_t, int32_t, int32_t,
    int32_t, int32_t, int32_t, const irx_arrow_chunked_array_handle*, uint64_t,
    int32_t, int32_t, const irx_arrow_chunked_array_handle*, uint64_t, int32_t,
    int32_t, irx_arrow_chunked_array_handle**, uint64_t*, int32_t*);
int32_t __wrap_irx_arrow_compute(uint32_t abi, int32_t op, int32_t arity,
    int32_t options, int32_t dtype, int32_t shape, int32_t lhs_type,
    const irx_arrow_chunked_array_handle* input, uint64_t bits, int32_t valid,
    int32_t rhs_type, const irx_arrow_chunked_array_handle* rhs,
    uint64_t rhs_bits, int32_t rhs_valid, int32_t result_type,
    irx_arrow_chunked_array_handle** output, uint64_t* out_bits,
    int32_t* out_valid) {
  int fail = shape == IRX_COMPUTE_SERIES &&
      ++series_calls == 3 && mode("type");
  int status = __real_irx_arrow_compute(abi, op, arity, options,
      fail ? -1 : dtype, shape, lhs_type, input, bits, valid,
      rhs_type, rhs, rhs_bits, rhs_valid, result_type,
      output, out_bits, out_valid);
  if (fail) { // Prove lowering never reads/publishes outputs after failure.
    *output = (irx_arrow_chunked_array_handle*)1;
    *out_bits = 123; *out_valid = 123;
  }
  if (!status && *output) {
    for (int i = 0; i < 32; ++i) if (!references[i]) {
      owners[i] = *output; references[i] = 1; break;
    }
  }
  return status;
}
int __real_irx_arrow_chunked_array_retain(irx_arrow_chunked_array_handle*);
int __wrap_irx_arrow_chunked_array_retain(
    irx_arrow_chunked_array_handle* value) {
  int status = __real_irx_arrow_chunked_array_retain(value);
  int index = find(value);
  if (!status && index >= 0) ++references[index];
  return status;
}
void __real_irx_arrow_chunked_array_release(irx_arrow_chunked_array_handle*);
void __wrap_irx_arrow_chunked_array_release(
    irx_arrow_chunked_array_handle* value) {
  int index = find(value);
  if (index >= 0) --references[index];
  __real_irx_arrow_chunked_array_release(value);
}
__attribute__((destructor)) static void audit(void) {
  int live = 0;
  for (int i = 0; i < 32; ++i) live += references[i];
  fprintf(stderr, "COMPUTE live=%d\n", live);
}
""")
    artifacts = builder.translator.runtime_features.native_artifacts()
    native = next(
        a.path.parent for a in artifacts if a.path.stem == "irx_arrow_compute"
    )
    binary = work / "program"
    link_executable(
        primary,
        binary,
        (*artifacts, NativeArtifact("c_source", audit, (native,))),
        (
            *builder.translator.runtime_features.linker_flags(),
            *(
                "-Wl,--wrap=" + name
                for name in (
                    "irx_arrow_compute_abi_version",
                    "irx_arrow_compute",
                    "irx_arrow_chunked_array_retain",
                    "irx_arrow_chunked_array_release",
                )
            ),
        ),
    )
    return binary


@pytest.mark.parametrize(
    "mode, role", [("", None), ("abi", "RuntimeError"), ("type", "TypeError")]
)
def test_compute_transport_and_cleanup(
    compute_program: Path, mode: str, role: str | None
) -> None:
    """
    title: Shared native math preserves values and cleans owners on failure.
    parameters:
      compute_program: Compute program.
      mode: Selected processing mode.
      role: Role.
    """
    result = subprocess.run(
        [str(compute_program)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "ARX_TEST_COMPUTE": mode},
        timeout=15,
    )
    assert "COMPUTE live=0" in result.stderr, result.stderr
    if role is None:
        assert result.returncode == 0, result.stderr
        return
    assert result.returncode != 0
    report = parse_exception_output(result.stderr)
    assert report is not None, result.stderr
    assert report.type_name.endswith("::class::" + role)
    if mode == "abi":
        assert report.message == "incompatible Arrow compute ABI revision"
    else:
        assert "unsupported compute input dtype" in report.message


@pytest.fixture(scope="module")
def scalar_module_ir() -> tuple[ArxBuilder, str]:
    """
    title: Translate scalar global updates and shadows once for native checks.
    returns: 'Result of this operation: translate scalar global updates and
      shadows once for native checks.'
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Scalar module storage\n```\n"
        "zero: i32\n"
        "limit: const :: auto = 10\n"
        "ratio: f64 = -1.25\n"
        "flag: bool\n"
        "optional: nullable[i32] = none\n"
        "valid_false: nullable[bool] = false\n"
        "@<T: i32 | i64>\n"
        "fn read_counter(value: T) -> i64:\n"
        "  return counter\n"
        "fn bump() -> none:\n"
        "  counter = counter + 1\n"
        "  counter += 2\n"
        "  ++counter\n"
        "  return none\n"
        "fn shadow() -> i64:\n"
        "  counter: i64 = 100\n"
        "  counter += 1\n"
        "  return counter\n"
        "counter: i64 = 5\n"
        "fn main() -> i32:\n"
        "  assert zero == 0\n"
        "  assert limit == 10\n"
        "  assert flag == false\n"
        "  assert ratio == -1.25\n"
        "  assert is_null(optional)\n"
        "  assert not is_null(valid_false)\n"
        "  assert fill_null(valid_false, true) == false\n"
        "  optional = 7\n"
        "  assert fill_null(optional, 0) == 7\n"
        "  bump()\n"
        "  assert counter == 9\n"
        "  assert read_counter(0) == 9\n"
        "  assert shadow() == 101\n"
        "  assert counter == 9\n"
        "  zero = 3\n"
        "  print(counter)\n"
        "  return zero - 3\n"
    )
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    return builder, text


def test_scalar_module_global_storage(
    scalar_module_ir: tuple[ArxBuilder, str],
) -> None:
    """
    title: Surface module declarations become internal scalar LLVM globals.
    parameters:
      scalar_module_ir: Scalar module IR.
    """
    _, text = scalar_module_ir
    module = llvm.parse_assembly(text)
    globals_ = [
        value
        for value in module.global_variables
        if value.name.startswith("module_global_")
    ]
    assert len(globals_) == 7
    assert all(value.linkage.name == "internal" for value in globals_)
    assert sorted(str(value.global_value_type) for value in globals_) == [
        "double",
        "i1",
        "i32",
        "i32",
        "i64",
        "{ i1, i1 }",
        "{ i1, i32 }",
    ]


@pytest.mark.skipif(shutil.which("clang") is None, reason="clang required")
def test_scalar_module_global_execution(
    scalar_module_ir: tuple[ArxBuilder, str], tmp_path: Path
) -> None:
    """
    title: Global updates persist across calls while local shadows stay local.
    parameters:
      scalar_module_ir: Scalar module IR.
      tmp_path: Temporary directory for this test.
    """
    builder, text = scalar_module_ir
    executable = tmp_path / "module-scalars"
    builder._build_from_ir_result(text, str(executable), True, "auto")
    result = subprocess.run(
        [str(executable)], capture_output=True, check=False, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == b"9\n"
    assert result.stderr == b""


@pytest.mark.parametrize(
    "declaration",
    ['value: str = "literal"', "value: i64 = initial()"],
)
def test_unsupported_module_storage_fails_before_lowering(
    declaration: str,
) -> None:
    """
    title: Unused unsupported globals fail with a real declaration location.
    parameters:
      declaration: Declaration being processed.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Unsupported module storage\n```\n"
        f"{declaration}\n"
        "fn initial() -> i64:\n  return 1\n"
        "fn main() -> i32:\n  return 0\n"
    )
    with pytest.raises(SemanticError) as error:
        ArxBuilder().translate(Parser().parse(Lexer().lex()))
    diagnostics = error.value.diagnostics.diagnostics
    assert len(diagnostics) == 1
    assert diagnostics[0].code in {
        DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        DiagnosticCodes.SEMANTIC_UNSUPPORTED_NODE,
    }
    location = diagnostics[0].resolved_source()
    assert location is not None and location.line == 4


@pytest.mark.parametrize("stop", [105, 110, 120])
def test_iterated_list_replacement_fails_at_assignment(stop: int) -> None:
    """
    title: Short, equal, and longer replacements fail before list lowering.
    parameters:
      stop: Stopping position.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Iterated owner replacement\n```\n"
        "fn main() -> i32:\n"
        "  data: list[i32] = list(range(0, 10))\n"
        "  for val in data:\n"
        "    if val == 2:\n"
        f"      data = list(range(100, {stop}))\n"
        "  return 0\n"
    )
    with pytest.raises(SemanticError) as error:
        ArxBuilder().translate(Parser().parse(Lexer().lex()))
    diagnostics = error.value.diagnostics.diagnostics
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.code == DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP
    assert "cannot replace list 'data' while it is being iterated" in (
        diagnostic.message
    )
    location = diagnostic.resolved_source()
    assert location is not None
    assert (location.line, location.col) == (8, 12)


def test_compound_count_update_stores_once() -> None:
    """
    title: Count updates consume compound results without storing them twice.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Compound count update\n```\n"
        "fn main() -> i32:\n"
        "  total: i32 = 0\n"
        "  for i: i32 = 0; i < 4; i += 1:\n"
        "    total += i\n"
        "  return total\n"
    )
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    module = llvm.parse_assembly(text)
    module.verify()
    updates = [
        (function, block)
        for function in module.functions
        for block in function.blocks
        if block.name.startswith("for.count.update")
    ]
    assert len(updates) == 1
    function, update = updates[0]
    load = next(
        instruction
        for instruction in update.instructions
        if instruction.opcode == "load"
    )
    address = next(iter(load.operands))
    stores = [
        instruction
        for block in function.blocks
        for instruction in block.instructions
        if instruction.opcode == "store"
        and list(instruction.operands)[1] == address
    ]
    assert len(stores) == 2  # Initializer plus one compound update.


@pytest.mark.parametrize(
    "body, message",
    [
        ("missing += 1", "cannot resolve name"),
        ("x: bool = true\n  x += true", "numeric scalars"),
        ('x: str = "a"\n  x += "b"', "numeric scalars"),
        ("x: list[i32] = [1]\n  x += [2]", "numeric scalars"),
        (
            "x: nullable[i32] = cast(1, nullable[i32])\n  x += 1",
            "numeric scalars",
        ),
        (
            "other: i32 = 0\n  for i: i32 = 0; i < 3; other += 1:\n    0",
            "induction binding",
        ),
    ],
)
def test_compound_semantic_restrictions(body: str, message: str) -> None:
    """
    title: Invalid scalar domains and loop bindings fail in IRx, not lowering.
    parameters:
      body: Statements forming the body.
      message: Diagnostic or output message.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Invalid compound assignment\n```\n"
        f"fn main() -> i32:\n  {body}\n  return 0\n"
    )
    with pytest.raises(SemanticError, match=message):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


def test_scalar_remainder_and_word_not_translate() -> None:
    """
    title: Surface operators reach checked remainder and Boolean LLVM plans.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Scalar operators\n```\n"
        "extern getchar() -> i32\n"
        "fn main() -> i32:\n"
        "  value: i32 = getchar()\n"
        "  assert not value % 3 == 2\n"
        "  return value % 3\n"
    )
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert "srem i32" in text
    assert "xor i1" in text
    assert "ARX-RUNTIME-ARITHMETIC-001" in text


@pytest.mark.parametrize(
    "body",
    [
        "  if value < 0:\n"
        "    return -1\n"
        "  elif value == 0:\n"
        "    return 0\n"
        "  else:\n"
        "    return 1\n",
        "  result: i32 = 9\n"
        "  if value < 0:\n"
        "    return -1\n"
        "  elif value == 0:\n"
        "    result = 0\n"
        "  elif value == 1:\n"
        "    print(value)\n"
        "  return result\n",
    ],
    ids=["all-returning", "mixed-fallthrough-without-else"],
)
def test_elif_chain_translate(body: str) -> None:
    """
    title: Elif lowering preserves terminators and statement result stacks.
    parameters:
      body: Statements forming the body.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Conditional chains\n```\n"
        "fn choose(value: i32) -> i32:\n" + body + "\n"
        "fn main() -> i32:\n  return choose(0)\n"
    )
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    # Top-level definitions produce functions, not leftover branch values.
    assert all(
        isinstance(value, ir.Function)
        for value in builder.translator.result_stack
    )


def test_elif_condition_requires_boolean() -> None:
    """
    title: Elif conditions retain IRx Boolean validity rather than truthiness.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Invalid elif condition\n```\n"
        "fn main() -> i32:\n"
        "  if false:\n    return 0\n"
        "  elif 1:\n    return 1\n"
        "  return 2\n"
    )
    with pytest.raises(SemanticError, match="condition must be Boolean"):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.mark.parametrize(
    "expression,operator,operand_types",
    [
        ('"hello" < 5', "<", ("String", "Int32")),
        ('5 == "hello"', "==", ("Int32", "String")),
        ("1 < x < 10", "<", ("Boolean", "Int32")),
    ],
)
def test_invalid_comparison_reports_its_operator(
    expression: str, operator: str, operand_types: tuple[str, str]
) -> None:
    """
    title: Invalid comparisons report their operator before LLVM lowering.
    parameters:
      expression: Comparison to compile.
      operator: Invalid operator spelling.
      operand_types: Expected names of the left and right operand types.
    """
    line = f"  condition: bool = {expression}"
    ArxIO.string_to_buffer(
        "```\ntitle: Invalid comparison\n```\n"
        "fn main() -> i32:\n"
        "  x: i32 = 5\n"
        f"{line}\n"
        "  return 0\n"
    )
    with pytest.raises(SemanticError) as error:
        ArxBuilder().translate(Parser().parse(Lexer().lex()))
    (diagnostic,) = error.value.diagnostics.diagnostics
    assert diagnostic.code == DiagnosticCodes.SEMANTIC_TYPE_MISMATCH
    assert diagnostic.message == (
        f"comparison '{operator}' does not support operands of type "
        f"{operand_types[0]} and {operand_types[1]}"
    )
    location = diagnostic.resolved_source()
    assert location is not None
    assert (location.line, location.col) == (6, line.rindex(operator) + 1)


def test_class_equality_compares_identity() -> None:
    """
    title: Comparing values of the same class retains identity equality.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Class identity comparison\n```\n"
        "class Item:\n"
        "  value: i32 = 0\n\n"
        "fn compare(left: Item, right: Item) -> bool:\n"
        "  return left == right\n"
    )
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    assert 'icmp eq %"main__Item"*' in text
    llvm.parse_assembly(text).verify()


@pytest.mark.parametrize("expression", ["café[0]", "café[:1]", "42[0]"])
def test_unsupported_subscript_reports_its_source(expression: str) -> None:
    """
    title: Unsupported subscripts diagnose the bracket, including Unicode.
    parameters:
      expression: Expression to process.
    """
    line = f"  print({expression})"
    source = (
        "```\ntitle: Unsupported indexing\n```\n"
        "fn main() -> i32:\n"
        "  café: i32 = 42\n"
        f"{line}\n"
        "  return 0\n"
    )
    ArxIO.string_to_buffer(source)
    with pytest.raises(SemanticError) as error:
        ArxBuilder().translate(Parser().parse(Lexer().lex()))
    first = error.value.diagnostics.diagnostics[0]
    assert "subscript access is not supported" in first.message
    location = first.resolved_source()
    assert location is not None
    assert (location.line, location.col) == (6, line.index("[") + 1)


@pytest.fixture(scope="module")
def literal_loop_ir() -> tuple[ArxBuilder, str]:
    """
    title: Translate list loop paths once for safety regressions.
    returns: 'Result of this operation: translate list loop paths once for
      safety regressions.'
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Bounded literal loop storage\n```\n"
        "extern getchar() -> i32\n"
        "fn offset(index: i32) -> i32:\n"
        "  return [-1, 2, 3][index]\n"
        "fn main() -> i32:\n"
        "  count: i32 = getchar() * 200\n"
        "  numbers: list[i32] = list(range(0, count))\n"
        "  total: i32 = 0\n"
        "  j: i32 = 1\n"
        "  for number in numbers:\n"
        "    total = total + offset(j)\n"
        "    assert ![true, false, true][j]\n"
        "    for value in [1, 2]:\n"
        "      total = total + value\n"
        "  assert total == count * 5\n"
        "  return 0\n"
    )
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    return builder, text


def test_literal_loop_allocations_are_in_entry(
    literal_loop_ir: tuple[ArxBuilder, str],
) -> None:
    """
    title: Loop scratch slots cannot accumulate on back edges.
    parameters:
      literal_loop_ir: Literal loop IR.
    """
    _, text = literal_loop_ir
    module = llvm.parse_assembly(text)
    tested = {"irx.entry.main"}
    found: set[str] = set()
    for function in module.functions:
        if function.name not in tested:
            continue
        found.add(function.name)
        entry = next(iter(function.blocks))
        for block in function.blocks:
            for instruction in block.instructions:
                if instruction.opcode == "alloca":
                    assert block == entry, (function.name, str(instruction))
    assert found == tested
    assert "irx_list_destroy" in text
    body = str(module.get_function("main__offset"))
    assert "irx_list_at" in body
    assert "internal constant [3 x i32] [i32 -1, i32 2, i32 3]" in text
    assert "irx_list_append" not in body
    assert "irx_list_destroy" not in body


@pytest.fixture(scope="module", params=[0, 3])
def literal_loop_binary(
    literal_loop_ir: tuple[ArxBuilder, str],
    tmp_path_factory: pytest.TempPathFactory,
    request: pytest.FixtureRequest,
) -> Path:
    """
    title: Separate compilation setup from repeated constrained execution.
    parameters:
      literal_loop_ir: Literal loop IR.
      tmp_path_factory: Factory for shared temporary test directories.
      request: Fixture request providing the current test context.
    returns: 'Result of this operation: separate compilation setup
      from repeated constrained execution.'
    """
    builder, text = literal_loop_ir
    module = llvm.parse_assembly(text)
    tuning = llvm.create_pipeline_tuning_options(speed_level=request.param)
    with llvm.create_pass_builder(
        builder.translator.target_machine, tuning
    ) as passes:
        with passes.getModulePassManager() as manager:
            manager.run(module, passes)
    module.verify()
    executable = tmp_path_factory.mktemp("literal-loop") / "probe"
    builder._build_from_ir_result(str(module), str(executable), True, "auto")
    return executable


@pytest.mark.skipif(
    sys.platform != "linux" or shutil.which("clang") is None,
    reason="Linux resource limits and native compiler required",
)
def test_literal_loop_runs_with_bounded_stack(
    literal_loop_binary: Path,
) -> None:
    """
    title: Reuse each optimized binary for short and long small-stack runs.
    parameters:
      literal_loop_binary: Literal loop binary.
    """
    launcher = (
        "import os, resource, sys; "
        "resource.setrlimit(resource.RLIMIT_CORE, (0, 0)); "
        "resource.setrlimit(resource.RLIMIT_STACK, (524288, 524288)); "
        "os.execv(sys.argv[1], [sys.argv[1]])"
    )
    for count in (1, 50):
        result = subprocess.run(
            [sys.executable, "-c", launcher, str(literal_loop_binary)],
            input=bytes([count]),
            capture_output=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == result.stderr == b""


@pytest.mark.parametrize(
    "code",
    [
        dedent(
            """
            fn main() -> i32:
              print(0.0 + 1.0)
              return 0
            """
        ).lstrip(),
        dedent(
            """
            fn main() -> i32:
              print(1.0 + 2.0 * (3.0 - 2.0))
              return 0
            """
        ).lstrip(),
        dedent(
            """
            fn main() -> i32:
              print(42)
              return 0
            """
        ).lstrip(),
        dedent(
            """
            fn main() -> i32:
              print(3.5)
              return 0
            """
        ).lstrip(),
        dedent(
            """
            fn average(x: f32, y: f32) -> f32:
              return (x + y) * 0.5

            fn main() -> i32:
              print(average(10.0, 20.0))
              return 0
            """
        ).lstrip(),
        dedent(
            """
            fn fib(x: i32) -> i32:
              if x < 3:
                return 1
              else:
                return fib(x-1)+fib(x-2)

            fn main() -> i32:
              print(fib(10))
              return 0
            """
        ).lstrip(),
        dedent(
            """
            @<T: i32 | f64>
            fn add(x: T, y: T) -> T:
              return x + y

            fn main() -> i32:
              print(add(1, 2))
              print(add<f64>(1.0, 2.0))
              return 0
            """
        ).lstrip(),
        dedent(
            """
            type Number = i32 | i64

            fn identity(value: Number) -> Number:
              return value

            fn main() -> i32:
              value: i64 = identity(5)
              ok: bool = isinstance(value, Number)
              name: str = type(value)
              print(name)
              if ok:
                return cast(value, i32)
              else:
                return 1
            """
        ).lstrip(),
        dedent(
            """
            class BaseCounter:
              value: public var :: int32 = 41

              fn read_seed(self) -> protected :: int32:
                return self.value

            class Counter(BaseCounter):
              version: public static const :: int32 = 3

              internal: private var :: int32 = 5

              fn internal_total(self) -> protected :: int32:
                return self.internal + self.value

              fn get(self) -> int32:
                return self.value

              fn read_internal(self) -> int32:
                return self.internal_total()

            class CounterFactory:
              fn make() -> public static :: Counter:
                return Counter()

              fn version_value() -> public static :: int32:
                return Counter.version

            fn take_counter(counter: Counter) -> int32:
              return counter.get() + counter.value + counter.read_internal()

            fn main() -> i32:
              direct: Counter = Counter()
              built: Counter = CounterFactory.make()
              print(take_counter(direct) + built.get())
              return CounterFactory.version_value() + Counter.version
            """
        ).lstrip(),
        dedent(
            """
            fn pick(grid: tensor[i32, 2, 2]) -> i32:
              return grid[1, 0] + grid[0, 1]

            fn main() -> i32:
              grid: tensor[i32, 2, 2] = [[1, 2], [3, 4]]
              return pick(grid)
            """
        ).lstrip(),
        dedent(
            """
            fn accept(values: tensor[i32, ...]) -> i32:
              return 0

            fn main() -> i32:
              values: tensor[i32, 2] = [1, 2]
              return accept(values)
            """
        ).lstrip(),
    ],
)
def test_ast_to_output(code: str) -> None:
    """
    title: Test AST to output.
    parameters:
      code: Source code or diagnostic identifier.
    """
    lexer = Lexer()
    parser = Parser()
    ir = ArxBuilder()

    ArxIO.string_to_buffer(code)

    module_ast = parser.parse(lexer.lex())

    result = ir.translate(module_ast)
    assert result


@pytest.mark.parametrize("factory", ["open", "File"])
def test_file_operations_translate_with_checked_cleanup(factory: str) -> None:
    """
    title: The public translate path emits status guards and lexical release.
    parameters:
      factory: Factory.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: File translate regression\n```\n"
        "fn main() -> i32:\n"
        f'  output: File = {factory}("output.txt", mode="w")\n'
        '  output.write("ok")\n'
        "  output.close()\n"
        "  return 0\n"
    )
    builder = ArxBuilder()
    result = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(result).verify()
    assert "irx_class_create" in result
    assert "irx_file_open" in result
    assert "irx_file_release" in result
    assert "ARX-RUNTIME-FILE-001" in result


def test_numeric_operand_plans_translate_mixed_widths() -> None:
    """
    title: Translate analyzed scalar conversions for arithmetic and comparison.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Numeric operand plan translation\n```\n"
        "fn combine(small: i8, large: i16) -> i16:\n"
        "  ordered: bool = small < large\n"
        "  return small + large\n"
        "fn main() -> i32:\n"
        "  return combine(cast(1, i8), cast(2, i16))\n"
    )
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert "sext i8" in text
    assert "icmp slt i16" in text
    assert "llvm.sadd.with.overflow.i16" in text
    assert any(
        'call i32 @"main__combine"' in line and "i16*" in line
        for line in text.splitlines()
    )


@pytest.mark.parametrize("generic", [False, True])
def test_contextual_float_arithmetic_translates_resolved_widths(
    generic: bool,
) -> None:
    """
    title: Assignment, return and call contexts lower floating literal trees.
    parameters:
      generic: Whether the identity call infers its type from a generic bound.
    """
    identity = (
        "@<T: f64>\nfn identity(value: T) -> T:\n"
        if generic
        else "fn identity(value: f64) -> f64:\n"
    )
    ArxIO.string_to_buffer(
        "```\ntitle: Contextual floating arithmetic\n```\n"
        + identity
        + "  return value\n"
        "@<T: f32 | f64>\n"
        "fn generic(value: T) -> T:\n"
        "  return value\n"
        "fn returned() -> f64:\n"
        "  return -(1e100 + 2.0)\n"
        "class Bounds:\n"
        "  @<T: f64>\n"
        "  fn echo(value: T) -> public static :: T:\n"
        "    return value\n"
        "fn expression() -> f64:\n"
        "  value: f64 = 0.0 - 1.0\n"
        "  value = (1.0 + 2.0) * 3.0\n"
        "  return identity(-(1e100 + 2.0)) + generic<f64>(3.0 / 2.0)\n"
        "fn main() -> i32:\n"
        "  result: f64 = expression()\n"
        "  result = Bounds.echo(1e100 + 2.0)\n"
        "  return 0\n"
    )
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    module = llvm.parse_assembly(text)
    module.verify()
    operations = [
        instruction
        for function in module.functions
        for block in function.blocks
        for instruction in block.instructions
        if instruction.opcode in {"fadd", "fsub", "fmul", "fdiv", "fneg"}
    ]
    assert {operation.opcode for operation in operations} >= {
        "fadd",
        "fsub",
        "fmul",
        "fdiv",
    }
    assert all(str(operation.type) == "double" for operation in operations)


def test_numeric_union_comparison_has_a_resolved_storage_plan() -> None:
    """
    title: Numeric unions retain comparison support without a raw
      LLVM fallback.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Numeric union comparison translation\n```\n"
        "type Number = i32 | i64\n"
        "fn compare(a: Number, b: i32) -> bool:\n"
        "  return a < b\n"
        "fn main() -> i32:\n"
        "  result: bool = compare(1, 2)\n"
        "  return 0\n"
    )
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert "sext i32" in text
    assert "icmp slt i64" in text


def test_integer_helpers_translate_with_wide_range_arithmetic() -> None:
    """
    title: Range uses wide count and index arithmetic alongside checked
      helpers.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Integer helper translation\n```\n"
        "import math from stdlib\n"
        "fn main() -> i32:\n"
        "  values: list[i32] = list(range(2147483646, 2147483647, 2))\n"
        "  return math.clamp(math.abs(values[0]), 0, math.square(46340))\n"
    )
    module = Parser().parse(Lexer().lex(), "integer_helpers")
    root = ParsedModule(
        "integer_helpers", inject_ambient_builtin_imports(module)
    )
    text = ArxBuilder().translate_modules(root, FileImportResolver(()))
    llvm.parse_assembly(text).verify()
    assert "sext i32" in text
    assert "udiv i64" in text
    assert "trunc i64" in text
    assert "ARX-RUNTIME-ARITHMETIC-001" in text
    assert "clamp() lower bound must not exceed upper bound" in text


@pytest.mark.parametrize("width", [8, 16, 32, 64])
def test_math_templates_translate_concrete_widths(width: int) -> None:
    """
    title: Imported aliases lower inferred and explicit concrete template
      calls.
    parameters:
      width: Bit width or display width.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Signed math specialization translation\n```\n"
        "import math as arithmetic from stdlib\n"
        "import square as squared from stdlib.math\n"
        "fn main() -> i32:\n"
        f"  value: i{width} = cast(0 - 3, i{width})\n"
        f"  zero: i{width} = cast(0, i{width})\n"
        f"  magnitude: i{width} = arithmetic.abs(value)\n"
        "  arithmetic.min(magnitude, value)\n"
        "  arithmetic.max(magnitude, value)\n"
        "  arithmetic.clamp(magnitude, zero, magnitude)\n"
        f"  squared<int{width}>(value=value)\n"
        "  return 0\n"
    )
    module = Parser().parse(Lexer().lex(), "typed_math")
    root = ParsedModule("typed_math", module)
    text = ArxBuilder().translate_modules(root, FileImportResolver(()))
    llvm.parse_assembly(text).verify()
    assert any(
        "call i32" in line and "square" in line and f"i{width}*" in line
        for line in text.splitlines()
    )
    assert f"llvm.ssub.with.overflow.i{width}" in text
    assert f"llvm.smul.with.overflow.i{width}" in text


def test_class_lifecycle_translate_verifies() -> None:
    """
    title: Constructor binding and lifetime callbacks produce valid LLVM.
    """
    ArxIO.string_to_buffer("""```
title: Lifecycle translate regression
```
class Counter:
  value: i32 = 0
  fn __init__(self, value: i32 = 1) -> none:
    self.value = value
    return none
  fn __del__(self) -> none:
    print(self.value)
    return none
fn main() -> i32:
  first: Counter = Counter(value=7)
  alias: Counter = first
  first = Counter()
  return alias.value - 7
""")
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    for symbol in (
        "irx_class_create",
        "irx_class_retain",
        "irx_class_release",
        "irx_class_complete",
    ):
        assert symbol in text
    assert "irx.drop." in text


def test_keyword_default_holes_translate_verifies() -> None:
    """
    title: Named calls with dependent default holes produce valid LLVM.
    """
    ArxIO.string_to_buffer("""```
title: Keyword translate regression
```
fn combine(a: i32, b: i32 = a + 1, c: i32 = b + 1) -> i32:
  return a * 100 + b * 10 + c
fn main() -> i32:
  return combine(c=9, a=2) - 239
""")
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert 'call i32 @"main__combine"' in text


def test_native_package_translate_verifies(tmp_path: Path) -> None:
    """
    title: The public translate path consumes resolved native package features.
    parameters:
      tmp_path: Temporary directory for this test.
    """
    fixture = Path(__file__).parents[1] / "fixtures" / "native-package"
    root_dir = tmp_path / "native"
    shutil.copytree(fixture, root_dir)
    path = root_dir / "src" / "main.x"
    source = (
        "```\ntitle: Native translate regression\n```\n"
        "import fixture_create from native_fixture.bridge\n"
        "fn main() -> i32:\n  return cast(fixture_create(size=1), i32)\n"
    )
    path.write_text(source)
    ArxIO.string_to_buffer(source)
    module = Parser().parse(Lexer().lex(), "main")
    resolver = FileImportResolver((str(path),))
    root = resolver.prepare_module(module, "main", str(path))
    builder = ArxBuilder()
    text = builder.translate_modules(root, resolver)
    llvm.parse_assembly(text).verify()
    artifacts = builder.translator.runtime_features.native_artifacts()
    assert any(artifact.path.name == "fixture.c" for artifact in artifacts)
    assert 'declare external i64 @"fixture_create"' in text


def test_arrow_stdlib_translate_uses_resolved_native_capabilities() -> None:
    """
    title: Ordinary Arrow classes lower through registered IRx native bindings.
    """
    ArxIO.string_to_buffer(
        "import (Schema, BatchBuilder) from stdlib.arrow\n"
        "fn main() -> i32:\n"
        "  schema: Schema = Schema()\n"
        '  schema.add("id", "int64")\n'
        "  builder: BatchBuilder = BatchBuilder(schema)\n"
        "  builder.append_i64(0, 42)\n"
        "  return cast(builder.finish().nrows(), i32)\n"
    )
    module = Parser().parse(Lexer().lex(), "arrow_translate")
    builder = ArxBuilder()
    ir = builder.translate_modules(
        ParsedModule("arrow_translate", module), FileImportResolver(())
    )
    llvm.parse_assembly(ir).verify()
    assert "irx_rb_api_builder_finish" in ir
    assert "irx_rb_api_batch_destroy" in ir
    assert "record_batch" in (
        builder.translator.runtime_features.active_feature_names()
    )
    assert "parquet" not in (
        builder.translator.runtime_features.active_feature_names()
    )
    assert "irx_rb_api_parquet" not in ir


def test_nullable_dataframe_translate_uses_checked_record_batch_abi() -> None:
    """
    title: Nullable literals produce verified LLVM without a Parquet
      dependency.
    """
    ArxIO.string_to_buffer(
        "type Frame = dataframe[id:i64 | none, label:str | none]\n"
        "fn main() -> i32:\n"
        '  frame: Frame = dataframe({id: [1, none], label: ["a", none]})\n'
        "  return cast(frame.nrows(), i32)\n"
    )
    module = Parser().parse(Lexer().lex(), "nullable_translate")
    builder = ArxBuilder()
    text = builder.translate_modules(
        ParsedModule("nullable_translate", module), FileImportResolver(())
    )
    llvm.parse_assembly(text).verify()
    assert "irx_rb_api_append_i64" in text
    assert "irx_rb_api_append_null" in text
    assert "irx_rb_api_append_utf8" in text
    assert "parquet" not in (
        builder.translator.runtime_features.active_feature_names()
    )


def test_temporal_dataframe_translate_uses_semantic_epoch_values() -> None:
    """
    title: Temporal DataFrame literals lower to verified checked ABI calls.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n"
        "  frame: dataframe[day:date, clock:time] = "
        'dataframe({day: [date("1969-12-31")], clock: [time("01:02:03")]})\n'
        "  return cast(frame.nrows(), i32)\n"
    )
    module = Parser().parse(Lexer().lex(), "temporal_translate")
    text = ArxBuilder().translate_modules(
        ParsedModule("temporal_translate", module), FileImportResolver(())
    )
    llvm.parse_assembly(text).verify()
    assert "irx_rb_api_append_date" in text
    assert "irx_rb_api_append_time" in text


def test_dynamic_dataframe_cannot_silently_narrow() -> None:
    """
    title: Runtime schemas cannot satisfy static contracts without checking.
    """
    ArxIO.string_to_buffer(
        "fn narrow(frame: dataframe[...]) -> dataframe[id:i64]:\n"
        "  return frame\n"
    )
    module = Parser().parse(Lexer().lex(), "unsafe_narrow")
    with pytest.raises(SemanticError):
        ArxBuilder().translate_modules(
            ParsedModule("unsafe_narrow", module), FileImportResolver(())
        )


def test_nullable_series_translate_verifies() -> None:
    """
    title: Nullable kernels consume semantic plans and produce valid LLVM.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n"
        "  frame: dataframe[x:i32 | none] = dataframe({x:[1, none]})\n"
        "  value: nullable[i32] = frame.x[0] + frame.x[1]\n"
        "  assert is_null(value)\n"
        "  return fill_null(value, 0)\n"
    )
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert "irx_arrow_compute" in text
    assert "irx_arrow_series_index" in text
    assert "column_valid" in text


def test_print_diagnostics_keep_primary_errors_and_source_locations() -> None:
    """
    title: Report a failed argument and an independent print error once each.
    """
    invalid_argument = '  print(df["label"][1])'
    invalid_print = '  print(df["x"][0])'
    ArxIO.string_to_buffer(
        "```\ntitle: Print argument diagnostics\n```\n"
        "fn main() -> i32:\n"
        "  df: dataframe[x: i64 | none, label: str] = "
        'dataframe({x: [10, none], label: ["a", "b"]})\n'
        f"{invalid_argument}\n"
        f"{invalid_print}\n"
        "  return 0\n"
    )
    with pytest.raises(SemanticError) as error:
        ArxBuilder().translate(Parser().parse(Lexer().lex()))
    argument, output = error.value.diagnostics.diagnostics
    assert argument.code == DiagnosticCodes.SEMANTIC_TYPE_MISMATCH
    assert "Series scalar operations support numeric and bool" in (
        argument.message
    )
    location = argument.resolved_source()
    assert location is not None
    assert (location.line, location.col) == (
        6,
        invalid_argument.rindex("[") + 1,
    )
    assert output.code == DiagnosticCodes.SEMANTIC_TYPE_MISMATCH
    assert (
        output.message == "unsupported PrintExpr message type nullable[Int64]"
    )
    location = output.resolved_source()
    assert location is not None
    assert (location.line, location.col) == (
        7,
        invalid_print.index("print") + 1,
    )


@pytest.mark.parametrize(
    "body,message",
    [
        (
            "bad: nullable[str] = cast(none, nullable[str])",
            "nullable scalars",
        ),
        ("bad: i32 = frame.x[0]", "cannot assign"),
        (
            "bad: nullable[i32] = frame.x[0] + true",
            "compatible scalar types",
        ),
        ("bad: nullable[i32] = frame.x[-1.0]", "integer representable"),
        (
            "bad: nullable[i32] = ++frame.x[0]",
            "unsupported nullable/Series unary",
        ),
        ("bad: bool = is_null(1)", "is_null requires"),
        ("bad: i32 = fill_null(frame.x[0], 1.5)", "matching non-null"),
        ("if frame.x[0]:\n    return 1", "condition must be Boolean"),
        ("bad: series[i32] = frame.x", "cannot assign"),
        ("bad: series[bool] = frame.x and frame.x", "require bool"),
    ],
)
def test_nullable_semantic_errors(body: str, message: str) -> None:
    """
    title: Unsupported operations fail in semantics, not during LLVM emission.
    parameters:
      body: Statements forming the body.
      message: Diagnostic or output message.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n"
        "  frame: dataframe[x:i32 | none] = dataframe({x:[1, none]})\n"
        f"  {body}\n  return 0\n"
    )
    with pytest.raises(SemanticError, match=message):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.mark.parametrize("namespace", [False, True])
def test_table_io_translate_uses_resolved_calls(namespace: bool) -> None:
    """
    title: CSV-only imported calls and direct casts emit verified native IR.
    parameters:
      namespace: Whether to use namespace.
    """
    imports = (
        "import stdlib.csv as csv\n"
        if namespace
        else "import (read_csv, write_csv) from stdlib.csv\n"
    )
    prefix = "csv." if namespace else ""
    ArxIO.string_to_buffer(
        imports + "fn main() -> i32:\n"
        f'  source: dataframe[...] = {prefix}read_csv("in.csv")\n'
        "  frame: dataframe[id:i64] = cast(source, dataframe[id:i64])\n"
        f'  {prefix}write_csv(frame=frame, path="out.csv")\n'
        "  return 0\n"
    )
    module = Parser().parse(Lexer().lex(), "table_io")
    builder = ArxBuilder()
    text = builder.translate_modules(
        ParsedModule("table_io", module), FileImportResolver(())
    )
    llvm.parse_assembly(text).verify()
    assert "irx_rb_api_read_csv" in text
    assert "irx_rb_api_table_cast" in text
    assert "irx_rb_api_write_csv" in text
    assert (
        "parquet"
        not in builder.translator.runtime_features.active_feature_names()
    )


@pytest.mark.parametrize(
    "module_name,class_name",
    [("csv", "CSVStream"), ("parquet", "ParquetStream")],
)
@pytest.mark.parametrize("alias", [False, True])
def test_format_stream_imports_translate(
    module_name: str, class_name: str, alias: bool
) -> None:
    """
    title: Explicit stream types and import aliases retain native lifecycles.
    parameters:
      module_name: Module name to resolve.
      class_name: Name of class.
      alias: Whether to use alias.
    """
    local_name = "Stream" if alias else class_name
    imported = f"{class_name} as Stream" if alias else class_name
    ArxIO.string_to_buffer(
        f"import {imported} from stdlib.{module_name}\n"
        "fn main() -> i32:\n"
        f"  stream: {local_name} = {local_name}()\n"
        "  stream.close()\n"
        "  return 0\n"
    )
    module = Parser().parse(Lexer().lex(), "format_stream")
    builder = ArxBuilder()
    text = builder.translate_modules(
        ParsedModule("format_stream", module), FileImportResolver(())
    )
    llvm.parse_assembly(text).verify()
    for operation in ("new", "close", "destroy"):
        assert f"irx_rb_api_{module_name}_{operation}" in text
    features = builder.translator.runtime_features.active_feature_names()
    assert "record_batch" in features
    assert ("parquet" in features) == (module_name == "parquet")


def test_table_io_names_do_not_grant_capabilities() -> None:
    """
    title: Equally named user functions remain ordinary scalar functions.
    """
    ArxIO.string_to_buffer(
        "fn read_csv(path: i32) -> i32:\n  return path + 1\n"
        "fn write_parquet(frame: i32) -> i32:\n  return frame + 1\n"
        "fn main() -> i32:\n  return write_parquet(read_csv(0))\n"
    )
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert (
        "record_batch"
        not in builder.translator.runtime_features.active_feature_names()
    )
    assert (
        "parquet"
        not in builder.translator.runtime_features.active_feature_names()
    )


@pytest.fixture(scope="module")
def owned_list_ir() -> tuple[ArxBuilder, str]:
    """
    title: Reuse the compiled-language list workflow for translation tests.
    returns: 'Result of this operation: reuse the compiled-language list
      workflow for translation tests.'
    """
    source = (Path(__file__).parents[1] / "arx" / "test_lists.x").read_text()
    source += (
        "\nfn main() -> i32:\n"
        "  test_owned_lists()\n"
        "  test_partial_construction()\n"
        "  test_owned_string_elements()\n"
        "  return 0\n"
    )
    ArxIO.string_to_buffer(source)
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    return builder, text


@pytest.fixture(scope="module")
def loop_transfer_ir() -> tuple[ArxBuilder, str]:
    """
    title: Translate statement scopes and loop cleanup once for native checks.
    returns: 'Result of this operation: translate statement scopes and loop
      cleanup once for native checks.'
    """
    source = (
        Path(__file__).parents[1] / "arx" / "test_control_flow.x"
    ).read_text(encoding="utf-8")
    source += (
        "\nfn main() -> i32:\n"
        "  test_loop_transfers()\n"
        "  test_loop_transfer_finalizers()\n"
        "  test_statement_body_scopes()\n"
        "  test_scoped_owner_exits()\n"
        "  loop_transfer_owners()\n"
        "  return 0\n"
    )
    ArxIO.string_to_buffer(source)
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    return builder, text


def test_loop_transfers_translate(
    loop_transfer_ir: tuple[ArxBuilder, str],
) -> None:
    """
    title: Statement scopes and transfers use verified IR and owner cleanup.
    parameters:
      loop_transfer_ir: Loop transfer IR.
    """
    _, text = loop_transfer_ir
    assert 'call void @"irx_list_destroy"' in text
    assert "irx_file_release" in text


@pytest.mark.skipif(shutil.which("clang") is None, reason="clang required")
@pytest.mark.parametrize("optimization", [0, 3])
def test_loop_transfers_execute(
    loop_transfer_ir: tuple[ArxBuilder, str],
    tmp_path: Path,
    optimization: int,
) -> None:
    """
    title: Shadowed owners survive or release once across all body exits.
    parameters:
      loop_transfer_ir: Loop transfer IR.
      tmp_path: Temporary directory for this test.
      optimization: Optimization level.
    """
    builder, text = loop_transfer_ir
    module = llvm.parse_assembly(text)
    tuning = llvm.create_pipeline_tuning_options(speed_level=optimization)
    with llvm.create_pass_builder(
        builder.translator.target_machine, tuning
    ) as passes:
        with passes.getModulePassManager() as manager:
            manager.run(module, passes)
    module.verify()
    if sys.platform == "linux":
        executable = build_audited_file_program(builder, str(module), tmp_path)
    else:
        executable = tmp_path / "loop-transfers"
        builder._build_from_ir_result(
            str(module), str(executable), True, "auto"
        )
    result = subprocess.run(
        [str(executable)],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == b""
    if sys.platform == "linux":
        assert result.stderr == b"AUDIT live=0 opened=2 released=2\n"
    else:
        assert result.stderr == b""
    assert (tmp_path / "loop-resource.txt").read_text() == "owned"


@pytest.mark.parametrize("keyword", ["break", "continue"])
@pytest.mark.parametrize(
    "prefix", ["", "fn run() -> none:\n  ", "while false:\n  print(1)\n"]
)
def test_loop_transfers_outside_loop_fail_before_lowering(
    keyword: str, prefix: str
) -> None:
    """
    title: Invalid loop transfers retain their source location in IRx.
    parameters:
      keyword: Keyword.
      prefix: Prefix.
    """
    source = prefix + keyword
    ArxIO.string_to_buffer(source)
    tree = Parser().parse(Lexer().lex())
    with pytest.raises(SemanticError) as error:
        ArxBuilder().translate(tree)
    diagnostics = error.value.diagnostics.diagnostics
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.code == DiagnosticCodes.SEMANTIC_INVALID_CONTROL_FLOW
    location = diagnostic.resolved_source()
    assert location is not None
    assert (location.line, location.col) == (
        source.count("\n") + 1,
        3 if prefix.startswith("fn") else 1,
    )


@pytest.mark.parametrize(
    "body,match",
    [
        ("with 1:\n  print(1)", "with manager requires a class value"),
        ("with Scope() as item:\n  item = 2", "constant"),
        ("with Scope() as item:\n  print(item)\nprint(item)", "resolve name"),
    ],
)
def test_resource_scope_semantic_boundary(body: str, match: str) -> None:
    """
    title: Source scopes retain type, binding, and lexical lifetime checks.
    parameters:
      body: Statements forming the body.
      match: Match.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: Resource scope validation\n```\n"
        "class Scope:\n  ```\n  title: Simple resource\n  ```\n"
        "  fn __enter__(self) -> i32:\n    return 1\n"
        "  fn __exit__(self, success: bool) -> none:\n    return none\n"
        "fn main() -> i32:\n"
        + "\n".join("  " + line for line in body.splitlines())
        + "\n  return 0\n"
    )
    with pytest.raises(SemanticError, match=match):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


def test_resource_scope_rejects_module_level() -> None:
    """
    title: Resource scopes cannot hide unsupported owned module storage.
    """
    ArxIO.string_to_buffer(
        '```\ntitle: Module resource scope\n```\nwith open("unused"):\n'
        "  print(1)\n"
    )
    tree = Parser().parse(Lexer().lex())
    root = ParsedModule("main", inject_ambient_builtin_imports(tree))
    with pytest.raises(SemanticError, match="with scopes require a function"):
        ArxBuilder().translate_modules(root, FileImportResolver(()))


@pytest.fixture(scope="module")
def resource_scope_ir() -> tuple[ArxBuilder, str]:
    """
    title: Reuse verified resource workflows for ownership and native checks.
    returns: 'Result of this operation: reuse verified resource workflows
      for ownership and native checks.'
    """
    source = (Path(__file__).parents[1] / "arx" / "test_file.x").read_text(
        encoding="utf-8"
    )
    source += (
        "\nfn main() -> i32:\n"
        "  test_resource_scopes()\n"
        "  scoped_file_workflow()\n"
        "  return 0\n"
    )
    ArxIO.string_to_buffer(source)
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    return builder, text


def test_resource_scopes_translate(
    resource_scope_ir: tuple[ArxBuilder, str],
) -> None:
    """
    title: Resource scopes use implicit cleanup and checked open-state queries.
    parameters:
      resource_scope_ir: Resource scope IR.
    """
    _, text = resource_scope_ir
    assert "irx_exception_cleanup_enter" in text
    assert "irx_file_require_open" in text


@pytest.mark.skipif(shutil.which("clang") is None, reason="clang required")
@pytest.mark.parametrize("optimization", [0, 3])
def test_resource_scopes_execute(
    resource_scope_ir: tuple[ArxBuilder, str],
    tmp_path: Path,
    optimization: int,
) -> None:
    """
    title: Entered owners, failed returns, and loop exits release once.
    parameters:
      resource_scope_ir: Resource scope IR.
      tmp_path: Temporary directory for this test.
      optimization: Optimization level.
    """
    builder, text = resource_scope_ir
    module = llvm.parse_assembly(text)
    tuning = llvm.create_pipeline_tuning_options(speed_level=optimization)
    with llvm.create_pass_builder(
        builder.translator.target_machine, tuning
    ) as passes:
        with passes.getModulePassManager() as manager:
            manager.run(module, passes)
    module.verify()
    if sys.platform == "linux":
        executable = build_audited_file_program(builder, str(module), tmp_path)
    else:
        executable = tmp_path / "resource-scopes"
        builder._build_from_ir_result(
            str(module), str(executable), True, "auto"
        )
    result = subprocess.run(
        [str(executable)],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == b""
    assert result.stderr == (
        b"AUDIT live=0 opened=2 released=2\n"
        if sys.platform == "linux"
        else b""
    )
    assert (tmp_path / "scoped-file.txt").read_text() == "hello"


def test_owned_list_translation(owned_list_ir: tuple[ArxBuilder, str]) -> None:
    """
    title: Expression lists use owned storage and non-truncating shared length.
    parameters:
      owned_list_ir: Owned list IR.
    """
    _, text = owned_list_ir
    assert 'call i32 @"irx_list_append"' in text
    assert 'call void @"irx_list_destroy"' in text
    assert "irx_collection_length_i64" in text
    assert "irx_collection_length_i32" not in text
    assert "irx_tensor" not in text


@pytest.mark.skipif(shutil.which("clang") is None, reason="clang required")
@pytest.mark.parametrize("optimization", [0, 3])
def test_owned_lists_build_and_run(
    owned_list_ir: tuple[ArxBuilder, str], tmp_path: Path, optimization: int
) -> None:
    """
    title: Native lists retain values through failures and transfers.
    parameters:
      owned_list_ir: Owned list IR.
      tmp_path: Temporary directory for this test.
      optimization: Optimization level.
    """
    builder, text = owned_list_ir
    executable = tmp_path / "owned-lists"
    module = llvm.parse_assembly(text)
    tuning = llvm.create_pipeline_tuning_options(speed_level=optimization)
    with llvm.create_pass_builder(
        builder.translator.target_machine, tuning
    ) as passes:
        with passes.getModulePassManager() as manager:
            manager.run(module, passes)
    module.verify()
    builder._build_from_ir(str(module), str(executable))
    result = subprocess.run(
        [str(executable)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            "fn main() -> i32:\n  return cast(len([]), i32)\n",
            "annotate empty",
        ),
        (
            "fn main() -> i32:\n  return cast(len([[1], [2]]), i32)\n",
            "nested owned",
        ),
        (
            "fn main() -> i32:\n  x: i8 = [128][0]\n  return 0\n",
            "representable",
        ),
        (
            "fn main() -> i32:\n  x: i8 = [cast(1, i32)][0]\n  return 0\n",
            "type Int8",
        ),
        ("fn main() -> i32:\n  return len([1])\n", "expects Int32"),
        (
            "fn main() -> i32:\n  return cast(len(1), i32)\n",
            "requires a collection",
        ),
        (
            "fn main() -> i32:\n  return cast(len([1], [2]), i32)\n",
            "one positional",
        ),
        (
            "fn main() -> i32:\n  len: i32 = 1\n  return len([1])\n",
            "does not resolve to a function",
        ),
        (
            "fn use(x: &list[i64]) -> none:\n  return none\n"
            "fn main() -> i32:\n  x: list[i32] = [1]\n"
            "  use(&x)\n  return 0\n",
            "ListType",
        ),
        (
            "fn escape(x: &list[i32]) -> list[i32]:\n  return x\n"
            "fn main() -> i32:\n  return 0\n",
            "borrowed",
        ),
        (
            "fn main() -> i32:\n"
            "  t: tensor[i32, 2, 2] = [[1, 2], [3]]\n  return 0\n",
            "rectangular",
        ),
        (
            "fn main() -> i32:\n  t: tensor[i32, 2] = [1]\n  return 0\n",
            "shape",
        ),
    ],
)
def test_owned_list_diagnostics(source: str, message: str) -> None:
    """
    title: Invalid collection domains and ownership fail before LLVM lowering.
    parameters:
      source: Source input to process.
      message: Diagnostic or output message.
    """
    ArxIO.string_to_buffer(source)
    with pytest.raises(SemanticError, match=message):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("  dst = src\n  return len(src)\n", "after a move"),
        (
            "  if flag:\n    dst = src\n  return len(src)\n",
            "after a move",
        ),
        (
            "  while flag:\n    dst = src\n  return 0\n",
            "after a move",
        ),
        (
            '  try:\n    dst = src\n    raise ValueError("failed")\n'
            "  except ValueError:\n    return len(src)\n  return 0\n",
            "after a move",
        ),
        (
            "  for item in src:\n    dst = src\n  return 0\n",
            "while it is being iterated",
        ),
        (
            "  data: bytes = bytes([1, 2])\n"
            "  saved: bytes = bytes()\n"
            "  for item in data:\n    saved = data\n  return 0\n",
            "while it is being iterated",
        ),
    ],
)
def test_invalid_local_list_moves(body: str, message: str) -> None:
    """
    title: Report invalid moves and subsequent list reads during analysis.
    parameters:
      body: Source lines that exercise list ownership.
      message: Expected ownership diagnostic.
    """
    ArxIO.string_to_buffer(
        "fn consume(flag: bool) -> i64:\n"
        "  src: list[i32] = [1]\n"
        "  dst: list[i32] = [2]\n" + body
    )
    with pytest.raises(SemanticError, match=message) as failure:
        ArxBuilder().translate(Parser().parse(Lexer().lex()))
    assert any(
        diagnostic.code == DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP
        for diagnostic in failure.value.diagnostics.diagnostics
    )


@pytest.mark.parametrize(
    "source",
    [
        (
            "class Consumer:\n"
            "  fn consume(self) -> i64:\n"
            "    src: list[i32] = [1]\n"
            "    dst: list[i32] = src\n"
            "    return len(src)\n"
        ),
        (
            "@<T: i32>\n"
            "fn consume(value: T) -> i64:\n"
            "  src: list[T] = [value]\n"
            "  dst: list[T] = src\n"
            "  return len(src)\n"
            "fn main() -> i32:\n"
            "  return cast(consume<i32>(1), i32)\n"
        ),
    ],
    ids=["method", "template-specialization"],
)
def test_local_list_moves_in_methods_and_templates(source: str) -> None:
    """
    title: Validate list moves in method and concrete template bodies.
    parameters:
      source: Callable definition that reads a moved source.
    """
    ArxIO.string_to_buffer(source)
    with pytest.raises(
        SemanticError, match="cannot use list 'src' after a move"
    ):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.mark.parametrize("name", ["len", "int", "ord"])
def test_text_builtins_can_be_shadowed_by_a_function(name: str) -> None:
    """
    title: Builtin spelling respects ordinary name resolution.
    parameters:
      name: Name identifying the declaration or operation.
    """
    ArxIO.string_to_buffer(
        f"fn {name}(value: i32) -> i32:\n  return value\n"
        f"fn main() -> i32:\n  return {name}(0)\n"
    )
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert "irx_collection_length" not in text
    assert "irx_text_" not in text


@pytest.mark.parametrize("name", ["len", "int", "ord"])
def test_local_text_builtin_shadow_is_not_callable(name: str) -> None:
    """
    title: Local values cannot fall through to intrinsic text names.
    parameters:
      name: Name identifying the declaration or operation.
    """
    ArxIO.string_to_buffer(
        f'fn main() -> i32:\n  {name}: i32 = 0\n  {name}("1")\n  return 0\n'
    )
    with pytest.raises(SemanticError, match="does not resolve to a function"):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.fixture(scope="module")
def text_operations_ir() -> tuple[ArxBuilder, str]:
    """
    title: Translate the Unicode workflow once for native optimization checks.
    returns: 'Result of this operation: translate the Unicode workflow once
      for native optimization checks.'
    """
    source = (Path(__file__).parents[1] / "arx" / "test_text.x").read_text()
    source += (
        "\nfn main() -> i32:\n"
        "  test_text_parsing()\n"
        "  test_text_argument_order()\n"
        "  test_text_queries_after_reassignment()\n"
        "  test_resource_reassignment()\n"
        "  test_text_failures()\n"
        '  words: list[str] = words_from_file("input.txt")\n'
        '  assert words[0] == "L68"\n'
        '  assert words[1] == "R-12"\n'
        "  return 0\n"
    )
    ArxIO.string_to_buffer(source)
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    return builder, text


def test_text_operations_translation(
    text_operations_ir: tuple[ArxBuilder, str],
) -> None:
    """
    title: Text lowering uses registered status/output APIs and valid LLVM.
    parameters:
      text_operations_ir: Text operations IR.
    """
    builder, text = text_operations_ir
    for operation in ("len", "index", "slice", "split", "strip", "int", "ord"):
        assert f'call i32 @"irx_text_{operation}"' in text
    assert {"text", "list", "file"} <= set(
        builder.translator.runtime_features.active_feature_names()
    )
    assert "ARX-RUNTIME-TEXT-001" in text
    failure_blocks = [
        block
        for function in llvm.parse_assembly(text).functions
        for block in function.blocks
        if block.name.startswith("text.failure")
    ]
    assert failure_blocks
    assert all(
        instruction.opcode != "load"
        for block in failure_blocks
        for instruction in block.instructions
    )


@pytest.mark.skipif(shutil.which("clang") is None, reason="clang required")
@pytest.mark.parametrize("optimization", [0, 3])
def test_text_operations_build_and_run(
    text_operations_ir: tuple[ArxBuilder, str],
    tmp_path: Path,
    optimization: int,
) -> None:
    """
    title: Native text survives source release, mutation and checked failures.
    parameters:
      text_operations_ir: Text operations IR.
      tmp_path: Temporary directory for this test.
      optimization: Optimization level.
    """
    builder, text = text_operations_ir
    executable = tmp_path / "text-operations"
    module = llvm.parse_assembly(text)
    tuning = llvm.create_pipeline_tuning_options(speed_level=optimization)
    with llvm.create_pass_builder(
        builder.translator.target_machine, tuning
    ) as passes:
        with passes.getModulePassManager() as manager:
            manager.run(module, passes)
    module.verify()
    if sys.platform == "linux":
        executable = build_audited_file_program(builder, str(module), tmp_path)
    else:
        builder._build_from_ir(str(module), str(executable))
    (tmp_path / "input.txt").write_text(" L68\nR-12\n", encoding="utf-8")
    result = subprocess.run(
        [str(executable)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == (
        "AUDIT live=0 opened=1 released=1\n" if sys.platform == "linux" else ""
    )


def test_numeric_sequence_example(tmp_path: Path) -> None:
    """
    title: One generic consumer executes across all surface source families.
    parameters:
      tmp_path: Temporary directory for this test.
    """
    if shutil.which("clang") is None:
        pytest.skip("native sequence integration requires clang")
    source = (
        Path(__file__).resolve().parents[4] / "examples/numeric-sequences.x"
    )
    ArxIO.string_to_buffer(source.read_text())
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert "irx_buffer_checked_offset" in text
    executable = tmp_path / "sequences"
    builder._build_from_ir(text, str(executable))
    result = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope="module")
def numeric_bounds_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    title: Compile tensor and sequence boundary failures once.
    parameters:
      tmp_path_factory: Factory for shared temporary test directories.
    returns: 'Result of this operation: compile tensor and sequence boundary
      failures once.'
    """
    if shutil.which("clang") is None:
        pytest.skip("native bounds checks require clang")
    source = """
extern getchar() -> i32
fn runtime_read(values: tensor[i64, ...], index: i32) -> i64:
  return values[index]
fn borrowed_read(values: sequence[i64], index: i32) -> i64:
  return values[index]
fn runtime_borrow(values: tensor[i64, ...]) -> i64:
  return borrowed_read(values, 0)
fn main() -> i32:
  mode: i32 = getchar()
  index: i32 = getchar() - 1
  values: tensor[i64, 2] = [7, 9]
  try:
    if mode == 0:
      return cast(values[index], i32)
    if mode == 1:
      return cast(runtime_read(values, index), i32)
    if mode == 2:
      return cast(borrowed_read([7, 9], index), i32)
    if mode == 3:
      empty: list[i64] = []
      return cast(borrowed_read(empty, 0), i32)
    if mode == 4:
      matrix: tensor[i64, 1, 2] = [[7, 9]]
      return cast(runtime_borrow(matrix), i32)
    if mode == 6:
      return [7, 9][index]
    copied: list[i64] = list(values, max_items=index)
    return cast(len(copied), i32)
  except IndexError:
    return 10
  except ValueError:
    return 11
"""
    ArxIO.string_to_buffer(source)
    module = Parser().parse(Lexer().lex(), "numeric_bounds")
    builder = ArxBuilder()
    text = builder.translate_modules(
        ParsedModule("numeric_bounds", inject_ambient_builtin_imports(module)),
        FileImportResolver(()),
    )
    llvm.parse_assembly(text).verify()
    executable = tmp_path_factory.mktemp("numeric-bounds") / "probe"
    builder._build_from_ir(text, str(executable))
    return executable


@pytest.mark.parametrize(
    "mode,index,expected",
    [
        (0, 0, 7),
        (0, -1, 10),
        (0, 2, 10),
        (1, 1, 9),
        (1, -1, 10),
        (1, 2, 10),
        (2, 0, 7),
        (2, -1, 10),
        (2, 2, 10),
        (3, 0, 10),
        (4, 0, 11),
        (5, -1, 11),
        (5, 1, 11),
        (6, 1, 9),
        (6, -1, 10),
        (6, 2, 10),
        (5, 2, 2),
    ],
)
def test_numeric_bounds_are_recoverable(
    numeric_bounds_binary: Path, mode: int, index: int, expected: int
) -> None:
    """
    title: Check rank, empty and signed bounds before reads or publication.
    parameters:
      numeric_bounds_binary: Numeric bounds binary.
      mode: Selected processing mode.
      index: Index selecting the item.
      expected: Expected result for this case.
    """
    result = subprocess.run(
        [str(numeric_bounds_binary)],
        input=bytes([mode, index + 1]),
        capture_output=True,
        check=False,
    )
    assert result.returncode == expected, result.stderr


@pytest.mark.parametrize("arguments", ["&values, typed", "typed, &values"])
def test_nested_template_list_borrow_inference(arguments: str) -> None:
    """
    title: Infer the exact element domain of a named list borrow.
    parameters:
      arguments: Arguments supplied to the call.
    """
    parameters = (
        "values: &list[T], seed: T"
        if arguments.startswith("&")
        else "seed: T, values: &list[T]"
    )
    ArxIO.string_to_buffer(
        f"@<T: i32 | i64>\nfn pick({parameters}) -> T:\n"
        "  return values[0]\n"
        "fn main() -> i32:\n"
        "  typed: i64 = 7\n"
        "  values: list[i64] = [1]\n"
        f"  assert pick({arguments}) == 1\n"
        f"  assert pick<i64>({arguments}) == 1\n"
        "  return 0\n"
    )
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    assert "irx_list_append" in text


@pytest.fixture(scope="module")
def binary_file_program(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    title: Verify and compile the byte workflow once without Arrow artifacts.
    parameters:
      tmp_path_factory: Factory for shared temporary test directories.
    returns: 'Result of this operation: verify and compile the byte workflow
      once without Arrow artifacts.'
    """
    if shutil.which("clang") is None:
        pytest.skip("binary file checks require clang")
    source = Path(__file__).parents[4] / "examples/binary-files.x"
    ArxIO.string_to_buffer(source.read_text())
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    artifacts = builder.translator.runtime_features.native_artifacts()
    assert all("arrow" not in str(artifact.path) for artifact in artifacts)
    assert "irx_file_read_bytes" in text and "irx_file_write_bytes" in text
    executable = tmp_path_factory.mktemp("binary-workflow") / "program"
    if sys.platform == "linux":
        return build_audited_file_program(builder, text, executable.parent)
    builder._build_from_ir(text, str(executable))
    return executable


def test_binary_file_roundtrip(
    binary_file_program: Path, tmp_path: Path
) -> None:
    """
    title: Independently inspect all bytes, append, empty writes and lifetimes.
    parameters:
      binary_file_program: Binary file program.
      tmp_path: Temporary directory for this test.
    """
    result = subprocess.run(
        [str(binary_file_program)],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    if sys.platform == "linux":
        assert b"AUDIT live=0 opened=6 released=6" in result.stderr
    assert (tmp_path / "binary-output.dat").read_bytes() == bytes(
        range(256)
    ) * 2
    assert (tmp_path / "binary-empty.dat").read_bytes() == b""


@pytest.mark.parametrize("binding", ["", "var :: ", "const :: "])
def test_inferred_declarations_translate(binding: str) -> None:
    """
    title: Inference crosses functions, nullable values, templates, and layout.
    parameters:
      binding: Resolved binding for the operation.
    """
    ArxIO.string_to_buffer(
        "limit: const :: auto = 10\n"
        "class Box:\n"
        "  value: auto = 3\n"
        "  count: static const :: auto = 1\n"
        "  fn read(self) -> i32:\n"
        "    return self.value\n"
        "@<T: i32 | i64>\n"
        "fn identity(value: const :: T) -> T:\n"
        "  result: const :: auto = value\n"
        "  return result\n"
        "fn optional() -> nullable[i32]:\n"
        "  return none\n"
        "fn frame() -> dataframe[x:i32]:\n"
        "  return dataframe({x:[1, 2]})\n"
        "fn tensor_value() -> tensor[i32, 2]:\n"
        "  return [1, 2]\n"
        "fn main() -> i32:\n"
        f"  value: {binding}auto = identity(1)\n"
        f"  box: {binding}auto = Box()\n"
        "  box.value = 4\n"
        f"  values: {binding}auto = [1, 2]\n"
        "  values.append(3)\n"
        f"  missing: {binding}auto = optional()\n"
        f"  table: {binding}auto = frame()\n"
        f"  tensor: {binding}auto = tensor_value()\n"
        "  assert table.nrows() == 2\n"
        "  assert table.ncols() == 1\n"
        "  column: const :: auto = table.x\n"
        "  assert series_count(column) == table.nrows()\n"
        "  assert fill_null(series_sum(table.x), 0) == 3\n"
        '  assert fill_null(series_sum(table["x"]), 0) == 3\n'
        "  assert tensor[1] == 2\n"
        "  assert is_null(missing)\n"
        "  assert box.read() == 4\n"
        "  assert Box.count == 1\n"
        "  assert value == 1\n"
        "  assert identity<i64>(1) == 1\n"
        "  assert limit == 10\n"
        "  total: i32 = 0\n"
        "  for i: auto = 0; i < 2; ++i:\n"
        "    total += i\n"
        "  return values[2] + total - 4\n"
    )
    module = Parser().parse(Lexer().lex())
    text = ArxBuilder().translate(module)
    llvm.parse_assembly(text).verify()
    main = module.nodes[-1]
    assert isinstance(main, astx.FunctionDef)
    declaration = next(
        node
        for node in main.body.nodes
        if isinstance(node, astx.VariableDeclaration) and node.name == "column"
    )
    initializer = declaration.value
    info = initializer.semantic
    assert isinstance(info, SemanticInfo)
    assert info.resource_ownership is not None
    assert info.resource_ownership.transfer_kind is OwnershipTransferKind.MOVE
    assert info.normalized_collection is not None
    normalized_info = info.normalized_collection.semantic
    assert isinstance(normalized_info, SemanticInfo)
    assert normalized_info.resource_ownership is info.resource_ownership


@pytest.mark.parametrize(
    "declaration,write",
    [
        ("value: const :: i32 = 1", "value = 2"),
        ("value: const :: auto = 1", "value += 1"),
        ("value: const :: i32 = 1", "++value"),
    ],
)
def test_constant_binding_writes_fail_before_lowering(
    declaration: str, write: str
) -> None:
    """
    title: Surface constant declarations authorize no scalar binding writes.
    parameters:
      declaration: Declaration being processed.
      write: Write.
    """
    ArxIO.string_to_buffer(
        f"fn main() -> i32:\n  {declaration}\n  {write}\n  return value\n"
    )
    with pytest.raises(SemanticError, match="declared as constant"):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.mark.parametrize(
    "declaration, call",
    [
        (
            "fn fixed(value: const :: i32) -> i32:\n"
            "  value += 1\n  return value\n",
            "fixed(1)",
        ),
        (
            "class Box:\n"
            "  fn fixed(value: const :: i32) -> static :: i32:\n"
            "    value += 1\n    return value\n",
            "Box.fixed(1)",
        ),
        (
            "@<T: i32 | i64>\n"
            "fn fixed(value: const :: T) -> T:\n"
            "  value += 1\n  return value\n",
            "fixed<i32>(1)",
        ),
    ],
)
def test_constant_parameter_writes_fail_before_lowering(
    declaration: str, call: str
) -> None:
    """
    title: Unchanged function heads enforce argument modifiers through
      analysis.
    parameters:
      declaration: Declaration being processed.
      call: Call being processed.
    """
    ArxIO.string_to_buffer(
        declaration + f"fn main() -> i32:\n  return {call}\n"
    )
    with pytest.raises(SemanticError, match="declared as constant"):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


@pytest.mark.parametrize(
    "source, message",
    [
        (
            "fn main() -> i32:\n  x: auto = none\n  return 0",
            "Cannot infer a concrete type",
        ),
        ("fn main() -> i32:\n  x: auto = []\n  return 0", "element type"),
        (
            "fn initial() -> i32:\n  return 1\nx: const :: auto = initial()",
            "runtime initialization is unsupported",
        ),
        (
            "class Recursive:\n  child: auto = Recursive()",
            "Field inference requires a literal initializer",
        ),
    ],
)
def test_inference_rejects_ambiguous_or_unsupported_storage(
    source: str, message: str
) -> None:
    """
    title: Inference neither invents a type nor enables unsupported
      initialization.
    parameters:
      source: Source input to process.
      message: Diagnostic or output message.
    """
    ArxIO.string_to_buffer(source)
    with pytest.raises(SemanticError, match=message):
        ArxBuilder().translate(Parser().parse(Lexer().lex()))


def test_failed_local_inference_keeps_dependent_names_in_scope() -> None:
    """
    title: Preserve a failed declaration's binding and report unrelated names.
    """
    ArxIO.string_to_buffer(
        "fn send(arg: i32) -> i32:\n  return arg\n"
        "fn main() -> i32:\n"
        "  value: auto = []\n"
        "  dependent: auto = value\n"
        "  annotated: i32 = value\n"
        "  print(value)\n"
        "  print(dependent + 1)\n"
        "  print(value[0])\n"
        "  print([1][value])\n"
        "  print(send(value))\n"
        "  print(value.method())\n"
        "  print(1[value])\n"
        "  print(annotated[0])\n"
        "  print(missing)\n"
        "  return dependent\n"
    )
    with pytest.raises(SemanticError) as error:
        ArxBuilder().translate(Parser().parse(Lexer().lex()))
    diagnostics = error.value.diagnostics.diagnostics
    primary, invalid_receiver, invalid_annotated, unresolved = diagnostics
    assert primary.code == DiagnosticCodes.SEMANTIC_TYPE_MISMATCH
    assert "list expression needs a concrete element type" in primary.message
    for invalid in (invalid_receiver, invalid_annotated):
        assert invalid.code == DiagnosticCodes.SEMANTIC_TYPE_MISMATCH
        assert invalid.message == "subscript access is not supported for Int32"
    assert unresolved.code == DiagnosticCodes.SEMANTIC_UNRESOLVED_NAME
    assert unresolved.message == "cannot resolve name 'missing'"


def test_failed_field_inference_keeps_lookup_without_allocating_slot() -> None:
    """
    title: Resolve inherited failed fields without adding object storage.
    """
    ArxIO.string_to_buffer(
        "fn initial() -> i32:\n  return 1\n"
        "class Box:\n"
        "  valid: i32 = 3\n"
        "  broken: auto = initial()\n"
        "class Child(Box):\n"
        "  own: i32 = 1\n"
        "fn main() -> i32:\n"
        "  box: Child = Child()\n"
        "  print(box.broken)\n"
        "  print(box.broken.child)\n"
        "  print(box.valid)\n"
        "  print(box.missing)\n"
        "  return 0\n"
    )
    module = Parser().parse(Lexer().lex())
    with pytest.raises(SemanticError) as error:
        ArxBuilder().translate(module)
    primary, unrelated = error.value.diagnostics.diagnostics
    assert primary.code == DiagnosticCodes.SEMANTIC_TYPE_MISMATCH
    assert "Field inference requires a literal initializer" in primary.message
    assert unrelated.code == DiagnosticCodes.SEMANTIC_INVALID_FIELD_ACCESS
    assert unrelated.message == "class 'Child' has no attribute 'missing'"
    child = next(
        node
        for node in module.nodes
        if isinstance(node, astx.ClassDefStmt) and node.name == "Child"
    )
    semantic = getattr(child, "semantic")
    class_ = semantic.resolved_class
    assert "broken" in class_.member_table
    assert set(class_.layout.visible_field_slots) == {"valid", "own"}


def test_collection_access_paths_have_equivalent_semantics() -> None:
    """
    title: Collection paths retain equivalent semantics as metadata is unified.
    """
    ArxIO.string_to_buffer(
        "fn frame() -> dataframe[x:i32]:\n  return dataframe({x:[1, 2]})\n"
        "fn main() -> i32:\n"
        "  typed_list: list[i32] = [1]\n"
        "  inferred_list: auto = [1]\n"
        "  typed_list.append(2)\n"
        "  inferred_list.append(2)\n"
        "  typed_frame: dataframe[x:i32] = frame()\n"
        "  inferred_frame: auto = frame()\n"
        "  typed_frame.x\n"
        "  inferred_frame.x\n"
        '  typed_frame["x"]\n'
        '  inferred_frame["x"]\n'
        "  typed_frame.nrows()\n"
        "  inferred_frame.nrows()\n"
        "  typed_frame.ncols()\n"
        "  inferred_frame.ncols()\n"
        "  return 0\n"
    )
    module = Parser().parse(Lexer().lex())
    main = module.nodes[-1]
    assert isinstance(main, astx.FunctionDef)
    operations = [
        node
        for node in main.body.nodes
        if not isinstance(
            node, (astx.VariableDeclaration, astx.FunctionReturn)
        )
    ]
    assert len(operations) == 10
    text = ArxBuilder().translate(module)
    llvm.parse_assembly(text).verify()
    for typed, inferred in zip(operations[::2], operations[1::2]):
        typed_info = typed.semantic
        inferred_info = inferred.semantic
        assert isinstance(typed_info, SemanticInfo)
        assert isinstance(inferred_info, SemanticInfo)
        normalized = inferred_info.normalized_collection
        assert normalized is not None
        if isinstance(typed, astx.MethodCall):
            # Only metadata pairs change to generic calls on both sides.
            assert typed.method_name in {"nrows", "ncols"}
            assert typed_info.normalized_collection is not None
            assert type(typed_info.normalized_collection) is type(normalized)
            assert isinstance(typed_info.resolved_type, astx.Int64)
        else:
            # List append and both column forms keep their unmigrated paths.
            assert typed_info.normalized_collection is None
            assert type(normalized) is type(typed)
        assert same_type(typed_info.resolved_type, inferred_info.resolved_type)


@pytest.mark.parametrize(
    "operation", ["nrows(1)", "ncols(unexpected=1)", "nrows<i32>()"]
)
def test_collection_metadata_arguments_fail_before_lowering(
    operation: str,
) -> None:
    """
    title: Explicit and inferred calls share semantic diagnostics and Unicode
      spans.
    parameters:
      operation: Operation to resolve or execute.
    """
    reports: list[tuple[str, str, int, int]] = []
    method = operation.split("(", maxsplit=1)[0].split("<", maxsplit=1)[0]
    for annotation in ("dataframe[x:i32]", "auto"):
        source = (
            "fn frame() -> dataframe[x:i32]:\n  return dataframe({x:[1]})\n"
            "fn main() -> i32:\n"
            f"  dátá: {annotation} = frame()\n"
            f"  0; dátá.{operation}\n  return 0\n"
        )
        ArxIO.string_to_buffer(source)
        module = Parser().parse(Lexer().lex())
        with pytest.raises(SemanticError) as error:
            ArxBuilder().translate(module)
        diagnostics = error.value.diagnostics.diagnostics
        assert len(diagnostics) == 1
        diagnostic = diagnostics[0]
        assert diagnostic.code == DiagnosticCodes.SEMANTIC_TYPE_MISMATCH
        assert diagnostic.message == (
            f"DataFrame {method} expects no arguments or templates"
        )
        location = diagnostic.resolved_source()
        assert location is not None
        assert location.line == 5
        assert location.col == source.splitlines()[4].index(method) + 1
        reports.append(
            (diagnostic.code, diagnostic.message, location.line, location.col)
        )
    assert reports[0] == reports[1]


def test_callable_modifiers_and_multiline_headers_translate() -> None:
    """
    title: Callable policies and wrapped signatures survive analysis and LLVM.
    """
    ArxIO.string_to_buffer(
        "class Calculator:\n"
        "  fn hidden(\n    self, value: const :: i32,\n  ) ->\n"
        "    private ::\n    i32\n  :\n    return value\n"
        "  fn read(self) -> public :: i32:\n    return self.hidden(1)\n"
        "  @<T: i32 | i64>\n"
        "  fn calculate(\n    value: const :: T,\n  ) ->\n"
        "    public static ::\n    T\n  :\n    return value\n"
        "fn helper(\n  value: i32 = 0,\n) ->\n  private ::\n  i32\n:\n"
        "  return value\n"
        "fn main() -> public :: i32:\n"
        "  calculator: Calculator = Calculator()\n"
        "  return Calculator.calculate(calculator.read()) - helper(1)\n"
    )
    text = ArxBuilder().translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()


@pytest.mark.parametrize("import_style", ["from", "namespace"])
def test_private_function_imports_fail_during_analysis(
    tmp_path: Path, import_style: str
) -> None:
    """
    title: Frontend visibility cannot be bypassed by either import spelling.
    parameters:
      tmp_path: Temporary directory for this test.
      import_style: Import style.
    """
    (tmp_path / "library.x").write_text(
        "```\ntitle: Private library\n```\n"
        "fn hidden() -> private :: i32:\n  return 7\n",
        encoding="utf-8",
    )
    source = (
        (
            "import hidden as alias from library\n"
            "fn main() -> i32:\n  return alias()\n"
        )
        if import_style == "from"
        else (
            "import library as alias\n"
            "fn main() -> i32:\n  return alias.hidden()\n"
        )
    )
    ArxIO.string_to_buffer(source)
    entry = tmp_path / "main.x"
    entry.write_text(source, encoding="utf-8")
    root = ParsedModule("main", Parser().parse(Lexer().lex()), str(entry))
    with pytest.raises(SemanticError, match="private to its module") as error:
        ArxBuilder().translate_modules(root, FileImportResolver((str(entry),)))
    diagnostic = next(
        item
        for item in error.value.diagnostics.diagnostics
        if "private to its module" in item.message
    )
    location = diagnostic.resolved_source()
    assert location is not None
    assert location.line == (1 if import_style == "from" else 3)


def test_imported_template_can_call_its_private_module_helper(
    tmp_path: Path,
) -> None:
    """
    title: Template privacy uses the defining module rather than the caller.
    parameters:
      tmp_path: Temporary directory for this test.
    """
    (tmp_path / "library.x").write_text(
        "```\ntitle: Private template helpers\n```\n"
        "@<T: i32 | i64>\n"
        "fn hidden(value: const :: T) -> private :: T:\n  return value\n"
        "@<T: i32 | i64>\n"
        "fn visible(value: const :: T) -> public :: T:\n"
        "  return hidden(value)\n",
        encoding="utf-8",
    )
    source = (
        "import visible from library\nfn main() -> i32:\n  return visible(0)\n"
    )
    entry = tmp_path / "main.x"
    entry.write_text(source, encoding="utf-8")
    ArxIO.string_to_buffer(source)
    root = ParsedModule("main", Parser().parse(Lexer().lex()), str(entry))
    text = ArxBuilder().translate_modules(
        root, FileImportResolver((str(entry),))
    )
    llvm.parse_assembly(text).verify()


@pytest.fixture(scope="module")
def metadata_count_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    title: Compile all metadata receiver forms once, separate from execution.
    parameters:
      tmp_path_factory: Factory for shared temporary test directories.
    returns: 'Result of this operation: compile all metadata receiver forms
      once, separate from execution.'
    """
    if shutil.which("clang") is None or shutil.which("c++") is None:
        pytest.skip("native Clang and C++ toolchains required")
    ArxIO.string_to_buffer(
        "```\ntitle: Metadata receiver evaluation and lifetime\n```\n"
        "calls: i32 = 0\n"
        "fn frame() -> dataframe[x:i32, y:i32]:\n"
        "  calls += 1\n"
        "  return dataframe({x:[1, 2, 3], y:[4, 5, 6]})\n"
        "fn runtime_counts(rows: dataframe[...]) -> i64:\n"
        "  return rows.nrows() * 10 + rows.ncols()\n"
        "fn main() -> i32:\n"
        "  typed: dataframe[x:i32, y:i32] = frame()\n"
        "  inferred: auto = frame()\n"
        "  assert typed.nrows() == 3\n"
        "  assert inferred.nrows() == 3\n"
        "  assert typed.ncols() == 2\n"
        "  assert inferred.ncols() == 2\n"
        "  assert runtime_counts(typed) == 32\n"
        "  assert runtime_counts(inferred) == 32\n"
        "  assert calls == 2\n"
        "  assert frame().nrows() == 3\n"
        "  assert calls == 3\n"
        "  assert frame().ncols() == 2\n"
        "  assert calls == 4\n"
        "  return 0\n"
    )
    module = Parser().parse(Lexer().lex())
    builder = ArxBuilder()
    text = builder.translate(module)
    parsed_ir = llvm.parse_assembly(text)
    parsed_ir.verify()
    # The native main wrapper delegates to this analyzed entry body.
    main = parsed_ir.get_function("irx.entry.main")
    released_temporaries = 0
    for block in main.blocks:
        calls = [item for item in block.instructions if item.opcode == "call"]
        released = [
            next(iter(item.operands))
            for item in calls
            if tuple(item.operands)[-1].name == "irx_arrow_table_release"
        ]
        for item in calls:
            operands = tuple(item.operands)
            if operands[-1].name not in {
                "irx_arrow_table_num_rows",
                "irx_arrow_table_num_columns",
            }:
                continue
            # The two factory temporaries must be dropped exactly once in
            # their expression, unlike loads from the longer-lived bindings.
            releases = sum(value == operands[0] for value in released)
            if releases:
                assert releases == 1
                released_temporaries += 1
    assert released_temporaries == 2
    executable = tmp_path_factory.mktemp("metadata-counts") / "program"
    builder._build_from_ir_result(text, str(executable), True, "auto")
    return executable


def test_metadata_counts_preserve_evaluation_and_lifetimes(
    metadata_count_binary: Path,
) -> None:
    """
    title: Static, inferred, runtime-schema, and temporary receivers run alike.
    parameters:
      metadata_count_binary: Metadata count binary.
    """
    result = subprocess.run(
        [str(metadata_count_binary)],
        cwd=metadata_count_binary.parent,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == b""
    assert result.stderr == b""
