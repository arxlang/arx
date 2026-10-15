```
title: Native schema descriptors
summary: Inspect Arrow-core types and schemas without importing Arrow.
```

fn layout() -> schema:
  ```
  title: Return a shared immutable schema value.
  ```
  return schema[count: i64 | none, label: string] {producer: "arx"}

fn main() -> i32:
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
  return 0
