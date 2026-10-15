// Copyright IRx contributors.
// Included in the array capability; all C++ types stay behind opaque owners.
extern "C++" {
namespace {
template <typename Operation>
irx_arrow_status array_value_operation(const char *name, Operation operation) {
  begin_operation(name);
  try {
    if (fail_allocation_for_operation(name))
      return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY,
                       "injected array operation allocation failure");
    return operation();
  } catch (const std::bad_alloc &) {
    return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY,
                     "array operation allocation failed");
  } catch (const std::exception &error) {
    return set_exception_error(name, error);
  }
}

irx_arrow_status validate_value_array(const irx_arrow_array_handle *array) {
  const auto status =
      validate_handle(array, IRX_ARROW_HANDLE_KIND_ARRAY, "array");
  if (status != kArrowOk)
    return status;
  if (!array->array)
    return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing Arrow array");
  return kArrowOk;
}

irx_arrow_status publish_value_array(std::shared_ptr<arrow::Array> value,
                                     bool nullable,
                                     irx_arrow_array_handle **output) {
  auto owner = make_runtime_handle<irx_arrow_array_handle>();
  auto resolved = resolved_from_arrow_type(value->type(), nullable);
  auto validation = value->ValidateFull();
  if (!validation.ok()) return set_arrow_error("array value", validation);
  owner->array = std::move(value);
  const auto status = populate_array_metadata(owner.get(), resolved);
  if (status != kArrowOk)
    return status;
  *output = owner.release();
  return kArrowOk;
}

template <typename Value, typename Extract>
irx_arrow_status extract_array_value(const irx_arrow_array_handle *array,
                                     int64_t index, AppendKind kind,
                                     int32_t *valid, Value *output,
                                     Extract extract) {
  if (valid)
    *valid = 0;
  if (output)
    *output = 0;
  if (!valid || !output)
    return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing scalar output");
  const auto status = validate_value_array(array);
  if (status != kArrowOk)
    return status;
  const auto *spec = type_spec_from_type_id(array->type_id);
  if (!spec ||
      (spec->append_kind != kind && !(kind == AppendKind::kSigned &&
                                      spec->append_kind == AppendKind::kBool)))
    return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                     "scalar output does not match array storage");
  if (index < 0 || index >= array->array->length())
    return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                     "array index is outside its length");
  if (array->array->IsNull(index))
    return kArrowOk;
  // Arrow's typed accessors incorporate both value and bitmap slice offsets.
  *output = extract(array->array.get());
  *valid = 1;
  return kArrowOk;
}
} // namespace
} // extern C++

irx_arrow_status
irx_arrow_array_builder_finish_typed(irx_arrow_array_builder_handle **builder,
                                     int32_t nullable,
                                     irx_arrow_array_handle **out_array) {
  if (out_array)
    *out_array = nullptr;
  return array_value_operation(
      "array_builder_finish_typed", [&]() -> irx_arrow_status {
        if (!builder || !out_array)
          return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                           "missing builder or array output");
        const auto status = validate_handle(
            *builder, IRX_ARROW_HANDLE_KIND_ARRAY_BUILDER, "array builder");
        if (status != kArrowOk)
          return status;
        if (nullable != 0 && nullable != 1)
          return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT,
                           "invalid nullability flag");
        if ((*builder)->logical_type) {
          const auto result = irx_arrow_array_builder_build(*builder, nullable, out_array);
          if (result != kArrowOk) return result;
          return irx_arrow_array_builder_release(builder);
        }
        if (!nullable && (*builder)->builder->null_count() != 0)
          return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                           "nulls in a nonnullable array");
        const auto finished =
            irx_arrow_array_builder_finish(builder, out_array);
        if (finished == kArrowOk)
          (*out_array)->nullable = nullable;
        return finished;
      });
}

irx_arrow_status irx_arrow_array_get_int(const irx_arrow_array_handle *array,
                                         int64_t index, int32_t *out_valid,
                                         int64_t *out_value) {
  if (out_valid)
    *out_valid = 0;
  if (out_value)
    *out_value = 0;
  return array_value_operation("array_get_int", [&]() {
    return extract_array_value(
        array, index, AppendKind::kSigned, out_valid, out_value,
        [&](const arrow::Array *value) -> int64_t {
          switch (value->type_id()) {
          case arrow::Type::BOOL:
            return static_cast<const arrow::BooleanArray *>(value)->Value(
                index);
          case arrow::Type::INT8:
            return static_cast<const arrow::Int8Array *>(value)->Value(index);
          case arrow::Type::INT16:
            return static_cast<const arrow::Int16Array *>(value)->Value(index);
          case arrow::Type::INT32:
            return static_cast<const arrow::Int32Array *>(value)->Value(index);
          default:
            return static_cast<const arrow::Int64Array *>(value)->Value(index);
          }
        });
  });
}

