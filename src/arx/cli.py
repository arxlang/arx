"""Functions and classes for handling the CLI call."""
import argparse

from arx.main import ArxMain, __version__


class CustomHelpFormatter(argparse.RawTextHelpFormatter):
    """Formatter for generating usage messages and argument help strings.

    Only the name of this class is considered a public API. All the methods
    provided by the class are considered an implementation detail.
    """

    def __init__(
        self,
        prog,
        indent_increment=2,
        max_help_position=4,
        width=None,
        **kwargs,
    ):
        super().__init__(
            prog,
            indent_increment=indent_increment,
            max_help_position=max_help_position,
            width=width,
            **kwargs,
        )


def get_args():
    """Get the CLI arguments."""
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
        "--version",
        action="store_true",
        help="Show the version of the installed MakIm tool.",
    )

    parser.add_argument(
        "--input",
        type=str,
        help="The input file",
    )

    parser.add_argument(
        "--output",
        type=str,
        help="The output file",
    )

    parser.add_argument(
        "--lib",
        action="store_true",
        help="build source code as library",
    )

    parser.add_argument(
        "--show-ast",
        action="store_true",
        help="Show the AST for the input source code",
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

    return parser


def show_version():
    """Show the application version."""
    print(__version__)


def app():
    """Run the application."""
    args_parser = get_args()
    args = args_parser.parse_args()

    if args.version:
        return show_version()

    arx = ArxMain()
    return arx.run(**dict(args._get_kwargs()))
