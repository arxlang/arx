// Copyright IRx contributors.

#include "irx_record_batch.h"

#include <arrow/api.h>
#include <arrow/compute/api.h>
#include <arrow/compute/initialize.h>
#include <arrow/io/api.h>
#include <arrow/ipc/api.h>
#include <arrow/result.h>
#include <arrow/status.h>
#include <arrow/type.h>

#include <cstdint>
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

uint32_t irx_record_batch_abi_version(void) {
    return IRX_RECORD_BATCH_ABI_VERSION;
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
    case IRX_COL_DATE32:       return arrow::date32();
    case IRX_COL_DATE64:       return arrow::date64();
    case IRX_COL_TIMESTAMP_S:  return arrow::timestamp(arrow::TimeUnit::SECOND);
    case IRX_COL_TIMESTAMP_MS: return arrow::timestamp(arrow::TimeUnit::MILLI);
    case IRX_COL_TIMESTAMP_US: return arrow::timestamp(arrow::TimeUnit::MICRO);
    case IRX_COL_TIMESTAMP_NS: return arrow::timestamp(arrow::TimeUnit::NANO);
    case IRX_COL_TIME32_S:     return arrow::time32(arrow::TimeUnit::SECOND);
    case IRX_COL_TIME32_MS:    return arrow::time32(arrow::TimeUnit::MILLI);
    case IRX_COL_TIME64_US:    return arrow::time64(arrow::TimeUnit::MICRO);
    case IRX_COL_TIME64_NS:    return arrow::time64(arrow::TimeUnit::NANO);
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
    case arrow::Type::DATE32:       return IRX_COL_DATE32;
    case arrow::Type::DATE64:       return IRX_COL_DATE64;
    case arrow::Type::TIMESTAMP: {
        const auto &tt = static_cast<const arrow::TimestampType &>(dt);
        switch (tt.unit()) {
        case arrow::TimeUnit::SECOND: return IRX_COL_TIMESTAMP_S;
        case arrow::TimeUnit::MILLI:  return IRX_COL_TIMESTAMP_MS;
        case arrow::TimeUnit::MICRO:  return IRX_COL_TIMESTAMP_US;
        case arrow::TimeUnit::NANO:   return IRX_COL_TIMESTAMP_NS;
        }
        return static_cast<IrxColumnType>(-1);
    }
    case arrow::Type::TIME32: {
        const auto &tt = static_cast<const arrow::Time32Type &>(dt);
        switch (tt.unit()) {
        case arrow::TimeUnit::SECOND: return IRX_COL_TIME32_S;
        case arrow::TimeUnit::MILLI:  return IRX_COL_TIME32_MS;
        default: return static_cast<IrxColumnType>(-1);
        }
    }
    case arrow::Type::TIME64: {
        const auto &tt = static_cast<const arrow::Time64Type &>(dt);
        switch (tt.unit()) {
        case arrow::TimeUnit::MICRO: return IRX_COL_TIME64_US;
        case arrow::TimeUnit::NANO:  return IRX_COL_TIME64_NS;
        default: return static_cast<IrxColumnType>(-1);
        }
    }
    default:                   return static_cast<IrxColumnType>(-1);
    }
}

struct IrxRbType_ {
    std::shared_ptr<arrow::DataType> dt;
};

IrxRbType *irx_type_primitive(IrxColumnType type) {
    auto dt = arrow_type(type);
    if (!dt) return nullptr;
    auto *t = new IrxRbType_();
    t->dt = std::move(dt);
    return t;
}

IrxRbType *irx_type_list(const IrxRbType *element) {
    if (!element || !element->dt) return nullptr;
    auto *t = new IrxRbType_();
    t->dt = arrow::list(element->dt);
    return t;
}

IrxRbType *irx_type_struct(const char *const *names,
                           const IrxRbType *const *fields, int n) {
    if (n < 0) return nullptr;
    if (n > 0 && (!names || !fields)) return nullptr;
    std::vector<std::shared_ptr<arrow::Field>> arrow_fields;
    arrow_fields.reserve(n);
    for (int i = 0; i < n; ++i) {
        if (!names[i] || !fields[i] || !fields[i]->dt) return nullptr;
        arrow_fields.push_back(arrow::field(names[i], fields[i]->dt));
    }
    auto *t = new IrxRbType_();
    t->dt = arrow::struct_(arrow_fields);
    return t;
}

void irx_type_release(IrxRbType *type) {
    delete type;
}

/* Per-column type descriptor. Leaf columns carry just `type`; a list column
 * carries one child (the element) and a struct column carries one child per
 * field (each with its `name`). The tree keeps nesting composable, so a
 * list-of-struct or struct-of-list slots in without a second representation. */
