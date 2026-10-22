// Copyright IRx contributors.
#ifndef IRX_BATCH_WRITER_H
#define IRX_BATCH_WRITER_H

#include <arrow/ipc/writer.h>
#include <arrow/record_batch.h>
#include <memory>

namespace irx {
// The shared handle needs only these operations, not IPC-specific statistics.
class BatchWriter {
 public:
    virtual ~BatchWriter() = default;
    virtual arrow::Status WriteRecordBatch(const arrow::RecordBatch &batch) = 0;
    virtual arrow::Status Close() = 0;
};

class IpcBatchWriter final : public BatchWriter {
 public:
    explicit IpcBatchWriter(std::shared_ptr<arrow::ipc::RecordBatchWriter> writer)
        : writer_(std::move(writer)) {}
    arrow::Status WriteRecordBatch(const arrow::RecordBatch &batch) override {
        return writer_->WriteRecordBatch(batch);
    }
    arrow::Status Close() override { return writer_->Close(); }
 private:
    std::shared_ptr<arrow::ipc::RecordBatchWriter> writer_;
};
} // namespace irx
#endif
