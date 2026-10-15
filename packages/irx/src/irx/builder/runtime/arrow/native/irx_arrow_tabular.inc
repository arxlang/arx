// Copyright IRx contributors.
// Immutable tabular values. No C++ layout crosses the public C ABI.
extern "C++" {
namespace {
template <typename Operation>
irx_arrow_status tabular_operation(const char *name, Operation operation) {
  begin_operation(name);
  try {
    if (fail_allocation_for_operation(name))
      return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY,
                       "injected tabular allocation failure");
    return operation();
  } catch (const std::bad_alloc &) {
    return set_error(IRX_ARROW_STATUS_OUT_OF_MEMORY,
                     "tabular allocation failed");
  } catch (const std::exception &error) {
    return set_exception_error(name, error);
  }
}

template <typename Handle, typename Value>
irx_arrow_status tabular_publish(std::shared_ptr<Value> value,
                                 std::shared_ptr<Value> Handle::*member,
                                 Handle **output) {
  auto validation = value->ValidateFull();
  if (!validation.ok())
    return set_arrow_error("tabular validation", validation);
  auto owner = make_runtime_handle<Handle>();
  owner.get()->*member = std::move(value);
  *output = owner.release();
  return kArrowOk;
}

irx_arrow_status tabular_schema(const irx_arrow_schema_handle *handle,
                                std::shared_ptr<arrow::Schema> *output) {
  auto status = validate_handle(handle, IRX_ARROW_HANDLE_KIND_SCHEMA, "schema");
  if (status != kArrowOk)
    return status;
  if (!handle->field || handle->field->type()->id() != arrow::Type::STRUCT)
    return set_error(IRX_ARROW_STATUS_INVALID_STATE,
                     "missing structural schema");
  auto type =
      std::static_pointer_cast<arrow::StructType>(handle->field->type());
  *output = arrow::schema(type->fields(), handle->field->metadata());
  std::unordered_set<std::string> names;
  for (const auto &field : (*output)->fields()) {
    if (!names.insert(field->name()).second)
      return set_error(IRX_ARROW_STATUS_SCHEMA_MISMATCH,
                       "duplicate column name");
  }
  return kArrowOk;
}

template <typename Column>
irx_arrow_status
tabular_column_check(const std::shared_ptr<arrow::Field> &field,
                     const std::shared_ptr<Column> &column, int64_t rows) {
  if (!column)
    return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing column");
  if (!field->type()->Equals(column->type()) ||
      (!field->nullable() && logical_null_count(*column)))
    return set_error(IRX_ARROW_STATUS_SCHEMA_MISMATCH,
                     "column type or nullability disagrees with schema");
  if (rows != column->length())
    return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT,
                     "unequal column lengths");
  auto validation = column->ValidateFull();
  return validation.ok() ? kArrowOk
                         : set_arrow_error("column validation", validation);
}
} // namespace
} // extern C++

irx_arrow_status
irx_arrow_batch_new_typed(const irx_arrow_schema_handle *schema,
                          const void **columns, int64_t count, int64_t rows,
                          irx_arrow_record_batch_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("batch_new_typed", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");

    if (rows < 0 || count < 0 || count > std::numeric_limits<int32_t>::max())
      return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT, "invalid dimensions");
    if (count && !columns)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing columns");
    std::shared_ptr<arrow::Schema> resolved;
    auto status = tabular_schema(schema, &resolved);
    if (status != kArrowOk)
      return status;
    if (count != resolved->num_fields())
      return set_error(IRX_ARROW_STATUS_SCHEMA_MISMATCH,
                       "column count differs from schema");
    std::vector<std::shared_ptr<arrow::Array>> values;
    for (int64_t i = 0; i < count; ++i) {
      const auto *column =
          static_cast<const irx_arrow_array_handle *>(columns[i]);
      status = validate_handle(column, IRX_ARROW_HANDLE_KIND_ARRAY, "column");
      if (status != kArrowOk)
        return status;
      status = tabular_column_check(resolved->field(static_cast<int>(i)),
                                    column->array, rows);
      if (status != kArrowOk)
        return status;
      values.push_back(column->array);
    }
    return tabular_publish(
        arrow::RecordBatch::Make(resolved, rows, std::move(values)),
        &irx_arrow_record_batch_handle::batch, output);
  });
}

