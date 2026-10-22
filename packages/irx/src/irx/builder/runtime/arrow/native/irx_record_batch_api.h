// Copyright IRx contributors.
#ifndef IRX_RECORD_BATCH_API_H
#define IRX_RECORD_BATCH_API_H
#include "irx_record_batch.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Class-owned boxes. close is idempotent; destroy exactly once on last class
 * reference. Strings returned here are malloc-owned, released by IRx strings.
 * Invalid operations use ARX-RUNTIME-ARROW-001 and exit, like the File API.
 * Embedders requiring recoverable errors should use the status-returning ABI.
 */
typedef struct IrxRbApiSchema IrxRbApiSchema;
typedef struct IrxRbApiBatch IrxRbApiBatch;
typedef struct IrxRbApiBuilder IrxRbApiBuilder;
typedef struct IrxRbApiReader IrxRbApiReader;
typedef struct IrxRbApiWriter IrxRbApiWriter;
typedef struct IrxRbApiParquet IrxRbApiParquet;
IrxRbApiParquet *irx_rb_api_parquet_new(void);
void irx_rb_api_parquet_destroy(IrxRbApiParquet *box);
void irx_rb_api_parquet_close(IrxRbApiParquet *box);
int32_t irx_rb_api_parquet_next(IrxRbApiParquet *box);
void irx_rb_api_parquet_batch(IrxRbApiParquet *box, IrxRbApiBatch *out);
void irx_rb_api_parquet_schema(IrxRbApiParquet *box, IrxRbApiSchema *out);
void irx_rb_api_parquet_write(IrxRbApiParquet *box, IrxRbApiBatch *batch);
void irx_rb_api_parquet_open_read(IrxRbApiParquet *box, const char *path, int64_t batch_size);
void irx_rb_api_parquet_open_read_as(IrxRbApiParquet *box, const char *path, IrxRbApiSchema *schema, int64_t batch_size);
void irx_rb_api_parquet_open_write(IrxRbApiParquet *box, const char *path, IrxRbApiSchema *schema, const char *compression, int64_t row_group_size);
typedef struct IrxRbApiCsv IrxRbApiCsv;
IrxRbApiCsv *irx_rb_api_csv_new(void);
void irx_rb_api_csv_destroy(IrxRbApiCsv *box);
void irx_rb_api_csv_close(IrxRbApiCsv *box);
int32_t irx_rb_api_csv_next(IrxRbApiCsv *box);
void irx_rb_api_csv_batch(IrxRbApiCsv *box, IrxRbApiBatch *out);
void irx_rb_api_csv_schema(IrxRbApiCsv *box, IrxRbApiSchema *out);
void irx_rb_api_csv_write(IrxRbApiCsv *box, IrxRbApiBatch *batch);
void irx_rb_api_csv_open_read(IrxRbApiCsv *box, const char *path, const char *delimiter, int32_t header, int32_t block_size);
void irx_rb_api_csv_open_read_as(IrxRbApiCsv *box, const char *path, IrxRbApiSchema *schema, const char *delimiter, int32_t header, int32_t block_size);
void irx_rb_api_csv_open_write(IrxRbApiCsv *box, const char *path, IrxRbApiSchema *schema, const char *delimiter, int32_t header);
typedef struct IrxRbApiOptions IrxRbApiOptions;
IrxRbApiOptions *irx_rb_api_options_copy(IrxRbApiOptions *);
void irx_rb_api_options_clear(IrxRbApiOptions *, const char *);
void irx_rb_api_options_filters(IrxRbApiOptions *, IrxRbApiOptions *);
void irx_rb_api_filter_i64(IrxRbApiOptions *, IrxRbApiOptions *, const char *, const char *, int64_t);
void irx_rb_api_filter_f64(IrxRbApiOptions *, IrxRbApiOptions *, const char *, const char *, double);
void irx_rb_api_filter_bool(IrxRbApiOptions *, IrxRbApiOptions *, const char *, const char *, int32_t);
void irx_rb_api_filter_text(IrxRbApiOptions *, IrxRbApiOptions *, const char *, const char *, const char *);
void irx_rb_api_filter_null(IrxRbApiOptions *, IrxRbApiOptions *, const char *, const char *);
irx_arrow_table_handle *irx_rb_api_read_parquet(const char *, IrxRbApiSchema *, IrxRbApiOptions *, int32_t);
void irx_rb_api_write_parquet(irx_arrow_table_handle *, const char *, IrxRbApiOptions *, int32_t);
IrxRbApiOptions *irx_rb_api_options_new(void);
void irx_rb_api_options_destroy(IrxRbApiOptions *);
void irx_rb_api_options_int(IrxRbApiOptions *, const char *, int64_t);
void irx_rb_api_options_text(IrxRbApiOptions *, const char *, const char *);
void irx_rb_api_parquet_read_options(IrxRbApiParquet *, const char *, IrxRbApiOptions *);
void irx_rb_api_parquet_write_options(IrxRbApiParquet *, const char *, IrxRbApiSchema *, IrxRbApiOptions *);
void irx_rb_api_append_u8(IrxRbApiBuilder *, int32_t, uint8_t);
uint8_t irx_rb_api_get_u8(IrxRbApiBatch *, int32_t, int64_t);
void irx_rb_api_append_u16(IrxRbApiBuilder *, int32_t, uint16_t);
uint16_t irx_rb_api_get_u16(IrxRbApiBatch *, int32_t, int64_t);
void irx_rb_api_append_u32(IrxRbApiBuilder *, int32_t, uint32_t);
uint32_t irx_rb_api_get_u32(IrxRbApiBatch *, int32_t, int64_t);
void irx_rb_api_append_u64(IrxRbApiBuilder *, int32_t, uint64_t);
uint64_t irx_rb_api_get_u64(IrxRbApiBatch *, int32_t, int64_t);
void irx_rb_api_reader_csv(IrxRbApiReader *box, const char *path,
                           const char *delimiter, int32_t header, int32_t block_size);
