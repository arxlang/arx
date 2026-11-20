"""
title: Arx is a compiler create with llvm.
attributes:
  version: Package version metadata.
  __author__: Package author attribution.
  __email__: Package author contact address.
  __version__: Installed package version.
"""

from importlib import metadata as importlib_metadata

_DISTRIBUTION_NAME = "arxlang"


def get_version() -> str:
    """
    title: Return the program version.
    returns: The program version.
    """
    try:
        return importlib_metadata.version(_DISTRIBUTION_NAME)
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover
        return "1.28.0"  # semantic-release


version: str = get_version()

__author__: str = "Ivan Ogasawara"
__email__: str = "ivan.ogasawara@gmail.com"
__version__: str = version
