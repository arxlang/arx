"""
title: Host-registered File capabilities without frontend source discovery.
"""

from typing import cast

import astx
import pytest

from irx.analysis import ParsedModule, SemanticError, analyze_modules
from irx.analysis.resolved_nodes import (
    ResolvedNativeFileInitialization,
    ResourceKind,
    SemanticInfo,
)
from irx.builder import Builder
from llvmlite import binding as llvm
from typeguard import TypeCheckError

from ..conftest import StaticImportResolver, make_module


def file_declaration() -> astx.ClassDefStmt:
    """
    title: Supply an ASTx native class independently of Arx or its filesystem.
    returns:
      type: astx.ClassDefStmt
    """
    methods = []
    for name in ("read", "write", "flush", "close"):
        args = astx.Arguments()
        body = astx.Block()
        return_type: astx.DataType = astx.NoneType()
        native_args: list[astx.DataType] = []
        if name == "write":
            args = astx.Arguments(astx.Argument("text", astx.String()))
            return_type = astx.Int64()
            native_args = [astx.Identifier("text")]
        elif name == "read":
            return_type = astx.String()
        operation = astx.MethodCall(
            astx.FieldAccess(astx.Identifier("self"), "storage"),
            name,
            native_args,
        )
        if isinstance(return_type, astx.NoneType):
            body.append(operation)
            body.append(astx.FunctionReturn(astx.LiteralNone()))
        else:
            body.append(astx.FunctionReturn(operation))
        methods.append(
            astx.FunctionDef(
                astx.FunctionPrototype(name, args, return_type), body
            )
        )
    return astx.ClassDefStmt(
        "NativeStream",
        attributes=[
            astx.VariableDeclaration(
                "storage",
                astx.FileType(),
                visibility=astx.VisibilityKind.private,
                mutability=astx.MutabilityKind.mutable,
            )
        ],
        methods=methods,
    )


@pytest.mark.parametrize("factory", ["open", "Factory"])
def test_native_class_requires_explicit_host_registration(
    factory: str,
) -> None:
    """
    title: A host capability, not the class/module spelling, selects native IO.
    parameters:
      factory:
        type: str
    """
    declaration = file_declaration()
    builtin = ParsedModule(
        "host.streams",
        make_module("host.streams", declaration),
        native_file_class=declaration,
    )
    call = astx.FunctionCall(factory, [astx.LiteralString("x")])
    body = astx.Block()
    body.append(call)
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    root = ParsedModule(
        "main",
        make_module(
            "main",
            astx.ImportFromStmt(
                [astx.AliasExpr("NativeStream", asname="Factory")],
                module="host.streams",
            ),
            astx.FunctionDef(
                astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
                body,
            ),
        ),
    )
    analyze_modules(root, StaticImportResolver({"host.streams": builtin}))
    info = cast(SemanticInfo, call.semantic)
    assert info.resolved_class_construction is not None
    assert info.resolved_class_construction.native_file is not None
    assert info.resolved_class_construction.class_.name == "NativeStream"
    assert info.resource_ownership is not None
    assert info.resource_ownership.resource_kind is ResourceKind.CLASS
    builder = Builder()
    result = builder.translate_modules(
        root, StaticImportResolver({"host.streams": builtin})
    )
    llvm.parse_assembly(result).verify()
    assert "irx_class_create" in result
    assert "irx_file_open" in result
    assert "irx_file_release" in result


def test_invalid_registration_inputs() -> None:
    """
    title: Host capabilities validate types and membership, not origin strings.
    """
    module = make_module("host")
    with pytest.raises(TypeCheckError):
        ParsedModule("host", module, native_file_class=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="belong to its module"):
        ParsedModule("host", module, native_file_class=file_declaration())


@pytest.mark.parametrize("invalid", ["field", "visibility", "return_type"])
def test_invalid_native_abi_is_rejected(invalid: str) -> None:
    """
    title: A malformed native registration fails semantically before lowering.
    parameters:
      invalid:
        type: str
    """
    declaration = file_declaration()
    if invalid == "field":
        declaration.attributes[0].type_ = astx.Int32()
    elif invalid == "visibility":
        declaration.attributes[0].visibility = astx.VisibilityKind.public
    else:
        declaration.methods[0].prototype.return_type = astx.Int32()
    root = ParsedModule(
        "host",
        make_module("host", declaration),
        native_file_class=declaration,
    )
    with pytest.raises(SemanticError, match="native File class contract"):
        analyze_modules(root, StaticImportResolver({}))


def test_unregistered_origin_does_not_grant_privilege() -> None:
    """
    title: A module name and packaged-looking origin cannot initialize handles.
    """
    declaration = file_declaration()
    root = ParsedModule(
        "builtins.files",
        make_module("builtins.files", declaration),
        origin="arx:builtins/files.x",
    )
    with pytest.raises(SemanticError, match="file field"):
        analyze_modules(root, StaticImportResolver({}))


def test_initializer_descriptor_checks_runtime_types() -> None:
    """
    title: Invalid host initialization metadata fails at its typed boundary.
    """
    with pytest.raises(TypeCheckError):
        ResolvedNativeFileInitialization(1, None)  # type: ignore[arg-type]


def test_duplicate_native_classes_are_rejected() -> None:
    """
    title: A compilation cannot select two competing native File capabilities.
    """
    first = file_declaration()
    second = file_declaration()
    root = ParsedModule(
        "first",
        make_module("first", first, astx.ImportFromStmt([], module="second")),
        native_file_class=first,
    )
    dependency = ParsedModule(
        "second", make_module("second", second), native_file_class=second
    )
    with pytest.raises(SemanticError, match="only one native File class"):
        analyze_modules(root, StaticImportResolver({"second": dependency}))
