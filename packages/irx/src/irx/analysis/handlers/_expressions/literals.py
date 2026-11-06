# mypy: disable-error-code=no-redef

"""
title: Expression literal visitors.
summary: >-
  Handle literal expressions, list operations, and generic subscript
  expressions during semantic analysis.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import replace
from datetime import date, datetime, time
from typing import Iterator, cast

import astx

from plum import dispatch
from public import private

from irx.analysis.arrow_conversion import contains_arrow
from irx.analysis.class_lifecycle import contains_class
from irx.analysis.collections import (
    collection_contains_types,
    collection_supports_sequence_search,
    is_collection_type,
)
from irx.analysis.dependencies.expression_literal import (
    ExpressionLiteralAnalysisServices,
)
from irx.analysis.extensions.literals import (
    DICTIONARY_LOOKUP,
    LITERAL_STORAGE,
    resolve_dictionary_lookup,
    resolve_literal_storage,
)
from irx.analysis.iterables import resolve_iteration_capability
from irx.analysis.normalization import normalize_flags, normalize_operator
from irx.analysis.numeric_literals import (
    contextualize_literal,
    resolve_numeric_literal,
)
from irx.analysis.numeric_policy import integer_bounds
from irx.analysis.ownership import (
    list_resource_ownership,
    string_resource_ownership,
    symbol_resource_ownership,
)
from irx.analysis.resolved_nodes import (
    CollectionMethodKind,
    OwnershipKind,
    ResolvedCollectionMethod,
    ResolvedGeneratorFunction,
    TextOperationKind,
)
from irx.analysis.sequences import resolve_sequence_access
from irx.analysis.types import (
    common_numeric_type,
    display_type_name,
    is_assignable,
    is_boolean_type,
    is_integer_type,
    is_numeric_type,
    is_string_type,
    same_type,
)
from irx.analysis.validation import (
    validate_assignment,
    validate_literal_datetime,
    validate_literal_time,
    validate_literal_timestamp,
)
from irx.builtins.collections.list import (
    list_element_type,
    list_has_concrete_element_type,
    list_supports_owned_element,
)
from irx.diagnostics import DiagnosticCodes
from irx.extensions.handlers import configuration_error
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
def collection_probe_matches(
    expected: astx.DataType, actual: astx.DataType | None
) -> bool:
    """
    title: Numeric searches use comparison domains, not assignment domains.
    parameters:
      expected:
        type: astx.DataType
      actual:
        type: astx.DataType | None
    returns:
      type: bool
    """
    if is_numeric_type(expected) and is_numeric_type(actual):
        return common_numeric_type(expected, actual) is not None
    return is_assignable(expected, actual)


@private
@typechecked
class ExpressionLiteralAnalysis:
    """
    title: Expression visitors for literals, list operations, and subscripts
    attributes:
      services:
        type: ExpressionLiteralAnalysisServices
    """

    services: ExpressionLiteralAnalysisServices

    def __init__(self, services: ExpressionLiteralAnalysisServices) -> None:
        """
        title: Bind one feature to explicit compilation-owned dependencies.
        parameters:
          services:
            type: ExpressionLiteralAnalysisServices
        """
        self.services = services

    @dispatch
    def visit(self, node: astx.AST) -> None:
        """
        title: Reject an input outside this feature's explicit support.
        parameters:
          node:
            type: astx.AST
        """
        raise configuration_error(
            f"unsupported {type(node).__name__} in ExpressionLiteralAnalysis"
        )

    @dispatch
    def visit(
        self,
        node: astx.LiteralInteger
        | astx.LiteralFloat
        | astx.LiteralInt8
        | astx.LiteralInt16
        | astx.LiteralInt32
        | astx.LiteralInt64
        | astx.LiteralInt128
        | astx.LiteralUInt8
        | astx.LiteralUInt16
        | astx.LiteralUInt32
        | astx.LiteralUInt64
        | astx.LiteralUInt128
        | astx.LiteralFloat16
        | astx.LiteralFloat32
        | astx.LiteralFloat64
        | astx.LiteralBoolean
        | astx.LiteralNone,
    ) -> None:
        """
        title: Resolve supported scalar literals, including nominal subtypes.
        summary: >-
          Plain type annotations do not grant expression support. Contextual
          widths and unsupported numeric representations retain their existing
          semantic validation; specialized literals use their own handlers.
        parameters:
          node:
            type: >-
              astx.LiteralInteger | astx.LiteralFloat | astx.LiteralInt8 |
              astx.LiteralInt16 | astx.LiteralInt32 | astx.LiteralInt64 |
              astx.LiteralInt128 | astx.LiteralUInt8 | astx.LiteralUInt16 |
              astx.LiteralUInt32 | astx.LiteralUInt64 | astx.LiteralUInt128 |
              astx.LiteralFloat16 | astx.LiteralFloat32 | astx.LiteralFloat64 |
              astx.LiteralBoolean | astx.LiteralNone
        """
        literal_type = resolve_numeric_literal(
            node, self.services.context.diagnostics
        )
        self.services.set_type(node, literal_type or node.type_)

    def _validate_comprehension_condition(
        self,
        condition: astx.AST,
    ) -> None:
        """
        title: Validate one comprehension filter expression.
        parameters:
          condition:
            type: astx.AST
        """
        if not self.services.require_value_expression(
            condition,
            context="comprehension filter",
        ):
            return
        condition_type = self.services.expr_type(condition)
        if condition_type is None or is_boolean_type(condition_type):
            return
        self.services.context.diagnostics.add(
            "comprehension filter must be Boolean, got "
            f"{display_type_name(condition_type)}",
            node=condition,
            code=DiagnosticCodes.SEMANTIC_INVALID_CONDITION,
        )

    @dispatch
    def visit(self, node: astx.LiteralString) -> None:
        """
        title: Visit string literal nodes as immortal static storage.
        parameters:
          node:
            type: astx.LiteralString
        """
        if "\0" in node.value:
            self.services.free_text_error(
                node,
                "text literals cannot contain NUL; use binary data instead",
            )
        try:
            node.value.encode("utf-8")
        except UnicodeEncodeError:
            self.services.free_text_error(
                node,
                "text literals require valid Unicode scalar values",
            )
        self.services.set_type(node, node.type_)
        self.services.set_resource_ownership(
            node,
            string_resource_ownership(OwnershipKind.STATIC),
        )

    def _visit_comprehension_clause(
        self,
        clause: astx.ComprehensionClause,
        borrows: ExitStack,
    ) -> None:
        """
        title: Visit one comprehension clause in the active scope.
        parameters:
          clause:
            type: astx.ComprehensionClause
          borrows:
            type: ExitStack
        """
        if clause.is_async:
            self.services.context.diagnostics.add(
                "async comprehensions are not supported",
                node=clause,
                code=DiagnosticCodes.SEMANTIC_INVALID_CONTROL_FLOW,
            )

        self.services.visit(clause.iterable)
        iterable_type = self.services.expr_type(clause.iterable)
        iteration = resolve_iteration_capability(
            clause.iterable,
            iterable_type,
        )
        if iteration is None:
            self.services.context.diagnostics.add(
                "comprehension requires an iterable value, got "
                f"{display_type_name(iterable_type)}",
                node=clause.iterable,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            self.services.set_iteration(clause, None)
            self.services.set_type(clause, None)
            return

        symbol = self.services.declare_iteration_target(
            clause.target,
            iteration.element_type,
            kind="comprehension",
            iteration_kind=iteration.kind,
        )
        resolved_iteration = replace(iteration, target_symbol=symbol)
        self.services.set_iteration(clause.iterable, resolved_iteration)
        self.services.set_iteration(clause, resolved_iteration)
        self.services.set_type(clause, iteration.element_type)

        borrows.enter_context(
            self.services.context.list_iteration(
                iteration.borrowed_owner_symbol_id
            )
        )
        for condition in clause.conditions.nodes:
            self.services.visit(condition)
            self._validate_comprehension_condition(condition)

    @contextmanager
    @typechecked
    def _visit_comprehension_clauses(
        self,
        clauses: list[astx.ComprehensionClause],
    ) -> Iterator[None]:
        """
        title: Borrow iterable owners through dependent clauses and results.
        parameters:
          clauses:
            type: list[astx.ComprehensionClause]
        returns:
          type: Iterator[None]
        """
        with ExitStack() as borrows:
            for clause in clauses:
                self._visit_comprehension_clause(clause, borrows)
            yield

    @dispatch
    def visit(self, node: astx.AliasExpr) -> None:
        """
        title: Visit AliasExpr nodes.
        parameters:
          node:
            type: astx.AliasExpr
        """
        self.services.set_type(node, None)

    def _visit_temporal_literal(self, node: astx.AST) -> None:
        """
        title: Visit one temporal literal.
        parameters:
          node:
            type: astx.AST
        """
        try:
            literal_value = cast(str, getattr(node, "value"))
            parsed_value: object
            if isinstance(node, astx.LiteralDate):
                if (
                    len(literal_value) != len("YYYY-MM-DD")
                    or literal_value[4::3] != "--"
                ):
                    raise ValueError("date literals require YYYY-MM-DD")
                parsed_value = date.fromisoformat(literal_value)
            elif isinstance(node, astx.LiteralTime):
                parsed_value = validate_literal_time(literal_value)
            elif isinstance(node, astx.LiteralTimestamp):
                parsed_value = validate_literal_timestamp(literal_value)
            else:
                parsed_value = validate_literal_datetime(literal_value)
            self.services.semantic(node).extras["parsed_value"] = parsed_value
            # Resolve Arrow's epoch representation here, not in lowering.
            if isinstance(parsed_value, datetime):
                delta = parsed_value - datetime(1970, 1, 1)
                physical = (delta.days * 86400 + delta.seconds) * 1000000
                physical += delta.microseconds
            elif isinstance(parsed_value, time):
                physical = (
                    parsed_value.hour * 3600
                    + parsed_value.minute * 60
                    + parsed_value.second
                ) * 1000000 + parsed_value.microsecond
            else:
                assert isinstance(parsed_value, date)
                physical = (parsed_value - date(1970, 1, 1)).days
            self.services.semantic(node).extras["dataframe_temporal_value"] = (
                physical
            )
        except ValueError as exc:
            self.services.context.diagnostics.add(str(exc), node=node)
        self.services.set_type(node, getattr(node, "type_", None))

    @dispatch
    def visit(self, node: astx.LiteralDate) -> None:
        """
        title: Validate calendar dates and resolve their epoch representation.
        parameters:
          node:
            type: astx.LiteralDate
        """
        self._visit_temporal_literal(node)

    @dispatch
    def visit(self, node: astx.LiteralTime) -> None:
        """
        title: Visit LiteralTime nodes.
        parameters:
          node:
            type: astx.LiteralTime
        """
        self._visit_temporal_literal(node)

    @dispatch
    def visit(self, node: astx.LiteralTimestamp) -> None:
        """
        title: Visit LiteralTimestamp nodes.
        parameters:
          node:
            type: astx.LiteralTimestamp
        """
        self._visit_temporal_literal(node)

    @dispatch
    def visit(self, node: astx.LiteralDateTime) -> None:
        """
        title: Visit LiteralDateTime nodes.
        parameters:
          node:
            type: astx.LiteralDateTime
        """
        self._visit_temporal_literal(node)

    def reject_class_element(self, node: astx.AST) -> None:
        """
        title: Reject class references in aggregate storage without ownership.
        parameters:
          node:
            type: astx.AST
        """
        if contains_class(self.services.expr_type(node)) or contains_arrow(
            self.services.expr_type(node)
        ):
            self.services.context.diagnostics.add(
                (
                    "class"
                    if contains_class(self.services.expr_type(node))
                    else "Arrow"
                )
                + " references inside containers/generators are unsupported",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )

    def _visit_element_sequence_literal(self, node: astx.AST) -> None:
        """
        title: Visit one element-sequence literal.
        parameters:
          node:
            type: astx.AST
        """
        for element in cast(list[astx.AST], getattr(node, "elements")):
            self.services.visit(element)
            self.reject_class_element(element)
        elements = cast(list[astx.AST], getattr(node, "elements"))
        types = [self.services.expr_type(element) for element in elements]
        concrete: list[astx.ExprType] = [
            type_ for type_ in types if type_ is not None
        ]
        if isinstance(node, astx.LiteralTuple):
            self.services.set_type(node, astx.TupleType(concrete))
        elif isinstance(node, astx.LiteralList):
            unique: list[astx.ExprType] = []
            for member in concrete:
                if not any(
                    same_type(
                        cast(astx.DataType, member),
                        cast(astx.DataType, previous),
                    )
                    for previous in unique
                ):
                    unique.append(member)
            self.services.set_type(
                node, astx.ListType(unique, size=len(elements))
            )
            storage = resolve_literal_storage(
                node,
                tuple(type_ for type_ in types if type_ is not None),
                self.services.context.diagnostics,
            )
            if storage is not None:
                info = self.services.semantic(node)
                info.facts = info.facts.with_fact(
                    LITERAL_STORAGE, storage, replace=True
                )

    def _has_compatible_collection_probe(
        self,
        expected_types: tuple[astx.DataType, ...],
        actual_type: astx.DataType | None,
    ) -> bool:
        """
        title: Return whether one collection probe type is compatible.
        parameters:
          expected_types:
            type: tuple[astx.DataType, Ellipsis]
          actual_type:
            type: astx.DataType | None
        returns:
          type: bool
        """
        if actual_type is None or not expected_types:
            return True
        return any(
            collection_probe_matches(expected_type, actual_type)
            for expected_type in expected_types
        )

    def _set_resolved_collection_method(
        self,
        node: astx.AST,
        *,
        base: astx.AST,
        method: CollectionMethodKind,
        return_type: astx.DataType,
        argument_types: tuple[astx.DataType, ...] = (),
    ) -> None:
        """
        title: Attach resolved collection method metadata.
        parameters:
          node:
            type: astx.AST
          base:
            type: astx.AST
          method:
            type: CollectionMethodKind
          return_type:
            type: astx.DataType
          argument_types:
            type: tuple[astx.DataType, Ellipsis]
        """
        receiver_type = self.services.expr_type(base)
        if receiver_type is None:
            self.services.set_collection_method(node, None)
            return
        probe = getattr(node, "value", None)
        probe_type = (
            self.services.expr_type(probe)
            if isinstance(probe, astx.AST)
            else None
        )
        entry_types = argument_types
        if isinstance(
            base,
            (
                astx.LiteralList,
                astx.LiteralTuple,
                astx.LiteralSet,
                astx.LiteralDict,
            ),
        ):
            entry_types = tuple(
                type_
                for entry in base.elements
                if (type_ := self.services.expr_type(entry)) is not None
            )
        if is_numeric_type(probe_type) and any(
            is_numeric_type(type_)
            and common_numeric_type(type_, probe_type) is None
            for type_ in entry_types
        ):
            self.services.context.diagnostics.add(
                "collection comparison has no lossless common numeric type; "
                "use an explicit cast",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        matching = tuple(
            type_
            for type_ in entry_types
            if collection_probe_matches(type_, probe_type)
        )
        comparisons = tuple(
            normalize_operator(
                "==",
                result_type=astx.Boolean(),
                lhs_type=type_,
                rhs_type=probe_type,
                flags=normalize_flags(
                    node, lhs_type=type_, rhs_type=probe_type
                ),
            )
            for type_ in matching
        )
        self.services.set_collection_method(
            node,
            ResolvedCollectionMethod(
                receiver_node=base,
                receiver_type=receiver_type,
                method=method,
                return_type=return_type,
                argument_types=argument_types,
                comparison_plans=comparisons,
                matching_types=matching,
            ),
        )

    def _validate_collection_query_base(
        self,
        node: astx.AST,
        base: astx.AST,
        *,
        context: str,
        analyzed: bool = False,
    ) -> astx.DataType | None:
        """
        title: Validate one collection query receiver.
        parameters:
          node:
            type: astx.AST
          base:
            type: astx.AST
          context:
            type: str
          analyzed:
            type: bool
        returns:
          type: astx.DataType | None
        """
        if not analyzed:
            self.services.visit(base)
        if not self.services.require_value_expression(base, context=context):
            return None
        base_type = self.services.expr_type(base)
        if is_collection_type(base_type):
            return base_type
        self.services.context.diagnostics.add(
            f"{context} requires a collection value, got "
            f"{display_type_name(base_type)}",
            node=base,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return None

    def _collection_method_supported_by_lowering(
        self,
        *,
        method: CollectionMethodKind,
        base: astx.AST,
        base_type: astx.DataType | None,
    ) -> bool:
        """
        title: Return whether the backend can lower a collection method.
        parameters:
          method:
            type: CollectionMethodKind
          base:
            type: astx.AST
          base_type:
            type: astx.DataType | None
        returns:
          type: bool
        """
        if base_type is None:
            return True
        if isinstance(base_type, astx.ListType):
            return True
        if isinstance(base_type, astx.TupleType):
            if method in (
                CollectionMethodKind.LENGTH,
                CollectionMethodKind.IS_EMPTY,
            ):
                return True
            return isinstance(base, astx.LiteralTuple)
        if isinstance(base_type, astx.SetType):
            return isinstance(base, astx.LiteralSet) and method in (
                CollectionMethodKind.LENGTH,
                CollectionMethodKind.IS_EMPTY,
                CollectionMethodKind.CONTAINS,
            )
        if isinstance(base_type, astx.DictType):
            return isinstance(base, astx.LiteralDict) and method in (
                CollectionMethodKind.LENGTH,
                CollectionMethodKind.IS_EMPTY,
                CollectionMethodKind.CONTAINS,
            )
        return False

    def _validate_collection_lowering_support(
        self,
        *,
        node: astx.AST,
        base: astx.AST,
        base_type: astx.DataType | None,
        method: CollectionMethodKind,
        context: str,
    ) -> bool:
        """
        title: Validate that one collection method is currently lowerable.
        parameters:
          node:
            type: astx.AST
          base:
            type: astx.AST
          base_type:
            type: astx.DataType | None
          method:
            type: CollectionMethodKind
          context:
            type: str
        returns:
          type: bool
        """
        if self._collection_method_supported_by_lowering(
            method=method,
            base=base,
            base_type=base_type,
        ):
            return True

        self.services.context.diagnostics.add(
            f"{context} currently supports literal collections, "
            "dynamic lists, and tuple length/emptiness only",
            node=base,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return False

    @dispatch
    def visit(self, node: astx.CollectionLength) -> None:
        """
        title: Visit CollectionLength nodes.
        parameters:
          node:
            type: astx.CollectionLength
        """
        info = self.services.semantic(node)
        info.resolved_text_operation = None
        info.resolved_collection_method = None
        info.sequence_access = None
        self.services.visit(node.base)
        if is_string_type(self.services.expr_type(node.base)):
            self.services.free_set_text_operation(
                node,
                TextOperationKind.LENGTH,
                (node.base,),
                (0,),
            )
            return
        if isinstance(
            self.services.expr_type(node.base),
            (astx.SequenceType, astx.TensorType, astx.SeriesType, astx.Bytes),
        ):
            info.sequence_access = resolve_sequence_access(
                self.services.expr_type(node.base)
            )
            if info.sequence_access is None:
                self.services.context.diagnostics.add(
                    "len requires a numeric rank-one tensor or typed Series",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
            self.services.set_type(node, astx.Int64())
            return
        return_type = astx.Int64()
        base_type = self._validate_collection_query_base(
            node,
            node.base,
            context="collection length",
            analyzed=True,
        )
        supported = self._validate_collection_lowering_support(
            node=node,
            base=node.base,
            base_type=base_type,
            method=CollectionMethodKind.LENGTH,
            context="collection length",
        )
        if base_type is not None and supported:
            self._set_resolved_collection_method(
                node,
                base=node.base,
                method=CollectionMethodKind.LENGTH,
                return_type=return_type,
            )
        self.services.set_type(node, return_type)

    @dispatch
    def visit(self, node: astx.CollectionIsEmpty) -> None:
        """
        title: Visit CollectionIsEmpty nodes.
        parameters:
          node:
            type: astx.CollectionIsEmpty
        """
        return_type = astx.Boolean()
        base_type = self._validate_collection_query_base(
            node,
            node.base,
            context="collection emptiness",
        )
        supported = self._validate_collection_lowering_support(
            node=node,
            base=node.base,
            base_type=base_type,
            method=CollectionMethodKind.IS_EMPTY,
            context="collection emptiness",
        )
        if base_type is not None and supported:
            self._set_resolved_collection_method(
                node,
                base=node.base,
                method=CollectionMethodKind.IS_EMPTY,
                return_type=return_type,
            )
        self.services.set_type(node, return_type)

    @dispatch
    def visit(self, node: astx.CollectionContains) -> None:
        """
        title: Visit CollectionContains nodes.
        parameters:
          node:
            type: astx.CollectionContains
        """
        return_type = astx.Boolean()
        base_type = self._validate_collection_query_base(
            node,
            node.base,
            context="collection containment",
        )
        contexts = collection_contains_types(base_type)
        if len(contexts) == 1:
            contextualize_literal(node.value, contexts[0])
        self.services.visit(node.value)
        expected_types = collection_contains_types(base_type)
        actual_type = self.services.expr_type(node.value)
        if not self._has_compatible_collection_probe(
            expected_types,
            actual_type,
        ):
            self.services.context.diagnostics.add(
                "collection containment probe expects "
                + " or ".join(
                    display_type_name(expected_type)
                    for expected_type in expected_types
                )
                + f", got {display_type_name(actual_type)}",
                node=node.value,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        supported = self._validate_collection_lowering_support(
            node=node,
            base=node.base,
            base_type=base_type,
            method=CollectionMethodKind.CONTAINS,
            context="collection containment",
        )
        if base_type is not None and supported:
            self._set_resolved_collection_method(
                node,
                base=node.base,
                method=CollectionMethodKind.CONTAINS,
                return_type=return_type,
                argument_types=expected_types,
            )
        self.services.set_type(node, return_type)

    @dispatch
    def visit(self, node: astx.CollectionIndex) -> None:
        """
        title: Visit CollectionIndex nodes.
        parameters:
          node:
            type: astx.CollectionIndex
        """
        return_type = astx.Int32()
        base_type = self._validate_collection_query_base(
            node,
            node.base,
            context="collection index",
        )
        contexts = collection_contains_types(base_type)
        if len(contexts) == 1:
            contextualize_literal(node.value, contexts[0])
        self.services.visit(node.value)
        expected_types = collection_contains_types(base_type)
        if base_type is not None and not collection_supports_sequence_search(
            base_type
        ):
            self.services.context.diagnostics.add(
                "collection index requires a list or tuple value",
                node=node.base,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        elif not self._has_compatible_collection_probe(
            expected_types,
            self.services.expr_type(node.value),
        ):
            self.services.context.diagnostics.add(
                "collection index probe expects "
                + " or ".join(
                    display_type_name(expected_type)
                    for expected_type in expected_types
                )
                + ", got "
                + display_type_name(self.services.expr_type(node.value)),
                node=node.value,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        supported = self._validate_collection_lowering_support(
            node=node,
            base=node.base,
            base_type=base_type,
            method=CollectionMethodKind.INDEX,
            context="collection index",
        )
        if (
            base_type is not None
            and collection_supports_sequence_search(base_type)
            and supported
        ):
            self._set_resolved_collection_method(
                node,
                base=node.base,
                method=CollectionMethodKind.INDEX,
                return_type=return_type,
                argument_types=expected_types,
            )
        self.services.set_type(node, return_type)

    @dispatch
    def visit(self, node: astx.CollectionCount) -> None:
        """
        title: Visit CollectionCount nodes.
        parameters:
          node:
            type: astx.CollectionCount
        """
        return_type = astx.Int32()
        base_type = self._validate_collection_query_base(
            node,
            node.base,
            context="collection count",
        )
        contexts = collection_contains_types(base_type)
        if len(contexts) == 1:
            contextualize_literal(node.value, contexts[0])
        self.services.visit(node.value)
        expected_types = collection_contains_types(base_type)
        if base_type is not None and not collection_supports_sequence_search(
            base_type
        ):
            self.services.context.diagnostics.add(
                "collection count requires a list or tuple value",
                node=node.base,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        elif not self._has_compatible_collection_probe(
            expected_types,
            self.services.expr_type(node.value),
        ):
            self.services.context.diagnostics.add(
                "collection count probe expects "
                + " or ".join(
                    display_type_name(expected_type)
                    for expected_type in expected_types
                )
                + ", got "
                + display_type_name(self.services.expr_type(node.value)),
                node=node.value,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        supported = self._validate_collection_lowering_support(
            node=node,
            base=node.base,
            base_type=base_type,
            method=CollectionMethodKind.COUNT,
            context="collection count",
        )
        if (
            base_type is not None
            and collection_supports_sequence_search(base_type)
            and supported
        ):
            self._set_resolved_collection_method(
                node,
                base=node.base,
                method=CollectionMethodKind.COUNT,
                return_type=return_type,
                argument_types=expected_types,
            )
        self.services.set_type(node, return_type)

    @dispatch
    def visit(self, node: astx.LiteralList) -> None:
        """
        title: Visit LiteralList nodes.
        parameters:
          node:
            type: astx.LiteralList
        """
        self._visit_element_sequence_literal(node)
        self.services.set_resource_ownership(
            node,
            list_resource_ownership(OwnershipKind.STATIC),
        )

    @dispatch
    def visit(self, node: astx.LiteralTuple) -> None:
        """
        title: Visit LiteralTuple nodes.
        parameters:
          node:
            type: astx.LiteralTuple
        """
        self._visit_element_sequence_literal(node)

    @dispatch
    def visit(self, node: astx.LiteralSet) -> None:
        """
        title: Visit LiteralSet nodes.
        parameters:
          node:
            type: astx.LiteralSet
        """
        for element in node.elements:
            self.services.visit(element)
            self.reject_class_element(element)
        if node.elements and not all(
            isinstance(element, astx.Literal)
            and (type_ := self.services.expr_type(element)) is not None
            and integer_bounds(type_) is not None
            for element in node.elements
        ):
            self.services.context.diagnostics.add(
                "LiteralSet: only integer constants are "
                "currently supported for lowering",
                node=node,
            )
        self.services.set_type(node, astx.LiteralSet(node.elements).type_)
        storage = resolve_literal_storage(
            node,
            tuple(
                type_
                for element in node.elements
                if (type_ := self.services.expr_type(element)) is not None
            ),
            self.services.context.diagnostics,
        )
        if storage is not None:
            info = self.services.semantic(node)
            info.facts = info.facts.with_fact(
                LITERAL_STORAGE, storage, replace=True
            )

    @dispatch
    def visit(self, node: astx.LiteralDict) -> None:
        """
        title: Visit LiteralDict nodes.
        parameters:
          node:
            type: astx.LiteralDict
        """
        for key, value in node.elements.items():
            self.services.visit(key)
            self.services.visit(value)
            self.reject_class_element(key)
            self.reject_class_element(value)
        self.services.set_type(node, astx.LiteralDict(node.elements).type_)

    @dispatch
    def visit(self, node: astx.ListCreate) -> None:
        """
        title: Visit ListCreate nodes.
        parameters:
          node:
            type: astx.ListCreate
        """
        self.services.set_type(node, node.type_)
        if contains_class(node.element_type) or contains_arrow(
            node.element_type
        ):
            self.reject_class_element(node)
        if isinstance(node.element_type, astx.ListType):
            self.services.context.diagnostics.add(
                "dynamic lists cannot own dynamic-list elements because "
                "nested ownership and destruction are not supported",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        if not list_supports_owned_element(node.element_type):
            self.services.context.diagnostics.add(
                "owned lists support numeric, Boolean, and string "
                "elements only",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        self.services.set_resource_ownership(
            node,
            list_resource_ownership(OwnershipKind.OWNED),
        )

    @dispatch
    def visit(self, node: astx.ComprehensionClause) -> None:
        """
        title: Visit ComprehensionClause nodes.
        parameters:
          node:
            type: astx.ComprehensionClause
        """
        with (
            self.services.context.scope("comprehension-clause"),
            ExitStack() as borrows,
        ):
            self._visit_comprehension_clause(node, borrows)

    @dispatch
    def visit(self, node: astx.ListComprehension) -> None:
        """
        title: Visit ListComprehension nodes.
        parameters:
          node:
            type: astx.ListComprehension
        """
        with (
            self.services.context.scope("list-comprehension"),
            self._visit_comprehension_clauses(list(node.generators.nodes)),
        ):
            self.services.visit(node.element)
            self.reject_class_element(node.element)
            element_type = self.services.expr_type(node.element)
        if element_type is None:
            self.services.set_type(node, None)
            return
        self.services.set_type(node, astx.ListType([element_type]))
        if isinstance(element_type, astx.ListType):
            self.services.context.diagnostics.add(
                "list comprehensions cannot produce owning list elements "
                "because nested ownership and destruction are not supported",
                node=node.element,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        if not list_supports_owned_element(element_type):
            self.services.context.diagnostics.add(
                "owned lists support numeric, Boolean, and string "
                "elements only",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        self.services.set_resource_ownership(
            node,
            list_resource_ownership(OwnershipKind.OWNED),
        )

    @dispatch
    def visit(self, node: astx.GeneratorExpr) -> None:
        """
        title: Visit GeneratorExpr nodes.
        parameters:
          node:
            type: astx.GeneratorExpr
        """
        with (
            self.services.context.scope("generator-expression"),
            self._visit_comprehension_clauses(list(node.generators.nodes)),
        ):
            self.services.visit(node.element)
            self.reject_class_element(node.element)
            element_type = self.services.expr_type(node.element)
        if element_type is None:
            self.services.set_type(node, None)
            return
        self.services.set_type(node, astx.GeneratorType(element_type))

    @dispatch
    def visit(self, node: astx.SetComprehension) -> None:
        """
        title: Visit SetComprehension nodes.
        parameters:
          node:
            type: astx.SetComprehension
        """
        with (
            self.services.context.scope("set-comprehension"),
            self._visit_comprehension_clauses(list(node.generators.nodes)),
        ):
            self.services.visit(node.element)
            self.reject_class_element(node.element)
            element_type = self.services.expr_type(node.element)
        if element_type is None:
            self.services.set_type(node, None)
            return
        self.services.set_type(node, astx.SetType(element_type))

    @dispatch
    def visit(self, node: astx.DictComprehension) -> None:
        """
        title: Visit DictComprehension nodes.
        parameters:
          node:
            type: astx.DictComprehension
        """
        with (
            self.services.context.scope("dict-comprehension"),
            self._visit_comprehension_clauses(list(node.generators.nodes)),
        ):
            self.services.visit(node.key)
            self.services.visit(node.value)
            self.reject_class_element(node.key)
            self.reject_class_element(node.value)
            key_type = self.services.expr_type(node.key)
            value_type = self.services.expr_type(node.value)
        if key_type is None or value_type is None:
            self.services.set_type(node, None)
            return
        self.services.set_type(node, astx.DictType(key_type, value_type))

    @private
    def resolve_list_read(
        self, node: astx.AST, element_type: astx.DataType | None
    ) -> None:
        """
        title: Resolve copied string results without borrowing list storage.
        parameters:
          node:
            type: astx.AST
          element_type:
            type: astx.DataType | None
        """
        self.services.set_type(node, element_type)
        self.services.semantic(node).resource_ownership = None
        if not is_string_type(element_type):
            return
        function = self.services.context.current_function
        if function is not None and isinstance(
            function.signature.metadata.get("generator"),
            ResolvedGeneratorFunction,
        ):
            self.services.context.diagnostics.add(
                "owned string list reads in generators require "
                "lifecycle cleanup",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
        self.services.set_resource_ownership(
            node, string_resource_ownership(OwnershipKind.OWNED)
        )

    @dispatch
    def visit(self, node: astx.ListIndex) -> None:
        """
        title: Visit ListIndex nodes.
        parameters:
          node:
            type: astx.ListIndex
        """
        self.services.visit(node.base)
        self.services.visit(node.index)

        value_type = self.services.expr_type(node.base)
        if not isinstance(value_type, astx.ListType):
            self.services.context.diagnostics.add(
                "list indexing requires a list value",
                node=node.base,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            self.services.set_type(node, None)
            return

        index_type = self.services.expr_type(node.index)
        if not is_integer_type(index_type):
            self.services.context.diagnostics.add(
                "list indexing requires an integer index",
                node=node.index,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        if not list_has_concrete_element_type(value_type):
            self.services.context.diagnostics.add(
                "list indexing requires a single concrete list element type",
                node=node.base,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        self.resolve_list_read(node, list_element_type(value_type))

    @dispatch
    def visit(self, node: astx.ListLength) -> None:
        """
        title: Visit ListLength nodes.
        parameters:
          node:
            type: astx.ListLength
        """
        self.services.visit(node.base)
        if not self.services.require_value_expression(
            node.base,
            context="list length",
        ):
            self.services.set_type(node, astx.Int64())
            return

        if not isinstance(self.services.expr_type(node.base), astx.ListType):
            self.services.context.diagnostics.add(
                "list length requires a list value",
                node=node.base,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        self.services.set_type(node, astx.Int64())

    @dispatch
    def visit(self, node: astx.ListAppend) -> None:
        """
        title: Visit ListAppend nodes.
        parameters:
          node:
            type: astx.ListAppend
        """
        self.services.visit(node.base)
        base_type = self.services.expr_type(node.base)
        contextualize_literal(
            node.value,
            list_element_type(base_type)
            if isinstance(base_type, astx.ListType)
            else None,
        )
        self.services.visit(node.value)
        self.reject_class_element(node.value)

        resolved_target = self.services.resolve_mutation_target(
            node.base,
            node=node,
            action="append to",
            invalid_message="list append target must be a variable or field",
        )
        if resolved_target is None:
            self.services.set_type(node, astx.Int32())
            return

        assignment_symbol, _target_name, target_type = resolved_target
        if not isinstance(target_type, astx.ListType):
            self.services.context.diagnostics.add(
                "list append requires a list target",
                node=node.base,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            self.services.set_assignment(node, assignment_symbol)
            self.services.set_type(node, astx.Int32())
            return

        element_type = list_element_type(target_type)
        if element_type is None:
            self.services.context.diagnostics.add(
                "list append requires a single concrete list element type",
                node=node.base,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            self.services.set_assignment(node, assignment_symbol)
            self.services.set_type(node, astx.Int32())
            return

        if isinstance(element_type, astx.ListType):
            self.services.context.diagnostics.add(
                "list append cannot transfer an owning list element because "
                "nested ownership and destruction are not supported",
                node=node.value,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )

        target_ownership = symbol_resource_ownership(assignment_symbol)
        if target_ownership is None:
            self.services.context.diagnostics.add(
                "list append target is missing ownership metadata",
                node=node.base,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
        elif target_ownership.kind is not OwnershipKind.OWNED:
            self.services.context.diagnostics.add(
                "list append requires locally owned dynamic storage; got "
                f"{target_ownership.kind.value} storage",
                node=node.base,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                notes=(
                    "borrowed parameters and static list literals cannot be "
                    "grown safely",
                ),
            )

        validate_assignment(
            self.services.context.diagnostics,
            target_name="list element",
            target_type=element_type,
            value_type=self.services.expr_type(node.value),
            node=node,
        )
        self.services.set_assignment(node, assignment_symbol)
        self.services.set_type(node, astx.Int32())

    @dispatch
    def visit(self, node: astx.SubscriptExpr) -> None:
        """
        title: Visit SubscriptExpr nodes.
        parameters:
          node:
            type: astx.SubscriptExpr
        """
        info = self.services.semantic(node)
        info.sequence_access = None
        info.tensor_index = None
        if info.resolved_text_operation is not None:
            info.resource_ownership = None
        info.resolved_text_operation = None
        self.services.visit(node.value)
        if isinstance(self.services.expr_type(node.value), astx.TensorType):
            if node.is_slice:
                self.services.context.diagnostics.add(
                    "tensor slicing requires an explicit view",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
                return
            access = astx.TensorIndex(node.value, [node.index])
            access.loc = node.loc
            self.services.visit(access)
            info.tensor_index = access
            self.services.set_type(node, self.services.expr_type(access))
            return
        if isinstance(
            self.services.expr_type(node.value),
            (astx.SequenceType, astx.Bytes),
        ):
            self.services.visit(node.index)
            info.sequence_access = resolve_sequence_access(
                self.services.expr_type(node.value)
            )
            if (
                node.is_slice
                or not is_integer_type(self.services.expr_type(node.index))
                or isinstance(
                    self.services.expr_type(node.index), astx.UInt128
                )
            ):
                self.services.context.diagnostics.add(
                    "sequence access requires one integer index; slicing is "
                    "unsupported",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
            if info.sequence_access is not None:
                self.services.set_type(node, info.sequence_access.element_type)
            return
        if is_string_type(self.services.expr_type(node.value)):
            self.services.free_resolve_text_subscript(node)
            return
        if not node.is_slice:
            self.services.visit(node.index)
        value_type = self.services.expr_type(node.value)
        if self.services.free_resolve_column_index(node):
            return
        if isinstance(value_type, astx.ListType):
            if node.is_slice:
                self.services.context.diagnostics.add(
                    "list slicing is not supported",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
                self.services.set_type(node, None)
                return
            index_type = self.services.expr_type(node.index)
            if not is_integer_type(index_type):
                self.services.context.diagnostics.add(
                    "list indexing requires an integer index",
                    node=node.index,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
            if not list_has_concrete_element_type(value_type):
                self.services.context.diagnostics.add(
                    "list indexing requires a single concrete list element "
                    "type",
                    node=node.value,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
            self.resolve_list_read(node, list_element_type(value_type))
            return
        if not isinstance(node.value, astx.LiteralDict):
            self.services.context.diagnostics.add(
                "subscript access is not supported for "
                f"{display_type_name(value_type)}",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            self.services.set_type(node, None)
            return
        if isinstance(node.value, astx.LiteralDict):
            if not node.value.elements:
                self.services.context.diagnostics.add(
                    "SubscriptExpr: key lookup on empty dict",
                    node=node,
                )
            elif not isinstance(
                node.index,
                (
                    astx.LiteralInt8,
                    astx.LiteralInt16,
                    astx.LiteralInt32,
                    astx.LiteralInteger,
                    astx.LiteralInt64,
                    astx.LiteralUInt8,
                    astx.LiteralUInt16,
                    astx.LiteralUInt32,
                    astx.LiteralUInt64,
                    astx.LiteralFloat32,
                    astx.LiteralFloat,
                    astx.LiteralFloat64,
                    astx.Identifier,
                ),
            ):
                self.services.context.diagnostics.add(
                    "SubscriptExpr: only integer and floating-point "
                    "dict keys are supported",
                    node=node,
                )
        lookup = resolve_dictionary_lookup(
            node,
            tuple(
                type_
                for key in node.value.elements
                if (type_ := self.services.expr_type(key)) is not None
            ),
            self.services.expr_type(node.index),
            self.services.context.diagnostics,
        )
        if lookup is not None:
            info = self.services.semantic(node)
            info.facts = info.facts.with_fact(
                DICTIONARY_LOOKUP, lookup, replace=True
            )
        self.services.set_type(
            node,
            cast(
                astx.DataType | None,
                getattr(value_type, "value_type", None),
            ),
        )

    def node_handlers(self) -> tuple[NodeHandler, ...]:
        """
        title: Export this feature's supported nominal node signatures.
        returns:
          type: tuple[NodeHandler, Ellipsis]
        """
        return tuple(
            contribute_node(
                "irx.analysis.expression_literal." + node_type.__name__,
                "irx.analysis.expression_literal",
                "analysis",
                node_type,
                self.visit,
                source=__name__ + ".ExpressionLiteralAnalysis.visit",
            )
            for node_type in (
                astx.LiteralInteger,
                astx.LiteralFloat,
                astx.LiteralInt8,
                astx.LiteralInt16,
                astx.LiteralInt32,
                astx.LiteralInt64,
                astx.LiteralInt128,
                astx.LiteralUInt8,
                astx.LiteralUInt16,
                astx.LiteralUInt32,
                astx.LiteralUInt64,
                astx.LiteralUInt128,
                astx.LiteralFloat16,
                astx.LiteralFloat32,
                astx.LiteralFloat64,
                astx.LiteralBoolean,
                astx.LiteralNone,
                astx.LiteralString,
                astx.AliasExpr,
                astx.LiteralDate,
                astx.LiteralTime,
                astx.LiteralTimestamp,
                astx.LiteralDateTime,
                astx.CollectionLength,
                astx.CollectionIsEmpty,
                astx.CollectionContains,
                astx.CollectionIndex,
                astx.CollectionCount,
                astx.LiteralList,
                astx.LiteralTuple,
                astx.LiteralSet,
                astx.LiteralDict,
                astx.ListCreate,
                astx.ComprehensionClause,
                astx.ListComprehension,
                astx.GeneratorExpr,
                astx.SetComprehension,
                astx.DictComprehension,
                astx.ListIndex,
                astx.ListLength,
                astx.ListAppend,
                astx.SubscriptExpr,
            )
        )
