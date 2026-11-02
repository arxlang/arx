"""
title: Numeric reader ABI bounds, exact bits, strides and output slots.
"""

import ctypes
import shutil
import subprocess

from pathlib import Path

import pytest

from .test_arrow_runtime import BufferViewStruct

BOUNDS_ERROR = 4
OFFSET_OVERFLOW = 2


class ListDescriptor(ctypes.Structure):
    """
    title: The public C list descriptor, not a C++ layout.
    """

    _fields_ = [
        ("data", ctypes.c_void_p),
        ("length", ctypes.c_int64),
        ("capacity", ctypes.c_int64),
        ("element_size", ctypes.c_int64),
        ("element_kind", ctypes.c_int32),
    ]


@pytest.fixture(scope="module")
def numeric_native(tmp_path_factory: pytest.TempPathFactory) -> ctypes.CDLL:
    """
    title: Build the list and buffer C readers once without Arrow.
    parameters:
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: ctypes.CDLL
    """
    compiler = shutil.which("clang")
    if compiler is None:
        pytest.skip("native sequence tests require clang")
    root = Path(__file__).parents[1] / "src/irx/builder/runtime"
    library = tmp_path_factory.mktemp("numeric-readers") / "readers.so"
    subprocess.run(
        [
            compiler,
            "-shared",
            "-fPIC",
            "-std=c99",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(root / "list/native/irx_list_runtime.c"),
            str(root / "buffer/native/irx_buffer_runtime.c"),
            "-o",
            str(library),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    native = ctypes.CDLL(str(library))
    for name in ("irx_list_sequence_read", "irx_buffer_sequence_read"):
        function = getattr(native, name)
        function.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int64,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_int32),
        ]
        function.restype = ctypes.c_int32
    native.irx_buffer_checked_offset.argtypes = [
        ctypes.POINTER(BufferViewStruct),
        ctypes.POINTER(ctypes.c_int64),
        ctypes.c_int32,
        ctypes.c_int64,
        ctypes.POINTER(ctypes.c_int64),
    ]
    native.irx_buffer_checked_offset.restype = ctypes.c_int32
    return native


@pytest.mark.parametrize(
    "width,bits",
    [
        (1, 0x80),
        (1, 0xFF),
        (2, 0x8000),
        (2, 0xFFFF),
        (4, 0x80000000),
        (4, 0xFFFFFFFF),
        (8, 2**53 + 1),
        (8, 2**63 - 1),
        (8, 2**63),
        (8, 2**64 - 1),
        (4, 0x7FC01234),
        (4, 0x7F800000),
        (8, 0x7FF8000000001234),
        (8, 0xFFF0000000000000),
    ],
)
def test_numeric_reader_preserves_bits(
    numeric_native: ctypes.CDLL, width: int, bits: int
) -> None:
    """
    title: Preserve every integer bit and float NaN payload without nulls.
    parameters:
      numeric_native:
        type: ctypes.CDLL
      width:
        type: int
      bits:
        type: int
    """
    scalar = {
        1: ctypes.c_uint8,
        2: ctypes.c_uint16,
        4: ctypes.c_uint32,
        8: ctypes.c_uint64,
    }[width]
    storage = (scalar * 3)(0, bits, 0)
    array = ListDescriptor(ctypes.addressof(storage), 3, 3, width, 0)
    shape = (ctypes.c_int64 * 1)(3)
    stride = (ctypes.c_int64 * 1)(-width)
    view = BufferViewStruct(
        ctypes.addressof(storage), None, None, 1, shape, stride, width * 2, 0
    )
    for name, descriptor in (
        ("irx_list_sequence_read", array),
        ("irx_buffer_sequence_read", view),
    ):
        reader = getattr(numeric_native, name)
        value, valid = ctypes.c_uint64(77), ctypes.c_int32(77)
        assert (
            reader(
                ctypes.byref(descriptor),
                1,
                width,
                ctypes.byref(value),
                ctypes.byref(valid),
            )
            == 0
        )
        assert (value.value, valid.value) == (bits, 1)
        for index in (-1, 3, 2**63 - 1):
            value.value = valid.value = 77
            assert (
                reader(
                    ctypes.byref(descriptor),
                    index,
                    width,
                    ctypes.byref(value),
                    ctypes.byref(valid),
                )
                == BOUNDS_ERROR
            )
            assert (value.value, valid.value) == (0, 0)


def test_checked_offset_rank_bounds_and_overflow(
    numeric_native: ctypes.CDLL,
) -> None:
    """
    title: Reject malformed rank and overflow before dereferencing memory.
    parameters:
      numeric_native:
        type: ctypes.CDLL
    """
    data = (ctypes.c_int32 * 12)(*range(12))
    shape = (ctypes.c_int64 * 2)(2, 3)
    strides = (ctypes.c_int64 * 2)(24, 8)
    view = BufferViewStruct(
        ctypes.addressof(data), None, None, 2, shape, strides, 4, 0
    )
    output = ctypes.c_int64(123)
    indices = (ctypes.c_int64 * 2)(1, 2)
    offset = numeric_native.irx_buffer_checked_offset
    assert offset(ctypes.byref(view), indices, 2, 4, ctypes.byref(output)) == 0
    assert output.value == 4 + 24 + 2 * 8
    assert offset(ctypes.byref(view), indices, 1, 4, ctypes.byref(output)) == 1
    assert output.value == 0
    for axis in range(2):
        old = indices[axis]
        for invalid in (-1, shape[axis]):
            indices[axis] = invalid
            assert (
                offset(ctypes.byref(view), indices, 2, 4, ctypes.byref(output))
                == BOUNDS_ERROR
            )
            assert output.value == 0
        indices[axis] = old
    for stride in (2**62, -(2**62) - 1):
        strides[1] = stride
        assert (
            offset(ctypes.byref(view), indices, 2, 4, ctypes.byref(output))
            == OFFSET_OVERFLOW
        )
        assert output.value == 0
    strides[1] = 8
    view.offset_bytes = 2**63 - 1
    assert (
        offset(ctypes.byref(view), indices, 2, 4, ctypes.byref(output))
        == OFFSET_OVERFLOW
    )
    assert output.value == 0
