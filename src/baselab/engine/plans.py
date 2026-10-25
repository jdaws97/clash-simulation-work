"""Attack plans for engine v2: army compositions plus a phased attacker brain.

Ported from the v1 `armies.py` brain (funnel -> main push -> support ->
cleanup) onto real v2 entities: spells are cast through `spells.cast` with
their real names and levels, sieges are deployed as units, wall access uses
real Wall Breakers / Earthquake / Jump spells, and hero abilities are
triggered by the plan like a player would.

Armies mirror what hits TH16-18 bases in ranked (docs/RESEARCH-2026-10.md).
Clan Castle troops are folded into the main army as in v1 (assumed: the
reinforcement lands with the push).
"""

from __future__ import annotations

import json
import math
import os
import warnings
from pathlib import Path
from dataclasses import InitVar, dataclass, field
from functools import lru_cache
from heapq import nlargest

from ..loadouts import HeroLoadout as L
from ..mechanics import WORLD
from . import heroes, spells, stats
from .entities import Building

CENTER = WORLD / 2.0

THREAT = {
    "th": 6,
    "inferno": 10,
    "scatter": 8,
    "eagle": 7,
    "xbow": 5,
    "mono": 5,
    "mgt": 5,
    "firespitter": 4,
    "swt": 5,
    "revenge": 4,
    "ad": 4,
    "ric": 4,
    "mat": 3,
    "wt": 3,
    "st": 3,
    "bt": 2,
    "at": 2,
    "tesla": 2,
    "cannon": 1,
    "bh": 1,
    "mortar": 1,
    "sweeper": 1,
}

# Learnable attacker policy: every decision threshold of the brain below.
# Defaults reproduce the hand-written brain exactly; tools/baselab/train_policy.py
# learns better values across many bases (name: (default, lo, hi)).
POLICY = {
    "commit_progress": (
        3.0,
        1.0,
        6.0,
    ),  # funnel buildings down before the main push commits
    "freeze_min_threat": (5.0, 3.0, 9.0),  # weakest defense worth a Freeze
    "freeze_reach": (
        1.5,
        -1.0,
        4.0,
    ),  # Freeze once the army is this far inside its range
    "freeze_min_units": (
        0.0,
        0.0,
        10.0,
    ),  # ... and at least this many troops are in range
    "totem_min_threats": (3.0, 1.0, 5.0),
    "totem_gap": (5.0, 2.0, 12.0),
    "og_min_score": (18.0, 6.0, 30.0),  # Overgrowth only on a cluster this dangerous
    "rage_engaged": (0.5, 0.15, 0.9),  # share of the army fighting before Rage
    "rage_gap": (9.0, 4.0, 15.0),
    "heal_hp": (0.6, 0.3, 0.9),
    "invis_hp": (
        0.6,
        0.3,
        0.9,
    ),  # Invisibility when the army drops below this health ...
    "invis_hot": (2.0, 1.0, 4.0),  # ... or this many heavy defenses shoot it
    "invis_gap": (4.5, 4.25, 8.0),
    "recall_after": (12.0, 5.0, 30.0),
    "recall_hp": (0.4, 0.2, 0.7),
    "haste_after": (3.0, 0.0, 12.0),
    "haste_gap": (8.0, 4.0, 15.0),
    "poison_min": (3.0, 1.0, 6.0),
    "hero_hp": (0.5, 0.15, 0.85),  # generic hero ability: below this health ...
    "hero_time": (25.0, 5.0, 60.0),  # ... or after this long fighting
    "warden_hp": (0.4, 0.15, 0.8),
    "warden_hurt": (
        1.0 / 3.0,
        0.1,
        0.8,
    ),  # share of nearby troops hurt before Eternal Tome
    "duke_hp": (0.6, 0.2, 0.9),
    "arrow_aim": (
        0.0,
        0.0,
        1.0,
    ),  # > 0.5: Giant Arrow is aimed at a heavy defense in reach
    "arrow_reach": (12.0, 5.0, 20.0),
    "arrow_threat": (7.0, 3.0, 10.0),
    "dash_aim": (
        0.0,
        0.0,
        1.0,
    ),  # > 0.5: Rocket Backpack dashes at a heavy defense in reach
    "dash_reach": (8.0, 4.0, 14.0),
    "dash_threat": (7.0, 3.0, 10.0),
    "distract_reach": (
        0.0,
        0.0,
        10.0,
    ),  # > 2: a cleanup troop pulls a heavy defense off the push
    "distract_threat": (8.0, 4.0, 10.0),
    "distract_max": (2.0, 0.0, 4.0),
    "lure_time": (
        -1.0,
        -5.0,
        30.0,
    ),  # >= 0: one troop dropped by the Clan Castle at this time
    "eq_core_dist": (
        0.0,
        0.0,
        12.0,
    ),  # > 2: Earthquakes on the core walls once the push is this close to the TH
    "eq_core_n": (2.0, 1.0, 4.0),
    # from the attack audit (docs/ATTACK_AUDIT.md); off by default until screened
    "deep_drop": (
        0.0,
        0.0,
        1.0,
    ),  # > 0.5: drop into corridors / pockets on the attack side, as real players do
    "angry_min": (
        0.0,
        0.0,
        8.0,
    ),  # > 0: Angry Spell when this many push troops chase non-defenses near a defense
    "skeleton_on": (
        0.0,
        0.0,
        1.0,
    ),  # > 0.5: Skeleton Spell as a distraction by a heavy defense locked on the push
    "bat_on": (0.0, 0.0, 1.0),  # > 0.5: Bat Spell onto defenses near the push
    "tank_lead": (
        0.0,
        0.0,
        4.0,
    ),  # > 0.3: tanks land first, damage dealers this many seconds later
}
TANKS = {
    "Ice Golem",
    "Golem",
    "Lava Hound",
    "Ice Hound",
    "Giant",
    "Super Giant",
    "Electro Titan",
    "P.E.K.K.A",
    "Yeti",
    "Meteor Golem",
    "Headhunter",
}

# Army capacity. Game data v18.200.9 (Aug 2026) gives 4 camps x 80/85 =
# 320/340 at TH16/17, but every real TH16 attacker in the user's battle log
# (Oct 2026) brings 340 camp + 55 Clan Castle and every TH17 one 352, so a
# later update raised them: the observed values win. TH18 is unobserved.
HOUSING_CAP = {16: 340, 17: 352, 18: 352}
# Clan Castle troop capacity when the attacker's Castle level is unknown:
# observed like HOUSING_CAP (TH16/17 attackers in the log bring up to 55,
# above game data's 50 for a TH16 Castle L12). A plan that gives
# clan_castle_level uses that level's capacity (AttackPlan._cc_capacity).
CC_HOUSING = {16: 55, 17: 55, 18: 55}
SPELL_CAP = {16: 11, 17: 11, 18: 11}  # Wiki: Spell Factory and Dark Spell Factory.
CC_SPELLS = {16: 3, 17: 3, 18: 4}  # Clan Castle L12/13/14 (wiki)

SPELL_NAMES = {
    "lightning": "Lightning Spell",
    "heal": "Healing Spell",
    "rage": "Rage Spell",
    "jump": "Jump Spell",
    "freeze": "Freeze Spell",
    "clone": "Clone Spell",
    "invis": "Invisibility Spell",
    "recall": "Recall Spell",
    "revive": "Revive Spell",
    "totem": "Totem Spell",
    "poison": "Poison Spell",
    "eq": "Earthquake Spell",
    "haste": "Haste Spell",
    "skeleton": "Skeleton Spell",
    "bat": "Bat Spell",
    "overgrowth": "Overgrowth Spell",
    "iceblock": "Ice Block Spell",
    "angry": "Angry Spell",
    "santa": "Santa's Surprise",
    "frostmites": "Bag of Frostmites",
    "birthday": "Birthday Boom",
    "yellow": "Yellow Card",
}


@lru_cache(maxsize=1)
def _logged_builds(path):
    return [
        build
        for build in json.loads(Path(path).read_text(encoding="utf-8"))["builds"]
        if build.get("observed") and build.get("source_battle_timestamps")
    ]


@lru_cache(maxsize=1)
def _siege_donation_caps():
    # Wiki: Clan Castle, Siege Machine Level Cap table (Castle L6 through L13+).
    path = stats.ROOT / "data" / "wiki" / "tables" / "Clan_Castle.json"
    table = next(
        table
        for table in json.loads(path.read_text(encoding="utf-8"))["tables"]
        if table.get("heading") == "Siege Machine Level Cap"
    )
    return {
        row[0]: {
            castle: int(stats.num(value, default=0))
            for castle, value in zip(range(6, 14), row[1:])
        }
        for row in table["rows"]
    }


@dataclass
class SpellStock:
    name: str
    origin: str
    remaining: int
    level: int | None = None


@dataclass
class Deployment:
    time: float
    name: str
    x: float
    y: float
    group: str = "main"
    level: int | None = None
    town_hall: int | None = None
    source: str = "army"
    mode: str | None = None


@dataclass
class DefenseSnipe:
    target: Building
    tool: str
    kind: str
    x: float
    y: float
    value: float
    # Wiki: Rocket Spear, finite opening resources compete with later use.
    seconds: float = 0.0
    cost: float = 0.0
    damage: dict = field(default_factory=dict)
    casts: int = 0
    confidence: float = 1.0


def edge_point(battle, angle: float, lateral: float = 0.0):
    """Closest legal deploy point walking in from `angle`, shifted sideways."""
    dx, dy = math.cos(angle), math.sin(angle)
    px, py = -dy, dx
    last = None
    r = WORLD
    while r > 0:
        x = CENTER + px * lateral + dx * r
        y = CENTER + py * lateral + dy * r
        if 0.5 <= x < WORLD - 0.5 and 0.5 <= y < WORLD - 0.5:
            if battle.can_deploy(x, y):
                last = (x, y)
            elif last is not None:
                break
        r -= 0.5
    if last is None:
        last = (
            min(WORLD - 1.0, max(1.0, CENTER + dx * 24)),
            min(WORLD - 1.0, max(1.0, CENTER + dy * 24)),
        )
    return last


def _cheb(x, y):
    return max(abs(x - CENTER), abs(y - CENTER))


def defense_cluster(
    battle,
    effects,
    *,
    hp=None,
    eq_hits=None,
    points=None,
    min_kills=0,
    band=None,
    center=None,
    reach=None,
):
    """Return (x, y, value, kills) for the best visible defense cluster.

    Effects are (kind, radius, damage), with fractional maximum HP for quakes.
    Stable building order breaks ties; scouting never inspects hidden Teslas.
    """
    # Wiki: Rocket Spear, do not spend another spell on a claimed lethal volley.
    claimed = getattr(battle.plan, "_snipe_claimed", ())
    defenses = [
        b
        for b in battle.buildings
        if b.is_defense
        and battle.building_targetable(b)
        and b.id not in claimed
        and (hp is None or hp.get(b.id, b.hp) > 1e-9)
    ]
    if not defenses or not effects:
        return None
    # Wiki: Fireball, its splash is centered on the nearest visible defense.
    # Policy: reuse scores within a tick/HP version; keep at most 24 nearby centers.
    version = (battle.t, tuple((b.id, b.hp, b.eq_hits) for b in defenses))
    if getattr(battle, "_cluster_version", None) != version:
        battle._cluster_version = version
        battle._cluster_scores = {}
        battle._cluster_points = {}
    if points is None:
        if center is None:
            army = [u for u in battle.attackers if u.alive and u.group == "main"]
            if army:
                center = AttackPlan.centroid(army)
                reach = 18.0
        point_key = (center, reach)
        if point_key not in battle._cluster_points:
            nearby = [
                b
                for b in defenses
                if center is None or reach is None or b.edge_distance(*center) <= reach
            ]
            battle._cluster_points[point_key] = tuple(
                (b.x, b.y)
                for b in nlargest(24, nearby, key=lambda b: THREAT.get(b.key, 1))
            )
        points = battle._cluster_points[point_key]
    score_key = (
        tuple(effects),
        tuple(points),
        min_kills,
        band,
        None if hp is None else tuple(hp.get(b.id, b.hp) for b in defenses),
        (
            None
            if eq_hits is None
            else tuple(eq_hits.get(b.id, b.eq_hits) for b in defenses)
        ),
    )
    if score_key in battle._cluster_scores:
        return battle._cluster_scores[score_key]
    best = None
    for x, y in points:
        score = 0.0
        kills = 0
        for b in defenses:
            remaining = b.hp if hp is None else hp.get(b.id, b.hp)
            damage = 0.0
            quakes = b.eq_hits if eq_hits is None else eq_hits.get(b.id, b.eq_hits)
            for kind, radius, value in effects:
                if kind in ("arrow", "dash"):
                    if not _band_hit(b, band, kind, radius):
                        continue
                    # Wiki: Giant Arrow, double damage to Air Defenses.
                    damage += value * (2 if kind == "arrow" and b.key == "ad" else 1)
                    continue
                elif b.edge_distance(x, y) > radius:
                    continue
                # Wiki: Lightning Spell/Home Village, TH/CC/storages are immune.
                if kind == "lightning" and b.key in spells.STORAGES | {"th", "cc"}:
                    continue
                if kind == "quake":
                    # Wiki: Earthquake Spell, building damage diminishes 1, 1/3, 1/5.
                    damage += b.max_hp * value / (2 * quakes + 1)
                    quakes += 1
                else:
                    damage += value
            # User (TH16 ranked, 2026-10-23): punish several valuable defenses at once.
            score += THREAT.get(b.key, 1) * min(1.0, damage / remaining)
            if damage >= remaining - 1e-9:
                kills += 1
        if score > 0 and kills >= min_kills and (best is None or score > best[2]):
            best = (x, y, score, kills)
    battle._cluster_scores[score_key] = best
    return best


def _band_hit(building, band, kind, radius):
    x, y, dx, dy, length = band
    along = (building.x - x) * dx + (building.y - y) * dy
    if kind == "arrow":
        # Wiki: Giant Arrow, pierces forward along the Queen's current target.
        off = abs((building.x - x) * dy - (building.y - y) * dx)
        return 0 < along < length and off <= building.half_hit + radius
    # game data v18.200.9: DragonDukeDeadlyDashMapCenter.ActAsPenetratingRadius=150.
    along = min(length, max(0.0, along))
    if building.edge_distance(x + dx * along, y + dy * along) <= radius:
        return True
    # Test corner projections too: the dash sweeps the whole square hitbox.
    for offset_x in (-building.half_hit, building.half_hit):
        for offset_y in (-building.half_hit, building.half_hit):
            along = (building.x + offset_x - x) * dx + (building.y + offset_y - y) * dy
            along = min(length, max(0.0, along))
            if building.edge_distance(x + dx * along, y + dy * along) <= radius:
                return True
    return False


@dataclass
class Wave:
    group: str
    units: list  # (name, count)
    spread: float = 2.5


