"""Village layouts: placement, validation, inventory and JSON I/O.

Coordinates are village tiles, 0..43 on each axis, with (0, 0) at the top
corner of the in-game diamond: x runs down-right, y runs down-left. A building
of size s placed at (x, y) covers tiles x..x+s-1, y..y+s-1.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .mechanics import BUILDING_TYPES, INVENTORY, OPTIONAL_KEYS, TRAP_INVENTORY, TRAP_SIZES, VILLAGE, WALL_COUNT


@dataclass
class Placement:
    key: str
    x: int
    y: int
    mode: str | None = None  # inferno single/multi, xbow ground/both, spell tower, sweeper dir

    @property
    def size(self) -> int:
        return BUILDING_TYPES[self.key].size

    def tiles(self):
        s = self.size
        for dx in range(s):
            for dy in range(s):
                yield (self.x + dx, self.y + dy)


@dataclass
class TrapPlacement:
    key: str
    x: int
    y: int
    mode: str | None = None  # skeleton trap: "ground" or "air"

    @property
    def size(self) -> int:
        return TRAP_SIZES.get(self.key, 1)

    def tiles(self):
        s = self.size
        for dx in range(s):
            for dy in range(s):
                yield (self.x + dx, self.y + dy)


@dataclass
class Layout:
    name: str
    buildings: list[Placement] = field(default_factory=list)
    walls: set[tuple[int, int]] = field(default_factory=set)
    traps: list[TrapPlacement] = field(default_factory=list)
    cc_troops: list[str] = field(default_factory=lambda: list(DEFAULT_CC))
    heroes: list[str] = field(default_factory=lambda: list(DEFAULT_DEFENDING_HEROES))
    notes: str = ""
    town_hall: int = 16
    guardian: str = "Longshot"  # TH18 Guardian standing on the Town Hall
    # the owner's actual levels (account-wide): building key -> level,
    # defending hero name -> level, wall level; empty means maxed for the TH
    levels: dict = field(default_factory=dict)
    hero_levels: dict = field(default_factory=dict)
    wall_level: int | None = None
    wall_levels: dict[tuple[int, int], int] = field(default_factory=dict)

    # ------------------------------------------------------------------ io
    def to_json(self) -> dict:
        return {
            "name": self.name,
            "notes": self.notes,
            "buildings": [
                {
                    "key": b.key,
                    "x": b.x,
                    "y": b.y,
                    **({"mode": b.mode} if b.mode else {}),
                }
                for b in self.buildings
            ],
            "walls": sorted([list(w) for w in self.walls]),
            "traps": [
                {
                    "key": t.key,
                    "x": t.x,
                    "y": t.y,
                    **({"mode": t.mode} if t.mode else {}),
                }
                for t in self.traps
            ],
            "cc_troops": self.cc_troops,
            "heroes": self.heroes,
            "town_hall": self.town_hall,
            "guardian": self.guardian,
            **({"levels": self.levels} if self.levels else {}),
            **({"hero_levels": self.hero_levels} if self.hero_levels else {}),
            **({"wall_level": self.wall_level} if self.wall_level else {}),
            **(
                {
                    "wall_levels": [
                        {"x": x, "y": y, "level": level}
                        for (x, y), level in sorted(self.wall_levels.items())
                    ]
                }
                if self.wall_levels
                else {}
            ),
        }

    @classmethod
    def from_json(cls, data: dict) -> "Layout":
        return cls(
            name=data["name"],
            notes=data.get("notes", ""),
            buildings=[Placement(**b) for b in data["buildings"]],
            walls={tuple(w) for w in data.get("walls", [])},
            traps=[TrapPlacement(**t) for t in data.get("traps", [])],
            cc_troops=data.get("cc_troops", list(DEFAULT_CC)),
            heroes=data.get("heroes", list(DEFAULT_DEFENDING_HEROES)),
            town_hall=data.get("town_hall", 16),
            guardian=data.get("guardian", "Longshot"),
            levels=data.get("levels", {}),
            hero_levels=data.get("hero_levels", {}),
            wall_level=data.get("wall_level"),
            wall_levels={
                (entry["x"], entry["y"]): entry["level"]
                for entry in data.get("wall_levels", [])
            },
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=1))

    @classmethod
    def load(cls, path: Path) -> "Layout":
        return cls.from_json(json.loads(Path(path).read_text()))

    def copy(self) -> "Layout":
        return Layout.from_json(json.loads(json.dumps(self.to_json())))

    # ---------------------------------------------------------- validation
    def occupancy(self) -> dict[tuple[int, int], str]:
        occ: dict[tuple[int, int], str] = {}
        for i, b in enumerate(self.buildings):
            for t in b.tiles():
                occ[t] = f"b{i}"
        for w in self.walls:
            occ[w] = "wall"
        for i, t in enumerate(self.traps):
            for tile in t.tiles():
                occ[tile] = f"t{i}"
        return occ

    def problems(self, *, require_full: bool = True) -> list[str]:
        issues: list[str] = []
        seen: dict[tuple[int, int], str] = {}

        def claim(tile, owner):
            x, y = tile
            if not (0 <= x < VILLAGE and 0 <= y < VILLAGE):
                issues.append(f"{owner} out of bounds at {tile}")
            elif tile in seen:
                issues.append(f"{owner} overlaps {seen[tile]} at {tile}")
            else:
                seen[tile] = owner

        for b in self.buildings:
            for t in b.tiles():
                claim(t, f"{b.key}@{b.x},{b.y}")
        for w in self.walls:
            claim(w, "wall")
        for position in self.wall_levels:
            if position not in self.walls:
                issues.append(f"wall level without a wall at {position}")
        for t in self.traps:
            for tile in t.tiles():
                claim(tile, f"trap {t.key}@{t.x},{t.y}")

        counts = Counter(b.key for b in self.buildings)
        inv = INVENTORY[self.town_hall]
        for key in BUILDING_TYPES:
            want = inv.get(key, 0)
            if counts[key] > want:
                issues.append(f"too many {key}: {counts[key]} > {want}")
            elif require_full and counts[key] < want and key not in OPTIONAL_KEYS:
                issues.append(f"missing {key}: {counts[key]} < {want}")
        if len(self.walls) > WALL_COUNT:
            issues.append(f"too many walls: {len(self.walls)} > {WALL_COUNT}")
        trap_counts = Counter(t.key for t in self.traps)
        for key, n in TRAP_INVENTORY[self.town_hall].items():
            if trap_counts[key] > n:
                issues.append(f"too many {key} traps: {trap_counts[key]} > {n}")
            elif require_full and trap_counts[key] < n:
                issues.append(f"missing {key} traps: {trap_counts[key]} < {n}")
        return issues


# A defensive Clan Castle that is legal at TH16 (50 housing): two Dragons,
# one Headhunter (anti-hero) and four Archers. Easy to change per layout.
DEFAULT_CC = ["Dragon", "Dragon", "Headhunter", "Archer", "Archer", "Archer", "Archer"]

# Defending heroes sit on the four hero banners. Queen, King, Warden and
# Minion Prince are the usual TH16 defensive picks. (assumed)
DEFAULT_DEFENDING_HEROES = ["Archer Queen", "Barbarian King", "Grand Warden", "Minion Prince"]