void irx_rb_api_reader_csv_as(IrxRbApiReader *box, const char *path, IrxRbApiSchema *schema,
                              const char *delimiter, int32_t header, int32_t block_size);
void irx_rb_api_writer_csv(IrxRbApiWriter *box, const char *path,
                           const char *delimiter, int32_t header);
struct irx_arrow_table_handle *irx_rb_api_batch_to_table(IrxRbApiBatch *box, IrxRbApiSchema *schema);
struct irx_arrow_table_handle *irx_rb_api_batch_to_dynamic_table(IrxRbApiBatch *box);
void irx_rb_api_table_to_dynamic_batch(struct irx_arrow_table_handle *table, IrxRbApiBatch *out);
void irx_rb_api_table_to_batch(struct irx_arrow_table_handle *table, IrxRbApiBatch *out);
IrxCsvOptions *irx_rb_api_csv_options_new(void);
void irx_rb_api_csv_options_destroy(IrxCsvOptions *);
void irx_rb_api_csv_options_int(IrxCsvOptions *, const char *, int64_t);
void irx_rb_api_csv_options_text(IrxCsvOptions *, const char *, const char *);
void irx_rb_api_csv_options_clear(IrxCsvOptions *, const char *);
irx_arrow_table_handle *irx_rb_api_read_csv(const char *, IrxRbApiSchema *, IrxCsvOptions *);
void irx_rb_api_write_csv(irx_arrow_table_handle *, const char *, IrxCsvOptions *);
irx_arrow_table_handle *irx_rb_api_table_cast(irx_arrow_table_handle *, IrxRbApiSchema *);
void irx_rb_api_schema_add_name(IrxRbApiSchema *, const char *, const char *, int32_t);
irx_arrow_table_handle *irx_rb_api_csv_frame(IrxRbApiCsv *);
irx_arrow_table_handle *irx_rb_api_parquet_frame(IrxRbApiParquet *);
void irx_rb_api_csv_write_frame(IrxRbApiCsv *, irx_arrow_table_handle *);
void irx_rb_api_parquet_write_frame(IrxRbApiParquet *, irx_arrow_table_handle *);
IrxRbApiSchema *irx_rb_api_schema_new(void);
IrxRbApiSchema *irx_rb_api_schema_ipc(const uint8_t *data, int64_t size);
IrxRbApiBatch *irx_rb_api_batch_new(void);
IrxRbApiReader *irx_rb_api_reader_new(void);
IrxRbApiBuilder *irx_rb_api_builder_new(IrxRbApiSchema *schema);
IrxRbApiWriter *irx_rb_api_writer_new(IrxRbApiSchema *schema);
void irx_rb_api_schema_destroy(IrxRbApiSchema *box);
void irx_rb_api_schema_close(IrxRbApiSchema *box);
void irx_rb_api_batch_destroy(IrxRbApiBatch *box);
void irx_rb_api_batch_close(IrxRbApiBatch *box);
void irx_rb_api_builder_destroy(IrxRbApiBuilder *box);
void irx_rb_api_builder_close(IrxRbApiBuilder *box);
void irx_rb_api_reader_destroy(IrxRbApiReader *box);
void irx_rb_api_reader_close(IrxRbApiReader *box);
void irx_rb_api_writer_destroy(IrxRbApiWriter *box);
void irx_rb_api_writer_close(IrxRbApiWriter *box);
void irx_rb_api_schema_add(IrxRbApiSchema *box, const char *name, int32_t type,
                           int32_t nullable);
