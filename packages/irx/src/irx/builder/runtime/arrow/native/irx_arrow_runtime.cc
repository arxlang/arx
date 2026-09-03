// Copyright IRx contributors.

#include "irx_arrow_runtime.h"

#include <arrow/api.h>
#include <arrow/c/bridge.h>
#include <arrow/tensor.h>

#include <stddef.h>
#include <stdint.h>

#include <algorithm>
#include <atomic>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <limits>
#include <memory>
#include <new>
#include <string>
#include <utility>
#include <vector>

namespace {

constexpr irx_arrow_status kArrowOk = IRX_ARROW_STATUS_OK;
constexpr int64_t kInitialRefcount = 1;
constexpr uint64_t kHandleMagic = UINT64_C(0x4952584152524f57);
constexpr int64_t kPrimitiveArrayBufferCount = 2;
constexpr size_t kErrorOperationCapacity = 128;
constexpr size_t kErrorMessageCapacity = 512;
constexpr size_t kErrorUpstreamDetailCapacity = 512;

struct ErrorDetail {
  irx_arrow_status code = IRX_ARROW_STATUS_OK;
  char operation[kErrorOperationCapacity] = {0};
  char message[kErrorMessageCapacity] = {0};
  char upstream_detail[kErrorUpstreamDetailCapacity] = {0};
};

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

thread_local ErrorDetail current_error;

enum class AppendKind {
  kSigned,
  kUnsigned,
  kDouble,
  kBool,
};

struct TypeSpec {
  int32_t type_id;
  arrow::Type::type arrow_type_id;
  uintptr_t dtype_token;
  int64_t element_size_bytes;
  bool buffer_view_compatible;
  AppendKind append_kind;
  const char* name;
  const char* c_data_format;
  std::shared_ptr<arrow::DataType> (*make_type)();
};

std::shared_ptr<arrow::DataType> make_int8_type() { return arrow::int8(); }
std::shared_ptr<arrow::DataType> make_int16_type() { return arrow::int16(); }
std::shared_ptr<arrow::DataType> make_int32_type() { return arrow::int32(); }
std::shared_ptr<arrow::DataType> make_int64_type() { return arrow::int64(); }
std::shared_ptr<arrow::DataType> make_uint8_type() { return arrow::uint8(); }
std::shared_ptr<arrow::DataType> make_uint16_type() { return arrow::uint16(); }
std::shared_ptr<arrow::DataType> make_uint32_type() { return arrow::uint32(); }
std::shared_ptr<arrow::DataType> make_uint64_type() { return arrow::uint64(); }
std::shared_ptr<arrow::DataType> make_float32_type() { return arrow::float32(); }
std::shared_ptr<arrow::DataType> make_float64_type() { return arrow::float64(); }
std::shared_ptr<arrow::DataType> make_bool_type() { return arrow::boolean(); }

const TypeSpec kTypeSpecs[] = {
    {
        IRX_ARROW_TYPE_INT32,
        arrow::Type::INT32,
        IRX_BUFFER_DTYPE_INT32,
        4,
        true,
        AppendKind::kSigned,
        "int32",
        "i",
        make_int32_type,
    },
    {
        IRX_ARROW_TYPE_INT8,
        arrow::Type::INT8,
        IRX_BUFFER_DTYPE_INT8,
        1,
        true,
        AppendKind::kSigned,
        "int8",
        "c",
        make_int8_type,
    },
    {
        IRX_ARROW_TYPE_INT16,
        arrow::Type::INT16,
        IRX_BUFFER_DTYPE_INT16,
        2,
        true,
        AppendKind::kSigned,
        "int16",
        "s",
        make_int16_type,
    },
    {
        IRX_ARROW_TYPE_INT64,
        arrow::Type::INT64,
        IRX_BUFFER_DTYPE_INT64,
        8,
        true,
        AppendKind::kSigned,
        "int64",
        "l",
        make_int64_type,
    },
    {
        IRX_ARROW_TYPE_UINT8,
        arrow::Type::UINT8,
        IRX_BUFFER_DTYPE_UINT8,
        1,
        true,
        AppendKind::kUnsigned,
        "uint8",
        "C",
        make_uint8_type,
    },
    {
        IRX_ARROW_TYPE_UINT16,
        arrow::Type::UINT16,
        IRX_BUFFER_DTYPE_UINT16,
        2,
        true,
        AppendKind::kUnsigned,
        "uint16",
        "S",
        make_uint16_type,
    },
    {
        IRX_ARROW_TYPE_UINT32,
        arrow::Type::UINT32,
        IRX_BUFFER_DTYPE_UINT32,
        4,
        true,
        AppendKind::kUnsigned,
        "uint32",
        "I",
        make_uint32_type,
    },
    {
        IRX_ARROW_TYPE_UINT64,
        arrow::Type::UINT64,
        IRX_BUFFER_DTYPE_UINT64,
        8,
        true,
        AppendKind::kUnsigned,
        "uint64",
        "L",
        make_uint64_type,
    },
    {
        IRX_ARROW_TYPE_FLOAT32,
        arrow::Type::FLOAT,
        IRX_BUFFER_DTYPE_FLOAT32,
        4,
        true,
        AppendKind::kDouble,
        "float32",
        "f",
        make_float32_type,
    },
    {
        IRX_ARROW_TYPE_FLOAT64,
        arrow::Type::DOUBLE,
        IRX_BUFFER_DTYPE_FLOAT64,
        8,
        true,
        AppendKind::kDouble,
        "float64",
        "g",
        make_float64_type,
    },
    {
        IRX_ARROW_TYPE_BOOL,
        arrow::Type::BOOL,
        IRX_BUFFER_DTYPE_BOOL,
        0,
        false,
        AppendKind::kBool,
        "bool",
        "b",
        make_bool_type,
    },
};

struct ResolvedSchema {
  const TypeSpec* spec = nullptr;
  bool nullable = false;
};

}  // namespace

struct irx_arrow_error_handle {
  HandleHeader header{
      IRX_ARROW_HANDLE_KIND_ERROR,
      IRX_ARROW_HANDLE_OWNERSHIP_SHARED};
  ErrorDetail detail;
};

struct irx_arrow_schema_handle {
  HandleHeader header{
      IRX_ARROW_HANDLE_KIND_SCHEMA,
      IRX_ARROW_HANDLE_OWNERSHIP_SHARED};
  std::shared_ptr<arrow::Field> field;
  int32_t type_id = IRX_ARROW_TYPE_UNKNOWN;
  int32_t nullable = 0;
};

struct irx_arrow_array_builder_handle {
  HandleHeader header{
      IRX_ARROW_HANDLE_KIND_ARRAY_BUILDER,
      IRX_ARROW_HANDLE_OWNERSHIP_UNIQUE};
  std::unique_ptr<arrow::ArrayBuilder> builder;
  int32_t type_id = IRX_ARROW_TYPE_UNKNOWN;
};

struct irx_arrow_array_handle {
  HandleHeader header{
      IRX_ARROW_HANDLE_KIND_ARRAY,
      IRX_ARROW_HANDLE_OWNERSHIP_SHARED};
  std::shared_ptr<arrow::Array> array;
  int32_t type_id = IRX_ARROW_TYPE_UNKNOWN;
  int32_t nullable = 0;
  uintptr_t dtype_token = 0;
  int64_t element_size_bytes = 0;
  int32_t buffer_view_compatible = 0;
  int64_t shape[1] = {0};
  int64_t strides[1] = {0};
};

struct irx_arrow_tensor_builder_handle {
  HandleHeader header{
      IRX_ARROW_HANDLE_KIND_TENSOR_BUILDER,
      IRX_ARROW_HANDLE_OWNERSHIP_UNIQUE};
  int32_t type_id = IRX_ARROW_TYPE_UNKNOWN;
  int32_t ndim = 0;
  int64_t element_count = 0;
  int64_t values_appended = 0;
  uintptr_t dtype_token = 0;
  int64_t element_size_bytes = 0;
  std::shared_ptr<arrow::DataType> type;
  std::vector<uint8_t> data;
  std::vector<int64_t> shape;
  std::vector<int64_t> strides;
};

struct irx_arrow_tensor_handle {
  HandleHeader header{
      IRX_ARROW_HANDLE_KIND_TENSOR,
      IRX_ARROW_HANDLE_OWNERSHIP_SHARED};
  std::shared_ptr<arrow::Tensor> tensor;
  std::vector<int64_t> shape_cache;
  std::vector<int64_t> strides_cache;
  int32_t type_id = IRX_ARROW_TYPE_UNKNOWN;
  uintptr_t dtype_token = 0;
  int64_t element_size_bytes = 0;
};

struct irx_arrow_table_handle {
  HandleHeader header{
      IRX_ARROW_HANDLE_KIND_TABLE,
      IRX_ARROW_HANDLE_OWNERSHIP_SHARED};
  std::shared_ptr<arrow::Table> table;
};

struct irx_arrow_chunked_array_handle {
  HandleHeader header{
      IRX_ARROW_HANDLE_KIND_CHUNKED_ARRAY,
      IRX_ARROW_HANDLE_OWNERSHIP_SHARED};
  std::shared_ptr<arrow::ChunkedArray> column;
};