struct ColDesc {
    IrxColumnType            type{static_cast<IrxColumnType>(-1)};
    std::string              name;
    std::vector<ColDesc>     children;
};

/* Recursively describe one Arrow type. Returns false for an unsupported type,
 * leaving `out` partially filled (the caller discards it on failure). */
static bool build_desc(const arrow::DataType &dt, ColDesc &out) {
    if (dt.id() == arrow::Type::LIST) {
        out.type = IRX_COL_LIST;
        const auto &lt = static_cast<const arrow::ListType &>(dt);
        out.children.emplace_back();
        return build_desc(*lt.value_type(), out.children.back());
    }
    if (dt.id() == arrow::Type::STRUCT) {
        out.type = IRX_COL_STRUCT;
        const auto &st = static_cast<const arrow::StructType &>(dt);
        for (int i = 0; i < st.num_fields(); ++i) {
            out.children.emplace_back();
            out.children.back().name = st.field(i)->name();
            if (!build_desc(*st.field(i)->type(), out.children.back()))
                return false;
        }
        return true;
    }
    auto ct = col_type_from_arrow(dt);
    if (static_cast<int>(ct) < 0) return false;
    out.type = ct;
    return true;
}

/* Append the descriptor for one top-level field to the parallel (col_types,
 * col_descs) vectors. Returns false (leaving both untouched) for an
 * unsupported type. */
static bool classify_field(const arrow::DataType &dt,
                            std::vector<IrxColumnType> &types,
                            std::vector<ColDesc> &descs) {
    ColDesc d;
    if (!build_desc(dt, d)) return false;
    types.push_back(d.type);
    descs.push_back(std::move(d));
    return true;
}

struct IrxRbSchema_ {
    std::shared_ptr<arrow::Schema>             schema;
    std::vector<IrxColumnType>                 col_types;
    /* Full type descriptor per column, parallel to col_types. */
    std::vector<ColDesc>                       col_descs;
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
    /* Full type descriptor per column, parallel to col_types. */
    std::vector<ColDesc>                       col_descs;
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
    s->col_descs.push_back(ColDesc{type, {}, {}});
    return IRX_OK;
}

int irx_rb_schema_add_field2(IrxRbSchema     *s,
                              const char      *name,
                              const IrxRbType *type,
                              int              nullable) {
    GUARD(s); GUARD(name); GUARD(type);
    if (!type->dt)
        return set_err("null type descriptor", IRX_ERR_TYPE);
    if (!classify_field(*type->dt, s->col_types, s->col_descs))
        return set_err("unsupported field type for record batch", IRX_ERR_TYPE);

    auto field = arrow::field(name, type->dt, nullable != 0);
    auto new_schema = s->schema->AddField(s->schema->num_fields(), field);
    if (!new_schema.ok()) {
        s->col_types.pop_back();
        s->col_descs.pop_back();
        return set_err(new_schema.status());
    }
    s->schema = *new_schema;
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
    case IRX_COL_DATE32:       b = std::make_unique<arrow::Date32Builder>(pool); break;
    case IRX_COL_DATE64:       b = std::make_unique<arrow::Date64Builder>(pool); break;
    case IRX_COL_TIMESTAMP_S:
    case IRX_COL_TIMESTAMP_MS:
    case IRX_COL_TIMESTAMP_US:
    case IRX_COL_TIMESTAMP_NS:
        b = std::make_unique<arrow::TimestampBuilder>(arrow_type(t), pool);
        break;
    case IRX_COL_TIME32_S:
    case IRX_COL_TIME32_MS:
        b = std::make_unique<arrow::Time32Builder>(arrow_type(t), pool);
        break;
    case IRX_COL_TIME64_US:
    case IRX_COL_TIME64_NS:
        b = std::make_unique<arrow::Time64Builder>(arrow_type(t), pool);
        break;
    }
    return b;
}

