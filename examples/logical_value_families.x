```
title: Logical value families
```
fn main() -> i32:
  var v0: scalar[string] = scalar[string]("λ")
  var a0: array[string | none] = array[string | none](v0, none)
  assert scalar_equal(expect_valid(array_at(a0, 0)), v0)
  assert is_null(array_at(a0, 1))
  assert array_null_count(a0) == 1
  assert array_equal(array_copy(a0), a0)
  var v1: scalar[large_string] = scalar[large_string]("large")
  var a1: array[large_string | none] = array[large_string | none](v1, none)
  assert scalar_equal(expect_valid(array_at(a1, 0)), v1)
  assert is_null(array_at(a1, 1))
  assert array_null_count(a1) == 1
  assert array_equal(array_copy(a1), a1)
  var v2: scalar[string_view] = scalar[string_view]("view")
  var a2: array[string_view | none] = array[string_view | none](v2, none)
  assert scalar_equal(expect_valid(array_at(a2, 0)), v2)
  assert is_null(array_at(a2, 1))
  assert array_null_count(a2) == 1
  assert array_equal(array_copy(a2), a2)
  var v3: scalar[binary] = scalar[binary](array[u8](cast(0, u8), cast(255, u8)))
  var a3: array[binary | none] = array[binary | none](v3, none)
  assert scalar_equal(expect_valid(array_at(a3, 0)), v3)
  assert is_null(array_at(a3, 1))
  assert array_null_count(a3) == 1
  assert array_equal(array_copy(a3), a3)
  var v4: scalar[large_binary] = scalar[large_binary]("abc")
  var a4: array[large_binary | none] = array[large_binary | none](v4, none)
  assert scalar_equal(expect_valid(array_at(a4, 0)), v4)
  assert is_null(array_at(a4, 1))
  assert array_null_count(a4) == 1
  assert array_equal(array_copy(a4), a4)
  var v5: scalar[binary_view] = scalar[binary_view]("abc")
  var a5: array[binary_view | none] = array[binary_view | none](v5, none)
  assert scalar_equal(expect_valid(array_at(a5, 0)), v5)
  assert is_null(array_at(a5, 1))
  assert array_null_count(a5) == 1
  assert array_equal(array_copy(a5), a5)
  var v6: scalar[fixed_binary(byte_width=3)] = scalar[fixed_binary(byte_width=3)]("abc")
  var a6: array[fixed_binary(byte_width=3) | none] = array[fixed_binary(byte_width=3) | none](v6, none)
  assert scalar_equal(expect_valid(array_at(a6, 0)), v6)
  assert is_null(array_at(a6, 1))
  assert array_null_count(a6) == 1
  assert array_equal(array_copy(a6), a6)
  var v7: scalar[date32] = scalar[date32]("2024-01-02")
  var a7: array[date32 | none] = array[date32 | none](v7, none)
  assert scalar_equal(expect_valid(array_at(a7, 0)), v7)
  assert is_null(array_at(a7, 1))
  assert array_null_count(a7) == 1
  assert array_equal(array_copy(a7), a7)
  var v8: scalar[date64] = scalar[date64]("2024-01-02")
  var a8: array[date64 | none] = array[date64 | none](v8, none)
  assert scalar_equal(expect_valid(array_at(a8, 0)), v8)
  assert is_null(array_at(a8, 1))
  assert array_null_count(a8) == 1
  assert array_equal(array_copy(a8), a8)
  var v9: scalar[time32(unit="s")] = scalar[time32(unit="s")]("12:34:56")
  var a9: array[time32(unit="s") | none] = array[time32(unit="s") | none](v9, none)
  assert scalar_equal(expect_valid(array_at(a9, 0)), v9)
  assert is_null(array_at(a9, 1))
  assert array_null_count(a9) == 1
  assert array_equal(array_copy(a9), a9)
  var v10: scalar[time64(unit="us")] = scalar[time64(unit="us")]("12:34:56.123456")
  var a10: array[time64(unit="us") | none] = array[time64(unit="us") | none](v10, none)
  assert scalar_equal(expect_valid(array_at(a10, 0)), v10)
  assert is_null(array_at(a10, 1))
  assert array_null_count(a10) == 1
  assert array_equal(array_copy(a10), a10)
  var v11: scalar[timestamp(unit="ns", timezone="UTC")] = scalar[timestamp(unit="ns", timezone="UTC")]("2024-01-02T03:04:05Z")
  var a11: array[timestamp(unit="ns", timezone="UTC") | none] = array[timestamp(unit="ns", timezone="UTC") | none](v11, none)
  assert scalar_equal(expect_valid(array_at(a11, 0)), v11)
  assert is_null(array_at(a11, 1))
  assert array_null_count(a11) == 1
  assert array_equal(array_copy(a11), a11)
  var v12: scalar[duration(unit="us")] = scalar[duration(unit="us")]("123")
  var a12: array[duration(unit="us") | none] = array[duration(unit="us") | none](v12, none)
  assert scalar_equal(expect_valid(array_at(a12, 0)), v12)
  assert is_null(array_at(a12, 1))
  assert array_null_count(a12) == 1
  assert array_equal(array_copy(a12), a12)
  var v13: scalar[month_interval] = scalar[month_interval](2)
  var a13: array[month_interval | none] = array[month_interval | none](v13, none)
  assert scalar_equal(expect_valid(array_at(a13, 0)), v13)
  assert is_null(array_at(a13, 1))
  assert array_null_count(a13) == 1
  assert array_equal(array_copy(a13), a13)
  var v14: scalar[day_time_interval] = scalar[day_time_interval](2, 3)
  var a14: array[day_time_interval | none] = array[day_time_interval | none](v14, none)
  assert scalar_equal(expect_valid(array_at(a14, 0)), v14)
  assert is_null(array_at(a14, 1))
  assert array_null_count(a14) == 1
  assert array_equal(array_copy(a14), a14)
  var v15: scalar[month_day_nano_interval] = scalar[month_day_nano_interval](2, 3, 4)
  var a15: array[month_day_nano_interval | none] = array[month_day_nano_interval | none](v15, none)
  assert scalar_equal(expect_valid(array_at(a15, 0)), v15)
  assert is_null(array_at(a15, 1))
  assert array_null_count(a15) == 1
  assert array_equal(array_copy(a15), a15)
  var v16: scalar[decimal32(precision=6, scale=2)] = scalar[decimal32(precision=6, scale=2)]("12.34")
  var a16: array[decimal32(precision=6, scale=2) | none] = array[decimal32(precision=6, scale=2) | none](v16, none)
  assert scalar_equal(expect_valid(array_at(a16, 0)), v16)
  assert is_null(array_at(a16, 1))
  assert array_null_count(a16) == 1
  assert array_equal(array_copy(a16), a16)
  var v17: scalar[decimal64(precision=6, scale=2)] = scalar[decimal64(precision=6, scale=2)]("12.34")
  var a17: array[decimal64(precision=6, scale=2) | none] = array[decimal64(precision=6, scale=2) | none](v17, none)
  assert scalar_equal(expect_valid(array_at(a17, 0)), v17)
  assert is_null(array_at(a17, 1))
  assert array_null_count(a17) == 1
  assert array_equal(array_copy(a17), a17)
  var v18: scalar[decimal128(precision=6, scale=2)] = scalar[decimal128(precision=6, scale=2)]("12.34")
  var a18: array[decimal128(precision=6, scale=2) | none] = array[decimal128(precision=6, scale=2) | none](v18, none)
  assert scalar_equal(expect_valid(array_at(a18, 0)), v18)
  assert is_null(array_at(a18, 1))
  assert array_null_count(a18) == 1
  assert array_equal(array_copy(a18), a18)
  var v19: scalar[decimal256(precision=6, scale=2)] = scalar[decimal256(precision=6, scale=2)]("12.34")
  var a19: array[decimal256(precision=6, scale=2) | none] = array[decimal256(precision=6, scale=2) | none](v19, none)
  assert scalar_equal(expect_valid(array_at(a19, 0)), v19)
  assert is_null(array_at(a19, 1))
  assert array_null_count(a19) == 1
  assert array_equal(array_copy(a19), a19)
  var v20: scalar[list[item:i32 | none]] = scalar[list[item:i32 | none]](array[i32 | none](1, none))
  var a20: array[list[item:i32 | none] | none] = array[list[item:i32 | none] | none](v20, none)
  assert scalar_equal(expect_valid(array_at(a20, 0)), v20)
  assert is_null(array_at(a20, 1))
  assert array_null_count(a20) == 1
  assert array_equal(array_copy(a20), a20)
  var v21: scalar[large_list[item:i32 | none]] = scalar[large_list[item:i32 | none]](array[i32 | none](1, none))
  var a21: array[large_list[item:i32 | none] | none] = array[large_list[item:i32 | none] | none](v21, none)
  assert scalar_equal(expect_valid(array_at(a21, 0)), v21)
  assert is_null(array_at(a21, 1))
  assert array_null_count(a21) == 1
  assert array_equal(array_copy(a21), a21)
  var v22: scalar[list_view[item:i32 | none]] = scalar[list_view[item:i32 | none]](array[i32 | none](1, none))
  var a22: array[list_view[item:i32 | none] | none] = array[list_view[item:i32 | none] | none](v22, none)
  assert scalar_equal(expect_valid(array_at(a22, 0)), v22)
  assert is_null(array_at(a22, 1))
  assert array_null_count(a22) == 1
  assert array_equal(array_copy(a22), a22)
  var v23: scalar[large_list_view[item:i32 | none]] = scalar[large_list_view[item:i32 | none]](array[i32 | none](1, none))
  var a23: array[large_list_view[item:i32 | none] | none] = array[large_list_view[item:i32 | none] | none](v23, none)
  assert scalar_equal(expect_valid(array_at(a23, 0)), v23)
  assert is_null(array_at(a23, 1))
  assert array_null_count(a23) == 1
  assert array_equal(array_copy(a23), a23)
  var v24: scalar[fixed_list(list_size=2)[item:i32 | none]] = scalar[fixed_list(list_size=2)[item:i32 | none]](array[i32 | none](1, none))
  var a24: array[fixed_list(list_size=2)[item:i32 | none] | none] = array[fixed_list(list_size=2)[item:i32 | none] | none](v24, none)
  assert scalar_equal(expect_valid(array_at(a24, 0)), v24)
  assert is_null(array_at(a24, 1))
  assert array_null_count(a24) == 1
  assert array_equal(array_copy(a24), a24)
  var v25: scalar[struct[]] = scalar[struct[]]()
  var a25: array[struct[] | none] = array[struct[] | none](v25, none)
  assert scalar_equal(expect_valid(array_at(a25, 0)), v25)
  assert is_null(array_at(a25, 1))
  assert array_null_count(a25) == 1
  assert array_equal(array_copy(a25), a25)
  var v26: scalar[map[entries:struct[key:i32, value:string | none]]] = scalar[map[entries:struct[key:i32, value:string | none]]](array[struct[key:i32, value:string | none]](scalar[struct[key:i32, value:string | none]](scalar[i32]("1"), none)))
  var a26: array[map[entries:struct[key:i32, value:string | none]] | none] = array[map[entries:struct[key:i32, value:string | none]] | none](v26, none)
  assert scalar_equal(expect_valid(array_at(a26, 0)), v26)
  assert is_null(array_at(a26, 1))
  assert array_null_count(a26) == 1
  assert array_equal(array_copy(a26), a26)
  var v27: scalar[dictionary[indices:i8, values:string]] = scalar[dictionary[indices:i8, values:string]](scalar[i8]("0"), array[string](scalar[string]("word")))
  var a27: array[dictionary[indices:i8, values:string] | none] = array[dictionary[indices:i8, values:string] | none](v27, none)
  assert scalar_equal(expect_valid(array_at(a27, 0)), v27)
  assert is_null(array_at(a27, 1))
  assert array_null_count(a27) == 1
  assert array_equal(array_copy(a27), a27)
  var v28: scalar[run_end_encoded[run_ends:i16, values:string | none]] = scalar[run_end_encoded[run_ends:i16, values:string | none]](scalar[string]("run"))
  var a28: array[run_end_encoded[run_ends:i16, values:string | none] | none] = array[run_end_encoded[run_ends:i16, values:string | none] | none](v28, none)
  assert scalar_equal(expect_valid(array_at(a28, 0)), v28)
  assert is_null(array_at(a28, 1))
  assert array_null_count(a28) == 1
  assert array_equal(array_copy(a28), a28)
  var v29: scalar[dense_union(type_codes=[3, 7])[number:i32, text:string]] = scalar[dense_union(type_codes=[3, 7])[number:i32, text:string]]("text", scalar[string]("union"))
  var a29: array[dense_union(type_codes=[3, 7])[number:i32, text:string] | none] = array[dense_union(type_codes=[3, 7])[number:i32, text:string] | none](v29, none)
  assert scalar_equal(expect_valid(array_at(a29, 0)), v29)
  assert is_null(array_at(a29, 1))
  assert array_null_count(a29) == 1
  assert array_equal(array_copy(a29), a29)
  var v30: scalar[sparse_union(type_codes=[3, 7])[number:i32, text:string]] = scalar[sparse_union(type_codes=[3, 7])[number:i32, text:string]]("text", scalar[string]("union"))
  var a30: array[sparse_union(type_codes=[3, 7])[number:i32, text:string] | none] = array[sparse_union(type_codes=[3, 7])[number:i32, text:string] | none](v30, none)
  assert scalar_equal(expect_valid(array_at(a30, 0)), v30)
  assert is_null(array_at(a30, 1))
  assert array_null_count(a30) == 1
  assert array_equal(array_copy(a30), a30)
  var raw: array[u8] = scalar_bytes(v3)
  assert expect_valid(array_at(raw, 0)) == 0
  assert expect_valid(array_at(raw, 1)) == 255
  var absent: array[null | none] = array[null | none](none, none)
  assert array_null_count(absent) == 2
  assert is_null(array_at(absent, 1))
  return 0