namespace {

bool is_utf8_continuation(unsigned char byte) {
  return (byte & 0xc0U) == 0x80U;
}

size_t valid_utf8_sequence_length(
    const unsigned char* data,
    size_t remaining) {
  const unsigned char lead = data[0];
  if (lead <= 0x7fU) {
    return 1;
  }
  if (lead >= 0xc2U && lead <= 0xdfU && remaining >= 2 &&
      is_utf8_continuation(data[1])) {
    return 2;
  }
  if (remaining >= 3 && lead >= 0xe0U && lead <= 0xefU &&
      is_utf8_continuation(data[2])) {
    const unsigned char second = data[1];
    const bool valid_second =
        (lead == 0xe0U && second >= 0xa0U && second <= 0xbfU) ||
        (lead == 0xedU && second >= 0x80U && second <= 0x9fU) ||
        ((lead >= 0xe1U && lead <= 0xecU) ||
         (lead >= 0xeeU && lead <= 0xefU)) &&
            is_utf8_continuation(second);
    if (valid_second) {
      return 3;
    }
  }
  if (remaining >= 4 && lead >= 0xf0U && lead <= 0xf4U &&
      is_utf8_continuation(data[2]) && is_utf8_continuation(data[3])) {
    const unsigned char second = data[1];
    const bool valid_second =
        (lead == 0xf0U && second >= 0x90U && second <= 0xbfU) ||
        (lead == 0xf4U && second >= 0x80U && second <= 0x8fU) ||
        (lead >= 0xf1U && lead <= 0xf3U &&
         is_utf8_continuation(second));
    if (valid_second) {
      return 4;
    }
  }
  return 0;
}

void sanitize_utf8(char* text) {
  const size_t input_length = std::strlen(text);
  size_t read_offset = 0;
  size_t write_offset = 0;
  while (read_offset < input_length) {
    const auto* current = reinterpret_cast<const unsigned char*>(
        text + read_offset);
    const size_t sequence_length = valid_utf8_sequence_length(
        current,
        input_length - read_offset);
    if (sequence_length == 0) {
      text[write_offset] = '?';
      ++read_offset;
      ++write_offset;
      continue;
    }
    std::memmove(
        text + write_offset,
        text + read_offset,
        sequence_length);
    read_offset += sequence_length;
    write_offset += sequence_length;
  }
  text[write_offset] = '\0';
}

void copy_error_text(char* destination, size_t capacity, const char* source) {
  if (capacity == 0) {
    return;
  }
  std::snprintf(destination, capacity, "%s", source == nullptr ? "" : source);
  sanitize_utf8(destination);
}

void begin_operation(const char* operation) {
  current_error = ErrorDetail{};
  copy_error_text(
      current_error.operation,
      sizeof(current_error.operation),
      operation);
}

irx_arrow_status set_error(irx_arrow_status code, const char* format, ...) {
  current_error.code = code;
  current_error.upstream_detail[0] = '\0';
  va_list args;
  va_start(args, format);
  std::vsnprintf(
      current_error.message,
      sizeof(current_error.message),
      format,
      args);
  va_end(args);
  sanitize_utf8(current_error.message);
  return code;
}

irx_arrow_status status_from_arrow(const arrow::Status& status) {
  if (status.IsInvalid()) {
    return IRX_ARROW_STATUS_INVALID_ARGUMENT;
  }
  if (status.IsTypeError()) {
    return IRX_ARROW_STATUS_TYPE_MISMATCH;
  }
  if (status.IsIndexError()) {
    return IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS;
  }
  if (status.IsCapacityError()) {
    return IRX_ARROW_STATUS_RESOURCE_EXHAUSTED;
  }
  if (status.IsOutOfMemory()) {
    return IRX_ARROW_STATUS_OUT_OF_MEMORY;
  }
  if (status.IsIOError()) {
    return IRX_ARROW_STATUS_IO_ERROR;
  }
  if (status.IsCancelled()) {
    return IRX_ARROW_STATUS_CANCELLED;
  }
  if (status.IsNotImplemented()) {
    return IRX_ARROW_STATUS_NOT_SUPPORTED;
  }
  return IRX_ARROW_STATUS_ARROW_ERROR;
}

irx_arrow_status set_arrow_error(
    const char* context,
    const arrow::Status& status) {
  try {
    const std::string upstream_detail = status.ToString();
    const irx_arrow_status code = set_error(
        status_from_arrow(status),
        "%s: %s",
        context,
        upstream_detail.c_str());
    copy_error_text(
        current_error.upstream_detail,
        sizeof(current_error.upstream_detail),
        upstream_detail.c_str());
    return code;
  } catch (const std::bad_alloc&) {
    return set_error(
        IRX_ARROW_STATUS_OUT_OF_MEMORY,
        "%s: error detail allocation failed",
        context);
  } catch (...) {
    return set_error(
        IRX_ARROW_STATUS_INTERNAL,
        "%s: Arrow error detail conversion failed",
        context);
  }
}

irx_arrow_status set_exception_error(
    const char* context,
    const std::exception&) {
  return set_error(
      IRX_ARROW_STATUS_INTERNAL,
      "%s: C++ exception contained at the Arrow ABI boundary",
      context);
}

template <typename Handle>
irx_arrow_status validate_handle(
    const Handle* handle,
    irx_arrow_handle_kind expected_kind,
    const char* label) {
  if (handle == nullptr) {
    return set_error(
        IRX_ARROW_STATUS_NULL_POINTER,
        "%s handle must not be NULL",
        label);
  }
  if (handle->header.magic != kHandleMagic) {
    return set_error(
        IRX_ARROW_STATUS_INVALID_STATE,
        "%s handle has an invalid runtime marker",
        label);
  }
  if (handle->header.kind != expected_kind) {
    return set_error(
        IRX_ARROW_STATUS_TYPE_MISMATCH,
        "%s handle has kind %d, expected %d",
        label,
        handle->header.kind,
        expected_kind);
  }
  if (handle->header.refcount.load(std::memory_order_acquire) <= 0) {
    return set_error(
        IRX_ARROW_STATUS_INVALID_STATE,
        "%s handle is released",
        label);
  }
  return kArrowOk;
}

template <typename Handle>
irx_arrow_status retain_shared_handle(
    const Handle* handle,
    Handle** out_handle,
    irx_arrow_handle_kind expected_kind,
    const char* label) {
  if (out_handle == nullptr) {
    return set_error(
        IRX_ARROW_STATUS_NULL_POINTER,
        "out_%s must not be NULL",
        label);
  }
  *out_handle = nullptr;

  const irx_arrow_status validation =
      validate_handle(handle, expected_kind, label);
  if (validation != kArrowOk) {
    return validation;
  }
  if (handle->header.ownership != IRX_ARROW_HANDLE_OWNERSHIP_SHARED) {
    return set_error(
        IRX_ARROW_STATUS_NOT_SUPPORTED,
        "%s handle is unique and cannot be retained",
        label);
  }

  auto& refcount = handle->header.refcount;
  int64_t current = refcount.load(std::memory_order_relaxed);
  while (current > 0) {
    if (current == std::numeric_limits<int64_t>::max()) {
      return set_error(
          IRX_ARROW_STATUS_RESOURCE_EXHAUSTED,
          "%s handle reference count overflow",
          label);
    }
    if (refcount.compare_exchange_weak(
            current,
            current + 1,
            std::memory_order_acq_rel,
            std::memory_order_relaxed)) {
      *out_handle = const_cast<Handle*>(handle);
      return kArrowOk;
    }
  }
  return set_error(
      IRX_ARROW_STATUS_INVALID_STATE,
      "%s handle is released",
      label);
}

template <typename Handle>
irx_arrow_status release_shared_handle(
    Handle** handle_slot,
    irx_arrow_handle_kind expected_kind,
    const char* label) {
  if (handle_slot == nullptr) {
    return set_error(
        IRX_ARROW_STATUS_NULL_POINTER,
        "%s handle slot must not be NULL",
        label);
  }
  Handle* handle = *handle_slot;
  if (handle == nullptr) {
    return kArrowOk;
  }

  const irx_arrow_status validation =
      validate_handle(handle, expected_kind, label);
  if (validation != kArrowOk) {
    return validation;
  }
  if (handle->header.ownership != IRX_ARROW_HANDLE_OWNERSHIP_SHARED) {
    return set_error(
        IRX_ARROW_STATUS_INVALID_STATE,
        "%s handle does not use shared ownership",
        label);
  }

  *handle_slot = nullptr;
  const int64_t previous =
      handle->header.refcount.fetch_sub(1, std::memory_order_acq_rel);
  if (previous == 1) {
    handle->header.magic = 0;
    delete handle;
    return kArrowOk;
  }
  if (previous <= 0) {
    return set_error(
        IRX_ARROW_STATUS_INVALID_STATE,
        "%s handle reference count is invalid",
        label);
  }
  return kArrowOk;
}

template <typename Handle>
irx_arrow_status release_unique_handle(
    Handle** handle_slot,
    irx_arrow_handle_kind expected_kind,
    const char* label) {
  if (handle_slot == nullptr) {
    return set_error(
        IRX_ARROW_STATUS_NULL_POINTER,
        "%s handle slot must not be NULL",
        label);
  }
  Handle* handle = *handle_slot;
  if (handle == nullptr) {
    return kArrowOk;
  }

  const irx_arrow_status validation =
      validate_handle(handle, expected_kind, label);
  if (validation != kArrowOk) {
    return validation;
  }
  if (handle->header.ownership != IRX_ARROW_HANDLE_OWNERSHIP_UNIQUE) {
    return set_error(
        IRX_ARROW_STATUS_INVALID_STATE,
        "%s handle does not use unique ownership",
        label);
  }

  *handle_slot = nullptr;
  handle->header.refcount.store(0, std::memory_order_release);
  handle->header.magic = 0;
  delete handle;
  return kArrowOk;
}

const TypeSpec* type_spec_from_type_id(int32_t type_id) {
  for (const TypeSpec& spec : kTypeSpecs) {
    if (spec.type_id == type_id) {
      return &spec;
    }
  }
  return nullptr;
}

const TypeSpec* type_spec_from_arrow_type_id(arrow::Type::type type_id) {
  for (const TypeSpec& spec : kTypeSpecs) {
    if (spec.arrow_type_id == type_id) {
      return &spec;
    }
  }
  return nullptr;
}

const TypeSpec* type_spec_from_c_data_format(const char* format) {
  if (format == nullptr) {
    return nullptr;
  }
  for (const TypeSpec& spec : kTypeSpecs) {
    if (std::strcmp(format, spec.c_data_format) == 0) {
      return &spec;
    }
  }
  return nullptr;
}

int validate_supported_c_schema(
    const ArrowSchema* schema,
    ResolvedSchema* out_resolved) {
  if (schema == nullptr) {
    return set_error(IRX_ARROW_STATUS_NULL_POINTER, "schema must not be NULL");
  }
  if (schema->n_children != 0 || schema->dictionary != nullptr) {
    return set_error(
        IRX_ARROW_STATUS_NOT_SUPPORTED,
        "Only plain primitive Arrow arrays are supported in this phase");
  }

  const TypeSpec* spec = type_spec_from_c_data_format(schema->format);
  if (spec == nullptr) {
    return set_error(
        IRX_ARROW_STATUS_NOT_SUPPORTED,
        "Unsupported Arrow storage type; supported types are bool, "
        "int8, int16, int32, int64, uint8, uint16, uint32, uint64, "
        "float32, and float64");
  }

  out_resolved->spec = spec;
  out_resolved->nullable = (schema->flags & ARROW_FLAG_NULLABLE) != 0;
  return kArrowOk;
}

int populate_array_metadata(
    irx_arrow_array_handle* handle,
    const ResolvedSchema& resolved) {
  if (!handle->array) {
    return set_error(IRX_ARROW_STATUS_INVALID_STATE, "array handle has no Arrow array");
  }

  handle->type_id = resolved.spec->type_id;
  handle->nullable = resolved.nullable ? 1 : 0;
  handle->dtype_token = resolved.spec->dtype_token;
  handle->element_size_bytes = resolved.spec->element_size_bytes;
  handle->buffer_view_compatible = resolved.spec->buffer_view_compatible ? 1 : 0;
  handle->shape[0] = handle->array->length();
  handle->strides[0] = resolved.spec->element_size_bytes;
  return kArrowOk;
}

ResolvedSchema resolved_from_arrow_type(
    const std::shared_ptr<arrow::DataType>& type,
    bool nullable) {
  ResolvedSchema resolved;
  resolved.spec = type_spec_from_arrow_type_id(type->id());
  resolved.nullable = nullable;
  return resolved;
}

bool c_data_bit_is_set(const void* data, int64_t bit_index) {
  if (data == nullptr) {
    return false;
  }
  const auto* bytes = static_cast<const uint8_t*>(data);
  const uint8_t mask = static_cast<uint8_t>(1U << (bit_index & 7));
  return (bytes[bit_index >> 3] & mask) != 0;
}

bool c_data_value_is_valid(const ArrowArray* array, int64_t logical_index) {
  if (array->null_count == 0 || array->buffers == nullptr ||
      array->buffers[0] == nullptr) {
    return true;
  }
  return c_data_bit_is_set(array->buffers[0], logical_index);
}

void noop_arrow_array_release(ArrowArray* array) {
  if (array == nullptr) {
    return;
  }
  array->release = nullptr;
}

int validate_c_data_array_layout(
    const ArrowArray* array,
    const ResolvedSchema& resolved) {
  if (array == nullptr) {
    return set_error(IRX_ARROW_STATUS_NULL_POINTER, "array must not be NULL");
  }
  if (array->release == nullptr) {
    return set_error(
        IRX_ARROW_STATUS_NULL_POINTER,
        "Arrow array release callback must not be NULL");
  }
  if (array->length < 0 || array->offset < 0) {
    return set_error(
        IRX_ARROW_STATUS_INVALID_ARGUMENT,
        "Arrow array length and offset must be non-negative");
  }
  if (array->null_count < -1) {
    return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT, "Arrow array null_count must be -1 or greater");
  }
  if (array->null_count > array->length) {
    return set_error(
        IRX_ARROW_STATUS_INVALID_ARGUMENT,
        "Arrow array null_count must not exceed array length");
  }
  if (!resolved.nullable && array->null_count != 0) {
    return set_error(
        IRX_ARROW_STATUS_SCHEMA_MISMATCH,
        "non-nullable Arrow schema cannot import nullable array data");
  }
  if (array->n_children != 0 || array->dictionary != nullptr) {
    return set_error(
        IRX_ARROW_STATUS_NOT_SUPPORTED,
        "Only plain primitive Arrow arrays are supported in this phase");
  }
  if (array->n_buffers < kPrimitiveArrayBufferCount) {
    return set_error(
        IRX_ARROW_STATUS_INVALID_ARGUMENT,
        "Arrow array n_buffers is smaller than the primitive layout requires");
  }
  if (array->buffers == nullptr) {
    return set_error(IRX_ARROW_STATUS_NULL_POINTER, "Arrow array buffers must not be NULL");
  }
  if (array->null_count > 0 && array->buffers[0] == nullptr) {
    return set_error(
        IRX_ARROW_STATUS_NULL_POINTER,
        "Arrow array validity bitmap must not be NULL when null_count is "
        "positive");
  }
  if (array->length > 0 && array->buffers[1] == nullptr) {
    return set_error(
        IRX_ARROW_STATUS_NULL_POINTER,
        "Arrow array value buffer must not be NULL for non-empty arrays");
  }
  if (array->offset > std::numeric_limits<int64_t>::max() - array->length) {
    return set_error(
        IRX_ARROW_STATUS_OVERFLOW,
        "Arrow array logical range overflowed int64");
  }
  if (resolved.spec->element_size_bytes > 0 && array->length > 0) {
    const int64_t logical_end = array->offset + array->length - 1;
    if (logical_end >
        std::numeric_limits<int64_t>::max() /
            resolved.spec->element_size_bytes) {
      return set_error(
          IRX_ARROW_STATUS_OVERFLOW,
          "Arrow array value-buffer byte offset overflowed int64");
    }
  }
  return kArrowOk;
}

