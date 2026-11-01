"""
title: Lower resolved tabular operations through registered opaque-handle APIs.
"""

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import SemanticInfo
from irx.analysis.table_io import TableIOCall
from irx.builder.diagnostics import (
    raise_lowering_internal_error,
    require_semantic_metadata,
)
from irx.builder.extensions.calls import LoweringCall
from irx.extensions import HandlerContribution, contribute
from irx.typecheck import typechecked


@private
@typechecked
def emit_table_io(plan: TableIOCall, call: LoweringCall) -> None:
    """
    title: Emit a typed table plan using only explicit narrow backend services.
    parameters:
      plan:
        type: TableIOCall
      call:
        type: LoweringCall
    """
    node, services = call.node, call.services
    builder = services.builder
    pointer = ir.IntType(8).as_pointer()
    null = ir.Constant(pointer, None)
    zero = ir.Constant(ir.IntType(32), 0)
    values: dict[str, ir.Value] = {}

    def text(value: str) -> ir.Value:
        """
        title: Materialize trusted configuration text.
        parameters:
          value:
            type: str
        returns:
          type: ir.Value
        """
        return services.text(value)

    def invoke(feature: str, name: str, args: list[ir.Value]) -> ir.Value:
        """
        title: Request a native feature only for a resolved operation.
        parameters:
          feature:
            type: str
          name:
            type: str
          args:
            type: list[ir.Value]
        returns:
          type: ir.Value
        """
        return services.invoke(node, feature, name, args)

    # All explicitly supplied operands run once, in source order, before
    # constructing options. Pin class/table aliases across later side effects.
    for argument in plan.arguments:
        if argument.kind in {"texts", "ints"}:
            continue
        value = services.evaluate(argument.expression)
        if argument.handle_index is not None:
            value = services.handle(
                argument.expression, value, argument.handle_index
            )
        elif argument.kind in {"int", "bool", "float"}:
            target = (
                astx.Float64() if argument.kind == "float" else astx.Int64()
            )
            value = services.convert(argument.expression, value, target)
        values[argument.name] = value
    operation = plan.operation
    if operation == "where":
        construction = require_semantic_metadata(
            plan.construction,
            node=node,
            metadata="filter construction",
            context="predicate factory",
        )
        construction_info = getattr(construction, "semantic", None)
        if not isinstance(construction_info, SemanticInfo):
            raise_lowering_internal_error(
                "missing filter construction metadata", node=construction
            )
        resolution = require_semantic_metadata(
            construction_info.resolved_class_construction,
            node=node,
            metadata="class construction",
            context="predicate factory",
        )
        instance = services.construct(node, resolution)
        index = require_semantic_metadata(
            plan.result_handle_index,
            node=node,
            metadata="filter handle",
            context="predicate factory",
        )
        handle = builder.load(
            builder.gep(instance, [zero, ir.Constant(ir.IntType(32), index)])
        )
        value_argument = next(
            (a for a in plan.arguments if a.name == "value"), None
        )
        suffix = (
            "null"
            if value_argument is None
            else {
                "int": "i64",
                "float": "f64",
                "text": "text",
                "bool": "bool",
            }[value_argument.kind]
        )
        args = [handle, null, values["column"], values["operation"]]
        if value_argument is not None:
            value = values["value"]
            if value_argument.kind == "bool":
                value = builder.trunc(value, ir.IntType(32))
            args.append(value)
        invoke("parquet", "irx_rb_api_filter_" + suffix, args)
        return
    if operation.endswith("_frame"):
        args = [values["box"]]
        if "write" in operation:
            args.append(values["frame"])
        result = invoke("record_batch", "irx_rb_api_" + operation, args)
        if "write" not in operation:
            services.publish(node, result)
        return
    parquet = operation.endswith("parquet")
    feature = "parquet" if parquet else "record_batch"
    prefix = "irx_rb_api_options_" if parquet else "irx_rb_api_csv_options_"
    options = invoke(
        feature,
        prefix + ("copy" if parquet else "new"),
        [values.get("options", null)] if parquet else [],
    )
    options_cleanup = services.track(
        node, feature, prefix + "destroy", options
    )
    for argument in plan.arguments:
        name = argument.name
        if name in {"path", "frame", "schema", "options"}:
            continue
        if name == "filters":
            invoke(feature, prefix + "filters", [options, values[name]])
            continue
        if argument.kind in {"texts", "ints"}:
            invoke(feature, prefix + "clear", [options, text(name)])
            key = (
                {
                    "columns": "column",
                    "row_groups": "row_group",
                    "partition_columns": "partition_column",
                }.get(name, name)
                if parquet
                else name
            )
            for literal in argument.literals:
                value = (
                    text(literal)
                    if isinstance(literal, str)
                    else ir.Constant(ir.IntType(64), literal)
                )
                invoke(
                    feature,
                    prefix + ("text" if isinstance(literal, str) else "int"),
                    [options, text(key), value],
                )
        else:
            invoke(
                feature,
                prefix + ("text" if argument.kind == "text" else "int"),
                [options, text(name), values[name]],
            )
    reading = operation.startswith("read")
    args = (
        [values["path"], values.get("schema", null), options]
        if reading
        else [values["frame"], values["path"], options]
    )
    if parquet:
        args.append(ir.Constant(ir.IntType(32), int("options" not in values)))
    result = invoke(feature, "irx_rb_api_" + operation, args)
    if reading:
        services.publish(node, result)
    services.release(options_cleanup)
    return


@private
@typechecked
def lowering_contributions() -> tuple[HandlerContribution, ...]:
    """
    title: >-
      Register plan emission without importing or mutating the call driver.
    returns:
      type: tuple[HandlerContribution, Ellipsis]
    """
    return (
        contribute(
            "table.emit",
            "irx.table_io",
            "lowering",
            TableIOCall,
            LoweringCall,
            emit_table_io,
        ),
    )
