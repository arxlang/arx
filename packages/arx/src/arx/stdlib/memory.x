```
title: Standard-library memory operations
summary: >-
  copy reads a dynamic list and creates an independent list of its exact type.
  Numeric and Boolean elements copy by value, and each string owns its bytes.
  Owned expressions and borrowed list parameters are valid inputs.
```

@<T: (
  list[i8] | list[i16] | list[i32] | list[i64] |
  list[u8] | list[u16] | list[u32] | list[u64] |
  list[f16] | list[f32] | list[f64] | list[bool] | list[str]
)>
extern copy(value: T) -> T
