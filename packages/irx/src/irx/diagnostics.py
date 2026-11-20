"""
title: Shared diagnostics and source-location helpers.
summary: Provide one small diagnostics foundation that semantic analysis,
  lowering, native compilation, linking, and runtime feature resolution can
  all share.
"""

from __future__ import annotations

import re

from dataclasses import dataclass
from typing import Iterable

import astx

from public import public

from irx.typecheck import typechecked

DEFAULT_DIAGNOSTIC_CODE_PREFIX = "IRX-"
_RENDERED_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*-[A-Z]\d{3,}$")


@public
@typechecked
@dataclass(frozen=True)
class DiagnosticCodeFormatter:
    """
    title: Render logical diagnostic identifiers with one configurable prefix.
    attributes:
      prefix: Prefix.
    """

    prefix: str = DEFAULT_DIAGNOSTIC_CODE_PREFIX

    def __post_init__(self) -> None:
        """
        title: Normalize the configured diagnostic prefix.
        """
        normalized = self.prefix.strip()
        if normalized and not normalized.endswith("-"):
            normalized = f"{normalized}-"
        object.__setattr__(self, "prefix", normalized)

    def format(self, code: str | None) -> str | None:
        """
        title: Format one logical diagnostic identifier.
        parameters:
          code: Source code or diagnostic identifier.
        returns: Formatted one logical diagnostic identifier.
        """
        if code is None:
            return None
        stripped = code.strip()
        if not stripped:
            return None
        if _RENDERED_CODE_PATTERN.match(stripped):
            return stripped
        return f"{self.prefix}{stripped}"


_DIAGNOSTIC_CODE_FORMATTER = DiagnosticCodeFormatter()


@public
@typechecked
def get_diagnostic_code_formatter() -> DiagnosticCodeFormatter:
    """
    title: Return the active diagnostic-code formatter.
    returns: The active diagnostic-code formatter.
    """
    return _DIAGNOSTIC_CODE_FORMATTER


@public
@typechecked
def set_diagnostic_code_formatter(
    formatter: DiagnosticCodeFormatter,
) -> DiagnosticCodeFormatter:
    """
    title: Replace the process-wide diagnostic-code formatter.
    parameters:
      formatter: Formatter.
    returns: 'Result of this operation: replace the process-wide
      diagnostic-code formatter.'
    """
    globals()["_DIAGNOSTIC_CODE_FORMATTER"] = formatter
    return formatter


@public
@typechecked
def set_diagnostic_code_prefix(prefix: str) -> DiagnosticCodeFormatter:
    """
    title: Configure the process-wide diagnostic-code prefix.
    parameters:
      prefix: Prefix.
    returns: 'Result of this operation: configure the process-wide
      diagnostic-code prefix.'
    """
    return set_diagnostic_code_formatter(DiagnosticCodeFormatter(prefix))


@public
@typechecked
def format_diagnostic_code(
    code: str | None,
    *,
    code_formatter: DiagnosticCodeFormatter | None = None,
) -> str | None:
    """
    title: Render one logical diagnostic identifier.
    parameters:
      code: Source code or diagnostic identifier.
      code_formatter: Code formatter.
    returns: 'Result of this operation: render one logical diagnostic
      identifier.'
    """
    formatter = code_formatter or get_diagnostic_code_formatter()
    return formatter.format(code)


@public
@typechecked
@dataclass(frozen=True)
class SourceLocation:
    """
    title: One best-effort source location.
    attributes:
      line: Source line coordinate.
      col: Source column coordinate.
      end_line: End line.
      end_col: End col.
    """

    line: int | None = None
    col: int | None = None
    end_line: int | None = None
    end_col: int | None = None

    def is_known(self) -> bool:
        """
        title: Return whether any source position is known.
        returns: Whether any source position is known.
        """
        return self.line is not None or self.col is not None

    def format(self) -> str:
        """
        title: Render one location without module identity.
        returns: 'Result of this operation: render one location without
          module identity.'
        """
        if self.line is None:
            return ""
        if self.col is None:
            return str(self.line)
        return f"{self.line}:{self.col}"