int validate_c_data_array_with_arrow_cpp(
    const ArrowArray* array,
    const ResolvedSchema& resolved) {
  int code = validate_c_data_array_layout(array, resolved);
  if (code != kArrowOk) {
    return code;
  }

  ArrowArray temporary = *array;
  temporary.release = noop_arrow_array_release;
  arrow::Result<std::shared_ptr<arrow::Array>> import_result =
      arrow::ImportArray(&temporary, resolved.spec->make_type());
  if (!import_result.ok()) {
    return set_arrow_error(
        "Arrow array validation import failed",
        import_result.status());
  }

  std::shared_ptr<arrow::Array> imported =
      std::move(import_result).ValueUnsafe();
  const arrow::Status status = imported->ValidateFull();
  if (!status.ok()) {
    return set_arrow_error(
        "Arrow array validation failed",
        status);
  }
  return kArrowOk;
}

template <typename Builder, typename Value>
int append_typed_value(arrow::ArrayBuilder* builder, Value value) {
  auto* typed_builder = dynamic_cast<Builder*>(builder);
  if (typed_builder == nullptr) {
    return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH, "array builder element type mismatch");
  }
  const arrow::Status status = typed_builder->Append(value);
  if (!status.ok()) {
    return set_arrow_error("Arrow array append failed", status);
  }
  return kArrowOk;
}

int append_int_value(arrow::ArrayBuilder* builder, int32_t type_id, int64_t value) {
  switch (type_id) {
    case IRX_ARROW_TYPE_INT8:
      return append_typed_value<arrow::Int8Builder>(builder, static_cast<int8_t>(value));
    case IRX_ARROW_TYPE_INT16:
      return append_typed_value<arrow::Int16Builder>(builder, static_cast<int16_t>(value));
    case IRX_ARROW_TYPE_INT32:
      return append_typed_value<arrow::Int32Builder>(builder, static_cast<int32_t>(value));
    case IRX_ARROW_TYPE_INT64:
      return append_typed_value<arrow::Int64Builder>(builder, static_cast<int64_t>(value));
    case IRX_ARROW_TYPE_BOOL:
      return append_typed_value<arrow::BooleanBuilder>(builder, value != 0);
    default:
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH, "array builder expected a signed integer element type");
  }
}

int append_uint_value(
    arrow::ArrayBuilder* builder,
    int32_t type_id,
    uint64_t value) {
  switch (type_id) {
    case IRX_ARROW_TYPE_UINT8:
      return append_typed_value<arrow::UInt8Builder>(builder, static_cast<uint8_t>(value));
    case IRX_ARROW_TYPE_UINT16:
      return append_typed_value<arrow::UInt16Builder>(builder, static_cast<uint16_t>(value));
    case IRX_ARROW_TYPE_UINT32:
      return append_typed_value<arrow::UInt32Builder>(builder, static_cast<uint32_t>(value));
    case IRX_ARROW_TYPE_UINT64:
      return append_typed_value<arrow::UInt64Builder>(builder, static_cast<uint64_t>(value));
    default:
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH, "array builder expected an unsigned integer element type");
  }
}

int append_double_value(
    arrow::ArrayBuilder* builder,
    int32_t type_id,
    double value) {
  switch (type_id) {
    case IRX_ARROW_TYPE_FLOAT32:
      return append_typed_value<arrow::FloatBuilder>(builder, static_cast<float>(value));
    case IRX_ARROW_TYPE_FLOAT64:
      return append_typed_value<arrow::DoubleBuilder>(builder, value);
    default:
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH, "array builder expected a floating element type");
  }
}

int append_c_data_value(
    arrow::ArrayBuilder* builder,
    const TypeSpec* spec,
    const ArrowArray* array,
    int64_t logical_index) {
  if (!c_data_value_is_valid(array, logical_index)) {
    const arrow::Status status = builder->AppendNull();
    if (!status.ok()) {
      return set_arrow_error("Arrow array null append failed", status);
    }
    return kArrowOk;
  }

  if (array->buffers == nullptr || array->buffers[1] == nullptr) {
    return set_error(IRX_ARROW_STATUS_NULL_POINTER, "Arrow array value buffer must not be NULL");
  }

  const auto* data = static_cast<const uint8_t*>(array->buffers[1]);
  const uint8_t* slot = data + logical_index * spec->element_size_bytes;

  switch (spec->type_id) {
    case IRX_ARROW_TYPE_INT8:
      return append_int_value(builder, spec->type_id, *reinterpret_cast<const int8_t*>(slot));
    case IRX_ARROW_TYPE_INT16:
      return append_int_value(builder, spec->type_id, *reinterpret_cast<const int16_t*>(slot));
    case IRX_ARROW_TYPE_INT32:
      return append_int_value(builder, spec->type_id, *reinterpret_cast<const int32_t*>(slot));
    case IRX_ARROW_TYPE_INT64:
      return append_int_value(builder, spec->type_id, *reinterpret_cast<const int64_t*>(slot));
    case IRX_ARROW_TYPE_UINT8:
      return append_uint_value(builder, spec->type_id, *reinterpret_cast<const uint8_t*>(slot));
    case IRX_ARROW_TYPE_UINT16:
      return append_uint_value(builder, spec->type_id, *reinterpret_cast<const uint16_t*>(slot));
    case IRX_ARROW_TYPE_UINT32:
      return append_uint_value(builder, spec->type_id, *reinterpret_cast<const uint32_t*>(slot));
    case IRX_ARROW_TYPE_UINT64:
      return append_uint_value(builder, spec->type_id, *reinterpret_cast<const uint64_t*>(slot));
    case IRX_ARROW_TYPE_FLOAT32:
      return append_double_value(builder, spec->type_id, *reinterpret_cast<const float*>(slot));
    case IRX_ARROW_TYPE_FLOAT64:
      return append_double_value(builder, spec->type_id, *reinterpret_cast<const double*>(slot));
    case IRX_ARROW_TYPE_BOOL:
      return append_typed_value<arrow::BooleanBuilder>(
          builder,
          c_data_bit_is_set(array->buffers[1], logical_index));
    default:
      return set_error(IRX_ARROW_STATUS_NOT_SUPPORTED, "unsupported Arrow array storage type");
  }
}

