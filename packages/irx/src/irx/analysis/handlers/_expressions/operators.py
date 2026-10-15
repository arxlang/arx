# mypy: disable-error-code=no-redef
# mypy: disable-error-code=attr-defined
# mypy: disable-error-code=untyped-decorator

"""
title: Expression operator visitors.
summary: >-
  Analyze unary, binary, cast, and print expressions plus their assignment-like
  operator behavior.
"""

from __future__ import annotations

from typing import cast

import astx

from astx.binary_op import (
    SPECIALIZED_BINARY_OP_EXTRA,
    specialize_binary_op,
)

from irx.analysis.handlers.base import (
    SemanticAnalyzerCore,
    SemanticVisitorMixinBase,
)
from irx.analysis.handlers.nullable import analyze_nullable_operator
from irx.analysis.normalization import normalize_flags, normalize_operator
from irx.analysis.nullability import PRIMITIVE_PAYLOADS, normalize_nullable
from irx.analysis.nullable_flow import nullable_branch_symbols
from irx.analysis.ownership import (
    resource_ownership,
    string_resource_ownership,
)
from irx.analysis.resolved_nodes import OwnershipKind
from irx.analysis.types import (
    display_type_name,
    is_boolean_type,
    is_float_type,
    is_integer_type,
    is_numeric_type,
    is_string_type,
    is_type_member,
)
from irx.analysis.typing import binary_result_type, unary_result_type
from irx.analysis.validation import validate_assignment, validate_cast
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked

COLUMNAR_OPERATOR_TYPES = (
    astx.TableType,
    astx.RecordBatchType,
    astx.ScalarType,
    astx.ArrayType,
    astx.ArrayBuilderType,
    astx.ChunkedArrayType,
    astx.DataFrameType,
    astx.SeriesType,
    astx.SchemaType,
    astx.FieldType,
    astx.TypeDescriptorType,
)


