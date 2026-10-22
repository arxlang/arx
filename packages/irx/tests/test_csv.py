"""
title: Native CSV factories, data contracts and failure paths.
"""

from pathlib import Path

import pytest

from irx.record_batch import (
    IrxColumnType,
    RecordBatchBuilder,
    RecordBatchSchema,
    RecordBatchStreamReader,
    RecordBatchStreamWriter,
)


def test_csv_quotes_nulls_and_batches(tmp_path: Path) -> None:
    """
    title: >-
      Preserve UTF-8, multiline quotes, empty strings, nulls and all batches.
    parameters:
      tmp_path:
        type: Path
    """
    schema = RecordBatchSchema()
    schema.add_field("id", IrxColumnType.INT64, False)
    schema.add_field("text", IrxColumnType.UTF8)
    path = tmp_path / "data.csv"
    path.write_text(
        'id,text\r\n1,"λ,\n""quoted"""\r\n2,""\r\n3,\r\n4,NA\r\n5,NULL\r\n',
        encoding="utf-8",
    )
    values: list[str | None] = []
    counts: list[int] = []
    with RecordBatchStreamReader.open_csv(
        path, schema=schema, block_size=32
    ) as reader:
        while (batch := reader.next_batch()) is not None:
            counts.append(batch.num_rows)
            for i in range(batch.num_rows):
                values.append(
                    None if batch.is_null(1, i) else batch.get_string(1, i)
                )
            batch.release()
    assert len(counts) > 1
    assert values == ['λ,\n"quoted"', "", None, "NA", "NULL"]
    with pytest.raises(RuntimeError, match="closed"):
        reader.next_batch()


@pytest.mark.parametrize("header", [True, False])
def test_csv_write_read_and_lifecycle(tmp_path: Path, header: bool) -> None:
    """
    title: Exact typed roundtrip supports headerless files and closed guards.
    parameters:
      tmp_path:
        type: Path
      header:
        type: bool
    """
    schema = RecordBatchSchema().add_field("value", IrxColumnType.INT16, False)
    builder = RecordBatchBuilder(schema)
    expected = 17
    builder.append_int16(0, expected)
    batch = builder.finish()
    path = tmp_path / "out.csv"
    writer = RecordBatchStreamWriter.open_csv(
        schema, path, header=header, delimiter=";"
    )
    writer.write_batch(batch)
    writer.close()
    writer.close()
    with pytest.raises(RuntimeError, match="closed"):
        writer.write_batch(batch)
    writer.release()
    writer.close()
    reader = RecordBatchStreamReader.open_csv(
        path, schema=schema, header=header, delimiter=";"
    )
    result = reader.next_batch()
    reader.close()
    assert result is not None
    assert result.get_int16(0, 0) == expected
    result.release()
    batch.release()
    builder.release()


@pytest.mark.parametrize("contents", ["", "a,a\n1,2\n", ",a\n1,2\n", "a\n\n"])
def test_csv_inference_failures(tmp_path: Path, contents: str) -> None:
    """
    title: Reject empty files, ambiguous names and unsupported inferred nulls.
    parameters:
      tmp_path:
        type: Path
      contents:
        type: str
    """
    path = tmp_path / "bad.csv"
    path.write_text(contents)
    with pytest.raises(RuntimeError):
        RecordBatchStreamReader.open_csv(path)


@pytest.mark.parametrize("delimiter", ["", "xx", "λ", "\0", '"', "\r", "\n"])
def test_invalid_options_do_not_truncate(
    tmp_path: Path, delimiter: str
) -> None:
    """
    title: Validate CSV options before opening or truncating output.
    parameters:
      tmp_path:
        type: Path
      delimiter:
        type: str
    """
    path = tmp_path / "keep.csv"
    path.write_text("keep")
    schema = RecordBatchSchema().add_field("a", IrxColumnType.INT64)
    with pytest.raises(ValueError, match="delimiter"):
        RecordBatchStreamWriter.open_csv(schema, path, delimiter=delimiter)
    assert path.read_text() == "keep"


def test_typed_header_only_and_schema_errors(tmp_path: Path) -> None:
    """
    title: >-
      Preserve header-only typed input but reject drift, overflow and nulls.
    parameters:
      tmp_path:
        type: Path
    """
    schema = RecordBatchSchema().add_field("a", IrxColumnType.INT8, False)
    path = tmp_path / "in.csv"
    path.write_text("a\n")
    with RecordBatchStreamReader.open_csv(path, schema=schema) as reader:
        for batch in reader:
            assert batch.num_rows == 0
    for contents in (
        "b\n1\n",
        "a\n128\n",
        'a\n""\n',
        "a\n\n",
        "a,b\n1,2\n",
        "a\n1,2\n",
    ):
        path.write_text(contents)
        with pytest.raises(RuntimeError):
            with RecordBatchStreamReader.open_csv(
                path, schema=schema
            ) as reader:
                list(reader)