int irx_rb_builder_create(const IrxRbSchema *schema, IrxRbBuilder **out) {
    GUARD(schema); GUARD(out);
    auto *b = new IrxRbBuilder_();
    b->schema_ref = schema;
    auto *pool = arrow::default_memory_pool();
    for (int i = 0; i < (int)schema->col_types.size(); ++i) {
        std::unique_ptr<arrow::ArrayBuilder> bldr;
        if (schema->col_types[i] == IRX_COL_LIST ||
            schema->col_types[i] == IRX_COL_STRUCT) {
            /* Nested types are built straight from the Arrow field type so the
             * child builders are wired up for us. */
            auto st = arrow::MakeBuilder(pool, schema->schema->field(i)->type(),
                                         &bldr);
            if (!st.ok()) {
                delete b;
                return set_err(st);
            }
        } else {
            bldr = make_builder(schema->col_types[i], pool);
        }
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
int irx_rb_builder_append_date(IrxRbBuilder *b, int col, int64_t v) {
    GUARD(b);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    arrow::Status st;
    switch (b->schema_ref->col_types[col])
    {
    case IRX_COL_DATE32:
        if (v < INT32_MIN || v > INT32_MAX)
            return set_err("value out of int32 range", IRX_ERR_OOB);
        st = static_cast<arrow::Date32Builder *>(
                 b->builders[col].get())
                 ->Append(static_cast<int32_t>(v));
        break;
    case IRX_COL_DATE64:
        st = static_cast<arrow::Date64Builder *>(
                 b->builders[col].get())
                 ->Append(v);
        break;
    default:
        return set_err("type mismatch on append", IRX_ERR_TYPE);
    }
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}

int irx_rb_builder_append_timestamp(IrxRbBuilder *b, int col, int64_t v) {
    GUARD(b);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    switch (b->schema_ref->col_types[col])
    {
    case IRX_COL_TIMESTAMP_S:
    case IRX_COL_TIMESTAMP_MS:
    case IRX_COL_TIMESTAMP_US:
    case IRX_COL_TIMESTAMP_NS:
        break;
    default:
        return set_err("type mismatch on append", IRX_ERR_TYPE);
    }
    auto st = static_cast<arrow::TimestampBuilder *>(
                  b->builders[col].get())
                  ->Append(v);
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}

int irx_rb_builder_append_time(IrxRbBuilder *b, int col, int64_t v) {
    GUARD(b);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    arrow::Status st;
    switch (b->schema_ref->col_types[col])
    {
    case IRX_COL_TIME32_S:
    case IRX_COL_TIME32_MS:
        if (v < INT32_MIN || v > INT32_MAX)
            return set_err("value out of int32 range", IRX_ERR_OOB);
        st = static_cast<arrow::Time32Builder *>(
                 b->builders[col].get())
                 ->Append(static_cast<int32_t>(v));
        break;
    case IRX_COL_TIME64_US:
    case IRX_COL_TIME64_NS:
        st = static_cast<arrow::Time64Builder *>(
                 b->builders[col].get())
                 ->Append(v);
        break;
    default:
        return set_err("type mismatch on append", IRX_ERR_TYPE);
    }
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}

/* Append `n` contiguous elements of CType from `data` to a typed value builder. */
template <typename Builder, typename CType>
static arrow::Status append_values_as(arrow::ArrayBuilder *vb,
                                      const void *data, int64_t n) {
    return static_cast<Builder *>(vb)->AppendValues(
        static_cast<const CType *>(data), n);
}

int irx_rb_builder_append_list(IrxRbBuilder *b, int col,
                               const void *data, int64_t n) {
    GUARD(b);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->schema_ref->col_types[col] != IRX_COL_LIST)
        return set_err("type mismatch on append", IRX_ERR_TYPE);
    if (n < 0)
        return set_err("negative list length", IRX_ERR_OOB);
    if (n > 0) GUARD(data);

    auto *lb = static_cast<arrow::ListBuilder *>(b->builders[col].get());
    /* Open a new (non-null) list slot; elements follow in the value builder. */
    auto st = lb->Append();
    if (!st.ok()) return set_err(st);

    arrow::ArrayBuilder *vb = lb->value_builder();
    switch (b->schema_ref->col_descs[col].children[0].type) {
    case IRX_COL_INT8:    st = append_values_as<arrow::Int8Builder,   int8_t>(vb, data, n);   break;
    case IRX_COL_INT16:   st = append_values_as<arrow::Int16Builder,  int16_t>(vb, data, n);  break;
    case IRX_COL_INT32:   st = append_values_as<arrow::Int32Builder,  int32_t>(vb, data, n);  break;
    case IRX_COL_INT64:   st = append_values_as<arrow::Int64Builder,  int64_t>(vb, data, n);  break;
    case IRX_COL_UINT8:   st = append_values_as<arrow::UInt8Builder,  uint8_t>(vb, data, n);  break;
    case IRX_COL_UINT16:  st = append_values_as<arrow::UInt16Builder, uint16_t>(vb, data, n); break;
    case IRX_COL_UINT32:  st = append_values_as<arrow::UInt32Builder, uint32_t>(vb, data, n); break;
    case IRX_COL_UINT64:  st = append_values_as<arrow::UInt64Builder, uint64_t>(vb, data, n); break;
    case IRX_COL_FLOAT32: st = append_values_as<arrow::FloatBuilder,  float>(vb, data, n);    break;
    case IRX_COL_FLOAT64: st = append_values_as<arrow::DoubleBuilder, double>(vb, data, n);   break;
    case IRX_COL_DATE32:  st = append_values_as<arrow::Date32Builder, int32_t>(vb, data, n);  break;
    case IRX_COL_DATE64:  st = append_values_as<arrow::Date64Builder, int64_t>(vb, data, n);  break;
    case IRX_COL_TIMESTAMP_S:
    case IRX_COL_TIMESTAMP_MS:
    case IRX_COL_TIMESTAMP_US:
    case IRX_COL_TIMESTAMP_NS:
        st = append_values_as<arrow::TimestampBuilder, int64_t>(vb, data, n); break;
    case IRX_COL_TIME32_S:
    case IRX_COL_TIME32_MS:
        st = append_values_as<arrow::Time32Builder, int32_t>(vb, data, n); break;
    case IRX_COL_TIME64_US:
    case IRX_COL_TIME64_NS:
        st = append_values_as<arrow::Time64Builder, int64_t>(vb, data, n); break;
    default:
        return set_err("unsupported list element type", IRX_ERR_TYPE);
    }
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}

/* Range-checked narrowing append onto a fixed-width struct field builder. The
 * int64 carrier holds every supported field value except uint64, which cannot
 * round-trip and is rejected. Mirrors the int32 guards on the scalar date/time
 * appenders so a too-wide value is refused rather than silently truncated. */
static int append_struct_field_int(arrow::ArrayBuilder *fb, IrxColumnType t,
                                    int64_t v) {
    arrow::Status st;
    switch (t) {
    case IRX_COL_INT8:
        if (v < INT8_MIN || v > INT8_MAX)
            return set_err("value out of int8 range", IRX_ERR_OOB);
        st = static_cast<arrow::Int8Builder *>(fb)->Append(static_cast<int8_t>(v));
        break;
    case IRX_COL_INT16:
        if (v < INT16_MIN || v > INT16_MAX)
            return set_err("value out of int16 range", IRX_ERR_OOB);
        st = static_cast<arrow::Int16Builder *>(fb)->Append(static_cast<int16_t>(v));
        break;
    case IRX_COL_INT32:
        if (v < INT32_MIN || v > INT32_MAX)
            return set_err("value out of int32 range", IRX_ERR_OOB);
        st = static_cast<arrow::Int32Builder *>(fb)->Append(static_cast<int32_t>(v));
        break;
    case IRX_COL_INT64:
        st = static_cast<arrow::Int64Builder *>(fb)->Append(v);
        break;
    case IRX_COL_UINT8:
        if (v < 0 || v > UINT8_MAX)
            return set_err("value out of uint8 range", IRX_ERR_OOB);
        st = static_cast<arrow::UInt8Builder *>(fb)->Append(static_cast<uint8_t>(v));
        break;
    case IRX_COL_UINT16:
        if (v < 0 || v > UINT16_MAX)
            return set_err("value out of uint16 range", IRX_ERR_OOB);
        st = static_cast<arrow::UInt16Builder *>(fb)->Append(static_cast<uint16_t>(v));
        break;
    case IRX_COL_UINT32:
        if (v < 0 || v > UINT32_MAX)
            return set_err("value out of uint32 range", IRX_ERR_OOB);
        st = static_cast<arrow::UInt32Builder *>(fb)->Append(static_cast<uint32_t>(v));
        break;
    case IRX_COL_BOOL:
        st = static_cast<arrow::BooleanBuilder *>(fb)->Append(v != 0);
        break;
    case IRX_COL_DATE32:
        if (v < INT32_MIN || v > INT32_MAX)
            return set_err("value out of int32 range", IRX_ERR_OOB);
        st = static_cast<arrow::Date32Builder *>(fb)->Append(static_cast<int32_t>(v));
        break;
    case IRX_COL_DATE64:
        st = static_cast<arrow::Date64Builder *>(fb)->Append(v);
        break;
    case IRX_COL_TIMESTAMP_S:
    case IRX_COL_TIMESTAMP_MS:
    case IRX_COL_TIMESTAMP_US:
    case IRX_COL_TIMESTAMP_NS:
        st = static_cast<arrow::TimestampBuilder *>(fb)->Append(v);
        break;
    case IRX_COL_TIME32_S:
    case IRX_COL_TIME32_MS:
        if (v < INT32_MIN || v > INT32_MAX)
            return set_err("value out of int32 range", IRX_ERR_OOB);
        st = static_cast<arrow::Time32Builder *>(fb)->Append(static_cast<int32_t>(v));
        break;
    case IRX_COL_TIME64_US:
    case IRX_COL_TIME64_NS:
        st = static_cast<arrow::Time64Builder *>(fb)->Append(v);
        break;
    default:
        return set_err("unsupported struct field type for integer append",
                       IRX_ERR_TYPE);
    }
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}

/* Resolve a struct column's child builder and declared field type, validating
 * the column is a struct and the field index is in range. */
static int resolve_struct_field(IrxRbBuilder *b, int col, int field,
                                arrow::ArrayBuilder **fb, IrxColumnType *ftype) {
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->schema_ref->col_types[col] != IRX_COL_STRUCT)
        return set_err("column is not a struct column", IRX_ERR_TYPE);
    const auto &children = b->schema_ref->col_descs[col].children;
    if (field < 0 || field >= (int)children.size())
        return set_err("struct field index out of bounds", IRX_ERR_OOB);
    *fb = static_cast<arrow::StructBuilder *>(b->builders[col].get())
              ->field_builder(field);
    *ftype = children[field].type;
    return IRX_OK;
}

