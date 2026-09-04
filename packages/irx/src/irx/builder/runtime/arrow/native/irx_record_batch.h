// Copyright IRx contributors.

#ifndef IRX_RECORD_BATCH_H_INCLUDED
#define IRX_RECORD_BATCH_H_INCLUDED

#include <stddef.h>
#include <stdint.h>

/* irx_rb_* is the ABI-1 compatibility surface and is removed in ABI 2.
 * Define IRX_RECORD_BATCH_DISABLE_DEPRECATION_WARNINGS before including this
 * header only while migrating an existing consumer to irx_arrow_* calls. */
#if defined(IRX_RECORD_BATCH_BUILDING_COMPATIBILITY) || \
    defined(IRX_RECORD_BATCH_DISABLE_DEPRECATION_WARNINGS)
#define IRX_RB_DEPRECATED
#elif defined(__GNUC__) || defined(__clang__)
#define IRX_RB_DEPRECATED \
    __attribute__((deprecated("use the irx_arrow ABI; irx_rb is removed in ABI 2")))
#elif defined(_MSC_VER)
#define IRX_RB_DEPRECATED \
    __declspec(deprecated("use the irx_arrow ABI; irx_rb is removed in ABI 2"))
#else
#define IRX_RB_DEPRECATED
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define IRX_OK       0
#define IRX_EOF      1   /* non-error: reader has no more batches */
#define IRX_ERR_ARROW   -1
#define IRX_ERR_NULLPTR -2
#define IRX_ERR_OOB     -3  /* column / row index out of bounds */
#define IRX_ERR_TYPE    -4  /* type mismatch */
#define IRX_ERR_IO      -5
#define IRX_RECORD_BATCH_ABI_VERSION 1

typedef enum IrxColumnType {
    IRX_COL_INT8    = 0,
    IRX_COL_INT16   = 1,
    IRX_COL_INT32   = 2,
    IRX_COL_INT64   = 3,
    IRX_COL_UINT8   = 4,
    IRX_COL_UINT16  = 5,
    IRX_COL_UINT32  = 6,
    IRX_COL_UINT64  = 7,
    IRX_COL_FLOAT32 = 8,
    IRX_COL_FLOAT64 = 9,
    IRX_COL_BOOL    = 10,
    IRX_COL_UTF8       = 11,
    IRX_COL_LARGE_UTF8 = 12,
    IRX_COL_DATE32       = 13,
    IRX_COL_DATE64       = 14,
    IRX_COL_TIMESTAMP_S  = 15,
    IRX_COL_TIMESTAMP_MS = 16,
    IRX_COL_TIMESTAMP_US = 17,
    IRX_COL_TIMESTAMP_NS = 18,
    IRX_COL_TIME32_S     = 19,
    IRX_COL_TIME32_MS    = 20,
    IRX_COL_TIME64_US    = 21,
    IRX_COL_TIME64_NS    = 22,
    IRX_COL_LIST         = 23,
    IRX_COL_STRUCT       = 24,
} IrxColumnType;

typedef struct IrxRbType_         IrxRbType;
typedef struct IrxRbSchema_       IrxRbSchema;
typedef struct IrxRbBuilder_      IrxRbBuilder;
typedef struct irx_arrow_record_batch_handle IrxRbBatch;
typedef struct IrxRbStreamWriter_ IrxRbStreamWriter;
typedef struct IrxRbStreamReader_ IrxRbStreamReader;

const char *irx_record_batch_errmsg(void);
uint32_t irx_record_batch_abi_version(void);

/* Nested-type descriptors. A descriptor is a heap-owned handle wrapping an
 * Arrow DataType; build one, pass it to irx_rb_schema_add_field2, then release
 * it. irx_type_list copies its element descriptor, so the caller keeps
 * ownership of the element and must release it separately. */
IrxRbType *irx_type_primitive(IrxColumnType type);
IrxRbType *irx_type_list(const IrxRbType *element);
/* Build a struct descriptor from `n` named field descriptors. `names[i]` is the
 * name of field `i` and `fields[i]` its type. The field descriptors are copied,
 * so the caller keeps ownership and must release each separately. */
IrxRbType *irx_type_struct(const char *const *names,
                           const IrxRbType *const *fields, int n);
void irx_type_release(IrxRbType *type);

IRX_RB_DEPRECATED int irx_rb_schema_create(IrxRbSchema **out);
IRX_RB_DEPRECATED int irx_rb_schema_add_field(IrxRbSchema *schema,
                             const char  *name,
                             IrxColumnType type,
                             int           nullable);
/* Add a field from a (possibly nested) type descriptor. */
IRX_RB_DEPRECATED int irx_rb_schema_add_field2(IrxRbSchema     *schema,
                              const char      *name,
                              const IrxRbType *type,
                              int              nullable);
IRX_RB_DEPRECATED int irx_rb_schema_num_fields(const IrxRbSchema *schema);
IRX_RB_DEPRECATED void irx_rb_schema_release(IrxRbSchema *schema);

