// Copyright IRx contributors.
#include "irx_record_batch_api_internal.h"
#include "irx_parquet_options.h"
#include <cstdlib>
#include <memory>
#include <charconv>
#include <cmath>
#include <limits>
#include <string_view>
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

IrxRbApiOptions *irx_rb_api_options_copy(IrxRbApiOptions *source) {
    try { return source ? new IrxRbApiOptions(*source) : new IrxRbApiOptions(); }
    catch (const std::exception &error) { fail(error.what()); }
}
void irx_rb_api_options_clear(IrxRbApiOptions *box, const char *name) {
    std::string_view key(name);
    if (key == "columns") box->value.columns.clear();
    else if (key == "row_groups") box->value.row_groups.clear();
    else if (key == "partition_columns") box->value.partition_columns.clear();
    else fail("unknown Parquet list option");
}
void irx_rb_api_options_filters(IrxRbApiOptions *box, IrxRbApiOptions *filters) {
    try { box->value.predicates = filters->value.predicates; }
    catch (const std::exception &error) { fail(error.what()); }
}
namespace {
const char *filter_operation(const char *operation) {
    std::string_view op(operation);
    if (op == "==") return "eq";
    if (op == "!=") return "ne";
    if (op == "<") return "lt";
    if (op == "<=") return "le";
    if (op == ">") return "gt";
    if (op == ">=") return "ge";
    if (op == "is_null" || op == "is_valid") return operation;
    fail("filter operator must be ==, !=, <, <=, >, >=, is_null or is_valid");
}
void add_filter(IrxRbApiOptions *out, IrxRbApiOptions *source, const char *column,
                const char *operation, const char *value, const char *type) {
    try {
        const char *op = filter_operation(operation);
        if (*type && (std::string_view(op) == "is_null" || std::string_view(op) == "is_valid"))
            fail("null checks do not accept a value");
        if (!*type && std::string_view(op) != "is_null" && std::string_view(op) != "is_valid")
            fail("comparison filters require a value");
        IrxParquetOptions next;
        if (source) next.predicates = source->value.predicates;
        checked(irx_parquet_options_filter(&next, column, op, value, *type ? type : "string"));
        out->value.predicates = std::move(next.predicates);
    } catch (const std::exception &error) { fail(error.what()); }
}
}
void irx_rb_api_filter_i64(IrxRbApiOptions *o, IrxRbApiOptions *s, const char *c, const char *op, int64_t v) {
    char text[32]; auto result = std::to_chars(text, text + sizeof(text) - 1, v); *result.ptr = 0;
    add_filter(o, s, c, op, text, "int64");
}
void irx_rb_api_filter_f64(IrxRbApiOptions *o, IrxRbApiOptions *s, const char *c, const char *op, double v) {
    if (!std::isfinite(v)) fail("filter floating value must be finite");
    char text[64]; auto result = std::to_chars(text, text + sizeof(text) - 1, v, std::chars_format::general, std::numeric_limits<double>::max_digits10);
    if (result.ec != std::errc{}) fail("cannot encode filter floating value");
    *result.ptr = 0; add_filter(o, s, c, op, text, "double");
}
void irx_rb_api_filter_bool(IrxRbApiOptions *o, IrxRbApiOptions *s, const char *c, const char *op, int32_t v) {
    add_filter(o, s, c, op, v ? "true" : "false", "bool");
}
void irx_rb_api_filter_text(IrxRbApiOptions *o, IrxRbApiOptions *s, const char *c, const char *op, const char *v) {
    add_filter(o, s, c, op, v, "string");
}
void irx_rb_api_filter_null(IrxRbApiOptions *o, IrxRbApiOptions *s, const char *c, const char *op) {
    add_filter(o, s, c, op, "", "");
}
irx_arrow_table_handle *irx_rb_api_read_parquet(const char *path, IrxRbApiSchema *schema, IrxRbApiOptions *o, int32_t detect) {
    irx_arrow_table_handle *result = nullptr;
    checked(irx_rb_parquet_read_table(path, irx::api_schema_value(schema), &o->value, detect, &result));
    return result;
}
void irx_rb_api_write_parquet(irx_arrow_table_handle *table, const char *path, IrxRbApiOptions *o, int32_t detect) {
    checked(irx_rb_parquet_write_table(table, path, &o->value, detect));
}
