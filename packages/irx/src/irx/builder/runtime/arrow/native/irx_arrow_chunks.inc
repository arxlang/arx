// Reusable primitive builders and immutable logical chunk sequences.
extern "C++" {
namespace {
irx_arrow_status validate_chunks(const irx_arrow_chunked_array_handle *value) {
  auto status = validate_handle(value, IRX_ARROW_HANDLE_KIND_CHUNKED_ARRAY,
                                "chunked array");
  if (status != kArrowOk)
    return status;
  if (!value->column)
    return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing chunked array");
  return kArrowOk;
}
irx_arrow_status publish_chunks(std::shared_ptr<arrow::ChunkedArray> value,
                                bool nullable,
                                irx_arrow_chunked_array_handle **output) {
  auto owner = make_runtime_handle<irx_arrow_chunked_array_handle>();
  owner->column = std::move(value);
  owner->nullable = nullable;
  *output = owner.release();
  return kArrowOk;
}
template <typename Value, typename Extract>
irx_arrow_status chunk_scalar(const irx_arrow_chunked_array_handle *value,
                              int64_t index, int32_t *valid, Value *output,
                              Extract extract) {
  if (valid)
    *valid = 0;
  if (output)
    *output = 0;
  if (!valid || !output)
    return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing scalar output");
  auto status = validate_chunks(value);
  if (status != kArrowOk)
    return status;
  if (index < 0 || index >= value->column->length())
    return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                     "chunked array index is outside its length");
  for (const auto &chunk : value->column->chunks()) {
    if (index >= chunk->length()) {
      index -= chunk->length();
      continue;
    }
    // A scoped borrowed wrapper, not an additional native ownership token.
    irx_arrow_array_handle borrowed;
    borrowed.array = chunk;
    status = populate_array_metadata(
        &borrowed, resolved_from_arrow_type(chunk->type(), value->nullable));
    if (status != kArrowOk)
      return status;
    return extract(&borrowed, index, valid, output);
  }
  return set_error(IRX_ARROW_STATUS_INTERNAL, "inconsistent chunk lengths");
}
} // namespace
} // extern C++

irx_arrow_status
irx_arrow_array_builder_reserve(irx_arrow_array_builder_handle *builder,
                                int64_t additional) {
  return array_value_operation(
      "array_builder_reserve", [&]() -> irx_arrow_status {
        auto status = validate_handle(
            builder, IRX_ARROW_HANDLE_KIND_ARRAY_BUILDER, "array builder");
        if (status != kArrowOk)
          return status;
        if (additional < 0)
          return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT,
                           "negative reserve");
        if (builder->logical_type) {
          if (static_cast<uint64_t>(additional) > builder->values.max_size() - builder->values.size())
            return set_error(IRX_ARROW_STATUS_OVERFLOW, "builder capacity overflow");
          builder->values.reserve(builder->values.size() + static_cast<size_t>(additional));
          return kArrowOk;
        }
        if (additional >
            std::numeric_limits<int64_t>::max() - builder->builder->length())
          return set_error(IRX_ARROW_STATUS_OVERFLOW,
                           "builder length overflow");
        auto result = builder->builder->Reserve(additional);
        return result.ok() ? kArrowOk
                           : set_arrow_error("builder reserve", result);
      });
}
irx_arrow_status
irx_arrow_array_builder_length(const irx_arrow_array_builder_handle *builder,
                               int64_t *out_length) {
  if (out_length)
    *out_length = 0;
  return array_value_operation(
      "array_builder_length", [&]() -> irx_arrow_status {
        if (!out_length)
          return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                           "missing length output");
        auto status = validate_handle(
            builder, IRX_ARROW_HANDLE_KIND_ARRAY_BUILDER, "array builder");
        if (status != kArrowOk)
          return status;
        *out_length = builder->logical_type ? static_cast<int64_t>(builder->values.size()) : builder->builder->length();
        return kArrowOk;
      });
}
irx_arrow_status
irx_arrow_array_builder_build(irx_arrow_array_builder_handle *builder,
                              int32_t nullable,
                              irx_arrow_array_handle **out_array) {
  if (out_array)
    *out_array = nullptr;
  return array_value_operation(
      "array_builder_build", [&]() -> irx_arrow_status {
        if (!out_array)
          return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                           "missing array output");
        auto status = validate_handle(
            builder, IRX_ARROW_HANDLE_KIND_ARRAY_BUILDER, "array builder");
        if (status != kArrowOk)
          return status;
        if (nullable != 0 && nullable != 1)
          return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT,
                           "invalid nullability");
        if (builder->logical_type) return build_logical_array(builder, nullable, out_array);
        if (!nullable && builder->builder->null_count())
          return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                           "nulls in nonnullable array");
        auto owner = make_runtime_handle<irx_arrow_array_handle>();
        auto result = builder->builder->Finish(&owner->array);
        if (!result.ok())
          return set_arrow_error("builder finish", result);
        status = populate_array_metadata(
            owner.get(),
            resolved_from_arrow_type(owner->array->type(), nullable != 0));
        if (status != kArrowOk)
          return status;
        // SnapshotPrimitiveBuilder does not mutate on Finish, so reset only
        // after metadata and the independent output owner are ready.
        builder->builder->Reset();
        *out_array = owner.release();
        return kArrowOk;
      });
}

