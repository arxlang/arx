"""
title: Generate Quarto API reference pages from Python source.
summary: Build lightweight Markdown API pages without site-generator plugins.
"""

from __future__ import annotations

import ast
import shutil
import textwrap

from dataclasses import dataclass
from pathlib import Path
from typing import TypeGuard

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
API_DIR = DOCS_DIR / "api"
SOURCE_ROOTS = (
    ROOT / "packages" / "arx" / "src",
    ROOT / "packages" / "astx" / "src",
    ROOT / "packages" / "irx" / "src",
)
PRIVATE_PREFIX = "_"


@dataclass(frozen=True)
class FunctionDoc:
    """
    title: Documentation data for one function-like symbol.
    attributes:
      name:
        type: str
      signature:
        type: str
      docstring:
        type: str
    """

    name: str
    signature: str
    docstring: str


@dataclass(frozen=True)
class ClassDoc:
    """
    title: Documentation data for one class symbol.
    attributes:
      name:
        type: str
      bases:
        type: tuple[str, Ellipsis]
      docstring:
        type: str
      methods:
        type: tuple[FunctionDoc, Ellipsis]
    """

    name: str
    bases: tuple[str, ...]
    docstring: str
    methods: tuple[FunctionDoc, ...]


@dataclass(frozen=True)
class ModuleDoc:
    """
    title: Documentation data for one Python module.
    attributes:
      name:
        type: str
      source_path:
        type: Path
      docstring:
        type: str
      classes:
        type: tuple[ClassDoc, Ellipsis]
      functions:
        type: tuple[FunctionDoc, Ellipsis]
    """

    name: str
    source_path: Path
    docstring: str
    classes: tuple[ClassDoc, ...]
    functions: tuple[FunctionDoc, ...]


class ApiDocError(Exception):
    """
    title: Raised when API documentation cannot be generated.
    """


def main() -> None:
    """
    title: Generate the API documentation tree.
    """
    modules = list(iter_modules())
    write_api_tree(modules)


def iter_modules() -> list[ModuleDoc]:
    """
    title: Collect documentation data for all public Python modules.
    returns:
      type: list[ModuleDoc]
    """
    modules: list[ModuleDoc] = []
    for source_root in SOURCE_ROOTS:
        for path in sorted(source_root.rglob("*.py")):
            if should_skip(path):
                continue
            modules.append(parse_module(source_root, path))
    return modules


def should_skip(path: Path) -> bool:
    """
    title: Return whether a Python file should be excluded from API docs.
    parameters:
      path:
        type: Path
    returns:
      type: bool
    """
    return path.name.startswith(PRIVATE_PREFIX) and path.name != "__init__.py"


def parse_module(source_root: Path, path: Path) -> ModuleDoc:
    """
    title: Parse public API documentation from one source file.
    parameters:
      source_root:
        type: Path
      path:
        type: Path
    returns:
      type: ModuleDoc
    """
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        msg = f"Cannot parse {path}: {exc}"
        raise ApiDocError(msg) from exc

    module_name = module_name_for(source_root, path)
    classes: list[ClassDoc] = []
    functions: list[FunctionDoc] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and is_public(node.name):
            classes.append(class_doc(node))
            continue
        if is_public_function(node):
            functions.append(function_doc(node))

    return ModuleDoc(
        name=module_name,
        source_path=path.relative_to(ROOT),
        docstring=clean_docstring(ast.get_docstring(tree)),
        classes=tuple(classes),
        functions=tuple(functions),
    )


def module_name_for(source_root: Path, path: Path) -> str:
    """
    title: Convert a Python path to its importable module name.
    parameters:
      source_root:
        type: Path
      path:
        type: Path
    returns:
      type: str
    """
    module_path = path.relative_to(source_root).with_suffix("")
    parts = module_path.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def class_doc(node: ast.ClassDef) -> ClassDoc:
    """
    title: Build documentation for a class definition.
    parameters:
      node:
        type: ast.ClassDef
    returns:
      type: ClassDoc
    """
    methods: list[FunctionDoc] = []
    for item in node.body:
        if is_public_function(item):
            methods.append(function_doc(item))

    return ClassDoc(
        name=node.name,
        bases=tuple(ast.unparse(base) for base in node.bases),
        docstring=clean_docstring(ast.get_docstring(node)),
        methods=tuple(methods),
    )


