// Copyright IRx contributors.

#ifndef IRX_RECORD_BATCH_H_INCLUDED
#define IRX_RECORD_BATCH_H_INCLUDED

#include <stddef.h>
#include <stdint.h>
#include "irx_arrow_c_abi.h"
#include "irx_native_status.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct irx_arrow_table_handle irx_arrow_table_handle;

#define IRX_RECORD_BATCH_ABI_VERSION 2

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
    IRX_COL_BINARY       = 25,
    IRX_COL_LARGE_BINARY = 26,
    IRX_COL_FIXED_BINARY = 27,
    IRX_COL_DECIMAL128   = 28,
    IRX_COL_DECIMAL256   = 29,
    IRX_COL_LARGE_LIST   = 30,
    IRX_COL_FIXED_LIST   = 31,
    IRX_COL_MAP          = 32,
    IRX_COL_DICTIONARY   = 33,
    IRX_COL_EXTENSION    = 34,
    IRX_COL_NULL         = 35,
} IrxColumnType;

typedef struct IrxRbType_         IrxRbType;
typedef struct IrxRbSchema_       IrxRbSchema;
typedef struct IrxRbBuilder_      IrxRbBuilder;
typedef struct IrxRbBatch_        IrxRbBatch;
typedef struct IrxRbStreamWriter_ IrxRbStreamWriter;
typedef struct IrxRbStreamReader_ IrxRbStreamReader;

/* Options are independent owners, copied at open; setters validate before mutation.
 * Encryption keys are raw 16/24/32-byte AES keys, never textual diagnostics. */
typedef struct IrxParquetOptions IrxParquetOptions;
IrxParquetOptions *irx_parquet_options_new(void);
void irx_parquet_options_release(IrxParquetOptions *);
int irx_parquet_options_int(IrxParquetOptions *, const char *name, int64_t value);
int irx_parquet_options_text(IrxParquetOptions *, const char *name, const char *value);
int irx_parquet_options_key(IrxParquetOptions *, const uint8_t *, int64_t size);
int irx_parquet_options_filter(IrxParquetOptions *, const char *column,
    const char *operation, const char *value, const char *type);
int irx_rb_parquet_read_table(const char *, const IrxRbSchema *, const IrxParquetOptions *, int, irx_arrow_table_handle **);
int irx_rb_parquet_write_table(const irx_arrow_table_handle *, const char *, const IrxParquetOptions *, int);
int irx_rb_parquet_reader_open_options(const char *, const IrxRbSchema *,
    const IrxParquetOptions *, IrxRbStreamReader **);
int irx_rb_parquet_writer_open_options(const IrxRbSchema *, const char *,
    const IrxParquetOptions *, IrxRbStreamWriter **);

/* CSV uses the same owned readers/writers as IPC. A null read schema enables
 * first-block inference. Outputs are null on failure; schema is borrowed only
 * for this call. Delimiter must be exactly one non-NUL ASCII byte. */
typedef struct IrxCsvOptions IrxCsvOptions;
IrxCsvOptions *irx_csv_options_new(void);
void irx_csv_options_release(IrxCsvOptions *);
int irx_csv_options_int(IrxCsvOptions *, const char *, int64_t);
int irx_csv_options_text(IrxCsvOptions *, const char *, const char *);
int irx_csv_options_clear(IrxCsvOptions *, const char *);
int irx_rb_csv_reader_open_options(const char *, const IrxRbSchema *, const IrxCsvOptions *, IrxRbStreamReader **);
int irx_rb_csv_writer_open_options(const IrxRbSchema *, const char *, const IrxCsvOptions *, IrxRbStreamWriter **);
int irx_rb_csv_read_table(const char *, const IrxRbSchema *, const IrxCsvOptions *, irx_arrow_table_handle **);
int irx_rb_csv_write_table(const irx_arrow_table_handle *, const char *, const IrxCsvOptions *);
int irx_rb_csv_reader_open(const char *path, const IrxRbSchema *schema,
                          const char *delimiter, int header, int block_size,
                          IrxRbStreamReader **out);
int irx_rb_csv_writer_open(const IrxRbSchema *schema, const char *path,
                          const char *delimiter, int header,
                          IrxRbStreamWriter **out);

/* Additive Parquet factories. Expected schema is an exact assertion or NULL.
 * Successful handles own references; output slots are NULL on failure. Close
 * the writer explicitly to observe footer finalization errors. */
