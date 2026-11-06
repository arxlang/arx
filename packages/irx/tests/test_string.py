"""
title: Tests for string operations.
"""

import ctypes as ct
import shutil
import subprocess
import tempfile

from pathlib import Path

import astx
import irx.builder.runtime.text.feature as text_runtime_feature
import pytest

from irx.analysis import (
    OwnershipEscapeKind,
    OwnershipKind,
    OwnershipTransferKind,
    ResourceKind,
    SemanticError,
    SemanticInfo,
    TextOperationKind,
    analyze,
    resource_ownership,
)
from irx.builder import Builder as LLVMBuilder
from irx.builder.base import Builder
from irx.builder.strings import StringEmission
from irx.system import PrintExpr
from llvmlite import binding as llvm
from llvmlite import ir

from .conftest import assert_ir_parses, build_and_run, check_result

EXPECTED_STRING_REPLACEMENT_FREES = 2
TEXT_OUT_OF_RANGE = 4
TEXT_ENCODING_ERROR = 5


def test_string_emission_caches_are_module_owned_and_collision_safe() -> None:
    """
    title: Reuse exact constants and helpers without sharing LLVM module state.
    """
    integer = ir.IntType(32)
    pointer = ir.IntType(8).as_pointer()

    def symbol(feature: str, name: str) -> ir.Function:
        """
        title: Constant and equality emission need no native activation.
        parameters:
          feature:
            type: str
          name:
            type: str
        returns:
          type: ir.Function
        """
        raise AssertionError(f"unexpected native request: {feature}/{name}")

    def guard(
        node: astx.AST,
        condition: ir.Value,
        *,
        code: str,
        message: str,
        block_name: str,
        exception_role: str = "RuntimeError",
    ) -> None:
        """
        title: Interning and equality never allocate fallible storage.
        parameters:
          node:
            type: astx.AST
          condition:
            type: ir.Value
          code:
            type: str
          message:
            type: str
          block_name:
            type: str
          exception_role:
            type: str
        """
        del node, condition, code, message, block_name, exception_role
        raise AssertionError("unexpected allocation guard")

    cached: list[ir.GlobalVariable] = []
    for _ in range(2):
        module = ir.Module()
        # User declarations must not become compiler helper/cache entries.
        collision = ir.GlobalVariable(module, integer, "fmt")
        collision.initializer = ir.Constant(integer, 7)
        reserved = ir.Function(
            module, ir.FunctionType(ir.VoidType(), []), "string_equals"
        )
        reserved.linkage = "external"
        function = ir.Function(
            module, ir.FunctionType(pointer, []), "constant_pointer"
        )
        builder = ir.IRBuilder(function.append_basic_block("entry"))
        strings = StringEmission(
            module, ir.IntType(64), lambda: builder, symbol, guard
        )
        text = strings.constant_global("é😀", name_hint="fmt")
        assert text is strings.constant_global("é😀", name_hint="fmt")
        assert text is not collision
        assert text.parent is module
        assert bytes(text.initializer.constant) == "é😀\0".encode()
        equality = strings.equality_function()
        assert equality is strings.equality_function()
        assert equality is not reserved
        builder.ret(strings.constant("é😀", name_hint="fmt"))
        llvm.parse_assembly(str(module)).verify()
        cached.append(text)
    assert cached[0] is not cached[1]


