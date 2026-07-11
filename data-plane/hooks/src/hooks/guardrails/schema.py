"""Minimal JSON-schema validation for model output (no external dependency).

Supports the subset we need for output validation: object type, required keys,
and per-property primitive types (string/number/integer/boolean/array/object).
"""

from __future__ import annotations

import json
from typing import Any

_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def validate(text: str, schema: dict[str, Any]) -> tuple[bool, str | None]:
    """Return (ok, error). Parses text as JSON and checks it against schema."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return False, "output is not valid JSON"

    if schema.get("type") == "object" and not isinstance(data, dict):
        return False, "expected a JSON object"

    for key in schema.get("required", []):
        if not isinstance(data, dict) or key not in data:
            return False, f"missing required field: {key}"

    for key, spec in schema.get("properties", {}).items():
        if isinstance(data, dict) and key in data:
            expected = _TYPES.get(spec.get("type", ""))
            # bool is a subclass of int; guard so integers don't accept booleans.
            if expected is _TYPES["integer"] and isinstance(data[key], bool):
                return False, f"field {key} has wrong type"
            if expected is not None and not isinstance(data[key], expected):
                return False, f"field {key} has wrong type"
    return True, None
