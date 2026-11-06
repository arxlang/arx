"""
title: Analysis-owned homogeneous storage for logical list literals.
summary: >-
  Logical member types stay in ListType. This fact separately selects the
  homogeneous representation and every numeric conversion needed by lowering.
"""

from __future__ import annotations

import math

from dataclasses import dataclass, replace

import astx

from public import private, public

from irx.analysis.facts import FactKey, SemanticFact
from irx.analysis.float_literals import rounded_float
from irx.analysis.numeric_literals import numeric_constant
from irx.analysis.numeric_policy import (
    FLOAT_PRECISIONS,
    NumericConversion,
    NumericConversionKind,
    classify_numeric_conversion,
)
from irx.analysis.resolved_nodes import ImplicitConversion
from irx.analysis.types import common_numeric_type, is_string_type, same_type
from irx.diagnostics import DiagnosticBag, DiagnosticCodes
from irx.typecheck import typechecked


@public
@typechecked
@dataclass(frozen=True)
class LiteralStorage(SemanticFact):
    """
    title: Resolved list representation and element-aligned conversion plans.
    summary: >-
      None denotes a nonnumeric identity conversion. Numeric plans include
      identity conversions. A constant-specific implicit plan is permitted only
      after analysis proves exact representability in the target format. Empty
      literals explicitly use i32 storage. No AST dependencies are held.
    attributes:
      element_type:
        type: astx.DataType
      conversions:
        type: tuple[NumericConversion | None, Ellipsis]
    """

    element_type: astx.DataType
    conversions: tuple[NumericConversion | None, ...]

    def __post_init__(self) -> None:
        """
        title: Check every generated constructor field and conversion item.
        """
        self.validate()

    def validate(self) -> None:
        """
        title: Validate nominal fields and every nested numeric plan.
        """
        validate_literal_storage(self.element_type, self.conversions)

    def dependencies(self) -> tuple[astx.AST, ...]:
        """
        title: Return no AST edges for this representation-only fact.
        returns:
          type: tuple[astx.AST, Ellipsis]
        """
        return ()


LITERAL_STORAGE = FactKey("irx.literals", LiteralStorage)


@private
@typechecked
def validate_literal_storage(
    element_type: astx.DataType,
    conversions: tuple[NumericConversion | None, ...],
) -> None:
    """
    title: Validate storage and complete conversion payloads at the boundary.
    parameters:
      element_type:
        type: astx.DataType
      conversions:
        type: tuple[NumericConversion | None, Ellipsis]
    """
    for conversion in conversions:
        if conversion is None:
            continue
        validate_conversion(
            conversion.source_type,
            conversion.target_type,
            conversion.kind,
            conversion.implicit,
            conversion.requires_range_check,
        )
        if not same_type(conversion.target_type, element_type):
            raise ValueError("literal conversion target must match storage")
        if not conversion.implicit or conversion.requires_range_check:
            raise ValueError(
                "literal storage requires proven safe conversions"
            )


@private
@typechecked
def validate_conversion(
    source: astx.DataType,
    target: astx.DataType,
    kind: NumericConversionKind,
    implicit: bool,
    requires_range_check: bool,
) -> None:
    """
    title: Check all fields of an immutable numeric conversion descriptor.
    parameters:
      source:
        type: astx.DataType
      target:
        type: astx.DataType
      kind:
        type: NumericConversionKind
      implicit:
        type: bool
      requires_range_check:
        type: bool
    """
    del source, target, kind, implicit, requires_range_check


@private
@typechecked
def constant_fits_float(node: astx.AST, target: astx.DataType) -> bool:
    """
    title: Prove exact conversion of an analyzed literal, not a typed domain.
    parameters:
      node:
        type: astx.AST
      target:
        type: astx.DataType
    returns:
      type: bool
    """
    if not isinstance(node, astx.Literal):
        return False
    value = numeric_constant(node)
    if value is None:
        return False
    converted = rounded_float(value, target)
    return converted == value or (
        isinstance(value, float)
        and math.isnan(value)
        and math.isnan(converted)
    )