def test_formatted_string_releases_unpublished_allocation() -> None:
    """
    title: Formatting owns its allocation until successful caller transfer.
    summary: >-
      Deterministic LLVM runtime stubs exercise all three failure boundaries
      without relying on actual allocation exhaustion or invalid libc formats.
      One compiled probe covers every case; its result encodes failure,
      allocation count, and release count.
    """
    module = ir.Module()
    integer, size = ir.IntType(32), ir.IntType(64)
    byte, pointer = ir.IntType(8), ir.IntType(8).as_pointer()
    allocations = ir.GlobalVariable(module, integer, "allocations")
    releases = ir.GlobalVariable(module, integer, "releases")
    allocations.initializer = releases.initializer = ir.Constant(integer, 0)
    size_result = ir.GlobalVariable(module, integer, "size_result")
    write_result = ir.GlobalVariable(module, integer, "write_result")
    size_result.initializer = write_result.initializer = ir.Constant(
        integer, 0
    )
    allocate = ir.GlobalVariable(module, ir.IntType(1), "allocate")
    allocate.initializer = ir.Constant(ir.IntType(1), 0)
    storage = ir.GlobalVariable(module, byte, "storage")
    storage.initializer = ir.Constant(byte, 0)
    snprintf = ir.Function(
        module,
        ir.FunctionType(integer, [pointer, size, pointer], var_arg=True),
        "snprintf",
    )
    probe = ir.IRBuilder(snprintf.append_basic_block("entry"))
    sizing = probe.icmp_unsigned(
        "==", snprintf.args[0], ir.Constant(pointer, None)
    )
    probe.ret(
        probe.select(
            sizing,
            probe.load(size_result),
            probe.load(write_result),
        )
    )
    malloc = ir.Function(module, ir.FunctionType(pointer, [size]), "malloc")
    probe = ir.IRBuilder(malloc.append_basic_block("entry"))
    probe.store(
        probe.add(probe.load(allocations), ir.Constant(integer, 1)),
        allocations,
    )
    probe.ret(
        probe.select(probe.load(allocate), storage, ir.Constant(pointer, None))
    )
    free = ir.Function(
        module, ir.FunctionType(ir.VoidType(), [pointer]), "free"
    )
    probe = ir.IRBuilder(free.append_basic_block("entry"))
    probe.store(
        probe.add(probe.load(releases), ir.Constant(integer, 1)), releases
    )
    probe.ret_void()
    function = ir.Function(
        module,
        ir.FunctionType(integer, [integer, integer, ir.IntType(1)]),
        "probe",
    )
    builder = ir.IRBuilder(function.append_basic_block("entry"))
    for destination, source in zip(
        (size_result, write_result, allocate), function.args, strict=True
    ):
        builder.store(source, destination)
    builder.store(ir.Constant(integer, 0), allocations)
    builder.store(ir.Constant(integer, 0), releases)

    def finish(status: int) -> None:
        """
        title: Return the status and observed ownership transitions.
        parameters:
          status:
            type: int
        """
        counts = builder.add(
            builder.mul(builder.load(allocations), ir.Constant(integer, 10)),
            builder.load(releases),
        )
        builder.ret(builder.add(ir.Constant(integer, status * 100), counts))

    def symbol(feature: str, name: str) -> ir.Function:
        """
        title: Supply only the formatting service's registered C ABI.
        parameters:
          feature:
            type: str
          name:
            type: str
        returns:
          type: ir.Function
        """
        assert feature == "libc"
        return {"snprintf": snprintf, "malloc": malloc, "free": free}[name]

    def guard(
        node: astx.AST,
        condition: ir.Value,
        *,
        code: str,
        message: str,
        block_name: str,
        exception_role: str = "RuntimeError",
    ) -> None:
        """
        title: Model checked control transfer without a compiler owner.
        parameters:
          node:
            type: astx.AST
          condition:
            type: ir.Value
          code:
            type: str
          message:
            type: str
          block_name:
            type: str
          exception_role:
            type: str
        """
        del node, code, message, block_name, exception_role
        with builder.if_then(builder.not_(condition)):
            finish(1)

    strings = StringEmission(module, size, lambda: builder, symbol, guard)
    result = strings.format_heap(
        astx.LiteralInt32(7),
        strings.format_global("%d"),
        [ir.Constant(integer, 7)],
    )
    builder.call(free, [result])
    finish(0)
    compiled = llvm.parse_assembly(str(module))
    compiled.verify()
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()
    machine = llvm.Target.from_default_triple().create_target_machine()
    with llvm.create_mcjit_compiler(compiled, machine) as engine:
        engine.finalize_object()
        run = ct.CFUNCTYPE(ct.c_int32, ct.c_int32, ct.c_int32, ct.c_bool)(
            engine.get_function_address("probe")
        )
        for query, write, allocated, expected in (
            (-1, 2, True, 100),
            (2, 2, False, 110),
            (2, -1, True, 111),
            (2, 2, True, 11),
        ):
            assert run(query, write, allocated) == expected


class NativeTextList(ct.Structure):
    """
    title: Test the native owned-string list output descriptor.
    """

    _fields_ = [
        ("data", ct.POINTER(ct.c_void_p)),
        ("length", ct.c_int64),
        ("capacity", ct.c_int64),
        ("element_size", ct.c_int64),
        ("element_kind", ct.c_int32),
    ]


@pytest.fixture(scope="module")
def text_runtime(tmp_path_factory: pytest.TempPathFactory) -> ct.CDLL:
    """
    title: Compile the real text/list ABI once for the native contract matrix.
    parameters:
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: ct.CDLL
    """
    if shutil.which("clang") is None:
        pytest.skip("clang required")
    native = Path(text_runtime_feature.__file__).parent / "native"
    lists = native.parent.parent / "list" / "native"
    library = tmp_path_factory.mktemp("text-runtime") / "text.so"
    subprocess.run(
        [
            "clang",
            "-std=c99",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-shared",
            "-fPIC",
            "-I",
            str(lists),
            str(native / "irx_text_runtime.c"),
            str(lists / "irx_list_runtime.c"),
            "-o",
            str(library),
        ],
        check=True,
        capture_output=True,
    )
    runtime = ct.CDLL(str(library))
    string, integer, output = ct.c_char_p, ct.c_int64, ct.POINTER(ct.c_void_p)
    arguments = {
        "len": [string, ct.POINTER(integer)],
        "ord": [string, ct.POINTER(integer)],
        "validate": [string, integer, ct.POINTER(integer)],
        "int": [string, integer, ct.POINTER(integer)],
        "index": [string, integer, output],
        "slice": [string, integer, integer, integer, output],
        "strip": [string, string, output],
        "split": [string, string, integer, ct.POINTER(NativeTextList)],
    }
    for name, types in arguments.items():
        function = getattr(runtime, f"irx_text_{name}")
        function.argtypes = types
        function.restype = ct.c_int32
    runtime.free.argtypes = [ct.c_void_p]
    runtime.free.restype = None
    runtime.irx_list_destroy.argtypes = [ct.POINTER(NativeTextList)]
    runtime.irx_list_destroy.restype = None
    return runtime


@pytest.mark.parametrize("value", ["", "abc", "é😀", "e\u0301", "\U0010ffff"])
def test_text_codepoint_queries(text_runtime: ct.CDLL, value: str) -> None:
    """
    title: Length, ordinal and indexing count scalars without normalization.
    parameters:
      text_runtime:
        type: ct.CDLL
      value:
        type: str
    """
    encoded = value.encode()
    number = ct.c_int64(-1)
    assert text_runtime.irx_text_len(encoded, ct.byref(number)) == 0
    assert number.value == len(value)
    expected_status = 0 if len(value) == 1 else 1
    assert (
        text_runtime.irx_text_ord(encoded, ct.byref(number)) == expected_status
    )
    assert number.value == (ord(value) if len(value) == 1 else 0)
    for index in range(-1, len(value) + 1):
        output = ct.c_void_p()
        status = text_runtime.irx_text_index(encoded, index, ct.byref(output))
        if 0 <= index < len(value):
            assert status == 0
            try:
                assert ct.string_at(output).decode() == value[index]
            finally:
                text_runtime.free(output)
        else:
            assert status == TEXT_OUT_OF_RANGE and output.value is None


