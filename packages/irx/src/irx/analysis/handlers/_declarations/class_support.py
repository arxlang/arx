# mypy: disable-error-code=no-redef
# mypy: disable-error-code=attr-defined
# mypy: disable-error-code=untyped-decorator

"""
title: Declaration class-support helpers.
summary: Resolve inheritance metadata and shared class-member support logic
  used by declaration analysis.
"""

from __future__ import annotations

import astx

from irx.analysis.handlers.class_helpers import (
    ClassMemberFormattingVisitorMixin,
)
from irx.analysis.resolved_nodes import (
    ClassInitializationSourceKind,
    ClassMemberKind,
    FunctionSignature,
    SemanticClass,
    SemanticClassMember,
)
from irx.analysis.types import display_type_name
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked

MIN_SHARED_ANCESTOR_BASE_COUNT = 2


@typechecked
class DeclarationClassSupportVisitorMixin(ClassMemberFormattingVisitorMixin):
    """
    title: Declaration helpers for class inheritance and member metadata
    """

    def _visibility_rank(
        self,
        visibility: astx.VisibilityKind,
    ) -> int:
        """
        title: Return one normalized visibility rank.
        parameters:
          visibility: Visibility.
        returns: One normalized visibility rank.
        """
        return {
            astx.VisibilityKind.private: 1,
            astx.VisibilityKind.protected: 2,
            astx.VisibilityKind.public: 3,
        }[visibility]

    def _class_resolution_stack(self) -> list[SemanticClass]:
        """
        title: Return the active class-resolution stack.
        returns: The active class-resolution stack.
        """
        stack = getattr(self, "_active_class_resolution", None)
        if isinstance(stack, list):
            return stack
        created: list[SemanticClass] = []
        setattr(self, "_active_class_resolution", created)
        return created

    def _attribute_is_static(
        self,
        declaration: astx.VariableDeclaration,
    ) -> bool:
        """
        title: Return whether one class attribute uses static storage.
        parameters:
          declaration: Declaration being processed.
        returns: Whether one class attribute uses static storage.
        """
        raw_value = getattr(declaration, "is_static", None)
        if isinstance(raw_value, bool):
            return raw_value
        return bool(declaration.scope == astx.ScopeKind.global_)

    def _method_is_static(
        self,
        declaration: astx.FunctionDef,
    ) -> bool:
        """
        title: Return whether one class method is static.
        parameters:
          declaration: Declaration being processed.
        returns: Whether one class method is static.
        """
        raw_value = getattr(declaration.prototype, "is_static", None)
        if isinstance(raw_value, bool):
            return raw_value
        return False

    def _method_is_abstract(
        self,
        declaration: astx.FunctionDef,
    ) -> bool:
        """
        title: Return whether one class method is abstract.
        parameters:
          declaration: Declaration being processed.
        returns: Whether one class method is abstract.
        """
        raw_value = getattr(declaration.prototype, "is_abstract", None)
        if isinstance(raw_value, bool):
            return raw_value
        raw_value = getattr(declaration, "is_abstract", None)
        if isinstance(raw_value, bool):
            return raw_value
        return False

    def _class_is_declared_abstract(
        self,
        class_: SemanticClass,
    ) -> bool:
        """
        title: Return whether one class declaration is explicitly abstract.
        parameters:
          class_: Class being processed.
        returns: Whether one class declaration is explicitly abstract.
        """
        raw_value = getattr(class_.declaration, "is_abstract", None)
        if isinstance(raw_value, bool):
            return raw_value
        return class_.is_abstract

    def _initializer_source_kind(
        self,
        value: astx.AST | None,
    ) -> ClassInitializationSourceKind:
        """
        title: Return how one class attribute obtains its initial value.
        parameters:
          value: Value to process.
        returns: How one class attribute obtains its initial value.
        """
        if value is None or isinstance(value, astx.Undefined):
            return ClassInitializationSourceKind.DEFAULT
        return ClassInitializationSourceKind.DECLARATION

    def _static_initializer_is_supported(
        self,
        value: astx.AST | None,
    ) -> bool:
        """
        title: Return whether one static field initializer is deterministic
          now.
        parameters:
          value: Value to process.
        returns: Whether one static field initializer is deterministic now.
        """
        if value is None or isinstance(value, astx.Undefined):
            return True
        return isinstance(
            value,
            (
                astx.LiteralBoolean,
                astx.LiteralInt8,
                astx.LiteralInt16,
                astx.LiteralInt32,
                astx.LiteralInteger,
                astx.LiteralInt64,
                astx.LiteralUInt8,
                astx.LiteralUInt16,
                astx.LiteralUInt32,
                astx.LiteralUInt64,
                astx.LiteralUInt128,
                astx.LiteralFloat16,
                astx.LiteralFloat32,
                astx.LiteralFloat,
                astx.LiteralFloat64,
                astx.LiteralNone,
            ),
        )

    def _method_signature_key(
        self,
        method_name: str,
        signature: FunctionSignature,
        *,
        is_static: bool,
    ) -> str:
        """
        title: Return one canonical visible method signature key.
        parameters:
          method_name: Name of method.
          signature: Resolved callable signature.
          is_static: Whether the member belongs to the class rather than
            an instance.
        returns: One canonical visible method signature key.
        """
        dispatch_kind = "static" if is_static else "instance"
        parameters = ",".join(
            display_type_name(parameter.type_)
            for parameter in signature.parameters
        )
        variadic = "variadic" if signature.is_variadic else "fixed"
        return (
            f"{dispatch_kind}|{method_name}|"
            f"{signature.calling_convention.value}|{variadic}|"
            f"({parameters})->{display_type_name(signature.return_type)}"
        )

    def _method_call_key_from_signature(
        self,
        method_name: str,
        signature: FunctionSignature,
        *,
        is_static: bool,
    ) -> str:
        """
        title: Return one overload-selection key without the return type.
        parameters:
          method_name: Name of method.
          signature: Resolved callable signature.
          is_static: Whether the member belongs to the class rather than
            an instance.
        returns: One overload-selection key without the return type.
        """
        dispatch_kind = "static" if is_static else "instance"
        parameters = ",".join(
            display_type_name(parameter.type_)
            for parameter in signature.parameters
        )
        variadic = "variadic" if signature.is_variadic else "fixed"
        return (
            f"{dispatch_kind}|{method_name}|"
            f"{signature.calling_convention.value}|{variadic}|"
            f"({parameters})"
        )

    def _member_call_key(self, member: SemanticClassMember) -> str:
        """
        title: Return one overload-selection key for a class method member.
        parameters:
          member: Member.
        returns: One overload-selection key for a class method member.
        """
        if member.signature is None:
            raise TypeError("class method must carry a visible signature")
        return self._method_call_key_from_signature(
            member.name,
            member.signature,
            is_static=member.is_static,
        )

    def _declared_member_tables(
        self,
        declared_members: tuple[SemanticClassMember, ...],
    ) -> tuple[
        dict[str, SemanticClassMember],
        dict[str, tuple[SemanticClassMember, ...]],
    ]:
        """
        title: Build the declared member tables for one class.
        parameters:
          declared_members: Declared members.
        returns: Constructed the declared member tables for one class.
        """
        declared_member_table: dict[str, SemanticClassMember] = {}
        declared_method_groups: dict[str, list[SemanticClassMember]] = {}

        for member in declared_members:
            if member.kind is ClassMemberKind.ATTRIBUTE:
                declared_member_table[member.name] = member
                continue
            declared_method_groups.setdefault(member.name, []).append(member)

        normalized_method_groups = {
            name: tuple(group)
            for name, group in declared_method_groups.items()
        }
        for name, group in normalized_method_groups.items():
            if len(group) == 1:
                declared_member_table[name] = group[0]

        return declared_member_table, normalized_method_groups

    def _ancestor_declared_attributes(
        self,
        mro: tuple[SemanticClass, ...],
    ) -> dict[str, tuple[SemanticClassMember, ...]]:
        """
        title: Collect visible ancestor attributes in MRO order.
        parameters:
          mro: Mro.
        returns: Collected visible ancestor attributes in MRO order.
        """
        members: dict[str, list[SemanticClassMember]] = {}
        for ancestor in mro[1:]:
            for member in ancestor.declared_members:
                if member.visibility is astx.VisibilityKind.private:
                    continue
                if member.kind is not ClassMemberKind.ATTRIBUTE:
                    continue
                members.setdefault(member.name, []).append(member)
        return {name: tuple(group) for name, group in members.items()}

    def _ancestor_declared_method_groups(
        self,
        mro: tuple[SemanticClass, ...],
    ) -> dict[str, tuple[SemanticClassMember, ...]]:
        """
        title: Collect visible ancestor method overload groups in MRO order.
        parameters:
          mro: Mro.
        returns: Collected visible ancestor method overload groups in MRO
          order.
        """
        groups: dict[str, list[SemanticClassMember]] = {}
        for ancestor in mro[1:]:
            for member in ancestor.declared_members:
                if member.visibility is astx.VisibilityKind.private:
                    continue
                if member.kind is not ClassMemberKind.METHOD:
                    continue
                groups.setdefault(member.name, []).append(member)
        return {name: tuple(group) for name, group in groups.items()}

    def _resolve_class_bases(
        self,
        class_: SemanticClass,
    ) -> tuple[SemanticClass, ...]:
        """
        title: Resolve the direct base-class list for one class.
        parameters:
          class_: Class being processed.
        returns: Resolved the direct base-class list for one class.
        """
        resolved: list[SemanticClass] = []
        seen: set[str] = set()
        active_stack = self._class_resolution_stack()
        active_identities = {item.qualified_name for item in active_stack}

        for base_type in class_.declaration.bases:
            base = self._resolve_class_from_type(
                base_type,
                node=base_type,
                unknown_message="Unknown base class '{name}'",
            )
            if base is None:
                continue
            if base.qualified_name == class_.qualified_name:
                self.context.diagnostics.add(
                    f"Class '{class_.name}' cannot inherit from itself",
                    node=base_type,
                    code=DiagnosticCodes.SEMANTIC_DUPLICATE_DECLARATION,
                )
                continue
            if base.qualified_name in seen:
                self.context.diagnostics.add(
                    f"Class '{class_.name}' repeats base class '{base.name}'",
                    node=base_type,
                    code=DiagnosticCodes.SEMANTIC_DUPLICATE_DECLARATION,
                )
                continue
            if base.qualified_name in active_identities:
                cycle_names = " -> ".join(
                    [item.name for item in active_stack] + [base.name]
                )
                self.context.diagnostics.add(
                    f"inheritance cycle is invalid: {cycle_names}",
                    node=base_type,
                    code=DiagnosticCodes.SEMANTIC_DUPLICATE_DECLARATION,
                )
                continue
            seen.add(base.qualified_name)
            resolved.append(self._resolve_class_structure(base))

        return tuple(resolved)

    def _compute_class_mro(
        self,
        class_: SemanticClass,
        bases: tuple[SemanticClass, ...],
    ) -> tuple[SemanticClass, ...]:
        """
        title: Compute one deterministic class linearization.
        parameters:
          class_: Class being processed.
          bases: Bases.
        returns: Computed one deterministic class linearization.
        """
        if not bases:
            return (class_,)

        sequences: list[list[SemanticClass]] = [
            list(base.mro or (base,)) for base in bases
        ] + [list(bases)]
        result: list[SemanticClass] = [class_]

        while True:
            sequences = [sequence for sequence in sequences if sequence]
            if not sequences:
                return tuple(result)

            candidate: SemanticClass | None = None
            for sequence in sequences:
                head = sequence[0]
                if any(
                    head.qualified_name == later.qualified_name
                    for other in sequences
                    for later in other[1:]
                ):
                    continue
                candidate = head
                break

            if candidate is None:
                base_names = ", ".join(base.name for base in bases)
                self.context.diagnostics.add(
                    (
                        f"Class '{class_.name}' has no consistent MRO "
                        f"for bases {base_names}"
                    ),
                    node=class_.declaration,
                    code=DiagnosticCodes.SEMANTIC_DUPLICATE_DECLARATION,
                )
                return (class_, *bases)

            result.append(candidate)
            for sequence in sequences:
                if sequence and (
                    sequence[0].qualified_name == candidate.qualified_name
                ):
                    sequence.pop(0)

    def _shared_class_ancestors(
        self,
        bases: tuple[SemanticClass, ...],
        mro: tuple[SemanticClass, ...],
    ) -> tuple[SemanticClass, ...]:
        """
        title: Return ancestors reachable through more than one base lineage.
        parameters:
          bases: Bases.
          mro: Mro.
        returns: Ancestors reachable through more than one base lineage.
        """
        if len(bases) < MIN_SHARED_ANCESTOR_BASE_COUNT:
            return ()

        counts: dict[str, int] = {}
        for base in bases:
            lineage_seen: set[str] = set()
            for ancestor in base.mro or (base,):
                if ancestor.qualified_name in lineage_seen:
                    continue
                lineage_seen.add(ancestor.qualified_name)
                counts[ancestor.qualified_name] = (
                    counts.get(ancestor.qualified_name, 0) + 1
                )

        return tuple(
            ancestor
            for ancestor in mro[1:]
            if counts.get(ancestor.qualified_name, 0) > 1
        )

    def _class_storage_ancestors(
        self,
        bases: tuple[SemanticClass, ...],
    ) -> tuple[SemanticClass, ...]:
        """
        title: Return the canonical ancestor storage order for one class.
        parameters:
          bases: Bases.
        returns: The canonical ancestor storage order for one class.
        """
        ordered: list[SemanticClass] = []
        seen: set[str] = set()

        def visit(base: SemanticClass) -> None:
            """
            title: Visit one base lineage for canonical storage ordering.
            parameters:
              base: Base value or declaration.
            """
            for ancestor in base.bases:
                visit(ancestor)
            if base.qualified_name in seen:
                return
            seen.add(base.qualified_name)
            ordered.append(base)

        for base in bases:
            visit(base)
        return tuple(ordered)

    def _member_dominates(
        self,
        dominant: SemanticClass,
        other: SemanticClass,
    ) -> bool:
        """
        title: Return whether one owner dominates another in inheritance.
        parameters:
          dominant: Dominant.
          other: Other value participating in the operation.
        returns: Whether one owner dominates another in inheritance.
        """
        if dominant.qualified_name == other.qualified_name:
            return True
        return any(
            ancestor.qualified_name == other.qualified_name
            for ancestor in dominant.mro[1:]
        )

    def _dominant_inherited_method(
        self,
        candidates: tuple[SemanticClassMember, ...],
    ) -> SemanticClassMember | None:
        """
        title: Return the unique dominant inherited method, if any.
        parameters:
          candidates: Candidates.
        returns: The unique dominant inherited method, if any.
        """
        if not candidates:
            return None
        selected = candidates[0]
        selected_owner = self.context.get_class(
            self._member_owner_module_key(selected),
            selected.owner_name,
        )
        if selected_owner is None:
            return None
        for candidate in candidates[1:]:
            owner = self.context.get_class(
                self._member_owner_module_key(candidate),
                candidate.owner_name,
            )
            if owner is None:
                return None
            if not self._member_dominates(selected_owner, owner):
                return None
        return selected
