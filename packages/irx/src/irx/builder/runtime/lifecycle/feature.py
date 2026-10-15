"""
title: Managed class-instance and generator-frame runtime helpers.
summary: >-
  Register module-local LLVM helpers that retain and release class instances
  and deterministically close suspended generator frames.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from llvmlite import ir

from irx.builder.runtime.features import ExternalSymbolSpec, RuntimeFeature
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.protocols import VisitorProtocol

LIFECYCLE_RUNTIME_FEATURE = "lifecycle"
CLASS_RETAIN_SYMBOL = "irx_class_retain"
CLASS_RELEASE_SYMBOL = "irx_class_release"
GENERATOR_RELEASE_SYMBOL = "irx_generator_release"


@typechecked
def generator_value_type(visitor: VisitorProtocol) -> ir.LiteralStructType:
    """
    title: Return the lowered generator object ABI type.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.LiteralStructType
    """
    pointer = visitor._llvm.OPAQUE_POINTER_TYPE
    return ir.LiteralStructType([pointer, pointer, pointer])


@typechecked
def class_header_type(visitor: VisitorProtocol) -> ir.LiteralStructType:
    """
    title: Return the common prefix of every lowered class instance.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.LiteralStructType
    """
    pointer = visitor._llvm.OPAQUE_POINTER_TYPE
    return ir.LiteralStructType(
        [pointer, pointer, pointer, visitor._llvm.INT64_TYPE]
    )


@typechecked
def build_lifecycle_runtime_feature() -> RuntimeFeature:
    """
    title: Build the managed aggregate and frame runtime feature.
    returns:
      type: RuntimeFeature
    """
    return RuntimeFeature(
        name=LIFECYCLE_RUNTIME_FEATURE,
        symbols={
            CLASS_RETAIN_SYMBOL: ExternalSymbolSpec(
                CLASS_RETAIN_SYMBOL,
                _define_class_retain,
            ),
            CLASS_RELEASE_SYMBOL: ExternalSymbolSpec(
                CLASS_RELEASE_SYMBOL,
                _define_class_release,
            ),
            GENERATOR_RELEASE_SYMBOL: ExternalSymbolSpec(
                GENERATOR_RELEASE_SYMBOL,
                _define_generator_release,
            ),
        },
        metadata={
            "class_ownership": "shared",
            "generator_ownership": "unique",
        },
    )


@typechecked
def _existing_function(
    visitor: VisitorProtocol,
    name: str,
    function_type: ir.FunctionType,
) -> ir.Function | None:
    """
    title: Return an existing compatible lifecycle helper.
    parameters:
      visitor:
        type: VisitorProtocol
      name:
        type: str
      function_type:
        type: ir.FunctionType
    returns:
      type: ir.Function | None
    """
    existing = visitor._llvm.module.globals.get(name)
    if existing is None:
        return None
    if not isinstance(existing, ir.Function):
        raise TypeError(f"Global '{name}' is not a function")
    if existing.function_type != function_type:
        raise TypeError(f"Function '{name}' already exists with a mismatch")
    return cast(ir.Function, existing)


@typechecked
def _define_class_retain(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Define the class-instance retain helper.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    pointer = visitor._llvm.OPAQUE_POINTER_TYPE
    function_type = ir.FunctionType(
        visitor._llvm.INT32_TYPE,
        [pointer, pointer.as_pointer(), pointer.as_pointer()],
    )
    existing = _existing_function(
        visitor,
        CLASS_RETAIN_SYMBOL,
        function_type,
    )
    if existing is not None:
        return existing

    function = ir.Function(
        visitor._llvm.module,
        function_type,
        CLASS_RETAIN_SYMBOL,
    )
    function.linkage = "internal"
    instance, output, _error = function.args
    entry = function.append_basic_block("entry")
    validate = function.append_basic_block("validate")
    retain = function.append_basic_block("retain")
    success = function.append_basic_block("success")
    failure = function.append_basic_block("failure")
    builder = ir.IRBuilder(entry)
    output_is_null = builder.icmp_unsigned(
        "==",
        output,
        ir.Constant(output.type, None),
        name="output_is_null",
    )
    builder.cbranch(output_is_null, failure, validate)

    builder.position_at_start(validate)
    builder.store(ir.Constant(pointer, None), output)
    instance_is_null = builder.icmp_unsigned(
        "==",
        instance,
        ir.Constant(pointer, None),
        name="instance_is_null",
    )
    builder.cbranch(instance_is_null, failure, retain)

    builder.position_at_start(retain)
    header = builder.bitcast(
        instance,
        class_header_type(visitor).as_pointer(),
        name="class_header",
    )
    count_address = builder.gep(
        header,
        [
            ir.Constant(visitor._llvm.INT32_TYPE, 0),
            ir.Constant(visitor._llvm.INT32_TYPE, 3),
        ],
        inbounds=True,
        name="reference_count_address",
    )
    count = builder.load(count_address, name="reference_count")
    count_is_zero = builder.icmp_unsigned(
        "==",
        count,
        ir.Constant(visitor._llvm.INT64_TYPE, 0),
        name="reference_count_is_zero",
    )
    next_count = builder.add(
        count,
        ir.Constant(visitor._llvm.INT64_TYPE, 1),
        name="retained_reference_count",
    )
    count_overflowed = builder.icmp_unsigned(
        "==",
        next_count,
        ir.Constant(visitor._llvm.INT64_TYPE, 0),
        name="reference_count_overflowed",
    )
    count_invalid = builder.or_(
        count_is_zero,
        count_overflowed,
        name="reference_count_invalid",
    )
    builder.cbranch(count_invalid, failure, success)

    builder.position_at_start(success)
    builder.store(next_count, count_address)
    builder.store(instance, output)
    builder.ret(ir.Constant(visitor._llvm.INT32_TYPE, 0))

    builder.position_at_start(failure)
    builder.ret(ir.Constant(visitor._llvm.INT32_TYPE, 1))
    return function


@typechecked
def _define_class_release(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Define the class-instance release helper.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    pointer = visitor._llvm.OPAQUE_POINTER_TYPE
    function_type = ir.FunctionType(
        visitor._llvm.INT32_TYPE,
        [pointer.as_pointer(), pointer.as_pointer()],
    )
    existing = _existing_function(
        visitor,
        CLASS_RELEASE_SYMBOL,
        function_type,
    )
    if existing is not None:
        return existing

    function = ir.Function(
        visitor._llvm.module,
        function_type,
        CLASS_RELEASE_SYMBOL,
    )
    function.linkage = "internal"
    slot, _error = function.args
    entry = function.append_basic_block("entry")
    load_instance = function.append_basic_block("load_instance")
    release = function.append_basic_block("release")
    valid_count = function.append_basic_block("valid_count")
    decrement = function.append_basic_block("decrement")
    destroy = function.append_basic_block("destroy")
    success = function.append_basic_block("success")
    failure = function.append_basic_block("failure")
    builder = ir.IRBuilder(entry)
    slot_is_null = builder.icmp_unsigned(
        "==",
        slot,
        ir.Constant(slot.type, None),
        name="slot_is_null",
    )
    builder.cbranch(slot_is_null, failure, load_instance)

    builder.position_at_start(load_instance)
    instance = builder.load(slot, name="class_instance")
    instance_is_null = builder.icmp_unsigned(
        "==",
        instance,
        ir.Constant(pointer, None),
        name="instance_is_null",
    )
    builder.cbranch(instance_is_null, success, release)

    builder.position_at_start(release)
    header = builder.bitcast(
        instance,
        class_header_type(visitor).as_pointer(),
        name="class_header",
    )
    count_address = builder.gep(
        header,
        [
            ir.Constant(visitor._llvm.INT32_TYPE, 0),
            ir.Constant(visitor._llvm.INT32_TYPE, 3),
        ],
        inbounds=True,
        name="reference_count_address",
    )
    count = builder.load(count_address, name="reference_count")
    count_is_zero = builder.icmp_unsigned(
        "==",
        count,
        ir.Constant(visitor._llvm.INT64_TYPE, 0),
        name="reference_count_is_zero",
    )
    count_is_one = builder.icmp_unsigned(
        "==",
        count,
        ir.Constant(visitor._llvm.INT64_TYPE, 1),
        name="reference_count_is_one",
    )
    builder.cbranch(count_is_zero, failure, valid_count)

    builder.position_at_start(valid_count)
    builder.cbranch(count_is_one, destroy, decrement)

    builder.position_at_start(decrement)
    next_count = builder.sub(
        count,
        ir.Constant(visitor._llvm.INT64_TYPE, 1),
        name="released_reference_count",
    )
    builder.store(next_count, count_address)
    builder.branch(success)

    builder.position_at_start(destroy)
    destructor_address = builder.gep(
        header,
        [
            ir.Constant(visitor._llvm.INT32_TYPE, 0),
            ir.Constant(visitor._llvm.INT32_TYPE, 2),
        ],
        inbounds=True,
        name="destructor_address",
    )
    destructor_raw = builder.load(
        destructor_address,
        name="destructor_raw",
    )
    destructor = builder.bitcast(
        destructor_raw,
        ir.FunctionType(visitor._llvm.VOID_TYPE, [pointer]).as_pointer(),
        name="destructor",
    )
    builder.call(destructor, [instance])
    builder.branch(success)

    builder.position_at_start(success)
    builder.store(ir.Constant(pointer, None), slot)
    builder.ret(ir.Constant(visitor._llvm.INT32_TYPE, 0))

    builder.position_at_start(failure)
    builder.ret(ir.Constant(visitor._llvm.INT32_TYPE, 1))
    return function


@typechecked
def _define_generator_release(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Define the generator-frame release helper.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    pointer = visitor._llvm.OPAQUE_POINTER_TYPE
    value_type = generator_value_type(visitor)
    function_type = ir.FunctionType(
        visitor._llvm.INT32_TYPE,
        [value_type.as_pointer(), pointer.as_pointer()],
    )
    existing = _existing_function(
        visitor,
        GENERATOR_RELEASE_SYMBOL,
        function_type,
    )
    if existing is not None:
        return existing

    function = ir.Function(
        visitor._llvm.module,
        function_type,
        GENERATOR_RELEASE_SYMBOL,
    )
    function.linkage = "internal"
    slot, _error = function.args
    entry = function.append_basic_block("entry")
    load_value = function.append_basic_block("load_value")
    destroy = function.append_basic_block("destroy")
    success = function.append_basic_block("success")
    failure = function.append_basic_block("failure")
    builder = ir.IRBuilder(entry)
    slot_is_null = builder.icmp_unsigned(
        "==",
        slot,
        ir.Constant(slot.type, None),
        name="slot_is_null",
    )
    builder.cbranch(slot_is_null, failure, load_value)

    builder.position_at_start(load_value)
    value = builder.load(slot, name="generator_value")
    frame = builder.extract_value(value, 0, name="generator_frame")
    destroy_raw = builder.extract_value(value, 2, name="generator_destroy_raw")
    frame_is_null = builder.icmp_unsigned(
        "==",
        frame,
        ir.Constant(pointer, None),
        name="frame_is_null",
    )
    builder.cbranch(frame_is_null, success, destroy)

    builder.position_at_start(destroy)
    destroy_function = builder.bitcast(
        destroy_raw,
        ir.FunctionType(visitor._llvm.VOID_TYPE, [pointer]).as_pointer(),
        name="generator_destroy",
    )
    builder.call(destroy_function, [frame])
    builder.branch(success)

    builder.position_at_start(success)
    builder.store(ir.Constant(value_type, None), slot)
    builder.ret(ir.Constant(visitor._llvm.INT32_TYPE, 0))

    builder.position_at_start(failure)
    builder.ret(ir.Constant(visitor._llvm.INT32_TYPE, 1))
    return function


__all__ = [
    "CLASS_RELEASE_SYMBOL",
    "CLASS_RETAIN_SYMBOL",
    "GENERATOR_RELEASE_SYMBOL",
    "LIFECYCLE_RUNTIME_FEATURE",
    "build_lifecycle_runtime_feature",
    "class_header_type",
    "generator_value_type",
]