@pytest.mark.parametrize(
    "invalid",
    [
        b"\0",
        b"a\0b",
        b"\x80",
        b"\xc0\x80",
        b"\xe0\x80\x80",
        b"\xed\xa0\x80",
        b"\xf4\x90\x80\x80",
        b"\xf0\x9f",
        b"\xff",
        b"\xc2x",
    ],
)
def test_text_rejects_invalid_utf8(
    text_runtime: ct.CDLL, invalid: bytes
) -> None:
    """
    title: Bounded native input rejects NUL and every UTF-8 invalidity class.
    parameters:
      text_runtime:
        type: ct.CDLL
      invalid:
        type: bytes
    """
    count = ct.c_int64(99)
    assert (
        text_runtime.irx_text_validate(invalid, len(invalid), ct.byref(count))
        == TEXT_ENCODING_ERROR
    )
    assert count.value == 0
    if b"\0" not in invalid:
        output = ct.c_void_p()
        assert (
            text_runtime.irx_text_strip(invalid, None, ct.byref(output))
            == TEXT_ENCODING_ERROR
        )
        assert output.value is None


@pytest.mark.parametrize(
    ("start", "stop", "step", "status"),
    [
        (0, 4, 1, 0),
        (1, 3, 1, 0),
        (1, 99, 1, 0),
        (99, 100, 1, 0),
        (3, 1, 1, 0),
        (0, 0, 1, 0),
        (-1, 2, 1, 1),
        (0, -1, 1, 1),
        (0, 2, 0, 1),
        (0, 2, 2, 1),
        (0, 2, -1, 1),
    ],
)
def test_text_slice_contract(
    text_runtime: ct.CDLL, start: int, stop: int, step: int, status: int
) -> None:
    """
    title: Half-open slices clip only nonnegative bounds and require unit step.
    parameters:
      text_runtime:
        type: ct.CDLL
      start:
        type: int
      stop:
        type: int
      step:
        type: int
      status:
        type: int
    """
    value = "A😀e\u0301"
    output = ct.c_void_p()
    assert (
        text_runtime.irx_text_slice(
            value.encode(), start, stop, step, ct.byref(output)
        )
        == status
    )
    if status:
        assert output.value is None
    else:
        try:
            assert ct.string_at(output).decode() == value[start:stop]
        finally:
            text_runtime.free(output)


@pytest.mark.parametrize(
    ("value", "separator"),
    [
        ("", None),
        ("", ","),
        (" \t\n", None),
        (" a  b  ", None),
        ("a,,b,", ","),
        ("é😀文😀", "😀"),
        ("aaaaa", "aa"),
        ("a\u00a0b\u2003c\u001cd", None),
    ],
)
@pytest.mark.parametrize("limit", [-7, -1, 0, 1, 2])
def test_text_split_matches_supported_python_contract(
    text_runtime: ct.CDLL, value: str, separator: str | None, limit: int
) -> None:
    """
    title: >-
      Whitespace and explicit splitting preserve limit and empty semantics.
    parameters:
      text_runtime:
        type: ct.CDLL
      value:
        type: str
      separator:
        type: str | None
      limit:
        type: int
    """
    output = NativeTextList()
    assert (
        text_runtime.irx_text_split(
            value.encode(),
            separator.encode() if separator is not None else None,
            limit,
            ct.byref(output),
        )
        == 0
    )
    try:
        assert output.element_kind == 1
        assert output.element_size == ct.sizeof(ct.c_void_p)
        words = [
            ct.string_at(output.data[i]).decode() for i in range(output.length)
        ]
        assert words == value.split(separator, limit)
    finally:
        text_runtime.irx_list_destroy(ct.byref(output))
    assert output.length == 0 and not output.data


@pytest.mark.parametrize(
    ("value", "chars"),
    [
        ("", None),
        (" \t\n", None),
        (" a  b ", None),
        ("\u2003a\u00a0", None),
        ("éétextéé", "é"),
        ("xyhellozyx", "xyz"),
        ("  abc  ", ""),
        ("\u200bvalue\u200b", None),
    ],
)
def test_text_strip_set_contract(
    text_runtime: ct.CDLL, value: str, chars: str | None
) -> None:
    """
    title: Strip removes code-point sets rather than substrings or graphemes.
    parameters:
      text_runtime:
        type: ct.CDLL
      value:
        type: str
      chars:
        type: str | None
    """
    output = ct.c_void_p()
    assert (
        text_runtime.irx_text_strip(
            value.encode(),
            chars.encode() if chars is not None else None,
            ct.byref(output),
        )
        == 0
    )
    try:
        assert ct.string_at(output).decode() == value.strip(chars)
    finally:
        text_runtime.free(output)


@pytest.mark.parametrize(
    ("value", "base", "status", "expected"),
    [
        ("  +42\u2003", 10, 0, 42),
        ("-0", 10, 0, 0),
        ("101", 2, 0, 5),
        ("zZ", 36, 0, 1295),
        ("-ff", 16, 0, -255),
        ("9223372036854775807", 10, 0, 2**63 - 1),
        ("-9223372036854775808", 10, 0, -(2**63)),
        ("9223372036854775808", 10, 2, 0),
        ("-9223372036854775809", 10, 2, 0),
        ("8000000000000000", 16, 2, 0),
        ("", 10, 1, 0),
        (" + ", 10, 1, 0),
        ("12junk", 10, 1, 0),
        ("1 2", 10, 1, 0),
        ("2", 2, 1, 0),
        ("0xff", 16, 1, 0),
        ("1_000", 10, 1, 0),
        ("٣", 10, 1, 0),
        ("1", 0, 1, 0),
        ("1", 1, 1, 0),
        ("1", 37, 1, 0),
    ],
)
def test_text_integer_contract(
    text_runtime: ct.CDLL, value: str, base: int, status: int, expected: int
) -> None:
    """
    title: >-
      Integer parsing is complete, locale independent and i64 range checked.
    parameters:
      text_runtime:
        type: ct.CDLL
      value:
        type: str
      base:
        type: int
      status:
        type: int
      expected:
        type: int
    """
    output = ct.c_int64(99)
    assert (
        text_runtime.irx_text_int(value.encode(), base, ct.byref(output))
        == status
    )
    assert output.value == expected