@private
@typechecked
def resolve_literal_storage(
    node: astx.LiteralList | astx.LiteralSet,
    types: tuple[astx.DataType, ...],
    diagnostics: DiagnosticBag,
) -> LiteralStorage | None:
    """
    title: Select safe homogeneous storage without changing logical members.
    summary: >-
      Integers use lossless domain promotion. Floating storage starts at the
      widest declared floating member; narrow storage is allowed only when
      every other domain is lossless or its literal is exactly representable.
      Nonliteral numeric expressions retain their complete domain guarantees.
      Unsupported mixtures produce a semantic diagnostic before lowering.
    parameters:
      node:
        type: astx.LiteralList | astx.LiteralSet
      types:
        type: tuple[astx.DataType, Ellipsis]
      diagnostics:
        type: DiagnosticBag
    returns:
      type: LiteralStorage | None
    """
    if len(types) != len(node.elements):
        return None
    if not types:
        return LiteralStorage(astx.Int32(), ())
    storage: astx.DataType | None = types[0]
    floating = [type_ for type_ in types if type(type_) in FLOAT_PRECISIONS]
    if floating:
        minimum = max(FLOAT_PRECISIONS[type(type_)] for type_ in floating)
        for candidate_type, precision in FLOAT_PRECISIONS.items():
            if precision < minimum:
                continue
            candidate = candidate_type()
            if all(
                (plan := classify_numeric_conversion(type_, candidate))
                is not None
                and (plan.implicit or constant_fits_float(element, candidate))
                for element, type_ in zip(node.elements, types)
            ):
                storage = candidate
                break
        else:
            storage = None
    else:
        for type_ in types[1:]:
            if storage is None:
                break
            if same_type(storage, type_):
                continue
            if is_string_type(storage) and is_string_type(type_):
                storage = astx.UTF8String()
                continue
            storage = common_numeric_type(storage, type_)
            if storage is None:
                break
    if storage is None:
        diagnostics.add(
            "literal elements have no safe common storage type",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return None
    conversions: list[NumericConversion | None] = []
    for type_ in types:
        conversion = classify_numeric_conversion(type_, storage)
        if conversion is not None and not conversion.implicit:
            conversion = replace(
                conversion, implicit=True, requires_range_check=False
            )
        conversions.append(conversion)
    return LiteralStorage(storage, tuple(conversions))


@public
@typechecked
@dataclass(frozen=True)
class DictionaryLookup(SemanticFact):
    """
    title: Resolved numeric dictionary comparison and operand conversions.
    attributes:
      comparison_type:
        type: astx.DataType
      key_conversion:
        type: ImplicitConversion
      index_conversion:
        type: ImplicitConversion
    """

    comparison_type: astx.DataType
    key_conversion: ImplicitConversion
    index_conversion: ImplicitConversion

    def __post_init__(self) -> None:
        """
        title: Validate all generated fields and nested conversion plans.
        """
        self.validate()

    def validate(self) -> None:
        """
        title: Check nominal domains and complete conversion payloads.
        """
        validate_dictionary_lookup(
            self.comparison_type, self.key_conversion, self.index_conversion
        )

    def dependencies(self) -> tuple[astx.AST, ...]:
        """
        title: Expose no AST dependencies for this comparison-only record.
        returns:
          type: tuple[astx.AST, Ellipsis]
        """
        return ()


DICTIONARY_LOOKUP = FactKey("irx.literals", DictionaryLookup)


@private
@typechecked
def validate_dictionary_lookup(
    comparison_type: astx.DataType,
    key_conversion: ImplicitConversion,
    index_conversion: ImplicitConversion,
) -> None:
    """
    title: Require lossless numeric operands targeting one comparison domain.
    parameters:
      comparison_type:
        type: astx.DataType
      key_conversion:
        type: ImplicitConversion
      index_conversion:
        type: ImplicitConversion
    """
    for conversion in (key_conversion, index_conversion):
        numeric = conversion.numeric
        if conversion.source_type is None or numeric is None:
            raise ValueError("dictionary comparison requires numeric operands")
        if not same_type(conversion.target_type, comparison_type):
            raise ValueError("dictionary comparison targets must match")
        validate_literal_storage(comparison_type, (numeric,))


@private
@typechecked
def resolve_dictionary_lookup(
    node: astx.SubscriptExpr,
    key_types: tuple[astx.DataType, ...],
    index_type: astx.DataType | None,
    diagnostics: DiagnosticBag,
) -> DictionaryLookup | None:
    """
    title: Resolve existing same-category dictionary lookup before LLVM.
    parameters:
      node:
        type: astx.SubscriptExpr
      key_types:
        type: tuple[astx.DataType, Ellipsis]
      index_type:
        type: astx.DataType | None
      diagnostics:
        type: DiagnosticBag
    returns:
      type: DictionaryLookup | None
    """
    if not key_types or index_type is None:
        return None
    key_type = key_types[0]
    if not all(same_type(type_, key_type) for type_ in key_types):
        diagnostics.add(
            "dictionary literal requires homogeneous key storage",
            node=node.value,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return None
    integer_keys = type(key_type) not in FLOAT_PRECISIONS
    integer_index = type(index_type) not in FLOAT_PRECISIONS
    comparison = (
        common_numeric_type(key_type, index_type)
        if integer_keys == integer_index
        else None
    )
    if comparison is None:
        diagnostics.add(
            "SubscriptExpr: index type is incompatible with dict key type; "
            "a lossless common comparison domain is required",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return None
    return DictionaryLookup(
        comparison,
        ImplicitConversion(key_type, comparison),
        ImplicitConversion(index_type, comparison),
    )