@typechecked
def _non_negative_int(value: object) -> int | None:
    """
    title: Return one non-negative integer when present.
    parameters:
      value: Value to process.
    returns: One non-negative integer when present.
    """
    if isinstance(value, int) and value >= 0:
        return value
    return None


@public
@typechecked
def source_location_from_loc(loc: object | None) -> SourceLocation | None:
    """
    title: Convert one arbitrary location-like object to SourceLocation.
    parameters:
      loc: Source coordinates associated with the node.
    returns: Converted one arbitrary location-like object to SourceLocation.
    """
    if loc is None:
        return None
    line = _non_negative_int(getattr(loc, "line", None))
    col = _non_negative_int(getattr(loc, "col", getattr(loc, "column", None)))
    end_line = _non_negative_int(getattr(loc, "end_line", None))
    end_col = _non_negative_int(
        getattr(loc, "end_col", getattr(loc, "end_column", None))
    )
    source = SourceLocation(
        line=line,
        col=col,
        end_line=end_line,
        end_col=end_col,
    )
    if not source.is_known():
        return None
    return source


@public
@typechecked
def get_node_source_location(node: astx.AST | None) -> SourceLocation | None:
    """
    title: Return one AST node's best-effort source location.
    parameters:
      node: Syntax node to process.
    returns: One AST node's best-effort source location.
    """
    if node is None:
        return None
    return source_location_from_loc(getattr(node, "loc", None))


@typechecked
def _string_or_none(value: object) -> str | None:
    """
    title: Return one non-empty string when present.
    parameters:
      value: Value to process.
    returns: One non-empty string when present.
    """
    if isinstance(value, str) and value:
        return value
    return None


@public
@typechecked
def get_node_module_key(node: astx.AST | None) -> str | None:
    """
    title: Return one AST node's best-effort module attribution.
    parameters:
      node: Syntax node to process.
    returns: One AST node's best-effort module attribution.
    """
    if node is None:
        return None

    direct = _string_or_none(getattr(node, "module_key", None))
    if direct is not None:
        return direct

    semantic = getattr(node, "semantic", None)
    if semantic is None:
        return None

    candidates: list[object] = [
        getattr(semantic, "resolved_function", None),
        getattr(semantic, "resolved_symbol", None),
        getattr(semantic, "resolved_struct", None),
        getattr(semantic, "resolved_module", None),
    ]
    resolved_call = getattr(semantic, "resolved_call", None)
    if resolved_call is not None:
        candidates.append(
            getattr(getattr(resolved_call, "callee", None), "function", None)
        )
    resolved_return = getattr(semantic, "resolved_return", None)
    if resolved_return is not None:
        candidates.append(
            getattr(
                getattr(resolved_return, "callable", None), "function", None
            )
        )
    resolved_assignment = getattr(semantic, "resolved_assignment", None)
    if resolved_assignment is not None:
        candidates.append(getattr(resolved_assignment, "target", None))
    resolved_field_access = getattr(semantic, "resolved_field_access", None)
    if resolved_field_access is not None:
        candidates.append(getattr(resolved_field_access, "struct", None))

    for candidate in candidates:
        module_key = _string_or_none(getattr(candidate, "module_key", None))
        if module_key is not None:
            return module_key
    return None


@public
@typechecked
def format_source_location(
    module_key: str | None = None,
    source: SourceLocation | None = None,
) -> str:
    """
    title: Format one module-aware source location.
    parameters:
      module_key: Canonical module identity.
      source: Source input to process.
    returns: Formatted one module-aware source location.
    """
    location_text = source.format() if source is not None else ""
    if module_key and location_text:
        return f"{module_key}:{location_text}"
    if module_key:
        return module_key
    return location_text


