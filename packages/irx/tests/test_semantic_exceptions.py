"""
title: Nominal exception semantics and conservative completion analysis.
"""

import astx
import pytest

from irx.analysis import (
    FlowOutcome,
    ParsedModule,
    ResolvedNativeExceptionInitialization,
    ResolvedTry,
    analyze,
    analyze_modules,
    builtin_exception_module,
    flow_outcomes,
)
from irx.analysis.exception_types import EXCEPTION_HIERARCHY
from irx.diagnostics import SemanticError
from typeguard import TypeCheckError


def block(*nodes: astx.AST) -> astx.Block:
    """
    title: Build a statement block.
    parameters:
      nodes:
        type: astx.AST
        variadic: positional
    returns:
      type: astx.Block
    """
    result = astx.Block()
    for node in nodes:
        result.append(node)
    return result


def module(*nodes: astx.AST) -> astx.Module:
    """
    title: Wrap exception statements in an integer-returning function.
    parameters:
      nodes:
        type: astx.AST
        variadic: positional
    returns:
      type: astx.Module
    """
    result = astx.Module("test")
    result.append(
        astx.FunctionDef(
            astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
            block(*nodes),
        )
    )
    return result


def test_direct_ast_exception_identity_and_constructor() -> None:
    """
    title: Direct AST hosts receive real nominal builtins and typed sidecars.
    """
    value = astx.ClassConstruct("ValueError", (astx.LiteralString("bad"),))
    raised = astx.ThrowStmt(value)
    handler = astx.CatchHandlerStmt(
        block(astx.FunctionReturn(astx.LiteralInt32(3))),
        astx.Identifier("error"),
        [astx.Identifier("ValueError")],
    )
    region = astx.ExceptionHandlerStmt(block(raised), [handler])
    tree = module(region)
    analyze(tree)
    assert raised.semantic.resolved_raise.exception_type is not None
    assert (
        value.semantic.resolved_class_construction.native_exception is not None
    )
    binding = handler.semantic.resolved_exception_handler
    assert binding.symbol.type_.name == "ValueError"
    assert binding.types[0].class_.qualified_name.endswith(
        "::class::ValueError"
    )
    assert set(tree.semantic.runtime_exception_types) == {
        name for name, _ in EXCEPTION_HIERARCHY
    }
    assert FlowOutcome.NORMAL not in flow_outcomes(region)


def test_dynamic_bare_reraise_and_finally_completion() -> None:
    """
    title: Bare raise is dynamically valid and finalizers replace completion.
    """
    raised = astx.ThrowStmt()
    region = astx.ExceptionHandlerStmt(
        block(raised),
        [],
        astx.FinallyHandlerStmt(
            block(astx.FunctionReturn(astx.LiteralInt32(8)))
        ),
    )
    analyze(module(region))
    assert raised.semantic.resolved_raise.exception_type is None
    assert FlowOutcome.RETURN in flow_outcomes(region)
    assert FlowOutcome.NORMAL not in flow_outcomes(region)


@pytest.mark.parametrize(
    "value", [astx.LiteralInt32(2), astx.LiteralString("bad")]
)
def test_nonexception_raise_rejected(value: astx.Expr) -> None:
    """
    title: Primitive values cannot impersonate nominal exception instances.
    parameters:
      value:
        type: astx.Expr
    """
    with pytest.raises(SemanticError, match="exception instance"):
        analyze(module(astx.ThrowStmt(value)))


def test_shadowed_handler_name_is_not_privileged() -> None:
    """
    title: A local named ValueError blocks the ambient exception class.
    """
    handler = astx.CatchHandlerStmt(
        block(), types=[astx.Identifier("ValueError")]
    )
    tree = module(
        astx.VariableDeclaration(
            "ValueError", astx.Int32(), value=astx.LiteralInt32(1)
        ),
        astx.ExceptionHandlerStmt(block(astx.ThrowStmt()), [handler]),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )
    with pytest.raises(SemanticError, match="handler type"):
        analyze(tree)