int irx_rb_builder_struct_append(IrxRbBuilder *b, int col) {
    GUARD(b);
    if (col < 0 || col >= (int)b->builders.size())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->schema_ref->col_types[col] != IRX_COL_STRUCT)
        return set_err("column is not a struct column", IRX_ERR_TYPE);
    auto st = static_cast<arrow::StructBuilder *>(b->builders[col].get())->Append();
    if (!st.ok()) return set_err(st);
    return IRX_OK;
}

int irx_rb_builder_struct_field_int(IrxRbBuilder *b, int col, int field,
                                    int64_t v) {
    GUARD(b);
    arrow::ArrayBuilder *fb;
    IrxColumnType ft;
    int rc = resolve_struct_field(b, col, field, &fb, &ft);
    if (rc != IRX_OK) return rc;
    return append_struct_field_int(fb, ft, v);
}

int irx_rb_builder_struct_field_float(IrxRbBuilder *b, int col, int field,
                                      double v) {
    GUARD(b);
    arrow::ArrayBuilder *fb;
    IrxColumnType ft;
    int rc = resolve_struct_field(b, col, field, &fb, &ft);
    if (rc != IRX_OK) return rc;
    arrow::Status st;
    switch (ft) {
    case IRX_COL_FLOAT32:
        st = static_cast<arrow::FloatBuilder *>(fb)->Append(static_cast<float>(v));
        break;
    case IRX_COL_FLOAT64:
        st = static_cast<arrow::DoubleBuilder *>(fb)->Append(v);
        break;
    default:
        return set_err("struct field is not a float column", IRX_ERR_TYPE);
    }
    if (!st.ok()) return set_err(st);
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
    batch->batch          = std::move(rb);
    batch->col_types      = b->schema_ref->col_types;
    batch->col_descs      = b->schema_ref->col_descs;
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

int irx_rb_batch_get_date(const IrxRbBatch *b, int col, int64_t row, int64_t *out) {
    GUARD(b); GUARD(out);
    if (check_bounds(b, col, row)) return IRX_ERR_OOB;
    switch (b->col_types[col]) {
    case IRX_COL_DATE32:
        *out = static_cast<const arrow::Date32Array *>(
                   b->batch->column(col).get())->Value(row);
        return IRX_OK;
    case IRX_COL_DATE64:
        *out = static_cast<const arrow::Date64Array *>(
                   b->batch->column(col).get())->Value(row);
        return IRX_OK;
    default:
        return set_err("type mismatch on get", IRX_ERR_TYPE);
    }
}

int irx_rb_batch_get_timestamp(const IrxRbBatch *b, int col, int64_t row, int64_t *out) {
    GUARD(b); GUARD(out);
    if (check_bounds(b, col, row)) return IRX_ERR_OOB;
    switch (b->col_types[col]) {
    case IRX_COL_TIMESTAMP_S:
    case IRX_COL_TIMESTAMP_MS:
    case IRX_COL_TIMESTAMP_US:
    case IRX_COL_TIMESTAMP_NS:
        *out = static_cast<const arrow::TimestampArray *>(
                   b->batch->column(col).get())->Value(row);
        return IRX_OK;
    default:
        return set_err("type mismatch on get", IRX_ERR_TYPE);
    }
}

int irx_rb_batch_get_time(const IrxRbBatch *b, int col, int64_t row, int64_t *out) {
    GUARD(b); GUARD(out);
    if (check_bounds(b, col, row)) return IRX_ERR_OOB;
    switch (b->col_types[col]) {
    case IRX_COL_TIME32_S:
    case IRX_COL_TIME32_MS:
        *out = static_cast<const arrow::Time32Array *>(
                   b->batch->column(col).get())->Value(row);
        return IRX_OK;
    case IRX_COL_TIME64_US:
    case IRX_COL_TIME64_NS:
        *out = static_cast<const arrow::Time64Array *>(
                   b->batch->column(col).get())->Value(row);
        return IRX_OK;
    default:
        return set_err("type mismatch on get", IRX_ERR_TYPE);
    }
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

int irx_rb_batch_list_elem_type(const IrxRbBatch *b, int col,
                                IrxColumnType *out) {
    GUARD(b); GUARD(out);
    if (col < 0 || col >= b->batch->num_columns())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->col_types[col] != IRX_COL_LIST)
        return set_err("column is not a list column", IRX_ERR_TYPE);
    *out = b->col_descs[col].children[0].type;
    return IRX_OK;
}

int irx_rb_batch_list_offsets(const IrxRbBatch *b, int col,
                              const int32_t **offs, int64_t *n) {
    GUARD(b); GUARD(offs); GUARD(n);
    if (col < 0 || col >= b->batch->num_columns())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->col_types[col] != IRX_COL_LIST)
        return set_err("column is not a list column", IRX_ERR_TYPE);
    auto *arr = static_cast<const arrow::ListArray *>(b->batch->column(col).get());
    *offs = arr->raw_value_offsets();
    *n = arr->length() + 1;
    return IRX_OK;
}

