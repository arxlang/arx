"""
title: Typed programmatic facade for the Arx compiler pipeline.
summary: >-
  Provide parse, check, compile, artifact, and execution APIs without exposing
  CLI state. Heavy frontend, semantic, and LLVM modules are imported only when
  an operation needs them, keeping `import arxpy` lightweight. Compiler
  operations are serialized because the current Arx lexer reads a process-wide
  source buffer; each lowering operation uses a fresh backend builder.
"""

# Compiler dependencies are intentionally operation-local to keep metadata and
# import-only use independent of LLVM initialization.
# ruff: noqa: PLC0415

from __future__ import annotations

import subprocess
import threading

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from arxpy.diagnostics import Diagnostic, DiagnosticSeverity
from arxpy.errors import CompileError, ExecutionError, ParseError

if TYPE_CHECKING:
    import astx

    from irx.analysis.module_interfaces import ImportResolver, ParsedModule

_COMPILER_LOCK = threading.RLock()


class ArtifactKind(Enum):
    """
    title: Kind of output requested from the compiler.
    """

    AUTO = "auto"
    LLVM_IR = "llvm-ir"
    OBJECT = "object"
    EXECUTABLE = "executable"


@dataclass(frozen=True)
class ParsedProgram:
    """
    title: Parsed Arx source plus stable source attribution.
    attributes:
      module:
        type: astx.Module
      source:
        type: str
      filename:
        type: str
      module_name:
        type: str
      origin:
        type: Path | None
      has_source_imports:
        type: bool
    """

    module: astx.Module
    source: str
    filename: str
    module_name: str
    origin: Path | None = None
    has_source_imports: bool = False


@dataclass(frozen=True)
class CheckedProgram:
    """
    title: Program that completed semantic analysis successfully.
    attributes:
      parsed:
        type: ParsedProgram
    """

    parsed: ParsedProgram


@dataclass(frozen=True)
class CompilationArtifact:
    """
    title: Materialized compiler output.
    attributes:
      kind:
        type: ArtifactKind
      path:
        type: Path | None
      llvm_ir:
        type: str | None
    """

    kind: ArtifactKind
    path: Path | None
    llvm_ir: str | None = None


@dataclass(frozen=True)
class ExecutionResult:
    """
    title: Captured result of running an executable artifact.
    attributes:
      exit_code:
        type: int
      stdout:
        type: str
      stderr:
        type: str
    """

    exit_code: int
    stdout: str
    stderr: str


def _api_diagnostic(
    message: str,
    *,
    filename: str,
    code: str,
) -> Diagnostic:
    """
    title: Build one facade-originated error diagnostic.
    parameters:
      message:
        type: str
      filename:
        type: str
      code:
        type: str
    returns:
      type: Diagnostic
    """
    return Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        message=message,
        filename=filename,
        line=None,
        column=None,
        code=code,
    )


def _compile_diagnostics(
    error: object,
    *,
    filename: str,
) -> list[Diagnostic]:
    """
    title: Translate a structured IRx failure into public diagnostics.
    parameters:
      error:
        type: object
      filename:
        type: str
    returns:
      type: list[Diagnostic]
    """
    from arxpy.diagnostics import _from_irx

    diagnostic = getattr(error, "diagnostic", None)
    if diagnostic is not None:
        return [_from_irx(diagnostic, filename=filename)]

    bag = getattr(error, "diagnostics", None)
    records = getattr(bag, "diagnostics", ())
    return [_from_irx(record, filename=filename) for record in records]


def _has_imports(module: astx.Module) -> bool:
    """
    title: Return whether a parsed module contains source imports.
    parameters:
      module:
        type: astx.Module
    returns:
      type: bool
    """
    import astx

    return any(
        isinstance(node, (astx.ImportStmt, astx.ImportFromStmt))
        for node in module.nodes
    )


