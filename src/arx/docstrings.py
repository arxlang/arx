"""
title: Validate Arx docstrings against the Douki YAML schema.
"""

from __future__ import annotations

import json
import textwrap

from functools import lru_cache
from importlib.resources import files
from typing import Any, cast

import yaml

from jsonschema import ValidationError, validate


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    """
    title: Load and cache the Douki JSON schema used by Arx.
    returns:
      type: dict[str, Any]
    """
    with files("arx").joinpath("douki_schema.json").open(
        encoding="utf-8"
    ) as fh:
        return cast(dict[str, Any], json.load(fh))


def validate_docstring(raw: str) -> dict[str, Any]:
    """
    title: Validate docstring content as Douki YAML.
    parameters:
      raw:
        type: str
        description: Raw text found inside the docstring block.
    returns:
      type: dict[str, Any]
    """
    normalized = textwrap.dedent(raw).strip()
    if not normalized:
        raise ValueError("Docstring block cannot be empty.")

    try:
        data = yaml.safe_load(normalized)
    except yaml.YAMLError as err:
        raise ValueError("Docstring content must be valid YAML.") from err

    if not isinstance(data, dict):
        raise ValueError("Docstring YAML must define an object mapping.")

    try:
        validate(instance=data, schema=_schema())
    except ValidationError as err:
        raise ValueError(
            f"Docstring YAML does not follow douki schema: {err.message}"
        ) from err

    return cast(dict[str, Any], data)
