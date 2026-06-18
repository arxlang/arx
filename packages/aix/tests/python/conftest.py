"""
title: AIX test import path setup.
"""

from __future__ import annotations

import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
for path in (
    ROOT / "packages" / "aix" / "src",
    ROOT / "packages" / "astx" / "src",
    ROOT / "packages" / "irx" / "src",
):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)
