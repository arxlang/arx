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

/* Borrowed inputs, independently owned output columns (release once).
 * Status 0 means outputs are initialized. Failure clears output slots.
 * Scalar bits contain the exact fixed-width numeric/bool representation;
 * validity is separate. Null slots carry zero bits. Indexing is zero-based,
 * rejects negative/out-of-range indices, and never borrows scalar storage.
 */
int irx_arrow_series_index(const irx_arrow_chunked_array_handle*, int64_t,
    int32_t, uint64_t*, int32_t*);
/* IPC input is borrowed and copied. Success transfers one owned table handle;
 * failure clears out. The result does not borrow the input bytes. */
int irx_arrow_table_from_ipc(const uint8_t* data, int64_t length,
    irx_arrow_table_handle** out);
/* Mutate the shared Series handle, not the originating table. On failure the
 * handle is unchanged. Concurrent mutation/read of this handle is unsupported. */
int irx_arrow_series_set(irx_arrow_chunked_array_handle* column, int64_t index,
    int32_t type, uint64_t bits, int32_t valid, int32_t nullable);
/* Slice inputs are borrowed; success returns an independently owned column.
 * bounds bit 0 supplies start and bit 1 supplies stop. Zero step is an error.
 * Defaults, negative bounds and clamping follow Python slicing semantics. */
int irx_arrow_series_slice(const irx_arrow_chunked_array_handle*, int64_t,
    int64_t, int64_t, int32_t, irx_arrow_chunked_array_handle**);
int irx_arrow_column_compute(const char*, int32_t,
    const irx_arrow_chunked_array_handle*, uint64_t, int32_t,
    const irx_arrow_chunked_array_handle*, uint64_t, int32_t,
    irx_arrow_chunked_array_handle**, uint64_t*, int32_t*);
/* As above, with checked casts to the semantically resolved common type. */
int irx_arrow_column_compute_promoted(const char*, int32_t,
    const irx_arrow_chunked_array_handle*, uint64_t, int32_t,
    const irx_arrow_chunked_array_handle*, uint64_t, int32_t,
    irx_arrow_chunked_array_handle**, uint64_t*, int32_t*);

int irx_arrow_schema_import_copy(
    const struct ArrowSchema* schema,
    irx_arrow_schema_handle** out_schema);
int irx_arrow_schema_export(
    const irx_arrow_schema_handle* schema,
    struct ArrowSchema* out_schema);
int32_t irx_arrow_schema_type_id(const irx_arrow_schema_handle* schema);
int32_t irx_arrow_schema_is_nullable(const irx_arrow_schema_handle* schema);
int irx_arrow_schema_retain(irx_arrow_schema_handle* schema);
void irx_arrow_schema_release(irx_arrow_schema_handle* schema);

int irx_arrow_array_builder_new(
    int32_t type_id,
    irx_arrow_array_builder_handle** out_builder);
int irx_arrow_array_builder_append_null(
    irx_arrow_array_builder_handle* builder,
    int64_t count);
int irx_arrow_array_builder_append_int(
    irx_arrow_array_builder_handle* builder,
    int64_t value);
int irx_arrow_array_builder_append_uint(
    irx_arrow_array_builder_handle* builder,
    uint64_t value);
int irx_arrow_array_builder_append_double(
    irx_arrow_array_builder_handle* builder,
    double value);

int irx_arrow_array_builder_int32_new(
    irx_arrow_array_builder_handle** out_builder);
int irx_arrow_array_builder_append_int32(
    irx_arrow_array_builder_handle* builder, int32_t value);
