"""Load game statistics from ClashKing's game-file extraction.

``raw()`` is the whole export (registry.py builds data/registry.json from
it); ``building()`` gives a building's stats at a Town Hall (used by
mechanics.weapon_spec), converted to simulator units:

* distances (ranges) in tiles; the raw data uses hundredths of a tile;
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