def _has_main(module: astx.Module) -> bool:
    """
    title: Return whether a module defines the executable entry point.
    parameters:
      module:
        type: astx.Module
    returns:
      type: bool
    """
    import astx

    return any(
        isinstance(node, astx.FunctionDef) and node.prototype.name == "main"
        for node in module.nodes
    )


def _program_context(
    program: ParsedProgram,
) -> tuple[ParsedModule, ImportResolver] | None:
    """
    title: Build an IRx root and resolver when a module uses imports.
    parameters:
      program:
        type: ParsedProgram
    returns:
      type: tuple[ParsedModule, ImportResolver] | None
    """
    if not _has_imports(program.module):
        return None
    if program.origin is None and program.has_source_imports:
        diagnostic = _api_diagnostic(
            "imports from in-memory source require a filesystem origin",
            filename=program.filename,
            code="ARXPY-IMPORT-001",
        )
        raise CompileError(
            "semantic analysis failed",
            diagnostics=[diagnostic],
        )

    from arx.main import FileImportResolver
    from irx.analysis.module_interfaces import ParsedModule

    root = ParsedModule(
        key=program.module_name,
        ast=program.module,
        display_name=program.module_name,
        origin=str(program.origin),
    )
    input_files = () if program.origin is None else (str(program.origin),)
    resolver: ImportResolver = FileImportResolver(input_files)
    return root, resolver


def _resolved_output_path(
    program: ParsedProgram,
    kind: ArtifactKind,
    output: str | Path | None,
) -> Path:
    """
    title: Resolve a caller-owned materialized artifact path.
    parameters:
      program:
        type: ParsedProgram
      kind:
        type: ArtifactKind
      output:
        type: str | Path | None
    returns:
      type: Path
    """
    if output is not None:
        return Path(output).expanduser().resolve()
    if program.origin is None:
        diagnostic = _api_diagnostic(
            "an output path is required when compiling in-memory source",
            filename=program.filename,
            code="ARXPY-OUTPUT-001",
        )
        raise CompileError("compilation failed", diagnostics=[diagnostic])

    suffix = ".o" if kind is ArtifactKind.OBJECT else ""
    return program.origin.with_suffix(suffix).resolve()


