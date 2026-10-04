"""Parse narrowly selected layout arrays without exporting surrounding memory.

These are raw, unverified game-record candidates. In particular, a numeric data
identifier or level is not converted to a simulator entity without a mapping.
"""

import hashlib
import json
import re


LAYOUT_KEYS = {"buildings", "buildings2", "traps", "obstacles", "war_layout"}
NUMERIC_FIELDS = {
    "id",
    "data",
    "lvl",
    "level",
    "x",
    "y",
    "x2",
    "y2",
    "type",
    "mode",
    "rot",
    "dir",
    "direction",
    "rotation",
    "gear",
    "lvl2",
    "layout",
    "active",
    "hp",
    "wp_lvl",
}


def select_layout_fields(item):
    """Keep only layout data, never account, queue or arbitrary nested values."""
    fields = {
        key: number
        for key, number in item.items()
        if key in NUMERIC_FIELDS and type(number) is int and -(2**31) <= number < 2**31
    }
    for key, value in item.items():
        if re.fullmatch(r"(?:l\d{1,2}x|lmx|e\d{1,2}x)", key):
            if (
                isinstance(value, list)
                and len(value) == 2
                and all(
                    type(coordinate) is int and -1 <= coordinate <= 255
                    for coordinate in value
                )
            ):
                fields[key] = value
        elif re.fullmatch(
            r"(?:attack_mode|air_mode)(?:[0-9]{1,2}|_[a-z0-9_]{1,16})?", key
        ):
            if isinstance(value, bool):
                fields[key] = value
    return fields


def inspect_layout_value(data, expected_key):
    """Read only the value immediately following a verified JSON key anchor."""
    if expected_key not in LAYOUT_KEYS:
        raise ValueError("Only known layout keys may be inspected")
    prefix = json.dumps(expected_key).encode("ascii")
    if not data.startswith(prefix):
        return {"status": "STALE_ANCHOR", "key": expected_key}
    tail = data[len(prefix) :].lstrip()
    if not tail.startswith(b":"):
        return {"status": "IDENTIFIER_WITHOUT_JSON_VALUE", "key": expected_key}
    text = tail[1:].lstrip().decode("utf-8", errors="replace")
    complete = True
    error_offset = None
    try:
        value, _ = json.JSONDecoder().raw_decode(text)
    except (ValueError, RecursionError) as error:
        # Guest pages need not be contiguous in host memory. Preserve complete
        # prefix objects as partial evidence, without filling or joining gaps.
        complete = False
        error_offset = getattr(error, "pos", None)
        value = []
        position = 1
        if text.startswith("["):
            decoder = json.JSONDecoder()
            while position < len(text) and len(value) < 2048:
                while position < len(text) and text[position].isspace():
                    position += 1
                try:
                    item, position = decoder.raw_decode(text, position)
                except (ValueError, RecursionError):
                    break
                value.append(item)
                while position < len(text) and text[position].isspace():
                    position += 1
                if position >= len(text) or text[position] != ",":
                    break
                position += 1
        if not value:
            return {
                "status": "NO_COMPLETE_JSON_VALUE",
                "key": expected_key,
                "starts_with_array": text.startswith("["),
                "json_error_offset": error_offset,
            }
    if not isinstance(value, list):
        return {
            "status": "VALUE_IS_NOT_LAYOUT_ARRAY",
            "key": expected_key,
            "value_type": type(value).__name__,
        }
    if len(value) > 2048:
        return {"status": "ARRAY_EXCEEDS_LAYOUT_LIMIT", "key": expected_key}
    entries = []
    shapes = set()
    field_shapes = {}
    for item in value:
        if not isinstance(item, dict):
            shapes.add(type(item).__name__)
            continue
        for key, field in item.items():
            if len(key) <= 64 and key.replace("_", "").isalnum():
                field_shapes.setdefault(key, set()).add(type(field).__name__)
        # Values outside the explicit numeric whitelist never leave this parser.
        fields = select_layout_fields(item)
        if {"x", "y"} <= fields.keys() and ("data" in fields or "id" in fields):
            entries.append(fields)
        else:
            shapes.add("object_without_position_and_identity")
    fingerprint = hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    return {
        "status": "UNVERIFIED_LAYOUT_CANDIDATE" if entries else "NO_LAYOUT_RECORDS",
        "key": expected_key,
        "array_length": len(value),
        "array_complete": complete,
        "json_error_offset": error_offset,
        "retained_entries": entries,
        "other_item_shapes": sorted(shapes),
        "object_field_types": {
            key: sorted(kinds) for key, kinds in sorted(field_shapes.items())
        },
        "fingerprint_of_retained_fields": fingerprint,
        "entity_ids_verified": False,
        "level_encoding_verified": False,
        "coordinate_encoding_verified": False,
    }


def find_layout_objects(data, allowed_data_ids, include_unmapped=False):
    """Find complete named building objects in a bounded window.

    No concatenation across missing memory pages is attempted. The caller must
    retain duplicates/conflicts and cannot infer a full layout from this search.
    """
    decoder = json.JSONDecoder()
    records = []
    for match in re.finditer(rb'\{"data":(?:1000\d{3}|120000\d{2}),', data):
        text = data[match.start() : match.start() + 8192].decode(
            "utf-8", errors="replace"
        )
        complete = True
        try:
            item, _ = decoder.raw_decode(text)
        except (ValueError, RecursionError):
            complete = False
            item = decode_object_prefix(text)
        if not isinstance(item, dict):
            continue
        if item.get("data") not in allowed_data_ids and not include_unmapped:
            continue
        fields = select_layout_fields(item)
        if not {"data", "id", "x", "y"} <= fields.keys():
            continue
        if not 500000000 <= fields["id"] < 505000000:
            continue
        records.append(
            {"offset": match.start(), "fields": fields, "object_complete": complete}
        )
    return records


def decode_object_prefix(text):
    """Return only syntactically complete fields before a discontinuity."""
    if not text.startswith("{"):
        return {}
    decoder = json.JSONDecoder()
    fields = {}
    position = 1
    while position < len(text):
        while position < len(text) and text[position].isspace():
            position += 1
        try:
            key, position = decoder.raw_decode(text, position)
            if not isinstance(key, str) or key in fields:
                break
            while position < len(text) and text[position].isspace():
                position += 1
            if position >= len(text) or text[position] != ":":
                break
            position += 1
            while position < len(text) and text[position].isspace():
                position += 1
            value, position = decoder.raw_decode(text, position)
            while position < len(text) and text[position].isspace():
                position += 1
            # A number ending at a torn boundary may only be a numeric prefix.
            # Accept a field only after seeing its closing JSON delimiter.
            if position >= len(text) or text[position] not in {",", "}"}:
                break
            fields[key] = value
            if text[position] == "}":
                break
            position += 1
        except (ValueError, RecursionError):
            break
    return fields
