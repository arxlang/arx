// Copyright IRx contributors.
// Included inside the array runtime: C++ objects remain behind typed owners.
extern "C++" {
namespace {
template <typename Operation>
irx_arrow_status descriptor_operation(const char* name, Operation operation) {
  begin_operation(name);
  try {
    if (fail_allocation_for_operation(name)) {
      return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY,
                       "injected descriptor allocation failure");
    }
    return operation();
  } catch (const std::bad_alloc&) {
    return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY,
                     "descriptor allocation failed");
  } catch (const std::exception& error) {
    return set_exception_error(name, error);
  }
}

std::shared_ptr<arrow::Field> descriptor_type_field(
    const std::shared_ptr<arrow::Field>& field) {
  // Unknown extensions are preserved by Arrow as field metadata. Ordinary
  // field metadata, its name and nullability are not part of a DataType.
  auto metadata = arrow::key_value_metadata({}, {});
  if (field->metadata()) {
    for (int64_t i = 0; i < field->metadata()->size(); ++i) {
      const auto& key = field->metadata()->key(i);
      if (key == "ARROW:extension:name" || key == "ARROW:extension:metadata") {
        metadata->Append(key, field->metadata()->value(i));
      }
    }
  }
  return arrow::field("", field->type(), false, metadata);
}
}  // namespace
}  // extern C++

irx_arrow_status irx_arrow_type_import_copy(const ArrowSchema* schema,
                                            irx_arrow_type_handle** out_value) {
  if (out_value) *out_value = nullptr;
  return descriptor_operation("type_import_copy", [&]() -> irx_arrow_status {
    if (!out_value)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing descriptor output");
    auto borrowed = borrow_schema_tree(schema);
    if (!borrowed.ok())
      return set_arrow_error("descriptor copy", borrowed.status());
    auto registered = register_storage_extensions(&(*borrowed)->schema);
    if (!registered.ok()) return set_arrow_error("extension registration", registered);
    auto field = arrow::ImportField(&(*borrowed)->schema);
    if (!field.ok())
      return set_arrow_error("descriptor import", field.status());
    auto result = make_runtime_handle<irx_arrow_type_handle>();
    result->field = descriptor_type_field(*field);
    *out_value = result.release();
    return kArrowOk;
  });
}

irx_arrow_status irx_arrow_type_export(const irx_arrow_type_handle* value,
                                       ArrowSchema* out_schema) {
  if (out_schema) std::memset(out_schema, 0, sizeof(*out_schema));
  return descriptor_operation("type_export", [&]() -> irx_arrow_status {
    if (!out_schema)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing C schema output");
    auto code = validate_handle(value, IRX_ARROW_HANDLE_KIND_TYPE, "type");
    if (code != kArrowOk) return code;
    auto status = arrow::ExportField(*value->field, out_schema);
    return status.ok() ? kArrowOk
                       : set_arrow_error("descriptor export", status);
  });
}

irx_arrow_status irx_arrow_type_retain(const irx_arrow_type_handle* value,
                                       irx_arrow_type_handle** out_value) {
  begin_operation(__func__);
  return retain_shared_handle(value, out_value, IRX_ARROW_HANDLE_KIND_TYPE,
                              "type");
}
irx_arrow_status irx_arrow_type_release(irx_arrow_type_handle** value) {
  begin_operation(__func__);
  return release_shared_handle(value, IRX_ARROW_HANDLE_KIND_TYPE, "type");
}

irx_arrow_status irx_arrow_field_import_copy(
    const ArrowSchema* schema, irx_arrow_field_handle** out_value) {
  if (out_value) *out_value = nullptr;
  return descriptor_operation("field_import_copy", [&]() -> irx_arrow_status {
    if (!out_value)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing descriptor output");
    auto borrowed = borrow_schema_tree(schema);
    if (!borrowed.ok())
      return set_arrow_error("descriptor copy", borrowed.status());
    auto registered = register_storage_extensions(&(*borrowed)->schema);
    if (!registered.ok()) return set_arrow_error("extension registration", registered);
    auto field = arrow::ImportField(&(*borrowed)->schema);
    if (!field.ok())
      return set_arrow_error("descriptor import", field.status());
    auto result = make_runtime_handle<irx_arrow_field_handle>();
    result->field = *field;
    *out_value = result.release();
    return kArrowOk;
  });
}