def test_text_native_invalid_options_and_whitespace(
    text_runtime: ct.CDLL,
) -> None:
    """
    title: >-
      Optional text validation and the complete whitespace set are explicit.
    parameters:
      text_runtime:
        type: ct.CDLL
    """
    output = ct.c_void_p()
    words = NativeTextList()
    count = ct.c_int64(99)
    assert text_runtime.irx_text_len(None, ct.byref(count)) == 1
    assert count.value == 0
    assert text_runtime.irx_text_len(b"x", None) == 1
    assert text_runtime.irx_text_split(b"a", b"", -1, ct.byref(words)) == 1
    assert not words.data and words.length == 0
    assert (
        text_runtime.irx_text_split(b"a", b"\xff", -1, ct.byref(words))
        == TEXT_ENCODING_ERROR
    )
    assert not words.data and words.length == 0
    assert (
        text_runtime.irx_text_strip(b"a", b"\xff", ct.byref(output))
        == TEXT_ENCODING_ERROR
    )
    assert output.value is None
    spaces = "".join(
        chr(cp)
        for cp in (
            *range(9, 14),
            *range(0x1C, 0x21),
            0x85,
            0xA0,
            0x1680,
            *range(0x2000, 0x200B),
            0x2028,
            0x2029,
            0x202F,
            0x205F,
            0x3000,
        )
    )
    assert all(char.isspace() for char in spaces)
    value = (spaces + "x" + spaces).encode()
    assert text_runtime.irx_text_strip(value, None, ct.byref(output)) == 0
    try:
        assert ct.string_at(output) == b"x"
    finally:
        text_runtime.free(output)
    assert text_runtime.irx_text_split(value, None, -1, ct.byref(words)) == 0
    try:
        assert words.length == 1 and ct.string_at(words.data[0]) == b"x"
    finally:
        text_runtime.irx_list_destroy(ct.byref(words))


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        (astx.FunctionCall("int", []), "requires a text"),
        (astx.FunctionCall("int", [astx.LiteralInt32(4)]), "requires text"),
        (
            astx.FunctionCall(
                "int", [astx.LiteralString("1"), astx.LiteralBoolean(True)]
            ),
            "integer",
        ),
        (
            astx.FunctionCall(
                "int", [astx.LiteralString("1"), astx.LiteralUInt64(10)]
            ),
            "integer",
        ),
        (
            astx.FunctionCall(
                "ord", [astx.LiteralString("x"), astx.LiteralInt32(1)]
            ),
            "too many",
        ),
        (
            astx.FunctionCall(
                "ord",
                [],
                keywords=(
                    astx.KeywordArgument("text", astx.LiteralString("x")),
                ),
            ),
            "unknown",
        ),
        (
            astx.FunctionCall(
                "int",
                [astx.LiteralString("1"), astx.LiteralInt32(10)],
                keywords=(astx.KeywordArgument("base", astx.LiteralInt32(2)),),
            ),
            "duplicate",
        ),
        (
            astx.FunctionCall(
                "int",
                [astx.LiteralString("1")],
                keywords=(
                    astx.KeywordArgument("radix", astx.LiteralInt32(2)),
                ),
            ),
            "unknown",
        ),
        (
            astx.MethodCall(
                astx.LiteralString("a"), "strip", [astx.LiteralInt32(1)]
            ),
            "requires text",
        ),
        (
            astx.MethodCall(
                astx.LiteralString("a"),
                "split",
                [astx.LiteralNone(), astx.LiteralFloat32(1.0)],
            ),
            "integer",
        ),
        (
            astx.MethodCall(
                astx.LiteralString("a"),
                "split",
                [],
                keywords=(
                    astx.KeywordArgument("count", astx.LiteralInt32(1)),
                ),
            ),
            "unknown",
        ),
        (
            astx.MethodCall(astx.LiteralString("a"), "int", []),
            "unsupported text method",
        ),
        (astx.MethodCall(astx.LiteralInt32(1), "strip", []), "text receiver"),
        (
            astx.SubscriptExpr(
                astx.LiteralString("a"), astx.LiteralBoolean(True)
            ),
            "integer",
        ),
        (
            astx.SubscriptExpr(
                astx.LiteralString("a"), lower=astx.LiteralFloat32(0.0)
            ),
            "integer",
        ),
        (
            astx.SubscriptExpr(astx.LiteralString("a"), astx.LiteralNone()),
            "integer",
        ),
        (
            astx.MethodCall(
                astx.VariableDeclaration(
                    "word", astx.String(), value=astx.LiteralString("x")
                ),
                "strip",
                [],
            ),
            "must be expressions",
        ),
        (astx.LiteralString("a\0b"), "NUL"),
        (astx.LiteralString("\ud800"), "Unicode scalar"),
    ],
)
def test_text_semantic_contract_rejections(
    expression: astx.AST, message: str
) -> None:
    """
    title: Invalid text calls and storage fail during analysis, not lowering.
    parameters:
      expression:
        type: astx.AST
      message:
        type: str
    """
    with pytest.raises(SemanticError, match=message):
        analyze(_string_main(expression))


