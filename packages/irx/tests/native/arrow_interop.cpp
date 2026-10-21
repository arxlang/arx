// Copyright IRx contributors. Standalone ASan/LSan interoperability harness.
#include "irx_record_batch.h"
#include "irx_arrow_runtime.h"
#include <cassert>

int main(int argc, char **argv) {
    assert(argc == 2);
    for (int iteration = 0; iteration < 100; ++iteration) {
        IrxRbSchema *schema = nullptr;
        assert(irx_rb_schema_create(&schema) == IRX_OK);
        assert(irx_rb_schema_add_field(schema, "id", IRX_COL_INT64, 1) ==
               IRX_OK);
        IrxRbBuilder *builder = nullptr;
        assert(irx_rb_builder_create(schema, &builder) == IRX_OK);
        // Builder must own a schema snapshot, not borrow a freed handle.
        irx_rb_schema_release(schema);
        assert(irx_rb_builder_append_int64(builder, 0, 42) == IRX_OK);
        assert(irx_rb_builder_append_null(builder, 0) == IRX_OK);
        IrxRbBatch *batch = nullptr;
        assert(irx_rb_builder_finish(builder, &batch) == IRX_OK);
        irx_rb_builder_release(builder);
        IrxRbSchema *expected = nullptr;
        assert(irx_rb_schema_create(&expected) == IRX_OK);
        assert(irx_rb_schema_add_field(expected, "id", IRX_COL_INT64, 0) == IRX_OK);
        irx_arrow_table_handle *table = nullptr;
        // Null-bearing input must fail without publishing or consuming input.
        assert(irx_rb_batch_to_table(batch, expected, &table) < 0 && !table);
        IrxRbBuilder *numbers = nullptr;
        assert(irx_rb_builder_create(expected, &numbers) == IRX_OK);
        assert(irx_rb_builder_append_int64(numbers, 0, 42) == IRX_OK);
        IrxRbBatch *single = nullptr;
        assert(irx_rb_builder_finish(numbers, &single) == IRX_OK);
        irx_rb_builder_release(numbers);
        assert(irx_rb_batch_to_table(single, expected, &table) == IRX_OK);
        irx_rb_batch_release(single);
        assert(irx_rb_table_to_batch(table, &single) == IRX_OK);
        irx_arrow_table_release(table);
        IrxRbStreamWriter *csv_writer = nullptr;
        assert(irx_rb_csv_writer_open(expected, argv[1], ",", 1, &csv_writer) == IRX_OK);
        irx_rb_schema_release(expected);
        assert(irx_rb_stream_writer_write_batch(csv_writer, single) == IRX_OK);
        irx_rb_batch_release(single);
        assert(irx_rb_stream_writer_close(csv_writer) == IRX_OK);
        irx_rb_stream_writer_release(csv_writer);
        IrxRbStreamReader *csv_reader = nullptr;
        assert(irx_rb_csv_reader_open(argv[1], nullptr, ",", 1, 1024, &csv_reader) == IRX_OK);
        assert(irx_rb_stream_reader_next_batch(csv_reader, &single) == IRX_OK);
        irx_rb_stream_reader_close(csv_reader);
        int64_t csv_value = 0;
        assert(irx_rb_batch_get_int64(single, 0, 0, &csv_value) == IRX_OK);
        assert(csv_value == 42);
        irx_rb_batch_release(single);

        ArrowArrayStream stream{};
        assert(irx_rb_batch_export_stream(batch, &stream) == IRX_OK);
        irx_rb_batch_release(batch);
        ArrowSchema c_schema{};
        ArrowArray array{};
        assert(stream.get_schema(&stream, &c_schema) == 0);
        assert(stream.get_next(&stream, &array) == 0);
        ArrowArray end{};
        assert(stream.get_next(&stream, &end) == 0 && !end.release);
        irx_rb_c_stream_release(&stream);
        irx_rb_c_stream_release(&stream);
        assert(irx_rb_batch_import(&array, &c_schema, &batch) == IRX_OK);
        assert(!array.release && !c_schema.release);
        irx_rb_c_array_release(&array);
        irx_rb_c_schema_release(&c_schema);
        int64_t value = 0;
        assert(irx_rb_batch_get_int64(batch, 0, 0, &value) == IRX_OK);
        assert(value == 42);
        assert(irx_rb_batch_export(batch, &array, &c_schema) == IRX_OK);
        irx_rb_batch_release(batch);
        irx_rb_c_array_release(&array);
        irx_rb_c_array_release(&array);
        irx_rb_c_schema_release(&c_schema);
        irx_rb_c_schema_release(&c_schema);
        IrxRbStreamReader *reader = nullptr;
        const uint8_t invalid[] = {0xff, 1, 0, 0};
        assert(irx_rb_stream_reader_open_buffer(invalid, sizeof(invalid),
                                                &reader) < 0);
        assert(reader == nullptr);
    }
}
