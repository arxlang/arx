// Opaque logical scalars and transactional descriptor-driven builders.
extern "C++" {
namespace {
template <typename Scalar>
arrow::Result<std::shared_ptr<arrow::Scalar>>
parse_decimal_scalar(const std::shared_ptr<arrow::DataType> &type,
                     std::string_view text) {
  using Decimal = typename Scalar::ValueType;
  Decimal value;
  int32_t precision = 0, scale = 0;
  ARROW_RETURN_NOT_OK(Decimal::FromString(text, &value, &precision, &scale));
  const auto &target = static_cast<const arrow::DecimalType &>(*type);
  ARROW_ASSIGN_OR_RAISE(auto adjusted, value.Rescale(scale, target.scale()));
  if (!adjusted.FitsInPrecision(target.precision()))
    return arrow::Status::Invalid("decimal value exceeds declared precision");
  return std::make_shared<Scalar>(adjusted, type);
}
arrow::Result<std::shared_ptr<arrow::Scalar>>
parse_logical_scalar(const std::shared_ptr<arrow::DataType> &type,
                     std::string_view text) {
  // Arrow's Scalar::Parse does not implement the view families. Construct
  // those with owned, length-delimited bytes; ValidateFull checks UTF-8.
  if (type->id() == arrow::Type::STRING_VIEW ||
      type->id() == arrow::Type::BINARY_VIEW) {
    ARROW_ASSIGN_OR_RAISE(
        auto buffer,
        arrow::AllocateBuffer(static_cast<int64_t>(text.size()),
                              irx_arrow_internal::builder_memory_pool()));
    if (!text.empty())
      std::memcpy(buffer->mutable_data(), text.data(), text.size());
    std::shared_ptr<arrow::Buffer> owned = std::move(buffer);
    if (type->id() == arrow::Type::STRING_VIEW)
      return std::make_shared<arrow::StringViewScalar>(std::move(owned));
    return std::make_shared<arrow::BinaryViewScalar>(std::move(owned));
  }
  if (type->id() == arrow::Type::HALF_FLOAT) {
    ARROW_ASSIGN_OR_RAISE(auto parsed,
                          arrow::Scalar::Parse(arrow::float64(), text));
    auto value = static_cast<const arrow::DoubleScalar &>(*parsed).value;
    return std::make_shared<arrow::HalfFloatScalar>(
        arrow::util::Float16::FromDouble(value).bits());
  }
  switch (type->id()) {
  case arrow::Type::DECIMAL32:
    return parse_decimal_scalar<arrow::Decimal32Scalar>(type, text);
  case arrow::Type::DECIMAL64:
    return parse_decimal_scalar<arrow::Decimal64Scalar>(type, text);
  case arrow::Type::DECIMAL128:
    return parse_decimal_scalar<arrow::Decimal128Scalar>(type, text);
  case arrow::Type::DECIMAL256:
    return parse_decimal_scalar<arrow::Decimal256Scalar>(type, text);
  default:
    return arrow::Scalar::Parse(type, text);
  }
}
arrow::Result<std::shared_ptr<arrow::Scalar>>
extract_logical_scalar(const arrow::Array &array, int64_t index) {
  if (array.type_id() != arrow::Type::EXTENSION)
    return array.GetScalar(index);
  // Arrow's extension extraction can derive validity from the parent bitmap,
  // which is absent for union/run-end storage. Preserve storage validity
  // instead.
  const auto &extension = static_cast<const arrow::ExtensionArray &>(array);
  ARROW_ASSIGN_OR_RAISE(auto storage,
                        extract_logical_scalar(*extension.storage(), index));
  return std::make_shared<arrow::ExtensionScalar>(storage, array.type(),
                                                  storage->is_valid);
}
irx_arrow_status validate_scalar(const irx_arrow_scalar_handle *value) {
  auto status = validate_handle(value, IRX_ARROW_HANDLE_KIND_SCALAR, "scalar");
  if (status != kArrowOk)
    return status;
  if (!value->scalar || !value->scalar->is_valid)
    return set_error(IRX_ARROW_STATUS_INVALID_STATE,
                     "scalar owner has no present value");
  return kArrowOk;
}
irx_arrow_status publish_scalar(std::shared_ptr<arrow::Scalar> value,
                                irx_arrow_scalar_handle **output) {
  auto valid = value->ValidateFull();
  if (!valid.ok())
    return set_arrow_error("scalar validation", valid);
  // Null is a nullable owner niche; no owner token is created for an absent
  // value.
  if (!value->is_valid)
    return kArrowOk;
  auto owner = make_runtime_handle<irx_arrow_scalar_handle>();
  owner->scalar = std::move(value);
  *output = owner.release();
  return kArrowOk;
}
irx_arrow_status scalar_type(const irx_arrow_type_handle *type) {
  auto status = validate_handle(type, IRX_ARROW_HANDLE_KIND_TYPE, "datatype");
  if (status != kArrowOk)
    return status;
  if (!type->field)
    return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing datatype");
  return kArrowOk;
}
irx_arrow_status append_logical_nulls(irx_arrow_array_builder_handle *builder,
                                      int64_t count) {
  return array_value_operation(
      "array_builder_append", [&]() -> irx_arrow_status {
        if (count < 0 ||
            static_cast<uint64_t>(count) >
                builder->values.max_size() - builder->values.size())
          return set_error(IRX_ARROW_STATUS_OVERFLOW,
                           "builder length overflow");
        auto value = arrow::MakeNullScalar(builder->logical_type);
        builder->values.insert(builder->values.end(),
                               static_cast<size_t>(count), std::move(value));
        return kArrowOk;
      });
}
irx_arrow_status build_logical_array(irx_arrow_array_builder_handle *builder,
                                     bool nullable,
                                     irx_arrow_array_handle **output) {
  arrow::ArrayVector arrays;
  arrays.reserve(builder->values.size());
  for (const auto &value : builder->values) {
    if (!nullable && !value->is_valid)
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "nulls in nonnullable array");
    auto item = arrow::MakeArrayFromScalar(
        *value, 1, irx_arrow_internal::builder_memory_pool());
    if (!item.ok())
      return set_arrow_error("scalar array", item.status());
    arrays.push_back(*item);
  }
  auto result =
      arrays.empty()
          ? arrow::MakeArrayOfNull(builder->logical_type, 0,
                                   irx_arrow_internal::builder_memory_pool())
          : arrow::Concatenate(arrays,
                               irx_arrow_internal::builder_memory_pool());
  if (!result.ok())
    return set_arrow_error("logical builder finish", result.status());
  auto status = publish_value_array(*result, nullable, output);
  if (status == kArrowOk)
    builder->values.clear();
  return status;
}
} // namespace
} // extern C++

