// Copyright IRx contributors.
#include "irx_record_batch_internal.h"
#include "irx_parquet_io.h"
#include <arrow/util/utf8.h>
#include <arrow/filesystem/api.h>
#include <algorithm>
#include <filesystem>
#include <string_view>
namespace {
int set_err(const std::string &message, int code = IRX_ERR_ARROW) {
    return irx::record_batch_error(message, code);
}
int set_err(const arrow::Status &status) { return set_err(status.ToString()); }
}
#define GUARD(p) do { if (!(p)) return set_err("null pointer argument", IRX_ERR_NULLPTR); } while (0)
// Parquet uses the existing owned handles; its adapters own all file state.
int irx_rb_parquet_reader_open_options(const char *path, const IrxRbSchema *expected,
                               const IrxParquetOptions *options, IrxRbStreamReader **out) {
    GUARD(out); *out = nullptr; GUARD(path); GUARD(options);
    try {
        auto reader = irx::parquet_reader(path, expected ? irx::record_batch_schema(expected) : nullptr, options->batch_size, options);
        if (!reader.ok()) return set_err(reader.status());
        return irx::own_reader(*reader, out);
    } catch (const std::exception &error) {
        return set_err(std::string("Parquet reader '") + path + "': " + error.what());
    }
}

int irx_rb_parquet_writer_open_options(const IrxRbSchema *schema, const char *path,
                               const IrxParquetOptions *options, IrxRbStreamWriter **out) {
    GUARD(out); *out = nullptr; GUARD(schema); GUARD(path); GUARD(options);
    try {
        auto writer = irx::parquet_writer(path, irx::record_batch_schema(schema), options->compression.c_str(), options->row_group_size, options);
        if (!writer.ok()) return set_err(writer.status());
        return irx::own_writer(irx::record_batch_schema(schema), *writer, out);
    } catch (const std::exception &error) {
        return set_err(std::string("Parquet writer '") + path + "': " + error.what());
    }
}

int irx_rb_parquet_reader_open(const char *path, const IrxRbSchema *expected,
                               int64_t batch_size, IrxRbStreamReader **out) {
    IrxParquetOptions options;
    options.batch_size = batch_size;
    return irx_rb_parquet_reader_open_options(path, expected, &options, out);
}
int irx_rb_parquet_writer_open(const IrxRbSchema *schema, const char *path,
                               const char *compression, int64_t row_group_size,
                               IrxRbStreamWriter **out) {
    GUARD(out); *out = nullptr; GUARD(compression);
    try {
        IrxParquetOptions options;
        options.compression = compression;
        options.row_group_size = row_group_size;
        return irx_rb_parquet_writer_open_options(schema, path, &options, out);
    } catch (const std::exception &error) { return set_err(error.what()); }
}
IrxParquetOptions *irx_parquet_options_new(void) {
    try { return new IrxParquetOptions(); }
    catch (const std::exception &error) { set_err(error.what()); return nullptr; }
}
void irx_parquet_options_release(IrxParquetOptions *options) { delete options; }
int irx_parquet_options_int(IrxParquetOptions *o, const char *name, int64_t value) {
    GUARD(o); GUARD(name);
    try {
        std::string_view n(name);
        if (n == "batch_size" || n == "row_group_size" || n == "data_page_size") {
            if (value <= 0) return set_err("Parquet sizes must be positive");
            if (n == "batch_size") o->batch_size = value;
            if (n == "row_group_size") o->row_group_size = value;
            if (n == "data_page_size") o->data_page_size = value;
        } else if (n == "row_group" || n == "compression_level") {
            if (value < INT32_MIN || value > INT32_MAX || (n == "row_group" && value < 0))
                return set_err("Parquet integer option out of range");
            if (n == "row_group") {
                if (std::find(o->row_groups.begin(), o->row_groups.end(), value) != o->row_groups.end())
                    return set_err("duplicate Parquet row group");
                o->row_groups.push_back(static_cast<int>(value));
            } else o->compression_level = static_cast<int>(value);
        } else {
            if (value != 0 && value != 1) return set_err("Parquet flags require 0 or 1");
            if (n == "use_threads") o->use_threads = value;
            else if (n == "pre_buffer") o->pre_buffer = value;
            else if (n == "dataset") o->dataset = value;
            else if (n == "hive") o->hive = value;
            else if (n == "unify") o->unify = value;
            else if (n == "normalize") o->normalize = value;
            else if (n == "atomic") o->atomic = value;
            else if (n == "durable") o->durable = value;
            else if (n == "reconstruct") o->reconstruct = value;
            else if (n == "append") o->append = value;
            else return set_err("unknown Parquet integer option");
        }
        return IRX_OK;
    } catch (const std::exception &error) { return set_err(error.what()); }
}
int irx_parquet_options_text(IrxParquetOptions *o, const char *name, const char *value) {
    GUARD(o); GUARD(name); GUARD(value);
    try {
        std::string_view n(name);
        if (n == "encryption_key_hex") {
            std::string_view hex(value);
            if (hex.size() != 32 && hex.size() != 48 && hex.size() != 64)
                return set_err("AES hex key must contain 32, 48 or 64 digits");
            arrow::util::SecureString secret(hex.size() / 2, 0);
            auto digit = [](char c) -> int {
                if (c >= '0' && c <= '9') return c - '0';
                if (c >= 'a' && c <= 'f') return c - 'a' + 10;
                if (c >= 'A' && c <= 'F') return c - 'A' + 10;
                return -1;
            };
            for (size_t i = 0; i < secret.size(); ++i) {
                int hi = digit(hex[2 * i]), lo = digit(hex[2 * i + 1]);
                if (hi < 0 || lo < 0) return set_err("AES key contains invalid hexadecimal digits");
                secret.as_span()[i] = static_cast<uint8_t>(16 * hi + lo);
            }
            o->key = std::move(secret);
        }
        else if (n == "compression") o->compression = value;
        else if (n == "column" || n == "partition_column") {
            auto &columns = n == "column" ? o->columns : o->partition_columns;
            if (!*value || !arrow::util::ValidateUTF8(std::string_view(value)))
                return set_err("Parquet column must be nonempty UTF-8");
            if (std::find(columns.begin(), columns.end(), value) != columns.end())
                return set_err("duplicate Parquet projection column");
            columns.emplace_back(value);
        } else return set_err("unknown Parquet text option");
        return IRX_OK;
    } catch (const std::exception &error) { return set_err(error.what()); }
}
int irx_parquet_options_key(IrxParquetOptions *o, const uint8_t *key, int64_t size) {
    GUARD(o); GUARD(key);
    if (size != 16 && size != 24 && size != 32) return set_err("AES key must contain 16, 24 or 32 bytes");
    try { o->key = arrow::util::SecureString(std::string(reinterpret_cast<const char *>(key), size)); return IRX_OK; }
    catch (const std::exception &) { return set_err("cannot configure Parquet encryption key"); }
}
int irx_parquet_options_filter(IrxParquetOptions *o, const char *column,
    const char *operation, const char *value, const char *type) {
    GUARD(o); GUARD(column); GUARD(operation); GUARD(value); GUARD(type);
    try {
        std::string_view op(operation), t(type);
        if (op != "eq" && op != "ne" && op != "lt" && op != "le" && op != "gt" && op != "ge" && op != "is_null" && op != "is_valid")
            return set_err("unknown Parquet predicate operation");
        if (t != "string" && t != "int64" && t != "double" && t != "bool")
            return set_err("unsupported Parquet predicate literal type");
        if (!*column || !arrow::util::ValidateUTF8(std::string_view(column)))
            return set_err("predicate column must be nonempty UTF-8");
        o->predicates.push_back({column, operation, value, type});
        return IRX_OK;
    } catch (const std::exception &error) { return set_err(error.what()); }
}

