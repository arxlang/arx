```
title: Nominal builtin exception hierarchy
summary: Message construction and diagnostic storage use a registered native capability.
```

class BaseException:
  ```
  title: Root exception
  summary: Owns an immutable message and private native diagnostic state.
  ```
  @[private]
  record: NativeExceptionRecord
  @[public, constant]
  message: str = ""

class Exception(BaseException):
  ```
  title: Exception
  summary: Nominal BaseException subtype with an inherited message constructor.
  ```

class ValueError(Exception):
  ```
  title: ValueError
  summary: Nominal Exception subtype with an inherited message constructor.
  ```

class TypeError(Exception):
  ```
  title: TypeError
  summary: Nominal Exception subtype with an inherited message constructor.
  ```

class RuntimeError(Exception):
  ```
  title: RuntimeError
  summary: Nominal Exception subtype with an inherited message constructor.
  ```

class AssertionError(Exception):
  ```
  title: AssertionError
  summary: Nominal Exception subtype with an inherited message constructor.
  ```

class OSError(Exception):
  ```
  title: OSError
  summary: Nominal Exception subtype with an inherited message constructor.
  ```

class ArithmeticError(Exception):
  ```
  title: ArithmeticError
  summary: Nominal Exception subtype with an inherited message constructor.
  ```

class OverflowError(ArithmeticError):
  ```
  title: OverflowError
  summary: Nominal ArithmeticError subtype with an inherited message constructor.
  ```

class ZeroDivisionError(ArithmeticError):
  ```
  title: ZeroDivisionError
  summary: Nominal ArithmeticError subtype with an inherited message constructor.
  ```

class LookupError(Exception):
  ```
  title: LookupError
  summary: Nominal Exception subtype with an inherited message constructor.
  ```

class IndexError(LookupError):
  ```
  title: IndexError
  summary: Nominal LookupError subtype with an inherited message constructor.
  ```