irx_arrow_status
irx_arrow_chunked_new(int32_t type_id, int32_t nullable, const void **chunks,
                      int64_t count,
                      irx_arrow_chunked_array_handle **out_value) {
  if (out_value)
    *out_value = nullptr;
  return array_value_operation("chunked_new", [&]() -> irx_arrow_status {
    if (!out_value || (count && !chunks))
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing chunks or output");
    if (count < 0 || count > std::numeric_limits<int32_t>::max() ||
        (nullable != 0 && nullable != 1))
      return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT,
                       "invalid chunk count or nullability");
    const auto *spec = type_spec_from_type_id(type_id);
    if (!spec)
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "unsupported chunk element");
    arrow::ArrayVector arrays;
    arrays.reserve(static_cast<size_t>(count));
    int64_t length = 0;
    for (int64_t index = 0; index < count; ++index) {
      const auto *chunk =
          static_cast<const irx_arrow_array_handle *>(chunks[index]);
      auto status = validate_value_array(chunk);
      if (status != kArrowOk)
        return status;
      if (chunk->type_id != type_id ||
          (!nullable && chunk->array->null_count()))
        return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH, "incompatible chunk");
      if (chunk->array->length() > std::numeric_limits<int64_t>::max() - length)
        return set_error(IRX_ARROW_STATUS_OVERFLOW, "chunked length overflow");
      length += chunk->array->length();
      arrays.push_back(chunk->array);
    }
    auto value =
        arrow::ChunkedArray::Make(std::move(arrays), spec->make_type());
    if (!value.ok())
      return set_arrow_error("chunked construction", value.status());
    return publish_chunks(*value, nullable != 0, out_value);
  });
}

irx_arrow_status
irx_arrow_chunked_length(const irx_arrow_chunked_array_handle *value,
                         int64_t *output) {
  if (output)
    *output = 0;
  return array_value_operation("chunked_length", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_chunks(value);
    if (status != kArrowOk)
      return status;
    *output = value->column->length();
    return kArrowOk;
  });
}

irx_arrow_status
irx_arrow_chunked_null_count(const irx_arrow_chunked_array_handle *value,
                             int64_t *output) {
  if (output)
    *output = 0;
  return array_value_operation("chunked_null_count", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_chunks(value);
    if (status != kArrowOk)
      return status;
    *output = logical_null_count(*value->column);
    return kArrowOk;
  });
}

irx_arrow_status
irx_arrow_chunked_num_chunks(const irx_arrow_chunked_array_handle *value,
                             int64_t *output) {
  if (output)
    *output = 0;
  return array_value_operation("chunked_num_chunks", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_chunks(value);
    if (status != kArrowOk)
      return status;
    *output = value->column->num_chunks();
    return kArrowOk;
  });
}

irx_arrow_status
irx_arrow_chunked_get_int(const irx_arrow_chunked_array_handle *value,
                          int64_t index, int32_t *valid, int64_t *output) {
  if (valid)
    *valid = 0;
  if (output)
    *output = 0;
  return array_value_operation("chunked_get_int", [&]() {
    return chunk_scalar(value, index, valid, output, irx_arrow_array_get_int);
  });
}

irx_arrow_status
irx_arrow_chunked_get_uint(const irx_arrow_chunked_array_handle *value,
                           int64_t index, int32_t *valid, uint64_t *output) {
  if (valid)
    *valid = 0;
  if (output)
    *output = 0;
  return array_value_operation("chunked_get_uint", [&]() {
    return chunk_scalar(value, index, valid, output, irx_arrow_array_get_uint);
  });
}

