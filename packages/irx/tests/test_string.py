"""
title: Tests for string operations.
"""

import astx
import pytest

from irx.analysis import (
    OwnershipEscapeKind,
    OwnershipKind,
    OwnershipTransferKind,
    ResourceKind,
    SemanticError,
    analyze,
    resource_ownership,
)
from irx.builder import Builder as LLVMBuilder
from irx.builder.base import Builder
from irx.system import PrintExpr

from .conftest import assert_ir_parses, check_result

EXPECTED_STRING_REPLACEMENT_FREES = 2


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
    block.append(PrintExpr(astx.LiteralUTF8String(expected)))
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
    block.append(PrintExpr(astx.LiteralUTF8String(expected)))
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
    block.append(PrintExpr(astx.LiteralUTF8String(expected)))
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
    block.append(PrintExpr(astx.LiteralUTF8String(expected)))
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
    block.append(PrintExpr(astx.LiteralUTF8String(str(expected_result))))
    block.append(astx.FunctionReturn(astx.LiteralInt32(0)))

    proto = astx.FunctionPrototype(
        name="main", args=astx.Arguments(), return_type=astx.Int32()
    )
    fn = astx.FunctionDef(prototype=proto, body=block)
    module.block.append(fn)

    check_result(
        "build", builder, module, expected_output=str(expected_result)
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
    block.append(PrintExpr(astx.LiteralUTF8String("EMPTY")))
    block.append(astx.FunctionReturn(astx.LiteralInt32(0)))

    proto = astx.FunctionPrototype(
        name="main", args=astx.Arguments(), return_type=astx.Int32()
    )
    fn = astx.FunctionDef(prototype=proto, body=block)
    module.block.append(fn)

    check_result("build", builder, module, expected_output="EMPTY")


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
    block.append(PrintExpr(astx.LiteralUTF8String(expected)))
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

    assert ir_text.count('call void @"free"') == 1
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

    assert (
        ir_text.count('call void @"free"') == EXPECTED_STRING_REPLACEMENT_FREES
    )
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
    assert ir_text.count('call void @"free"') == 1
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
    assert ir_text.count('call void @"free"') == 1
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

    assert ir_text.count('call void @"free"') == 1
    puts_position = ir_text.index('call i32 @"puts"')
    free_position = ir_text.index('call void @"free"')
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
    initializer: astx.AST,
    replacement: astx.AST,
) -> None:
    """
    title: Assignment should not mix static and heap string lifetimes.
    parameters:
      initializer:
        type: astx.AST
      replacement:
        type: astx.AST
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