irx_arrow_status irx_arrow_scalar_retain(const irx_arrow_scalar_handle *value,
                                         irx_arrow_scalar_handle **output) {
  begin_operation(__func__);
  return retain_shared_handle(value, output, IRX_ARROW_HANDLE_KIND_SCALAR,
                              "scalar");
}
irx_arrow_status irx_arrow_scalar_release(irx_arrow_scalar_handle **value) {
  begin_operation(__func__);
  return release_shared_handle(value, IRX_ARROW_HANDLE_KIND_SCALAR, "scalar");
}
irx_arrow_status irx_arrow_scalar_parse(const irx_arrow_type_handle *type,
                                        const char *text,
                                        irx_arrow_scalar_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("scalar_parse", [&]() -> irx_arrow_status {
    if (!text || !output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing scalar text or output");
    auto status = scalar_type(type);
    if (status != kArrowOk)
      return status;
    auto result = parse_logical_scalar(type->field->type(), text);
    if (!result.ok())
      return set_arrow_error("scalar parse", result.status());
    return publish_scalar(*result, output);
  });
}
irx_arrow_status
irx_arrow_scalar_from_array(const irx_arrow_type_handle *type,
                            const irx_arrow_array_handle *value,
                            irx_arrow_scalar_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("scalar_from_array", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing scalar output");
    auto status = scalar_type(type);
    if (status != kArrowOk)
      return status;
    status = validate_value_array(value);
    if (status != kArrowOk)
      return status;
    const auto &target = type->field->type();
    if (target->num_fields() != 1 ||
        !target->field(0)->type()->Equals(value->array->type(), true) ||
        (!target->field(0)->nullable() && logical_null_count(*value->array)))
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "list scalar child mismatch");
    std::shared_ptr<arrow::Scalar> result;
    switch (target->id()) {
    case arrow::Type::LIST:
      result = std::make_shared<arrow::ListScalar>(value->array, target);
      break;
    case arrow::Type::LARGE_LIST:
      result = std::make_shared<arrow::LargeListScalar>(value->array, target);
      break;
    case arrow::Type::LIST_VIEW:
      result = std::make_shared<arrow::ListViewScalar>(value->array, target);
      break;
    case arrow::Type::LARGE_LIST_VIEW:
      result =
          std::make_shared<arrow::LargeListViewScalar>(value->array, target);
      break;
    case arrow::Type::MAP:
      result = std::make_shared<arrow::MapScalar>(value->array, target);
      break;
    case arrow::Type::FIXED_SIZE_LIST:
      if (value->array->length() !=
          static_cast<const arrow::FixedSizeListType &>(*target).list_size())
        return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT,
                         "fixed list length mismatch");
      result =
          std::make_shared<arrow::FixedSizeListScalar>(value->array, target);
      break;
    default:
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "expected list or map datatype");
    }
    return publish_scalar(std::move(result), output);
  });
}
irx_arrow_status
irx_arrow_scalar_from_fields(const irx_arrow_type_handle *type,
                             const void **values, int64_t count,
                             irx_arrow_scalar_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("scalar_from_fields", [&]() -> irx_arrow_status {
    if (!output || (count && !values))
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing scalar fields or output");
    auto status = scalar_type(type);
    if (status != kArrowOk)
      return status;
    auto target = type->field->type();
    if (target->id() != arrow::Type::STRUCT || count != target->num_fields())
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "struct scalar field count mismatch");
    arrow::ScalarVector children;
    for (int64_t i = 0; i < count; ++i) {
      auto field = target->field(static_cast<int>(i));
      const auto *child =
          static_cast<const irx_arrow_scalar_handle *>(values[i]);
      if (!child) {
        if (!field->nullable())
          return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                           "null nonnullable scalar field");
        children.push_back(arrow::MakeNullScalar(field->type()));
        continue;
      }
      status = validate_scalar(child);
      if (status != kArrowOk)
        return status;
      if (!field->type()->Equals(child->scalar->type, true))
        return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                         "scalar field type mismatch");
      children.push_back(child->scalar);
    }
    return publish_scalar(
        std::make_shared<arrow::StructScalar>(std::move(children), target),
        output);
  });
}
irx_arrow_status irx_arrow_scalar_dictionary(
    const irx_arrow_type_handle *type, const irx_arrow_scalar_handle *index,
    const irx_arrow_array_handle *values, irx_arrow_scalar_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("scalar_dictionary", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = scalar_type(type);
    if (status != kArrowOk)
      return status;
    status = validate_scalar(index);
    if (status != kArrowOk)
      return status;
    status = validate_value_array(values);
    if (status != kArrowOk)
      return status;
    auto target = type->field->type();
    if (target->id() != arrow::Type::DICTIONARY)
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "expected dictionary datatype");
    const auto &dictionary =
        static_cast<const arrow::DictionaryType &>(*target);
    if (!dictionary.index_type()->Equals(index->scalar->type, true) ||
        !dictionary.value_type()->Equals(values->array->type(), true))
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "dictionary scalar storage mismatch");
    return publish_scalar(
        std::make_shared<arrow::DictionaryScalar>(
            arrow::DictionaryScalar::ValueType{index->scalar, values->array},
            target),
        output);
  });
}
irx_arrow_status irx_arrow_scalar_wrap(const irx_arrow_type_handle *type,
                                       const irx_arrow_scalar_handle *value,
                                       irx_arrow_scalar_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("scalar_wrap", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = scalar_type(type);
    if (status != kArrowOk)
      return status;
    status = validate_scalar(value);
    if (status != kArrowOk)
      return status;
    auto target = type->field->type();
    if (target->id() == arrow::Type::EXTENSION) {
      const auto &extension =
          static_cast<const arrow::ExtensionType &>(*target);
      if (!extension.storage_type()->Equals(value->scalar->type, true))
        return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                         "extension storage mismatch");
      return publish_scalar(
          std::make_shared<arrow::ExtensionScalar>(value->scalar, target),
          output);
    }
    if (target->id() != arrow::Type::RUN_END_ENCODED ||
        !target->field(1)->type()->Equals(value->scalar->type, true))
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "wrapped scalar type mismatch");
    return publish_scalar(
        std::make_shared<arrow::RunEndEncodedScalar>(value->scalar, target),
        output);
  });
}