int irx_rb_batch_list_child_buffer(const IrxRbBatch *b, int col,
                                   const void **buf, int64_t *len) {
    GUARD(b); GUARD(buf); GUARD(len);
    if (col < 0 || col >= b->batch->num_columns())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->col_types[col] != IRX_COL_LIST)
        return set_err("column is not a list column", IRX_ERR_TYPE);
    auto *arr = static_cast<const arrow::ListArray *>(b->batch->column(col).get());
    auto values = arr->values();
    auto &data = *values->data();
    if (data.buffers.size() < 2 || !data.buffers[1])
        return set_err("list child has no value buffer", IRX_ERR_TYPE);
    const auto *fw = dynamic_cast<const arrow::FixedWidthType *>(values->type().get());
    if (fw == nullptr)
        return set_err("list child is not a fixed-width type", IRX_ERR_TYPE);
    const int64_t byte_width = fw->bit_width() / 8;
    const uint8_t *base = data.buffers[1]->data();
    *buf = base + data.offset * byte_width;
    *len = values->length();
    return IRX_OK;
}

int irx_rb_batch_struct_num_fields(const IrxRbBatch *b, int col, int *out) {
    GUARD(b); GUARD(out);
    if (col < 0 || col >= b->batch->num_columns())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->col_types[col] != IRX_COL_STRUCT)
        return set_err("column is not a struct column", IRX_ERR_TYPE);
    *out = static_cast<int>(b->col_descs[col].children.size());
    return IRX_OK;
}

