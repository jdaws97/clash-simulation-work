"""Shared validation and stable identifiers."""

import hashlib
import json
import math
from pathlib import Path


class InputError(ValueError):
    """Required evidence or input is missing or inconsistent."""


def require(mapping, key):
    if key not in mapping or mapping[key] is None:
        raise InputError(f"Missing explicit input: {key}")
    return mapping[key]


def number(value, label, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{label} must be a number")
    if not math.isfinite(value):
        raise InputError(f"{label} must be finite")
    if minimum is not None and value < minimum:
        raise InputError(f"{label} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise InputError(f"{label} must be at most {maximum}")
    return value


def integer(value, label, minimum=None, maximum=None):
    number(value, label, minimum, maximum)
    if not isinstance(value, int):
        raise InputError(f"{label} must be an integer")
    return value


def identifier(value, label):
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{label} must be a nonempty string")
    return value


def stable_id(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()[:20]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
