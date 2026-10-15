```
title: Checked C Data owners and packed source buffers
```
fn make_data() -> c_data:
  var values: array[string | none] = array[string | none]("λ", none)
  return export_c_data(values)

fn main() -> i32:
  var token: c_data | none = make_data()
  var copied: array[string | none] = array_from_c_data(expect_valid(token), field[value:string | none])
  token = none
  assert scalar_text(expect_valid(array_at(copied, 0))) == "λ"
  assert is_null(array_at(copied, 1))
  var packed: array[bool | none] = array_from_buffers(field[value:bool | none], array[u8](cast(10, u8)), array[u8](cast(6, u8)), 3, 1)
  assert expect_valid(array_at(packed, 0))
  assert expect_valid(array_at(packed, 1)) == false
  assert is_null(array_at(packed, 2))
  var masked: array[string | none] = array_with_validity(array[string]("a", "b", "c"), array[u8](cast(160, u8)), 5)
  assert scalar_text(expect_valid(array_at(masked, 0))) == "a"
  assert is_null(array_at(masked, 1))
  assert scalar_text(expect_valid(array_at(masked, 2))) == "c"
  return 0