int build_array_copy_from_c_data(
    const ArrowArray* array,
    const ResolvedSchema& resolved,
    std::shared_ptr<arrow::Array>* out_array) {
  int code = validate_c_data_array_with_arrow_cpp(array, resolved);
  if (code != kArrowOk) {
    return code;
  }

  arrow::Result<std::unique_ptr<arrow::ArrayBuilder>> builder_result =
      arrow::MakeBuilder(resolved.spec->make_type());
  if (!builder_result.ok()) {
    return set_arrow_error("Arrow builder allocation failed", builder_result.status());
  }

  std::unique_ptr<arrow::ArrayBuilder> builder = std::move(builder_result).ValueUnsafe();
  arrow::Status status = builder->Reserve(array->length);
  if (!status.ok()) {
    return set_arrow_error("Arrow builder reserve failed", status);
  }

  for (int64_t index = 0; index < array->length; ++index) {
    code = append_c_data_value(
        builder.get(),
        resolved.spec,
        array,
        array->offset + index);
    if (code != kArrowOk) {
      return code;
    }
  }

  status = builder->Finish(out_array);
  if (!status.ok()) {
    return set_arrow_error("Arrow builder finish failed", status);
  }
  return kArrowOk;
}

int checked_offset_bytes(
    int64_t offset,
    int64_t element_size_bytes,
    int64_t* out_offset_bytes) {
  if (offset < 0 || element_size_bytes < 0) {
    return set_error(
        IRX_ARROW_STATUS_INVALID_ARGUMENT,
        "buffer view offset computation requires non-negative values");
  }
  if (offset > 0 && element_size_bytes > std::numeric_limits<int64_t>::max() / offset) {
    return set_error(
        IRX_ARROW_STATUS_OVERFLOW,
        "Arrow array offset overflowed buffer view byte offset");
  }
  *out_offset_bytes = offset * element_size_bytes;
  return kArrowOk;
}

bool array_has_validity_buffer(const irx_arrow_array_handle* array) {
  if (array == nullptr || !array->array) {
    return false;
  }
  const std::shared_ptr<arrow::ArrayData>& data = array->array->data();
  return data && !data->buffers.empty() && data->buffers[0] != nullptr;
}

int64_t tensor_shape_extent(
    int32_t ndim,
    const int64_t* shape,
    int64_t* out_element_count) {
  int64_t element_count = 1;

  if (ndim < 0) {
    return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT, "tensor ndim must be non-negative");
  }
  if (ndim > 0 && shape == nullptr) {
    return set_error(
        IRX_ARROW_STATUS_NULL_POINTER,
        "tensor shape must not be NULL when ndim is positive");
  }

  for (int32_t axis = 0; axis < ndim; ++axis) {
    const int64_t dim = shape[axis];
    if (dim < 0) {
      return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT, "tensor shape dimensions must be non-negative");
    }
    if (dim != 0 && element_count > std::numeric_limits<int64_t>::max() / dim) {
      return set_error(IRX_ARROW_STATUS_OVERFLOW, "tensor shape extent overflowed int64");
    }
    element_count *= dim;
  }

  *out_element_count = element_count;
  return kArrowOk;
}

int copy_tensor_layout(
    int32_t ndim,
    const int64_t* shape,
    const int64_t* strides,
    int64_t element_size_bytes,
    std::vector<int64_t>* out_shape,
    std::vector<int64_t>* out_strides) {
  out_shape->clear();
  out_strides->clear();

  if (ndim == 0) {
    return kArrowOk;
  }

  out_shape->assign(shape, shape + ndim);
  out_strides->resize(static_cast<size_t>(ndim));

  if (strides != nullptr) {
    for (int32_t axis = 0; axis < ndim; ++axis) {
      if (strides[axis] < 0) {
        return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT, "tensor strides must be non-negative");
      }
      (*out_strides)[static_cast<size_t>(axis)] = strides[axis];
    }
    return kArrowOk;
  }

  int64_t stride = element_size_bytes;
  for (int32_t axis = ndim - 1; axis >= 0; --axis) {
    (*out_strides)[static_cast<size_t>(axis)] = stride;
    const int64_t dim = (*out_shape)[static_cast<size_t>(axis)] > 1
                            ? (*out_shape)[static_cast<size_t>(axis)]
                            : 1;
    if (stride > 0 && dim > std::numeric_limits<int64_t>::max() / stride) {
      return set_error(IRX_ARROW_STATUS_OVERFLOW, "tensor default stride computation overflowed int64");
    }
    stride *= dim;
  }

  return kArrowOk;
}

int tensor_data_nbytes(
    int64_t element_count,
    int64_t element_size_bytes,
    int64_t* out_data_nbytes) {
  if (element_size_bytes <= 0) {
    return set_error(
        IRX_ARROW_STATUS_TYPE_MISMATCH,
        "tensor element type must have a positive byte width");
  }
  if (element_count > 0 &&
      element_count > std::numeric_limits<int64_t>::max() / element_size_bytes) {
    return set_error(IRX_ARROW_STATUS_OVERFLOW, "tensor data size overflowed int64");
  }
  *out_data_nbytes = element_count * element_size_bytes;
  return kArrowOk;
}

int tensor_builder_require_slot(
    irx_arrow_tensor_builder_handle* builder,
    uint8_t** out_slot) {
  const irx_arrow_status validation = validate_handle(
      builder,
      IRX_ARROW_HANDLE_KIND_TENSOR_BUILDER,
      "tensor builder");
  if (validation != kArrowOk) {
    return validation;
  }
  if (builder->values_appended >= builder->element_count) {
    return set_error(IRX_ARROW_STATUS_INVALID_STATE, "too many values appended to tensor builder");
  }
  *out_slot = builder->data.data() + builder->values_appended * builder->element_size_bytes;
  builder->values_appended += 1;
  return kArrowOk;
}

template <typename T>
void write_tensor_slot(uint8_t* slot, T value) {
  std::memcpy(slot, &value, sizeof(value));
}

bool tensor_is_c_contiguous(const irx_arrow_tensor_handle* tensor) {
  int64_t stride = tensor->element_size_bytes;
  for (int32_t axis = static_cast<int32_t>(tensor->shape_cache.size()) - 1; axis >= 0; --axis) {
    const size_t index = static_cast<size_t>(axis);
    if (tensor->strides_cache[index] != stride) {
      return false;
    }
    const int64_t dim = tensor->shape_cache[index] > 1 ? tensor->shape_cache[index] : 1;
    if (stride > 0 && dim > std::numeric_limits<int64_t>::max() / stride) {
      return false;
    }
    stride *= dim;
  }
  return true;
}

bool tensor_is_f_contiguous(const irx_arrow_tensor_handle* tensor) {
  int64_t stride = tensor->element_size_bytes;
  for (size_t axis = 0; axis < tensor->shape_cache.size(); ++axis) {
    if (tensor->strides_cache[axis] != stride) {
      return false;
    }
    const int64_t dim = tensor->shape_cache[axis] > 1 ? tensor->shape_cache[axis] : 1;
    if (stride > 0 && dim > std::numeric_limits<int64_t>::max() / stride) {
      return false;
    }
    stride *= dim;
  }
  return true;
}

}  // namespace

