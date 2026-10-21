"""Behaviour tables that the game-file extraction does not describe.

Every value here is a modelling choice. Each block notes its source:

* ``data`` - read from ClashKing game data at runtime (see gamedata.py);
* ``catalog`` - chiefpansancolt catalog, not independently cross-checked;
* ``patch`` - official Supercell patch notes / sneak peeks;
* ``assumed`` - community knowledge or a reasoned guess. These are the
  first things to revisit if simulated outcomes look wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import gamedata

# --------------------------------------------------------------------------
# Village geometry
# --------------------------------------------------------------------------

# The buildable village is 44x44 tiles; troops can also be deployed in a
# 3-tile margin around it, giving a 50x50 world. (assumed, standard layout)
VILLAGE = 44
MARGIN = 3
WORLD = VILLAGE + 2 * MARGIN

# --------------------------------------------------------------------------
# Buildings
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class WeaponSpec:
    targets: str  # "air", "ground" or "both"
    mode: str  # see sim.Weapon for the behaviour of each mode
    range: float
    min_range: float = 0.0
    interval: float = 1.0
    damage: float = 0.0  # per shot (per target for multi modes)
    splash: float = 0.0
    n_targets: int = 1
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class BuildingType:
    key: str
    name: str  # ClashKing name
    size: int
    count: int  # maximum at TH16, after merges (see INVENTORY_NOTES)
    kind: str  # defense, resource, army, townhall, castle, other
    counted: bool = True  # counts toward destruction percentage
    weapon_key: str | None = None


INVENTORY_NOTES = (
    "TH16 counts are from game data and agree with the catalog. A maxed TH16 "
    "has merged two pairs of Archer Towers into Multi-Archer Towers and two "
    "pairs of Cannons into Ricochet Cannons (Supercell 'Building Merging' "
    "post), leaving 4 Archer Towers and 3 Cannons. Hero banners are placement "
    "markers for defending heroes and do not count toward destruction (assumed). "
    "Helper Hut and B.O.B's Hut have no combat stats in game data; they are "
    "modelled as blocking, uncounted obstacles (assumed)."
)

BUILDING_TYPES: dict[str, BuildingType] = {
    bt.key: bt
    for bt in [
        BuildingType("th", "Town Hall", 4, 1, "townhall", weapon_key="th"),
        BuildingType("cc", "Clan Castle", 3, 1, "castle"),
        BuildingType("ad", "Air Defense", 3, 4, "defense", weapon_key="ad"),
        BuildingType("sweeper", "Air Sweeper", 2, 2, "defense", weapon_key="sweeper"),
        BuildingType("at", "Archer Tower", 3, 4, "defense", weapon_key="at"),
        BuildingType("mat", "Multi-Archer Tower", 3, 2, "defense", weapon_key="mat"),
        BuildingType("cannon", "Cannon", 3, 3, "defense", weapon_key="cannon"),
        BuildingType("ric", "Ricochet Cannon", 3, 2, "defense", weapon_key="ric"),
        BuildingType("bt", "Bomb Tower", 3, 2, "defense", weapon_key="bt"),
        BuildingType("bh", "Builder's Hut", 2, 5, "defense", weapon_key="bh"),
        BuildingType("eagle", "Eagle Artillery", 4, 1, "defense", weapon_key="eagle"),
        BuildingType("tesla", "Hidden Tesla", 2, 5, "defense", weapon_key="tesla"),
        BuildingType("inferno", "Inferno Tower", 2, 3, "defense", weapon_key="inferno"),
        BuildingType("mono", "Monolith", 3, 1, "defense", weapon_key="mono"),
        BuildingType("mortar", "Mortar", 3, 4, "defense", weapon_key="mortar"),
        BuildingType("scatter", "Scattershot", 3, 2, "defense", weapon_key="scatter"),
        BuildingType("st", "Spell Tower", 2, 2, "defense", weapon_key="st"),
        BuildingType("wt", "Wizard Tower", 3, 5, "defense", weapon_key="wt"),
        BuildingType("xbow", "X-Bow", 3, 4, "defense", weapon_key="xbow"),
        BuildingType("gm", "Gold Mine", 3, 7, "resource"),
        BuildingType("ec", "Elixir Collector", 3, 7, "resource"),
        BuildingType("dd", "Dark Elixir Drill", 3, 3, "resource"),
        BuildingType("gs", "Gold Storage", 3, 4, "resource"),
        BuildingType("es", "Elixir Storage", 3, 4, "resource"),
        BuildingType("ds", "Dark Elixir Storage", 3, 1, "resource"),
        BuildingType("camp", "Army Camp", 4, 4, "army"),
        BuildingType("barracks", "Barracks", 3, 1, "army"),
        BuildingType("dbarracks", "Dark Barracks", 3, 1, "army"),
        BuildingType("sf", "Spell Factory", 3, 1, "army"),
        BuildingType("dsf", "Dark Spell Factory", 3, 1, "army"),
        BuildingType("lab", "Laboratory", 3, 1, "army"),
        BuildingType("workshop", "Workshop", 4, 1, "army"),
        BuildingType("pethouse", "Pet House", 3, 1, "army"),
        BuildingType("smith", "Blacksmith", 3, 1, "army"),
        BuildingType("herohall", "Hero Hall", 4, 1, "army"),
        BuildingType("helper", "Helper Hut", 3, 1, "other"),
        BuildingType("bob", "B.O.B's Hut", 2, 1, "other"),
        BuildingType("banner", "Hero Banner", 2, 4, "other", counted=False),
        # TH17-18 only (counts per TH come from INVENTORY below)
        BuildingType("mgt", "Multi-Gear Tower", 3, 0, "defense", weapon_key="mgt"),
        BuildingType(
            "firespitter", "Firespitter", 3, 0, "defense", weapon_key="firespitter"
        ),
        BuildingType("swt", "Super Wizard Tower", 3, 0, "defense", weapon_key="swt"),
        BuildingType("revenge", "Revenge Tower", 3, 0, "defense", weapon_key="revenge"),
        # Seasonal Crafting Station: a defensive building switched between the
        # season's three Crafted Defenses (wiki: Crafting Station). Mode picks
        # which: cake (Cake-A-Pult), candle (Hot Candle), hunter (Hero Hunter).
        BuildingType(
            "crafting", "Crafting Station", 3, 0, "defense", weapon_key="crafting"
        ),
    ]
}

# Maxed, fully merged inventories per Town Hall (ClashKing Town Hall unlocks,
# minus merges: 2 AT -> MAT, 2 Cannon -> Ricochet (TH16+); geared AT + geared
# Cannon -> Multi-Gear Tower and Eagle -> Inferno Artillery (TH17+);
# 2 Wizard Towers -> Super Wizard Tower (TH18)).
INVENTORY = {
    16: {"th": 1, "cc": 1, "ad": 4, "sweeper": 2, "at": 4, "mat": 2, "cannon": 3, "ric": 2, "bt": 2, "bh": 5,
         "eagle": 1, "tesla": 5, "inferno": 3, "mono": 1, "mortar": 4, "scatter": 2, "st": 2, "wt": 5, "xbow": 4,
         "crafting": 1},
    17: {"th": 1, "cc": 1, "ad": 4, "sweeper": 2, "at": 2, "mat": 3, "cannon": 0, "ric": 3, "bt": 2, "bh": 5,
         "eagle": 0, "tesla": 5, "inferno": 3, "mono": 1, "mortar": 4, "scatter": 2, "st": 2, "wt": 5, "xbow": 4,
         "mgt": 1, "firespitter": 2, "crafting": 1},
    18: {"th": 1, "cc": 1, "ad": 4, "sweeper": 2, "at": 2, "mat": 3, "cannon": 0, "ric": 3, "bt": 2, "bh": 5,
         "eagle": 0, "tesla": 5, "inferno": 3, "mono": 1, "mortar": 4, "scatter": 2, "st": 2, "wt": 2, "xbow": 4,
         "mgt": 1, "firespitter": 2, "swt": 2, "revenge": 1, "crafting": 1},
}
for _th in INVENTORY:
    for _k, _bt in BUILDING_TYPES.items():
        if _bt.kind != "defense" and _k not in ("th", "cc") and _k not in INVENTORY[_th]:
            INVENTORY[_th][_k] = _bt.count
        INVENTORY[_th].setdefault(_k, 0)
# Buildings a layout may leave out without being incomplete (seasonal).
OPTIONAL_KEYS = {"crafting"}
TRAP_INVENTORY = {
    16: {"bomb": 8, "spring": 9, "giant": 7, "airbomb": 7, "seeking": 8, "skeleton": 4, "tornado": 1, "giga": 0},
    17: {"bomb": 8, "spring": 9, "giant": 8, "airbomb": 7, "seeking": 9, "skeleton": 4, "tornado": 1, "giga": 1},
    18: {"bomb": 8, "spring": 9, "giant": 8, "airbomb": 8, "seeking": 9, "skeleton": 4, "tornado": 1, "giga": 1},
}

# Building sizes that ClashKing does not list (assumed from in-game footprint).
_SIZE_FALLBACK = {"Hero Banner": 2, "B.O.B's Hut": 2, "Helper Hut": 3}

WALL_COUNT = 325
TRAP_COUNTS = {
    "bomb": 8,
    "spring": 9,
    "giant": 7,
    "airbomb": 7,
    "seeking": 8,
    "skeleton": 4,
    "tornado": 1,
}
TRAP_NAMES = {
    "giga": "Giga Bomb",
    "bomb": "Bomb",
    "spring": "Spring Trap",
    "giant": "Giant Bomb",
    "airbomb": "Air Bomb",
    "seeking": "Seeking Air Mine",
    "skeleton": "Skeleton Trap",
    "tornado": "Tornado Trap",
}
TRAP_SIZES = {"giant": 2, "giga": 2}


def weapon_spec(key: str, town_hall: int = 16) -> WeaponSpec:
    """Return the TH-appropriate weapon for a building type."""
    bt = BUILDING_TYPES[key]
    stats = gamedata.building(bt.name, town_hall)
    dps = stats.dps
    if key == "th":
        # TH16 Giga Inferno (wiki statistics): 300 DPS per target (38.4 per hit),
        # 4 targets, range 10. The 50% slow belongs to the poison left when the
        # Town Hall is destroyed, not to the live beams. Death: 1100 damage within
        # 4.5 tiles. (Was 150 per target with a beam slow until 2026-10-15.)
        return WeaponSpec(
            "both",
            "giga",
            range=10,
            interval=0.128,
            damage=300 * 0.128,
            n_targets=4,
            extra={"death_damage": 1100, "death_radius": 4.5},
        )
    if key == "ad":
        return WeaponSpec("air", "single", 10, interval=1.0, damage=dps * 1.0)
    if key == "sweeper":
        # Gust every 5 s inside a 120-degree cone, pushing air units away.
        # pushStrength 4 in the catalog; we push 1.5 tiles (assumed).
        return WeaponSpec(
            "air", "sweeper", 15, min_range=1, interval=5.0, extra={"push": 4.0}
        )
    if key == "at":
        return WeaponSpec("both", "single", 10, interval=0.5, damage=dps * 0.5)
    if key == "mat":
        # 3 targets, 65 damage per arrow every 0.6 s (catalog, data agrees on HP).
        return WeaponSpec("both", "multi", 10, interval=0.6, damage=65, n_targets=3)
    if key == "cannon":
        return WeaponSpec("ground", "single", 9, interval=0.8, damage=dps * 0.8)
    if key == "ric":
        # One bounce to a second ground target within 3.5 tiles (catalog).
        return WeaponSpec(
            "ground",
            "ricochet",
            9,
            interval=0.8,
            damage=dps * 0.8,
            extra={"bounce_damage": 218.4, "bounce_range": 3.5},
        )
    if key == "bt":
        return WeaponSpec(
            "ground",
            "splash",
            6,
            interval=1.1,
            damage=dps * 1.1,
            splash=1.5,
            extra={"death_damage": 600, "death_radius": 2.75},
        )
    if key == "bh":
        return WeaponSpec("both", "single", 7, interval=0.4, damage=dps * 0.4)
    if key == "eagle":
        # Activates after 200 housing of attackers is deployed. Bursts of 3
        # shells every 10 s, 525 damage within 0.75 tiles plus a 50-damage
        # shockwave out to 3 tiles (wiki, verified 2026-10-15).
        return WeaponSpec(
            "both",
            "eagle",
            50,
            min_range=7,
            interval=10.0,
            damage=525,
            splash=0.75,
            extra={"activation_housing": 200, "shells": 3, "shell_gap": 0.75, "shockwave": 50.0, "shockwave_radius": 3.0},
        )
    if key == "tesla":
        return WeaponSpec(
            "both", "single", 7, interval=0.6, damage=dps * 0.6, extra={"hidden": 6}
        )
    if key == "inferno":
        # Mode chosen per layout: "single" ramps 120 -> 260 -> 2600 DPS at
        # 1.5 s and 5.25 s on one target (wiki, verified); "multi" hits
        # 6 targets at 120 DPS each (data).
        return WeaponSpec(
            "both",
            "inferno",
            9,
            interval=0.128,
            damage=0,
            n_targets=6,
            extra={
                "ramp": [(0.0, 120.0), (1.5, 260.0), (5.25, 2600.0)],
                "multi_dps": 120.0,
                "multi_range": 10.0,
            },
        )
    if key == "mono":
        # 289.5 per shot plus 13% of the target's current HP (catalog).
        return WeaponSpec(
            "both",
            "monolith",
            11,
            interval=1.5,
            damage=289.5,
            extra={"pct_current_hp": 0.13},
        )
    if key == "mortar":
        return WeaponSpec(
            "ground",
            "shell",
            11,
            min_range=4,
            interval=5.0,
            damage=300,
            splash=1.5,
            extra={"flight": 1.5},
        )
    if key == "scatter":
        # 576 to the primary target, up to 420 splash nearby (catalog).
        return WeaponSpec(
            "both",
            "splash",
            10,
            min_range=3,
            interval=3.2,
            damage=576,
            splash=2.5,
            extra={"splash_damage": 420},
        )
    if key == "st":
        return WeaponSpec("both", "spelltower", 9, interval=70.0)
    if key == "wt":
        return WeaponSpec("both", "splash", 7, interval=1.3, damage=dps * 1.3, splash=1.0)
    if key == "xbow":
        # Mode chosen per layout: ground-only range 14 or air+ground 11.5 (data).
        return WeaponSpec(
            "ground",
            "single",
            14,
            interval=0.128,
            damage=dps * 0.128,
            extra={"both_range": 11.5},
        )
    raise KeyError(key)
