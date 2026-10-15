```
title: logical scalar owners
```
class Box:
  ```
  title: Shared optional scalar storage
  ```
  @[public, mutable]
  text: scalar[string] | none = none
fn box() -> Box | none:
  var result: Box = Box()
  result.text = scalar[string]("boxed")
  return result
fn make() -> scalar[string] | none:
  var values: array[string | none] = array[string | none]("λ", none, "")
  var copy: array[string | none] = array_copy(array_slice(values, 0, 2))
  assert array_equal(copy, array_slice(values, 0, 2))
  assert is_null(array_at(copy, 1))
  assert scalar_text(expect_valid(array_at(values, 2))) == ""
  return array_at(copy, 0)
fn scalar_identity(value: scalar[string]) -> scalar[string]:
  return value
fn main() -> i32:
  var boxed: Box | none = box()
  var saved: Box | none = boxed
  boxed = none
  assert scalar_text(expect_valid(expect_valid(saved).text)) == "boxed"
  saved = none
  var source: tensor[i32, 3] = [1, 2, 3]
  var copied: array[i32] = array_from_buffer(source)
  assert expect_valid(array_at(copied, 1)) == 2
  var item: scalar[string] | none = make()
  assert scalar_text(expect_valid(item)) == "λ"
  var other: scalar[string] | none = item
  item = none
  assert scalar_text(scalar_identity(expect_valid(other))) == "λ"
  var builder: array_builder[string | none] = array_builder[string | none]()
  builder_reserve(builder, 3)
  builder_append(builder, expect_valid(other))
  builder_append(builder, none)
  var first: array[string | none] = builder_finish(builder)
  assert builder_length(builder) == 0
  builder_append(builder, "second")
  var second: array[string | none] = builder_finish(builder)
  var chunks: chunked_array[string | none] = chunked_array[string | none](first, second)
  assert scalar_text(expect_valid(array_at(chunks, 2))) == "second"
  assert is_null(array_at(chunks, 1))
  assert array_length(combine_chunks(chunks)) == 3
  return 0