int irx_rb_batch_struct_field_name(const IrxRbBatch *b, int col, int field,
                                   const char **out) {
    GUARD(b); GUARD(out);
    if (col < 0 || col >= b->batch->num_columns())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->col_types[col] != IRX_COL_STRUCT)
        return set_err("column is not a struct column", IRX_ERR_TYPE);
    const auto &children = b->col_descs[col].children;
    if (field < 0 || field >= (int)children.size())
        return set_err("struct field index out of bounds", IRX_ERR_OOB);
    *out = children[field].name.c_str();
    return IRX_OK;
}

int irx_rb_batch_struct_field_type(const IrxRbBatch *b, int col, int field,
                                   IrxColumnType *out) {
    GUARD(b); GUARD(out);
    if (col < 0 || col >= b->batch->num_columns())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->col_types[col] != IRX_COL_STRUCT)
        return set_err("column is not a struct column", IRX_ERR_TYPE);
    const auto &children = b->col_descs[col].children;
    if (field < 0 || field >= (int)children.size())
        return set_err("struct field index out of bounds", IRX_ERR_OOB);
    *out = children[field].type;
    return IRX_OK;
}

int irx_rb_batch_struct_field_buffer(const IrxRbBatch *b, int col, int field,
                                     const void **buf, int64_t *len) {
    GUARD(b); GUARD(buf); GUARD(len);
    if (col < 0 || col >= b->batch->num_columns())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->col_types[col] != IRX_COL_STRUCT)
        return set_err("column is not a struct column", IRX_ERR_TYPE);
    auto *arr = static_cast<const arrow::StructArray *>(b->batch->column(col).get());
    if (field < 0 || field >= arr->num_fields())
        return set_err("struct field index out of bounds", IRX_ERR_OOB);
    auto child = arr->field(field);
    auto &data = *child->data();
    if (data.buffers.size() < 2 || !data.buffers[1])
        return set_err("struct field has no value buffer", IRX_ERR_TYPE);
    const auto *fw = dynamic_cast<const arrow::FixedWidthType *>(child->type().get());
    if (fw == nullptr)
        return set_err("struct field is not a fixed-width type", IRX_ERR_TYPE);
    const int64_t byte_width = fw->bit_width() / 8;
    const uint8_t *base = data.buffers[1]->data();
    *buf = base + data.offset * byte_width;
    *len = child->length();
    return IRX_OK;
}