irx_arrow_status
irx_arrow_batch_rows(const irx_arrow_record_batch_handle *value,
                     int64_t *output) {
  if (output)
    *output = 0;
  return tabular_operation("batch_rows", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status =
        validate_handle(value, IRX_ARROW_HANDLE_KIND_RECORD_BATCH, "batch");
    if (status != kArrowOk)
      return status;
    if (!value->batch)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing batch");
    *output = value->batch->num_rows();
    return kArrowOk;
  });
}

irx_arrow_status
irx_arrow_batch_columns(const irx_arrow_record_batch_handle *value,
                        int64_t *output) {
  if (output)
    *output = 0;
  return tabular_operation("batch_columns", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status =
        validate_handle(value, IRX_ARROW_HANDLE_KIND_RECORD_BATCH, "batch");
    if (status != kArrowOk)
      return status;
    if (!value->batch)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing batch");
    *output = value->batch->num_columns();
    return kArrowOk;
  });
}

irx_arrow_status
irx_arrow_batch_schema(const irx_arrow_record_batch_handle *value,
                       irx_arrow_schema_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("batch_schema", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status =
        validate_handle(value, IRX_ARROW_HANDLE_KIND_RECORD_BATCH, "batch");
    if (status != kArrowOk)
      return status;
    if (!value->batch)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing batch");

    auto owner = make_runtime_handle<irx_arrow_schema_handle>();
    auto schema = value->batch->schema();
    owner->field = arrow::field("", arrow::struct_(schema->fields()), false,
                                schema->metadata());
    *output = owner.release();
    return kArrowOk;
  });
}

irx_arrow_status irx_arrow_batch_column_checked(
    const irx_arrow_record_batch_handle *value, int64_t index,
    const irx_arrow_field_handle *expected, irx_arrow_array_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("batch_column_checked", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status =
        validate_handle(value, IRX_ARROW_HANDLE_KIND_RECORD_BATCH, "batch");
    if (status != kArrowOk)
      return status;
    if (!value->batch)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing batch");

    status = validate_handle(expected, IRX_ARROW_HANDLE_KIND_FIELD,
                             "expected field");
    if (status != kArrowOk)
      return status;
    if (index < 0 || index >= value->batch->num_columns())
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                       "column index out of bounds");
    auto field = value->batch->schema()->field(static_cast<int>(index));
    if (!expected->field || !field->Equals(expected->field, true))
      return set_error(IRX_ARROW_STATUS_SCHEMA_MISMATCH,
                       "checked projection field mismatch");
    auto owner = make_runtime_handle<irx_arrow_array_handle>();
    owner->array = value->batch->column(static_cast<int>(index));
    status = populate_array_metadata(
        owner.get(),
        resolved_from_arrow_type(field->type(), field->nullable()));
    if (status != kArrowOk)
      return status;
    *output = owner.release();
    return kArrowOk;
  });
}

irx_arrow_status
irx_arrow_batch_slice(const irx_arrow_record_batch_handle *value,
                      int64_t offset, int64_t length,
                      irx_arrow_record_batch_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("batch_slice", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status =
        validate_handle(value, IRX_ARROW_HANDLE_KIND_RECORD_BATCH, "batch");
    if (status != kArrowOk)
      return status;
    if (!value->batch)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing batch");

    if (offset < 0 || length < 0 || offset > value->batch->num_rows() ||
        length > value->batch->num_rows() - offset)
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                       "row slice out of bounds");
    return tabular_publish(value->batch->Slice(offset, length),
                           &irx_arrow_record_batch_handle::batch, output);
  });
}

