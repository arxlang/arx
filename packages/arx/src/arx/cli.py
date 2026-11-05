"""
title: Functions and classes for handling the CLI call.
"""

import argparse
import json
import os
import sys

from pathlib import Path
from typing import Any, Callable, Optional, Protocol, Sequence

from arx import __version__
from arx.exceptions import ArxError

KNOWN_SUBCOMMANDS: tuple[str, ...] = ("test",)
COMPILATION_ERROR_EXIT_CODE = 1
INTERNAL_ERROR_EXIT_CODE = 70
DIAGNOSTIC_SCHEMA_VERSION = 1
DIAGNOSTIC_FORMATS: tuple[str, ...] = ("human", "json")
INTERNAL_DIAGNOSTIC_CODE = "ARX-INTERNAL-001"


class ArxApplication(Protocol):
    """
    title: Define the CLI-facing compiler application contract.
    """

    def run(self, **kwargs: Any) -> None:
        """
        title: Run one normal compiler command.
        parameters:
          kwargs:
            type: Any
            variadic: keyword
        """
        ...

    def run_tests(self, **kwargs: Any) -> int:
        """
        title: Run one compiled-language test command.
        parameters:
          kwargs:
            type: Any
            variadic: keyword
        returns:
          type: int
        """
        ...


ArxMain: Callable[[], ArxApplication] | None = None


def create_arx_application() -> ArxApplication:
    """
    title: Create the compiler application without loading it for metadata CLI.
    returns:
      type: ArxApplication
    """
    if ArxMain is not None:
        return ArxMain()

    # Keep metadata-only commands independent of LLVM and native backends.
    from arx.main import ArxMain as ArxMainImplementation  # noqa: PLC0415

    return ArxMainImplementation()


def _arx_error_record(error: ArxError) -> dict[str, Any]:
    """
    title: Convert one expected frontend error to the CLI diagnostic schema.
    parameters:
      error:
        type: ArxError
    returns:
      type: dict[str, Any]
    """
    location = error.location
    return {
        "code": error.code,
        "column": None if location is None else location.col,
        "end_column": None,
        "end_line": None,
        "hint": None,
        "line": None if location is None else location.line,
        "message": getattr(error, "message", str(error)),
        "module": None,
        "notes": [],
        "phase": "frontend",
        "severity": "error",
    }


def _irx_diagnostic_record(diagnostic: object) -> dict[str, Any]:
    """
    title: Convert one structured IRx diagnostic to the CLI schema.
    parameters:
      diagnostic:
        type: object
    returns:
      type: dict[str, Any]
    """
    source_resolver = getattr(diagnostic, "resolved_source", None)
    source = source_resolver() if callable(source_resolver) else None
    module_resolver = getattr(diagnostic, "resolved_module_key", None)
    module = module_resolver() if callable(module_resolver) else None
    code_renderer = getattr(diagnostic, "rendered_code", None)
    code = code_renderer() if callable(code_renderer) else None
    return {
        "code": code,
        "column": getattr(source, "col", None),
        "end_column": getattr(source, "end_col", None),
        "end_line": getattr(source, "end_line", None),
        "hint": getattr(diagnostic, "hint", None),
        "line": getattr(source, "line", None),
        "message": str(getattr(diagnostic, "message", diagnostic)),
        "module": None if module is None else str(module),
        "notes": list(getattr(diagnostic, "notes", ())),
        "phase": str(getattr(diagnostic, "phase", "compiler")),
        "severity": str(getattr(diagnostic, "severity", "error")),
    }


def _compiler_error_records(error: Exception) -> list[dict[str, Any]] | None:
    """
    title: Return machine records for a known compiler failure.
    parameters:
      error:
        type: Exception
    returns:
      type: list[dict[str, Any]] | None
    """
    if isinstance(error, ArxError):
        return [_arx_error_record(error)]

    # IRx is already loaded for a backend failure. Keeping this import here
    # preserves fast `--help` and `--version` commands.
    from irx.diagnostics import (  # noqa: PLC0415
        IRxDiagnosticError,
        SemanticError,
    )

    if isinstance(error, IRxDiagnosticError):
        return [_irx_diagnostic_record(error.diagnostic)]
    if isinstance(error, SemanticError):
        return [
            _irx_diagnostic_record(diagnostic)
            for diagnostic in error.diagnostics.diagnostics
        ]
    return None