int irx_rb_parquet_read_table(const char *path, const IrxRbSchema *expected,
                              const IrxParquetOptions *options, int auto_detect,
                              irx_arrow_table_handle **out) {
    GUARD(out); *out = nullptr; GUARD(path); GUARD(options);
    try {
        IrxParquetOptions effective = *options;
        if (auto_detect) {
            std::string resolved;
            auto fs = arrow::fs::FileSystemFromUriOrPath(
                std::string_view(path).find("://") == std::string_view::npos
                    ? std::filesystem::absolute(path).string() : std::string(path), &resolved);
            if (!fs.ok()) return set_err(fs.status());
            auto info = (*fs)->GetFileInfo(resolved);
            if (!info.ok()) return set_err(info.status());
            effective.dataset = effective.hive = info->IsDirectory();
        }
        IrxRbStreamReader *raw = nullptr;
        int rc = irx_rb_parquet_reader_open_options(path, expected, &effective, &raw);
        std::unique_ptr<IrxRbStreamReader, decltype(&irx_rb_stream_reader_close)> reader(raw, irx_rb_stream_reader_close);
        if (rc != IRX_OK) return rc;
        return irx_rb_reader_read_table(reader.get(), out);
    } catch (const std::exception &error) { return set_err(error.what()); }
}
int irx_rb_parquet_write_table(const irx_arrow_table_handle *table, const char *path,
                               const IrxParquetOptions *options, int auto_dataset) {
    GUARD(table); GUARD(path); GUARD(options);
    try {
        IrxParquetOptions effective = *options;
        if (auto_dataset && !effective.partition_columns.empty()) effective.dataset = effective.hive = true;
        IrxRbSchema *raw_schema = nullptr;
        int rc = irx_rb_table_schema(table, &raw_schema);
        std::unique_ptr<IrxRbSchema, decltype(&irx_rb_schema_release)> schema(raw_schema, irx_rb_schema_release);
        if (rc != IRX_OK) return rc;
        IrxRbStreamWriter *raw = nullptr;
        rc = irx_rb_parquet_writer_open_options(schema.get(), path, &effective, &raw);
        std::unique_ptr<IrxRbStreamWriter, decltype(&irx_rb_stream_writer_release)> writer(raw, irx_rb_stream_writer_release);
        if (rc != IRX_OK) return rc;
        rc = irx_rb_writer_write_table(writer.get(), table);
        return rc == IRX_OK ? irx_rb_stream_writer_close(writer.get()) : rc;
    } catch (const std::exception &error) { return set_err(error.what()); }
}
