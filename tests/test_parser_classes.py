"""
title: Tests for annotation-based class parsing.
"""

import pytest

from arx.exceptions import ParserException
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser
from irx import astx


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
    title: Parse class members onto IRx/ASTx class nodes.
    """
    tree = _parse_module(
        "class Counter(BaseCounter, Audited):\n"
        "  @[public, static, constant]\n"
        "  version: int32 = 1\n"
        "\n"
        "  value: int32 = 0\n"
        "\n"
        "  @[protected]\n"
        "  fn process(self, x: int32) -> int32:\n"
        "    return self.value\n"
    )

    cls = tree.nodes[0]
    assert isinstance(cls, astx.ClassDefStmt)
    assert cls.name == "Counter"
    assert [base.name for base in cls.bases.nodes] == [
        "BaseCounter",
        "Audited",
    ]
    assert [field.name for field in cls.attributes.nodes] == [
        "version",
        "value",
    ]
    assert [method.name for method in cls.methods.nodes] == ["process"]

    version = cls.attributes.nodes[0]
    assert version.visibility is astx.VisibilityKind.public
    assert version.mutability is astx.MutabilityKind.constant
    assert (
        getattr(version, "explicit_visibility") is astx.VisibilityKind.public
    )
    assert (
        getattr(version, "explicit_mutability") is astx.MutabilityKind.constant
    )
    assert getattr(version, "is_static", False) is True
    assert isinstance(version.value, astx.LiteralInt32)

    value = cls.attributes.nodes[1]
    assert value.visibility is astx.VisibilityKind.public
    assert value.mutability is astx.MutabilityKind.mutable
    assert not hasattr(value, "explicit_visibility")
    assert not hasattr(value, "explicit_mutability")
    assert not getattr(value, "is_static", False)
    assert isinstance(value.value, astx.LiteralInt32)

    method = cls.methods.nodes[0]
    assert isinstance(method, astx.FunctionDef)
    assert method.prototype.visibility is astx.VisibilityKind.protected
    assert getattr(method.prototype, "explicit_visibility") is (
        astx.VisibilityKind.protected
    )
    assert len(method.prototype.args.nodes) == 1
    assert method.prototype.args.nodes[0].name == "x"
    assert isinstance(method.prototype.args.nodes[0].type_, astx.Int32)
    assert isinstance(method.prototype.return_type, astx.Int32)
    assert isinstance(method.body.nodes[0], astx.FunctionReturn)
    assert isinstance(method.body.nodes[0].value, astx.FieldAccess)
    assert isinstance(method.body.nodes[0].value.value, astx.Identifier)
    assert method.body.nodes[0].value.value.name == "self"
    assert method.body.nodes[0].value.field_name == "value"


def test_parse_class_annotations_and_abstract_method_metadata() -> None:
    """
    title: Parse class-level metadata onto direct IRx/ASTx nodes.
    """
    tree = _parse_module(
        "@[public, abstract]\n"
        "class Shape:\n"
        "  @[public, abstract]\n"
        "  fn area(self) -> float64\n"
    )

    cls = tree.nodes[0]
    assert isinstance(cls, astx.ClassDefStmt)
    assert cls.visibility is astx.VisibilityKind.public
    assert getattr(cls, "explicit_visibility") is astx.VisibilityKind.public
    assert getattr(cls, "is_abstract", False) is True

    method = cls.methods.nodes[0]
    assert isinstance(method, astx.FunctionDef)
    assert method.prototype.visibility is astx.VisibilityKind.public
    assert getattr(method.prototype, "explicit_visibility") is (
        astx.VisibilityKind.public
    )
    assert getattr(method.prototype, "is_abstract", False) is True
    assert method.prototype.args.nodes == []
    assert isinstance(method.prototype.return_type, astx.Float64)
    assert method.body.nodes == []


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
            "class Bad:\n  @[abstract]\n  value: int32 = 0\n",
            "field cannot use 'abstract'",
        ),
        (
            "class Bad:\n  @[override]\n  value: int32 = 0\n",
            "unknown modifier 'override'",
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
        (
            "class Bad:\n"
            "  @[static]\n"
            "  fn helper(self) -> int32:\n"
            "    return 1\n",
            "static method cannot declare implicit receiver 'self'",
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
