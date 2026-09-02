"""
title: Tests for fatal runtime diagnostic reporting.
"""

from irx.builder.runtime.errors import (
    RuntimeFailureReport,
    parse_runtime_failure_line,
    parse_runtime_failure_output,
)


def test_parse_runtime_failure_decodes_machine_record() -> None:
    """
    title: Runtime failure reports decode locations and escaped text.
    """
    line = (
        "ARX_RUNTIME_FAIL|ARX-RUNTIME-ARITHMETIC-001|demo\\pfile.x|"
        "7|11|bad\\nvalue"
    )
    expected = RuntimeFailureReport(
        code="ARX-RUNTIME-ARITHMETIC-001",
        source="demo|file.x",
        line=7,
        col=11,
        message="bad\nvalue",
    )
    assert parse_runtime_failure_line(line) == expected
    assert parse_runtime_failure_output(f"noise\n{line}\n") == expected


def test_parse_runtime_failure_rejects_unrelated_or_malformed_lines() -> None:
    """
    title: Runtime report parsing fails closed for incomplete records.
    """
    assert parse_runtime_failure_line("unrelated") is None
    assert parse_runtime_failure_line("ARX_RUNTIME_FAIL|too|short") is None
    assert (
        parse_runtime_failure_line(
            "ARX_RUNTIME_FAIL|CODE|source|not-a-line|2|message"
        )
        is None
    )