irx_arrow_status
irx_arrow_batch_select(const irx_arrow_record_batch_handle *value,
                       const int64_t *indices, int64_t count,
                       irx_arrow_record_batch_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("batch_select", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status =
        validate_handle(value, IRX_ARROW_HANDLE_KIND_RECORD_BATCH, "batch");
    if (status != kArrowOk)
      return status;
    if (!value->batch)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing batch");

    if (count < 0 || count > value->batch->num_columns())
      return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT,
                       "invalid projection count");
    if (count && !indices)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing indices");
    std::vector<int> selected;
    std::unordered_set<int64_t> seen;
    for (int64_t i = 0; i < count; ++i) {
      if (indices[i] < 0 || indices[i] >= value->batch->num_columns())
        return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                         "projection index out of bounds");
      if (!seen.insert(indices[i]).second)
        return set_error(IRX_ARROW_STATUS_SCHEMA_MISMATCH,
                         "duplicate projection");
      selected.push_back(static_cast<int>(indices[i]));
    }
    auto result = value->batch->SelectColumns(selected);
    if (!result.ok())
      return set_arrow_error("select columns", result.status());
    return tabular_publish(*result, &irx_arrow_record_batch_handle::batch,
                           output);
  });
}

irx_arrow_status
irx_arrow_batch_with_schema(const irx_arrow_record_batch_handle *value,
                            const irx_arrow_schema_handle *schema,
                            irx_arrow_record_batch_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("batch_with_schema", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status =
        validate_handle(value, IRX_ARROW_HANDLE_KIND_RECORD_BATCH, "batch");
    if (status != kArrowOk)
      return status;
    if (!value->batch)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing batch");

    std::shared_ptr<arrow::Schema> resolved;
    status = tabular_schema(schema, &resolved);
    if (status != kArrowOk)
      return status;
    if (resolved->num_fields() != value->batch->num_columns())
      return set_error(IRX_ARROW_STATUS_SCHEMA_MISMATCH,
                       "schema column count mismatch");
    for (int i = 0; i < resolved->num_fields(); ++i) {
      status = tabular_column_check(resolved->field(i), value->batch->column(i),
                                    value->batch->num_rows());
      if (status != kArrowOk)
        return status;
    }
    return tabular_publish(arrow::RecordBatch::Make(resolved,
                                                    value->batch->num_rows(),
                                                    value->batch->columns()),
                           &irx_arrow_record_batch_handle::batch, output);
  });
}

irx_arrow_status
irx_arrow_batch_set_column(const irx_arrow_record_batch_handle *value,
                           int64_t index, const irx_arrow_field_handle *field,
                           const irx_arrow_array_handle *column,
                           irx_arrow_record_batch_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("batch_set_column", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status =
        validate_handle(value, IRX_ARROW_HANDLE_KIND_RECORD_BATCH, "batch");
    if (status != kArrowOk)
      return status;
    if (!value->batch)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing batch");

    status = validate_handle(field, IRX_ARROW_HANDLE_KIND_FIELD, "field");
    if (status != kArrowOk)
      return status;
    status = validate_handle(column, IRX_ARROW_HANDLE_KIND_ARRAY, "column");
    if (status != kArrowOk)
      return status;
    if (!field->field)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing field");
    if (index < 0 || index > value->batch->num_columns())
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                       "column index out of bounds");
    for (int i = 0; i < value->batch->num_columns(); ++i) {
      if (i != index &&
          value->batch->schema()->field(i)->name() == field->field->name())
        return set_error(IRX_ARROW_STATUS_SCHEMA_MISMATCH,
                         "duplicate column name");
    }
    status = tabular_column_check(field->field, column->array,
                                  value->batch->num_rows());
    if (status != kArrowOk)
      return status;
    auto result = index == value->batch->num_columns()
                      ? value->batch->AddColumn(static_cast<int>(index),
                                                field->field, column->array)
                      : value->batch->SetColumn(static_cast<int>(index),
                                                field->field, column->array);
    if (!result.ok())
      return set_arrow_error("set column", result.status());
    return tabular_publish(*result, &irx_arrow_record_batch_handle::batch,
                           output);
  });
}

