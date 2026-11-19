// Copyright IRx contributors.
#include "irx_arrow_runtime.h"
#include "irx_arrow_common.h"
#include "irx_record_batch.h"
#include <cassert>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <cstdio>
#include <limits>

// Exercise an actual allocation failure without adding a runtime test API.
static bool fail_allocation = false;
void* operator new(std::size_t size) {
  if (fail_allocation) {
    fail_allocation = false;
    throw std::bad_alloc();
  }
  if (auto* value = std::malloc(size ? size : 1)) return value;
  throw std::bad_alloc();
}
void operator delete(void* value) noexcept { std::free(value); }
void operator delete(void* value, std::size_t) noexcept { std::free(value); }

static void check_compute_abi() {
  assert(irx_arrow_compute_abi_version() == IRX_COMPUTE_ABI_VERSION);
  arrow::DoubleBuilder builder;
  assert(builder.AppendValues({0.0, 4.0}).ok());
  auto first = builder.Finish().ValueOrDie();
  assert(builder.AppendNull().ok());
  auto second = builder.Finish().ValueOrDie();
  for (int operation : {IRX_COMPUTE_SQRT, IRX_COMPUTE_EXP}) {
    auto* input = new irx_arrow_chunked_array_handle();
    input->refcount = 1;
    input->column = std::make_shared<arrow::ChunkedArray>(
        arrow::ArrayVector{first, second});
    irx_arrow_chunked_array_handle* output = nullptr;
    uint64_t bits = 123;
    int32_t valid = 123;
    assert(irx_arrow_compute(1, operation, 1, 0, 12, 2, input, 0, 0,
                            &output, &bits, &valid) == IRX_OK);
    assert(output && bits == 0 && valid == 0);
    irx_arrow_chunked_array_release(input);
    assert(irx_arrow_chunked_array_retain(output) == IRX_OK);
    irx_arrow_chunked_array_release(output);
    assert(output->column->length() == 3 && output->column->null_count() == 1);
    auto scalar = output->column->GetScalar(1).ValueOrDie();
    const double value = static_cast<const arrow::DoubleScalar&>(*scalar).value;
    assert(std::abs(value - (operation == IRX_COMPUTE_SQRT ? 2.0 : std::exp(4.0))) < 1e-12);
    irx_arrow_chunked_array_release(output);

    // Missing slots clear every remaining output; an incompatible revision is
    // rejected without dereferencing even an inaccessible input pointer.
    for (int missing = 0; missing < 3; ++missing) {
      output = reinterpret_cast<irx_arrow_chunked_array_handle*>(1);
      bits = valid = 123;
      assert(irx_arrow_compute(1, operation, 1, 0, 12, 1, nullptr, 0, 1,
          missing == 0 ? nullptr : &output, missing == 1 ? nullptr : &bits,
          missing == 2 ? nullptr : &valid) == IRX_ERR_NULLPTR);
      if (missing != 0) assert(output == nullptr);
      if (missing != 1) assert(bits == 0);
      if (missing != 2) assert(valid == 0);
    }
    assert(irx_arrow_compute(99, operation, 1, 0, 12, 2,
        reinterpret_cast<irx_arrow_chunked_array_handle*>(1), 0, 0,
        &output, &bits, &valid) == IRX_ERR_INVALID);
    assert(!output && bits == 0 && valid == 0);
    irx_arrow_chunked_array_handle wrong_tag;
    wrong_tag.tag = 0;
    assert(irx_arrow_compute(1, operation, 1, 0, 12, 2, &wrong_tag, 0, 0,
                            &output, &bits, &valid) == IRX_ERR_TYPE);
    assert(!output && bits == 0 && valid == 0);
    wrong_tag.tag = irx_arrow_chunked_array_handle::tag_value;
    wrong_tag.refcount = 1;
    wrong_tag.column = arrow::ChunkedArray::MakeEmpty(arrow::int32()).ValueOrDie();
    assert(irx_arrow_compute(1, operation, 1, 0, 12, 2, &wrong_tag, 0, 0,
                            &output, &bits, &valid) == IRX_ERR_TYPE);
    assert(!output && bits == 0 && valid == 0);
    fail_allocation = true;
    assert(irx_arrow_compute(1, operation, 1, 0, 12, 1, nullptr, 0, 1,
                            &output, &bits, &valid) == IRX_ERR_ALLOC);
    assert(!fail_allocation && !output && bits == 0 && valid == 0);
  }
  assert(irx::record_batch_status(arrow::Status::OutOfMemory("test")) == IRX_ERR_ALLOC);
  assert(irx::record_batch_status(arrow::Status::CapacityError("test")) == IRX_ERR_OVERFLOW);
  assert(irx::record_batch_status(arrow::Status::IndexError("test")) == IRX_ERR_OOB);
  assert(irx::record_batch_status(arrow::Status::TypeError("test")) == IRX_ERR_TYPE);
  assert(irx::record_batch_status(arrow::Status::IOError("test")) == IRX_ERR_IO);
  assert(irx::native_exception_status(std::overflow_error("test")) == IRX_ERR_OVERFLOW);
}

