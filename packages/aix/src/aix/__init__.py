"""
title: AIX package metadata.
"""

from importlib import metadata as importlib_metadata

_DISTRIBUTION_NAME = "airx"


def get_version() -> str:
    """
    title: Return the installed package version.
    returns:
      type: str
    """
    try:
        return importlib_metadata.version(_DISTRIBUTION_NAME)
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover
        return "1.24.0"  # semantic-release


version: str = get_version()

__author__: str = "Ivan Ogasawara"
__email__: str = "ivan.ogasawara@gmail.com"
__version__: str = version