irx_arrow_status
irx_arrow_batch_remove(const irx_arrow_record_batch_handle *value,
                       int64_t index, irx_arrow_record_batch_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("batch_remove", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status =
        validate_handle(value, IRX_ARROW_HANDLE_KIND_RECORD_BATCH, "batch");
    if (status != kArrowOk)
      return status;
    if (!value->batch)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing batch");

    if (index < 0 || index >= value->batch->num_columns())
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                       "column index out of bounds");
    auto result = value->batch->RemoveColumn(static_cast<int>(index));
    if (!result.ok())
      return set_arrow_error("remove column", result.status());
    return tabular_publish(*result, &irx_arrow_record_batch_handle::batch,
                           output);
  });
}

irx_arrow_status
irx_arrow_table_new_typed(const irx_arrow_schema_handle *schema,
                          const void **columns, int64_t count, int64_t rows,
                          irx_arrow_table_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("table_new_typed", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");

    if (rows < 0 || count < 0 || count > std::numeric_limits<int32_t>::max())
      return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT, "invalid dimensions");
    if (count && !columns)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing columns");
    std::shared_ptr<arrow::Schema> resolved;
    auto status = tabular_schema(schema, &resolved);
    if (status != kArrowOk)
      return status;
    if (count != resolved->num_fields())
      return set_error(IRX_ARROW_STATUS_SCHEMA_MISMATCH,
                       "column count differs from schema");
    std::vector<std::shared_ptr<arrow::ChunkedArray>> values;
    for (int64_t i = 0; i < count; ++i) {
      const auto *column =
          static_cast<const irx_arrow_chunked_array_handle *>(columns[i]);
      status = validate_handle(column, IRX_ARROW_HANDLE_KIND_CHUNKED_ARRAY,
                               "column");
      if (status != kArrowOk)
        return status;
      status = tabular_column_check(resolved->field(static_cast<int>(i)),
                                    column->column, rows);
      if (status != kArrowOk)
        return status;
      values.push_back(column->column);
    }
    return tabular_publish(
        arrow::Table::Make(resolved, std::move(values), rows),
        &irx_arrow_table_handle::table, output);
  });
}

irx_arrow_status irx_arrow_table_rows(const irx_arrow_table_handle *value,
                                      int64_t *output) {
  if (output)
    *output = 0;
  return tabular_operation("table_rows", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_handle(value, IRX_ARROW_HANDLE_KIND_TABLE, "table");
    if (status != kArrowOk)
      return status;
    if (!value->table)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing table");
    *output = value->table->num_rows();
    return kArrowOk;
  });
}

irx_arrow_status irx_arrow_table_columns(const irx_arrow_table_handle *value,
                                         int64_t *output) {
  if (output)
    *output = 0;
  return tabular_operation("table_columns", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_handle(value, IRX_ARROW_HANDLE_KIND_TABLE, "table");
    if (status != kArrowOk)
      return status;
    if (!value->table)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing table");
    *output = value->table->num_columns();
    return kArrowOk;
  });
}

irx_arrow_status irx_arrow_table_schema(const irx_arrow_table_handle *value,
                                        irx_arrow_schema_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("table_schema", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_handle(value, IRX_ARROW_HANDLE_KIND_TABLE, "table");
    if (status != kArrowOk)
      return status;
    if (!value->table)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing table");

    auto owner = make_runtime_handle<irx_arrow_schema_handle>();
    auto schema = value->table->schema();
    owner->field = arrow::field("", arrow::struct_(schema->fields()), false,
                                schema->metadata());
    *output = owner.release();
    return kArrowOk;
  });
}

