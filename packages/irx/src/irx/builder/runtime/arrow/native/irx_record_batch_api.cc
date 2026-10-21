// Copyright IRx contributors.
// Checked value-returning facade for languages without C out-parameters.
#include "irx_record_batch_api.h"
#include <cstdlib>
#include <cstring>
#include <memory>
#include <string_view>
extern "C" void __arx_runtime_fail(const char *, const char *, int, int,
                                   const char *);
namespace {
[[noreturn]] void fail(const char *message) {
    __arx_runtime_fail("ARX-RUNTIME-ARROW-001", nullptr, 0, 0, message);
    std::abort();
}
void checked(int status) {
    if (status < 0)
        fail(irx_record_batch_errmsg());
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
        fail("out of memory copying Arrow text");
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

IrxRbApiSchema *irx_rb_api_schema_new(void) {
    auto result = std::make_unique<IrxRbApiSchema>();
    checked(irx_rb_schema_create(&result->value));
    return result.release();
}

IrxRbApiBatch *irx_rb_api_batch_new(void) {
    auto result = std::make_unique<IrxRbApiBatch>();
    return result.release();
}

IrxRbApiReader *irx_rb_api_reader_new(void) {
    auto result = std::make_unique<IrxRbApiReader>();
    return result.release();
}

IrxRbApiBuilder *irx_rb_api_builder_new(IrxRbApiSchema *schema) {
    auto result = std::make_unique<IrxRbApiBuilder>();
    checked(irx_rb_builder_create(schema->get(), &result->value));
    return result.release();
}

IrxRbApiWriter *irx_rb_api_writer_new(IrxRbApiSchema *schema) {
    auto result = std::make_unique<IrxRbApiWriter>();
    checked(irx_rb_schema_clone(schema->get(), &result->schema.value));
    return result.release();
}

void irx_rb_api_schema_destroy(IrxRbApiSchema *box) { delete box; }

void irx_rb_api_schema_close(IrxRbApiSchema *box) { box->reset(); }

void irx_rb_api_batch_destroy(IrxRbApiBatch *box) { delete box; }

void irx_rb_api_batch_close(IrxRbApiBatch *box) { box->reset(); }

void irx_rb_api_builder_destroy(IrxRbApiBuilder *box) { delete box; }

void irx_rb_api_builder_close(IrxRbApiBuilder *box) { box->reset(); }

void irx_rb_api_reader_destroy(IrxRbApiReader *box) { delete box; }

void irx_rb_api_reader_close(IrxRbApiReader *box) {
    box->current.reset();
    box->reset();
}

void irx_rb_api_writer_destroy(IrxRbApiWriter *box) { delete box; }

void irx_rb_api_writer_close(IrxRbApiWriter *box) {
    if (box->value)
        checked(irx_rb_stream_writer_close(box->value));
    box->reset();
}

void irx_rb_api_schema_add(IrxRbApiSchema *box, const char *name, int32_t type,
                           int32_t nullable) {
    checked(irx_rb_schema_add_field(
        box->get(), name, static_cast<IrxColumnType>(type), nullable));
}

int32_t irx_rb_api_schema_count(IrxRbApiSchema *box) {
    return irx_rb_schema_num_fields(box->get());
}

char *irx_rb_api_schema_name(IrxRbApiSchema *box, int32_t col) {
    const char *name;
    int type, nullable;
    checked(irx_rb_schema_field(box->get(), col, &name, &type, &nullable));
    return owned_text(name, std::strlen(name));
}

int32_t irx_rb_api_schema_type(IrxRbApiSchema *box, int32_t col) {
    const char *name;
    int type, nullable;
    checked(irx_rb_schema_field(box->get(), col, &name, &type, &nullable));
    return type;
}

int32_t irx_rb_api_schema_nullable(IrxRbApiSchema *box, int32_t col) {
    const char *name;
    int type, nullable;
    checked(irx_rb_schema_field(box->get(), col, &name, &type, &nullable));
    return nullable;
}

char *irx_rb_api_schema_type_name(IrxRbApiSchema *box, int32_t col) {
    const char *name;
    checked(irx_rb_schema_type_name(box->get(), col, &name));
    return owned_text(name, std::strlen(name));
}

int32_t irx_rb_api_schema_equal(IrxRbApiSchema *box, IrxRbApiSchema *other) {
    return irx_rb_schema_equal(box->get(), other->get());
}

void irx_rb_api_builder_finish(IrxRbApiBuilder *box, IrxRbApiBatch *out) {
    IrxRbBatch *batch;
    checked(irx_rb_builder_finish(box->get(), &batch));
    out->reset(batch);
}

int64_t irx_rb_api_batch_rows(IrxRbApiBatch *box) {
    return irx_rb_batch_num_rows(box->get());
}

int32_t irx_rb_api_batch_columns(IrxRbApiBatch *box) {
    return irx_rb_batch_num_columns(box->get());
}

void irx_rb_api_batch_schema(IrxRbApiBatch *box, IrxRbApiSchema *out) {
    IrxRbSchema *schema;
    checked(irx_rb_batch_schema(box->get(), &schema));
    out->reset(schema);
}

int32_t irx_rb_api_batch_null(IrxRbApiBatch *box, int32_t col, int64_t row) {
    int result;
    checked(irx_rb_batch_is_null(box->get(), col, row, &result));
    return result;
}

namespace {
void require_value(IrxRbApiBatch *box, int col, int64_t row) {
    if (irx_rb_api_batch_null(box, col, row))
        fail("null Arrow value: call is_null before a typed getter");
}
} // namespace

void irx_rb_api_append_i8(IrxRbApiBuilder *box, int32_t col, int8_t value) {
    checked(irx_rb_builder_append_int8(box->get(), col, value));
}

int8_t irx_rb_api_get_i8(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    int8_t result;
    checked(irx_rb_batch_get_int8(box->get(), col, row, &result));
    return result;
}

void irx_rb_api_append_i16(IrxRbApiBuilder *box, int32_t col, int16_t value) {
    checked(irx_rb_builder_append_int16(box->get(), col, value));
}

int16_t irx_rb_api_get_i16(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    int16_t result;
    checked(irx_rb_batch_get_int16(box->get(), col, row, &result));
    return result;
}

void irx_rb_api_append_i32(IrxRbApiBuilder *box, int32_t col, int32_t value) {
    checked(irx_rb_builder_append_int32(box->get(), col, value));
}

int32_t irx_rb_api_get_i32(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    int32_t result;
    checked(irx_rb_batch_get_int32(box->get(), col, row, &result));
    return result;
}

void irx_rb_api_append_i64(IrxRbApiBuilder *box, int32_t col, int64_t value) {
    checked(irx_rb_builder_append_int64(box->get(), col, value));
}

int64_t irx_rb_api_get_i64(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    int64_t result;
    checked(irx_rb_batch_get_int64(box->get(), col, row, &result));
    return result;
}

void irx_rb_api_append_f32(IrxRbApiBuilder *box, int32_t col, float value) {
    checked(irx_rb_builder_append_float32(box->get(), col, value));
}

float irx_rb_api_get_f32(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    float result;
    checked(irx_rb_batch_get_float32(box->get(), col, row, &result));
    return result;
}

void irx_rb_api_append_f64(IrxRbApiBuilder *box, int32_t col, double value) {
    checked(irx_rb_builder_append_float64(box->get(), col, value));
}

double irx_rb_api_get_f64(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    double result;
    checked(irx_rb_batch_get_float64(box->get(), col, row, &result));
    return result;
}

void irx_rb_api_append_bool(IrxRbApiBuilder *box, int32_t col, int32_t value) {
    checked(irx_rb_builder_append_bool(box->get(), col, value));
}

int32_t irx_rb_api_get_bool(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    int32_t result;
    checked(irx_rb_batch_get_bool(box->get(), col, row, &result));
    return result;
}

void irx_rb_api_append_date(IrxRbApiBuilder *box, int32_t col, int64_t value) {
    checked(irx_rb_builder_append_date(box->get(), col, value));
}

int64_t irx_rb_api_get_date(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    int64_t result;
    checked(irx_rb_batch_get_date(box->get(), col, row, &result));
    return result;
}

void irx_rb_api_append_timestamp(IrxRbApiBuilder *box, int32_t col,
                                 int64_t value) {
    checked(irx_rb_builder_append_timestamp(box->get(), col, value));
}

int64_t irx_rb_api_get_timestamp(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    int64_t result;
    checked(irx_rb_batch_get_timestamp(box->get(), col, row, &result));
    return result;
}

void irx_rb_api_append_time(IrxRbApiBuilder *box, int32_t col, int64_t value) {
    checked(irx_rb_builder_append_time(box->get(), col, value));
}

int64_t irx_rb_api_get_time(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    int64_t result;
    checked(irx_rb_batch_get_time(box->get(), col, row, &result));
    return result;
}

void irx_rb_api_append_utf8(IrxRbApiBuilder *box, int32_t col,
                            const char *value) {
    checked(
        irx_rb_builder_append_utf8(box->get(), col, value, std::strlen(value)));
}

char *irx_rb_api_get_utf8(IrxRbApiBatch *box, int32_t col, int64_t row) {
    require_value(box, col, row);
    const char *data;
    int64_t size;
    checked(irx_rb_batch_get_utf8(box->get(), col, row, &data, &size));
    return owned_text(data, size);
}

void irx_rb_api_append_null(IrxRbApiBuilder *box, int32_t col) {
    checked(irx_rb_builder_append_null(box->get(), col));
}

void irx_rb_api_reader_file(IrxRbApiReader *box, const char *path) {
    if (box->value)
        fail("close Arrow reader before reopening");
    IrxRbStreamReader *result;
    checked(irx_rb_file_reader_open(path, &result));
    box->reset(result);
}

void irx_rb_api_reader_stream(IrxRbApiReader *box, const char *path) {
    if (box->value)
        fail("close Arrow reader before reopening");
    IrxRbStreamReader *result;
    checked(irx_rb_stream_reader_open_file(path, &result));
    box->reset(result);
}

void irx_rb_api_reader_tcp(IrxRbApiReader *box, const char *host, int32_t port,
                           int32_t timeout) {
    if (box->value)
        fail("close Arrow reader before connecting");
    IrxRbStreamReader *result;
    checked(irx_rb_tcp_reader_open(host, port, timeout, &result));
    box->reset(result);
}

void irx_rb_api_writer_file(IrxRbApiWriter *box, const char *path) {
    if (box->value)
        fail("close Arrow writer before reopening");
    IrxRbStreamWriter *result;
    checked(irx_rb_file_writer_open(box->schema.get(), path, &result));
    box->reset(result);
}

void irx_rb_api_writer_stream(IrxRbApiWriter *box, const char *path) {
    if (box->value)
        fail("close Arrow writer before reopening");
    IrxRbStreamWriter *result;
    checked(irx_rb_stream_writer_open_file(box->schema.get(), path, &result));
    box->reset(result);
}

void irx_rb_api_writer_tcp(IrxRbApiWriter *box, const char *host, int32_t port,
                           int32_t timeout) {
    if (box->value)
        fail("close Arrow writer before connecting");
    IrxRbStreamWriter *result;
    checked(irx_rb_tcp_writer_open(box->schema.get(), host, port, timeout,
                                   &result));
    box->reset(result);
}

void irx_rb_api_writer_write(IrxRbApiWriter *box, IrxRbApiBatch *batch) {
    checked(irx_rb_stream_writer_write_batch(box->get(), batch->get()));
}

int32_t irx_rb_api_reader_next(IrxRbApiReader *box) {
    box->current.reset();
    IrxRbBatch *batch;
    int status = irx_rb_stream_reader_next_batch(box->get(), &batch);
    checked(status);
    if (status == IRX_OK)
        box->current.reset(batch);
    return status;
}

void irx_rb_api_reader_batch(IrxRbApiReader *box, IrxRbApiBatch *out) {
    IrxRbBatch *batch;
    checked(irx_rb_batch_clone(box->current.get(), &batch));
    out->reset(batch);
}

void irx_rb_api_reader_schema(IrxRbApiReader *box, IrxRbApiSchema *out) {
    IrxRbSchema *schema;
    checked(
        irx_rb_schema_clone(irx_rb_stream_reader_schema(box->get()), &schema));
    out->reset(schema);
}

int32_t irx_rb_api_batch_export_stream(IrxRbApiBatch *box, int64_t address) {
    return irx_rb_batch_export_stream(
        box->get(),
        reinterpret_cast<ArrowArrayStream *>(static_cast<uintptr_t>(address)));
}

int32_t irx_rb_api_batch_export(IrxRbApiBatch *box, int64_t array,
                                int64_t schema) {
    return irx_rb_batch_export(
        box->get(),
        reinterpret_cast<ArrowArray *>(static_cast<uintptr_t>(array)),
        reinterpret_cast<ArrowSchema *>(static_cast<uintptr_t>(schema)));
}

void irx_rb_api_batch_import(IrxRbApiBatch *box, int64_t array,
                             int64_t schema) {
    IrxRbBatch *batch;
    checked(irx_rb_batch_import(
        reinterpret_cast<ArrowArray *>(static_cast<uintptr_t>(array)),
        reinterpret_cast<ArrowSchema *>(static_cast<uintptr_t>(schema)),
        &batch));
    box->reset(batch);
}

void irx_rb_api_reader_import(IrxRbApiReader *box, int64_t address) {
    if (box->value)
        fail("close Arrow reader before importing");
    IrxRbStreamReader *reader;
    checked(irx_rb_stream_reader_import(
        reinterpret_cast<ArrowArrayStream *>(static_cast<uintptr_t>(address)),
        &reader));
    box->reset(reader);
}
