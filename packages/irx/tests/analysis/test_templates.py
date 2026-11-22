"""
title: Tests for template-function semantic analysis.
"""

from __future__ import annotations

from typing import cast

import astx
import pytest

from irx.analysis import (
    MethodDispatchKind,
    SemanticError,
    analyze,
    analyze_modules,
)
from irx.analysis.resolved_nodes import SemanticInfo
from irx.analysis.types import same_type

from ..conftest import (
    StaticImportResolver,
    make_module,
    make_parsed_module,
)

EXPECTED_NUMBER_SPECIALIZATION_COUNT = 2


def _semantic(node: astx.AST) -> SemanticInfo:
    """
    title: Return semantic sidecar information for a node.
    parameters:
      node: Syntax node to process.
    returns: Semantic sidecar information for a node.
    """
    return cast(SemanticInfo, getattr(node, "semantic"))


def _number_bound() -> astx.UnionType:
    """
    title: Build the small Number template domain used in tests.
    returns: Constructed the small Number template domain used in tests.
    """
    return astx.UnionType(
        (astx.Int32(), astx.Float64()),
        alias_name="Number",
    )


def _mixed_scalar_bound() -> astx.UnionType:
    """
    title: Build a small mixed bound with one unsupported member.
    returns: Constructed a small mixed bound with one unsupported member.
    """
    return astx.UnionType(
        (astx.Int32(), astx.Boolean()),
        alias_name="IntOrBoolean",
    )


def _generated_function_names(module: astx.Module) -> set[str]:
    """
    title: Return generated template function names for one module.
    parameters:
      module: Module to process.
    returns: Generated template function names for one module.
    """
    return {
        node.name
        for node in astx.generated_template_nodes(module)
        if isinstance(node, astx.FunctionDef)
    }


def _template_param(name: str = "T") -> astx.TemplateParam:
    """
    title: Build one Number-bounded template parameter.
    parameters:
      name: Name identifying the declaration or operation.
    returns: Constructed one Number-bounded template parameter.
    """
    return astx.TemplateParam(name, _number_bound())


def _template_var(name: str = "T") -> astx.TemplateTypeVar:
    """
    title: Build one Number-bounded template type variable.
    parameters:
      name: Name identifying the declaration or operation.
    returns: Constructed one Number-bounded template type variable.
    """
    return astx.TemplateTypeVar(name, bound=_number_bound())


def _templated_function(
    name: str,
    return_value: astx.AST,
    *args: astx.Argument,
    return_type: astx.DataType | None = None,
    template_params: tuple[astx.TemplateParam, ...] | None = None,
) -> astx.FunctionDef:
    """
    title: Build one templated function definition.
    parameters:
      name: Name identifying the declaration or operation.
      return_value: Return value.
      return_type: Declared result type.
      template_params: Template parameters declared by the callable.
      args:
        variadic: positional
        description: Positional arguments.
    returns: Constructed one templated function definition.
    """
    prototype = astx.FunctionPrototype(
        name,
        args=astx.Arguments(*args),
        return_type=return_type or _template_var(),
    )
    astx.set_template_params(
        prototype, template_params or (_template_param(),)
    )
    body = astx.Block()
    body.append(astx.FunctionReturn(return_value))
    return astx.FunctionDef(prototype=prototype, body=body)


def _templated_method(
    name: str,
    return_value: astx.AST,
    *args: astx.Argument,
    is_static: bool = False,
) -> astx.FunctionDef:
    """
    title: Build one templated class method definition.
    parameters:
      name: Name identifying the declaration or operation.
      return_value: Return value.
      is_static: Whether the member belongs to the class rather than
        an instance.
      args:
        variadic: positional
        description: Positional arguments.
    returns: Constructed one templated class method definition.
    """
    method = _templated_function(name, return_value, *args)
    if is_static:
        method.prototype.is_static = True
    return method


def _main_returning(value: astx.AST) -> astx.FunctionDef:
    """
    title: Build a simple Int32-returning main function.
    parameters:
      value: Value to process.
    returns: Constructed a simple Int32-returning main function.
    """
    body = astx.Block()
    body.append(astx.FunctionReturn(value))
    return astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            name="main",
            args=astx.Arguments(),
            return_type=astx.Int32(),
        ),
        body=body,
    )


def test_analyze_template_function_specializes_inferred_call() -> None:
    """
    title: Inferred template calls bind to one concrete specialization.
    """
    template_fn = _templated_function(
        "add",
        astx.BinaryOp("+", astx.Identifier("lhs"), astx.Identifier("rhs")),
        astx.Argument("lhs", _template_var()),
        astx.Argument("rhs", _template_var()),
    )
    call = astx.FunctionCall(
        "add",
        [astx.LiteralInt32(1), astx.LiteralInt32(2)],
    )
    module = make_module(
        "app.main",
        template_fn,
        _main_returning(call),
    )

    analyze(module)

    resolved_call = _semantic(call).resolved_call
    resolved_function = _semantic(call).resolved_function
    generated_names = _generated_function_names(module)

    assert resolved_call is not None
    assert resolved_function is not None
    assert resolved_function.name == "add__Int32"
    assert isinstance(resolved_call.result_type, astx.Int32)
    assert generated_names == {"add__Int32", "add__Float64"}


