"""
title: Functions and classes for handling the CLI call.
"""

import argparse
import sys

from pathlib import Path
from typing import Any, Optional, Sequence

from arx import __version__
from arx.main import ArxMain


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
        help="Show the version of the installed MakIm tool.",
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
        "--shell",
        action="store_true",
        help="Open Arx in a shell prompt",
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
        "input_file",
        nargs="?",
        default="tests/main.x",
        type=str,
        help="Test entry file (defaults to tests/main.x)",
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
    return parser


def show_version() -> None:
    """
    title: Show the application version.
    """
    print(__version__)


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
        arx = ArxMain()
        exit_code = arx.run_tests(**dict(args._get_kwargs()))
        if exit_code != 0:
            raise SystemExit(exit_code)
        return None

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

    if not args.shell and args.input_files:
        missing = [
            entry for entry in args.input_files if not Path(entry).is_file()
        ]
        if missing:
            print(
                f"arx: unknown command or missing file: '{missing[0]}'",
                file=sys.stderr,
            )
            raise SystemExit(2)

    arx = ArxMain()
    return arx.run(**dict(args._get_kwargs()))
