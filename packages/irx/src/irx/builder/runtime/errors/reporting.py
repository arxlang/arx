"""
title: Machine-readable fatal runtime diagnostic parsing helpers.
"""

from __future__ import annotations

from dataclasses import dataclass

from public import public

from irx.typecheck import typechecked

RUNTIME_FAILURE_PREFIX = "ARX_RUNTIME_FAIL"
RUNTIME_FAILURE_FIELD_COUNT = 6


@public
@typechecked
@dataclass(frozen=True)
class RuntimeFailureReport:
    """
    title: Parsed fatal runtime diagnostic.
    attributes:
      code:
        type: str
      source:
        type: str
      line:
        type: int
      col:
        type: int
      message:
        type: str
    """

    code: str
    source: str
    line: int
    col: int
    message: str


@typechecked
def _decode_runtime_failure_field(text: str) -> str:
    """
    title: Decode one escaped runtime diagnostic field.
    parameters:
      text:
        type: str
    returns:
      type: str
    """
    decoded: list[str] = []
    index = 0
    escapes = {
        "\\": "\\",
        "n": "\n",
        "p": "|",
        "r": "\r",
        "t": "\t",
    }
    while index < len(text):
        char = text[index]
        if char != "\\":
            decoded.append(char)
            index += 1
            continue
        if index + 1 >= len(text):
            decoded.append("\\")
            break
        escaped = text[index + 1]
        replacement = escapes.get(escaped)
        if replacement is None:
            decoded.extend(("\\", escaped))
        else:
            decoded.append(replacement)
        index += 2
    return "".join(decoded)


@public
@typechecked
def parse_runtime_failure_line(line: str) -> RuntimeFailureReport | None:
    """
    title: Parse one fatal runtime diagnostic line.
    parameters:
      line:
        type: str
    returns:
      type: RuntimeFailureReport | None
    """
    stripped = line.strip()
    prefix = f"{RUNTIME_FAILURE_PREFIX}|"
    if not stripped.startswith(prefix):
        return None
    parts = stripped.split("|", RUNTIME_FAILURE_FIELD_COUNT - 1)
    if len(parts) != RUNTIME_FAILURE_FIELD_COUNT:
        return None
    _, code, source, line_text, col_text, message = parts
    try:
        line_number = int(line_text)
        col_number = int(col_text)
    except ValueError:
        return None
    return RuntimeFailureReport(
        code=_decode_runtime_failure_field(code),
        source=_decode_runtime_failure_field(source),
        line=line_number,
        col=col_number,
        message=_decode_runtime_failure_field(message),
    )


@public
@typechecked
def parse_runtime_failure_output(
    stderr: str,
) -> RuntimeFailureReport | None:
    """
    title: Parse the first fatal runtime diagnostic from standard error.
    parameters:
      stderr:
        type: str
    returns:
      type: RuntimeFailureReport | None
    """
    for line in stderr.splitlines():
        parsed = parse_runtime_failure_line(line)
        if parsed is not None:
            return parsed
    return None