irx_arrow_status
irx_arrow_table_column_checked(const irx_arrow_table_handle *value,
                               int64_t index,
                               const irx_arrow_field_handle *expected,
                               irx_arrow_chunked_array_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("table_column_checked", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_handle(value, IRX_ARROW_HANDLE_KIND_TABLE, "table");
    if (status != kArrowOk)
      return status;
    if (!value->table)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing table");

    status = validate_handle(expected, IRX_ARROW_HANDLE_KIND_FIELD,
                             "expected field");
    if (status != kArrowOk)
      return status;
    if (index < 0 || index >= value->table->num_columns())
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                       "column index out of bounds");
    auto field = value->table->schema()->field(static_cast<int>(index));
    if (!expected->field || !field->Equals(expected->field, true))
      return set_error(IRX_ARROW_STATUS_SCHEMA_MISMATCH,
                       "checked projection field mismatch");
    auto owner = make_runtime_handle<irx_arrow_chunked_array_handle>();
    owner->column = value->table->column(static_cast<int>(index));
    owner->nullable = field->nullable();
    *output = owner.release();
    return kArrowOk;
  });
}

irx_arrow_status irx_arrow_table_slice(const irx_arrow_table_handle *value,
                                       int64_t offset, int64_t length,
                                       irx_arrow_table_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("table_slice", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_handle(value, IRX_ARROW_HANDLE_KIND_TABLE, "table");
    if (status != kArrowOk)
      return status;
    if (!value->table)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing table");

    if (offset < 0 || length < 0 || offset > value->table->num_rows() ||
        length > value->table->num_rows() - offset)
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                       "row slice out of bounds");
    return tabular_publish(value->table->Slice(offset, length),
                           &irx_arrow_table_handle::table, output);
  });
}

irx_arrow_status irx_arrow_table_select(const irx_arrow_table_handle *value,
                                        const int64_t *indices, int64_t count,
                                        irx_arrow_table_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("table_select", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_handle(value, IRX_ARROW_HANDLE_KIND_TABLE, "table");
    if (status != kArrowOk)
      return status;
    if (!value->table)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing table");

    if (count < 0 || count > value->table->num_columns())
      return set_error(IRX_ARROW_STATUS_INVALID_ARGUMENT,
                       "invalid projection count");
    if (count && !indices)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing indices");
    std::vector<int> selected;
    std::unordered_set<int64_t> seen;
    for (int64_t i = 0; i < count; ++i) {
      if (indices[i] < 0 || indices[i] >= value->table->num_columns())
        return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                         "projection index out of bounds");
      if (!seen.insert(indices[i]).second)
        return set_error(IRX_ARROW_STATUS_SCHEMA_MISMATCH,
                         "duplicate projection");
      selected.push_back(static_cast<int>(indices[i]));
    }
    auto result = value->table->SelectColumns(selected);
    if (!result.ok())
      return set_arrow_error("select columns", result.status());
    return tabular_publish(*result, &irx_arrow_table_handle::table, output);
  });
}

irx_arrow_status
irx_arrow_table_with_schema(const irx_arrow_table_handle *value,
                            const irx_arrow_schema_handle *schema,
                            irx_arrow_table_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("table_with_schema", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_handle(value, IRX_ARROW_HANDLE_KIND_TABLE, "table");
    if (status != kArrowOk)
      return status;
    if (!value->table)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing table");

    std::shared_ptr<arrow::Schema> resolved;
    status = tabular_schema(schema, &resolved);
    if (status != kArrowOk)
      return status;
    if (resolved->num_fields() != value->table->num_columns())
      return set_error(IRX_ARROW_STATUS_SCHEMA_MISMATCH,
                       "schema column count mismatch");
    for (int i = 0; i < resolved->num_fields(); ++i) {
      status = tabular_column_check(resolved->field(i), value->table->column(i),
                                    value->table->num_rows());
      if (status != kArrowOk)
        return status;
    }
    return tabular_publish(arrow::Table::Make(resolved, value->table->columns(),
                                              value->table->num_rows()),
                           &irx_arrow_table_handle::table, output);
  });
}