static void release_tensor_context(void* context) {
  irx_arrow_tensor_release(static_cast<irx_arrow_tensor_handle*>(context));
}

static void check_tensor_lifetimes() {
  const int64_t shape[] = {2}, strides[] = {sizeof(int32_t)};
  for (int repeat = 0; repeat < 32; ++repeat) {
    irx_arrow_tensor_builder_handle* builder = nullptr;
    assert(irx_arrow_tensor_builder_new(
        IRX_ARROW_TYPE_INT32, 1, shape, strides, &builder) == 0);
    assert(irx_arrow_tensor_builder_append_int(builder, 11) == 0);
    irx_arrow_tensor_handle* tensor = nullptr;
    assert(irx_arrow_tensor_builder_finish(builder, &tensor) != 0);
    assert(tensor == nullptr);
    // Failed finish retains the builder, including its partial contents.
    assert(irx_arrow_tensor_builder_append_int(builder, 22) == 0);
    assert(irx_arrow_tensor_builder_finish(builder, &tensor) == 0);
    irx_buffer_view view{};
    assert(irx_arrow_tensor_borrow_buffer_view(tensor, &view) == 0);
    assert(static_cast<int32_t*>(view.data)[1] == 22);
    assert(irx_buffer_owner_external_new(
        tensor, release_tensor_context, nullptr) != 0);
    // Failed bridge creation did not consume the tensor.
    assert(irx_buffer_owner_external_new(
        tensor, release_tensor_context, &view.owner) == 0);
    assert(irx_buffer_view_retain(&view) == 0);
    irx_buffer_owner_handle* retained = view.owner;
    assert(irx_buffer_view_release(&view) == 0);
    assert(view.owner == nullptr);
    assert(irx_buffer_owner_release(retained) == 0);

    assert(irx_arrow_tensor_builder_new(
        IRX_ARROW_TYPE_INT32, 1, shape, strides, &builder) == 0);
    assert(irx_arrow_tensor_builder_append_int(builder, 33) == 0);
    irx_arrow_tensor_builder_release(builder);
  }
}