def test_handler_binding_cannot_escape_scope() -> None:
    """
    title: Handler-owned references are inaccessible after the region.
    """
    handler = astx.CatchHandlerStmt(block(), astx.Identifier("caught"))
    tree = module(
        astx.ExceptionHandlerStmt(block(astx.ThrowStmt()), [handler]),
        astx.ThrowStmt(astx.Identifier("caught")),
    )
    with pytest.raises(SemanticError, match="cannot resolve name 'caught'"):
        analyze(tree)


def test_finalizer_cannot_read_skipped_initializer() -> None:
    """
    title: A try-local owner is not definitely available to a finalizer.
    """
    region = astx.ExceptionHandlerStmt(
        block(
            astx.VariableDeclaration(
                "pending",
                astx.ClassType("ValueError"),
                value=astx.ClassConstruct("ValueError"),
            )
        ),
        [],
        astx.FinallyHandlerStmt(
            block(astx.ThrowStmt(astx.Identifier("pending")))
        ),
    )
    with pytest.raises(SemanticError, match="cannot resolve name 'pending'"):
        analyze(module(region))


def test_unregistered_named_class_cannot_be_raised() -> None:
    """
    title: Identically spelled classes do not acquire native exception powers.
    """
    tree = module(astx.ThrowStmt(astx.ClassConstruct("ValueError")))
    tree.nodes.insert(0, astx.ClassDefStmt("ValueError"))
    with pytest.raises(SemanticError, match="exception instance"):
        analyze(tree)


def test_capability_requires_own_declaration_identity() -> None:
    """
    title: A capability cannot register a class from another parsed module.
    """
    builtin = builtin_exception_module()
    with pytest.raises(ValueError, match="belong"):
        ParsedModule(
            "fake",
            astx.Module("fake"),
            exception_classes=builtin.exception_classes,
        )


def test_custom_subclass_inherits_message_constructor() -> None:
    """
    title: Extra ordinary fields do not hide the inherited message argument.
    """
    custom = astx.ClassDefStmt(
        "Problem",
        bases=[astx.ClassType("ValueError")],
        attributes=[
            astx.VariableDeclaration(
                "code",
                astx.Int32(),
                value=astx.LiteralInt32(7),
            )
        ],
    )
    value = astx.ClassConstruct(
        "Problem",
        keywords=(
            astx.KeywordArgument("message", astx.LiteralString("specific")),
        ),
    )
    tree = module(astx.ThrowStmt(value))
    tree.nodes.insert(0, custom)
    analyze(tree)
    plan = value.semantic.resolved_class_construction
    assert plan.native_exception.message_index == 0
    assert plan.native_exception.exception_type.class_.name == "Problem"
    assert plan.evaluations[0].value == "specific"


def test_multiple_handlers_bind_nearest_common_exception_class() -> None:
    """
    title: Alternative nominal types yield their nearest common exception base.
    """
    handler = astx.CatchHandlerStmt(
        block(astx.FunctionReturn(astx.LiteralInt32(1))),
        astx.Identifier("error"),
        [astx.Identifier("ValueError"), astx.Identifier("TypeError")],
    )
    analyze(
        module(astx.ExceptionHandlerStmt(block(astx.ThrowStmt()), [handler]))
    )
    assert (
        handler.semantic.resolved_exception_handler.binding_type.name
        == "Exception"
    )


def test_explicit_cause_requires_an_exception_and_none_suppresses() -> None:
    """
    title: Explicit diagnostic suppression differs from an invalid cause.
    """
    raised = astx.ThrowStmt(
        astx.ClassConstruct("ValueError"), cause=astx.LiteralNone()
    )
    tree = module(raised)
    analyze(tree)
    assert raised.semantic.resolved_raise.cause_mode.value == "suppress"
    raised.cause = astx.LiteralInt32(4)
    with pytest.raises(SemanticError, match="exception instance"):
        analyze(tree)


