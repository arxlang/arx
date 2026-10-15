```
title: Native extension storage with preserved logical identity
```
type Price = scalar[extension(extension_name="arx.example.price", extension_metadata="USD:v1")[storage:decimal128(precision=12, scale=2)]]

fn main() -> i32:
  var price: Price = scalar[extension(extension_name="arx.example.price", extension_metadata="USD:v1")[storage:decimal128(precision=12, scale=2)]](scalar[decimal128(precision=12, scale=2)]("12.34"))
  var values: array[extension(extension_name="arx.example.price", extension_metadata="USD:v1")[storage:decimal128(precision=12, scale=2)] | none] = array[extension(extension_name="arx.example.price", extension_metadata="USD:v1")[storage:decimal128(precision=12, scale=2)] | none](price, none)
  assert is_null(array_at(values, 1))
  assert scalar_equal(scalar_storage(expect_valid(array_at(array_copy(values), 0))), scalar[decimal128(precision=12, scale=2)]("12.34"))
  var uuid: scalar[extension(extension_name="arrow.uuid", extension_metadata="")[storage:fixed_binary(byte_width=16)]] = scalar[extension(extension_name="arrow.uuid", extension_metadata="")[storage:fixed_binary(byte_width=16)]](scalar[fixed_binary(byte_width=16)]("0123456789abcdef"))
  assert array_length(scalar_bytes(scalar_storage(uuid))) == 16
  var encoded: scalar[extension(extension_name="arrow.json", extension_metadata="")[storage:string]] = scalar[extension(extension_name="arrow.json", extension_metadata="")[storage:string]](scalar[string]("{}"))
  assert scalar_text(scalar_storage(encoded)) == "{}"
  return 0
