// Copyright IRx contributors.
#include "irx_parquet_io.h"
#include "irx_parquet_commit.h"

#include <arrow/api.h>
#include <arrow/compute/api.h>
#include <arrow/compute/initialize.h>
#include <arrow/dataset/api.h>
#include <arrow/extension_type.h>
#include <arrow/filesystem/api.h>
#include <arrow/io/api.h>
#include <arrow/ipc/api.h>
#include <arrow/util/compression.h>
#include <arrow/util/key_value_metadata.h>
#include <arrow/util/utf8.h>
#include <parquet/arrow/reader.h>
#include <parquet/arrow/writer.h>
#include <parquet/encryption/encryption.h>
#include <parquet/properties.h>
#include <algorithm>
#include <filesystem>
#include <numeric>
#include <random>
#include <unordered_set>
#ifndef _WIN32
#include <unistd.h>
#endif

namespace irx {
namespace {
using arrow::Status;
namespace ds = arrow::dataset;
namespace cp = arrow::compute;
constexpr const char *logical_schema_key = "IRX:logical_schema:v1";

arrow::Result<std::shared_ptr<arrow::DataType>> physical_type(
    const std::shared_ptr<arrow::DataType> &type, bool normalize,
    bool reconstruct = false, bool storage = false) {
    switch (type->id()) {
    case arrow::Type::INT8: case arrow::Type::INT16:
    case arrow::Type::INT32: case arrow::Type::INT64:
    case arrow::Type::UINT8: case arrow::Type::UINT16:
    case arrow::Type::UINT32: case arrow::Type::UINT64:
    case arrow::Type::FLOAT: case arrow::Type::DOUBLE:
    case arrow::Type::BOOL: case arrow::Type::STRING:
    case arrow::Type::LARGE_STRING: case arrow::Type::DATE32:
    case arrow::Type::TIME64: case arrow::Type::BINARY:
    case arrow::Type::LARGE_BINARY: case arrow::Type::FIXED_SIZE_BINARY:
    case arrow::Type::DECIMAL128: case arrow::Type::DECIMAL256:
    case arrow::Type::NA:
        return type;
    case arrow::Type::DATE64:
        if (normalize) return arrow::date32();
        break;
    case arrow::Type::TIMESTAMP: {
        auto &t = static_cast<const arrow::TimestampType &>(*type);
        if (t.unit() != arrow::TimeUnit::SECOND) return type;
        if (normalize) return arrow::timestamp(arrow::TimeUnit::MILLI, t.timezone());
        break;
    }
    case arrow::Type::TIME32:
        if (static_cast<const arrow::Time32Type &>(*type).unit() != arrow::TimeUnit::SECOND) return type;
        if (normalize) return arrow::time32(arrow::TimeUnit::MILLI);
        break;
    case arrow::Type::LIST: case arrow::Type::LARGE_LIST:
    case arrow::Type::FIXED_SIZE_LIST: {
        auto field = type->field(0);
        ARROW_ASSIGN_OR_RAISE(auto child, physical_type(field->type(), normalize, reconstruct, storage));
        field = field->WithType(child);
        if (type->id() == arrow::Type::LIST) return arrow::list(field);
        if (type->id() == arrow::Type::LARGE_LIST) return arrow::large_list(field);
        if (reconstruct && storage) return arrow::list(field);
        return arrow::fixed_size_list(field, static_cast<const arrow::FixedSizeListType &>(*type).list_size());
    }
    case arrow::Type::STRUCT: {
        arrow::FieldVector fields;
        for (const auto &field : type->fields()) {
            ARROW_ASSIGN_OR_RAISE(auto child, physical_type(field->type(), normalize, reconstruct, storage));
            fields.push_back(field->WithType(child));
        }
        return arrow::struct_(fields);
    }
    case arrow::Type::MAP: {
        auto &t = static_cast<const arrow::MapType &>(*type);
        ARROW_ASSIGN_OR_RAISE(auto key, physical_type(t.key_type(), normalize, reconstruct, storage));
        ARROW_ASSIGN_OR_RAISE(auto item, physical_type(t.item_type(), normalize, reconstruct, storage));
        return std::make_shared<arrow::MapType>(t.key_field()->WithType(key), t.item_field()->WithType(item), t.keys_sorted());
    }
    case arrow::Type::DICTIONARY: {
        auto &t = static_cast<const arrow::DictionaryType &>(*type);
        if (reconstruct && t.ordered())
            return Status::NotImplemented("logical reconstruction cannot preserve ordered dictionary codebooks; use IPC");
        ARROW_ASSIGN_OR_RAISE(auto child, physical_type(t.value_type(), normalize, reconstruct, storage));
        // Arrow's Parquet reader reconstructs dictionaries for binary/string
        // values only. Other dictionaries would silently decode to plain arrays.
        if (child->id() != arrow::Type::STRING && child->id() != arrow::Type::BINARY &&
            !(reconstruct && ((arrow::is_integer(child->id()) || arrow::is_floating(child->id())) || arrow::is_decimal(child->id()))))
            return Status::NotImplemented("Parquet dictionary values must be string or binary; use reconstruct=true for numeric dictionaries");
        if (reconstruct && storage) return child;
        return arrow::dictionary(t.index_type(), child, t.ordered());
    }
    case arrow::Type::EXTENSION: {
        auto &t = static_cast<const arrow::ExtensionType &>(*type);
        ARROW_ASSIGN_OR_RAISE(auto storage, physical_type(t.storage_type(), false));
        if (!storage->Equals(t.storage_type())) return Status::Invalid("extension storage cannot be normalized");
        if (!arrow::GetExtensionType(t.extension_name()))
            return Status::NotImplemented("extension must be registered in the native Arrow registry: ", t.extension_name());
        return type;
    }
    default: break;
    }
    return Status::TypeError("Unsupported Parquet type ", type->ToString(),
        "; implicit coercion is disabled; use normalize=true for checked temporal normalization, or IPC");
}

Status field_names(const arrow::FieldVector &fields) {
    std::unordered_set<std::string> names;
    for (const auto &field : fields) {
        // Unknown extensions remain opaque storage plus their exact Arrow
        // extension metadata. No Python callbacks run in compiled programs.
        const auto &name = field->name();
        if (name.empty() || name.find('\0') != std::string::npos ||
            !arrow::util::ValidateUTF8(name) || !names.insert(name).second)
            return Status::Invalid("Parquet requires unique nonempty UTF-8 column names: '", name, "'");
        ARROW_RETURN_NOT_OK(field_names(field->type()->fields()));
    }
    return Status::OK();
}

arrow::Result<std::shared_ptr<arrow::Schema>> physical_schema(
    const std::shared_ptr<arrow::Schema> &schema, bool writing, bool normalize,
    bool reconstruct = false, bool storage = false) {
    if (!schema->num_fields()) return Status::Invalid("Parquet requires at least one column");
    if (writing && schema->metadata() && schema->metadata()->Contains("ARROW:schema"))
        return Status::Invalid("Parquet reserves the ARROW:schema metadata key");
    if (writing && schema->metadata() && schema->metadata()->Contains(logical_schema_key))
        return Status::Invalid("Parquet reserves the IRX logical schema metadata key");
    ARROW_RETURN_NOT_OK(field_names(schema->fields()));
    arrow::FieldVector fields;
    for (const auto &field : schema->fields()) {
        auto type = physical_type(field->type(), normalize, reconstruct, storage);
        if (!type.ok()) return Status::TypeError("Unsupported Parquet column '", field->name(), "': ", type.status().ToString());
        fields.push_back(field->WithType(*type));
    }
    return arrow::schema(fields, schema->metadata());
}

// Validate only reachable child slots. A null struct/list parent may contain
// arbitrary child storage, including nulls in otherwise required child fields.
Status reachable_value(const arrow::Field &field, const arrow::Array &array, int64_t row) {
    if (array.IsNull(row)) {
        return field.nullable() ? Status::OK() : Status::Invalid("Parquet column '", field.name(), "' contains nulls but is not nullable");
    }
    if (array.type_id() == arrow::Type::DICTIONARY) {
        const auto &a = static_cast<const arrow::DictionaryArray &>(array);
        return reachable_value(field, *a.dictionary(), a.GetValueIndex(row));
    }
    if (array.type_id() == arrow::Type::STRUCT) {
        auto &a = static_cast<const arrow::StructArray &>(array);
        for (int i = 0; i < a.num_fields(); ++i)
            ARROW_RETURN_NOT_OK(reachable_value(*field.type()->field(i), *a.field(i), row));
    } else if (array.type_id() == arrow::Type::LIST || array.type_id() == arrow::Type::MAP) {
        auto &a = static_cast<const arrow::ListArray &>(array);
        for (auto i = a.value_offset(row); i < a.value_offset(row) + a.value_length(row); ++i)
            ARROW_RETURN_NOT_OK(reachable_value(*field.type()->field(0), *a.values(), i));
    } else if (array.type_id() == arrow::Type::LARGE_LIST) {
        auto &a = static_cast<const arrow::LargeListArray &>(array);
        for (auto i = a.value_offset(row); i < a.value_offset(row) + a.value_length(row); ++i)
            ARROW_RETURN_NOT_OK(reachable_value(*field.type()->field(0), *a.values(), i));
    } else if (array.type_id() == arrow::Type::FIXED_SIZE_LIST) {
        auto &a = static_cast<const arrow::FixedSizeListArray &>(array);
        for (auto i = a.value_offset(row); i < a.value_offset(row) + a.value_length(); ++i)
            ARROW_RETURN_NOT_OK(reachable_value(*field.type()->field(0), *a.values(), i));
    }
    return Status::OK();
}

Status validate_nulls(const arrow::RecordBatch &batch, bool reconstruct = false) {
    for (int i = 0; i < batch.num_columns(); ++i) {
        const auto &field = *batch.schema()->field(i);
        const auto &array = *batch.column(i);
        if (!reconstruct && array.type_id() == arrow::Type::FIXED_SIZE_LIST && array.null_count())
            return Status::NotImplemented("Parquet fixed-size list null parents cannot roundtrip in this Arrow backend; use variable lists");
        if (field.type()->num_fields() || array.type_id() == arrow::Type::DICTIONARY) {
            for (int64_t row = 0; row < array.length(); ++row)
                ARROW_RETURN_NOT_OK(reachable_value(field, array, row));
        } else if (!field.nullable() && array.null_count())
            return Status::Invalid("Parquet column '", field.name(), "' contains nulls but is not nullable");
    }
    return Status::OK();
}

// Arrow's Parquet writer also checks required child storage beneath null
// parents. Canonicalize only those unreachable null slots after validating all
// reachable values; never fill a user-visible null or change the field schema.
arrow::Result<std::shared_ptr<arrow::Array>> canonical_children(
    const std::shared_ptr<arrow::Array> &array, const arrow::Field &field,
    bool reconstruct = false) {
    if (!reconstruct && array->type_id() == arrow::Type::FIXED_SIZE_LIST && array->null_count())
        return Status::NotImplemented("Parquet fixed-size list null parents cannot roundtrip in this Arrow backend; use variable lists");
    auto data = array->data()->Copy();
    const auto &fields = array->type()->fields();
    for (size_t i = 0; i < fields.size(); ++i) {
        ARROW_ASSIGN_OR_RAISE(auto child, canonical_children(
            arrow::MakeArray(data->child_data[i]), *fields[i], reconstruct));
        data->child_data[i] = child->data();
    }
    auto result = arrow::MakeArray(data);
    if (field.nullable() || !result->null_count()) return result;
    ARROW_ASSIGN_OR_RAISE(auto builder, arrow::MakeBuilder(result->type()));
    for (int64_t i = 0; i < result->length(); ++i) {
        if (result->IsNull(i)) { ARROW_RETURN_NOT_OK(builder->AppendEmptyValue()); }
        else {
            ARROW_ASSIGN_OR_RAISE(auto scalar, result->GetScalar(i));
            ARROW_RETURN_NOT_OK(builder->AppendScalar(*scalar));
        }
    }
    return builder->Finish();
}

parquet::ReaderProperties reader_properties(const IrxParquetOptions &o) {
    parquet::ReaderProperties properties;
    if (!o.key.empty()) properties.file_decryption_properties(
        parquet::FileDecryptionProperties::Builder().footer_key(o.key)->build());
    return properties;
}

class OwnedReader final : public arrow::RecordBatchReader {
 public:
    OwnedReader(std::shared_ptr<arrow::RecordBatchReader> reader,
                std::shared_ptr<arrow::io::RandomAccessFile> source = nullptr,
                std::unique_ptr<parquet::arrow::FileReader> file = nullptr)
        : source_(std::move(source)), file_(std::move(file)), reader_(std::move(reader)), schema_(reader_->schema()) {}
    std::shared_ptr<arrow::Schema> schema() const override { return schema_; }
    Status ReadNext(std::shared_ptr<arrow::RecordBatch> *out) override {
        *out = nullptr;
        if (!failure_.ok()) return failure_;
        if (!reader_) return Status::Invalid("Parquet reader is closed");
        try { failure_ = reader_->ReadNext(out); }
        catch (const std::exception &error) { failure_ = Status::IOError("Parquet read: ", error.what()); }
        if (!failure_.ok()) *out = nullptr;
        return failure_;
    }
    Status Close() override {
        try {
            auto status = reader_ ? reader_->Close() : Status::OK();
            reader_.reset(); file_.reset();
            auto closed = source_ ? source_->Close() : Status::OK();
            source_.reset();
            return status.ok() ? closed : status;
        } catch (const std::exception &error) { return Status::IOError("Parquet reader close: ", error.what()); }
    }

