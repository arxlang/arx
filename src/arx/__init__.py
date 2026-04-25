"""
title: Arx is a compiler create with llvm.
"""

import sys

from importlib import metadata as importlib_metadata
from pathlib import Path


def _prefer_local_irx_checkout() -> None:
    """
    title: Prefer one sibling IRX checkout during source-tree development.
    summary: >-
      When Arx is imported from a repository checkout that sits next to an IRX
      checkout, put that local IRX source tree ahead of any installed wheel so
      cross-repo development and tests pick up unreleased IRX changes.
    """
    repo_root = Path(__file__).resolve().parents[2]
    local_irx_src = repo_root.parent / "irx" / "src"
    if not local_irx_src.is_dir():
        return

    local_irx_src_str = str(local_irx_src)
    if local_irx_src_str in sys.path:
        return

    sys.path.insert(0, local_irx_src_str)


_prefer_local_irx_checkout()


def get_version() -> str:
    """
    title: Return the program version.
    returns:
      type: str
    """
    try:
        return importlib_metadata.version(__name__)
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover
        return "0.15.0"  # semantic-release


version: str = get_version()

__author__: str = "Ivan Ogasawara"
__email__: str = "ivan.ogasawara@gmail.com"
__version__: str = version