@dataclass
class AttackPlan:
    angle: float = 0.0
    town_hall: int = 18
    seed: int = 0
    label: str = "attack"
    funnel_heroes: list = field(default_factory=list)  # (name, lateral)
    flank: list = field(default_factory=list)  # (name, count, lateral)
    main: list = field(default_factory=list)  # list[Wave]
    support: list = field(default_factory=list)  # list[Wave], 2 s after main
    push_heroes: list = field(default_factory=list)
    cleanup: list = field(default_factory=list)  # (name, count)
    breakers: list = field(default_factory=list)  # (name, count) kept for wall access
    siege: str | None = None
    siege_donated: bool = False
    cc_troops: list = field(
        default_factory=list
    )  # Clan Castle troops, released when the siege breaks
    cc_spells: dict = field(default_factory=dict)  # Clan Castle spells (key -> count)
    spells: dict = field(default_factory=dict)  # key -> count (keys in SPELL_NAMES)
    ground: bool = True
    auto_ability_on_ko: bool = True
    zap_ad: tuple = (0, 0)  # (lightnings, quakes) opening on an air defense
    main_min: float = 8.0
    main_max: float = 22.0
    strength: float = 1.0
    loadouts: dict = field(default_factory=dict)
    troop_levels: dict = field(default_factory=dict)
    spell_levels: dict = field(default_factory=dict)
    cc_spell_levels: dict = field(default_factory=dict)
    spell_factory_level: int | None = None
    dark_spell_factory_level: int | None = None
    laboratory_level: int | None = None
    clan_castle_level: int | None = None
    event_ruleset: dict = field(default_factory=dict)
    auto_revive: bool = True
    equipment_levels: dict = field(default_factory=dict)
    # data/your-levels.json: only account-built plans enforce equipment ownership.
    account_equipment: bool = False
    pet_levels: dict = field(default_factory=dict)
    hero_levels: dict = field(default_factory=dict)
    revive_delay: float = 1.5  # Attacker policy assumption; no wiki delay.
    freeze_first: tuple = ()  # building keys to Freeze before anything else
    pol: dict = field(default_factory=dict)  # learned policy values (POLICY keys)
    charge_hero: str | None = (
        None  # Queen / Champion charge: this hero opens with Healers along the side
    )
    charge_lat: float = 0.0
    charge_at: float = 0.0
    charge_recall_hp: float = 0.35  # Recall the charging hero below this health ...
    charge_len: float = 25.0  # ... or this long after the charge starts
    recall_funnel: bool = (
        False  # Recall then redeploy the charge up the opposite flank (TrophyCoach QC guide)
    )
    split_main: float = (
        0.0  # > 0: the main wave lands on two flanks this far apart (radians), e.g. two-flank Hydra
    )
    recalled: list = field(default_factory=list)
    _cast_log: list = field(default_factory=list)
    _totem_casts: list = field(default_factory=list)  # (time, x, y)
    _next_brain: float = 0.0
    _phase: str = "funnel"
    _entry: tuple | None = None
    _main_at: float = 0.0
    _zap_done: bool = False
    _cc_released: bool = False
    # Wiki: Eagle Artillery, eliminate exposed key defenses before the main army.
    snipe_exposed: InitVar[bool] = True
    # Wiki: Rocket Spear, weigh early removal against the ability's later use.
    # Policy: value requires a +2 margin; aggressive accepts down to -0.5.
    snipe_mode: InitVar[str] = "value"
    snipe_log: InitVar[tuple] = ()

    def __setattr__(self, name, value):
        # Wiki: Eagle Artillery, early removal protects the main army.
        # Keep defaults implicit for the current Rust plan-field whitelist.
        if (
            (name == "snipe_exposed" and value is True)
            or (name == "snipe_mode" and value == "value")
            or (name == "snipe_log" and not value)
        ):
            self.__dict__.pop(name, None)
        else:
            super().__setattr__(name, value)

    def P(self, name):
        v = self.pol.get(name)
        return POLICY[name][0] if v is None else v

    def __post_init__(self, snipe_exposed=True, snipe_mode="value", snipe_log=()):
        self.snipe_exposed = snipe_exposed
        self.snipe_mode = snipe_mode
        self.snipe_log = list(snipe_log)
        if self.snipe_mode not in ("off", "value", "aggressive"):
            raise ValueError(f"Unknown snipe mode {self.snipe_mode}")
        self.spells = dict(self.spells)
        self.cleanup = [list(c) for c in self.cleanup]
        self._charge_n = 0
        self._later = []  # (time, name, x, y, group, jitter): delayed drops (tank lead)
        self._distracts = 0
        self._lured = False
        self.breakers = [list(b) for b in self.breakers]
        self._spells0 = dict(self.spells)
        self._cc_spells0 = dict(self.cc_spells)
        self._spell_stock = []
        for origin, inventory in (
            ("brewed", self._spells0),
            ("donated", self._cc_spells0),
        ):
            for key, count in inventory.items():
                if key not in SPELL_NAMES:
                    raise ValueError(f"Unknown spell key {key}")
                if type(count) is not int or count < 0:
                    raise ValueError(f"Invalid {origin} spell count for {key}: {count}")
                self._spell_stock.append(SpellStock(SPELL_NAMES[key], origin, count))
        self.spells = {
            key: self._spells0.get(key, 0) + self._cc_spells0.get(key, 0)
            for key in self._spells0.keys() | self._cc_spells0.keys()
        }

    # ----------------------------------------------------------- inventory
    def _building_level(self, name, supplied):
        production = {
            "Barracks": "barracks",
            "Dark Barracks": "dbarracks",
            "Workshop": "workshop",
        }
        if supplied is None and self.account_equipment and name in production:
            from ..meta_armies import user_levels

            return user_levels().get("levels", {}).get(production[name], 0)
        return stats.max_level(name, self.town_hall) if supplied is None else supplied

    def _siege_level_cap(self):
        # Wiki: Clan Castle, siege donations use their own cap, not the Laboratory.
        castle = self._building_level("Clan Castle", self.clan_castle_level)
        return _siege_donation_caps()[self.siege].get(min(castle or 0, 13), 0)

    def _cc_capacity(self, castle):
        """Clan Castle troop housing for this attack (uses CC_HOUSING)."""
        if self.clan_castle_level is None:
            return CC_HOUSING[self.town_hall]
        if not castle:
            return 0
        # game data v18.200.9: Clan Castle.HousingSpace=50 -> troop capacity
        # 50 at Castle L11 (the user's; L12 also 50, L13-14 55). The user's
        # logged attacks bring at most 50, matching.
        return int(stats.get("Clan Castle", castle, "Troop Capacity"))

    def _spell_level(self, stock):
        if stock.level is not None:
            return stock.level
        if stock.origin == "donated":
            levels = self.cc_spell_levels
            castle = self._building_level("Clan Castle", self.clan_castle_level)
            # Wiki: Clan Castle, Laboratory Level Cap.
            lab = (
                stats.get("Clan Castle", castle, "~laboratory level cap", default=0)
                if castle
                else 0
            )
            candidates = [
                row["level"]
                for row in stats.record(stock.name)["levels"]
                if isinstance(row["level"], int)
                and stats.get(
                    stock.name, row["level"], "Laboratory Level Required", default=0
                )
                <= lab
                and stats.required_town_hall(stock.name, row["level"])
                <= stats.required_town_hall("Laboratory", int(lab))
            ]
            default = max(candidates, default=None)
        else:
            levels = self.spell_levels
            lab = self._building_level("Laboratory", self.laboratory_level)
            candidates = [
                row["level"]
                for row in stats.record(stock.name)["levels"]
                if isinstance(row["level"], int)
                and stats.required_town_hall(stock.name, row["level"]) <= self.town_hall
                and stats.get(
                    stock.name, row["level"], "Laboratory Level Required", default=0
                )
                <= lab
            ]
            default = max(candidates, default=None)
        return levels.get(stock.name, default)

    def housing(self) -> dict:
        """Army and spell capacity, including actual attacking building levels."""

        def h(name):
            if name in heroes.HEROES:
                return 0
            attrs = stats.attrs(name)
            return int(attrs.get("housing_ck") or attrs.get("housing") or 0)

        def sp_space(inventory):
            return sum(
                int(stats.attrs(SPELL_NAMES[key])["housing"]) * count
                for key, count in inventory.items()
            )

        camp = sum(h(name) * count for name, count, _ in self.flank)
        camp += sum(
            h(name) * count
            for wave in self.main + self.support
            for name, count in wave.units
        )
        camp += sum(h(name) * count for name, count in self.cleanup + self.breakers)
        # Wiki: Army Camp, moving Healers into a charge does not free housing.
        camp += h("Healer") * self._charge_n
        factory = self._building_level("Spell Factory", self.spell_factory_level)
        dark = self._building_level("Dark Spell Factory", self.dark_spell_factory_level)
        castle = self._building_level("Clan Castle", self.clan_castle_level)
        # Wiki: Spell Factory, Dark Spell Factory and Clan Castle capacity tables.
        capacity = sum(
            stats.get(name, level, "Spell Storage Capacity")
            for name, level in (
                ("Spell Factory", factory),
                ("Dark Spell Factory", dark),
            )
            if level
        )
        return {
            "camp": camp,
            "camp_cap": HOUSING_CAP[self.town_hall],
            "cc": sum(
                h(
                    entry
                    if isinstance(entry, str)
                    else entry.get("name") or entry["type"]
                )
                * (1 if isinstance(entry, str) else entry.get("count", 1))
                for entry in self.cc_troops
            ),
            "cc_cap": self._cc_capacity(castle),
            "spells": sp_space(self._spells0),
            "spell_cap": capacity,
            "cc_spells": sp_space(self._cc_spells0),
            "cc_spell_cap": (
                stats.get("Clan Castle", castle, "Spell Capacity", default=0)
                if castle
                else 0
            ),
            "siege": self.siege,
        }

    def legal(self) -> list:
        """Problems with roster, loadouts, levels, unlocks and army capacity."""
        out = []
        try:
            quantities = [(name, count) for name, count, _ in self.flank]
            quantities.extend(
                (name, count)
                for wave in self.main + self.support
                for name, count in wave.units
            )
            quantities.extend(self.cleanup + self.breakers)
            roster = [name for name, _ in self.funnel_heroes] + list(self.push_heroes)
            if self.charge_hero:
                roster.append(self.charge_hero)
            roster.extend(
                name
                for name, count in quantities
                if count and name in heroes.HEROES
                for _ in range(count)
            )
            # Wiki: Hero Hall, L10 (TH16), L11 and L12 each have four Hero Slots.
            hall = stats.max_level("Hero Hall", self.town_hall)
            slots = int(stats.get("Hero Hall", hall, "Hero Slots", default=0))
            if len(roster) > slots:
                out.append(f"heroes {len(roster)} > {slots} slots")
            seen = set()
            pets = set()
            for name in roster:
                if name in seen:
                    out.append(f"Duplicate hero: {name}")
                    continue
                seen.add(name)
                if name not in heroes.HEROES:
                    out.append(f"Unknown hero: {name}")
                    continue
                if stats.max_level(name, self.town_hall) is None:
                    out.append(f"{name} is unavailable at Town Hall {self.town_hall}")
                lo = self.loadouts.get(name) or heroes.DEFAULT_LOADOUTS[name]
                if lo.hero != name:
                    out.append(f"Loadout for {lo.hero} cannot be applied to {name}")
                if len(lo.equipment) > 2:
                    out.append(f"{name} can equip at most 2 equipment items")
                if len(set(lo.equipment)) != len(lo.equipment):
                    out.append(f"Duplicate equipment for {name}")
                for item in lo.equipment:
                    if stats.record(item)["kind"] != "equipment":
                        out.append(f"{item} is not hero equipment")
                        continue
                    owner = stats.attrs(item).get("raw", {}).get("User")
                    if owner != name:
                        out.append(f"{item} belongs to {owner}, not {name}")
                    maximum = stats.max_level(item, self.town_hall)
                    if maximum is None:
                        out.append(
                            f"{item} is unavailable at Town Hall {self.town_hall}"
                        )
                    elif item in self.equipment_levels:
                        stats.validate_level(
                            item, self.equipment_levels[item], self.town_hall
                        )
                if lo.pet:
                    if lo.pet in pets:
                        out.append(f"Duplicate pet: {lo.pet}")
                    pets.add(lo.pet)
                    if stats.record(lo.pet)["kind"] != "pet":
                        out.append(f"{lo.pet} is not a pet")
                    elif stats.max_level(lo.pet, self.town_hall) is None:
                        out.append(
                            f"{lo.pet} is unavailable at Town Hall {self.town_hall}"
                        )
                    elif lo.pet in self.pet_levels:
                        stats.validate_level(
                            lo.pet, self.pet_levels[lo.pet], self.town_hall
                        )
            # Wiki: Super Troops, only two boosted types at once; donated troops
            # do not occupy a boost slot. Count positive camp quantities only.
            boosted = {
                name
                for name, count in quantities
                if count > 0 and stats.record(name).get("super")
            }
            if len(boosted) > 2:
                out.append(f"boosted super troop types {len(boosted)} > 2")
            for name, count in quantities:
                if type(count) is not int or count < 0:
                    raise ValueError(f"Invalid troop count for {name}: {count}")
            for name, supplied in (
                ("Spell Factory", self.spell_factory_level),
                ("Dark Spell Factory", self.dark_spell_factory_level),
                ("Laboratory", self.laboratory_level),
                ("Clan Castle", self.clan_castle_level),
            ):
                if supplied is not None:
                    if type(supplied) is not int or supplied < 0:
                        raise ValueError(f"Invalid {name} level {supplied}")
                    if supplied:
                        stats.validate_level(name, supplied, self.town_hall)
            # game data v18.200.9 / registry raw: Meteor Golem requires
            # Barracks 19; Sky Wagon requires Workshop 9 (TH16 maxima 18/8).
            # output/research/usage/meteor-golem.md and sky-wagon.md.
            trained = list(quantities)
            if self.siege and not self.siege_donated:
                trained.append((self.siege, 1))
            for name, count in trained:
                if count <= 0:
                    continue
                raw = stats.attrs(name).get("raw", {})
                for building in ("Barracks", "Dark Barracks", "Workshop"):
                    required = stats.num(raw.get(building + " Level Required"), 0)
                    available = self._building_level(building, None) or 0
                    if available < required:
                        raise ValueError(
                            f"{name} requires {building} level {required:g} (available {available})"
                        )
            # game data v18.200.9: Laboratory L14.TownHallLevel=16;
            # Dragon L11/L12.LaboratoryLevel=14/15 -> cap explicit overrides.
            # game data v18.200.9: Archer Queen L96.RequiredTownHallLevel=17.
            lab = self._building_level("Laboratory", self.laboratory_level)
            troop_levels = self.troop_levels
            if self.siege and self.siege_donated:
                # Wiki: Clan Castle, also validate the default donated siege level.
                troop_levels = {self.siege: self._level(self.siege), **troop_levels}
            for levels in (troop_levels, self.hero_levels):
                for name, level in levels.items():
                    if type(level) is not int or level <= 0:
                        raise ValueError(f"Invalid {name} level {level}")
                    if name == self.siege and self.siege_donated:
                        # Wiki: Clan Castle, separate Siege Machine Level Cap table.
                        stats.row(name, level)
                        cap = self._siege_level_cap()
                        if level > cap:
                            raise ValueError(
                                f"{name} level {level} exceeds Clan Castle donation cap {cap}"
                            )
                        continue
                    stats.validate_level(name, level, self.town_hall)
                    research = name
                    # Wiki: Super Troops, their level follows the original troop.
                    if stats.record(name).get("super"):
                        for column in stats.attrs(name).get("raw", {}):
                            base = column.removesuffix(" Level Required")
                            if (
                                column.endswith(" Level Required")
                                and base in stats.registry()
                                and stats.record(base)["kind"] == "troop"
                            ):
                                research = base
                                break
                    if (
                        stats.get(
                            research, level, "Laboratory Level Required", default=0
                        )
                        > lab
                    ):
                        raise ValueError(
                            f"{name} level {level} exceeds Laboratory level {lab}"
                        )
            # Wiki: Spell Factory and Clan Castle, brewed/donated level limits.
            for levels, donated in (
                (self.spell_levels, False),
                (self.cc_spell_levels, True),
            ):
                for name, level in levels.items():
                    spells.validate(self, name, level, donated=donated)
            for stock in self._spell_stock:
                if stock.remaining == 0 and stock.level is None:
                    continue
                level = self._spell_level(stock)
                spells.validate(
                    self, stock.name, level, donated=stock.origin == "donated"
                )
            housing = self.housing()
            for key, cap in (
                ("camp", "camp_cap"),
                ("cc", "cc_cap"),
                ("spells", "spell_cap"),
                ("cc_spells", "cc_spell_cap"),
            ):
                if housing[key] > housing[cap]:
                    out.append(f"{key} {housing[key]} > {housing[cap]}")
        except (KeyError, TypeError, ValueError) as error:
            out.append(str(error))
        return out

    def _logged_exception(self, problem):
        # data/observed-armies.json: nine decoded TH17 armies have four donated
        # spell spaces despite the mirrored Castle cap of three. An observed
        # flag alone is not provenance. Only this cap and the logged Raven's
        # existing replay replacement may warn; roster/equipment errors fail.
        if problem not in (
            "cc_spells 4 > 3.0",
            "Greedy Raven is unavailable at Town Hall 17",
        ) or not getattr(self, "observed", False):
            return False
        from collections import Counter

        from ..meta_armies import OBSERVED, SIEGES, SPELL_KEYS, _loadouts

        for build in _logged_builds(str(OBSERVED)):
            key = f"{build['archetype']}-{build['th']}-{build['build']}"
            if key != getattr(self, "build_id", None) or self.town_hall != build["th"]:
                continue
            brewed = {SPELL_KEYS[n]: c for n, c in build["spells"].items() if c}
            donated = {
                SPELL_KEYS[n]: c
                for n, c in build.get("cc", {}).items()
                if n in SPELL_KEYS and c
            }
            roster = [name for name, _ in self.funnel_heroes] + list(self.push_heroes)
            if self.charge_hero:
                roster.append(self.charge_hero)
            expected = Counter(
                {n: c for n, c in build["troops"].items() if n not in SIEGES}
            )
            fixed = Counter()
            for n, c, _ in self.flank:
                fixed[n] += c
            for wave in self.main + self.support:
                for n, c in wave.units:
                    fixed[n] += c
            fixed["Healer"] += self._charge_n
            reserves = Counter()
            for n, c in self.cleanup + self.breakers:
                reserves[n] += c
            # cleanup/breakers are mutable remaining stocks in the generic plan.
            # Only their depletion is permitted; every other camp count is exact.
            reserve_names = {n for n, _ in self.cleanup + self.breakers}
            if self._phase == "done":
                from ..meta_armies import BREAKERS, CLEANUP

                reserve_names.update(CLEANUP | BREAKERS)
            army_matches = all(
                (
                    fixed[n] + reserves[n] <= expected[n]
                    if n in reserve_names
                    else fixed[n] == expected[n]
                )
                for n in expected.keys() | fixed.keys() | reserves.keys()
            )
            expected_cc = Counter(
                {
                    n: c
                    for n, c in build.get("cc", {}).items()
                    if n not in SPELL_KEYS and n not in SIEGES
                }
            )
            actual_cc = Counter()
            for entry in self.cc_troops:
                if isinstance(entry, str):
                    actual_cc[entry] += 1
                else:
                    actual_cc[entry.get("name") or entry["type"]] += entry.get(
                        "count", 1
                    )
            expected_siege = next(
                (
                    n
                    for n in list(build["troops"]) + list(build.get("cc", {}))
                    if n in SIEGES
                ),
                None,
            )
            return (
                sorted(roster) == sorted(build["heroes"])
                and army_matches
                and actual_cc == expected_cc
                and self.siege == expected_siege
                and self.loadouts == _loadouts(build, build["heroes"])
                and {k: c for k, c in self._spells0.items() if c} == brewed
                and {k: c for k, c in self._cc_spells0.items() if c} == donated
            )
        return False

    def require_legal(self):
        problems = []
        # tools/baselab/replay_log.py to_build: armies decoded from the user's
        # battle log ("log-N") were really played, so a legality miss there is
        # a gap in our unlock data (e.g. a TH15 attacker's Spirit Fox and
        # Totem Spell), not an illegal army: warn and keep the logged army.
        battle_log = getattr(self, "observed", False) and (
            str(getattr(self, "build_id", "")).startswith("log-")
            or getattr(self, "real_battle", False)  # replay_observed.py
        )
        for problem in self.legal():
            if battle_log or self._logged_exception(problem):
                warnings.warn(
                    f"Logged army {getattr(self, 'build_id', '(replay)')}: {problem}; using documented replay handling",
                    RuntimeWarning,
                    stacklevel=2,
                )
            else:
                problems.append(problem)
        if problems:
            raise ValueError("Illegal attack plan: " + "; ".join(problems))
        for stock in self._spell_stock:
            if stock.remaining:
                stock.level = self._spell_level(stock)

    def cast_spell(self, battle, name, x, y, *, level=None, origin=None):
        self.require_legal()
        stock = next(
            (
                entry
                for entry in self._spell_stock
                if entry.name == name
                and entry.remaining > 0
                and (origin is None or entry.origin == origin)
                and (level is None or self._spell_level(entry) == level)
            ),
            None,
        )
        if stock is None:
            raise ValueError(f"No matching {name} remaining")
        selected_level = self._spell_level(stock)
        field = spells.cast_effect(battle, name, x, y, selected_level)
        stock.remaining -= 1
        key = next(key for key, value in SPELL_NAMES.items() if value == name)
        self.spells[key] -= 1
        # Wiki: Eagle Artillery, five activation spaces per spell housing.
        battle.deployed_housing += 5 * stats.attrs(name)["housing"]
        self._cast_log.append((round(battle.t, 1), key))
        if key == "totem":
            # User (TH16 ranked, 2026-10-23): spread Totems between drops.
            self._totem_casts.append((battle.t, x, y))
        return field

    def revive_knocked_out(self, battle, *, single_cast=False):
        if not self.auto_revive:
            return
        for hero in battle.attackers:
            if (
                not hero.alive
                and hero.extra.get("revivable")
                and self._have("revive")
                and battle.t >= hero.extra["ko_at"] + self.revive_delay
            ):
                self._use(battle, "revive", hero.x, hero.y)
                # Video: docs/VIDEO_MEASUREMENTS.md:31, one spell drop per action.
                if single_cast:
                    return

    def _level(self, name):
        if name in heroes.HEROES:
            return self.hero_levels.get(name)
        if name == self.siege and self.siege_donated:
            # Wiki: Clan Castle, pass its donation cap explicitly to battle.spawn.
            return self.troop_levels.get(name, self._siege_level_cap())
        return self.troop_levels.get(name)

    # ------------------------------------------------------------ deploying
    def _charge_spells(self, battle, charge):
        """How players run a hero charge: Invisibility on the hero when heavy
        defenses lock on (or she is hurt), then Recall her (and the Healers
        near her) before she dies or once the charge has done its job; she
        comes back with the main push (see on_tick / _launch_main)."""
        t = battle.t
        if t < getattr(self, "_busy_until", 0.0):
            return
        hero = next(
            (u for u in charge if u.is_hero and u.name == self.charge_hero), None
        )
        if hero is None:
            return
        frac = hero.hp / max(1.0, hero.max_hp)
        locked = any(
            b.alive
            and b.weapon is not None
            and b.weapon.target is hero
            and THREAT.get(b.key, 0) >= 4
            for b in battle.buildings
        )
        if (
            self._have("invis")
            and t - self._last("invis") > self.P("invis_gap")
            and t >= hero.invisible_until
            and (locked or frac < 0.6)
        ):
            self._use(battle, "invis", hero.x, hero.y)
            return
        done = t - self.charge_at > self.charge_len
        if (
            self._have("recall")
            and self._last("recall_charge") < 0
            and (frac < self.charge_recall_hp or done)
        ):
            self._use(battle, "recall", hero.x, hero.y)
            self._cast_log.append((round(t, 1), "recall_charge"))

    def setup_charge(self, hero, healers, lateral=0.0, at=0.0):
        """A hero charge (Queen Charge, Royal Champion charge): the hero opens
        toward a scouted cluster with up to `healers` of the army's own
        Healers (taken from the support waves), before the main push. Spells
        are spent on the charge while it is the only thing on the map."""
        heroes_in = [n for n, _ in self.funnel_heroes] + list(self.push_heroes)
        if hero not in heroes_in:
            return False
        self.funnel_heroes = [(n, l) for n, l in self.funnel_heroes if n != hero]
        self.push_heroes = [n for n in self.push_heroes if n != hero]
        # Healers heal ground units only (wiki: Healer), so a flying hero
        # (Dragon Duke, Minion Prince) charges without them
        want = 0 if stats.attrs(hero).get("is_flying") else int(healers)
        taken = 0
        waves = []
        for w in self.support:
            units = []
            for n, c in w.units:
                if n == "Healer" and taken < want:
                    k = min(c, want - taken)
                    taken += k
                    c -= k
                if c > 0:
                    units.append((n, c))
            waves.append(Wave(w.group, units, spread=w.spread))
        self.support = [w for w in waves if w.units]
        self.charge_hero, self._charge_n, self.charge_lat, self.charge_at = (
            hero,
            taken,
            lateral,
            at,
        )
        return True

    def charge_point(self, battle, angle, lateral=0.0):
        # User (TH16 ranked, 2026-10-23): hero charges take out defense clusters.
        # Policy: scout a 6-tile cluster, at most 12 tiles from a legal edge drop.
        effects = [("damage", 6.0, math.inf)]
        candidates = []
        # Wiki: Archer Queen, a charge clears the selected entry flank.
        # Policy: keep clusters within 45 degrees of the chosen lateral entry.
        origin = edge_point(battle, angle, lateral)
        direction = math.atan2(origin[1] - CENTER, origin[0] - CENTER)
        for b in battle.buildings:
            if not b.is_defense or not battle.building_targetable(b):
                continue
            bearing = math.atan2(b.y - CENTER, b.x - CENTER)
            if math.cos(bearing - direction) < math.cos(math.pi / 4):
                continue
            x, y = edge_point(battle, bearing, lateral)
            if b.edge_distance(x, y) <= 12.0:
                candidates.append((b.x, b.y))
        cluster = defense_cluster(battle, effects, points=candidates)
        if cluster is None:
            return edge_point(battle, angle, lateral)
        return edge_point(
            battle, math.atan2(cluster[1] - CENTER, cluster[0] - CENTER), lateral
        )

    def _has_backpack(self):
        # Wiki: Hero Equipment, the equipped and owned item enables its ability.
        loadout = (
            self.loadouts.get("Dragon Duke") or heroes.DEFAULT_LOADOUTS["Dragon Duke"]
        )
        return "Rocket Backpack" in loadout.equipment and (
            not self.account_equipment or "Rocket Backpack" in self.equipment_levels
        )

    def backpack_point(self, battle, angle, lateral=0.0):
        # User (TH16 ranked, 2026-10-23): Backpack openings punish defense bands.
        # Policy: stable one-degree scan of legal edge drops, starting at the plan's side.
        level = self.equipment_levels.get("Rocket Backpack") or stats.max_level(
            "Rocket Backpack", self.town_hall
        )
        damage = float(
            heroes._ability_data(
                "Rocket Backpack", level, "DragonDukeDeadlyDashMapCenter"
            )["ActAsPenetratingDamage"]
        )
        best = None
        point = edge_point(battle, angle, lateral)
        for index in range(360):
            x, y = (
                point if index == 0 else edge_point(battle, angle + math.radians(index))
            )
            if not battle.can_deploy(x, y):
                continue
            dx, dy, length, radius = heroes.dash_geometry(x, y, (1.0, 0.0))
            candidate = defense_cluster(
                battle,
                [("dash", radius, damage)],
                points=[(x, y)],
                band=(x, y, dx, dy, length),
            )
            if candidate is not None and (best is None or candidate[2] > best[2]):
                best = candidate
        return best[:2] if best is not None else point

    def deployments(self, battle):
        out = self.opening_deployments(battle)
        th = self.town_hall
        for name, lateral in self.funnel_heroes:
            if name in self._snipe_deployed:
                continue
            x, y = edge_point(battle, self.angle, lateral)
            if name == "Dragon Duke" and self._has_backpack():
                x, y = self.backpack_point(battle, self.angle, lateral)
            out.append(
                Deployment(
                    0.0,
                    name,
                    x,
                    y,
                    group="funnel",
                    level=self._level(name),
                    town_hall=th,
                )
            )
        if self.charge_hero:
            # User (TH16 ranked, 2026-10-23): scout the charge flank for clusters.
            x, y = self.charge_point(battle, self.angle, self.charge_lat)
            if self.charge_hero == "Dragon Duke" and self._has_backpack():
                x, y = self.backpack_point(battle, self.angle, self.charge_lat)
            elif self.P("deep_drop") > 0.5:
                x, y = self._deep_charge_point(battle, (x, y))
            out.append(
                Deployment(
                    self.charge_at,
                    self.charge_hero,
                    x,
                    y,
                    group="charge",
                    level=self._level(self.charge_hero),
                    town_hall=th,
                )
            )
            for k in range(self._charge_n):
                out.append(
                    Deployment(
                        self.charge_at + 0.6 + 0.1 * k,
                        "Healer",
                        x,
                        y,
                        group="charge",
                        level=self._level("Healer"),
                        town_hall=th,
                    )
                )
        t = 0.5
        for name, count, lateral in self.flank:
            for k in range(count):
                x, y = edge_point(battle, self.angle, lateral + (k - count / 2) * 0.6)
                out.append(
                    Deployment(
                        t,
                        name,
                        x,
                        y,
                        group="funnel",
                        level=self._level(name),
                        town_hall=th,
                    )
                )
                t += 0.15
        return out

    def _snipe_available(self, name):
        # Wiki: Hero Equipment, a tool must be carried by an undeployed hero.
        if name in getattr(self, "_snipe_deployed", set()):
            return False
        if name == "Flame Flinger":
            return self.siege == name
        return name != self.charge_hero and (
            name in self.push_heroes
            or any(hero == name for hero, _ in self.funnel_heroes)
        )

    def _snipe_air_army(self):
        # Wiki: Air Defense, prioritize it for armies whose fighting troops fly.
        if hasattr(self, "inventory"):
            troops = list(self.inventory.items())
        else:
            troops = [item for wave in self.main + self.support for item in wave.units]
            troops += [(name, count) for name, count, _ in self.flank]
            troops += list(self.cleanup)
        air = ground = 0
        for name, count in troops:
            if name == "Healer" or stats.record(name)["kind"] == "siege":
                continue
            attrs = stats.attrs(name)
            housing = count * attrs.get("housing", 0)
            if attrs.get("is_flying"):
                air += housing
            else:
                ground += housing
        return air > ground

    def _snipe_weights(self, battle):
        # Wiki: Air Defense/Home Village, threatens air armies and ground Healers.
        # Wiki: Air Sweeper, affects only flying troops.
        # Wiki: Monolith, particularly dangerous to heroes and high-HP troops.
        # Policy multipliers on THREAT: air AD 2.5, Sweeper 3, Eagle/Scatter 1.25;
        # ground AD 0 (0.5 with Healers), Sweeper 0; air ground-only weapons 0.2.
        # Hero-heavy (4+ Healers or a charge): Monolith 1.6, single Inferno 1.5.
        air_army = self._snipe_air_army()
        if hasattr(self, "inventory"):
            healers = self.inventory.get("Healer", 0)
        else:
            healers = self._charge_n + sum(
                count
                for wave in self.main + self.support
                for name, count in wave.units
                if name == "Healer"
            )
        weights = {}
        # output/research/usage/hidden-tesla.md: concealed Teslas are not scouted.
        # https://clashofclans.fandom.com/wiki/Hidden_Tesla/Home_Village
        others = [
            b
            for b in battle.buildings
            if b.key != "wall" and (b.key != "tesla" or b.revealed)
        ]
        for building in battle.buildings:
            weight = float(THREAT.get(building.key, 1))
            if air_army:
                weight *= {
                    "ad": 2.5,
                    "sweeper": 3.0,
                    "eagle": 1.25,
                    "scatter": 1.25,
                }.get(building.key, 1.0)
                if building.weapon is not None and building.weapon.targets == "ground":
                    weight *= 0.2
            elif building.key == "ad":
                weight *= 0.5 if healers else 0.0
            elif building.key == "sweeper":
                weight = 0.0
            if healers >= 4 or self.charge_hero:
                if building.key == "mono":
                    weight *= 1.6
                elif building.key == "inferno" and building.mode == "single":
                    weight *= 1.5
            # User (TH16 ranked, 2026-10-24): an exposed Eagle is prime value for
            # a Spear, Backpack or Earthquake. A defense that reaches more of the
            # village fights more of the attack: scale by the share it covers.
            weapon = building.weapon
            if weapon is not None and others:
                covered = sum(
                    1
                    for other in others
                    if other is not building
                    and weapon.min_range
                    <= math.hypot(other.x - building.x, other.y - building.y)
                    <= weapon.range + building.half_hit
                )
                weight *= 1.0 + covered / len(others)
            weights[building.id] = weight
        return weights

    def _snipe_role(self, name):
        return "main" if name in self.push_heroes or name == self.siege else "funnel"

    def _snipe_cost(self, name, kind):
        # Wiki: Rocket Spear, early activation spends finite shots and paired gear.
        # Policy opportunity costs in THREAT units: ordinary walk 3, Arrow 4,
        # Spear 5, Backpack 7, Fireball 7, Flinger 4; main role +2, funnel +0.5.
        # These retain core damage, a funnel, siege cargo and paired protection.
        cost = {
            "queen": 3.0,
            "arrow": 4.0,
            "spear": 5.0,
            "dash": 7.0,
            "fireball": 7.0,
            "flinger": 4.0,
        }[kind]
        cost += 2.0 if self._snipe_role(name) == "main" else 0.5
        if kind not in ("queen", "flinger"):
            loadout = self.loadouts.get(name) or heroes.DEFAULT_LOADOUTS[name]
            # Wiki: Hero Equipment, activating a hero also uses its other ability.
            # Policy: price lost protection/healing, not passive equipment boosts.
            paired = {
                "Eternal Tome": 6.0,
                "Healing Tome": 3.0,
                "Invisibility Vial": 2.0,
                "Healer Puppet": 2.0,
                "Royal Gem": 1.5,
                "Haste Vial": 2.0,
                "Seeking Shield": 2.0,
                "Action Figure": 2.0,
                "Revenge Deck": 2.0,
            }
            cost += sum(
                paired.get(item, 0.0)
                for item in loadout.equipment
                if not self.account_equipment or item in self.equipment_levels
            )
        return cost

    def _snipe_timing(self, battle, name, kind, target, x, y, damage):
        from .playbook import action_time
        from .specs import unit_numbers

        # Policy: finish an opening within 12 s; charge 0.25 THREAT per second.
        # game data v18.200.9: QueenPierceProjectile.Speed=3500 -> 35 tiles/s.
        # game data v18.200.9: RocketSpearProjectile.Speed=1200 -> 12 tiles/s.
        # game data v18.200.9: vfx_chr_gw_Fireball_lvl1.FixedTravelTime=1500 -> 1.5 s.
        distance = math.hypot(target.x - x, target.y - y)
        seconds = action_time("deploy") + action_time("ability")
        level = self._level(name) or stats.max_level(name, self.town_hall)
        numbers = unit_numbers(name, level)
        if kind == "arrow":
            seconds += distance / 35.0
        elif kind == "dash":
            # game data v18.200.9: DragonDukeDeadlyDashMapCenter.Speed=1500 -> 15 tiles/s.
            seconds += distance / 15.0
        elif kind == "fireball":
            seconds += 1.5
        elif kind == "spear":
            equipment = self.equipment_levels.get("Rocket Spear") or stats.max_level(
                "Rocket Spear", self.town_hall
            )
            bonus = heroes._col("Rocket Spear", equipment, "damage per shot increase")
            shot = (numbers["dmg"] + bonus) * self.strength * battle.atk_hero_mult
            shots = max(1, math.ceil(target.hp / max(1.0, shot)))
            seconds += (shots - 1) * numbers["interval"] + distance / 12.0
        else:
            # Wiki: Flame Flinger/Archer Queen, sustained damage needs combat time.
            # Replace the helper's infinite rank estimate with a finite HP budget.
            dps = max(1.0, numbers["dps"] * self.strength * battle.atk_hero_mult)
            seconds = action_time("deploy") + target.hp / dps
            seconds += distance / (5.0 if kind == "flinger" else 12.0)
            damage = target.hp  # Candidates taking over 12 s are rejected below.
        flying = numbers["flying"] or (name == "Grand Warden" and not self.ground)
        incoming = 0.0
        for defense in battle.buildings:
            weapon = defense.weapon
            if not battle.building_targetable(defense) or weapon is None:
                continue
            if weapon.targets == ("ground" if flying else "air"):
                continue
            # Wiki: Eagle Artillery, it cannot retaliate before deployment activation.
            if (
                weapon.kind == "eagle"
                and battle.deployed_housing < weapon.extra["activation"]
            ):
                continue
            separation = math.hypot(defense.x - x, defense.y - y)
            if weapon.min_range <= separation <= weapon.range:
                incoming += weapon.damage / max(0.1, weapon.interval)
        # Wiki: Rocket Spear, X-Bows can retaliate; high damage can waste the volley.
        # Policy: HP loss lowers kill confidence and costs up to 4 THREAT units.
        loss = min(1.0, incoming * seconds / max(1.0, numbers["hp"]))
        return damage, seconds, loss

    def _snipe_tools(self):
        # Wiki: Hero Equipment, only carried, unreserved tools can open a snipe.
        tools = []
        # Policy: stable tool order breaks equal-value ties; no scouting RNG.
        for name in (
            "Archer Queen",
            "Royal Champion",
            "Flame Flinger",
            "Dragon Duke",
            "Grand Warden",
        ):
            if self._snipe_available(name):
                tool = heroes.sniping_tool(self, name)
                if tool is not None:
                    tools.append((name, tool))
        lightning = self._snipe_lightning_count()
        if lightning:
            effects = self._cluster_effects("lightning", lightning)
            tools.append(
                (
                    "Lightning Spell",
                    ("lightning", math.inf, effects[0][1], sum(e[2] for e in effects)),
                )
            )
        return tools

    def _opening_reachable(self, battle, tiles):
        # Wiki: Walls, an exposed attack position has a wall-free ground approach.
        # Use the grid's eight neighbors and corner rule, once from legal deploy tiles.
        from ..pathing import RES, _NEIGHBORS

        if hasattr(battle, "_opening_reachable"):
            return battle._opening_reachable
        grid = battle.grid
        n = grid.n
        blocked = grid.blocked.copy()
        # Wiki: Hidden Tesla, its unrevealed position cannot guide opening scouting.
        for building in battle.buildings:
            if building.key == "tesla" and not building.revealed:
                i0 = int(round((building.x - building.half_hit) * RES))
                i1 = int(round((building.x + building.half_hit) * RES))
                j0 = int(round((building.y - building.half_hit) * RES))
                j1 = int(round((building.y + building.half_hit) * RES))
                blocked[i0:i1, j0:j1] = False
        walkable = (~(blocked | grid.wall)).tolist()
        reached = [[False] * n for _ in range(n)]
        queue = []
        for x, y in tiles:
            i, j = grid.cell(x, y)
            if walkable[i][j] and not reached[i][j]:
                reached[i][j] = True
                queue.append((i, j))
        neighbors = _NEIGHBORS.tolist()
        for i, j in queue:
            for di, dj in neighbors:
                ni, nj = i + di, j + dj
                if not (0 <= ni < n and 0 <= nj < n):
                    continue
                if reached[ni][nj] or not walkable[ni][nj]:
                    continue
                if di and dj and (not walkable[i][nj] or not walkable[ni][j]):
                    continue
                reached[ni][nj] = True
                queue.append((ni, nj))
        battle._opening_reachable = reached
        return reached

    def exposed_defenses(self, battle):
        """Scout visible targets from legal tiles, without deploying or drawing RNG."""
        from ..pathing import RES
        from .playbook import action_time
        from .specs import unit_numbers

        if not self.snipe_exposed or self.snipe_mode == "off":
            return []
        tools = self._snipe_tools()
        if not tools:
            return []
        # Wiki: Rocket Spear, suitable targets depend on value and retaliation.
        # Policy: cap scouting at 24 valuable defenses and eight drops per tool/target.
        visible = [b for b in battle.buildings if battle.building_targetable(b)]
        defenses = [b for b in visible if battle.is_defense_target(b)]
        weights = self._snipe_weights(battle)
        targets = nlargest(24, defenses, key=lambda b: weights[b.id])
        main_point = edge_point(battle, self.angle)
        tiles = battle.deploy_tiles()
        reached = self._opening_reachable(battle, tiles)
        ranked_tiles = {}
        lightning_effects = self._cluster_effects(
            "lightning", self._snipe_lightning_count()
        )
        # Wiki: Earthquake Spell, price a spare paired cast without spending a breach.
        fallback = getattr(self, "_fallback", False)
        self._fallback = True
        try:
            paired_quake = self._spare_quakes(battle) > 0
        finally:
            self._fallback = fallback
        out = []
        for name, (kind, reach, radius, damage) in tools:
            # Wiki: Giant Arrow/Fireball, the caster's ordinary range controls approach.
            if kind == "lightning":
                approach = 0.5
                base_cost = 0.0
            else:
                level = self._level(name) or stats.max_level(name, self.town_hall)
                approach = min(reach, unit_numbers(name, level)["range"])
                if kind == "spear":
                    approach = reach
                base_cost = self._snipe_cost(name, kind)
            for target in targets:
                # Even a certain kill cannot repay a tool whose cost exceeds its value.
                if weights[target.id] < base_cost - 0.5:
                    continue
                if kind == "lightning" and target.key in spells.STORAGES | {"th", "cc"}:
                    continue
                extent = target.half_hit + approach
                n = battle.grid.n
                accessible = any(
                    reached[i][j]
                    and target.edge_distance((i + 0.5) / RES, (j + 0.5) / RES)
                    <= approach
                    for i in range(
                        max(0, int((target.x - extent) * RES)),
                        min(n, int((target.x + extent) * RES) + 1),
                    )
                    for j in range(
                        max(0, int((target.y - extent) * RES)),
                        min(n, int((target.y + extent) * RES) + 1),
                    )
                )
                if not accessible:
                    continue
                if target.id not in ranked_tiles:
                    ranked_tiles[target.id] = sorted(
                        ((target.edge_distance(x, y), x, y) for x, y in tiles),
                        key=lambda item: item[0],
                    )
                legal = [item for item in ranked_tiles[target.id] if item[0] <= reach]
                drops = legal[:4] + legal[-4:]
                best = None
                for distance, x, y in dict.fromkeys(drops):
                    band = None
                    center = (target.x, target.y)
                    effect_kind = "damage"
                    if kind in ("queen", "arrow"):
                        nearest = min(visible, key=lambda b: b.edge_distance(x, y))
                        if kind == "queen" and nearest is not target:
                            continue
                        if kind == "arrow":
                            dx, dy = nearest.x - x, nearest.y - y
                            length = math.hypot(dx, dy)
                            data = heroes.game_data(
                                "special_abilities", "ArcherQueenPierceProjectile"
                            )
                            band = (
                                x,
                                y,
                                dx / length,
                                dy / length,
                                length + float(data["PenetratingExtraRange"]) / 100.0,
                            )
                            effect_kind = "arrow"
                    elif kind == "dash":
                        dx, dy, length, radius = heroes.dash_geometry(x, y, (1.0, 0.0))
                        band = (x, y, dx, dy, length)
                        effect_kind = "dash"
                    elif kind in ("spear", "flinger", "fireball"):
                        nearest = min(defenses, key=lambda b: b.edge_distance(x, y))
                        if kind != "fireball" and nearest is not target:
                            continue
                        center = (nearest.x, nearest.y)
                        if (
                            kind == "fireball"
                            and target.edge_distance(*center) > radius
                        ):
                            continue
                    if band is not None:
                        if not _band_hit(target, band, effect_kind, radius):
                            continue
                        center = (x, y)
                    # Wiki: Giant Arrow/Fireball, track collateral within the
                    # existing line or splash geometry, using remaining HP.
                    casts = 0
                    if kind == "lightning":
                        effects = lightning_effects
                        dealt = 0.0
                        for effect in effects:
                            dealt += effect[2]
                            casts += 1
                            if dealt >= target.hp:
                                break
                        # Wiki: Lightning Spell, a short stack cannot destroy the target.
                        if dealt < target.hp:
                            continue
                        seconds = casts * action_time("spell") + spells.LAND_DELAY
                        loss = 0.0
                        # Policy: each spare zap can finish a later defense.
                        cost = 1.5 * casts
                    else:
                        dealt, seconds, loss = self._snipe_timing(
                            battle, name, kind, target, x, y, damage
                        )
                        cost = base_cost
                        if paired_quake and kind in ("arrow", "dash"):
                            # game data v18.200.9: Earthquake.NumberOfHits=5,
                            # TimeBetweenHitsMS=400 -> wait for the paired cast's pulses.
                            seconds += max(
                                action_time("spell"), spells.LAND_DELAY + 4 * 0.4
                            )
                            cost += 1.5  # Policy: one spare spell's later damage value.
                        # Policy: moving off the planned flank loses funnel/support value.
                        cost += (
                            2.0
                            * math.hypot(x - main_point[0], y - main_point[1])
                            / WORLD
                        )
                    if seconds > 12.0:
                        continue
                    cost += 0.25 * seconds + 4.0 * loss
                    hits = {}
                    value = -cost
                    for defense in defenses:
                        if band is not None:
                            hit = _band_hit(defense, band, effect_kind, radius)
                        else:
                            hit = defense.edge_distance(*center) <= radius
                        if kind in ("queen", "spear"):
                            hit = defense is target
                        if not hit:
                            continue
                        if kind == "lightning" and defense.key in spells.STORAGES | {
                            "th",
                            "cc",
                        }:
                            continue
                        hit_damage = dealt
                        # Wiki: Giant Arrow, double damage against Air Defenses.
                        if kind == "arrow" and defense.key == "ad":
                            hit_damage *= 2
                        # Deterministic confidence proxy, not sampled/calibrated odds.
                        probability = min(1.0, hit_damage / defense.hp) * (1.0 - loss)
                        hits[defense.id] = hit_damage
                        # Policy: earn opening value from the exposed target.
                        # Interior collateral remains tracked to avoid duplicate spending.
                        if defense is target:
                            value += weights[defense.id] * probability
                    # Stable tile order breaks ties; ranged troops prefer standoff.
                    rank = (value, distance)
                    if best is None or rank > best[0]:
                        best = (rank, x, y, seconds, cost, hits, casts, 1.0 - loss)
                if best is not None:
                    out.append(
                        DefenseSnipe(
                            target,
                            name,
                            kind,
                            best[1],
                            best[2],
                            best[0][0],
                            best[3],
                            best[4],
                            best[5],
                            best[6],
                            best[7],
                        )
                    )
        return out

    def _snipe_lightning_count(self):
        # Playbooks override _have to protect planned and repeating spell casts.
        fallback = getattr(self, "_fallback", False)
        self._fallback = True
        try:
            return self._unreserved_spells("lightning")
        finally:
            self._fallback = fallback

    def opening_deployments(self, battle):
        from .playbook import action_time

        self._snipe_deployed = set()
        self._snipe_assignments = {}
        self._snipe_claimed = set()
        self._snipe_lightning = None
        self._snipe_lightning_at = 0.0
        self._snipe_lightning_left = 0
        self._exposed = self.exposed_defenses(battle) if self.snipe_exposed else []
        if not self._exposed:
            return []
        out = []
        at = 0.0
        remaining = {building.id: building.hp for building in battle.buildings}
        for chosen in self.selected_snipes(battle, self._exposed):
            if chosen.kind == "lightning":
                # Reserve this stack's target alongside hero assignments.
                self._snipe_lightning = chosen
                self._snipe_lightning_at = at
                self._snipe_lightning_left = chosen.casts
            else:
                name = chosen.tool
                self._snipe_assignments[name] = chosen
                self._snipe_deployed.add(name)
                out.append(
                    Deployment(
                        at,
                        name,
                        chosen.x,
                        chosen.y,
                        group="snipe",
                        level=self._level(name),
                        town_hall=self.town_hall,
                    )
                )
                self._log_snipe(
                    (
                        round(at, 1),
                        "deploy:" + chosen.kind,
                        chosen.target.id,
                        chosen.x,
                        chosen.y,
                    )
                )
            for bid, damage in chosen.damage.items():
                remaining[bid] -= damage
                if remaining[bid] <= 0 and chosen.kind != "lightning":
                    self._snipe_claimed.add(bid)
            at += (
                action_time("spell") * chosen.casts
                if chosen.kind == "lightning"
                else action_time("deploy")
            )
        if out:
            self._busy_until = at
        return out

    def selected_snipes(self, battle, exposed):
        """Select an opening without deploying, casting, or drawing RNG."""
        from .playbook import action_time

        # Wiki: Hero Equipment, retaining every tool is the off-mode opening.
        if not self.snipe_exposed or self.snipe_mode == "off":
            return []
        selected = []
        at = 0.0
        # Wiki: Rocket Spear, spend tools only when early removal merits the cost.
        # Policy: best marginal value first; all landing estimates stay within 12 s.
        threshold = 2.0 if self.snipe_mode == "value" else -0.5
        remaining = {building.id: building.hp for building in battle.buildings}
        weights = self._snipe_weights(battle)
        used = set()
        while True:
            candidates = []
            for candidate in exposed:
                if candidate.tool in used or remaining[candidate.target.id] <= 0:
                    continue
                if at + candidate.seconds > 12.0:
                    continue
                # Revalue damage against HP remaining after earlier assignments.
                probability = (
                    min(
                        1.0,
                        candidate.damage[candidate.target.id]
                        / remaining[candidate.target.id],
                    )
                    * candidate.confidence
                )
                value = (
                    weights[candidate.target.id] * probability
                    - candidate.cost
                    - 0.25 * at
                )
                if value >= threshold:
                    candidates.append((value, candidate))
            if not candidates:
                break
            _, chosen = max(candidates, key=lambda item: item[0])
            used.add(chosen.tool)
            selected.append(chosen)
            for bid, damage in chosen.damage.items():
                remaining[bid] -= damage
            at += (
                action_time("spell") * chosen.casts
                if chosen.kind == "lightning"
                else action_time("deploy")
            )
        return selected

    def _log_snipe(self, entry):
        # Wiki: Rocket Spear, activation spends a finite volley.
        self.snipe_log = [*self.snipe_log, entry]

    def opening_actions(self, battle):
        """Spend one spare opening action using the normal spell/ability machinery."""
        from .playbook import action_time

        # output/research/usage/hero-sniping-of-exposed-defenses.md:
        # https://clashofclans.fandom.com/wiki/Rocket_Spear
        # Claims predict the opening, not permanent destruction. Release any
        # survivor when the existing 12-second opening policy ends.
        if battle.t > 12.0:
            self._snipe_claimed.clear()
        if not self.snipe_exposed or self.snipe_mode == "off" or battle.t > 12.0:
            return False
        # Video: docs/VIDEO_MEASUREMENTS.md:31, spells share the player's action clock.
        if battle.t < getattr(self, "_busy_until", 0.0):
            return False
        # Wiki: Lightning Spell, pace the selected stack in its reserved action slots.
        # Deployments and casts keep the value ordering, before hero activation.
        chosen = self._snipe_lightning
        if (
            chosen is not None
            and self._snipe_lightning_left > 0
            and battle.t >= self._snipe_lightning_at
            and battle.building_targetable(chosen.target)
            # Wiki: Rocket Spear, retain spells while a lethal opening is claimed.
            and chosen.target.id not in self._snipe_claimed
        ):
            available = min(self._snipe_lightning_count(), self._snipe_lightning_left)
            hp, _ = self._cluster_state(battle)
            remaining = hp.get(chosen.target.id, 0.0)
            effects = self._cluster_effects("lightning", available) if available else []
            if (
                remaining > 0
                and sum(effect[2] for effect in effects) >= remaining
                and battle.t + spells.LAND_DELAY <= 12.0
            ):
                self._use(battle, "lightning", chosen.target.x, chosen.target.y)
                self._snipe_lightning_left -= 1
                self._snipe_lightning_at = battle.t + action_time("spell")
                self._busy_until = max(
                    getattr(self, "_busy_until", 0.0), self._snipe_lightning_at
                )
                self._log_snipe(
                    (
                        round(battle.t, 1),
                        "lightning",
                        chosen.target.id,
                        chosen.target.x,
                        chosen.target.y,
                    )
                )
                return True
        if battle.t < getattr(self, "_busy_until", 0.0):
            return False
        for unit in battle.attackers:
            chosen = self._snipe_assignments.get(unit.name)
            if (
                chosen is None
                or not unit.alive
                or unit.kind == "hero_clone"
                or unit.ability_used
                or unit.kit is None
            ):
                continue
            target = chosen.target
            # Policy: do not begin an ability whose estimated landing exceeds the opening.
            if battle.t + chosen.seconds > 12.0:
                continue
            if not battle.building_targetable(target) or chosen.kind == "queen":
                continue
            if chosen.kind in ("arrow", "dash"):
                band, effect = self._ability_band(battle, unit)
                if band is None or not _band_hit(target, band, effect[0], effect[1]):
                    continue
                # Wiki: Earthquake Spell, retain the existing paired line-ability cast.
                if not self._fire_aimed(battle, unit):
                    return True
            else:
                nearest = min(
                    heroes._targets(battle, defenses=True),
                    key=lambda b: b.edge_distance(unit.x, unit.y),
                    default=None,
                )
                if nearest is None:
                    continue
                if chosen.kind == "spear":
                    if (
                        nearest is not target
                        or target.edge_distance(unit.x, unit.y) > heroes.SPEAR_RANGE
                    ):
                        continue
                elif target.edge_distance(nearest.x, nearest.y) > heroes._col(
                    "Fireball", unit.kit.lv("Fireball"), "damage radius"
                ):
                    continue
                heroes.activate(battle, unit)
            self._log_snipe(
                (round(battle.t, 1), chosen.kind, target.id, unit.x, unit.y)
            )
            self._busy_until = battle.t + action_time("ability")
            return True
        return False

    def has_offensive_pending(self, battle):
        if self._has_deployable_cc(battle):
            return True
        if (
            self.auto_revive
            and self._have("revive")
            and any(
                not hero.alive and hero.extra.get("revivable")
                for hero in battle.attackers
            )
        ):
            return True
        if any(unit.name != "Healer" for unit in battle.portal_stash):
            return True
        # Wiki: Healer, undeployed non-healing troops keep the battle running.
        if any(name != "Healer" for name, _level, _hp in self.recalled):
            return True
        if any(entry[1] != "Healer" for entry in self._later):
            return True
        if any(
            name != "Healer" and count > 0
            for name, count in self.cleanup + self.breakers
        ):
            return True
        waves = []
        if self._phase == "funnel":
            if (
                self.siege
                or self.push_heroes
                or any(
                    (
                        entry
                        if isinstance(entry, str)
                        else entry.get("name") or entry["type"]
                    )
                    != "Healer"
                    for entry in self.cc_troops
                )
            ):
                return True
            waves.extend(self.main)
        if self._phase in ("funnel", "support"):
            waves.extend(self.support)
        return any(
            name != "Healer" and count > 0
            for wave in waves
            for name, count in wave.units
        )

    def has_pending(self) -> bool:
        return self._phase != "done" or bool(getattr(self, "_battle_portal", None))

    def _has_deployable_cc(self, battle):
        from . import units

        # output/research/usage/cleanup-troops-and-end-of-attack-play.md:
        # spend remaining troops rather than ending with reserves onboard.
        # https://www.youtube.com/watch?v=ahiJ-bgdmSE&t=2125
        return (
            not self.siege
            and not self._cc_released
            and any(entry["name"] != "Healer" for entry in units.onboard_cargo(battle))
        )

    def _drop(
        self,
        battle,
        name,
        x,
        y,
        group,
        jitter=0.0,
        *,
        source="army",
        at=None,
        fixed_point=False,
    ):
        if jitter:
            jitter_x = battle.rng.uniform(-jitter, jitter)
            jitter_y = battle.rng.uniform(-jitter, jitter)
            if not fixed_point:
                x += jitter_x
                y += jitter_y
        # User (TH16 ranked, 2026-10-23): retain the scouted legal Backpack line.
        # Existing jitter draws remain x then y; the selected point needs no scatter.
        if not fixed_point:
            x = min(WORLD - 0.6, max(0.6, x))
            y = min(WORLD - 0.6, max(0.6, y))
        deployment = Deployment(
            battle.t if at is None else at,
            name,
            x,
            y,
            group=group,
            level=self._level(name),
            town_hall=self.town_hall,
            source=source,
        )
        # Video: docs/VIDEO_MEASUREMENTS.md, held troops arrive 0.133 s apart.
        # Jitter draws stay in step order (x then y), when the drop is scheduled.
        if deployment.time > battle.t:
            remaining = battle.deployments[battle._next_deploy :]
            remaining.append(deployment)
            battle.deployments[battle._next_deploy :] = sorted(
                remaining, key=lambda d: d.time
            )
            return None
        return battle.deploy(deployment)

    def _best_entry(self, battle):
        best = None
        for lat in range(-5, 6):
            x, y = edge_point(battle, self.angle, float(lat))
            nearest, nd = None, 1e9
            for b in battle.buildings:
                if b.alive and b.counted:
                    d = b.edge_distance(x, y)
                    if d < nd:
                        nd, nearest = d, b
            if nearest is None:
                continue
            # players drop the push against the base, next to what the funnel
            # opened; a spot far from every building just costs walking time
            score = (
                0.5 * _cheb(nearest.x, nearest.y)
                + 2.0 * max(0.0, nd - 1.5)
                + 0.3 * abs(lat)
            )
            if best is None or score < best[0]:
                best = (score, x, y, lat)
        # holes inside the walls: players drop the push straight in when a
        # gap wider than two tiles sits near the core
        spots = battle.inside_spots()
        for x, y in spots[:: max(1, len(spots) // 40)]:
            nearest, nd = None, 1e9
            for b in battle.buildings:
                if b.alive and b.counted:
                    d = b.edge_distance(x, y)
                    if d < nd:
                        nd, nearest = d, b
            if nearest is None:
                continue
            score = 0.5 * _cheb(nearest.x, nearest.y) + 2.0 * max(0.0, nd - 1.5)
            if best is None or score < best[0]:
                best = (score, x, y, 0.0)
        if self.P("deep_drop") > 0.5:
            # any legal tile on the attack side (within ~40 degrees), corridors
            # and open pockets included: same scoring, so the push lands deep
            # when a corridor reaches toward the core
            for x, y in self._sector_tiles(battle, self.angle, 0.7)[::3]:
                nearest, nd = None, 1e9
                for b in battle.buildings:
                    if b.alive and b.counted:
                        d = b.edge_distance(x, y)
                        if d < nd:
                            nd, nearest = d, b
                if nearest is None:
                    continue
                score = 0.5 * _cheb(nearest.x, nearest.y) + 2.0 * max(0.0, nd - 1.5)
                if best is None or score < best[0]:
                    best = (score, x, y, 0.0)
        self._entry_lat = best[3] if best else 0.0
        return (best[1], best[2]) if best else edge_point(battle, self.angle, 0.0)

    @staticmethod
    def _sector_tiles(battle, angle, half_width):
        out = []
        for x, y in battle.deploy_tiles():
            a = math.atan2(y - CENTER, x - CENTER)
            if abs((a - angle + math.pi) % (2 * math.pi) - math.pi) <= half_width:
                out.append((x, y))
        return out

    def _deep_charge_point(self, battle, default):
        """A charging hero drops at the legal tile on its side closest to the
        most dangerous defense there (e.g. right beside the Monolith)."""
        ang = math.atan2(default[1] - CENTER, default[0] - CENTER)
        defs = [
            b
            for b in battle.buildings
            if b.alive
            and b.weapon is not None
            and THREAT.get(b.key, 0) >= 5
            and abs(
                (math.atan2(b.y - CENTER, b.x - CENTER) - ang + math.pi) % (2 * math.pi)
                - math.pi
            )
            <= 0.8
        ]
        tiles = self._sector_tiles(battle, ang, 0.6)
        if not defs or not tiles:
            return default
        tgt = max(
            defs,
            key=lambda b: (
                THREAT.get(b.key, 0),
                -math.hypot(b.x - default[0], b.y - default[1]),
            ),
        )
        return min(tiles, key=lambda p: math.hypot(p[0] - tgt.x, p[1] - tgt.y))

    def _funnel_progress(self, battle):
        ex, ey = edge_point(battle, self.angle, 0.0)
        return sum(
            1
            for b in battle.buildings
            if not b.alive and b.counted and math.hypot(b.x - ex, b.y - ey) < 10
        )

    def _launch_main(self, battle):
        self._entry = self._best_entry(battle)
        ex, ey = self._entry
        if self.siege:
            # Wiki: Flame Flinger, an opening siege retains its cargo until it opens.
            if self.siege not in self._snipe_deployed:
                self._drop(battle, self.siege, ex, ey, "main")
        elif self.cc_troops and not self._cc_released:
            from . import units

            units.release_cc_at(battle, ex, ey, "main")
        e2 = (
            edge_point(battle, self.angle + self.split_main, 0.0)
            if self.split_main > 0.05
            else None
        )
        k = 0
        tank_k = 0
        damage_k = 0
        lead = self.P("tank_lead")
        # Video: docs/VIDEO_MEASUREMENTS.md:30 -> each sequence uses 0.133 s per troop.
        # Attacker policy: tanks start now; damage starts tank_lead seconds later.
        # Jitter draws keep wave/unit order (x then y) when scheduling each troop.
        for wave in self.main:
            for name, c in wave.units:
                for _ in range(c):
                    px, py = (e2[0], e2[1]) if e2 is not None and k % 2 else (ex, ey)
                    if lead > 0.3 and name in TANKS:
                        at = battle.t + tank_k * 0.133
                        tank_k += 1
                    elif lead > 0.3:
                        at = battle.t + lead + damage_k * 0.133
                        damage_k += 1
                    else:
                        at = battle.t + k * 0.133
                    self._drop(battle, name, px, py, "main", jitter=wave.spread, at=at)
                    k += 1
        for name in self.push_heroes:
            if name in self._snipe_deployed:
                continue
            self._drop(battle, name, ex, ey, "main", jitter=0.5)
        if self.charge_hero and battle.portal_stash:
            heroes.portal_redeploy(battle, ex, ey)  # the recalled charge joins the push
        self._main_at = battle.t
        self._phase = "support"

    def _snipe_point(self, battle, b):
        """Legal deploy spot closest to building b."""
        # the no-spawn zone shrinks as buildings fall, and holes inside the
        # walls count too, so recompute the candidate spots each time
        if getattr(self, "_snipe_t", None) != battle.t:
            self._snipe_pts = [
                edge_point(battle, 2 * math.pi * k / 64, 0.0) for k in range(64)
            ] + battle.inside_spots()
            self._snipe_t = battle.t
        return min(self._snipe_pts, key=lambda p: math.hypot(p[0] - b.x, p[1] - b.y))

    def portal_point(self, battle):
        """Redeploy where the most buildings are still standing."""
        best, bs = None, -1
        for k in range(16):
            x, y = edge_point(battle, self.angle + 2 * math.pi * k / 16, 0.0)
            s = sum(
                1
                for b in battle.buildings
                if b.alive and b.counted and math.hypot(b.x - x, b.y - y) < 11
            )
            if s > bs:
                best, bs = (x, y), s
        return best

    def on_tick(self, battle):
        t = battle.t
        opening = self.opening_actions(battle)
        if t >= getattr(self, "_busy_until", 0.0):
            self.revive_knocked_out(battle, single_cast=True)
        self._battle_portal = battle.portal_stash
        if self._later:
            due = [d for d in self._later if d[0] <= t]
            self._later = [d for d in self._later if d[0] > t]
            for _, name, x, y, group, jit in due:
                self._drop(battle, name, x, y, group, jitter=jit)
        hold = (
            self.charge_hero and self._phase == "funnel" and not self.recall_funnel
        )  # a recalled charge comes back with the main push
        if (
            battle.portal_stash
            and t >= battle.portal_ready_at
            and self.recall_funnel
            and self.charge_hero
            and self._phase == "funnel"
        ):
            x, y = edge_point(
                battle,
                self.angle,
                -self.charge_lat if abs(self.charge_lat) > 1 else 8.0,
            )
            heroes.portal_redeploy(battle, x, y)  # recall funnel: the other flank
            hold = True
        if battle.portal_stash and t >= battle.portal_ready_at and not hold:
            x, y = self.portal_point(battle)
            heroes.portal_redeploy(battle, x, y)
        if self._phase == "funnel":
            if (
                not opening
                and t >= getattr(self, "_busy_until", 0.0)
                and not self._zap_done
                and self.zap_ad != (0, 0)
            ):
                self._zap(battle, single_cast=True)
            if t >= self.main_max or (
                t >= self.main_min
                and self._funnel_progress(battle) >= self.P("commit_progress")
            ):
                self._launch_main(battle)
        elif self._phase == "support" and t >= self._main_at + 2.0:
            ex, ey = self._entry
            # Video: docs/VIDEO_MEASUREMENTS.md:30 -> support uses the same queue.
            k = 0
            for wave in self.support:
                for name, c in wave.units:
                    for _ in range(c):
                        self._drop(
                            battle,
                            name,
                            ex,
                            ey,
                            "main",
                            jitter=wave.spread,
                            at=t + k * 0.133,
                        )
                        k += 1
            self._phase = "push"
        elif self._phase == "push" and t >= self._main_at + 25.0:
            # cleanup: each spare troop goes to the legal spot nearest a
            # different building far from the push, so the far side does not
            # run the clock out (players snipe the outer ring early)
            names = [n for n, c in self.cleanup for _ in range(c)] + [
                n for n, _lvl, _h in self.recalled
            ]
            # Wiki: Healer, only undeployed reserves count toward battle survival.
            self.cleanup.clear()
            self.recalled.clear()
            army = self.main_units(battle)
            cx, cy = self.centroid(army) if army else (CENTER, CENTER)
            far = sorted(
                (b for b in battle.buildings if b.alive and b.counted),
                key=lambda b: -math.hypot(b.x - cx, b.y - cy),
            )
            # Video: docs/VIDEO_MEASUREMENTS.md:30, held troops are 0.133 s
            # apart; slot-switch time remains action_time's policy assumption.
            # https://www.youtube.com/watch?v=w4RTiOi6C_w&t=88
            from .playbook import PACE_TAP, action_time

            started = max(t, getattr(self, "_busy_until", 0.0))
            tap = PACE_TAP * float(os.environ.get("BASELAB_PACE", "1.0"))
            for k, name in enumerate(names):
                if not far:
                    x, y = edge_point(battle, self.angle + math.pi, 0.0)
                else:
                    x, y = self._snipe_point(
                        battle, far[k % min(len(far), max(1, len(names) // 2 + 1))]
                    )
                self._drop(
                    battle, name, x, y, "cleanup", jitter=0.3, at=started + k * tap
                )
            if names:
                self._busy_until = started + action_time("deploy", len(names))
            self._phase = "done"
        if not self._lured and self.P("lure_time") >= 0 and t >= self.P("lure_time"):
            self._lured = True
            cc = next((b for b in battle.buildings if b.key == "cc" and b.alive), None)
            name = self._spare_troop() if cc is not None else None
            if name is not None:
                x, y = self._snipe_point_xy(battle, cc.x, cc.y)
                self._drop(battle, name, x, y, "cleanup", jitter=0.2)
                self._cast_log.append((round(t, 1), "lure"))
        if t >= self._next_brain and t >= getattr(self, "_busy_until", 0.0):
            self._next_brain = t + 0.5
            self.hero_abilities(battle)
            if self.charge_hero and self._last("recall_charge") < 0:
                # the charge is managed until the hero is recalled (or dies),
                # also after the main push has gone in
                charge = self.main_units(battle, "charge")
                if charge:
                    self._charge_spells(battle, charge)
                    if self._phase == "funnel":
                        self.generic_spells(battle, charge, single_cast=True)
            if self._phase in ("support", "push", "done"):
                self.generic_spells(battle, self.main_units(battle), single_cast=True)

    # ---------------------------------------------------------- abilities
    def hero_abilities(self, battle):
        """Players fire abilities to save a hero or at a key moment."""
        t = battle.t
        for u in battle.attackers:
            # Video: docs/VIDEO_MEASUREMENTS.md:31, pairing spends one paced action.
            if t < getattr(self, "_busy_until", 0.0):
                break
            if not u.alive or not u.is_hero or u.kit is None or u.ability_used:
                continue
            frac = u.hp / max(1.0, u.max_hp)
            engaged = u.target is not None and t - u.spawned_at > 2.0
            if u.name == "Minion Prince" and u.kit.has("Portal Pendant"):
                # pull the push out of a dead or losing spot and drop it fresh
                near = [
                    a
                    for a in battle.attackers_near(u.x, u.y, 7.0)
                    if not a.is_hero and a.kind != "pet" and a.name != "Totem"
                ]
                if near:
                    cx, cy = self.centroid(near)
                    work = any(
                        b.alive and b.counted and b.edge_distance(cx, cy) < 7
                        for b in battle.buildings
                    )
                    hurt = sum(a.hp / a.max_hp for a in near) / len(near)
                    if (
                        len(near) >= 6
                        and (not work or hurt < 0.45)
                        and t - u.spawned_at > 15.0
                    ):
                        heroes.activate(battle, u)
                elif frac < 0.35:
                    heroes.activate(battle, u)
            elif u.name == "Grand Warden":
                near = [
                    a
                    for a in battle.attackers_near(u.x, u.y, 7.0)
                    if a.name != "Totem" and not a.is_hero
                ]
                hurt = sum(1 for a in near if a.hp < 0.55 * a.max_hp)
                if (
                    len(near) >= 5
                    and hurt >= int(len(near) * self.P("warden_hurt") + 1e-9)
                    or frac < self.P("warden_hp")
                ):
                    heroes.activate(battle, u)
                elif u.kit.has("Fireball"):
                    # Wiki: Fireball, time the nearest-defense blast for cluster value.
                    self._cluster_ability(battle, u)
            elif u.name == "Royal Champion" and (
                u.kit.has("Rocket Spear") or u.kit.has("Seeking Shield")
            ):
                # Wiki: Rocket Spear/Seeking Shield, snipe several defenses early.
                self._cluster_ability(battle, u, force=frac < self.P("hero_hp"))
            elif u.kit.has("Giant Arrow"):
                # Wiki: Giant Arrow, time the actual firing line through defenses.
                self._line_ability(battle, u, force=frac < self.P("hero_hp"))
            elif u.name == "Dragon Duke":
                if engaged and (
                    frac < self.P("duke_hp") or getattr(u.target, "is_defense", False)
                ):
                    self._fire_aimed(battle, u)
            elif frac < self.P("hero_hp") or (
                engaged and t - u.spawned_at > self.P("hero_time")
            ):
                heroes.activate(battle, u)

    def _aim(self, battle, u, kind):
        """Score only the ability's real, automatically chosen direction."""
        band, effect = self._ability_band(battle, u)
        if band is None:
            return False
        current = defense_cluster(battle, [effect], points=[band[:2]], band=band)
        # User (TH16 ranked, 2026-10-23): several defenses make a useful shot.
        return current is not None and current[2] >= self.P(kind + "_threat")

    def _ability_band(self, battle, u):
        # Wiki: Giant Arrow/Rocket Backpack, score the same damage as activation.
        if u.kit.has("Giant Arrow"):
            target = u.target
            if target is None or not target.alive:
                return None, None
            if target in battle.buildings and not battle.building_targetable(target):
                return None, None
            if target in battle.defenders and not target.targetable(battle.t):
                return None, None
            dx, dy, length, radius = heroes.arrow_geometry(u, target)
            damage = float(
                heroes._ability_data(
                    "Giant Arrow",
                    u.kit.lv("Giant Arrow"),
                    "ArcherQueenPierceProjectile",
                )["Damage"]
            )
            kind = "arrow"
        elif u.kit.has("Rocket Backpack"):
            dx, dy, length, radius = heroes.dash_geometry(u.x, u.y, u.extra["facing"])
            damage = float(
                heroes._ability_data(
                    "Rocket Backpack",
                    u.kit.lv("Rocket Backpack"),
                    "DragonDukeDeadlyDashMapCenter",
                )["ActAsPenetratingDamage"]
            )
            kind = "dash"
        else:
            return None, None
        return (u.x, u.y, dx, dy, length), (kind, radius, damage)

    def _line_ability(self, battle, u, *, force=False, deadline=None):
        # Policy: at most 10 s from first ready; a playbook's own window is tighter.
        since = u.extra.setdefault("line_ability_since", battle.t)
        limit = since + 10.0 if deadline is None else min(since + 10.0, deadline)
        ready = u.kit.has("Rocket Backpack") or self._aim(battle, u, "arrow")
        if force or ready or battle.t >= limit:
            return self._fire_aimed(battle, u, deadline=limit)
        return False

    def _fire_aimed(self, battle, u, *, deadline=None):
        """Activate once the hero's current firing line is useful."""
        # Wiki: Giant Arrow, the player times activation, not its direction.
        if self._pair_line_quake(battle, u, deadline=deadline):
            return False
        heroes.activate(battle, u)
        return True

    def _pair_line_quake(self, battle, u, *, deadline=None):
        # Wiki: Earthquake Spell, weaken buildings before the piercing ability hits.
        until = u.extra.get("line_quake_until")
        if until is not None:
            return battle.t < until and (deadline is None or battle.t < deadline)
        # Match the existing playbook spell action; generic casts use the same pace.
        from .playbook import action_time

        pace = action_time("spell")
        # game data v18.200.9: Earthquake.NumberOfHits=5, TimeBetweenHitsMS=400.
        wait = max(pace, spells.LAND_DELAY + 4 * 0.4)
        if deadline is not None and battle.t + wait > deadline:
            return False
        fallback = getattr(self, "_fallback", False)
        self._fallback = True
        try:
            spare = self._spare_quakes(battle)
        finally:
            self._fallback = fallback
        if not spare:
            return False
        band, effect = self._ability_band(battle, u)
        if band is None:
            return False
        x, y, dx, dy, length = band
        # Wiki: Earthquake Spell, pair damage along the actual ability band.
        # Policy: at most 12 projected defenses plus 12 midpoint candidates.
        targets = nlargest(
            12,
            (
                b
                for b in battle.buildings
                if (
                    b.is_defense
                    and battle.building_targetable(b)
                    and _band_hit(b, band, effect[0], effect[1])
                )
            ),
            key=lambda b: THREAT.get(b.key, 1),
        )
        points = []
        for b in targets:
            along = min(length, max(0.0, (b.x - x) * dx + (b.y - y) * dy))
            points.append((x + dx * along, y + dy * along))
        # User observation: quake a point on the selected line/band, including clumps.
        centers = list(points)
        for index, first in enumerate(centers):
            for second in centers[index + 1 :]:
                if len(points) >= 24:
                    break
                points.append(((first[0] + second[0]) / 2, (first[1] + second[1]) / 2))
        hp, eq_hits = self._cluster_state(battle)
        cluster = defense_cluster(
            battle,
            self._cluster_effects("eq", 1) + [effect],
            hp=hp,
            eq_hits=eq_hits,
            points=points,
            band=band,
        )
        if cluster is None:
            return False
        self._use(battle, "eq", cluster[0], cluster[1])
        u.extra["line_quake_until"] = battle.t + wait
        # Video: docs/VIDEO_MEASUREMENTS.md:31, a spell is a separate player action.
        self._busy_until = max(getattr(self, "_busy_until", 0.0), battle.t + pace)
        return True

    def _cluster_ability(self, battle, u, *, force=False):
        """Time automatically aimed equipment for a valuable nearby cluster."""
        # Wiki: Fireball/Rocket Spear, wait for automatic aim, within a bounded hold.
        since = u.extra.setdefault("cluster_ability_since", battle.t)
        if force or battle.t - since >= 10.0:
            heroes.activate(battle, u)
            return True
        # Policy: retry held aim at most twice a second, not on every engine tick.
        if battle.t < u.extra.get("cluster_ability_check_at", -1.0):
            return False
        u.extra["cluster_ability_check_at"] = battle.t + 0.5
        if u.kit.has("Fireball"):
            # game data v18.200.9: GrandWardenFireball L27.Damage=4100,
            # DamageRadius=600 -> the equipped Fireball's damage and tile radius.
            level = u.kit.lv("Fireball")
            radius = heroes._col("Fireball", level, "damage radius")
            damage = heroes._col("Fireball", level, "projectile damage")
            # Policy: compare nearby clusters the Warden can approach while fighting.
            reach = u.range + radius
        elif u.name == "Royal Champion":
            damage = 0.0
            if u.kit.has("Rocket Spear"):
                # Wiki: Rocket Spear, 10-tile range; each shot adds equipment damage.
                damage += (
                    u.dmg
                    + heroes._col(
                        "Rocket Spear",
                        u.kit.lv("Rocket Spear"),
                        "damage per shot increase",
                    )
                    * battle.atk_hero_mult
                )
            if u.kit.has("Seeking Shield"):
                # Wiki: Seeking Shield, four defense-prioritized hits, unlimited travel.
                damage += (
                    heroes._col(
                        "Seeking Shield",
                        u.kit.lv("Seeking Shield"),
                        "projectile damage",
                    )
                    * battle.atk_hero_mult
                )
            # Policy: value successive targets in the next 6-tile neighborhood.
            radius = 6.0
            reach = (
                heroes.SPEAR_RANGE if u.kit.has("Rocket Spear") else u.range + radius
            )
        else:
            return False
        defenses = heroes._targets(battle, defenses=True)
        if not defenses:
            # Wiki: Fireball/Seeking Shield, fall back to other buildings for cleanup.
            heroes.activate(battle, u)
            return True
        nearest = min(defenses, key=lambda b: heroes._distance(b, u.x, u.y))
        effects = [("damage", radius, damage)]
        best = defense_cluster(battle, effects, center=(u.x, u.y), reach=reach)
        current = defense_cluster(battle, effects, points=[(nearest.x, nearest.y)])
        # Wiki: Fireball/Rocket Spear, the nearest defense controls actual aim.
        # Seeking Shield's nearest-first bounces also remain automatic.
        ready = (
            best is not None
            and current is not None
            and current[2] >= best[2]
            and nearest.edge_distance(u.x, u.y) <= reach
        )
        # Policy: retain the playbook's 10 s aim wait; low HP still forces activation.
        if force or ready or battle.t - since >= 10.0:
            heroes.activate(battle, u)
            return True
        return False

    # -------------------------------------------------------------- spells
    def _zap(self, battle, *, single_cast=False, reserved=()):
        if self._zap_done:
            return
        if not hasattr(self, "_zap_left"):
            self._zap_left = list(self.zap_ad)
        ex, ey = edge_point(battle, self.angle, 0.0)
        # Wiki: Rocket Spear, a claimed lethal hit already pays for this defense.
        claimed = getattr(self, "_snipe_claimed", ())
        ads = sorted(
            # Wiki: Giant Arrow, preserve the playbook's later Air Defense targets.
            (
                b
                for b in battle.buildings
                if b.alive
                and b.key == "ad"
                and b.id not in reserved
                and b.id not in claimed
            ),
            key=lambda b: math.hypot(b.x - ex, b.y - ey),
        )
        if not ads:
            self._zap_done = not reserved
            return
        hp = {b.id: b.hp for b in ads}
        eq_hits = {b.id: b.eq_hits for b in ads}
        cast_hits = {}

        def account(field, hits):
            for b in ads:
                if b.edge_distance(field.x, field.y) > field.radius:
                    continue
                if field.kind == "lightning":
                    hp[b.id] -= field.value
                else:
                    # Wiki: Earthquake Spell, successive casts deal 1, 1/3, 1/5.
                    key = (id(field), b.id)
                    if key not in cast_hits:
                        n = field.extra.get("hits", {}).get(("building", b.id))
                        if n is None:
                            eq_hits[b.id] += 1
                            n = eq_hits[b.id]
                        cast_hits[key] = n
                    hp[b.id] -= b.max_hp * field.value * hits / (2 * cast_hits[key] - 1)

        # game data v18.200.9: Lightning L11.Damage=640;
        # Earthquake L7.BuildingDamagePermil=58, NumberOfHits=5 -> 29% total.
        # Include falling bottles and unresolved quake hits without changing HP.
        for pending in battle.pending:
            field = pending.extra.get("quake")
            if field is not None and field.kind == "quake":
                account(field, 1)
        for field in battle.fields:
            if field.kind in ("lightning", "quake"):
                account(field, 5 if field.kind == "quake" else 1)
        # Wiki: Lightning_Spell_Home_Village, use enough casts to destroy each
        # Air Defense, then spend the remaining spells on the next defense.
        while any(self._zap_left):
            target = next((b for b in ads if hp[b.id] > 1e-9), None)
            if target is None:
                break
            index, kind = (1, "eq") if self._zap_left[1] else (0, "lightning")
            if not self._have(kind):
                self._zap_left[index] = 0
                continue
            if reserved:
                # Wiki: Lightning Spell/Home Village, its area damage also hits
                # nearby buildings; keep the reserved hero targets out of it.
                stock = next(
                    s
                    for s in self._spell_stock
                    if s.name == SPELL_NAMES[kind] and s.remaining > 0
                )
                radius = spells._radius(stock.name, self._spell_level(stock), 0.0)
                target = next(
                    (
                        b
                        for b in ads
                        if hp[b.id] > 1e-9
                        and all(
                            r.edge_distance(b.x, b.y) > radius
                            for r in battle.buildings
                            if r.alive and r.id in reserved
                        )
                    ),
                    None,
                )
                if target is None:
                    break
            field = self._use(battle, kind, target.x, target.y)
            self._zap_left[index] -= 1
            account(field, 5 if kind == "eq" else 1)
            if single_cast:
                self._zap_done = not any(self._zap_left) or (
                    not reserved and all(hp[b.id] <= 1e-9 for b in ads)
                )
                return
        self._zap_done = not any(self._zap_left) or not reserved

    def _have(self, kind):
        return self.spells.get(kind, 0) > 0

    def _use(self, battle, kind, x, y):
        from .playbook import action_time

        field = spells.cast(battle, SPELL_NAMES[kind], x, y)
        # Video: docs/VIDEO_MEASUREMENTS.md:31; one spell action at a time.
        # https://www.youtube.com/watch?v=w4RTiOi6C_w&t=52
        self._busy_until = max(
            getattr(self, "_busy_until", 0.0), battle.t + action_time("spell")
        )
        return field

    def _last(self, kind):
        for t, k in reversed(self._cast_log):
            if k == kind:
                return t
        return -100.0

    def main_units(self, battle, group="main"):
        return [
            u
            for u in battle.attackers
            if u.alive and u.group == group and u.name != "Totem" and u.kind != "pet"
        ]

    @staticmethod
    def centroid(units):
        w = sum(max(1, u.housing) for u in units)
        return (
            sum(u.x * max(1, u.housing) for u in units) / w,
            sum(u.y * max(1, u.housing) for u in units) / w,
        )

    @staticmethod
    def threats_near(battle, x, y, r):
        out = []
        t = battle.t
        # Wiki: Rocket Spear, direct spell support skips defenses already claimed lethal.
        claimed = getattr(battle.plan, "_snipe_claimed", ())
        for b in battle.buildings:
            if not b.alive or b.weapon is None or b.disabled(t) or b.id in claimed:
                continue
            d = math.hypot(b.x - x, b.y - y)
            if d <= r:
                out.append((b, d))
        return out

    def _totem_covered(self, battle, x, y):
        # game data v18.200.9: Totem.Radius=500 -> 5 tiles at every level.
        level = spells._lvl(battle, "Totem Spell", None)
        radius = spells._radius("Totem Spell", level, 5.0)
        if any(
            u.alive and u.name == "Totem" and math.hypot(u.x - x, u.y - y) <= radius
            for u in battle.attackers
        ):
            return True
        # User (TH16 ranked, 2026-10-23): never drop three on one spot.
        # Remember casts for 5 s (policy), including landing and early deaths.
        return any(
            battle.t - t <= 5.0 and math.hypot(tx - x, ty - y) <= radius
            for t, tx, ty in self._totem_casts
        )

    def _totem_targets(self, battle, threats):
        # User (TH16 ranked, 2026-10-23): spread casts over uncovered threats.
        level = spells._lvl(battle, "Totem Spell", None)
        radius = spells._radius("Totem Spell", level, 5.0)
        uncovered = [
            (b, d)
            for b, d in threats
            if battle.building_targetable(b)
            and not self._totem_covered(battle, b.x, b.y)
        ]
        return [
            (
                b,
                d,
                sum(
                    THREAT.get(other.key, 1)
                    for other, _ in uncovered
                    if math.hypot(other.x - b.x, other.y - b.y) <= radius
                ),
            )
            for b, d in uncovered
        ]

    def _breach(self, battle, units, *, single_cast=False):
        """Open walls where several push troops are stuck: Wall Breakers
        first, then Earthquake x4 / Jump if carried."""
        stuck = [u for u in units if u.wall_target is not None and u.wall_target.alive]
        if len(stuck) < 2:
            return
        w = stuck[0].wall_target
        if (
            sum(
                1
                for v in stuck
                if abs(v.wall_target.x - w.x) + abs(v.wall_target.y - w.y) <= 3
            )
            < 2
        ):
            return
        cx, cy = self.centroid(stuck)
        # Wiki: Wall Breaker, sacrifices itself; fallback spends the same army.
        inventory = getattr(self, "inventory", None)
        for b in self.breakers:
            left = b[1] if inventory is None else inventory.get(b[0], 0)
            if left > 0:
                n = min(left, 3)
                b[1] = left - n
                if inventory is not None:
                    inventory[b[0]] = left - n
                for _ in range(n):
                    self._drop(battle, b[0], cx, cy, "breach", jitter=0.4)
                self._cast_log.append((round(battle.t, 1), "breach"))
                return
        if self._have("jump"):
            self._use(battle, "jump", w.x, w.y)
            self._cast_log.append((round(battle.t, 1), "breach"))
        elif self._unreserved_spells("eq") >= 4:
            # Video: docs/VIDEO_MEASUREMENTS.md:31, spell drops have nonzero spacing.
            if single_cast:
                self._fallback_quakes = [(w.x, w.y)] * 3
            for _ in range(1 if single_cast else 4):
                self._use(battle, "eq", w.x, w.y)
            self._cast_log.append((round(battle.t, 1), "breach"))

    def _unreserved_spells(self, kind):
        # Policy: retain the playbook's planned casts before spending spare spells.
        if not self._have(kind):
            return 0
        available = self.spells.get(kind, 0)
        if getattr(self, "_fallback", False):
            available -= sum(
                1
                for st in getattr(self, "steps", [])
                if st["action"] == "spell"
                and st.get("what") == SPELL_NAMES[kind]
                and st["id"] not in self._done
                and st["id"] not in self._cancelled
            )
        return max(0, available)

    def _cluster_effects(self, kind, count):
        effects = []
        for stock in self._spell_stock:
            if stock.name != SPELL_NAMES[kind] or stock.remaining <= 0:
                continue
            level = self._spell_level(stock)
            radius = spells._radius(stock.name, level, 0.0)
            # game data v18.200.9: Lightning L11.Damage=640 -> damage per cast.
            value = stats.get(stock.name, level, "damage", "Damage")
            if kind == "eq":
                # game data v18.200.9: Earthquake.BuildingDamagePermil=58,
                # NumberOfHits=5 -> 29% of maximum building HP per first cast.
                value = stats.get(stock.name, level, "Building Damage %") / 100.0
            take = min(count, stock.remaining)
            effects.extend([("quake" if kind == "eq" else kind, radius, value)] * take)
            count -= take
            if count == 0:
                break
        return effects

    def _cluster_state(self, battle):
        # Wiki: Lightning/Earthquake Spell, count damage still falling or pulsing.
        hp = {b.id: b.hp for b in battle.buildings if b.alive}
        eq_hits = {b.id: b.eq_hits for b in battle.buildings if b.alive}
        casts = {}

        def account(field, hits):
            for b in battle.buildings:
                if not b.alive or b.edge_distance(field.x, field.y) > field.radius:
                    continue
                if field.kind == "lightning":
                    if b.key not in spells.STORAGES | {"th", "cc"}:
                        hp[b.id] -= field.value
                elif b.counted and b.key not in spells.STORAGES:
                    key = (id(field), b.id)
                    if key not in casts:
                        n = field.extra.get("hits", {}).get(("building", b.id))
                        if n is None:
                            eq_hits[b.id] += 1
                            n = eq_hits[b.id]
                        casts[key] = n
                    hp[b.id] -= b.max_hp * field.value * hits / (2 * casts[key] - 1)

        for pending in battle.pending:
            field = pending.extra.get("quake")
            if field is not None and field.kind == "quake":
                account(field, 1)
        for field in battle.fields:
            if field.kind in ("lightning", "quake"):
                account(field, 5 if field.kind == "quake" else 1)
        # Wiki: Rocket Spear, reserve defenses with lethal opening damage in flight.
        for bid in getattr(self, "_snipe_claimed", ()):
            if bid in hp:
                hp[bid] = 0.0
        return hp, eq_hits

    def _spare_quakes(self, battle):
        available = self._unreserved_spells("eq")
        # Wiki: Earthquake Spell, four casts open walls; keep that breach intact.
        reserved = len(getattr(self, "_fallback_quakes", []))
        if (
            self.ground
            and not self._have("jump")
            and any(w.alive for w in battle.walls.values())
        ):
            if self.spells.get("eq", 0) >= 4:
                reserved = max(reserved, 4)
        if self.P("eq_core_dist") > 2 and self._last("eq_core") < 0:
            reserved = max(reserved, int(round(self.P("eq_core_n"))))
        return max(0, available - reserved)

    def _hold_line_quake(self, battle):
        # User (TH16 ranked, 2026-10-23): save one spare quake for Arrow/Backpack.
        for name, equipment in (
            ("Archer Queen", "Giant Arrow"),
            ("Dragon Duke", "Rocket Backpack"),
        ):
            deployed = [
                u for u in battle.attackers if u.name == name and u.kind != "hero_clone"
            ]
            if deployed:
                if any(
                    u.alive
                    and not u.ability_used
                    and u.kit is not None
                    and u.kit.has(equipment)
                    and "line_quake_until" not in u.extra
                    for u in deployed
                ):
                    return True
                continue
            loadout = self.loadouts.get(name) or heroes.DEFAULT_LOADOUTS[name]
            if equipment not in loadout.equipment or (
                self.account_equipment and equipment not in self.equipment_levels
            ):
                continue
            if hasattr(self, "steps"):
                pending = any(
                    s["action"] == "deploy"
                    and s.get("what") == name
                    and s["id"] not in self._done
                    and s["id"] not in self._cancelled
                    for s in self.steps
                )
            else:
                pending = (
                    name in self.push_heroes
                    or any(hero == name for hero, _ in self.funnel_heroes)
                    or name == self.charge_hero
                )
            if pending:
                return True
        return False

    def _spare_lightning(self, battle):
        # User (TH16 ranked, 2026-10-23): combine damage spells on clumped defenses.
        queued = getattr(self, "_cluster_casts", [])
        if queued:
            kind, x, y = queued.pop(0)
            # Wiki: Rocket Spear, a later lethal claim can make a queued zap redundant.
            effects = self._cluster_effects(kind, 1) if self._have(kind) else []
            if (
                effects
                and defense_cluster(battle, effects, points=[(x, y)]) is not None
            ):
                self._use(battle, kind, x, y)
                return True
            queued.clear()
        available = self._unreserved_spells("lightning")
        if not available:
            return False
        hp, eq_hits = self._cluster_state(battle)
        if any(b.alive and b.key == "ad" and hp[b.id] > 1e-9 for b in battle.buildings):
            return False
        effects = self._cluster_effects("lightning", available)
        combo = None
        if available >= 2 and self._spare_quakes(battle) > int(
            self._hold_line_quake(battle)
        ):
            quake = self._cluster_effects("eq", 1)
            for count in (2, 3):
                if count > available:
                    break
                # Wiki: Lightning Spell/Home Village, ZapQuake removes grouped defenses.
                candidate = defense_cluster(
                    battle,
                    quake + effects[:count],
                    hp=hp,
                    eq_hits=eq_hits,
                    min_kills=2,
                )
                if candidate is not None and (
                    combo is None or candidate[2] > combo[0][2]
                ):
                    combo = (candidate, count)
        if combo is not None:
            cluster, count = combo
            x, y = cluster[:2]
            # Quake first, then Lightning; one cast per existing player action.
            self._cluster_casts = [("lightning", x, y)] * count
            self._use(battle, "eq", x, y)
            return True
        cluster = defense_cluster(battle, effects, hp=hp, eq_hits=eq_hits)
        if cluster is None:
            return False
        self._use(battle, "lightning", cluster[0], cluster[1])
        return True

    def _spare_quake(self, battle):
        # Wiki: Earthquake Spell, weaken several buildings before hero abilities.
        available = self._spare_quakes(battle)
        if available <= int(self._hold_line_quake(battle)):
            return False
        hp, eq_hits = self._cluster_state(battle)
        cluster = defense_cluster(
            battle, self._cluster_effects("eq", available), hp=hp, eq_hits=eq_hits
        )
        if cluster is None:
            return False
        self._use(battle, "eq", cluster[0], cluster[1])
        return True

    def _cargo_support(self, battle):
        # Wiki: Battle Blimp, Super Archer/Wizard invisibility and Clone Balloon
        # strategies support released cargo. Other payloads keep main-group casts.
        if not self.siege or not self.cc_troops:
            return None
        names = {
            entry if isinstance(entry, str) else entry.get("name") or entry["type"]
            for entry in self.cc_troops
        }
        supported = names & {"Super Archer", "Super Wizard"}
        if self.siege == "Battle Blimp" and (
            self._spells0.get("clone", 0) or self._cc_spells0.get("clone", 0)
        ):
            supported.update(names & {"Balloon"})
        for st in getattr(self, "steps", []):
            if st["action"] == "spell" and st.get("what") in (
                "Clone Spell",
                "Invisibility Spell",
            ):
                at = st.get("at", "")
                if at in ("group:cargo", "group:cc"):
                    supported.update(names)
                elif at.startswith(("unit:", "unit_ahead:")):
                    supported.update(names & {at.split(":", 1)[1]})
        if not supported:
            return None
        delivered = [
            u
            for u in battle.attackers
            if u.name in supported and u.extra.get("deployment_source") == "siege"
        ]
        groups = {u.group for u in delivered}
        cargo = [
            u
            for u in battle.attackers
            if u.alive
            and u.name in supported
            and (
                u.extra.get("deployment_source") == "siege"
                or (u.extra.get("clone") and u.group in groups)
            )
        ]
        if cargo:
            return cargo
        # Wiki: Battle Blimp, Clone/Invisibility support the surviving payload.
        # Once it is lost, remaining spells can support the main army instead.
        if delivered or self._cc_released:
            return None
        carriers = [u for u in battle.attackers if u.name == self.siege]
        if carriers and not any(u.alive for u in carriers):
            return None
        # Attacker policy assumption: hold at most 30 s from the first generic
        # support check if the siege never releases; this is not a game timer.
        if not hasattr(self, "_cargo_wait_since"):
            self._cargo_wait_since = battle.t
        return [] if battle.t - self._cargo_wait_since < 30.0 else None

    def generic_spells(self, battle, units, *, single_cast=False):
        # Video: docs/VIDEO_MEASUREMENTS.md:31, finish the paired cast action first.
        if battle.t < getattr(self, "_busy_until", 0.0):
            return
        # Wiki: Lightning Spell/Home Village, surplus casts remove other defenses.
        if self._spare_lightning(battle) and single_cast:
            return
        # Wiki: Earthquake Spell, unreserved casts can cripple defense clusters.
        if self._spare_quake(battle) and single_cast:
            return
        if not units:
            return
        cargo = self._cargo_support(battle)
        t = battle.t
        if t - self._last("breach") > 3:
            before = len(self._cast_log)
            self._breach(battle, units, single_cast=single_cast)
            # Video: docs/VIDEO_MEASUREMENTS.md:31, one fallback cast per action.
            if single_cast and len(self._cast_log) > before:
                return
        cx, cy = self.centroid(units)
        avg_hp = sum(u.hp / u.max_hp for u in units) / len(units)
        engaged = sum(1 for u in units if u.target is not None and u.cooldown > 0)
        if self._have("freeze"):
            prio = {k: 100 - i for i, k in enumerate(self.freeze_first)}
            for b, d in sorted(
                self.threats_near(battle, cx, cy, 12),
                key=lambda bd: -(prio.get(bd[0].key) or THREAT.get(bd[0].key, 1)),
            ):
                # output/research/usage/freeze-spell.md: overlapping Freezes
                # do not stack. Include bottles awaiting their landing tick.
                # https://houseofclashers.com/home-village/spells-elixir/freeze-spell
                if any(
                    field.kind == "freeze"
                    and field.team == "atk"
                    and b.edge_distance(field.x, field.y) <= field.radius
                    for field in battle.fields
                ):
                    continue
                if (
                    (
                        b.key in prio
                        or THREAT.get(b.key, 0) >= self.P("freeze_min_threat")
                    )
                    and d <= b.weapon.range + self.P("freeze_reach")
                    and (b.weapon.target is not None or b.weapon.multi)
                ):
                    if self.P("freeze_min_units") > 0:
                        inr = sum(
                            1
                            for u in units
                            if math.hypot(u.x - b.x, u.y - b.y) <= b.weapon.range
                        )
                        if inr < self.P("freeze_min_units"):
                            continue
                    self._use(battle, "freeze", b.x, b.y)
                    if single_cast:
                        return
                    break
        if self._have("totem") and t - self._last("totem") > self.P("totem_gap"):
            hot = self.threats_near(battle, cx, cy, 10)
            if len(hot) >= self.P("totem_min_threats"):
                # User (TH16 ranked, 2026-10-23): attackers spread Totems out.
                targets = self._totem_targets(battle, hot)
                if targets:
                    b, _, _ = max(targets, key=lambda target: (target[2], -target[1]))
                    self._use(battle, "totem", b.x, b.y)
                    if single_cast:
                        return
        if self._have("overgrowth"):
            best = None
            for b, d in self.threats_near(battle, cx, cy, 13):
                if THREAT.get(b.key, 0) < 4:
                    continue
                score = sum(
                    THREAT.get(o.key, 1)
                    for o, _ in self.threats_near(battle, b.x, b.y, 6)
                )
                if best is None or score > best[0]:
                    best = (score, b)
            if best is not None and best[0] >= self.P("og_min_score"):
                self._use(battle, "overgrowth", best[1].x, best[1].y)
                if single_cast:
                    return
        if (
            self._have("rage")
            and engaged >= max(2, int(len(units) * self.P("rage_engaged")))
            and t - self._last("rage") > self.P("rage_gap")
        ):
            self._use(battle, "rage", cx, cy)
            if single_cast:
                return
        if (
            self._have("heal")
            and avg_hp < self.P("heal_hp")
            and t - self._last("heal") > 6
        ):
            self._use(battle, "heal", cx, cy)
            if single_cast:
                return
        if (
            self._have("invis")
            and t - self._last("invis") > self.P("invis_gap")
            and (cargo is None or cargo)
        ):
            # players chain Invisibility over the push whenever heavy
            # defenses are shooting it (wiki: 4.25 s per spell)
            hot = [
                b
                for b, d in self.threats_near(battle, cx, cy, 11)
                if THREAT.get(b.key, 0) >= 4
                and (b.weapon.target is not None or b.weapon.multi)
            ]
            # Wiki: Battle Blimp, keep its Super Archer/Wizard cargo invisible.
            if cargo or avg_hp < self.P("invis_hp") or len(hot) >= self.P("invis_hot"):
                ix, iy = self.centroid(cargo) if cargo else (cx, cy)
                self._use(battle, "invis", ix, iy)
                if single_cast:
                    return
        if (
            self._have("recall")
            and t - self._last("recall") > 6.0
            and t - self._main_at > self.P("recall_after")
        ):
            # pull a stalled or dying push back and drop it where buildings remain
            work = any(
                b.alive and b.counted and b.edge_distance(cx, cy) < 7
                for b in battle.buildings
            )
            if len(units) >= 6 and (not work or avg_hp < self.P("recall_hp")):
                self._use(battle, "recall", cx, cy)
                if single_cast:
                    return
        if (
            self._have("clone")
            and t - self._main_at > 1.0
            and t - self._last("clone") > 1.0
        ):
            # Wiki: Battle Blimp, Clone supports its released payload, not the push.
            big = [
                u
                for u in (units if cargo is None else cargo)
                if (cargo is not None or u.housing >= 10) and not u.extra.get("clone")
            ]
            if big:
                bx, by = self.centroid(big)
                self._use(battle, "clone", bx, by)
                if single_cast:
                    return
        if (
            self._have("haste")
            and t - self._main_at > self.P("haste_after")
            and t - self._last("haste") > self.P("haste_gap")
        ):
            self._use(battle, "haste", cx, cy)
            if single_cast:
                return
        if self._have("iceblock") and avg_hp < 0.45 and t - self._last("iceblock") > 8:
            self._use(battle, "iceblock", cx, cy)
            if single_cast:
                return
        if self._have("poison"):
            foes = [
                d
                for d in battle.defenders
                if d.alive and t >= d.active_at and math.hypot(d.x - cx, d.y - cy) < 7
            ]
            if len(foes) >= self.P("poison_min") or any(f.is_hero for f in foes):
                self._use(
                    battle,
                    "poison",
                    sum(f.x for f in foes) / len(foes),
                    sum(f.y for f in foes) / len(foes),
                )
                if single_cast:
                    return
        self._learned_plays(battle, units, cx, cy, single_cast=single_cast)

    def _learned_plays(self, battle, units, cx, cy, *, single_cast=False):
        """Plays switched on by the learned policy (all off by default)."""
        t = battle.t
        # Angry Spell: push troops chasing non-defenses next to a defense turn onto it
        if (
            self.P("angry_min") > 0
            and self._have("angry")
            and t - self._last("angry") > 6
        ):
            astray = [
                u
                for u in units
                if u.target is not None
                and not getattr(u.target, "is_defense", True)
                and any(
                    b.alive
                    and b.weapon is not None
                    and math.hypot(b.x - u.x, b.y - u.y) < 7
                    for b in battle.buildings
                )
            ]
            if len(astray) >= self.P("angry_min"):
                ax, ay = self.centroid(astray)
                self._use(battle, "angry", ax, ay)
                if single_cast:
                    return
        # Skeleton Spell: a distraction beside a heavy defense that is locked on the push
        if (
            self.P("skeleton_on") > 0.5
            and self._have("skeleton")
            and t - self._last("skeleton") > 8
        ):
            for b, d in self.threats_near(battle, cx, cy, 12):
                if (
                    THREAT.get(b.key, 0) >= 5
                    and b.weapon.target is not None
                    and not b.weapon.multi
                ):
                    self._use(
                        battle,
                        "skeleton",
                        b.x + (cx - b.x) * 0.25,
                        b.y + (cy - b.y) * 0.25,
                    )
                    if single_cast:
                        return
                    break
        # Bat Spell: onto the defenses the push is about to meet
        if self.P("bat_on") > 0.5 and self._have("bat") and t - self._last("bat") > 6:
            hot = self.threats_near(battle, cx, cy, 10)
            if len(hot) >= 2:
                self._use(
                    battle,
                    "bat",
                    sum(b.x for b, _ in hot) / len(hot),
                    sum(b.y for b, _ in hot) / len(hot),
                )
                if single_cast:
                    return
        th = battle.th
        # Earthquakes on the core walls between the push and the Town Hall
        d_core = self.P("eq_core_dist")
        n_eq = int(round(self.P("eq_core_n")))
        if (
            d_core > 2
            and th is not None
            and th.alive
            and self._unreserved_spells("eq") >= n_eq
            and self._last("eq_core") < 0
        ):
            if math.hypot(th.x - cx, th.y - cy) <= d_core + 4:
                px, py = cx + (th.x - cx) * 0.6, cy + (th.y - cy) * 0.6
                # Video: docs/VIDEO_MEASUREMENTS.md:31, pace the remaining quakes.
                if single_cast:
                    self._fallback_quakes = [(px, py)] * (n_eq - 1)
                for _ in range(1 if single_cast else n_eq):
                    self._use(battle, "eq", px, py)
                self._cast_log.append((round(t, 1), "eq_core"))
                if single_cast:
                    return
        # distraction: one cleanup troop pulls a heavy defense off the push
        reach = self.P("distract_reach")
        if (
            reach > 2
            and self._distracts < int(round(self.P("distract_max")))
            and t - self._last("distract") > 3.0
        ):
            for b, d in self.threats_near(battle, cx, cy, 16):
                if (
                    THREAT.get(b.key, 0) >= self.P("distract_threat")
                    and b.weapon.range < d <= b.weapon.range + reach
                ):
                    name = self._spare_troop()
                    if name is None:
                        break
                    x, y = self._snipe_point_xy(
                        battle, b.x + (b.x - cx), b.y + (b.y - cy)
                    )  # far side of the defense
                    self._drop(battle, name, x, y, "cleanup", jitter=0.3)
                    self._distracts += 1
                    self._cast_log.append((round(t, 1), "distract"))
                    break

    def _spare_troop(self):
        # Wiki: Army Camp, fallback distractions spend the same undeployed stock
        # as cited steps. cleanup describes roles; inventory owns playbook stock.
        inventory = getattr(self, "inventory", None)
        for c in self.cleanup:
            left = c[1] if inventory is None else inventory.get(c[0], 0)
            if left > 0:
                c[1] = left - 1
                if inventory is not None:
                    inventory[c[0]] = left - 1
                return c[0]
        return None

    def _snipe_point_xy(self, battle, x, y):
        if getattr(self, "_snipe_t", None) != battle.t:
            self._snipe_pts = [
                edge_point(battle, 2 * math.pi * k / 64, 0.0) for k in range(64)
            ] + battle.inside_spots()
            self._snipe_t = battle.t
        return min(self._snipe_pts, key=lambda p: math.hypot(p[0] - x, p[1] - y))


# ==========================================================================
# Armies from real ranked attacks on the user's base (Clash API battle log,
# decoded 2026-10-14), made legal per Town Hall:
#   army camps 320 / 340 / 352, Clan Castle troops 50 / 55 / 55,
#   spells 11 / 11 / 11, Clan Castle spells 3 / 3 / 4 (wiki).
# Clan Castle troops ride in the siege machine and come out where it breaks.
# ==========================================================================
def hydra(angle=0.0, town_hall=18, seed=0) -> AttackPlan:
    """Dragons + Dragon Riders + mass Invisibility (3* 100% on the user)."""
    camp = {
        16: [("Dragon", 8), ("Dragon Rider", 6)],
        17: [("Dragon", 9), ("Dragon Rider", 6)],
        18: [("Dragon", 9), ("Dragon Rider", 6), ("Minion", 6)],
    }[town_hall]
    return AttackPlan(
        angle=angle,
        town_hall=town_hall,
        seed=seed,
        label="Hydra (Dragons + Dragon Riders, mass Invisibility)",
        funnel_heroes=[("Dragon Duke", -6.0), ("Royal Champion", 6.0)],
        flank=[("Baby Dragon", 1, -4.0)],
        main=[Wave("main", camp, spread=3.0)],
        push_heroes=["Grand Warden", "Minion Prince"],
        siege="Sky Wagon",
        cc_troops=(
            ["Dragon", "Dragon", "Baby Dragon"]
            if town_hall == 16
            else ["Super Dragon", "Inferno Dragon"]
        ),
        spells={"invis": 9, "revive": 1},
        cc_spells=(
            {"freeze": 2, "invis": 1} if town_hall < 18 else {"freeze": 2, "invis": 2}
        ),
        ground=False,
        loadouts={
            "Dragon Duke": L(
                "Dragon Duke", ("Revenge Deck", "Rocket Backpack"), "Diggy"
            ),
            "Royal Champion": L(
                "Royal Champion", ("Rocket Spear", "Electro Boots"), "Phoenix"
            ),
            "Grand Warden": L(
                "Grand Warden", ("Eternal Tome", "Rage Gem"), "Electro Owl"
            ),
            "Minion Prince": L(
                "Minion Prince", ("Meteor Staff", "Dark Orb"), "Angry Jelly"
            ),
        },
        main_min=10.0,
        main_max=20.0,
    )


def throwers(angle=0.0, town_hall=18, seed=0) -> AttackPlan:
    if town_hall == 16:
        # 3* 100% on the user from a TH16
        return AttackPlan(
            angle=angle,
            town_hall=town_hall,
            seed=seed,
            label="Mass Throwers + Healers (Log Launcher)",
            funnel_heroes=[("Barbarian King", -6.0), ("Dragon Duke", 6.0)],
            flank=[("Balloon", 2, 0.0)],
            main=[
                Wave(
                    "main",
                    [("Ice Golem", 2), ("Furnace", 1), ("Thrower", 11), ("Wizard", 2)],
                    spread=2.5,
                )
            ],
            support=[Wave("main", [("Healer", 5)], spread=1.0)],
            push_heroes=["Archer Queen", "Grand Warden"],
            cleanup=[("Archer", 4)],
            breakers=[("Wall Breaker", 2)],
            siege="Log Launcher",
            cc_troops=["Thrower", "Thrower", "Thrower", "Wall Breaker"],
            spells={"totem": 4, "poison": 1, "freeze": 2, "revive": 2},
            cc_spells={"totem": 1, "freeze": 2},
            loadouts={
                "Barbarian King": L(
                    "Barbarian King", ("Earthquake Boots", "Spiky Ball"), "Mighty Yak"
                ),
                "Archer Queen": L(
                    "Archer Queen", ("Giant Arrow", "Healer Puppet"), "Frosty"
                ),
                "Grand Warden": L(
                    "Grand Warden", ("Eternal Tome", "Rage Gem"), "Electro Owl"
                ),
                "Dragon Duke": L(
                    "Dragon Duke", ("Fire Heart", "Electro Fangs"), "Phoenix"
                ),
            },
            main_min=8.0,
            main_max=18.0,
        )
    # 2* 94% on the user from a TH17: 17 Throwers, 4 Healers, 4 Invisibility
    n, archers = {17: (15, 9), 18: (16, 5)}[town_hall]
    return AttackPlan(
        angle=angle,
        town_hall=town_hall,
        seed=seed,
        label="Mass Throwers + Healers (Log Launcher)",
        funnel_heroes=[("Royal Champion", -6.0), ("Dragon Duke", 6.0)],
        flank=[("Balloon", 4, 0.0)],
        main=[Wave("main", [("Ice Golem", 1), ("Thrower", n)], spread=3.0)],
        support=[Wave("main", [("Healer", 4)], spread=1.0)],
        push_heroes=["Archer Queen", "Grand Warden"],
        cleanup=[("Archer", archers)],
        siege="Log Launcher",
        cc_troops=["Thrower", "Thrower", "Thrower", "Balloon", "Wall Breaker"],
        spells={"invis": 4, "freeze": 2, "totem": 3, "revive": 1},
        cc_spells=(
            {"totem": 2, "freeze": 1} if town_hall == 17 else {"totem": 2, "freeze": 2}
        ),
        loadouts={
            "Archer Queen": L(
                "Archer Queen", ("Healer Puppet", "Magic Mirror"), "Mighty Yak"
            ),
            "Grand Warden": L(
                "Grand Warden", ("Healing Tome", "Eternal Tome"), "Sneezy"
            ),
            "Royal Champion": L(
                "Royal Champion", ("Electro Boots", "Rocket Spear"), "Unicorn"
            ),
            "Dragon Duke": L(
                "Dragon Duke", ("Electro Fangs", "Rocket Backpack"), "Phoenix"
            ),
        },
        main_min=8.0,
        main_max=18.0,
    )


def edrag(angle=0.0, town_hall=18, seed=0) -> AttackPlan:
    """Electro Dragons + Clone/Haste (3* 100% on the user from a TH17)."""
    camp = {
        16: [("Electro Dragon", 10), ("Balloon", 2)],
        17: [("Electro Dragon", 11), ("Balloon", 2)],
        18: [("Electro Dragon", 11), ("Minion", 6)],
    }[town_hall]
    return AttackPlan(
        angle=angle,
        town_hall=town_hall,
        seed=seed,
        label="Electro Dragon spam (Clone + Haste)",
        funnel_heroes=[("Barbarian King", -6.0), ("Archer Queen", 6.0)],
        flank=[("Baby Dragon", 1, -3.0)] if town_hall != 17 else [],
        main=[Wave("main", camp, spread=6.0)],
        push_heroes=["Grand Warden", "Minion Prince"],
        siege="Log Launcher",
        cc_troops=(
            ["Super Witch", "Balloon", "Balloon"]
            if town_hall == 16
            else ["Super Witch", "Super Hog Rider", "Sneaky Goblin"]
        ),
        spells={"clone": 3, "haste": 2},
        cc_spells=(
            {"eq": 1, "freeze": 1, "haste": 1}
            if town_hall < 18
            else {"eq": 1, "freeze": 2, "haste": 1}
        ),
        ground=False,
        loadouts={
            "Barbarian King": L(
                "Barbarian King", ("Spiky Ball", "Snake Bracelet"), "Spirit Fox"
            ),
            # Wiki: Greedy Raven, requires TH18; lower THs use the Queen's default pet.
            "Archer Queen": L(
                "Archer Queen",
                ("Action Figure", "Frozen Arrow"),
                (
                    "Greedy Raven"
                    if town_hall == 18
                    else heroes.DEFAULT_LOADOUTS["Archer Queen"].pet
                ),
            ),
            "Grand Warden": L(
                "Grand Warden", ("Eternal Tome", "Life Gem"), "Electro Owl"
            ),
            "Minion Prince": L(
                "Minion Prince", ("Meteor Staff", "Dark Orb"), "Angry Jelly"
            ),
        },
        main_min=5.0,
        main_max=12.0,
    )


def root_riders(angle=0.0, town_hall=18, seed=0) -> AttackPlan:
    """The user's own Root Rider army (3* 100% vs TH17 twice)."""
    rr = {16: 4, 17: 5, 18: 5}[town_hall]
    minions = {16: 6, 17: 6, 18: 12}[town_hall]
    return AttackPlan(
        angle=angle,
        town_hall=town_hall,
        seed=seed,
        label="Root Riders + Valkyries (Siege Barracks)",
        funnel_heroes=[("Royal Champion", -6.0), ("Dragon Duke", 6.0)],
        flank=[("Rocket Balloon", 4, -4.0), ("Balloon", 2, 4.0)],
        main=[
            Wave(
                "main",
                [("Ice Golem", 2), ("Root Rider", rr), ("Valkyrie", 8)],
                spread=2.0,
            )
        ],
        support=[Wave("main", [("Healer", 5), ("Apprentice Warden", 1)], spread=1.0)],
        push_heroes=["Archer Queen", "Grand Warden"],
        cleanup=[("Minion", minions), ("Archer", 2)],
        siege="Siege Barracks",
        cc_troops=(
            ["Super Hog Rider"] * 4 + ["Minion"]
            if town_hall == 16
            else ["Super Hog Rider"] * 4 + ["Minion"] * 3 + ["Archer"]
        ),
        spells={"invis": 5, "recall": 1, "freeze": 1, "poison": 1, "overgrowth": 1},
        cc_spells=(
            {"rage": 1, "totem": 1} if town_hall < 18 else {"rage": 1, "totem": 2}
        ),
        loadouts={
            "Royal Champion": L(
                "Royal Champion", ("Rocket Spear", "Electro Boots"), "Unicorn"
            ),
            "Dragon Duke": L("Dragon Duke", ("Revenge Deck", "Fire Heart"), "Phoenix"),
            "Archer Queen": L(
                "Archer Queen", ("Action Figure", "Giant Arrow"), "Frosty"
            ),
            "Grand Warden": L(
                "Grand Warden", ("Eternal Tome", "Rage Gem"), "Poison Lizard"
            ),
        },
        main_min=8.0,
        main_max=18.0,
    )


ARMIES = {
    "hydra": hydra,
    "throwers": throwers,
    "edrag": edrag,
    "rootrider": root_riders,
}
META_WEIGHTS = {"hydra": 0.271, "throwers": 0.260, "edrag": 0.115, "rootrider": 0.097}