def test_text_plans_preserve_argument_order_and_reanalysis() -> None:
    """
    title: Text plans bind named operands in source order and clear stale data.
    """
    receiver = astx.LiteralString("a,b")
    limit = astx.LiteralInt64(1)
    separator = astx.LiteralString(",")
    call = astx.MethodCall(
        receiver,
        "split",
        [],
        keywords=(
            astx.KeywordArgument("maxsplit", limit),
            astx.KeywordArgument("sep", separator),
        ),
    )
    length = astx.CollectionLength(astx.LiteralString("😀"))
    module = _string_main(call, length)
    analyze(module)
    info = call.semantic
    assert isinstance(info, SemanticInfo)
    assert info.resolved_text_operation is not None
    assert info.resolved_text_operation.kind is TextOperationKind.SPLIT
    assert info.resolved_text_operation.evaluations == (
        receiver,
        limit,
        separator,
    )
    assert info.resolved_text_operation.argument_indices == (0, 2, 1)
    assert resource_ownership(call).kind is OwnershipKind.OWNED
    assert isinstance(length.semantic.resolved_type, astx.Int64)
    assert length.semantic.resolved_text_operation is not None
    length.base = astx.ListExpr([astx.LiteralInt64(1)])
    analyze(module)
    assert length.semantic.resolved_text_operation is None
    assert length.semantic.resolved_collection_method is not None


@pytest.mark.parametrize(
    ("expression", "frees"),
    [
        (astx.MethodCall(astx.LiteralString(" x "), "strip", []), 1),
        (
            astx.SubscriptExpr(
                astx.BinaryOp(
                    "+", astx.LiteralString("a"), astx.LiteralString("b")
                ),
                astx.LiteralInt32(1),
            ),
            3,
        ),
        (
            astx.SubscriptExpr(
                astx.BinaryOp(
                    "+", astx.LiteralString("a"), astx.LiteralString("b")
                ),
                lower=astx.LiteralInt32(1),
            ),
            3,
        ),
    ],
)
def test_owned_text_result_cleanup(
    expression: astx.DataType, frees: int
) -> None:
    """
    title: Source temporaries, snapshots, and owned results each drop once.
    parameters:
      expression:
        type: astx.DataType
      frees:
        type: int
    """
    module = _string_main(
        astx.VariableDeclaration(
            "result",
            astx.String(),
            value=expression,
        )
    )
    assert_executed_string_frees(module, frees)