irx_arrow_status
irx_arrow_chunked_get_double(const irx_arrow_chunked_array_handle *value,
                             int64_t index, int32_t *valid, double *output) {
  if (valid)
    *valid = 0;
  if (output)
    *output = 0;
  return array_value_operation("chunked_get_double", [&]() {
    return chunk_scalar(value, index, valid, output,
                        irx_arrow_array_get_double);
  });
}
irx_arrow_status
irx_arrow_chunked_chunk(const irx_arrow_chunked_array_handle *value,
                        int64_t index, irx_arrow_array_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("chunked_chunk", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_chunks(value);
    if (status != kArrowOk)
      return status;
    if (index < 0 || index >= value->column->num_chunks())
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                       "chunk index out of bounds");
    return publish_value_array(value->column->chunk(static_cast<int>(index)),
                               value->nullable, output);
  });
}
irx_arrow_status
irx_arrow_chunked_combine(const irx_arrow_chunked_array_handle *value,
                          irx_arrow_array_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("chunked_combine", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_chunks(value);
    if (status != kArrowOk)
      return status;
    auto combined =
        value->column->num_chunks() == 0
            ? arrow::MakeArrayOfNull(value->column->type(), 0,
                                     irx_arrow_internal::builder_memory_pool())
            : arrow::Concatenate(value->column->chunks(),
                                 irx_arrow_internal::builder_memory_pool());
    if (!combined.ok())
      return set_arrow_error("combine chunks", combined.status());
    return publish_value_array(*combined, value->nullable, output);
  });
}
irx_arrow_status
irx_arrow_chunked_slice(const irx_arrow_chunked_array_handle *value,
                        int64_t offset, int64_t length,
                        irx_arrow_chunked_array_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("chunked_slice", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_chunks(value);
    if (status != kArrowOk)
      return status;
    if (offset < 0 || length < 0 || offset > value->column->length() ||
        length > value->column->length() - offset)
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                       "chunked slice out of bounds");
    return publish_chunks(value->column->Slice(offset, length), value->nullable,
                          output);
  });
}
irx_arrow_status
irx_arrow_chunked_concat(const irx_arrow_chunked_array_handle *lhs,
                         const irx_arrow_chunked_array_handle *rhs,
                         irx_arrow_chunked_array_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("chunked_concat", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_chunks(lhs);
    if (status != kArrowOk)
      return status;
    status = validate_chunks(rhs);
    if (status != kArrowOk)
      return status;
    if (!lhs->column->type()->Equals(rhs->column->type(), true))
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "incompatible chunk types");
    if (rhs->column->length() >
            std::numeric_limits<int64_t>::max() - lhs->column->length() ||
        rhs->column->num_chunks() >
            std::numeric_limits<int32_t>::max() - lhs->column->num_chunks())
      return set_error(IRX_ARROW_STATUS_OVERFLOW, "chunked length overflow");
    auto arrays = lhs->column->chunks();
    arrays.insert(arrays.end(), rhs->column->chunks().begin(),
                  rhs->column->chunks().end());
    auto result =
        arrow::ChunkedArray::Make(std::move(arrays), lhs->column->type());
    if (!result.ok())
      return set_arrow_error("chunked concat", result.status());
    return publish_chunks(*result, lhs->nullable || rhs->nullable, output);
  });
}
irx_arrow_status
irx_arrow_chunked_copy(const irx_arrow_chunked_array_handle *value,
                       irx_arrow_chunked_array_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("chunked_copy", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_chunks(value);
    if (status != kArrowOk)
      return status;
    arrow::ArrayVector copies;
    for (const auto &chunk : value->column->chunks()) {
      auto copy = arrow::Concatenate({chunk},
                                     irx_arrow_internal::builder_memory_pool());
      if (!copy.ok())
        return set_arrow_error("chunk copy", copy.status());
      if (!type_spec_from_arrow_type_id(chunk->type_id())) {
        copy = (*copy)->CopyTo(arrow::CPUDevice::memory_manager(
            irx_arrow_internal::builder_memory_pool()));
        if (!copy.ok()) return set_arrow_error("nested chunk copy", copy.status());
      }
      copies.push_back(*copy);
    }
    auto result =
        arrow::ChunkedArray::Make(std::move(copies), value->column->type());
    if (!result.ok())
      return set_arrow_error("chunked copy", result.status());
    return publish_chunks(*result, value->nullable, output);
  });
}
irx_arrow_status
irx_arrow_chunked_equal(const irx_arrow_chunked_array_handle *lhs,
                        const irx_arrow_chunked_array_handle *rhs,
                        int32_t *output) {
  if (output)
    *output = 0;
  return array_value_operation("chunked_equal", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_chunks(lhs);
    if (status != kArrowOk)
      return status;
    status = validate_chunks(rhs);
    if (status != kArrowOk)
      return status;
    *output = lhs->column->Equals(*rhs->column) ? 1 : 0;
    return kArrowOk;
  });
}