@public
@typechecked
@dataclass(frozen=True)
class DiagnosticRelatedInformation:
    """
    title: One secondary diagnostic location or note.
    attributes:
      message: Diagnostic message.
      node: Syntax node to process.
      module_key: Canonical module identity.
      source: Source input to process.
    """

    message: str
    node: astx.AST | None = None
    module_key: str | None = None
    source: SourceLocation | None = None

    def resolved_source(self) -> SourceLocation | None:
        """
        title: Return the related entry's source location.
        returns: The related entry's source location.
        """
        return self.source or get_node_source_location(self.node)

    def resolved_module_key(self) -> str | None:
        """
        title: Return the related entry's module attribution.
        returns: The related entry's module attribution.
        """
        return self.module_key or get_node_module_key(self.node)


@public
@typechecked
@dataclass(frozen=True)
class Diagnostic:
    """
    title: One structured diagnostic record.
    attributes:
      message: Diagnostic message.
      node: Syntax node to process.
      code: Stable diagnostic identifier.
      severity: Severity.
      module_key: Canonical module identity.
      phase: Phase.
      source: Source input to process.
      notes: Notes.
      hint: Hint.
      cause: Cause.
      related: Related.
    """

    message: str
    node: astx.AST | None = None
    code: str | None = None
    severity: str = "error"
    module_key: str | None = None
    phase: str = "semantic"
    source: SourceLocation | None = None
    notes: tuple[str, ...] = ()
    hint: str | None = None
    cause: Exception | None = None
    related: tuple[DiagnosticRelatedInformation, ...] = ()

    def resolved_source(self) -> SourceLocation | None:
        """
        title: Return the diagnostic's best-effort source location.
        returns: The diagnostic's best-effort source location.
        """
        return self.source or get_node_source_location(self.node)

    def resolved_module_key(self) -> str | None:
        """
        title: Return the diagnostic's best-effort module attribution.
        returns: The diagnostic's best-effort module attribution.
        """
        return self.module_key or get_node_module_key(self.node)

    def rendered_code(
        self,
        *,
        code_formatter: DiagnosticCodeFormatter | None = None,
    ) -> str | None:
        """
        title: Return the final rendered diagnostic code.
        parameters:
          code_formatter: Code formatter.
        returns: The final rendered diagnostic code.
        """
        return format_diagnostic_code(
            self.code,
            code_formatter=code_formatter,
        )

    def format(
        self,
        *,
        code_formatter: DiagnosticCodeFormatter | None = None,
    ) -> str:
        """
        title: Format the diagnostic for human display.
        parameters:
          code_formatter: Code formatter.
        returns: Formatted the diagnostic for human display.
        """
        prefix = format_source_location(
            self.resolved_module_key(),
            self.resolved_source(),
        )
        prefix_text = f"{prefix}: " if prefix else ""
        rendered_code = self.rendered_code(code_formatter=code_formatter)
        label = self.severity
        if rendered_code is not None:
            label = f"{label}[{rendered_code}]"
        if self.phase and self.phase != "semantic":
            label = f"{label} ({self.phase})"

        lines = [f"{prefix_text}{label}: {self.message}"]
        for note in self.notes:
            lines.append(f"  note: {note}")
        if self.hint is not None:
            lines.append(f"  hint: {self.hint}")
        if self.cause is not None:
            cause_message = (
                str(self.cause).strip() or self.cause.__class__.__name__
            )
            lines.append(
                f"  cause: {self.cause.__class__.__name__}: {cause_message}"
            )
        for related in self.related:
            related_prefix = format_source_location(
                related.resolved_module_key(),
                related.resolved_source(),
            )
            related_text = (
                f"{related_prefix}: {related.message}"
                if related_prefix
                else related.message
            )
            lines.append(f"  related: {related_text}")
        return "\n".join(lines)


