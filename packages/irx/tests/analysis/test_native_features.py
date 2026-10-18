"""
title: Host-supplied native capabilities and compilation isolation.
"""

from pathlib import Path

import astx
import pytest

from irx.analysis import ParsedModule, SemanticError, analyze_modules
from irx.builder import Builder
from irx.builder.runtime.registry import get_default_runtime_feature_registry
from irx.native import NativeArtifact, NativeBinding, NativeFeature
from llvmlite import binding as llvm
from typeguard import TypeCheckError


def unavailable(
    requesting: str,
    node: astx.ImportStmt | astx.ImportFromStmt,
    specifier: str,
) -> ParsedModule:
    """
    title: Reject unexpected graph expansion in single-module host fixtures.
    parameters:
      requesting:
        type: str
      node:
        type: astx.ImportStmt | astx.ImportFromStmt
      specifier:
        type: str
    returns:
      type: ParsedModule
    """
    raise LookupError(
        f"unexpected import {requesting}: {specifier}: {type(node)}"
    )


def native_module(name: str = "package:test:backend") -> ParsedModule:
    """
    title: Supply native metadata independently of Arx syntax or discovery.
    parameters:
      name:
        type: str
    returns:
      type: ParsedModule
    """
    prototype = astx.FunctionPrototype(
        "native_value", astx.Arguments(), astx.Int32()
    )
    prototype.is_extern = True
    module = astx.Module()
    module.name = "main"
    module.block.append(prototype)
    body = astx.Block()
    body.append(astx.FunctionReturn(astx.FunctionCall("native_value", [])))
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
            body,
        )
    )
    return ParsedModule(
        "main",
        module,
        native_features=(NativeFeature(name),),
        native_bindings=(NativeBinding(prototype, (name,)),),
    )


def test_native_capabilities_reach_lowering_without_global_mutation() -> None:
    """
    title: Semantic identities activate only the current compilation registry.
    """
    root = native_module()
    session = analyze_modules(root, unavailable)
    assert tuple(session.native_features) == ("package:test:backend",)
    builder = Builder()
    text = builder.translate_modules(root, unavailable)
    llvm.parse_assembly(text).verify()
    assert builder.translator.runtime_features.is_active(
        "package:test:backend"
    )
    assert (
        "package:test:backend"
        not in get_default_runtime_feature_registry().names()
    )
    builder.translate_modules(
        native_module("package:other:backend"), unavailable
    )
    assert not builder.translator.runtime_features.is_active(
        "package:test:backend"
    )


def test_native_binding_does_not_mutate_prototype() -> None:
    """
    title: Reanalysis binds host metadata without rewriting source prototypes.
    """
    root = native_module()
    for _ in range(2):
        analyze_modules(root, unavailable)
    assert not hasattr(root.native_bindings[0].declaration, "runtime_features")


def test_native_features_cannot_replace_builtins() -> None:
    """
    title: External capabilities cannot override builtin native definitions.
    """
    with pytest.raises(SemanticError, match="conflicts with a builtin"):
        analyze_modules(native_module("libc"), unavailable)


def test_native_bindings_require_available_features() -> None:
    """
    title: Unknown features fail semantically before lowering.
    """
    original = native_module()
    root = ParsedModule(
        "main", original.ast, native_bindings=original.native_bindings
    )
    with pytest.raises(SemanticError, match="unknown runtime feature"):
        analyze_modules(root, unavailable)


def test_native_registration_requires_declaration_identity() -> None:
    """
    title: Matching textual names do not authorize another AST declaration.
    """
    root = native_module()
    with pytest.raises(ValueError, match="belong"):
        ParsedModule(
            "other", astx.Module(), native_bindings=root.native_bindings
        )
    root.native_bindings[0].declaration.is_extern = False
    with pytest.raises(ValueError, match="extern"):
        ParsedModule("main", root.ast, native_bindings=root.native_bindings)


