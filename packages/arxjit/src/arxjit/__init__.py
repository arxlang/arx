"""
title: Top-level package for arxjit.
"""

from importlib import metadata as importlib_metadata

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

__all__ = ["__version__", "get_version"]