 private:
    std::shared_ptr<arrow::io::RandomAccessFile> source_;
    std::unique_ptr<parquet::arrow::FileReader> file_;
    std::shared_ptr<arrow::RecordBatchReader> reader_;
    std::shared_ptr<arrow::Schema> schema_;
    Status failure_;
};

arrow::Result<std::shared_ptr<arrow::Array>> restore_array(
    std::shared_ptr<arrow::Array> array, const std::shared_ptr<arrow::DataType> &type) {
    if (array->type()->Equals(type)) return array;
    if (type->id() == arrow::Type::DICTIONARY) {
        const auto &dictionary = static_cast<const arrow::DictionaryType &>(*type);
        ARROW_ASSIGN_OR_RAISE(auto encoded, cp::DictionaryEncode(array));
        auto values = std::static_pointer_cast<arrow::DictionaryArray>(encoded.make_array());
        ARROW_ASSIGN_OR_RAISE(auto indices, cp::Cast(*values->indices(), dictionary.index_type(), cp::CastOptions::Safe()));
        return arrow::DictionaryArray::FromArrays(type, indices, values->dictionary());
    }
    if (type->id() == arrow::Type::FIXED_SIZE_LIST && array->type_id() == arrow::Type::LIST) {
        auto intermediate = arrow::fixed_size_list(array->type()->field(0),
            static_cast<const arrow::FixedSizeListType &>(*type).list_size());
        ARROW_ASSIGN_OR_RAISE(array, cp::Cast(*array, intermediate, cp::CastOptions::Safe()));
    }
    if (type->id() == array->type_id() && type->num_fields()) {
        auto data = array->data()->Copy();
        if (data->child_data.size() != static_cast<size_t>(type->num_fields()))
            return Status::TypeError("invalid reconstructed child count");
        for (int i = 0; i < type->num_fields(); ++i) {
            ARROW_ASSIGN_OR_RAISE(auto child, restore_array(arrow::MakeArray(data->child_data[i]), type->field(i)->type()));
            data->child_data[i] = child->data();
        }
        data->type = type;
        auto restored = arrow::MakeArray(data);
        ARROW_RETURN_NOT_OK(restored->ValidateFull());
        return restored;
    }
    return cp::Cast(*array, type, cp::CastOptions::Safe());
}

class RestoringReader final : public arrow::RecordBatchReader {
 public:
    RestoringReader(std::shared_ptr<arrow::RecordBatchReader> reader, std::shared_ptr<arrow::Schema> schema)
        : reader_(std::move(reader)), schema_(std::move(schema)) {}
    std::shared_ptr<arrow::Schema> schema() const override { return schema_; }
    Status ReadNext(std::shared_ptr<arrow::RecordBatch> *out) override {
        *out = nullptr;
        if (!failure_.ok()) return failure_;
        if (!reader_) return Status::Invalid("reconstructing Parquet reader is closed");
        auto next = read();
        if (!next.ok()) return failure_ = next.status();
        *out = *next;
        return Status::OK();
    }
    Status Close() override {
        auto status = reader_ ? reader_->Close() : Status::OK();
        reader_.reset();
        return status;
    }
 private:
    arrow::Result<std::shared_ptr<arrow::RecordBatch>> read() {
        std::shared_ptr<arrow::RecordBatch> batch;
        ARROW_RETURN_NOT_OK(reader_->ReadNext(&batch));
        if (!batch) return batch;
        arrow::ArrayVector columns;
        for (int i = 0; i < batch->num_columns(); ++i) {
            ARROW_ASSIGN_OR_RAISE(auto values, restore_array(batch->column(i), schema_->field(i)->type()));
            columns.push_back(values);
        }
        return arrow::RecordBatch::Make(schema_, batch->num_rows(), columns);
    }
    std::shared_ptr<arrow::RecordBatchReader> reader_;
    std::shared_ptr<arrow::Schema> schema_;
    Status failure_;
};

arrow::Result<std::shared_ptr<arrow::RecordBatchReader>> restore_reader(
    const std::shared_ptr<arrow::RecordBatchReader> &reader) {
    auto actual = reader->schema();
    if (!actual->metadata() || !actual->metadata()->Contains(logical_schema_key)) return reader;
    ARROW_RETURN_NOT_OK(cp::Initialize());
    ARROW_ASSIGN_OR_RAISE(auto serialized, actual->metadata()->Get(logical_schema_key));
    arrow::io::BufferReader input(arrow::Buffer::FromString(serialized));
    arrow::ipc::DictionaryMemo dictionaries;
    ARROW_ASSIGN_OR_RAISE(auto logical, arrow::ipc::ReadSchema(&input, &dictionaries));
    ARROW_RETURN_NOT_OK(physical_schema(logical, false, false, true).status());
    arrow::FieldVector fields;
    for (const auto &field : actual->fields()) {
        auto original = logical->GetFieldByName(field->name());
        if (!original) return Status::Invalid("reconstruction metadata is missing a projected field");
        ARROW_ASSIGN_OR_RAISE(auto storage, physical_type(original->type(), false, true, true));
        if (!original->WithType(storage)->Equals(field, true))
            return Status::TypeError("reconstruction metadata does not match physical field '", field->name(), "'");
        fields.push_back(original);
    }
    return std::make_shared<RestoringReader>(reader, arrow::schema(fields, logical->metadata()));
}

arrow::Result<std::shared_ptr<arrow::Schema>> metadata_schema(
    const std::shared_ptr<arrow::fs::FileSystem> &fs, const std::string &path,
    const IrxParquetOptions &options) {
    ARROW_ASSIGN_OR_RAISE(auto source, fs->OpenInputFile(path));
    parquet::arrow::FileReaderBuilder builder;
    ARROW_RETURN_NOT_OK(builder.Open(source, reader_properties(options)));
    ARROW_ASSIGN_OR_RAISE(auto file, builder.Build());
    std::shared_ptr<arrow::Schema> schema;
    ARROW_RETURN_NOT_OK(file->GetSchema(&schema));
    return schema;
}

arrow::Result<std::shared_ptr<arrow::RecordBatchReader>> scan_reader(
    const std::shared_ptr<arrow::fs::FileSystem> &fs, const std::string &path,
    const IrxParquetOptions &o) {
    ARROW_RETURN_NOT_OK(cp::Initialize());
    auto format = std::make_shared<ds::ParquetFileFormat>(reader_properties(o));
    auto fragment_options = std::make_shared<ds::ParquetFragmentScanOptions>();
    fragment_options->reader_properties = std::make_shared<parquet::ReaderProperties>(reader_properties(o));
    fragment_options->arrow_reader_properties = std::make_shared<parquet::ArrowReaderProperties>();
    fragment_options->arrow_reader_properties->set_pre_buffer(o.pre_buffer);
    fragment_options->arrow_reader_properties->set_arrow_extensions_enabled(true);
    format->default_fragment_scan_options = fragment_options;
    std::shared_ptr<ds::Dataset> dataset;
    if (o.dataset) {
        if (!o.row_groups.empty()) return Status::Invalid("row_groups apply to a single file, not a dataset");
        ds::FileSystemFactoryOptions factory_options;
        std::shared_ptr<arrow::Schema> recorded_schema;
        if (o.hive) {
            ARROW_ASSIGN_OR_RAISE(auto metadata, fs->GetFileInfo(path + "/_common_metadata"));
            if (metadata.type() == arrow::fs::FileType::File) {
                ARROW_ASSIGN_OR_RAISE(recorded_schema, metadata_schema(fs, metadata.path(), o));
                factory_options.partitioning = std::make_shared<ds::HivePartitioning>(recorded_schema);
            } else factory_options.partitioning = ds::HivePartitioning::MakeFactory();
        }
        arrow::fs::FileSelector selector;
        selector.base_dir = path;
        selector.recursive = true;
        ARROW_ASSIGN_OR_RAISE(auto factory, ds::FileSystemDatasetFactory::Make(fs, selector, format, factory_options));
        ds::InspectOptions inspect;
        inspect.fragments = ds::InspectOptions::kInspectAllFragments;
        ARROW_ASSIGN_OR_RAISE(auto schemas, factory->InspectSchemas(inspect));
        // Strict mode checks every physical file, never only the first fragment.
        // The final schema in InspectSchemas is the partition schema.
        if (!o.unify && schemas.size() > 2) {
            for (size_t i = 1; i + 1 < schemas.size(); ++i)
                if (!schemas[0]->Equals(*schemas[i], true))
                    return Status::TypeError("dataset schemas differ; set unify=true to union same-typed nullable fields");
        }
        if (o.unify) {
            // Do not let Arrow's default null-type promotion or missing-field
            // synthesis silently weaken our exact-type/nullability contract.
            for (size_t i = 0; i + 1 < schemas.size(); ++i) {
                for (const auto &field : schemas[i]->fields()) {
                    for (size_t j = 0; j + 1 < schemas.size(); ++j) {
                        auto other = schemas[j]->GetFieldByName(field->name());
                        if (!other && !field->nullable())
                            return Status::TypeError("missing dataset column must be nullable: ", field->name());
                        if (other && !other->type()->Equals(field->type()))
                            return Status::TypeError("dataset column types differ: ", field->name());
                    }
                }
            }
        }
        ds::FinishOptions finish;
        finish.inspect_options = inspect;
        finish.validate_fragments = true;
        if (recorded_schema) {
            // Physical fragments omit partition columns. Keep the recorded
            // field order/metadata instead of moving every partition to the end.
            for (size_t i = 0; i + 1 < schemas.size(); ++i) {
                for (const auto &field : schemas[i]->fields()) {
                    auto recorded = recorded_schema->GetFieldByName(field->name());
                    if (recorded && !recorded->type()->Equals(field->type()))
                        return Status::TypeError("recorded dataset column type differs: ", field->name());
                }
            }
            ARROW_ASSIGN_OR_RAISE(auto discovered, factory->Inspect(inspect));
            ARROW_ASSIGN_OR_RAISE(finish.schema, arrow::UnifySchemas({recorded_schema, discovered}));
        }
        ARROW_ASSIGN_OR_RAISE(dataset, factory->Finish(finish));
    } else {
        ds::FileSource source(path, fs);
        ARROW_ASSIGN_OR_RAISE(auto schema, format->Inspect(source));
        std::shared_ptr<ds::FileFragment> fragment;
        if (o.row_groups.empty()) {
            ARROW_ASSIGN_OR_RAISE(fragment, format->MakeFragment(source, cp::literal(true), schema));
        } else {
            ARROW_ASSIGN_OR_RAISE(auto selected, format->MakeFragment(source, cp::literal(true), schema, o.row_groups));
            ARROW_RETURN_NOT_OK(selected->EnsureCompleteMetadata());
            fragment = selected;
        }
        ARROW_ASSIGN_OR_RAISE(dataset, ds::FileSystemDataset::Make(schema, cp::literal(true), format, fs, {fragment}));
    }
    ARROW_ASSIGN_OR_RAISE(auto builder, dataset->NewScan());
    if (!o.columns.empty()) ARROW_RETURN_NOT_OK(builder->Project(o.columns));
    cp::Expression filter = cp::literal(true);
    for (const auto &p : o.predicates) {
        cp::Expression predicate;
        if (p.operation == "is_null" || p.operation == "is_valid") {
            predicate = cp::call(p.operation, {cp::field_ref(p.column)});
        } else {
            auto type = p.type == "string" ? arrow::utf8() : p.type == "int64" ? arrow::int64() : p.type == "double" ? arrow::float64() : arrow::boolean();
            ARROW_ASSIGN_OR_RAISE(auto value, arrow::Scalar::Parse(type, p.value));
            std::string op = p.operation == "eq" ? "equal" : p.operation == "ne" ? "not_equal" : p.operation == "lt" ? "less" : p.operation == "le" ? "less_equal" : p.operation == "gt" ? "greater" : "greater_equal";
            predicate = cp::call(op, {cp::field_ref(p.column), cp::literal(value)});
        }
        filter = cp::and_(filter, predicate);
    }
    ARROW_RETURN_NOT_OK(builder->Filter(filter));
    ARROW_RETURN_NOT_OK(builder->UseThreads(o.use_threads));
    ARROW_RETURN_NOT_OK(builder->BatchSize(o.batch_size));
    ARROW_RETURN_NOT_OK(builder->BatchReadahead(0));
    ARROW_RETURN_NOT_OK(builder->FragmentReadahead(1));
    ARROW_RETURN_NOT_OK(builder->FragmentScanOptions(fragment_options));
    ARROW_ASSIGN_OR_RAISE(auto scanner, builder->Finish());
    return scanner->ToRecordBatchReader();
}

arrow::Result<std::shared_ptr<arrow::RecordBatch>> prepare_batch(
    const arrow::RecordBatch &batch, const std::shared_ptr<arrow::Schema> &physical) {
    bool reconstruct = physical->metadata() && physical->metadata()->Contains(logical_schema_key);
    ARROW_RETURN_NOT_OK(validate_nulls(batch, reconstruct));
    std::shared_ptr<arrow::Array> indices;
    if (reconstruct) {
        arrow::Int64Builder builder;
        ARROW_RETURN_NOT_OK(builder.Reserve(batch.num_rows()));
        for (int64_t row = 0; row < batch.num_rows(); ++row) builder.UnsafeAppend(row);
        ARROW_ASSIGN_OR_RAISE(indices, builder.Finish());
    }
    arrow::ArrayVector arrays;
    for (int i = 0; i < batch.num_columns(); ++i) {
        ARROW_ASSIGN_OR_RAISE(auto array, canonical_children(batch.column(i), *batch.schema()->field(i), reconstruct));
        const auto &type = physical->field(i)->type();
        if (!array->type()->Equals(type)) {
            ARROW_ASSIGN_OR_RAISE(array, cp::Cast(*array, type, cp::CastOptions::Safe()));
        }
        if (indices) {
            // Fixed-to-variable list casts retain child slots beneath null
            // parents. Parquet rejects those nonzero null ranges. Identity
            // Take compacts unreachable slots recursively without changing
            // any visible value, bounded by this input batch.
            ARROW_ASSIGN_OR_RAISE(auto compact, cp::Take(array, indices));
            array = compact.make_array();
        }
        arrays.push_back(array);
    }
    return arrow::RecordBatch::Make(physical, batch.num_rows(), arrays);
}

// Fresh encryption properties give every fragment its own AAD/nonce state.
// Reusing one FileEncryptionProperties object across fragments is unsafe.
class KeyedParquetFormat final : public ds::ParquetFileFormat {
 public:
    explicit KeyedParquetFormat(arrow::util::SecureString key) : key_(std::move(key)) {}
    arrow::Result<std::shared_ptr<ds::FileWriter>> MakeWriter(
        std::shared_ptr<arrow::io::OutputStream> sink, std::shared_ptr<arrow::Schema> schema,
        std::shared_ptr<ds::FileWriteOptions> options,
        arrow::fs::FileLocator locator) const override {
        auto input = std::static_pointer_cast<ds::ParquetFileWriteOptions>(options);
        auto output = std::make_shared<ds::ParquetFileWriteOptions>(*input);
        output->writer_properties = parquet::WriterProperties::Builder(*input->writer_properties)
            .encryption(parquet::FileEncryptionProperties::Builder(key_).build())->build();
        return ds::ParquetFileFormat::MakeWriter(sink, schema, output, locator);
    }
 private:
    arrow::util::SecureString key_;
};

class DatasetWriter final : public BatchWriter {
 public:
    DatasetWriter(ds::FileSystemDatasetWriteOptions options,
                  std::shared_ptr<arrow::Schema> schema, bool threads,
                  std::shared_ptr<LocalWriteLease> lease)
        : options_(std::move(options)), schema_(std::move(schema)), threads_(threads), lease_(std::move(lease)) {}
    Status WriteRecordBatch(const arrow::RecordBatch &batch) override {
        if (!failure_.ok()) return failure_;
        if (closed_) return Status::Invalid("Parquet dataset writer is closed");
        try {
            for (const auto &field : options_.partitioning->schema()->fields()) {
                if (field->type()->id() != arrow::Type::STRING) continue;
                const auto &values = static_cast<const arrow::StringArray &>(
                    *batch.GetColumnByName(field->name()));
                for (int64_t row = 0; row < values.length(); ++row)
                    if (!values.IsNull(row) && values.GetView(row) == "__HIVE_DEFAULT_PARTITION__")
                        return failure_ = Status::Invalid("partition column '", field->name(), "' contains the reserved Hive null marker; encode this value before partitioning");
            }
            auto prepared = prepare_batch(batch, schema_);
            if (!prepared.ok()) return failure_ = prepared.status();
            if (!batch.num_rows()) return Status::OK();
            auto reader = arrow::RecordBatchReader::Make({*prepared}, schema_);
            if (!reader.ok()) return failure_ = reader.status();
            auto builder = ds::ScannerBuilder::FromRecordBatchReader(*reader);
            auto status = builder->UseThreads(threads_);
            if (!status.ok()) return failure_ = status;
            auto scanner = builder->Finish();
            if (!scanner.ok()) return failure_ = scanner.status();
            // Each input batch is a bounded write. Fresh names allow appending
            // without truncating any existing fragment; no multi-file transaction.
            std::random_device random;
            std::string nonce;
            for (int i = 0; i < 4; ++i) nonce += std::to_string(random()) + "-";
            options_.basename_template = "irx-" + nonce + "{i}.parquet";
            failure_ = ds::FileSystemDataset::Write(options_, *scanner);
        } catch (const std::exception &error) { failure_ = Status::IOError("Parquet dataset write: ", error.what()); }
        return failure_;
    }
    Status Close() override {
        closed_ = true;
        lease_.reset();
        return failure_;
    }
    void Abandon() override { closed_ = true; lease_.reset(); }
    void Invalidate(const Status &status) override { failure_ = status; Abandon(); }
 private:
    ds::FileSystemDatasetWriteOptions options_;
    std::shared_ptr<arrow::Schema> schema_;
    bool threads_, closed_{false};
    std::shared_ptr<LocalWriteLease> lease_;
    Status failure_;
};

class SnapshotWriter final : public BatchWriter {
 public:
    SnapshotWriter(std::shared_ptr<BatchWriter> writer, std::shared_ptr<arrow::Schema> input,
                   std::shared_ptr<arrow::Schema> output, std::filesystem::path generation,
                   std::filesystem::path destination, std::shared_ptr<LocalWriteLease> lease,
                   bool durable)
        : writer_(std::move(writer)), input_(std::move(input)), output_(std::move(output)),
          generation_(std::move(generation)), destination_(std::move(destination)),
          lease_(std::move(lease)), durable_(durable) {}
    ~SnapshotWriter() override { Abandon(); }
    Status WriteRecordBatch(const arrow::RecordBatch &batch) override {
        if (!failure_.ok()) return failure_;
        if (closed_) return Status::Invalid("dataset transaction is closed");
        auto prepared = prepare_batch(batch, input_);
        if (!prepared.ok()) return failure_ = prepared.status();
        arrow::ArrayVector arrays;
        for (const auto &field : output_->fields()) {
            auto values = (*prepared)->GetColumnByName(field->name());
            if (!values) {
                auto nulls = arrow::MakeArrayOfNull(field->type(), batch.num_rows());
                if (!nulls.ok()) return failure_ = nulls.status();
                values = *nulls;
            }
            arrays.push_back(values);
        }
        failure_ = writer_->WriteRecordBatch(*arrow::RecordBatch::Make(output_, batch.num_rows(), arrays));
        return failure_;
    }
    Status Close() override {
        if (closed_) return failure_;
        closed_ = true;
        try {
            if (failure_.ok()) failure_ = writer_->Close();
            if (failure_.ok() && durable_) {
                std::vector<std::filesystem::path> directories{generation_};
                for (const auto &entry : std::filesystem::recursive_directory_iterator(generation_)) {
                    if (entry.is_directory()) directories.push_back(entry.path());
                    else if (failure_.ok()) failure_ = sync_local_path(entry.path(), false);
                }
                for (auto it = directories.rbegin(); failure_.ok() && it != directories.rend(); ++it)
                    failure_ = sync_local_path(*it, true);
                if (failure_.ok()) failure_ = sync_local_path(generation_.parent_path(), true);
            }
#ifndef _WIN32
            if (failure_.ok()) {
                std::string pattern = destination_.string() + ".irx-XXXXXX";
                int fd = ::mkstemp(pattern.data());
                if (fd < 0) failure_ = Status::IOError("cannot reserve dataset commit pointer");
                else {
                    (void)::close(fd);
                    pointer_ = pattern;
                    std::filesystem::remove(pointer_);
                    std::filesystem::create_symlink(generation_, pointer_);
                    std::filesystem::rename(pointer_, destination_);
                    pointer_.clear();
                    committed_ = true;
                    if (durable_) failure_ = sync_local_path(destination_.parent_path(), true);
                }
            }
#else
            failure_ = Status::NotImplemented("dataset snapshots require POSIX");
#endif
        } catch (const std::exception &error) { failure_ = Status::IOError("dataset commit: ", error.what()); }
        cleanup();
        return failure_;
    }
    void Invalidate(const Status &status) override { failure_ = status; Abandon(); }
    void Abandon() override {
        if (writer_) writer_->Abandon();
        closed_ = true;
        cleanup();
    }
 private:
    void cleanup() {
        std::error_code ignored;
        if (!pointer_.empty()) std::filesystem::remove(pointer_, ignored);
        if (!committed_) std::filesystem::remove_all(generation_, ignored);
        lease_.reset();
    }
    std::shared_ptr<BatchWriter> writer_;
    std::shared_ptr<arrow::Schema> input_, output_;
    std::filesystem::path generation_, destination_, pointer_;
    std::shared_ptr<LocalWriteLease> lease_;
    bool durable_, closed_{false}, committed_{false};
    Status failure_;
};

arrow::Result<std::shared_ptr<BatchWriter>> snapshot_writer(
    const std::shared_ptr<arrow::fs::FileSystem> &fs, const std::string &path,
    const std::shared_ptr<arrow::Schema> &input, const IrxParquetOptions &o) {
#ifdef _WIN32
    return Status::NotImplemented("dataset snapshots require POSIX");
#else
    if (fs->type_name() != "local") return Status::NotImplemented("dataset snapshots require a local POSIX filesystem");
    std::filesystem::path destination = std::filesystem::absolute(path).lexically_normal();
    destination = std::filesystem::canonical(destination.parent_path()) / destination.filename();
    ARROW_ASSIGN_OR_RAISE(auto lease, LocalWriteLease::Acquire(destination.string()));
    auto versions = destination.parent_path() / ("." + destination.filename().string() + ".irx-versions");
    std::filesystem::path previous;
    if (std::filesystem::exists(destination) || std::filesystem::is_symlink(destination)) {
        if (!std::filesystem::is_symlink(destination))
            return Status::Invalid("atomic dataset replacement requires a new destination or an IRx snapshot dataset");
        previous = std::filesystem::canonical(destination);
        if (previous.parent_path() != versions || !previous.filename().string().starts_with("generation-"))
            return Status::Invalid("destination is not an IRx snapshot dataset");
    } else if (o.append) return Status::Invalid("dataset append requires an existing snapshot");
    auto output = input;
    if (o.append) {
        ARROW_ASSIGN_OR_RAISE(auto old, metadata_schema(fs, (previous / "_common_metadata").string(), o));
        if (!o.unify && !old->Equals(*input, true)) return Status::TypeError("dataset append requires exact schema or unify=true");
        if (o.unify) {
            for (const auto &side : {old, input}) for (const auto &field : side->fields()) {
                auto other = (side == old ? input : old)->GetFieldByName(field->name());
                if (!other && !field->nullable()) return Status::TypeError("missing dataset column must be nullable: ", field->name());
                if (other && !other->Equals(field, true)) return Status::TypeError("dataset evolution cannot change an existing field: ", field->name());
            }
            if ((old->metadata() == nullptr) != (input->metadata() == nullptr) ||
                (old->metadata() && !old->metadata()->Equals(*input->metadata())))
                return Status::TypeError("dataset evolution cannot change schema metadata");
            ARROW_ASSIGN_OR_RAISE(output, arrow::UnifySchemas({old, input}));
        }
    }
    if (std::filesystem::is_symlink(versions)) return Status::Invalid("snapshot storage must not be a symbolic link");
    std::filesystem::create_directories(versions);
    std::string pattern = (versions / "generation-XXXXXX").string();
    if (!::mkdtemp(pattern.data())) return Status::IOError("cannot create dataset generation");
    std::filesystem::path generation(pattern);
    struct Guard {
        std::filesystem::path path; bool transferred{false};
        ~Guard() { if (!transferred) { std::error_code ignored; std::filesystem::remove_all(path, ignored); } }
    } guard{generation};
    if (o.append) {
        // Immutable fragments are shared; metadata is regenerated, never modified
        // through a hard link. Old generations remain valid for pinned readers.
        for (const auto &entry : std::filesystem::recursive_directory_iterator(previous)) {
            auto relative = entry.path().lexically_relative(previous);
            if (entry.is_symlink()) return Status::Invalid("snapshot fragments cannot be symbolic links");
            if (entry.is_directory()) std::filesystem::create_directories(generation / relative);
            else if (relative != "_common_metadata") std::filesystem::create_hard_link(entry.path(), generation / relative);
        }
        // Initialize the new schema before the inner append session opens.
        auto metadata_options = o;
        metadata_options.dataset = metadata_options.hive = metadata_options.atomic = false;
        metadata_options.append = metadata_options.unify = metadata_options.durable = false;
        metadata_options.partition_columns.clear();
        ARROW_ASSIGN_OR_RAISE(auto metadata, parquet_writer((generation / "_common_metadata").c_str(), output,
            o.compression.c_str(), o.row_group_size, &metadata_options));
        ARROW_RETURN_NOT_OK(metadata->Close());
    } else std::filesystem::remove(generation);
    auto inner_options = o;
    inner_options.atomic = inner_options.durable = inner_options.unify = false;
    ARROW_ASSIGN_OR_RAISE(auto writer, parquet_writer(generation.c_str(), output,
        o.compression.c_str(), o.row_group_size, &inner_options));
    guard.transferred = true;
    return std::make_shared<SnapshotWriter>(writer, input, output, generation, destination, lease, o.durable);
#endif
}

class ParquetWriter final : public BatchWriter {
 public:
    ParquetWriter(std::shared_ptr<arrow::io::OutputStream> sink,
                  std::unique_ptr<parquet::arrow::FileWriter> writer,
                  std::shared_ptr<arrow::Schema> physical,
                  std::string temporary, std::string destination,
                  std::shared_ptr<LocalWriteLease> lease, bool durable)
        : sink_(std::move(sink)), writer_(std::move(writer)), physical_(std::move(physical)),
          temporary_(std::move(temporary)), destination_(std::move(destination)),
          lease_(std::move(lease)), durable_(durable) {}
    ~ParquetWriter() override { Abandon(); }
    Status WriteRecordBatch(const arrow::RecordBatch &batch) override {
        if (!failure_.ok()) return failure_;
        if (closed_) return Status::Invalid("Parquet writer is closed");
        try {
            auto prepared = prepare_batch(batch, physical_);
            if (!prepared.ok()) return failure_ = prepared.status();
            if (batch.num_rows()) failure_ = writer_->WriteRecordBatch(**prepared);
        } catch (const std::exception &error) { failure_ = Status::IOError("Parquet write: ", error.what()); }
        return failure_;
    }
    Status Close() override {
        if (closed_) return failure_;
        closed_ = true;
        try {
            if (failure_.ok()) failure_ = writer_->Close();
            writer_.reset();
            auto status = sink_->Close();
            if (failure_.ok()) failure_ = status;
            if (failure_.ok() && durable_) failure_ = sync_local_path(temporary_, false);
            if (failure_.ok() && !temporary_.empty()) {
                std::error_code error;
                std::filesystem::rename(temporary_, destination_, error);
                if (error) failure_ = Status::IOError("atomic Parquet replacement failed: ", error.message());
                else {
                    temporary_.clear();
                    if (durable_) failure_ = sync_local_path(std::filesystem::path(destination_).parent_path(), true);
                }
            }
        } catch (const std::exception &error) {
            if (failure_.ok()) failure_ = Status::IOError("Parquet close: ", error.what());
        }
        cleanup();
        return failure_;
    }
    void Invalidate(const Status &status) override {
        if (failure_.ok()) failure_ = status;
        Abandon();
    }
    void Abandon() override {
        // Release/exception unwinding must never commit an atomic replacement.
        if (!closed_) {
            closed_ = true;
            try { if (sink_) (void)sink_->Close(); }
            catch (const std::exception &) { /* Best-effort cancellation only. */ }
            writer_.reset();
        }
        cleanup();
    }
 private:
    void cleanup() {
        if (!temporary_.empty()) {
            std::error_code ignored;
            std::filesystem::remove(temporary_, ignored);
            temporary_.clear();
        }
        lease_.reset();
    }
    std::shared_ptr<arrow::io::OutputStream> sink_;
    std::unique_ptr<parquet::arrow::FileWriter> writer_;
    std::shared_ptr<arrow::Schema> physical_;
    std::string temporary_, destination_;
    std::shared_ptr<LocalWriteLease> lease_;
    bool durable_;
    bool closed_{false};
    Status failure_;
};
} // namespace

arrow::Result<std::shared_ptr<arrow::RecordBatchReader>> parquet_reader(
    const char *path, const std::shared_ptr<arrow::Schema> &expected,
    int64_t batch_size, const IrxParquetOptions *options) {
    IrxParquetOptions o = options ? *options : IrxParquetOptions{};
    o.batch_size = batch_size;
    if (batch_size <= 0) return Status::Invalid("Parquet batch_size must be positive");
    if (o.atomic || o.durable || o.reconstruct || o.append || o.normalize || !o.partition_columns.empty() ||
        o.compression != "snappy" || o.compression_level || o.row_group_size != 1048576 || o.data_page_size != 1048576)
        return Status::Invalid("write-only Parquet options supplied to a reader");
    if ((o.hive || o.unify) && !o.dataset) return Status::Invalid("hive/unify require dataset=true");
    std::string fs_path;
    ARROW_ASSIGN_OR_RAISE(auto fs, arrow::fs::FileSystemFromUriOrPath(
        std::string_view(path).find("://") == std::string_view::npos
            ? std::filesystem::absolute(path).string() : std::string(path), &fs_path));
    std::shared_ptr<arrow::RecordBatchReader> result;
    // Pin one committed generation before discovering fragments. A later commit
    // changes only the public symlink; this reader keeps its original snapshot.
    if (o.dataset && fs->type_name() == "local")
        fs_path = std::filesystem::canonical(fs_path).string();
    if (o.dataset || !o.columns.empty() || !o.predicates.empty()) {
        ARROW_ASSIGN_OR_RAISE(auto reader, scan_reader(fs, fs_path, o));
        result = std::make_shared<OwnedReader>(reader);
    } else {
        ARROW_ASSIGN_OR_RAISE(auto source, fs->OpenInputFile(fs_path));
        parquet::ArrowReaderProperties properties;
        properties.set_use_threads(o.use_threads);
        properties.set_pre_buffer(o.pre_buffer);
        properties.set_arrow_extensions_enabled(true);
        parquet::arrow::FileReaderBuilder builder;
        ARROW_RETURN_NOT_OK(builder.Open(source, reader_properties(o)));
        builder.properties(properties);
        ARROW_ASSIGN_OR_RAISE(auto file, builder.Build());
        file->set_batch_size(batch_size);
        std::vector<int> groups = o.row_groups;
        if (groups.empty()) { groups.resize(file->num_row_groups()); std::iota(groups.begin(), groups.end(), 0); }
        for (int group : groups) if (group < 0 || group >= file->num_row_groups()) return Status::IndexError("Parquet row group out of range");
        ARROW_ASSIGN_OR_RAISE(auto reader, file->GetRecordBatchReader(groups));
        result = std::make_shared<OwnedReader>(std::move(reader), source, std::move(file));
    }
    bool reconstruct = result->schema()->metadata() && result->schema()->metadata()->Contains(logical_schema_key);
    ARROW_ASSIGN_OR_RAISE(result, restore_reader(result));
    ARROW_RETURN_NOT_OK(physical_schema(result->schema(), false, false, reconstruct).status());
    if (expected && !expected->Equals(*result->schema(), true))
        return Status::TypeError("Parquet schema mismatch (names/order/types/metadata/nullability); expected schema is an assertion, not a conversion");
    return result;
}

arrow::Result<std::shared_ptr<BatchWriter>> parquet_writer(
    const char *path, const std::shared_ptr<arrow::Schema> &schema,
    const char *compression, int64_t row_group_size, const IrxParquetOptions *options) {
    IrxParquetOptions o = options ? *options : IrxParquetOptions{};
    if (!o.columns.empty() || !o.predicates.empty() || !o.row_groups.empty() || o.pre_buffer)
        return Status::Invalid("read-only Parquet options supplied to a writer");
    if (o.unify && !(o.dataset && o.atomic && o.append))
        return Status::Invalid("write-time unify requires an atomic dataset append");
    if (o.hive && !o.dataset) return Status::Invalid("hive requires dataset=true");
    if (o.durable && !o.atomic && !o.append) return Status::Invalid("durable requires atomic=true or append=true");
    ARROW_ASSIGN_OR_RAISE(auto physical, physical_schema(schema, true, o.normalize, o.reconstruct, true));
    if (o.reconstruct) {
        if (o.dataset) return Status::NotImplemented("explicit schema reconstruction currently targets single files");
        ARROW_RETURN_NOT_OK(cp::Initialize());
        ARROW_ASSIGN_OR_RAISE(auto logical, physical_schema(schema, true, o.normalize, true));
        ARROW_ASSIGN_OR_RAISE(auto encoded, arrow::ipc::SerializeSchema(*logical));
        auto metadata = physical->metadata() ? physical->metadata()->Copy() : arrow::key_value_metadata({}, {});
        ARROW_RETURN_NOT_OK(metadata->Set(logical_schema_key, encoded->ToString()));
        physical = physical->WithMetadata(metadata);
    }
    if (row_group_size <= 0 || o.data_page_size <= 0) return Status::Invalid("Parquet sizes must be positive");
    if (o.normalize) ARROW_RETURN_NOT_OK(cp::Initialize());
    ARROW_ASSIGN_OR_RAISE(auto codec, arrow::util::Codec::GetCompressionType(compression));
    if (codec != arrow::Compression::UNCOMPRESSED && codec != arrow::Compression::SNAPPY &&
        codec != arrow::Compression::ZSTD && codec != arrow::Compression::GZIP &&
        codec != arrow::Compression::BROTLI && codec != arrow::Compression::LZ4)
        return Status::Invalid("unsupported Parquet compression codec");
    if (!arrow::util::Codec::IsAvailable(codec)) return Status::NotImplemented("Parquet codec unavailable");
    if (o.compression_level) {
        if (!arrow::util::Codec::SupportsCompressionLevel(codec)) return Status::Invalid("codec does not support compression_level");
        ARROW_ASSIGN_OR_RAISE(auto min, arrow::util::Codec::MinimumCompressionLevel(codec));
        ARROW_ASSIGN_OR_RAISE(auto max, arrow::util::Codec::MaximumCompressionLevel(codec));
        if (*o.compression_level < min || *o.compression_level > max) return Status::Invalid("compression_level out of codec range");
    }
    parquet::WriterProperties::Builder properties;
    properties.version(parquet::ParquetVersion::PARQUET_2_6)->compression(codec)
        ->max_row_group_length(row_group_size)->data_pagesize(o.data_page_size);
    if (o.compression_level) properties.compression_level(*o.compression_level);
    if (!o.key.empty()) properties.encryption(parquet::FileEncryptionProperties::Builder(o.key).build());
    auto arrow_properties = parquet::ArrowWriterProperties::Builder()
        .store_schema()->disable_deprecated_int96_timestamps()->disallow_truncated_timestamps()
        ->disable_compliant_nested_types()->set_use_threads(o.use_threads)->build();
    std::string fs_path;
    ARROW_ASSIGN_OR_RAISE(auto fs, arrow::fs::FileSystemFromUriOrPath(
        std::string_view(path).find("://") == std::string_view::npos
            ? std::filesystem::absolute(path).string() : std::string(path), &fs_path));
    if (o.dataset) {
        if (!o.hive || o.partition_columns.empty()) return Status::Invalid("dataset output requires hive=true and partition_columns");
        if (o.durable && !o.atomic) return Status::Invalid("durable dataset writes require atomic=true");
        if (o.atomic) return snapshot_writer(fs, fs_path, physical, o);
        if (fs->type_name() == "local" && std::filesystem::is_symlink(fs_path))
            return Status::Invalid("snapshot datasets require atomic=true for every write");
        if (o.partition_columns.size() >= static_cast<size_t>(physical->num_fields()))
            return Status::Invalid("dataset output needs at least one non-partition column");
        ARROW_RETURN_NOT_OK(cp::Initialize());
        arrow::FieldVector partition_fields;
        for (const auto &name : o.partition_columns) {
            if (name.find_first_of("/\\=%") != std::string::npos)
                return Status::Invalid("Hive partition column names cannot contain /, backslash, = or %: ", name);
            auto field = physical->GetFieldByName(name);
            if (!field) return Status::Invalid("unknown partition column: ", name);
            if (field->type()->id() != arrow::Type::STRING &&
                field->type()->id() != arrow::Type::BOOL &&
                field->type()->id() != arrow::Type::DATE32 &&
                field->type()->id() != arrow::Type::TIME32 &&
                field->type()->id() != arrow::Type::TIME64 &&
                field->type()->id() != arrow::Type::TIMESTAMP &&
                !arrow::is_integer(field->type()->id()))
                return Status::TypeError("partition columns must be strings, integers, Boolean, date32, time or timestamp");
            partition_fields.push_back(field);
        }
        std::shared_ptr<LocalWriteLease> lease;
        if (fs->type_name() == "local") { ARROW_ASSIGN_OR_RAISE(lease, LocalWriteLease::Acquire(fs_path)); }
        ARROW_ASSIGN_OR_RAISE(auto info, fs->GetFileInfo(fs_path));
        if (!o.append && info.type() != arrow::fs::FileType::NotFound)
            return Status::Invalid("dataset destination exists; use append=true for new fragments");
        if (o.append && info.type() != arrow::fs::FileType::NotFound && info.type() != arrow::fs::FileType::Directory)
            return Status::Invalid("dataset destination is not a directory");
        const std::string metadata_path = fs_path + "/_common_metadata";
        if (info.type() != arrow::fs::FileType::NotFound) {
            // Our schema-only footer records original partition types and a
            // stable append contract. External datasets can be read/unified,
            // but append must not guess their intended partition types.
            ARROW_ASSIGN_OR_RAISE(auto previous, metadata_schema(fs, metadata_path, o));
            if (!previous->Equals(*physical, true)) return Status::TypeError("dataset append requires exact schema including partition types and metadata");
        } else {
            ARROW_RETURN_NOT_OK(fs->CreateDir(fs_path, true));
            ARROW_ASSIGN_OR_RAISE(auto sink, fs->OpenOutputStream(metadata_path));
            ARROW_ASSIGN_OR_RAISE(auto metadata, parquet::arrow::FileWriter::Open(
                *physical, arrow::default_memory_pool(), sink, properties.build(), arrow_properties));
            ARROW_RETURN_NOT_OK(metadata->Close());
            ARROW_RETURN_NOT_OK(sink->Close());
        }
        std::shared_ptr<ds::ParquetFileFormat> format = o.key.empty()
            ? std::make_shared<ds::ParquetFileFormat>() : std::make_shared<KeyedParquetFormat>(o.key);
        auto write_options = std::static_pointer_cast<ds::ParquetFileWriteOptions>(format->DefaultWriteOptions());
        write_options->writer_properties = properties.build();
        write_options->arrow_writer_properties = arrow_properties;
        ds::FileSystemDatasetWriteOptions write;
        write.file_write_options = write_options;
        write.filesystem = fs;
        write.base_dir = fs_path;
        write.partitioning = std::make_shared<ds::HivePartitioning>(arrow::schema(partition_fields));
        write.max_rows_per_group = row_group_size;
        write.preserve_order = true;
        write.existing_data_behavior = ds::ExistingDataBehavior::kOverwriteOrIgnore;
        return std::make_shared<DatasetWriter>(write, physical, o.use_threads, lease);
    }
    if (!o.partition_columns.empty()) return Status::Invalid("partition_columns require dataset=true");
    const bool atomic = o.atomic || o.append;
    if (atomic && fs->type_name() != "local") return Status::NotImplemented("atomic replacement and rewrite append require a local filesystem");
    std::shared_ptr<LocalWriteLease> lease;
    if (fs->type_name() == "local") {
        ARROW_ASSIGN_OR_RAISE(lease, LocalWriteLease::Acquire(fs_path));
        if (std::filesystem::is_symlink(fs_path))
            return Status::Invalid("Parquet file output must not be a symbolic link");
    }
    std::shared_ptr<arrow::RecordBatchReader> existing;
    if (o.append) {
        // Check before creating output. Append means rewrite+replace, never
        // concatenating Parquet footers. Hold the lease before reading old data.
        IrxParquetOptions read;
        read.key = o.key;
        auto expected = physical;
        if (o.reconstruct) {
            ARROW_ASSIGN_OR_RAISE(expected, physical_schema(schema, true, o.normalize, true));
        }
        ARROW_ASSIGN_OR_RAISE(existing, parquet_reader(path, expected, o.batch_size, &read));
    }
    std::string temporary;
    struct TemporaryGuard {
        std::string &path;
        bool transferred{false};
        ~TemporaryGuard() {
            if (!transferred && !path.empty()) { std::error_code ignored; std::filesystem::remove(path, ignored); }
        }
    } guard{temporary};
    std::shared_ptr<arrow::io::OutputStream> sink;
    if (atomic) {
#ifdef _WIN32
        return Status::NotImplemented("atomic Parquet replacement is currently POSIX-only");
#else
        std::string pattern = fs_path + ".irx-XXXXXX";
        int fd = mkstemp(pattern.data());
        if (fd < 0) return Status::IOError("cannot create sibling Parquet temporary file");
        temporary = pattern;
        auto opened = arrow::io::FileOutputStream::Open(fd);
        if (!opened.ok()) { ::close(fd); std::filesystem::remove(temporary); return opened.status(); }
        sink = *opened;
#endif
    } else { ARROW_ASSIGN_OR_RAISE(sink, fs->OpenOutputStream(fs_path)); }
    auto opened = parquet::arrow::FileWriter::Open(*physical, arrow::default_memory_pool(), sink, properties.build(), arrow_properties);
    if (!opened.ok()) {
        (void)sink->Close();
        if (!temporary.empty()) std::filesystem::remove(temporary);
        return opened.status();
    }
    auto writer = std::make_shared<ParquetWriter>(sink, std::move(*opened), physical, temporary, fs_path, lease, o.durable);
    guard.transferred = true;
    if (existing) {
        while (true) {
            std::shared_ptr<arrow::RecordBatch> batch;
            ARROW_RETURN_NOT_OK(existing->ReadNext(&batch));
            if (!batch) break;
            ARROW_RETURN_NOT_OK(writer->WriteRecordBatch(*batch));
        }
        ARROW_RETURN_NOT_OK(existing->Close());
    }
    return writer;
}
} // namespace irx