int irx_rb_parquet_reader_open(const char *path, const IrxRbSchema *expected,
                               int64_t batch_size, IrxRbStreamReader **out);
int irx_rb_parquet_writer_open(const IrxRbSchema *schema, const char *path,
                               const char *compression, int64_t row_group_size,
                               IrxRbStreamWriter **out);

struct irx_arrow_table_handle;
/* Runtime-schema conversions borrow their inputs and return independent owners.
 * On IRX_OK, release *out with irx_arrow_table_release or irx_rb_batch_release,
 * respectively. On error a valid out slot is reset to NULL. Complete supported
 * Arrow schemas/metadata are preserved; table export may combine chunks/copy. */
/* Chunk-preserving table bridges. Inputs are borrowed, output slots are null
 * on failure, and stream/table outputs own independent Arrow references. */
int irx_rb_reader_read_table(IrxRbStreamReader *, irx_arrow_table_handle **);
int irx_rb_table_schema(const irx_arrow_table_handle *, IrxRbSchema **);
int irx_rb_writer_write_table(IrxRbStreamWriter *, const irx_arrow_table_handle *);
int irx_rb_table_cast(const irx_arrow_table_handle *, const IrxRbSchema *, irx_arrow_table_handle **);
int irx_rb_table_project(const irx_arrow_table_handle *, const char *const *, int32_t, irx_arrow_table_handle **);
int irx_rb_batch_to_dynamic_table(const IrxRbBatch *batch, struct irx_arrow_table_handle **out);
int irx_rb_table_to_dynamic_batch(const struct irx_arrow_table_handle *table, IrxRbBatch **out);
/* Results own independent references. Neither operation consumes its input. */
int irx_rb_batch_to_table(const IrxRbBatch *batch, const IrxRbSchema *expected,
                         struct irx_arrow_table_handle **out);
int irx_rb_table_to_batch(const struct irx_arrow_table_handle *table,
                         IrxRbBatch **out);

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

int irx_rb_schema_create(IrxRbSchema **out);
int irx_rb_schema_add_named_field(IrxRbSchema *, const char *, const char *, int);
int irx_rb_schema_add_field(IrxRbSchema *schema,
                             const char  *name,
                             IrxColumnType type,
                             int           nullable);
/* Add a field from a (possibly nested) type descriptor. */
int irx_rb_schema_add_field2(IrxRbSchema     *schema,
                              const char      *name,
                              const IrxRbType *type,
                              int              nullable);
int irx_rb_schema_num_fields(const IrxRbSchema *schema);
void irx_rb_schema_release(IrxRbSchema *schema);

int irx_rb_builder_create(const IrxRbSchema *schema, IrxRbBuilder **out);
int irx_rb_builder_append_int8   (IrxRbBuilder *b, int col, int8_t   v);
int irx_rb_builder_append_int16  (IrxRbBuilder *b, int col, int16_t  v);
int irx_rb_builder_append_int32  (IrxRbBuilder *b, int col, int32_t  v);
int irx_rb_builder_append_int64  (IrxRbBuilder *b, int col, int64_t  v);
int irx_rb_builder_append_uint8  (IrxRbBuilder *b, int col, uint8_t  v);
int irx_rb_builder_append_uint16 (IrxRbBuilder *b, int col, uint16_t v);
int irx_rb_builder_append_uint32 (IrxRbBuilder *b, int col, uint32_t v);
int irx_rb_builder_append_uint64 (IrxRbBuilder *b, int col, uint64_t v);
int irx_rb_builder_append_float32(IrxRbBuilder *b, int col, float    v);
int irx_rb_builder_append_float64(IrxRbBuilder *b, int col, double   v);
int irx_rb_builder_append_bool   (IrxRbBuilder *b, int col, int      v);
int irx_rb_builder_append_utf8   (IrxRbBuilder *b, int col,const char *data, int64_t nbytes);
int irx_rb_builder_append_date     (IrxRbBuilder *b, int col, int64_t v);
int irx_rb_builder_append_timestamp(IrxRbBuilder *b, int col, int64_t v);
int irx_rb_builder_append_time     (IrxRbBuilder *b, int col, int64_t v);
int irx_rb_builder_append_null   (IrxRbBuilder *b, int col);
/* Append one list slot to a list column. `data` points to `n` contiguous
 * elements of the column's (fixed-width primitive) element type; the element
 * type determines how the bytes are read. A null list slot is produced with
 * irx_rb_builder_append_null instead. */
int irx_rb_builder_append_list   (IrxRbBuilder *b, int col,
                                    const void *data, int64_t n);
