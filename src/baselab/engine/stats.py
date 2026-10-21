"""Read entity statistics from the unified registry (data/registry.json).

Every number the v2 engine uses for an entity comes through here, so the
source of each value is traceable: wiki combat fields first, with extracted
game data retained as a fallback.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "data" / "registry.json"
_NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def num(value, default=None):
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    m = _NUM.search(str(value).replace("−", "-"))
    if not m:
        return default
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return default


@lru_cache(maxsize=1)
def registry() -> dict:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    # Wiki: Birthday Boom table; its historical TH-scaling formula conflicts.
    data.setdefault(
        "Birthday Boom",
        {
            "name": "Birthday Boom",
            "kind": "spell",
            "seasonal": True,
            "attrs": {"housing": 2, "raw": {"Spell Factory Level Required": 1}},
            "levels": [
                {
                    "level": 1,
                    "wiki": {
                        "Damage": 500,
                        "Damage vs Town Hall": 350,
                        "Radius": 2.5,
                        "Freeze Duration": 2,
                    },
                }
            ],
        },
    )
    # Wiki: Yellow Card has one level and a 15-second suspension.
    data.setdefault(
        "Yellow Card",
        {
            "name": "Yellow Card",
            "kind": "spell",
            "seasonal": True,
            "attrs": {"housing": 1, "raw": {"Spell Factory Level Required": 1}},
            "levels": [{"level": 1, "wiki": {"Duration": 15, "Radius": 7}}],
        },
    )
    # Published level rows (wiki: Lavaloon/Lavaloon Pup).
    damage = (10, 13, 16, 19, 22, 25, 28, 31, 34, 37, 40, 42, 44)
    health = (10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70)
    data.setdefault(
        "Lavaloon Pup",
        {
            "name": "Lavaloon Pup",
            "kind": "summon",
            "attrs": {
                "housing": 1,
                "speed_display": 32,
                "attack_interval": 1.0,
                "range": 2.0,
                "is_flying": True,
                "is_air_targeting": True,
                "is_ground_targeting": True,
            },
            "levels": [
                {
                    "level": level,
                    "wiki": {
                        "Hitpoints": hp,
                        "Damage per Attack": hit,
                        "Damage per Second": hit,
                    },
                }
                for level, (hp, hit) in enumerate(zip(health, damage), 1)
            ],
        },
    )
    # Wiki: Monolith and Multi-Gear Tower, separate TH18 Supercharge tables.
    charges = {
        "Monolith": {
            "health": (5959, 6161),
            "wiki": {"Base Damage per Shot": 352.5, "Bonus Damage per Shot": 15},
        },
        "Multi-Gear Tower": {
            "health": (4350, 4500),
            "wiki": {"Damage per Hit": 400, "Damage per Hit**": 172.8},
        },
    }
    for name, profile in charges.items():
        levels = data[name]["levels"]
        for charge, health in enumerate(profile["health"], 1):
            level = f"charge:{charge}"
            if not any(entry["level"] == level for entry in levels):
                levels.append(
                    {
                        "level": level,
                        "wiki": {
                            **profile["wiki"],
                            "Hitpoints": health,
                            "Town Hall Level Required": 18,
                        },
                        "wiki_only": True,
                    }
                )
    return data


def record(name: str) -> dict:
    return registry()[name]


def attrs(name: str) -> dict:
    return registry()[name]["attrs"]


def max_level(name: str, town_hall: int) -> int | None:
    rec = record(name)
    mapping = rec.get("max_level", {})
    if str(town_hall) in mapping:
        return mapping[str(town_hall)]
    levels = [
        entry["level"]
        for entry in rec["levels"]
        if isinstance(entry.get("level"), int)
        and required_town_hall(name, entry["level"]) <= town_hall
    ]
    return max(levels) if levels else None


def required_town_hall(name, level):
    # Individual wiki tables state the required Town Hall for each level.
    return get(name, level, "Town Hall Level Required", "required_townhall", default=0)


def validate_level(name, level, town_hall):
    if max_level(name, town_hall) is None:
        raise ValueError(f"{name} is unavailable at Town Hall {town_hall}")
    if required_town_hall(name, level) > town_hall:
        raise ValueError(f"Illegal {name} level {level} at Town Hall {town_hall}")
    row(name, level)
    return level


@lru_cache(maxsize=4096)
def row(name: str, level) -> dict:
    """Merged stats for one level: game data keys plus wiki columns."""
    rec = registry()[name]
    for r in rec["levels"]:
        if r.get("level") == level:
            out = {k: v for k, v in r.items() if k != "wiki"}
            for k, v in r.get("wiki", {}).items():
                out[k] = v
            return out
    raise KeyError(f"{name} has no level {level}")


def get(name: str, level, *keys, default=None):
    """First numeric value found under any of `keys` (case-insensitive,
    substring match allowed with a leading '~')."""
    r = row(name, level)
    lower = {k.lower(): v for k, v in r.items()}
    entry = next(e for e in record(name)["levels"] if e.get("level") == level)
    wiki = entry.get("wiki", {})
    # Game data wins for hitpoints and DPS where it has them (registry.py:
    # "ClashKing (game files) is authoritative for numbers it has"; checked
    # against game data v18.200.9 Characters.csv/Heroes.csv, e.g. Lavaloon L1
    # 1080 HP / 50 DPS, Flame Flinger L1 127 DPS, Barbarian King L1 102 DPS,
    # where the wiki columns read 970/45, 124 and 51). The wiki column is the
    # fallback for rows without game data. Without this the wiki "Hitpoints"
    # column (same lowercase key) silently replaced the game value.
    for alias, columns in (
        ("hitpoints", ("hitpoints",)),
        ("dps", ("damage per second", "damage per second*", "base damage per second")),
    ):
        game = entry.get(alias)
        if num(game) is not None:
            lower[alias] = game
            continue
        value = next(
            (
                v
                for column in columns
                for k, v in wiki.items()
                if k.lower() == column and num(v) is not None
            ),
            None,
        )
        if value is not None:
            lower[alias] = value
    for key in keys:
        if key.startswith("~"):
            frag = key[1:].lower()
            for k, v in lower.items():
                if frag in k:
                    n = num(v)
                    if n is not None:
                        return n
            continue
        v = lower.get(key.lower())
        n = num(v)
        if n is not None:
            return n
    return default


def text(name: str, level, *keys, default=None):
    r = row(name, level)
    lower = {k.lower(): v for k, v in r.items()}
    for key in keys:
        if key.lower() in lower:
            return lower[key.lower()]
    return default
