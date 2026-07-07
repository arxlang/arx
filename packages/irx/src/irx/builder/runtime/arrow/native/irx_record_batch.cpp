// Copyright IRx contributors.

#include "irx_record_batch.h"

#include <arrow/api.h>
#include <arrow/io/api.h>
#include <arrow/ipc/api.h>
#include <arrow/result.h>
#include <arrow/status.h>
#include <arrow/type.h>

#include <cstring>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

static thread_local std::string tl_errmsg;

static int set_err(const std::string &msg, int code) {
    tl_errmsg = msg;
    return code;
}

static int set_err(const arrow::Status &st, int code = IRX_ERR_ARROW) {
    tl_errmsg = st.ToString();
    return code;
}

const char *irx_record_batch_errmsg(void) {
    // Hand the message to a holder and clear the live buffer, so a second
    // read (with no error in between) returns "" instead of a stale message.
    // The holder keeps the returned pointer valid until the next read.
    static thread_local std::string consumed;
    consumed = std::move(tl_errmsg);
    tl_errmsg.clear();
    return consumed.c_str();
}

static std::shared_ptr<arrow::DataType> arrow_type(IrxColumnType t) {
    switch (t) {
    case IRX_COL_INT8:    return arrow::int8();
    case IRX_COL_INT16:   return arrow::int16();
    case IRX_COL_INT32:   return arrow::int32();
    case IRX_COL_INT64:   return arrow::int64();
    case IRX_COL_UINT8:   return arrow::uint8();
    case IRX_COL_UINT16:  return arrow::uint16();
    case IRX_COL_UINT32:  return arrow::uint32();
    case IRX_COL_UINT64:  return arrow::uint64();
    case IRX_COL_FLOAT32: return arrow::float32();
    case IRX_COL_FLOAT64: return arrow::float64();
    case IRX_COL_BOOL:    return arrow::boolean();
    case IRX_COL_UTF8:       return arrow::utf8();
    case IRX_COL_LARGE_UTF8: return arrow::large_utf8();
    }
    return nullptr;
}

static IrxColumnType col_type_from_arrow(const arrow::DataType &dt) {
    switch (dt.id()) {
    case arrow::Type::INT8:    return IRX_COL_INT8;
    case arrow::Type::INT16:   return IRX_COL_INT16;
    case arrow::Type::INT32:   return IRX_COL_INT32;
    case arrow::Type::INT64:   return IRX_COL_INT64;
    case arrow::Type::UINT8:   return IRX_COL_UINT8;
    case arrow::Type::UINT16:  return IRX_COL_UINT16;
    case arrow::Type::UINT32:  return IRX_COL_UINT32;
    case arrow::Type::UINT64:  return IRX_COL_UINT64;
    case arrow::Type::FLOAT:   return IRX_COL_FLOAT32;
    case arrow::Type::DOUBLE:  return IRX_COL_FLOAT64;
    case arrow::Type::BOOL:    return IRX_COL_BOOL;
    case arrow::Type::STRING:       return IRX_COL_UTF8;
    case arrow::Type::LARGE_STRING: return IRX_COL_LARGE_UTF8;
    default:                   return static_cast<IrxColumnType>(-1);
    }
}

struct IrxRbSchema_ {
    std::shared_ptr<arrow::Schema>             schema;
    std::vector<IrxColumnType>                 col_types;
    /* Parallel vector used by the reader-side schema handle (owned). */
    bool                                       reader_owned{false};
};

struct IrxRbBuilder_ {
    const IrxRbSchema_                        *schema_ref;
    std::vector<std::unique_ptr<arrow::ArrayBuilder>> builders;
};

struct IrxRbBatch_ {
    std::shared_ptr<arrow::RecordBatch>        batch;
    /* Cached col_types mirrored from the schema for fast type checks. */
    std::vector<IrxColumnType>                 col_types;
};

struct IrxRbStreamWriter_ {
    std::shared_ptr<arrow::io::OutputStream>   sink;
    std::shared_ptr<arrow::ipc::RecordBatchWriter> writer;
    /* For buffer-based writers. */
    std::shared_ptr<arrow::io::BufferOutputStream> buf_sink;
    bool                                       closed{false};
    /* Cached serialised bytes (valid after close for buffer writers). */
    std::shared_ptr<arrow::Buffer>             finished_buf;
};

struct IrxRbStreamReader_ {
    std::shared_ptr<arrow::ipc::RecordBatchStreamReader> reader;
    /* Schema handle exposed to callers (not released by caller). */
    IrxRbSchema_                               schema_handle;
};

