"""
title: Borrowed sequence descriptor and exact numeric callback ABI.
summary: >-
  A descriptor carries borrowed context, i64 length, a checked read callback,
  and adapter configuration. Readers publish scalar bits and validity only on
  status zero. No Arrow implementation layout is part of this ABI.
"""

from typing import TYPE_CHECKING

from llvmlite import ir
from public import private

from irx.builder.runtime.features import declare_external_function
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.protocols import VisitorProtocol


@private
@typechecked
def sequence_reader_type() -> ir.FunctionType:
    """
    title: Define status(context, index, configuration, bits-out, valid-out).
    returns:
      type: ir.FunctionType
    """
    return ir.FunctionType(
        ir.IntType(32),
        [
            ir.IntType(8).as_pointer(),
            ir.IntType(64),
            ir.IntType(32),
            ir.IntType(64).as_pointer(),
            ir.IntType(32).as_pointer(),
        ],
    )


@private
@typechecked
def sequence_view_type() -> ir.LiteralStructType:
    """
    title: Define the call-scoped borrowed numeric descriptor.
    returns:
      type: ir.LiteralStructType
    """
    return ir.LiteralStructType(
        [
            ir.IntType(8).as_pointer(),
            ir.IntType(64),
            sequence_reader_type().as_pointer(),
            ir.IntType(32),
        ]
    )


@private
@typechecked
def declare_sequence_reader(
    visitor: "VisitorProtocol", name: str
) -> ir.Function:
    """
    title: Declare a registered collection-specific checked numeric reader.
    parameters:
      visitor:
        type: VisitorProtocol
      name:
        type: str
    returns:
      type: ir.Function
    """
    return declare_external_function(
        visitor._llvm.module, name, sequence_reader_type()
    )
