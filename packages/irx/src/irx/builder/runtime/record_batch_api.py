"""
title: Checked RecordBatch facade ABI signatures.
"""

ARROW_API_SIGNATURES: dict[str, tuple[str, tuple[str, ...]]] = {
    "irx_rb_api_reader_csv": ("v", ("p", "p", "p", "i32", "i32")),
    "irx_rb_api_reader_csv_as": ("v", ("p", "p", "p", "p", "i32", "i32")),
    "irx_rb_api_writer_csv": ("v", ("p", "p", "p", "i32")),
    "irx_rb_api_batch_to_table": ("p", ("p", "p")),
    "irx_rb_api_batch_to_dynamic_table": ("p", ("p",)),
    "irx_rb_api_table_to_dynamic_batch": ("v", ("p", "p")),
    "irx_rb_api_table_to_batch": ("v", ("p", "p")),
    "irx_rb_api_schema_new": ("p", ()),
    "irx_rb_api_batch_new": ("p", ()),
    "irx_rb_api_reader_new": ("p", ()),
    "irx_rb_api_builder_new": ("p", ("p",)),
    "irx_rb_api_writer_new": ("p", ("p",)),
    "irx_rb_api_schema_destroy": ("v", ("p",)),
    "irx_rb_api_schema_close": ("v", ("p",)),
    "irx_rb_api_batch_destroy": ("v", ("p",)),
    "irx_rb_api_batch_close": ("v", ("p",)),
    "irx_rb_api_builder_destroy": ("v", ("p",)),
    "irx_rb_api_builder_close": ("v", ("p",)),
    "irx_rb_api_reader_destroy": ("v", ("p",)),
    "irx_rb_api_reader_close": ("v", ("p",)),
    "irx_rb_api_writer_destroy": ("v", ("p",)),
    "irx_rb_api_writer_close": ("v", ("p",)),
    "irx_rb_api_schema_ipc": ("p", ("p", "i64")),
    "irx_rb_api_schema_add": ("v", ("p", "p", "i32", "i32")),
    "irx_rb_api_schema_count": ("i32", ("p",)),
    "irx_rb_api_schema_name": ("p", ("p", "i32")),
    "irx_rb_api_schema_type": ("i32", ("p", "i32")),
    "irx_rb_api_schema_nullable": ("i32", ("p", "i32")),
    "irx_rb_api_schema_type_name": ("p", ("p", "i32")),
    "irx_rb_api_schema_equal": ("i32", ("p", "p")),
    "irx_rb_api_builder_finish": ("v", ("p", "p")),
    "irx_rb_api_batch_rows": ("i64", ("p",)),
    "irx_rb_api_batch_columns": ("i32", ("p",)),
    "irx_rb_api_batch_schema": ("v", ("p", "p")),
    "irx_rb_api_batch_null": ("i32", ("p", "i32", "i64")),
    "irx_rb_api_append_i8": ("v", ("p", "i32", "i8")),
    "irx_rb_api_get_i8": ("i8", ("p", "i32", "i64")),
    "irx_rb_api_append_i16": ("v", ("p", "i32", "i16")),
    "irx_rb_api_get_i16": ("i16", ("p", "i32", "i64")),
    "irx_rb_api_append_i32": ("v", ("p", "i32", "i32")),
    "irx_rb_api_get_i32": ("i32", ("p", "i32", "i64")),
    "irx_rb_api_append_i64": ("v", ("p", "i32", "i64")),
    "irx_rb_api_get_i64": ("i64", ("p", "i32", "i64")),
    "irx_rb_api_append_f32": ("v", ("p", "i32", "f32")),
    "irx_rb_api_get_f32": ("f32", ("p", "i32", "i64")),
    "irx_rb_api_append_f64": ("v", ("p", "i32", "f64")),
    "irx_rb_api_get_f64": ("f64", ("p", "i32", "i64")),
    "irx_rb_api_append_bool": ("v", ("p", "i32", "i32")),
    "irx_rb_api_get_bool": ("i32", ("p", "i32", "i64")),
    "irx_rb_api_append_date": ("v", ("p", "i32", "i64")),
    "irx_rb_api_get_date": ("i64", ("p", "i32", "i64")),
    "irx_rb_api_append_timestamp": ("v", ("p", "i32", "i64")),
    "irx_rb_api_get_timestamp": ("i64", ("p", "i32", "i64")),
    "irx_rb_api_append_time": ("v", ("p", "i32", "i64")),
    "irx_rb_api_get_time": ("i64", ("p", "i32", "i64")),
    "irx_rb_api_append_utf8": ("v", ("p", "i32", "p")),
    "irx_rb_api_get_utf8": ("p", ("p", "i32", "i64")),
    "irx_rb_api_append_null": ("v", ("p", "i32")),
    "irx_rb_api_reader_file": ("v", ("p", "p")),
    "irx_rb_api_reader_stream": ("v", ("p", "p")),
    "irx_rb_api_reader_tcp": ("v", ("p", "p", "i32", "i32")),
    "irx_rb_api_writer_file": ("v", ("p", "p")),
    "irx_rb_api_writer_stream": ("v", ("p", "p")),
    "irx_rb_api_writer_tcp": ("v", ("p", "p", "i32", "i32")),
    "irx_rb_api_writer_write": ("v", ("p", "p")),
    "irx_rb_api_reader_next": ("i32", ("p",)),
    "irx_rb_api_reader_batch": ("v", ("p", "p")),
    "irx_rb_api_reader_schema": ("v", ("p", "p")),
    "irx_rb_api_batch_export_stream": ("i32", ("p", "i64")),
    "irx_rb_api_batch_export": ("i32", ("p", "i64", "i64")),
    "irx_rb_api_batch_import": ("v", ("p", "i64", "i64")),
    "irx_rb_api_reader_import": ("v", ("p", "i64")),
}

