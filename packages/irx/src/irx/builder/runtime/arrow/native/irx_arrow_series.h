// Copyright IRx contributors.
// Included after the opaque handle definitions in irx_arrow_runtime.cc.
#ifndef IRX_ARROW_SERIES_H
#define IRX_ARROW_SERIES_H
#include <type_traits>
#include <arrow/compute/api.h>
#include <arrow/compute/initialize.h>

namespace {
template <typename ArrowType>
std::shared_ptr<arrow::Scalar> scalar_from_bits(uint64_t bits, bool valid) {
  using Value = typename ArrowType::c_type;
  Value value{};
  if constexpr (std::is_floating_point_v<Value>) {
    if constexpr (sizeof(Value) == 4) {
      uint32_t narrow = static_cast<uint32_t>(bits);
      std::memcpy(&value, &narrow, sizeof(value));
    } else {
      std::memcpy(&value, &bits, sizeof(value));
    }
  } else {
    value = static_cast<Value>(bits);
  }
  using Scalar = typename arrow::TypeTraits<ArrowType>::ScalarType;
  auto result = std::make_shared<Scalar>(value);
  result->is_valid = valid;
  return result;
}
std::shared_ptr<arrow::Scalar> column_scalar(int32_t type, uint64_t bits, bool valid) {
#define IRX_SCALAR_CASE(ID, TYPE) case ID: return scalar_from_bits<arrow::TYPE>(bits, valid)
  switch (type) {
    IRX_SCALAR_CASE(IRX_ARROW_TYPE_INT8, Int8Type);
    IRX_SCALAR_CASE(IRX_ARROW_TYPE_INT16, Int16Type);
    IRX_SCALAR_CASE(IRX_ARROW_TYPE_INT32, Int32Type);
    IRX_SCALAR_CASE(IRX_ARROW_TYPE_INT64, Int64Type);
    IRX_SCALAR_CASE(IRX_ARROW_TYPE_UINT8, UInt8Type);
    IRX_SCALAR_CASE(IRX_ARROW_TYPE_UINT16, UInt16Type);
    IRX_SCALAR_CASE(IRX_ARROW_TYPE_UINT32, UInt32Type);
    IRX_SCALAR_CASE(IRX_ARROW_TYPE_UINT64, UInt64Type);
    IRX_SCALAR_CASE(IRX_ARROW_TYPE_FLOAT32, FloatType);
    IRX_SCALAR_CASE(IRX_ARROW_TYPE_FLOAT64, DoubleType);
    IRX_SCALAR_CASE(IRX_ARROW_TYPE_BOOL, BooleanType);
    default: return nullptr;
  }
#undef IRX_SCALAR_CASE
}
arrow::Status scalar_bits(const arrow::Scalar& scalar, uint64_t* bits, int32_t* valid) {
  *bits = 0;
  *valid = scalar.is_valid ? 1 : 0;
  if (!scalar.is_valid) return arrow::Status::OK();
#define IRX_BITS_CASE(ID, TYPE) case arrow::Type::ID: *bits = static_cast<uint64_t>(static_cast<const arrow::TYPE##Scalar&>(scalar).value); return arrow::Status::OK()
  switch (scalar.type->id()) {
    IRX_BITS_CASE(INT8, Int8); IRX_BITS_CASE(INT16, Int16);
    IRX_BITS_CASE(INT32, Int32); IRX_BITS_CASE(INT64, Int64);
    IRX_BITS_CASE(UINT8, UInt8); IRX_BITS_CASE(UINT16, UInt16);
    IRX_BITS_CASE(UINT32, UInt32); IRX_BITS_CASE(UINT64, UInt64);
    IRX_BITS_CASE(BOOL, Boolean);
    case arrow::Type::FLOAT: {
      uint32_t narrow;
      auto value = static_cast<const arrow::FloatScalar&>(scalar).value;
      std::memcpy(&narrow, &value, sizeof(value)); *bits = narrow;
      return arrow::Status::OK();
    }
    case arrow::Type::DOUBLE: {
      auto value = static_cast<const arrow::DoubleScalar&>(scalar).value;
      std::memcpy(bits, &value, sizeof(value)); return arrow::Status::OK();
    }
    default: return arrow::Status::TypeError("unsupported Series scalar type");
  }
#undef IRX_BITS_CASE
}
}

