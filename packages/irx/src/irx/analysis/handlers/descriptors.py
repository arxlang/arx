# mypy: disable-error-code=no-redef
# mypy: disable-error-code=untyped-decorator
"""
title: Descriptor literal validation and closed inspection signatures.
"""

from __future__ import annotations

import astx

from plum import dispatch
from public import private

from irx.analysis.handlers.base import (
    SemanticAnalyzerCore,
    SemanticVisitorMixinBase,
)
from irx.analysis.ownership import (
    resource_contract_for_type,
    typed_resource_ownership,
)
from irx.analysis.resolved_nodes import OwnershipKind
from irx.analysis.schema import SchemaError, canonical_schema
from irx.analysis.schema_conversions import (
    SchemaConversion,
    logical_conversion,
    schema_conversion,
)
from irx.analysis.schema_descriptors import (
    DescriptorOutput,
    ResolvedDescriptor,
    resolve_c_schema,
)
from irx.analysis.types import bit_width, is_signed_integer_type
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked

BINARY_ARITY = 2
DESCRIPTOR_TYPES = (astx.SchemaType, astx.FieldType, astx.TypeDescriptorType)
# Each accepted operation resolves to a typed runtime symbol before lowering.
QUERY_SIGNATURES = {
    astx.DescriptorOperation.FIELD_NAME: (
        astx.FieldType,
        "field_name_copy",
        astx.String,
    ),
    astx.DescriptorOperation.SCHEMA_FIELD_COUNT: (
        astx.SchemaType,
        "schema_num_fields",
        astx.Int64,
    ),
    astx.DescriptorOperation.SCHEMA_FIELD: (
        astx.SchemaType,
        "schema_field",
        astx.FieldType,
    ),
    astx.DescriptorOperation.FIELD_TYPE: (
        astx.FieldType,
        "field_type",
        astx.TypeDescriptorType,
    ),
    astx.DescriptorOperation.FIELD_NULLABLE: (
        astx.FieldType,
        "field_nullable",
        astx.Boolean,
    ),
    astx.DescriptorOperation.TYPE_BIT_WIDTH: (
        astx.TypeDescriptorType,
        "type_bit_width",
        astx.Int64,
    ),
    astx.DescriptorOperation.TYPE_FIELD_COUNT: (
        astx.TypeDescriptorType,
        "type_num_fields",
        astx.Int64,
    ),
    astx.DescriptorOperation.TYPE_FIELD: (
        astx.TypeDescriptorType,
        "type_field",
        astx.FieldType,
    ),
}
INDEX_OPERATIONS = {
    astx.DescriptorOperation.SCHEMA_FIELD,
    astx.DescriptorOperation.TYPE_FIELD,
}


@private
@dispatch
@typechecked
def descriptor_conversion(source: object, target: object) -> SchemaConversion:
    """
    title: Reject mixed or unsupported descriptor conversion kinds.
    parameters:
      source:
        type: object
      target:
        type: object
    returns:
      type: SchemaConversion
    """
    raise SchemaError("conversion_kind requires matching descriptor kinds")


@private
@dispatch
@typechecked
def descriptor_conversion(
    source: astx.LogicalType, target: astx.LogicalType
) -> SchemaConversion:
    """
    title: Classify a logical type pair without executing a value cast.
    parameters:
      source:
        type: astx.LogicalType
      target:
        type: astx.LogicalType
    returns:
      type: SchemaConversion
    """
    return logical_conversion(source, target)


@private
@dispatch
@typechecked
def descriptor_conversion(
    source: astx.Schema, target: astx.Schema
) -> SchemaConversion:
    """
    title: Classify a complete schema pair before lowering.
    parameters:
      source:
        type: astx.Schema
      target:
        type: astx.Schema
    returns:
      type: SchemaConversion
    """
    return schema_conversion(source, target)


