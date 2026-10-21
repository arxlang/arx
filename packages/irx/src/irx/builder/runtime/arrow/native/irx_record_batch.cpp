// Copyright IRx contributors.

#include "irx_record_batch.h"
#include "irx_arrow_runtime.h"

#include <arrow/api.h>
#include <arrow/c/bridge.h>
#include <arrow/csv/api.h>
#include "irx_arrow_transport.h"
#include <arrow/io/api.h>
#include <arrow/ipc/api.h>
#include <arrow/result.h>
#include <arrow/status.h>
#include <arrow/type.h>
#include <arrow/util/utf8.h>

#include <cstdint>
#include <cstring>
#include <memory>
#include <string>
#include <string_view>
#include <unordered_set>
#include <vector>

static thread_local std::string tl_errmsg;

static int set_err(const std::string &msg, int code = IRX_ERR_ARROW) {
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
    IrxRbSchema_ schema_snapshot;
    const IrxRbSchema_ *schema_ref;
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
    std::shared_ptr<arrow::Schema> schema;
    /* For buffer-based writers. */
    std::shared_ptr<arrow::io::BufferOutputStream> buf_sink;
    bool                                       closed{false};
    bool                                       csv{false};
    /* Cached serialised bytes (valid after close for buffer writers). */
    std::shared_ptr<arrow::Buffer>             finished_buf;
};

