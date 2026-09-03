// Copyright IRx contributors.

#ifndef IRX_ARROW_RUNTIME_H_INCLUDED
#define IRX_ARROW_RUNTIME_H_INCLUDED

#include <stddef.h>
#include <stdint.h>

#include "irx_arrow_c_abi.h"
#include "irx_buffer_runtime.h"

#ifdef __cplusplus
extern "C" {
#endif

#define IRX_ARROW_ABI_VERSION_MAJOR UINT32_C(1)
#define IRX_ARROW_ABI_VERSION_MINOR UINT32_C(0)
#define IRX_ARROW_ABI_VERSION_PATCH UINT32_C(0)
#define IRX_ARROW_ABI_VERSION                                                  \
  ((IRX_ARROW_ABI_VERSION_MAJOR << 16) | (IRX_ARROW_ABI_VERSION_MINOR << 8) |  \
   IRX_ARROW_ABI_VERSION_PATCH)

/* Stable status values are Arx-owned and append-only. They must not expose
 * errno or arrow::StatusCode values across the ABI. OK and END_OF_STREAM are
 * non-errors; every other status requires an error-detail record. */
typedef int32_t irx_arrow_status;
enum irx_arrow_status_code {
  IRX_ARROW_STATUS_OK = 0,
  IRX_ARROW_STATUS_END_OF_STREAM = 1,
  IRX_ARROW_STATUS_INVALID_ARGUMENT = 100,
  IRX_ARROW_STATUS_NULL_POINTER = 101,
  IRX_ARROW_STATUS_INVALID_STATE = 102,
  IRX_ARROW_STATUS_TYPE_MISMATCH = 103,
  IRX_ARROW_STATUS_SCHEMA_MISMATCH = 104,
  IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS = 105,
  IRX_ARROW_STATUS_OVERFLOW = 106,
  IRX_ARROW_STATUS_NOT_SUPPORTED = 107,
  IRX_ARROW_STATUS_ABI_MISMATCH = 108,
  IRX_ARROW_STATUS_OUT_OF_MEMORY = 200,
  IRX_ARROW_STATUS_RESOURCE_EXHAUSTED = 201,
  IRX_ARROW_STATUS_IO_ERROR = 300,
  IRX_ARROW_STATUS_CANCELLED = 301,
  IRX_ARROW_STATUS_ARROW_ERROR = 400,
  IRX_ARROW_STATUS_INTERNAL = 401,
};

typedef int32_t irx_arrow_status_category;
enum irx_arrow_status_category_code {
  IRX_ARROW_STATUS_CATEGORY_SUCCESS = 0,
  IRX_ARROW_STATUS_CATEGORY_CONTROL = 1,
  IRX_ARROW_STATUS_CATEGORY_INVALID = 2,
  IRX_ARROW_STATUS_CATEGORY_RESOURCE = 3,
  IRX_ARROW_STATUS_CATEGORY_IO = 4,
  IRX_ARROW_STATUS_CATEGORY_INTERNAL = 5,
  IRX_ARROW_STATUS_CATEGORY_UNKNOWN = 6,
};

typedef struct irx_arrow_schema_handle irx_arrow_schema_handle;
typedef struct irx_arrow_array_builder_handle irx_arrow_array_builder_handle;
typedef struct irx_arrow_array_handle irx_arrow_array_handle;
typedef struct irx_arrow_tensor_builder_handle irx_arrow_tensor_builder_handle;
typedef struct irx_arrow_tensor_handle irx_arrow_tensor_handle;
typedef struct irx_arrow_table_handle irx_arrow_table_handle;
typedef struct irx_arrow_chunked_array_handle irx_arrow_chunked_array_handle;

enum irx_arrow_type_id {
  IRX_ARROW_TYPE_UNKNOWN = 0,
  IRX_ARROW_TYPE_INT32 = 1,
  IRX_ARROW_TYPE_INT8 = 2,
  IRX_ARROW_TYPE_INT16 = 3,
  IRX_ARROW_TYPE_INT64 = 4,
  IRX_ARROW_TYPE_UINT8 = 5,
  IRX_ARROW_TYPE_UINT16 = 6,
  IRX_ARROW_TYPE_UINT32 = 7,
  IRX_ARROW_TYPE_UINT64 = 8,
  IRX_ARROW_TYPE_FLOAT32 = 9,
  IRX_ARROW_TYPE_FLOAT64 = 10,
  IRX_ARROW_TYPE_BOOL = 11,
};

uint32_t irx_arrow_abi_version(void);
irx_arrow_status_category irx_arrow_status_get_category(
    irx_arrow_status status);

irx_arrow_status irx_arrow_schema_import_copy(
    const struct ArrowSchema* schema,
    irx_arrow_schema_handle** out_schema);
irx_arrow_status irx_arrow_schema_export(
    const irx_arrow_schema_handle* schema,
    struct ArrowSchema* out_schema);
int32_t irx_arrow_schema_type_id(const irx_arrow_schema_handle* schema);
int32_t irx_arrow_schema_is_nullable(const irx_arrow_schema_handle* schema);
irx_arrow_status irx_arrow_schema_retain(irx_arrow_schema_handle* schema);
void irx_arrow_schema_release(irx_arrow_schema_handle* schema);

irx_arrow_status irx_arrow_array_builder_new(
    int32_t type_id,
    irx_arrow_array_builder_handle** out_builder);
irx_arrow_status irx_arrow_array_builder_append_null(
    irx_arrow_array_builder_handle* builder,
    int64_t count);
irx_arrow_status irx_arrow_array_builder_append_int(
    irx_arrow_array_builder_handle* builder,
    int64_t value);
irx_arrow_status irx_arrow_array_builder_append_uint(
    irx_arrow_array_builder_handle* builder,
    uint64_t value);
irx_arrow_status irx_arrow_array_builder_append_double(
    irx_arrow_array_builder_handle* builder,
    double value);

irx_arrow_status irx_arrow_array_builder_int32_new(
    irx_arrow_array_builder_handle** out_builder);
irx_arrow_status irx_arrow_array_builder_append_int32(
    irx_arrow_array_builder_handle* builder, int32_t value);
irx_arrow_status irx_arrow_array_builder_finish(
    irx_arrow_array_builder_handle* builder,
    irx_arrow_array_handle** out_array);
void irx_arrow_array_builder_release(irx_arrow_array_builder_handle* builder);

int64_t irx_arrow_array_length(const irx_arrow_array_handle* array);
int64_t irx_arrow_array_offset(const irx_arrow_array_handle* array);
int64_t irx_arrow_array_null_count(const irx_arrow_array_handle* array);
int32_t irx_arrow_array_type_id(const irx_arrow_array_handle* array);
int32_t irx_arrow_array_is_nullable(const irx_arrow_array_handle* array);
int32_t irx_arrow_array_has_validity_bitmap(
    const irx_arrow_array_handle* array);
int32_t irx_arrow_array_can_borrow_buffer_view(
    const irx_arrow_array_handle* array);

irx_arrow_status irx_arrow_array_schema_copy(
    const irx_arrow_array_handle* array,
    irx_arrow_schema_handle** out_schema);

irx_arrow_status irx_arrow_array_export(
    const irx_arrow_array_handle* array,
    struct ArrowArray* out_array,
    struct ArrowSchema* out_schema);
irx_arrow_status irx_arrow_array_import(
    const struct ArrowArray* array,
    const struct ArrowSchema* schema,
    irx_arrow_array_handle** out_array);
irx_arrow_status irx_arrow_array_import_copy(
    const struct ArrowArray* array,
    const struct ArrowSchema* schema,
    irx_arrow_array_handle** out_array);
irx_arrow_status irx_arrow_array_import_move(
    struct ArrowArray* array,
    struct ArrowSchema* schema,
    irx_arrow_array_handle** out_array);

irx_arrow_status irx_arrow_array_validity_bitmap(
    const irx_arrow_array_handle* array,
    const void** out_data,
    int64_t* out_offset_bits,
    int64_t* out_length_bits);
irx_arrow_status irx_arrow_array_borrow_buffer_view(
    const irx_arrow_array_handle* array,
    irx_buffer_view* out_view);

irx_arrow_status irx_arrow_array_retain(irx_arrow_array_handle* array);
void irx_arrow_array_release(irx_arrow_array_handle* array);

irx_arrow_status irx_arrow_tensor_builder_new(
    int32_t type_id,
    int32_t ndim,
    const int64_t* shape,
    const int64_t* strides,
    irx_arrow_tensor_builder_handle** out_builder);
irx_arrow_status irx_arrow_tensor_builder_append_int(
    irx_arrow_tensor_builder_handle* builder,
    int64_t value);
irx_arrow_status irx_arrow_tensor_builder_append_uint(
    irx_arrow_tensor_builder_handle* builder,
    uint64_t value);
irx_arrow_status irx_arrow_tensor_builder_append_double(
    irx_arrow_tensor_builder_handle* builder,
    double value);
irx_arrow_status irx_arrow_tensor_builder_finish(
    irx_arrow_tensor_builder_handle* builder,
    irx_arrow_tensor_handle** out_tensor);
void irx_arrow_tensor_builder_release(
    irx_arrow_tensor_builder_handle* builder);

int32_t irx_arrow_tensor_type_id(const irx_arrow_tensor_handle* tensor);
int32_t irx_arrow_tensor_ndim(const irx_arrow_tensor_handle* tensor);
int64_t irx_arrow_tensor_size(const irx_arrow_tensor_handle* tensor);
const int64_t* irx_arrow_tensor_shape(const irx_arrow_tensor_handle* tensor);
const int64_t* irx_arrow_tensor_strides(const irx_arrow_tensor_handle* tensor);
irx_arrow_status irx_arrow_tensor_borrow_buffer_view(
    const irx_arrow_tensor_handle* tensor,
    irx_buffer_view* out_view);
irx_arrow_status irx_arrow_tensor_retain(irx_arrow_tensor_handle* tensor);
void irx_arrow_tensor_release(irx_arrow_tensor_handle* tensor);

irx_arrow_status irx_arrow_table_new_from_arrays(
    int64_t column_count,
    const char** names,
    irx_arrow_array_handle** arrays,
    irx_arrow_table_handle** out_table);
int64_t irx_arrow_table_num_rows(const irx_arrow_table_handle* table);
int64_t irx_arrow_table_num_columns(const irx_arrow_table_handle* table);
irx_arrow_status irx_arrow_table_column_by_name(
    const irx_arrow_table_handle* table,
    const char* name,
    irx_arrow_chunked_array_handle** out_column);
irx_arrow_status irx_arrow_table_column_by_index(
    const irx_arrow_table_handle* table,
    int32_t index,
    irx_arrow_chunked_array_handle** out_column);
irx_arrow_status irx_arrow_table_retain(irx_arrow_table_handle* table);
void irx_arrow_table_release(irx_arrow_table_handle* table);
irx_arrow_status irx_arrow_chunked_array_retain(irx_arrow_chunked_array_handle* column);
void irx_arrow_chunked_array_release(irx_arrow_chunked_array_handle* column);
const char* irx_arrow_last_error(void);

#ifdef __cplusplus
}
#endif

#endif
