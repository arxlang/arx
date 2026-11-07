```
title: External scalar native bridge fixture
summary: The compiler binds package metadata to these exact extern declarations.
```
fixture_create: extern :: fn(size: i32) -> i64
fixture_note: extern :: fn(token: i64, value: f64, label: str) -> i32
fixture_write: extern :: fn(token: i64, path: str, kind: i32) -> i32
fixture_release: extern :: fn(token: i64) -> i32
fixture_alive: extern :: fn() -> i32
fixture_releases: extern :: fn() -> i32