def test_finally_normal_path_does_not_erase_try_fallthrough() -> None:
    """
    title: >-
      A possibly falling-through finalizer cannot prove a function returns.
    """
    region = astx.ExceptionHandlerStmt(
        block(),
        [],
        astx.FinallyHandlerStmt(block()),
    )
    with pytest.raises(SemanticError, match="return"):
        analyze(module(region))


def test_constructor_may_raise_without_initializing_file_field() -> None:
    """
    title: Exceptional constructor exits do not publish partially built fields.
    """
    initializer = astx.FunctionDef(
        astx.FunctionPrototype("__init__", astx.Arguments(), astx.NoneType()),
        block(astx.ThrowStmt(astx.ClassConstruct("ValueError"))),
    )
    custom = astx.ClassDefStmt(
        "Resource",
        attributes=[
            astx.VariableDeclaration(
                "handle",
                astx.FileType(),
                mutability=astx.MutabilityKind.mutable,
            )
        ],
        methods=[initializer],
    )
    tree = module(astx.FunctionReturn(astx.LiteralInt32(0)))
    tree.nodes.insert(0, custom)
    analyze(tree)


def test_message_is_readonly_and_diagnostic_storage_is_private() -> None:
    """
    title: Native diagnostic storage cannot bypass ordinary field visibility.
    """
    declaration = astx.VariableDeclaration(
        "error",
        astx.ClassType("ValueError"),
        value=astx.ClassConstruct("ValueError"),
    )
    assignment = astx.BinaryOp(
        "=",
        astx.FieldAccess(astx.Identifier("error"), "message"),
        astx.LiteralString("replacement"),
    )
    with pytest.raises(SemanticError, match="constant"):
        analyze(
            module(
                declaration,
                assignment,
                astx.FunctionReturn(astx.LiteralInt32(0)),
            )
        )
    private_read = astx.FieldAccess(astx.Identifier("error"), "record")
    with pytest.raises(SemanticError, match=r"private|accessible"):
        analyze(
            module(
                declaration,
                private_read,
                astx.FunctionReturn(astx.LiteralInt32(0)),
            )
        )


def test_host_registered_import_alias_and_qualified_handlers() -> None:
    """
    title: Imported aliases and namespace members retain nominal identity.
    """
    builtin = builtin_exception_module()
    alias_handler = astx.CatchHandlerStmt(
        block(astx.FunctionReturn(astx.LiteralInt32(1))),
        types=[astx.Identifier("InputError")],
    )
    qualified_handler = astx.CatchHandlerStmt(
        block(astx.FunctionReturn(astx.LiteralInt32(2))),
        types=[astx.FieldAccess(astx.Identifier("errors"), "RuntimeError")],
    )
    tree = module(
        astx.ExceptionHandlerStmt(
            block(astx.ThrowStmt()),
            [alias_handler, qualified_handler],
        )
    )
    tree.nodes[:0] = [
        astx.ImportFromStmt(
            [astx.AliasExpr("ValueError", "InputError")],
            module=builtin.key,
        ),
        astx.ImportStmt([astx.AliasExpr(builtin.key, "errors")]),
    ]

    def resolve(
        requesting_module_key: str,
        import_node: astx.AST,
        requested_specifier: str,
    ) -> ParsedModule:
        """
        title: Supply exactly the registered canonical builtin module.
        parameters:
          requesting_module_key:
            type: str
          import_node:
            type: astx.AST
          requested_specifier:
            type: str
        returns:
          type: ParsedModule
        """
        assert requested_specifier == builtin.key
        return builtin

    analyze_modules(ParsedModule(tree.name, tree), resolve)
    first = alias_handler.semantic.resolved_exception_handler.types[0]
    second = qualified_handler.semantic.resolved_exception_handler.types[0]
    assert first.class_.declaration in builtin.exception_classes
    assert second.class_.declaration in builtin.exception_classes
    assert first.class_.name == "ValueError"
    assert second.class_.name == "RuntimeError"


