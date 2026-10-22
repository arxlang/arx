// Copyright IRx contributors.
#include "irx_arrow_runtime.h"
#include "irx_record_batch.h"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <limits>

int main() {
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
  }
  std::remove("sanitizer.parquet");
  return 0;
}
