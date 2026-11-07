```
title: Exception syntax fixture
summary: Nominal handlers, explicit context suppression, else, and finalization.
```

reject: fn(value: i32) -> i32:
  if value < 0:
    raise ValueError("count must be nonnegative")
  return value

main: fn() -> i32:
  try:
    print(reject(-1))
  except (ValueError, RuntimeError) as error:
    raise error from none
  else:
    print("accepted")
  finally:
    print("finished")
  return 0
