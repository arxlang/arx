// Copyright IRx contributors.
// Checked value-returning facade for languages without C out-parameters.
#include "irx_record_batch_api_internal.h"
#include <cstdlib>
#include <cstring>
#include <memory>
#include <string_view>
namespace {
[[noreturn]] void fail(const char *message, int status = IRX_ERR_INVALID) {
    throw irx::ApiError{status, message};
}
void checked(int status) {
    if (status < 0)
        fail(irx_record_batch_errmsg(), status);
}
template <class T, void (*release)(T *)> struct Box {
    T *value{nullptr};
    ~Box() { release(value); }
    T *get() const {
        if (!value)
            fail("Arrow object is closed or uninitialized");
        return value;
    }
    void reset(T *next = nullptr) {
        release(value);
        value = next;
    }
};
char *owned_text(const char *text, size_t size) {
    if (size && std::memchr(text, 0, size))
        fail("embedded NUL is not representable in Arx str; use C Data/IPC to "
             "preserve it");
    char *copy = static_cast<char *>(std::malloc(size + 1));
    if (!copy)
        throw std::bad_alloc();
    if (size)
        std::memcpy(copy, text, size);
    copy[size] = 0;
    return copy;
}
} // namespace
struct IrxRbApiSchema : Box<IrxRbSchema, irx_rb_schema_release> {};
struct IrxRbApiBatch : Box<IrxRbBatch, irx_rb_batch_release> {};
struct IrxRbApiBuilder : Box<IrxRbBuilder, irx_rb_builder_release> {};
struct IrxRbApiReader : Box<IrxRbStreamReader, irx_rb_stream_reader_close> {
    Box<IrxRbBatch, irx_rb_batch_release> current;
};
struct IrxRbApiWriter : Box<IrxRbStreamWriter, irx_rb_stream_writer_release> {
    Box<IrxRbSchema, irx_rb_schema_release> schema;
};

IrxRbApiSchema *irx_rb_impl_schema_ipc(const uint8_t *data, int64_t size) {
    auto result = std::make_unique<IrxRbApiSchema>();
    checked(irx_rb_schema_from_ipc(data, size, &result->value));
    return result.release();
}

IrxRbApiSchema *irx_rb_impl_schema_new(void) {
    auto result = std::make_unique<IrxRbApiSchema>();
    checked(irx_rb_schema_create(&result->value));
    return result.release();
}

IrxRbApiBatch *irx_rb_impl_batch_new(void) {
    auto result = std::make_unique<IrxRbApiBatch>();
    return result.release();
}

IrxRbApiReader *irx_rb_impl_reader_new(void) {
    auto result = std::make_unique<IrxRbApiReader>();
    return result.release();
}

IrxRbApiBuilder *irx_rb_impl_builder_new(IrxRbApiSchema *schema) {
    auto result = std::make_unique<IrxRbApiBuilder>();
    checked(irx_rb_builder_create(schema->get(), &result->value));
    return result.release();
}

IrxRbApiWriter *irx_rb_impl_writer_new(IrxRbApiSchema *schema) {
    auto result = std::make_unique<IrxRbApiWriter>();
    checked(irx_rb_schema_clone(schema->get(), &result->schema.value));
    return result.release();
}

void irx_rb_impl_schema_destroy(IrxRbApiSchema *box) { delete box; }

void irx_rb_impl_schema_close(IrxRbApiSchema *box) { box->reset(); }

void irx_rb_impl_batch_destroy(IrxRbApiBatch *box) { delete box; }

void irx_rb_impl_batch_close(IrxRbApiBatch *box) { box->reset(); }

void irx_rb_impl_builder_destroy(IrxRbApiBuilder *box) { delete box; }

void irx_rb_impl_builder_close(IrxRbApiBuilder *box) { box->reset(); }

void irx_rb_impl_reader_destroy(IrxRbApiReader *box) { delete box; }

void irx_rb_impl_reader_close(IrxRbApiReader *box) {
    box->current.reset();
    box->reset();
}

void irx_rb_impl_writer_destroy(IrxRbApiWriter *box) {
    // Destruction abandons uncommitted writes; only explicit close publishes.
    delete box;
}

void irx_rb_impl_writer_close(IrxRbApiWriter *box) {
    if (box->value)
        checked(irx_rb_stream_writer_close(box->value));
    box->reset();
}

void irx_rb_impl_schema_add(IrxRbApiSchema *box, const char *name, int32_t type,
                           int32_t nullable) {
    checked(irx_rb_schema_add_field(
        box->get(), name, static_cast<IrxColumnType>(type), nullable));
}

int32_t irx_rb_impl_schema_count(IrxRbApiSchema *box) {
    return irx_rb_schema_num_fields(box->get());
}

char *irx_rb_impl_schema_name(IrxRbApiSchema *box, int32_t col) {
    const char *name;
    int type, nullable;
    checked(irx_rb_schema_field(box->get(), col, &name, &type, &nullable));
    return owned_text(name, std::strlen(name));
}

int32_t irx_rb_impl_schema_type(IrxRbApiSchema *box, int32_t col) {
    const char *name;
    int type, nullable;
    checked(irx_rb_schema_field(box->get(), col, &name, &type, &nullable));
    return type;
}

int32_t irx_rb_impl_schema_nullable(IrxRbApiSchema *box, int32_t col) {
    const char *name;
    int type, nullable;
    checked(irx_rb_schema_field(box->get(), col, &name, &type, &nullable));
    return nullable;
}

char *irx_rb_impl_schema_type_name(IrxRbApiSchema *box, int32_t col) {
    const char *name;
    checked(irx_rb_schema_type_name(box->get(), col, &name));
    return owned_text(name, std::strlen(name));
}

int32_t irx_rb_impl_schema_equal(IrxRbApiSchema *box, IrxRbApiSchema *other) {
    return irx_rb_schema_equal(box->get(), other->get());
}

void irx_rb_impl_builder_finish(IrxRbApiBuilder *box, IrxRbApiBatch *out) {
    IrxRbBatch *batch;
    checked(irx_rb_builder_finish(box->get(), &batch));
    out->reset(batch);
}

int64_t irx_rb_impl_batch_rows(IrxRbApiBatch *box) {
    return irx_rb_batch_num_rows(box->get());
}