struct IrxRbStreamReader_ {
    std::shared_ptr<arrow::RecordBatchReader> reader;
    std::shared_ptr<arrow::io::InputStream> source;
    bool eof{false};
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
    b->schema_snapshot = *schema;
    b->schema_ref = &b->schema_snapshot;
    auto *pool = arrow::default_memory_pool();
    for (int i = 0; i < (int)schema->col_types.size(); ++i) {
        std::unique_ptr<arrow::ArrayBuilder> bldr;
        if (schema->col_types[i] == IRX_COL_LIST ||
            schema->col_types[i] == IRX_COL_STRUCT ||
            schema->schema->field(i)->type()->id() == arrow::Type::TIMESTAMP) {
            /* Preserve nested fields and timestamp timezone parameters. */
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
    if (!b->schema_ref->schema->field(col)->nullable())
        return set_err("null in a non-nullable field", IRX_ERR_TYPE);
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
    w->schema = schema->schema;
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
    w->schema = schema->schema;
    *out = w;
    return IRX_OK;
}

int irx_rb_stream_writer_write_batch(IrxRbStreamWriter *w,
                                      const IrxRbBatch  *batch) {
    GUARD(w); GUARD(batch);
    if (w->closed) return set_err("writer already closed", IRX_ERR_IO);
    if (!w->schema->Equals(*batch->batch->schema(), true))
        return set_err("batch schema mismatch (including metadata/nullability)", IRX_ERR_TYPE);
    auto validation = batch->batch->ValidateFull();
    if (!validation.ok()) return set_err(validation);
    if (w->csv) {
        for (int i = 0; i < batch->batch->num_columns(); ++i) {
            if (!w->schema->field(i)->nullable() && batch->batch->column(i)->null_count())
                return set_err("CSV column '" + w->schema->field(i)->name() +
                               "' contains nulls but is not nullable", IRX_ERR_TYPE);
        }
    }
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

// Arrow permits a physical EOF in place of an IPC end marker. Interop readers
// require the marker so an interrupted transfer cannot look like success.
class CheckedIpcInput final : public arrow::io::InputStream {
 public:
    explicit CheckedIpcInput(std::shared_ptr<arrow::io::InputStream> source)
        : source_(std::move(source)) {}
    arrow::Status Close() override { return source_->Close(); }
    bool closed() const override { return source_->closed(); }
    arrow::Result<int64_t> Tell() const override { return source_->Tell(); }
    arrow::Result<int64_t> Read(int64_t n, void *out) override {
        ARROW_ASSIGN_OR_RAISE(auto count, source_->Read(n, out));
        if (n > 0 && count == 0)
            return arrow::Status::IOError("truncated IPC stream: missing end marker");
        return count;
    }
    arrow::Result<std::shared_ptr<arrow::Buffer>> Read(int64_t n) override {
        ARROW_ASSIGN_OR_RAISE(auto buffer, source_->Read(n));
        if (n > 0 && buffer->size() == 0)
            return arrow::Status::IOError("truncated IPC stream: missing end marker");
        return buffer;
    }
 private:
    std::shared_ptr<arrow::io::InputStream> source_;
};

static int populate_schema(std::shared_ptr<arrow::Schema> schema,
                           IrxRbSchema *out) {
    IrxRbSchema result;
    result.schema = schema;
    for (const auto &field : schema->fields()) {
        if (!classify_field(*field->type(), result.col_types, result.col_descs))
            return set_err("unsupported Arrow field '" + field->name() +
                           "': " + field->type()->ToString(), IRX_ERR_TYPE);
    }
    *out = std::move(result);
    return IRX_OK;
}

static int open_stream_reader(std::shared_ptr<arrow::io::InputStream> stream,
                               IrxRbStreamReader **out) {
    *out = nullptr;
    auto source = std::make_shared<CheckedIpcInput>(std::move(stream));
    auto result = arrow::ipc::RecordBatchStreamReader::Open(source);
    if (!result.ok()) return set_err(result.status());
    auto r = std::make_unique<IrxRbStreamReader>();
    r->source = source;
    r->reader = *result;
    int status = populate_schema(r->reader->schema(), &r->schema_handle);
    if (status != IRX_OK) return status;
    r->schema_handle.reader_owned = true;
    *out = r.release();
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
    *batch = nullptr;
    if (r->eof) return IRX_EOF;
    std::shared_ptr<arrow::RecordBatch> rb;
    auto st = r->reader->ReadNext(&rb);
    if (!st.ok()) return set_err(st);
    if (!rb) {
        r->eof = true;
        return IRX_EOF;
    }
    auto validation = rb->ValidateFull();
    if (!validation.ok()) return set_err(validation);
    if (!r->schema_handle.schema->Equals(*rb->schema(), true))
        return set_err("batch schema mismatch", IRX_ERR_TYPE);
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
    if (!r) return;
    if (r->reader) (void)r->reader->Close();
    if (r->source) (void)r->source->Close();
    delete r;
}

// Additive ABI v1 interoperability entry points. Outputs must be fresh/released.
int irx_rb_batch_schema(const IrxRbBatch *batch, IrxRbSchema **out) {
    GUARD(out); *out = nullptr; GUARD(batch);
    auto schema = std::make_unique<IrxRbSchema>();
    int status = populate_schema(batch->batch->schema(), schema.get());
    if (status != IRX_OK) return status;
    *out = schema.release();
    return IRX_OK;
}
int irx_rb_schema_field(const IrxRbSchema *schema, int col, const char **name,
                        int *type, int *nullable) {
    GUARD(schema); GUARD(name); GUARD(type); GUARD(nullable);
    if (col < 0 || col >= schema->schema->num_fields())
        return set_err("schema field index out of bounds", IRX_ERR_OOB);
    if (schema->schema->field(col)->name().find('\0') != std::string::npos)
        return set_err("embedded NUL in field name cannot be exposed as C text", IRX_ERR_TYPE);
    *name = schema->schema->field(col)->name().c_str();
    *type = schema->col_types[col];
    *nullable = schema->schema->field(col)->nullable();
    return IRX_OK;
}
int irx_rb_schema_equal(const IrxRbSchema *left, const IrxRbSchema *right) {
    if (!left || !right) return IRX_ERR_NULLPTR;
    return left->schema->Equals(*right->schema, true) ? 1 : 0;
}
// C schema names and timezone formats are NUL-terminated. IPC can preserve
// embedded NUL here, but a C export must reject it rather than truncate it.
static int check_c_fields(const arrow::FieldVector &fields) {
    for (const auto &field : fields) {
        if (field->name().find('\0') != std::string::npos)
            return set_err("embedded NUL in field name cannot cross C Data", IRX_ERR_TYPE);
        if (field->type()->id() == arrow::Type::TIMESTAMP) {
            const auto &type = static_cast<const arrow::TimestampType &>(*field->type());
            if (type.timezone().find('\0') != std::string::npos)
                return set_err("embedded NUL in timezone cannot cross C Data", IRX_ERR_TYPE);
        }
        int status = check_c_fields(field->type()->fields());
        if (status != IRX_OK) return status;
    }
    return IRX_OK;
}

int irx_rb_schema_export(const IrxRbSchema *schema, ArrowSchema *out) {
    GUARD(schema); GUARD(out);
    if (out->release) return set_err("output schema is not released", IRX_ERR_ARROW);
    int valid = check_c_fields(schema->schema->fields());
    if (valid != IRX_OK) return valid;
    auto status = arrow::ExportSchema(*schema->schema, out);
    return status.ok() ? IRX_OK : set_err(status);
}
int irx_rb_schema_import(ArrowSchema *schema, IrxRbSchema **out) {
    GUARD(out); *out = nullptr; GUARD(schema);
    if (!schema->release) return set_err("schema already released", IRX_ERR_ARROW);
    auto result = arrow::ImportSchema(schema);
    if (!result.ok()) return set_err(result.status());
    auto handle = std::make_unique<IrxRbSchema>();
    int status = populate_schema(*result, handle.get());
    if (status != IRX_OK) return status;
    *out = handle.release();
    return IRX_OK;
}
int irx_rb_batch_export(const IrxRbBatch *batch, ArrowArray *array,
                         ArrowSchema *schema) {
    GUARD(batch); GUARD(array); GUARD(schema);
    if (array->release || schema->release)
        return set_err("C Data outputs must be released", IRX_ERR_ARROW);
    int valid = check_c_fields(batch->batch->schema()->fields());
    if (valid != IRX_OK) return valid;
    auto status = arrow::ExportRecordBatch(*batch->batch, array, schema);
    return status.ok() ? IRX_OK : set_err(status);
}
int irx_rb_batch_import(ArrowArray *array, ArrowSchema *schema, IrxRbBatch **out) {
    GUARD(out); *out = nullptr; GUARD(array); GUARD(schema);
    if (!array->release || !schema->release)
        return set_err("C Data input already released", IRX_ERR_ARROW);
    auto result = arrow::ImportRecordBatch(array, schema);
    if (!result.ok()) return set_err(result.status());
    auto validation = (*result)->ValidateFull();
    if (!validation.ok()) return set_err(validation);
    IrxRbSchema info;
    int status = populate_schema((*result)->schema(), &info);
    if (status != IRX_OK) return status;
    auto batch = std::make_unique<IrxRbBatch>();
    batch->batch = *result;
    batch->col_types = std::move(info.col_types);
    batch->col_descs = std::move(info.col_descs);
    *out = batch.release();
    return IRX_OK;
}
int irx_rb_batch_export_stream(const IrxRbBatch *batch, ArrowArrayStream *out) {
    GUARD(batch); GUARD(out);
    if (out->release) return set_err("output stream is not released", IRX_ERR_ARROW);
    int valid = check_c_fields(batch->batch->schema()->fields());
    if (valid != IRX_OK) return valid;
    auto reader = arrow::RecordBatchReader::Make({batch->batch}, batch->batch->schema());
    if (!reader.ok()) return set_err(reader.status());
    auto status = arrow::ExportRecordBatchReader(*reader, out);
    return status.ok() ? IRX_OK : set_err(status);
}
int irx_rb_stream_reader_import(ArrowArrayStream *stream, IrxRbStreamReader **out) {
    GUARD(out); *out = nullptr; GUARD(stream);
    if (!stream->release) return set_err("stream already released", IRX_ERR_ARROW);
    auto reader = arrow::ImportRecordBatchReader(stream);
    if (!reader.ok()) return set_err(reader.status());
    auto result = std::make_unique<IrxRbStreamReader>();
    result->reader = *reader;
    int status = populate_schema(result->reader->schema(), &result->schema_handle);
    if (status != IRX_OK) return status;
    *out = result.release();
    return IRX_OK;
}
int irx_rb_stream_reader_export(IrxRbStreamReader *reader, ArrowArrayStream *out) {
    GUARD(reader); GUARD(out);
    if (!reader->reader) return set_err("reader already transferred", IRX_ERR_IO);
    if (out->release) return set_err("output stream is not released", IRX_ERR_ARROW);
    int valid = check_c_fields(reader->schema_handle.schema->fields());
    if (valid != IRX_OK) return valid;
    auto status = arrow::ExportRecordBatchReader(reader->reader, out);
    if (!status.ok()) return set_err(status);
    reader->reader.reset();
    reader->source.reset();
    reader->eof = true;
    return IRX_OK;
}
void irx_rb_c_stream_release(ArrowArrayStream *stream) {
    if (stream && stream->release) stream->release(stream);
}
void irx_rb_c_array_release(ArrowArray *array) {
    if (array && array->release) array->release(array);
}
void irx_rb_c_schema_release(ArrowSchema *schema) {
    if (schema && schema->release) schema->release(schema);
}

class IpcFileReader final : public arrow::RecordBatchReader {
 public:
    IpcFileReader(std::shared_ptr<arrow::ipc::RecordBatchFileReader> reader,
                  std::shared_ptr<arrow::io::RandomAccessFile> source)
        : reader_(std::move(reader)), source_(std::move(source)) {}
    std::shared_ptr<arrow::Schema> schema() const override { return reader_->schema(); }
    arrow::Status ReadNext(std::shared_ptr<arrow::RecordBatch> *out) override {
        if (index_ == reader_->num_record_batches()) { *out = nullptr; return arrow::Status::OK(); }
        ARROW_ASSIGN_OR_RAISE(*out, reader_->ReadRecordBatch(index_));
        ++index_;
        return arrow::Status::OK();
    }
    arrow::Status Close() override { return source_->Close(); }
 private:
    std::shared_ptr<arrow::ipc::RecordBatchFileReader> reader_;
    std::shared_ptr<arrow::io::RandomAccessFile> source_;
    int index_{0};
};
int irx_rb_file_reader_open(const char *path, IrxRbStreamReader **out) {
    GUARD(out); *out = nullptr; GUARD(path);
    auto source = arrow::io::ReadableFile::Open(path);
    if (!source.ok()) return set_err(source.status(), IRX_ERR_IO);
    auto reader = arrow::ipc::RecordBatchFileReader::Open(*source);
    if (!reader.ok()) return set_err(reader.status());
    auto r = std::make_unique<IrxRbStreamReader>();
    r->reader = std::make_shared<IpcFileReader>(*reader, *source);
    r->source = *source;
    int status = populate_schema(r->reader->schema(), &r->schema_handle);
    if (status != IRX_OK) return status;
    *out = r.release();
    return IRX_OK;
}
static int open_writer(const IrxRbSchema *schema,
                        std::shared_ptr<arrow::io::OutputStream> sink,
                        bool file_format, IrxRbStreamWriter **out) {
    auto result = file_format ? arrow::ipc::MakeFileWriter(sink, schema->schema)
                              : arrow::ipc::MakeStreamWriter(sink, schema->schema);
    if (!result.ok()) return set_err(result.status());
    auto w = std::make_unique<IrxRbStreamWriter>();
    w->sink = std::move(sink);
    w->writer = *result;
    w->schema = schema->schema;
    *out = w.release();
    return IRX_OK;
}
int irx_rb_file_writer_open(const IrxRbSchema *schema, const char *path,
                             IrxRbStreamWriter **out) {
    GUARD(out); *out = nullptr; GUARD(schema); GUARD(path);
    auto sink = arrow::io::FileOutputStream::Open(path);
    if (!sink.ok()) return set_err(sink.status(), IRX_ERR_IO);
    return open_writer(schema, *sink, true, out);
}
int irx_rb_tcp_reader_open(const char *host, int port, int timeout_ms,
                            IrxRbStreamReader **out) {
    GUARD(out); *out = nullptr;
    auto source = irx::tcp_input(host, port, timeout_ms);
    if (!source.ok()) return set_err(source.status(), IRX_ERR_IO);
    return open_stream_reader(*source, out);
}
int irx_rb_tcp_writer_open(const IrxRbSchema *schema, const char *host,
                            int port, int timeout_ms, IrxRbStreamWriter **out) {
    GUARD(out); *out = nullptr; GUARD(schema);
    auto sink = irx::tcp_output(host, port, timeout_ms);
    if (!sink.ok()) return set_err(sink.status(), IRX_ERR_IO);
    return open_writer(schema, *sink, false, out);
}
int irx_rb_fd_reader_open(int fd, IrxRbStreamReader **out) {
    GUARD(out); *out = nullptr;
    auto source = irx::fd_input(fd);
    if (!source.ok()) return set_err(source.status(), IRX_ERR_IO);
    return open_stream_reader(*source, out);
}
int irx_rb_fd_writer_open(const IrxRbSchema *schema, int fd,
                           IrxRbStreamWriter **out) {
    GUARD(out); *out = nullptr; GUARD(schema);
    auto sink = irx::fd_output(fd);
    if (!sink.ok()) return set_err(sink.status(), IRX_ERR_IO);
    return open_writer(schema, *sink, false, out);
}
int irx_rb_schema_clone(const IrxRbSchema *schema, IrxRbSchema **out) {
    GUARD(out); *out = nullptr; GUARD(schema);
    *out = new IrxRbSchema(*schema);
    return IRX_OK;
}
int irx_rb_batch_clone(const IrxRbBatch *batch, IrxRbBatch **out) {
    GUARD(out); *out = nullptr; GUARD(batch);
    *out = new IrxRbBatch(*batch);
    return IRX_OK;
}
int irx_rb_schema_type_name(const IrxRbSchema *schema, int col, const char **out) {
    GUARD(schema); GUARD(out);
    if (col < 0 || col >= schema->schema->num_fields())
        return set_err("schema field index out of bounds", IRX_ERR_OOB);
    static thread_local std::string name;
    name = schema->schema->field(col)->type()->ToString();
    if (name.find('\0') != std::string::npos)
        return set_err("embedded NUL in type name cannot be exposed as C text", IRX_ERR_TYPE);
    *out = name.c_str();
    return IRX_OK;
}

namespace {
arrow::Status csv_schema(const arrow::Schema &schema) {
    if (!schema.num_fields()) return arrow::Status::Invalid("CSV requires at least one column");
    std::unordered_set<std::string> names;
    for (const auto &field : schema.fields()) {
        const auto &name = field->name();
        if (name.empty() || name.find('\0') != std::string::npos ||
            !arrow::util::ValidateUTF8(name) || !names.insert(name).second)
            return arrow::Status::Invalid("CSV requires unique nonempty UTF-8 column names: '", name, "'");
        if (col_type_from_arrow(*field->type()) < IRX_COL_INT8 ||
            col_type_from_arrow(*field->type()) > IRX_COL_TIME64_NS)
            return arrow::Status::TypeError("Unsupported CSV column '", name, "' (",
                field->type()->ToString(), "); use an explicit supported schema");
    }
    return arrow::Status::OK();
}
arrow::Status csv_options(const char *delimiter, int header) {
    if (!delimiter || !delimiter[0] || delimiter[1] ||
        static_cast<unsigned char>(delimiter[0]) > 127 ||
        delimiter[0] == '"' || delimiter[0] == '\r' || delimiter[0] == '\n')
        return arrow::Status::Invalid("CSV delimiter must be one ASCII byte other than NUL, quote, CR or LF");
    if (header != 0 && header != 1)
        return arrow::Status::Invalid("CSV header must be boolean");
    return arrow::Status::OK();
}

// Conversion options alone do not enforce header order or field nullability.
class CsvReader final : public arrow::RecordBatchReader {
 public:
    CsvReader(std::shared_ptr<arrow::RecordBatchReader> reader,
              std::shared_ptr<arrow::Schema> schema)
        : reader_(std::move(reader)), schema_(std::move(schema)) {}
    std::shared_ptr<arrow::Schema> schema() const override { return schema_; }
    arrow::Status Close() override { return reader_->Close(); }
    arrow::Status ReadNext(std::shared_ptr<arrow::RecordBatch> *out) override {
        *out = nullptr;
        std::shared_ptr<arrow::RecordBatch> batch;
        ARROW_RETURN_NOT_OK(reader_->ReadNext(&batch));
        if (!batch) return arrow::Status::OK();
        for (int i = 0; i < schema_->num_fields(); ++i) {
            if (!schema_->field(i)->nullable() && batch->column(i)->null_count())
                return arrow::Status::Invalid("CSV column '", schema_->field(i)->name(),
                                              "' contains nulls but is not nullable");
        }
        *out = arrow::RecordBatch::Make(schema_, batch->num_rows(), batch->columns());
        return (*out)->ValidateFull();
    }
 private:
    std::shared_ptr<arrow::RecordBatchReader> reader_;
    std::shared_ptr<arrow::Schema> schema_;
};

arrow::Status dataframe_schema(const arrow::Schema &schema) {
    if (!schema.num_fields()) return arrow::Status::Invalid("DataFrame requires a nonempty static schema");
    std::unordered_set<std::string> names;
    for (const auto &field : schema.fields()) {
        auto type = field->type()->id();
        if (type != arrow::Type::INT8 && type != arrow::Type::INT16 &&
            type != arrow::Type::INT32 && type != arrow::Type::INT64 &&
            type != arrow::Type::FLOAT && type != arrow::Type::DOUBLE &&
            type != arrow::Type::BOOL)
            return arrow::Status::TypeError("Cannot convert column '", field->name(),
                "' (", field->type()->ToString(), ") to DataFrame: only non-null signed integers, "
                "f32, f64 and bool are supported; keep this data as a RecordBatch");
        if (field->name().empty() || field->name().find('\0') != std::string::npos ||
            !arrow::util::ValidateUTF8(field->name()) || !names.insert(field->name()).second)
            return arrow::Status::Invalid("DataFrame requires unique nonempty column names");
    }
    return arrow::Status::OK();
}
} // namespace

int irx_rb_csv_reader_open(const char *path, const IrxRbSchema *schema,
                          const char *delimiter, int header, int block_size,
                          IrxRbStreamReader **out) {
    GUARD(out); *out = nullptr; GUARD(path);
    try {
        auto status = csv_options(delimiter, header);
        if (!status.ok()) return set_err(status, IRX_ERR_TYPE);
        if (block_size <= 0) return set_err("CSV block_size must be positive", IRX_ERR_TYPE);
        auto read = arrow::csv::ReadOptions::Defaults();
        auto parse = arrow::csv::ParseOptions::Defaults();
        auto convert = arrow::csv::ConvertOptions::Defaults();
        read.use_threads = false;
        read.block_size = block_size;
        read.autogenerate_column_names = !header && !schema;
        parse.delimiter = delimiter[0];
        parse.newlines_in_values = true;
        parse.ignore_empty_lines = false;
        convert.null_values = {""};
        convert.strings_can_be_null = true;
        convert.quoted_strings_can_be_null = false;
        convert.check_utf8 = true;
        if (schema) {
            status = csv_schema(*schema->schema);
            if (!status.ok()) return set_err(status, IRX_ERR_TYPE);
            for (const auto &field : schema->schema->fields()) {
                convert.column_types.emplace(field->name(), field->type());
                if (!header) read.column_names.push_back(field->name());
            }
        }
        auto source = arrow::io::ReadableFile::Open(path);
        if (!source.ok()) return set_err(source.status(), IRX_ERR_IO);
        auto reader = arrow::csv::StreamingReader::Make(
            arrow::io::default_io_context(), *source, read, parse, convert);
        if (!reader.ok()) return set_err(reader.status());
        auto actual = (*reader)->schema();
        status = csv_schema(*actual);
        if (!status.ok()) return set_err(status, IRX_ERR_TYPE);
        if (schema) {
            if (actual->num_fields() != schema->schema->num_fields())
                return set_err("CSV header column count does not match explicit schema", IRX_ERR_TYPE);
            for (int i = 0; i < actual->num_fields(); ++i) {
                if (actual->field(i)->name() != schema->schema->field(i)->name() ||
                    !actual->field(i)->type()->Equals(schema->schema->field(i)->type()))
                    return set_err("CSV column '" + actual->field(i)->name() +
                        "' does not match explicit schema name/order/type", IRX_ERR_TYPE);
            }
        }
        auto result = std::make_unique<IrxRbStreamReader>();
        result->reader = std::make_shared<CsvReader>(*reader, schema ? schema->schema : actual);
        result->source = *source;
        int rc = populate_schema(result->reader->schema(), &result->schema_handle);
        if (rc != IRX_OK) return rc;
        result->schema_handle.reader_owned = true;
        *out = result.release();
        return IRX_OK;
    } catch (const std::exception &error) {
        return set_err(std::string("CSV reader: ") + error.what());
    }
}

int irx_rb_csv_writer_open(const IrxRbSchema *schema, const char *path,
                          const char *delimiter, int header, IrxRbStreamWriter **out) {
    GUARD(out); *out = nullptr; GUARD(schema); GUARD(path);
    try {
        auto status = csv_options(delimiter, header);
        if (!status.ok()) return set_err(status, IRX_ERR_TYPE);
        status = csv_schema(*schema->schema);
        if (!status.ok()) return set_err(status, IRX_ERR_TYPE);
        auto options = arrow::csv::WriteOptions::Defaults();
        options.delimiter = delimiter[0];
        options.include_header = header;
        status = options.Validate();
        if (!status.ok()) return set_err(status, IRX_ERR_TYPE);
        auto sink = arrow::io::FileOutputStream::Open(path);
        if (!sink.ok()) return set_err(sink.status(), IRX_ERR_IO);
        auto writer = arrow::csv::MakeCSVWriter(*sink, schema->schema, options);
        if (!writer.ok()) return set_err(writer.status());
        auto result = std::make_unique<IrxRbStreamWriter>();
        result->sink = *sink;
        result->writer = *writer;
        result->schema = schema->schema;
        result->csv = true;
        *out = result.release();
        return IRX_OK;
    } catch (const std::exception &error) {
        return set_err(std::string("CSV writer: ") + error.what());
    }
}

int irx_rb_batch_to_table(const IrxRbBatch *batch, const IrxRbSchema *expected,
                         irx_arrow_table_handle **out) {
    GUARD(out); *out = nullptr; GUARD(batch); GUARD(expected);
    ArrowArray array{};
    ArrowSchema schema{};
    // C Data exports are independent references and must be released on all paths.
    struct Release {
        ArrowArray &a; ArrowSchema &s;
        ~Release() { if (a.release) a.release(&a); if (s.release) s.release(&s); }
    } release{array, schema};
    try {
        auto status = dataframe_schema(*batch->batch->schema());
        if (!status.ok()) return set_err(status, IRX_ERR_TYPE);
        status = dataframe_schema(*expected->schema);
        if (!status.ok()) return set_err(status, IRX_ERR_TYPE);
        if (batch->batch->num_columns() != expected->schema->num_fields())
            return set_err("DataFrame column count does not match the declared schema", IRX_ERR_TYPE);
        for (int i = 0; i < batch->batch->num_columns(); ++i) {
            auto actual = batch->batch->schema()->field(i);
            auto field = expected->schema->field(i);
            if (field->nullable()) return set_err("nullable DataFrame targets are unsupported", IRX_ERR_TYPE);
            if (actual->name() != field->name() || !actual->type()->Equals(field->type()))
                return set_err("Cannot convert column '" + actual->name() + "' (" +
                    actual->type()->ToString() + "): expected '" + field->name() + "' (" +
                    field->type()->ToString() + "); use a matching explicit CSV schema", IRX_ERR_TYPE);
            if (batch->batch->column(i)->null_count())
                return set_err("Cannot convert column '" + field->name() +
                    "' to DataFrame: the current batch contains null values; keep it as a RecordBatch", IRX_ERR_TYPE);
        }
        auto converted = arrow::RecordBatch::Make(expected->schema, batch->batch->num_rows(), batch->batch->columns());
        status = converted->ValidateFull();
        if (!status.ok()) return set_err(status);
        status = arrow::ExportRecordBatch(*converted, &array, &schema);
        if (!status.ok()) return set_err(status);
        int rc = irx_arrow_table_import_batch(&array, &schema, out);
        return rc == 0 ? IRX_OK : set_err(irx_arrow_last_error());
    } catch (const std::exception &error) {
        return set_err(std::string("DataFrame conversion: ") + error.what());
    }
}

int irx_rb_table_to_batch(const irx_arrow_table_handle *table, IrxRbBatch **out) {
    GUARD(out); *out = nullptr; GUARD(table);
    ArrowArray array{};
    ArrowSchema schema{};
    struct Release {
        ArrowArray &a; ArrowSchema &s;
        ~Release() { if (a.release) a.release(&a); if (s.release) s.release(&s); }
    } release{array, schema};
    try {
        if (irx_arrow_table_export_batch(table, &array, &schema) != 0)
            return set_err(irx_arrow_last_error());
        auto imported = arrow::ImportRecordBatch(&array, &schema);
        if (!imported.ok()) return set_err(imported.status());
        auto status = dataframe_schema(*(*imported)->schema());
        if (!status.ok()) return set_err(status, IRX_ERR_TYPE);
        for (int i = 0; i < (*imported)->num_columns(); ++i) {
            if ((*imported)->column(i)->null_count())
                return set_err("DataFrame column '" + (*imported)->schema()->field(i)->name() + "' contains null values", IRX_ERR_TYPE);
        }
        auto result = std::make_unique<IrxRbBatch>();
        result->batch = *imported;
        IrxRbSchema described;
        int rc = populate_schema(result->batch->schema(), &described);
        if (rc != IRX_OK) return rc;
        result->col_types = described.col_types;
        result->col_descs = described.col_descs;
        *out = result.release();
        return IRX_OK;
    } catch (const std::exception &error) {
        return set_err(std::string("RecordBatch conversion: ") + error.what());
    }
}