int main() {
  check_compute_abi();
  check_tensor_lifetimes();
  for (int repeat = 0; repeat < 16; ++repeat) {
    IrxRbSchema* schema = nullptr;
    assert(irx_rb_schema_create(&schema) == 0);
    assert(irx_rb_schema_add_field(schema, "x", IRX_COL_INT32, 1) == 0);
    IrxRbBuilder* builder = nullptr;
    assert(irx_rb_builder_create(schema, &builder) == 0);
    assert(irx_rb_builder_append_int32(builder, 0, 5) == 0);
    assert(irx_rb_builder_append_null(builder, 0) == 0);
    IrxRbBatch* batch = nullptr;
    assert(irx_rb_builder_finish(builder, &batch) == 0);
    irx_rb_builder_release(builder);
    irx_arrow_table_handle* table = nullptr;
    assert(irx_rb_batch_to_table(batch, schema, &table) == 0);
    irx_arrow_chunked_array_handle* column = nullptr;
    assert(irx_arrow_table_column_by_index(table, 0, &column) == 0);
    irx_arrow_table_release(table);
    uint64_t bits = 0;
    int32_t valid = 0;
    assert(irx_arrow_series_index(column, 0, IRX_ARROW_TYPE_INT32, &bits, &valid) == 0);
    assert(bits == 5 && valid == 1);
    assert(irx_arrow_series_index(column, 1, IRX_ARROW_TYPE_INT32, &bits, &valid) == 0);
    assert(bits == 0 && valid == 0);
    assert(irx_arrow_series_index(column, -1, IRX_ARROW_TYPE_INT32, &bits, &valid) != 0);
    irx_arrow_chunked_array_handle* sum = nullptr;
    assert(irx_arrow_column_compute("add_checked", IRX_ARROW_TYPE_INT32,
        column, 0, 1, column, 0, 1, &sum, &bits, &valid) == 0);
    irx_arrow_chunked_array_handle* slice = nullptr;
    assert(irx_arrow_series_slice(column, 0, 0, -1, 0, &slice) == 0);
    assert(irx_arrow_series_set(column, 1, IRX_ARROW_TYPE_INT32, 9, 1, 1) == 0);
    assert(irx_arrow_series_index(slice, 0, IRX_ARROW_TYPE_INT32, &bits, &valid) == 0);
    assert(valid == 0);
    assert(irx_arrow_series_set(column, -1, IRX_ARROW_TYPE_INT32, 9, 1, 1) != 0);
    irx_arrow_chunked_array_handle* reduced = nullptr;
    assert(irx_arrow_column_compute("sum", IRX_ARROW_TYPE_INT32,
        column, 0, 1, nullptr, 0, 0, &reduced, &bits, &valid) == 0);
    assert(reduced == nullptr && bits == 14 && valid == 1);
    irx_arrow_chunked_array_release(slice);
    irx_arrow_chunked_array_release(column);
    assert(irx_arrow_series_index(sum, 0, IRX_ARROW_TYPE_INT32, &bits, &valid) == 0);
    assert(bits == 10 && valid == 1);
    irx_arrow_chunked_array_release(sum);
    sum = nullptr;
    assert(irx_arrow_column_compute("add_checked", IRX_ARROW_TYPE_INT32,
        nullptr, std::numeric_limits<int32_t>::max(), 1, nullptr, 1, 1,
        &sum, &bits, &valid) != 0);
    assert(sum == nullptr && bits == 0 && valid == 0);

    IrxParquetOptions* options = irx_parquet_options_new();
    assert(options != nullptr);
    assert(irx_parquet_options_int(options, "atomic", 1) == 0);
    assert(irx_parquet_options_int(options, "durable", 1) == 0);
    IrxRbStreamWriter* writer = nullptr;
    assert(irx_rb_parquet_writer_open_options(schema, "sanitizer.parquet", options, &writer) == 0);
    assert(irx_rb_stream_writer_write_batch(writer, batch) == 0);
    assert(irx_rb_stream_writer_close(writer) == 0);
    irx_rb_stream_writer_release(writer);
    irx_parquet_options_release(options);
    irx_rb_batch_release(batch);
    irx_rb_schema_release(schema);
    IrxRbStreamReader* reader = nullptr;
    assert(irx_rb_parquet_reader_open("sanitizer.parquet", nullptr, 1, &reader) == 0);
    assert(irx_rb_stream_reader_next_batch(reader, &batch) == 0);
    assert(batch != nullptr);
    int32_t value = 0;
    assert(irx_rb_batch_get_int32(batch, 0, 0, &value) == 0 && value == 5);
    irx_rb_batch_release(batch);
    irx_rb_stream_reader_close(reader);

    // Exercise multi-batch tables independently of their closed input session.
    assert(irx_rb_parquet_reader_open("sanitizer.parquet", nullptr, 1, &reader) == 0);
    table = nullptr;
    assert(irx_rb_reader_read_table(reader, &table) == 0);
    irx_rb_stream_reader_close(reader);
    assert(irx_arrow_table_num_rows(table) == 2);
    ArrowArrayStream stream{};
    assert(irx_arrow_table_export_stream(table, &stream) == 0);
    irx_arrow_table_handle* imported = nullptr;
    assert(irx_arrow_table_import_stream(&stream, &imported) == 0);
    assert(stream.release == nullptr);
    irx_arrow_table_release(table);
    assert(irx_rb_table_schema(imported, &schema) == 0);
    irx_arrow_table_handle* checked = nullptr;
    assert(irx_rb_table_cast(imported, schema, &checked) == 0);
    irx_arrow_table_release(checked);
    IrxRbSchema* required = nullptr;
    assert(irx_rb_schema_create(&required) == 0);
    assert(irx_rb_schema_add_named_field(required, "x", "int32", 0) == 0);
    checked = reinterpret_cast<irx_arrow_table_handle*>(1);
    assert(irx_rb_table_cast(imported, required, &checked) < 0);
    assert(checked == nullptr);
    irx_rb_schema_release(required);
    const char* missing[] = {"missing"};
    checked = reinterpret_cast<irx_arrow_table_handle*>(1);
    assert(irx_rb_table_project(imported, missing, 1, &checked) < 0);
    assert(checked == nullptr);
    IrxCsvOptions* csv = irx_csv_options_new();
    assert(csv != nullptr);
    assert(irx_rb_csv_write_table(imported, "sanitizer.csv", csv) == 0);
    assert(irx_rb_csv_read_table("sanitizer.csv", schema, csv, &checked) == 0);
    assert(irx_arrow_table_num_rows(checked) == 2);
    irx_csv_options_release(csv);
    irx_rb_schema_release(schema);
    irx_arrow_table_release(imported);
    options = irx_parquet_options_new();
    assert(irx_parquet_options_int(options, "row_group_size", 1) == 0);
    assert(irx_rb_parquet_write_table(checked, "table.parquet", options, 1) == 0);
    irx_arrow_table_release(checked);
    irx_parquet_options_release(options);
    options = irx_parquet_options_new();
    assert(irx_rb_parquet_read_table("table.parquet", nullptr, options, 1, &imported) == 0);
    assert(irx_arrow_table_num_rows(imported) == 2);
    irx_arrow_table_release(imported);
    irx_parquet_options_release(options);
  }
  std::remove("sanitizer.parquet");
  std::remove("table.parquet");
  std::remove("sanitizer.csv");
  return 0;
}