def test_native_records_validate_nonfirst_collection_items() -> None:
    """
    title: Runtime checks reject invalid capabilities and collection items.
    """
    with pytest.raises(TypeCheckError):
        NativeFeature("test", (NativeArtifact("c_source", Path("a.c")), 3))  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        NativeArtifact("c_source", Path("a.c"), (Path("include"), "bad"))  # type: ignore[arg-type]
    root = native_module()
    with pytest.raises(TypeCheckError):
        NativeBinding(root.native_bindings[0].declaration, ("test", 2))  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        ParsedModule(
            "main", root.ast, native_features=(NativeFeature("test"), 2)
        )  # type: ignore[arg-type]


def test_native_binding_rejects_duplicate_declarations() -> None:
    """
    title: Native registrations cannot contain contradictory duplicate entries.
    """
    root = native_module()
    with pytest.raises(ValueError, match="duplicate native extern"):
        ParsedModule(
            "main",
            root.ast,
            native_bindings=(*root.native_bindings, *root.native_bindings),
        )


def test_native_conflicts_across_modules_fail_semantically() -> None:
    """
    title: >-
      Extern C symbol requirements cannot conflict across module boundaries.
    """
    root = native_module()
    other = native_module("package:other:backend")
    other = ParsedModule(
        "other",
        other.ast,
        native_features=other.native_features,
        native_bindings=other.native_bindings,
    )
    root.ast.block.append(astx.ImportStmt([astx.AliasExpr("other")]))

    def resolver(
        requesting: str,
        node: astx.ImportStmt | astx.ImportFromStmt,
        specifier: str,
    ) -> ParsedModule:
        """
        title: Return a second module with a contradictory extern contract.
        parameters:
          requesting:
            type: str
          node:
            type: astx.ImportStmt | astx.ImportFromStmt
          specifier:
            type: str
        returns:
          type: ParsedModule
        """
        if specifier == "other":
            return other
        return unavailable(requesting, node, specifier)

    with pytest.raises(SemanticError, match="Extern symbol"):
        analyze_modules(root, resolver)


def test_extern_rejects_known_nul_literal() -> None:
    """
    title: Native C strings cannot silently truncate known embedded NUL text.
    """
    prototype = astx.FunctionPrototype(
        "consume",
        astx.Arguments(astx.Argument("label", astx.String())),
        astx.Int32(),
    )
    prototype.is_extern = True
    module = astx.Module()
    module.block.append(prototype)
    body = astx.Block()
    body.append(
        astx.FunctionReturn(
            astx.FunctionCall("consume", [astx.LiteralString("bad\x00suffix")])
        )
    )
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
            body,
        )
    )
    with pytest.raises(SemanticError, match="cannot contain NUL"):
        analyze_modules(ParsedModule("main", module), unavailable)


def test_native_artifact_options_cannot_conflict() -> None:
    """
    title: >-
      Duplicate source paths cannot silently discard distinct build inputs.
    """
    root = native_module()
    feature = NativeFeature(
        "package:test:backend",
        (
            NativeArtifact("c_source", Path("input.c")),
            NativeArtifact("c_source", Path("input.c"), (Path("headers"),)),
        ),
    )
    root = ParsedModule(
        "main",
        root.ast,
        native_features=(feature,),
        native_bindings=root.native_bindings,
    )
    with pytest.raises(SemanticError, match="conflicting native artifact"):
        analyze_modules(root, unavailable)


def test_native_record_names_and_duplicates_are_rejected() -> None:
    """
    title: Empty names and duplicate capabilities are invalid host inputs.
    """
    root = native_module()
    with pytest.raises(ValueError):
        NativeFeature(" ")
    with pytest.raises(ValueError):
        NativeBinding(root.native_bindings[0].declaration, ("x", "x"))
    with pytest.raises(ValueError):
        ParsedModule(
            "main",
            root.ast,
            native_features=(*root.native_features, *root.native_features),
        )
