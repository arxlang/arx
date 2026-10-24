// Copyright IRx contributors.
// Included after the opaque handle definitions in irx_arrow_runtime.cc.
#ifndef IRX_ARROW_SERIES_H
#define IRX_ARROW_SERIES_H
#include <type_traits>
#include <limits>
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

arrow::Result<arrow::Datum> reduce_column(const std::string& name, const arrow::Datum& input) {
  if (!input.is_chunked_array()) return arrow::Status::TypeError("reduction requires a Series");
  auto column = input.chunked_array();
  if (name == "sum" && arrow::is_integer(column->type()->id())) {
    const bool unsigned_type = arrow::is_unsigned_integer(column->type()->id());
    const auto target = unsigned_type ? arrow::uint64() : arrow::int64();
    ARROW_ASSIGN_OR_RAISE(auto widened, arrow::compute::Cast(input, target));
    uint64_t unsigned_total = 0; int64_t signed_total = 0; bool valid = false;
    for (const auto& chunk : widened.chunked_array()->chunks()) {
      for (int64_t i = 0; i < chunk->length(); ++i) {
        if (chunk->IsNull(i)) continue;
        valid = true;
        if (unsigned_type) {
          auto value = static_cast<const arrow::UInt64Array&>(*chunk).Value(i);
          if (value > std::numeric_limits<uint64_t>::max() - unsigned_total)
            return arrow::Status::Invalid("Series sum overflow");
          unsigned_total += value;
        } else {
          auto value = static_cast<const arrow::Int64Array&>(*chunk).Value(i);
          if ((value > 0 && signed_total > std::numeric_limits<int64_t>::max() - value) ||
              (value < 0 && signed_total < std::numeric_limits<int64_t>::min() - value))
            return arrow::Status::Invalid("Series sum overflow");
          signed_total += value;
        }
      }
    }
    if (!valid) return arrow::Datum(arrow::MakeNullScalar(target));
    return unsigned_type ? arrow::Datum(unsigned_total) : arrow::Datum(signed_total);
  }
  if (name == "min" || name == "max") {
    ARROW_ASSIGN_OR_RAISE(auto result, arrow::compute::CallFunction("min_max", {input}));
    return arrow::Datum(static_cast<const arrow::StructScalar&>(*result.scalar()).value[name == "min" ? 0 : 1]);
  }
  return arrow::compute::CallFunction(name, {input});
}
}

extern "C" int irx_arrow_series_index(
    const irx_arrow_chunked_array_handle* column, int64_t index, int32_t type,
    uint64_t* out_bits, int32_t* out_valid) {
  try {
  clear_error();
  if (out_bits) *out_bits = 0;
  if (out_valid) *out_valid = 0;
  if (!out_bits || !out_valid) return set_error(EINVAL, "scalar outputs must not be NULL");
  try {
    auto spec = type_spec_from_type_id(type);
    if (!column || !column->column || !spec || column->column->type()->id() != spec->arrow_type_id)
      return set_error(IRX_ERR_TYPE, "Series index type mismatch");
    if (index < 0 || index >= column->column->length())
      return set_error(ERANGE, "Series index out of bounds");
    auto scalar = column->column->GetScalar(index);
    if (!scalar.ok()) return set_error(irx::record_batch_status(scalar.status()), "%s", scalar.status().ToString().c_str());
    auto status = scalar_bits(**scalar, out_bits, out_valid);
    return status.ok() ? 0 : set_error(irx::record_batch_status(status), "%s", status.ToString().c_str());
  } catch (const std::exception& error) { return set_exception_error("Series index", error); }

  } catch (const std::exception& native_error) {
    return set_exception_error("irx_arrow_series_index", native_error);
  } catch (...) {
    return set_error(IRX_ERR_ARROW, "unknown native Arrow failure");
  }
}