def function_doc(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionDoc:
    """
    title: Build documentation for a function or method definition.
    parameters:
      node:
        type: ast.FunctionDef | ast.AsyncFunctionDef
    returns:
      type: FunctionDoc
    """
    return FunctionDoc(
        name=node.name,
        signature=signature_for(node),
        docstring=clean_docstring(ast.get_docstring(node)),
    )


def signature_for(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """
    title: Return a display signature for a function-like AST node.
    parameters:
      node:
        type: ast.FunctionDef | ast.AsyncFunctionDef
    returns:
      type: str
    """
    arguments = ast.unparse(node.args)
    returns = ""
    if node.returns is not None:
        returns = f" -> {ast.unparse(node.returns)}"
    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    return f"{prefix}{node.name}({arguments}){returns}"


def clean_docstring(docstring: str | None) -> str:
    """
    title: Normalize one Python docstring for Markdown output.
    parameters:
      docstring:
        type: str | None
    returns:
      type: str
    """
    if docstring is None:
        return ""
    return textwrap.dedent(docstring).strip()


def is_public(name: str) -> bool:
    """
    title: Return whether a symbol name is part of public documentation.
    parameters:
      name:
        type: str
    returns:
      type: bool
    """
    return not name.startswith(PRIVATE_PREFIX)


def is_public_function(
    node: ast.stmt,
) -> TypeGuard[ast.FunctionDef | ast.AsyncFunctionDef]:
    """
    title: Return whether a statement is a public function definition.
    parameters:
      node:
        type: ast.stmt
    returns:
      type: TypeGuard[ast.FunctionDef | ast.AsyncFunctionDef]
    """
    if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return False
    return is_public(node.name)


def write_api_tree(modules: list[ModuleDoc]) -> None:
    """
    title: Write generated API Markdown pages under ``docs/api``.
    parameters:
      modules:
        type: list[ModuleDoc]
    """
    if API_DIR.exists():
        shutil.rmtree(API_DIR)
    API_DIR.mkdir(parents=True)

    packages: dict[str, list[ModuleDoc]] = {"arx": [], "astx": [], "irx": []}
    for module in modules:
        package = module.name.split(".", maxsplit=1)[0]
        packages.setdefault(package, []).append(module)
        write_module_page(module)

    write_api_index(packages)
    for package, package_modules in sorted(packages.items()):
        write_package_index(package, package_modules)


def write_api_index(packages: dict[str, list[ModuleDoc]]) -> None:
    """
    title: Write the top-level API index page.
    parameters:
      packages:
        type: dict[str, list[ModuleDoc]]
    """
    lines = [
        "---",
        "title: API Docs",
        "---",
        "",
        "# API Docs",
        "",
        "Generated from the Python sources for Arx, ASTx, and IRx.",
        "",
    ]
    for package in sorted(packages):
        if not packages[package]:
            continue
        lines.append(f"- [{package}](./{package}/index.md)")
    write_lines(API_DIR / "index.md", lines)


def write_package_index(package: str, modules: list[ModuleDoc]) -> None:
    """
    title: Write an index page for one package API section.
    parameters:
      package:
        type: str
      modules:
        type: list[ModuleDoc]
    """
    package_dir = API_DIR / package
    package_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f"title: {package} API",
        "---",
        "",
        f"# `{package}` API",
        "",
    ]
    for module in sorted(modules, key=lambda item: item.name):
        href = module_href_from_package_index(package, module)
        lines.append(f"- [`{module.name}`]({href})")
    write_lines(package_dir / "index.md", lines)


def write_module_page(module: ModuleDoc) -> None:
    """
    title: Write one module API page.
    parameters:
      module:
        type: ModuleDoc
    """
    target = API_DIR / Path(*module.name.split(".")).with_suffix(".md")
    target.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "---",
        f"title: {module.name}",
        "---",
        "",
        f"# `{module.name}`",
        "",
        f"Source: `{module.source_path.as_posix()}`",
        "",
    ]
    append_docstring(lines, module.docstring)
    append_functions(lines, module.functions)
    append_classes(lines, module.classes)
    write_lines(target, lines)


def append_functions(
    lines: list[str],
    functions: tuple[FunctionDoc, ...],
) -> None:
    """
    title: Append function documentation sections.
    parameters:
      lines:
        type: list[str]
      functions:
        type: tuple[FunctionDoc, Ellipsis]
    """
    if not functions:
        return
    lines.extend(["## Functions", ""])
    for item in functions:
        lines.extend([f"### `{item.signature}`", ""])
        append_docstring(lines, item.docstring)


def append_classes(lines: list[str], classes: tuple[ClassDoc, ...]) -> None:
    """
    title: Append class documentation sections.
    parameters:
      lines:
        type: list[str]
      classes:
        type: tuple[ClassDoc, Ellipsis]
    """
    if not classes:
        return
    lines.extend(["## Classes", ""])
    for item in classes:
        title = item.name
        if item.bases:
            title = f"{item.name}({', '.join(item.bases)})"
        lines.extend([f"### `{title}`", ""])
        append_docstring(lines, item.docstring)
        append_methods(lines, item.methods)


def append_methods(lines: list[str], methods: tuple[FunctionDoc, ...]) -> None:
    """
    title: Append method documentation for one class.
    parameters:
      lines:
        type: list[str]
      methods:
        type: tuple[FunctionDoc, Ellipsis]
    """
    if not methods:
        return
    lines.extend(["#### Methods", ""])
    for item in methods:
        lines.extend([f"##### `{item.signature}`", ""])
        append_docstring(lines, item.docstring)


def append_docstring(lines: list[str], docstring: str) -> None:
    """
    title: Append a normalized docstring as Markdown.
    parameters:
      lines:
        type: list[str]
      docstring:
        type: str
    """
    if not docstring:
        lines.extend(["_No docstring available._", ""])
        return
    lines.extend(["```yaml", docstring, "```", ""])


def module_href_from_package_index(package: str, module: ModuleDoc) -> str:
    """
    title: Return the relative link from a package index to a module page.
    parameters:
      package:
        type: str
      module:
        type: ModuleDoc
    returns:
      type: str
    """
    parts = module.name.split(".")
    if parts == [package]:
        return f"../{package}.md"
    return "./" + "/".join(parts[1:]) + ".md"


def write_lines(path: Path, lines: list[str]) -> None:
    """
    title: Write Markdown lines to a file with a trailing newline.
    parameters:
      path:
        type: Path
      lines:
        type: list[str]
    """
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