class Compiler:
    """
    title: Reusable facade for parse, check, compile, and run operations.
    summary: >-
      Operations are safe to repeat and serialized across Compiler instances
      while the frontend uses its process-wide input buffer. The facade never
      creates an implicit temporary artifact: callers provide an output path
      for in-memory compilation, while file compilation defaults beside the
      source. Unknown internal exceptions are not hidden as user diagnostics.
    """

    def parse_string(
        self,
        source: str,
        *,
        filename: str = "<string>",
        module_name: str = "main",
    ) -> ParsedProgram:
        """
        title: Parse Arx source text.
        parameters:
          source:
            type: str
          filename:
            type: str
          module_name:
            type: str
        returns:
          type: ParsedProgram
        """
        from arx.exceptions import ArxError as FrontendError
        from arx.io import ArxIO
        from arx.lexer import Lexer
        from arx.parser import Parser

        from arxpy.diagnostics import _from_arx_error

        try:
            with _COMPILER_LOCK:
                ArxIO.string_to_buffer(source)
                module = Parser().parse(Lexer().lex(), module_name)
        except FrontendError as error:
            diagnostic = _from_arx_error(error, filename=filename)
            raise ParseError(
                "source parsing failed",
                diagnostics=[diagnostic],
            ) from None

        return ParsedProgram(
            module=module,
            source=source,
            filename=filename,
            module_name=module_name,
            has_source_imports=_has_imports(module),
        )

    def parse_file(self, path: str | Path) -> ParsedProgram:
        """
        title: Read and parse one UTF-8 Arx source file.
        parameters:
          path:
            type: str | Path
        returns:
          type: ParsedProgram
        """
        from arx.main import get_module_name_from_file_path

        source_path = Path(path).expanduser().resolve()
        try:
            source = source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            diagnostic = _api_diagnostic(
                str(error),
                filename=str(source_path),
                code="ARXPY-SOURCE-001",
            )
            raise ParseError(
                "source loading failed",
                diagnostics=[diagnostic],
            ) from None

        parsed = self.parse_string(
            source,
            filename=str(source_path),
            module_name=get_module_name_from_file_path(str(source_path)),
        )
        return ParsedProgram(
            module=parsed.module,
            source=parsed.source,
            filename=parsed.filename,
            module_name=parsed.module_name,
            origin=source_path,
            has_source_imports=parsed.has_source_imports,
        )

    def check(self, program: ParsedProgram) -> CheckedProgram:
        """
        title: Run semantic analysis without lowering or materialization.
        parameters:
          program:
            type: ParsedProgram
        returns:
          type: CheckedProgram
        """
        from arx.main import inject_ambient_builtin_imports
        from irx.analysis import analyze_module, analyze_modules
        from irx.diagnostics import IRxDiagnosticError, SemanticError

        try:
            with _COMPILER_LOCK:
                inject_ambient_builtin_imports(program.module)
                context = _program_context(program)
                if context is None:
                    analyze_module(program.module)
                else:
                    root, resolver = context
                    analyze_modules(root, resolver)
        except (IRxDiagnosticError, SemanticError) as error:
            diagnostics = _compile_diagnostics(
                error,
                filename=program.filename,
            )
            raise CompileError(
                "semantic analysis failed",
                diagnostics=diagnostics,
            ) from None

        return CheckedProgram(parsed=program)

    def compile(
        self,
        program: ParsedProgram | CheckedProgram,
        *,
        kind: ArtifactKind = ArtifactKind.AUTO,
        output: str | Path | None = None,
        link_mode: Literal["auto", "pie", "no-pie"] = "auto",
    ) -> CompilationArtifact:
        """
        title: Lower a program and optionally materialize a host artifact.
        parameters:
          program:
            type: ParsedProgram | CheckedProgram
          kind:
            type: ArtifactKind
          output:
            type: str | Path | None
          link_mode:
            type: Literal[auto, pie, no-pie]
        returns:
          type: CompilationArtifact
        """
        from arx.codegen import ArxBuilder
        from arx.main import inject_ambient_builtin_imports
        from irx.diagnostics import IRxDiagnosticError, SemanticError

        parsed = (
            program.parsed if isinstance(program, CheckedProgram) else program
        )
        requested_kind = kind
        if requested_kind is ArtifactKind.AUTO:
            requested_kind = (
                ArtifactKind.EXECUTABLE
                if _has_main(parsed.module)
                else ArtifactKind.OBJECT
            )
        if requested_kind is ArtifactKind.EXECUTABLE and not _has_main(
            parsed.module
        ):
            diagnostic = _api_diagnostic(
                "an executable requires a top-level 'main' function",
                filename=parsed.filename,
                code="ARXPY-ENTRY-001",
            )
            raise CompileError("compilation failed", diagnostics=[diagnostic])
        if link_mode not in {"auto", "pie", "no-pie"}:
            diagnostic = _api_diagnostic(
                "link_mode must be one of: auto, pie, no-pie",
                filename=parsed.filename,
                code="ARXPY-LINK-MODE-001",
            )
            raise CompileError("compilation failed", diagnostics=[diagnostic])

        try:
            with _COMPILER_LOCK:
                inject_ambient_builtin_imports(parsed.module)
                context = _program_context(parsed)
                builder = ArxBuilder()
                if requested_kind is ArtifactKind.LLVM_IR:
                    if context is None:
                        llvm_ir = builder.translate(parsed.module)
                    else:
                        root, resolver = context
                        llvm_ir = builder.translate_modules(root, resolver)
                    output_path = None
                    if output is not None:
                        output_path = Path(output).expanduser().resolve()
                        output_path.write_text(llvm_ir, encoding="utf-8")
                    return CompilationArtifact(
                        kind=requested_kind,
                        path=output_path,
                        llvm_ir=llvm_ir,
                    )

                output_path = _resolved_output_path(
                    parsed,
                    requested_kind,
                    output,
                )
                if context is None:
                    builder.build(
                        parsed.module,
                        str(output_path),
                        link=requested_kind is ArtifactKind.EXECUTABLE,
                        link_mode=link_mode,
                    )
                else:
                    root, resolver = context
                    builder.build_modules(
                        root,
                        resolver,
                        str(output_path),
                        link=requested_kind is ArtifactKind.EXECUTABLE,
                        link_mode=link_mode,
                    )
                return CompilationArtifact(
                    kind=requested_kind,
                    path=output_path,
                )
        except (IRxDiagnosticError, SemanticError) as error:
            diagnostics = _compile_diagnostics(
                error,
                filename=parsed.filename,
            )
            raise CompileError(
                "compilation failed",
                diagnostics=diagnostics,
            ) from None
        except OSError as error:
            diagnostic = _api_diagnostic(
                str(error),
                filename=parsed.filename,
                code="ARXPY-ARTIFACT-001",
            )
            raise CompileError(
                "artifact materialization failed",
                diagnostics=[diagnostic],
            ) from None

    def compile_file(
        self,
        path: str | Path,
        *,
        kind: ArtifactKind = ArtifactKind.AUTO,
        output: str | Path | None = None,
        link_mode: Literal["auto", "pie", "no-pie"] = "auto",
    ) -> CompilationArtifact:
        """
        title: Parse and compile one source file.
        parameters:
          path:
            type: str | Path
          kind:
            type: ArtifactKind
          output:
            type: str | Path | None
          link_mode:
            type: Literal[auto, pie, no-pie]
        returns:
          type: CompilationArtifact
        """
        return self.compile(
            self.parse_file(path),
            kind=kind,
            output=output,
            link_mode=link_mode,
        )

    def run(
        self,
        artifact: CompilationArtifact,
        *,
        args: Sequence[str] = (),
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> ExecutionResult:
        """
        title: Run an executable artifact without invoking a shell.
        parameters:
          artifact:
            type: CompilationArtifact
          args:
            type: Sequence[str]
          cwd:
            type: str | Path | None
          env:
            type: Mapping[str, str] | None
          timeout:
            type: float | None
        returns:
          type: ExecutionResult
        """
        if (
            artifact.kind is not ArtifactKind.EXECUTABLE
            or artifact.path is None
        ):
            diagnostic = _api_diagnostic(
                "only executable artifacts can be run",
                filename=str(artifact.path or "<artifact>"),
                code="ARXPY-EXECUTABLE-001",
            )
            raise ExecutionError(
                "execution failed",
                diagnostics=[diagnostic],
            )

        try:
            completed = subprocess.run(
                [str(artifact.path), *args],
                cwd=None if cwd is None else str(cwd),
                env=None if env is None else dict(env),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            diagnostic = _api_diagnostic(
                f"execution exceeded timeout of {error.timeout} seconds",
                filename=str(artifact.path),
                code="ARXPY-EXECUTION-TIMEOUT-001",
            )
            raise ExecutionError(
                "execution timed out",
                diagnostics=[diagnostic],
            ) from None
        except OSError as error:
            diagnostic = _api_diagnostic(
                str(error),
                filename=str(artifact.path),
                code="ARXPY-EXECUTION-001",
            )
            raise ExecutionError(
                "execution failed",
                diagnostics=[diagnostic],
            ) from None

        return ExecutionResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


__all__ = [
    "ArtifactKind",
    "CheckedProgram",
    "CompilationArtifact",
    "Compiler",
    "ExecutionResult",
    "ParsedProgram",
]
