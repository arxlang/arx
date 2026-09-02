"""
title: Top-level package for ArxPy.
"""

from importlib import metadata as importlib_metadata

from public import public

from arxpy.compiler import (
    ArtifactKind,
    CheckedProgram,
    CompilationArtifact,
    Compiler,
    ExecutionResult,
    ParsedProgram,
)
from arxpy.diagnostics import Diagnostic, DiagnosticSeverity
from arxpy.errors import (
    ArxError,
    CompileError,
    ExecutionError,
    ParseError,
)
from arxpy.typecheck import typechecked

DISTRIBUTION_NAME = "arxpy"


@public
@typechecked
def get_version() -> str:
    """
    title: Return the program version.
    returns:
      type: str
    """
    try:
        return importlib_metadata.version(DISTRIBUTION_NAME)
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover
        return "1.24.1"  # semantic-release


__author__: str = "Ivan Ogasawara"
__email__: str = "ivan.ogasawara@gmail.com"
__version__: str = get_version()

__all__ = [
    "ArtifactKind",
    "ArxError",
    "CheckedProgram",
    "CompilationArtifact",
    "CompileError",
    "Compiler",
    "Diagnostic",
    "DiagnosticSeverity",
    "ExecutionError",
    "ExecutionResult",
    "ParseError",
    "ParsedProgram",
    "__version__",
    "get_version",
]
