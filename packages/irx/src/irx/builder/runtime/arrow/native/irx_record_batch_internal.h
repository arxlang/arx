// Copyright IRx contributors.
#ifndef IRX_RECORD_BATCH_INTERNAL_H
#define IRX_RECORD_BATCH_INTERNAL_H
#include "irx_record_batch.h"
#include "irx_batch_writer.h"
#include <arrow/type.h>
#include <string>
namespace irx {
int record_batch_error(const std::string &, int code = IRX_ERR_ARROW);
const std::shared_ptr<arrow::Schema> &record_batch_schema(const IrxRbSchema *);
int own_reader(std::shared_ptr<arrow::RecordBatchReader>, IrxRbStreamReader **);
int own_writer(std::shared_ptr<arrow::Schema>, std::shared_ptr<BatchWriter>, IrxRbStreamWriter **);
}
#endif
