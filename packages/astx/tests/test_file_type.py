"""
title: Language-neutral file type modeling.
"""

import astx


def test_file_type_is_an_opaque_stream() -> None:
    """
    title: Native file layout stays opaque to AST clients.
    """
    type_ = astx.FileType()
    assert isinstance(type_, astx.OpaqueHandleType)
    assert type_.handle_name == "irx_file"
    assert type_.get_struct()
