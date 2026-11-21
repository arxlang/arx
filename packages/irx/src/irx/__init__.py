"""
title: Top-level package for IRx.
attributes:
  __version__: Installed package version.
"""

from importlib import metadata as importlib_metadata

from irx.typecheck import typechecked

_DISTRIBUTION_NAME = "pyirx"


@typechecked
def get_version() -> str:
    """
    title: Return the program version.
    returns: The program version.
    """
    try:
        return importlib_metadata.version(_DISTRIBUTION_NAME)
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover
        return "1.29.0"  # semantic-release


__author__ = """Ivan Ogasawara"""
__email__ = "ivan.ogasawara@gmail.com"
__version__: str = get_version()
