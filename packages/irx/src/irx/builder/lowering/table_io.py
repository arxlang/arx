"""
title: Lower resolved tabular operations through registered opaque-handle APIs.
"""

from typing import cast

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import SemanticInfo
from irx.analysis.table_io import TABLE_IO, TableIOCall
from irx.builder.diagnostics import (
    raise_lowering_internal_error,
    require_lowered_value,
    require_semantic_metadata,
)
from irx.builder.lowering.classes import ClassVisitorMixin
from irx.builder.lowering.control_flow import ControlFlowVisitorMixin
from irx.builder.runtime import safe_pop
from irx.typecheck import typechecked


@private
@typechecked
def lower_table_io(
    visitor: ClassVisitorMixin,
    node: astx.FunctionCall | astx.MethodCall,
) -> bool:
    """
    title: Consume an I/O plan without rediscovering semantic facts.
    parameters:
      visitor:
        type: ClassVisitorMixin
      node:
        type: astx.FunctionCall | astx.MethodCall
    returns:
      type: bool
    """
    semantic = getattr(node, "semantic", None)
    if not isinstance(semantic, SemanticInfo):
        return False
    plan = semantic.extras.get(TABLE_IO)
    if not isinstance(plan, TableIOCall):
        function = semantic.resolved_function
        if function is not None and function.signature.metadata.get(TABLE_IO):
            raise_lowering_internal_error(
                "missing resolved table I/O plan", node=node
            )
        return False
    builder = visitor._llvm.ir_builder
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
        return cast(
            ControlFlowVisitorMixin, visitor
        )._constant_c_string_pointer(value, name_hint="table_io")

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
        return visitor.checked_native_call(
            node, visitor.require_runtime_symbol(feature, name), args
        )

    # All explicitly supplied operands run once, in source order, before
    # constructing options. Pin class/table aliases across later side effects.
    for argument in plan.arguments:
        if argument.kind in {"texts", "ints"}:
            continue
        visitor.visit_child(argument.expression)
        value = require_lowered_value(
            safe_pop(visitor.result_stack),
            node=argument.expression,
            context="table I/O argument",
        )
        visitor.class_pin(argument.expression, value)
        if argument.handle_index is not None:
            visitor.class_operation(argument.expression, "require", value)
            value = builder.load(
                builder.gep(
                    value,
                    [zero, ir.Constant(ir.IntType(32), argument.handle_index)],
                )
            )
        elif argument.kind in {"int", "bool", "float"}:
            target = (
                astx.Float64() if argument.kind == "float" else astx.Int64()
            )
            value = visitor._cast_ast_value(
                value,
                source_type=visitor._resolved_ast_type(argument.expression),
                target_type=target,
            )
        values[argument.name] = value
    operation = plan.operation
    if operation == "where":
        construction = require_semantic_metadata(
            plan.construction,
            node=node,
            metadata="filter construction",
            context="predicate factory",
        )
        resolution = require_semantic_metadata(
            cast(
                SemanticInfo, getattr(construction, "semantic", None)
            ).resolved_class_construction,
            node=node,
            metadata="class construction",
            context="predicate factory",
        )
        visitor.lower_class_construct(node, resolution)
        instance = visitor.result_stack[-1]
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
        return True
    if operation.endswith("_frame"):
        args = [values["box"]]
        if "write" in operation:
            args.append(values["frame"])
        result = invoke("record_batch", "irx_rb_api_" + operation, args)
        if "write" not in operation:
            visitor.arrow_temporary(node, result)
            visitor.result_stack.append(result)
        return True
    parquet = operation.endswith("parquet")
    feature = "parquet" if parquet else "record_batch"
    prefix = "irx_rb_api_options_" if parquet else "irx_rb_api_csv_options_"
    options = invoke(
        feature,
        prefix + ("copy" if parquet else "new"),
        [values.get("options", null)] if parquet else [],
    )
    options_cleanup = visitor.track_native_handle(
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
        visitor.arrow_temporary(node, result)
        visitor.result_stack.append(result)
    visitor.release_native_handle(options_cleanup)
    return True
