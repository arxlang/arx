"""
title: Focused semantic rules for single-owner native text files.
"""

from dataclasses import replace

import astx

from public import private

from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.ownership import (
    resource_ownership,
    string_resource_ownership,
)
from irx.analysis.resolved_nodes import (
    OwnershipKind,
    OwnershipTransferKind,
    ResolvedFileOpen,
    ResolvedFileOperation,
    ResourceKind,
    ResourceOwnership,
    SemanticSymbol,
)
from irx.analysis.types import is_string_type
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked

OPEN_PARAMETERS = (
    "file",
    "mode",
    "buffering",
    "encoding",
    "errors",
    "newline",
    "closefd",
    "opener",
)
FILE_MODES = {"r", "w", "a", "rt", "wt", "at"}


@private
@typechecked
def file_error(
    analyzer: SemanticAnalyzerCore,
    node: astx.AST,
    message: str,
) -> None:
    """
    title: Report an actionable file contract violation.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.AST
      message:
        type: str
    """
    analyzer.context.diagnostics.add(
        message,
        node=node,
        code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
    )


@private
@typechecked
def literal_nul(node: astx.AST) -> bool:
    """
    title: Detect literal NUL in a string expression without evaluating calls.
    parameters:
      node:
        type: astx.AST
    returns:
      type: bool
    """
    if isinstance(node, astx.LiteralString):
        return "\0" in node.value
    if isinstance(node, astx.BinaryOp):
        return literal_nul(node.lhs) or literal_nul(node.rhs)
    if isinstance(node, astx.Cast):
        return literal_nul(node.value)
    return False


@private
@typechecked
def supported_option(name: str, value: astx.DataType) -> bool:
    """
    title: Recognize the supported constant optional arguments of open.
    parameters:
      name:
        type: str
      value:
        type: astx.DataType
    returns:
      type: bool
    """
    if name == "buffering":
        integers = (
            astx.LiteralInt8,
            astx.LiteralInt16,
            astx.LiteralInt32,
            astx.LiteralInt64,
        )
        if isinstance(value, astx.UnaryOp) and value.op_code == "-":
            return isinstance(value.operand, integers) and (
                value.operand.value == 1
            )
        return isinstance(value, integers) and value.value == -1
    if name == "closefd":
        return isinstance(value, astx.LiteralBoolean) and value.value is True
    if isinstance(value, astx.LiteralNone):
        return True
    if isinstance(value, astx.LiteralString):
        return (name, value.value) in {
            ("encoding", "utf-8"),
            ("errors", "strict"),
        }
    return False


@private
@typechecked
def resolve_file_open(
    analyzer: SemanticAnalyzerCore,
    node: astx.FunctionCall,
) -> None:
    """
    title: Bind the restricted eight-argument open interface in source order.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.FunctionCall
    """
    info = analyzer._semantic(node)
    info.resolved_call = None
    info.resolved_callable = None
    info.resolved_function = None
    supplied = list(node.args)
    values: dict[str, astx.DataType] = {}
    if len(supplied) > len(OPEN_PARAMETERS):
        file_error(analyzer, node, "open expects at most eight arguments")
        return
    ordered = list(zip(OPEN_PARAMETERS, supplied))
    for name, value in ordered:
        values[name] = value
    for keyword in node.keywords:
        if keyword.name not in OPEN_PARAMETERS:
            file_error(
                analyzer, keyword, f"unknown open argument '{keyword.name}'"
            )
            return
        if keyword.name in values:
            file_error(
                analyzer, keyword, f"duplicate open argument '{keyword.name}'"
            )
            return
        values[keyword.name] = keyword.value
        supplied.append(keyword.value)
        ordered.append((keyword.name, keyword.value))
    if "file" not in values:
        file_error(analyzer, node, "open requires a file path")
        return
    if astx.get_template_args(node) is not None:
        file_error(analyzer, node, "open does not accept template arguments")
        return
    for value in supplied:
        analyzer.visit(value)
    valid = True
    for name, value in values.items():
        if name in {"file", "mode"}:
            if not is_string_type(analyzer._expr_type(value)):
                file_error(analyzer, value, f"open {name} requires a string")
                valid = False
            if literal_nul(value):
                file_error(analyzer, value, f"open {name} cannot contain NUL")
                valid = False
            if name == "mode" and isinstance(value, astx.LiteralString):
                if value.value not in FILE_MODES:
                    file_error(
                        analyzer,
                        value,
                        "open supports only r, w, a, rt, wt, at modes",
                    )
                    valid = False
        elif not supported_option(name, value):
            file_error(
                analyzer,
                value,
                f"open {name} supports only its documented constant default "
                "(or utf-8/strict)",
            )
            valid = False
    function = analyzer.context.current_function
    if (function is None and analyzer.context.current_class is None) or (
        function is not None
        and function.signature.metadata.get("generator") is not None
    ):
        file_error(
            analyzer,
            node,
            "open requires a non-generator function with lexical cleanup",
        )
        valid = False
    if not valid:
        return
    # Optional arguments are validated constants, not runtime/void operands.
    operands = [
        (name, value) for name, value in ordered if name in {"file", "mode"}
    ]
    evaluations = tuple(value for name, value in operands)
    path_index = next(
        i for i, (name, value) in enumerate(operands) if name == "file"
    )
    mode_index = next(
        (i for i, (name, value) in enumerate(operands) if name == "mode"), None
    )
    analyzer._semantic(node).resolved_file_open = ResolvedFileOpen(
        evaluations,
        path_index,
        mode_index,
    )
    analyzer._set_type(node, astx.FileType())
    analyzer._set_resource_ownership(
        node,
        ResourceOwnership(ResourceKind.FILE, OwnershipKind.OWNED),
    )


