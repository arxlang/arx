"""
title: Class ownership, constructor binding, and bounded lifecycle validity.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Final, cast

import astx

from public import private

from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.numeric_literals import contextualize_literal
from irx.analysis.ownership import resource_ownership
from irx.analysis.resolved_nodes import (
    ClassLifecyclePhase,
    OwnershipEscapeKind,
    OwnershipKind,
    OwnershipTransferKind,
    ResourceKind,
    ResourceOwnership,
    SemanticClass,
    SemanticClassInitialization,
    SemanticSymbol,
)
from irx.analysis.types import is_assignable, is_string_type
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True)
class ClassHookSpec:
    """
    title: One language-defined class protocol, not a private method.
    attributes:
      name:
        type: str
      accepts_parameters:
        type: bool
      is_lifecycle:
        type: bool
    """

    name: str
    accepts_parameters: bool
    is_lifecycle: bool = True

    def __init__(
        self,
        name: str,
        accepts_parameters: bool,
        is_lifecycle: bool = True,
    ) -> None:
        """
        title: Validate hook specification inputs before freezing them.
        parameters:
          name:
            type: str
          accepts_parameters:
            type: bool
          is_lifecycle:
            type: bool
        """
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "accepts_parameters", accepts_parameters)
        object.__setattr__(self, "is_lifecycle", is_lifecycle)


INITIALIZER_HOOK: Final = ClassHookSpec("__init__", accepts_parameters=True)
FINALIZER_HOOK: Final = ClassHookSpec("__del__", accepts_parameters=False)
CONTEXT_ENTER_HOOK: Final = ClassHookSpec(
    "__enter__", accepts_parameters=True, is_lifecycle=False
)
CONTEXT_EXIT_HOOK: Final = ClassHookSpec(
    "__exit__", accepts_parameters=True, is_lifecycle=False
)
CLASS_HOOKS: Final[Mapping[str, ClassHookSpec]] = MappingProxyType(
    {
        hook.name: hook
        for hook in (
            INITIALIZER_HOOK,
            FINALIZER_HOOK,
            CONTEXT_ENTER_HOOK,
            CONTEXT_EXIT_HOOK,
        )
    }
)
LIFECYCLE_HOOKS: Final[Mapping[str, ClassHookSpec]] = MappingProxyType(
    {name: hook for name, hook in CLASS_HOOKS.items() if hook.is_lifecycle}
)
DUNDER_MIN_LENGTH: Final = 4


@private
@typechecked
def reject_hook_call(
    analyzer: SemanticAnalyzerCore, node: astx.AST, name: str
) -> bool:
    """
    title: Reject explicit calls to compiler-only lifecycle entry points.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.AST
      name:
        type: str
    returns:
      type: bool
    """
    if name not in LIFECYCLE_HOOKS:
        return False
    lifecycle_error(
        analyzer,
        node,
        f"lifecycle hook '{name}' cannot be called explicitly; "
        "construct with Class(...) and let ownership release the object",
    )
    return True


@private
@typechecked
def lifecycle_error(
    analyzer: SemanticAnalyzerCore, node: astx.AST, message: str
) -> None:
    """
    title: Reject an unsupported or unsafe lifecycle operation.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.AST
      message:
        type: str
    """
    analyzer.context.diagnostics.add(
        message, node=node, code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP
    )


@private
@typechecked
def field_resource(type_: astx.DataType | None) -> ResourceKind | None:
    """
    title: Classify supported owned instance storage during analysis.
    parameters:
      type_:
        type: astx.DataType | None
    returns:
      type: ResourceKind | None
    """
    if isinstance(type_, astx.ClassType):
        return ResourceKind.CLASS
    if isinstance(type_, astx.FileType):
        return ResourceKind.FILE
    if is_string_type(type_):
        return ResourceKind.STRING
    return None


@private
@typechecked
def unsupported_class_field(type_: astx.DataType) -> bool:
    """
    title: Preserve scalar unions while rejecting unmodeled field resources.
    parameters:
      type_:
        type: astx.DataType
    returns:
      type: bool
    """
    if isinstance(type_, astx.UnionType):
        return any(
            field_resource(member) is not None
            or unsupported_class_field(member)
            for member in type_.members
        )
    return isinstance(
        type_,
        (
            astx.ListType,
            astx.TensorType,
            astx.DataFrameType,
            astx.SeriesType,
            astx.GeneratorType,
            astx.BufferOwnerType,
            astx.BufferViewType,
        ),
    )


@private
@typechecked
def contains_class(type_: astx.DataType | None) -> bool:
    """
    title: Detect class references hidden in unsupported aggregate types.
    parameters:
      type_:
        type: astx.DataType | None
    returns:
      type: bool
    """
    if isinstance(type_, astx.ClassType):
        return True
    for name in (
        "element_types",
        "members",
        "element_type",
        "key_type",
        "value_type",
        "yield_type",
        "pointee_type",
        "bound",
    ):
        value = getattr(type_, name, None)
        if isinstance(value, astx.DataType) and contains_class(value):
            return True
        if isinstance(value, (tuple, list)) and any(
            isinstance(item, astx.DataType) and contains_class(item)
            for item in value
        ):
            return True
    return False


@private
@typechecked
def class_ownership(
    kind: OwnershipKind,
    *,
    symbol: str | None = None,
    transfer: OwnershipTransferKind = OwnershipTransferKind.NONE,
    escape: OwnershipEscapeKind = OwnershipEscapeKind.NONE,
) -> ResourceOwnership:
    """
    title: Describe one owned reference, not a unique object.
    parameters:
      kind:
        type: OwnershipKind
      symbol:
        type: str | None
      transfer:
        type: OwnershipTransferKind
      escape:
        type: OwnershipEscapeKind
    returns:
      type: ResourceOwnership
    """
    return ResourceOwnership(
        ResourceKind.CLASS,
        kind,
        owner_symbol_id=symbol if kind is OwnershipKind.OWNED else None,
        source_symbol_id=symbol,
        transfer_kind=transfer,
        escape_kind=escape,
    )


@private
@typechecked
def acquire_class(
    analyzer: SemanticAnalyzerCore,
    node: astx.AST,
    value: astx.AST | None,
    symbol: str | None = None,
) -> None:
    """
    title: Resolve an owned reference acquired by a binding, store, or return.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.AST
      value:
        type: astx.AST | None
      symbol:
        type: str | None
    """
    ownership = resource_ownership(value)
    operation = OwnershipTransferKind.COPY
    if (
        value is not None
        and ownership is not None
        and ownership.kind is OwnershipKind.OWNED
    ):
        operation = OwnershipTransferKind.MOVE
        analyzer._set_resource_ownership(
            value, replace(ownership, transfer_kind=operation)
        )
    analyzer._set_resource_ownership(
        node,
        class_ownership(
            OwnershipKind.OWNED, symbol=symbol, transfer=operation
        ),
    )


@private
@typechecked
def class_local(
    analyzer: SemanticAnalyzerCore,
    node: astx.VariableDeclaration | astx.InlineVariableDeclaration,
    symbol: SemanticSymbol,
) -> None:
    """
    title: Resolve a class reference owner without changing alias semantics.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.VariableDeclaration | astx.InlineVariableDeclaration
      symbol:
        type: SemanticSymbol
    """
    function = analyzer.context.current_function
    if (
        function is None
        or function.signature.metadata.get("generator") is not None
    ):
        lifecycle_error(
            analyzer,
            node,
            "owned class globals and generator locals are unsupported",
        )
        return
    acquire_class(analyzer, node, node.value, symbol.symbol_id)


@private
@typechecked
def lifecycle_plan(
    class_: SemanticClass, initialization: SemanticClassInitialization
) -> SemanticClassInitialization:
    """
    title: Resolve base-first phases from canonical field storage order.
    parameters:
      class_:
        type: SemanticClass
      initialization:
        type: SemanticClassInitialization
    returns:
      type: SemanticClassInitialization
    """
    owners: list[SemanticClass] = []

    def append(owner: SemanticClass) -> None:
        """
        title: Deduplicate shared ancestors in existing storage order.
        parameters:
          owner:
            type: SemanticClass
        """
        for base in owner.bases:
            append(base)
        if not any(
            item.qualified_name == owner.qualified_name for item in owners
        ):
            owners.append(owner)

    append(class_)
    phases = []
    for owner in owners:
        hooks = {
            member.name: member.lowered_function
            for member in owner.declared_members
            if member.name in LIFECYCLE_HOOKS
        }
        phases.append(
            ClassLifecyclePhase(
                owner.qualified_name,
                tuple(
                    item
                    for item in initialization.instance_initializers
                    if item.owner_qualified_name == owner.qualified_name
                ),
                hooks.get(INITIALIZER_HOOK.name),
                hooks.get(FINALIZER_HOOK.name),
            )
        )
    return replace(initialization, phases=tuple(phases))


@private
@typechecked
def constructor_arguments(
    analyzer: SemanticAnalyzerCore,
    node: astx.ClassConstruct | astx.FunctionCall | astx.MethodCall,
    class_: SemanticClass,
) -> tuple[
    tuple[astx.DataType, ...], tuple[int, ...], tuple[astx.DataType, ...]
]:
    """
    title: Bind constructor names while preserving supplied evaluation order.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.ClassConstruct | astx.FunctionCall | astx.MethodCall
      class_:
        type: SemanticClass
    returns:
      type: >-
        tuple[tuple[astx.DataType, Ellipsis], tuple[int, Ellipsis],
        tuple[astx.DataType, Ellipsis]]
    """
    assert class_.initialization is not None
    function = analyzer.context.current_function
    if (
        function is not None
        and function.signature.metadata.get("generator") is not None
    ):
        lifecycle_error(
            analyzer, node, "class construction in generators is unsupported"
        )
    if function is None:
        lifecycle_error(
            analyzer,
            node,
            "class construction requires a non-generator function",
        )
    phases = class_.initialization.phases
    initializer = phases[-1].initializer if phases else None
    params = list(initializer.prototype.args.nodes) if initializer else []
    positional = list(node.args)
    evaluations = list(positional)
    supplied: dict[str, int] = {}
    if len(positional) > len(params):
        lifecycle_error(analyzer, node, "too many constructor arguments")
    for param, index in zip(params, range(len(positional))):
        supplied[param.name] = index
    for item in node.keywords:
        if item.name == "self" or item.name not in {p.name for p in params}:
            lifecycle_error(
                analyzer, item, f"unknown constructor argument '{item.name}'"
            )
        elif item.name in supplied:
            lifecycle_error(
                analyzer, item, f"duplicate constructor argument '{item.name}'"
            )
        supplied[item.name] = len(evaluations)
        evaluations.append(item.value)
    for param in params:
        if param.name in supplied:
            contextualize_literal(
                evaluations[supplied[param.name]], param.type_
            )
    for value in evaluations:
        analyzer.visit(value)
    indices: list[int] = []
    for param in params:
        if param.name not in supplied:
            if isinstance(param.default, astx.Undefined):
                lifecycle_error(
                    analyzer,
                    node,
                    f"missing constructor argument '{param.name}'",
                )
                continue
            supplied[param.name] = len(evaluations)
            evaluations.append(cast(astx.DataType, param.default))
            analyzer.visit(param.default)
        index = supplied[param.name]
        indices.append(index)
        if not is_assignable(
            param.type_, analyzer._expr_type(evaluations[index])
        ):
            lifecycle_error(
                analyzer,
                evaluations[index],
                f"constructor argument '{param.name}' has incompatible type",
            )
    for phase in phases[:-1]:
        if phase.initializer and any(
            isinstance(arg.default, astx.Undefined)
            for arg in phase.initializer.prototype.args.nodes
        ):
            lifecycle_error(
                analyzer,
                node,
                "base constructor requires explicit arguments; "
                "forwarding is unsupported",
            )
    return (
        tuple(evaluations),
        tuple(indices),
        tuple(param.type_ for param in params),
    )


@private
@typechecked
def lifecycle_children(node: astx.AST) -> Iterator[astx.AST]:
    """
    title: Traverse source children without semantic/parent backreferences.
    parameters:
      node:
        type: astx.AST
    returns:
      type: Iterator[astx.AST]
    """
    for name, value in vars(node).items():
        if name in {"semantic", "parent", "type_", "loc"}:
            continue
        if isinstance(value, astx.AST):
            yield value
        elif isinstance(value, (tuple, list)):
            for item in value:
                if isinstance(item, astx.AST):
                    yield item


@private
@typechecked
def validate_hook(
    analyzer: SemanticAnalyzerCore, declaration: astx.FunctionDef
) -> None:
    """
    title: Forbid resurrection, receiver escape, and unsafe hook declarations.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      declaration:
        type: astx.FunctionDef
    """
    hook = CLASS_HOOKS.get(declaration.name)
    if hook is None:
        if (
            len(declaration.name) >= DUNDER_MIN_LENGTH
            and declaration.name.startswith("__")
            and declaration.name.endswith("__")
        ):
            analyzer.context.diagnostics.add(
                f"unsupported class hook '{declaration.name}'; "
                "dunder method names are reserved for language protocols; "
                f"supported hooks: {', '.join(CLASS_HOOKS)}",
                node=declaration,
                code=DiagnosticCodes.SEMANTIC_INVALID_FIELD_ACCESS,
            )
        return
    # Context hooks retain ordinary dispatch and their existing call-site
    # validation; lifecycle-only restrictions must not change that protocol.
    if not hook.is_lifecycle:
        return
    prototype = declaration.prototype
    if (
        getattr(prototype, "is_static", False)
        or getattr(prototype, "is_abstract", False)
        or getattr(prototype, "is_extern", False)
        or astx.is_template_node(prototype)
        or not isinstance(prototype.return_type, astx.NoneType)
        or (not hook.accepts_parameters and prototype.args.nodes)
    ):
        lifecycle_error(
            analyzer,
            declaration,
            f"invalid lifecycle hook signature for '{hook.name}'",
        )
    for arg in prototype.args.nodes:
        if not isinstance(arg.default, astx.Undefined) and not isinstance(
            arg.default, (astx.Literal, astx.UnaryOp)
        ):
            lifecycle_error(
                analyzer, arg, "constructor defaults must be literals"
            )

    def inspect(node: astx.AST, parent: astx.AST | None = None) -> None:
        """
        title: Allow the receiver only as the base of a field access.
        parameters:
          node:
            type: astx.AST
          parent:
            type: astx.AST | None
        """
        if isinstance(node, astx.Identifier) and node.name == "self":
            if not (
                (isinstance(parent, astx.FieldAccess) and parent.value is node)
                or (
                    isinstance(parent, astx.BaseFieldAccess)
                    and parent.receiver is node
                )
            ):
                lifecycle_error(
                    analyzer,
                    node,
                    "lifecycle self cannot escape or receive method calls",
                )
        for child in lifecycle_children(node):
            inspect(child, node)

    inspect(declaration.body)


@private
@typechecked
def validate_class_graph(analyzer: SemanticAnalyzerCore) -> None:
    """
    title: Reject strong ownership cycles including assignable subtypes.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
    """
    classes = tuple(analyzer.context.classes.values())
    edges: dict[str, set[str]] = {}
    for owner in classes:
        targets: set[str] = set()
        if owner.layout is not None:
            for field in owner.layout.instance_fields:
                type_ = field.member.type_
                if isinstance(type_, astx.ClassType):
                    for candidate in classes:
                        if any(
                            ancestor.qualified_name == type_.qualified_name
                            for ancestor in candidate.mro
                        ):
                            targets.add(candidate.qualified_name)
        edges[owner.qualified_name] = targets

    def cyclic(name: str, active: frozenset[str]) -> bool:
        """
        title: Detect a cycle without accepting subtype-hidden back edges.
        parameters:
          name:
            type: str
          active:
            type: frozenset[str]
        returns:
          type: bool
        """
        if name in active:
            return True
        return any(
            cyclic(target, active | {name}) for target in edges.get(name, ())
        )

    for owner in classes:
        if cyclic(owner.qualified_name, frozenset()):
            with analyzer.context.in_module(owner.module_key):
                lifecycle_error(
                    analyzer,
                    owner.declaration,
                    "cyclic class-field ownership is unsupported "
                    "(including subtypes)",
                )


@private
@typechecked
def resolve_store(
    analyzer: SemanticAnalyzerCore, node: astx.BinaryOp, symbol: SemanticSymbol
) -> bool:
    """
    title: Resolve managed storage before ordinary assignment validation.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.BinaryOp
      symbol:
        type: SemanticSymbol
    returns:
      type: bool
    """
    analyzer._semantic(node).resolved_resource_store = None
    analyzer._semantic(node).lifecycle_field_store = False
    target_type = analyzer._expr_type(node.lhs)
    kind = field_resource(target_type)
    info = analyzer._semantic(node.lhs)
    field = (
        info.resolved_class_field_access
        or info.resolved_base_class_field_access
    )
    if field is not None and kind is not None:
        analyzer._semantic(node).lifecycle_field_store = True
        value_info = resource_ownership(node.rhs)
        operation = OwnershipTransferKind.COPY
        if value_info and value_info.kind is OwnershipKind.OWNED:
            operation = OwnershipTransferKind.MOVE
            analyzer._set_resource_ownership(
                node.rhs, replace(value_info, transfer_kind=operation)
            )
        if kind is ResourceKind.FILE:
            function = analyzer.context.current_function
            if (
                function is None
                or not function.signature.metadata.get("is_class_initializer")
                or not isinstance(node.lhs, astx.FieldAccess)
                or not isinstance(node.lhs.value, astx.Identifier)
                or node.lhs.value.name != "self"
                or (
                    analyzer.context.current_class is not None
                    and field.member.owner_qualified_name
                    != analyzer.context.current_class.qualified_name
                )
                or analyzer._semantic(node.rhs).resolved_file_open is None
            ):
                lifecycle_error(
                    analyzer,
                    node,
                    "file fields require a fresh open in their owning "
                    f"{INITIALIZER_HOOK.name}; "
                    "replacement is unsupported",
                )
        analyzer._set_resource_ownership(
            node,
            ResourceOwnership(
                kind, OwnershipKind.OWNED, transfer_kind=operation
            ),
        )
        analyzer._semantic(node).resolved_resource_store = resource_ownership(
            node
        )
        analyzer._set_resource_ownership(
            node,
            ResourceOwnership(
                kind,
                OwnershipKind.BORROWED,
                transfer_kind=OwnershipTransferKind.BORROW,
            ),
        )
        return True
    if kind is ResourceKind.CLASS:
        if not isinstance(node.lhs, astx.Identifier):
            lifecycle_error(
                analyzer, node, "owning class statics are unsupported"
            )
        acquire_class(analyzer, node, node.rhs, symbol.symbol_id)
        analyzer._semantic(node).resolved_resource_store = resource_ownership(
            node
        )
        analyzer._set_resource_ownership(
            node, class_ownership(OwnershipKind.BORROWED)
        )
        return True
    return False


@private
@typechecked
def validate_file_fields(
    analyzer: SemanticAnalyzerCore, class_: SemanticClass
) -> None:
    """
    title: Prove exactly-once initialization of native file fields.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      class_:
        type: SemanticClass
    """
    from irx.analysis.builtin_file import (  # noqa: PLC0415
        is_native_file_class,
        validate_native_file_class,
    )

    if is_native_file_class(analyzer, class_):
        validate_native_file_class(analyzer, class_)
        return
    if class_.initialization is None:
        return
    phase = class_.initialization.phases[-1]
    required = {
        item.field.member.name
        for item in phase.fields
        if item.field.resource_kind is ResourceKind.FILE
    }
    initialized = {
        item.field.member.name
        for item in phase.fields
        if item.field.resource_kind is ResourceKind.FILE
        and item.value is not None
    }
    ready: set[str] = set()

    def initial_reads(node: astx.AST) -> None:
        """
        title: Reject reads of later fields during setup.
        parameters:
          node:
            type: astx.AST
        """
        if (
            isinstance(node, astx.FieldAccess)
            and isinstance(node.value, astx.Identifier)
            and node.value.name == "self"
        ):
            resolution = analyzer._semantic(node).resolved_class_field_access
            if (
                resolution is not None
                and resolution.field.owner_qualified_name
                == class_.qualified_name
                and node.field_name not in ready
            ):
                lifecycle_error(
                    analyzer, node, "field read before initialization"
                )
        for child in lifecycle_children(node):
            initial_reads(child)

    for item in phase.fields:
        if (
            item.field.resource_kind is ResourceKind.FILE
            and item.value is not None
            and analyzer._semantic(item.value).resolved_file_open is None
        ):
            lifecycle_error(
                analyzer,
                item.value,
                "file fields require a fresh open initializer",
            )
        if item.value is not None:
            initial_reads(item.value)
        if (
            item.value is not None
            or item.field.resource_kind is not ResourceKind.FILE
        ):
            ready.add(item.field.member.name)
    if not required:
        return

    def field_name(node: astx.AST) -> str | None:
        """
        title: Identify this phase's direct receiver file slots.
        parameters:
          node:
            type: astx.AST
        returns:
          type: str | None
        """
        if (
            isinstance(node, astx.FieldAccess)
            and isinstance(node.value, astx.Identifier)
            and node.value.name == "self"
            and node.field_name in required
        ):
            return node.field_name
        return None

    def reads(node: astx.AST, state: set[str]) -> None:
        """
        title: Reject a file read before initialization.
        parameters:
          node:
            type: astx.AST
          state:
            type: set[str]
        """
        name = field_name(node)
        if name is not None and name not in state:
            lifecycle_error(
                analyzer,
                node,
                f"file field '{name}' read before initialization",
            )
        for child in lifecycle_children(node):
            reads(child, state)

    def exits(node: astx.AST, state: set[str]) -> None:
        """
        title: Check normal constructor exits separately.
        parameters:
          node:
            type: astx.AST
          state:
            type: set[str]
        """
        if required - state:
            lifecycle_error(
                analyzer,
                node,
                "file fields must initialize on every constructor exit",
            )

    def flow(node: astx.AST, state: set[str]) -> set[str] | None:
        """
        title: Merge definite initialization over supported branches.
        parameters:
          node:
            type: astx.AST
          state:
            type: set[str]
        returns:
          type: set[str] | None
        """
        if isinstance(node, astx.Block):
            for child in node.nodes:
                result = flow(child, state)
                if result is None:
                    return None
                state = result
            return state
        if isinstance(node, astx.IfStmt):
            reads(node.condition, state)
            left = flow(node.then, set(state))
            right = (
                flow(node.else_, set(state))
                if node.else_ is not None
                else set(state)
            )
            if left is None:
                return right
            if right is None:
                return left
            return left & right
        if isinstance(node, astx.FunctionReturn):
            exits(node, state)
            return None
        if isinstance(node, astx.BinaryOp) and node.op_code == "=":
            name = field_name(node.lhs)
            if name is not None:
                reads(node.rhs, state)
                if name in state:
                    lifecycle_error(
                        analyzer, node, "file-field replacement is unsupported"
                    )
                return state | {name}

        def file_writes(child: astx.AST) -> bool:
            """
            title: Detect initialization hidden in loops or expressions.
            parameters:
              child:
                type: astx.AST
            returns:
              type: bool
            """
            if (
                isinstance(child, astx.BinaryOp)
                and child.op_code == "="
                and field_name(child.lhs) is not None
            ):
                return True
            return any(file_writes(item) for item in lifecycle_children(child))

        if file_writes(node):
            lifecycle_error(
                analyzer, node, "file initialization in loops is unsupported"
            )
        reads(node, state)
        return state

    if phase.initializer is None or phase.initializer.definition is None:
        exits(class_.declaration, initialized)
    else:
        remaining = flow(phase.initializer.definition.body, initialized)
        if remaining is not None:
            exits(phase.initializer.definition, remaining)