#define GUARD(ptr) \
    do { if (!(ptr)) return set_err("null pointer argument", IRX_ERR_NULLPTR); } while (0)

int irx_rb_schema_create(IrxRbSchema **out) {
    GUARD(out);
    *out = new IrxRbSchema_();
    (*out)->schema = arrow::schema({});
    return IRX_OK;
}

int irx_rb_schema_add_field(IrxRbSchema *s,
                             const char  *name,
                             IrxColumnType type,
                             int           nullable) {
    GUARD(s); GUARD(name);
    auto dt = arrow_type(type);
    if (!dt)
        return set_err("unknown IrxColumnType", IRX_ERR_TYPE);

    auto field = arrow::field(name, dt, nullable != 0);
    auto new_schema = s->schema->AddField(s->schema->num_fields(), field);
    if (!new_schema.ok())
        return set_err(new_schema.status());
    s->schema = *new_schema;
    s->col_types.push_back(type);
    return IRX_OK;
}

int irx_rb_schema_num_fields(const IrxRbSchema *s) {
    if (!s) return IRX_ERR_NULLPTR;
    return s->schema->num_fields();
}

void irx_rb_schema_release(IrxRbSchema *s) {
    delete s;
}

static std::unique_ptr<arrow::ArrayBuilder>
make_builder(IrxColumnType t, arrow::MemoryPool *pool) {
    std::unique_ptr<arrow::ArrayBuilder> b;
    switch (t) {
    case IRX_COL_INT8:    b = std::make_unique<arrow::Int8Builder>(pool);    break;
    case IRX_COL_INT16:   b = std::make_unique<arrow::Int16Builder>(pool);   break;
    case IRX_COL_INT32:   b = std::make_unique<arrow::Int32Builder>(pool);   break;
    case IRX_COL_INT64:   b = std::make_unique<arrow::Int64Builder>(pool);   break;
    case IRX_COL_UINT8:   b = std::make_unique<arrow::UInt8Builder>(pool);   break;
    case IRX_COL_UINT16:  b = std::make_unique<arrow::UInt16Builder>(pool);  break;
    case IRX_COL_UINT32:  b = std::make_unique<arrow::UInt32Builder>(pool);  break;
    case IRX_COL_UINT64:  b = std::make_unique<arrow::UInt64Builder>(pool);  break;
    case IRX_COL_FLOAT32: b = std::make_unique<arrow::FloatBuilder>(pool);   break;
    case IRX_COL_FLOAT64: b = std::make_unique<arrow::DoubleBuilder>(pool);  break;
    case IRX_COL_BOOL:    b = std::make_unique<arrow::BooleanBuilder>(pool); break;
    case IRX_COL_UTF8:       b = std::make_unique<arrow::StringBuilder>(pool);      break;
    case IRX_COL_LARGE_UTF8: b = std::make_unique<arrow::LargeStringBuilder>(pool); break;
    }
    return b;
}

int irx_rb_builder_create(const IrxRbSchema *schema, IrxRbBuilder **out) {
    GUARD(schema); GUARD(out);
    auto *b = new IrxRbBuilder_();
    b->schema_ref = schema;
    auto *pool = arrow::default_memory_pool();
    for (auto ct : schema->col_types) {
        auto bldr = make_builder(ct, pool);
        if (!bldr) {
            delete b;
            return set_err("failed to create column builder", IRX_ERR_ARROW);
        }
        b->builders.push_back(std::move(bldr));
    }
    *out = b;
    return IRX_OK;
}

/* Append helpers are written out longhand: Arrow builder class names
 * (Int8Builder, FloatBuilder, …) do not map mechanically from IrxColumnType,
 * so a token-pasting macro cannot cover every case cleanly. */
