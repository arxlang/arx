// Copyright IRx contributors.

#ifndef IRX_ARROW_RUNTIME_INTERNAL_H_INCLUDED
#define IRX_ARROW_RUNTIME_INTERNAL_H_INCLUDED

#include "irx_arrow_runtime.h"

#include <arrow/api.h>

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <memory>

namespace irx_arrow_internal {

inline constexpr int64_t kInitialRefcount = 1;
inline constexpr uint64_t kHandleMagic = UINT64_C(0x4952584152524f57);
inline constexpr std::size_t kErrorOperationCapacity = 128;
inline constexpr std::size_t kErrorMessageCapacity = 512;
inline constexpr std::size_t kErrorUpstreamDetailCapacity = 512;

struct ErrorDetail {
  irx_arrow_status code = IRX_ARROW_STATUS_OK;
  char operation[kErrorOperationCapacity] = {0};
  char message[kErrorMessageCapacity] = {0};
  char upstream_detail[kErrorUpstreamDetailCapacity] = {0};
};

extern thread_local ErrorDetail current_error;

struct HandleHeader {
  HandleHeader(
      irx_arrow_handle_kind handle_kind,
      irx_arrow_handle_ownership handle_ownership)
      : magic(kHandleMagic),
        kind(handle_kind),
        ownership(handle_ownership),
        refcount(kInitialRefcount) {}

  uint64_t magic;
  irx_arrow_handle_kind kind;
  irx_arrow_handle_ownership ownership;
  mutable std::atomic<int64_t> refcount;
};

}  // namespace irx_arrow_internal

extern "C" void irx_internal_arrow_register_linked_feature(
    irx_arrow_runtime_feature_id feature_id,
    uint32_t contract_version);

struct irx_arrow_record_batch_handle {
  irx_arrow_internal::HandleHeader header{
      IRX_ARROW_HANDLE_KIND_RECORD_BATCH,
      IRX_ARROW_HANDLE_OWNERSHIP_SHARED};
  std::shared_ptr<arrow::RecordBatch> batch;
};

#endif
