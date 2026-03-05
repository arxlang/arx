# Functions

Functions are defined with `fn`, a name, parameters in `()`, and a body after
`:` with indentation.

## Definition Syntax

```arx
fn add(x, y):
  return x + y
```

## Calling Functions

```arx
fn double(v):
  return v * 2

fn main():
  return double(10)
```

## Function Body Rules

- The block starts after `:`.
- The next line must be indented.
- A function docstring (if present) must be the first element in the function
  block.
- Function docstrings must use Douki YAML and include at least `title`.

Example:

```arx
fn add(x, y):
```

title: Add two numbers summary: Returns x + y

```
return x + y
```

## Extern Prototypes

Arx also supports external function declarations:

```arx
extern putchard(x)
```
