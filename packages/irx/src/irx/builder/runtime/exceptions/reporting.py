"""
title: Parse typed, escaped exception reports without guessing from messages.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from public import private, public

from irx.typecheck import typechecked

EXCEPTION_FIELD_COUNT = 8
FRAME_FIELD_COUNT = 4


@public
@typechecked
@dataclass(frozen=True)
class ExceptionFrame:
    """
    title: One trustworthy generated propagation location.
    attributes:
      source:
        type: str
      line:
        type: int
      col:
        type: int
    """

    source: str
    line: int
    col: int


@public
@typechecked
@dataclass(frozen=True)
class ExceptionReport:
    """
    title: Immutable typed report with chronological related diagnostics.
    attributes:
      role:
        type: Literal[root, cause, context, cleanup]
      code:
        type: str
      type_name:
        type: str
      source:
        type: str
      line:
        type: int
      col:
        type: int
      message:
        type: str
      frames:
        type: tuple[ExceptionFrame, Ellipsis]
      related:
        type: tuple[ExceptionReport, Ellipsis]
    notes: >-
      type_name is a canonical nominal identity, not message-derived text.
      Unknown origins use line and col minus one; they are not fabricated.
      related holds cause, context, and secondary cleanup reports in order.
    """

    role: Literal["root", "cause", "context", "cleanup"]
    code: str
    type_name: str
    source: str
    line: int
    col: int
    message: str
    frames: tuple[ExceptionFrame, ...] = ()
    related: tuple[ExceptionReport, ...] = ()


@private
@typechecked
def decode_field(value: str) -> str:
    """
    title: Decode protocol escapes while preserving unknown escape pairs.
    parameters:
      value:
        type: str
    returns:
      type: str
    """
    escapes = {"\\": "\\", "n": "\n", "r": "\r", "t": "\t", "p": "|"}
    result: list[str] = []
    index = 0
    while index < len(value):
        if value[index] != "\\" or index + 1 == len(value):
            result.append(value[index])
            index += 1
            continue
        key = value[index + 1]
        result.append(escapes.get(key, "\\" + key))
        index += 2
    return "".join(result)


@public
@typechecked
def parse_exception_output(stderr: str) -> ExceptionReport | None:
    """
    title: Parse the first complete root report and its preceding diagnostics.
    parameters:
      stderr:
        type: str
    returns:
      type: ExceptionReport | None
    notes: >-
      Unrelated stderr and malformed records are ignored. Frame records attach
      only to the immediately preceding report. This parser does not classify
      exceptions by display name or message.
    """
    reports: list[ExceptionReport] = []
    root: ExceptionReport | None = None
    for line in stderr.splitlines():
        parts = line.split("|")
        if (
            parts[0] == "ARX_EXCEPTION_FRAME"
            and len(parts) == FRAME_FIELD_COUNT
        ):
            if not reports:
                continue
            try:
                frame = ExceptionFrame(
                    decode_field(parts[1]), int(parts[2]), int(parts[3])
                )
            except ValueError:
                continue
            if frame.line < 1 or frame.col < 1:
                continue
            report = replace(reports[-1], frames=(*reports[-1].frames, frame))
            reports[-1] = report
            if report.role == "root":
                root = report
            continue
        if parts[0] != "ARX_EXCEPTION" or len(parts) != EXCEPTION_FIELD_COUNT:
            continue
        if root is not None:
            break
        role = parts[1]
        if role not in ("root", "cause", "context", "cleanup"):
            continue
        try:
            report = ExceptionReport(
                role=role,  # type: ignore[arg-type]
                code=decode_field(parts[2]),
                type_name=decode_field(parts[3]),
                source=decode_field(parts[4]),
                line=int(parts[5]),
                col=int(parts[6]),
                message=decode_field(parts[7]),
            )
        except ValueError:
            continue
        reports.append(report)
        if role == "root":
            root = report
    if root is None:
        return None
    return replace(root, related=tuple(reports[:-1]))
