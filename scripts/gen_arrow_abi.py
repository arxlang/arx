"""
title: Generate Apache Arrow runtime ABI declarations.
summary: Validate the canonical ABI manifest and render language bindings.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, cast

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = (
    ROOT / "packages" / "irx" / "src" / "irx" / "builder" / "runtime" / "arrow"
)
DEFAULT_MANIFEST = RUNTIME_ROOT / "abi.json"
GENERATED_HEADER = RUNTIME_ROOT / "native" / "irx_arrow_abi_generated.h"
GENERATED_INTERNAL_NAMES = (
    RUNTIME_ROOT / "native" / "irx_arrow_abi_internal_names_generated.h"
)
GENERATED_WRAPPERS = (
    RUNTIME_ROOT / "native" / "irx_arrow_abi_wrappers_generated.inc"
)
GENERATED_FEATURE_QUERY = (
    RUNTIME_ROOT / "native" / "irx_arrow_feature_query_generated.inc"
)
GENERATED_PYTHON = RUNTIME_ROOT / "abi_generated.py"
GENERATED_LLVM = RUNTIME_ROOT / "llvm_abi_generated.py"
GENERATED_SYMBOLS = RUNTIME_ROOT / "symbols.generated.txt"
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
PAIR_LENGTH = 2
LINE_LENGTH = 79
PACKED_VERSION_MAJOR_MAX = (1 << 16) - 1
PACKED_VERSION_COMPONENT_MAX = (1 << 8) - 1

FIXED_C_TYPES = {
    "void": "void",
    "status": "irx_arrow_status",
    "status_category": "irx_arrow_status_category",
    "runtime_feature_id": "irx_arrow_runtime_feature_id",
    "handle_kind_pointer": "irx_arrow_handle_kind*",
    "ownership_pointer": "irx_arrow_handle_ownership*",
    "uint32": "uint32_t",
    "uint32_pointer": "uint32_t*",
    "int32": "int32_t",
    "int32_pointer": "int32_t*",
    "int64": "int64_t",
    "uint64": "uint64_t",
    "double": "double",
    "c_string": "const char*",
    "c_string_pointer": "const char**",
    "const_void": "const void*",
    "void_pointer": "void*",
    "const_void_pointer": "const void**",
    "int64_pointer": "int64_t*",
    "const_int64_pointer": "const int64_t*",
    "const_int64_output": "const int64_t**",
    "status_pointer": "irx_arrow_status*",
    "buffer_view": "irx_buffer_view*",
    "const_arrow_schema": "const struct ArrowSchema*",
    "arrow_schema": "struct ArrowSchema*",
    "const_arrow_array": "const struct ArrowArray*",
    "arrow_array": "struct ArrowArray*",
}


@dataclass(frozen=True)
class Handle:
    """
    title: Describe one opaque handle declared by the Arrow ABI.
    attributes:
      id:
        type: int
      name:
        type: str
      c_type:
        type: str
      ownership:
        type: str
      availability:
        type: str
      retain:
        type: str | None
      release:
        type: str
    """

    id: int
    name: str
    c_type: str
    ownership: str
    availability: str
    retain: str | None
    release: str


@dataclass(frozen=True)
class RuntimeFeature:
    """
    title: Describe one versioned Arrow runtime capability.
    attributes:
      id:
        type: int
      name:
        type: str
      contract_version:
        type: tuple[int, int, int]
      availability:
        type: str
    """

    id: int
    name: str
    contract_version: tuple[int, int, int]
    availability: str


@dataclass(frozen=True)
class Function:
    """
    title: Describe one function declared by the Arrow ABI.
    attributes:
      name:
        type: str
      features:
        type: tuple[str, Ellipsis]
      return_type:
        type: str
      parameters:
        type: tuple[tuple[str, str], Ellipsis]
      fallible:
        type: bool
      result:
        type: tuple[str, str] | None
    """

    name: str
    features: tuple[str, ...]
    return_type: str
    parameters: tuple[tuple[str, str], ...]
    fallible: bool
    result: tuple[str, str] | None


@dataclass(frozen=True)
class Manifest:
    """
    title: Hold validated canonical Arrow ABI records.
    attributes:
      version:
        type: tuple[int, int, int]
      status_codes:
        type: tuple[tuple[str, int], Ellipsis]
      status_categories:
        type: tuple[tuple[str, int], Ellipsis]
      ownership_kinds:
        type: tuple[tuple[str, int], Ellipsis]
      type_ids:
        type: tuple[tuple[str, int], Ellipsis]
      runtime_features:
        type: tuple[RuntimeFeature, Ellipsis]
      handles:
        type: tuple[Handle, Ellipsis]
      functions:
        type: tuple[Function, Ellipsis]
    """

    version: tuple[int, int, int]
    status_codes: tuple[tuple[str, int], ...]
    status_categories: tuple[tuple[str, int], ...]
    ownership_kinds: tuple[tuple[str, int], ...]
    type_ids: tuple[tuple[str, int], ...]
    runtime_features: tuple[RuntimeFeature, ...]
    handles: tuple[Handle, ...]
    functions: tuple[Function, ...]


def load_enum_records(
    raw: dict[str, object], field: str
) -> tuple[tuple[str, int], ...]:
    """
    title: Load and validate one named integer record list.
    parameters:
      raw:
        type: dict[str, object]
      field:
        type: str
    returns:
      type: tuple[tuple[str, int], Ellipsis]
    """
    records = cast(list[list[object]], raw.get(field))
    if not isinstance(records, list) or not records:
        raise ValueError(f"'{field}' must be a non-empty list")

    result: list[tuple[str, int]] = []
    for record in records:
        if not isinstance(record, list) or len(record) != PAIR_LENGTH:
            raise ValueError(f"'{field}' records must be [name, value]")
        name, value = record
        if not isinstance(name, str) or not IDENTIFIER_PATTERN.fullmatch(name):
            raise ValueError(f"'{field}' contains an invalid name")
        if not isinstance(value, int):
            raise ValueError(f"'{field}' contains a non-integer value")
        result.append((name, value))

    if len({name for name, _ in result}) != len(result):
        raise ValueError(f"'{field}' contains duplicate names")
    if len({value for _, value in result}) != len(result):
        raise ValueError(f"'{field}' contains duplicate values")
    return tuple(result)


def load_runtime_features(
    raw: dict[str, object],
) -> tuple[RuntimeFeature, ...]:
    """
    title: Load and validate versioned runtime-feature declarations.
    parameters:
      raw:
        type: dict[str, object]
    returns:
      type: tuple[RuntimeFeature, Ellipsis]
    """
    records = cast(list[dict[str, object]], raw.get("runtime_features"))
    if not isinstance(records, list) or not records:
        raise ValueError("'runtime_features' must be a non-empty list")

    features: list[RuntimeFeature] = []
    for record in records:
        feature_id = record.get("id")
        name = record.get("name")
        version_text = record.get("contract_version")
        availability = record.get("availability")
        if not isinstance(feature_id, int):
            raise ValueError("runtime feature id must be an integer")
        if not isinstance(name, str) or not IDENTIFIER_PATTERN.fullmatch(name):
            raise ValueError("runtime feature name must be an identifier")
        if name != name.lower():
            raise ValueError("runtime feature names must be lowercase")
        if not isinstance(version_text, str):
            raise ValueError(
                f"runtime feature '{name}' must have a semantic version"
            )
        match = VERSION_PATTERN.fullmatch(version_text)
        if match is None:
            raise ValueError(
                f"runtime feature '{name}' must have a semantic version"
            )
        version = tuple(int(part) for part in match.groups())
        major, minor, patch = version
        if major > PACKED_VERSION_MAJOR_MAX or any(
            component > PACKED_VERSION_COMPONENT_MAX
            for component in (minor, patch)
        ):
            raise ValueError(
                f"runtime feature '{name}' version cannot be packed"
            )
        if not isinstance(availability, str) or not (
            availability == "implemented"
            or availability.startswith("planned_m")
        ):
            raise ValueError(
                f"runtime feature '{name}' has invalid availability"
            )
        features.append(
            RuntimeFeature(
                feature_id,
                name,
                cast(tuple[int, int, int], version),
                availability,
            )
        )

    if [feature.id for feature in features] != list(
        range(1, len(features) + 1)
    ):
        raise ValueError(
            "runtime feature ids must be contiguous and start at one"
        )
    if len({feature.name for feature in features}) != len(features):
        raise ValueError("runtime feature names must be unique")
    return tuple(features)


def load_handles(raw: dict[str, object]) -> tuple[Handle, ...]:
    """
    title: Load and validate opaque handle declarations.
    parameters:
      raw:
        type: dict[str, object]
    returns:
      type: tuple[Handle, Ellipsis]
    """
    records = cast(list[dict[str, object]], raw.get("handles"))
    if not isinstance(records, list) or not records:
        raise ValueError("'handles' must be a non-empty list")

    handles: list[Handle] = []
    for record in records:
        handle_id = record.get("id")
        name = record.get("name")
        c_type = record.get("c_type")
        ownership = record.get("ownership")
        availability = record.get("availability")
        retain = record.get("retain")
        release = record.get("release")
        if not isinstance(handle_id, int):
            raise ValueError("handle id must be an integer")
        if not isinstance(name, str) or not IDENTIFIER_PATTERN.fullmatch(name):
            raise ValueError("handle name must be an identifier")
        if not isinstance(c_type, str) or not IDENTIFIER_PATTERN.fullmatch(
            c_type
        ):
            raise ValueError(f"handle '{name}' has an invalid C type")
        if ownership not in {"shared", "unique"}:
            raise ValueError(f"handle '{name}' has invalid ownership")
        if not isinstance(availability, str):
            raise ValueError(f"handle '{name}' has invalid availability")
        if retain is not None and not isinstance(retain, str):
            raise ValueError(f"handle '{name}' has an invalid retain symbol")
        if not isinstance(release, str):
            raise ValueError(f"handle '{name}' has an invalid release symbol")
        handles.append(
            Handle(
                handle_id,
                name,
                c_type,
                ownership,
                availability,
                retain,
                release,
            )
        )

    if [handle.id for handle in handles] != list(range(1, len(handles) + 1)):
        raise ValueError("handle ids must be contiguous and start at one")
    if len({handle.name for handle in handles}) != len(handles):
        raise ValueError("handle names must be unique")
    if len({handle.c_type for handle in handles}) != len(handles):
        raise ValueError("handle C types must be unique")
    return tuple(handles)


def c_type_for(token: str, handles: tuple[Handle, ...]) -> str:
    """
    title: Resolve one manifest type token to its C ABI spelling.
    parameters:
      token:
        type: str
      handles:
        type: tuple[Handle, Ellipsis]
    returns:
      type: str
    """
    fixed = FIXED_C_TYPES.get(token)
    if fixed is not None:
        return fixed

    for handle in handles:
        if token == handle.name:
            return f"{handle.c_type}*"
        if token == f"const_{handle.name}":
            return f"const {handle.c_type}*"
        if token == f"{handle.name}_pointer":
            return f"{handle.c_type}**"
    raise ValueError(f"unknown ABI type token '{token}'")


def load_result(
    record: dict[str, object],
    function_name: str,
    return_type: str,
    fallible: bool,
    handles: tuple[Handle, ...],
) -> tuple[str, str] | None:
    """
    title: Load and validate one optional ordinary result slot.
    parameters:
      record:
        type: dict[str, object]
      function_name:
        type: str
      return_type:
        type: str
      fallible:
        type: bool
      handles:
        type: tuple[Handle, Ellipsis]
    returns:
      type: tuple[str, str] | None
    """
    result_record = record.get("result")
    if result_record is None:
        if fallible and return_type != "status":
            raise ValueError(
                f"fallible function '{function_name}' must define a result"
            )
        return None
    if not isinstance(result_record, list) or (
        len(result_record) != PAIR_LENGTH
    ):
        raise ValueError(f"function '{function_name}' has an invalid result")

    result_type, result_name = result_record
    if not isinstance(result_type, str):
        raise ValueError(
            f"function '{function_name}' has an invalid result type"
        )
    if not isinstance(result_name, str) or not (
        IDENTIFIER_PATTERN.fullmatch(result_name)
    ):
        raise ValueError(
            f"function '{function_name}' has an invalid result name"
        )
    if not fallible:
        raise ValueError(
            f"infallible function '{function_name}' cannot define a result"
        )
    c_type_for(result_type, handles)
    return result_type, result_name


def load_functions(
    raw: dict[str, object],
    handles: tuple[Handle, ...],
    runtime_features: tuple[RuntimeFeature, ...],
) -> tuple[Function, ...]:
    """
    title: Load and validate function declarations.
    parameters:
      raw:
        type: dict[str, object]
      handles:
        type: tuple[Handle, Ellipsis]
      runtime_features:
        type: tuple[RuntimeFeature, Ellipsis]
    returns:
      type: tuple[Function, Ellipsis]
    """
    records = cast(list[dict[str, object]], raw.get("functions"))
    if not isinstance(records, list) or not records:
        raise ValueError("'functions' must be a non-empty list")

    runtime_feature_names = {feature.name for feature in runtime_features}
    functions: list[Function] = []
    for record in records:
        name = record.get("name")
        feature_records = record.get("features")
        return_type = record.get("return")
        parameter_records = record.get("parameters")
        fallible = record.get("fallible", True)
        if not isinstance(name, str) or not name.startswith("irx_arrow_"):
            raise ValueError("function names must use the 'irx_arrow_' prefix")
        if not IDENTIFIER_PATTERN.fullmatch(name):
            raise ValueError(f"function '{name}' is not a C identifier")
        if not isinstance(feature_records, list) or not all(
            isinstance(feature, str) for feature in feature_records
        ):
            raise ValueError(f"function '{name}' has invalid features")
        features = cast(list[str], feature_records)
        if len(set(features)) != len(features) or any(
            feature not in runtime_feature_names for feature in features
        ):
            raise ValueError(f"function '{name}' has unknown features")
        if not isinstance(return_type, str):
            raise ValueError(f"function '{name}' has an invalid return type")
        c_type_for(return_type, handles)
        if not isinstance(fallible, bool):
            raise ValueError(f"function '{name}' has invalid fallibility")
        if not isinstance(parameter_records, list):
            raise ValueError(f"function '{name}' has invalid parameters")

        parameters: list[tuple[str, str]] = []
        for parameter in parameter_records:
            if (
                not isinstance(parameter, list)
                or len(parameter) != PAIR_LENGTH
            ):
                raise ValueError(
                    f"function '{name}' parameters must be [type, name]"
                )
            type_token, parameter_name = parameter
            if not isinstance(type_token, str):
                raise ValueError(f"function '{name}' has invalid type token")
            if not isinstance(parameter_name, str) or not (
                IDENTIFIER_PATTERN.fullmatch(parameter_name)
            ):
                raise ValueError(
                    f"function '{name}' has invalid parameter name"
                )
            c_type_for(type_token, handles)
            parameters.append((type_token, parameter_name))
        if len({item[1] for item in parameters}) != len(parameters):
            raise ValueError(
                f"function '{name}' has duplicate parameter names"
            )
        result = load_result(
            record,
            name,
            return_type,
            fallible,
            handles,
        )
        functions.append(
            Function(
                name,
                tuple(features),
                return_type,
                tuple(parameters),
                fallible,
                result,
            )
        )

    names = {function.name for function in functions}
    if len(names) != len(functions):
        raise ValueError("function names must be unique")
    for handle in handles:
        if handle.availability != "implemented":
            continue
        if handle.release not in names:
            raise ValueError(
                "implemented handle "
                f"'{handle.name}' has no release declaration"
            )
        if handle.retain is not None and handle.retain not in names:
            raise ValueError(
                f"implemented handle '{handle.name}' has no retain declaration"
            )
    return tuple(functions)


def load_manifest(path: Path) -> Manifest:
    """
    title: Load and validate the canonical Arrow ABI manifest.
    parameters:
      path:
        type: Path
    returns:
      type: Manifest
    """
    raw = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    if raw.get("schema_version") != 1:
        raise ValueError("unsupported Arrow ABI manifest schema version")
    version_text = raw.get("abi_version")
    if not isinstance(version_text, str):
        raise ValueError("'abi_version' must be a semantic version")
    match = VERSION_PATTERN.fullmatch(version_text)
    if match is None:
        raise ValueError("'abi_version' must be a semantic version")

    handles = load_handles(raw)
    runtime_features = load_runtime_features(raw)
    return Manifest(
        version=(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        ),
        status_codes=load_enum_records(raw, "status_codes"),
        status_categories=load_enum_records(raw, "status_categories"),
        ownership_kinds=load_enum_records(raw, "ownership_kinds"),
        type_ids=load_enum_records(raw, "type_ids"),
        runtime_features=runtime_features,
        handles=handles,
        functions=load_functions(raw, handles, runtime_features),
    )


def render_enum(
    typedef_name: str,
    enum_name: str,
    constant_prefix: str,
    records: tuple[tuple[str, int], ...],
    include_typedef: bool = True,
) -> list[str]:
    """
    title: Render one stable C integer enumeration.
    parameters:
      typedef_name:
        type: str
      enum_name:
        type: str
      constant_prefix:
        type: str
      records:
        type: tuple[tuple[str, int], Ellipsis]
      include_typedef:
        type: bool
    returns:
      type: list[str]
    """
    lines: list[str] = []
    if include_typedef:
        lines.extend([f"typedef int32_t {typedef_name};", ""])
    lines.append(f"enum {enum_name} {{")
    lines.extend(
        f"  {constant_prefix}{name} = {value}," for name, value in records
    )
    lines.extend(["};", ""])
    return lines


def packed_version(version: tuple[int, int, int]) -> int:
    """
    title: Pack one feature-contract version as 0xMMMMmmpp.
    parameters:
      version:
        type: tuple[int, int, int]
    returns:
      type: int
    """
    major, minor, patch = version
    return (major << 16) | (minor << 8) | patch


def render_runtime_features(
    features: tuple[RuntimeFeature, ...],
) -> list[str]:
    """
    title: Render stable runtime-feature IDs and contract versions.
    parameters:
      features:
        type: tuple[RuntimeFeature, Ellipsis]
    returns:
      type: list[str]
    """
    records = tuple((feature.name.upper(), feature.id) for feature in features)
    lines = render_enum(
        "irx_arrow_runtime_feature_id",
        "irx_arrow_runtime_feature_id_code",
        "IRX_ARROW_RUNTIME_FEATURE_",
        (("UNKNOWN", 0), *records),
    )
    for feature in features:
        prefix = f"IRX_ARROW_RUNTIME_FEATURE_{feature.name.upper()}_CONTRACT"
        major, minor, patch = feature.contract_version
        lines.extend(
            [
                f"#define {prefix}_VERSION_MAJOR UINT32_C({major})",
                f"#define {prefix}_VERSION_MINOR UINT32_C({minor})",
                f"#define {prefix}_VERSION_PATCH UINT32_C({patch})",
                f"#define {prefix}_VERSION \\",
                f"  (({prefix}_VERSION_MAJOR << 16) | \\",
                f"   ({prefix}_VERSION_MINOR << 8) | \\",
                f"   {prefix}_VERSION_PATCH)",
                "",
            ]
        )
    return lines


def public_signature(
    function: Function,
) -> tuple[str, tuple[tuple[str, str], ...]]:
    """
    title: Build the public signature for one manifest function.
    parameters:
      function:
        type: Function
    returns:
      type: tuple[str, tuple[tuple[str, str], Ellipsis]]
    """
    if not function.fallible:
        return function.return_type, function.parameters

    parameters = list(function.parameters)
    if function.result is not None:
        parameters.append(function.result)
    parameters.append(("error_pointer", "out_failure"))
    return "status", tuple(parameters)


def render_header(manifest: Manifest) -> str:
    """
    title: Render the generated public C ABI header.
    parameters:
      manifest:
        type: Manifest
    returns:
      type: str
    """
    major, minor, patch = manifest.version
    lines = [
        "// Generated by scripts/gen_arrow_abi.py. Do not edit.",
        "",
        "#ifndef IRX_ARROW_ABI_GENERATED_H_INCLUDED",
        "#define IRX_ARROW_ABI_GENERATED_H_INCLUDED",
        "",
        "#include <stddef.h>",
        "#include <stdint.h>",
        "",
        '#include "irx_arrow_c_abi.h"',
        '#include "irx_buffer_runtime.h"',
        "",
        "#ifdef __cplusplus",
        'extern "C" {',
        "#endif",
        "",
        f"#define IRX_ARROW_ABI_VERSION_MAJOR UINT32_C({major})",
        f"#define IRX_ARROW_ABI_VERSION_MINOR UINT32_C({minor})",
        f"#define IRX_ARROW_ABI_VERSION_PATCH UINT32_C({patch})",
        "#define IRX_ARROW_ABI_VERSION \\",
        "  ((IRX_ARROW_ABI_VERSION_MAJOR << 16) | \\",
        "   (IRX_ARROW_ABI_VERSION_MINOR << 8) | \\",
        "   IRX_ARROW_ABI_VERSION_PATCH)",
        "",
    ]
    lines.extend(
        render_enum(
            "irx_arrow_status",
            "irx_arrow_status_code",
            "IRX_ARROW_STATUS_",
            manifest.status_codes,
        )
    )
    lines.extend(
        render_enum(
            "irx_arrow_status_category",
            "irx_arrow_status_category_code",
            "IRX_ARROW_STATUS_CATEGORY_",
            manifest.status_categories,
        )
    )
    lines.extend(render_runtime_features(manifest.runtime_features))
    for handle in manifest.handles:
        lines.append(f"typedef struct {handle.c_type} {handle.c_type};")
    lines.append("")
    handle_kinds = (
        ("UNKNOWN", 0),
        *((handle.name.upper(), handle.id) for handle in manifest.handles),
    )
    lines.extend(
        render_enum(
            "irx_arrow_handle_kind",
            "irx_arrow_handle_kind_code",
            "IRX_ARROW_HANDLE_KIND_",
            handle_kinds,
        )
    )
    lines.extend(
        render_enum(
            "irx_arrow_handle_ownership",
            "irx_arrow_handle_ownership_code",
            "IRX_ARROW_HANDLE_OWNERSHIP_",
            manifest.ownership_kinds,
        )
    )
    lines.extend(
        render_enum(
            "",
            "irx_arrow_type_id",
            "IRX_ARROW_TYPE_",
            manifest.type_ids,
            include_typedef=False,
        )
    )
    for function in manifest.functions:
        if function.name == "irx_arrow_runtime_has_feature":
            lines.extend(
                [
                    "/*",
                    " * Query one runtime feature contract.",
                    " * A zero required version discovers any implemented",
                    " * contract. Unknown IDs return OK with unavailable and",
                    " * version zero. Known incompatible IDs report their",
                    " * supported version.",
                    " */",
                ]
            )
        return_token, parameters = public_signature(function)
        return_type = c_type_for(return_token, manifest.handles)
        if not parameters:
            lines.extend([f"{return_type} {function.name}(void);", ""])
            continue
        lines.append(f"{return_type} {function.name}(")
        for index, (type_token, name) in enumerate(parameters):
            suffix = ");" if index == len(parameters) - 1 else ","
            c_type = c_type_for(type_token, manifest.handles)
            lines.append(f"    {c_type} {name}{suffix}")
        lines.append("")
    lines.extend(
        [
            "#ifdef __cplusplus",
            "}",
            "#endif",
            "",
            "#endif",
            "",
        ]
    )
    return "\n".join(lines)


def render_signature_rows(functions: tuple[Function, ...]) -> list[str]:
    """
    title: Render generated Python ABI signature rows.
    parameters:
      functions:
        type: tuple[Function, Ellipsis]
    returns:
      type: list[str]
    """
    rows: list[str] = []
    for function in functions:
        return_type, public_parameters = public_signature(function)
        rows.extend(
            [
                f'    "{function.name}": (',
                f'        "{return_type}",',
            ]
        )
        if not public_parameters:
            rows.append("        (),")
        elif len(public_parameters) == 1:
            type_token = public_parameters[0][0]
            rows.append(f'        ("{type_token}",),')
        else:
            rows.append("        (")
            rows.extend(
                f'            "{type_token}",'
                for type_token, _ in public_parameters
            )
            rows.append("        ),")
        rows.append("    ),")
    return rows


def render_feature_rows(
    features: tuple[RuntimeFeature, ...],
    functions: tuple[Function, ...],
) -> list[str]:
    """
    title: Render generated runtime-feature symbol rows.
    parameters:
      features:
        type: tuple[RuntimeFeature, Ellipsis]
      functions:
        type: tuple[Function, Ellipsis]
    returns:
      type: list[str]
    """
    rows: list[str] = []
    for feature in features:
        names = tuple(
            function.name
            for function in functions
            if feature.name in function.features
        )
        if not names:
            rows.append(f'    "{feature.name}": (),')
            continue
        rows.append(f'    "{feature.name}": (')
        rows.extend(f'        "{name}",' for name in names)
        rows.append("    ),")
    return rows


def render_python(manifest: Manifest) -> str:
    """
    title: Render generated Python ctypes declaration metadata.
    parameters:
      manifest:
        type: Manifest
    returns:
      type: str
    """
    lines = [
        '"""',
        "title: Generated Python declarations for the Arrow runtime ABI.",
        "summary: Do not edit; regenerate from abi.json.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        f"ABI_VERSION = {manifest.version!r}",
        "RUNTIME_FEATURE_IDS = {",
        *(
            f'    "{feature.name}": {feature.id},'
            for feature in manifest.runtime_features
        ),
        "}",
        "RUNTIME_FEATURE_VERSIONS = {",
        *(
            f'    "{feature.name}": {feature.contract_version!r},'
            for feature in manifest.runtime_features
        ),
        "}",
        "RUNTIME_FEATURE_PACKED_VERSIONS = {",
        *(
            f'    "{feature.name}": '
            f"{packed_version(feature.contract_version)},"
            for feature in manifest.runtime_features
        ),
        "}",
        "HANDLE_TYPES = (",
        *(f'    "{handle.name}",' for handle in manifest.handles),
        ")",
        "CTYPES_SIGNATURES: dict[str, tuple[str, tuple[str, ...]]] = {",
        *render_signature_rows(manifest.functions),
        "}",
        "FEATURE_SYMBOLS: dict[str, tuple[str, ...]] = {",
        *render_feature_rows(manifest.runtime_features, manifest.functions),
        "}",
        "FALLIBLE_SYMBOLS = (",
        *(
            f'    "{function.name}",'
            for function in manifest.functions
            if function.fallible
        ),
        ")",
        "VALUE_RESULTS: dict[str, str] = {",
        *(
            f'    "{function.name}": "{function.return_type}",'
            for function in manifest.functions
            if function.result is not None
        ),
        "}",
        "ABI_SYMBOLS = tuple(CTYPES_SIGNATURES)",
        "",
        "__all__ = [",
        '    "ABI_SYMBOLS",',
        '    "ABI_VERSION",',
        '    "CTYPES_SIGNATURES",',
        '    "FALLIBLE_SYMBOLS",',
        '    "FEATURE_SYMBOLS",',
        '    "HANDLE_TYPES",',
        '    "RUNTIME_FEATURE_IDS",',
        '    "RUNTIME_FEATURE_PACKED_VERSIONS",',
        '    "RUNTIME_FEATURE_VERSIONS",',
        '    "VALUE_RESULTS",',
        "]",
        "",
    ]
    return "\n".join(lines)