@public
@typechecked
class DiagnosticBag:
    """
    title: Collect diagnostics across one semantic-analysis attempt.
    attributes:
      diagnostics: Collected structured diagnostics.
      default_module_key: Default module key.
    """

    diagnostics: list[Diagnostic]
    default_module_key: str | None

    def __init__(self) -> None:
        """
        title: Initialize DiagnosticBag.
        """
        self.diagnostics = []
        self.default_module_key = None

    def add(
        self,
        message: str,
        *,
        node: astx.AST | None = None,
        code: str | None = None,
        severity: str = "error",
        module_key: str | None = None,
        phase: str = "semantic",
        source: SourceLocation | None = None,
        notes: Iterable[str] = (),
        hint: str | None = None,
        cause: Exception | None = None,
        related: Iterable[DiagnosticRelatedInformation] = (),
    ) -> None:
        """
        title: Add one diagnostic to the bag.
        parameters:
          message: Diagnostic or output message.
          node: Syntax node to process.
          code: Source code or diagnostic identifier.
          severity: Severity.
          module_key: Canonical module identity.
          phase: Phase.
          source: Source input to process.
          notes: Notes.
          hint: Hint.
          cause: Cause.
          related: Related.
        """
        self.diagnostics.append(
            Diagnostic(
                message=message,
                node=node,
                code=code,
                severity=severity,
                module_key=module_key or self.default_module_key,
                phase=phase,
                source=source,
                notes=tuple(notes),
                hint=hint,
                cause=cause,
                related=tuple(related),
            )
        )

    def extend(self, diagnostics: Iterable[Diagnostic]) -> None:
        """
        title: Extend the bag with additional diagnostics.
        parameters:
          diagnostics: Collected structured diagnostics.
        """
        self.diagnostics.extend(diagnostics)

    def has_errors(self) -> bool:
        """
        title: Return True when the bag contains diagnostics.
        returns: True when the bag contains diagnostics.
        """
        return bool(self.diagnostics)

    def format(
        self,
        *,
        code_formatter: DiagnosticCodeFormatter | None = None,
    ) -> str:
        """
        title: Format the whole bag.
        parameters:
          code_formatter: Code formatter.
        returns: Formatted the whole bag.
        """
        return "\n".join(
            diagnostic.format(code_formatter=code_formatter)
            for diagnostic in self.diagnostics
        )

    def raise_if_errors(self) -> None:
        """
        title: Raise SemanticError when diagnostics exist.
        """
        if self.has_errors():
            raise SemanticError(self)


@public
@typechecked
class IRxDiagnosticError(Exception):
    """
    title: Raised when one non-semantic compiler phase emits a diagnostic.
    attributes:
      diagnostic: Structured diagnostic to inspect or report.
      code_formatter: Code formatter.
    """

    diagnostic: Diagnostic
    code_formatter: DiagnosticCodeFormatter

    def __init__(
        self,
        diagnostic: Diagnostic,
        *,
        code_formatter: DiagnosticCodeFormatter | None = None,
    ) -> None:
        """
        title: Initialize IRxDiagnosticError.
        parameters:
          diagnostic: Structured diagnostic to inspect or report.
          code_formatter: Code formatter.
        """
        self.diagnostic = diagnostic
        self.code_formatter = code_formatter or get_diagnostic_code_formatter()
        super().__init__(diagnostic.format(code_formatter=self.code_formatter))

    def format(self) -> str:
        """
        title: Return the formatted diagnostic message.
        returns: The formatted diagnostic message.
        """
        return self.diagnostic.format(code_formatter=self.code_formatter)


@public
@typechecked
class LoweringError(IRxDiagnosticError):
    """
    title: Raised when lowering fails with one structured diagnostic.
    attributes:
      diagnostic: Structured diagnostic to inspect or report.
      code_formatter: Code formatter.
    """


@public
@typechecked
class NativeCompileError(IRxDiagnosticError):
    """
    title: Raised when native artifact compilation fails.
    attributes:
      diagnostic: Structured diagnostic to inspect or report.
      code_formatter: Code formatter.
    """


@public
@typechecked
class LinkingError(IRxDiagnosticError):
    """
    title: Raised when final executable linking fails.
    attributes:
      diagnostic: Structured diagnostic to inspect or report.
      code_formatter: Code formatter.
    """


@public
@typechecked
class RuntimeFeatureError(IRxDiagnosticError):
    """
    title: Raised when runtime feature activation or symbol resolution fails.
    attributes:
      diagnostic: Structured diagnostic to inspect or report.
      code_formatter: Code formatter.
    """