def assert_executed_string_frees(module: astx.Module, expected: int) -> None:
    """
    title: Count executed source cleanup calls instead of failure-edge copies.
    summary: Instrument source functions only; runtime bookkeeping is separate.
    parameters:
      module:
        type: astx.Module
      expected:
        type: int
    """
    builder = LLVMBuilder()
    builder.translate(module)
    generated = builder.translator._llvm.module
    integer = ir.IntType(32)
    counter = ir.GlobalVariable(generated, integer, "test.free_count")
    counter.initializer = ir.Constant(integer, 0)
    for (
        function
    ) in builder.translator.module_state.llvm_functions_by_symbol_id.values():
        for block in function.blocks:
            for instruction in list(block.instructions):
                if (
                    not isinstance(instruction, ir.CallInstr)
                    or instruction.callee.name != "free"
                ):
                    continue
                instrument = ir.IRBuilder(block)
                instrument.position_before(instruction)
                increment = instrument.add(
                    instrument.load(counter), ir.Constant(integer, 1)
                )
                instrument.store(increment, counter)
    wrapper = generated.get_global("main")
    assert isinstance(wrapper, ir.Function)
    success = next(
        block for block in wrapper.blocks if block.name == "success"
    )
    terminator = success.terminator
    assert terminator is not None
    instrument = ir.IRBuilder(success)
    instrument.position_before(terminator)
    counted = instrument.load(counter)
    terminator.replace_usage(terminator.operands[0], counted)
    text = str(generated)
    llvm.parse_assembly(text).verify()
    with tempfile.TemporaryDirectory() as directory:
        executable = Path(directory) / "string_cleanup"
        builder._build_from_ir(text, str(executable))
        result = subprocess.run(
            [str(executable)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    assert result.stderr == ""
    assert result.returncode == expected


def _string_concat(lhs: str, rhs: str) -> astx.BinaryOp:
    """
    title: Build one heap-producing string concatenation.
    parameters:
      lhs:
        type: str
      rhs:
        type: str
    returns:
      type: astx.BinaryOp
    """
    return astx.BinaryOp(
        "+",
        astx.LiteralString(lhs),
        astx.LiteralString(rhs),
    )


def _string_main(*nodes: astx.AST) -> astx.Module:
    """
    title: Build one integer main module for string ownership tests.
    parameters:
      nodes:
        type: astx.AST
        variadic: positional
    returns:
      type: astx.Module
    """
    module = astx.Module()
    body = astx.Block()
    for node in nodes:
        body.append(node)
    if not any(isinstance(node, astx.FunctionReturn) for node in nodes):
        body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype(
                "main",
                args=astx.Arguments(),
                return_type=astx.Int32(),
            ),
            body,
        )
    )
    return module


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_string_literal_utf8_with_print(
    builder_class: type[Builder],
) -> None:
    """
    title: Test UTF-8 string literal by printing to stdout.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    module = builder.module()

    expected = "Hello, World!"

    string_literal = astx.LiteralUTF8String(expected)

    decl_tmp = astx.VariableDeclaration(
        name="tmp", type_=astx.String(), value=string_literal
    )

    block = astx.Block()
    block.append(decl_tmp)
    block.append(PrintExpr(astx.Identifier("tmp")))
    block.append(astx.FunctionReturn(astx.LiteralInt32(0)))

    proto = astx.FunctionPrototype(
        name="main", args=astx.Arguments(), return_type=astx.Int32()
    )
    fn = astx.FunctionDef(prototype=proto, body=block)
    module.block.append(fn)

    check_result("build", builder, module, expected_output=expected)


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_string_literal_utf8_char_with_print(
    builder_class: type[Builder],
) -> None:
    """
    title: Test UTF-8 char literal by printing to stdout.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    module = builder.module()

    expected = "A"

    char_literal = astx.LiteralUTF8Char(expected)

    decl_tmp = astx.VariableDeclaration(
        name="tmp", type_=astx.String(), value=char_literal
    )

    block = astx.Block()
    block.append(decl_tmp)
    block.append(PrintExpr(astx.Identifier("tmp")))
    block.append(astx.FunctionReturn(astx.LiteralInt32(0)))

    proto = astx.FunctionPrototype(
        name="main", args=astx.Arguments(), return_type=astx.Int32()
    )
    fn = astx.FunctionDef(prototype=proto, body=block)
    module.block.append(fn)

    check_result("build", builder, module, expected_output=expected)


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_string_literal_generic_with_print(
    builder_class: type[Builder],
) -> None:
    """
    title: Test generic string literal by printing to stdout.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    module = builder.module()

    expected = "Generic String"

    string_literal = astx.LiteralString(expected)

    decl_tmp = astx.VariableDeclaration(
        name="tmp", type_=astx.String(), value=string_literal
    )

    block = astx.Block()
    block.append(decl_tmp)
    block.append(PrintExpr(astx.Identifier("tmp")))
    block.append(astx.FunctionReturn(astx.LiteralInt32(0)))

    proto = astx.FunctionPrototype(
        name="main", args=astx.Arguments(), return_type=astx.Int32()
    )
    fn = astx.FunctionDef(prototype=proto, body=block)
    module.block.append(fn)

    check_result("build", builder, module, expected_output=expected)


@pytest.mark.parametrize(
    "lhs_str, rhs_str, expected",
    [
        ("Hello, ", "World!", "Hello, World!"),
        ("", "Empty", "Empty"),
        ("123", "456", "123456"),
    ],
)
@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_string_concatenation_with_print(
    builder_class: type[Builder],
    lhs_str: str,
    rhs_str: str,
    expected: str,
) -> None:
    """
    title: Test string concatenation by printing result to stdout.
    parameters:
      builder_class:
        type: type[Builder]
      lhs_str:
        type: str
      rhs_str:
        type: str
      expected:
        type: str
    """
    builder = builder_class()
    module = builder.module()

    left = astx.LiteralUTF8Char(lhs_str)
    right = astx.LiteralUTF8Char(rhs_str)
    expr = astx.BinaryOp("+", left, right)

    decl_tmp = astx.VariableDeclaration(
        name="tmp", type_=astx.String(), value=expr
    )

    block = astx.Block()
    block.append(decl_tmp)
    block.append(PrintExpr(astx.Identifier("tmp")))
    block.append(astx.FunctionReturn(astx.LiteralInt32(0)))

    proto = astx.FunctionPrototype(
        name="main", args=astx.Arguments(), return_type=astx.Int32()
    )
    fn = astx.FunctionDef(prototype=proto, body=block)
    module.block.append(fn)

    check_result("build", builder, module, expected_output=expected)


@pytest.mark.parametrize(
    "lhs_str, op, rhs_str, expected_result",
    [
        ("hello", "==", "hello", True),
        ("hello", "==", "world", False),
        ("test", "!=", "different", True),
        ("", "==", "", True),
        ("", "!=", "nonempty", True),
    ],
)
@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_string_comparison_with_print(
    builder_class: type[Builder],
    lhs_str: str,
    op: str,
    rhs_str: str,
    expected_result: bool,
) -> None:
    """
    title: Test string comparison operations by printing result to stdout.
    parameters:
      builder_class:
        type: type[Builder]
      lhs_str:
        type: str
      op:
        type: str
      rhs_str:
        type: str
      expected_result:
        type: bool
    """
    builder = builder_class()
    module = builder.module()

    left = astx.LiteralUTF8Char(lhs_str)
    right = astx.LiteralUTF8Char(rhs_str)
    expr = astx.BinaryOp(op, left, right)

    decl_tmp = astx.VariableDeclaration(
        name="tmp", type_=astx.Boolean(), value=expr
    )

    block = astx.Block()
    block.append(decl_tmp)
    block.append(PrintExpr(astx.Identifier("tmp")))
    block.append(astx.FunctionReturn(astx.LiteralInt32(0)))

    proto = astx.FunctionPrototype(
        name="main", args=astx.Arguments(), return_type=astx.Int32()
    )
    fn = astx.FunctionDef(prototype=proto, body=block)
    module.block.append(fn)

    check_result(
        "build", builder, module, expected_output=str(int(expected_result))
    )


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_empty_string_with_print(
    builder_class: type[Builder],
) -> None:
    """
    title: Test empty string by printing to stdout.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    module = builder.module()

    expected = ""

    string_literal = astx.LiteralUTF8String(expected)

    decl_tmp = astx.VariableDeclaration(
        name="tmp", type_=astx.String(), value=string_literal
    )

    block = astx.Block()
    block.append(decl_tmp)
    block.append(PrintExpr(astx.Identifier("tmp")))
    block.append(astx.FunctionReturn(astx.LiteralInt32(0)))

    proto = astx.FunctionPrototype(
        name="main", args=astx.Arguments(), return_type=astx.Int32()
    )
    fn = astx.FunctionDef(prototype=proto, body=block)
    module.block.append(fn)

    result = build_and_run(builder, module)
    assert result.returncode == 0
    assert result.stdout == "\n"
    assert result.stderr == ""


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_string_with_special_characters_with_print(
    builder_class: type[Builder],
) -> None:
    """
    title: Test string with special characters by printing to stdout.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    module = builder.module()

    expected = 'Special: \\n\\t\\r"'

    string_literal = astx.LiteralUTF8String(expected)

    # Declare tmp: string = "Special: \\n\\t\\r\""
    decl_tmp = astx.VariableDeclaration(
        name="tmp", type_=astx.String(), value=string_literal
    )

    # Return block that prints string with special chars then returns 0
    block = astx.Block()
    block.append(decl_tmp)
    block.append(PrintExpr(astx.Identifier("tmp")))
    block.append(astx.FunctionReturn(astx.LiteralInt32(0)))

    proto = astx.FunctionPrototype(
        name="main", args=astx.Arguments(), return_type=astx.Int32()
    )
    fn = astx.FunctionDef(prototype=proto, body=block)
    module.block.append(fn)

    check_result("build", builder, module, expected_output=expected)


def test_utf8_char_lowering_correctness() -> None:
    """
    title: Verify LiteralUTF8Char correctly lowers to UTF-8 hex in IR.
    """

    builder = LLVMBuilder()
    module = builder.module()

    # 'é' is represented as \xc3\xa9 in UTF-8
    char_node = astx.LiteralUTF8Char("é")

    block = astx.Block()
    block.append(
        astx.VariableDeclaration(
            name="tmp", type_=astx.String(), value=char_node
        )
    )
    block.append(astx.FunctionReturn(astx.LiteralInt32(0)))

    proto = astx.FunctionPrototype(
        name="main", args=astx.Arguments(), return_type=astx.Int32()
    )
    module.block.append(astx.FunctionDef(prototype=proto, body=block))

    ir_output = builder.translate(module)

    # Verify the UTF-8 hex sequence exists in the generated IR constant
    assert "\\c3\\a9" in ir_output.lower()


def test_string_semantics_distinguish_static_owned_and_borrowed_storage() -> (
    None
):
    """
    title: String sidecars should record static, owned, move, and borrow roles.
    """
    literal = astx.LiteralString("static")
    concat = _string_concat("owned", " value")
    static_decl = astx.VariableDeclaration(
        "static_value",
        astx.String(),
        value=literal,
    )
    owned_decl = astx.VariableDeclaration(
        "owned_value",
        astx.String(),
        value=concat,
    )
    identifier = astx.Identifier("owned_value")
    module = _string_main(
        static_decl,
        owned_decl,
        PrintExpr(identifier),
    )

    analyze(module)

    literal_ownership = resource_ownership(literal)
    concat_ownership = resource_ownership(concat)
    static_ownership = resource_ownership(static_decl)
    owned_ownership = resource_ownership(owned_decl)
    identifier_ownership = resource_ownership(identifier)
    assert literal_ownership is not None
    assert literal_ownership.resource_kind is ResourceKind.STRING
    assert literal_ownership.kind is OwnershipKind.STATIC
    assert static_ownership is not None
    assert static_ownership.kind is OwnershipKind.STATIC
    assert concat_ownership is not None
    assert concat_ownership.kind is OwnershipKind.OWNED
    assert concat_ownership.transfer_kind is OwnershipTransferKind.MOVE
    assert owned_ownership is not None
    assert owned_ownership.kind is OwnershipKind.OWNED
    assert identifier_ownership is not None
    assert identifier_ownership.kind is OwnershipKind.BORROWED
    assert identifier_ownership.source_symbol_id is not None


def test_owned_string_local_is_released_after_use() -> None:
    """
    title: Owned string locals should be usable and freed on return.
    """
    module = _string_main(
        astx.VariableDeclaration(
            "message",
            astx.String(),
            value=_string_concat("hello", " world"),
        ),
        PrintExpr(astx.Identifier("message")),
    )

    ir_text = LLVMBuilder().translate(module)

    assert_executed_string_frees(module, 1)
    assert "ARX-RUNTIME-STRING-001" in ir_text
    assert_ir_parses(ir_text)
    check_result(
        "build",
        LLVMBuilder(),
        module,
        expected_output="hello world",
    )


def test_owned_string_assignment_releases_each_lifetime_generation() -> None:
    """
    title: >-
      Replacing owned strings should free old and final storage exactly once.
    """
    module = _string_main(
        astx.VariableDeclaration(
            "message",
            astx.String(),
            mutability=astx.MutabilityKind.mutable,
            value=_string_concat("first", " value"),
        ),
        astx.BinaryOp(
            "=",
            astx.Identifier("message"),
            _string_concat("second", " value"),
        ),
        PrintExpr(astx.Identifier("message")),
    )

    ir_text = LLVMBuilder().translate(module)

    assert_executed_string_frees(module, EXPECTED_STRING_REPLACEMENT_FREES)
    assert_ir_parses(ir_text)
    check_result(
        "build",
        LLVMBuilder(),
        module,
        expected_output="second value",
    )


def test_static_string_return_is_copied_and_released_by_caller() -> None:
    """
    title: Returning static text should copy it into caller-owned storage.
    """
    literal = astx.LiteralString("returned")
    make_message = astx.FunctionDef(
        astx.FunctionPrototype(
            "make_message",
            args=astx.Arguments(),
            return_type=astx.String(),
        ),
        astx.Block(),
    )
    make_message.body.append(astx.FunctionReturn(literal))
    call = astx.FunctionCall("make_message", [])
    result_decl = astx.VariableDeclaration(
        "result",
        astx.String(),
        value=call,
    )
    module = _string_main(
        result_decl,
        PrintExpr(astx.Identifier("result")),
    )
    module.block.insert(0, make_message)

    ir_text = LLVMBuilder().translate(module)

    literal_ownership = resource_ownership(literal)
    call_ownership = resource_ownership(call)
    assert literal_ownership is not None
    assert literal_ownership.transfer_kind is OwnershipTransferKind.COPY
    assert literal_ownership.escape_kind is OwnershipEscapeKind.RETURN
    assert call_ownership is not None
    assert call_ownership.kind is OwnershipKind.OWNED
    assert_executed_string_frees(module, 1)
    assert_ir_parses(ir_text)
    check_result(
        "build",
        LLVMBuilder(),
        module,
        expected_output="returned",
    )


def test_owned_string_return_moves_cleanup_to_caller() -> None:
    """
    title: Returning a heap string should move its cleanup to the caller.
    """
    owned_decl = astx.VariableDeclaration(
        "owned",
        astx.String(),
        value=_string_concat("moved", " value"),
    )
    returned_identifier = astx.Identifier("owned")
    make_message = astx.FunctionDef(
        astx.FunctionPrototype(
            "make_owned_message",
            args=astx.Arguments(),
            return_type=astx.String(),
        ),
        astx.Block(),
    )
    make_message.body.append(owned_decl)
    make_message.body.append(astx.FunctionReturn(returned_identifier))
    result_decl = astx.VariableDeclaration(
        "result",
        astx.String(),
        value=astx.FunctionCall("make_owned_message", []),
    )
    module = _string_main(
        result_decl,
        PrintExpr(astx.Identifier("result")),
    )
    module.block.insert(0, make_message)

    ir_text = LLVMBuilder().translate(module)

    returned_ownership = resource_ownership(returned_identifier)
    assert returned_ownership is not None
    assert returned_ownership.transfer_kind is OwnershipTransferKind.MOVE
    assert returned_ownership.escape_kind is OwnershipEscapeKind.RETURN
    assert_executed_string_frees(module, 1)
    assert_ir_parses(ir_text)
    check_result(
        "build",
        LLVMBuilder(),
        module,
        expected_output="moved value",
    )


def test_printed_string_temporary_is_released_after_consumption() -> None:
    """
    title: Consumed string temporaries should be freed after their statement.
    """
    module = _string_main(PrintExpr(_string_concat("temporary", " text")))

    ir_text = LLVMBuilder().translate(module)

    assert_executed_string_frees(module, 1)
    source_main = ir_text[ir_text.index('define i32 @"irx.entry.main"') :]
    puts_position = source_main.index('call i32 @"puts"')
    free_position = source_main.index('call void @"free"')
    assert puts_position < free_position
    assert_ir_parses(ir_text)
    check_result(
        "build",
        LLVMBuilder(),
        module,
        expected_output="temporary text",
    )


@pytest.mark.parametrize(
    ("initializer", "replacement"),
    [
        (astx.LiteralString("static"), _string_concat("owned", " value")),
        (_string_concat("owned", " value"), astx.LiteralString("static")),
    ],
)
def test_string_assignment_rejects_storage_class_changes(
    initializer: astx.Expr,
    replacement: astx.DataType,
) -> None:
    """
    title: Assignment should not mix static and heap string lifetimes.
    parameters:
      initializer:
        type: astx.Expr
      replacement:
        type: astx.DataType
    """
    module = _string_main(
        astx.VariableDeclaration(
            "message",
            astx.String(),
            mutability=astx.MutabilityKind.mutable,
            value=initializer,
        ),
        astx.BinaryOp(
            "=",
            astx.Identifier("message"),
            replacement,
        ),
    )

    with pytest.raises(
        SemanticError,
        match="must preserve its static or owned storage class",
    ):
        analyze(module)


def test_borrowed_string_parameter_cannot_escape_as_owned_result() -> None:
    """
    title: Borrowed string parameters should not escape through owned returns.
    """
    echo = astx.FunctionDef(
        astx.FunctionPrototype(
            "echo",
            args=astx.Arguments(astx.Argument("message", astx.String())),
            return_type=astx.String(),
        ),
        astx.Block(),
    )
    echo.body.append(astx.FunctionReturn(astx.Identifier("message")))
    module = astx.Module()
    module.block.append(echo)

    with pytest.raises(
        SemanticError,
        match="cannot return a borrowed string as an owned result",
    ):
        analyze(module)


def test_borrowed_string_parameter_cannot_initialize_local_alias() -> None:
    """
    title: Borrowed string aliases should fail without a copy operation.
    """
    copy = astx.FunctionDef(
        astx.FunctionPrototype(
            "copy",
            args=astx.Arguments(astx.Argument("message", astx.String())),
            return_type=astx.Int32(),
        ),
        astx.Block(),
    )
    copy.body.append(
        astx.VariableDeclaration(
            "alias",
            astx.String(),
            value=astx.Identifier("message"),
        )
    )
    copy.body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module = astx.Module()
    module.block.append(copy)

    with pytest.raises(
        SemanticError,
        match="would alias borrowed storage",
    ):
        analyze(module)


def test_external_string_return_requires_explicit_ownership_abi() -> None:
    """
    title: External string returns should fail without an ownership contract.
    """
    external = astx.FunctionPrototype(
        "external_message",
        args=astx.Arguments(),
        return_type=astx.String(),
    )
    module = _string_main(
        PrintExpr(astx.FunctionCall("external_message", [])),
    )
    module.block.insert(0, external)

    with pytest.raises(
        SemanticError,
        match="external string-returning calls require an explicit ownership",
    ):
        analyze(module)