# Unified format facade symbols use the same registered RecordBatch feature.
ARROW_API_SIGNATURES.update(
    {
        "irx_rb_api_parquet_new": ("p", ()),
        "irx_rb_api_parquet_destroy": ("v", ("p",)),
        "irx_rb_api_parquet_close": ("v", ("p",)),
        "irx_rb_api_parquet_next": ("i32", ("p",)),
        "irx_rb_api_parquet_batch": ("v", ("p", "p")),
        "irx_rb_api_parquet_schema": ("v", ("p", "p")),
        "irx_rb_api_parquet_write": ("v", ("p", "p")),
        "irx_rb_api_parquet_open_read": ("v", ("p", "p", "i64")),
        "irx_rb_api_parquet_open_read_as": ("v", ("p", "p", "p", "i64")),
        "irx_rb_api_parquet_open_write": ("v", ("p", "p", "p", "p", "i64")),
        "irx_rb_api_csv_new": ("p", ()),
        "irx_rb_api_csv_destroy": ("v", ("p",)),
        "irx_rb_api_csv_close": ("v", ("p",)),
        "irx_rb_api_csv_next": ("i32", ("p",)),
        "irx_rb_api_csv_batch": ("v", ("p", "p")),
        "irx_rb_api_csv_schema": ("v", ("p", "p")),
        "irx_rb_api_csv_write": ("v", ("p", "p")),
        "irx_rb_api_csv_open_read": ("v", ("p", "p", "p", "i32", "i32")),
        "irx_rb_api_csv_open_read_as": (
            "v",
            ("p", "p", "p", "p", "i32", "i32"),
        ),
        "irx_rb_api_csv_open_write": ("v", ("p", "p", "p", "p", "i32")),
    }
)

ARROW_API_SIGNATURES.update(
    {
        "irx_rb_api_options_new": ("p", ()),
        "irx_rb_api_options_destroy": ("v", ("p",)),
        "irx_rb_api_options_int": ("v", ("p", "p", "i64")),
        "irx_rb_api_options_text": ("v", ("p", "p", "p")),
        "irx_rb_api_parquet_read_options": ("v", ("p", "p", "p")),
        "irx_rb_api_parquet_write_options": ("v", ("p", "p", "p", "p")),
        "irx_rb_api_append_u8": ("v", ("p", "i32", "i8")),
        "irx_rb_api_get_u8": ("i8", ("p", "i32", "i64")),
        "irx_rb_api_append_u16": ("v", ("p", "i32", "i16")),
        "irx_rb_api_get_u16": ("i16", ("p", "i32", "i64")),
        "irx_rb_api_append_u32": ("v", ("p", "i32", "i32")),
        "irx_rb_api_get_u32": ("i32", ("p", "i32", "i64")),
        "irx_rb_api_append_u64": ("v", ("p", "i32", "i64")),
        "irx_rb_api_get_u64": ("i64", ("p", "i32", "i64")),
    }
)

ARROW_API_SIGNATURES.update(
    {
        "irx_rb_api_schema_add_name": ("v", ("p", "p", "p", "i32")),
        "irx_rb_api_table_cast": ("p", ("p", "p")),
        "irx_rb_api_csv_options_new": ("p", ()),
        "irx_rb_api_csv_options_destroy": ("v", ("p",)),
        "irx_rb_api_csv_options_int": ("v", ("p", "p", "i64")),
        "irx_rb_api_csv_options_text": ("v", ("p", "p", "p")),
        "irx_rb_api_csv_options_clear": ("v", ("p", "p")),
        "irx_rb_api_read_csv": ("p", ("p", "p", "p")),
        "irx_rb_api_write_csv": ("v", ("p", "p", "p")),
        "irx_rb_api_read_parquet": ("p", ("p", "p", "p", "i32")),
        "irx_rb_api_write_parquet": ("v", ("p", "p", "p", "i32")),
        "irx_rb_api_options_copy": ("p", ("p",)),
        "irx_rb_api_options_clear": ("v", ("p", "p")),
        "irx_rb_api_options_filters": ("v", ("p", "p")),
        "irx_rb_api_filter_i64": ("v", ("p", "p", "p", "p", "i64")),
        "irx_rb_api_filter_f64": ("v", ("p", "p", "p", "p", "f64")),
        "irx_rb_api_filter_bool": ("v", ("p", "p", "p", "p", "i32")),
        "irx_rb_api_filter_text": ("v", ("p", "p", "p", "p", "p")),
        "irx_rb_api_filter_null": ("v", ("p", "p", "p", "p")),
        "irx_rb_api_csv_frame": ("p", ("p",)),
        "irx_rb_api_parquet_frame": ("p", ("p",)),
        "irx_rb_api_csv_write_frame": ("v", ("p", "p")),
        "irx_rb_api_parquet_write_frame": ("v", ("p", "p")),
    }
)

# Opening/configuration activates the optional format implementation. Shared
# lifetime operations remain in the base RecordBatch runtime.
PARQUET_API_SYMBOLS = frozenset(
    name
    for name in ARROW_API_SIGNATURES
    if name.startswith("irx_rb_api_options_")
    or name.startswith("irx_rb_api_parquet_open_")
    or name.startswith("irx_rb_api_filter_")
    or name in {"irx_rb_api_read_parquet", "irx_rb_api_write_parquet"}
    or name
    in {"irx_rb_api_parquet_read_options", "irx_rb_api_parquet_write_options"}
)
