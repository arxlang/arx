"""
title: Reusable semantic callback shapes with named and optional arguments.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import astx

from public import private

from irx.analysis.resolved_nodes import (
    FunctionSignature,
    IterationKind,
    SemanticBinding,
    SemanticClass,
    SemanticClassLayoutField,
    SemanticClassMember,
    SemanticFunction,
    SemanticModule,
    SemanticStruct,
    SemanticSymbol,
)


@private
@runtime_checkable
class DeclareIterationTargetCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self,
        target: astx.AST,
        element_type: astx.DataType,
        *,
        kind: str,
        iteration_kind: IterationKind,
    ) -> SemanticSymbol | None:
        """
        title: Invoke the typed declare iteration target dependency.
        parameters:
          target:
            type: astx.AST
          element_type:
            type: astx.DataType
          kind:
            type: str
          iteration_kind:
            type: IterationKind
        returns:
          type: SemanticSymbol | None
        """
        del target, element_type, kind, iteration_kind
        raise NotImplementedError


@private
@runtime_checkable
class MakeLoweredMethodFunctionCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self,
        class_: SemanticClass,
        declaration: astx.FunctionDef,
        signature: FunctionSignature,
        *,
        is_static: bool,
        signature_key: str,
    ) -> SemanticFunction:
        """
        title: Invoke the typed make lowered method function dependency.
        parameters:
          class_:
            type: SemanticClass
          declaration:
            type: astx.FunctionDef
          signature:
            type: FunctionSignature
          is_static:
            type: bool
          signature_key:
            type: str
        returns:
          type: SemanticFunction
        """
        del class_, declaration, signature, is_static, signature_key
        raise NotImplementedError


@private
@runtime_checkable
class MethodCallKeyFromSignatureCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self,
        method_name: str,
        signature: FunctionSignature,
        *,
        is_static: bool,
    ) -> str:
        """
        title: Invoke the typed method call key from signature dependency.
        parameters:
          method_name:
            type: str
          signature:
            type: FunctionSignature
          is_static:
            type: bool
        returns:
          type: str
        """
        del method_name, signature, is_static
        raise NotImplementedError


@private
@runtime_checkable
class MethodSignatureKeyCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self,
        method_name: str,
        signature: FunctionSignature,
        *,
        is_static: bool,
    ) -> str:
        """
        title: Invoke the typed method signature key dependency.
        parameters:
          method_name:
            type: str
          signature:
            type: FunctionSignature
          is_static:
            type: bool
        returns:
          type: str
        """
        del method_name, signature, is_static
        raise NotImplementedError


@private
@runtime_checkable
class ModuleNamespaceNameCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self, node: astx.AST, module: SemanticModule | None = None
    ) -> str:
        """
        title: Invoke the typed module namespace name dependency.
        parameters:
          node:
            type: astx.AST
          module:
            type: SemanticModule | None
        returns:
          type: str
        """
        del node, module
        raise NotImplementedError


@private
@runtime_checkable
class RequireValueExpressionCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(self, node: astx.AST | None, *, context: str) -> bool:
        """
        title: Invoke the typed require value expression dependency.
        parameters:
          node:
            type: astx.AST | None
          context:
            type: str
        returns:
          type: bool
        """
        del node, context
        raise NotImplementedError


@private
@runtime_checkable
class ResolveBaseAccessClassesCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self,
        receiver_type: astx.DataType | None,
        base_class_name: str,
        *,
        node: astx.AST,
        context: str,
    ) -> tuple[SemanticClass, SemanticClass] | None:
        """
        title: Invoke the typed resolve base access classes dependency.
        parameters:
          receiver_type:
            type: astx.DataType | None
          base_class_name:
            type: str
          node:
            type: astx.AST
          context:
            type: str
        returns:
          type: tuple[SemanticClass, SemanticClass] | None
        """
        del receiver_type, base_class_name, node, context
        raise NotImplementedError


@private
@runtime_checkable
class ResolveClassAttributeMemberCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self, class_: SemanticClass, field_name: str, *, node: astx.AST
    ) -> SemanticClassMember | None:
        """
        title: Invoke the typed resolve class attribute member dependency.
        parameters:
          class_:
            type: SemanticClass
          field_name:
            type: str
          node:
            type: astx.AST
        returns:
          type: SemanticClassMember | None
        """
        del class_, field_name, node
        raise NotImplementedError


@private
@runtime_checkable
class ResolveClassFieldSlotCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self,
        class_: SemanticClass,
        member: SemanticClassMember,
        *,
        visible_name: str | None = None,
    ) -> SemanticClassLayoutField:
        """
        title: Invoke the typed resolve class field slot dependency.
        parameters:
          class_:
            type: SemanticClass
          member:
            type: SemanticClassMember
          visible_name:
            type: str | None
        returns:
          type: SemanticClassLayoutField
        """
        del class_, member, visible_name
        raise NotImplementedError


@private
@runtime_checkable
class ResolveClassFromTypeCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self,
        type_: astx.DataType | None,
        *,
        node: astx.AST,
        unknown_message: str,
    ) -> SemanticClass | None:
        """
        title: Invoke the typed resolve class from type dependency.
        parameters:
          type_:
            type: astx.DataType | None
          node:
            type: astx.AST
          unknown_message:
            type: str
        returns:
          type: SemanticClass | None
        """
        del type_, node, unknown_message
        raise NotImplementedError


@private
@runtime_checkable
class ResolveDeclaredTypeCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self,
        type_: astx.DataType,
        *,
        node: astx.AST,
        unknown_message: str = "Unknown type '{name}'",
        storage_required: bool = True,
    ) -> astx.DataType:
        """
        title: Invoke the typed resolve declared type dependency.
        parameters:
          type_:
            type: astx.DataType
          node:
            type: astx.AST
          unknown_message:
            type: str
          storage_required:
            type: bool
        returns:
          type: astx.DataType
        """
        del type_, node, unknown_message, storage_required
        raise NotImplementedError


@private
@runtime_checkable
class ListAssignmentOwnership(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self,
        node: astx.AST,
        value: astx.AST,
        symbol: SemanticSymbol,
        *,
        target_name: str,
        target_type: astx.DataType | None,
        is_local: bool,
    ) -> None:
        """
        title: Invoke the typed resolve list assignment ownership dependency.
        parameters:
          node:
            type: astx.AST
          value:
            type: astx.AST
          symbol:
            type: SemanticSymbol
          target_name:
            type: str
          target_type:
            type: astx.DataType | None
          is_local:
            type: bool
        """
        del node, value, symbol, target_name, target_type, is_local
        raise NotImplementedError


@private
@runtime_checkable
class ResolveMethodOverloadCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self,
        class_: SemanticClass,
        method_name: str,
        arg_types: list[astx.DataType | None],
        *,
        is_static: bool,
        node: astx.AST,
    ) -> tuple[SemanticClassMember, tuple[SemanticClassMember, ...]] | None:
        """
        title: Invoke the typed resolve method overload dependency.
        parameters:
          class_:
            type: SemanticClass
          method_name:
            type: str
          arg_types:
            type: list[astx.DataType | None]
          is_static:
            type: bool
          node:
            type: astx.AST
        returns:
          type: >-
            tuple[SemanticClassMember, tuple[SemanticClassMember, Ellipsis]] |
            None
        """
        del class_, method_name, arg_types, is_static, node
        raise NotImplementedError


@private
@runtime_checkable
class ResolveModuleMemberBindingCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self,
        module: SemanticModule,
        member_name: str,
        *,
        node: astx.AST,
        namespace_name: str,
    ) -> SemanticBinding | None:
        """
        title: Invoke the typed resolve module member binding dependency.
        parameters:
          module:
            type: SemanticModule
          member_name:
            type: str
          node:
            type: astx.AST
          namespace_name:
            type: str
        returns:
          type: SemanticBinding | None
        """
        del module, member_name, node, namespace_name
        raise NotImplementedError


@private
@runtime_checkable
class ResolveMutationTargetCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self,
        target: astx.AST,
        *,
        node: astx.AST,
        action: str,
        invalid_message: str,
    ) -> tuple[SemanticSymbol, str, astx.DataType | None] | None:
        """
        title: Invoke the typed resolve mutation target dependency.
        parameters:
          target:
            type: astx.AST
          node:
            type: astx.AST
          action:
            type: str
          invalid_message:
            type: str
        returns:
          type: tuple[SemanticSymbol, str, astx.DataType | None] | None
        """
        del target, node, action, invalid_message
        raise NotImplementedError


@private
@runtime_checkable
class ResolveNamedClassCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(self, name: str, *, node: astx.AST) -> SemanticClass | None:
        """
        title: Invoke the typed resolve named class dependency.
        parameters:
          name:
            type: str
          node:
            type: astx.AST
        returns:
          type: SemanticClass | None
        """
        del name, node
        raise NotImplementedError


@private
@runtime_checkable
class StringAssignmentOwnership(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self,
        node: astx.AST,
        value: astx.AST,
        symbol: SemanticSymbol,
        *,
        target_name: str,
        target_type: astx.DataType | None,
        is_local: bool,
    ) -> None:
        """
        title: Invoke the typed resolve string assignment ownership dependency.
        parameters:
          node:
            type: astx.AST
          value:
            type: astx.AST
          symbol:
            type: SemanticSymbol
          target_name:
            type: str
          target_type:
            type: astx.DataType | None
          is_local:
            type: bool
        """
        del node, value, symbol, target_name, target_type, is_local
        raise NotImplementedError


@private
@runtime_checkable
class ResolveStructFromTypeCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self,
        type_: astx.DataType | None,
        *,
        node: astx.AST,
        unknown_message: str,
    ) -> SemanticStruct | None:
        """
        title: Invoke the typed resolve struct from type dependency.
        parameters:
          type_:
            type: astx.DataType | None
          node:
            type: astx.AST
          unknown_message:
            type: str
        returns:
          type: SemanticStruct | None
        """
        del type_, node, unknown_message
        raise NotImplementedError


@private
@runtime_checkable
class SetModuleMemberResolutionCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self,
        node: astx.AST,
        *,
        module: SemanticModule,
        member_name: str,
        binding: SemanticBinding,
    ) -> None:
        """
        title: Invoke the typed set module member resolution dependency.
        parameters:
          node:
            type: astx.AST
          module:
            type: SemanticModule
          member_name:
            type: str
          binding:
            type: SemanticBinding
        """
        del node, module, member_name, binding
        raise NotImplementedError


@private
@runtime_checkable
class BufferLifetimeCheck(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self, *, node: astx.AST, view: astx.AST, operation: str
    ) -> None:
        """
        title: Invoke the typed validate buffer lifetime operation dependency.
        parameters:
          node:
            type: astx.AST
          view:
            type: astx.AST
          operation:
            type: str
        """
        del node, view, operation
        raise NotImplementedError


@private
@runtime_checkable
class BufferIndexCheck(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self,
        *,
        node: astx.AST,
        base: astx.AST,
        indices: list[astx.AST],
        is_store: bool,
    ) -> astx.DataType | None:
        """
        title: >-
          Invoke the typed validate buffer view index operation dependency.
        parameters:
          node:
            type: astx.AST
          base:
            type: astx.AST
          indices:
            type: list[astx.AST]
          is_store:
            type: bool
        returns:
          type: astx.DataType | None
        """
        del node, base, indices, is_store
        raise NotImplementedError


@private
@runtime_checkable
class ValidateTensorIndexOperationCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self,
        *,
        node: astx.AST,
        base: astx.AST,
        indices: list[astx.AST],
        is_store: bool,
    ) -> astx.DataType | None:
        """
        title: Invoke the typed validate tensor index operation dependency.
        parameters:
          node:
            type: astx.AST
          base:
            type: astx.AST
          indices:
            type: list[astx.AST]
          is_store:
            type: bool
        returns:
          type: astx.DataType | None
        """
        del node, base, indices, is_store
        raise NotImplementedError


@private
@runtime_checkable
class TensorLifetimeCheck(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(
        self, *, node: astx.AST, view: astx.AST, operation: str
    ) -> None:
        """
        title: Invoke the typed validate tensor lifetime operation dependency.
        parameters:
          node:
            type: astx.AST
          view:
            type: astx.AST
          operation:
            type: str
        """
        del node, view, operation
        raise NotImplementedError


@private
@runtime_checkable
class VisitModuleCallback(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(self, module: astx.Module, *, predeclared: bool) -> None:
        """
        title: Invoke the typed visit module dependency.
        parameters:
          module:
            type: astx.Module
          predeclared:
            type: bool
        """
        del module, predeclared
        raise NotImplementedError


@private
@runtime_checkable
class FileArgumentCheck(Protocol):
    """
    title: Preserve the dependency call shape, including named options.
    """

    def __call__(self, node: astx.MethodCall, *, public: bool = False) -> bool:
        """
        title: Invoke the typed free validate file method arguments dependency.
        parameters:
          node:
            type: astx.MethodCall
          public:
            type: bool
        returns:
          type: bool
        """
        del node, public
        raise NotImplementedError
