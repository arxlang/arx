"""
title: Top-level package for arxjit.
"""

from importlib import metadata as importlib_metadata

from arxjit.core import JitFunction, jit
from arxjit.diagnostics import Diagnostic, DiagnosticSeverity
from arxjit.errors import (
    ArxJitError,
    SourceExtractionError,
    UnsupportedSyntaxError,
)
from arxjit.source import ExtractedSource, extract_source
from arxjit.types import (
    Signature,
    SigType,
    bool_,
    f32,
    f64,
    i32,
    i64,
)

_DISTRIBUTION_NAME = "arxjit"


def get_version() -> str:
    """
    title: Return the program version.
    returns:
      type: str
    """
    try:
        return importlib_metadata.version(_DISTRIBUTION_NAME)
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover
        return "1.23.1"  # semantic-release


__author__: str = "Ivan Ogasawara"
__email__: str = "ivan.ogasawara@gmail.com"
__version__: str = get_version()

__all__ = [
    "ArxJitError",
    "Diagnostic",
    "DiagnosticSeverity",
    "ExtractedSource",
    "JitFunction",
    "SigType",
    "Signature",
    "SourceExtractionError",
    "UnsupportedSyntaxError",
    "__version__",
    "bool_",
    "extract_source",
    "f32",
    "f64",
    "get_version",
    "i32",
    "i64",
    "jit",
]
