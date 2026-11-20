// Copyright IRx contributors.
// Included after the opaque handle definitions in irx_arrow_runtime.cc.
#ifndef IRX_ARROW_SERIES_H
#define IRX_ARROW_SERIES_H
#include <type_traits>
#include <limits>
#include <arrow/compute/api.h>
#include <arrow/compute/initialize.h>

using irx::column_scalar;
using irx::scalar_bits;

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
    const auto initialized = irx::initialize_compute();
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
    auto spec = type_spec_from_type_id(type);
    auto scalar = spec ? column_scalar(spec->arrow_type_id, bits, valid != 0) : nullptr;
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