def test_analyze_template_function_uses_explicit_template_args() -> None:
    """
    title: Explicit template arguments select the requested specialization.
    """
    template_fn = _templated_function(
        "identity",
        astx.Identifier("value"),
        astx.Argument("value", _template_var()),
    )
    call = astx.FunctionCall("identity", [astx.LiteralInt32(7)])
    astx.set_template_args(call, (astx.Float64(),))
    body = astx.Block()
    body.append(call)
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    main = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            name="main",
            args=astx.Arguments(),
            return_type=astx.Int32(),
        ),
        body=body,
    )
    module = make_module("app.main", template_fn, main)

    analyze(module)

    resolved_call = _semantic(call).resolved_call
    resolved_function = _semantic(call).resolved_function

    assert resolved_call is not None
    assert resolved_function is not None
    assert resolved_function.name == "identity__Float64"
    assert isinstance(resolved_call.result_type, astx.Float64)
    assert isinstance(resolved_call.resolved_argument_types[0], astx.Float64)


@pytest.mark.parametrize(
    "argument", [astx.LiteralFloat("1e100"), astx.LiteralFloat64(4.0)]
)
def test_explicit_nullable_template_argument_conversion(
    argument: astx.DataType,
) -> None:
    """
    title: User templates record the ordinary valid-value nullable conversion.
    parameters:
      argument: Exact literal or explicitly typed non-nullable value.
    """
    optional = astx.NullableType(astx.Float64())
    variable = astx.TemplateTypeVar("T", bound=optional)
    template_fn = _templated_function(
        "identity",
        astx.Identifier("value"),
        astx.Argument("value", variable),
        return_type=variable,
        template_params=(astx.TemplateParam("T", optional),),
    )
    call = astx.FunctionCall("identity", [argument])
    astx.set_template_args(call, (optional,))
    main = _main_returning(astx.LiteralInt32(0))
    main.body.nodes.insert(0, call)
    analyze(make_module("app.main", template_fn, main))
    resolved = _semantic(call).resolved_call
    assert resolved is not None
    assert same_type(resolved.result_type, optional)
    conversion = resolved.implicit_conversions[0]
    assert conversion is not None
    assert isinstance(conversion.source_type, astx.Float64)
    assert same_type(conversion.target_type, optional)


def test_series_template_specializations_preserve_nullability() -> None:
    """
    title: Series bounds preserve validity in type identity and cached calls.
    """
    types = (
        astx.SeriesType(astx.Float64()),
        astx.SeriesType(astx.Float64(), nullable=True),
    )
    assert not same_type(*types)
    bound = astx.UnionType(types)
    variable = astx.TemplateTypeVar("T", bound=bound)
    template_fn = _templated_function(
        "accept",
        astx.LiteralInt32(0),
        astx.Argument("value", variable),
        return_type=astx.Int32(),
        template_params=(astx.TemplateParam("T", bound),),
    )
    calls = []
    probes = []
    for index, type_ in enumerate(types):
        call = astx.FunctionCall("accept", [astx.Identifier("value")])
        calls.append(call)
        body = astx.Block()
        body.append(astx.FunctionReturn(call))
        probes.append(
            astx.FunctionDef(
                astx.FunctionPrototype(
                    f"probe_{index}",
                    astx.Arguments(astx.Argument("value", type_)),
                    astx.Int32(),
                ),
                body,
            )
        )
    analyze(make_module("app.main", template_fn, *probes))
    keys = []
    for call, expected in zip(calls, types):
        function = _semantic(call).resolved_function
        assert function is not None
        actual = function.signature.parameters[0].type_
        assert isinstance(actual, astx.SeriesType)
        assert same_type(actual, expected)
        assert actual.nullable is expected.nullable
        assert function.specialization_key is not None
        keys.append(function.specialization_key)
    assert keys[0] != keys[1]


def test_analyze_template_function_rejects_out_of_bound_explicit_arg() -> None:
    """
    title: Explicit template arguments must satisfy their finite bound.
    """
    template_fn = _templated_function(
        "identity",
        astx.Identifier("value"),
        astx.Argument("value", _template_var()),
    )
    call = astx.FunctionCall("identity", [astx.LiteralString("bad")])
    astx.set_template_args(call, (astx.String(),))
    body = astx.Block()
    body.append(call)
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    main = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            name="main",
            args=astx.Arguments(),
            return_type=astx.Int32(),
        ),
        body=body,
    )
    module = make_module("app.main", template_fn, main)

    with pytest.raises(SemanticError) as excinfo:
        analyze(module)

    assert "does not satisfy bound 'Number'" in str(excinfo.value)


