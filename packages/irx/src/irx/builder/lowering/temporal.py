# mypy: disable-error-code=no-redef

"""
title: Temporal literal lowering implementations for llvmliteir.
"""

from datetime import datetime
from datetime import time as time_value
from typing import cast

import astx

from llvmlite import ir
from plum import dispatch
from public import private

from irx.analysis.resolved_nodes import SemanticInfo
from irx.builder.diagnostics import (
    raise_lowering_error,
    raise_lowering_internal_error,
    require_semantic_metadata,
)
from irx.builder.lowering.contracts import TemporalServices
from irx.diagnostics import DiagnosticCodes
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class TemporalLowering:
    """
    title: Lower temporal values and operations to LLVM.
    attributes:
      services:
        type: TemporalServices
    """

    services: TemporalServices

    def __init__(self, services: TemporalServices) -> None:
        """
        title: Bind explicit family-owned emission dependencies.
        parameters:
          services:
            type: TemporalServices
        """
        self.services = services

    @dispatch
    def visit(self, node: astx.AST) -> None:
        """
        title: Fail closed for nodes not exported by this feature family.
        parameters:
          node:
            type: astx.AST
        """
        raise_lowering_internal_error(
            f"no temporal handler for {type(node).__name__}", node=node
        )

    def node_handlers(self) -> tuple[NodeHandler, ...]:
        """
        title: >-
          Export explicit concrete signatures without mutating a shared
          dispatcher.
        returns:
          type: tuple[NodeHandler, Ellipsis]
        """
        return (
            contribute_node(
                "llvm.temporal.LiteralDate",
                "irx.temporal",
                "lowering",
                astx.LiteralDate,
                self.visit,
                source="irx.builder.lowering.temporal.TemporalLowering.visit",
            ),
            contribute_node(
                "llvm.temporal.LiteralTime",
                "irx.temporal",
                "lowering",
                astx.LiteralTime,
                self.visit,
                source="irx.builder.lowering.temporal.TemporalLowering.visit",
            ),
            contribute_node(
                "llvm.temporal.LiteralTimestamp",
                "irx.temporal",
                "lowering",
                astx.LiteralTimestamp,
                self.visit,
                source="irx.builder.lowering.temporal.TemporalLowering.visit",
            ),
            contribute_node(
                "llvm.temporal.LiteralDateTime",
                "irx.temporal",
                "lowering",
                astx.LiteralDateTime,
                self.visit,
                source="irx.builder.lowering.temporal.TemporalLowering.visit",
            ),
        )

    @dispatch
    def visit(self, node: astx.LiteralDate) -> None:
        """
        title: Lower a semantically validated date as epoch days.
        parameters:
          node:
            type: astx.LiteralDate
        """
        info = cast(SemanticInfo | None, getattr(node, "semantic", None))
        days = require_semantic_metadata(
            None
            if info is None
            else info.extras.get("dataframe_temporal_value"),
            node=node,
            metadata="dataframe_temporal_value",
            context="date literal",
        )
        self.services.function_state.result_stack.append(
            ir.Constant(ir.IntType(32), days)
        )

    @dispatch
    def visit(self, node: astx.LiteralTime) -> None:
        """
        title: Visit LiteralTime nodes.
        parameters:
          node:
            type: astx.LiteralTime
        """
        hour_minute_count = 2
        hour_minute_second_count = 3
        max_hour = 23
        max_minute_second = 59

        value = node.value.strip()
        parts = value.split(":")
        if len(parts) not in (hour_minute_count, hour_minute_second_count):
            raise_lowering_error(
                (
                    "LiteralTime: invalid time format '"
                    f"{node.value}"
                    "'. Expected 'HH:MM' or 'HH:MM:SS'."
                ),
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
            )

        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except ValueError as exc:
            raise_lowering_error(
                f"LiteralTime: invalid hour/minute in '{node.value}'.",
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
                cause=exc,
            )

        if len(parts) == hour_minute_second_count:
            sec_part = parts[2]
            if "." in sec_part:
                raise_lowering_error(
                    (
                        "LiteralTime: fractional seconds not supported in '"
                        f"{node.value}"
                        "'."
                    ),
                    code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                    node=node,
                )
            try:
                second = int(sec_part)
            except ValueError as exc:
                raise_lowering_error(
                    f"LiteralTime: invalid seconds in '{node.value}'.",
                    code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                    node=node,
                    cause=exc,
                )
        else:
            second = 0

        if not (0 <= hour <= max_hour):
            raise_lowering_error(
                f"LiteralTime: hour out of range in '{node.value}'.",
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
            )
        if not (0 <= minute <= max_minute_second):
            raise_lowering_error(
                f"LiteralTime: minute out of range in '{node.value}'.",
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
            )
        if not (0 <= second <= max_minute_second):
            raise_lowering_error(
                f"LiteralTime: second out of range in '{node.value}'.",
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
            )

        i32 = self.services.llvm.INT32_TYPE
        const_time = ir.Constant(
            self.services.llvm.TIME_TYPE,
            [
                ir.Constant(i32, hour),
                ir.Constant(i32, minute),
                ir.Constant(i32, second),
            ],
        )
        self.services.function_state.result_stack.append(const_time)

    @dispatch
    def visit(self, node: astx.LiteralTimestamp) -> None:
        """
        title: Visit LiteralTimestamp nodes.
        parameters:
          node:
            type: astx.LiteralTimestamp
        """
        nanosecond_digits = 9
        max_hour = 23
        max_minute_second = 59

        value = node.value.strip()
        if "T" in value:
            date_part, time_part = value.split("T", 1)
        elif " " in value:
            date_part, time_part = value.split(" ", 1)
        else:
            raise_lowering_error(
                (
                    "LiteralTimestamp: invalid format '"
                    f"{node.value}"
                    "'. Expected 'YYYY-MM-DDTHH:MM:SS[.fffffffff]' (or "
                    "space instead of 'T')."
                ),
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
            )

        if time_part.endswith("Z") or "+" in time_part or "-" in time_part[2:]:
            raise_lowering_error(
                (
                    "LiteralTimestamp: timezone offsets not supported in '"
                    f"{node.value}"
                    "'."
                ),
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
            )

        try:
            y_str, m_str, d_str = date_part.split("-")
            year = int(y_str)
            month = int(m_str)
            day = int(d_str)
            datetime(year, month, day)
        except ValueError as exc:
            raise_lowering_error(
                (
                    "LiteralTimestamp: invalid date in '"
                    f"{node.value}"
                    "'. Expected valid 'YYYY-MM-DD'."
                ),
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
                cause=exc,
            )
        except ValueError as exc:
            raise_lowering_error(
                (
                    "LiteralTimestamp: invalid date part in '"
                    f"{node.value}"
                    "'. Expected 'YYYY-MM-DD'."
                ),
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
                cause=exc,
            )

        frac_ns = 0
        try:
            if "." in time_part:
                hms, frac = time_part.split(".", 1)
                if not frac.isdigit():
                    raise ValueError("fractional seconds must be digits")
                if len(frac) > nanosecond_digits:
                    frac = frac[:nanosecond_digits]
                frac_ns = int(frac.ljust(nanosecond_digits, "0"))
            else:
                hms = time_part

            h_str, m_str, s_str = hms.split(":")
            hour = int(h_str)
            minute = int(m_str)
            second = int(s_str)
        except ValueError as exc:
            raise_lowering_error(
                (
                    "LiteralTimestamp: invalid time part in '"
                    f"{node.value}"
                    "'. Expected 'HH:MM:SS' (optionally with "
                    "'.fffffffff')."
                ),
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
                cause=exc,
            )

        if not (0 <= hour <= max_hour):
            raise_lowering_error(
                f"LiteralTimestamp: hour out of range in '{node.value}'.",
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
            )
        if not (0 <= minute <= max_minute_second):
            raise_lowering_error(
                f"LiteralTimestamp: minute out of range in '{node.value}'.",
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
            )
        if not (0 <= second <= max_minute_second):
            raise_lowering_error(
                f"LiteralTimestamp: second out of range in '{node.value}'.",
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
            )

        i32 = self.services.llvm.INT32_TYPE
        const_ts = ir.Constant(
            self.services.llvm.TIMESTAMP_TYPE,
            [
                ir.Constant(i32, year),
                ir.Constant(i32, month),
                ir.Constant(i32, day),
                ir.Constant(i32, hour),
                ir.Constant(i32, minute),
                ir.Constant(i32, second),
                ir.Constant(i32, frac_ns),
            ],
        )
        self.services.function_state.result_stack.append(const_ts)

    @dispatch
    def visit(self, node: astx.LiteralDateTime) -> None:
        """
        title: Visit LiteralDateTime nodes.
        parameters:
          node:
            type: astx.LiteralDateTime
        """
        hour_minute_count = 2
        hour_minute_second_count = 3
        max_hour = 23
        max_minute_second = 59

        value = node.value.strip()
        if "T" in value:
            date_part, time_part = value.split("T", 1)
        elif " " in value:
            date_part, time_part = value.split(" ", 1)
        else:
            raise ValueError(
                f"LiteralDateTime: invalid format '{node.value}'. "
                "Expected 'YYYY-MM-DDTHH:MM[:SS]' (or space instead of 'T')."
            )

        if "." in time_part:
            raise ValueError(
                "LiteralDateTime: fractional seconds not supported in "
                f"'{node.value}'. Use LiteralTimestamp instead."
            )
        if time_part.endswith("Z") or "+" in time_part or "-" in time_part[2:]:
            raise ValueError(
                "LiteralDateTime: timezone offsets not supported in "
                f"'{node.value}'. Use LiteralTimestamp for timezones."
            )

        try:
            y_str, m_str, d_str = date_part.split("-")
            year = int(y_str)
            month = int(m_str)
            day = int(d_str)
        except ValueError as exc:
            raise ValueError(
                f"LiteralDateTime: invalid date part in '{node.value}'. "
                "Expected 'YYYY-MM-DD'."
            ) from exc

        int32_min, int32_max = -(2**31), 2**31 - 1
        if not (int32_min <= year <= int32_max):
            raise ValueError(
                f"LiteralDateTime: year out of 32-bit range in '{node.value}'."
            )

        try:
            parts = time_part.split(":")
            if len(parts) not in (hour_minute_count, hour_minute_second_count):
                raise ValueError("time must be HH:MM or HH:MM:SS")
            hour = int(parts[0])
            minute = int(parts[1])
            second = (
                int(parts[2]) if len(parts) == hour_minute_second_count else 0
            )
        except ValueError as exc:
            raise ValueError(
                f"LiteralDateTime: invalid time part in '{node.value}'. "
                "Expected 'HH:MM' or 'HH:MM:SS'."
            ) from exc

        if not (0 <= hour <= max_hour):
            raise ValueError(
                f"LiteralDateTime: hour out of range in '{node.value}'."
            )
        if not (0 <= minute <= max_minute_second):
            raise ValueError(
                f"LiteralDateTime: minute out of range in '{node.value}'."
            )
        if not (0 <= second <= max_minute_second):
            raise ValueError(
                f"LiteralDateTime: second out of range in '{node.value}'."
            )

        try:
            datetime(year, month, day)
            time_value(hour, minute, second)
        except ValueError as exc:
            raise ValueError(
                "LiteralDateTime: invalid calendar date/time in "
                f"'{node.value}'."
            ) from exc

        i32 = self.services.llvm.INT32_TYPE
        const_dt = ir.Constant(
            self.services.llvm.DATETIME_TYPE,
            [
                ir.Constant(i32, year),
                ir.Constant(i32, month),
                ir.Constant(i32, day),
                ir.Constant(i32, hour),
                ir.Constant(i32, minute),
                ir.Constant(i32, second),
            ],
        )
        self.services.function_state.result_stack.append(const_dt)