irx_arrow_status irx_arrow_scalar_storage(const irx_arrow_scalar_handle *value,
                                          irx_arrow_scalar_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("scalar_storage", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_scalar(value);
    if (status != kArrowOk)
      return status;
    if (value->scalar->type->id() == arrow::Type::EXTENSION)
      return publish_scalar(
          static_cast<const arrow::ExtensionScalar &>(*value->scalar).value,
          output);
    if (value->scalar->type->id() == arrow::Type::RUN_END_ENCODED)
      return publish_scalar(
          static_cast<const arrow::RunEndEncodedScalar &>(*value->scalar).value,
          output);
    return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                     "expected extension or run-end scalar");
  });
}
irx_arrow_status irx_arrow_scalar_union(const irx_arrow_type_handle *type,
                                        const char *name,
                                        const irx_arrow_scalar_handle *value,
                                        irx_arrow_scalar_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("scalar_union", [&]() -> irx_arrow_status {
    if (!output || !name)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing output or field name");
    auto status = scalar_type(type);
    if (status != kArrowOk)
      return status;
    status = validate_scalar(value);
    if (status != kArrowOk)
      return status;
    auto target = type->field->type();
    if (target->id() != arrow::Type::DENSE_UNION &&
        target->id() != arrow::Type::SPARSE_UNION)
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "expected union datatype");
    const auto &union_type = static_cast<const arrow::UnionType &>(*target);
    int index = -1;
    for (int i = 0; i < target->num_fields(); ++i)
      if (target->field(i)->name() == name) {
        index = i;
        break;
      }
    if (index < 0 ||
        !target->field(index)->type()->Equals(value->scalar->type, true))
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "union scalar field mismatch");
    auto result =
        target->id() == arrow::Type::DENSE_UNION
            ? std::shared_ptr<arrow::Scalar>(
                  std::make_shared<arrow::DenseUnionScalar>(
                      value->scalar, union_type.type_codes()[index], target))
            : arrow::SparseUnionScalar::FromValue(value->scalar, index, target);
    return publish_scalar(std::move(result), output);
  });
}
irx_arrow_status irx_arrow_scalar_interval(const irx_arrow_type_handle *type,
                                           const int64_t *values, int64_t count,
                                           irx_arrow_scalar_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("scalar_interval", [&]() -> irx_arrow_status {
    if (!output || !values)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing interval values or output");
    auto status = scalar_type(type);
    if (status != kArrowOk)
      return status;
    auto id = type->field->type()->id();
    int required = id == arrow::Type::INTERVAL_MONTHS           ? 1
                   : id == arrow::Type::INTERVAL_DAY_TIME       ? 2
                   : id == arrow::Type::INTERVAL_MONTH_DAY_NANO ? 3
                                                                : 0;
    if (!required || count != required)
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "interval component count mismatch");
    for (int i = 0; i < std::min(required, 2); ++i)
      if (values[i] < std::numeric_limits<int32_t>::min() ||
          values[i] > std::numeric_limits<int32_t>::max())
        return set_error(IRX_ARROW_STATUS_OVERFLOW,
                         "interval component overflow");
    std::shared_ptr<arrow::Scalar> result;
    if (required == 1)
      result = std::make_shared<arrow::MonthIntervalScalar>(
          static_cast<int32_t>(values[0]));
    if (required == 2)
      result = std::make_shared<arrow::DayTimeIntervalScalar>(
          arrow::DayTimeIntervalType::DayMilliseconds{
              static_cast<int32_t>(values[0]),
              static_cast<int32_t>(values[1])});
    if (required == 3)
      result = std::make_shared<arrow::MonthDayNanoIntervalScalar>(
          arrow::MonthDayNanoIntervalType::MonthDayNanos{
              static_cast<int32_t>(values[0]), static_cast<int32_t>(values[1]),
              values[2]});
    return publish_scalar(std::move(result), output);
  });
}
irx_arrow_status irx_arrow_scalar_equal(const irx_arrow_scalar_handle *left,
                                        const irx_arrow_scalar_handle *right,
                                        int32_t *output) {
  if (output)
    *output = 0;
  return array_value_operation("scalar_equal", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing equality output");
    auto status = validate_scalar(left);
    if (status != kArrowOk)
      return status;
    status = validate_scalar(right);
    if (status != kArrowOk)
      return status;
    if (!left->scalar->type->Equals(right->scalar->type, true))
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "scalar equality type mismatch");
    *output = left->scalar->Equals(*right->scalar);
    return kArrowOk;
  });
}
irx_arrow_status irx_arrow_scalar_text(const irx_arrow_scalar_handle *value,
                                       const char **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("scalar_text", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing string output");
    auto status = validate_scalar(value);
    if (status != kArrowOk)
      return status;
    auto text = value->scalar->ToString();
    if (text.find('\0') != std::string::npos)
      return set_error(IRX_ARROW_STATUS_NOT_SUPPORTED,
                       "embedded NUL cannot be represented by an Arx string");
    auto result = static_cast<char *>(std::malloc(text.size() + 1));
    if (!result)
      return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY,
                       "scalar string allocation failed");
    std::memcpy(result, text.c_str(), text.size() + 1);
    *output = result;
    return kArrowOk;
  });
}
irx_arrow_status irx_arrow_scalar_values(const irx_arrow_scalar_handle *value,
                                         irx_arrow_array_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("scalar_values", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_scalar(value);
    if (status != kArrowOk)
      return status;
    auto list = std::dynamic_pointer_cast<arrow::BaseListScalar>(value->scalar);
    if (!list)
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "expected list or map scalar");
    return publish_value_array(list->value, list->type->field(0)->nullable(),
                               output);
  });
}
irx_arrow_status irx_arrow_scalar_field(const irx_arrow_scalar_handle *value,
                                        const char *name,
                                        irx_arrow_scalar_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("scalar_field", [&]() -> irx_arrow_status {
    if (!output || !name)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing name or output");
    auto status = validate_scalar(value);
    if (status != kArrowOk)
      return status;
    auto object = std::dynamic_pointer_cast<arrow::StructScalar>(value->scalar);
    if (!object)
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "expected struct scalar");
    auto field = object->field(name);
    if (!field.ok())
      return set_arrow_error("scalar field", field.status());
    return publish_scalar(*field, output);
  });
}
irx_arrow_status irx_arrow_array_get_scalar(const irx_arrow_array_handle *value,
                                            int64_t index,
                                            irx_arrow_scalar_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("array_get_scalar", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing scalar output");
    auto status = validate_value_array(value);
    if (status != kArrowOk)
      return status;
    if (index < 0 || index >= value->array->length())
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                       "array scalar index out of bounds");
    auto result = extract_logical_scalar(*value->array, index);
    if (!result.ok())
      return set_arrow_error("array scalar", result.status());
    return publish_scalar(*result, output);
  });
}
irx_arrow_status
irx_arrow_chunked_get_scalar(const irx_arrow_chunked_array_handle *value,
                             int64_t index, irx_arrow_scalar_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("chunked_get_scalar", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing scalar output");
    auto status = validate_handle(value, IRX_ARROW_HANDLE_KIND_CHUNKED_ARRAY,
                                  "chunked array");
    if (status != kArrowOk)
      return status;
    if (!value->column)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing chunked array");
    if (index < 0 || index >= value->column->length())
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                       "chunked scalar index out of bounds");
    for (const auto &chunk : value->column->chunks()) {
      if (index >= chunk->length()) {
        index -= chunk->length();
        continue;
      }
      auto result = extract_logical_scalar(*chunk, index);
      if (!result.ok())
        return set_arrow_error("chunked scalar", result.status());
      return publish_scalar(*result, output);
    }
    return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing scalar chunk");
  });
}
irx_arrow_status
irx_arrow_array_builder_new_logical(const irx_arrow_type_handle *type,
                                    irx_arrow_array_builder_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation(
      "array_builder_new_logical", [&]() -> irx_arrow_status {
        if (!output)
          return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                           "missing builder output");
        auto status = scalar_type(type);
        if (status != kArrowOk)
          return status;
        auto owner = make_runtime_handle<irx_arrow_array_builder_handle>();
        owner->logical_type = type->field->type();
        *output = owner.release();
        return kArrowOk;
      });
}
irx_arrow_status
irx_arrow_array_builder_append_scalar(irx_arrow_array_builder_handle *builder,
                                      const irx_arrow_scalar_handle *value) {
  return array_value_operation(
      "array_builder_append", [&]() -> irx_arrow_status {
        auto status = validate_handle(
            builder, IRX_ARROW_HANDLE_KIND_ARRAY_BUILDER, "builder");
        if (status != kArrowOk)
          return status;
        status = validate_scalar(value);
        if (status != kArrowOk)
          return status;
        if (!builder->logical_type ||
            !builder->logical_type->Equals(value->scalar->type, true))
          return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                           "builder scalar type mismatch");
        if (builder->values.size() == builder->values.max_size())
          return set_error(IRX_ARROW_STATUS_OVERFLOW, "builder size overflow");
        builder->values.push_back(value->scalar);
        return kArrowOk;
      });
}
irx_arrow_status irx_arrow_chunked_new_logical(
    const irx_arrow_type_handle *type, int32_t nullable, const void **chunks,
    int64_t count, irx_arrow_chunked_array_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation(
      "chunked_new_logical", [&]() -> irx_arrow_status {
        if (!output || (count && !chunks))
          return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                           "missing chunks or output");
        auto status = scalar_type(type);
        if (status != kArrowOk)
          return status;
        if (count < 0 || count > std::numeric_limits<int32_t>::max() ||
            (nullable != 0 && nullable != 1))
          return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT,
                           "invalid chunk count or nullability");
        arrow::ArrayVector arrays;
        int64_t length = 0;
        for (int64_t i = 0; i < count; ++i) {
          auto chunk = static_cast<const irx_arrow_array_handle *>(chunks[i]);
          status = validate_value_array(chunk);
          if (status != kArrowOk)
            return status;
          if (!chunk->array->type()->Equals(type->field->type(), true) ||
              (!nullable && logical_null_count(*chunk->array)))
            return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                             "chunk element mismatch");
          if (chunk->array->length() >
              std::numeric_limits<int64_t>::max() - length)
            return set_error(IRX_ARROW_STATUS_OVERFLOW,
                             "chunked length overflow");
          length += chunk->array->length();
          arrays.push_back(chunk->array);
        }
        auto result =
            arrow::ChunkedArray::Make(std::move(arrays), type->field->type());
        if (!result.ok())
          return set_arrow_error("chunked construction", result.status());
        auto owner = make_runtime_handle<irx_arrow_chunked_array_handle>();
        owner->column = *result;
        owner->nullable = nullable;
        *output = owner.release();
        return kArrowOk;
      });
}

