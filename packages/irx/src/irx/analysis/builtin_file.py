"""
title: >-
  Explicit host capabilities and construction of native-backed File classes.
"""

from typing import cast

import astx

from public import private

from irx.analysis.class_lifecycle import class_ownership
from irx.analysis.file_io import bind_file_arguments, file_error
from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.resolved_nodes import (
    OwnershipKind,
    ResolvedClassConstruction,
    ResolvedNativeFileInitialization,
    SemanticClass,
)
from irx.analysis.types import is_string_type
from irx.typecheck import typechecked

NATIVE_FILE_METHODS = frozenset({"read", "write", "flush", "close"})


@private
@typechecked
def is_native_file_class(
    analyzer: SemanticAnalyzerCore, class_: SemanticClass
) -> bool:
    """
    title: Identify a builtin by its host-registered declaration, not its name.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      class_:
        type: SemanticClass
    returns:
      type: bool
    """
    return analyzer.session is not None and any(
        module.native_file_class is class_.declaration
        for module in analyzer.session.modules.values()
    )


@private
@typechecked
def registered_file_class(
    analyzer: SemanticAnalyzerCore,
) -> SemanticClass | None:
    """
    title: Look up the unique native File capability supplied by the host.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
    returns:
      type: SemanticClass | None
    """
    if analyzer.session is None:
        return None
    for module in analyzer.session.modules.values():
        declaration = module.native_file_class
        if declaration is not None:
            class_ = analyzer.context.get_class(module.key, declaration.name)
            if class_ is not None and not class_.is_resolved:
                resolver = getattr(analyzer, "_resolve_class_definition")
                class_ = cast(SemanticClass, resolver(class_))
            return class_
    return None


@private
@typechecked
def validate_native_file_class(
    analyzer: SemanticAnalyzerCore, class_: SemanticClass
) -> bool:
    """
    title: Prove the layout contract before granting native initialization.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      class_:
        type: SemanticClass
    returns:
      type: bool
    """
    if not is_native_file_class(analyzer, class_):
        return False
    declaration = class_.declaration
    fields = declaration.attributes
    valid = (
        not declaration.bases
        and len(fields) == 1
        and isinstance(fields[0].type_, astx.FileType)
        and fields[0].visibility is astx.VisibilityKind.private
        and not getattr(fields[0], "is_static", False)
        and (
            fields[0].value is None
            or isinstance(fields[0].value, astx.Undefined)
        )
        and len(declaration.methods) == len(NATIVE_FILE_METHODS)
        and {method.name for method in declaration.methods}
        == NATIVE_FILE_METHODS
    )
    for method in declaration.methods:
        prototype = method.prototype
        parameters = prototype.args.nodes
        valid = (
            valid
            and not any(
                getattr(prototype, flag, False)
                for flag in (
                    "is_static",
                    "is_abstract",
                    "is_extern",
                    "is_variadic",
                )
            )
            and not astx.is_template_node(prototype)
        )
        valid = valid and prototype.visibility is astx.VisibilityKind.public
        if method.name == "write":
            valid = valid and (
                len(parameters) == 1
                and is_string_type(parameters[0].type_)
                and isinstance(prototype.return_type, astx.Int64)
            )
        elif method.name == "read":
            valid = (
                valid
                and not parameters
                and is_string_type(prototype.return_type)
            )
        else:
            valid = (
                valid
                and not parameters
                and isinstance(prototype.return_type, astx.NoneType)
            )
    if not valid:
        file_error(analyzer, declaration, "invalid native File class contract")
    return valid


@private
@typechecked
def resolve_public_file_construction(
    analyzer: SemanticAnalyzerCore,
    node: astx.FunctionCall | astx.ClassConstruct | astx.MethodCall,
    class_: SemanticClass,
) -> None:
    """
    title: Bind both public factories to one checked class initialization plan.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.FunctionCall | astx.ClassConstruct | astx.MethodCall
      class_:
        type: SemanticClass
    """
    if not validate_native_file_class(analyzer, class_):
        return
    entry = (
        "open"
        if isinstance(node, astx.FunctionCall) and node.fn == "open"
        else "File"
    )
    operands = bind_file_arguments(analyzer, node, entry)
    if operands is None:
        return
    if class_.layout is None or class_.initialization is None:
        raise TypeError("native File requires resolved class layout")
    field = class_.layout.instance_fields[0]
    analyzer._set_class(node, class_)
    analyzer._set_class_construction(
        node,
        ResolvedClassConstruction(
            class_,
            class_.initialization,
            evaluations=operands.evaluations,
            native_file=ResolvedNativeFileInitialization(field, operands),
        ),
    )
    analyzer._set_type(
        node,
        astx.ClassType(
            class_.name,
            module_key=class_.module_key,
            qualified_name=class_.qualified_name,
            resolved_name=class_.name,
        ),
    )
    analyzer._set_resource_ownership(
        node, class_ownership(OwnershipKind.OWNED)
    )