extern "C" {

uint32_t irx_arrow_abi_version(void) {
  return IRX_ARROW_ABI_VERSION;
}

irx_arrow_status_category irx_arrow_status_get_category(
    irx_arrow_status status) {
  switch (status) {
    case IRX_ARROW_STATUS_OK:
      return IRX_ARROW_STATUS_CATEGORY_SUCCESS;
    case IRX_ARROW_STATUS_END_OF_STREAM:
    case IRX_ARROW_STATUS_CANCELLED:
      return IRX_ARROW_STATUS_CATEGORY_CONTROL;
    case IRX_ARROW_STATUS_INVALID_ARGUMENT:
    case IRX_ARROW_STATUS_NULL_POINTER:
    case IRX_ARROW_STATUS_INVALID_STATE:
    case IRX_ARROW_STATUS_TYPE_MISMATCH:
    case IRX_ARROW_STATUS_SCHEMA_MISMATCH:
    case IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS:
    case IRX_ARROW_STATUS_OVERFLOW:
    case IRX_ARROW_STATUS_NOT_SUPPORTED:
    case IRX_ARROW_STATUS_ABI_MISMATCH:
      return IRX_ARROW_STATUS_CATEGORY_INVALID;
    case IRX_ARROW_STATUS_OUT_OF_MEMORY:
    case IRX_ARROW_STATUS_RESOURCE_EXHAUSTED:
      return IRX_ARROW_STATUS_CATEGORY_RESOURCE;
    case IRX_ARROW_STATUS_IO_ERROR:
      return IRX_ARROW_STATUS_CATEGORY_IO;
    case IRX_ARROW_STATUS_ARROW_ERROR:
    case IRX_ARROW_STATUS_INTERNAL:
      return IRX_ARROW_STATUS_CATEGORY_INTERNAL;
    default:
      return IRX_ARROW_STATUS_CATEGORY_UNKNOWN;
  }
}

irx_arrow_status irx_arrow_handle_kind_of(
    const void* handle,
    irx_arrow_handle_kind* out_kind) {
  begin_operation(__func__);
  if (out_kind == nullptr) {
    return set_error(
        IRX_ARROW_STATUS_NULL_POINTER,
        "out_kind must not be NULL");
  }
  *out_kind = IRX_ARROW_HANDLE_KIND_UNKNOWN;
  if (handle == nullptr) {
    return set_error(
        IRX_ARROW_STATUS_NULL_POINTER,
        "handle must not be NULL");
  }
  const auto* header = static_cast<const HandleHeader*>(handle);
  if (header->magic != kHandleMagic ||
      header->refcount.load(std::memory_order_acquire) <= 0) {
    return set_error(
        IRX_ARROW_STATUS_INVALID_STATE,
        "handle has an invalid runtime marker or is released");
  }
  *out_kind = header->kind;
  return kArrowOk;
}

irx_arrow_status irx_arrow_handle_ownership_of(
    const void* handle,
    irx_arrow_handle_ownership* out_ownership) {
  begin_operation(__func__);
  if (out_ownership == nullptr) {
    return set_error(
        IRX_ARROW_STATUS_NULL_POINTER,
        "out_ownership must not be NULL");
  }
  *out_ownership = IRX_ARROW_HANDLE_OWNERSHIP_UNKNOWN;
  if (handle == nullptr) {
    return set_error(
        IRX_ARROW_STATUS_NULL_POINTER,
        "handle must not be NULL");
  }
  const auto* header = static_cast<const HandleHeader*>(handle);
  if (header->magic != kHandleMagic ||
      header->refcount.load(std::memory_order_acquire) <= 0) {
    return set_error(
        IRX_ARROW_STATUS_INVALID_STATE,
        "handle has an invalid runtime marker or is released");
  }
  *out_ownership = header->ownership;
  return kArrowOk;
}

irx_arrow_status irx_arrow_error_snapshot(
    irx_arrow_error_handle** out_error) {
  if (out_error == nullptr) {
    return IRX_ARROW_STATUS_NULL_POINTER;
  }
  *out_error = nullptr;
  if (current_error.code == IRX_ARROW_STATUS_OK) {
    return IRX_ARROW_STATUS_OK;
  }

  auto* error = new (std::nothrow) irx_arrow_error_handle;
  if (error == nullptr) {
    return IRX_ARROW_STATUS_OUT_OF_MEMORY;
  }
  error->detail = current_error;
  *out_error = error;
  return IRX_ARROW_STATUS_OK;
}

irx_arrow_status irx_arrow_error_code(
    const irx_arrow_error_handle* error) {
  begin_operation(__func__);
  const irx_arrow_status validation = validate_handle(
      error,
      IRX_ARROW_HANDLE_KIND_ERROR,
      "error");
  if (validation != kArrowOk) {
    return validation;
  }
  return error->detail.code;
}

const char* irx_arrow_error_operation(
    const irx_arrow_error_handle* error) {
  begin_operation(__func__);
  const irx_arrow_status validation = validate_handle(
      error,
      IRX_ARROW_HANDLE_KIND_ERROR,
      "error");
  return validation == kArrowOk ? error->detail.operation : "";
}

const char* irx_arrow_error_message(const irx_arrow_error_handle* error) {
  begin_operation(__func__);
  const irx_arrow_status validation = validate_handle(
      error,
      IRX_ARROW_HANDLE_KIND_ERROR,
      "error");
  return validation == kArrowOk ? error->detail.message : "";
}

const char* irx_arrow_error_upstream_detail(
    const irx_arrow_error_handle* error) {
  begin_operation(__func__);
  const irx_arrow_status validation = validate_handle(
      error,
      IRX_ARROW_HANDLE_KIND_ERROR,
      "error");
  return validation == kArrowOk ? error->detail.upstream_detail : "";
}

irx_arrow_status irx_arrow_error_retain(
    const irx_arrow_error_handle* error,
    irx_arrow_error_handle** out_error) {
  begin_operation(__func__);
  return retain_shared_handle(
      error,
      out_error,
      IRX_ARROW_HANDLE_KIND_ERROR,
      "error");
}

irx_arrow_status irx_arrow_error_release(
    irx_arrow_error_handle** error) {
  begin_operation(__func__);
  return release_shared_handle(
      error,
      IRX_ARROW_HANDLE_KIND_ERROR,
      "error");
}

irx_arrow_status irx_arrow_schema_import_copy(
    const ArrowSchema* schema,
    irx_arrow_schema_handle** out_schema) {
  begin_operation(__func__);
  try {
    if (out_schema == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "out_schema must not be NULL");
    }
    *out_schema = nullptr;

    ResolvedSchema resolved;
    int code = validate_supported_c_schema(schema, &resolved);
    if (code != kArrowOk) {
      return code;
    }

    auto handle = std::make_unique<irx_arrow_schema_handle>();
    handle->field = arrow::field("", resolved.spec->make_type(), resolved.nullable);
    handle->type_id = resolved.spec->type_id;
    handle->nullable = resolved.nullable ? 1 : 0;

    *out_schema = handle.release();
    return kArrowOk;
  } catch (const std::bad_alloc&) {
    return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY, "failed to allocate Arrow schema");
  } catch (const std::exception& exc) {
    return set_exception_error("irx_arrow_schema_import_copy", exc);
  }
}

irx_arrow_status irx_arrow_schema_export(
    const irx_arrow_schema_handle* schema,
    ArrowSchema* out_schema) {
  begin_operation(__func__);
  try {
    const irx_arrow_status validation = validate_handle(
        schema,
        IRX_ARROW_HANDLE_KIND_SCHEMA,
        "schema");
    if (validation != kArrowOk) {
      return validation;
    }
    if (out_schema == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "out_schema must not be NULL");
    }
    std::memset(out_schema, 0, sizeof(*out_schema));

    const arrow::Status status = arrow::ExportField(*schema->field, out_schema);
    if (!status.ok()) {
      return set_arrow_error("Arrow schema export failed", status);
    }
    return kArrowOk;
  } catch (const std::exception& exc) {
    return set_exception_error("irx_arrow_schema_export", exc);
  }
}

int32_t irx_arrow_schema_type_id(const irx_arrow_schema_handle* schema) {
  begin_operation(__func__);
  if (validate_handle(
          schema,
          IRX_ARROW_HANDLE_KIND_SCHEMA,
          "schema") != kArrowOk) {
    return IRX_ARROW_TYPE_UNKNOWN;
  }
  return schema->type_id;
}

int32_t irx_arrow_schema_is_nullable(const irx_arrow_schema_handle* schema) {
  begin_operation(__func__);
  if (validate_handle(
          schema,
          IRX_ARROW_HANDLE_KIND_SCHEMA,
          "schema") != kArrowOk) {
    return 0;
  }
  return schema->nullable;
}

irx_arrow_status irx_arrow_schema_retain(
    const irx_arrow_schema_handle* schema,
    irx_arrow_schema_handle** out_schema) {
  begin_operation(__func__);
  return retain_shared_handle(
      schema,
      out_schema,
      IRX_ARROW_HANDLE_KIND_SCHEMA,
      "schema");
}

irx_arrow_status irx_arrow_schema_release(
    irx_arrow_schema_handle** schema) {
  begin_operation(__func__);
  return release_shared_handle(
      schema,
      IRX_ARROW_HANDLE_KIND_SCHEMA,
      "schema");
}

irx_arrow_status irx_arrow_array_builder_new(
    int32_t type_id,
    irx_arrow_array_builder_handle** out_builder) {
  begin_operation(__func__);
  try {
    if (out_builder == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "out_builder must not be NULL");
    }
    *out_builder = nullptr;

    const TypeSpec* spec = type_spec_from_type_id(type_id);
    if (spec == nullptr) {
      return set_error(IRX_ARROW_STATUS_NOT_SUPPORTED, "unsupported Arrow type id %d", type_id);
    }

    arrow::Result<std::unique_ptr<arrow::ArrayBuilder>> builder_result =
        arrow::MakeBuilder(spec->make_type());
    if (!builder_result.ok()) {
      return set_arrow_error("Arrow builder allocation failed", builder_result.status());
    }

    auto handle = std::make_unique<irx_arrow_array_builder_handle>();
    handle->builder = std::move(builder_result).ValueUnsafe();
    handle->type_id = type_id;
    *out_builder = handle.release();
    return kArrowOk;
  } catch (const std::bad_alloc&) {
    return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY, "failed to allocate Arrow builder");
  } catch (const std::exception& exc) {
    return set_exception_error("irx_arrow_array_builder_new", exc);
  }
}

irx_arrow_status irx_arrow_array_builder_append_null(
    irx_arrow_array_builder_handle* builder,
    int64_t count) {
  begin_operation(__func__);
  const irx_arrow_status validation = validate_handle(
      builder,
      IRX_ARROW_HANDLE_KIND_ARRAY_BUILDER,
      "array builder");
  if (validation != kArrowOk) {
    return validation;
  }
  if (count < 0) {
    return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT, "null append count must be non-negative");
  }
  const arrow::Status status = builder->builder->AppendNulls(count);
  if (!status.ok()) {
    return set_arrow_error("Arrow null append failed", status);
  }
  return kArrowOk;
}

irx_arrow_status irx_arrow_array_builder_append_int(
    irx_arrow_array_builder_handle* builder,
    int64_t value) {
  begin_operation(__func__);
  const irx_arrow_status validation = validate_handle(
      builder,
      IRX_ARROW_HANDLE_KIND_ARRAY_BUILDER,
      "array builder");
  if (validation != kArrowOk) {
    return validation;
  }
  return append_int_value(builder->builder.get(), builder->type_id, value);
}

irx_arrow_status irx_arrow_array_builder_append_uint(
    irx_arrow_array_builder_handle* builder,
    uint64_t value) {
  begin_operation(__func__);
  const irx_arrow_status validation = validate_handle(
      builder,
      IRX_ARROW_HANDLE_KIND_ARRAY_BUILDER,
      "array builder");
  if (validation != kArrowOk) {
    return validation;
  }
  return append_uint_value(builder->builder.get(), builder->type_id, value);
}

irx_arrow_status irx_arrow_array_builder_append_double(
    irx_arrow_array_builder_handle* builder,
    double value) {
  begin_operation(__func__);
  const irx_arrow_status validation = validate_handle(
      builder,
      IRX_ARROW_HANDLE_KIND_ARRAY_BUILDER,
      "array builder");
  if (validation != kArrowOk) {
    return validation;
  }
  return append_double_value(builder->builder.get(), builder->type_id, value);
}

irx_arrow_status irx_arrow_array_builder_int32_new(
    irx_arrow_array_builder_handle** out_builder) {
  return irx_arrow_array_builder_new(IRX_ARROW_TYPE_INT32, out_builder);
}

irx_arrow_status irx_arrow_array_builder_append_int32(
    irx_arrow_array_builder_handle* builder,
    int32_t value) {
  return irx_arrow_array_builder_append_int(builder, value);
}

irx_arrow_status irx_arrow_array_builder_finish(
    irx_arrow_array_builder_handle** builder_slot,
    irx_arrow_array_handle** out_array) {
  begin_operation(__func__);
  try {
    if (out_array == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "out_array must not be NULL");
    }
    *out_array = nullptr;
    if (builder_slot == nullptr) {
      return set_error(
          IRX_ARROW_STATUS_NULL_POINTER,
          "array builder handle slot must not be NULL");
    }
    irx_arrow_array_builder_handle* builder = *builder_slot;
    const irx_arrow_status validation = validate_handle(
        builder,
        IRX_ARROW_HANDLE_KIND_ARRAY_BUILDER,
        "array builder");
    if (validation != kArrowOk) {
      return validation;
    }

    std::shared_ptr<arrow::Array> array;
    const arrow::Status status = builder->builder->Finish(&array);
    if (!status.ok()) {
      return set_arrow_error("Arrow builder finish failed", status);
    }

    const TypeSpec* spec = type_spec_from_type_id(builder->type_id);
    if (spec == nullptr) {
      return set_error(IRX_ARROW_STATUS_NOT_SUPPORTED, "builder used unsupported Arrow type id %d", builder->type_id);
    }

    auto handle = std::make_unique<irx_arrow_array_handle>();
    handle->array = std::move(array);
    ResolvedSchema resolved{spec, true};
    int code = populate_array_metadata(handle.get(), resolved);
    if (code != kArrowOk) {
      return code;
    }

    const irx_arrow_status release_status = release_unique_handle(
        builder_slot,
        IRX_ARROW_HANDLE_KIND_ARRAY_BUILDER,
        "array builder");
    if (release_status != kArrowOk) {
      return release_status;
    }
    *out_array = handle.release();
    return kArrowOk;
  } catch (const std::bad_alloc&) {
    return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY, "failed to allocate Arrow array");
  } catch (const std::exception& exc) {
    return set_exception_error("irx_arrow_array_builder_finish", exc);
  }
}

