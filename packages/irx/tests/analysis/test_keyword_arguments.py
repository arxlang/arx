"""
title: Bound call plans and independent ASTx host keyword lowering.
"""

from dataclasses import replace
from typing import cast

import astx
import pytest

from irx.analysis import analyze
from irx.analysis.resolved_nodes import (
    ResolvedCallArguments,
    ResolvedDefaultArgument,
    SemanticInfo,
)
from irx.builder import Builder
from irx.diagnostics import LoweringError, SemanticError
from llvmlite import binding as llvm
from typeguard import TypeCheckError

from ..conftest import make_module


def block(value: astx.DataType) -> astx.Block:
    """
    title: Return one expression from a function body.
    parameters:
      value:
        type: astx.DataType
    returns:
      type: astx.Block
    """
    result = astx.Block()
    result.append(astx.FunctionReturn(value))
    return result


def main(value: astx.DataType) -> astx.FunctionDef:
    """
    title: Wrap a test call in an ordinary main function.
    parameters:
      value:
        type: astx.DataType
    returns:
      type: astx.FunctionDef
    """
    return astx.FunctionDef(
        astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
        block(value),
    )


@pytest.mark.parametrize("kind", ["instance", "static", "base"])
def test_astx_host_method_keywords(kind: str) -> None:
    """
    title: Every method representation lowers named arguments without Arx.
    parameters:
      kind:
        type: str
    """
    prototype = astx.FunctionPrototype(
        "combine",
        astx.Arguments(
            astx.Argument("a", astx.Int32()),
            astx.Argument("b", astx.Int32(), default=astx.LiteralInt32(4)),
        ),
        astx.Int32(),
    )
    prototype.is_static = kind == "static"
    method = astx.FunctionDef(
        prototype,
        block(astx.BinaryOp("+", astx.Identifier("a"), astx.Identifier("b"))),
    )
    base = astx.ClassDefStmt("Base", methods=[method])
    derived = astx.ClassDefStmt("Derived", bases=[astx.ClassType("Base")])
    keywords = (
        astx.KeywordArgument("b", astx.LiteralInt32(9)),
        astx.KeywordArgument("a", astx.LiteralInt32(2)),
    )
    call: astx.DataType
    if kind == "base":
        call = astx.BaseMethodCall(
            astx.ClassConstruct("Derived"),
            "Base",
            "combine",
            [],
            keywords=keywords,
        )
    elif kind == "static":
        call = astx.StaticMethodCall("Base", "combine", [], keywords=keywords)
    else:
        call = astx.MethodCall(
            astx.ClassConstruct("Derived"), "combine", [], keywords=keywords
        )
    module = make_module("main", base, derived, main(call))
    text = Builder().translate(module)
    llvm.parse_assembly(text).verify()
    info = cast(SemanticInfo, call.semantic)
    assert info.resolved_call is not None
    assert info.resolved_call.arguments is not None
    assert info.resolved_call.arguments.indices == (1, 0)


@pytest.mark.parametrize("keyword", [True, False])
def test_extern_fixed_keywords_and_variadic_promotions(keyword: bool) -> None:
    """
    title: >-
      Fixed names bind normally and positional tail promotions are retained.
    parameters:
      keyword:
        type: bool
    """
    prototype = astx.FunctionPrototype(
        "printf",
        astx.Arguments(astx.Argument("format", astx.String())),
        astx.Int32(),
    )
    prototype.is_extern = True
    prototype.is_variadic = True
    prototype.calling_convention = "c"
    call = astx.FunctionCall(
        "printf",
        [] if keyword else [astx.LiteralString("%d"), astx.LiteralInt8(7)],
        keywords=(astx.KeywordArgument("format", astx.LiteralString("hello")),)
        if keyword
        else (),
    )
    text = Builder().translate(make_module("main", prototype, main(call)))
    llvm.parse_assembly(text).verify()
    info = cast(SemanticInfo, call.semantic)
    assert info.resolved_call is not None
    assert info.resolved_call.arguments is not None
    assert info.resolved_call.arguments.indices == (
        (0,) if keyword else (0, 1)
    )
    if not keyword:
        assert isinstance(
            info.resolved_call.resolved_argument_types[1], astx.Int32
        )


def test_keyword_variadic_tail_name_is_not_a_parameter() -> None:
    """
    title: Extern variadic operands cannot be introduced as keyword entries.
    """
    prototype = astx.FunctionPrototype(
        "printf",
        astx.Arguments(astx.Argument("format", astx.String())),
        astx.Int32(),
    )
    prototype.is_extern = True
    prototype.is_variadic = True
    prototype.calling_convention = "c"
    call = astx.FunctionCall(
        "printf",
        [astx.LiteralString("hello")],
        keywords=(astx.KeywordArgument("tail", astx.LiteralInt32(1)),),
    )
    with pytest.raises(SemanticError, match="unknown argument 'tail'"):
        analyze(make_module("main", prototype, main(call)))


def test_bound_metadata_runtime_item_validation() -> None:
    """
    title: >-
      Metadata rejects invalid types and non-first invalid collection items.
    """
    with pytest.raises(TypeCheckError):
        ResolvedCallArguments(
            (astx.LiteralInt32(1), 2), (0, 1), (), (), None, 2
        )  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        ResolvedDefaultArgument(0, "invalid", astx.Int32())  # type: ignore[arg-type]


def test_bound_metadata_rejects_dropped_operands() -> None:
    """
    title: Inconsistent metadata cannot silently discard evaluated operands.
    """
    with pytest.raises(ValueError, match="every slot exactly once"):
        ResolvedCallArguments((astx.LiteralInt32(1),), (), (), (), None, 0)


def test_raw_file_method_keywords_remain_explicitly_unsupported() -> None:
    """
    title: Broad method syntax never silently discards raw-handle keywords.
    """
    body = astx.Block()
    body.append(
        astx.VariableDeclaration(
            "stream",
            astx.FileType(),
            value=astx.FunctionCall("open", [astx.LiteralString("unused")]),
        )
    )
    body.append(
        astx.MethodCall(
            astx.Identifier("stream"),
            "read",
            [],
            keywords=(astx.KeywordArgument("ignored", astx.LiteralInt32(1)),),
        )
    )
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    function = astx.FunctionDef(
        astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()), body
    )
    with pytest.raises(
        SemanticError, match="raw file methods do not accept keywords"
    ):
        analyze(make_module("main", function))


def test_call_lowering_requires_bound_arguments() -> None:
    """
    title: Missing semantic binding metadata fails before operand lowering.
    """
    callee = astx.FunctionDef(
        astx.FunctionPrototype("f", astx.Arguments(), astx.Int32()),
        block(astx.LiteralInt32(1)),
    )
    call = astx.FunctionCall("f", [])
    analyze(make_module("main", callee, main(call)))
    resolution = cast(SemanticInfo, call.semantic).resolved_call
    assert resolution is not None
    with pytest.raises(LoweringError, match="arguments"):
        Builder().translator.lower_bound_call_arguments(
            replace(resolution, arguments=None)
        )
