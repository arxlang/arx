"""
title: Test cases for collection data types.
"""

from __future__ import annotations

import pytest

from typeguard import TypeCheckError

import astx

from astx.literals.base import Literal
from astx.literals.collections import (
    LiteralDict,
    LiteralList,
    LiteralSet,
    LiteralTuple,
)
from astx.literals.numeric import LiteralInt32
from astx.types.collections import DictType, ListType, SetType, TupleType
from astx.types.operators import BinaryOp, UnaryOp


def test_range_type_exports_and_storage_independence() -> None:
    """
    title: Range models an integer progression, not an owning list or view.
    """
    from astx.types import RangeType
    from astx.types.collections import CollectionType

    value = RangeType()
    assert isinstance(value, CollectionType)
    assert isinstance(value, astx.RangeType)
    assert not isinstance(value, (astx.ListType, astx.SequenceType))
    assert str(value) == "RangeType"


def test_literal_list_creation() -> None:
    """
    title: Test creation of LiteralList.
    """
    elements: list[Literal] = [
        LiteralInt32(1),
        LiteralInt32(2),
        LiteralInt32(3),
    ]
    lit_list = LiteralList(elements)
    assert isinstance(lit_list, LiteralList)
    assert isinstance(lit_list.type_, ListType)
    assert lit_list.elements == elements


def test_literal_tuple_creation() -> None:
    """
    title: Test creation of LiteralTuple.
    """
    elements: tuple[Literal, ...] = (
        LiteralInt32(1),
        LiteralInt32(2),
        LiteralInt32(3),
    )
    lit_tuple = LiteralTuple(elements)
    assert isinstance(lit_tuple, LiteralTuple)
    assert isinstance(lit_tuple.type_, TupleType)
    assert lit_tuple.elements == elements


def test_literal_set_creation() -> None:
    """
    title: Test creation of LiteralSet.
    """
    elements: set[Literal] = {
        LiteralInt32(1),
        LiteralInt32(2),
        LiteralInt32(3),
    }
    lit_set = LiteralSet(elements)
    assert isinstance(lit_set, LiteralSet)
    assert isinstance(lit_set.type_, SetType)
    assert lit_set.elements == elements


def test_literal_dict_creation() -> None:
    """
    title: Test creation of LiteralDict.
    """
    elements: dict[Literal, Literal] = {
        LiteralInt32(1): LiteralInt32(10),
        LiteralInt32(2): LiteralInt32(20),
    }
    lit_dict = LiteralDict(elements)
    assert isinstance(lit_dict, LiteralDict)
    assert isinstance(lit_dict.type_, DictType)
    assert lit_dict.elements == elements


def test_literal_list_binary_addition() -> None:
    """
    title: Test binary addition operation on LiteralList.
    """
    elements1: list[Literal] = [LiteralInt32(1), LiteralInt32(2)]
    elements2: list[Literal] = [LiteralInt32(3), LiteralInt32(4)]
    lit_list1 = LiteralList(elements1)
    lit_list2 = LiteralList(elements2)
    combined = BinaryOp("+", lit_list1, lit_list2)
    assert isinstance(combined, BinaryOp)
    assert combined.op_code == "+"
    assert combined.lhs == lit_list1
    assert combined.rhs == lit_list2


def test_literal_list_unary_negation() -> None:
    """
    title: Test unary negation operation on LiteralList.
    """
    elements: list[Literal] = [
        LiteralInt32(1),
        LiteralInt32(2),
        LiteralInt32(3),
    ]
    lit_list = LiteralList(elements)
    negated = UnaryOp("-", lit_list)
    assert isinstance(negated, UnaryOp)
    assert negated.op_code == "-"
    assert negated.operand == lit_list


def test_literal_set_binary_union() -> None:
    """
    title: Test binary union operation on LiteralSet.
    """
    elements1: set[Literal] = {LiteralInt32(1), LiteralInt32(2)}
    elements2: set[Literal] = {LiteralInt32(3), LiteralInt32(4)}
    lit_set1 = LiteralSet(elements1)
    lit_set2 = LiteralSet(elements2)
    union_set = BinaryOp("|", lit_set1, lit_set2)
    assert isinstance(union_set, BinaryOp)
    assert union_set.op_code == "|"
    assert union_set.lhs == lit_set1
    assert union_set.rhs == lit_set2


def test_literal_dict_binary_merge() -> None:
    """
    title: Test binary merge operation on LiteralDict.
    """
    elements1: dict[Literal, Literal] = {LiteralInt32(1): LiteralInt32(10)}
    elements2: dict[Literal, Literal] = {LiteralInt32(2): LiteralInt32(20)}
    lit_dict1 = LiteralDict(elements1)
    lit_dict2 = LiteralDict(elements2)
    merged_dict = BinaryOp("**", lit_dict1, lit_dict2)
    assert isinstance(merged_dict, BinaryOp)
    assert merged_dict.op_code == "**"
    assert merged_dict.lhs == lit_dict1
    assert merged_dict.rhs == lit_dict2


def test_list_expression_preserves_nonliteral_elements() -> None:
    """
    title: Owned construction is distinct from the literal-only AST contract.
    """
    import astx

    from astx.collections import ListExpr

    elements: list[astx.DataType] = [
        astx.Identifier("value"),
        astx.FunctionCall("next", []),
        astx.Cast(astx.LiteralInteger(1), astx.Int64()),
    ]
    expression = ListExpr(elements, loc=astx.SourceLocation(2, 3))
    assert astx.ListExpr is ListExpr
    assert expression.elements == elements
    assert expression.elements is not elements
    assert (expression.loc.line, expression.loc.col) == (2, 3)
    assert isinstance(expression.type_, astx.types.AnyType)
    for simplified in (False, True):
        assert "elements" in str(expression.get_struct(simplified))
    assert isinstance(astx.ListLength(expression).type_, astx.Int64)
    assert isinstance(astx.CollectionLength(expression).type_, astx.Int64)


def test_list_expression_checks_every_element() -> None:
    """
    title: Invalid non-first items cannot bypass runtime collection checking.
    """
    from typing import cast

    import pytest

    from typeguard import TypeCheckError

    import astx

    with pytest.raises(TypeCheckError):
        astx.ListExpr(cast(list[astx.DataType], [astx.LiteralInt32(1), "bad"]))
    with pytest.raises(TypeCheckError):
        astx.LiteralList(cast(list[Literal], [astx.Identifier("value")]))


def test_numeric_sequence_model() -> None:
    """
    title: Model exact element types and reject untyped runtime arguments.
    """
    element = astx.NullableType(astx.Int64())
    sequence = astx.SequenceType(element)
    assert sequence.element_type is element
    assert "nullable" in str(sequence)
    with pytest.raises(TypeCheckError):
        astx.SequenceType("i64")  # type: ignore[arg-type]
