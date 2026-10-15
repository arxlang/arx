```
title: Native schema descriptors
summary: Inspect Arrow-core types and schemas without importing Arrow.
```

fn layout() -> schema:
  ```
  title: Return a shared immutable schema value.
  ```
  return schema[count: i64 | none, label: string] {producer: "arx"}

fn test_native_schema_descriptors() -> none:
  ```
  title: Construct and inspect descriptors using native Arrow C++.
  ```
  var rows: schema = layout()
  var count: field = schema_field(rows, 0)
  assert schema_nfields(rows) == 2
  assert field_name(count) == "count"
  assert field_nullable(count)
  assert descriptor_equal(field_type(count), datatype[i64])
  assert type_bit_width(datatype[bool]) == 1
  assert conversion_kind(datatype[i32], datatype[i64]) == 1
  return none


class Layout:
  ```
  title: Own shared immutable descriptors in a managed class.
  ```
  @[public, mutable]
  rows: schema = schema[id: i64]

  @[public, mutable]
  column: field = field[id: i64]

  @[public, mutable]
  logical: datatype = datatype[i64]

fn test_descriptor_class_fields() -> none:
  ```
  title: Replace descriptor owners and inspect retained class fields.
  ```
  var box: Layout = Layout()
  var saved: field = box.column
  box.rows = schema[]
  box.column = field[text: string]
  box.logical = datatype[string]
  assert schema_nfields(box.rows) == 0
  assert field_name(saved) == "id"
  assert field_name(box.column) == "text"
  assert descriptor_equal(box.logical, datatype[string])
