/**
 * irx_record_batch.h
 *
 * Public C ABI for RecordBatch streaming via the Arrow C++ bridge.
 *
 * This header is the ONLY surface that compiled Arx programs (or other native
 * callers) may use. Every handle is opaque; the Arrow C++ types never leak
 * across the boundary. All functions return IRX_OK (0) on success or a
 * negative IRX_ERR_* code on failure. The last error message for the current
 * thread can be retrieved with irx_record_batch_errmsg().
 *
 * Lifecycle contract
 * ------------------
 *  1. Create a schema with irx_rb_schema_create().
 *  2. Add fields to the schema with irx_rb_schema_add_field().
 *  3. Open a stream writer with irx_rb_stream_writer_open_file() or
 *     irx_rb_stream_writer_open_buffer().
 *  4. For each batch:
 *       a. irx_rb_builder_create()   -- allocate a builder
 *       b. irx_rb_builder_append_*() -- push values per column
 *       c. irx_rb_builder_finish()   -- materialise the RecordBatch
 *       d. irx_rb_stream_writer_write_batch()
 *       e. irx_rb_batch_release()    -- drop the batch handle
 *       f. irx_rb_builder_release()  -- drop the builder handle
 *  5. irx_rb_stream_writer_close()
 *  6. irx_rb_schema_release()
 *
 * Reading
 * -------
 *  1. irx_rb_stream_reader_open_file() / irx_rb_stream_reader_open_buffer()
 *  2. irx_rb_stream_reader_next_batch() in a loop until it returns
 *     IRX_EOF (1).
 *  3. Inspect the batch with irx_rb_batch_num_rows() /
 *     irx_rb_batch_column_int32() etc.
 *  4. irx_rb_batch_release() per batch.
 *  5. irx_rb_stream_reader_close().
 */

#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------------------------------------------------ */
/* Return codes                                                         */
/* ------------------------------------------------------------------ */
#define IRX_OK       0
#define IRX_EOF      1   /* non-error: reader has no more batches */
#define IRX_ERR_ARROW   -1
#define IRX_ERR_NULLPTR -2
#define IRX_ERR_OOB     -3  /* column / row index out of bounds   */
#define IRX_ERR_TYPE    -4  /* type mismatch                      */
#define IRX_ERR_IO      -5

/* ------------------------------------------------------------------ */
/* Column storage types (mirrors irx_arrow.h primitive set)            */
/* ------------------------------------------------------------------ */
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

/* ------------------------------------------------------------------ */
/* Opaque handle types                                                  */
/* ------------------------------------------------------------------ */
typedef struct IrxRbSchema_       IrxRbSchema;
typedef struct IrxRbBuilder_      IrxRbBuilder;
typedef struct IrxRbBatch_        IrxRbBatch;
typedef struct IrxRbStreamWriter_ IrxRbStreamWriter;
typedef struct IrxRbStreamReader_ IrxRbStreamReader;

/* ------------------------------------------------------------------ */
/* Error reporting                                                      */
/* ------------------------------------------------------------------ */

/** Return the last error message for the calling thread (never NULL). */
const char *irx_record_batch_errmsg(void);

/* ------------------------------------------------------------------ */
/* Schema                                                               */
/* ------------------------------------------------------------------ */

/**
 * Create an empty schema. Caller must call irx_rb_schema_release() when done.
 * @param[out] out  receives the new schema handle.
 */
int irx_rb_schema_create(IrxRbSchema **out);

/**
 * Add a named field to the schema.
 * @param nullable  non-zero = field may contain nulls.
 */
int irx_rb_schema_add_field(IrxRbSchema *schema,
                             const char  *name,
                             IrxColumnType type,
                             int           nullable);

/** Return the number of fields in the schema. */
int irx_rb_schema_num_fields(const IrxRbSchema *schema);

/** Release the schema handle and free resources. */
void irx_rb_schema_release(IrxRbSchema *schema);

/* ------------------------------------------------------------------ */
/* Builder (one per batch)                                              */
/* ------------------------------------------------------------------ */

/**
 * Create a new builder for the given schema.
 * The schema must outlive the builder.
 */
int irx_rb_builder_create(const IrxRbSchema *schema, IrxRbBuilder **out);

/* Append helpers — col is a zero-based column index. */
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

/**
 * Finalise the builder and produce a RecordBatch.
 * All columns must have the same length; otherwise IRX_ERR_ARROW is returned.
 * @param[out] out  receives the new batch handle.
 */