extern "C" int irx_arrow_column_compute(
    const char* kernel, int32_t type,
    const irx_arrow_chunked_array_handle* lhs, uint64_t lhs_bits, int32_t lhs_valid,
    const irx_arrow_chunked_array_handle* rhs, uint64_t rhs_bits, int32_t rhs_valid,
    irx_arrow_chunked_array_handle** out_column, uint64_t* out_bits, int32_t* out_valid) {
  try {
  clear_error();
  if (out_column) *out_column = nullptr;
  if (out_bits) *out_bits = 0;
  if (out_valid) *out_valid = 0;
  if (!out_column || !out_bits || !out_valid)
    return set_error(EINVAL, "column outputs must not be NULL");
  try {
    if (!kernel) return set_error(EINVAL, "kernel must not be NULL");
    const std::string name(kernel);
    const std::vector<std::string> allowed = {"add_checked", "subtract_checked", "multiply_checked", "divide_checked", "equal", "not_equal", "less", "less_equal", "greater", "greater_equal", "and", "or", "is_null", "coalesce", "identity", "negate_checked", "invert", "sum", "min", "max", "mean", "count", "any", "all"};
    if (std::find(allowed.begin(), allowed.end(), name) == allowed.end())
      return set_error(EINVAL, "unsupported Series kernel");
    auto left_scalar = column_scalar(type, lhs_bits, lhs_valid != 0);
    auto right_scalar = column_scalar(type, rhs_bits, rhs_valid != 0);
    if (type == 0 && lhs && lhs->column && (name == "is_null" || name == "count")) {
      left_scalar = arrow::MakeNullScalar(lhs->column->type());
      right_scalar = left_scalar;
    }
    if (!left_scalar || !right_scalar) return set_error(IRX_ERR_TYPE, "unsupported Series operand type");
    for (auto column : {lhs, rhs})
      if (column && (!column->column || !column->column->type()->Equals(left_scalar->type)))
        return set_error(IRX_ERR_TYPE, "Series operand type mismatch");
    if (lhs && rhs && lhs->column->length() != rhs->column->length())
      return set_error(EINVAL, "Series lengths must match");
    static const auto initialized = arrow::compute::Initialize();
    if (!initialized.ok()) return set_error(irx::record_batch_status(initialized), "%s", initialized.ToString().c_str());
    std::vector<arrow::Datum> inputs = {lhs ? arrow::Datum(lhs->column) : arrow::Datum(left_scalar)};
    const bool reduction = name == "sum" || name == "min" || name == "max" || name == "mean" || name == "count" || name == "any" || name == "all";
    const bool unary = reduction || name == "is_null" || name == "identity" || name == "negate_checked" || name == "invert";
    if (!unary) inputs.push_back(rhs ? arrow::Datum(rhs->column) : arrow::Datum(right_scalar));
    arrow::Result<arrow::Datum> computed = name == "identity" ? arrow::Result<arrow::Datum>(inputs[0])
        : reduction ? reduce_column(name, inputs[0]) : arrow::compute::CallFunction(name, inputs);
    if (!computed.ok()) return set_error(irx::record_batch_status(computed.status()), "%s", computed.status().ToString().c_str());
    if (computed->is_scalar()) {
      auto status = scalar_bits(*computed->scalar(), out_bits, out_valid);
      return status.ok() ? 0 : set_error(irx::record_batch_status(status), "%s", status.ToString().c_str());
    }
    auto result = std::make_unique<irx_arrow_chunked_array_handle>();
    result->refcount = 1;
    result->column = computed->is_chunked_array() ? computed->chunked_array()
        : std::make_shared<arrow::ChunkedArray>(computed->make_array());
    *out_column = result.release();
    return 0;
  } catch (const std::exception& error) { return set_exception_error("Series compute", error); }

  } catch (const std::exception& native_error) {
    return set_exception_error("irx_arrow_column_compute", native_error);
  } catch (...) {
    return set_error(IRX_ERR_ARROW, "unknown native Arrow failure");
  }
}

extern "C" int irx_arrow_column_compute_promoted(
    const char* kernel, int32_t type,
    const irx_arrow_chunked_array_handle* lhs, uint64_t lhs_bits, int32_t lhs_valid,
    const irx_arrow_chunked_array_handle* rhs, uint64_t rhs_bits, int32_t rhs_valid,
    irx_arrow_chunked_array_handle** out_column, uint64_t* out_bits, int32_t* out_valid) {
  try {
  clear_error();
  if (out_column) *out_column = nullptr;
  if (out_bits) *out_bits = 0;
  if (out_valid) *out_valid = 0;
  if (!out_column || !out_bits || !out_valid) return set_error(EINVAL, "column outputs must not be NULL");
  try {
    auto scalar = column_scalar(type, 0, false);
    if (!scalar) return irx_arrow_column_compute(kernel, type, lhs, lhs_bits, lhs_valid, rhs, rhs_bits, rhs_valid, out_column, out_bits, out_valid);
    static const auto initialized = arrow::compute::Initialize();
    if (!initialized.ok()) return set_error(irx::record_batch_status(initialized), "%s", initialized.ToString().c_str());
    irx_arrow_chunked_array_handle left{}, right{};
    auto convert = [&scalar](const irx_arrow_chunked_array_handle* source, irx_arrow_chunked_array_handle* target) -> arrow::Status {
      if (!source) return arrow::Status::OK();
      if (!source->column) return arrow::Status::Invalid("invalid Series operand");
      ARROW_ASSIGN_OR_RAISE(auto converted, arrow::compute::Cast(arrow::Datum(source->column), scalar->type));
      target->column = converted.chunked_array();
      return arrow::Status::OK();
    };
    auto status = convert(lhs, &left);
    if (status.ok()) status = convert(rhs, &right);
    if (!status.ok()) return set_error(irx::record_batch_status(status), "%s", status.ToString().c_str());
    return irx_arrow_column_compute(kernel, type, lhs ? &left : nullptr, lhs_bits, lhs_valid,
        rhs ? &right : nullptr, rhs_bits, rhs_valid, out_column, out_bits, out_valid);
  } catch (const std::exception& error) { return set_exception_error("Series promotion", error); }

  } catch (const std::exception& native_error) {
    return set_exception_error("irx_arrow_column_compute_promoted", native_error);
  } catch (...) {
    return set_error(IRX_ERR_ARROW, "unknown native Arrow failure");
  }
}