int32_t irx_rb_impl_batch_columns(IrxRbApiBatch *box) {
    return irx_rb_batch_num_columns(box->get());
}

void irx_rb_impl_batch_schema(IrxRbApiBatch *box, IrxRbApiSchema *out) {
    IrxRbSchema *schema;
    checked(irx_rb_batch_schema(box->get(), &schema));
    out->reset(schema);
}

int32_t irx_rb_impl_batch_null(IrxRbApiBatch *box, int32_t col, int64_t row) {
    int result;
    checked(irx_rb_batch_is_null(box->get(), col, row, &result));
    return result;
}

namespace {
void require_value(IrxRbApiBatch *box, int col, int64_t row) {
    if (irx_rb_impl_batch_null(box, col, row))
        fail("null Arrow value: call is_null before a typed getter");
}
} // namespace

void irx_rb_impl_append_i8(IrxRbApiBuilder *box, int32_t col, int8_t value) {
    checked(irx_rb_builder_append_int8(box->get(), col, value));
}

int8_t irx_rb_impl_get_i8(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    int8_t result;
    checked(irx_rb_batch_get_int8(box->get(), col, row, &result));
    return result;
}

void irx_rb_impl_append_i16(IrxRbApiBuilder *box, int32_t col, int16_t value) {
    checked(irx_rb_builder_append_int16(box->get(), col, value));
}

int16_t irx_rb_impl_get_i16(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    int16_t result;
    checked(irx_rb_batch_get_int16(box->get(), col, row, &result));
    return result;
}

void irx_rb_impl_append_i32(IrxRbApiBuilder *box, int32_t col, int32_t value) {
    checked(irx_rb_builder_append_int32(box->get(), col, value));
}

int32_t irx_rb_impl_get_i32(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    int32_t result;
    checked(irx_rb_batch_get_int32(box->get(), col, row, &result));
    return result;
}

void irx_rb_impl_append_i64(IrxRbApiBuilder *box, int32_t col, int64_t value) {
    checked(irx_rb_builder_append_int64(box->get(), col, value));
}

int64_t irx_rb_impl_get_i64(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    int64_t result;
    checked(irx_rb_batch_get_int64(box->get(), col, row, &result));
    return result;
}

void irx_rb_impl_append_f32(IrxRbApiBuilder *box, int32_t col, float value) {
    checked(irx_rb_builder_append_float32(box->get(), col, value));
}

float irx_rb_impl_get_f32(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    float result;
    checked(irx_rb_batch_get_float32(box->get(), col, row, &result));
    return result;
}

void irx_rb_impl_append_f64(IrxRbApiBuilder *box, int32_t col, double value) {
    checked(irx_rb_builder_append_float64(box->get(), col, value));
}

double irx_rb_impl_get_f64(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    double result;
    checked(irx_rb_batch_get_float64(box->get(), col, row, &result));
    return result;
}

void irx_rb_impl_append_bool(IrxRbApiBuilder *box, int32_t col, int32_t value) {
    checked(irx_rb_builder_append_bool(box->get(), col, value));
}

int32_t irx_rb_impl_get_bool(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    int32_t result;
    checked(irx_rb_batch_get_bool(box->get(), col, row, &result));
    return result;
}

void irx_rb_impl_append_date(IrxRbApiBuilder *box, int32_t col, int64_t value) {
    checked(irx_rb_builder_append_date(box->get(), col, value));
}

int64_t irx_rb_impl_get_date(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    int64_t result;
    checked(irx_rb_batch_get_date(box->get(), col, row, &result));
    return result;
}

void irx_rb_impl_append_timestamp(IrxRbApiBuilder *box, int32_t col,
                                 int64_t value) {
    checked(irx_rb_builder_append_timestamp(box->get(), col, value));
}

int64_t irx_rb_impl_get_timestamp(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    int64_t result;
    checked(irx_rb_batch_get_timestamp(box->get(), col, row, &result));
    return result;
}

void irx_rb_impl_append_time(IrxRbApiBuilder *box, int32_t col, int64_t value) {
    checked(irx_rb_builder_append_time(box->get(), col, value));
}

int64_t irx_rb_impl_get_time(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    int64_t result;
    checked(irx_rb_batch_get_time(box->get(), col, row, &result));
    return result;
}

void irx_rb_impl_append_utf8(IrxRbApiBuilder *box, int32_t col,
                            const char *value) {
    checked(
        irx_rb_builder_append_utf8(box->get(), col, value, std::strlen(value)));
}

char *irx_rb_impl_get_utf8(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    const char *data;
    int64_t size;
    checked(irx_rb_batch_get_utf8(box->get(), col, row, &data, &size));
    return owned_text(data, size);
}

void irx_rb_impl_append_null(IrxRbApiBuilder *box, int32_t col) {
    checked(irx_rb_builder_append_null(box->get(), col));
}

void irx_rb_impl_reader_file(IrxRbApiReader *box, const char *path) {
    if (box->value)
        fail("close Arrow reader before reopening");
    IrxRbStreamReader *result;
    checked(irx_rb_file_reader_open(path, &result));
    box->reset(result);
}

void irx_rb_impl_reader_stream(IrxRbApiReader *box, const char *path) {
    if (box->value)
        fail("close Arrow reader before reopening");
    IrxRbStreamReader *result;
    checked(irx_rb_stream_reader_open_file(path, &result));
    box->reset(result);
}

void irx_rb_impl_reader_tcp(IrxRbApiReader *box, const char *host, int32_t port,
                           int32_t timeout) {
    if (box->value)
        fail("close Arrow reader before connecting");
    IrxRbStreamReader *result;
    checked(irx_rb_tcp_reader_open(host, port, timeout, &result));
    box->reset(result);
}

void irx_rb_impl_writer_file(IrxRbApiWriter *box, const char *path) {
    if (box->value)
        fail("close Arrow writer before reopening");
    IrxRbStreamWriter *result;
    checked(irx_rb_file_writer_open(box->schema.get(), path, &result));
    box->reset(result);
}

