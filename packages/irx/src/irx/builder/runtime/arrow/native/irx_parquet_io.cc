// Copyright IRx contributors.
#include "irx_parquet_io.h"

#include <arrow/api.h>
#include <arrow/io/api.h>
#include <arrow/util/compression.h>
#include <arrow/util/key_value_metadata.h>
#include <arrow/util/utf8.h>
#include <parquet/arrow/reader.h>
#include <parquet/arrow/writer.h>
#include <parquet/properties.h>
#include <string_view>
#include <unordered_set>

namespace irx {
namespace {
arrow::Status parquet_schema(const arrow::Schema &schema, bool writing) {
    if (!schema.num_fields())
        return arrow::Status::Invalid("Parquet requires at least one column");
    if (writing && schema.metadata() && schema.metadata()->Contains("ARROW:schema"))
        return arrow::Status::Invalid("Parquet reserves the ARROW:schema metadata key");
    std::unordered_set<std::string> names;
    for (const auto &field : schema.fields()) {
        const auto &name = field->name();
        if (name.empty() || name.find('\0') != std::string::npos ||
            !arrow::util::ValidateUTF8(name) || !names.insert(name).second)
            return arrow::Status::Invalid("Parquet requires unique nonempty UTF-8 column names: '", name, "'");
        const auto &type = *field->type();
        switch (type.id()) {
        case arrow::Type::INT8: case arrow::Type::INT16:
        case arrow::Type::INT32: case arrow::Type::INT64:
        case arrow::Type::UINT8: case arrow::Type::UINT16:
        case arrow::Type::UINT32: case arrow::Type::UINT64:
        case arrow::Type::FLOAT: case arrow::Type::DOUBLE:
        case arrow::Type::BOOL: case arrow::Type::STRING:
        case arrow::Type::LARGE_STRING: case arrow::Type::DATE32:
        case arrow::Type::TIME64:
            continue;
        case arrow::Type::TIMESTAMP:
            if (static_cast<const arrow::TimestampType &>(type).unit() != arrow::TimeUnit::SECOND)
                continue;
            break;
        case arrow::Type::TIME32:
            if (static_cast<const arrow::Time32Type &>(type).unit() == arrow::TimeUnit::MILLI)
                continue;
            break;
        default: break;
        }
        return arrow::Status::TypeError("Unsupported Parquet column '", name, "' (",
            type.ToString(), "); convert explicitly to a supported type or use IPC; implicit coercion is disabled");
    }
    return arrow::Status::OK();
}

class ParquetReader final : public arrow::RecordBatchReader {
 public:
    ParquetReader(std::shared_ptr<arrow::io::RandomAccessFile> source,
                  std::unique_ptr<parquet::arrow::FileReader> file,
                  std::unique_ptr<arrow::RecordBatchReader> reader,
                  std::shared_ptr<arrow::Schema> schema)
        : source_(std::move(source)), file_(std::move(file)),
          reader_(std::move(reader)), schema_(std::move(schema)) {}
    std::shared_ptr<arrow::Schema> schema() const override { return schema_; }
    arrow::Status ReadNext(std::shared_ptr<arrow::RecordBatch> *out) override {
        *out = nullptr;
        if (!failure_.ok()) return failure_;
        if (!reader_) return arrow::Status::Invalid("Parquet reader is closed");
        try {
            failure_ = reader_->ReadNext(out);
        } catch (const std::exception &error) {
            failure_ = arrow::Status::IOError("Parquet read: ", error.what());
        }
        if (!failure_.ok()) *out = nullptr;
        return failure_;
    }
    arrow::Status Close() override {
        try {
            auto status = reader_ ? reader_->Close() : arrow::Status::OK();
            reader_.reset();
            file_.reset();
            auto closed = source_->Close();
            return status.ok() ? closed : status;
        } catch (const std::exception &error) {
            return arrow::Status::IOError("Parquet reader close: ", error.what());
        }
    }
 private:
    // Destruction order matters, including after an Arrow C stream transfer.
    std::shared_ptr<arrow::io::RandomAccessFile> source_;
    std::unique_ptr<parquet::arrow::FileReader> file_;
    std::unique_ptr<arrow::RecordBatchReader> reader_;
    std::shared_ptr<arrow::Schema> schema_;
    arrow::Status failure_;
};

class ParquetWriter final : public BatchWriter {
 public:
    ParquetWriter(std::shared_ptr<arrow::io::OutputStream> sink,
                  std::unique_ptr<parquet::arrow::FileWriter> writer)
        : sink_(std::move(sink)), writer_(std::move(writer)) {}
    arrow::Status WriteRecordBatch(const arrow::RecordBatch &batch) override {
        if (!failure_.ok()) return failure_;
        if (!writer_) return arrow::Status::Invalid("Parquet writer is closed");
        try {
            for (int i = 0; i < batch.num_columns(); ++i) {
                if (!batch.schema()->field(i)->nullable() && batch.column(i)->null_count())
                    return arrow::Status::Invalid("Parquet column '", batch.schema()->field(i)->name(),
                                                  "' contains nulls but is not nullable");
            }
            if (batch.num_rows()) failure_ = writer_->WriteRecordBatch(batch);
        } catch (const std::exception &error) {
            failure_ = arrow::Status::IOError("Parquet write: ", error.what());
        }
        return failure_;
    }
    arrow::Status Close() override {
        if (closed_) return failure_;
        closed_ = true;
        try {
            // Never repeat a failed footer finalization as a successful close.
            if (failure_.ok()) failure_ = writer_->Close();
            writer_.reset();
            auto status = sink_->Close();
            if (failure_.ok()) failure_ = status;
        } catch (const std::exception &error) {
            if (failure_.ok()) failure_ = arrow::Status::IOError("Parquet close: ", error.what());
        }
        return failure_;
    }
 private:
    std::shared_ptr<arrow::io::OutputStream> sink_;
    std::unique_ptr<parquet::arrow::FileWriter> writer_;
    bool closed_{false};
    arrow::Status failure_;
};
} // namespace

arrow::Result<std::shared_ptr<arrow::RecordBatchReader>> parquet_reader(
    const char *path, const std::shared_ptr<arrow::Schema> &expected,
    int64_t batch_size) {
    if (batch_size <= 0) return arrow::Status::Invalid("Parquet batch_size must be positive");
    if (expected) ARROW_RETURN_NOT_OK(parquet_schema(*expected, false));
    ARROW_ASSIGN_OR_RAISE(auto source, arrow::io::ReadableFile::Open(path));
    parquet::ArrowReaderProperties properties;
    properties.set_use_threads(false);
    properties.set_pre_buffer(false);
    properties.set_arrow_extensions_enabled(true);
    parquet::arrow::FileReaderBuilder builder;
    ARROW_RETURN_NOT_OK(builder.Open(source));
    builder.properties(properties);
    ARROW_ASSIGN_OR_RAISE(auto file, builder.Build());
    file->set_batch_size(batch_size);
    std::shared_ptr<arrow::Schema> schema;
    ARROW_RETURN_NOT_OK(file->GetSchema(&schema));
    ARROW_RETURN_NOT_OK(parquet_schema(*schema, false));
    if (expected && !expected->Equals(*schema, true))
        return arrow::Status::TypeError("Parquet schema mismatch (names/order/types/metadata/nullability); expected schema is an assertion, not a conversion");
    ARROW_ASSIGN_OR_RAISE(auto reader, file->GetRecordBatchReader());
    return std::make_shared<ParquetReader>(source, std::move(file), std::move(reader), schema);
}

arrow::Result<std::shared_ptr<BatchWriter>> parquet_writer(
    const char *path, const std::shared_ptr<arrow::Schema> &schema,
    const char *compression, int64_t row_group_size) {
    ARROW_RETURN_NOT_OK(parquet_schema(*schema, true));
    if (row_group_size <= 0)
        return arrow::Status::Invalid("Parquet row_group_size must be positive");
    arrow::Compression::type codec;
    std::string_view name(compression);
    if (name == "uncompressed") codec = arrow::Compression::UNCOMPRESSED;
    else if (name == "snappy") codec = arrow::Compression::SNAPPY;
    else if (name == "zstd") codec = arrow::Compression::ZSTD;
    else return arrow::Status::Invalid("Parquet compression must be snappy, uncompressed or zstd");
    if (!arrow::util::Codec::IsAvailable(codec))
        return arrow::Status::NotImplemented("Parquet compression codec unavailable: ", name);
    auto properties = parquet::WriterProperties::Builder()
        .version(parquet::ParquetVersion::PARQUET_2_6)->compression(codec)
        ->max_row_group_length(row_group_size)->build();
    // A fresh builder leaves timestamp coercion disabled.
    auto arrow_properties = parquet::ArrowWriterProperties::Builder()
        .store_schema()->disable_deprecated_int96_timestamps()
        ->disallow_truncated_timestamps()->set_use_threads(false)->build();
    // All option/schema checks precede the destructive open.
    ARROW_ASSIGN_OR_RAISE(auto sink, arrow::io::FileOutputStream::Open(path));
    ARROW_ASSIGN_OR_RAISE(auto writer, parquet::arrow::FileWriter::Open(
        *schema, arrow::default_memory_pool(), sink, properties, arrow_properties));
    return std::make_shared<ParquetWriter>(sink, std::move(writer));
}
} // namespace irx