IRX_RB_DEPRECATED int irx_rb_builder_create(
    const IrxRbSchema *schema, IrxRbBuilder **out);
IRX_RB_DEPRECATED int irx_rb_builder_append_int8(
    IrxRbBuilder *b, int col, int8_t v);
IRX_RB_DEPRECATED int irx_rb_builder_append_int16(
    IrxRbBuilder *b, int col, int16_t v);
IRX_RB_DEPRECATED int irx_rb_builder_append_int32(
    IrxRbBuilder *b, int col, int32_t v);
IRX_RB_DEPRECATED int irx_rb_builder_append_int64(
    IrxRbBuilder *b, int col, int64_t v);
IRX_RB_DEPRECATED int irx_rb_builder_append_uint8(
    IrxRbBuilder *b, int col, uint8_t v);
IRX_RB_DEPRECATED int irx_rb_builder_append_uint16(
    IrxRbBuilder *b, int col, uint16_t v);
IRX_RB_DEPRECATED int irx_rb_builder_append_uint32(
    IrxRbBuilder *b, int col, uint32_t v);
IRX_RB_DEPRECATED int irx_rb_builder_append_uint64(
    IrxRbBuilder *b, int col, uint64_t v);
IRX_RB_DEPRECATED int irx_rb_builder_append_float32(
    IrxRbBuilder *b, int col, float v);
IRX_RB_DEPRECATED int irx_rb_builder_append_float64(
    IrxRbBuilder *b, int col, double v);
IRX_RB_DEPRECATED int irx_rb_builder_append_bool(
    IrxRbBuilder *b, int col, int v);
IRX_RB_DEPRECATED int irx_rb_builder_append_utf8(
    IrxRbBuilder *b, int col, const char *data, int64_t nbytes);
IRX_RB_DEPRECATED int irx_rb_builder_append_date(
    IrxRbBuilder *b, int col, int64_t v);
IRX_RB_DEPRECATED int irx_rb_builder_append_timestamp(
    IrxRbBuilder *b, int col, int64_t v);
IRX_RB_DEPRECATED int irx_rb_builder_append_time(
    IrxRbBuilder *b, int col, int64_t v);
IRX_RB_DEPRECATED int irx_rb_builder_append_null(IrxRbBuilder *b, int col);
/* Append one list slot to a list column. `data` points to `n` contiguous
 * elements of the column's (fixed-width primitive) element type; the element
 * type determines how the bytes are read. A null list slot is produced with
 * irx_rb_builder_append_null instead. */
IRX_RB_DEPRECATED int irx_rb_builder_append_list(
    IrxRbBuilder *b, int col, const void *data, int64_t n);
/* Open one (non-null) struct slot in a struct column, then set each field with
 * the struct_field_* calls below before moving to the next row. A null struct
 * slot is produced with irx_rb_builder_append_null instead. */
IRX_RB_DEPRECATED int irx_rb_builder_struct_append(
    IrxRbBuilder *b, int col);
/* Append `v` to field `field` of the struct slot opened last. The integer
 * variant covers integer, bool, date and time fields (the value is narrowed to
 * the field's declared width); the float variant covers float32/float64. */
IRX_RB_DEPRECATED int irx_rb_builder_struct_field_int(
    IrxRbBuilder *b, int col, int field, int64_t v);
IRX_RB_DEPRECATED int irx_rb_builder_struct_field_float(
    IrxRbBuilder *b, int col, int field, double v);
IRX_RB_DEPRECATED int irx_rb_builder_finish(
    IrxRbBuilder *b, IrxRbBatch **out);
IRX_RB_DEPRECATED void irx_rb_builder_release(IrxRbBuilder *b);

IRX_RB_DEPRECATED int64_t irx_rb_batch_num_rows(const IrxRbBatch *batch);
IRX_RB_DEPRECATED int irx_rb_batch_num_columns(const IrxRbBatch *batch);
IRX_RB_DEPRECATED int irx_rb_batch_get_int8(
    const IrxRbBatch *b, int col, int64_t row, int8_t *out);
IRX_RB_DEPRECATED int irx_rb_batch_get_int16(
    const IrxRbBatch *b, int col, int64_t row, int16_t *out);
IRX_RB_DEPRECATED int irx_rb_batch_get_int32(
    const IrxRbBatch *b, int col, int64_t row, int32_t *out);
IRX_RB_DEPRECATED int irx_rb_batch_get_int64(
    const IrxRbBatch *b, int col, int64_t row, int64_t *out);
IRX_RB_DEPRECATED int irx_rb_batch_get_uint8(
    const IrxRbBatch *b, int col, int64_t row, uint8_t *out);
IRX_RB_DEPRECATED int irx_rb_batch_get_uint16(
    const IrxRbBatch *b, int col, int64_t row, uint16_t *out);
IRX_RB_DEPRECATED int irx_rb_batch_get_uint32(
    const IrxRbBatch *b, int col, int64_t row, uint32_t *out);