void irx_rb_impl_writer_stream(IrxRbApiWriter *box, const char *path) {
    if (box->value)
        fail("close Arrow writer before reopening");
    IrxRbStreamWriter *result;
    checked(irx_rb_stream_writer_open_file(box->schema.get(), path, &result));
    box->reset(result);
}

void irx_rb_impl_writer_tcp(IrxRbApiWriter *box, const char *host, int32_t port,
                           int32_t timeout) {
    if (box->value)
        fail("close Arrow writer before connecting");
    IrxRbStreamWriter *result;
    checked(irx_rb_tcp_writer_open(box->schema.get(), host, port, timeout,
                                   &result));
    box->reset(result);
}

void irx_rb_impl_writer_write(IrxRbApiWriter *box, IrxRbApiBatch *batch) {
    checked(irx_rb_stream_writer_write_batch(box->get(), batch->get()));
}

int32_t irx_rb_impl_reader_next(IrxRbApiReader *box) {
    box->current.reset();
    IrxRbBatch *batch;
    int status = irx_rb_stream_reader_next_batch(box->get(), &batch);
    checked(status);
    if (status == IRX_OK)
        box->current.reset(batch);
    return status;
}

void irx_rb_impl_reader_batch(IrxRbApiReader *box, IrxRbApiBatch *out) {
    IrxRbBatch *batch;
    checked(irx_rb_batch_clone(box->current.get(), &batch));
    out->reset(batch);
}

void irx_rb_impl_reader_schema(IrxRbApiReader *box, IrxRbApiSchema *out) {
    IrxRbSchema *schema;
    checked(
        irx_rb_schema_clone(irx_rb_stream_reader_schema(box->get()), &schema));
    out->reset(schema);
}

int32_t irx_rb_impl_batch_export_stream(IrxRbApiBatch *box, int64_t address) {
    return irx_rb_batch_export_stream(
        box->get(),
        reinterpret_cast<ArrowArrayStream *>(static_cast<uintptr_t>(address)));
}

int32_t irx_rb_impl_batch_export(IrxRbApiBatch *box, int64_t array,
                                int64_t schema) {
    return irx_rb_batch_export(
        box->get(),
        reinterpret_cast<ArrowArray *>(static_cast<uintptr_t>(array)),
        reinterpret_cast<ArrowSchema *>(static_cast<uintptr_t>(schema)));
}

void irx_rb_impl_batch_import(IrxRbApiBatch *box, int64_t array,
                             int64_t schema) {
    IrxRbBatch *batch;
    checked(irx_rb_batch_import(
        reinterpret_cast<ArrowArray *>(static_cast<uintptr_t>(array)),
        reinterpret_cast<ArrowSchema *>(static_cast<uintptr_t>(schema)),
        &batch));
    box->reset(batch);
}

void irx_rb_impl_reader_import(IrxRbApiReader *box, int64_t address) {
    if (box->value)
        fail("close Arrow reader before importing");
    IrxRbStreamReader *reader;
    checked(irx_rb_stream_reader_import(
        reinterpret_cast<ArrowArrayStream *>(static_cast<uintptr_t>(address)),
        &reader));
    box->reset(reader);
}

void irx_rb_impl_reader_csv_as(IrxRbApiReader *box, const char *path, IrxRbApiSchema *schema,
                              const char *delimiter, int32_t header, int32_t block_size) {
    if (box->value) fail("close CSV reader before reopening");
    IrxRbStreamReader *result = nullptr;
    checked(irx_rb_csv_reader_open(path, schema ? schema->get() : nullptr,
                                  delimiter, header, block_size, &result));
    box->reset(result);
}
void irx_rb_impl_reader_csv(IrxRbApiReader *box, const char *path,
                           const char *delimiter, int32_t header, int32_t block_size) {
    irx_rb_impl_reader_csv_as(box, path, nullptr, delimiter, header, block_size);
}
void irx_rb_impl_writer_csv(IrxRbApiWriter *box, const char *path,
                           const char *delimiter, int32_t header) {
    if (box->value) fail("close CSV writer before reopening");
    IrxRbStreamWriter *result = nullptr;
    checked(irx_rb_csv_writer_open(box->schema.get(), path, delimiter, header, &result));
    box->reset(result);
}
irx_arrow_table_handle *irx_rb_impl_batch_to_table(IrxRbApiBatch *box, IrxRbApiSchema *schema) {
    irx_arrow_table_handle *result = nullptr;
    checked(irx_rb_batch_to_table(box->get(), schema->get(), &result));
    return result;
}
irx_arrow_table_handle *irx_rb_impl_batch_to_dynamic_table(IrxRbApiBatch *box) {
    irx_arrow_table_handle *result = nullptr;
    checked(irx_rb_batch_to_dynamic_table(box->get(), &result));
    return result;
}
void irx_rb_impl_table_to_dynamic_batch(irx_arrow_table_handle *table, IrxRbApiBatch *out) {
    IrxRbBatch *batch = nullptr;
    checked(irx_rb_table_to_dynamic_batch(table, &batch));
    out->reset(batch);
}
void irx_rb_impl_table_to_batch(irx_arrow_table_handle *table, IrxRbApiBatch *out) {
    IrxRbBatch *batch = nullptr;
    checked(irx_rb_table_to_batch(table, &batch));
    out->reset(batch);
}