def render_llvm(manifest: Manifest) -> str:
    """
    title: Render generated LLVM declaration metadata.
    parameters:
      manifest:
        type: Manifest
    returns:
      type: str
    """
    lines = [
        '"""',
        "title: Generated LLVM declarations for the Arrow runtime ABI.",
        "summary: Do not edit; regenerate from abi.json.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "LLVM_RUNTIME_FEATURE_IDS = {",
        *(
            f'    "{feature.name}": {feature.id},'
            for feature in manifest.runtime_features
        ),
        "}",
        "LLVM_RUNTIME_FEATURE_VERSIONS = {",
        *(
            f'    "{feature.name}": '
            f"{packed_version(feature.contract_version)},"
            for feature in manifest.runtime_features
        ),
        "}",
        "LLVM_HANDLE_TYPES = (",
        *(f'    "{handle.name}",' for handle in manifest.handles),
        ")",
        "LLVM_SIGNATURES: dict[str, tuple[str, tuple[str, ...]]] = {",
        *render_signature_rows(manifest.functions),
        "}",
        "LLVM_FEATURE_SYMBOLS: dict[str, tuple[str, ...]] = {",
        *render_feature_rows(manifest.runtime_features, manifest.functions),
        "}",
        "",
        "__all__ = [",
        '    "LLVM_FEATURE_SYMBOLS",',
        '    "LLVM_HANDLE_TYPES",',
        '    "LLVM_RUNTIME_FEATURE_IDS",',
        '    "LLVM_RUNTIME_FEATURE_VERSIONS",',
        '    "LLVM_SIGNATURES",',
        "]",
        "",
    ]
    return "\n".join(lines)


def render_internal_names(manifest: Manifest) -> str:
    """
    title: Render private preprocessor aliases for native implementations.
    parameters:
      manifest:
        type: Manifest
    returns:
      type: str
    """
    lines = [
        "// Generated by scripts/gen_arrow_abi.py. Do not edit.",
        "",
        "#ifndef IRX_ARROW_ABI_INTERNAL_NAMES_GENERATED_H_INCLUDED",
        "#define IRX_ARROW_ABI_INTERNAL_NAMES_GENERATED_H_INCLUDED",
        "",
    ]
    for function in manifest.functions:
        lines.extend(
            [
                f"#define {function.name} \\",
                f"  irx_arrow_internal_{function.name[10:]}",
            ]
        )
    lines.append("")
    for function in manifest.functions:
        return_type = c_type_for(function.return_type, manifest.handles)
        if not function.parameters:
            lines.extend([f"{return_type} {function.name}(void);", ""])
            continue
        lines.append(f"{return_type} {function.name}(")
        for index, (type_token, name) in enumerate(function.parameters):
            suffix = ");" if index == len(function.parameters) - 1 else ","
            c_type = c_type_for(type_token, manifest.handles)
            lines.append(f"    {c_type} {name}{suffix}")
        lines.append("")
    lines.extend(["", "#endif", ""])
    return "\n".join(lines)


def render_c_parameters(
    parameters: tuple[tuple[str, str], ...],
    handles: tuple[Handle, ...],
) -> list[str]:
    """
    title: Render a C parameter list for a generated wrapper.
    parameters:
      parameters:
        type: tuple[tuple[str, str], Ellipsis]
      handles:
        type: tuple[Handle, Ellipsis]
    returns:
      type: list[str]
    """
    if not parameters:
        return ["void"]
    return [
        f"{c_type_for(token, handles)} {name}" for token, name in parameters
    ]


def render_wrapper_signature(
    return_type: str,
    name: str,
    parameters: tuple[tuple[str, str], ...],
    handles: tuple[Handle, ...],
) -> list[str]:
    """
    title: Render one generated wrapper definition signature.
    parameters:
      return_type:
        type: str
      name:
        type: str
      parameters:
        type: tuple[tuple[str, str], Ellipsis]
      handles:
        type: tuple[Handle, Ellipsis]
    returns:
      type: list[str]
    """
    rendered = render_c_parameters(parameters, handles)
    if rendered == ["void"]:
        return [f"{c_type_for(return_type, handles)} {name}(void) {{"]
    lines = [f"{c_type_for(return_type, handles)} {name}("]
    lines.extend(
        f"    {parameter}{',' if index < len(rendered) - 1 else ') {'}"
        for index, parameter in enumerate(rendered)
    )
    return lines


def render_internal_call(function: Function, indentation: str) -> list[str]:
    """
    title: Render one private implementation call as a C expression.
    parameters:
      function:
        type: Function
      indentation:
        type: str
    returns:
      type: list[str]
    """
    name = f"irx_arrow_internal_{function.name[10:]}"
    arguments = tuple(parameter[1] for parameter in function.parameters)
    compact = f"{indentation}{name}({', '.join(arguments)});"
    if len(compact) <= LINE_LENGTH:
        return [compact]

    lines = [f"{indentation}{name}("]
    lines.extend(
        f"{indentation}    {argument}"
        f"{',' if index < len(arguments) - 1 else ');'}"
        for index, argument in enumerate(arguments)
    )
    return lines


def render_wrapper(
    function: Function, handles: tuple[Handle, ...]
) -> list[str]:
    """
    title: Render one public wrapper around a private native implementation.
    parameters:
      function:
        type: Function
      handles:
        type: tuple[Handle, Ellipsis]
    returns:
      type: list[str]
    """
    return_type, parameters = public_signature(function)
    lines = render_wrapper_signature(
        return_type,
        function.name,
        parameters,
        handles,
    )
    arguments = ", ".join(name for _, name in function.parameters)
    call = f"irx_arrow_internal_{function.name[10:]}({arguments})"
    if not function.fallible:
        if function.return_type == "void":
            lines.extend([f"  {call};", "}", ""])
        else:
            lines.extend([f"  return {call};", "}", ""])
        return lines

    lines.extend(
        [
            "  if (out_failure == nullptr) {",
            f'    begin_operation("{function.name}");',
            "    return set_error(",
            "        IRX_ARROW_STATUS_NULL_POINTER,",
            '        "out_failure must not be NULL");',
            "  }",
            "  *out_failure = nullptr;",
        ]
    )
    if function.result is None:
        lines.extend(
            [
                "  const irx_arrow_status status =",
                *render_internal_call(function, "      "),
                "  return finish_generated_call(",
                "      status,",
                f'      "{function.name}",',
                "      out_failure);",
                "}",
                "",
            ]
        )
        return lines

    _, result_name = function.result
    default_value = (
        "nullptr"
        if function.return_type in {"c_string", "const_int64_pointer"}
        else "0"
    )
    result_c_type = c_type_for(function.return_type, handles)
    lines.extend(
        [
            f"  if ({result_name} == nullptr) {{",
            f'    begin_operation("{function.name}");',
            "    const irx_arrow_status status = set_error(",
            "        IRX_ARROW_STATUS_NULL_POINTER,",
            f'        "{result_name} must not be NULL");',
            "    return finish_generated_call(",
            "        status,",
            f'        "{function.name}",',
            "        out_failure);",
            "  }",
            f"  *{result_name} = {default_value};",
            f"  {result_c_type} value =",
            *render_internal_call(function, "      "),
            "  const irx_arrow_status status = current_error.code;",
            "  if (status == IRX_ARROW_STATUS_OK) {",
            f"    *{result_name} = value;",
            "  }",
            "  return finish_generated_call(",
            "      status,",
            f'      "{function.name}",',
            "      out_failure);",
            "}",
            "",
        ]
    )
    return lines


def render_wrappers(manifest: Manifest) -> str:
    """
    title: Render public wrappers that publish explicit owned error details.
    parameters:
      manifest:
        type: Manifest
    returns:
      type: str
    """
    lines = [
        "// Generated by scripts/gen_arrow_abi.py. Do not edit.",
        "",
    ]
    lines.extend(f"#undef {function.name}" for function in manifest.functions)
    lines.extend(
        [
            "",
            "#if defined(__GNUC__) || defined(__clang__)",
            "#pragma GCC visibility pop",
            "#endif",
            "",
            "static irx_arrow_status finish_generated_call(",
            "    irx_arrow_status status,",
            "    const char* operation,",
            "    irx_arrow_error_handle** out_failure) {",
            "  if (status == IRX_ARROW_STATUS_OK ||",
            "      status == IRX_ARROW_STATUS_END_OF_STREAM) {",
            "    return status;",
            "  }",
            "  copy_error_text(",
            "      current_error.operation,",
            "      sizeof(current_error.operation),",
            "      operation);",
            "  const irx_arrow_status snapshot_status =",
            "      irx_arrow_internal_error_snapshot(out_failure);",
            "  if (snapshot_status != IRX_ARROW_STATUS_OK) {",
            "    *out_failure = nullptr;",
            "  }",
            "  return status;",
            "}",
            "",
        ]
    )
    for function in manifest.functions:
        lines.extend(render_wrapper(function, manifest.handles))
    return "\n".join(lines)


def render_feature_query(manifest: Manifest) -> str:
    """
    title: Render implemented feature-contract lookup cases.
    parameters:
      manifest:
        type: Manifest
    returns:
      type: str
    """
    lines = ["// Generated by scripts/gen_arrow_abi.py. Do not edit.", ""]
    for feature in manifest.runtime_features:
        if feature.availability != "implemented":
            continue
        prefix = f"IRX_ARROW_RUNTIME_FEATURE_{feature.name.upper()}"
        lines.extend(
            [
                f"case {prefix}:",
                f"  supported_contract_version = {prefix}_CONTRACT_VERSION;",
                "  break;",
            ]
        )
    return "\n".join(lines) + "\n"


def expected_outputs(manifest: Manifest) -> dict[Path, str]:
    """
    title: Build every generated Arrow ABI output.
    parameters:
      manifest:
        type: Manifest
    returns:
      type: dict[Path, str]
    """
    return {
        GENERATED_HEADER: render_header(manifest),
        GENERATED_INTERNAL_NAMES: render_internal_names(manifest),
        GENERATED_WRAPPERS: render_wrappers(manifest),
        GENERATED_FEATURE_QUERY: render_feature_query(manifest),
        GENERATED_PYTHON: render_python(manifest),
        GENERATED_LLVM: render_llvm(manifest),
        GENERATED_SYMBOLS: "\n".join(
            function.name for function in manifest.functions
        )
        + "\n",
    }


def update_outputs(outputs: dict[Path, str], check: bool) -> int:
    """
    title: Write generated outputs or report stale files.
    parameters:
      outputs:
        type: dict[Path, str]
      check:
        type: bool
    returns:
      type: int
    """
    stale = [
        path
        for path, content in outputs.items()
        if not path.exists() or path.read_text(encoding="utf-8") != content
    ]
    if check:
        if stale:
            for path in stale:
                print(
                    f"stale generated Arrow ABI output: {path}",
                    file=sys.stderr,
                )
            return 1
        return 0

    for path in stale:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(outputs[path], encoding="utf-8")
        print(f"updated {path.relative_to(ROOT)}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """
    title: Generate or validate Arrow ABI declarations.
    parameters:
      argv:
        type: Sequence[str] | None
    returns:
      type: int
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        manifest = load_manifest(arguments.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"invalid Arrow ABI manifest: {error}", file=sys.stderr)
        return 1
    return update_outputs(expected_outputs(manifest), arguments.check)


if __name__ == "__main__":
    raise SystemExit(main())
