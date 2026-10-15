"""
title: Language-neutral native file type.
"""

from public import public

from astx.ffi import OpaqueHandleType
from astx.tools.typing import typechecked


@public
@typechecked
class FileType(OpaqueHandleType):
    """
    title: An owned opaque text stream, distinct from arbitrary FFI handles.
    """

    def __init__(self) -> None:
        """
        title: Initialize the native text file type.
        """
        super().__init__("irx_file")