extern "C" int irx_arrow_series_index(
    const irx_arrow_chunked_array_handle* column, int64_t index, int32_t type,
    uint64_t* out_bits, int32_t* out_valid) {
  clear_error();
  if (out_bits) *out_bits = 0;
  if (out_valid) *out_valid = 0;
  if (!out_bits || !out_valid) return set_error(EINVAL, "scalar outputs must not be NULL");
  try {
    auto spec = type_spec_from_type_id(type);
    if (!column || !column->column || !spec || column->column->type()->id() != spec->arrow_type_id)
      return set_error(EINVAL, "Series index type mismatch");
    if (index < 0 || index >= column->column->length())
      return set_error(ERANGE, "Series index out of bounds");
    auto scalar = column->column->GetScalar(index);
    if (!scalar.ok()) return set_error(EINVAL, "%s", scalar.status().ToString().c_str());
    auto status = scalar_bits(**scalar, out_bits, out_valid);
    return status.ok() ? 0 : set_error(EINVAL, "%s", status.ToString().c_str());
  } catch (const std::exception& error) { return set_exception_error("Series index", error); }
}

extern "C" int irx_arrow_column_compute(
    const char* kernel, int32_t type,
    const irx_arrow_chunked_array_handle* lhs, uint64_t lhs_bits, int32_t lhs_valid,
    const irx_arrow_chunked_array_handle* rhs, uint64_t rhs_bits, int32_t rhs_valid,
    irx_arrow_chunked_array_handle** out_column, uint64_t* out_bits, int32_t* out_valid) {
  clear_error();
  if (out_column) *out_column = nullptr;
  if (out_bits) *out_bits = 0;
  if (out_valid) *out_valid = 0;
  if (!out_column || !out_bits || !out_valid)
    return set_error(EINVAL, "column outputs must not be NULL");
  try {
    if (!kernel) return set_error(EINVAL, "kernel must not be NULL");
    const std::string name(kernel);
    const std::vector<std::string> allowed = {"add_checked", "subtract_checked", "multiply_checked", "divide_checked", "equal", "not_equal", "less", "less_equal", "greater", "greater_equal", "and", "or", "is_null", "coalesce"};
    if (std::find(allowed.begin(), allowed.end(), name) == allowed.end())
      return set_error(EINVAL, "unsupported Series kernel");
    auto left_scalar = column_scalar(type, lhs_bits, lhs_valid != 0);
    auto right_scalar = column_scalar(type, rhs_bits, rhs_valid != 0);
    if (!left_scalar || !right_scalar) return set_error(EINVAL, "unsupported Series operand type");
    for (auto column : {lhs, rhs})
      if (column && (!column->column || !column->column->type()->Equals(left_scalar->type)))
        return set_error(EINVAL, "Series operand type mismatch");
    if (lhs && rhs && lhs->column->length() != rhs->column->length())
      return set_error(EINVAL, "Series lengths must match");
    static const auto initialized = arrow::compute::Initialize();
    if (!initialized.ok()) return set_error(EINVAL, "%s", initialized.ToString().c_str());
    std::vector<arrow::Datum> inputs = {lhs ? arrow::Datum(lhs->column) : arrow::Datum(left_scalar)};
    if (name != "is_null") inputs.push_back(rhs ? arrow::Datum(rhs->column) : arrow::Datum(right_scalar));
    auto computed = arrow::compute::CallFunction(name, inputs);
    if (!computed.ok()) return set_error(EINVAL, "%s", computed.status().ToString().c_str());
    if (computed->is_scalar()) {
      auto status = scalar_bits(*computed->scalar(), out_bits, out_valid);
      return status.ok() ? 0 : set_error(EINVAL, "%s", status.ToString().c_str());
    }
    auto result = std::make_unique<irx_arrow_chunked_array_handle>();
    result->refcount = 1;
    result->column = computed->is_chunked_array() ? computed->chunked_array()
        : std::make_shared<arrow::ChunkedArray>(computed->make_array());
    *out_column = result.release();
    return 0;
  } catch (const std::exception& error) { return set_exception_error("Series compute", error); }
}
#endif
