# Modules

A module in Arx is a source file (for example, `math.x`) containing top-level
statements such as function definitions and extern declarations.

## Module Layout

```arx
fn average(x, y):
  return (x + y) * 0.5
```

## Module Docstring

Arx supports module docstrings in Douki YAML format, delimited by triple
backticks:

````text
```
title: Module documentation
summary: Optional summary text
```
````

Current placement rule:

- The module docstring must be the **first top-level element** in the file.
- It must begin at **character 0 of line 1** (no leading spaces).

Valid:

````text
```
title: Module docs
```
fn main():
  return 1
````

Invalid (leading indentation before module docstring):

````text
  ```
  Module docs
  ```
fn main():
  return 1
````

For now, module docstrings are parsed and validated but ignored by AST/IR
generation.