def test_generator_can_raise_without_suspending_protected_state() -> None:
    """
    title: A resumed generator may construct and propagate an exception.
    """
    raised = astx.ThrowStmt(astx.ClassConstruct("ValueError"))
    function = astx.FunctionDef(
        astx.FunctionPrototype(
            "values", astx.Arguments(), astx.GeneratorType(astx.Int32())
        ),
        block(astx.YieldStmt(astx.LiteralInt32(1)), raised),
    )
    tree = astx.Module("generators")
    tree.append(function)
    analyze(tree)
    assert raised.semantic.resolved_raise.exception_type is not None


def test_generator_protected_region_without_yield_can_bind_exception() -> None:
    """
    title: A handler-only exception reference never escapes across suspension.
    """
    handler = astx.CatchHandlerStmt(
        block(astx.FieldAccess(astx.Identifier("error"), "message")),
        astx.Identifier("error"),
        [astx.Identifier("ValueError")],
    )
    region = astx.ExceptionHandlerStmt(
        block(astx.ThrowStmt(astx.ClassConstruct("ValueError"))),
        [handler],
    )
    function = astx.FunctionDef(
        astx.FunctionPrototype(
            "values", astx.Arguments(), astx.GeneratorType(astx.Int32())
        ),
        block(region, astx.YieldStmt(astx.LiteralInt32(1))),
    )
    tree = astx.Module("generators")
    tree.append(function)
    analyze(tree)
    assert handler.semantic.resolved_exception_handler.symbol is not None


def test_generator_rejects_yield_in_protected_region() -> None:
    """
    title: Suspended try/handler/finally state is rejected before lowering.
    """
    region = astx.ExceptionHandlerStmt(
        block(astx.YieldStmt(astx.LiteralInt32(1))),
        [],
        astx.FinallyHandlerStmt(block()),
    )
    function = astx.FunctionDef(
        astx.FunctionPrototype(
            "values", astx.Arguments(), astx.GeneratorType(astx.Int32())
        ),
        block(region),
    )
    tree = astx.Module("generators")
    tree.append(function)
    with pytest.raises(SemanticError, match="suspension in protected"):
        analyze(tree)


def test_else_failures_are_not_handler_alternatives() -> None:
    """
    title: Handler fallthrough cannot swallow a failure produced only by else.
    """
    region = astx.ExceptionHandlerStmt(
        block(),
        [astx.CatchHandlerStmt(block())],
        else_body=block(astx.ThrowStmt(astx.ClassConstruct("ValueError"))),
    )
    analyze(module(region))
    assert FlowOutcome.NORMAL not in flow_outcomes(region)


def test_loop_outcomes_preserve_returns_and_consume_local_breaks() -> None:
    """
    title: Loop completion preserves returns while local breaks become normal.
    """
    loop = astx.WhileStmt(
        astx.LiteralBoolean(True),
        block(
            astx.IfStmt(
                astx.LiteralBoolean(True),
                block(astx.FunctionReturn(astx.LiteralInt32(1))),
                block(astx.BreakStmt()),
            ),
        ),
    )
    outcomes = flow_outcomes(loop)
    assert FlowOutcome.RETURN in outcomes
    assert FlowOutcome.NORMAL in outcomes
    assert FlowOutcome.BREAK not in outcomes


def test_exception_sidecars_validate_all_runtime_collection_items() -> None:
    """
    title: Invalid host-side semantic metadata fails its typed boundary.
    """
    builtin = builtin_exception_module()
    with pytest.raises(TypeCheckError):
        ParsedModule(
            builtin.key,
            builtin.ast,
            exception_classes=(builtin.exception_classes[0], 1),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeCheckError):
        ResolvedNativeExceptionInitialization(1, 0)  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        ResolvedTry((1,))  # type: ignore[arg-type]