def test_nested_writer_schema_preserves_existing_file(tmp_path: Path) -> None:
    """
    title: Reject unsupported nested CSV schemas before truncating output.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "keep.csv"
    path.write_text("keep")
    schema = RecordBatchSchema().add_list_field("items", IrxColumnType.INT32)
    with pytest.raises(RuntimeError, match="Unsupported CSV"):
        RecordBatchStreamWriter.open_csv(schema, path)
    assert path.read_text() == "keep"


@pytest.mark.parametrize("block_size", [0, -1, 1 << 31, True])
def test_csv_rejects_invalid_block_size(
    tmp_path: Path, block_size: int
) -> None:
    """
    title: >-
      Reject invalid sizes before narrowing Python integers across the ABI.
    parameters:
      tmp_path:
        type: Path
      block_size:
        type: int
    """
    with pytest.raises(ValueError, match="block_size"):
        RecordBatchStreamReader.open_csv(
            tmp_path / "missing", block_size=block_size
        )


def test_late_schema_drift_and_invalid_utf8(tmp_path: Path) -> None:
    """
    title: >-
      Later incompatible rows and malformed UTF-8 never silently disappear.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "late.csv"
    path.write_text("id\n" + "1\n" * 100 + "text\n")
    with RecordBatchStreamReader.open_csv(path, block_size=32) as reader:
        first = reader.next_batch()
        assert first is not None
        first.release()
        with pytest.raises(RuntimeError, match="conversion"):
            list(reader)
    path.write_bytes(b"name\n\xff\n")
    schema = RecordBatchSchema().add_field("name", IrxColumnType.UTF8)
    with pytest.raises(RuntimeError):
        with RecordBatchStreamReader.open_csv(path, schema=schema) as reader:
            list(reader)


def test_released_schema_is_not_dereferenced(tmp_path: Path) -> None:
    """
    title: >-
      CSV factories reject released Python schema owners before native calls.
    parameters:
      tmp_path:
        type: Path
    """
    schema = RecordBatchSchema().add_field("a", IrxColumnType.INT64)
    schema.release()
    with pytest.raises(RuntimeError, match="released"):
        RecordBatchStreamWriter.open_csv(schema, tmp_path / "out.csv")
    with pytest.raises(RuntimeError, match="released"):
        RecordBatchStreamReader.open_csv(tmp_path / "in.csv", schema=schema)


def test_headerless_inference_and_schema_snapshot(tmp_path: Path) -> None:
    """
    title: >-
      Headerless inference keeps the first row and typed readers own schemas.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "in.csv"
    path.write_text("1\n2\n")
    expected_rows = 2
    with RecordBatchStreamReader.open_csv(path, header=False) as reader:
        batch = reader.next_batch()
        assert batch is not None
        assert batch.num_rows == expected_rows
        assert batch.get_int64(0, 0) == 1
        batch.release()
    schema = RecordBatchSchema().add_field("a", IrxColumnType.INT64, False)
    with RecordBatchStreamReader.open_csv(
        path, schema=schema, header=False
    ) as reader:
        schema.release()
        batch = reader.next_batch()
        assert batch is not None
        assert batch.num_rows == expected_rows
        batch.release()


@pytest.mark.parametrize("header", [True, False])
def test_unified_csv_preserves_existing_bytes(
    tmp_path: Path, header: bool
) -> None:
    """
    title: The unified owner preserves quoting, nulls and headerless CSV bytes.
    parameters:
      tmp_path:
        type: Path
      header:
        type: bool
    """
    from irx.record_batch import CSV  # noqa: PLC0415

    schema = RecordBatchSchema().add_field("id", IrxColumnType.INT64, False)
    schema.add_field("text", IrxColumnType.UTF8)
    builder = RecordBatchBuilder(schema)
    for index, value in enumerate(["", None, 'λ;\n"quoted"']):
        builder.append_int64(0, index)
        if value is None:
            builder.append_null(1)
        else:
            builder.append_string(1, value)
    batch = builder.finish()
    old = tmp_path / "legacy.csv"
    new = tmp_path / "unified.csv"
    with RecordBatchStreamWriter.open_csv(
        schema, old, delimiter=";", header=header
    ) as writer:
        writer.write_batch(batch)
    with CSV() as file:
        file.open_write(new, schema, delimiter=";", header=header)
        file.write_batch(batch)
        file.close()
        assert new.read_bytes() == old.read_bytes()
        file.open_read(
            new, schema=schema, delimiter=";", header=header, block_size=32
        )
        snapshot = file.schema()
        snapshot.release()
        values: list[str | None] = []
        for read in file:
            for row in range(read.num_rows):
                values.append(
                    None if read.is_null(1, row) else read.get_string(1, row)
                )
        assert values == ["", None, 'λ;\n"quoted"']
    batch.release()
    builder.release()
    schema.release()
