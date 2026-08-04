"""A JSON Schema subset validator, hand-written on purpose.

`backend/requirements.txt` carries no `jsonschema`, and a catalogue that only
validates when an optional dependency happens to be installed is a catalogue
that does not validate. The subset here is exactly what
`catalog/_schema/pack.schema.json` uses — `type`, `enum`, `const`, `required`,
`properties`, `additionalProperties`, `items`, `pattern`, `minLength`,
`minItems`, `minimum`, `maximum`, `oneOf`, `allOf`, `not`, `if`/`then` — and
anything outside it raises rather than silently passing.

Adding a keyword to the schema without adding it here is therefore a loud
failure, not a quiet hole.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_KNOWN = {
    "$schema", "$id", "title", "description",
    "type", "enum", "const", "required", "properties", "additionalProperties",
    "items", "pattern", "minLength", "minItems", "minimum", "maximum",
    "oneOf", "allOf", "not", "if", "then", "propertyNames", "default",
}

_TYPES = {
    "object": dict, "array": list, "string": str, "boolean": bool,
    "integer": int, "number": (int, float), "null": type(None),
}


class SchemaError(Exception):
    """The schema itself uses something this validator does not implement."""


def _type_ok(value: object, spec: str) -> bool:
    py = _TYPES[spec]
    # bool is a subclass of int in Python; JSON Schema treats them apart.
    if spec in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, py)


def _validate(value: object, schema: dict, path: str, errors: list[str]) -> None:
    unknown = set(schema) - _KNOWN
    if unknown:
        raise SchemaError(f"{path}: unsupported schema keywords {sorted(unknown)}")

    if "type" in schema:
        wanted = schema["type"]
        options = wanted if isinstance(wanted, list) else [wanted]
        if not any(_type_ok(value, t) for t in options):
            errors.append(f"{path}: expected {wanted}, got {type(value).__name__}")
            return

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: must be {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not one of {schema['enum']}")

    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {value!r} does not match /{schema['pattern']}/")
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']}")

    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} > maximum {schema['maximum']}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                _validate(item, schema["items"], f"{path}[{i}]", errors)

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required '{key}'")
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in value:
                _validate(value[key], sub, f"{path}.{key}", errors)
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(f"{path}: unknown property '{key}'")

    if "not" in schema:
        inner: list[str] = []
        _validate(value, schema["not"], path, inner)
        if not inner:
            errors.append(f"{path}: must NOT match the forbidden shape")

    for sub in schema.get("allOf", []):
        _validate(value, sub, path, errors)

    if "if" in schema:
        probe: list[str] = []
        _validate(value, schema["if"], path, probe)
        if not probe and "then" in schema:
            _validate(value, schema["then"], path, errors)

    if "oneOf" in schema:
        matches = []
        branch_errors = []
        for i, sub in enumerate(schema["oneOf"]):
            inner: list[str] = []
            _validate(value, sub, path, inner)
            if inner:
                branch_errors.append(inner)
            else:
                matches.append(i)
        if len(matches) != 1:
            if not matches:
                # Report the branch that got closest, not all of them: a
                # provider typo otherwise prints five irrelevant error lists.
                best = min(branch_errors, key=len)
                errors.append(f"{path}: matches no oneOf branch; closest: {best[0]}")
            else:
                errors.append(f"{path}: matches {len(matches)} oneOf branches, expected 1")


def load_schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(instance: object, schema: dict, name: str = "pack") -> list[str]:
    """Return the list of problems; empty means valid."""
    errors: list[str] = []
    _validate(instance, schema, name, errors)
    return errors