int32_t irx_rb_api_schema_count(IrxRbApiSchema *box);
char *irx_rb_api_schema_name(IrxRbApiSchema *box, int32_t col);
int32_t irx_rb_api_schema_type(IrxRbApiSchema *box, int32_t col);
int32_t irx_rb_api_schema_nullable(IrxRbApiSchema *box, int32_t col);
char *irx_rb_api_schema_type_name(IrxRbApiSchema *box, int32_t col);
int32_t irx_rb_api_schema_equal(IrxRbApiSchema *box, IrxRbApiSchema *other);
void irx_rb_api_builder_finish(IrxRbApiBuilder *box, IrxRbApiBatch *out);
int64_t irx_rb_api_batch_rows(IrxRbApiBatch *box);
int32_t irx_rb_api_batch_columns(IrxRbApiBatch *box);
void irx_rb_api_batch_schema(IrxRbApiBatch *box, IrxRbApiSchema *out);
int32_t irx_rb_api_batch_null(IrxRbApiBatch *box, int32_t col, int64_t row);
void irx_rb_api_append_i8(IrxRbApiBuilder *box, int32_t col, int8_t value);
int8_t irx_rb_api_get_i8(IrxRbApiBatch *box, int32_t col, int64_t row);
void irx_rb_api_append_i16(IrxRbApiBuilder *box, int32_t col, int16_t value);
int16_t irx_rb_api_get_i16(IrxRbApiBatch *box, int32_t col, int64_t row);
void irx_rb_api_append_i32(IrxRbApiBuilder *box, int32_t col, int32_t value);
int32_t irx_rb_api_get_i32(IrxRbApiBatch *box, int32_t col, int64_t row);
void irx_rb_api_append_i64(IrxRbApiBuilder *box, int32_t col, int64_t value);
int64_t irx_rb_api_get_i64(IrxRbApiBatch *box, int32_t col, int64_t row);
void irx_rb_api_append_f32(IrxRbApiBuilder *box, int32_t col, float value);
float irx_rb_api_get_f32(IrxRbApiBatch *box, int32_t col, int64_t row);
void irx_rb_api_append_f64(IrxRbApiBuilder *box, int32_t col, double value);
double irx_rb_api_get_f64(IrxRbApiBatch *box, int32_t col, int64_t row);
void irx_rb_api_append_bool(IrxRbApiBuilder *box, int32_t col, int32_t value);
int32_t irx_rb_api_get_bool(IrxRbApiBatch *box, int32_t col, int64_t row);
void irx_rb_api_append_date(IrxRbApiBuilder *box, int32_t col, int64_t value);
int64_t irx_rb_api_get_date(IrxRbApiBatch *box, int32_t col, int64_t row);
void irx_rb_api_append_timestamp(IrxRbApiBuilder *box, int32_t col,
                                 int64_t value);
int64_t irx_rb_api_get_timestamp(IrxRbApiBatch *box, int32_t col, int64_t row);
void irx_rb_api_append_time(IrxRbApiBuilder *box, int32_t col, int64_t value);
int64_t irx_rb_api_get_time(IrxRbApiBatch *box, int32_t col, int64_t row);
void irx_rb_api_append_utf8(IrxRbApiBuilder *box, int32_t col,
                            const char *value);
char *irx_rb_api_get_utf8(IrxRbApiBatch *box, int32_t col, int64_t row);
void irx_rb_api_append_null(IrxRbApiBuilder *box, int32_t col);
void irx_rb_api_reader_file(IrxRbApiReader *box, const char *path);
void irx_rb_api_reader_stream(IrxRbApiReader *box, const char *path);
void irx_rb_api_reader_tcp(IrxRbApiReader *box, const char *host, int32_t port,
                           int32_t timeout);
void irx_rb_api_writer_file(IrxRbApiWriter *box, const char *path);
void irx_rb_api_writer_stream(IrxRbApiWriter *box, const char *path);
void irx_rb_api_writer_tcp(IrxRbApiWriter *box, const char *host, int32_t port,
                           int32_t timeout);
void irx_rb_api_writer_write(IrxRbApiWriter *box, IrxRbApiBatch *batch);
int32_t irx_rb_api_reader_next(IrxRbApiReader *box);
void irx_rb_api_reader_batch(IrxRbApiReader *box, IrxRbApiBatch *out);
void irx_rb_api_reader_schema(IrxRbApiReader *box, IrxRbApiSchema *out);
int32_t irx_rb_api_batch_export_stream(IrxRbApiBatch *box, int64_t address);
int32_t irx_rb_api_batch_export(IrxRbApiBatch *box, int64_t array,
                                int64_t schema);
void irx_rb_api_batch_import(IrxRbApiBatch *box, int64_t array, int64_t schema);
void irx_rb_api_reader_import(IrxRbApiReader *box, int64_t address);
#ifdef __cplusplus
}
#endif
#endif
