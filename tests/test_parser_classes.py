"""
title: Tests for annotation-based class parsing.
"""

import astx
import pytest

from arx.class_ast import (
    ClassDecl,
    FieldDecl,
    MemberAccessExpr,
    MethodDecl,
    ModifierKind,
)
from arx.exceptions import ParserException
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser


def _parse_module(code: str) -> astx.Module:
    """
    title: Parse one snippet into an AST module.
    parameters:
      code:
        type: str
    returns:
      type: astx.Module
    """
    ArxIO.string_to_buffer(code)
    return Parser().parse(Lexer().lex())


def test_parse_class_with_member_annotations_and_defaults() -> None:
    """
    title: Parse class members with explicit modifiers and defaulted metadata.
    """
    tree = _parse_module(
        "class Counter(BaseCounter, Audited):\n"
        "  @[public, static, constant]\n"
        "  version: int32 = 1\n"
        "\n"
        "  value: int32 = 0\n"
        "\n"
        "  @[protected, override]\n"
        "  fn process(self, x: int32) -> int32:\n"
        "    return self.value\n"
    )

    cls = tree.nodes[0]
    assert isinstance(cls, ClassDecl)
    assert cls.name == "Counter"
    assert cls.bases == ("BaseCounter", "Audited")
    assert [type(member) for member in cls.body] == [
        FieldDecl,
        FieldDecl,
        MethodDecl,
    ]

    version = cls.body[0]
    assert isinstance(version, FieldDecl)
    assert version.modifiers is not None
    assert version.modifiers.kinds == (
        ModifierKind.PUBLIC,
        ModifierKind.STATIC,
        ModifierKind.CONSTANT,
    )
    assert isinstance(version.initializer, astx.LiteralInt32)

    value = cls.body[1]
    assert isinstance(value, FieldDecl)
    assert value.modifiers is None
    assert value.resolved_visibility() is ModifierKind.PUBLIC
    assert value.resolved_mutability() is ModifierKind.MUTABLE

    method = cls.body[2]
    assert isinstance(method, MethodDecl)
    assert method.modifiers is not None
    assert method.modifiers.kinds == (
        ModifierKind.PROTECTED,
        ModifierKind.OVERRIDE,
    )
    assert method.params[0].name == "self"
    assert method.params[0].is_self is True
    assert method.params[0].type_ is None
    assert method.params[1].name == "x"
    assert isinstance(method.params[1].type_, astx.Int32)
    assert isinstance(method.return_type, astx.Int32)
    assert method.body is not None
    assert isinstance(method.body.nodes[0], astx.FunctionReturn)
    assert isinstance(method.body.nodes[0].value, MemberAccessExpr)
    assert method.body.nodes[0].value.member_name == "value"


def test_parse_class_level_annotations_and_abstract_method_decl() -> None:
    """
    title: Parse optional class annotations and body-less abstract methods.
    """
    tree = _parse_module(
        "@[public, abstract]\n"
        "class Shape:\n"
        "  @[public, abstract]\n"
        "  fn area(self) -> float64\n"
    )

    cls = tree.nodes[0]
    assert isinstance(cls, ClassDecl)
    assert cls.annotations is not None
    assert cls.annotations.kinds == (
        ModifierKind.PUBLIC,
        ModifierKind.ABSTRACT,
    )
    method = cls.body[0]
    assert isinstance(method, MethodDecl)
    assert method.body is None
    assert method.modifiers is not None
    assert method.modifiers.kinds == (
        ModifierKind.PUBLIC,
        ModifierKind.ABSTRACT,
    )
    assert method.params[0].is_self is True
    assert isinstance(method.return_type, astx.Float64)


@pytest.mark.parametrize(
    ("code", "message"),
    [
        (
            "@[ ]\nclass Bad:\n  value: int32 = 0\n",
            "empty annotation is not allowed",
        ),
        (
            "class Bad:\n  @[public, public]\n  value: int32 = 0\n",
            "duplicate modifier 'public'",
        ),
        (
            "class Bad:\n  @[public, private]\n  value: int32 = 0\n",
            "conflicting visibility modifiers",
        ),
        (
            "class Bad:\n  @[constant, mutable]\n  value: int32 = 0\n",
            "conflicting mutability modifiers",
        ),
        (
            "class Bad:\n  @[override]\n  value: int32 = 0\n",
            "field cannot use 'override'",
        ),
        (
            "class Bad:\n  @[mystery]\n  value: int32 = 0\n",
            "unknown modifier 'mystery'",
        ),
        (
            "class Bad:\n  @[public]\n",
            "annotation must be followed by a declaration",
        ),
        (
            "class Bad:\n  @[public] value: int32 = 0\n",
            "annotation must appear on its own line",
        ),
        (
            "class Bad:\n  fn area(self) -> float64\n",
            "method declaration without a body requires "
            "'abstract' or 'extern'",
        ),
    ],
)
def test_parse_class_modifier_errors(code: str, message: str) -> None:
    """
    title: Reject invalid annotation and class-member modifier combinations.
    parameters:
      code:
        type: str
      message:
        type: str
    """
    with pytest.raises(ParserException, match=message):
        _parse_module(code)
