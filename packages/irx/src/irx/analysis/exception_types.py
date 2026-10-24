"""
title: Host-registered exception identities and ordinary class construction.
summary: >-
  Exception privileges come from declaration identities, never source spelling.
  Hosts and direct AST clients share one validated builtin hierarchy contract.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import astx

from public import private, public

from irx.analysis.class_lifecycle import class_ownership, constructor_arguments
from irx.analysis.module_interfaces import ParsedModule
from irx.analysis.resolved_nodes import (
    OwnershipKind,
    ResolvedClassConstruction,
    ResolvedExceptionType,
    ResolvedNativeExceptionInitialization,
    SemanticClass,
)
from irx.analysis.types import is_string_type
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.analysis.handlers.base import SemanticAnalyzerCore

EXCEPTION_HIERARCHY = (
    ("BaseException", None),
    ("Exception", "BaseException"),
    ("ValueError", "Exception"),
    ("TypeError", "Exception"),
    ("RuntimeError", "Exception"),
    ("AssertionError", "Exception"),
    ("OSError", "Exception"),
    ("ArithmeticError", "Exception"),
    ("OverflowError", "ArithmeticError"),
    ("ZeroDivisionError", "ArithmeticError"),
    ("LookupError", "Exception"),
    ("IndexError", "LookupError"),
)


@public
@typechecked
def builtin_exception_module() -> ParsedModule:
    """
    title: Build language-neutral builtin exceptions for direct AST hosts.
    summary: >-
      Return fresh declaration identities and their explicit ParsedModule
      capability, suitable for a host resolver without source parsing. The
      hierarchy uses the same schema validated for frontend-supplied builtins.
    returns:
      type: ParsedModule
    """
    module = astx.Module("builtins.exceptions")
    declarations: list[astx.ClassDefStmt] = []
    for name, parent in EXCEPTION_HIERARCHY:
        fields: list[astx.VariableDeclaration] = []
        if parent is None:
            fields = [
                astx.VariableDeclaration(
                    "record",
                    astx.OpaqueHandleType("irx_exception_info"),
                    visibility=astx.VisibilityKind.private,
                    mutability=astx.MutabilityKind.mutable,
                ),
                astx.VariableDeclaration(
                    "message",
                    astx.String(),
                    value=astx.LiteralString(""),
                    mutability=astx.MutabilityKind.constant,
                ),
            ]
        declaration = astx.ClassDefStmt(
            name,
            bases=[astx.ClassType(parent)] if parent else [],
            attributes=fields,
        )
        declarations.append(declaration)
        module.append(declaration)
    return ParsedModule(
        module.name, module, exception_classes=tuple(declarations)
    )


@private
@typechecked
def exception_error(
    analyzer: SemanticAnalyzerCore, node: astx.AST, message: str
) -> None:
    """
    title: Report an invalid nominal exception contract.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.AST
      message:
        type: str
    """
    analyzer.context.diagnostics.add(
        message, node=node, code=DiagnosticCodes.SEMANTIC_INVALID_EXCEPTION
    )


@private
@typechecked
def exception_class_type(class_: SemanticClass) -> astx.ClassType:
    """
    title: Preserve nominal ancestry in an exception expression type.
    parameters:
      class_:
        type: SemanticClass
    returns:
      type: astx.ClassType
    """
    return astx.ClassType(
        class_.name,
        resolved_name=class_.name,
        module_key=class_.module_key,
        qualified_name=class_.qualified_name,
        ancestor_qualified_names=tuple(
            ancestor.qualified_name for ancestor in class_.mro[1:]
        ),
    )


@private
@typechecked
def register_exception_types(analyzer: SemanticAnalyzerCore) -> None:
    """
    title: Attach validated base slots and nominal identities after layout.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
    """
    declarations = analyzer.context.exception_declarations
    if not declarations:
        return
    names = tuple(node.name for node in declarations)
    if len(names) != len(EXCEPTION_HIERARCHY) or set(names) != {
        name for name, _ in EXCEPTION_HIERARCHY
    }:
        exception_error(
            analyzer,
            declarations[0],
            "register exactly one complete builtin exception hierarchy",
        )
        return
    roots = [node for node in declarations if node.name == "BaseException"]
    if len(roots) != 1:
        exception_error(
            analyzer,
            declarations[0],
            "one canonical BaseException must be registered",
        )
        return
    root_decl = roots[0]
    classes = tuple(analyzer.context.classes.values())
    root = next(
        (item for item in classes if item.declaration is root_decl), None
    )
    if root is None or root.layout is None:
        return
    fields = {
        field.member.name: field for field in root.layout.instance_fields
    }
    record, message = fields.get("record"), fields.get("message")
    if (
        root.bases
        or record is None
        or message is None
        or set(fields) != {"record", "message"}
        or not isinstance(record.member.type_, astx.OpaqueHandleType)
        or record.member.type_.handle_name != "irx_exception_info"
        or record.member.visibility is not astx.VisibilityKind.private
        or not is_string_type(message.member.type_)
        or message.member.visibility is not astx.VisibilityKind.public
        or not message.member.is_constant
        or not isinstance(record.member.declaration, astx.VariableDeclaration)
        or not isinstance(record.member.declaration.value, astx.Undefined)
        or not isinstance(message.member.declaration, astx.VariableDeclaration)
        or not isinstance(message.member.declaration.value, astx.LiteralString)
        or message.member.declaration.value.value != ""
        or bool(root.instance_methods or root.static_methods)
    ):
        exception_error(
            analyzer,
            root_decl,
            "invalid registered BaseException storage contract",
        )
        return
    registered = {id(node): node.name for node in declarations}
    expected = dict(EXCEPTION_HIERARCHY)
    for class_ in classes:
        if class_.layout is None:
            continue
        ancestry = (
            class_.qualified_name,
            *(item.qualified_name for item in class_.mro[1:]),
        )
        if root.qualified_name not in ancestry:
            if id(class_.declaration) in registered:
                exception_error(
                    analyzer,
                    class_.declaration,
                    "registered exception must inherit BaseException",
                )
            continue
        if len(class_.bases) > 1:
            exception_error(
                analyzer,
                class_.declaration,
                "exception classes require single inheritance",
            )
        if class_.declaration is not root_decl and any(
            name in class_.declared_member_table
            for name in ("record", "message")
        ):
            exception_error(
                analyzer,
                class_.declaration,
                "exception storage fields cannot be overridden",
            )
        role = registered.get(id(class_.declaration))
        if role is not None:
            parent = expected.get(role)
            parent_decl = next(
                (node for node in declarations if node.name == parent), None
            )
            actual = class_.bases[0].declaration if class_.bases else None
            if role not in expected or parent_decl is not actual:
                exception_error(
                    analyzer,
                    class_.declaration,
                    "invalid registered exception hierarchy",
                )
        own_fields = {
            field.member.qualified_name: field
            for field in class_.layout.instance_fields
        }
        descriptor = ResolvedExceptionType(
            class_,
            own_fields[record.member.qualified_name],
            own_fields[message.member.qualified_name],
            tuple(ancestry),
        )
        updated = replace(class_, exception_type=descriptor)
        analyzer.context.register_class(updated)
        analyzer.bindings.bind_class(
            updated.name,
            updated,
            node=updated.declaration,
            module_key=updated.module_key,
        )
        analyzer._set_class(updated.declaration, updated)
        if role is not None:
            analyzer.context.runtime_exception_types[role] = descriptor
    if analyzer.session is not None:
        analyzer.session.runtime_exception_types.update(
            analyzer.context.runtime_exception_types
        )


@private
@typechecked
def resolve_exception_construction(
    analyzer: SemanticAnalyzerCore,
    node: astx.ClassConstruct | astx.FunctionCall | astx.MethodCall,
    class_: SemanticClass,
) -> None:
    """
    title: Bind inherited message construction without special source names.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.ClassConstruct | astx.FunctionCall | astx.MethodCall
      class_:
        type: SemanticClass
    """
    assert class_.initialization is not None
    assert class_.exception_type is not None
    function = analyzer.context.current_function
    if function is None:
        exception_error(
            analyzer,
            node,
            "exception construction requires a function body",
        )
    own_init = class_.declared_member_table.get("__init__")
    if own_init is not None:
        evaluations, indices, types = constructor_arguments(
            analyzer, node, class_
        )
        message_index = None
    else:
        values = list(node.args)
        if len(values) > 1:
            exception_error(
                analyzer, node, "exception accepts at most one message"
            )
        for keyword in node.keywords:
            if keyword.name != "message":
                exception_error(
                    analyzer, keyword, "unknown exception constructor argument"
                )
            elif values:
                exception_error(
                    analyzer, keyword, "duplicate message argument"
                )
            values.append(keyword.value)
        if not values:
            values.append(astx.LiteralString(""))
        for value in values:
            analyzer.visit(value)
            if not is_string_type(analyzer._expr_type(value)):
                exception_error(
                    analyzer, value, "exception message must have type str"
                )
        evaluations, indices, types = tuple(values), (), ()
        message_index = 0
    analyzer._set_class(node, class_)
    analyzer._set_type(node, exception_class_type(class_))
    analyzer._set_resource_ownership(
        node, class_ownership(OwnershipKind.OWNED)
    )
    analyzer._semantic(
        node
    ).resolved_class_construction = ResolvedClassConstruction(
        class_=class_,
        initialization=class_.initialization,
        evaluations=evaluations,
        argument_indices=indices,
        argument_types=types,
        native_exception=ResolvedNativeExceptionInitialization(
            class_.exception_type, message_index
        ),
    )


@private
@typechecked
def bind_direct_exception_names(
    analyzer: SemanticAnalyzerCore, node: astx.AST
) -> None:
    """
    title: Bind direct-AST ambient names without replacing user declarations.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.AST
    """
    module_key = node.name if isinstance(node, astx.Module) else "<root>"
    declared: set[str] = set()
    if isinstance(node, astx.Module):
        for child in node.nodes:
            if isinstance(child, astx.FunctionDef):
                declared.add(child.prototype.name)
            elif isinstance(child, (astx.ImportStmt, astx.ImportFromStmt)):
                declared.update(
                    alias.asname or alias.name for alias in child.names
                )
            else:
                name = getattr(child, "name", None)
                if isinstance(name, str):
                    declared.add(name)
    for descriptor in analyzer.context.runtime_exception_types.values():
        class_ = analyzer.context.get_class(
            descriptor.class_.module_key, descriptor.class_.name
        )
        assert class_ is not None
        if class_.name not in declared:
            analyzer.bindings.bind_class(
                class_.name,
                class_,
                node=class_.declaration,
                module_key=module_key,
            )
