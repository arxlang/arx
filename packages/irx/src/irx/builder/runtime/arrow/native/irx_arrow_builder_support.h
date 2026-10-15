// Copyright IRx contributors.
#ifndef IRX_ARROW_BUILDER_SUPPORT_H_INCLUDED
#define IRX_ARROW_BUILDER_SUPPORT_H_INCLUDED

#include <arrow/api.h>
#include <arrow/util/bit_util.h>

#include <cstdlib>
#include <cstring>
#include <limits>
#include <memory>
#include <type_traits>

namespace irx_arrow_internal {

#if defined(IRX_ARROW_ENABLE_TEST_FAILURES)
// Per-thread and reset at each ABI operation. Never present in production.
inline thread_local int64_t pool_allocations_before_failure = -1;

inline void reset_pool_failure() {
  const char* setting = std::getenv("IRX_ARROW_TEST_FAIL_POOL_ALLOCATION");
  pool_allocations_before_failure = -1;
  if (setting == nullptr || *setting == '\0') return;
  char* end = nullptr;
  const long long value = std::strtoll(setting, &end, 10);
  if (*end == '\0' && value >= 0) pool_allocations_before_failure = value;
}

inline bool fail_pool_allocation() {
  if (pool_allocations_before_failure < 0) return false;
  return pool_allocations_before_failure-- == 0;
}

class FailureMemoryPool final : public arrow::ProxyMemoryPool {
 public:
  FailureMemoryPool() : arrow::ProxyMemoryPool(arrow::default_memory_pool()) {}

  arrow::Status Allocate(int64_t size, int64_t alignment,
                         uint8_t** out) override {
    if (fail_pool_allocation()) {
      return arrow::Status::OutOfMemory(
          "injected Arrow pool allocation failure");
    }
    return arrow::ProxyMemoryPool::Allocate(size, alignment, out);
  }

  arrow::Status Reallocate(int64_t old_size, int64_t new_size,
                           int64_t alignment, uint8_t** pointer) override {
    if (fail_pool_allocation()) {
      // The original allocation must remain untouched on failure.
      return arrow::Status::OutOfMemory(
          "injected Arrow pool reallocation failure");
    }
    return arrow::ProxyMemoryPool::Reallocate(old_size, new_size, alignment,
                                              pointer);
  }
};

inline arrow::MemoryPool* builder_memory_pool() {
  static FailureMemoryPool pool;
  return &pool;
}
#else
inline void reset_pool_failure() {}
inline arrow::MemoryPool* builder_memory_pool() {
  return arrow::default_memory_pool();
}
#endif

// Arrow's ordinary Finish can move one buffer before another allocation fails.
// Our consuming ABI instead snapshots primitive buffers and only destroys the
// original builder after the entire result is published. This deliberately
// trades one bounded copy at finish for retry safety; no per-append copy.
template <typename Builder>
class SnapshotPrimitiveBuilder final : public Builder {
 public:
  explicit SnapshotPrimitiveBuilder(arrow::MemoryPool* pool) : Builder(pool) {}

  arrow::Status Resize(int64_t capacity) override {
    const int64_t original_capacity = this->capacity_;
    try {
      auto status = Builder::Resize(capacity);
      // Arrow can update capacity_ before allocating the validity bitmap.
      // A retry must re-enter Resize, not UnsafeAppend into a missing bitmap.
      if (!status.ok()) this->capacity_ = original_capacity;
      return status;
    } catch (...) {
      this->capacity_ = original_capacity;
      throw;
    }
  }

  arrow::Status FinishInternal(
      std::shared_ptr<arrow::ArrayData>* out) override {
    constexpr int64_t kWidth = sizeof(typename Builder::value_type);
    constexpr bool kBoolean =
        std::is_same_v<typename Builder::value_type, bool>;
    const int64_t length = this->length();
    if (!kBoolean && length > std::numeric_limits<int64_t>::max() / kWidth) {
      return arrow::Status::CapacityError("primitive snapshot size overflow");
    }
    const int64_t size =
        kBoolean ? arrow::bit_util::BytesForBits(length) : length * kWidth;
    ARROW_ASSIGN_OR_RAISE(auto data, arrow::AllocateBuffer(size, this->pool_));
    if (size != 0) {
      std::memcpy(data->mutable_data(), this->data_builder_.data(), size);
    }
    data->ZeroPadding();
    std::shared_ptr<arrow::Buffer> validity;
    if (this->null_count() != 0) {
      const int64_t bitmap_size = arrow::bit_util::BytesForBits(length);
      ARROW_ASSIGN_OR_RAISE(validity,
                            arrow::AllocateBuffer(bitmap_size, this->pool_));
      std::memcpy(validity->mutable_data(), this->null_bitmap_builder_.data(),
                  bitmap_size);
      validity->ZeroPadding();
    }
    *out = arrow::ArrayData::Make(this->type(), length,
                                  {std::move(validity), std::move(data)},
                                  this->null_count());
    return arrow::Status::OK();
  }
};

inline std::unique_ptr<arrow::ArrayBuilder> make_snapshot_builder(
    arrow::Type::type type) {
  arrow::MemoryPool* pool = builder_memory_pool();
#define IRX_SNAPSHOT_BUILDER(id, name) \
  case arrow::Type::id:                \
    return std::make_unique<SnapshotPrimitiveBuilder<arrow::name>>(pool)
  switch (type) {
    IRX_SNAPSHOT_BUILDER(INT8, Int8Builder);
    IRX_SNAPSHOT_BUILDER(INT16, Int16Builder);
    IRX_SNAPSHOT_BUILDER(INT32, Int32Builder);
    IRX_SNAPSHOT_BUILDER(INT64, Int64Builder);
    IRX_SNAPSHOT_BUILDER(UINT8, UInt8Builder);
    IRX_SNAPSHOT_BUILDER(UINT16, UInt16Builder);
    IRX_SNAPSHOT_BUILDER(UINT32, UInt32Builder);
    IRX_SNAPSHOT_BUILDER(UINT64, UInt64Builder);
    IRX_SNAPSHOT_BUILDER(HALF_FLOAT, HalfFloatBuilder);
    IRX_SNAPSHOT_BUILDER(FLOAT, FloatBuilder);
    IRX_SNAPSHOT_BUILDER(DOUBLE, DoubleBuilder);
    IRX_SNAPSHOT_BUILDER(BOOL, BooleanBuilder);
    default:
      return nullptr;
  }
#undef IRX_SNAPSHOT_BUILDER
}

}  // namespace irx_arrow_internal
#endif