extern "C" int irx_arrow_series_slice(
    const irx_arrow_chunked_array_handle* column, int64_t start, int64_t stop,
    int64_t step, int32_t bounds, irx_arrow_chunked_array_handle** out) {
  try {
  clear_error();
  if (!out) return set_error(EINVAL, "slice output must not be NULL");
  *out = nullptr;
  try {
    if (!column || !column->column) return set_error(EINVAL, "slice requires a Series");
    if (!step) return set_error(EINVAL, "slice step cannot be zero");
    const int64_t length = column->column->length();
    auto normalize = [length, step](int64_t bound) {
      if (bound < 0) bound += length;
      return step > 0 ? std::clamp(bound, int64_t(0), length)
                      : std::clamp(bound, int64_t(-1), length - 1);
    };
    start = (bounds & 1) ? normalize(start) : (step > 0 ? 0 : length - 1);
    stop = (bounds & 2) ? normalize(stop) : (step > 0 ? length : -1);
    arrow::Int64Builder builder;
    for (int64_t i = start; step > 0 ? i < stop : i > stop;) {
      auto status = builder.Append(i);
      if (!status.ok()) return set_error(irx::record_batch_status(status), "%s", status.ToString().c_str());
      if (step > 0 ? step >= stop - i : step <= stop - i) break;
      i += step;
    }
    auto indices = builder.Finish();
    if (!indices.ok()) return set_error(irx::record_batch_status(indices.status()), "%s", indices.status().ToString().c_str());
    static const auto initialized = arrow::compute::Initialize();
    if (!initialized.ok()) return set_error(irx::record_batch_status(initialized), "%s", initialized.ToString().c_str());
    auto taken = arrow::compute::Take(arrow::Datum(column->column), arrow::Datum(*indices));
    if (!taken.ok()) return set_error(irx::record_batch_status(taken.status()), "%s", taken.status().ToString().c_str());
    auto result = std::make_unique<irx_arrow_chunked_array_handle>();
    result->refcount = 1;
    result->column = taken->chunked_array();
    *out = result.release();
    return 0;
  } catch (const std::exception& error) { return set_exception_error("Series slice", error); }

  } catch (const std::exception& native_error) {
    return set_exception_error("irx_arrow_series_slice", native_error);
  } catch (...) {
    return set_error(IRX_ERR_ARROW, "unknown native Arrow failure");
  }
}

extern "C" int irx_arrow_series_set(irx_arrow_chunked_array_handle* column,
    int64_t index, int32_t type, uint64_t bits, int32_t valid, int32_t nullable) {
  try {
  clear_error();
  try {
    auto scalar = column_scalar(type, bits, valid != 0);
    if (!column || !column->column || !scalar || !scalar->type->Equals(column->column->type()))
      return set_error(IRX_ERR_TYPE, "Series update type mismatch");
    if (!valid && !nullable) return set_error(EINVAL, "null update of non-nullable Series");
    if (index < 0 || index >= column->column->length()) return set_error(ERANGE, "Series index out of bounds");
    auto replacement = arrow::MakeArrayFromScalar(*scalar, 1);
    if (!replacement.ok()) return set_error(irx::record_batch_status(replacement.status()), "%s", replacement.status().ToString().c_str());
    std::vector<std::shared_ptr<arrow::Array>> chunks;
    auto prefix = column->column->Slice(0, index);
    auto suffix = column->column->Slice(index + 1);
    for (auto chunk : prefix->chunks()) chunks.push_back(chunk);
    chunks.push_back(*replacement);
    for (auto chunk : suffix->chunks()) chunks.push_back(chunk);
    auto result = std::make_shared<arrow::ChunkedArray>(std::move(chunks), scalar->type);
    column->column = std::move(result);
    return 0;
  } catch (const std::exception& error) { return set_exception_error("Series update", error); }

  } catch (const std::exception& native_error) {
    return set_exception_error("irx_arrow_series_set", native_error);
  } catch (...) {
    return set_error(IRX_ERR_ARROW, "unknown native Arrow failure");
  }
}
#endif