@private
@typechecked
def resolve_file_method(
    analyzer: SemanticAnalyzerCore,
    node: astx.MethodCall,
) -> None:
    """
    title: Resolve a native file method after visiting receiver and arguments.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.MethodCall
    """
    info = analyzer._semantic(node)
    info.resolved_call = None
    info.resolved_callable = None
    info.resolved_method_call = None
    info.resolved_function = None
    info.resolved_module_member_access = None
    info.resource_ownership = None
    arity = {"read": 0, "write": 1, "flush": 0, "close": 0}
    if node.method_name not in arity:
        file_error(
            analyzer, node, f"unsupported file method '{node.method_name}'"
        )
        return
    if (
        len(node.args) != arity[node.method_name]
        or astx.get_template_args(node) is not None
    ):
        file_error(
            analyzer,
            node,
            f"file {node.method_name} expects {arity[node.method_name]} "
            "arguments and no templates",
        )
        return
    if node.method_name == "write":
        if not is_string_type(
            analyzer._expr_type(node.args[0])
        ) or literal_nul(node.args[0]):
            file_error(analyzer, node, "file write requires a NUL-free string")
            return
    ownership = resource_ownership(node.receiver)
    if ownership is None or ownership.resource_kind is not ResourceKind.FILE:
        file_error(
            analyzer, node, "file receiver is missing its ownership contract"
        )
        return
    analyzer._semantic(node).resolved_file_operation = ResolvedFileOperation(
        node.method_name
    )
    result_type: astx.DataType = astx.NoneType()
    if node.method_name == "read":
        result_type = astx.String()
        analyzer._set_resource_ownership(
            node, string_resource_ownership(OwnershipKind.OWNED)
        )
    elif node.method_name == "write":
        result_type = astx.Int64()
    analyzer._set_type(node, result_type)


@private
@typechecked
def resolve_file_local(
    analyzer: SemanticAnalyzerCore,
    node: astx.VariableDeclaration | astx.InlineVariableDeclaration,
    symbol: SemanticSymbol,
) -> None:
    """
    title: Transfer a fresh open result into one local owner.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.VariableDeclaration | astx.InlineVariableDeclaration
      symbol:
        type: SemanticSymbol
    """
    value = node.value
    if (
        not isinstance(value, astx.FunctionCall)
        or analyzer._semantic(value).resolved_file_open is None
    ):
        file_error(
            analyzer,
            node,
            "file locals require a direct open initializer; "
            "copies are unsupported",
        )
        return
    ownership = resource_ownership(value)
    if ownership is None:
        file_error(analyzer, node, "open result is missing ownership metadata")
        return
    analyzer._set_resource_ownership(
        value,
        replace(
            ownership,
            owner_symbol_id=symbol.symbol_id,
            transfer_kind=OwnershipTransferKind.MOVE,
        ),
    )
    analyzer._set_resource_ownership(
        node,
        ResourceOwnership(
            ResourceKind.FILE,
            OwnershipKind.OWNED,
            owner_symbol_id=symbol.symbol_id,
        ),
    )