def report_compiler_error(
    error: Exception,
    diagnostic_format: str = "human",
) -> bool:
    """
    title: Render one known compiler failure without hiding internal errors.
    parameters:
      error:
        type: Exception
      diagnostic_format:
        type: str
    returns:
      type: bool
    """
    records = _compiler_error_records(error)
    if records is None:
        return False

    if diagnostic_format == "json":
        print(
            json.dumps(
                {
                    "diagnostics": records,
                    "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return True

    if isinstance(error, ArxError):
        print(f"arx: [{error.code}] {error}", file=sys.stderr)
    else:
        print(f"arx: {error}", file=sys.stderr)
    return True


def report_internal_error(diagnostic_format: str = "human") -> None:
    """
    title: Render a non-source internal compiler failure safely.
    parameters:
      diagnostic_format:
        type: str
    """
    message = "internal compiler error; rerun with --traceback to debug"
    if diagnostic_format == "json":
        print(
            json.dumps(
                {
                    "diagnostics": [
                        {
                            "code": INTERNAL_DIAGNOSTIC_CODE,
                            "column": None,
                            "end_column": None,
                            "end_line": None,
                            "hint": "rerun with --traceback to debug",
                            "line": None,
                            "message": "internal compiler error",
                            "module": None,
                            "notes": [],
                            "phase": "compiler",
                            "severity": "error",
                        }
                    ],
                    "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return
    print(
        f"arx: [{INTERNAL_DIAGNOSTIC_CODE}] {message}",
        file=sys.stderr,
    )


class CustomHelpFormatter(argparse.RawTextHelpFormatter):
    """
    title: Formatter for generating usage messages and argument help strings.
    summary: >-
      Only the name of this class is considered a public API. All the methods
      provided by the class are considered an implementation detail.
    """

    def __init__(
        self,
        prog: str,
        indent_increment: int = 2,
        max_help_position: int = 4,
        width: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        """
        title: Initialize CustomHelpFormatter.
        parameters:
          prog:
            type: str
          indent_increment:
            type: int
          max_help_position:
            type: int
          width:
            type: Optional[int]
          kwargs:
            type: Any
            variadic: keyword
        """
        super().__init__(
            prog,
            indent_increment=indent_increment,
            max_help_position=max_help_position,
            width=width,
            **kwargs,
        )


def get_args() -> argparse.ArgumentParser:
    """
    title: Get the CLI arguments.
    returns:
      type: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="arx",
        description=(
            "Arx is a compiler that uses the power of llvm to bring a modern "
            "infra-structure."
        ),
        epilog=(
            "If you have any problem, open an issue at: "
            "https://github.com/arxlang/arx"
        ),
        add_help=True,
        formatter_class=CustomHelpFormatter,
    )
    parser.add_argument(
        "input_files",
        nargs="*",
        type=str,
        help="The input file",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show the installed Arx compiler version.",
    )

    parser.add_argument(
        "--output-file",
        type=str,
        help="The output file",
    )

    parser.add_argument(
        "--lib",
        dest="is_lib",
        action="store_true",
        help="build source code as library",
    )

    parser.add_argument(
        "--show-ast",
        action="store_true",
        help="Show the AST for the input source code",
    )

    parser.add_argument(
        "--show-tokens",
        action="store_true",
        help="Show the tokens for the input source code",
    )

    parser.add_argument(
        "--show-llvm-ir",
        action="store_true",
        help="Show the LLVM IR for the input source code",
    )

    parser.add_argument(
        "--run",
        action="store_true",
        help="Build and run the compiled binary.",
    )
    parser.add_argument(
        "--link-mode",
        type=str,
        choices=("auto", "pie", "no-pie"),
        default="auto",
        help=(
            "Set executable link mode: auto (toolchain default), "
            "pie, or no-pie."
        ),
    )
    parser.add_argument(
        "--diagnostic-format",
        choices=DIAGNOSTIC_FORMATS,
        default="human",
        help="Render compiler failures as human text or versioned JSON.",
    )
    parser.add_argument(
        "--traceback",
        action="store_true",
        help="Show Python tracebacks for internal compiler failures.",
    )

    return parser


def get_test_args() -> argparse.ArgumentParser:
    """
    title: Get the CLI arguments for `arx test`.
    returns:
      type: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="arx test",
        description="Discover, compile, and run Arx tests.",
        formatter_class=CustomHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=str,
        help=(
            "Test files or directories to discover tests in. "
            "Directories are searched recursively for files matching the "
            "configured file pattern. Defaults to `tests` (or the value "
            "from [tests].paths in .arxproject.toml, if present)."
        ),
    )
    parser.add_argument(
        "--list",
        dest="list_only",
        action="store_true",
        help="List discovered tests without running them",
    )
    parser.add_argument(
        "-k",
        dest="name_filter",
        default="",
        type=str,
        help="Run only tests whose names contain the given substring",
    )
    parser.add_argument(
        "-x",
        "--fail-fast",
        dest="fail_fast",
        action="store_true",
        help="Stop after the first failing test",
    )
    parser.add_argument(
        "--exclude",
        dest="exclude",
        action="append",
        default=None,
        type=str,
        help=(
            "Glob pattern to exclude from test discovery. Repeat the flag "
            "to supply multiple patterns."
        ),
    )
    parser.add_argument(
        "--file-pattern",
        dest="file_pattern",
        default=None,
        type=str,
        help="Glob pattern for test file discovery (default: test_*.x)",
    )
    parser.add_argument(
        "--function-pattern",
        dest="function_pattern",
        default=None,
        type=str,
        help="Glob pattern for test function names (default: test_*)",
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Keep generated wrapper/debug artifacts and executables",
    )
    parser.add_argument(
        "--link-mode",
        type=str,
        choices=("auto", "pie", "no-pie"),
        default="auto",
        help=(
            "Set executable link mode for generated test binaries: "
            "auto, pie, or no-pie."
        ),
    )
    parser.add_argument(
        "--diagnostic-format",
        choices=DIAGNOSTIC_FORMATS,
        default="human",
        help="Render compiler failures as human text or versioned JSON.",
    )
    parser.add_argument(
        "--traceback",
        action="store_true",
        help="Show Python tracebacks for internal compiler failures.",
    )
    return parser


def show_version() -> None:
    """
    title: Show the application version.
    """
    print(__version__)


def _looks_like_subcommand_attempt(token: str) -> bool:
    """
    title: Return whether a leading token appears to be a subcommand attempt.
    parameters:
      token:
        type: str
    returns:
      type: bool
    """
    if not token:
        return False
    if token.startswith("-"):
        return False
    if token == "run" or token in KNOWN_SUBCOMMANDS:
        return False
    if "/" in token or "\\" in token or os.sep in token:
        return False
    if "." in token:
        return False
    if Path(token).exists():
        return False
    return True


def app(argv: Sequence[str] | None = None) -> None:
    """
    title: Run the application.
    parameters:
      argv:
        type: Sequence[str] | None
    """
    raw_args = list(sys.argv[1:] if argv is None else argv)

    if raw_args and raw_args[0] == "test":
        args_parser = get_test_args()
        args = args_parser.parse_args(raw_args[1:])
        try:
            arx = create_arx_application()
            exit_code = arx.run_tests(**dict(args._get_kwargs()))
        except Exception as err:
            if report_compiler_error(err, args.diagnostic_format):
                raise SystemExit(COMPILATION_ERROR_EXIT_CODE) from None
            if args.traceback:
                raise
            report_internal_error(args.diagnostic_format)
            raise SystemExit(INTERNAL_ERROR_EXIT_CODE) from None
        if exit_code != 0:
            raise SystemExit(exit_code)
        return None

    if raw_args and _looks_like_subcommand_attempt(raw_args[0]):
        known = ", ".join(KNOWN_SUBCOMMANDS)
        print(
            f"arx: unknown command '{raw_args[0]}' "
            f"(known subcommands: {known})",
            file=sys.stderr,
        )
        raise SystemExit(2)

    args_parser = get_args()
    args = (
        args_parser.parse_args()
        if argv is None
        else args_parser.parse_args(raw_args)
    )

    if args.input_files and args.input_files[0] == "run":
        args.run = True
        args.input_files = args.input_files[1:]

    if args.version:
        return show_version()

    if len(args.input_files) > 1:
        print(
            "arx: compiling multiple direct input files is not supported; "
            "use imports from one entry module",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if args.input_files:
        missing = [
            entry for entry in args.input_files if not Path(entry).is_file()
        ]
        if missing:
            print(
                f"arx: input file not found: '{missing[0]}'",
                file=sys.stderr,
            )
            raise SystemExit(2)

    try:
        arx = create_arx_application()
        return arx.run(**dict(args._get_kwargs()))
    except Exception as err:
        if report_compiler_error(err, args.diagnostic_format):
            raise SystemExit(COMPILATION_ERROR_EXIT_CODE) from None
        if args.traceback:
            raise
        report_internal_error(args.diagnostic_format)
        raise SystemExit(INTERNAL_ERROR_EXIT_CODE) from None