@pytest.mark.parametrize("conditional", [False, True])
def test_else_requires_normally_initialized_try_local(
    conditional: bool,
) -> None:
    """
    title: Else sees direct try owners but cannot read conditional locals.
    parameters:
      conditional:
        type: bool
    """
    declaration = astx.VariableDeclaration(
        "error",
        astx.ClassType("ValueError"),
        value=astx.ClassConstruct("ValueError"),
    )
    statement: astx.AST = declaration
    if conditional:
        statement = astx.IfStmt(
            astx.LiteralBoolean(True), block(declaration), block()
        )
    region = astx.ExceptionHandlerStmt(
        block(statement),
        [astx.CatchHandlerStmt(block())],
        else_body=block(astx.ThrowStmt(astx.Identifier("error"))),
    )
    tree = module(region, astx.FunctionReturn(astx.LiteralInt32(0)))
    if conditional:
        with pytest.raises(SemanticError, match="not definitely initialized"):
            analyze(tree)
    else:
        analyze(tree)


@pytest.mark.parametrize("access", ["fresh", "read", "write"])
def test_finalizer_cannot_reuse_pending_list_return(access: str) -> None:
    """
    title: An affine return cannot be read twice while fresh replacement works.
    parameters:
      access:
        type: str
    """
    result = (
        astx.Identifier("values")
        if access == "read"
        else astx.ListCreate(astx.Int32())
    )
    finalizer = block(astx.FunctionReturn(result))
    if access == "write":
        finalizer.nodes.insert(
            0, astx.VariableAssignment("values", astx.ListCreate(astx.Int32()))
        )
    region = astx.ExceptionHandlerStmt(
        block(astx.FunctionReturn(astx.Identifier("values"))),
        [],
        astx.FinallyHandlerStmt(finalizer),
    )
    tree = astx.Module("test")
    tree.append(
        astx.FunctionDef(
            astx.FunctionPrototype(
                "values", astx.Arguments(), astx.ListType([astx.Int32()])
            ),
            block(
                astx.VariableDeclaration(
                    "values",
                    astx.ListType([astx.Int32()]),
                    value=astx.ListCreate(astx.Int32()),
                    mutability=astx.MutabilityKind.mutable,
                ),
                region,
            ),
        )
    )
    if access != "fresh":
        with pytest.raises(SemanticError, match="list moved by a pending"):
            analyze(tree)
    else:
        analyze(tree)


def test_handler_only_custom_type_is_a_lowering_dependency() -> None:
    """
    title: Lazy modules retain classes referenced only by nominal handlers.
    """
    builtin = builtin_exception_module()
    errors = astx.Module("errors")
    errors.append(
        astx.ImportFromStmt([astx.AliasExpr("Exception")], module=builtin.key)
    )
    problem = astx.ClassDefStmt("Problem", bases=[astx.ClassType("Exception")])
    unused = astx.ClassDefStmt("Unused")
    errors.append(problem)
    errors.append(unused)
    imported = ParsedModule("errors", errors, lazy_declarations=True)
    handler = astx.CatchHandlerStmt(
        block(astx.FieldAccess(astx.Identifier("caught"), "message")),
        astx.Identifier("caught"),
        [astx.FieldAccess(astx.Identifier("errors"), "Problem")],
    )
    tree = module(
        astx.ExceptionHandlerStmt(block(), [handler]),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )
    tree.nodes.insert(0, astx.ImportStmt([astx.AliasExpr("errors")]))
    modules = {builtin.key: builtin, imported.key: imported}

    def resolve(
        requesting_module_key: str,
        import_node: astx.AST,
        requested_specifier: str,
    ) -> ParsedModule:
        """
        title: Resolve a lazy custom exception module and its builtin base.
        parameters:
          requesting_module_key:
            type: str
          import_node:
            type: astx.AST
          requested_specifier:
            type: str
        returns:
          type: ParsedModule
        """
        return modules[requested_specifier]

    session = analyze_modules(ParsedModule(tree.name, tree), resolve)
    assert session.lowering_declarations is not None
    assert id(problem) in session.lowering_declarations
    assert id(unused) not in session.lowering_declarations
