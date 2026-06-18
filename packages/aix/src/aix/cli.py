"""
title: AIX command-line interface.
"""

from __future__ import annotations

import argparse
import sys

from pathlib import Path
from typing import Sequence

from aix import __version__
from aix.main import AixMain

KNOWN_SUBCOMMANDS: tuple[str, ...] = ("test",)


class CustomHelpFormatter(argparse.RawTextHelpFormatter):
    """
    title: Formatter for preserving CLI help layout.
    """


def get_args() -> argparse.ArgumentParser:
    """
    title: Build the AIX CLI argument parser.
    returns:
      type: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="aix",
        description="AIX compiler frontend for .aix source files.",
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
        help="The input .aix file(s)",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show the installed AIX package version.",
    )
    parser.add_argument("--output-file", type=str, help="The output file")
    parser.add_argument(
        "--lib",
        dest="is_lib",
        action="store_true",
        help="Build source code as a library.",
    )
    parser.add_argument(
        "--show-ast",
        action="store_true",
        help="Show the AST for the input source code.",
    )
    parser.add_argument(
        "--show-tokens",
        action="store_true",
        help="Show tokens for the input source code.",
    )
    parser.add_argument(
        "--show-llvm-ir",
        action="store_true",
        help="Show LLVM IR for the input source code.",
    )
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Open AIX in a shell prompt.",
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
        help="Set executable link mode: auto, pie, or no-pie.",
    )
    return parser


def get_test_args() -> argparse.ArgumentParser:
    """
    title: Build parser for `aix test`.
    returns:
      type: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="aix test",
        description="Discover and run AIX tests.",
        formatter_class=CustomHelpFormatter,
    )
    parser.add_argument("paths", nargs="*", type=str, help="Test paths")
    parser.add_argument("--list", dest="list_only", action="store_true")
    parser.add_argument("-k", dest="name_filter", default="", type=str)
    parser.add_argument(
        "-x",
        "--fail-fast",
        dest="fail_fast",
        action="store_true",
    )
    parser.add_argument("--exclude", dest="exclude", action="append")
    parser.add_argument("--file-pattern", dest="file_pattern", default=None)
    parser.add_argument(
        "--function-pattern",
        dest="function_pattern",
        default=None,
    )
    parser.add_argument("--keep-artifacts", action="store_true")
    parser.add_argument(
        "--link-mode",
        type=str,
        choices=("auto", "pie", "no-pie"),
        default="auto",
    )
    return parser


def show_version() -> None:
    """
    title: Print package version.
    """
    print(__version__)


def _looks_like_subcommand_attempt(token: str) -> bool:
    if not token or token.startswith("-"):
        return False
    if token == "run" or token in KNOWN_SUBCOMMANDS:
        return False
    if "/" in token or "\\" in token:
        return False
    if "." in token or Path(token).exists():
        return False
    return True


def app(argv: Sequence[str] | None = None) -> None:
    """
    title: Run the AIX CLI.
    parameters:
      argv:
        type: Sequence[str] | None
    """
    raw_args = list(sys.argv[1:] if argv is None else argv)

    if raw_args and raw_args[0] == "test":
        args = get_test_args().parse_args(raw_args[1:])
        exit_code = AixMain().run_tests(**dict(args._get_kwargs()))
        if exit_code != 0:
            raise SystemExit(exit_code)
        return None

    if raw_args and _looks_like_subcommand_attempt(raw_args[0]):
        known = ", ".join(KNOWN_SUBCOMMANDS)
        print(
            f"aix: unknown command '{raw_args[0]}' "
            f"(known subcommands: {known})",
            file=sys.stderr,
        )
        raise SystemExit(2)

    args_parser = get_args()
    args = args_parser.parse_args(raw_args)

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
                f"aix: input file not found: '{missing[0]}'",
                file=sys.stderr,
            )
            raise SystemExit(2)

    return AixMain().run(**dict(args._get_kwargs()))