@typechecked
class ExpressionOperatorVisitorMixin(SemanticVisitorMixinBase):
    """
    title: Expression visitors for unary, binary, cast, and print operations
    """

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.UnaryOp) -> None:
        """
        title: Visit UnaryOp nodes.
        parameters:
          node:
            type: astx.UnaryOp
        """
        self.visit(node.operand)
        if not self._require_value_expression(
            node.operand,
            context=f"Unary operator '{node.op_code}'",
        ):
            self._set_type(node, None)
            return
        operand_type = self._expr_type(node.operand)
        if isinstance(operand_type, COLUMNAR_OPERATOR_TYPES):
            self.context.diagnostics.add(
                "columnar owners do not support scalar unary operators",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            self._set_type(node, None)
            return
        operand_symbol = self._semantic(node.operand).resolved_symbol
        if node.op_code in {"++", "--"} and operand_symbol is not None:
            if isinstance(
                normalize_nullable(operand_symbol.type_), astx.NullableType
            ):
                self.context.diagnostics.add(
                    "nullable increment/decrement is unsupported; use an "
                    "explicit assignment",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
                self._set_type(node, None)
                return
        if isinstance(operand_type, astx.NullableType):
            analyze_nullable_operator(cast(SemanticAnalyzerCore, self), node)
            return
        if (
            node.op_code == "!"
            and operand_type is not None
            and not is_boolean_type(operand_type)
        ):
            self.context.diagnostics.add(
                "unary operator '!' requires Boolean operand",
                node=node,
            )
        if node.op_code in {"+", "-"} and not is_numeric_type(operand_type):
            self.context.diagnostics.add(
                f"unary operator '{node.op_code}' requires a numeric operand",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            self._set_type(node, None)
            return
        result_type = unary_result_type(node.op_code, operand_type)
        if node.op_code in {"++", "--"}:
            resolved_target = self._resolve_mutation_target(
                node.operand,
                node=node,
                action="mutate",
                invalid_message=(
                    "mutation target must be a variable or field"
                ),
            )
            if resolved_target is not None:
                target_symbol, _target_name, _target_type = resolved_target
                self._set_assignment(node, target_symbol)
        flags = normalize_flags(node, lhs_type=operand_type)
        self._set_flags(node, flags)
        self._set_operator(
            node,
            normalize_operator(
                node.op_code,
                result_type=result_type,
                lhs_type=operand_type,
                flags=flags,
            ),
        )
        self._set_type(node, result_type)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.BinaryOp) -> None:
        """
        title: Visit BinaryOp nodes.
        parameters:
          node:
            type: astx.BinaryOp
        """
        self.visit(node.lhs)
        incoming_valid = self.context.valid_nullable_symbols.copy()
        if node.op_code in {"and", "&&", "or", "||"}:
            proof = nullable_branch_symbols(
                node.lhs, node.op_code in {"and", "&&"}
            )
            self.context.valid_nullable_symbols.update(proof)
        self.visit(node.rhs)
        self.context.valid_nullable_symbols.intersection_update(incoming_valid)
        lhs_type = self._expr_type(node.lhs)
        rhs_type = self._expr_type(node.rhs)
        flags = normalize_flags(node, lhs_type=lhs_type, rhs_type=rhs_type)
        self._set_flags(node, flags)
        specialized = specialize_binary_op(node)
        if specialized is not node:
            setattr(specialized, "semantic", self._semantic(node))
        self._semantic(node).extras[SPECIALIZED_BINARY_OP_EXTRA] = specialized

        if node.op_code == "=":
            resolved_target = self._resolve_mutation_target(
                node.lhs,
                node=node,
                action="assign to",
                invalid_message=(
                    "assignment target must be a variable or field"
                ),
            )
            if resolved_target is None:
                return
            assignment_symbol, target_name, target_type = resolved_target
            if self._require_value_expression(
                node.rhs,
                context=f"Assignment to '{target_name}'",
                allow_none=isinstance(
                    normalize_nullable(target_type), astx.NullableType
                ),
            ):
                validate_assignment(
                    self.context.diagnostics,
                    target_name=target_name,
                    target_type=target_type,
                    value_type=rhs_type,
                    node=node,
                )
            self._set_assignment(node, assignment_symbol)
            if isinstance(node.lhs, astx.Identifier):
                self._set_symbol(node.lhs, assignment_symbol)
            self._set_type(node, target_type)
            self._set_operator(
                node,
                normalize_operator(
                    node.op_code,
                    result_type=target_type,
                    lhs_type=target_type,
                    rhs_type=rhs_type,
                    flags=flags,
                ),
            )
            self._resolve_list_assignment_ownership(
                node,
                node.rhs,
                assignment_symbol,
                target_name=target_name,
                target_type=target_type,
                is_local=isinstance(node.lhs, astx.Identifier),
            )
            self._resolve_string_assignment_ownership(
                node,
                node.rhs,
                assignment_symbol,
                target_name=target_name,
                target_type=target_type,
                is_local=isinstance(node.lhs, astx.Identifier),
            )
            self._resolve_arrow_assignment_ownership(
                node,
                node.rhs,
                assignment_symbol,
                target_name=target_name,
                target_type=target_type,
                is_local=isinstance(node.lhs, astx.Identifier),
            )
            return

        if isinstance(lhs_type, COLUMNAR_OPERATOR_TYPES) or isinstance(
            rhs_type, COLUMNAR_OPERATOR_TYPES
        ):
            self.context.diagnostics.add(
                "columnar owners require typed operations, such as "
                "array_equal or descriptor_equal, not scalar operators",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            self._set_type(node, None)
            return
        if isinstance(lhs_type, astx.NullableType) or isinstance(
            rhs_type, astx.NullableType
        ):
            analyze_nullable_operator(cast(SemanticAnalyzerCore, self), node)
            return
        lhs_has_value = self._require_value_expression(
            node.lhs,
            context=f"Operator '{node.op_code}'",
        )
        rhs_has_value = self._require_value_expression(
            node.rhs,
            context=f"Operator '{node.op_code}'",
        )
        if not (lhs_has_value and rhs_has_value):
            self._set_type(node, None)
            self._set_operator(
                node,
                normalize_operator(
                    node.op_code,
                    result_type=None,
                    lhs_type=lhs_type,
                    rhs_type=rhs_type,
                    flags=flags,
                ),
            )
            return

        if flags.fma and flags.fma_rhs is None:
            self.context.diagnostics.add(
                "FMA requires a third operand (fma_rhs)",
                node=node,
            )
        if flags.fma and flags.fma_rhs is not None:
            self.visit(flags.fma_rhs)

        if (
            node.op_code in {"&&", "and", "||", "or"}
            and lhs_type is not None
            and rhs_type is not None
            and not (is_boolean_type(lhs_type) and is_boolean_type(rhs_type))
        ):
            self.context.diagnostics.add(
                f"logical operator '{node.op_code}' requires Boolean operands",
                node=node,
            )

        if node.op_code in {"+", "-", "*", "/", "%"} and not (
            (is_numeric_type(lhs_type) and is_numeric_type(rhs_type))
            or (
                node.op_code == "+"
                and is_string_type(lhs_type)
                and is_string_type(rhs_type)
            )
        ):
            self.context.diagnostics.add(
                f"Invalid operator '{node.op_code}' for operand types",
                node=node,
            )

        result_type = binary_result_type(node.op_code, lhs_type, rhs_type)
        self._set_type(node, result_type)
        self._set_operator(
            node,
            normalize_operator(
                node.op_code,
                result_type=result_type,
                lhs_type=lhs_type,
                rhs_type=rhs_type,
                flags=flags,
            ),
        )
        if node.op_code == "+" and is_string_type(result_type):
            self._set_resource_ownership(
                node,
                string_resource_ownership(OwnershipKind.OWNED),
            )

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.Cast) -> None:
        """
        title: Visit Cast nodes.
        parameters:
          node:
            type: astx.Cast
        """
        target_type = normalize_nullable(node.target_type)
        self.visit(node.value)
        if not self._require_value_expression(
            node.value,
            context="Cast",
            allow_none=isinstance(target_type, astx.NullableType),
        ):
            self._set_type(node, cast(astx.DataType | None, node.target_type))
            return
        source_type = self._expr_type(node.value)
        if isinstance(source_type, astx.NullableType) or isinstance(
            target_type, astx.NullableType
        ):
            self.resolve_nullable_cast(node, source_type, target_type)
            return
        validate_cast(
            self.context.diagnostics,
            source_type=source_type,
            target_type=target_type,
            node=node,
        )
        self._set_type(node, target_type)
        if not is_string_type(target_type):
            return
        source_ownership = resource_ownership(node.value)
        if is_string_type(source_type):
            if source_ownership is None:
                self.context.diagnostics.add(
                    "string cast source is missing ownership metadata",
                    node=node.value,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                )
                return
            if source_ownership.kind is OwnershipKind.OWNED:
                self.context.diagnostics.add(
                    "identity casts of owned strings are not supported; "
                    "remove the redundant cast to preserve the owner",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                )
            self._set_resource_ownership(node, source_ownership)
            return
        self._set_resource_ownership(
            node,
            string_resource_ownership(OwnershipKind.OWNED),
        )

    def resolve_nullable_cast(
        self,
        node: astx.Cast,
        source: astx.DataType | None,
        target: astx.DataType | None,
    ) -> None:
        """
        title: Cast primitive payloads without implicitly discarding validity.
        parameters:
          node:
            type: astx.Cast
          source:
            type: astx.DataType | None
          target:
            type: astx.DataType | None
        """
        payload = (
            source.payload_type
            if isinstance(source, astx.NullableType)
            else source
        )
        if (
            not isinstance(target, astx.NullableType)
            or type(target.payload_type) not in PRIMITIVE_PAYLOADS
            or (
                type(payload) not in PRIMITIVE_PAYLOADS
                and not isinstance(source, astx.NoneType)
            )
        ):
            self.context.diagnostics.add(
                "nullable casts require primitive payloads and a nullable "
                "target; use expect_valid to remove nullability",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            self._set_type(node, None)
            return
        if not isinstance(source, astx.NoneType):
            validate_cast(
                self.context.diagnostics,
                source_type=payload,
                target_type=target.payload_type,
                node=node,
            )
        self._set_type(node, target)

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.IsInstanceExpr) -> None:
        """
        title: Visit IsInstanceExpr nodes.
        parameters:
          node:
            type: astx.IsInstanceExpr
        """
        self.visit(node.value)
        self._resolve_declared_type(node.target_type, node=node)
        if not self._require_value_expression(
            node.value,
            context="IsInstanceExpr",
        ):
            self._set_type(node, astx.Boolean())
            setattr(node, "static_result", False)
            return
        value_type = self._expr_type(node.value)
        static_result = is_type_member(node.target_type, value_type)
        setattr(node, "static_result", static_result)
        self._set_type(node, astx.Boolean())

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.PrintExpr) -> None:
        """
        title: Visit PrintExpr nodes.
        parameters:
          node:
            type: astx.PrintExpr
        """
        self.visit(node.message)
        if not self._require_value_expression(
            node.message,
            context="PrintExpr",
        ):
            self._set_type(node, astx.Int32())
            return
        message_type = self._expr_type(node.message)
        if not (
            is_string_type(message_type)
            or is_integer_type(message_type)
            or is_float_type(message_type)
            or is_boolean_type(message_type)
        ):
            self.context.diagnostics.add(
                "unsupported PrintExpr message type "
                f"{display_type_name(message_type)}",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        self._set_type(node, astx.Int32())

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.TypeOfExpr) -> None:
        """
        title: Visit TypeOfExpr nodes.
        parameters:
          node:
            type: astx.TypeOfExpr
        """
        self.visit(node.value)
        if not self._require_value_expression(
            node.value,
            context="TypeOfExpr",
        ):
            self._set_type(node, astx.String())
            self._set_resource_ownership(
                node,
                string_resource_ownership(OwnershipKind.STATIC),
            )
            return
        self._set_type(node, astx.String())
        self._set_resource_ownership(
            node,
            string_resource_ownership(OwnershipKind.STATIC),
        )
