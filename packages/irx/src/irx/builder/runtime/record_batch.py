"""
packages/irx/src/irx/builder/runtime/record_batch.py

Runtime-feature descriptor for RecordBatch streaming via the Arrow C++ bridge.

This module is discovered by the IRx runtime registry and registers the
`record_batch` feature so that compiled Arx programs (and IRx-level externs)
can call the irx_rb_* family of functions.

Usage from an IRx extern declaration (Python side):

    import astx
    proto = astx.FunctionPrototype(
        name="irx_rb_schema_create",
        args=astx.Arguments(),
        return_type=astx.Int32(),
        is_extern=True,
        runtime_feature="record_batch",
    )

The feature guarantees:
  * The irx_record_batch.cpp native source is compiled and linked.
  * Arrow C++ headers are available on the include path (via
    arx-arrowcpp-sources).
  * libarrow is linked (requires a system Arrow installation or the one
    bundled by arx-arrowcpp-sources).
"""

from __future__ import annotations

import importlib.resources

from pathlib import Path
from typing import Optional, Sequence

from irx.typecheck import typechecked

# ---------------------------------------------------------------------------
# Public symbol table
# ---------------------------------------------------------------------------
# Every C-level symbol exposed by irx_record_batch.h must appear here so that
# the IRx lowering layer can route externs through the registry rather than
# emitting ad-hoc declarations.

RECORD_BATCH_SYMBOLS: frozenset[str] = frozenset(
    [
        # Error reporting
        "irx_record_batch_errmsg",
        # Schema
        "irx_rb_schema_create",
        "irx_rb_schema_add_field",
        "irx_rb_schema_num_fields",
        "irx_rb_schema_release",
        # Builder
        "irx_rb_builder_create",
        "irx_rb_builder_append_int8",
        "irx_rb_builder_append_int16",
        "irx_rb_builder_append_int32",
        "irx_rb_builder_append_int64",
        "irx_rb_builder_append_uint8",
        "irx_rb_builder_append_uint16",
        "irx_rb_builder_append_uint32",
        "irx_rb_builder_append_uint64",
        "irx_rb_builder_append_float32",
        "irx_rb_builder_append_float64",
        "irx_rb_builder_append_bool",
        "irx_rb_builder_append_null",
        "irx_rb_builder_finish",
        "irx_rb_builder_release",
        # RecordBatch inspection
        "irx_rb_batch_num_rows",
        "irx_rb_batch_num_columns",
        "irx_rb_batch_get_int8",
        "irx_rb_batch_get_int16",
        "irx_rb_batch_get_int32",
        "irx_rb_batch_get_int64",
        "irx_rb_batch_get_uint8",
        "irx_rb_batch_get_uint16",
        "irx_rb_batch_get_uint32",
        "irx_rb_batch_get_uint64",
        "irx_rb_batch_get_float32",
        "irx_rb_batch_get_float64",
        "irx_rb_batch_get_bool",
        "irx_rb_batch_is_null",
        "irx_rb_batch_value_buffer",
        "irx_rb_batch_release",
        # Stream writer
        "irx_rb_stream_writer_open_file",
        "irx_rb_stream_writer_open_buffer",
        "irx_rb_stream_writer_write_batch",
        "irx_rb_stream_writer_close",
        "irx_rb_stream_writer_buffer_data",
        "irx_rb_stream_writer_release",
        # Stream reader
        "irx_rb_stream_reader_open_file",
        "irx_rb_stream_reader_open_buffer",
        "irx_rb_stream_reader_next_batch",
        "irx_rb_stream_reader_schema",
        "irx_rb_stream_reader_close",
    ]
)


@typechecked
def _arrow_native_source_dir() -> Path:
    """Return the directory that contains irx_record_batch.cpp."""
    # Installed package: the C++ sources live next to this file inside the
    # installed package tree (packages/irx/src/irx/builder/runtime/arrow/).
    try:
        ref = importlib.resources.files("irx.builder.runtime.arrow")
        return Path(str(ref))
    except Exception:
        # Editable / development install fall-back: resolve relative to this file.
        return Path(__file__).parent / "arrow"


@typechecked
def _arrowcpp_include_dir() -> Optional[Path]:
    """
    Try to locate Arrow C++ headers via the arx-arrowcpp-sources package.
    Returns None if the package is not installed (headers must then be on the
    system include path).
    """
    try:
        import arx_arrowcpp_sources  # type: ignore[import]

        return Path(arx_arrowcpp_sources.include_dir())
    except ModuleNotFoundError:
        return None


# ---------------------------------------------------------------------------
# IRx RuntimeFeature descriptor
# ---------------------------------------------------------------------------


@typechecked
class RecordBatchFeature:
    """
    IRx runtime feature descriptor for ``record_batch``.

    The IRx registry calls ``native_sources()``, ``extra_include_dirs()``,
    ``link_flags()``, and ``owned_symbols()`` when building a compilation unit
    that activates this feature.
    """

    name: str = "record_batch"

    # The feature depends on the `array` feature (which owns the Arrow C++
    # build infrastructure and libarrow link flags).  Declaring this here lets
    # the registry automatically activate `array` whenever `record_batch` is
    # requested, avoiding duplicate link flags.
    depends_on: Sequence[str] = ("array",)

    def native_sources(self) -> list[Path]:
        """C++ source files to compile and link for this feature."""
        src_dir = _arrow_native_source_dir()
        return [src_dir / "irx_record_batch.cpp"]

    def extra_include_dirs(self) -> list[Path]:
        """Additional include directories (Arrow C++ headers)."""
        dirs: list[Path] = []
        arrow_inc = _arrowcpp_include_dir()
        if arrow_inc is not None:
            dirs.append(arrow_inc)
        return dirs

    def link_flags(self) -> list[str]:
        """
        Extra linker flags.  Arrow is linked via the `array` feature; we only
        add the IPC component here (arrow_ipc is header-only in Arrow ≥ 12 but
        was a separate shared lib in earlier versions).
        """
        return []  # arrow_ipc is covered by -larrow in the `array` feature

    def owned_symbols(self) -> frozenset[str]:
        """
        Return the set of C symbols owned by this feature.  The registry uses
        this to route extern declarations without ad-hoc hard-coding.
        """
        return RECORD_BATCH_SYMBOLS


# Singleton instance that the registry imports.
feature = RecordBatchFeature()
