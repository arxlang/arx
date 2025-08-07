"""Arx is a compiler create with llvm."""

from importlib import metadata as importlib_metadata


def get_version() -> str:
    """Return the program version."""
    try:
        return importlib_metadata.version(__name__)
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover
        return "0.2.0"  # semantic-release


version: str = get_version()

__author__: str = "Ivan Ogasawara"
__email__: str = "ivan.ogasawara@gmail.com"
__version__: str = version
