"""
title: Semantic entity factories.
summary: Build semantic sidecar entities and visible binding wrappers in
  one place so analyzer visitors can focus on traversal and rule orchestration.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any

import astx

from public import public

from irx.analysis.context import SemanticContext
from irx.analysis.module_interfaces import ModuleKey
from irx.analysis.module_symbols import (
    qualified_class_member_name,
    qualified_class_name,
    qualified_function_name,
    qualified_struct_name,
)
from irx.analysis.resolved_nodes import (
    CallableResolution,
    CallingConvention,
    ClassMemberKind,
    FFICallableInfo,
    FunctionSignature,
    ParameterPassingKind,
    ParameterSpec,
    ResolvedImportBinding,
    SemanticBinding,
    SemanticClass,
    SemanticClassMember,
    SemanticFunction,
    SemanticModule,
    SemanticStruct,
    SemanticSymbol,
)
from irx.analysis.symbols import variable_symbol
from irx.analysis.types import clone_type
from irx.typecheck import typechecked

PARAMETER_DEFAULT_FINGERPRINT_METADATA = "default_fingerprint"
PARAMETER_HAS_DEFAULT_METADATA = "has_default"
_TRANSIENT_AST_FIELDS = frozenset(
    {
        "comment",
        "kind",
        "loc",
        "parent",
        "ref",
        "semantic",
        "type_",
    }
)


@public
@typechecked
class SemanticEntityFactory:
    """
    title: Central semantic entity construction.
    summary: Create semantic symbols, functions, structs, modules, and visible
      bindings with consistent ids and qualified names.
    attributes:
      context: Context for the operation.
    """

    context: SemanticContext

    def __init__(self, context: SemanticContext) -> None:
        """
        title: Initialize SemanticEntityFactory.
        parameters:
          context: Context for the operation.
        """
        self.context = context

    def make_variable_symbol(
        self,
        module_key: ModuleKey,
        name: str,
        type_: astx.DataType,
        *,
        is_mutable: bool,
        declaration: astx.AST | None,
        kind: str = "variable",
    ) -> SemanticSymbol:
        """
        title: Create a variable-like semantic symbol.
        parameters:
          module_key: Canonical module identity.
          name: Name identifying the declaration or operation.
          type_: Type expression to process.
          is_mutable: Whether is mutable.
          declaration: Declaration being processed.
          kind: Kind of value or operation.
        returns: Created a variable-like semantic symbol.
        """
        return variable_symbol(
            self.context.next_symbol_id(kind),
            module_key,
            name,
            clone_type(type_),
            is_mutable=is_mutable,
            declaration=declaration,
            kind=kind,
        )

    def make_parameter_symbol(
        self,
        module_key: ModuleKey,
        argument: astx.Argument,
    ) -> SemanticSymbol:
        """
        title: Create one function-parameter semantic symbol.
        summary: Rebinding follows Argument.mutability independently
          of parameter passing and resource-ownership policy.
        parameters:
          module_key: Canonical module identity.
          argument: Argument.
        returns: Created one function-parameter semantic symbol.
        """
        return self.make_variable_symbol(
            module_key,
            argument.name,
            argument.type_,
            is_mutable=argument.mutability != astx.MutabilityKind.constant,
            declaration=argument,
            kind="argument",
        )

    def _argument_has_default(
        self,
        argument: astx.Argument,
    ) -> bool:
        """
        title: Return whether one parameter declares a default value.
        parameters:
          argument: Argument.
        returns: Whether one parameter declares a default value.
        """
        return not isinstance(argument.default, astx.Undefined)

    def _is_transient_ast_name(
        self,
        node: object,
        value: object,
    ) -> bool:
        """
        title: Return whether an AST name is an implementation-generated name.
        parameters:
          node: Syntax node to process.
          value: Value to process.
        returns: Whether an AST name is an implementation-generated name.
        """
        if isinstance(node, astx.Identifier):
            return False
        return (
            isinstance(value, str)
            and value.startswith("temp_")
            and value[5:].isdigit()
        )

    def _default_fingerprint(self, value: object) -> object:
        """
        title: Build one structural fingerprint for a parameter default.
        summary: Compare AST default expressions without relying
          on ASTx equality, which lowers equality into expression
          nodes instead of booleans.
        parameters:
          value: Value to process.
        returns: Constructed one structural fingerprint for a parameter
          default.
        """
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        if isinstance(value, Enum):
            return (
                "enum",
                type(value).__module__,
                type(value).__qualname__,
                self._default_fingerprint(value.value),
            )
        if isinstance(value, astx.AST):
            return self._object_fingerprint(
                "ast",
                value,
            )
        if isinstance(value, Mapping):
            items = tuple(
                sorted(
                    (
                        (
                            self._default_fingerprint(key),
                            self._default_fingerprint(item),
                        )
                        for key, item in value.items()
                    ),
                    key=repr,
                )
            )
            return ("mapping", items)
        if isinstance(value, Sequence) and not isinstance(
            value,
            (str, bytes, bytearray),
        ):
            return (
                "sequence",
                tuple(self._default_fingerprint(item) for item in value),
            )
        if isinstance(value, type):
            return ("type", value.__module__, value.__qualname__)
        if hasattr(value, "__dict__"):
            return self._object_fingerprint(
                "object",
                value,
            )
        return (
            "value",
            type(value).__module__,
            type(value).__qualname__,
            repr(value),
        )

    def _object_fingerprint(
        self,
        tag: str,
        value: object,
    ) -> object:
        """
        title: Build one structural fingerprint for an object's data fields.
        parameters:
          tag: Tag.
          value: Value to process.
        returns: Constructed one structural fingerprint for an object's data
          fields.
        """
        fields: list[tuple[str, object]] = []
        for field_name, field_value in sorted(vars(value).items()):
            if field_name in _TRANSIENT_AST_FIELDS:
                continue
            if field_name == "name" and self._is_transient_ast_name(
                value,
                field_value,
            ):
                continue
            fields.append(
                (
                    field_name,
                    self._default_fingerprint(field_value),
                )
            )
        return (
            tag,
            type(value).__module__,
            type(value).__qualname__,
            tuple(fields),
        )

    def _parameter_default_metadata(
        self,
        argument: astx.Argument,
    ) -> dict[str, Any]:
        """
        title: Return normalized default metadata for one parameter.
        parameters:
          argument: Argument.
        returns: Normalized default metadata for one parameter.
        """
        if not self._argument_has_default(argument):
            return {
                PARAMETER_HAS_DEFAULT_METADATA: False,
                PARAMETER_DEFAULT_FINGERPRINT_METADATA: None,
            }
        return {
            PARAMETER_HAS_DEFAULT_METADATA: True,
            PARAMETER_DEFAULT_FINGERPRINT_METADATA: (
                self._default_fingerprint(argument.default)
            ),
        }

    def make_parameter_spec(
        self,
        argument: astx.Argument,
    ) -> ParameterSpec:
        """
        title: Create one canonical semantic parameter specification.
        parameters:
          argument: Argument.
        returns: Created one canonical semantic parameter specification.
        """
        return ParameterSpec(
            name=argument.name,
            type_=clone_type(argument.type_),
            passing_kind=ParameterPassingKind.from_access(
                argument.borrow_access
            ),
            metadata=self._parameter_default_metadata(argument),
        )

    def make_function_signature(
        self,
        prototype: astx.FunctionPrototype,
        *,
        calling_convention: CallingConvention,
        is_variadic: bool,
        is_extern: bool,
        symbol_name: str,
        required_runtime_features: tuple[str, ...] = (),
        ffi: FFICallableInfo | None = None,
    ) -> FunctionSignature:
        """
        title: Create one canonical semantic function signature.
        parameters:
          prototype: Prototype.
          calling_convention: Calling convention.
          is_variadic: Whether is variadic.
          is_extern: Whether is extern.
          symbol_name: Name of symbol.
          required_runtime_features: Required runtime features.
          ffi: FFI.
        returns: Created one canonical semantic function signature.
        """
        return FunctionSignature(
            name=prototype.name,
            parameters=tuple(
                self.make_parameter_spec(argument)
                for argument in prototype.args.nodes
            ),
            return_type=clone_type(prototype.return_type),
            calling_convention=calling_convention,
            is_variadic=is_variadic,
            is_extern=is_extern,
            exception_abi=not is_extern,
            symbol_name=symbol_name,
            required_runtime_features=required_runtime_features,
            ffi=ffi,
        )

    def make_function(
        self,
        module_key: ModuleKey,
        prototype: astx.FunctionPrototype,
        *,
        signature: FunctionSignature,
        definition: astx.FunctionDef | None = None,
        args: tuple[SemanticSymbol, ...] | None = None,
    ) -> SemanticFunction:
        """
        title: Create one semantic function entity.
        parameters:
          module_key: Canonical module identity.
          prototype: Prototype.
          signature: Resolved callable signature.
          definition: Definition.
          args: Arguments supplied to the operation.
        returns: Created one semantic function entity.
        """
        semantic_args = args
        if semantic_args is None:
            semantic_args = tuple(
                self.make_parameter_symbol(module_key, argument)
                for argument in (
                    definition.prototype.args.nodes
                    if definition is not None
                    else prototype.args.nodes
                )
            )
        return SemanticFunction(
            symbol_id=self.context.next_symbol_id("fn"),
            name=prototype.name,
            return_type=clone_type(signature.return_type),
            args=semantic_args,
            signature=signature,
            prototype=prototype,
            definition=definition,
            module_key=module_key,
            qualified_name=qualified_function_name(module_key, prototype.name),
            visibility=prototype.visibility,
            template_params=tuple(
                astx.TemplateParam(
                    param.name,
                    clone_type(param.bound),
                    param.loc,
                )
                for param in astx.get_template_params(prototype)
            ),
        )

    def make_callable_resolution(
        self,
        function: SemanticFunction,
    ) -> CallableResolution:
        """
        title: Create one resolved callable wrapper.
        parameters:
          function: Function to process.
        returns: Created one resolved callable wrapper.
        """
        return CallableResolution(
            function=function,
            signature=function.signature,
        )

    def make_struct(
        self,
        module_key: ModuleKey,
        node: astx.StructDefStmt,
    ) -> SemanticStruct:
        """
        title: Create one semantic struct entity.
        parameters:
          module_key: Canonical module identity.
          node: Syntax node to process.
        returns: Created one semantic struct entity.
        """
        return SemanticStruct(
            symbol_id=self.context.next_symbol_id("struct"),
            name=node.name,
            module_key=module_key,
            qualified_name=qualified_struct_name(module_key, node.name),
            declaration=node,
        )

    def make_class(
        self,
        module_key: ModuleKey,
        node: astx.ClassDefStmt,
    ) -> SemanticClass:
        """
        title: Create one semantic class entity.
        parameters:
          module_key: Canonical module identity.
          node: Syntax node to process.
        returns: Created one semantic class entity.
        """
        return SemanticClass(
            symbol_id=self.context.next_symbol_id("class"),
            name=node.name,
            module_key=module_key,
            qualified_name=qualified_class_name(module_key, node.name),
            declaration=node,
            is_abstract=bool(getattr(node, "is_abstract", False)),
        )

    def make_class_member(
        self,
        class_: SemanticClass,
        *,
        name: str,
        kind: ClassMemberKind,
        declaration: astx.AST,
        visibility: astx.VisibilityKind,
        is_static: bool,
        is_constant: bool,
        is_mutable: bool,
        is_abstract: bool = False,
        type_: astx.DataType | None = None,
        signature: FunctionSignature | None = None,
        signature_key: str | None = None,
        overrides: str | None = None,
        dispatch_slot: int | None = None,
        lowered_function: SemanticFunction | None = None,
    ) -> SemanticClassMember:
        """
        title: Create one semantic class-member record.
        parameters:
          class_: Class being processed.
          name: Name identifying the declaration or operation.
          kind: Kind of value or operation.
          declaration: Declaration being processed.
          visibility: Visibility.
          is_static: Whether the member belongs to the class rather than
            an instance.
          is_constant: Whether is constant.
          is_mutable: Whether is mutable.
          is_abstract: Whether is abstract.
          type_: Type expression to process.
          signature: Resolved callable signature.
          signature_key: Signature key.
          overrides: Overrides.
          dispatch_slot: Dispatch slot.
          lowered_function: Lowered function.
        returns: Created one semantic class-member record.
        """
        prefix = (
            "class_attr"
            if kind is ClassMemberKind.ATTRIBUTE
            else "class_method"
        )
        return SemanticClassMember(
            symbol_id=self.context.next_symbol_id(prefix),
            name=name,
            qualified_name=qualified_class_member_name(
                class_.module_key,
                class_.name,
                name,
                signature_key if kind is ClassMemberKind.METHOD else None,
            ),
            owner_name=class_.name,
            owner_qualified_name=class_.qualified_name,
            kind=kind,
            visibility=visibility,
            is_static=is_static,
            is_abstract=is_abstract,
            is_constant=is_constant,
            is_mutable=is_mutable,
            declaration=declaration,
            type_=clone_type(type_) if type_ is not None else None,
            signature=signature,
            signature_key=signature_key,
            overrides=overrides,
            dispatch_slot=dispatch_slot,
            lowered_function=lowered_function,
        )

    def make_module(
        self,
        module_key: ModuleKey,
        *,
        display_name: str | None = None,
    ) -> SemanticModule:
        """
        title: Create one semantic module entity.
        parameters:
          module_key: Canonical module identity.
          display_name: Name of display.
        returns: Created one semantic module entity.
        """
        return SemanticModule(
            module_key=module_key,
            display_name=display_name,
        )

    def make_function_binding(
        self,
        function: SemanticFunction,
    ) -> SemanticBinding:
        """
        title: Create a visible binding for a function.
        parameters:
          function: Function to process.
        returns: Created a visible binding for a function.
        """
        return SemanticBinding(
            kind="function",
            module_key=function.module_key,
            qualified_name=function.qualified_name,
            function=function,
        )

    def make_struct_binding(
        self,
        struct: SemanticStruct,
    ) -> SemanticBinding:
        """
        title: Create a visible binding for a struct.
        parameters:
          struct: Struct.
        returns: Created a visible binding for a struct.
        """
        return SemanticBinding(
            kind="struct",
            module_key=struct.module_key,
            qualified_name=struct.qualified_name,
            struct=struct,
        )

    def make_class_binding(
        self,
        class_: SemanticClass,
    ) -> SemanticBinding:
        """
        title: Create a visible binding for a class.
        parameters:
          class_: Class being processed.
        returns: Created a visible binding for a class.
        """
        return SemanticBinding(
            kind="class",
            module_key=class_.module_key,
            qualified_name=class_.qualified_name,
            class_=class_,
        )

    def make_module_binding(
        self,
        module: SemanticModule,
    ) -> SemanticBinding:
        """
        title: Create a visible binding for a module.
        parameters:
          module: Module to process.
        returns: Created a visible binding for a module.
        """
        return SemanticBinding(
            kind="module",
            module_key=module.module_key,
            qualified_name=str(module.module_key),
            module=module,
        )

    def make_import_binding(
        self,
        *,
        local_name: str,
        requested_name: str,
        source_module_key: ModuleKey,
        binding: SemanticBinding,
    ) -> ResolvedImportBinding:
        """
        title: Create one resolved import binding record.
        parameters:
          local_name: Name of local.
          requested_name: Name of requested.
          source_module_key: Source module key.
          binding: Resolved binding for the operation.
        returns: Created one resolved import binding record.
        """
        return ResolvedImportBinding(
            local_name=local_name,
            requested_name=requested_name,
            source_module_key=source_module_key,
            binding=binding,
        )