@typechecked
class DescriptorVisitorMixin(SemanticVisitorMixinBase):
    """
    title: >-
      Resolve native descriptor operations without a Python runtime fallback.
    """

    def descriptor_literal(
        self, node: astx.DataType, field: astx.SchemaField, kind: str
    ) -> None:
        """
        title: >-
          Canonicalize one descriptor and attach its complete native sidecar.
        parameters:
          node:
            type: astx.DataType
          field:
            type: astx.SchemaField
          kind:
            type: str
        """
        try:
            tree = resolve_c_schema(field)
        except SchemaError as error:
            self.context.diagnostics.add(
                str(error),
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            self._set_type(node, None)
            return
        self._semantic(node).resolved_descriptor = ResolvedDescriptor(
            f"irx_arrow_{kind}_import_copy",
            DescriptorOutput.HANDLE,
            tree,
        )
        result_type = {
            "type": astx.TypeDescriptorType,
            "schema": astx.SchemaType,
            "field": astx.FieldType,
        }[kind]()
        self._set_type(node, result_type)
        self._set_resource_ownership(
            node, typed_resource_ownership(result_type, OwnershipKind.OWNED)
        )

    def descriptor_signature(
        self, node: astx.DescriptorQuery
    ) -> tuple[str, astx.DataType] | None:
        """
        title: Match the closed descriptor signature set, failing closed.
        parameters:
          node:
            type: astx.DescriptorQuery
        returns:
          type: tuple[str, astx.DataType] | None
        """
        args = node.arguments
        if not args:
            return None
        base = self._expr_type(args[0])
        if node.operation is astx.DescriptorOperation.EQUAL:
            if len(args) != BINARY_ARITY or not isinstance(
                base, DESCRIPTOR_TYPES
            ):
                return None
            if type(base) is not type(self._expr_type(args[1])):
                return None
            prefix = {
                astx.SchemaType: "schema",
                astx.FieldType: "field",
                astx.TypeDescriptorType: "type",
            }[type(base)]
            return prefix + "_equals", astx.Boolean()
        signature = QUERY_SIGNATURES.get(node.operation)
        if signature is None:
            return None
        expected, symbol, result = signature
        indexed = node.operation in INDEX_OPERATIONS
        if len(args) != (2 if indexed else 1) or not isinstance(
            base, expected
        ):
            return None
        if indexed and not is_signed_integer_type(self._expr_type(args[1])):
            return None
        return symbol, result()

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.TypeDescriptorLiteral) -> None:
        """
        title: Resolve a logical type literal to a native type owner.
        parameters:
          node:
            type: astx.TypeDescriptorLiteral
        """
        self.descriptor_literal(node, astx.SchemaField("", node.value), "type")

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.FieldLiteral) -> None:
        """
        title: Resolve a field literal to a native field owner.
        parameters:
          node:
            type: astx.FieldLiteral
        """
        self.descriptor_literal(node, node.value, "field")

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.SchemaLiteral) -> None:
        """
        title: Resolve an ordered schema, retaining binary root metadata.
        parameters:
          node:
            type: astx.SchemaLiteral
        """
        try:
            schema = canonical_schema(node.value)
        except SchemaError as error:
            self.context.diagnostics.add(
                str(error),
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        self.descriptor_literal(
            node,
            astx.SchemaField(
                "",
                astx.LogicalType(
                    astx.LogicalKind.STRUCT, fields=schema.fields
                ),
                metadata=schema.metadata,
            ),
            "schema",
        )

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.DescriptorQuery) -> None:
        """
        title: >-
          Resolve operand types, arity and the exact native inspection call.
        parameters:
          node:
            type: astx.DescriptorQuery
        """
        for arg in node.arguments:
            self.visit(arg)
        signature = self.descriptor_signature(node)
        if signature is None:
            self.context.diagnostics.add(
                "invalid operands for descriptor operation "
                f"{node.operation.value}",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            self._set_type(node, None)
            return
        symbol, result = signature
        self._set_type(node, result)
        output = DescriptorOutput.INT64
        if isinstance(result, astx.String):
            output = DescriptorOutput.STRING
            self._set_resource_ownership(
                node, typed_resource_ownership(result, OwnershipKind.OWNED)
            )
        elif isinstance(result, astx.Boolean):
            output = DescriptorOutput.BOOLEAN
        elif resource_contract_for_type(result) is not None:
            output = DescriptorOutput.HANDLE
            self._set_resource_ownership(
                node, typed_resource_ownership(result, OwnershipKind.OWNED)
            )
        self._semantic(node).resolved_descriptor = ResolvedDescriptor(
            "irx_arrow_" + symbol,
            output,
            index_bit_width=(
                bit_width(self._expr_type(node.arguments[1]))
                if node.operation in INDEX_OPERATIONS
                else None
            ),
        )

    @SemanticAnalyzerCore.visit.dispatch
    def visit(self, node: astx.DescriptorCompatibility) -> None:
        """
        title: >-
          Resolve complete conversion policy before emitting a scalar constant.
        parameters:
          node:
            type: astx.DescriptorCompatibility
        """
        try:
            result = descriptor_conversion(node.source, node.target)
        except SchemaError as error:
            self.context.diagnostics.add(
                str(error),
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            self._set_type(node, None)
            return
        self._semantic(node).resolved_descriptor_conversion = result
        self._set_type(node, astx.Int32())
