// Copyright IRx contributors.

#ifndef IRX_RECORD_BATCH_H_INCLUDED
#define IRX_RECORD_BATCH_H_INCLUDED

#include <stddef.h>
#include <stdint.h>

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
} IrxColumnType;

typedef struct IrxRbSchema_       IrxRbSchema;
typedef struct IrxRbBuilder_      IrxRbBuilder;
typedef struct IrxRbBatch_        IrxRbBatch;
typedef struct IrxRbStreamWriter_ IrxRbStreamWriter;
typedef struct IrxRbStreamReader_ IrxRbStreamReader;

const char *irx_record_batch_errmsg(void);

int irx_rb_schema_create(IrxRbSchema **out);
int irx_rb_schema_add_field(IrxRbSchema *schema,
                             const char  *name,
                             IrxColumnType type,
                             int           nullable);
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
int irx_rb_builder_append_null   (IrxRbBuilder *b, int col);
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
int irx_rb_batch_is_null(const IrxRbBatch *b, int col, int64_t row, int *out);
int irx_rb_batch_value_buffer(const IrxRbBatch *b, int col,
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

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* IRX_RECORD_BATCH_H_INCLUDED */