int irx_rb_builder_append_int8(IrxRbBuilder *b, int col, int8_t v) {
    GUARD(b);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->schema_ref->col_types[col] != IRX_COL_INT8)
        return set_err("type mismatch on append", IRX_ERR_TYPE);
    auto st = static_cast<arrow::Int8Builder *>(b->builders[col].get())->Append(v);
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}
int irx_rb_builder_append_int16(IrxRbBuilder *b, int col, int16_t v) {
    GUARD(b);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->schema_ref->col_types[col] != IRX_COL_INT16)
        return set_err("type mismatch on append", IRX_ERR_TYPE);
    auto st = static_cast<arrow::Int16Builder *>(b->builders[col].get())->Append(v);
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}
int irx_rb_builder_append_int32(IrxRbBuilder *b, int col, int32_t v) {
    GUARD(b);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->schema_ref->col_types[col] != IRX_COL_INT32)
        return set_err("type mismatch on append", IRX_ERR_TYPE);
    auto st = static_cast<arrow::Int32Builder *>(b->builders[col].get())->Append(v);
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}
int irx_rb_builder_append_int64(IrxRbBuilder *b, int col, int64_t v) {
    GUARD(b);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->schema_ref->col_types[col] != IRX_COL_INT64)
        return set_err("type mismatch on append", IRX_ERR_TYPE);
    auto st = static_cast<arrow::Int64Builder *>(b->builders[col].get())->Append(v);
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}
int irx_rb_builder_append_uint8(IrxRbBuilder *b, int col, uint8_t v) {
    GUARD(b);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->schema_ref->col_types[col] != IRX_COL_UINT8)
        return set_err("type mismatch on append", IRX_ERR_TYPE);
    auto st = static_cast<arrow::UInt8Builder *>(b->builders[col].get())->Append(v);
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}
int irx_rb_builder_append_uint16(IrxRbBuilder *b, int col, uint16_t v) {
    GUARD(b);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->schema_ref->col_types[col] != IRX_COL_UINT16)
        return set_err("type mismatch on append", IRX_ERR_TYPE);
    auto st = static_cast<arrow::UInt16Builder *>(b->builders[col].get())->Append(v);
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}
int irx_rb_builder_append_uint32(IrxRbBuilder *b, int col, uint32_t v) {
    GUARD(b);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->schema_ref->col_types[col] != IRX_COL_UINT32)
        return set_err("type mismatch on append", IRX_ERR_TYPE);
    auto st = static_cast<arrow::UInt32Builder *>(b->builders[col].get())->Append(v);
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}
int irx_rb_builder_append_uint64(IrxRbBuilder *b, int col, uint64_t v) {
    GUARD(b);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->schema_ref->col_types[col] != IRX_COL_UINT64)
        return set_err("type mismatch on append", IRX_ERR_TYPE);
    auto st = static_cast<arrow::UInt64Builder *>(b->builders[col].get())->Append(v);
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}
int irx_rb_builder_append_float32(IrxRbBuilder *b, int col, float v) {
    GUARD(b);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->schema_ref->col_types[col] != IRX_COL_FLOAT32)
        return set_err("type mismatch on append", IRX_ERR_TYPE);
    auto st = static_cast<arrow::FloatBuilder *>(b->builders[col].get())->Append(v);
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}
int irx_rb_builder_append_float64(IrxRbBuilder *b, int col, double v) {
    GUARD(b);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->schema_ref->col_types[col] != IRX_COL_FLOAT64)
        return set_err("type mismatch on append", IRX_ERR_TYPE);
    auto st = static_cast<arrow::DoubleBuilder *>(b->builders[col].get())->Append(v);
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}
int irx_rb_builder_append_bool(IrxRbBuilder *b, int col, int v) {
    GUARD(b);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->schema_ref->col_types[col] != IRX_COL_BOOL)
        return set_err("type mismatch on append", IRX_ERR_TYPE);
    auto st = static_cast<arrow::BooleanBuilder *>(b->builders[col].get())->Append(v != 0);
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}
/* Append a UTF-8 string to the specified column.
 * Works with both UTF8 and LARGE_UTF8 column types.
 * The string data is copied internally, so the input pointer does not need to remain valid.
 * Interior NUL bytes are allowed; nbytes determines the string length. */
int irx_rb_builder_append_utf8(IrxRbBuilder *b, int col,
                               const char *data, int64_t nbytes)
{
    GUARD(b);
    GUARD(data);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    std::string_view view(data, static_cast<size_t>(nbytes));
    arrow::Status st;
    switch (b->schema_ref->col_types[col])
    {
    case IRX_COL_UTF8:
        st = static_cast<arrow::StringBuilder *>(
                 b->builders[col].get())
                 ->Append(view);
        break;
    case IRX_COL_LARGE_UTF8:
        st = static_cast<arrow::LargeStringBuilder *>(
                 b->builders[col].get())
                 ->Append(view);
        break;
    default:
        return set_err("type mismatch on append", IRX_ERR_TYPE);
    }
    if (!st.ok())
        return set_err(st);
    return IRX_OK;
}
int irx_rb_builder_append_null(IrxRbBuilder *b, int col) {
    GUARD(b);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    auto st = b->builders[col]->AppendNull();
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}