irx_arrow_status irx_arrow_array_builder_release(
    irx_arrow_array_builder_handle** builder) {
  begin_operation(__func__);
  return release_unique_handle(
      builder,
      IRX_ARROW_HANDLE_KIND_ARRAY_BUILDER,
      "array builder");
}

int64_t irx_arrow_array_length(const irx_arrow_array_handle* array) {
  begin_operation(__func__);
  if (validate_handle(
          array,
          IRX_ARROW_HANDLE_KIND_ARRAY,
          "array") != kArrowOk ||
      !array->array) {
    return -1;
  }
  return array->array->length();
}

int64_t irx_arrow_array_offset(const irx_arrow_array_handle* array) {
  begin_operation(__func__);
  if (validate_handle(
          array,
          IRX_ARROW_HANDLE_KIND_ARRAY,
          "array") != kArrowOk ||
      !array->array) {
    return -1;
  }
  return array->array->offset();
}

int64_t irx_arrow_array_null_count(const irx_arrow_array_handle* array) {
  begin_operation(__func__);
  if (validate_handle(
          array,
          IRX_ARROW_HANDLE_KIND_ARRAY,
          "array") != kArrowOk ||
      !array->array) {
    return -1;
  }
  return array->array->null_count();
}

int32_t irx_arrow_array_type_id(const irx_arrow_array_handle* array) {
  begin_operation(__func__);
  if (validate_handle(
          array,
          IRX_ARROW_HANDLE_KIND_ARRAY,
          "array") != kArrowOk) {
    return IRX_ARROW_TYPE_UNKNOWN;
  }
  return array->type_id;
}

int32_t irx_arrow_array_is_nullable(const irx_arrow_array_handle* array) {
  begin_operation(__func__);
  if (validate_handle(
          array,
          IRX_ARROW_HANDLE_KIND_ARRAY,
          "array") != kArrowOk) {
    return 0;
  }
  return array->nullable;
}

int32_t irx_arrow_array_has_validity_bitmap(
    const irx_arrow_array_handle* array) {
  begin_operation(__func__);
  if (validate_handle(
          array,
          IRX_ARROW_HANDLE_KIND_ARRAY,
          "array") != kArrowOk) {
    return 0;
  }
  return array_has_validity_buffer(array) ? 1 : 0;
}

int32_t irx_arrow_array_can_borrow_buffer_view(
    const irx_arrow_array_handle* array) {
  begin_operation(__func__);
  if (validate_handle(
          array,
          IRX_ARROW_HANDLE_KIND_ARRAY,
          "array") != kArrowOk) {
    return 0;
  }
  return array->buffer_view_compatible;
}

irx_arrow_status irx_arrow_array_schema_copy(
    const irx_arrow_array_handle* array,
    irx_arrow_schema_handle** out_schema) {
  begin_operation(__func__);
  try {
    const irx_arrow_status validation = validate_handle(
        array,
        IRX_ARROW_HANDLE_KIND_ARRAY,
        "array");
    if (validation != kArrowOk) {
      return validation;
    }
    if (!array->array) {
      return set_error(
          IRX_ARROW_STATUS_INVALID_STATE,
          "array handle has no Arrow array");
    }
    if (out_schema == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "out_schema must not be NULL");
    }
    *out_schema = nullptr;

    ResolvedSchema resolved = resolved_from_arrow_type(array->array->type(), array->nullable != 0);
    if (resolved.spec == nullptr) {
      return set_error(IRX_ARROW_STATUS_NOT_SUPPORTED, "unsupported Arrow array storage type");
    }

    auto handle = std::make_unique<irx_arrow_schema_handle>();
    handle->field = arrow::field("", array->array->type(), resolved.nullable);
    handle->type_id = resolved.spec->type_id;
    handle->nullable = resolved.nullable ? 1 : 0;
    *out_schema = handle.release();
    return kArrowOk;
  } catch (const std::bad_alloc&) {
    return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY, "failed to allocate Arrow schema");
  } catch (const std::exception& exc) {
    return set_exception_error("irx_arrow_array_schema_copy", exc);
  }
}

irx_arrow_status irx_arrow_array_export(
    const irx_arrow_array_handle* array,
    ArrowArray* out_array,
    ArrowSchema* out_schema) {
  begin_operation(__func__);
  try {
    const irx_arrow_status validation = validate_handle(
        array,
        IRX_ARROW_HANDLE_KIND_ARRAY,
        "array");
    if (validation != kArrowOk) {
      return validation;
    }
    if (!array->array) {
      return set_error(
          IRX_ARROW_STATUS_INVALID_STATE,
          "array handle has no Arrow array");
    }
    if (out_array == nullptr || out_schema == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "out_array and out_schema must not be NULL");
    }
    std::memset(out_array, 0, sizeof(*out_array));
    std::memset(out_schema, 0, sizeof(*out_schema));

    const arrow::Status status = arrow::ExportArray(*array->array, out_array, out_schema);
    if (!status.ok()) {
      return set_arrow_error("Arrow array export failed", status);
    }
    return kArrowOk;
  } catch (const std::exception& exc) {
    return set_exception_error("irx_arrow_array_export", exc);
  }
}

irx_arrow_status irx_arrow_array_import(
    const ArrowArray* array,
    const ArrowSchema* schema,
    irx_arrow_array_handle** out_array) {
  return irx_arrow_array_import_copy(array, schema, out_array);
}

irx_arrow_status irx_arrow_array_import_copy(
    const ArrowArray* array,
    const ArrowSchema* schema,
    irx_arrow_array_handle** out_array) {
  begin_operation(__func__);
  try {
    if (array == nullptr || schema == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "array and schema must not be NULL");
    }
    if (out_array == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "out_array must not be NULL");
    }
    *out_array = nullptr;

    ResolvedSchema resolved;
    int code = validate_supported_c_schema(schema, &resolved);
    if (code != kArrowOk) {
      return code;
    }

    std::shared_ptr<arrow::Array> copied_array;
    code = build_array_copy_from_c_data(array, resolved, &copied_array);
    if (code != kArrowOk) {
      return code;
    }

    auto handle = std::make_unique<irx_arrow_array_handle>();
    handle->array = std::move(copied_array);
    code = populate_array_metadata(handle.get(), resolved);
    if (code != kArrowOk) {
      return code;
    }

    *out_array = handle.release();
    return kArrowOk;
  } catch (const std::bad_alloc&) {
    return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY, "failed to allocate Arrow array");
  } catch (const std::exception& exc) {
    return set_exception_error("irx_arrow_array_import_copy", exc);
  }
}

irx_arrow_status irx_arrow_array_import_move(
    ArrowArray* array,
    ArrowSchema* schema,
    irx_arrow_array_handle** out_array) {
  begin_operation(__func__);
  try {
    if (array == nullptr || schema == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "array and schema must not be NULL");
    }
    if (out_array == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "out_array must not be NULL");
    }
    *out_array = nullptr;

    ResolvedSchema resolved;
    int code = validate_supported_c_schema(schema, &resolved);
    if (code != kArrowOk) {
      return code;
    }

    arrow::Result<std::shared_ptr<arrow::Array>> import_result =
        arrow::ImportArray(array, schema);
    if (!import_result.ok()) {
      return set_arrow_error("Arrow array import failed", import_result.status());
    }

    std::shared_ptr<arrow::Array> imported = std::move(import_result).ValueUnsafe();
    ResolvedSchema imported_resolved = resolved_from_arrow_type(imported->type(), resolved.nullable);
    if (imported_resolved.spec == nullptr) {
      return set_error(IRX_ARROW_STATUS_NOT_SUPPORTED, "unsupported Arrow array storage type");
    }

    auto handle = std::make_unique<irx_arrow_array_handle>();
    handle->array = std::move(imported);
    code = populate_array_metadata(handle.get(), imported_resolved);
    if (code != kArrowOk) {
      return code;
    }

    *out_array = handle.release();
    return kArrowOk;
  } catch (const std::bad_alloc&) {
    return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY, "failed to allocate Arrow array");
  } catch (const std::exception& exc) {
    return set_exception_error("irx_arrow_array_import_move", exc);
  }
}

irx_arrow_status irx_arrow_array_validity_bitmap(
    const irx_arrow_array_handle* array,
    const void** out_data,
    int64_t* out_offset_bits,
    int64_t* out_length_bits) {
  begin_operation(__func__);
  const irx_arrow_status validation = validate_handle(
      array,
      IRX_ARROW_HANDLE_KIND_ARRAY,
      "array");
  if (validation != kArrowOk) {
    return validation;
  }
  if (!array->array) {
    return set_error(
        IRX_ARROW_STATUS_INVALID_STATE,
        "array handle has no Arrow array");
  }
  if (out_data == nullptr || out_offset_bits == nullptr || out_length_bits == nullptr) {
    return set_error(IRX_ARROW_STATUS_NULL_POINTER, "out_data, out_offset_bits, and out_length_bits must not be NULL");
  }

  *out_data = nullptr;
  *out_offset_bits = 0;
  *out_length_bits = array->array->length();

  if (array_has_validity_buffer(array)) {
    *out_data = array->array->data()->buffers[0]->data();
    *out_offset_bits = array->array->offset();
  }
  return kArrowOk;
}