irx_arrow_status
irx_arrow_table_set_column(const irx_arrow_table_handle *value, int64_t index,
                           const irx_arrow_field_handle *field,
                           const irx_arrow_chunked_array_handle *column,
                           irx_arrow_table_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("table_set_column", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_handle(value, IRX_ARROW_HANDLE_KIND_TABLE, "table");
    if (status != kArrowOk)
      return status;
    if (!value->table)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing table");

    status = validate_handle(field, IRX_ARROW_HANDLE_KIND_FIELD, "field");
    if (status != kArrowOk)
      return status;
    status =
        validate_handle(column, IRX_ARROW_HANDLE_KIND_CHUNKED_ARRAY, "column");
    if (status != kArrowOk)
      return status;
    if (!field->field)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing field");
    if (index < 0 || index > value->table->num_columns())
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                       "column index out of bounds");
    for (int i = 0; i < value->table->num_columns(); ++i) {
      if (i != index &&
          value->table->schema()->field(i)->name() == field->field->name())
        return set_error(IRX_ARROW_STATUS_SCHEMA_MISMATCH,
                         "duplicate column name");
    }
    status = tabular_column_check(field->field, column->column,
                                  value->table->num_rows());
    if (status != kArrowOk)
      return status;
    auto result = index == value->table->num_columns()
                      ? value->table->AddColumn(static_cast<int>(index),
                                                field->field, column->column)
                      : value->table->SetColumn(static_cast<int>(index),
                                                field->field, column->column);
    if (!result.ok())
      return set_arrow_error("set column", result.status());
    return tabular_publish(*result, &irx_arrow_table_handle::table, output);
  });
}

irx_arrow_status irx_arrow_table_remove(const irx_arrow_table_handle *value,
                                        int64_t index,
                                        irx_arrow_table_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("table_remove", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_handle(value, IRX_ARROW_HANDLE_KIND_TABLE, "table");
    if (status != kArrowOk)
      return status;
    if (!value->table)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing table");

    if (index < 0 || index >= value->table->num_columns())
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                       "column index out of bounds");
    auto result = value->table->RemoveColumn(static_cast<int>(index));
    if (!result.ok())
      return set_arrow_error("remove column", result.status());
    return tabular_publish(*result, &irx_arrow_table_handle::table, output);
  });
}

irx_arrow_status
irx_arrow_batch_to_table(const irx_arrow_record_batch_handle *value,
                         irx_arrow_table_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("batch_to_table", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status =
        validate_handle(value, IRX_ARROW_HANDLE_KIND_RECORD_BATCH, "input");
    if (status != kArrowOk)
      return status;
    if (!value->batch)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing input");
    auto result =
        arrow::Table::FromRecordBatches(value->batch->schema(), {value->batch});
    if (!result.ok())
      return set_arrow_error("batch_to_table", result.status());
    return tabular_publish(*result, &irx_arrow_table_handle::table, output);
  });
}

irx_arrow_status
irx_arrow_table_to_batch(const irx_arrow_table_handle *value,
                         irx_arrow_record_batch_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("table_to_batch", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_handle(value, IRX_ARROW_HANDLE_KIND_TABLE, "input");
    if (status != kArrowOk)
      return status;
    if (!value->table)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing input");
    auto result = value->table->CombineChunksToBatch(
        irx_arrow_internal::builder_memory_pool());
    if (!result.ok())
      return set_arrow_error("table_to_batch", result.status());
    return tabular_publish(*result, &irx_arrow_record_batch_handle::batch,
                           output);
  });
}

irx_arrow_status irx_arrow_table_combine(const irx_arrow_table_handle *value,
                                         irx_arrow_table_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("table_combine", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing output");
    auto status = validate_handle(value, IRX_ARROW_HANDLE_KIND_TABLE, "input");
    if (status != kArrowOk)
      return status;
    if (!value->table)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing input");
    auto result =
        value->table->CombineChunks(irx_arrow_internal::builder_memory_pool());
    if (!result.ok())
      return set_arrow_error("table_combine", result.status());
    return tabular_publish(*result, &irx_arrow_table_handle::table, output);
  });
}