void irx_rb_batch_release(IrxRbBatch *batch) {
    delete batch;
}

/* Populate arrow::compute's kernel registry once. Since the compute split the
 * registry lives in a separate library that must be initialized explicitly
 * before any kernel is looked up; the function-local static runs it once. */
static arrow::Status ensure_compute_init() {
    static arrow::Status init = arrow::compute::Initialize();
    return init;
}

/* Wrap an Arrow RecordBatch produced by a compute kernel in a batch handle,
 * classifying each column so the existing readers work on the result. */
static int make_batch_handle(std::shared_ptr<arrow::RecordBatch> rb,
                             IrxRbBatch **out) {
    auto *batch = new IrxRbBatch_();
    batch->batch = std::move(rb);
    for (int i = 0; i < batch->batch->num_columns(); ++i) {
        if (!classify_field(*batch->batch->schema()->field(i)->type(),
                            batch->col_types, batch->col_descs)) {
            delete batch;
            return set_err("unsupported column type in compute result",
                           IRX_ERR_TYPE);
        }
    }
    *out = batch;
    return IRX_OK;
}

/* Read a numeric Arrow scalar into the (int, double) out-params, reporting the
 * source type so the caller knows which one was written. */
static int scalar_to_out(const std::shared_ptr<arrow::Scalar> &s,
                         IrxColumnType *out_type, int64_t *i_out,
                         double *f_out) {
    if (!s || !s->is_valid)
        return set_err("aggregation over no valid values", IRX_ERR_ARROW);
    switch (s->type->id()) {
    case arrow::Type::INT8:
        *i_out = static_cast<const arrow::Int8Scalar &>(*s).value;
        *out_type = IRX_COL_INT8; return IRX_OK;
    case arrow::Type::INT16:
        *i_out = static_cast<const arrow::Int16Scalar &>(*s).value;
        *out_type = IRX_COL_INT16; return IRX_OK;
    case arrow::Type::INT32:
        *i_out = static_cast<const arrow::Int32Scalar &>(*s).value;
        *out_type = IRX_COL_INT32; return IRX_OK;
    case arrow::Type::INT64:
        *i_out = static_cast<const arrow::Int64Scalar &>(*s).value;
        *out_type = IRX_COL_INT64; return IRX_OK;
    case arrow::Type::UINT8:
        *i_out = static_cast<const arrow::UInt8Scalar &>(*s).value;
        *out_type = IRX_COL_UINT8; return IRX_OK;
    case arrow::Type::UINT16:
        *i_out = static_cast<const arrow::UInt16Scalar &>(*s).value;
        *out_type = IRX_COL_UINT16; return IRX_OK;
    case arrow::Type::UINT32:
        *i_out = static_cast<const arrow::UInt32Scalar &>(*s).value;
        *out_type = IRX_COL_UINT32; return IRX_OK;
    case arrow::Type::UINT64:
        *i_out = static_cast<int64_t>(
            static_cast<const arrow::UInt64Scalar &>(*s).value);
        *out_type = IRX_COL_UINT64; return IRX_OK;
    case arrow::Type::FLOAT:
        *f_out = static_cast<const arrow::FloatScalar &>(*s).value;
        *out_type = IRX_COL_FLOAT32; return IRX_OK;
    case arrow::Type::DOUBLE:
        *f_out = static_cast<const arrow::DoubleScalar &>(*s).value;
        *out_type = IRX_COL_FLOAT64; return IRX_OK;
    default:
        return set_err("unsupported aggregation result type", IRX_ERR_TYPE);
    }
}

