```
title: External scalar native bridge fixture
summary: The compiler binds package metadata to these exact extern declarations.
```
extern fixture_create(size: i32) -> i64
extern fixture_note(token: i64, value: f64, label: str) -> i32
extern fixture_write(token: i64, path: str, kind: i32) -> i32
extern fixture_release(token: i64) -> i32
extern fixture_alive() -> i32
extern fixture_releases() -> i32
