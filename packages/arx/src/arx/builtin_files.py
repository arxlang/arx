"""
title: Frontend discovery of the native-backed File builtin dependency.
"""

from collections.abc import Iterator

import astx

from arx.builtins import BUILTIN_FILE, BUILTIN_FILE_MODULE, BUILTIN_OPEN


def source_children(node: astx.AST) -> Iterator[astx.AST]:
    """
    title: >-
      Traverse source nodes and types without revisiting semantic sidecars.
    parameters:
      node:
        type: astx.AST
    returns:
      type: Iterator[astx.AST]
    """
    pending = [node]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        for name, value in vars(current).items():
            if name in {"semantic", "parent"}:
                continue
            if isinstance(value, astx.AST):
                pending.append(value)
            elif isinstance(value, (list, tuple)):
                pending.extend(
                    item for item in value if isinstance(item, astx.AST)
                )


def needs_file_builtin(module: astx.Module) -> bool:
    """
    title: Request File lazily, without adding native dependencies to scalars.
    parameters:
      module:
        type: astx.Module
    returns:
      type: bool
    """
    if module.name == BUILTIN_FILE_MODULE:
        return False
    declared = {
        node.name
        for node in module.nodes
        if isinstance(
            node, (astx.FunctionDef, astx.FunctionPrototype, astx.ClassDefStmt)
        )
    }
    for node in source_children(module):
        if (
            isinstance(node, astx.ImportFromStmt)
            and node.module == BUILTIN_FILE_MODULE
        ):
            return True
        if isinstance(node, astx.ImportStmt) and any(
            alias.name == BUILTIN_FILE_MODULE for alias in node.names
        ):
            return True
        if isinstance(node, astx.ClassType) and (
            (node.name == BUILTIN_FILE and BUILTIN_FILE not in declared)
            or node.module_key == BUILTIN_FILE_MODULE
        ):
            return True
        if (
            isinstance(node, astx.FunctionCall)
            and node.fn
            in {
                BUILTIN_OPEN,
                BUILTIN_FILE,
            }
            and node.fn not in declared
        ):
            return True
        if (
            isinstance(node, astx.ClassConstruct)
            and node.class_name == BUILTIN_FILE
            and BUILTIN_FILE not in declared
        ):
            return True
    return False