namespace {
// Only the new unified facades use this state machine. Legacy APIs are intact.
enum class FileMode { Closed, Read, Write, Failed };
const char *mode_name(FileMode mode) {
    switch (mode) {
    case FileMode::Closed: return "closed";
    case FileMode::Read: return "read";
    case FileMode::Write: return "write";
    default: return "failed";
    }
}
struct FileSession {
    FileMode mode{FileMode::Closed};
    IrxRbApiReader reader;
    IrxRbApiWriter writer;
    void require(FileMode required, const char *operation) const {
        if (mode != required) {
            std::string message = std::string(operation) + " requires " + mode_name(required) +
                " mode; current mode is " + mode_name(mode);
            fail(message.c_str());
        }
    }
    void check(int status) {
        if (status >= 0) return;
        std::string message = irx_record_batch_errmsg();
        mode = FileMode::Failed;
        reader.current.reset();
        reader.reset();
        writer.reset();
        writer.schema.reset();
        fail(message.c_str(), status);
    }
    int32_t next() {
        require(FileMode::Read, "next");
        reader.current.reset();
        IrxRbBatch *batch = nullptr;
        int status = irx_rb_stream_reader_next_batch(reader.get(), &batch);
        check(status);
        reader.current.reset(batch);
        return status;
    }
    void batch(IrxRbApiBatch *out) {
        require(FileMode::Read, "batch");
        irx_rb_impl_reader_batch(&reader, out);
    }
    void schema(IrxRbApiSchema *out) {
        if (mode == FileMode::Read) {
            irx_rb_impl_reader_schema(&reader, out);
            return;
        }
        require(FileMode::Write, "schema (read or write)");
        IrxRbSchema *copy = nullptr;
        check(irx_rb_schema_clone(writer.schema.get(), &copy));
        out->reset(copy);
    }
    void write(IrxRbApiBatch *batch) {
        require(FileMode::Write, "write");
        check(irx_rb_stream_writer_write_batch(writer.get(), batch->get()));
    }
    void close() {
        if (mode == FileMode::Closed) return;
        if (mode == FileMode::Write) check(irx_rb_stream_writer_close(writer.get()));
        reader.current.reset();
        reader.reset();
        writer.reset();
        writer.schema.reset();
        if (mode != FileMode::Failed) mode = FileMode::Closed;
    }
};
} // namespace
struct IrxRbApiParquet : FileSession {};
struct IrxRbApiCsv : FileSession {};

IrxRbApiParquet *irx_rb_impl_parquet_new(void) {
    try { return new IrxRbApiParquet(); } catch (...) { throw; }
}

void irx_rb_impl_parquet_destroy(IrxRbApiParquet *box) {
    delete box;
}

void irx_rb_impl_parquet_close(IrxRbApiParquet *box) {
    try { box->close(); } catch (...) { throw; }
}

int32_t irx_rb_impl_parquet_next(IrxRbApiParquet *box) {
    try { return box->next(); } catch (...) { throw; }
}

void irx_rb_impl_parquet_batch(IrxRbApiParquet *box, IrxRbApiBatch *out) {
    try { box->batch(out); } catch (...) { throw; }
}

void irx_rb_impl_parquet_schema(IrxRbApiParquet *box, IrxRbApiSchema *out) {
    try { box->schema(out); } catch (...) { throw; }
}

void irx_rb_impl_parquet_write(IrxRbApiParquet *box, IrxRbApiBatch *batch) {
    try { box->write(batch); } catch (...) { throw; }
}

IrxRbApiCsv *irx_rb_impl_csv_new(void) {
    try { return new IrxRbApiCsv(); } catch (...) { throw; }
}

void irx_rb_impl_csv_destroy(IrxRbApiCsv *box) {
    delete box;
}

void irx_rb_impl_csv_close(IrxRbApiCsv *box) {
    try { box->close(); } catch (...) { throw; }
}

int32_t irx_rb_impl_csv_next(IrxRbApiCsv *box) {
    try { return box->next(); } catch (...) { throw; }
}

void irx_rb_impl_csv_batch(IrxRbApiCsv *box, IrxRbApiBatch *out) {
    try { box->batch(out); } catch (...) { throw; }
}

void irx_rb_impl_csv_schema(IrxRbApiCsv *box, IrxRbApiSchema *out) {
    try { box->schema(out); } catch (...) { throw; }
}

void irx_rb_impl_csv_write(IrxRbApiCsv *box, IrxRbApiBatch *batch) {
    try { box->write(batch); } catch (...) { throw; }
}

void irx_rb_impl_csv_open_read(IrxRbApiCsv *box, const char *path, const char *delimiter, int32_t header, int32_t block_size) {
    try {
        box->require(FileMode::Closed, "open_read");
        IrxRbStreamReader *reader = nullptr;
        checked(irx_rb_csv_reader_open(path, nullptr, delimiter, header, block_size, &reader));
        box->reader.reset(reader);
        box->mode = FileMode::Read;
    } catch (...) { throw; }
}

void irx_rb_impl_csv_open_read_as(IrxRbApiCsv *box, const char *path, IrxRbApiSchema *schema, const char *delimiter, int32_t header, int32_t block_size) {
    try {
        box->require(FileMode::Closed, "open_read_as");
        IrxRbStreamReader *reader = nullptr;
        checked(irx_rb_csv_reader_open(path, schema->get(), delimiter, header, block_size, &reader));
        box->reader.reset(reader);
        box->mode = FileMode::Read;
    } catch (...) { throw; }
}

void irx_rb_impl_csv_open_write(IrxRbApiCsv *box, const char *path, IrxRbApiSchema *schema, const char *delimiter, int32_t header) {
    try {
        box->require(FileMode::Closed, "open_write");
        Box<IrxRbSchema, irx_rb_schema_release> copy;
        checked(irx_rb_schema_clone(schema->get(), &copy.value));
        IrxRbStreamWriter *writer = nullptr;
        checked(irx_rb_csv_writer_open(copy.get(), path, delimiter, header, &writer));
        box->writer.reset(writer);
        box->writer.schema.reset(copy.value);
        copy.value = nullptr;
        box->mode = FileMode::Write;
    } catch (...) { throw; }
}

void irx_rb_impl_append_u8(IrxRbApiBuilder *box, int32_t col, uint8_t value) {
    checked(irx_rb_builder_append_uint8(box->get(), col, value));
}
uint8_t irx_rb_impl_get_u8(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    uint8_t result;
    checked(irx_rb_batch_get_uint8(box->get(), col, row, &result));
    return result;
}

void irx_rb_impl_append_u16(IrxRbApiBuilder *box, int32_t col, uint16_t value) {
    checked(irx_rb_builder_append_uint16(box->get(), col, value));
}
uint16_t irx_rb_impl_get_u16(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    uint16_t result;
    checked(irx_rb_batch_get_uint16(box->get(), col, row, &result));
    return result;
}

void irx_rb_impl_append_u32(IrxRbApiBuilder *box, int32_t col, uint32_t value) {
    checked(irx_rb_builder_append_uint32(box->get(), col, value));
}
uint32_t irx_rb_impl_get_u32(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    uint32_t result;
    checked(irx_rb_batch_get_uint32(box->get(), col, row, &result));
    return result;
}