extern "C++" {
namespace {
irx_arrow_status selection_indices(const irx_arrow_array_handle *indices,
                                   int64_t rows,
                                   std::shared_ptr<arrow::Int64Array> *output) {
  auto status =
      validate_handle(indices, IRX_ARROW_HANDLE_KIND_ARRAY, "row indices");
  if (status != kArrowOk)
    return status;
  if (!indices->array || indices->array->type_id() != arrow::Type::INT64 ||
      indices->array->null_count())
    return set_error(IRX_ARROW_STATUS_TYPE_MISMATCH,
                     "row indices require nonnullable int64 values");
  auto values = std::static_pointer_cast<arrow::Int64Array>(indices->array);
  for (int64_t i = 0; i < values->length(); ++i)
    if (values->Value(i) < 0 || values->Value(i) >= rows)
      return set_error(IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS,
                       "row selection index out of bounds");
  *output = std::move(values);
  return kArrowOk;
}
} // namespace
} // extern C++

irx_arrow_status
irx_arrow_batch_take(const irx_arrow_record_batch_handle *value,
                     const irx_arrow_array_handle *indices,
                     irx_arrow_record_batch_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("batch_take", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing batch output");
    auto status =
        validate_handle(value, IRX_ARROW_HANDLE_KIND_RECORD_BATCH, "batch");
    if (status != kArrowOk)
      return status;
    if (!value->batch)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing batch");
    std::shared_ptr<arrow::Int64Array> selected;
    status = selection_indices(indices, value->batch->num_rows(), &selected);
    if (status != kArrowOk)
      return status;
    arrow::ArrayVector columns;
    for (const auto &column : value->batch->columns()) {
      arrow::ArrayVector slices;
      for (int64_t i = 0; i < selected->length(); ++i)
        slices.push_back(column->Slice(selected->Value(i), 1));
      auto result =
          slices.empty()
              ? arrow::Result<std::shared_ptr<arrow::Array>>(
                    column->Slice(0, 0))
              : arrow::Concatenate(slices,
                                   irx_arrow_internal::builder_memory_pool());
      if (!result.ok())
        return set_arrow_error("batch row selection", result.status());
      columns.push_back(*result);
    }
    return tabular_publish(arrow::RecordBatch::Make(value->batch->schema(),
                                                    selected->length(),
                                                    std::move(columns)),
                           &irx_arrow_record_batch_handle::batch, output);
  });
}
irx_arrow_status irx_arrow_table_take(const irx_arrow_table_handle *value,
                                      const irx_arrow_array_handle *indices,
                                      irx_arrow_table_handle **output) {
  if (output)
    *output = nullptr;
  return tabular_operation("table_take", [&]() -> irx_arrow_status {
    if (!output)
      return set_error(IRX_ARROW_STATUS_NULL_POINTER, "missing table output");
    auto status = validate_handle(value, IRX_ARROW_HANDLE_KIND_TABLE, "table");
    if (status != kArrowOk)
      return status;
    if (!value->table)
      return set_error(IRX_ARROW_STATUS_INVALID_STATE, "missing table");
    std::shared_ptr<arrow::Int64Array> selected;
    status = selection_indices(indices, value->table->num_rows(), &selected);
    if (status != kArrowOk)
      return status;
    std::vector<std::shared_ptr<arrow::ChunkedArray>> columns;
    for (const auto &column : value->table->columns()) {
      arrow::ArrayVector chunks;
      for (int64_t i = 0; i < selected->length(); ++i) {
        auto slice = column->Slice(selected->Value(i), 1);
        chunks.insert(chunks.end(), slice->chunks().begin(),
                      slice->chunks().end());
      }
      auto result =
          arrow::ChunkedArray::Make(std::move(chunks), column->type());
      if (!result.ok())
        return set_arrow_error("table row selection", result.status());
      columns.push_back(*result);
    }
    return tabular_publish(arrow::Table::Make(value->table->schema(),
                                              std::move(columns),
                                              selected->length()),
                           &irx_arrow_table_handle::table, output);
  });
}