irx_arrow_status
irx_arrow_scalar_from_bytes(const irx_arrow_type_handle *type,
                            const irx_arrow_array_handle *value,
                            irx_arrow_scalar_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("scalar_from_bytes", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing scalar output");
    auto status = scalar_type(type);
    if (status != kArrowOk)
      return status;
    status = validate_value_array(value);
    if (status != kArrowOk)
      return status;
    if (value->array->type_id() != arrow::Type::UINT8 ||
        logical_null_count(*value->array))
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "binary scalar requires nonnullable uint8 data");
    const auto &bytes = static_cast<const arrow::UInt8Array &>(*value->array);
    const char *data = bytes.length()
                           ? reinterpret_cast<const char *>(bytes.raw_values())
                           : "";
    auto result = parse_logical_scalar(
        type->field->type(),
        std::string_view(data, static_cast<size_t>(bytes.length())));
    if (!result.ok())
      return set_arrow_error("scalar bytes", result.status());
    return publish_scalar(*result, output);
  });
}
irx_arrow_status irx_arrow_scalar_bytes(const irx_arrow_scalar_handle *value,
                                        irx_arrow_array_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("scalar_bytes", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing byte array output");
    auto status = validate_scalar(value);
    if (status != kArrowOk)
      return status;
    auto bytes =
        std::dynamic_pointer_cast<arrow::BaseBinaryScalar>(value->scalar);
    if (!bytes || !bytes->value)
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "expected binary or string scalar");
    auto result =
        std::make_shared<arrow::UInt8Array>(bytes->value->size(), bytes->value);
    return publish_value_array(std::move(result), false, output);
  });
}

