// Copyright IRx contributors.
#include "irx_record_batch_api_internal.h"
#include "irx_parquet_options.h"
#include <cstdlib>
#include <memory>
extern "C" void __arx_runtime_fail(const char *, const char *, int, int, const char *);
namespace {
[[noreturn]] void fail(const char *message) {
    __arx_runtime_fail("ARX-RUNTIME-ARROW-001", nullptr, 0, 0, message);
    std::abort();
}
void checked(int status) { if (status < 0) fail(irx_record_batch_errmsg()); }
}
struct IrxRbApiOptions { IrxParquetOptions value; };
IrxRbApiOptions *irx_rb_api_options_new(void) {
    try { return new IrxRbApiOptions(); }
    catch (const std::exception &error) { fail(error.what()); }
}
void irx_rb_api_options_destroy(IrxRbApiOptions *box) { delete box; }
void irx_rb_api_options_int(IrxRbApiOptions *box, const char *name, int64_t value) {
    checked(irx_parquet_options_int(&box->value, name, value));
}
void irx_rb_api_options_text(IrxRbApiOptions *box, const char *name, const char *value) {
    checked(irx_parquet_options_text(&box->value, name, value));
}
void irx_rb_api_options_filter(IrxRbApiOptions *box, const char *column, const char *operation, const char *value, const char *type) {
    checked(irx_parquet_options_filter(&box->value, column, operation, value, type));
}
void irx_rb_api_parquet_read_options(IrxRbApiParquet *box, const char *path, IrxRbApiOptions *options) {
    irx::api_open_read(box, path, nullptr, &options->value, irx_rb_parquet_reader_open_options);
}
void irx_rb_api_parquet_write_options(IrxRbApiParquet *box, const char *path, IrxRbApiSchema *schema, IrxRbApiOptions *options) {
    irx::api_open_write(box, path, schema, &options->value, irx_rb_parquet_writer_open_options);
}
void irx_rb_api_parquet_open_read(IrxRbApiParquet *box, const char *path, int64_t batch_size) {
    IrxParquetOptions options;
    options.batch_size = batch_size;
    irx::api_open_read(box, path, nullptr, &options, irx_rb_parquet_reader_open_options);
}
void irx_rb_api_parquet_open_read_as(IrxRbApiParquet *box, const char *path, IrxRbApiSchema *schema, int64_t batch_size) {
    IrxParquetOptions options;
    options.batch_size = batch_size;
    irx::api_open_read(box, path, schema, &options, irx_rb_parquet_reader_open_options);
}
void irx_rb_api_parquet_open_write(IrxRbApiParquet *box, const char *path, IrxRbApiSchema *schema, const char *compression, int64_t row_group_size) {
    try {
        IrxParquetOptions options;
        options.compression = compression;
        options.row_group_size = row_group_size;
        irx::api_open_write(box, path, schema, &options, irx_rb_parquet_writer_open_options);
    } catch (const std::exception &error) { fail(error.what()); }
}
