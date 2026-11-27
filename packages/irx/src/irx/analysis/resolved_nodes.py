"""
title: Sidecar semantic dataclasses attached to AST nodes.
summary: Define the semantic sidecar objects that analysis attaches to AST
  nodes and reuses during lowering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

import astx

from public import private, public

from irx.analysis.extensions.records import CallOperation
from irx.analysis.facts import SemanticFacts
from irx.analysis.flow import FlowOutcome
from irx.analysis.module_interfaces import ModuleKey
from irx.analysis.numeric_policy import (
    NumericConversion,
    classify_numeric_conversion,
)
from irx.typecheck import typechecked


@private
@typechecked
class FailedInferenceType(astx.DataType):
    """
    title: Track a value whose declaration already failed type inference.
    summary: This analysis-only type keeps name lookup available after an
      error. It carries no storage or lowering contract.
    """


@public
@typechecked
@dataclass(frozen=True)
class SemanticSymbol:
    """
    title: Resolved symbol information.
    summary: Describe one resolved variable-like symbol, including its stable
      semantic id and declared type.
    attributes:
      symbol_id: Identifier for symbol.
      name: Name identifying this declaration.
      type_: Type associated with this expression.
      is_mutable: Whether is mutable.
      kind: Kind of value or operation.
      declaration: Declaration being processed.
      module_key: Canonical module identity.
      qualified_name: Name of qualified.
    """

    symbol_id: str
    name: str
    type_: astx.DataType
    is_mutable: bool
    kind: str
    declaration: astx.AST | None = None
    module_key: ModuleKey = field(default_factory=lambda: "<unknown>")
    qualified_name: str = ""


@private
@typechecked
@dataclass(frozen=True)
class ResolvedBorrow:
    """
    title: Address transfer between a local place and a lexical borrow slot.
    attributes:
      target: Borrow binding storing the address.
      source: Local binding whose address is borrowed.
      access: Access granted by the borrow.
    """

    target: SemanticSymbol
    source: SemanticSymbol
    access: astx.BorrowAccess


@public
@typechecked
@dataclass(frozen=True, init=False)
class ResolvedModuleStorage:
    """
    title: Validated static storage for one module scalar binding.
    summary: The symbol supplies identity, declared type and mutability.
      Initializers are already converted scalar constants; None denotes an
      invalid nullable payload, never an uninitialized ordinary scalar. No
      runtime init or owned module lifecycle is authorized by this plan.
    attributes:
      symbol: Resolved symbol for the operation.
      initializer: Expression providing the initial value.
    """

    symbol: SemanticSymbol
    initializer: int | float | bool | None

    def __init__(
        self,
        symbol: SemanticSymbol,
        initializer: int | float | bool | None,
    ) -> None:
        """
        title: Validate runtime argument types for module storage metadata.
        parameters:
          symbol: Resolved symbol for the operation.
          initializer: Expression providing the initial value.
        """
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "initializer", initializer)


@public
@typechecked
class ResourceKind(str, Enum):
    """
    title: Runtime-managed resource categories.
    summary: Identify the concrete runtime resource whose lifetime is described
      by an ownership sidecar.
    """

    GENERATOR = "generator"
    LIST = "list"
    STRING = "string"
    FILE = "file"
    CLASS = "class"
    DATAFRAME = "dataframe"
    SERIES = "series"


@public
@typechecked
class OwnershipKind(str, Enum):
    """
    title: Semantic resource ownership classes.
    summary: Distinguish values responsible for cleanup from borrowed and
      static values that must not be released by the current expression or
      binding.
    """

    OWNED = "owned"
    BORROWED = "borrowed"
    STATIC = "static"
    OWNED_OR_STATIC = "owned_or_static"


@public
@typechecked
class OwnershipTransferKind(str, Enum):
    """
    title: Semantic resource transfer operations.
    """

    NONE = "none"
    BORROW = "borrow"
    COPY = "copy"
    MOVE = "move"


@public
@typechecked
class OwnershipEscapeKind(str, Enum):
    """
    title: Semantic resource escape boundaries.
    """

    NONE = "none"
    CALL = "call"
    RETURN = "return"


@public
@typechecked
@dataclass(frozen=True)
class ResourceOwnership:
    """
    title: Resolved ownership and escape metadata for one resource value.
    attributes:
      resource_kind: Resource kind.
      kind: Kind of value or operation.
      owner_symbol_id: Identifier for owner symbol.
      source_symbol_id: Identifier for source symbol.
      transfer_kind: Transfer kind.
      escape_kind: Escape kind.
    """

    resource_kind: ResourceKind
    kind: OwnershipKind
    owner_symbol_id: str | None = None
    source_symbol_id: str | None = None
    transfer_kind: OwnershipTransferKind = OwnershipTransferKind.NONE
    escape_kind: OwnershipEscapeKind = OwnershipEscapeKind.NONE


@public
@typechecked
@dataclass(frozen=True)
class SemanticStruct:
    """
    title: Resolved struct information.
    summary: Describe one top-level struct declaration with module-aware
      identity.
    attributes:
      symbol_id: Identifier for symbol.
      name: Name identifying this declaration.
      module_key: Canonical module identity.
      qualified_name: Name of qualified.
      declaration: Declaration being processed.
      fields: Declared fields.
      field_indices: Field indices.
    """

    symbol_id: str
    name: str
    module_key: ModuleKey
    qualified_name: str
    declaration: astx.StructDefStmt
    fields: tuple["SemanticStructField", ...] = ()
    field_indices: dict[str, int] = field(default_factory=dict)


@public
@typechecked
@dataclass(frozen=True)
class SemanticStructField:
    """
    title: Resolved struct field information.
    summary: Describe one ordered field within a semantic struct, including
      its stable index and resolved field type.
    attributes:
      name: Name identifying this declaration.
      index: Index selecting the item.
      type_: Type associated with this expression.
      declaration: Declaration being processed.
    """

    name: str
    index: int
    type_: astx.DataType
    declaration: astx.VariableDeclaration


@public
@typechecked
class ParameterPassingKind(str, Enum):
    """
    title: Stable semantic parameter-passing modes.
    summary: Classify how one semantic parameter is passed across the callable
      boundary.
    attributes:
      borrow_prefix: The source prefix for the passing mode.
    """

    BY_VALUE = "by_value"
    READ_ONLY_BORROW = "read_only_borrow"
    EXCLUSIVE_BORROW = "exclusive_borrow"

    @classmethod
    def from_access(
        cls, access: astx.BorrowAccess | None
    ) -> ParameterPassingKind:
        """
        title: Normalize a declared or supplied borrow mode.
        parameters:
          access: Explicit access mode, if present.
        returns: Canonical passing mode.
        """
        if access is astx.BorrowAccess.read_only:
            return cls.READ_ONLY_BORROW
        if access is astx.BorrowAccess.exclusive:
            return cls.EXCLUSIVE_BORROW
        return cls.BY_VALUE

    @property
    def borrow_prefix(self) -> str:
        """
        title: Render the explicit prefix required at the call boundary.
        returns: Borrow prefix or an empty string for by-value arguments.
        """
        if self is ParameterPassingKind.READ_ONLY_BORROW:
            return "&"
        if self is ParameterPassingKind.EXCLUSIVE_BORROW:
            return "&&"
        return ""


@public
@typechecked
class CallingConvention(str, Enum):
    """
    title: Stable semantic calling-convention classes.
    summary: Distinguish IRx-native callable semantics from C/native interop
      callables even when lowering currently emits the same LLVM calling
      convention.
    """

    IRX_DEFAULT = "irx_default"
    C = "c"


@public
@typechecked
class FFIAdmissibility(str, Enum):
    """
    title: Stable semantic FFI admissibility classes.
    summary: Distinguish regular IRx callables from callables that satisfy
      the public FFI contract.
    """

    INTERNAL_ONLY = "internal_only"
    PUBLIC = "public"


@public
@typechecked
class FFILinkStrategy(str, Enum):
    """
    title: Stable semantic native symbol-resolution strategies.
    summary: Describe whether an extern symbol relies only on the system
      linker or on one or more explicit runtime features.
    """

    SYSTEM_LINKER = "system_linker"
    RUNTIME_FEATURES = "runtime_features"


@public
@typechecked
class FFITypeClass(str, Enum):
    """
    title: Stable semantic FFI type classes.
    summary: Classify the narrow set of public ABI-safe value categories
      supported by IRx's current FFI contract.
    """

    BOOLEAN = "boolean"
    FLOAT = "float"
    INTEGER = "integer"
    OPAQUE_HANDLE = "opaque_handle"
    POINTER = "pointer"
    STRING = "string"
    STRUCT = "struct"
    VOID = "void"


@public
@typechecked
@dataclass(frozen=True)
class FFITypeInfo:
    """
    title: One canonical semantic FFI type description.
    summary: Describe how one semantically validated public FFI type
      participates in the stable ABI contract.
    attributes:
      classification: Classification.
      display_name: Name of display.
      metadata: Metadata associated with the operation.
    """

    classification: FFITypeClass
    display_name: str
    metadata: dict[str, Any] = field(default_factory=dict)


@public
@typechecked
@dataclass(frozen=True)
class FFICallableInfo:
    """
    title: Canonical public FFI callable metadata.
    summary: Record the validated FFI classification, type categories, symbol
      resolution strategy, and runtime-feature dependencies for one extern
      callable.
    attributes:
      admissibility: Admissibility.
      parameters: Declared callable parameters.
      return_type: Declared result type.
      required_runtime_features: Required runtime features.
      link_strategy: Link strategy.
    """

    admissibility: FFIAdmissibility
    parameters: tuple[FFITypeInfo, ...]
    return_type: FFITypeInfo
    required_runtime_features: tuple[str, ...] = ()
    link_strategy: FFILinkStrategy = FFILinkStrategy.SYSTEM_LINKER


@public
@typechecked
@dataclass(frozen=True)
class ParameterSpec:
    """
    title: One canonical semantic parameter specification.
    summary: Describe one ordered callable parameter together with
      its declared type and passing policy, plus stable metadata
      such as default fingerprints.
    attributes:
      name: Name identifying this declaration.
      type_: Type associated with this expression.
      passing_kind: Passing kind.
      metadata: Metadata associated with the operation.
    """

    name: str
    type_: astx.DataType
    passing_kind: ParameterPassingKind = ParameterPassingKind.BY_VALUE
    metadata: dict[str, Any] = field(default_factory=dict)


@public
@typechecked
@dataclass(frozen=True)
class FunctionSignature:
    """
    title: Canonical semantic callable signature.
    summary: Normalize the stable callable contract that semantic analysis
      resolves and lowering consumes.
    attributes:
      name: Name identifying this declaration.
      parameters: Declared callable parameters.
      return_type: Declared result type.
      calling_convention: Calling convention.
      is_variadic: Whether is variadic.
      is_extern: Whether is extern.
      exception_abi: Generated functions return status and receive context
        plus a typed output slot for non-none results. Externs retain their
        declared ABI.
      symbol_name: Name of symbol.
      required_runtime_features: Required runtime features.
      ffi: FFI.
      metadata: Metadata associated with the operation.
      operation: Operation to resolve or execute.
    """

    name: str
    parameters: tuple[ParameterSpec, ...]
    return_type: astx.DataType
    calling_convention: CallingConvention
    is_variadic: bool = False
    is_extern: bool = False
    exception_abi: bool = True
    symbol_name: str = ""
    required_runtime_features: tuple[str, ...] = ()
    ffi: FFICallableInfo | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    operation: CallOperation | None = None


@public
@typechecked
class ClassMemberKind(str, Enum):
    """
    title: Stable semantic class-member categories.
    summary: Distinguish fields from methods inside one class member namespace.
    """

    ATTRIBUTE = "attribute"
    METHOD = "method"


@public
@typechecked
class ClassMemberResolutionKind(str, Enum):
    """
    title: Stable class-member resolution categories.
    summary: Distinguish members declared locally, members that override
      inherited declarations, and members inherited directly from the resolved
      MRO.
    """

    DECLARED = "declared"
    OVERRIDE = "override"
    INHERITED = "inherited"


@public
@typechecked
@dataclass(frozen=True)
class SemanticClassMember:
    """
    title: Canonical semantic class-member record.
    summary: Normalize one declared class member so later phases can reason
      about visibility, storage, mutability, and overrides without re-reading
      raw AST modifier fields.
    attributes:
      symbol_id: Identifier for symbol.
      name: Name identifying this declaration.
      qualified_name: Name of qualified.
      owner_name: Name of owner.
      owner_qualified_name: Name of owner qualified.
      kind: Kind of value or operation.
      visibility: Visibility.
      is_static: Whether the member belongs to the class rather than an
        instance.
      is_abstract: Whether is abstract.
      is_constant: Whether is constant.
      is_mutable: Whether is mutable.
      declaration: Declaration being processed.
      type_: Type associated with this expression.
      signature: Resolved callable signature.
      signature_key: Signature key.
      overrides: Overrides.
      dispatch_slot: Dispatch slot.
      lowered_function: Lowered function.
    """

    symbol_id: str
    name: str
    qualified_name: str
    owner_name: str
    owner_qualified_name: str
    kind: ClassMemberKind
    visibility: astx.VisibilityKind
    is_static: bool
    is_abstract: bool
    is_constant: bool
    is_mutable: bool
    declaration: astx.AST
    type_: astx.DataType | None = None
    signature: FunctionSignature | None = None
    signature_key: str | None = None
    overrides: str | None = None
    dispatch_slot: int | None = None
    lowered_function: "SemanticFunction" | None = None


@public
@typechecked
@dataclass(frozen=True)
class SemanticClassMemberResolution:
    """
    title: Canonical class-member lookup resolution.
    summary: Record the ordered candidate set that one class member name
      considered and the member that won after deterministic inheritance
      resolution.
    attributes:
      name: Name identifying this declaration.
      kind: Kind of value or operation.
      selected: Selected.
      candidates: Candidates.
      signature_key: Signature key.
    """

    name: str
    kind: ClassMemberResolutionKind
    selected: SemanticClassMember
    candidates: tuple[SemanticClassMember, ...] = ()
    signature_key: str | None = None


@public
@typechecked
class ClassObjectRepresentationKind(str, Enum):
    """
    title: Stable class object-representation categories.
    summary: Distinguish whether class values are modeled as pointers or
      values.
    """

    POINTER = "pointer"


@public
@typechecked
class MethodDispatchKind(str, Enum):
    """
    title: Stable method-dispatch categories.
    summary: Distinguish direct method calls from dispatch-table-driven
      instance calls.
    """

    DIRECT = "direct"
    INDIRECT = "indirect"


@public
@typechecked
class ClassHeaderFieldKind(str, Enum):
    """
    title: Stable class-header field categories.
    summary: Name the reserved object-header slots that later lowering and
      dispatch phases can populate without changing the class object layout.
    """

    TYPE_DESCRIPTOR = "type_descriptor"
    DISPATCH_TABLE = "dispatch_table"
    LIFETIME = "lifetime"


@public
@typechecked
@dataclass(frozen=True)
class SemanticClassHeaderField:
    """
    title: One reserved class-object header slot.
    summary: Describe one hidden header entry that occupies a stable index
      in every class object representation.
    attributes:
      name: Name identifying this declaration.
      kind: Kind of value or operation.
      storage_index: Index selecting storage.
    """

    name: str
    kind: ClassHeaderFieldKind
    storage_index: int


@public
@typechecked
@dataclass(frozen=True)
class SemanticClassLayoutField:
    """
    title: One resolved instance-field storage slot.
    summary: Record the stable storage position for one declared instance
      attribute in the flattened class-object layout.
    attributes:
      member: Member.
      logical_index: Index selecting logical.
      storage_index: Index selecting storage.
      owner_name: Name of owner.
      owner_qualified_name: Name of owner qualified.
      resource_kind: Resource kind.
      access_index: Index selecting access.
    """

    member: SemanticClassMember
    logical_index: int
    storage_index: int
    owner_name: str
    owner_qualified_name: str
    resource_kind: ResourceKind | None = None
    access_index: int = 0


@public
@typechecked
@dataclass(frozen=True)
class SemanticClassStaticStorage:
    """
    title: One resolved static-member storage record.
    summary: Describe the module-global storage backing one declared static
      class attribute.
    attributes:
      member: Member.
      global_name: Name of global.
      owner_name: Name of owner.
      owner_qualified_name: Name of owner qualified.
    """

    member: SemanticClassMember
    global_name: str
    owner_name: str
    owner_qualified_name: str


@public
@typechecked
@dataclass(frozen=True)
class SemanticClassMethodDispatch:
    """
    title: One resolved class-method dispatch entry.
    summary: Record the stable dispatch slot and lowered function
      implementation for one visible instance method.
    attributes:
      member: Member.
      function: Function to process.
      slot_index: Index selecting slot.
      owner_name: Name of owner.
      owner_qualified_name: Name of owner qualified.
    """

    member: SemanticClassMember
    function: "SemanticFunction"
    slot_index: int
    owner_name: str
    owner_qualified_name: str


@public
@typechecked
class ClassInitializationSourceKind(str, Enum):
    """
    title: Stable class-initialization source categories.
    summary: Distinguish declaration-provided field initializers from implicit
      default construction values.
    """

    DECLARATION = "declaration"
    DEFAULT = "default"


@public
@typechecked
@dataclass(frozen=True)
class SemanticClassFieldInitializer:
    """
    title: One resolved instance-field initialization step.
    summary: Record the ordered value source for one instance field during
      default class construction.
    attributes:
      field: Field to process.
      source_kind: Source kind.
      value: Stored value.
      owner_name: Name of owner.
      owner_qualified_name: Name of owner qualified.
    """

    field: SemanticClassLayoutField
    source_kind: ClassInitializationSourceKind
    value: astx.AST | None
    owner_name: str
    owner_qualified_name: str


@public
@typechecked
@dataclass(frozen=True)
class SemanticClassStaticInitializer:
    """
    title: One resolved static-field initialization step.
    summary: Record the deterministic module-global initializer source for
      one static class attribute.
    attributes:
      storage: Storage.
      source_kind: Source kind.
      value: Stored value.
      owner_name: Name of owner.
      owner_qualified_name: Name of owner qualified.
    """

    storage: SemanticClassStaticStorage
    source_kind: ClassInitializationSourceKind
    value: astx.AST | None
    owner_name: str
    owner_qualified_name: str


@public
@typechecked
@dataclass(frozen=True)
class SemanticClassInitialization:
    """
    title: Canonical class construction and initialization plan.
    summary: Normalize the ordered instance-field and static-field
      initialization plan that semantic analysis resolves for one
      class.
    attributes:
      instance_initializers: Instance initializers.
      static_initializers: Static initializers.
      phases: Phases.
    """

    instance_initializers: tuple[SemanticClassFieldInitializer, ...] = ()
    static_initializers: tuple[SemanticClassStaticInitializer, ...] = ()
    phases: tuple[ClassLifecyclePhase, ...] = ()


@public
@typechecked
@dataclass(frozen=True)
class ClassLifecyclePhase:
    """
    title: One canonical initialization and destruction phase.
    attributes:
      owner: Owner keeping the resource alive.
      fields: Declared fields.
      initializer: Expression providing the initial value.
      destructor: Destructor.
    """

    owner: str
    fields: tuple[SemanticClassFieldInitializer, ...]
    initializer: SemanticFunction | None = None
    destructor: SemanticFunction | None = None


@public
@typechecked
@dataclass(frozen=True)
class SemanticClassLayout:
    """
    title: Canonical class-object layout metadata.
    summary: Normalize the low-level object representation, hidden header
      slots, flattened instance-field storage, and static-global storage
      names for one class.
    attributes:
      llvm_name: Name of LLVM.
      object_representation: Object representation.
      descriptor_global_name: Name of descriptor global.
      dispatch_global_name: Name of dispatch global.
      header_fields: Header fields.
      instance_fields: Instance fields.
      field_slots: Field slots.
      visible_field_slots: Visible field slots.
      dispatch_entries: Dispatch entries.
      dispatch_slots: Dispatch slots.
      visible_method_slots: Visible method slots.
      dispatch_table_size: Size of dispatch table.
      static_fields: Static fields.
      static_storage: Static storage.
      visible_static_storage: Visible static storage.
    """

    llvm_name: str
    object_representation: ClassObjectRepresentationKind
    descriptor_global_name: str
    dispatch_global_name: str
    header_fields: tuple[SemanticClassHeaderField, ...] = ()
    instance_fields: tuple[SemanticClassLayoutField, ...] = ()
    field_slots: dict[str, SemanticClassLayoutField] = field(
        default_factory=dict
    )
    visible_field_slots: dict[str, SemanticClassLayoutField] = field(
        default_factory=dict
    )
    dispatch_entries: tuple[SemanticClassMethodDispatch, ...] = ()
    dispatch_slots: dict[int, SemanticClassMethodDispatch] = field(
        default_factory=dict
    )
    visible_method_slots: dict[str, SemanticClassMethodDispatch] = field(
        default_factory=dict
    )
    dispatch_table_size: int = 0
    static_fields: tuple[SemanticClassStaticStorage, ...] = ()
    static_storage: dict[str, SemanticClassStaticStorage] = field(
        default_factory=dict
    )
    visible_static_storage: dict[str, SemanticClassStaticStorage] = field(
        default_factory=dict
    )


@public
@typechecked
@dataclass(frozen=True)
class SemanticClass:
    """
    title: Resolved class information.
    summary: Describe one top-level class declaration together with normalized
      bases, member tables, and deterministic inheritance metadata.
    attributes:
      symbol_id: Identifier for symbol.
      name: Name identifying this declaration.
      module_key: Canonical module identity.
      qualified_name: Name of qualified.
      declaration: Declaration being processed.
      bases: Bases.
      declared_members: Declared members.
      declared_member_table: Declared member table.
      declared_method_groups: Declared method groups.
      member_table: Member table.
      method_groups: Method groups.
      member_resolution: Member resolution.
      method_resolution: Method resolution.
      instance_attributes: Instance attributes.
      static_attributes: Static attributes.
      instance_methods: Instance methods.
      static_methods: Static methods.
      abstract_methods: Abstract methods.
      inheritance_graph: Inheritance graph.
      shared_ancestors: Shared ancestors.
      layout: Layout.
      initialization: Initialization.
      mro: Mro.
      is_structurally_resolved: Whether is structurally resolved.
      is_resolved: Whether is resolved.
      is_abstract: Whether is abstract.
      exception_type: Exception class being handled.
    """

    symbol_id: str
    name: str
    module_key: ModuleKey
    qualified_name: str
    declaration: astx.ClassDefStmt
    bases: tuple["SemanticClass", ...] = ()
    declared_members: tuple[SemanticClassMember, ...] = ()
    declared_member_table: dict[str, SemanticClassMember] = field(
        default_factory=dict
    )
    declared_method_groups: dict[str, tuple[SemanticClassMember, ...]] = field(
        default_factory=dict
    )
    member_table: dict[str, SemanticClassMember] = field(default_factory=dict)
    method_groups: dict[str, tuple[SemanticClassMember, ...]] = field(
        default_factory=dict
    )
    member_resolution: dict[str, SemanticClassMemberResolution] = field(
        default_factory=dict
    )
    method_resolution: dict[str, tuple[SemanticClassMemberResolution, ...]] = (
        field(default_factory=dict)
    )
    instance_attributes: tuple[SemanticClassMember, ...] = ()
    static_attributes: tuple[SemanticClassMember, ...] = ()
    instance_methods: tuple[SemanticClassMember, ...] = ()
    static_methods: tuple[SemanticClassMember, ...] = ()
    abstract_methods: tuple[SemanticClassMember, ...] = ()
    inheritance_graph: tuple[str, ...] = ()
    shared_ancestors: tuple["SemanticClass", ...] = ()
    layout: SemanticClassLayout | None = None
    initialization: SemanticClassInitialization | None = None
    mro: tuple["SemanticClass", ...] = ()
    is_structurally_resolved: bool = False
    is_resolved: bool = False
    is_abstract: bool = False
    exception_type: ResolvedExceptionType | None = None


@public
@typechecked
@dataclass(frozen=True)
class ImplicitConversion:
    """
    title: One semantically inserted implicit conversion.
    summary: Record one source-to-target type conversion that semantic
      analysis validated and lowering should honor directly.
    attributes:
      source_type: Type of the source value.
      target_type: Destination type for the conversion.
      numeric: Checked-policy classification for supported numeric domains.
        This describes required guards; lowering must implement the conversion
        plan.
    """

    source_type: astx.DataType | None
    target_type: astx.DataType | None
    numeric: NumericConversion | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        """
        title: Classify numeric source and destination domains during analysis.
        """
        if self.source_type is not None and self.target_type is not None:
            object.__setattr__(
                self,
                "numeric",
                classify_numeric_conversion(
                    self.source_type, self.target_type
                ),
            )


@public
@typechecked
@dataclass(frozen=True)
class TemplateArgumentBinding:
    """
    title: One concrete template argument binding.
    summary: Record the concrete type selected for one named template parameter
      in a specialization.
    attributes:
      name: Name identifying this declaration.
      type_: Type associated with this expression.
    """

    name: str
    type_: astx.DataType


@public
@typechecked
@dataclass(frozen=True)
class TemplateSpecializationKey:
    """
    title: Stable semantic template-specialization identity.
    summary: Identify one concrete specialization of a template function
      by the original semantic function name and the ordered concrete type
      names.
    attributes:
      qualified_name: Name of qualified.
      arg_type_names: Arg type names.
    """

    qualified_name: str
    arg_type_names: tuple[str, ...]


@public
@typechecked
@dataclass(frozen=True)
class SemanticFunction:
    """
    title: Resolved function information.
    summary: Describe one top-level function declaration or definition together
      with its semantic identity, canonical signature, and argument symbols.
    attributes:
      symbol_id: Identifier for symbol.
      name: Name identifying this declaration.
      return_type: Declared result type.
      args: Declared or supplied call arguments.
      signature: Resolved callable signature.
      prototype: Prototype.
      definition: Definition.
      module_key: Canonical module identity.
      qualified_name: Name of qualified.
      visibility: Visibility.
      template_params: Template parameters declared by the callable.
      template_bindings: Template bindings.
      template_definition: Template definition.
      specialization_key: Specialization key.
      specializations: Specializations.
    """

    symbol_id: str
    name: str
    return_type: astx.DataType
    args: tuple[SemanticSymbol, ...]
    signature: FunctionSignature
    prototype: astx.FunctionPrototype
    definition: astx.FunctionDef | None = None
    module_key: ModuleKey = field(default_factory=lambda: "<unknown>")
    qualified_name: str = ""
    visibility: astx.VisibilityKind = astx.VisibilityKind.public
    template_params: tuple[astx.TemplateParam, ...] = ()
    template_bindings: tuple[TemplateArgumentBinding, ...] = ()
    template_definition: "SemanticFunction" | None = None
    specialization_key: TemplateSpecializationKey | None = None
    specializations: dict[TemplateSpecializationKey, "SemanticFunction"] = (
        field(default_factory=dict, compare=False)
    )


@public
@typechecked
@dataclass(frozen=True)
class CallableResolution:
    """
    title: Resolved callable identity.
    summary: Point from one semantic site to the canonical callable identity
      and signature that analysis resolved.
    attributes:
      function: Function to process.
      signature: Resolved callable signature.
    """

    function: SemanticFunction
    signature: FunctionSignature


@public
@typechecked
@dataclass(frozen=True, init=False)
class ResolvedDefaultArgument:
    """
    title: One declaration-resolved omitted argument and its destination.
    attributes:
      index: Index selecting the item.
      expression: Expression to process.
      type_: Type associated with this expression.
    """

    index: int
    expression: astx.DataType
    type_: astx.DataType

    def __init__(
        self, index: int, expression: astx.DataType, type_: astx.DataType
    ) -> None:
        """
        title: Validate one default operand descriptor.
        parameters:
          index: Index selecting the item.
          expression: Expression to process.
          type_: Type expression to process.
        """
        object.__setattr__(self, "index", index)
        object.__setattr__(self, "expression", expression)
        object.__setattr__(self, "type_", type_)


@public
@typechecked
@dataclass(frozen=True, init=False)
class ResolvedCallArguments:
    """
    title: Source-ordered evaluations mapped onto positional ABI slots.
    attributes:
      evaluations: Evaluations.
      indices: Indices.
      defaults: Defaults.
      parameters: Declared callable parameters.
      receiver: Receiver.
      argument_count: Number of argument.
    """

    evaluations: tuple[astx.DataType, ...]
    indices: tuple[int, ...]
    defaults: tuple[ResolvedDefaultArgument, ...]
    parameters: tuple[SemanticSymbol, ...]
    receiver: SemanticSymbol | None
    argument_count: int

    def __init__(
        self,
        evaluations: tuple[astx.DataType, ...],
        indices: tuple[int, ...],
        defaults: tuple[ResolvedDefaultArgument, ...],
        parameters: tuple[SemanticSymbol, ...],
        receiver: SemanticSymbol | None,
        argument_count: int,
    ) -> None:
        """
        title: Validate the complete bound-call descriptor.
        parameters:
          evaluations: Evaluations.
          indices: Indices.
          defaults: Defaults.
          parameters: Declared callable parameters.
          receiver: Receiver.
          argument_count: Number of argument.
        """
        object.__setattr__(self, "evaluations", evaluations)
        object.__setattr__(self, "indices", indices)
        object.__setattr__(self, "defaults", defaults)
        object.__setattr__(self, "parameters", parameters)
        object.__setattr__(self, "receiver", receiver)
        object.__setattr__(self, "argument_count", argument_count)
        destinations = (*indices, *(default.index for default in defaults))
        if (
            len(evaluations) != len(indices)
            or argument_count < len(parameters)
            or len(destinations) != len(set(destinations))
            or set(destinations) != set(range(argument_count))
        ):
            raise ValueError(
                "call argument plan must populate every slot exactly once"
            )


@public
@typechecked
@dataclass(frozen=True)
class ResolvedSequenceAccess:
    """
    title: Exact borrowed numeric adapter selected by semantic analysis.
    attributes:
      kind: Kind of value or operation.
      element_type: Type of each element.
      type_id: Identifier for type.
      literal_list: Literal list.
    """

    kind: Literal["list", "tensor", "series", "sequence"]
    element_type: astx.DataType
    type_id: int
    literal_list: astx.LiteralList | None = None


@public
@typechecked
@dataclass(frozen=True)
class CallResolution:
    """
    title: Resolved function-call semantics.
    summary: Capture the canonical callee, validated argument conversions,
      and result type for one call site.
    attributes:
      callee: Callee.
      signature: Resolved callable signature.
      resolved_argument_types: Types of resolved argument.
      result_type: Resolved result type.
      implicit_conversions: Implicit conversions.
      arguments: Arguments supplied to the call.
      sequence_arguments: Sequence arguments.
    """

    callee: CallableResolution
    signature: FunctionSignature
    resolved_argument_types: tuple[astx.DataType | None, ...]
    result_type: astx.DataType
    implicit_conversions: tuple[ImplicitConversion | None, ...] = ()
    arguments: ResolvedCallArguments | None = None
    sequence_arguments: tuple[ResolvedSequenceAccess | None, ...] = ()


@public
@typechecked
@dataclass(frozen=True)
class ReturnResolution:
    """
    title: Resolved return-statement semantics.
    summary: Capture how one return statement relates to the enclosing
      function signature and any implicit conversion that analysis inserted.
    attributes:
      callable: Callable.
      expected_type: Expected semantic or storage type.
      value_type: Type of the stored value.
      returns_void: Whether to use returns void.
      implicit_conversion: Implicit conversion.
    """

    callable: CallableResolution
    expected_type: astx.DataType
    value_type: astx.DataType | None
    returns_void: bool
    implicit_conversion: ImplicitConversion | None = None


@public
@typechecked
@dataclass(frozen=True)
class ResolvedGeneratorFunction:
    """
    title: Resolved generator-function semantics.
    summary: Describe one function body that suspends at yield sites and
      returns a first-class generator object from call sites.
    attributes:
      function: Function to process.
      yield_type: Type of yield.
      yield_nodes: Yield nodes.
    """

    function: "SemanticFunction"
    yield_type: astx.DataType
    yield_nodes: tuple[astx.AST, ...] = ()


@public
@typechecked
@dataclass(frozen=True)
class ResolvedYield:
    """
    title: Resolved yield-site semantics.
    summary: Capture how one yield statement or expression maps to
      its enclosing generator function and yielded element type.
    attributes:
      generator: Generator.
      expected_type: Expected semantic or storage type.
      value_type: Type of the stored value.
      site_index: Index selecting site.
      implicit_conversion: Implicit conversion.
    """

    generator: ResolvedGeneratorFunction
    expected_type: astx.DataType
    value_type: astx.DataType | None
    site_index: int
    implicit_conversion: ImplicitConversion | None = None


@public
@typechecked
@dataclass(frozen=True)
class SemanticModule:
    """
    title: Semantic identity for an imported module.
    summary: Represent a module binding that plain imports introduce into
      a module namespace.
    attributes:
      module_key: Canonical module identity.
      display_name: Name of display.
    """

    module_key: ModuleKey
    display_name: str | None = None


@public
@typechecked
@dataclass(frozen=True)
class SemanticBinding:
    """
    title: One visible top-level binding in a module namespace.
    summary: Normalize imported and local top-level names into one binding
      shape for module-visible lookup.
    attributes:
      kind: Kind of value or operation.
      module_key: Canonical module identity.
      qualified_name: Name of qualified.
      function: Function to process.
      struct: Struct.
      class_: Class being processed.
      module: Module to process.
    """

    kind: str
    module_key: ModuleKey
    qualified_name: str
    function: SemanticFunction | None = None
    struct: SemanticStruct | None = None
    class_: SemanticClass | None = None
    module: SemanticModule | None = None


@public
@typechecked
@dataclass(frozen=True)
class ResolvedImportBinding:
    """
    title: One resolved imported local binding.
    summary: Record how one imported local name maps back to its source-module
      declaration.
    attributes:
      local_name: Name of local.
      requested_name: Name of requested.
      source_module_key: Source module key.
      binding: Resolved binding for the operation.
    """

    local_name: str
    requested_name: str
    source_module_key: ModuleKey
    binding: SemanticBinding


@public
@typechecked
@dataclass(frozen=True)
class ResolvedModuleMemberAccess:
    """
    title: Resolved module-namespace member access.
    summary: Record which imported module namespace one member access targeted
      and the visible binding that namespace lookup selected.
    attributes:
      module: Module to process.
      member_name: Name of member.
      binding: Resolved binding for the operation.
    """

    module: SemanticModule
    member_name: str
    binding: SemanticBinding


@public
@typechecked
@dataclass(frozen=True)
class SemanticFlags:
    """
    title: Normalized semantic flags.
    summary: Store normalized semantic modifiers such as unsigned and fast-math
      intent.
    attributes:
      unsigned: Whether to use unsigned semantics.
      fast_math: Whether to use fast math.
      fma: Whether to use fma.
      fma_rhs: Fma right operand.
    """

    unsigned: bool = False
    fast_math: bool = False
    fma: bool = False
    fma_rhs: astx.AST | None = None


@public
@typechecked
@dataclass(frozen=True)
class ResolvedOperator:
    """
    title: Normalized operator meaning.
    summary: Capture the normalized operator opcode, operand types, result
      type, and semantic flags for one expression.
    attributes:
      op_code: Operator spelling.
      result_type: Resolved result type.
      mode: Selected processing mode.
      lhs_type: Type of left operand.
      rhs_type: Type of right operand.
      flags: Flags.
      computation_type: Numeric operand type, distinct from comparison results.
      lhs_conversion: Left operand conversion.
      rhs_conversion: Right operand conversion.
      string_comparison: Whether equality compares text contents.
    """

    op_code: str
    result_type: astx.DataType | None = None
    mode: astx.NumericMode = astx.NumericMode.CHECKED
    lhs_type: astx.DataType | None = None
    rhs_type: astx.DataType | None = None
    flags: SemanticFlags = field(default_factory=SemanticFlags)
    computation_type: astx.DataType | None = None
    lhs_conversion: ImplicitConversion | None = None
    rhs_conversion: ImplicitConversion | None = None
    string_comparison: bool = False


@public
@typechecked
@dataclass(frozen=True)
class ResolvedAssignment:
    """
    title: Resolved assignment target.
    summary: Point from an assignment-like node back to the resolved target
      symbol it mutates.
    attributes:
      target: Destination of the operation.
    """

    target: SemanticSymbol


@public
@typechecked
@dataclass(frozen=True)
class ResolvedAugAssignment:
    """
    title: Resolved scalar compound mutation and its lossless store
      conversion.
    summary: Load target before evaluating the RHS once. Compute
      using operation's resolved operand conversions, then convert
      and store only on success. Yield the stored value; independent
      RHS side effects are not rolled back. This plan supports numeric
      identifiers, not fields or owning resources.
    attributes:
      target: Destination of the operation.
      operation: Operation to resolve or execute.
      store_conversion: Store conversion.
    """

    target: SemanticSymbol
    operation: ResolvedOperator
    store_conversion: ImplicitConversion


@public
@typechecked
@dataclass(frozen=True)
class ResolvedFieldAccess:
    """
    title: Resolved field access metadata.
    summary: Point from a field-access node to its owning struct and stable
      field metadata.
    attributes:
      struct: Struct.
      field: Field to process.
    """

    struct: SemanticStruct
    field: SemanticStructField


@public
@typechecked
@dataclass(frozen=True)
class ResolvedClassFieldAccess:
    """
    title: Resolved class-field access metadata.
    summary: Point from a class-attribute access node to the owning class
      member and stable flattened layout slot.
    attributes:
      class_: Class being processed.
      member: Member.
      field: Field to process.
    """

    class_: SemanticClass
    member: SemanticClassMember
    field: SemanticClassLayoutField


@public
@typechecked
@dataclass(frozen=True)
class ResolvedBaseClassFieldAccess:
    """
    title: Resolved explicit base-class field access metadata.
    summary: Point from a base-qualified instance attribute read
      to the selected base view, concrete receiver class, and stable
      flattened layout slot.
    attributes:
      receiver_class: Receiver class.
      base_class: Base class.
      member: Member.
      field: Field to process.
    """

    receiver_class: SemanticClass
    base_class: SemanticClass
    member: SemanticClassMember
    field: SemanticClassLayoutField


@public
@typechecked
@dataclass(frozen=True)
class ResolvedStaticClassFieldAccess:
    """
    title: Resolved static class-field access metadata.
    summary: Point from a class-qualified static attribute read to the selected
      class member and stable emitted storage metadata.
    attributes:
      class_: Class being processed.
      member: Member.
      storage: Storage.
    """

    class_: SemanticClass
    member: SemanticClassMember
    storage: SemanticClassStaticStorage


@public
@typechecked
class ExceptionCauseMode(str, Enum):
    """
    title: Diagnostic chaining requested by a raise expression.
    """

    IMPLICIT = "implicit"
    EXPLICIT = "explicit"
    SUPPRESS = "suppress"


@public
@typechecked
@dataclass(frozen=True)
class ResolvedExceptionType:
    """
    title: Nominal exception identity and validated base storage.
    attributes:
      class_: Class being processed.
      diagnostic_field: Diagnostic field.
      message_field: Message field.
      ancestry: Ancestry.
    """

    class_: SemanticClass
    diagnostic_field: SemanticClassLayoutField
    message_field: SemanticClassLayoutField
    ancestry: tuple[str, ...]

    def __post_init__(self) -> None:
        """
        title: Check generated dataclass arguments at the runtime boundary.
        """
        validate_exception_type_metadata(
            self.class_,
            self.diagnostic_field,
            self.message_field,
            self.ancestry,
        )


@public
@typechecked
@dataclass(frozen=True)
class ResolvedNativeExceptionInitialization:
    """
    title: Native diagnostic initialization within ordinary class construction.
    attributes:
      exception_type: Exception class being handled.
      message_index: Index into source-order construction evaluations. None
        initializes the inherited message to the empty string before a custom
        initializer.
    """

    exception_type: ResolvedExceptionType
    message_index: int | None

    def __post_init__(self) -> None:
        """
        title: Check generated dataclass arguments at the runtime boundary.
        """
        validate_exception_initialization(
            self.exception_type, self.message_index
        )


@public
@typechecked
@dataclass(frozen=True)
class ResolvedRaise:
    """
    title: Validated raised value and explicit diagnostic cause.
    attributes:
      exception_type: Exception class being handled.
      cause_mode: Cause mode.
      cause_type: Type of cause.
    """

    exception_type: ResolvedExceptionType | None = None
    cause_mode: ExceptionCauseMode = ExceptionCauseMode.IMPLICIT
    cause_type: ResolvedExceptionType | None = None

    def __post_init__(self) -> None:
        """
        title: Check generated dataclass arguments at the runtime boundary.
        """
        validate_raise_metadata(
            self.exception_type, self.cause_mode, self.cause_type
        )


@public
@typechecked
@dataclass(frozen=True)
class ResolvedExceptionHandler:
    """
    title: Ordered nominal matches and a lexical handler binding.
    attributes:
      types: Types.
      symbol: Resolved symbol for the operation.
      binding_type: Type of binding.
    """

    types: tuple[ResolvedExceptionType, ...]
    symbol: SemanticSymbol | None
    binding_type: astx.ClassType

    def __post_init__(self) -> None:
        """
        title: Check generated dataclass arguments at the runtime boundary.
        """
        validate_exception_handler_metadata(
            self.types, self.symbol, self.binding_type
        )


@public
@typechecked
@dataclass(frozen=True)
class ResolvedTry:
    """
    title: Validated statement-only exception region.
    attributes:
      handlers: Handlers.
    """

    handlers: tuple[ResolvedExceptionHandler, ...]

    def __post_init__(self) -> None:
        """
        title: Check generated dataclass arguments at the runtime boundary.
        """
        validate_exception_handlers(self.handlers)


@public
@typechecked
@dataclass(frozen=True)
class ResolvedClassConstruction:
    """
    title: Resolved class construction metadata.
    summary: Capture the analyzed class identity and ordered initialization
      plan for one default class construction expression.
    attributes:
      class_: Class being processed.
      initialization: Initialization.
      evaluations: Evaluations.
      argument_indices: Argument indices.
      argument_types: Types of argument.
      native_file: File containing native.
      native_exception: Native exception.
    """

    class_: SemanticClass
    initialization: SemanticClassInitialization
    evaluations: tuple[astx.DataType, ...] = ()
    argument_indices: tuple[int, ...] = ()
    argument_types: tuple[astx.DataType, ...] = ()
    native_file: ResolvedNativeFileInitialization | None = None
    native_exception: ResolvedNativeExceptionInitialization | None = None


@public
@typechecked
@dataclass(frozen=True)
class ResolvedMethodCall:
    """
    title: Resolved class method call metadata.
    summary: Capture the resolved class member, lowered implementation,
      dispatch mode, and validated argument conversions for one method
      call site.
    attributes:
      class_: Class being processed.
      member: Member.
      function: Function to process.
      overload_key: Overload key.
      dispatch_kind: Dispatch kind.
      call: Call being processed.
      candidates: Candidates.
      receiver_type: Type of receiver.
      receiver_class: Receiver class.
      slot_index: Index selecting slot.
    """

    class_: SemanticClass
    member: SemanticClassMember
    function: SemanticFunction
    overload_key: str
    dispatch_kind: MethodDispatchKind
    call: CallResolution
    candidates: tuple[SemanticClassMember, ...] = ()
    receiver_type: astx.DataType | None = None
    receiver_class: SemanticClass | None = None
    slot_index: int | None = None


@public
@typechecked
@dataclass(frozen=True)
class ResolvedContextManager:
    """
    title: Resolved context-manager metadata.
    summary: Capture analyzed bindings and calls for one resource scope.
      The manager binding pins its identity; value_binding owns the actual
      enter result, including when no source target is requested. Exit receives
      a Boolean completion value and returns none. Lowering reuses ordinary
      declaration ownership and call plans without resolving the protocol
      again.
    attributes:
      class_: Class being processed.
      manager_type: Type of manager.
      enter: Enter.
      exit: Exit.
      manager_binding: Manager binding.
      enter_call: Enter call.
      value_binding: Value binding.
      success_binding: Success binding.
      exit_call: Exit call.
      target_symbol: Target symbol.
    """

    class_: SemanticClass
    manager_type: astx.DataType
    enter: ResolvedMethodCall
    exit: ResolvedMethodCall
    manager_binding: astx.VariableDeclaration
    enter_call: astx.MethodCall
    value_binding: astx.VariableDeclaration | None
    success_binding: astx.VariableDeclaration
    exit_call: astx.MethodCall
    target_symbol: SemanticSymbol | None = None


@public
@typechecked
class IterationKind(str, Enum):
    """
    title: Stable iterable adapter kinds.
    summary: Classify the semantic adapter that turns one iterable expression
      into a backend iteration plan.
    """

    LIST = "list"
    SEQUENCE = "sequence"
    DICT_KEYS = "dict_keys"
    SET = "set"
    GENERATOR = "generator"
    RANGE = "range"
    CUSTOM = "custom"


@public
@typechecked
class IterationOrder(str, Enum):
    """
    title: Stable iterable ordering categories.
    summary: Describe the user-visible order guarantee, if any, exposed by
      one iterable adapter.
    """

    INDEX = "index"
    INSERTION = "insertion"
    STABLE = "stable"
    UNSPECIFIED = "unspecified"


@public
@typechecked
class CursorProtocol(str, Enum):
    """
    title: Closed acquisition, advancement, and finalization protocols.
    summary: Indexed and range values acquire independent positions. Generator
      acquisition consumes a one-shot frame, rejecting reacquisition.
      Advance distinguishes a produced item from exhaustion and checks
      failure before reading output slots. Close is idempotent and runs
      on every cursor exit; generator close prevents resumption without
      freeing its lexical owner.
    """

    INDEXED = "indexed"
    RANGE = "range"
    GENERATOR = "generator"


@public
@typechecked
@dataclass(frozen=True)
class ResolvedIteration:
    """
    title: Resolved iterable capability.
    summary: Attach the semantic iteration plan that a for-in loop
      or comprehension should consume during backend lowering.
    attributes:
      iterable_node: Iterable node.
      iterable_type: Type of iterable.
      element_type: Type of each element.
      kind: Kind of value or operation.
      is_reiterable: Whether is reiterable.
      order: Order.
      target_symbol: Target symbol.
      sequence_access: Sequence access.
      borrowed_owner_symbol_id: Named list owner protected from replacement
        during iteration.
      extras: Extras.
      cursor_protocol: Cursor protocol.
      element_ownership: Scalars are copied values. String-list elements
        borrow their source until the existing loop adapter creates
        an independent local owner.
    """

    iterable_node: astx.AST
    iterable_type: astx.DataType
    element_type: astx.DataType
    kind: IterationKind
    is_reiterable: bool = True
    order: IterationOrder = IterationOrder.UNSPECIFIED
    target_symbol: SemanticSymbol | None = None
    sequence_access: ResolvedSequenceAccess | None = None
    borrowed_owner_symbol_id: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)
    cursor_protocol: CursorProtocol | None = None
    element_ownership: Literal["value", "borrowed"] = "value"


@public
@typechecked
class CollectionMethodKind(str, Enum):
    """
    title: Stable collection-method semantic categories.
    """

    LENGTH = "length"
    IS_EMPTY = "is_empty"
    CONTAINS = "contains"
    INDEX = "index"
    COUNT = "count"


@public
@typechecked
@dataclass(frozen=True)
class ResolvedMaterialization:
    """
    title: Single-pass numeric materialization with an optional sized
      bound.
    summary: Unsized inputs require max_items. On excess, at most
      max_items + 1 items have been consumed, and no partial list
      is published. Consumed input is not rolled back. Fresh iterator
      frames transfer to this call; named iterator frames are borrowed
      from their lexical owner. checked_bytes selects immutable UInt8
      output with per-item 0..255 validation before narrowing, not
      the source element width. No invalid prefix is published.
    attributes:
      iteration: Iteration.
      max_items: Max items.
      checked_bytes: Whether to use checked bytes.
    """

    iteration: ResolvedIteration
    max_items: astx.AST | None
    checked_bytes: bool = False


@public
@typechecked
@dataclass(frozen=True)
class ResolvedCollectionMethod:
    """
    title: Resolved collection method capability.
    summary: Attach the semantic collection operation that lowering should
      consume without re-resolving receiver kind or result type.
    attributes:
      receiver_node: Receiver node.
      receiver_type: Type of receiver.
      method: Method.
      return_type: Declared result type.
      argument_types: Types of argument.
      comparison_plans: Comparison plans.
      matching_types: Types of matching.
      mutates: Whether to use mutates.
      extras: Extras.
    """

    receiver_node: astx.AST
    receiver_type: astx.DataType
    method: CollectionMethodKind
    return_type: astx.DataType
    argument_types: tuple[astx.DataType, ...] = ()
    comparison_plans: tuple[ResolvedOperator, ...] = ()
    matching_types: tuple[astx.DataType, ...] = ()
    mutates: bool = False
    extras: dict[str, Any] = field(default_factory=dict)


@public
@typechecked
@dataclass(frozen=True)
class ResolvedFileOpen:
    """
    title: Validated open operands in original evaluation order.
    summary: text_options records non-None encoding/errors/newline so dynamic
      binary modes reject incompatible settings before creating or truncating
      a path.
    attributes:
      evaluations: Evaluations.
      path_index: Index selecting path.
      mode_index: Index selecting mode.
      text_options: Whether to use text options.
    """

    evaluations: tuple[astx.DataType, ...]
    path_index: int
    mode_index: int | None
    text_options: bool = False


@public
@typechecked
@dataclass(frozen=True)
class ResolvedNativeFileInitialization:
    """
    title: Caller-checked native initialization of a real File class field.
    attributes:
      field: Field to process.
      operands: Operands.
    """

    field: SemanticClassLayoutField
    operands: ResolvedFileOpen

    def __init__(
        self, field: SemanticClassLayoutField, operands: ResolvedFileOpen
    ) -> None:
        """
        title: Validate the native initializer descriptor at runtime.
        parameters:
          field: Field to process.
          operands: Operands.
        """
        object.__setattr__(self, "field", field)
        object.__setattr__(self, "operands", operands)


@public
@typechecked
@dataclass(frozen=True)
class ResolvedFileOperation:
    """
    title: A validated operation on an owned native file.
    attributes:
      name: Name identifying this declaration.
      receiver_field: Receiver field.
    """

    name: str
    receiver_field: SemanticClassLayoutField | None = None


@public
@typechecked
class TextOperationKind(Enum):
    """
    title: Validated operations on NUL-free Unicode text.
    """

    LENGTH = "len"
    INDEX = "index"
    SLICE = "slice"
    SPLIT = "split"
    STRIP = "strip"
    INTEGER = "int"
    ORDINAL = "ord"


@public
@typechecked
@dataclass(frozen=True)
class ResolvedTextOperation:
    """
    title: Source-ordered text operands and their normalized ABI positions.
    summary: Evaluate each operand once in order. Each argument index selects
      an evaluation; None selects the operation's documented default. Inputs
      are borrowed for the operation and owned results are independent copies.
    attributes:
      kind: Kind of value or operation.
      evaluations: Evaluations.
      argument_indices: Argument indices.
      cache_receiver: Whether the receiver can use its binding's query cache.
    """

    kind: TextOperationKind
    evaluations: tuple[astx.AST, ...]
    argument_indices: tuple[int | None, ...]
    cache_receiver: bool = False


@public
@typechecked
@dataclass
class SemanticInfo:
    """
    title: Sidecar semantic information stored on AST nodes.
    summary: Aggregate all semantic sidecar fields that analysis may attach
      to a single AST node.
    attributes:
      range_construction: Range construction.
      range_access: Whether to use range access.
      materialization: Materialization.
      sequence_access: Sequence access.
      normalized_collection: Normalized collection.
      tensor_index: Index selecting tensor.
      constant_list_elements: Static integer values for a direct list read.
      numeric_storage: Numeric storage.
      module_storage: Module storage.
      literal_context: Expected literal, literal-arithmetic, or collection
        type, consumed on visit.
      numeric_constant: Numeric constant.
      numeric_conversion: Numeric conversion.
      numeric_mode: Numeric mode.
      resolved_type: Type of resolved.
      resolved_symbol: Resolved symbol.
      resolved_function: Resolved function.
      resolved_callable: Resolved callable.
      resolved_struct: Resolved struct.
      resolved_class: Resolved class.
      resolved_module: Resolved module.
      resolved_imports: Resolved imports.
      resolved_file_open: Resolved file open.
      resolved_file_operation: Resolved file operation.
      resolved_call: Resolved call.
      resolved_operator: Resolved operator.
      resolved_assignment: Resolved assignment.
      resolved_borrow: Resolved local borrow creation or retargeting.
      resolved_aug_assignment: Resolved aug assignment.
      resolved_field_access: Resolved field access.
      resolved_module_member_access: Resolved module member access.
      resolved_class_field_access: Resolved class field access.
      resolved_base_class_field_access: Resolved base class field access.
      resolved_static_class_field_access: Resolved static class field access.
      resolved_method_call: Resolved method call.
      resolved_context_manager: Resolved context manager.
      resolved_class_construction: Resolved class construction.
      resolved_raise: Resolved raise.
      resolved_exception_handler: Resolved exception handler.
      resolved_try: Resolved try.
      flow_outcomes: Flow outcomes.
      runtime_exception_types: Types of runtime exception.
      resolved_return: Resolved return.
      resolved_generator_function: Resolved generator function.
      resolved_yield: Resolved yield.
      resolved_iteration: Resolved iteration.
      resolved_collection_method: Resolved collection method.
      resource_ownership: Resource ownership.
      tensor_temporary_owner: This tensor expression constructs a fresh
        owner, possibly through views. Scalar consumers release it after
        use; named tensors and explicit retain/release operations keep their
        existing lifetime.
      collection_tensor: An explicitly tensor-contextualized collection
        expression.
      collection_length: Collection length.
      text_query_cache: Whether this binding needs a scoped UTF-8 query
        cache.
      resolved_text_operation: Resolved unshadowed len intrinsic using shared
        queries.
      lifecycle_self: Whether to use lifecycle self.
      lifecycle_field_store: Whether to use lifecycle field store.
      resolved_resource_store: Resolved resource store.
      initializer_receiver: Initializer receiver.
      semantic_flags: Semantic flags.
      facts: Facts.
      extras: Extras.
    """

    range_construction: CallResolution | None = None
    range_access: bool = False
    materialization: ResolvedMaterialization | None = None
    sequence_access: ResolvedSequenceAccess | None = None
    normalized_collection: astx.Expr | None = None
    tensor_index: astx.TensorIndex | None = None
    constant_list_elements: tuple[int, ...] | None = None
    numeric_storage: astx.DataType | None = None
    module_storage: ResolvedModuleStorage | None = None
    literal_context: astx.DataType | None = None
    numeric_constant: int | float | None = None
    numeric_conversion: NumericConversion | None = None
    numeric_mode: astx.NumericMode = astx.NumericMode.CHECKED
    resolved_type: astx.DataType | None = None
    resolved_symbol: SemanticSymbol | None = None
    resolved_function: SemanticFunction | None = None
    resolved_callable: CallableResolution | None = None
    resolved_struct: SemanticStruct | None = None
    resolved_class: SemanticClass | None = None
    resolved_module: SemanticModule | None = None
    resolved_imports: tuple[ResolvedImportBinding, ...] = ()
    resolved_file_open: ResolvedFileOpen | None = None
    resolved_file_operation: ResolvedFileOperation | None = None
    resolved_call: CallResolution | None = None
    resolved_operator: ResolvedOperator | None = None
    resolved_assignment: ResolvedAssignment | None = None
    resolved_borrow: ResolvedBorrow | None = None
    resolved_aug_assignment: ResolvedAugAssignment | None = None
    resolved_field_access: ResolvedFieldAccess | None = None
    resolved_module_member_access: ResolvedModuleMemberAccess | None = None
    resolved_class_field_access: ResolvedClassFieldAccess | None = None
    resolved_base_class_field_access: ResolvedBaseClassFieldAccess | None = (
        None
    )
    resolved_static_class_field_access: (
        ResolvedStaticClassFieldAccess | None
    ) = None
    resolved_method_call: ResolvedMethodCall | None = None
    resolved_context_manager: ResolvedContextManager | None = None
    resolved_class_construction: ResolvedClassConstruction | None = None
    resolved_raise: ResolvedRaise | None = None
    resolved_exception_handler: ResolvedExceptionHandler | None = None
    resolved_try: ResolvedTry | None = None
    flow_outcomes: frozenset[FlowOutcome] = frozenset()
    runtime_exception_types: dict[str, ResolvedExceptionType] = field(
        default_factory=dict
    )
    resolved_return: ReturnResolution | None = None
    resolved_generator_function: ResolvedGeneratorFunction | None = None
    resolved_yield: ResolvedYield | None = None
    resolved_iteration: ResolvedIteration | None = None
    resolved_collection_method: ResolvedCollectionMethod | None = None
    resource_ownership: ResourceOwnership | None = None
    tensor_temporary_owner: bool = False
    collection_tensor: astx.TensorLiteral | None = None
    collection_length: astx.CollectionLength | None = None
    text_query_cache: bool = False
    resolved_text_operation: ResolvedTextOperation | None = None
    lifecycle_self: bool = False
    lifecycle_field_store: bool = False
    resolved_resource_store: ResourceOwnership | None = None
    initializer_receiver: SemanticSymbol | None = None
    semantic_flags: SemanticFlags = field(default_factory=SemanticFlags)
    facts: SemanticFacts = field(default_factory=SemanticFacts)
    extras: dict[str, Any] = field(default_factory=dict)


@private
@typechecked
def validate_exception_type_metadata(
    class_: SemanticClass,
    diagnostic_field: SemanticClassLayoutField,
    message_field: SemanticClassLayoutField,
    ancestry: tuple[str, ...],
) -> None:
    """
    title: Validate exception metadata and every collection item.
    parameters:
      class_: Class being processed.
      diagnostic_field: Diagnostic field.
      message_field: Message field.
      ancestry: Ancestry.
    """


@private
@typechecked
def validate_exception_initialization(
    exception_type: ResolvedExceptionType, message_index: int | None
) -> None:
    """
    title: Validate exception metadata and every collection item.
    parameters:
      exception_type: Exception class being handled.
      message_index: Index selecting message.
    """


@private
@typechecked
def validate_raise_metadata(
    exception_type: ResolvedExceptionType | None,
    cause_mode: ExceptionCauseMode,
    cause_type: ResolvedExceptionType | None,
) -> None:
    """
    title: Validate exception metadata and every collection item.
    parameters:
      exception_type: Exception class being handled.
      cause_mode: Cause mode.
      cause_type: Type of cause.
    """


@private
@typechecked
def validate_exception_handler_metadata(
    types: tuple[ResolvedExceptionType, ...],
    symbol: SemanticSymbol | None,
    binding_type: astx.ClassType,
) -> None:
    """
    title: Validate exception metadata and every collection item.
    parameters:
      types: Types.
      symbol: Resolved symbol for the operation.
      binding_type: Type of binding.
    """


@private
@typechecked
def validate_exception_handlers(
    handlers: tuple[ResolvedExceptionHandler, ...],
) -> None:
    """
    title: Validate exception metadata and every collection item.
    parameters:
      handlers: Handlers.
    """
