"""
title: Exhaustive portable descriptor fixtures shared by schema tests.
"""

from dataclasses import replace

from astx.schema import (
    LogicalKind,
    LogicalParameter,
    LogicalType,
    ParameterKind,
    SchemaField,
    TimeUnit,
)


def logical_type_cases() -> tuple[LogicalType, ...]:
    """
    title: Supply a parameterized descriptor for every logical family.
    returns:
      type: tuple[LogicalType, Ellipsis]
    """
    result: list[LogicalType] = []
    int32 = LogicalType(LogicalKind.INT32)
    item = SchemaField(
        "item", int32, nullable=True, metadata=((b"unit", b"\x00\xff"),)
    )
    for kind in LogicalKind:
        fields: tuple[SchemaField, ...] = ()
        parameters: tuple[LogicalParameter, ...] = ()
        if kind.value.startswith("decimal"):
            parameters = (
                LogicalParameter(ParameterKind.PRECISION, 9),
                LogicalParameter(ParameterKind.SCALE, -2),
            )
        if kind in {
            LogicalKind.TIME32,
            LogicalKind.TIME64,
            LogicalKind.TIMESTAMP,
            LogicalKind.DURATION,
        }:
            unit = (
                TimeUnit.SECOND
                if kind is LogicalKind.TIME32
                else TimeUnit.NANOSECOND
            )
            parameters = (LogicalParameter(ParameterKind.TIME_UNIT, unit),)
        if kind is LogicalKind.TIMESTAMP:
            parameters += (LogicalParameter(ParameterKind.TIMEZONE, "UTC"),)
        if kind is LogicalKind.FIXED_BINARY:
            parameters = (LogicalParameter(ParameterKind.BYTE_WIDTH, 16),)
        if "list" in kind.value:
            fields = (item,)
        if kind is LogicalKind.FIXED_LIST:
            parameters = (LogicalParameter(ParameterKind.LIST_SIZE, 3),)
        if kind is LogicalKind.STRUCT:
            fields = (
                item,
                SchemaField("name", LogicalType(LogicalKind.STRING)),
            )
        if kind is LogicalKind.MAP:
            fields = (
                SchemaField(
                    "entries",
                    LogicalType(
                        LogicalKind.STRUCT,
                        fields=(
                            SchemaField("key", int32),
                            replace(item, name="value"),
                        ),
                    ),
                ),
            )
            parameters = (LogicalParameter(ParameterKind.KEYS_SORTED, True),)
        if kind in {LogicalKind.SPARSE_UNION, LogicalKind.DENSE_UNION}:
            fields = (
                item,
                SchemaField("text", LogicalType(LogicalKind.STRING)),
            )
            parameters = (
                LogicalParameter(ParameterKind.TYPE_CODES, (3, 127)),
            )
        if kind is LogicalKind.DICTIONARY:
            fields = (
                SchemaField("indices", LogicalType(LogicalKind.UINT16)),
                SchemaField("values", LogicalType(LogicalKind.STRING)),
            )
            parameters = (LogicalParameter(ParameterKind.ORDERED, True),)
        if kind is LogicalKind.RUN_END_ENCODED:
            fields = (
                SchemaField("run_ends", int32),
                SchemaField(
                    "values", LogicalType(LogicalKind.STRING), nullable=True
                ),
            )
        if kind is LogicalKind.EXTENSION:
            fields = (SchemaField("storage", LogicalType(LogicalKind.BINARY)),)
            parameters = (
                LogicalParameter(
                    ParameterKind.EXTENSION_NAME, "arx.test.opaque"
                ),
                LogicalParameter(
                    ParameterKind.EXTENSION_METADATA, b"\x00\xffpayload"
                ),
            )
        result.append(LogicalType(kind, fields=fields, parameters=parameters))
    return tuple(result)
