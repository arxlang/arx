# mypy: disable-error-code=no-redef

"""
title: Expression operator visitors.
summary: >-
  Analyze unary, binary, cast, and print expressions plus their assignment-like
  operator behavior.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import astx

from astx.binary_op import (
    SPECIALIZED_BINARY_OP_EXTRA,
    specialize_binary_op,
)
from plum import dispatch
from public import private

from irx.analysis.arrow_conversion import (
    arrow_ownership,
)
from irx.analysis.class_lifecycle import class_ownership
from irx.analysis.dependencies.expression_operator import (
    ExpressionOperatorAnalysisServices,
)
from irx.analysis.normalization import normalize_flags, normalize_operator
from irx.analysis.numeric_literals import (
    analyze_constant_cast,
    analyze_constant_operation,
    contextualize_literal,
)
from irx.analysis.numeric_policy import (
    classify_numeric_conversion,
    integer_bounds,
)
from irx.analysis.ownership import (
    resource_ownership,
    string_resource_ownership,
)
from irx.analysis.resolved_nodes import (
    ImplicitConversion,
    OwnershipKind,
    ResolvedAugAssignment,
)
from irx.analysis.types import (
    common_numeric_type,
    display_type_name,
    is_assignable,
    is_boolean_type,
    is_float_type,
    is_integer_type,
    is_numeric_type,
    is_string_type,
    is_type_member,
    same_type,
    union_storage_type,
)
from irx.analysis.typing import binary_result_type, unary_result_type
from irx.analysis.validation import validate_assignment, validate_cast
from irx.diagnostics import DiagnosticCodes
from irx.extensions.handlers import configuration_error
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class ExpressionOperatorAnalysis:
    """
    title: Expression visitors for unary, binary, cast, and print operations
    attributes:
      services:
        type: ExpressionOperatorAnalysisServices
    """

    services: ExpressionOperatorAnalysisServices

    def __init__(self, services: ExpressionOperatorAnalysisServices) -> None:
        """
        title: Bind one feature to explicit compilation-owned dependencies.
        parameters:
          services:
            type: ExpressionOperatorAnalysisServices
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
            f"unsupported {type(node).__name__} in ExpressionOperatorAnalysis"
        )

    @dispatch
    def visit(self, node: astx.AugAssign) -> None:
        """
        title: Resolve checked compound mutation of one numeric identifier.
        summary: >-
          Accept +=, -=, *=, /=, and %= with lossless operand and store
          conversions. This internal value-producing operation does not imply
          expression-context support in a frontend. Reject other modeled
          opcodes and non-scalar domains before lowering.
        parameters:
          node:
            type: astx.AugAssign
        """
        self.services.semantic(node).resolved_aug_assignment = None
        if node.op_code not in {"+=", "-=", "*=", "/=", "%="}:
            self.services.context.diagnostics.add(
                f"unsupported compound assignment '{node.op_code}'",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        if not isinstance(node.target, astx.Identifier):
            self.services.context.diagnostics.add(
                "compound assignment requires an identifier target",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_ASSIGNMENT_TARGET,
            )
            return
        self.services.visit(node.target)
        resolved = self.services.resolve_mutation_target(
            node.target,
            node=node,
            action="assign to",
            invalid_message="compound assignment requires a mutable variable",
        )
        if resolved is None:
            return
        symbol, target_name, target_type = resolved
        contextualize_literal(node.value, target_type)
        self.services.visit(node.value)
        if not self.services.require_value_expression(
            node.value, context="Compound assignment"
        ):
            return
        value_type = self.services.expr_type(node.value)
        if not (is_numeric_type(target_type) and is_numeric_type(value_type)):
            self.services.context.diagnostics.add(
                "compound assignment requires non-nullable numeric scalars",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        result_type = common_numeric_type(target_type, value_type)
        if result_type is None:
            self.services.context.diagnostics.add(
                "compound operands have no lossless common type; "
                "use an explicit cast",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        validate_assignment(
            self.services.context.diagnostics,
            target_name=target_name,
            target_type=target_type,
            value_type=result_type,
            node=node,
        )
        if not symbol.is_mutable or not is_assignable(
            target_type, result_type
        ):
            return
        flags = normalize_flags(
            node, lhs_type=target_type, rhs_type=value_type
        )
        operation = normalize_operator(
            node.op_code[0],
            result_type=result_type,
            lhs_type=target_type,
            rhs_type=value_type,
            flags=flags,
        )
        self.services.set_flags(node, flags)
        self.services.set_operator(node, operation)
        self.services.set_assignment(node, symbol)
        self.services.set_type(node, target_type)
        self.services.semantic(
            node
        ).resolved_aug_assignment = ResolvedAugAssignment(
            symbol, operation, ImplicitConversion(result_type, target_type)
        )

    @dispatch
    def visit(self, node: astx.UnaryOp) -> None:
        """
        title: Visit UnaryOp nodes.
        parameters:
          node:
            type: astx.UnaryOp
        """
        self.services.visit(node.operand)
        if not self.services.require_value_expression(
            node.operand,
            context=f"Unary operator '{node.op_code}'",
        ):
            self.services.set_type(node, None)
            return
        operand_type = self.services.expr_type(node.operand)
        if self.services.free_resolve_column_unary(node):
            return
        if node.op_code in {"+", "-"} and not is_numeric_type(operand_type):
            self.services.context.diagnostics.add(
                "unary sign requires a numeric operand",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        if (
            node.op_code == "!"
            and operand_type is not None
            and not is_boolean_type(operand_type)
        ):
            self.services.context.diagnostics.add(
                "unary operator '!' requires Boolean operand",
                node=node,
            )
        if isinstance(operand_type, astx.FileType):
            self.services.context.diagnostics.add(
                "file operators are unsupported",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        result_type = unary_result_type(node.op_code, operand_type)
        if node.op_code in {"++", "--"}:
            resolved_target = self.services.resolve_mutation_target(
                node.operand,
                node=node,
                action="mutate",
                invalid_message=(
                    "mutation target must be a variable or field"
                ),
            )
            if resolved_target is not None:
                target_symbol, _target_name, _target_type = resolved_target
                self.services.set_assignment(node, target_symbol)
        flags = normalize_flags(node, lhs_type=operand_type)
        self.services.set_flags(node, flags)
        self.services.set_operator(
            node,
            normalize_operator(
                node.op_code,
                result_type=result_type,
                lhs_type=operand_type,
                flags=flags,
            ),
        )
        self.services.set_type(node, result_type)
        analyze_constant_operation(node, self.services.context, result_type)

    @dispatch
    def visit(self, node: astx.BinaryOp) -> None:
        """
        title: Visit BinaryOp nodes.
        parameters:
          node:
            type: astx.BinaryOp
        """
        self.services.semantic(node).resource_ownership = None
        self.services.semantic(node).resolved_resource_store = None
        self.services.semantic(node).lifecycle_field_store = False
        source_literal = (astx.LiteralInteger, astx.LiteralFloat)
        rhs_visited = False
        if isinstance(node.lhs, source_literal) and not isinstance(
            node.rhs, source_literal
        ):
            self.services.visit(node.rhs)
            rhs_visited = True
            contextualize_literal(node.lhs, self.services.expr_type(node.rhs))
        explicit = (
            astx.get_template_args(node)
            if node.mode is astx.NumericMode.WRAPPING
            else None
        )
        if explicit is not None and len(explicit) == 1:
            contextualize_literal(node.lhs, explicit[0])
            contextualize_literal(node.rhs, explicit[0])
        self.services.visit(node.lhs)
        target = self.services.expr_type(node.lhs)
        if not isinstance(node.lhs, source_literal):
            contextualize_literal(node.rhs, target)
        if (
            node.op_code == "="
            and isinstance(target, astx.NullableType)
            and isinstance(node.rhs, astx.LiteralNone)
        ):
            node.rhs = astx.Cast(node.rhs, target)
            node.rhs.loc = node.rhs.value.loc
        if not rhs_visited:
            with self.services.context.constant_diagnostics(
                node.op_code not in {"&&", "and", "||", "or"}
                or (
                    isinstance(node.lhs, astx.LiteralBoolean)
                    and node.lhs.value == (node.op_code in {"&&", "and"})
                )
            ):
                self.services.visit(node.rhs)
        lhs_type = self.services.expr_type(node.lhs)
        rhs_type = self.services.expr_type(node.rhs)
        if (
            isinstance(lhs_type, astx.FileType)
            or isinstance(rhs_type, astx.FileType)
        ) and not (
            node.op_code == "=" and isinstance(node.lhs, astx.FieldAccess)
        ):
            self.services.context.diagnostics.add(
                "file operators and reassignment are unsupported",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        if (
            node.op_code == "="
            and isinstance(node.lhs, astx.SubscriptExpr)
            and isinstance(
                self.services.expr_type(node.lhs.value), astx.SeriesType
            )
        ):
            if (
                self.services.resolve_mutation_target(
                    node.lhs.value,
                    node=node,
                    action="update",
                    invalid_message=(
                        "Series updates require a mutable variable or field"
                    ),
                )
                is None
            ):
                return
        if node.mode is astx.NumericMode.WRAPPING:
            chosen = (
                explicit[0]
                if explicit is not None and len(explicit) == 1
                else lhs_type
            )
            valid = (
                node.op_code in {"+", "-", "*"}
                and chosen is not None
                and integer_bounds(chosen) is not None
                and lhs_type is not None
                and integer_bounds(lhs_type) is not None
                and rhs_type is not None
                and integer_bounds(rhs_type) is not None
                and (explicit is None or len(explicit) == 1)
                and (
                    same_type(lhs_type, rhs_type)
                    if explicit is None
                    else is_assignable(chosen, lhs_type)
                    and is_assignable(chosen, rhs_type)
                )
            )
            if not valid:
                self.services.context.diagnostics.add(
                    "wrapping arithmetic requires one concrete integer type; "
                    "use "
                    "an explicit lossless specialization",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
                )
                return
            assert chosen is not None
            flags = normalize_flags(node, lhs_type=chosen, rhs_type=chosen)
            plan = normalize_operator(
                node.op_code,
                result_type=chosen,
                lhs_type=lhs_type,
                rhs_type=rhs_type,
                flags=flags,
                mode=node.mode,
            )

            plan = replace(
                plan,
                computation_type=chosen,
                lhs_conversion=ImplicitConversion(lhs_type, chosen),
                rhs_conversion=ImplicitConversion(rhs_type, chosen),
            )
            self.services.set_flags(node, flags)
            self.services.set_operator(node, plan)
            self.services.set_type(node, chosen)
            analyze_constant_operation(node, self.services.context, chosen)
            return
        if node.op_code == "%" and not (
            is_numeric_type(lhs_type) and is_numeric_type(rhs_type)
        ):
            self.services.context.diagnostics.add(
                "remainder '%' requires non-nullable numeric scalars; "
                "collection and vector remainder is unsupported",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            self.services.set_type(node, None)
            return
        if self.services.free_resolve_column_binary(node):
            return
        flags = normalize_flags(node, lhs_type=lhs_type, rhs_type=rhs_type)
        self.services.set_flags(node, flags)
        specialized = specialize_binary_op(node)
        if specialized is not node:
            setattr(specialized, "semantic", self.services.semantic(node))
        self.services.semantic(node).extras[SPECIALIZED_BINARY_OP_EXTRA] = (
            specialized
        )

        if node.op_code == "=":
            resolved_target = self.services.resolve_mutation_target(
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
            managed_store = self.services.free_resolve_arrow_store(
                node, assignment_symbol
            ) or self.services.free_resolve_store(node, assignment_symbol)
            if self.services.require_value_expression(
                node.rhs,
                context=f"Assignment to '{target_name}'",
            ):
                validate_assignment(
                    self.services.context.diagnostics,
                    target_name=target_name,
                    target_type=target_type,
                    value_type=rhs_type,
                    node=node,
                )
            self.services.set_assignment(node, assignment_symbol)
            if isinstance(node.lhs, astx.Identifier):
                self.services.set_symbol(node.lhs, assignment_symbol)
            self.services.set_type(node, target_type)
            self.services.set_operator(
                node,
                normalize_operator(
                    node.op_code,
                    result_type=target_type,
                    lhs_type=target_type,
                    rhs_type=rhs_type,
                    flags=flags,
                ),
            )
            if managed_store:
                return
            self.services.resolve_list_assignment_ownership(
                node,
                node.rhs,
                assignment_symbol,
                target_name=target_name,
                target_type=target_type,
                is_local=isinstance(node.lhs, astx.Identifier),
            )
            self.services.resolve_string_assignment_ownership(
                node,
                node.rhs,
                assignment_symbol,
                target_name=target_name,
                target_type=target_type,
                is_local=isinstance(node.lhs, astx.Identifier),
            )
            return

        lhs_has_value = self.services.require_value_expression(
            node.lhs,
            context=f"Operator '{node.op_code}'",
        )
        rhs_has_value = self.services.require_value_expression(
            node.rhs,
            context=f"Operator '{node.op_code}'",
        )
        if not (lhs_has_value and rhs_has_value):
            self.services.set_type(node, None)
            self.services.set_operator(
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
            self.services.context.diagnostics.add(
                "FMA requires a third operand (fma_rhs)",
                node=node,
            )
        if flags.fma and flags.fma_rhs is not None:
            self.services.visit(flags.fma_rhs)

        if (
            node.op_code in {"&&", "and", "||", "or"}
            and lhs_type is not None
            and rhs_type is not None
            and not (is_boolean_type(lhs_type) and is_boolean_type(rhs_type))
        ):
            self.services.context.diagnostics.add(
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
            self.services.context.diagnostics.add(
                f"Invalid operator '{node.op_code}' for operand types",
                node=node,
            )

        if (
            is_numeric_type(lhs_type)
            and is_numeric_type(rhs_type)
            and common_numeric_type(lhs_type, rhs_type) is None
        ):
            self.services.context.diagnostics.add(
                "numeric operands have no lossless common type; use an "
                "explicit cast",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        result_type = binary_result_type(node.op_code, lhs_type, rhs_type)
        self.services.set_type(node, result_type)
        analyze_constant_operation(node, self.services.context, result_type)
        self.services.set_operator(
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
            self.services.set_resource_ownership(
                node,
                string_resource_ownership(OwnershipKind.OWNED),
            )

    @dispatch
    def visit(self, node: astx.Cast) -> None:
        """
        title: Visit Cast nodes.
        parameters:
          node:
            type: astx.Cast
        """
        self.services.semantic(node).resource_ownership = None
        if node.mode is astx.NumericMode.CHECKED and not (
            isinstance(node.value, astx.LiteralInteger)
            and is_float_type(
                node.target_type.value_type
                if isinstance(node.target_type, astx.NullableType)
                else node.target_type
            )
        ):
            contextualize_literal(node.value, node.target_type)
        self.services.visit(node.value)
        source = self.services.expr_type(node.value)
        target = node.target_type
        if isinstance(source, astx.Bytes) or isinstance(target, astx.Bytes):
            self.services.context.diagnostics.add(
                "bytes casts are unsupported; "
                "use bytes(input) for a checked copy",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            self.services.set_type(node, target)
            return
        source_scalar = (
            source.value_type
            if isinstance(source, astx.NullableType)
            else source
        )
        target_scalar = (
            target.value_type
            if isinstance(target, astx.NullableType)
            else target
        )
        if isinstance(source_scalar, astx.UnionType):
            source_scalar = union_storage_type(source_scalar)
        if isinstance(target_scalar, astx.UnionType):
            target_scalar = union_storage_type(target_scalar)
        if target_scalar is None:
            self.services.context.diagnostics.add(
                "union has no lossless scalar storage",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        self.services.semantic(node).numeric_mode = node.mode
        if source_scalar is not None:
            self.services.semantic(
                node
            ).numeric_conversion = classify_numeric_conversion(
                source_scalar, target_scalar
            )
        if (
            is_numeric_type(source_scalar)
            and is_numeric_type(target_scalar)
            and self.services.semantic(node).numeric_conversion is None
        ):
            self.services.context.diagnostics.add(
                "unsupported numeric conversion domain",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        analyze_constant_cast(node, self.services.context)
        if node.mode is astx.NumericMode.WRAPPING and (
            source_scalar is None
            or integer_bounds(source_scalar) is None
            or integer_bounds(target_scalar) is None
        ):
            self.services.context.diagnostics.add(
                "wrapping_cast requires integer source and destination types",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        if isinstance(node.target_type, astx.NullableType) and isinstance(
            node.value, astx.LiteralNone
        ):
            self.services.resolve_declared_type(node.target_type, node=node)
            self.services.set_type(node, node.target_type)
            return
        if not self.services.require_value_expression(
            node.value,
            context="Cast",
        ):
            self.services.set_type(
                node, cast(astx.DataType | None, node.target_type)
            )
            return
        self.services.resolve_declared_type(node.target_type, node=node)
        if self.services.free_resolve_arrow_cast(node):
            return
        if self.services.free_reject_native_file_cast(node):
            return
        source_type = self.services.expr_type(node.value)
        target_type = cast(astx.DataType | None, node.target_type)
        validate_cast(
            self.services.context.diagnostics,
            source_type=source_type,
            target_type=target_type,
            node=node,
        )
        self.services.set_type(node, target_type)
        if isinstance(target_type, astx.ClassType):
            self.services.set_resource_ownership(
                node, class_ownership(OwnershipKind.BORROWED)
            )
        if isinstance(target_type, astx.DataFrameType | astx.SeriesType):
            self.services.set_resource_ownership(
                node, arrow_ownership(target_type, OwnershipKind.BORROWED)
            )
        if not is_string_type(target_type):
            return
        source_ownership = resource_ownership(node.value)
        if is_string_type(source_type):
            if source_ownership is None:
                self.services.context.diagnostics.add(
                    "string cast source is missing ownership metadata",
                    node=node.value,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                )
                return
            if source_ownership.kind is OwnershipKind.OWNED:
                self.services.context.diagnostics.add(
                    "identity casts of owned strings are not supported; "
                    "remove the redundant cast to preserve the owner",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
                )
            self.services.set_resource_ownership(node, source_ownership)
            return
        self.services.set_resource_ownership(
            node,
            string_resource_ownership(OwnershipKind.OWNED),
        )

    @dispatch
    def visit(self, node: astx.IsInstanceExpr) -> None:
        """
        title: Visit IsInstanceExpr nodes.
        parameters:
          node:
            type: astx.IsInstanceExpr
        """
        self.services.visit(node.value)
        self.services.resolve_declared_type(node.target_type, node=node)
        if not self.services.require_value_expression(
            node.value,
            context="IsInstanceExpr",
        ):
            self.services.set_type(node, astx.Boolean())
            setattr(node, "static_result", False)
            return
        value_type = self.services.expr_type(node.value)
        static_result = is_type_member(node.target_type, value_type)
        setattr(node, "static_result", static_result)
        self.services.set_type(node, astx.Boolean())

    @dispatch
    def visit(self, node: astx.PrintExpr) -> None:
        """
        title: Visit PrintExpr nodes.
        parameters:
          node:
            type: astx.PrintExpr
        """
        self.services.visit(node.message)
        if not self.services.require_value_expression(
            node.message,
            context="PrintExpr",
        ):
            self.services.set_type(node, astx.Int32())
            return
        message_type = self.services.expr_type(node.message)
        if not (
            is_string_type(message_type)
            or is_integer_type(message_type)
            or is_float_type(message_type)
            or is_boolean_type(message_type)
        ):
            self.services.context.diagnostics.add(
                "unsupported PrintExpr message type "
                f"{display_type_name(message_type)}",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        self.services.set_type(node, astx.Int32())

    @dispatch
    def visit(self, node: astx.TypeOfExpr) -> None:
        """
        title: Visit TypeOfExpr nodes.
        parameters:
          node:
            type: astx.TypeOfExpr
        """
        self.services.visit(node.value)
        if not self.services.require_value_expression(
            node.value,
            context="TypeOfExpr",
        ):
            self.services.set_type(node, astx.String())
            self.services.set_resource_ownership(
                node,
                string_resource_ownership(OwnershipKind.STATIC),
            )
            return
        self.services.set_type(node, astx.String())
        self.services.set_resource_ownership(
            node,
            string_resource_ownership(OwnershipKind.STATIC),
        )

    def node_handlers(self) -> tuple[NodeHandler, ...]:
        """
        title: Export this feature's supported nominal node signatures.
        returns:
          type: tuple[NodeHandler, Ellipsis]
        """
        return tuple(
            contribute_node(
                "irx.analysis.expression_operator." + node_type.__name__,
                "irx.analysis.expression_operator",
                "analysis",
                node_type,
                self.visit,
                source=__name__ + ".ExpressionOperatorAnalysis.visit",
            )
            for node_type in (
                astx.AugAssign,
                astx.UnaryOp,
                astx.BinaryOp,
                astx.Cast,
                astx.IsInstanceExpr,
                astx.PrintExpr,
                astx.TypeOfExpr,
            )
        )
