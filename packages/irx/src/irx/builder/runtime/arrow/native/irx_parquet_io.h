// Copyright IRx contributors.
#ifndef IRX_PARQUET_IO_H
#define IRX_PARQUET_IO_H

#include "irx_batch_writer.h"
#include <arrow/result.h>

namespace irx {
arrow::Result<std::shared_ptr<arrow::RecordBatchReader>> parquet_reader(
    const char *path, const std::shared_ptr<arrow::Schema> &expected,
    int64_t batch_size);
arrow::Result<std::shared_ptr<BatchWriter>> parquet_writer(
    const char *path, const std::shared_ptr<arrow::Schema> &schema,
    const char *compression, int64_t row_group_size);
} // namespace irx
#endif
