"""
title: Reserved class protocols and centralized lifecycle hook contracts.
"""

from typing import cast

import astx
import pytest

from irx.analysis import SemanticError, analyze, analyze_modules
from irx.analysis.class_lifecycle import (
    CLASS_HOOKS,
    LIFECYCLE_HOOKS,
    ClassHookSpec,
)
from irx.analysis.resolved_nodes import SemanticInfo
from typeguard import TypeCheckError

from ..conftest import StaticImportResolver, make_module, make_parsed_module


def hook_method(name: str) -> astx.FunctionDef:
    """
    title: Build a void instance method with no explicit parameters.
    parameters:
      name:
        type: str
    returns:
      type: astx.FunctionDef
    """
    body = astx.Block()
    body.append(astx.FunctionReturn(astx.LiteralNone()))
    return astx.FunctionDef(
        astx.FunctionPrototype(name, astx.Arguments(), astx.NoneType()), body
    )


def test_hook_registry_and_phase_metadata() -> None:
    """
    title: Only documented hooks participate in nondispatchable phases.
    """
    assert set(CLASS_HOOKS) == {"__init__", "__del__", "__enter__", "__exit__"}
    assert set(LIFECYCLE_HOOKS) == {"__init__", "__del__"}
    initializer = hook_method("__init__")
    finalizer = hook_method("__del__")
    class_ = astx.ClassDefStmt("Value", methods=[initializer, finalizer])
    analyze(make_module("hooks", class_))
    resolved = cast(SemanticInfo, class_.semantic).resolved_class
    assert resolved is not None
    assert resolved.initialization is not None
    phase = resolved.initialization.phases[0]
    assert phase.initializer is not None
    assert phase.destructor is not None
    assert phase.initializer.signature.metadata["is_class_initializer"]
    assert not phase.destructor.signature.metadata["is_class_initializer"]
    assert all(
        member.dispatch_slot is None for member in resolved.declared_members
    )


@pytest.mark.parametrize(
    "name", ["__inti__", "__str__", "__deinit__", "__new__", "__exitx__"]
)
@pytest.mark.parametrize("is_static", [False, True])
def test_unknown_dunder_methods_are_rejected(
    name: str, is_static: bool
) -> None:
    """
    title: Typos and future protocols cannot silently become ordinary methods.
    parameters:
      name:
        type: str
      is_static:
        type: bool
    """
    method = hook_method(name)
    method.prototype.is_static = is_static
    with pytest.raises(
        SemanticError, match="dunder method names are reserved"
    ):
        analyze(
            make_module("hooks", astx.ClassDefStmt("Value", methods=[method]))
        )


@pytest.mark.parametrize("name", ["__init__", "__del__"])
def test_hook_names_cannot_be_fields(name: str) -> None:
    """
    title: Instance storage cannot shadow a compiler lifecycle entry point.
    parameters:
      name:
        type: str
    """
    class_ = astx.ClassDefStmt(
        "Value",
        attributes=[
            astx.VariableDeclaration(
                name, astx.Int32(), value=astx.LiteralInt32(0)
            )
        ],
    )
    with pytest.raises(SemanticError, match="reserved for a lifecycle method"):
        analyze(make_module("hooks", class_))


@pytest.mark.parametrize("name", ["__init__", "__del__"])
@pytest.mark.parametrize("call_kind", ["instance", "static", "base"])
def test_explicit_hook_calls_are_rejected(name: str, call_kind: str) -> None:
    """
    title: All ASTx method call forms preserve compiler-only hook entry.
    parameters:
      name:
        type: str
      call_kind:
        type: str
    """
    base = astx.ClassDefStmt("Base", methods=[hook_method(name)])
    child = astx.ClassDefStmt("Child", bases=[astx.ClassType("Base")])
    calls = {
        "instance": astx.MethodCall(astx.Identifier("value"), name, []),
        "static": astx.StaticMethodCall("Base", name, []),
        "base": astx.BaseMethodCall(
            astx.Identifier("value"), "Base", name, []
        ),
    }
    body = astx.Block()
    body.append(
        astx.VariableDeclaration(
            "value",
            astx.ClassType("Child"),
            value=astx.ClassConstruct("Child"),
        )
    )
    body.append(calls[call_kind])
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    main = astx.FunctionDef(
        astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()), body
    )
    with pytest.raises(SemanticError, match="cannot be called explicitly"):
        analyze(make_module("hooks", base, child, main))


def test_hook_spec_rejects_invalid_runtime_types() -> None:
    """
    title: Hook specifications validate names and flags at the Python boundary.
    """
    with pytest.raises(TypeCheckError):
        ClassHookSpec(42, accepts_parameters=True)  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        ClassHookSpec("__init__", accepts_parameters="yes")  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        ClassHookSpec("__init__", True, is_lifecycle="yes")  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["__enter__", "__exit__"])
def test_context_hooks_remain_callable_and_dispatchable(name: str) -> None:
    """
    title: Existing context protocols do not acquire lifecycle restrictions.
    parameters:
      name:
        type: str
    """
    class_ = astx.ClassDefStmt("Value", methods=[hook_method(name)])
    call = astx.MethodCall(astx.Identifier("value"), name, [])
    body = astx.Block()
    body.append(
        astx.VariableDeclaration(
            "value",
            astx.ClassType("Value"),
            value=astx.ClassConstruct("Value"),
        )
    )
    body.append(call)
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    main = astx.FunctionDef(
        astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()), body
    )
    analyze(make_module("hooks", class_, main))
    method = cast(SemanticInfo, call.semantic).resolved_method_call
    assert method is not None
    assert method.slot_index is not None
    assert not CLASS_HOOKS[name].is_lifecycle


@pytest.mark.parametrize("name", ["__init__", "__del__", "__str__"])
def test_module_functions_are_not_class_hooks(name: str) -> None:
    """
    title: Class-only protocols do not capture namespace function calls.
    parameters:
      name:
        type: str
    """
    call = astx.MethodCall(astx.Identifier("helpers"), name, [])
    main_body = astx.Block()
    main_body.append(call)
    main_body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    root = make_parsed_module(
        "main",
        astx.ImportStmt([astx.AliasExpr("helpers")]),
        astx.FunctionDef(
            astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
            main_body,
        ),
    )
    helpers = make_parsed_module("helpers", hook_method(name))
    analyze_modules(root, StaticImportResolver({"helpers": helpers}))
    resolved = cast(SemanticInfo, call.semantic).resolved_function
    assert resolved is not None
    assert resolved.module_key == "helpers"