irx_arrow_status irx_arrow_array_borrow_buffer_view(
    const irx_arrow_array_handle* array,
    irx_buffer_view* out_view) {
  begin_operation(__func__);
  const irx_arrow_status validation = validate_handle(
      array,
      IRX_ARROW_HANDLE_KIND_ARRAY,
      "array");
  if (validation != kArrowOk) {
    return validation;
  }
  if (!array->array) {
    return set_error(
        IRX_ARROW_STATUS_INVALID_STATE,
        "array handle has no Arrow array");
  }
  if (out_view == nullptr) {
    return set_error(IRX_ARROW_STATUS_NULL_POINTER, "out_view must not be NULL");
  }
  if (!array->buffer_view_compatible) {
    return set_error(
        IRX_ARROW_STATUS_NOT_SUPPORTED,
        "Arrow bool arrays use bit-packed values and cannot be exposed as plain buffer views");
  }

  int64_t offset_bytes = 0;
  int code = checked_offset_bytes(
      array->array->offset(),
      array->element_size_bytes,
      &offset_bytes);
  if (code != kArrowOk) {
    return code;
  }

  const std::shared_ptr<arrow::ArrayData>& data = array->array->data();
  void* value_data = nullptr;
  if (data && data->buffers.size() > 1 && data->buffers[1] != nullptr) {
    value_data = const_cast<uint8_t*>(data->buffers[1]->data());
  }

  std::memset(out_view, 0, sizeof(*out_view));
  out_view->data = value_data;
  out_view->owner = nullptr;
  out_view->dtype = reinterpret_cast<void*>(array->dtype_token);
  out_view->ndim = 1;
  out_view->shape = const_cast<int64_t*>(array->shape);
  out_view->strides = const_cast<int64_t*>(array->strides);
  out_view->offset_bytes = offset_bytes;
  out_view->flags = IRX_BUFFER_FLAG_BORROWED |
                    IRX_BUFFER_FLAG_READONLY |
                    IRX_BUFFER_FLAG_C_CONTIGUOUS;
  if (array_has_validity_buffer(array)) {
    out_view->flags |= IRX_BUFFER_FLAG_VALIDITY_BITMAP;
  }
  return kArrowOk;
}

irx_arrow_status irx_arrow_array_retain(
    const irx_arrow_array_handle* array,
    irx_arrow_array_handle** out_array) {
  begin_operation(__func__);
  return retain_shared_handle(
      array,
      out_array,
      IRX_ARROW_HANDLE_KIND_ARRAY,
      "array");
}

irx_arrow_status irx_arrow_array_release(
    irx_arrow_array_handle** array) {
  begin_operation(__func__);
  return release_shared_handle(
      array,
      IRX_ARROW_HANDLE_KIND_ARRAY,
      "array");
}

irx_arrow_status irx_arrow_tensor_builder_new(
    int32_t type_id,
    int32_t ndim,
    const int64_t* shape,
    const int64_t* strides,
    irx_arrow_tensor_builder_handle** out_builder) {
  begin_operation(__func__);
  try {
    if (out_builder == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "out_builder must not be NULL");
    }
    *out_builder = nullptr;

    const TypeSpec* spec = type_spec_from_type_id(type_id);
    if (spec == nullptr) {
      return set_error(IRX_ARROW_STATUS_NOT_SUPPORTED, "unsupported Arrow tensor type id %d", type_id);
    }
    if (!spec->buffer_view_compatible || spec->element_size_bytes <= 0) {
      return set_error(
          IRX_ARROW_STATUS_INVALID_ARGUMENT,
          "Arrow tensor builder requires a fixed-width primitive value type");
    }

    int64_t element_count = 0;
    int code = static_cast<int>(tensor_shape_extent(ndim, shape, &element_count));
    if (code != kArrowOk) {
      return code;
    }

    int64_t data_nbytes = 0;
    code = tensor_data_nbytes(element_count, spec->element_size_bytes, &data_nbytes);
    if (code != kArrowOk) {
      return code;
    }

    auto builder = std::make_unique<irx_arrow_tensor_builder_handle>();
    builder->type_id = type_id;
    builder->ndim = ndim;
    builder->element_count = element_count;
    builder->dtype_token = spec->dtype_token;
    builder->element_size_bytes = spec->element_size_bytes;
    builder->type = spec->make_type();
    builder->data.assign(static_cast<size_t>(data_nbytes), 0);

    code = copy_tensor_layout(
        ndim,
        shape,
        strides,
        spec->element_size_bytes,
        &builder->shape,
        &builder->strides);
    if (code != kArrowOk) {
      return code;
    }

    *out_builder = builder.release();
    return kArrowOk;
  } catch (const std::bad_alloc&) {
    return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY, "failed to allocate Arrow tensor builder");
  } catch (const std::exception& exc) {
    return set_exception_error("irx_arrow_tensor_builder_new", exc);
  }
}

irx_arrow_status irx_arrow_tensor_builder_append_int(
    irx_arrow_tensor_builder_handle* builder,
    int64_t value) {
  begin_operation(__func__);
  uint8_t* slot = nullptr;
  const int code = tensor_builder_require_slot(builder, &slot);
  if (code != kArrowOk) {
    return code;
  }

  switch (builder->type_id) {
    case IRX_ARROW_TYPE_INT8:
      write_tensor_slot(slot, static_cast<int8_t>(value));
      return kArrowOk;
    case IRX_ARROW_TYPE_INT16:
      write_tensor_slot(slot, static_cast<int16_t>(value));
      return kArrowOk;
    case IRX_ARROW_TYPE_INT32:
      write_tensor_slot(slot, static_cast<int32_t>(value));
      return kArrowOk;
    case IRX_ARROW_TYPE_INT64:
      write_tensor_slot(slot, static_cast<int64_t>(value));
      return kArrowOk;
    default:
      builder->values_appended -= 1;
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH, "tensor builder expected a signed integer element type");
  }
}

irx_arrow_status irx_arrow_tensor_builder_append_uint(
    irx_arrow_tensor_builder_handle* builder,
    uint64_t value) {
  begin_operation(__func__);
  uint8_t* slot = nullptr;
  const int code = tensor_builder_require_slot(builder, &slot);
  if (code != kArrowOk) {
    return code;
  }

  switch (builder->type_id) {
    case IRX_ARROW_TYPE_UINT8:
      write_tensor_slot(slot, static_cast<uint8_t>(value));
      return kArrowOk;
    case IRX_ARROW_TYPE_UINT16:
      write_tensor_slot(slot, static_cast<uint16_t>(value));
      return kArrowOk;
    case IRX_ARROW_TYPE_UINT32:
      write_tensor_slot(slot, static_cast<uint32_t>(value));
      return kArrowOk;
    case IRX_ARROW_TYPE_UINT64:
      write_tensor_slot(slot, static_cast<uint64_t>(value));
      return kArrowOk;
    default:
      builder->values_appended -= 1;
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH, "tensor builder expected an unsigned integer element type");
  }
}

irx_arrow_status irx_arrow_tensor_builder_append_double(
    irx_arrow_tensor_builder_handle* builder,
    double value) {
  begin_operation(__func__);
  uint8_t* slot = nullptr;
  const int code = tensor_builder_require_slot(builder, &slot);
  if (code != kArrowOk) {
    return code;
  }

  switch (builder->type_id) {
    case IRX_ARROW_TYPE_FLOAT32:
      write_tensor_slot(slot, static_cast<float>(value));
      return kArrowOk;
    case IRX_ARROW_TYPE_FLOAT64:
      write_tensor_slot(slot, static_cast<double>(value));
      return kArrowOk;
    default:
      builder->values_appended -= 1;
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH, "tensor builder expected a floating element type");
  }
}

irx_arrow_status irx_arrow_tensor_builder_finish(
    irx_arrow_tensor_builder_handle** builder_slot,
    irx_arrow_tensor_handle** out_tensor) {
  begin_operation(__func__);
  try {
    if (out_tensor == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "out_tensor must not be NULL");
    }
    *out_tensor = nullptr;
    if (builder_slot == nullptr) {
      return set_error(
          IRX_ARROW_STATUS_NULL_POINTER,
          "tensor builder handle slot must not be NULL");
    }
    irx_arrow_tensor_builder_handle* builder = *builder_slot;
    const irx_arrow_status validation = validate_handle(
        builder,
        IRX_ARROW_HANDLE_KIND_TENSOR_BUILDER,
        "tensor builder");
    if (validation != kArrowOk) {
      return validation;
    }

    if (builder->values_appended != builder->element_count) {
      return set_error(
          IRX_ARROW_STATUS_INVALID_ARGUMENT,
          "tensor builder value count does not match tensor shape extent");
    }

    std::shared_ptr<arrow::Buffer> buffer = arrow::Buffer::FromVector(std::move(builder->data));
    arrow::Result<std::shared_ptr<arrow::Tensor>> tensor_result = arrow::Tensor::Make(
        builder->type,
        buffer,
        builder->shape,
        builder->strides);
    if (!tensor_result.ok()) {
      return set_arrow_error("Arrow tensor construction failed", tensor_result.status());
    }

    auto tensor = std::make_unique<irx_arrow_tensor_handle>();
    tensor->tensor = std::move(tensor_result).ValueUnsafe();
    tensor->shape_cache = tensor->tensor->shape();
    tensor->strides_cache = tensor->tensor->strides();
    tensor->type_id = builder->type_id;
    tensor->dtype_token = builder->dtype_token;
    tensor->element_size_bytes = builder->element_size_bytes;

    const irx_arrow_status release_status = release_unique_handle(
        builder_slot,
        IRX_ARROW_HANDLE_KIND_TENSOR_BUILDER,
        "tensor builder");
    if (release_status != kArrowOk) {
      return release_status;
    }
    *out_tensor = tensor.release();
    return kArrowOk;
  } catch (const std::bad_alloc&) {
    return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY, "failed to allocate Arrow tensor handle");
  } catch (const std::exception& exc) {
    return set_exception_error("irx_arrow_tensor_builder_finish", exc);
  }
}

irx_arrow_status irx_arrow_tensor_builder_release(
    irx_arrow_tensor_builder_handle** builder) {
  begin_operation(__func__);
  return release_unique_handle(
      builder,
      IRX_ARROW_HANDLE_KIND_TENSOR_BUILDER,
      "tensor builder");
}

int32_t irx_arrow_tensor_type_id(const irx_arrow_tensor_handle* tensor) {
  begin_operation(__func__);
  if (validate_handle(
          tensor,
          IRX_ARROW_HANDLE_KIND_TENSOR,
          "tensor") != kArrowOk) {
    return IRX_ARROW_TYPE_UNKNOWN;
  }
  return tensor->type_id;
}

int32_t irx_arrow_tensor_ndim(const irx_arrow_tensor_handle* tensor) {
  begin_operation(__func__);
  if (validate_handle(
          tensor,
          IRX_ARROW_HANDLE_KIND_TENSOR,
          "tensor") != kArrowOk ||
      !tensor->tensor) {
    return -1;
  }
  return tensor->tensor->ndim();
}

