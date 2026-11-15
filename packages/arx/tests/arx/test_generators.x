```
title: Integer range workflows
summary: Cover lazy values, independent cursors, and explicit bounded copies.
```

fn test_range_returns_zero_based_values() -> none:
  ```
  title: test_range_returns_zero_based_values
  summary: Verifies that range(start, stop) returns zero-based values.
  ```
  values: range = range(0, 4)
  first: i32 = values[0]
  second: i32 = values[1]
  third: i32 = values[2]
  fourth: i32 = values[3]
  assert first == 0, "range(0, 4)[0] should be 0"
  assert second == 1, "range(0, 4)[1] should be 1"
  assert third == 2, "range(0, 4)[2] should be 2"
  assert fourth == 3, "range(0, 4)[3] should be 3"

fn test_range_supports_inline_indexing() -> none:
  ```
  title: test_range_supports_inline_indexing
  summary: Verifies that range results can be indexed inline.
  ```
  value: i32 = range(0, 3)[2]
  assert value == 2, "range(0, 3)[2] should be 2"

fn test_range_supports_custom_step() -> none:
  ```
  title: test_range_supports_custom_step
  summary: Verifies that range(start, stop, step) honors custom steps.
  ```
  values: range = range(2, 8, 2)
  first: i32 = values[0]
  second: i32 = values[1]
  third: i32 = values[2]
  assert first == 2, "range(2, 8, 2)[0] should be 2"
  assert second == 4, "range(2, 8, 2)[1] should be 4"
  assert third == 6, "range(2, 8, 2)[2] should be 6"

fn test_range_supports_descending_step() -> none:
  ```
  title: test_range_supports_descending_step
  summary: Verifies that range(start, stop, step) supports negative steps.
  ```
  values: range = range(5, 0, 0 - 1)
  first: i32 = values[0]
  second: i32 = values[1]
  third: i32 = values[2]
  fourth: i32 = values[3]
  fifth: i32 = values[4]
  assert first == 5, "range(5, 0, -1)[0] should be 5"
  assert second == 4, "range(5, 0, -1)[1] should be 4"
  assert third == 3, "range(5, 0, -1)[2] should be 3"
  assert fourth == 2, "range(5, 0, -1)[3] should be 2"
  assert fifth == 1, "range(5, 0, -1)[4] should be 1"

fn test_range_empty_intervals() -> none:
  ```
  title: test_range_empty_intervals
  summary: Equal endpoints and wrong-direction steps produce empty ranges.
  ```
  count: i32 = 0
  for value in range(7, 7):
    count = count + 1
  for value in range(7, 7, 0 - 1):
    count = count + 1
  for value in range(3, 0):
    count = count + 1
  for value in range(0, 3, 0 - 1):
    count = count + 1
  assert count == 0

class RangeOwner:
  ```
  title: Observe body-local cleanup on cursor transfers.
  ```
  released: static :: i32 = 0
  argument_order: static :: i32 = 0
  calls: static :: i32 = 0

  fn __del__(self) -> none:
    RangeOwner.released = RangeOwner.released + 1

fn record_argument(value: i32) -> i32:
  ```
  title: Observe range evaluation order without changing the returned endpoint.
  ```
  RangeOwner.argument_order = RangeOwner.argument_order * 10 + value
  return value

fn first_range_value(values: range) -> i32:
  ```
  title: Borrow a range value and leave its cursor through a return.
  ```
  for item in values:
    owner: RangeOwner = RangeOwner()
    return item
  return -1

fn make_range() -> range:
  ```
  title: Return a range without allocating collection storage.
  ```
  RangeOwner.calls = RangeOwner.calls + 1
  return range(4)

fn test_lazy_range_workflows() -> none:
  ```
  title: Use independent positions, checked access, and explicit materialization.
  ```
  minimum: i32 = 0 - 2147483647 - 1
  full: range = range(minimum, 2147483647)
  assert len(full) == 4294967295
  assert full[0] == minimum
  assert full[4294967294] == 2147483646
  assert len(range(stop=0)) == 0
  assert len(range(stop=-5)) == 0
  assert len(range(4, stop=8, step=2)) == 2
  RangeOwner.argument_order = 0
  named: auto = range(stop=record_argument(6), step=record_argument(2), start=record_argument(0))
  assert RangeOwner.argument_order == 620
  assert len(named) == 3
  assert named[2] == 4

  total: i32 = 0
  for outer in range(3):
    for inner in range(3):
      total = total + outer + inner
  assert total == 18
  values: range = make_range()
  assert RangeOwner.calls == 1
  saved: range = values
  total = 0
  for item in values:
    values = range(100)
    total = total + item
  assert total == 6
  assert len(values) == 100
  assert len(saved) == 4
  total = 0
  for item in make_range():
    total = total + item
  assert total == 6
  assert RangeOwner.calls == 2
  assert first_range_value(saved) == 0
  assert first_range_value(saved) == 0
  assert RangeOwner.released == 2

  for item in full:
    owner: RangeOwner = RangeOwner()
    if item == minimum:
      continue
    break
  assert RangeOwner.released == 4
  try:
    for item in full:
      owner: RangeOwner = RangeOwner()
      raise ValueError("body")
  except ValueError as error:
    assert error.message == "body"
  assert RangeOwner.released == 5
  count: i32 = 0
  for item in range(3):
    try:
      continue
    finally:
      count = count + 1
  assert count == 3

  copied: list[i32] = list(saved, max_items=4)
  copied.append(9)
  assert len(copied) == 5
  assert copied[3] == 3
  assert len(saved) == 4
  try:
    copied = list(range(5), max_items=2)
    assert false, "a bounded copy must not publish a truncated prefix"
  except ValueError:
    assert copied[4] == 9
  assert len(list(range(0), max_items=0)) == 0
  assert len(bytes(range(256))) == 256
  try:
    saved[-1]
    assert false, "negative range indices are unsupported"
  except IndexError:
    assert true
  try:
    saved[4]
    assert false, "index at length must fail"
  except IndexError:
    assert true
  try:
    range(0)[0]
    assert false, "empty range access must fail"
  except IndexError:
    assert true