void irx_rb_impl_append_u64(IrxRbApiBuilder *box, int32_t col, uint64_t value) {
    checked(irx_rb_builder_append_uint64(box->get(), col, value));
}
uint64_t irx_rb_impl_get_u64(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    uint64_t result;
    checked(irx_rb_batch_get_uint64(box->get(), col, row, &result));
    return result;
}

namespace irx {
void api_open_read(IrxRbApiParquet *box, const char *path, IrxRbApiSchema *schema,
                   const IrxParquetOptions *options, ReaderFactory factory) {
    try {
        box->require(FileMode::Closed, "open_read");
        IrxRbStreamReader *reader = nullptr;
        checked(factory(path, schema ? schema->get() : nullptr, options, &reader));
        box->reader.reset(reader);
        box->mode = FileMode::Read;
    } catch (...) { throw; }
}
void api_open_write(IrxRbApiParquet *box, const char *path, IrxRbApiSchema *schema,
                    const IrxParquetOptions *options, WriterFactory factory) {
    try {
        box->require(FileMode::Closed, "open_write");
        Box<IrxRbSchema, irx_rb_schema_release> copy;
        checked(irx_rb_schema_clone(schema->get(), &copy.value));
        IrxRbStreamWriter *writer = nullptr;
        checked(factory(copy.get(), path, options, &writer));
        box->writer.reset(writer);
        box->writer.schema.reset(copy.value);
        copy.value = nullptr;
        box->mode = FileMode::Write;
    } catch (...) { throw; }
}
}

IrxCsvOptions *irx_rb_impl_csv_options_new(void) {
    auto result = irx_csv_options_new();
    if (!result) fail(irx_record_batch_errmsg(), irx::api_last_error_code());
    return result;
}
void irx_rb_impl_csv_options_destroy(IrxCsvOptions *o) { irx_csv_options_release(o); }
void irx_rb_impl_csv_options_int(IrxCsvOptions *o, const char *k, int64_t v) { checked(irx_csv_options_int(o, k, v)); }
void irx_rb_impl_csv_options_text(IrxCsvOptions *o, const char *k, const char *v) { checked(irx_csv_options_text(o, k, v)); }
void irx_rb_impl_csv_options_clear(IrxCsvOptions *o, const char *k) { checked(irx_csv_options_clear(o, k)); }
irx_arrow_table_handle *irx_rb_impl_read_csv(const char *path, IrxRbApiSchema *schema, IrxCsvOptions *o) {
    irx_arrow_table_handle *result = nullptr;
    checked(irx_rb_csv_read_table(path, schema ? schema->get() : nullptr, o, &result));
    return result;
}
void irx_rb_impl_write_csv(irx_arrow_table_handle *table, const char *path, IrxCsvOptions *o) {
    checked(irx_rb_csv_write_table(table, path, o));
}
irx_arrow_table_handle *irx_rb_impl_table_cast(irx_arrow_table_handle *table, IrxRbApiSchema *schema) {
    irx_arrow_table_handle *result = nullptr;
    checked(irx_rb_table_cast(table, schema->get(), &result));
    return result;
}
void irx_rb_impl_schema_add_name(IrxRbApiSchema *schema, const char *name, const char *type, int32_t nullable) {
    checked(irx_rb_schema_add_named_field(schema->get(), name, type, nullable));
}
namespace irx {
const IrxRbSchema *api_schema_value(IrxRbApiSchema *box) { return box ? box->get() : nullptr; }
}
irx_arrow_table_handle *irx_rb_impl_csv_frame(IrxRbApiCsv *box) {
    try {
    box->require(FileMode::Read, "frame");
    irx_arrow_table_handle *result = nullptr;
    checked(irx_rb_batch_to_dynamic_table(box->reader.current.get(), &result));
    return result;
    } catch (...) { throw; }
}
irx_arrow_table_handle *irx_rb_impl_parquet_frame(IrxRbApiParquet *box) {
    try {
    box->require(FileMode::Read, "frame");
    irx_arrow_table_handle *result = nullptr;
    checked(irx_rb_batch_to_dynamic_table(box->reader.current.get(), &result));
    return result;
    } catch (...) { throw; }
}
void irx_rb_impl_csv_write_frame(IrxRbApiCsv *box, irx_arrow_table_handle *table) {
    try {
    box->require(FileMode::Write, "write");
    box->check(irx_rb_writer_write_table(box->writer.get(), table));
    } catch (...) { throw; }
}
void irx_rb_impl_parquet_write_frame(IrxRbApiParquet *box, irx_arrow_table_handle *table) {
    try {
    box->require(FileMode::Write, "write");
    box->check(irx_rb_writer_write_table(box->writer.get(), table));
    } catch (...) { throw; }
}