irx_arrow_status irx_arrow_array_from_buffer(int32_t type_id,
                                             irx_buffer_view *view,
                                             irx_arrow_array_handle **output) {
  if (output)
    *output = nullptr;
  return array_value_operation("array_from_buffer", [&]() -> irx_arrow_status {
    if (!output || !view)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER,
                       "missing buffer view or output");
    const auto *spec = type_spec_from_type_id(type_id);
    if (!spec || !spec->buffer_view_compatible ||
        reinterpret_cast<uintptr_t>(view->dtype) != spec->dtype_token)
      return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                       "buffer storage type mismatch");
    if (view->ndim != 1 || !view->shape || !view->strides ||
        view->shape[0] < 0 || view->offset_bytes < 0)
      return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT,
                       "expected a rank-one buffer with valid dimensions");
    if (view->flags & IRX_BUFFER_FLAG_VALIDITY_BITMAP)
      return set_error(
          IRX_ARROW_STATUS_NOT_SUPPORTED,
          "buffer validity requires an explicit Arrow bitmap constructor");
    int64_t count = view->shape[0], stride = view->strides[0],
            width = spec->element_size_bytes;
    if (count > std::numeric_limits<int64_t>::max() / width)
      return set_error(IRX_ARROW_STATUS_OVERFLOW,
                       "buffer result size overflow");
    if (count && !view->data)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing buffer data");
    if (count > 1) {
      if (stride >= 0 &&
          stride > (std::numeric_limits<int64_t>::max() - view->offset_bytes) /
                       (count - 1))
        return set_error(IRX_ARROW_STATUS_OVERFLOW, "buffer stride overflow");
      if (stride < 0 && (stride == std::numeric_limits<int64_t>::min() ||
                         -stride > view->offset_bytes / (count - 1)))
        return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT,
                         "negative stride precedes buffer start");
    }
    int64_t last = count ? view->offset_bytes + (count - 1) * stride : 0;
    if (count && std::max(last, view->offset_bytes) >
                     std::numeric_limits<int64_t>::max() - width)
      return set_error(IRX_ARROW_STATUS_OVERFLOW,
                       "buffer byte extent overflow");
    auto allocated = arrow::AllocateBuffer(
        count * width, irx_arrow_internal::builder_memory_pool());
    if (!allocated.ok())
      return set_arrow_error("buffer array allocation", allocated.status());
    std::shared_ptr<arrow::Buffer> buffer = std::move(*allocated);
    const auto *source = static_cast<const uint8_t *>(view->data);
    for (int64_t i = 0; i < count; ++i)
      std::memcpy(buffer->mutable_data() + i * width,
                  source + view->offset_bytes + i * stride,
                  static_cast<size_t>(width));
    auto result = arrow::MakeArray(arrow::ArrayData::Make(
        spec->make_type(), count, {nullptr, std::move(buffer)}, 0));
    return publish_value_array(std::move(result), false, output);
  });
}
