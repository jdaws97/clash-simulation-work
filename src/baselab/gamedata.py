"""Load game statistics from ClashKing's game-file extraction.

Units are converted to simulator units on the way out:

* distances (ranges, radii) in tiles; the raw data uses hundredths of a tile;
* movement speed in tiles per second (raw value / 100);
* attack intervals in seconds (raw value is milliseconds).

The raw file was cross-checked against the independent chiefpansancolt catalog
on 2026-10-14: TH16 building HP/DPS and building counts agree exactly. Troop
rows agree except where ClashKing reflects the September 2026 balance patch
(Thrower, Electro Dragon, Dragon Rider), so ClashKing is the primary source.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLASHKING_PATH = ROOT / "data" / "clashking-static-data.json"


@lru_cache(maxsize=1)
def raw() -> dict:
    with open(CLASHKING_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _index(section: str) -> dict[str, dict]:
    return {
        entry["name"]: entry
        for entry in raw()[section]
        if entry.get("village", "home") == "home"
    }


@lru_cache(maxsize=None)
def buildings() -> dict[str, dict]:
    return _index("buildings")


@lru_cache(maxsize=None)
def troops() -> dict[str, dict]:
    return _index("troops")


@lru_cache(maxsize=None)
def heroes() -> dict[str, dict]:
    return _index("heroes")


@lru_cache(maxsize=None)
def traps() -> dict[str, dict]:
    return _index("traps")


def _max_level_for_th(levels: list[dict], town_hall: int) -> dict:
    eligible = [lvl for lvl in levels if (lvl.get("required_townhall") or 0) <= town_hall]
    if not eligible:
        raise ValueError(f"no level available at TH{town_hall}")
    return eligible[-1]


def _level(levels: list[dict], level: int) -> dict:
    for entry in levels:
        if entry["level"] == level:
            return entry
    raise ValueError(f"level {level} not present (max {levels[-1]['level']})")


@dataclass(frozen=True)
class BuildingStats:
    name: str
    level: int
    hitpoints: float
    width: int
    hitbox: float
    dps: float
    attack_interval: float
    attack_range: float
    min_range: float


def building(name: str, town_hall: int = 16) -> BuildingStats:
    entry = buildings()[name]
    if name == "Town Hall":
        # Town Hall rows are offset by one: level N lists the TH needed to
        # *upgrade into* it, so the TH-N building is simply level N.
        row = _level(entry["levels"], town_hall)
    else:
        row = _max_level_for_th(entry["levels"], town_hall)
    return BuildingStats(
        name=name,
        level=row["level"],
        hitpoints=float(row.get("hitpoints") or 0),
        width=int(entry.get("width") or 1),
        hitbox=float(entry.get("hitbox_width") or entry.get("width") or 1),
        dps=float(row.get("dps") or 0),
        attack_interval=(row.get("attack_speed") or 0) / 1000.0,
        attack_range=(row.get("attack_range") or 0) / 100.0,
        min_range=(row.get("min_range") or 0) / 100.0,
    )


@dataclass(frozen=True)
class UnitStats:
    name: str
    level: int
    hitpoints: float
    dps: float
    attack_interval: float
    attack_range: float
    speed: float
    housing: int
    flying: bool
    hits_air: bool
    hits_ground: bool


def _unit(entry: dict, row: dict) -> UnitStats:
    return UnitStats(
        name=entry["name"],
        level=row["level"],
        hitpoints=float(row["hitpoints"]),
        dps=float(row.get("dps") or 0),
        attack_interval=(entry.get("attack_speed") or 1000) / 1000.0,
        attack_range=(entry.get("attack_range") or 0) / 100.0,
        speed=(entry.get("movement_speed") or 0) / 100.0,
        housing=int(entry.get("housing_space") or 0),
        flying=bool(entry.get("is_flying")),
        hits_air=bool(entry.get("is_air_targeting")),
        hits_ground=bool(entry.get("is_ground_targeting")),
    )


def troop(name: str, *, town_hall: int | None = None, level: int | None = None) -> UnitStats:
    entry = troops()[name]
    if level is not None:
        row = _level(entry["levels"], level)
    else:
        row = _max_level_for_th(entry["levels"], town_hall or 16)
    return _unit(entry, row)


def hero(name: str, *, town_hall: int | None = None, level: int | None = None) -> UnitStats:
    entry = heroes()[name]
    if level is not None:
        row = _level(entry["levels"], level)
    else:
        row = _max_level_for_th(entry["levels"], town_hall or 16)
    return _unit(entry, row)


def trap(name: str, town_hall: int = 16) -> dict:
    entry = traps()[name]
    row = _max_level_for_th(entry["levels"], town_hall)
    return {
        "name": name,
        "level": row["level"],
        "damage": float(row.get("damage") or 0),
        "width": int(entry.get("width") or 1),
        "trigger_radius": (entry.get("trigger_radius") or 0) / 100.0,
        "damage_radius": (entry.get("damage_radius") or 0) / 100.0,
        "air": bool(entry.get("air_trigger")),
        "ground": bool(entry.get("ground_trigger")),
    }
