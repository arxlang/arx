"""
title: Direct AST exception ABI and lexical exit-region regressions.
"""

import shutil
import subprocess

from pathlib import Path

import astx
import pytest

from astx.types import AnyType
from irx.builder import Builder
from llvmlite import binding as llvm
from llvmlite import ir

from .test_dynamic_list import assert_executed_list_cleanups
from .test_string import assert_executed_string_frees

CAUGHT_VALUE = 7
ABI_ARGUMENTS = 2
EXIT_STATE = 9
METHOD_CAUGHT_VALUE = 8


def block(*nodes: astx.AST) -> astx.Block:
    """
    title: Build an ordered statement block.
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


def function(
    name: str, body: astx.Block, return_type: AnyType | None = None
) -> astx.FunctionDef:
    """
    title: Build a resolved-by-analysis source function.
    parameters:
      name:
        type: str
      body:
        type: astx.Block
      return_type:
        type: AnyType | None
    returns:
      type: astx.FunctionDef
    """
    return astx.FunctionDef(
        astx.FunctionPrototype(
            name, astx.Arguments(), return_type or astx.Int32()
        ),
        body,
    )


def raised() -> astx.ThrowStmt:
    """
    title: Construct a nominal builtin raise without Arx parsing.
    returns:
      type: astx.ThrowStmt
    """
    return astx.ThrowStmt(
        astx.FunctionCall("ValueError", [astx.LiteralString("failure")])
    )


def caught(
    body: astx.Block, value: astx.DataType
) -> astx.ExceptionHandlerStmt:
    """
    title: Return a supplied value when ValueError reaches this region.
    parameters:
      body:
        type: astx.Block
      value:
        type: astx.DataType
    returns:
      type: astx.ExceptionHandlerStmt
    """
    return astx.ExceptionHandlerStmt(
        body,
        [
            astx.CatchHandlerStmt(
                block(astx.FunctionReturn(value)),
                types=[astx.Identifier("ValueError")],
            )
        ],
    )


def run_module(tmp_path: Path, *nodes: astx.AST) -> tuple[str, int]:
    """
    title: Verify generated LLVM and execute its platform wrapper.
    parameters:
      tmp_path:
        type: Path
      nodes:
        type: astx.AST
        variadic: positional
    returns:
      type: tuple[str, int]
    """
    if shutil.which("clang") is None:
        pytest.skip("native exception test requires clang")
    module = astx.Module(name="exception_abi")
    for node in nodes:
        module.block.append(node)
    builder = Builder()
    text = builder.translate(module)
    llvm.parse_assembly(text).verify()
    executable = tmp_path / "program"
    builder._build_from_ir(text, str(executable))
    result = subprocess.run(
        [str(executable)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.stderr == ""
    return text, result.returncode


def test_status_call_reads_only_success_output(tmp_path: Path) -> None:
    """
    title: A throwing function never exposes its uninitialized return slot.
    parameters:
      tmp_path:
        type: Path
    """
    helper = function("helper", block(raised()))
    main = function(
        "main",
        block(
            caught(
                block(astx.FunctionCall("helper", [])),
                astx.LiteralInt32(CAUGHT_VALUE),
            ),
            astx.FunctionReturn(astx.LiteralInt32(0)),
        ),
    )
    text, result = run_module(tmp_path, helper, main)
    assert result == CAUGHT_VALUE
    parsed = llvm.parse_assembly(text)
    entry = parsed.get_function("irx.entry.main")
    assert len(list(entry.arguments)) == ABI_ARGUMENTS
    assert len(list(parsed.get_function("main").arguments)) == 0
    failed = [
        item for item in entry.blocks if item.name.startswith("call.failure")
    ]
    assert failed
    for item in failed:
        assert all(
            instruction.opcode != "load" for instruction in item.instructions
        )


@pytest.mark.parametrize(
    ("transfer", "expected"), [("break", 1), ("continue", 3)]
)
def test_loop_transfer_runs_finally(
    tmp_path: Path, transfer: str, expected: int
) -> None:
    """
    title: Direct AST loop transfers run finalization once per iteration.
    parameters:
      tmp_path:
        type: Path
      transfer:
        type: str
      expected:
        type: int
    """
    counter = astx.VariableDeclaration(
        "counter",
        astx.Int32(),
        mutability=astx.MutabilityKind.mutable,
        value=astx.LiteralInt32(0),
    )
    exits = astx.VariableDeclaration(
        "exits",
        astx.Int32(),
        mutability=astx.MutabilityKind.mutable,
        value=astx.LiteralInt32(0),
    )
    advance = astx.VariableAssignment(
        "counter",
        astx.BinaryOp("+", astx.Identifier("counter"), astx.LiteralInt32(1)),
    )
    finalizer = astx.FinallyHandlerStmt(
        block(
            astx.VariableAssignment(
                "exits",
                astx.BinaryOp(
                    "+", astx.Identifier("exits"), astx.LiteralInt32(1)
                ),
            )
        )
    )
    region = astx.ExceptionHandlerStmt(
        block(
            advance,
            astx.BreakStmt() if transfer == "break" else astx.ContinueStmt(),
        ),
        [],
        finalizer,
    )
    loop = astx.WhileStmt(
        astx.BinaryOp("<", astx.Identifier("counter"), astx.LiteralInt32(3)),
        block(region),
    )
    _, result = run_module(
        tmp_path,
        function(
            "main",
            block(
                counter,
                exits,
                loop,
                astx.FunctionReturn(astx.Identifier("exits")),
            ),
        ),
    )
    assert result == expected


def test_with_exception_runs_exit_before_handler(tmp_path: Path) -> None:
    """
    title: Exceptional with exit runs through the same status ABI as methods.
    parameters:
      tmp_path:
        type: Path
    """
    state = astx.VariableDeclaration(
        "state",
        astx.Int32(),
        mutability=astx.MutabilityKind.mutable,
        scope=astx.ScopeKind.global_,
        value=astx.LiteralInt32(0),
    )
    setattr(state, "is_static", True)
    manager = astx.ClassDefStmt(
        "Manager",
        attributes=[state],
        methods=[
            function(
                "__enter__", block(astx.FunctionReturn(astx.LiteralInt32(1)))
            ),
            function(
                "__exit__",
                block(
                    astx.BinaryOp(
                        "=",
                        astx.StaticFieldAccess("Manager", "state"),
                        astx.LiteralInt32(EXIT_STATE),
                    )
                ),
                astx.NoneType(),
            ),
        ],
    )
    main = function(
        "main",
        block(
            caught(
                block(
                    astx.WithStmt(
                        astx.ClassConstruct("Manager"), block(raised())
                    )
                ),
                astx.StaticFieldAccess("Manager", "state"),
            ),
            astx.FunctionReturn(astx.LiteralInt32(0)),
        ),
    )
    _, result = run_module(tmp_path, manager, main)
    assert result == EXIT_STATE


@pytest.mark.parametrize("dispatch", ["virtual", "static", "base"])
def test_method_status_propagates(tmp_path: Path, dispatch: str) -> None:
    """
    title: >-
      Every resolved method dispatch shape propagates an exceptional status.
    parameters:
      tmp_path:
        type: Path
      dispatch:
        type: str
    """
    method = function("fail", block(raised()))
    if dispatch == "static":
        setattr(method.prototype, "is_static", True)
    base = astx.ClassDefStmt("Base", methods=[method])
    child = astx.ClassDefStmt("Child", bases=[astx.ClassType("Base")])
    call: astx.AST
    if dispatch == "static":
        call = astx.StaticMethodCall("Base", "fail", [])
    elif dispatch == "base":
        call = astx.BaseMethodCall(
            astx.ClassConstruct("Child"), "Base", "fail", []
        )
    else:
        call = astx.MethodCall(astx.ClassConstruct("Child"), "fail", [])
    main = function(
        "main",
        block(
            caught(block(call), astx.LiteralInt32(METHOD_CAUGHT_VALUE)),
            astx.FunctionReturn(astx.LiteralInt32(0)),
        ),
    )
    _, result = run_module(tmp_path, base, child, main)
    assert result == METHOD_CAUGHT_VALUE


def test_raise_operand_survives_mutating_cause(tmp_path: Path) -> None:
    """
    title: Pin a borrowed raised field before a cause expression replaces it.
    parameters:
      tmp_path:
        type: Path
    """
    original = astx.FunctionCall(
        "ValueError", [astx.LiteralString("original")]
    )
    field = astx.VariableDeclaration(
        "error",
        astx.ClassType("ValueError"),
        mutability=astx.MutabilityKind.mutable,
        value=original,
    )
    holder = astx.ClassDefStmt("Holder", attributes=[field])
    replace = astx.FunctionDef(
        astx.FunctionPrototype(
            "replace",
            astx.Arguments(astx.Argument("holder", astx.ClassType("Holder"))),
            astx.ClassType("ValueError"),
        ),
        block(
            astx.BinaryOp(
                "=",
                astx.FieldAccess(astx.Identifier("holder"), "error"),
                astx.FunctionCall(
                    "ValueError", [astx.LiteralString("replacement")]
                ),
            ),
            astx.FunctionReturn(
                astx.FunctionCall("ValueError", [astx.LiteralString("cause")])
            ),
        ),
    )
    handler = astx.CatchHandlerStmt(
        block(
            astx.IfStmt(
                astx.BinaryOp(
                    "==",
                    astx.FieldAccess(astx.Identifier("caught"), "message"),
                    astx.LiteralString("original"),
                ),
                block(astx.FunctionReturn(astx.LiteralInt32(CAUGHT_VALUE))),
                block(astx.FunctionReturn(astx.LiteralInt32(0))),
            )
        ),
        name=astx.Identifier("caught"),
        types=[astx.Identifier("ValueError")],
    )
    main = function(
        "main",
        block(
            astx.VariableDeclaration(
                "holder",
                astx.ClassType("Holder"),
                value=astx.ClassConstruct("Holder"),
            ),
            astx.ExceptionHandlerStmt(
                block(
                    astx.ThrowStmt(
                        astx.FieldAccess(astx.Identifier("holder"), "error"),
                        cause=astx.FunctionCall(
                            "replace", [astx.Identifier("holder")]
                        ),
                    )
                ),
                [handler],
            ),
            astx.FunctionReturn(astx.LiteralInt32(0)),
        ),
    )
    _, result = run_module(tmp_path, holder, replace, main)
    assert result == CAUGHT_VALUE


@pytest.mark.parametrize("nested", [False, True])
def test_cancelled_return_owns_only_its_completion(
    tmp_path: Path, nested: bool
) -> None:
    """
    title: >-
      Local loop transfers cancel inner returns without releasing older ones.
    parameters:
      tmp_path:
        type: Path
      nested:
        type: bool
    """
    original = astx.BinaryOp(
        "+", astx.LiteralString("original"), astx.LiteralString("")
    )
    inner = astx.ExceptionHandlerStmt(
        block(
            astx.FunctionReturn(
                astx.BinaryOp(
                    "+",
                    astx.LiteralString("cancelled"),
                    astx.LiteralString(""),
                )
            )
        ),
        [],
        astx.FinallyHandlerStmt(block(astx.BreakStmt())),
    )
    loop = astx.WhileStmt(astx.LiteralBoolean(True), block(inner))
    if nested:
        body = block(
            astx.VariableDeclaration("value", astx.String(), value=original),
            astx.ExceptionHandlerStmt(
                block(astx.FunctionReturn(astx.Identifier("value"))),
                [],
                astx.FinallyHandlerStmt(block(loop)),
            ),
        )
        expected_text = "original"
        expected_frees = 3
    else:
        body = block(loop, astx.FunctionReturn(original))
        expected_text = "original"
        expected_frees = 2
    make = function("make", body, astx.String())
    main = function(
        "main",
        block(
            astx.VariableDeclaration(
                "result", astx.String(), value=astx.FunctionCall("make", [])
            ),
            astx.IfStmt(
                astx.BinaryOp(
                    "==",
                    astx.Identifier("result"),
                    astx.LiteralString(expected_text),
                ),
                block(astx.FunctionReturn(astx.LiteralInt32(CAUGHT_VALUE))),
                block(astx.FunctionReturn(astx.LiteralInt32(0))),
            ),
        ),
    )
    _, result = run_module(tmp_path, make, main)
    assert result == CAUGHT_VALUE
    module = astx.Module(name="exception_abi")
    module.block.append(make)
    module.block.append(main)
    assert_executed_string_frees(module, expected_frees)


@pytest.mark.parametrize("cancellation", ["break", "handler"])
def test_cancelled_list_move_restores_surviving_binding(
    tmp_path: Path, cancellation: str
) -> None:
    """
    title: A cancelled affine move returns ownership to an in-scope binding.
    parameters:
      tmp_path:
        type: Path
      cancellation:
        type: str
    """
    type_ = astx.ListType([astx.Int32()])
    body = block(
        astx.VariableDeclaration(
            "values",
            type_,
            mutability=astx.MutabilityKind.mutable,
            value=astx.ListCreate(astx.Int32()),
        ),
        astx.ListAppend(
            astx.Identifier("values"), astx.LiteralInt32(CAUGHT_VALUE)
        ),
    )
    bad = astx.ClassDefStmt(
        "Bad", methods=[function("__del__", block(raised()), astx.NoneType())]
    )
    if cancellation == "break":
        body.append(
            astx.WhileStmt(
                astx.LiteralBoolean(True),
                block(
                    astx.ExceptionHandlerStmt(
                        block(astx.FunctionReturn(astx.Identifier("values"))),
                        [],
                        astx.FinallyHandlerStmt(block(astx.BreakStmt())),
                    )
                ),
            )
        )
    else:
        body.append(
            astx.ExceptionHandlerStmt(
                block(
                    astx.VariableDeclaration(
                        "bad",
                        astx.ClassType("Bad"),
                        value=astx.ClassConstruct("Bad"),
                    ),
                    astx.FunctionReturn(astx.Identifier("values")),
                ),
                [
                    astx.CatchHandlerStmt(
                        block(astx.LiteralInt32(0)),
                        types=[astx.Identifier("ValueError")],
                    )
                ],
            )
        )
    body.append(astx.FunctionReturn(astx.Identifier("values")))
    make = function("make", body, type_)
    main = function(
        "main",
        block(
            astx.VariableDeclaration(
                "result", type_, value=astx.FunctionCall("make", [])
            ),
            astx.FunctionReturn(
                astx.SubscriptExpr(
                    astx.Identifier("result"), astx.LiteralInt32(0)
                )
            ),
        ),
    )
    _, result = run_module(tmp_path, bad, make, main)
    assert result == CAUGHT_VALUE
    module = astx.Module(name="exception_abi")
    for declaration in (bad, make, main):
        module.block.append(declaration)
    assert_executed_list_cleanups(
        module, tmp_path, expected=1, expected_result=CAUGHT_VALUE
    )


@pytest.mark.parametrize("generator", [False, True])
def test_void_return_evaluates_failing_expression(
    tmp_path: Path, generator: bool
) -> None:
    """
    title: Void return expressions propagate failures before committing return.
    parameters:
      tmp_path:
        type: Path
      generator:
        type: bool
    """
    fail = function("fail", block(raised()), astx.NoneType())
    body = block()
    if generator:
        body.append(astx.YieldStmt(astx.LiteralInt32(1)))
    body.append(astx.FunctionReturn(astx.FunctionCall("fail", [])))
    forward = function(
        "forward",
        body,
        astx.GeneratorType(astx.Int32()) if generator else astx.NoneType(),
    )
    call = astx.FunctionCall("forward", [])
    invocation = (
        astx.ForInLoopStmt(
            astx.Identifier("item"), call, block(astx.LiteralInt32(0))
        )
        if generator
        else call
    )
    main = function(
        "main",
        block(
            caught(
                block(invocation),
                astx.LiteralInt32(CAUGHT_VALUE),
            ),
            astx.FunctionReturn(astx.LiteralInt32(0)),
        ),
    )
    _, result = run_module(tmp_path, fail, forward, main)
    assert result == CAUGHT_VALUE


def test_native_failures_share_cold_materialization_helpers() -> None:
    """
    title: Reuse cold exception construction without merging source locations.
    """
    lines = (11, 17)
    module = astx.Module(name="helper_cache")
    assertions = [
        astx.AssertStmt(
            astx.Identifier("valid"),
            message=astx.LiteralString("checked"),
            loc=astx.SourceLocation(line=line, col=3),
        )
        for line in lines
    ]
    module.block.append(
        function(
            "main",
            block(
                astx.VariableDeclaration(
                    "valid", astx.Boolean(), value=astx.LiteralBoolean(True)
                ),
                *assertions,
                astx.FunctionReturn(astx.LiteralInt32(0)),
            ),
        )
    )
    builder = Builder()
    text = builder.translate(module)
    llvm.parse_assembly(text).verify()
    generated = builder.translator._llvm.module
    helpers = [
        item
        for item in generated.functions
        if item.name == "irx.raise.builtins.exceptions::class::AssertionError"
    ]
    assert len(helpers) == 1
    helper = helpers[0]
    assert "cold" in helper.attributes
    assert "noinline" in helper.attributes
    calls = [
        instruction
        for item in generated.functions
        for basic_block in item.blocks
        for instruction in basic_block.instructions
        if isinstance(instruction, ir.CallInstr)
        and instruction.callee is helper
    ]
    assert [call.args[3].constant for call in calls] == list(lines)


@pytest.mark.parametrize("empty", ["operand", "cause"])
def test_empty_exception_reference_is_checked(
    tmp_path: Path, empty: str
) -> None:
    """
    title: Empty raised values and explicit causes become checked RuntimeError.
    parameters:
      tmp_path:
        type: Path
      empty:
        type: str
    """
    declaration = astx.VariableDeclaration(
        "missing", astx.ClassType("ValueError")
    )
    operand = (
        astx.Identifier("missing")
        if empty == "operand"
        else astx.FunctionCall("ValueError", [astx.LiteralString("outer")])
    )
    statement = astx.ThrowStmt(
        operand, cause=astx.Identifier("missing") if empty == "cause" else None
    )
    handler = astx.CatchHandlerStmt(
        block(astx.FunctionReturn(astx.LiteralInt32(CAUGHT_VALUE))),
        types=[astx.Identifier("RuntimeError")],
    )
    main = function(
        "main",
        block(
            declaration,
            astx.ExceptionHandlerStmt(block(statement), [handler]),
            astx.FunctionReturn(astx.LiteralInt32(0)),
        ),
    )
    _, result = run_module(tmp_path, main)
    assert result == CAUGHT_VALUE


def test_raw_and_checked_externs_share_native_feature() -> None:
    """
    title: Facade adaptation uses exact symbols, not every export in a feature.
    """
    module = astx.Module("native_contract")
    declarations = (
        (
            "release_raw",
            "irx_rb_schema_release",
            astx.NoneType(),
            "raw_schema",
        ),
        (
            "count_checked",
            "irx_rb_api_schema_count",
            astx.Int32(),
            "api_schema",
        ),
    )
    for index, (alias, symbol, result, handle_name) in enumerate(declarations):
        prototype = astx.FunctionPrototype(
            alias,
            astx.Arguments(
                astx.Argument("handle", astx.OpaqueHandleType(handle_name))
            ),
            result,
        )
        prototype.is_extern = True
        prototype.calling_convention = "c"
        prototype.symbol_name = symbol
        prototype.runtime_feature = "record_batch"
        module.append(prototype)
        call = astx.FunctionCall(alias, [astx.Identifier("handle")])
        body = (
            block(call, astx.FunctionReturn(astx.LiteralNone()))
            if isinstance(result, astx.NoneType)
            else block(astx.FunctionReturn(call))
        )
        module.append(
            astx.FunctionDef(
                astx.FunctionPrototype(
                    f"consume_{index}",
                    astx.Arguments(
                        astx.Argument(
                            "handle", astx.OpaqueHandleType(handle_name)
                        )
                    ),
                    result,
                ),
                body,
            )
        )
    module.append(
        function("main", block(astx.FunctionReturn(astx.LiteralInt32(0))))
    )
    text = Builder().translate(module)
    llvm.parse_assembly(text).verify()
    assert 'declare external void @"irx_rb_schema_release"(i8*' in text
    assert 'call void @"irx_rb_schema_release"(i8*' in text
    assert 'call i32 @"irx_rb_api_schema_count"(i8*' in text
    assert 'declare external i32 @"irx_rb_api_schema_count"(i8*' in text