int64_t irx_arrow_tensor_size(const irx_arrow_tensor_handle* tensor) {
  begin_operation(__func__);
  if (validate_handle(
          tensor,
          IRX_ARROW_HANDLE_KIND_TENSOR,
          "tensor") != kArrowOk ||
      !tensor->tensor) {
    return -1;
  }
  return tensor->tensor->size();
}

const int64_t* irx_arrow_tensor_shape(const irx_arrow_tensor_handle* tensor) {
  begin_operation(__func__);
  if (validate_handle(
          tensor,
          IRX_ARROW_HANDLE_KIND_TENSOR,
          "tensor") != kArrowOk) {
    return nullptr;
  }
  return tensor->shape_cache.empty() ? nullptr : tensor->shape_cache.data();
}

const int64_t* irx_arrow_tensor_strides(const irx_arrow_tensor_handle* tensor) {
  begin_operation(__func__);
  if (validate_handle(
          tensor,
          IRX_ARROW_HANDLE_KIND_TENSOR,
          "tensor") != kArrowOk) {
    return nullptr;
  }
  return tensor->strides_cache.empty() ? nullptr : tensor->strides_cache.data();
}

irx_arrow_status irx_arrow_tensor_borrow_buffer_view(
    const irx_arrow_tensor_handle* tensor,
    irx_buffer_view* out_view) {
  begin_operation(__func__);
  const irx_arrow_status validation = validate_handle(
      tensor,
      IRX_ARROW_HANDLE_KIND_TENSOR,
      "tensor");
  if (validation != kArrowOk) {
    return validation;
  }
  if (!tensor->tensor) {
    return set_error(
        IRX_ARROW_STATUS_INVALID_STATE,
        "tensor handle has no Arrow tensor");
  }
  if (out_view == nullptr) {
    return set_error(IRX_ARROW_STATUS_NULL_POINTER, "out_view must not be NULL");
  }

  std::memset(out_view, 0, sizeof(*out_view));
  out_view->data = const_cast<uint8_t*>(tensor->tensor->raw_data());
  out_view->owner = nullptr;
  out_view->dtype = reinterpret_cast<void*>(tensor->dtype_token);
  out_view->ndim = static_cast<int32_t>(tensor->shape_cache.size());
  out_view->shape = const_cast<int64_t*>(tensor->shape_cache.data());
  out_view->strides = const_cast<int64_t*>(tensor->strides_cache.data());
  out_view->offset_bytes = 0;
  out_view->flags = IRX_BUFFER_FLAG_BORROWED | IRX_BUFFER_FLAG_READONLY;

  if (tensor_is_c_contiguous(tensor)) {
    out_view->flags |= IRX_BUFFER_FLAG_C_CONTIGUOUS;
  }
  if (tensor_is_f_contiguous(tensor)) {
    out_view->flags |= IRX_BUFFER_FLAG_F_CONTIGUOUS;
  }
  return kArrowOk;
}

irx_arrow_status irx_arrow_tensor_retain(
    const irx_arrow_tensor_handle* tensor,
    irx_arrow_tensor_handle** out_tensor) {
  begin_operation(__func__);
  return retain_shared_handle(
      tensor,
      out_tensor,
      IRX_ARROW_HANDLE_KIND_TENSOR,
      "tensor");
}

irx_arrow_status irx_arrow_tensor_release(
    irx_arrow_tensor_handle** tensor) {
  begin_operation(__func__);
  return release_shared_handle(
      tensor,
      IRX_ARROW_HANDLE_KIND_TENSOR,
      "tensor");
}

void irx_arrow_tensor_release_callback(void* tensor) {
  auto* tensor_handle = static_cast<irx_arrow_tensor_handle*>(tensor);
  (void)irx_arrow_tensor_release(&tensor_handle);
}

irx_arrow_status irx_arrow_table_new_from_arrays(
    int64_t column_count,
    const char** names,
    irx_arrow_array_handle** arrays,
    irx_arrow_table_handle** out_table) {
  begin_operation(__func__);
  try {
    if (out_table == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "out_table must not be NULL");
    }
    *out_table = nullptr;
    if (column_count < 0) {
      return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT, "column_count must be non-negative");
    }
    if (column_count > 0 && names == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "names must not be NULL");
    }
    if (column_count > 0 && arrays == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "arrays must not be NULL");
    }

    std::vector<std::shared_ptr<arrow::Field>> fields;
    std::vector<std::shared_ptr<arrow::ChunkedArray>> columns;
    fields.reserve(static_cast<size_t>(column_count));
    columns.reserve(static_cast<size_t>(column_count));

    int64_t row_count = -1;
    for (int64_t index = 0; index < column_count; ++index) {
      if (names[index] == nullptr) {
        return set_error(IRX_ARROW_STATUS_NULL_POINTER, "column name must not be NULL");
      }
      irx_arrow_array_handle* array = arrays[index];
      const irx_arrow_status validation = validate_handle(
          array,
          IRX_ARROW_HANDLE_KIND_ARRAY,
          "array");
      if (validation != kArrowOk) {
        return validation;
      }
      if (!array->array) {
        return set_error(
            IRX_ARROW_STATUS_INVALID_STATE,
            "array handle has no Arrow array");
      }
      const int64_t length = array->array->length();
      if (row_count < 0) {
        row_count = length;
      } else if (length != row_count) {
        return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT, "dataframe columns must have equal length");
      }

      fields.push_back(arrow::field(
          std::string(names[index]),
          array->array->type(),
          array->nullable != 0));
      columns.push_back(std::make_shared<arrow::ChunkedArray>(array->array));
    }

    auto schema = arrow::schema(std::move(fields));
    auto table = arrow::Table::Make(
        schema,
        std::move(columns),
        row_count < 0 ? 0 : row_count);

    auto handle = std::make_unique<irx_arrow_table_handle>();
    handle->table = std::move(table);
    *out_table = handle.release();
    return kArrowOk;
  } catch (const std::bad_alloc&) {
    return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY, "failed to allocate Arrow table");
  } catch (const std::exception& exc) {
    return set_exception_error("irx_arrow_table_new_from_arrays", exc);
  }
}

int64_t irx_arrow_table_num_rows(const irx_arrow_table_handle* table) {
  begin_operation(__func__);
  if (validate_handle(
          table,
          IRX_ARROW_HANDLE_KIND_TABLE,
          "table") != kArrowOk ||
      !table->table) {
    return -1;
  }
  return table->table->num_rows();
}

int64_t irx_arrow_table_num_columns(const irx_arrow_table_handle* table) {
  begin_operation(__func__);
  if (validate_handle(
          table,
          IRX_ARROW_HANDLE_KIND_TABLE,
          "table") != kArrowOk ||
      !table->table) {
    return -1;
  }
  return table->table->num_columns();
}

irx_arrow_status irx_arrow_table_column_by_name(
    const irx_arrow_table_handle* table,
    const char* name,
    irx_arrow_chunked_array_handle** out_column) {
  begin_operation(__func__);
  try {
    const irx_arrow_status validation = validate_handle(
        table,
        IRX_ARROW_HANDLE_KIND_TABLE,
        "table");
    if (validation != kArrowOk) {
      return validation;
    }
    if (!table->table) {
      return set_error(
          IRX_ARROW_STATUS_INVALID_STATE,
          "table handle has no Arrow table");
    }
    if (name == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "column name must not be NULL");
    }
    if (out_column == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "out_column must not be NULL");
    }
    *out_column = nullptr;

    std::shared_ptr<arrow::ChunkedArray> column =
        table->table->GetColumnByName(name);
    if (!column) {
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS, "table has no column named '%s'", name);
    }

    auto handle = std::make_unique<irx_arrow_chunked_array_handle>();
    handle->column = std::move(column);
    *out_column = handle.release();
    return kArrowOk;
  } catch (const std::bad_alloc&) {
    return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY, "failed to allocate Arrow chunked array handle");
  } catch (const std::exception& exc) {
    return set_exception_error("irx_arrow_table_column_by_name", exc);
  }
}

irx_arrow_status irx_arrow_table_column_by_index(
    const irx_arrow_table_handle* table,
    int32_t index,
    irx_arrow_chunked_array_handle** out_column) {
  begin_operation(__func__);
  try {
    const irx_arrow_status validation = validate_handle(
        table,
        IRX_ARROW_HANDLE_KIND_TABLE,
        "table");
    if (validation != kArrowOk) {
      return validation;
    }
    if (!table->table) {
      return set_error(
          IRX_ARROW_STATUS_INVALID_STATE,
          "table handle has no Arrow table");
    }
    if (out_column == nullptr) {
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "out_column must not be NULL");
    }
    *out_column = nullptr;
    if (index < 0 || index >= table->table->num_columns()) {
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS, "column index is out of bounds");
    }

    auto handle = std::make_unique<irx_arrow_chunked_array_handle>();
    handle->column = table->table->column(index);
    *out_column = handle.release();
    return kArrowOk;
  } catch (const std::bad_alloc&) {
    return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY, "failed to allocate Arrow chunked array handle");
  } catch (const std::exception& exc) {
    return set_exception_error("irx_arrow_table_column_by_index", exc);
  }
}

irx_arrow_status irx_arrow_table_retain(
    const irx_arrow_table_handle* table,
    irx_arrow_table_handle** out_table) {
  begin_operation(__func__);
  return retain_shared_handle(
      table,
      out_table,
      IRX_ARROW_HANDLE_KIND_TABLE,
      "table");
}

irx_arrow_status irx_arrow_table_release(
    irx_arrow_table_handle** table) {
  begin_operation(__func__);
  return release_shared_handle(
      table,
      IRX_ARROW_HANDLE_KIND_TABLE,
      "table");
}

irx_arrow_status irx_arrow_chunked_array_retain(
    const irx_arrow_chunked_array_handle* column,
    irx_arrow_chunked_array_handle** out_column) {
  begin_operation(__func__);
  return retain_shared_handle(
      column,
      out_column,
      IRX_ARROW_HANDLE_KIND_CHUNKED_ARRAY,
      "chunked array");
}

irx_arrow_status irx_arrow_chunked_array_release(
    irx_arrow_chunked_array_handle** column) {
  begin_operation(__func__);
  return release_shared_handle(
      column,
      IRX_ARROW_HANDLE_KIND_CHUNKED_ARRAY,
      "chunked array");
}

const char* irx_arrow_last_error(void) {
  return current_error.message;
}

}  // extern "C"