int irx_rb_builder_finish(IrxRbBuilder *b, IrxRbBatch **out) {
    GUARD(b); GUARD(out);

    /* Verify all columns have the same length. */
    if (!b->builders.empty()) {
        int64_t len = b->builders[0]->length();
        for (size_t i = 1; i < b->builders.size(); ++i) {
            if (b->builders[i]->length() != len)
                return set_err("column length mismatch in RecordBatch", IRX_ERR_ARROW);
        }
    }

    std::vector<std::shared_ptr<arrow::Array>> arrays;
    arrays.reserve(b->builders.size());
    for (auto &bldr : b->builders) {
        std::shared_ptr<arrow::Array> arr;
        auto st = bldr->Finish(&arr);
        if (!st.ok()) return set_err(st);
        arrays.push_back(std::move(arr));
    }

    auto rb = arrow::RecordBatch::Make(b->schema_ref->schema,
                                        arrays.empty() ? 0 : arrays[0]->length(),
                                        arrays);
    auto *batch = new IrxRbBatch_();
    batch->batch     = std::move(rb);
    batch->col_types = b->schema_ref->col_types;
    *out = batch;
    return IRX_OK;
}

void irx_rb_builder_release(IrxRbBuilder *b) {
    delete b;
}

int64_t irx_rb_batch_num_rows(const IrxRbBatch *batch) {
    if (!batch) return IRX_ERR_NULLPTR;
    return batch->batch->num_rows();
}

int irx_rb_batch_num_columns(const IrxRbBatch *batch) {
    if (!batch) return IRX_ERR_NULLPTR;
    return batch->batch->num_columns();
}

/* Bounds-check helper — returns true and sets error on failure. */
static bool check_bounds(const IrxRbBatch *b, int col, int64_t row) {
    if (col < 0 || col >= b->batch->num_columns()) {
        set_err("column index out of bounds", IRX_ERR_OOB);
        return true;
    }
    if (row < 0 || row >= b->batch->num_rows()) {
        set_err("row index out of bounds", IRX_ERR_OOB);
        return true;
    }
    return false;
}

#define GET_IMPL(fname, ctype, arrowarray, irxtype)                         \
int fname(const IrxRbBatch *b, int col, int64_t row, ctype *out) {        \
    GUARD(b); GUARD(out);                                                   \
    if (check_bounds(b, col, row)) return IRX_ERR_OOB;                     \
    if (b->col_types[col] != irxtype)                                       \
        return set_err("type mismatch on get", IRX_ERR_TYPE);               \
    auto *arr = static_cast<const arrow::arrowarray *>(                     \
        b->batch->column(col).get());                                       \
    *out = arr->Value(row);                                                 \
    return IRX_OK;                                                          \
}

GET_IMPL(irx_rb_batch_get_int8,    int8_t,   Int8Array,    IRX_COL_INT8)
GET_IMPL(irx_rb_batch_get_int16,   int16_t,  Int16Array,   IRX_COL_INT16)
GET_IMPL(irx_rb_batch_get_int32,   int32_t,  Int32Array,   IRX_COL_INT32)
GET_IMPL(irx_rb_batch_get_int64,   int64_t,  Int64Array,   IRX_COL_INT64)
GET_IMPL(irx_rb_batch_get_uint8,   uint8_t,  UInt8Array,   IRX_COL_UINT8)
GET_IMPL(irx_rb_batch_get_uint16,  uint16_t, UInt16Array,  IRX_COL_UINT16)
GET_IMPL(irx_rb_batch_get_uint32,  uint32_t, UInt32Array,  IRX_COL_UINT32)
GET_IMPL(irx_rb_batch_get_uint64,  uint64_t, UInt64Array,  IRX_COL_UINT64)
GET_IMPL(irx_rb_batch_get_float32, float,    FloatArray,   IRX_COL_FLOAT32)
GET_IMPL(irx_rb_batch_get_float64, double,   DoubleArray,  IRX_COL_FLOAT64)

int irx_rb_batch_get_bool(const IrxRbBatch *b, int col, int64_t row, int *out) {
    GUARD(b); GUARD(out);
    if (check_bounds(b, col, row)) return IRX_ERR_OOB;
    if (b->col_types[col] != IRX_COL_BOOL)
        return set_err("type mismatch on get", IRX_ERR_TYPE);
    auto *arr = static_cast<const arrow::BooleanArray *>(b->batch->column(col).get());
    *out = arr->Value(row) ? 1 : 0;
    return IRX_OK;
}