int irx_rb_builder_finish(IrxRbBuilder *b, IrxRbBatch **out);

/** Release the builder. May be called before or after finish(). */
void irx_rb_builder_release(IrxRbBuilder *b);

/* ------------------------------------------------------------------ */
/* RecordBatch inspection                                               */
/* ------------------------------------------------------------------ */

/** Number of rows in the batch. */
int64_t irx_rb_batch_num_rows(const IrxRbBatch *batch);

/** Number of columns. */
int irx_rb_batch_num_columns(const IrxRbBatch *batch);

/**
 * Read a single value from a typed column by row index.
 * Returns IRX_ERR_OOB if row >= num_rows or col >= num_columns.
 * Returns IRX_ERR_TYPE if the column type does not match the accessor.
 */
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

/** True if the value at (col, row) is null. */
int irx_rb_batch_is_null(const IrxRbBatch *b, int col, int64_t row, int *out);

/**
 * Zero-copy read-only pointer to the raw value buffer of a fixed-width column.
 * The pointer is valid until irx_rb_batch_release() is called.
 * @param[out] buf   set to the start of the value buffer.
 * @param[out] len   number of elements (== num_rows for fixed-width types).
 */
int irx_rb_batch_value_buffer(const IrxRbBatch *b, int col,
                               const void **buf, int64_t *len);

/** Release the batch and free Arrow resources. */
void irx_rb_batch_release(IrxRbBatch *batch);

/* ------------------------------------------------------------------ */
/* Stream writer                                                        */
/* ------------------------------------------------------------------ */

/**
 * Open an Arrow IPC stream writer to a file path.
 * Creates or truncates the file.
 */
int irx_rb_stream_writer_open_file(const IrxRbSchema   *schema,
                                    const char          *path,
                                    IrxRbStreamWriter  **out);

/**
 * Open an Arrow IPC stream writer to a growable in-memory buffer.
 * Retrieve the finished bytes with irx_rb_stream_writer_buffer_data() after
 * close.
 */
int irx_rb_stream_writer_open_buffer(const IrxRbSchema   *schema,
                                      IrxRbStreamWriter  **out);

/** Write one RecordBatch to the stream. */
int irx_rb_stream_writer_write_batch(IrxRbStreamWriter *w,
                                      const IrxRbBatch  *batch);

/**
 * Finalise and close the stream.  Must be called before reading back a
 * buffer-based writer's bytes.
 */
int irx_rb_stream_writer_close(IrxRbStreamWriter *w);

/**
 * For buffer-based writers only: return a pointer to the serialised IPC bytes
 * and their length.  Valid only after irx_rb_stream_writer_close().
 * The pointer is owned by the writer and freed by irx_rb_stream_writer_release().
 */
int irx_rb_stream_writer_buffer_data(const IrxRbStreamWriter *w,
                                      const uint8_t **data,
                                      int64_t        *size);

/** Release the writer. Implicitly closes if not already closed. */
void irx_rb_stream_writer_release(IrxRbStreamWriter *w);

/* ------------------------------------------------------------------ */
/* Stream reader                                                        */
/* ------------------------------------------------------------------ */

/**
 * Open an Arrow IPC stream reader from a file.
 * The schema embedded in the stream is used; the caller does not need to
 * supply one.
 */
int irx_rb_stream_reader_open_file(const char         *path,
                                    IrxRbStreamReader **out);

/**
 * Open an Arrow IPC stream reader from a byte buffer.
 * The bytes are copied into an Arrow-owned buffer, so the caller's buffer
 * does not need to outlive the reader.
 */
int irx_rb_stream_reader_open_buffer(const uint8_t      *data,
                                      int64_t             size,
                                      IrxRbStreamReader **out);

/**
 * Read the next RecordBatch from the stream.
 * Returns IRX_OK and sets *batch on success.
 * Returns IRX_EOF (1) when the stream is exhausted (*batch is set to NULL).
 * Returns a negative IRX_ERR_* on error.
 */
int irx_rb_stream_reader_next_batch(IrxRbStreamReader *r,
                                     IrxRbBatch       **batch);

/**
 * Return the schema advertised by the stream (do NOT release this pointer;
 * it is owned by the reader).
 */
const IrxRbSchema *irx_rb_stream_reader_schema(const IrxRbStreamReader *r);

/** Close and release the reader. */
void irx_rb_stream_reader_close(IrxRbStreamReader *r);

#ifdef __cplusplus
} /* extern "C" */
#endif