IRX_RB_DEPRECATED int irx_rb_batch_get_uint64(
    const IrxRbBatch *b, int col, int64_t row, uint64_t *out);
IRX_RB_DEPRECATED int irx_rb_batch_get_float32(
    const IrxRbBatch *b, int col, int64_t row, float *out);
IRX_RB_DEPRECATED int irx_rb_batch_get_float64(
    const IrxRbBatch *b, int col, int64_t row, double *out);
IRX_RB_DEPRECATED int irx_rb_batch_get_bool(
    const IrxRbBatch *b, int col, int64_t row, int *out);
IRX_RB_DEPRECATED int irx_rb_batch_get_utf8(
    const IrxRbBatch *b,
    int col,
    int64_t row,
    const char **out,
    int64_t *len);
IRX_RB_DEPRECATED int irx_rb_batch_get_date(
    const IrxRbBatch *b, int col, int64_t row, int64_t *out);
IRX_RB_DEPRECATED int irx_rb_batch_get_timestamp(
    const IrxRbBatch *b, int col, int64_t row, int64_t *out);
IRX_RB_DEPRECATED int irx_rb_batch_get_time(
    const IrxRbBatch *b, int col, int64_t row, int64_t *out);
IRX_RB_DEPRECATED int irx_rb_batch_is_null(
    const IrxRbBatch *b, int col, int64_t row, int *out);
IRX_RB_DEPRECATED int irx_rb_batch_value_buffer(
    const IrxRbBatch *b, int col, const void **buf, int64_t *len);
/* List column readers (zero-copy). list_elem_type reports the element type.
 * list_offsets exposes the int32 offset array (length = num_rows + 1); the
 * elements of row r occupy child indices [offs[r], offs[r+1]). list_child_buffer
 * exposes the flattened fixed-width child value buffer (len = element count). */
IRX_RB_DEPRECATED int irx_rb_batch_list_elem_type(
    const IrxRbBatch *b, int col, IrxColumnType *out);
IRX_RB_DEPRECATED int irx_rb_batch_list_offsets(
    const IrxRbBatch *b, int col, const int32_t **offs, int64_t *n);
IRX_RB_DEPRECATED int irx_rb_batch_list_child_buffer(
    const IrxRbBatch *b, int col, const void **buf, int64_t *len);
/* Struct column readers (zero-copy). struct_num_fields reports the field count;
 * struct_field_type reports field `field`'s element type; struct_field_buffer
 * exposes that field's flattened fixed-width value buffer (len = num_rows). */
IRX_RB_DEPRECATED int irx_rb_batch_struct_num_fields(
    const IrxRbBatch *b, int col, int *out);
/* Report field `field`'s name. The returned pointer is owned by the batch and
 * stays valid until the batch is released. */
IRX_RB_DEPRECATED int irx_rb_batch_struct_field_name(
    const IrxRbBatch *b, int col, int field, const char **out);
IRX_RB_DEPRECATED int irx_rb_batch_struct_field_type(
    const IrxRbBatch *b, int col, int field, IrxColumnType *out);
IRX_RB_DEPRECATED int irx_rb_batch_struct_field_buffer(
    const IrxRbBatch *b,
    int col,
    int field,
    const void **buf,
    int64_t *len);
IRX_RB_DEPRECATED void irx_rb_batch_release(IrxRbBatch *batch);

IRX_RB_DEPRECATED int irx_rb_stream_writer_open_file(
    const IrxRbSchema *schema, const char *path, IrxRbStreamWriter **out);
IRX_RB_DEPRECATED int irx_rb_stream_writer_open_buffer(
    const IrxRbSchema *schema, IrxRbStreamWriter **out);
IRX_RB_DEPRECATED int irx_rb_stream_writer_write_batch(
    IrxRbStreamWriter *w, const IrxRbBatch *batch);
IRX_RB_DEPRECATED int irx_rb_stream_writer_close(IrxRbStreamWriter *w);
IRX_RB_DEPRECATED int irx_rb_stream_writer_buffer_data(
    const IrxRbStreamWriter *w, const uint8_t **data, int64_t *size);
IRX_RB_DEPRECATED void irx_rb_stream_writer_release(IrxRbStreamWriter *w);

IRX_RB_DEPRECATED int irx_rb_stream_reader_open_file(
    const char *path, IrxRbStreamReader **out);
IRX_RB_DEPRECATED int irx_rb_stream_reader_open_buffer(
    const uint8_t *data, int64_t size, IrxRbStreamReader **out);
IRX_RB_DEPRECATED int irx_rb_stream_reader_next_batch(
    IrxRbStreamReader *r, IrxRbBatch **batch);
IRX_RB_DEPRECATED const IrxRbSchema *irx_rb_stream_reader_schema(
    const IrxRbStreamReader *r);
IRX_RB_DEPRECATED void irx_rb_stream_reader_close(IrxRbStreamReader *r);

#ifdef __cplusplus
} /* extern "C" */
#endif

#undef IRX_RB_DEPRECATED

#endif /* IRX_RECORD_BATCH_H_INCLUDED */