irx_arrow_status irx_arrow_field_export(const irx_arrow_field_handle* value,
                                        ArrowSchema* out_schema) {
  if (out_schema) std::memset(out_schema, 0, sizeof(*out_schema));
  return descriptor_operation("field_export", [&]() -> irx_arrow_status {
    if (!out_schema)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing C schema output");
    auto code = validate_handle(value, IRX_ARROW_HANDLE_KIND_FIELD, "field");
    if (code != kArrowOk) return code;
    auto status = arrow::ExportField(*value->field, out_schema);
    return status.ok() ? kArrowOk
                       : set_arrow_error("descriptor export", status);
  });
}

irx_arrow_status irx_arrow_field_retain(const irx_arrow_field_handle* value,
                                        irx_arrow_field_handle** out_value) {
  begin_operation(__func__);
  return retain_shared_handle(value, out_value, IRX_ARROW_HANDLE_KIND_FIELD,
                              "field");
}
irx_arrow_status irx_arrow_field_release(irx_arrow_field_handle** value) {
  begin_operation(__func__);
  return release_shared_handle(value, IRX_ARROW_HANDLE_KIND_FIELD, "field");
}

irx_arrow_status irx_arrow_type_equals(const irx_arrow_type_handle* left,
                                       const irx_arrow_type_handle* right,
                                       int32_t* out_equal) {
  if (out_equal) *out_equal = 0;
  return descriptor_operation("type_equals", [&]() -> irx_arrow_status {
    if (!out_equal)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing equality output");
    auto code = validate_handle(left, IRX_ARROW_HANDLE_KIND_TYPE, "type");
    if (code != kArrowOk) return code;
    code = validate_handle(right, IRX_ARROW_HANDLE_KIND_TYPE, "type");
    if (code != kArrowOk) return code;
    *out_equal = left->field->Equals(*right->field, true);
    return kArrowOk;
  });
}

irx_arrow_status irx_arrow_field_equals(const irx_arrow_field_handle* left,
                                        const irx_arrow_field_handle* right,
                                        int32_t* out_equal) {
  if (out_equal) *out_equal = 0;
  return descriptor_operation("field_equals", [&]() -> irx_arrow_status {
    if (!out_equal)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing equality output");
    auto code = validate_handle(left, IRX_ARROW_HANDLE_KIND_FIELD, "field");
    if (code != kArrowOk) return code;
    code = validate_handle(right, IRX_ARROW_HANDLE_KIND_FIELD, "field");
    if (code != kArrowOk) return code;
    *out_equal = left->field->Equals(*right->field, true);
    return kArrowOk;
  });
}

irx_arrow_status irx_arrow_schema_equals(const irx_arrow_schema_handle* left,
                                         const irx_arrow_schema_handle* right,
                                         int32_t* out_equal) {
  if (out_equal) *out_equal = 0;
  return descriptor_operation("schema_equals", [&]() -> irx_arrow_status {
    if (!out_equal)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing equality output");
    auto code = validate_handle(left, IRX_ARROW_HANDLE_KIND_SCHEMA, "schema");
    if (code != kArrowOk) return code;
    code = validate_handle(right, IRX_ARROW_HANDLE_KIND_SCHEMA, "schema");
    if (code != kArrowOk) return code;
    *out_equal = left->field->Equals(*right->field, true);
    return kArrowOk;
  });
}

irx_arrow_status irx_arrow_type_num_fields(const irx_arrow_type_handle* value,
                                           int64_t* out_count) {
  if (out_count) *out_count = 0;
  return descriptor_operation("type_num_fields", [&]() -> irx_arrow_status {
    if (!out_count)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing field count output");
    auto code = validate_handle(value, IRX_ARROW_HANDLE_KIND_TYPE, "type");
    if (code != kArrowOk) return code;

    *out_count = value->field->type()->num_fields();
    return kArrowOk;
  });
}

irx_arrow_status irx_arrow_type_field(const irx_arrow_type_handle* value,
                                      int64_t index,
                                      irx_arrow_field_handle** out_field) {
  if (out_field) *out_field = nullptr;
  return descriptor_operation("type_field", [&]() -> irx_arrow_status {
    if (!out_field)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing field output");
    auto code = validate_handle(value, IRX_ARROW_HANDLE_KIND_TYPE, "type");
    if (code != kArrowOk) return code;

    if (index < 0 || index >= value->field->type()->num_fields())
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                       "descriptor field index out of bounds");
    auto result = make_runtime_handle<irx_arrow_field_handle>();
    result->field = value->field->type()->field(static_cast<int>(index));
    *out_field = result.release();
    return kArrowOk;
  });
}

