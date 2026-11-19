// Copyright IRx contributors.
#include "irx_arrow_common.h"
#include <arrow/compute/initialize.h>
#include <arrow/util/config.h>
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <limits>

static_assert(ARROW_VERSION_MAJOR == 26 && ARROW_VERSION_MINOR == 0 &&
              ARROW_VERSION_PATCH == 1, "IRx requires Arrow 26.0.1 headers");
static_assert(static_cast<int>(arrow::Type::DOUBLE) == IRX_COMPUTE_F64);

namespace {
thread_local char last_error[512] = {};
const char* operation_name(int32_t operation) {
  switch (operation) {
#define IRX_COMPUTE_OPERATION(SYMBOL, ID, NAME, ULPS) case ID: return #NAME;
#include "irx_arrow_compute_catalog.h"
#undef IRX_COMPUTE_OPERATION
    default: return nullptr;
  }
}
}

namespace irx {
void clear_error() { last_error[0] = '\0'; }
int set_error(int code, const char* format, ...) {
  va_list args;
  va_start(args, format);
  std::vsnprintf(last_error, sizeof(last_error), format, args);
  va_end(args);
  switch (code) {
    case EINVAL: return IRX_ERR_INVALID;
    case ERANGE: return IRX_ERR_OOB;
    case EOVERFLOW: return IRX_ERR_OVERFLOW;
    case ENOMEM: return IRX_ERR_ALLOC;
    case EIO: return IRX_ERR_IO;
    default: return code;
  }
}
int set_arrow_error(int, const char* context, const arrow::Status& status) {
  return set_error(record_batch_status(status), "%s: %s", context,
                   status.ToString().c_str());
}
int set_exception_error(const char* context, const std::exception& error) {
  return set_error(native_exception_status(error), "%s: %s", context, error.what());
}
arrow::Status initialize_compute() {
  if (arrow::GetBuildInfo().version_string != "26.0.1")
    return arrow::Status::Invalid("IRx requires Arrow 26.0.1 libraries");
  static const auto initialized = arrow::compute::Initialize();
  return initialized;
}
arrow::Result<arrow::Datum> call_compute(
    const std::string& name, const std::vector<arrow::Datum>& inputs) {
  ARROW_RETURN_NOT_OK(initialize_compute());
  return arrow::compute::CallFunction(name, inputs);
}
}

