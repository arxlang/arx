"""
title: Generated LLVM declarations for the Arrow runtime ABI.
summary: Do not edit; regenerate from abi.json.
"""

from __future__ import annotations

LLVM_RUNTIME_FEATURE_IDS = {
    "core": 1,
    "array": 2,
    "tensor": 3,
    "dataframe": 4,
    "record_batch": 5,
}
LLVM_RUNTIME_FEATURE_VERSIONS = {
    "core": 65536,
    "array": 67072,
    "tensor": 65536,
    "dataframe": 66048,
    "record_batch": 65536,
}
LLVM_HANDLE_TYPES = (
    "error",
    "type",
    "schema",
    "scalar",
    "array_builder",
    "array",
    "chunked_array",
    "record_batch",
    "table",
    "tensor_builder",
    "tensor",
    "stream",
    "dataset",
    "execution_plan",
    "field",
    "c_data",
)
LLVM_SIGNATURES: dict[str, tuple[str, tuple[str, ...]]] = {
    "irx_arrow_abi_version": (
        "uint32",
        (),
    ),
    "irx_arrow_runtime_has_feature": (
        "status",
        (
            "runtime_feature_id",
            "uint32",
            "int32_pointer",
            "uint32_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_status_get_category": (
        "status_category",
        ("status",),
    ),
    "irx_arrow_handle_kind_of": (
        "status",
        (
            "const_void",
            "handle_kind_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_handle_ownership_of": (
        "status",
        (
            "const_void",
            "ownership_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_error_snapshot": (
        "status",
        (
            "error_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_error_code": (
        "status",
        (
            "const_error",
            "status_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_error_operation": (
        "status",
        (
            "const_error",
            "c_string_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_error_message": (
        "status",
        (
            "const_error",
            "c_string_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_error_upstream_detail": (
        "status",
        (
            "const_error",
            "c_string_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_error_retain": (
        "status",
        (
            "const_error",
            "error_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_error_release": (
        "status",
        (
            "error_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_schema_import_copy": (
        "status",
        (
            "const_arrow_schema",
            "schema_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_schema_export": (
        "status",
        (
            "const_schema",
            "arrow_schema",
            "error_pointer",
        ),
    ),
    "irx_arrow_schema_type_id": (
        "status",
        (
            "const_schema",
            "int32_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_schema_is_nullable": (
        "status",
        (
            "const_schema",
            "int32_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_schema_retain": (
        "status",
        (
            "const_schema",
            "schema_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_schema_release": (
        "status",
        (
            "schema_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_builder_new": (
        "status",
        (
            "int32",
            "array_builder_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_builder_append_null": (
        "status",
        (
            "array_builder",
            "int64",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_builder_append_int": (
        "status",
        (
            "array_builder",
            "int64",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_builder_append_uint": (
        "status",
        (
            "array_builder",
            "uint64",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_builder_append_double": (
        "status",
        (
            "array_builder",
            "double",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_builder_int32_new": (
        "status",
        (
            "array_builder_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_builder_append_int32": (
        "status",
        (
            "array_builder",
            "int32",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_builder_finish": (
        "status",
        (
            "array_builder_pointer",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_builder_release": (
        "status",
        (
            "array_builder_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_length": (
        "status",
        (
            "const_array",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_offset": (
        "status",
        (
            "const_array",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_null_count": (
        "status",
        (
            "const_array",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_type_id": (
        "status",
        (
            "const_array",
            "int32_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_is_nullable": (
        "status",
        (
            "const_array",
            "int32_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_has_validity_bitmap": (
        "status",
        (
            "const_array",
            "int32_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_can_borrow_buffer_view": (
        "status",
        (
            "const_array",
            "int32_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_schema_copy": (
        "status",
        (
            "const_array",
            "schema_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_export": (
        "status",
        (
            "const_array",
            "arrow_array",
            "arrow_schema",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_import": (
        "status",
        (
            "const_arrow_array",
            "const_arrow_schema",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_import_copy": (
        "status",
        (
            "const_arrow_array",
            "const_arrow_schema",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_import_move": (
        "status",
        (
            "arrow_array",
            "arrow_schema",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_validity_bitmap": (
        "status",
        (
            "const_array",
            "const_void_pointer",
            "int64_pointer",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_borrow_buffer_view": (
        "status",
        (
            "const_array",
            "buffer_view",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_retain": (
        "status",
        (
            "const_array",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_release": (
        "status",
        (
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_record_batch_import_move": (
        "status",
        (
            "arrow_array",
            "arrow_schema",
            "record_batch_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_record_batch_export": (
        "status",
        (
            "const_record_batch",
            "arrow_array",
            "arrow_schema",
            "error_pointer",
        ),
    ),
    "irx_arrow_record_batch_num_rows": (
        "status",
        (
            "const_record_batch",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_record_batch_num_columns": (
        "status",
        (
            "const_record_batch",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_record_batch_retain": (
        "status",
        (
            "const_record_batch",
            "record_batch_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_record_batch_release": (
        "status",
        (
            "record_batch_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_tensor_builder_new": (
        "status",
        (
            "int32",
            "int32",
            "const_int64_pointer",
            "const_int64_pointer",
            "tensor_builder_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_tensor_builder_append_int": (
        "status",
        (
            "tensor_builder",
            "int64",
            "error_pointer",
        ),
    ),
    "irx_arrow_tensor_builder_append_uint": (
        "status",
        (
            "tensor_builder",
            "uint64",
            "error_pointer",
        ),
    ),
    "irx_arrow_tensor_builder_append_double": (
        "status",
        (
            "tensor_builder",
            "double",
            "error_pointer",
        ),
    ),
    "irx_arrow_tensor_builder_finish": (
        "status",
        (
            "tensor_builder_pointer",
            "tensor_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_tensor_builder_release": (
        "status",
        (
            "tensor_builder_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_tensor_type_id": (
        "status",
        (
            "const_tensor",
            "int32_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_tensor_ndim": (
        "status",
        (
            "const_tensor",
            "int32_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_tensor_size": (
        "status",
        (
            "const_tensor",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_tensor_shape": (
        "status",
        (
            "const_tensor",
            "const_int64_output",
            "error_pointer",
        ),
    ),
    "irx_arrow_tensor_strides": (
        "status",
        (
            "const_tensor",
            "const_int64_output",
            "error_pointer",
        ),
    ),
    "irx_arrow_tensor_borrow_buffer_view": (
        "status",
        (
            "const_tensor",
            "buffer_view",
            "error_pointer",
        ),
    ),
    "irx_arrow_tensor_retain": (
        "status",
        (
            "const_tensor",
            "tensor_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_tensor_release": (
        "status",
        (
            "tensor_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_new_from_arrays": (
        "status",
        (
            "int64",
            "c_string_pointer",
            "array_pointer",
            "table_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_num_rows": (
        "status",
        (
            "const_table",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_num_columns": (
        "status",
        (
            "const_table",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_column_by_name": (
        "status",
        (
            "const_table",
            "c_string",
            "chunked_array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_column_by_index": (
        "status",
        (
            "const_table",
            "int32",
            "chunked_array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_retain": (
        "status",
        (
            "const_table",
            "table_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_release": (
        "status",
        (
            "table_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_chunked_array_retain": (
        "status",
        (
            "const_chunked_array",
            "chunked_array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_chunked_array_release": (
        "status",
        (
            "chunked_array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_tensor_release_callback": (
        "void",
        ("void_pointer",),
    ),
    "irx_arrow_last_error": (
        "c_string",
        (),
    ),
    "irx_arrow_type_import_copy": (
        "status",
        (
            "const_arrow_schema",
            "type_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_type_export": (
        "status",
        (
            "const_type",
            "arrow_schema",
            "error_pointer",
        ),
    ),
    "irx_arrow_type_retain": (
        "status",
        (
            "const_type",
            "type_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_type_release": (
        "status",
        (
            "type_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_field_import_copy": (
        "status",
        (
            "const_arrow_schema",
            "field_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_field_export": (
        "status",
        (
            "const_field",
            "arrow_schema",
            "error_pointer",
        ),
    ),
    "irx_arrow_field_retain": (
        "status",
        (
            "const_field",
            "field_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_field_release": (
        "status",
        (
            "field_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_type_equals": (
        "status",
        (
            "const_type",
            "const_type",
            "int32_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_field_equals": (
        "status",
        (
            "const_field",
            "const_field",
            "int32_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_schema_equals": (
        "status",
        (
            "const_schema",
            "const_schema",
            "int32_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_type_num_fields": (
        "status",
        (
            "const_type",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_type_field": (
        "status",
        (
            "const_type",
            "int64",
            "field_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_schema_num_fields": (
        "status",
        (
            "const_schema",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_schema_field": (
        "status",
        (
            "const_schema",
            "int64",
            "field_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_field_type": (
        "status",
        (
            "const_field",
            "type_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_field_nullable": (
        "status",
        (
            "const_field",
            "int32_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_type_bit_width": (
        "status",
        (
            "const_type",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_field_name_copy": (
        "status",
        (
            "const_field",
            "c_string_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_get_int": (
        "status",
        (
            "const_array",
            "int64",
            "int32_pointer",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_get_uint": (
        "status",
        (
            "const_array",
            "int64",
            "int32_pointer",
            "uint64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_get_double": (
        "status",
        (
            "const_array",
            "int64",
            "int32_pointer",
            "double_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_slice": (
        "status",
        (
            "const_array",
            "int64",
            "int64",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_concat": (
        "status",
        (
            "const_array",
            "const_array",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_copy": (
        "status",
        (
            "const_array",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_equal": (
        "status",
        (
            "const_array",
            "const_array",
            "int32_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_builder_finish_typed": (
        "status",
        (
            "array_builder_pointer",
            "int32",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_builder_reserve": (
        "status",
        (
            "array_builder",
            "int64",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_builder_length": (
        "status",
        (
            "const_array_builder",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_builder_build": (
        "status",
        (
            "array_builder",
            "int32",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_chunked_new": (
        "status",
        (
            "int32",
            "int32",
            "const_void_pointer",
            "int64",
            "chunked_array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_chunked_length": (
        "status",
        (
            "const_chunked_array",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_chunked_null_count": (
        "status",
        (
            "const_chunked_array",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_chunked_num_chunks": (
        "status",
        (
            "const_chunked_array",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_chunked_get_int": (
        "status",
        (
            "const_chunked_array",
            "int64",
            "int32_pointer",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_chunked_get_uint": (
        "status",
        (
            "const_chunked_array",
            "int64",
            "int32_pointer",
            "uint64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_chunked_get_double": (
        "status",
        (
            "const_chunked_array",
            "int64",
            "int32_pointer",
            "double_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_chunked_chunk": (
        "status",
        (
            "const_chunked_array",
            "int64",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_chunked_combine": (
        "status",
        (
            "const_chunked_array",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_chunked_slice": (
        "status",
        (
            "const_chunked_array",
            "int64",
            "int64",
            "chunked_array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_chunked_copy": (
        "status",
        (
            "const_chunked_array",
            "chunked_array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_chunked_concat": (
        "status",
        (
            "const_chunked_array",
            "const_chunked_array",
            "chunked_array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_chunked_equal": (
        "status",
        (
            "const_chunked_array",
            "const_chunked_array",
            "int32_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_batch_new_typed": (
        "status",
        (
            "const_schema",
            "const_void_pointer",
            "int64",
            "int64",
            "record_batch_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_batch_rows": (
        "status",
        (
            "const_record_batch",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_batch_columns": (
        "status",
        (
            "const_record_batch",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_batch_schema": (
        "status",
        (
            "const_record_batch",
            "schema_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_batch_column_checked": (
        "status",
        (
            "const_record_batch",
            "int64",
            "const_field",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_batch_slice": (
        "status",
        (
            "const_record_batch",
            "int64",
            "int64",
            "record_batch_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_batch_select": (
        "status",
        (
            "const_record_batch",
            "const_int64_pointer",
            "int64",
            "record_batch_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_batch_with_schema": (
        "status",
        (
            "const_record_batch",
            "const_schema",
            "record_batch_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_batch_set_column": (
        "status",
        (
            "const_record_batch",
            "int64",
            "const_field",
            "const_array",
            "record_batch_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_batch_remove": (
        "status",
        (
            "const_record_batch",
            "int64",
            "record_batch_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_new_typed": (
        "status",
        (
            "const_schema",
            "const_void_pointer",
            "int64",
            "int64",
            "table_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_rows": (
        "status",
        (
            "const_table",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_columns": (
        "status",
        (
            "const_table",
            "int64_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_schema": (
        "status",
        (
            "const_table",
            "schema_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_column_checked": (
        "status",
        (
            "const_table",
            "int64",
            "const_field",
            "chunked_array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_slice": (
        "status",
        (
            "const_table",
            "int64",
            "int64",
            "table_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_select": (
        "status",
        (
            "const_table",
            "const_int64_pointer",
            "int64",
            "table_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_with_schema": (
        "status",
        (
            "const_table",
            "const_schema",
            "table_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_set_column": (
        "status",
        (
            "const_table",
            "int64",
            "const_field",
            "const_chunked_array",
            "table_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_remove": (
        "status",
        (
            "const_table",
            "int64",
            "table_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_batch_to_table": (
        "status",
        (
            "const_record_batch",
            "table_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_to_batch": (
        "status",
        (
            "const_table",
            "record_batch_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_combine": (
        "status",
        (
            "const_table",
            "table_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_scalar_retain": (
        "status",
        (
            "const_scalar",
            "scalar_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_scalar_release": (
        "status",
        (
            "scalar_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_scalar_parse": (
        "status",
        (
            "const_type",
            "c_string",
            "scalar_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_scalar_from_array": (
        "status",
        (
            "const_type",
            "const_array",
            "scalar_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_scalar_from_fields": (
        "status",
        (
            "const_type",
            "const_void_pointer",
            "int64",
            "scalar_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_scalar_dictionary": (
        "status",
        (
            "const_type",
            "const_scalar",
            "const_array",
            "scalar_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_scalar_wrap": (
        "status",
        (
            "const_type",
            "const_scalar",
            "scalar_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_scalar_union": (
        "status",
        (
            "const_type",
            "c_string",
            "const_scalar",
            "scalar_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_scalar_interval": (
        "status",
        (
            "const_type",
            "const_int64_pointer",
            "int64",
            "scalar_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_scalar_equal": (
        "status",
        (
            "const_scalar",
            "const_scalar",
            "int32_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_scalar_text": (
        "status",
        (
            "const_scalar",
            "c_string_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_scalar_values": (
        "status",
        (
            "const_scalar",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_scalar_field": (
        "status",
        (
            "const_scalar",
            "c_string",
            "scalar_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_get_scalar": (
        "status",
        (
            "const_array",
            "int64",
            "scalar_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_chunked_get_scalar": (
        "status",
        (
            "const_chunked_array",
            "int64",
            "scalar_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_builder_new_logical": (
        "status",
        (
            "const_type",
            "array_builder_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_builder_append_scalar": (
        "status",
        (
            "array_builder",
            "const_scalar",
            "error_pointer",
        ),
    ),
    "irx_arrow_chunked_new_logical": (
        "status",
        (
            "const_type",
            "int32",
            "const_void_pointer",
            "int64",
            "chunked_array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_scalar_from_bytes": (
        "status",
        (
            "const_type",
            "const_array",
            "scalar_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_scalar_bytes": (
        "status",
        (
            "const_scalar",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_batch_take": (
        "status",
        (
            "const_record_batch",
            "const_array",
            "record_batch_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_table_take": (
        "status",
        (
            "const_table",
            "const_array",
            "table_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_from_buffer": (
        "status",
        (
            "int32",
            "buffer_view",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_c_data_retain": (
        "status",
        (
            "const_c_data",
            "c_data_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_c_data_release": (
        "status",
        (
            "c_data_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_c_data_from_array": (
        "status",
        (
            "const_array",
            "c_data_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_c_data_import_move": (
        "status",
        (
            "arrow_array",
            "arrow_schema",
            "c_data_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_c_data_export": (
        "status",
        (
            "const_c_data",
            "arrow_array",
            "arrow_schema",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_from_c_data": (
        "status",
        (
            "const_c_data",
            "const_field",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_with_validity": (
        "status",
        (
            "const_array",
            "const_array",
            "int64",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_array_from_buffers": (
        "status",
        (
            "const_field",
            "const_array",
            "const_array",
            "int64",
            "int64",
            "array_pointer",
            "error_pointer",
        ),
    ),
    "irx_arrow_scalar_storage": (
        "status",
        (
            "const_scalar",
            "scalar_pointer",
            "error_pointer",
        ),
    ),
}
LLVM_FEATURE_SYMBOLS: dict[str, tuple[str, ...]] = {
    "core": (
        "irx_arrow_abi_version",
        "irx_arrow_runtime_has_feature",
        "irx_arrow_status_get_category",
        "irx_arrow_handle_kind_of",
        "irx_arrow_handle_ownership_of",
        "irx_arrow_error_snapshot",
        "irx_arrow_error_code",
        "irx_arrow_error_operation",
        "irx_arrow_error_message",
        "irx_arrow_error_upstream_detail",
        "irx_arrow_error_retain",
        "irx_arrow_error_release",
        "irx_arrow_last_error",
    ),
    "array": (
        "irx_arrow_schema_import_copy",
        "irx_arrow_schema_export",
        "irx_arrow_schema_type_id",
        "irx_arrow_schema_is_nullable",
        "irx_arrow_schema_retain",
        "irx_arrow_schema_release",
        "irx_arrow_array_builder_new",
        "irx_arrow_array_builder_append_null",
        "irx_arrow_array_builder_append_int",
        "irx_arrow_array_builder_append_uint",
        "irx_arrow_array_builder_append_double",
        "irx_arrow_array_builder_int32_new",
        "irx_arrow_array_builder_append_int32",
        "irx_arrow_array_builder_finish",
        "irx_arrow_array_builder_release",
        "irx_arrow_array_length",
        "irx_arrow_array_offset",
        "irx_arrow_array_null_count",
        "irx_arrow_array_type_id",
        "irx_arrow_array_is_nullable",
        "irx_arrow_array_has_validity_bitmap",
        "irx_arrow_array_can_borrow_buffer_view",
        "irx_arrow_array_schema_copy",
        "irx_arrow_array_export",
        "irx_arrow_array_import",
        "irx_arrow_array_import_copy",
        "irx_arrow_array_import_move",
        "irx_arrow_array_validity_bitmap",
        "irx_arrow_array_borrow_buffer_view",
        "irx_arrow_array_retain",
        "irx_arrow_array_release",
        "irx_arrow_type_import_copy",
        "irx_arrow_type_export",
        "irx_arrow_type_retain",
        "irx_arrow_type_release",
        "irx_arrow_field_import_copy",
        "irx_arrow_field_export",
        "irx_arrow_field_retain",
        "irx_arrow_field_release",
        "irx_arrow_type_equals",
        "irx_arrow_field_equals",
        "irx_arrow_schema_equals",
        "irx_arrow_type_num_fields",
        "irx_arrow_type_field",
        "irx_arrow_schema_num_fields",
        "irx_arrow_schema_field",
        "irx_arrow_field_type",
        "irx_arrow_field_nullable",
        "irx_arrow_type_bit_width",
        "irx_arrow_field_name_copy",
        "irx_arrow_array_get_int",
        "irx_arrow_array_get_uint",
        "irx_arrow_array_get_double",
        "irx_arrow_array_slice",
        "irx_arrow_array_concat",
        "irx_arrow_array_copy",
        "irx_arrow_array_equal",
        "irx_arrow_array_builder_finish_typed",
        "irx_arrow_array_builder_reserve",
        "irx_arrow_array_builder_length",
        "irx_arrow_array_builder_build",
        "irx_arrow_chunked_new",
        "irx_arrow_chunked_length",
        "irx_arrow_chunked_null_count",
        "irx_arrow_chunked_num_chunks",
        "irx_arrow_chunked_get_int",
        "irx_arrow_chunked_get_uint",
        "irx_arrow_chunked_get_double",
        "irx_arrow_chunked_chunk",
        "irx_arrow_chunked_combine",
        "irx_arrow_chunked_slice",
        "irx_arrow_chunked_copy",
        "irx_arrow_chunked_concat",
        "irx_arrow_chunked_equal",
        "irx_arrow_scalar_retain",
        "irx_arrow_scalar_release",
        "irx_arrow_scalar_parse",
        "irx_arrow_scalar_from_array",
        "irx_arrow_scalar_from_fields",
        "irx_arrow_scalar_dictionary",
        "irx_arrow_scalar_wrap",
        "irx_arrow_scalar_union",
        "irx_arrow_scalar_interval",
        "irx_arrow_scalar_equal",
        "irx_arrow_scalar_text",
        "irx_arrow_scalar_values",
        "irx_arrow_scalar_field",
        "irx_arrow_array_get_scalar",
        "irx_arrow_chunked_get_scalar",
        "irx_arrow_array_builder_new_logical",
        "irx_arrow_array_builder_append_scalar",
        "irx_arrow_chunked_new_logical",
        "irx_arrow_scalar_from_bytes",
        "irx_arrow_scalar_bytes",
        "irx_arrow_array_from_buffer",
        "irx_arrow_c_data_retain",
        "irx_arrow_c_data_release",
        "irx_arrow_c_data_from_array",
        "irx_arrow_c_data_import_move",
        "irx_arrow_c_data_export",
        "irx_arrow_array_from_c_data",
        "irx_arrow_array_with_validity",
        "irx_arrow_array_from_buffers",
        "irx_arrow_scalar_storage",
    ),
    "tensor": (
        "irx_arrow_tensor_builder_new",
        "irx_arrow_tensor_builder_append_int",
        "irx_arrow_tensor_builder_append_uint",
        "irx_arrow_tensor_builder_append_double",
        "irx_arrow_tensor_builder_finish",
        "irx_arrow_tensor_builder_release",
        "irx_arrow_tensor_type_id",
        "irx_arrow_tensor_ndim",
        "irx_arrow_tensor_size",
        "irx_arrow_tensor_shape",
        "irx_arrow_tensor_strides",
        "irx_arrow_tensor_borrow_buffer_view",
        "irx_arrow_tensor_retain",
        "irx_arrow_tensor_release",
        "irx_arrow_tensor_release_callback",
    ),
    "dataframe": (
        "irx_arrow_table_new_from_arrays",
        "irx_arrow_table_num_rows",
        "irx_arrow_table_num_columns",
        "irx_arrow_table_column_by_name",
        "irx_arrow_table_column_by_index",
        "irx_arrow_table_retain",
        "irx_arrow_table_release",
        "irx_arrow_chunked_array_retain",
        "irx_arrow_chunked_array_release",
        "irx_arrow_batch_new_typed",
        "irx_arrow_batch_rows",
        "irx_arrow_batch_columns",
        "irx_arrow_batch_schema",
        "irx_arrow_batch_column_checked",
        "irx_arrow_batch_slice",
        "irx_arrow_batch_select",
        "irx_arrow_batch_with_schema",
        "irx_arrow_batch_set_column",
        "irx_arrow_batch_remove",
        "irx_arrow_table_new_typed",
        "irx_arrow_table_rows",
        "irx_arrow_table_columns",
        "irx_arrow_table_schema",
        "irx_arrow_table_column_checked",
        "irx_arrow_table_slice",
        "irx_arrow_table_select",
        "irx_arrow_table_with_schema",
        "irx_arrow_table_set_column",
        "irx_arrow_table_remove",
        "irx_arrow_batch_to_table",
        "irx_arrow_table_to_batch",
        "irx_arrow_table_combine",
        "irx_arrow_batch_take",
        "irx_arrow_table_take",
    ),
    "record_batch": (
        "irx_arrow_record_batch_import_move",
        "irx_arrow_record_batch_export",
        "irx_arrow_record_batch_num_rows",
        "irx_arrow_record_batch_num_columns",
        "irx_arrow_record_batch_retain",
        "irx_arrow_record_batch_release",
    ),
}

__all__ = [
    "LLVM_FEATURE_SYMBOLS",
    "LLVM_HANDLE_TYPES",
    "LLVM_RUNTIME_FEATURE_IDS",
    "LLVM_RUNTIME_FEATURE_VERSIONS",
    "LLVM_SIGNATURES",
]
