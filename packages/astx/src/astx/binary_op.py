"""
title: IRx-owned BinaryOp node specializations.
"""

from __future__ import annotations

from astx.tools.typing import typechecked
from astx.types import BinaryOp

SPECIALIZED_BINARY_OP_EXTRA = "specialized_binary_op"


@typechecked
class AssignmentBinOp(BinaryOp):
    """
    title: Specialized assignment binary operation node.
    """


@typechecked
class AddBinOp(BinaryOp):
    """
    title: Specialized addition binary operation node.
    """


@typechecked
class SubBinOp(BinaryOp):
    """
    title: Specialized subtraction binary operation node.
    """


@typechecked
class MulBinOp(BinaryOp):
    """
    title: Specialized multiplication binary operation node.
    """


@typechecked
class DivBinOp(BinaryOp):
    """
    title: Specialized division binary operation node.
    """


@typechecked
class ModBinOp(BinaryOp):
    """
    title: Specialized modulo binary operation node.
    """


@typechecked
class EqBinOp(BinaryOp):
    """
    title: Specialized equality binary operation node.
    """


@typechecked
class NeBinOp(BinaryOp):
    """
    title: Specialized inequality binary operation node.
    """


@typechecked
class LtBinOp(BinaryOp):
    """
    title: Specialized less-than binary operation node.
    """


@typechecked
class GtBinOp(BinaryOp):
    """
    title: Specialized greater-than binary operation node.
    """


@typechecked
class LeBinOp(BinaryOp):
    """
    title: Specialized less-than-or-equal binary operation node.
    """


@typechecked
class GeBinOp(BinaryOp):
    """
    title: Specialized greater-than-or-equal binary operation node.
    """


@typechecked
class LogicalAndBinOp(BinaryOp):
    """
    title: Specialized logical-and binary operation node.
    """


@typechecked
class LogicalOrBinOp(BinaryOp):
    """
    title: Specialized logical-or binary operation node.
    """


@typechecked
class BitOrBinOp(BinaryOp):
    """
    title: Specialized bitwise-or binary operation node.
    """


@typechecked
class BitAndBinOp(BinaryOp):
    """
    title: Specialized bitwise-and binary operation node.
    """


@typechecked
class BitXorBinOp(BinaryOp):
    """
    title: Specialized bitwise-xor binary operation node.
    """


_BINARY_OP_TYPES: dict[str, type[BinaryOp]] = {
    "=": AssignmentBinOp,
    "+": AddBinOp,
    "-": SubBinOp,
    "*": MulBinOp,
    "/": DivBinOp,
    "%": ModBinOp,
    "==": EqBinOp,
    "!=": NeBinOp,
    "<": LtBinOp,
    ">": GtBinOp,
    "<=": LeBinOp,
    ">=": GeBinOp,
    "&&": LogicalAndBinOp,
    "and": LogicalAndBinOp,
    "||": LogicalOrBinOp,
    "or": LogicalOrBinOp,
    "|": BitOrBinOp,
    "&": BitAndBinOp,
    "^": BitXorBinOp,
}


@typechecked
def binary_op_type_for_opcode(op_code: str) -> type[BinaryOp]:
    """
    title: Return the specialized BinaryOp subclass for an opcode.
    parameters:
      op_code:
        type: str
    returns:
      type: type[BinaryOp]
    """
    return _BINARY_OP_TYPES.get(op_code, BinaryOp)


@typechecked
def specialize_binary_op(node: BinaryOp) -> BinaryOp:
    """
    title: Return a specialized BinaryOp instance for the given opcode.
    parameters:
      node:
        type: BinaryOp
    returns:
      type: BinaryOp
    """
    target_type = binary_op_type_for_opcode(node.op_code)
    if target_type is BinaryOp or isinstance(node, target_type):
        return node

    specialized = target_type(
        node.op_code,
        node.lhs,
        node.rhs,
        loc=node.loc,
        parent=node.parent,
    )
    specialized.__dict__.update(vars(node))
    return specialized


__all__ = [
    "SPECIALIZED_BINARY_OP_EXTRA",
    "AddBinOp",
    "AssignmentBinOp",
    "BitAndBinOp",
    "BitOrBinOp",
    "BitXorBinOp",
    "DivBinOp",
    "EqBinOp",
    "GeBinOp",
    "GtBinOp",
    "LeBinOp",
    "LogicalAndBinOp",
    "LogicalOrBinOp",
    "LtBinOp",
    "ModBinOp",
    "MulBinOp",
    "NeBinOp",
    "SubBinOp",
    "binary_op_type_for_opcode",
    "specialize_binary_op",
]