irx_arrow_status irx_arrow_schema_num_fields(
    const irx_arrow_schema_handle* value, int64_t* out_count) {
  if (out_count) *out_count = 0;
  return descriptor_operation("schema_num_fields", [&]() -> irx_arrow_status {
    if (!out_count)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing field count output");
    auto code = validate_handle(value, IRX_ARROW_HANDLE_KIND_SCHEMA, "schema");
    if (code != kArrowOk) return code;
    if (value->field->type()->id() != arrow::Type::STRUCT)
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "schema must be a struct-root descriptor");
    *out_count = value->field->type()->num_fields();
    return kArrowOk;
  });
}

irx_arrow_status irx_arrow_schema_field(const irx_arrow_schema_handle* value,
                                        int64_t index,
                                        irx_arrow_field_handle** out_field) {
  if (out_field) *out_field = nullptr;
  return descriptor_operation("schema_field", [&]() -> irx_arrow_status {
    if (!out_field)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing field output");
    auto code = validate_handle(value, IRX_ARROW_HANDLE_KIND_SCHEMA, "schema");
    if (code != kArrowOk) return code;
    if (value->field->type()->id() != arrow::Type::STRUCT)
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "schema must be a struct-root descriptor");
    if (index < 0 || index >= value->field->type()->num_fields())
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                       "descriptor field index out of bounds");
    auto result = make_runtime_handle<irx_arrow_field_handle>();
    result->field = value->field->type()->field(static_cast<int>(index));
    *out_field = result.release();
    return kArrowOk;
  });
}

irx_arrow_status irx_arrow_field_type(const irx_arrow_field_handle* value,
                                      irx_arrow_type_handle** out_type) {
  if (out_type) *out_type = nullptr;
  return descriptor_operation("field_type", [&]() -> irx_arrow_status {
    if (!out_type)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing type output");
    auto code = validate_handle(value, IRX_ARROW_HANDLE_KIND_FIELD, "field");
    if (code != kArrowOk) return code;
    auto result = make_runtime_handle<irx_arrow_type_handle>();
    result->field = descriptor_type_field(value->field);
    *out_type = result.release();
    return kArrowOk;
  });
}

irx_arrow_status irx_arrow_field_nullable(const irx_arrow_field_handle* value,
                                          int32_t* out_nullable) {
  if (out_nullable) *out_nullable = 0;
  return descriptor_operation("field_nullable", [&]() -> irx_arrow_status {
    if (!out_nullable)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing nullability output");
    auto code = validate_handle(value, IRX_ARROW_HANDLE_KIND_FIELD, "field");
    if (code != kArrowOk) return code;
    *out_nullable = value->field->nullable();
    return kArrowOk;
  });
}

irx_arrow_status irx_arrow_type_bit_width(const irx_arrow_type_handle* value,
                                          int64_t* out_width) {
  if (out_width) *out_width = -1;
  return descriptor_operation("type_bit_width", [&]() -> irx_arrow_status {
    if (!out_width)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing bit width output");
    auto code = validate_handle(value, IRX_ARROW_HANDLE_KIND_TYPE, "type");
    if (code != kArrowOk) return code;
    auto* fixed =
        dynamic_cast<const arrow::FixedWidthType*>(value->field->type().get());
    if (fixed) *out_width = fixed->bit_width();
    return kArrowOk;
  });
}

// The result is an independent malloc owner; callers release it with free.
irx_arrow_status irx_arrow_field_name_copy(const irx_arrow_field_handle* value,
                                           const char** out_name) {
  if (out_name) *out_name = nullptr;
  return descriptor_operation("field_name_copy", [&]() -> irx_arrow_status {
    if (!out_name)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing field name output");
    auto code = validate_handle(value, IRX_ARROW_HANDLE_KIND_FIELD, "field");
    if (code != kArrowOk) return code;
    const auto& name = value->field->name();
    if (name.size() == std::numeric_limits<size_t>::max())
      return set_error(IRX_ARROW_STATUS_OVERFLOW, "field name length overflow");
    auto* copy = static_cast<char*>(std::malloc(name.size() + 1));
    if (!copy)
      return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY,
                       "field name allocation failed");
    std::memcpy(copy, name.c_str(), name.size() + 1);
    *out_name = copy;
    return kArrowOk;
  });
}