@public
@typechecked
class SemanticError(Exception):
    """
    title: Raised when semantic analysis fails.
    attributes:
      diagnostics: Collected structured diagnostics.
      code_formatter: Code formatter.
    """

    diagnostics: DiagnosticBag
    code_formatter: DiagnosticCodeFormatter

    def __init__(
        self,
        diagnostics: DiagnosticBag,
        *,
        code_formatter: DiagnosticCodeFormatter | None = None,
    ) -> None:
        """
        title: Initialize SemanticError.
        parameters:
          diagnostics: Collected structured diagnostics.
          code_formatter: Code formatter.
        """
        self.diagnostics = diagnostics
        self.code_formatter = code_formatter or get_diagnostic_code_formatter()
        super().__init__(
            diagnostics.format(code_formatter=self.code_formatter)
        )

    def format(self) -> str:
        """
        title: Return the formatted diagnostic bag.
        returns: The formatted diagnostic bag.
        """
        return self.diagnostics.format(code_formatter=self.code_formatter)


@public
@typechecked
class DiagnosticCodes:
    """
    title: Stable logical diagnostic identifiers.
    summary: Group the most important semantic, lowering,
      FFI, runtime, compile, and link families under short
      stable identifiers. These identifiers are rendered
      through one shared DiagnosticCodeFormatter.
    """

    SEMANTIC_UNRESOLVED_NAME = "S001"
    SEMANTIC_DUPLICATE_DECLARATION = "S002"
    SEMANTIC_INVALID_CONDITION = "S003"
    SEMANTIC_INVALID_RETURN = "S004"
    SEMANTIC_INVALID_ASSIGNMENT_TARGET = "S005"
    SEMANTIC_INVALID_FIELD_ACCESS = "S006"
    SEMANTIC_INVALID_CONTROL_FLOW = "S007"
    SEMANTIC_CALL_ARITY = "S008"
    SEMANTIC_BUFFER_MISUSE = "S009"
    SEMANTIC_TYPE_MISMATCH = "S010"
    SEMANTIC_IMPORT_RESOLUTION = "S011"
    SEMANTIC_IMPORT_CYCLE = "S012"
    SEMANTIC_INVALID_OWNERSHIP = "S013"
    SEMANTIC_INVALID_EXCEPTION = "S014"
    SEMANTIC_MISSING_METADATA = "S015"
    SEMANTIC_UNSUPPORTED_NODE = "S016"
    FFI_INVALID_SIGNATURE = "F001"
    LOWERING_MISSING_SEMANTIC_METADATA = "L001"
    LOWERING_MISSING_HANDLER = "L002"
    LOWERING_TYPE_MISMATCH = "L010"
    LOWERING_INVALID_CONTROL_FLOW = "L011"
    NATIVE_COMPILE_FAILED = "C001"
    LINK_FAILED = "K001"
    RUNTIME_FEATURE_UNKNOWN = "R001"
    RUNTIME_FEATURE_SYMBOL_MISSING = "R002"
    RUNTIME_FEATURE_UNAVAILABLE = "R003"
    RUNTIME_FEATURE_DEPENDENCY_CYCLE = "R004"
    RUNTIME_ARTIFACT_KIND_INVALID = "R003"


__all__ = [
    "DEFAULT_DIAGNOSTIC_CODE_PREFIX",
    "Diagnostic",
    "DiagnosticBag",
    "DiagnosticCodeFormatter",
    "DiagnosticCodes",
    "DiagnosticRelatedInformation",
    "IRxDiagnosticError",
    "LinkingError",
    "LoweringError",
    "NativeCompileError",
    "RuntimeFeatureError",
    "SemanticError",
    "SourceLocation",
    "format_diagnostic_code",
    "format_source_location",
    "get_diagnostic_code_formatter",
    "get_node_module_key",
    "get_node_source_location",
    "set_diagnostic_code_formatter",
    "set_diagnostic_code_prefix",
    "source_location_from_loc",
]