int irx_arrow_array_builder_finish(
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

int irx_arrow_array_schema_copy(
    const irx_arrow_array_handle* array,
    irx_arrow_schema_handle** out_schema);

int irx_arrow_array_export(
    const irx_arrow_array_handle* array,
    struct ArrowArray* out_array,
    struct ArrowSchema* out_schema);
int irx_arrow_array_import(
    const struct ArrowArray* array,
    const struct ArrowSchema* schema,
    irx_arrow_array_handle** out_array);
int irx_arrow_array_import_copy(
    const struct ArrowArray* array,
    const struct ArrowSchema* schema,
    irx_arrow_array_handle** out_array);
int irx_arrow_array_import_move(
    struct ArrowArray* array,
    struct ArrowSchema* schema,
    irx_arrow_array_handle** out_array);

int irx_arrow_array_validity_bitmap(
    const irx_arrow_array_handle* array,
    const void** out_data,
    int64_t* out_offset_bits,
    int64_t* out_length_bits);
int irx_arrow_array_borrow_buffer_view(
    const irx_arrow_array_handle* array,
    irx_buffer_view* out_view);

int irx_arrow_array_retain(irx_arrow_array_handle* array);
void irx_arrow_array_release(irx_arrow_array_handle* array);

int irx_arrow_tensor_builder_new(
    int32_t type_id,
    int32_t ndim,
    const int64_t* shape,
    const int64_t* strides,
    irx_arrow_tensor_builder_handle** out_builder);
int irx_arrow_tensor_builder_append_int(
    irx_arrow_tensor_builder_handle* builder,
    int64_t value);
int irx_arrow_tensor_builder_append_uint(
    irx_arrow_tensor_builder_handle* builder,
    uint64_t value);
int irx_arrow_tensor_builder_append_double(
    irx_arrow_tensor_builder_handle* builder,
    double value);
int irx_arrow_tensor_builder_finish(
    irx_arrow_tensor_builder_handle* builder,
    irx_arrow_tensor_handle** out_tensor);
void irx_arrow_tensor_builder_release(
    irx_arrow_tensor_builder_handle* builder);

int32_t irx_arrow_tensor_type_id(const irx_arrow_tensor_handle* tensor);
int32_t irx_arrow_tensor_ndim(const irx_arrow_tensor_handle* tensor);
int64_t irx_arrow_tensor_size(const irx_arrow_tensor_handle* tensor);
const int64_t* irx_arrow_tensor_shape(const irx_arrow_tensor_handle* tensor);
const int64_t* irx_arrow_tensor_strides(const irx_arrow_tensor_handle* tensor);
int irx_arrow_tensor_borrow_buffer_view(
    const irx_arrow_tensor_handle* tensor,
    irx_buffer_view* out_view);
int irx_arrow_tensor_retain(irx_arrow_tensor_handle* tensor);
void irx_arrow_tensor_release(irx_arrow_tensor_handle* tensor);

int irx_arrow_table_new_from_arrays(
    int64_t column_count,
    const char** names,
    irx_arrow_array_handle** arrays,
    irx_arrow_table_handle** out_table);
int64_t irx_arrow_table_num_rows(const irx_arrow_table_handle* table);
int64_t irx_arrow_table_num_columns(const irx_arrow_table_handle* table);
int irx_arrow_table_column_by_name(
    const irx_arrow_table_handle* table,
    const char* name,
    irx_arrow_chunked_array_handle** out_column);
int irx_arrow_table_column_by_index(
    const irx_arrow_table_handle* table,
    int32_t index,
    irx_arrow_chunked_array_handle** out_column);
/* C Data imports consume the supplied callbacks; exports own fresh references.
 * Table export combines all chunks, and may allocate. Outputs must be empty. */
int irx_arrow_table_import_batch(struct ArrowArray* array, struct ArrowSchema* schema,
                                 irx_arrow_table_handle** out_table);
int irx_arrow_table_export_batch(const irx_arrow_table_handle* table,
                                 struct ArrowArray* array, struct ArrowSchema* schema);
int irx_arrow_table_retain(irx_arrow_table_handle* table);
void irx_arrow_table_release(irx_arrow_table_handle* table);
int irx_arrow_chunked_array_retain(irx_arrow_chunked_array_handle* column);
void irx_arrow_chunked_array_release(irx_arrow_chunked_array_handle* column);
const char* irx_arrow_last_error(void);

#ifdef __cplusplus
}
#endif

#endif
