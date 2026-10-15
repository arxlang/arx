// Checked source interchange; C structures and release callbacks stay native.
extern "C++" {
namespace {
irx_arrow_status byte_array(const irx_arrow_array_handle *value) {
  auto status = validate_value_array(value);
  if (status != kArrowOk)
    return status;
  if (value->array->type_id() != arrow::Type::UINT8 ||
      value->array->null_count())
    return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                     "expected nonnullable uint8 array");
  return kArrowOk;
}
struct CDataMoveGuard {
  ArrowArray *array;
  ArrowSchema *schema;
  bool active = true;
  ~CDataMoveGuard() {
    if (!active)
      return;
    if (array->release)
      array->release(array);
    if (schema->release)
      schema->release(schema);
  }
};
} // namespace
} // extern C++

irx_arrow_status irx_arrow_c_data_retain(const irx_arrow_c_data_handle *value,
                                         irx_arrow_c_data_handle **output) {
  begin_operation(__func__);
  return retain_shared_handle(value, output, IRX_ARROW_HANDLE_KIND_C_DATA,
                              "C Data");
}
irx_arrow_status irx_arrow_c_data_release(irx_arrow_c_data_handle **value) {
  begin_operation(__func__);
  return release_shared_handle(value, IRX_ARROW_HANDLE_KIND_C_DATA, "C Data");
}
irx_arrow_status
irx_arrow_c_data_from_array(const irx_arrow_array_handle *value,
                            irx_arrow_c_data_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("c_data_from_array", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_value_array(value);
    if (status != kArrowOk)
      return status;
    auto owner = make_runtime_handle<irx_arrow_c_data_handle>();
    owner->array = value->array;
    owner->field = arrow::field("", value->array->type(), value->nullable);
    *output = owner.release();
    return kArrowOk;
  });
}
irx_arrow_status
irx_arrow_c_data_import_move(ArrowArray *array, ArrowSchema *schema,
                             irx_arrow_c_data_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("c_data_import_move", [&]() -> irx_arrow_status {
    if (!output || !array || !schema)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing C Data input or output");
    if (!array->release || !schema->release || array->length < 0 ||
        array->offset < 0 || array->null_count < -1 ||
        array->null_count > array->length || array->n_buffers < 0 ||
        array->n_children < 0 ||
        array->offset > std::numeric_limits<int64_t>::max() - array->length)
      return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT,
                       "invalid C Data header");
    // Reserve our owner before consuming the producer. Once the guard exists,
    // both live release callbacks are consumed on every success/failure path.
    auto owner = make_runtime_handle<irx_arrow_c_data_handle>();
    CDataMoveGuard guard{array, schema};
    auto registered = register_storage_extensions(schema);
    if (!registered.ok())
      return set_arrow_error("extension registration", registered);
    auto field = arrow::ImportField(schema);
    if (!field.ok())
      return set_arrow_error("C Data field", field.status());
    auto imported = arrow::ImportArray(array, (*field)->type());
    if (!imported.ok())
      return set_arrow_error("C Data array", imported.status());
    auto valid = (*imported)->ValidateFull();
    if (!valid.ok())
      return set_arrow_error("C Data validation", valid);
    if (!(*field)->nullable() && logical_null_count(**imported))
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "null data in nonnullable field");
    owner->array = *imported;
    owner->field = *field;
    *output = owner.release();
    return kArrowOk;
  });
}
irx_arrow_status irx_arrow_c_data_export(const irx_arrow_c_data_handle *value,
                                         ArrowArray *array,
                                         ArrowSchema *schema) {
  if (array)
    std::memset(array, 0, sizeof(*array));
  if (schema)
    std::memset(schema, 0, sizeof(*schema));
  return array_value_operation("c_data_export", [&]() -> irx_arrow_status {
    if (!array || !schema)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing export outputs");
    auto status =
        validate_handle(value, IRX_ARROW_HANDLE_KIND_C_DATA, "C Data");
    if (status != kArrowOk)
      return status;
    if (!value->array || !value->field)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "empty C Data owner");
    CDataMoveGuard guard{array, schema};
    auto exported = arrow::ExportArray(*value->array, array);
    if (!exported.ok())
      return set_arrow_error("C Data export", exported);
    exported = arrow::ExportField(*value->field, schema);
    if (!exported.ok())
      return set_arrow_error("C Data field export", exported);
    guard.active = false;
    return kArrowOk;
  });
}
irx_arrow_status
irx_arrow_array_from_c_data(const irx_arrow_c_data_handle *value,
                            const irx_arrow_field_handle *field,
                            irx_arrow_array_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("array_from_c_data", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status =
        validate_handle(value, IRX_ARROW_HANDLE_KIND_C_DATA, "C Data");
    if (status != kArrowOk)
      return status;
    status =
        validate_handle(field, IRX_ARROW_HANDLE_KIND_FIELD, "expected field");
    if (status != kArrowOk)
      return status;
    if (!value->array || !value->field || !field->field)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE,
                       "empty C Data or field owner");
    if (!field->field->type()->Equals(value->array->type(), true) ||
        (!field->field->nullable() && logical_null_count(*value->array)))
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "C Data differs from expected array type");
    // Array values have a datatype and validity, not a top-level field name or
    // metadata. The original carrier still owns and exports the complete field.
    return publish_value_array(value->array, field->field->nullable(), output);
  });
}
irx_arrow_status
irx_arrow_array_with_validity(const irx_arrow_array_handle *value,
                              const irx_arrow_array_handle *bitmap,
                              int64_t offset, irx_arrow_array_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation(
      "array_with_validity", [&]() -> irx_arrow_status {
        if (!output)
          return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
        auto status = validate_value_array(value);
        if (status != kArrowOk)
          return status;
        status = byte_array(bitmap);
        if (status != kArrowOk)
          return status;
        int64_t count = value->array->length();
        if (offset < 0 || offset > std::numeric_limits<int64_t>::max() - count)
          return set_error(IRX_ARROW_STATUS_OVERFLOW, "invalid bitmap extent");
        int64_t end = offset + count;
        int64_t required = end / 8 + (end % 8 != 0);
        if (required > bitmap->array->length())
          return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT,
                           "validity bitmap is too short");
        const auto &bits =
            static_cast<const arrow::UInt8Array &>(*bitmap->array);
        irx_arrow_array_builder_handle builder;
        builder.logical_type = value->array->type();
        for (int64_t i = 0; i < count; ++i) {
          if (!((bits.Value((offset + i) / 8) >> ((offset + i) % 8)) & 1)) {
            builder.values.push_back(
                arrow::MakeNullScalar(builder.logical_type));
            continue;
          }
          auto scalar = extract_logical_scalar(*value->array, i);
          if (!scalar.ok())
            return set_arrow_error("validity scalar", scalar.status());
          builder.values.push_back(*scalar);
        }
        return build_logical_array(&builder, true, output);
      });
}
irx_arrow_status irx_arrow_array_from_buffers(
    const irx_arrow_field_handle *field, const irx_arrow_array_handle *data,
    const irx_arrow_array_handle *bitmap, int64_t length, int64_t offset,
    irx_arrow_array_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("array_from_buffers", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_handle(field, IRX_ARROW_HANDLE_KIND_FIELD, "field");
    if (status != kArrowOk)
      return status;
    status = byte_array(data);
    if (status != kArrowOk)
      return status;
    status = byte_array(bitmap);
    if (status != kArrowOk)
      return status;
    if (!field->field)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing field");
    auto type =
        std::dynamic_pointer_cast<arrow::FixedWidthType>(field->field->type());
    if (!type)
      return set_error(
          IRX_ARROW_STATUS_NOT_SUPPORTED,
          "raw buffers require fixed-width or packed Boolean storage");
    int64_t width = type->bit_width();
    if (length < 0 || offset < 0 || width <= 0 ||
        length > std::numeric_limits<int64_t>::max() - offset ||
        length + offset > std::numeric_limits<int64_t>::max() / width)
      return set_error(IRX_ARROW_STATUS_OVERFLOW, "invalid buffer extent");
    int64_t bits = (length + offset) * width;
    int64_t bytes = bits / 8 + (bits % 8 != 0);
    int64_t validity_bytes =
        (length + offset) / 8 + ((length + offset) % 8 != 0);
    if (bytes > data->array->length() ||
        (bitmap->array->length() && validity_bytes > bitmap->array->length()))
      return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT,
                       "data or validity buffer is too short");
    const auto &raw = static_cast<const arrow::UInt8Array &>(*data->array);
    auto allocated =
        arrow::AllocateBuffer(bytes, irx_arrow_internal::builder_memory_pool());
    if (!allocated.ok())
      return set_arrow_error("buffer copy", allocated.status());
    std::shared_ptr<arrow::Buffer> copied = std::move(*allocated);
    if (bytes)
      std::memcpy(copied->mutable_data(), raw.raw_values(), bytes);
    std::shared_ptr<arrow::Buffer> validity;
    if (bitmap->array->length()) {
      auto allocated_bits = arrow::AllocateBuffer(
          validity_bytes, irx_arrow_internal::builder_memory_pool());
      if (!allocated_bits.ok())
        return set_arrow_error("bitmap copy", allocated_bits.status());
      validity = std::move(*allocated_bits);
      if (validity_bytes)
        std::memcpy(
            validity->mutable_data(),
            static_cast<const arrow::UInt8Array &>(*bitmap->array).raw_values(),
            validity_bytes);
    }
    auto array = arrow::MakeArray(arrow::ArrayData::Make(
        type, length, {validity, copied},
        validity ? arrow::kUnknownNullCount : 0, offset));
    if (!field->field->nullable() && logical_null_count(*array))
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "null bitmap for nonnullable array");
    return publish_value_array(std::move(array), field->field->nullable(),
                               output);
  });
}