int irx_compute_aggregate(const IrxRbBatch *b, int col, int op,
                          IrxColumnType *out_type, int64_t *i_out,
                          double *f_out) {
    GUARD(b); GUARD(out_type); GUARD(i_out); GUARD(f_out);
    if (auto st = ensure_compute_init(); !st.ok()) return set_err(st);
    if (col < 0 || col >= b->batch->num_columns())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    arrow::Datum in(b->batch->column(col));
    arrow::Result<arrow::Datum> res;
    switch (op) {
    case IRX_AGG_SUM:   res = arrow::compute::Sum(in);   break;
    case IRX_AGG_MEAN:  res = arrow::compute::Mean(in);  break;
    case IRX_AGG_COUNT: res = arrow::compute::Count(in); break;
    case IRX_AGG_MIN:
    case IRX_AGG_MAX: {
        auto mm = arrow::compute::MinMax(in);
        if (!mm.ok()) return set_err(mm.status());
        const auto &sc =
            static_cast<const arrow::StructScalar &>(*mm->scalar());
        return scalar_to_out(sc.value[op == IRX_AGG_MIN ? 0 : 1], out_type,
                             i_out, f_out);
    }
    default:
        return set_err("unknown aggregation op", IRX_ERR_TYPE);
    }
    if (!res.ok()) return set_err(res.status());
    return scalar_to_out(res->scalar(), out_type, i_out, f_out);
}

int irx_compute_binary(const IrxRbBatch *b, int col_a, int col_b, int op,
                       IrxRbBatch **out) {
    GUARD(b); GUARD(out);
    if (auto st = ensure_compute_init(); !st.ok()) return set_err(st);
    const int ncol = b->batch->num_columns();
    if (col_a < 0 || col_a >= ncol || col_b < 0 || col_b >= ncol)
        return set_err("column index out of bounds", IRX_ERR_OOB);
    const char *fn = nullptr;
    switch (op) {
    case IRX_BINOP_ADD: fn = "add";      break;
    case IRX_BINOP_SUB: fn = "subtract"; break;
    case IRX_BINOP_MUL: fn = "multiply"; break;
    case IRX_BINOP_DIV: fn = "divide";   break;
    default:
        return set_err("unknown binary op", IRX_ERR_TYPE);
    }
    arrow::Datum lhs(b->batch->column(col_a));
    arrow::Datum rhs(b->batch->column(col_b));
    auto res = arrow::compute::CallFunction(fn, {lhs, rhs});
    if (!res.ok()) return set_err(res.status());
    auto arr = res->make_array();
    auto schema = arrow::schema({arrow::field("result", arr->type())});
    auto rb = arrow::RecordBatch::Make(schema, arr->length(), {arr});
    return make_batch_handle(std::move(rb), out);
}

int irx_compute_filter(const IrxRbBatch *b, int mask_col, IrxRbBatch **out) {
    GUARD(b); GUARD(out);
    if (auto st = ensure_compute_init(); !st.ok()) return set_err(st);
    if (mask_col < 0 || mask_col >= b->batch->num_columns())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    if (b->col_types[mask_col] != IRX_COL_BOOL)
        return set_err("mask column is not a boolean column", IRX_ERR_TYPE);
    arrow::Datum batch_datum(b->batch);
    arrow::Datum mask(b->batch->column(mask_col));
    auto res = arrow::compute::CallFunction("filter", {batch_datum, mask});
    if (!res.ok()) return set_err(res.status());
    return make_batch_handle(res->record_batch(), out);
}

int irx_compute_sort_indices(const IrxRbBatch *b, int col, int ascending,
                             int64_t *out, int64_t out_len) {
    GUARD(b); GUARD(out);
    if (auto st = ensure_compute_init(); !st.ok()) return set_err(st);
    if (col < 0 || col >= b->batch->num_columns())
        return set_err("column index out of bounds", IRX_ERR_OOB);
    const int64_t nrows = b->batch->num_rows();
    if (out_len < nrows)
        return set_err("output buffer too small for sort indices", IRX_ERR_OOB);
    arrow::compute::ArraySortOptions options(
        ascending ? arrow::compute::SortOrder::Ascending
                  : arrow::compute::SortOrder::Descending);
    arrow::Datum in(b->batch->column(col));
    auto res = arrow::compute::CallFunction("array_sort_indices", {in},
                                            &options);
    if (!res.ok()) return set_err(res.status());
    auto idx = std::static_pointer_cast<arrow::UInt64Array>(res->make_array());
    for (int64_t i = 0; i < nrows; ++i)
        out[i] = static_cast<int64_t>(idx->Value(i));
    return IRX_OK;
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
        if (!classify_field(*field.type(),
                            r->schema_handle.col_types,
                            r->schema_handle.col_descs)) {
            delete r;
            return set_err(
                "stream column '" + field.name() + "' has type '" +
                    field.type()->ToString() +
                    "' which is not supported by this reader",
                IRX_ERR_TYPE);
        }
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
    b->batch          = std::move(rb);
    b->col_types      = r->schema_handle.col_types;
    b->col_descs      = r->schema_handle.col_descs;
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