/* Open one (non-null) struct slot in a struct column, then set each field with
 * the struct_field_* calls below before moving to the next row. A null struct
 * slot is produced with irx_rb_builder_append_null instead. */
int irx_rb_builder_struct_append     (IrxRbBuilder *b, int col);
/* Append `v` to field `field` of the struct slot opened last. The integer
 * variant covers integer, bool, date and time fields (the value is narrowed to
 * the field's declared width); the float variant covers float32/float64. */
int irx_rb_builder_struct_field_int  (IrxRbBuilder *b, int col, int field,
                                        int64_t v);
int irx_rb_builder_struct_field_float(IrxRbBuilder *b, int col, int field,
                                        double v);
int irx_rb_builder_finish(IrxRbBuilder *b, IrxRbBatch **out);
void irx_rb_builder_release(IrxRbBuilder *b);

int64_t irx_rb_batch_num_rows(const IrxRbBatch *batch);
int irx_rb_batch_num_columns(const IrxRbBatch *batch);
int irx_rb_batch_get_int8   (const IrxRbBatch *b, int col, int64_t row, int8_t   *out);
int irx_rb_batch_get_int16  (const IrxRbBatch *b, int col, int64_t row, int16_t  *out);
int irx_rb_batch_get_int32  (const IrxRbBatch *b, int col, int64_t row, int32_t  *out);
int irx_rb_batch_get_int64  (const IrxRbBatch *b, int col, int64_t row, int64_t  *out);
int irx_rb_batch_get_uint8  (const IrxRbBatch *b, int col, int64_t row, uint8_t  *out);
int irx_rb_batch_get_uint16 (const IrxRbBatch *b, int col, int64_t row, uint16_t *out);
int irx_rb_batch_get_uint32 (const IrxRbBatch *b, int col, int64_t row, uint32_t *out);
int irx_rb_batch_get_uint64 (const IrxRbBatch *b, int col, int64_t row, uint64_t *out);
int irx_rb_batch_get_float32(const IrxRbBatch *b, int col, int64_t row, float    *out);
int irx_rb_batch_get_float64(const IrxRbBatch *b, int col, int64_t row, double   *out);
int irx_rb_batch_get_bool   (const IrxRbBatch *b, int col, int64_t row, int      *out);
int irx_rb_batch_get_utf8   (const IrxRbBatch *b, int col, int64_t row,const char **out, int64_t *len);
int irx_rb_batch_get_date     (const IrxRbBatch *b, int col, int64_t row, int64_t *out);
int irx_rb_batch_get_timestamp(const IrxRbBatch *b, int col, int64_t row, int64_t *out);
int irx_rb_batch_get_time     (const IrxRbBatch *b, int col, int64_t row, int64_t *out);
int irx_rb_batch_is_null(const IrxRbBatch *b, int col, int64_t row, int *out);
int irx_rb_batch_value_buffer(const IrxRbBatch *b, int col,
                               const void **buf, int64_t *len);
/* List column readers (zero-copy). list_elem_type reports the element type.
 * list_offsets exposes the int32 offset array (length = num_rows + 1); the
 * elements of row r occupy child indices [offs[r], offs[r+1]). list_child_buffer
 * exposes the flattened fixed-width child value buffer (len = element count). */
int irx_rb_batch_list_elem_type(const IrxRbBatch *b, int col, IrxColumnType *out);
int irx_rb_batch_list_offsets(const IrxRbBatch *b, int col,
                               const int32_t **offs, int64_t *n);
int irx_rb_batch_list_child_buffer(const IrxRbBatch *b, int col,
                                    const void **buf, int64_t *len);
/* Struct column readers (zero-copy). struct_num_fields reports the field count;
 * struct_field_type reports field `field`'s element type; struct_field_buffer
 * exposes that field's flattened fixed-width value buffer (len = num_rows). */
int irx_rb_batch_struct_num_fields (const IrxRbBatch *b, int col, int *out);
/* Report field `field`'s name. The returned pointer is owned by the batch and
 * stays valid until the batch is released. */
int irx_rb_batch_struct_field_name (const IrxRbBatch *b, int col, int field,
                                     const char **out);
int irx_rb_batch_struct_field_type (const IrxRbBatch *b, int col, int field,
                                     IrxColumnType *out);
int irx_rb_batch_struct_field_buffer(const IrxRbBatch *b, int col, int field,
                                      const void **buf, int64_t *len);