int irx_rb_batch_get_utf8(const IrxRbBatch *b, int col, int64_t row,
                          const char **out, int64_t *len)
{
    GUARD(b);
    GUARD(out);
    GUARD(len);
    if (check_bounds(b, col, row))
        return IRX_ERR_OOB;
    std::string_view view;
    switch (b->col_types[col])
    {
    case IRX_COL_UTF8:
        view = static_cast<const arrow::StringArray *>(
                   b->batch->column(col).get())
                   ->GetView(row);
        break;
    case IRX_COL_LARGE_UTF8:
        view = static_cast<const arrow::LargeStringArray *>(
                   b->batch->column(col).get())
                   ->GetView(row);
        break;
    default:
        return set_err("type mismatch on get", IRX_ERR_TYPE);
    }
    *out = view.data();
    *len = static_cast<int64_t>(view.size());
    return IRX_OK;
}

int irx_rb_batch_is_null(const IrxRbBatch *b, int col, int64_t row, int *out) {
    GUARD(b); GUARD(out);
    if (check_bounds(b, col, row)) return IRX_ERR_OOB;
    *out = b->batch->column(col)->IsNull(row) ? 1 : 0;
    return IRX_OK;
}

int irx_rb_batch_value_buffer(const IrxRbBatch *b, int col,
                               const void **buf, int64_t *len) {
    GUARD(b); GUARD(buf); GUARD(len);
    if (col < 0 || col >= b->batch->num_columns())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    auto arr = b->batch->column(col);
    auto &data = *arr->data();
    /* Buffer 1 is the value buffer for fixed-width types. */
    if (data.buffers.size() < 2 || !data.buffers[1])
        return set_err("column has no value buffer (variable-width type?)", IRX_ERR_TYPE);
    /* Account for a non-zero logical offset (sliced arrays): the value buffer
     * starts before the array's first logical element. Advance by
     * offset * byte_width so the returned pointer aligns with element 0. */
    const auto *type = arr->type().get();
    const auto *fw = dynamic_cast<const arrow::FixedWidthType *>(type);
    if (fw == nullptr)
        return set_err("column is not a fixed-width type", IRX_ERR_TYPE);
    const int64_t byte_width = fw->bit_width() / 8;
    const uint8_t *base = data.buffers[1]->data();
    *buf = base + data.offset * byte_width;
    *len = arr->length();
    return IRX_OK;
}

void irx_rb_batch_release(IrxRbBatch *batch) {
    delete batch;
}

int irx_rb_stream_writer_open_file(const IrxRbSchema   *schema,
                                    const char          *path,
                                    IrxRbStreamWriter  **out) {
    GUARD(schema); GUARD(path); GUARD(out);

    auto open_result = arrow::io::FileOutputStream::Open(path);
    if (!open_result.ok()) return set_err(open_result.status(), IRX_ERR_IO);

    auto sink = *open_result;
    auto writer_result = arrow::ipc::MakeStreamWriter(sink, schema->schema);
    if (!writer_result.ok()) return set_err(writer_result.status());

    auto *w = new IrxRbStreamWriter_();
    w->sink   = sink;
    w->writer = *writer_result;
    *out = w;
    return IRX_OK;
}

int irx_rb_stream_writer_open_buffer(const IrxRbSchema   *schema,
                                      IrxRbStreamWriter  **out) {
    GUARD(schema); GUARD(out);

    auto buf_sink_result = arrow::io::BufferOutputStream::Create();
    if (!buf_sink_result.ok()) return set_err(buf_sink_result.status(), IRX_ERR_IO);

    auto buf_sink = *buf_sink_result;
    auto writer_result = arrow::ipc::MakeStreamWriter(buf_sink, schema->schema);
    if (!writer_result.ok()) return set_err(writer_result.status());

    auto *w = new IrxRbStreamWriter_();
    w->buf_sink = buf_sink;
    w->sink     = buf_sink;
    w->writer   = *writer_result;
    *out = w;
    return IRX_OK;
}

int irx_rb_stream_writer_write_batch(IrxRbStreamWriter *w,
                                      const IrxRbBatch  *batch) {
    GUARD(w); GUARD(batch);
    if (w->closed) return set_err("writer already closed", IRX_ERR_IO);
    auto st = w->writer->WriteRecordBatch(*batch->batch);
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}