irx_arrow_status irx_arrow_array_get_uint(const irx_arrow_array_handle *array,
                                          int64_t index, int32_t *out_valid,
                                          uint64_t *out_value) {
  if (out_valid)
    *out_valid = 0;
  if (out_value)
    *out_value = 0;
  return array_value_operation("array_get_uint", [&]() {
    return extract_array_value(
        array, index, AppendKind::kUnsigned, out_valid, out_value,
        [&](const arrow::Array *value) -> uint64_t {
          switch (value->type_id()) {
          case arrow::Type::UINT8:
            return static_cast<const arrow::UInt8Array *>(value)->Value(index);
          case arrow::Type::UINT16:
            return static_cast<const arrow::UInt16Array *>(value)->Value(index);
          case arrow::Type::UINT32:
            return static_cast<const arrow::UInt32Array *>(value)->Value(index);
          default:
            return static_cast<const arrow::UInt64Array *>(value)->Value(index);
          }
        });
  });
}

irx_arrow_status irx_arrow_array_get_double(const irx_arrow_array_handle *array,
                                            int64_t index, int32_t *out_valid,
                                            double *out_value) {
  if (out_valid)
    *out_valid = 0;
  if (out_value)
    *out_value = 0;
  return array_value_operation("array_get_double", [&]() {
    return extract_array_value(
        array, index, AppendKind::kDouble, out_valid, out_value,
        [&](const arrow::Array *value) -> double {
          if (value->type_id() == arrow::Type::HALF_FLOAT)
            return arrow::util::Float16::FromBits(
                       static_cast<const arrow::HalfFloatArray *>(value)->Value(
                           index))
                .ToDouble();
          if (value->type_id() == arrow::Type::FLOAT)
            return static_cast<const arrow::FloatArray *>(value)->Value(index);
          return static_cast<const arrow::DoubleArray *>(value)->Value(index);
        });
  });
}

irx_arrow_status irx_arrow_array_slice(const irx_arrow_array_handle *array,
                                       int64_t offset, int64_t length,
                                       irx_arrow_array_handle **out_array) {
  if (out_array)
    *out_array = nullptr;
  return array_value_operation("array_slice", [&]() -> irx_arrow_status {
    if (!out_array)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing array output");
    const auto status = validate_value_array(array);
    if (status != kArrowOk)
      return status;
    if (offset < 0 || length < 0 || offset > array->array->length() ||
        length > array->array->length() - offset)
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                       "array slice is outside its length");
    return publish_value_array(array->array->Slice(offset, length),
                               array->nullable != 0, out_array);
  });
}

irx_arrow_status irx_arrow_array_concat(const irx_arrow_array_handle *lhs,
                                        const irx_arrow_array_handle *rhs,
                                        irx_arrow_array_handle **out_array) {
  if (out_array)
    *out_array = nullptr;
  return array_value_operation("array_concat", [&]() -> irx_arrow_status {
    if (!out_array)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing array output");
    auto status = validate_value_array(lhs);
    if (status != kArrowOk)
      return status;
    status = validate_value_array(rhs);
    if (status != kArrowOk)
      return status;
    if (!lhs->array->type()->Equals(rhs->array->type(), true))
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "array concatenation requires equal element types");
    if (rhs->array->length() >
        std::numeric_limits<int64_t>::max() - lhs->array->length())
      return set_error(IRX_ARROW_STATUS_OVERFLOW, "array length overflow");
    auto result = arrow::Concatenate({lhs->array, rhs->array},
                                     irx_arrow_internal::builder_memory_pool());
    if (!result.ok())
      return set_arrow_error("array concatenation", result.status());
    return publish_value_array(*result, lhs->nullable || rhs->nullable,
                               out_array);
  });
}

irx_arrow_status irx_arrow_array_copy(const irx_arrow_array_handle *array,
                                      irx_arrow_array_handle **out_array) {
  if (out_array)
    *out_array = nullptr;
  return array_value_operation("array_copy", [&]() -> irx_arrow_status {
    if (!out_array)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing array output");
    const auto status = validate_value_array(array);
    if (status != kArrowOk)
      return status;
    // Concatenate rebuilds value and validity buffers, including for a slice.
    auto result = arrow::Concatenate({array->array},
                                     irx_arrow_internal::builder_memory_pool());
    if (!result.ok())
      return set_arrow_error("array copy", result.status());
    // Concatenate may share dictionary storage. Explicit copy must detach
    // recursively, not merely publish another independent owner token.
    if (array->type_id == IRX_ARROW_TYPE_UNKNOWN) {
      result = (*result)->CopyTo(arrow::CPUDevice::memory_manager(
          irx_arrow_internal::builder_memory_pool()));
      if (!result.ok()) return set_arrow_error("nested array copy", result.status());
    }
    return publish_value_array(*result, array->nullable != 0, out_array);
  });
}

irx_arrow_status irx_arrow_array_equal(const irx_arrow_array_handle *lhs,
                                       const irx_arrow_array_handle *rhs,
                                       int32_t *out_equal) {
  if (out_equal)
    *out_equal = 0;
  return array_value_operation("array_equal", [&]() -> irx_arrow_status {
    if (!out_equal)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing equality output");
    auto status = validate_value_array(lhs);
    if (status != kArrowOk)
      return status;
    status = validate_value_array(rhs);
    if (status != kArrowOk)
      return status;
    *out_equal = lhs->array->Equals(*rhs->array) ? 1 : 0;
    return kArrowOk;
  });
}
