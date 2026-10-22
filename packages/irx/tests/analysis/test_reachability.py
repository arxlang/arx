"""
title: Declaration dependency traversal preserves expression-bearing map keys.
"""

import astx

from irx.analysis.module_interfaces import ParsedModule
from irx.analysis.reachability import DeclarationReachability
from irx.analysis.session import CompilationSession


def unused_resolver(
    requesting_module_key: str,
    import_node: astx.ImportStmt | astx.ImportFromStmt,
    requested_specifier: str,
) -> ParsedModule:
    """
    title: No imports are needed by this isolated graph traversal.
    parameters:
      requesting_module_key:
        type: str
      import_node:
        type: astx.ImportStmt | astx.ImportFromStmt
      requested_specifier:
        type: str
    returns:
      type: ParsedModule
    """
    raise AssertionError(
        f"unexpected import {requested_specifier} from "
        f"{requesting_module_key}: {import_node}"
    )


def test_literal_dictionary_keys_are_reachable() -> None:
    """
    title: Keys carry dependencies just as dictionary values do.
    """
    root = ParsedModule("root", astx.Module())
    walker = DeclarationReachability(CompilationSession(root, unused_resolver))
    key = astx.LiteralInt32(1)
    value = astx.LiteralInt32(2)
    literal = astx.LiteralDict({key: value})
    reached = walker.collect([literal])
    assert id(key) in reached
    assert id(value) in reached