int irx_rb_stream_writer_close(IrxRbStreamWriter *w) {
    GUARD(w);
    if (w->closed) return IRX_OK;
    auto st = w->writer->Close();
    if (!st.ok()) return set_err(st);
    if (w->buf_sink) {
        auto buf_result = w->buf_sink->Finish();
        if (!buf_result.ok()) return set_err(buf_result.status(), IRX_ERR_IO);
        w->finished_buf = *buf_result;
    } else {
        auto st2 = w->sink->Close();
        if (!st2.ok()) return set_err(st2, IRX_ERR_IO);
    }
    w->closed = true;
    return IRX_OK;
}

int irx_rb_stream_writer_buffer_data(const IrxRbStreamWriter *w,
                                      const uint8_t **data,
                                      int64_t        *size) {
    GUARD(w); GUARD(data); GUARD(size);
    if (!w->closed)
        return set_err("writer not yet closed; call irx_rb_stream_writer_close first",
                       IRX_ERR_IO);
    if (!w->buf_sink || !w->finished_buf)
        return set_err("writer is file-based, not buffer-based", IRX_ERR_IO);
    *data = w->finished_buf->data();
    *size = w->finished_buf->size();
    return IRX_OK;
}

void irx_rb_stream_writer_release(IrxRbStreamWriter *w) {
    if (!w) return;
    if (!w->closed && w->writer) {
        (void)w->writer->Close();
    }
    delete w;
}

static int open_stream_reader(std::shared_ptr<arrow::io::InputStream> stream,
                               IrxRbStreamReader **out) {
    auto reader_result = arrow::ipc::RecordBatchStreamReader::Open(stream);
    if (!reader_result.ok()) return set_err(reader_result.status());

    auto *r = new IrxRbStreamReader_();
    r->reader = *reader_result;

    /* Populate the schema handle from the stream schema. */
    auto arrow_schema = r->reader->schema();
    r->schema_handle.schema       = arrow_schema;
    r->schema_handle.reader_owned = true;
    for (int i = 0; i < arrow_schema->num_fields(); ++i) {
        auto &field = *arrow_schema->field(i);
        auto ct = col_type_from_arrow(*field.type());
        if (static_cast<int>(ct) < 0) {
            delete r;
            return set_err(
                "stream column '" + field.name() + "' has type '" +
                    field.type()->ToString() +
                    "' which is not supported by this reader",
                IRX_ERR_TYPE);
        }
        r->schema_handle.col_types.push_back(ct);
    }

    *out = r;
    return IRX_OK;
}

int irx_rb_stream_reader_open_file(const char         *path,
                                    IrxRbStreamReader **out) {
    GUARD(path); GUARD(out);
    auto open_result = arrow::io::ReadableFile::Open(path);
    if (!open_result.ok()) return set_err(open_result.status(), IRX_ERR_IO);
    return open_stream_reader(*open_result, out);
}

int irx_rb_stream_reader_open_buffer(const uint8_t      *data,
                                      int64_t             size,
                                      IrxRbStreamReader **out) {
    GUARD(data); GUARD(out);
    /* Copy the caller's bytes into an Arrow-owned buffer so the reader (and
     * any batches it yields) stay valid regardless of the caller's buffer
     * lifetime. Avoids a use-after-free when the source bytes are freed
     * before the reader is closed. */
    auto buf_res = arrow::AllocateBuffer(size);
    if (!buf_res.ok()) return set_err(buf_res.status(), IRX_ERR_IO);
    std::shared_ptr<arrow::Buffer> buf = std::move(*buf_res);
    if (size > 0) std::memcpy(const_cast<uint8_t*>(buf->data()), data, size);
    auto stream = std::make_shared<arrow::io::BufferReader>(buf);
    return open_stream_reader(stream, out);
}

int irx_rb_stream_reader_next_batch(IrxRbStreamReader *r,
                                     IrxRbBatch       **batch) {
    GUARD(r); GUARD(batch);
    std::shared_ptr<arrow::RecordBatch> rb;
    auto st = r->reader->ReadNext(&rb);
    if (!st.ok()) return set_err(st);
    if (!rb) {
        *batch = nullptr;
        return IRX_EOF;
    }
    auto *b = new IrxRbBatch_();
    b->batch     = std::move(rb);
    b->col_types = r->schema_handle.col_types;
    *batch = b;
    return IRX_OK;
}

const IrxRbSchema *irx_rb_stream_reader_schema(const IrxRbStreamReader *r) {
    if (!r) return nullptr;
    return &r->schema_handle;
}

void irx_rb_stream_reader_close(IrxRbStreamReader *r) {
    delete r;
}
