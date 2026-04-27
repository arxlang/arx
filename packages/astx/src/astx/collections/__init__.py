"""
title: IRX-owned collection helper AST nodes.
summary: >-
  Group IRX-specific collection-oriented AST helpers behind one stable package
  boundary while re-exporting the current public node names.
"""

from __future__ import annotations

from astx.collections.common import (
    CollectionContains as CollectionContains,
)
from astx.collections.common import CollectionCount as CollectionCount
from astx.collections.common import CollectionIndex as CollectionIndex
from astx.collections.common import (
    CollectionIsEmpty as CollectionIsEmpty,
)
from astx.collections.common import CollectionLength as CollectionLength
from astx.collections.list import ListAppend as ListAppend
from astx.collections.list import ListCreate as ListCreate
from astx.collections.list import ListIndex as ListIndex
from astx.collections.list import ListLength as ListLength

__all__ = (
    "CollectionContains",
    "CollectionCount",
    "CollectionIndex",
    "CollectionIsEmpty",
    "CollectionLength",
    "ListAppend",
    "ListCreate",
    "ListIndex",
    "ListLength",
)