// Checked foreign boundary; every failure is contained in C++.
int32_t irx_rb_api_parquet_new(IrxRbApiParquet ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_parquet_new(); });
}
int32_t irx_rb_api_parquet_destroy(IrxRbApiParquet * arg0, char* error) {
    return irx::api_boundary(error, [&] { irx_rb_impl_parquet_destroy(arg0); });
}
int32_t irx_rb_api_parquet_close(IrxRbApiParquet * arg0, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_parquet_close(arg0); });
}
int32_t irx_rb_api_parquet_next(IrxRbApiParquet * arg0, int32_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_parquet_next(arg0); });
}
int32_t irx_rb_api_parquet_batch(IrxRbApiParquet * arg0, IrxRbApiBatch * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_parquet_batch(arg0, arg1); });
}
int32_t irx_rb_api_parquet_schema(IrxRbApiParquet * arg0, IrxRbApiSchema * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_parquet_schema(arg0, arg1); });
}
int32_t irx_rb_api_parquet_write(IrxRbApiParquet * arg0, IrxRbApiBatch * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_parquet_write(arg0, arg1); });
}
int32_t irx_rb_api_csv_new(IrxRbApiCsv ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_csv_new(); });
}
int32_t irx_rb_api_csv_destroy(IrxRbApiCsv * arg0, char* error) {
    return irx::api_boundary(error, [&] { irx_rb_impl_csv_destroy(arg0); });
}
int32_t irx_rb_api_csv_close(IrxRbApiCsv * arg0, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_csv_close(arg0); });
}
int32_t irx_rb_api_csv_next(IrxRbApiCsv * arg0, int32_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_csv_next(arg0); });
}
int32_t irx_rb_api_csv_batch(IrxRbApiCsv * arg0, IrxRbApiBatch * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_csv_batch(arg0, arg1); });
}
int32_t irx_rb_api_csv_schema(IrxRbApiCsv * arg0, IrxRbApiSchema * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_csv_schema(arg0, arg1); });
}
int32_t irx_rb_api_csv_write(IrxRbApiCsv * arg0, IrxRbApiBatch * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_csv_write(arg0, arg1); });
}
int32_t irx_rb_api_csv_open_read(IrxRbApiCsv * arg0, const char * arg1, const char * arg2, int32_t arg3, int32_t arg4, char* error) {
    if (!arg0 || !arg1 || !arg2) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_csv_open_read(arg0, arg1, arg2, arg3, arg4); });
}
int32_t irx_rb_api_csv_open_read_as(IrxRbApiCsv * arg0, const char * arg1, IrxRbApiSchema * arg2, const char * arg3, int32_t arg4, int32_t arg5, char* error) {
    if (!arg0 || !arg1 || !arg2 || !arg3) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_csv_open_read_as(arg0, arg1, arg2, arg3, arg4, arg5); });
}
int32_t irx_rb_api_csv_open_write(IrxRbApiCsv * arg0, const char * arg1, IrxRbApiSchema * arg2, const char * arg3, int32_t arg4, char* error) {
    if (!arg0 || !arg1 || !arg2 || !arg3) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_csv_open_write(arg0, arg1, arg2, arg3, arg4); });
}
int32_t irx_rb_api_append_u8(IrxRbApiBuilder * arg0, int32_t arg1, uint8_t arg2, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_append_u8(arg0, arg1, arg2); });
}
int32_t irx_rb_api_get_u8(IrxRbApiBatch * arg0, int32_t arg1, int64_t arg2, uint8_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_get_u8(arg0, arg1, arg2); });
}
int32_t irx_rb_api_append_u16(IrxRbApiBuilder * arg0, int32_t arg1, uint16_t arg2, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_append_u16(arg0, arg1, arg2); });
}
int32_t irx_rb_api_get_u16(IrxRbApiBatch * arg0, int32_t arg1, int64_t arg2, uint16_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_get_u16(arg0, arg1, arg2); });
}
int32_t irx_rb_api_append_u32(IrxRbApiBuilder * arg0, int32_t arg1, uint32_t arg2, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_append_u32(arg0, arg1, arg2); });
}
int32_t irx_rb_api_get_u32(IrxRbApiBatch * arg0, int32_t arg1, int64_t arg2, uint32_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_get_u32(arg0, arg1, arg2); });
}
int32_t irx_rb_api_append_u64(IrxRbApiBuilder * arg0, int32_t arg1, uint64_t arg2, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_append_u64(arg0, arg1, arg2); });
}
int32_t irx_rb_api_get_u64(IrxRbApiBatch * arg0, int32_t arg1, int64_t arg2, uint64_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_get_u64(arg0, arg1, arg2); });
}
int32_t irx_rb_api_reader_csv(IrxRbApiReader * arg0, const char * arg1, const char * arg2, int32_t arg3, int32_t arg4, char* error) {
    if (!arg0 || !arg1 || !arg2) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_reader_csv(arg0, arg1, arg2, arg3, arg4); });
}
int32_t irx_rb_api_reader_csv_as(IrxRbApiReader * arg0, const char * arg1, IrxRbApiSchema * arg2, const char * arg3, int32_t arg4, int32_t arg5, char* error) {
    if (!arg0 || !arg1 || !arg2 || !arg3) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_reader_csv_as(arg0, arg1, arg2, arg3, arg4, arg5); });
}
int32_t irx_rb_api_writer_csv(IrxRbApiWriter * arg0, const char * arg1, const char * arg2, int32_t arg3, char* error) {
    if (!arg0 || !arg1 || !arg2) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_writer_csv(arg0, arg1, arg2, arg3); });
}
int32_t irx_rb_api_batch_to_table(IrxRbApiBatch * arg0, IrxRbApiSchema * arg1, struct irx_arrow_table_handle ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_batch_to_table(arg0, arg1); });
}
int32_t irx_rb_api_batch_to_dynamic_table(IrxRbApiBatch * arg0, struct irx_arrow_table_handle ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_batch_to_dynamic_table(arg0); });
}
int32_t irx_rb_api_table_to_dynamic_batch(struct irx_arrow_table_handle * arg0, IrxRbApiBatch * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_table_to_dynamic_batch(arg0, arg1); });
}
int32_t irx_rb_api_table_to_batch(struct irx_arrow_table_handle * arg0, IrxRbApiBatch * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_table_to_batch(arg0, arg1); });
}
int32_t irx_rb_api_csv_options_new(IrxCsvOptions ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_csv_options_new(); });
}
int32_t irx_rb_api_csv_options_destroy(IrxCsvOptions * arg0, char* error) {
    return irx::api_boundary(error, [&] { irx_rb_impl_csv_options_destroy(arg0); });
}
int32_t irx_rb_api_csv_options_int(IrxCsvOptions * arg0, const char * arg1, int64_t arg2, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_csv_options_int(arg0, arg1, arg2); });
}
int32_t irx_rb_api_csv_options_text(IrxCsvOptions * arg0, const char * arg1, const char * arg2, char* error) {
    if (!arg0 || !arg1 || !arg2) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_csv_options_text(arg0, arg1, arg2); });
}
int32_t irx_rb_api_csv_options_clear(IrxCsvOptions * arg0, const char * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_csv_options_clear(arg0, arg1); });
}
int32_t irx_rb_api_read_csv(const char * arg0, IrxRbApiSchema * arg1, IrxCsvOptions * arg2, irx_arrow_table_handle ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0 || !arg2) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_read_csv(arg0, arg1, arg2); });
}
int32_t irx_rb_api_write_csv(irx_arrow_table_handle * arg0, const char * arg1, IrxCsvOptions * arg2, char* error) {
    if (!arg0 || !arg1 || !arg2) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_write_csv(arg0, arg1, arg2); });
}
int32_t irx_rb_api_table_cast(irx_arrow_table_handle * arg0, IrxRbApiSchema * arg1, irx_arrow_table_handle ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_table_cast(arg0, arg1); });
}
int32_t irx_rb_api_schema_add_name(IrxRbApiSchema * arg0, const char * arg1, const char * arg2, int32_t arg3, char* error) {
    if (!arg0 || !arg1 || !arg2) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_schema_add_name(arg0, arg1, arg2, arg3); });
}
int32_t irx_rb_api_csv_frame(IrxRbApiCsv * arg0, irx_arrow_table_handle ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_csv_frame(arg0); });
}
int32_t irx_rb_api_parquet_frame(IrxRbApiParquet * arg0, irx_arrow_table_handle ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_parquet_frame(arg0); });
}
int32_t irx_rb_api_csv_write_frame(IrxRbApiCsv * arg0, irx_arrow_table_handle * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_csv_write_frame(arg0, arg1); });
}
int32_t irx_rb_api_parquet_write_frame(IrxRbApiParquet * arg0, irx_arrow_table_handle * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_parquet_write_frame(arg0, arg1); });
}
int32_t irx_rb_api_schema_new(IrxRbApiSchema ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_schema_new(); });
}
int32_t irx_rb_api_schema_ipc(const uint8_t * arg0, int64_t arg1, IrxRbApiSchema ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_schema_ipc(arg0, arg1); });
}
int32_t irx_rb_api_batch_new(IrxRbApiBatch ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_batch_new(); });
}
int32_t irx_rb_api_reader_new(IrxRbApiReader ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_reader_new(); });
}
int32_t irx_rb_api_builder_new(IrxRbApiSchema * arg0, IrxRbApiBuilder ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_builder_new(arg0); });
}
int32_t irx_rb_api_writer_new(IrxRbApiSchema * arg0, IrxRbApiWriter ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_writer_new(arg0); });
}
int32_t irx_rb_api_schema_destroy(IrxRbApiSchema * arg0, char* error) {
    return irx::api_boundary(error, [&] { irx_rb_impl_schema_destroy(arg0); });
}
int32_t irx_rb_api_schema_close(IrxRbApiSchema * arg0, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_schema_close(arg0); });
}
int32_t irx_rb_api_batch_destroy(IrxRbApiBatch * arg0, char* error) {
    return irx::api_boundary(error, [&] { irx_rb_impl_batch_destroy(arg0); });
}
int32_t irx_rb_api_batch_close(IrxRbApiBatch * arg0, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_batch_close(arg0); });
}
int32_t irx_rb_api_builder_destroy(IrxRbApiBuilder * arg0, char* error) {
    return irx::api_boundary(error, [&] { irx_rb_impl_builder_destroy(arg0); });
}
int32_t irx_rb_api_builder_close(IrxRbApiBuilder * arg0, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_builder_close(arg0); });
}
int32_t irx_rb_api_reader_destroy(IrxRbApiReader * arg0, char* error) {
    return irx::api_boundary(error, [&] { irx_rb_impl_reader_destroy(arg0); });
}
int32_t irx_rb_api_reader_close(IrxRbApiReader * arg0, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_reader_close(arg0); });
}
int32_t irx_rb_api_writer_destroy(IrxRbApiWriter * arg0, char* error) {
    return irx::api_boundary(error, [&] { irx_rb_impl_writer_destroy(arg0); });
}
int32_t irx_rb_api_writer_close(IrxRbApiWriter * arg0, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_writer_close(arg0); });
}
int32_t irx_rb_api_schema_add(IrxRbApiSchema * arg0, const char * arg1, int32_t arg2, int32_t arg3, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_schema_add(arg0, arg1, arg2, arg3); });
}
int32_t irx_rb_api_schema_count(IrxRbApiSchema * arg0, int32_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_schema_count(arg0); });
}
int32_t irx_rb_api_schema_name(IrxRbApiSchema * arg0, int32_t arg1, char ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_schema_name(arg0, arg1); });
}
int32_t irx_rb_api_schema_type(IrxRbApiSchema * arg0, int32_t arg1, int32_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_schema_type(arg0, arg1); });
}
int32_t irx_rb_api_schema_nullable(IrxRbApiSchema * arg0, int32_t arg1, int32_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_schema_nullable(arg0, arg1); });
}
int32_t irx_rb_api_schema_type_name(IrxRbApiSchema * arg0, int32_t arg1, char ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_schema_type_name(arg0, arg1); });
}
int32_t irx_rb_api_schema_equal(IrxRbApiSchema * arg0, IrxRbApiSchema * arg1, int32_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_schema_equal(arg0, arg1); });
}
int32_t irx_rb_api_builder_finish(IrxRbApiBuilder * arg0, IrxRbApiBatch * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_builder_finish(arg0, arg1); });
}
int32_t irx_rb_api_batch_rows(IrxRbApiBatch * arg0, int64_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_batch_rows(arg0); });
}
int32_t irx_rb_api_batch_columns(IrxRbApiBatch * arg0, int32_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_batch_columns(arg0); });
}
int32_t irx_rb_api_batch_schema(IrxRbApiBatch * arg0, IrxRbApiSchema * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_batch_schema(arg0, arg1); });
}
int32_t irx_rb_api_batch_null(IrxRbApiBatch * arg0, int32_t arg1, int64_t arg2, int32_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_batch_null(arg0, arg1, arg2); });
}
int32_t irx_rb_api_append_i8(IrxRbApiBuilder * arg0, int32_t arg1, int8_t arg2, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_append_i8(arg0, arg1, arg2); });
}
int32_t irx_rb_api_get_i8(IrxRbApiBatch * arg0, int32_t arg1, int64_t arg2, int8_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_get_i8(arg0, arg1, arg2); });
}
int32_t irx_rb_api_append_i16(IrxRbApiBuilder * arg0, int32_t arg1, int16_t arg2, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_append_i16(arg0, arg1, arg2); });
}
int32_t irx_rb_api_get_i16(IrxRbApiBatch * arg0, int32_t arg1, int64_t arg2, int16_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_get_i16(arg0, arg1, arg2); });
}
int32_t irx_rb_api_append_i32(IrxRbApiBuilder * arg0, int32_t arg1, int32_t arg2, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_append_i32(arg0, arg1, arg2); });
}
int32_t irx_rb_api_get_i32(IrxRbApiBatch * arg0, int32_t arg1, int64_t arg2, int32_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_get_i32(arg0, arg1, arg2); });
}
int32_t irx_rb_api_append_i64(IrxRbApiBuilder * arg0, int32_t arg1, int64_t arg2, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_append_i64(arg0, arg1, arg2); });
}
int32_t irx_rb_api_get_i64(IrxRbApiBatch * arg0, int32_t arg1, int64_t arg2, int64_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_get_i64(arg0, arg1, arg2); });
}
int32_t irx_rb_api_append_f32(IrxRbApiBuilder * arg0, int32_t arg1, float arg2, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_append_f32(arg0, arg1, arg2); });
}
int32_t irx_rb_api_get_f32(IrxRbApiBatch * arg0, int32_t arg1, int64_t arg2, float* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_get_f32(arg0, arg1, arg2); });
}
int32_t irx_rb_api_append_f64(IrxRbApiBuilder * arg0, int32_t arg1, double arg2, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_append_f64(arg0, arg1, arg2); });
}
int32_t irx_rb_api_get_f64(IrxRbApiBatch * arg0, int32_t arg1, int64_t arg2, double* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_get_f64(arg0, arg1, arg2); });
}
int32_t irx_rb_api_append_bool(IrxRbApiBuilder * arg0, int32_t arg1, int32_t arg2, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_append_bool(arg0, arg1, arg2); });
}
int32_t irx_rb_api_get_bool(IrxRbApiBatch * arg0, int32_t arg1, int64_t arg2, int32_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_get_bool(arg0, arg1, arg2); });
}
int32_t irx_rb_api_append_date(IrxRbApiBuilder * arg0, int32_t arg1, int64_t arg2, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_append_date(arg0, arg1, arg2); });
}
int32_t irx_rb_api_get_date(IrxRbApiBatch * arg0, int32_t arg1, int64_t arg2, int64_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_get_date(arg0, arg1, arg2); });
}
int32_t irx_rb_api_append_timestamp(IrxRbApiBuilder * arg0, int32_t arg1, int64_t arg2, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_append_timestamp(arg0, arg1, arg2); });
}
int32_t irx_rb_api_get_timestamp(IrxRbApiBatch * arg0, int32_t arg1, int64_t arg2, int64_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_get_timestamp(arg0, arg1, arg2); });
}
int32_t irx_rb_api_append_time(IrxRbApiBuilder * arg0, int32_t arg1, int64_t arg2, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_append_time(arg0, arg1, arg2); });
}
int32_t irx_rb_api_get_time(IrxRbApiBatch * arg0, int32_t arg1, int64_t arg2, int64_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_get_time(arg0, arg1, arg2); });
}
int32_t irx_rb_api_append_utf8(IrxRbApiBuilder * arg0, int32_t arg1, const char * arg2, char* error) {
    if (!arg0 || !arg2) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_append_utf8(arg0, arg1, arg2); });
}
int32_t irx_rb_api_get_utf8(IrxRbApiBatch * arg0, int32_t arg1, int64_t arg2, char ** result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_get_utf8(arg0, arg1, arg2); });
}
int32_t irx_rb_api_append_null(IrxRbApiBuilder * arg0, int32_t arg1, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_append_null(arg0, arg1); });
}
int32_t irx_rb_api_reader_file(IrxRbApiReader * arg0, const char * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_reader_file(arg0, arg1); });
}
int32_t irx_rb_api_reader_stream(IrxRbApiReader * arg0, const char * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_reader_stream(arg0, arg1); });
}
int32_t irx_rb_api_reader_tcp(IrxRbApiReader * arg0, const char * arg1, int32_t arg2, int32_t arg3, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_reader_tcp(arg0, arg1, arg2, arg3); });
}
int32_t irx_rb_api_writer_file(IrxRbApiWriter * arg0, const char * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_writer_file(arg0, arg1); });
}
int32_t irx_rb_api_writer_stream(IrxRbApiWriter * arg0, const char * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_writer_stream(arg0, arg1); });
}
int32_t irx_rb_api_writer_tcp(IrxRbApiWriter * arg0, const char * arg1, int32_t arg2, int32_t arg3, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_writer_tcp(arg0, arg1, arg2, arg3); });
}
int32_t irx_rb_api_writer_write(IrxRbApiWriter * arg0, IrxRbApiBatch * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_writer_write(arg0, arg1); });
}
int32_t irx_rb_api_reader_next(IrxRbApiReader * arg0, int32_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_reader_next(arg0); });
}
int32_t irx_rb_api_reader_batch(IrxRbApiReader * arg0, IrxRbApiBatch * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_reader_batch(arg0, arg1); });
}
int32_t irx_rb_api_reader_schema(IrxRbApiReader * arg0, IrxRbApiSchema * arg1, char* error) {
    if (!arg0 || !arg1) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_reader_schema(arg0, arg1); });
}
int32_t irx_rb_api_batch_export_stream(IrxRbApiBatch * arg0, int64_t arg1, int32_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_batch_export_stream(arg0, arg1); });
}
int32_t irx_rb_api_batch_export(IrxRbApiBatch * arg0, int64_t arg1, int64_t arg2, int32_t* result, char* error) {
    if (result) *result = {};
    if (!result) return irx::api_error(error, IRX_ERR_NULLPTR, "missing result slot");
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { *result = irx_rb_impl_batch_export(arg0, arg1, arg2); });
}
int32_t irx_rb_api_batch_import(IrxRbApiBatch * arg0, int64_t arg1, int64_t arg2, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_batch_import(arg0, arg1, arg2); });
}
int32_t irx_rb_api_reader_import(IrxRbApiReader * arg0, int64_t arg1, char* error) {
    if (!arg0) return irx::api_error(error, IRX_ERR_NULLPTR, "null argument");
    return irx::api_boundary(error, [&] { irx_rb_impl_reader_import(arg0, arg1); });
}