def test_analyze_template_definition_reports_failing_substitution() -> None:
    """
    title: Template validation reports the substitution that fails.
    """
    mixed_bound = _mixed_scalar_bound()
    mixed_param = astx.TemplateParam("T", mixed_bound)
    mixed_var = astx.TemplateTypeVar("T", bound=mixed_bound)
    template_fn = _templated_function(
        "add_like",
        astx.BinaryOp("+", astx.Identifier("lhs"), astx.Identifier("rhs")),
        astx.Argument("lhs", mixed_var),
        astx.Argument("rhs", mixed_var),
        return_type=mixed_var,
        template_params=(mixed_param,),
    )
    module = make_module(
        "app.main",
        template_fn,
        _main_returning(astx.LiteralInt32(0)),
    )

    with pytest.raises(SemanticError) as excinfo:
        analyze(module)

    message = str(excinfo.value)
    assert "Template function 'add_like' is invalid for T = Boolean" in message
    assert "Invalid operator '+' for operand types" in message


def test_analyze_template_instance_method_uses_direct_specialization() -> None:
    """
    title: Instance template methods lower through direct specializations.
    """
    echo = _templated_method(
        "echo",
        astx.Identifier("value"),
        astx.Argument("value", _template_var()),
    )
    box = astx.ClassDefStmt(name="Box", methods=[echo])
    call = astx.MethodCall(
        astx.Identifier("box"),
        "echo",
        [astx.LiteralInt32(7)],
    )
    probe_body = astx.Block()
    probe_body.append(astx.FunctionReturn(call))
    probe = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            name="probe",
            args=astx.Arguments(
                astx.Argument("box", astx.ClassType("Box")),
            ),
            return_type=astx.Int32(),
        ),
        body=probe_body,
    )
    module = make_module(
        "app.main",
        box,
        probe,
        _main_returning(astx.LiteralInt32(0)),
    )

    analyze(module)

    resolved_class = _semantic(box).resolved_class
    resolved_method = _semantic(call).resolved_method_call
    generated_names = _generated_function_names(module)

    assert resolved_class is not None
    assert resolved_class.declared_member_table["echo"].dispatch_slot is None
    assert resolved_method is not None
    assert resolved_method.dispatch_kind is MethodDispatchKind.DIRECT
    assert resolved_method.function.name == "echo__Int32"
    assert "echo__Int32" in generated_names


def test_analyze_static_template_method_specializes_call() -> None:
    """
    title: Static template methods specialize like top-level template funcs.
    """
    identity = _templated_method(
        "identity",
        astx.Identifier("value"),
        astx.Argument("value", _template_var()),
        is_static=True,
    )
    math = astx.ClassDefStmt(name="Math", methods=[identity])
    call = astx.StaticMethodCall("Math", "identity", [astx.LiteralInt32(11)])
    module = make_module("app.main", math, _main_returning(call))

    analyze(module)

    resolved_method = _semantic(call).resolved_method_call

    assert resolved_method is not None
    assert resolved_method.function.name == "identity__Int32"
    assert resolved_method.dispatch_kind is MethodDispatchKind.DIRECT


def test_analyze_template_analysis_is_idempotent_for_same_module_ast() -> None:
    """
    title: Reanalyzing one module clears old generated specializations first.
    """
    template_fn = _templated_function(
        "add",
        astx.BinaryOp("+", astx.Identifier("lhs"), astx.Identifier("rhs")),
        astx.Argument("lhs", _template_var()),
        astx.Argument("rhs", _template_var()),
    )
    call = astx.FunctionCall(
        "add",
        [astx.LiteralInt32(1), astx.LiteralInt32(2)],
    )
    module = make_module("app.main", template_fn, _main_returning(call))

    analyze(module)
    first_names = _generated_function_names(module)

    analyze(module)
    second_names = _generated_function_names(module)

    assert first_names == {"add__Int32", "add__Float64"}
    assert second_names == first_names
    assert len(astx.generated_template_nodes(module)) == (
        EXPECTED_NUMBER_SPECIALIZATION_COUNT
    )


def test_analyze_modules_template_analysis_is_idempotent() -> None:
    """
    title: Reanalyzing one module graph clears old generated specializations.
    """
    template_fn = _templated_function(
        "add",
        astx.BinaryOp("+", astx.Identifier("lhs"), astx.Identifier("rhs")),
        astx.Argument("lhs", _template_var()),
        astx.Argument("rhs", _template_var()),
    )
    call = astx.FunctionCall(
        "add",
        [astx.LiteralInt32(1), astx.LiteralInt32(2)],
    )
    root = make_parsed_module(
        "app.main",
        astx.ImportFromStmt(module="lib", names=[astx.AliasExpr("add")]),
        _main_returning(call),
    )
    lib = make_parsed_module("lib", template_fn)
    resolver = StaticImportResolver({"lib": lib})

    analyze_modules(root, resolver)
    first_names = _generated_function_names(lib.ast)

    analyze_modules(root, resolver)
    second_names = _generated_function_names(lib.ast)

    assert first_names == {"add__Int32", "add__Float64"}
    assert second_names == first_names
    assert len(astx.generated_template_nodes(lib.ast)) == (
        EXPECTED_NUMBER_SPECIALIZATION_COUNT
    )
