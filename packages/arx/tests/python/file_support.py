"""
title: Host-supplied builtin dependencies for Arx semantic regression tests.
"""

from typing import cast

import astx

from arx.builtin_files import needs_file_builtin
from arx.main import FileImportResolver, inject_ambient_builtin_imports
from irx.analysis import analyze, analyze_modules
from irx.analysis.module_interfaces import ParsedModule


def analyze_arx(module: astx.Module) -> astx.Module:
    """
    title: Analyze Arx source through its owning builtin-module host.
    parameters:
      module:
        type: astx.Module
    returns:
      type: astx.Module
    """
    if not needs_file_builtin(module):
        return cast(astx.Module, analyze(module))
    analyze_modules(
        ParsedModule(module.name, inject_ambient_builtin_imports(module)),
        FileImportResolver(input_files=()),
    )
    return module
