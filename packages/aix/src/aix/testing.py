"""
title: Minimal AIX compiled-test placeholders.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TEST_PATHS: tuple[str, ...] = ("tests/aix",)
DEFAULT_TEST_FILE_PATTERN = "test_*.aix"
DEFAULT_TEST_FUNCTION_PATTERN = "test_*"


@dataclass(frozen=True)
class AixTestSummary:
    """
    title: Summary returned by the placeholder test runner.
    attributes:
      exit_code:
        type: int
    """

    exit_code: int


class AixTestRunner:
    """
    title: Placeholder for future compiled AIX test execution.
    """

    def __init__(self, **kwargs: object) -> None:
        """
        title: Store runner options.
        parameters:
          kwargs:
            type: object
            variadic: keyword
        """
        self.kwargs = kwargs

    def run(self) -> AixTestSummary:
        """
        title: Return an unimplemented-test summary.
        returns:
          type: AixTestSummary
        """
        return AixTestSummary(exit_code=2)


ArxTestRunner = AixTestRunner