void irx_rb_batch_release(IrxRbBatch *batch);

int irx_rb_stream_writer_open_file(const IrxRbSchema   *schema,
                                    const char          *path,
                                    IrxRbStreamWriter  **out);
int irx_rb_stream_writer_open_buffer(const IrxRbSchema   *schema,
                                      IrxRbStreamWriter  **out);
int irx_rb_stream_writer_write_batch(IrxRbStreamWriter *w,
                                      const IrxRbBatch  *batch);
int irx_rb_stream_writer_close(IrxRbStreamWriter *w);
int irx_rb_stream_writer_buffer_data(const IrxRbStreamWriter *w,
                                      const uint8_t **data,
                                      int64_t        *size);
void irx_rb_stream_writer_release(IrxRbStreamWriter *w);

int irx_rb_stream_reader_open_file(const char         *path,
                                    IrxRbStreamReader **out);
int irx_rb_stream_reader_open_buffer(const uint8_t      *data,
                                      int64_t             size,
                                      IrxRbStreamReader **out);
int irx_rb_stream_reader_next_batch(IrxRbStreamReader *r,
                                     IrxRbBatch       **batch);
const IrxRbSchema *irx_rb_stream_reader_schema(const IrxRbStreamReader *r);
void irx_rb_stream_reader_close(IrxRbStreamReader *r);


int irx_rb_schema_clone(const IrxRbSchema *, IrxRbSchema **);
int irx_rb_batch_clone(const IrxRbBatch *, IrxRbBatch **);
/* type_name is borrowed until the next call on this thread. */
int irx_rb_schema_type_name(const IrxRbSchema *, int col, const char **);

/* Additive ABI v1: file means Arrow IPC file format, stream means IPC streaming
 * bytes. A reader owns its source; batches and schema snapshots outlive it.
 * All output handles are caller-owned. No output may be read on failure.
 * Writer schema matching includes metadata and field nullability. */
int irx_rb_file_writer_open(const IrxRbSchema *, const char *, IrxRbStreamWriter **);
int irx_rb_file_reader_open(const char *, IrxRbStreamReader **);
int irx_rb_tcp_writer_open(const IrxRbSchema *, const char *, int port,
                            int timeout_ms, IrxRbStreamWriter **);
int irx_rb_tcp_reader_open(const char *, int port, int timeout_ms, IrxRbStreamReader **);
int irx_rb_fd_writer_open(const IrxRbSchema *, int fd, IrxRbStreamWriter **);
int irx_rb_fd_reader_open(int fd, IrxRbStreamReader **);
int irx_rb_batch_schema(const IrxRbBatch *, IrxRbSchema **);
/* field name is borrowed until schema release; equal includes all metadata. */
int irx_rb_schema_field(const IrxRbSchema *, int col, const char **name,
                          int *type, int *nullable);
int irx_rb_schema_equal(const IrxRbSchema *, const IrxRbSchema *);

/* C outputs must be zero-initialized or released. Exports retain buffers, not
 * handles, and remain valid after releasing the original handle. Imports move
 * the C input, including on some failures: call release only if still non-null.
 * The caller owns the outer C structs. Never call a null release callback.
 * reader_export transfers iteration to the C stream, leaving an EOF reader. */
int irx_rb_schema_export(const IrxRbSchema *, struct ArrowSchema *);
/* Borrow IPC bytes only during the call; return an independently owned schema.
 * Failure clears out; release a successful output once with schema_release. */
int irx_rb_schema_from_ipc(const uint8_t *data, int64_t size, IrxRbSchema **out);
int irx_rb_schema_import(struct ArrowSchema *, IrxRbSchema **);
int irx_rb_batch_export(const IrxRbBatch *, struct ArrowArray *, struct ArrowSchema *);
int irx_rb_batch_import(struct ArrowArray *, struct ArrowSchema *, IrxRbBatch **);
int irx_rb_batch_export_stream(const IrxRbBatch *, struct ArrowArrayStream *);
int irx_rb_stream_reader_import(struct ArrowArrayStream *, IrxRbStreamReader **);
int irx_rb_stream_reader_export(IrxRbStreamReader *, struct ArrowArrayStream *);
/* Idempotent guards; do not pass a freed outer struct. */
void irx_rb_c_stream_release(struct ArrowArrayStream *);
void irx_rb_c_array_release(struct ArrowArray *);
void irx_rb_c_schema_release(struct ArrowSchema *);

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* IRX_RECORD_BATCH_H_INCLUDED */