extern "C" {
uint32_t irx_arrow_compute_abi_version(void) { return IRX_COMPUTE_ABI_VERSION; }

int32_t irx_arrow_compute_supports(uint32_t abi, int32_t operation,
    int32_t arity, int32_t options, int32_t arrow_type, int32_t shape) {
  irx::clear_error();
  try {
    if (abi != IRX_COMPUTE_ABI_VERSION)
      return irx::set_error(IRX_ERR_INVALID, "incompatible Arrow compute ABI revision");
    const char* name = operation_name(operation);
    if (!name || arity != 1 || options != IRX_COMPUTE_NO_OPTIONS)
      return irx::set_error(IRX_ERR_INVALID, "unsupported compute operation, arity or options");
    if (arrow_type != IRX_COMPUTE_F64)
      return irx::set_error(IRX_ERR_TYPE, "compute requires Arrow f64");
    if (shape != IRX_COMPUTE_SCALAR && shape != IRX_COMPUTE_SERIES)
      return irx::set_error(IRX_ERR_TYPE, "unsupported compute shape");
    auto status = irx::initialize_compute();
    if (!status.ok()) return irx::set_arrow_error(0, "compute initialization", status);
    auto function = arrow::compute::GetFunctionRegistry()->GetFunction(name);
    if (!function.ok()) return irx::set_arrow_error(0, "compute registration", function.status());
    return IRX_OK;
  } catch (const std::exception& error) {
    return irx::set_exception_error("compute capability", error);
  } catch (...) {
    return irx::set_error(IRX_ERR_ARROW, "unknown compute capability failure");
  }
}

int32_t irx_arrow_compute(uint32_t abi, int32_t operation, int32_t arity,
    int32_t options, int32_t arrow_type, int32_t shape,
    const irx_arrow_chunked_array_handle* column, uint64_t bits, int32_t valid,
    irx_arrow_chunked_array_handle** out_column, uint64_t* out_bits,
    int32_t* out_valid) {
  irx::clear_error();
  if (out_column) *out_column = nullptr;
  if (out_bits) *out_bits = 0;
  if (out_valid) *out_valid = 0;
  try {
    if (!out_column || !out_bits || !out_valid)
      return irx::set_error(IRX_ERR_NULLPTR, "compute output slots must not be NULL");
    const auto supported = irx_arrow_compute_supports(abi, operation, arity,
        options, arrow_type, shape);
    if (supported != IRX_OK) return supported;
    arrow::Datum input;
    if (shape == IRX_COMPUTE_SCALAR) {
      if (column || (valid != 0 && valid != 1))
        return irx::set_error(IRX_ERR_INVALID, "invalid compute scalar descriptor");
      if (!valid) {
        input = arrow::MakeNullScalar(arrow::float64());
      } else {
        double value;
        std::memcpy(&value, &bits, sizeof(value));
        input = arrow::Datum(value);
      }
    } else {
      if (!column) return irx::set_error(IRX_ERR_NULLPTR, "compute Series must not be NULL");
      if (bits || valid || column->tag != irx_arrow_chunked_array_handle::tag_value)
        return irx::set_error(IRX_ERR_TYPE, "invalid compute Series descriptor/tag");
      if (column->refcount <= 0 || !column->column ||
          column->column->type()->id() != arrow::Type::DOUBLE)
        return irx::set_error(IRX_ERR_TYPE, "compute Series requires live f64 storage");
      input = column->column;
    }
    auto computed = irx::call_compute(operation_name(operation), {input});
    if (!computed.ok()) return irx::set_arrow_error(0, "Arrow compute", computed.status());
    if ((shape == IRX_COMPUTE_SCALAR && !computed->is_scalar()) ||
        (shape == IRX_COMPUTE_SERIES && !computed->is_chunked_array() &&
         !computed->is_array()))
      return irx::set_error(IRX_ERR_TYPE, "unexpected compute result shape");
    if (computed->type()->id() != arrow::Type::DOUBLE)
      return irx::set_error(IRX_ERR_TYPE, "unexpected compute result dtype");
    if (shape == IRX_COMPUTE_SCALAR) {
      const auto& scalar = static_cast<const arrow::DoubleScalar&>(*computed->scalar());
      if (scalar.is_valid) {
        std::memcpy(out_bits, &scalar.value, sizeof(scalar.value));
        *out_valid = 1;
      }
    } else {
      if (computed->length() != column->column->length())
        return irx::set_error(IRX_ERR_TYPE, "unexpected compute result shape/length");
      auto result = std::make_unique<irx_arrow_chunked_array_handle>();
      result->refcount = 1;
      result->column = computed->is_chunked_array() ? computed->chunked_array()
          : std::make_shared<arrow::ChunkedArray>(computed->make_array());
      *out_column = result.release();
    }
    return IRX_OK;
  } catch (const std::exception& error) {
    return irx::set_exception_error("Arrow compute", error);
  } catch (...) {
    return irx::set_error(IRX_ERR_ARROW, "unknown Arrow compute failure");
  }
}

int irx_arrow_chunked_array_retain(irx_arrow_chunked_array_handle* column) {
  irx::clear_error();
  if (!column) return IRX_OK;
  if (column->tag != irx_arrow_chunked_array_handle::tag_value || column->refcount <= 0)
    return irx::set_error(IRX_ERR_INVALID, "invalid chunked array handle");
  if (column->refcount == std::numeric_limits<int64_t>::max())
    return irx::set_error(IRX_ERR_OVERFLOW, "chunked array reference overflow");
  ++column->refcount;
  return IRX_OK;
}
void irx_arrow_chunked_array_release(irx_arrow_chunked_array_handle* column) {
  if (!column || column->tag != irx_arrow_chunked_array_handle::tag_value ||
      column->refcount <= 0) return;
  if (--column->refcount == 0) delete column;
}
const char* irx_arrow_last_error(void) { return last_error; }
}
