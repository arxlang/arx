// Copyright IRx contributors.
#include "irx_arrow_common.h"
#include <arrow/compute/initialize.h>
#include <arrow/util/config.h>
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <limits>
#include <type_traits>

static_assert(ARROW_VERSION_MAJOR == 26 && ARROW_VERSION_MINOR == 0 &&
              ARROW_VERSION_PATCH == 1, "IRx requires Arrow 26.0.1 headers");
static_assert(static_cast<int>(arrow::Type::DOUBLE) == IRX_COMPUTE_F64);

namespace {
thread_local char last_error[512] = {};
enum class Domain { F64, NUMERIC, PRIMITIVE, BOOL, ANY };
enum class Result { SAME, BOOL, SUM, MINMAX, MEAN, COUNT, BOOL_REDUCE };
struct Operation {
  const char* name;
  int32_t arity;
  Domain domain;
  Result result;
  bool reduction() const {
    return result == Result::SUM || result == Result::MINMAX ||
        result == Result::MEAN || result == Result::COUNT || result == Result::BOOL_REDUCE;
  }
};
const Operation* operation_spec(int32_t operation) {
  switch (operation) {
#define IRX_COMPUTE_OPERATION(SYMBOL, ID, NAME, ARITY, DOMAIN, RESULT, ULPS) \
    case ID: { static const Operation spec{#NAME, ARITY, Domain::DOMAIN, Result::RESULT}; return &spec; }
#include "irx_arrow_compute_catalog.h"
#undef IRX_COMPUTE_OPERATION
    default: return nullptr;
  }
}
bool integer_type(int32_t type) {
  return type >= arrow::Type::UINT8 && type <= arrow::Type::INT64;
}
bool numeric_type(int32_t type) {
  return integer_type(type) || type == arrow::Type::FLOAT || type == arrow::Type::DOUBLE;
}
bool primitive_type(int32_t type) { return numeric_type(type) || type == arrow::Type::BOOL; }

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

template <typename ArrowType>
std::shared_ptr<arrow::Scalar> scalar_from_bits(uint64_t bits, bool valid) {
  using Value = typename ArrowType::c_type;
  if (!valid) return arrow::MakeNullScalar(arrow::TypeTraits<ArrowType>::type_singleton());
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
    IRX_SCALAR_CASE(arrow::Type::INT8, Int8Type);
    IRX_SCALAR_CASE(arrow::Type::INT16, Int16Type);
    IRX_SCALAR_CASE(arrow::Type::INT32, Int32Type);
    IRX_SCALAR_CASE(arrow::Type::INT64, Int64Type);
    IRX_SCALAR_CASE(arrow::Type::UINT8, UInt8Type);
    IRX_SCALAR_CASE(arrow::Type::UINT16, UInt16Type);
    IRX_SCALAR_CASE(arrow::Type::UINT32, UInt32Type);
    IRX_SCALAR_CASE(arrow::Type::UINT64, UInt64Type);
    IRX_SCALAR_CASE(arrow::Type::FLOAT, FloatType);
    IRX_SCALAR_CASE(arrow::Type::DOUBLE, DoubleType);
    IRX_SCALAR_CASE(arrow::Type::BOOL, BooleanType);
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
    ARROW_ASSIGN_OR_RAISE(auto result, irx::call_compute("min_max", {input}));
    return arrow::Datum(static_cast<const arrow::StructScalar&>(*result.scalar()).value[name == "min" ? 0 : 1]);
  }
  return irx::call_compute(name, {input});
}

arrow::Result<arrow::Datum> compute_operand(
    const Operation& spec, int32_t type, int32_t source_type,
    const irx_arrow_chunked_array_handle* column, uint64_t bits, int32_t valid) {
  arrow::Datum input;
  if (!column) {
    if (!primitive_type(source_type) || (valid != 0 && valid != 1) ||
        (spec.domain == Domain::F64 && source_type != IRX_COMPUTE_F64))
      return arrow::Status::TypeError("invalid compute scalar descriptor");
    input = arrow::Datum(column_scalar(source_type, bits, valid != 0));
  } else {
    if (bits || valid || column->tag != irx_arrow_chunked_array_handle::tag_value ||
        column->refcount <= 0 || !column->column)
      return arrow::Status::TypeError("invalid compute Series descriptor/tag");
    const auto actual = column->column->type()->id();
    if ((source_type != actual && !(source_type == 0 && spec.domain == Domain::ANY)) ||
        (spec.domain == Domain::F64 && source_type != IRX_COMPUTE_F64))
      return arrow::Status::TypeError("compute Series physical/declared type mismatch");
    input = arrow::Datum(column->column);
  }
  if (type == 0 && spec.domain == Domain::ANY) return input;
  if (!primitive_type(source_type))
    return arrow::Status::TypeError("unsupported compute operand conversion");
  if (source_type != type) {
    auto target = column_scalar(type, 0, false)->type;
    return arrow::compute::Cast(input, target);
  }
  return input;
}
// Called only after checked integer division failed. Inspect valid pairs, not
// error text: a zero hidden by a null numerator must not mask min/-1 overflow.
bool has_zero_divisor(const arrow::Datum& lhs, const arrow::Datum& rhs) {
  const auto length = lhs.is_scalar() ? (rhs.is_scalar() ? 1 : rhs.length()) : lhs.length();
  for (int64_t i = 0; i < length; ++i) {
    auto left = lhs.is_scalar() ? arrow::Result<std::shared_ptr<arrow::Scalar>>(lhs.scalar())
        : lhs.chunked_array()->GetScalar(i);
    auto right = rhs.is_scalar() ? arrow::Result<std::shared_ptr<arrow::Scalar>>(rhs.scalar())
        : rhs.chunked_array()->GetScalar(i);
    if (!left.ok() || !right.ok()) continue;
    if (!(*left)->is_valid || !(*right)->is_valid) continue;
    uint64_t bits = 0; int32_t valid = 0;
    if (scalar_bits(**right, &bits, &valid).ok() && valid && bits == 0) return true;
  }
  return false;
}

}

extern "C" {
uint32_t irx_arrow_compute_abi_version(void) { return IRX_COMPUTE_ABI_VERSION; }

int32_t irx_arrow_compute_supports(uint32_t abi, int32_t operation,
    int32_t arity, int32_t options, int32_t type, int32_t shape, int32_t result_type) {
  irx::clear_error();
  try {
    if (abi != IRX_COMPUTE_ABI_VERSION)
      return irx::set_error(IRX_ERR_INVALID, "incompatible Arrow compute ABI revision");
    const auto* spec = operation_spec(operation);
    if (!spec || arity != spec->arity || options != IRX_COMPUTE_NO_OPTIONS)
      return irx::set_error(IRX_ERR_INVALID, "unsupported compute operation, arity or options");
    const bool domain = spec->domain == Domain::F64 ? type == IRX_COMPUTE_F64
        : spec->domain == Domain::NUMERIC ? numeric_type(type)
        : spec->domain == Domain::BOOL ? type == arrow::Type::BOOL
        : spec->domain == Domain::ANY ? (type == 0 || primitive_type(type)) : primitive_type(type);
    if (!domain || (operation == IRX_COMPUTE_NEGATE_CHECKED &&
                    integer_type(type) && arrow::is_unsigned_integer(static_cast<arrow::Type::type>(type))))
      return irx::set_error(IRX_ERR_TYPE, "unsupported compute input dtype");
    if ((shape != IRX_COMPUTE_SCALAR && shape != IRX_COMPUTE_SERIES) ||
        (spec->reduction() && shape != IRX_COMPUTE_SCALAR))
      return irx::set_error(IRX_ERR_TYPE, "unsupported compute result shape");
    int32_t expected = type;
    switch (spec->result) {
      case Result::BOOL: case Result::BOOL_REDUCE: expected = arrow::Type::BOOL; break;
      case Result::COUNT: expected = arrow::Type::INT64; break;
      case Result::MEAN: expected = arrow::Type::DOUBLE; break;
      case Result::SUM:
        expected = integer_type(type) ? (arrow::is_unsigned_integer(static_cast<arrow::Type::type>(type))
            ? arrow::Type::UINT64 : arrow::Type::INT64) : arrow::Type::DOUBLE;
        break;
      default: break;
    }
    if (result_type != expected)
      return irx::set_error(IRX_ERR_TYPE, "unsupported compute result dtype");
    auto status = irx::initialize_compute();
    if (!status.ok()) return irx::set_arrow_error(0, "compute initialization", status);
    if (operation != IRX_COMPUTE_IDENTITY) {
      const char* name = spec->result == Result::MINMAX ? "min_max" : spec->name;
      auto function = arrow::compute::GetFunctionRegistry()->GetFunction(name);
      if (!function.ok()) return irx::set_arrow_error(0, "compute registration", function.status());
    }
    return IRX_OK;
  } catch (const std::exception& error) {
    return irx::set_exception_error("compute capability", error);
  } catch (...) {
    return irx::set_error(IRX_ERR_ARROW, "unknown compute capability failure");
  }
}

int32_t irx_arrow_compute(uint32_t abi, int32_t operation, int32_t arity,
    int32_t options, int32_t type, int32_t shape,
    int32_t lhs_type, const irx_arrow_chunked_array_handle* lhs, uint64_t lhs_bits, int32_t lhs_valid,
    int32_t rhs_type, const irx_arrow_chunked_array_handle* rhs, uint64_t rhs_bits, int32_t rhs_valid,
    int32_t result_type, irx_arrow_chunked_array_handle** out_column, uint64_t* out_bits,
    int32_t* out_valid) {
  irx::clear_error();
  if (out_column) *out_column = nullptr;
  if (out_bits) *out_bits = 0;
  if (out_valid) *out_valid = 0;
  try {
    if (!out_column || !out_bits || !out_valid)
      return irx::set_error(IRX_ERR_NULLPTR, "compute output slots must not be NULL");
    const auto supported = irx_arrow_compute_supports(abi, operation, arity, options, type, shape, result_type);
    if (supported != IRX_OK) return supported;
    const auto& spec = *operation_spec(operation);
    if (arity == 1 && (rhs_type || rhs || rhs_bits || rhs_valid))
      return irx::set_error(IRX_ERR_INVALID, "unary compute requires an empty RHS descriptor");
    if ((spec.reduction() && !lhs) || (!spec.reduction() &&
        ((shape == IRX_COMPUTE_SERIES) != (lhs != nullptr || rhs != nullptr))))
      return irx::set_error(IRX_ERR_TYPE, "compute input/result shape mismatch");
    auto left = irx::compute_operand(spec, type, lhs_type, lhs, lhs_bits, lhs_valid);
    if (!left.ok()) return irx::set_arrow_error(0, "compute LHS", left.status());
    std::vector<arrow::Datum> inputs{*left};
    if (arity == 2) {
      auto right = irx::compute_operand(spec, type, rhs_type, rhs, rhs_bits, rhs_valid);
      if (!right.ok()) return irx::set_arrow_error(0, "compute RHS", right.status());
      if (lhs && rhs && left->length() != right->length())
        return irx::set_error(IRX_ERR_TYPE, "compute Series lengths must match");
      inputs.push_back(*right);
    }
    // Floating division follows IEEE just like primitive LLVM fdiv. Integer
    // arithmetic and reductions retain checked, exact-width behavior.
    const char* name = operation == IRX_COMPUTE_DIVIDE_CHECKED && !integer_type(type)
        ? "divide" : spec.name;
    auto computed = operation == IRX_COMPUTE_IDENTITY ? arrow::Result<arrow::Datum>(*left)
        : spec.reduction() ? irx::reduce_column(name, *left) : irx::call_compute(name, inputs);
    if (!computed.ok()) {
      int code = irx::record_batch_status(computed.status());
      if (computed.status().IsInvalid() && integer_type(type)) {
        switch (operation) {
          case IRX_COMPUTE_DIVIDE_CHECKED:
            code = irx::has_zero_divisor(inputs[0], inputs[1]) ? IRX_ERR_DIVZERO : IRX_ERR_OVERFLOW;
            break;
          case IRX_COMPUTE_ADD_CHECKED: case IRX_COMPUTE_SUBTRACT_CHECKED:
          case IRX_COMPUTE_MULTIPLY_CHECKED: case IRX_COMPUTE_NEGATE_CHECKED:
          case IRX_COMPUTE_SUM: code = IRX_ERR_OVERFLOW; break;
          default: break;
        }
      }
      return irx::set_error(code, "Arrow compute: %s", computed.status().ToString().c_str());
    }
    if ((shape == IRX_COMPUTE_SCALAR && !computed->is_scalar()) ||
        (shape == IRX_COMPUTE_SERIES && !computed->is_chunked_array() && !computed->is_array()) ||
        computed->type()->id() != result_type)
      return irx::set_error(IRX_ERR_TYPE, "unexpected compute result shape/dtype");
    if (shape == IRX_COMPUTE_SCALAR) {
      uint64_t bits = 0; int32_t valid = 0;
      auto status = irx::scalar_bits(*computed->scalar(), &bits, &valid);
      if (!status.ok()) return irx::set_arrow_error(0, "compute result", status);
      *out_bits = bits;
      *out_valid = valid;
    } else {
      const auto length = lhs ? lhs->column->length() : rhs->column->length();
      if (computed->length() != length)
        return irx::set_error(IRX_ERR_TYPE, "unexpected compute result length");
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
