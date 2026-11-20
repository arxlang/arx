// Private C++ storage shared by compute and the existing collection bridge.
#ifndef IRX_ARROW_COMMON_H
#define IRX_ARROW_COMMON_H
#include "irx_arrow_compute.h"
#include "irx_arrow_status.h"
#include <arrow/api.h>
#include <arrow/compute/api.h>

struct irx_arrow_chunked_array_handle {
  static constexpr uint64_t tag_value = 0x495258434f4c0001;
  uint64_t tag = tag_value;
  int64_t refcount = 0;
  std::shared_ptr<arrow::ChunkedArray> column;
};

namespace irx {
std::shared_ptr<arrow::Scalar> column_scalar(int32_t type, uint64_t bits, bool valid);
arrow::Status scalar_bits(const arrow::Scalar& scalar, uint64_t* bits, int32_t* valid);
void clear_error();
int set_error(int code, const char* format, ...);
int set_arrow_error(int code, const char* context, const arrow::Status& status);
int set_exception_error(const char* context, const std::exception& error);
arrow::Status initialize_compute();
arrow::Result<arrow::Datum> call_compute(
    const std::string& name, const std::vector<arrow::Datum>& inputs);
}
#endif
