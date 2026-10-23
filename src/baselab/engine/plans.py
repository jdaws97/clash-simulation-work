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
from dataclasses import dataclass, field
from functools import lru_cache

from ..loadouts import HeroLoadout as L
from ..mechanics import WORLD
from . import heroes, spells, stats

CENTER = WORLD / 2.0

THREAT = {
    "th": 6, "inferno": 10, "scatter": 8, "eagle": 7, "xbow": 5, "mono": 5, "mgt": 5, "firespitter": 4,
    "swt": 5, "revenge": 4, "ad": 4, "ric": 4, "mat": 3, "wt": 3, "st": 3, "bt": 2, "at": 2, "tesla": 2,
    "cannon": 1, "bh": 1, "mortar": 1, "sweeper": 1,
}

# Learnable attacker policy: every decision threshold of the brain below.
# Defaults reproduce the hand-written brain exactly; tools/baselab/train_policy.py
# learns better values across many bases (name: (default, lo, hi)).
POLICY = {
    "commit_progress": (3.0, 1.0, 6.0),     # funnel buildings down before the main push commits
    "freeze_min_threat": (5.0, 3.0, 9.0),   # weakest defense worth a Freeze
    "freeze_reach": (1.5, -1.0, 4.0),       # Freeze once the army is this far inside its range
    "freeze_min_units": (0.0, 0.0, 10.0),   # ... and at least this many troops are in range
    "totem_min_threats": (3.0, 1.0, 5.0),
    "totem_gap": (5.0, 2.0, 12.0),
    "og_min_score": (18.0, 6.0, 30.0),      # Overgrowth only on a cluster this dangerous
    "rage_engaged": (0.5, 0.15, 0.9),       # share of the army fighting before Rage
    "rage_gap": (9.0, 4.0, 15.0),
    "heal_hp": (0.6, 0.3, 0.9),
    "invis_hp": (0.6, 0.3, 0.9),            # Invisibility when the army drops below this health ...
    "invis_hot": (2.0, 1.0, 4.0),           # ... or this many heavy defenses shoot it
    "invis_gap": (4.5, 4.25, 8.0),
    "recall_after": (12.0, 5.0, 30.0),
    "recall_hp": (0.4, 0.2, 0.7),
    "haste_after": (3.0, 0.0, 12.0),
    "haste_gap": (8.0, 4.0, 15.0),
    "poison_min": (3.0, 1.0, 6.0),
    "hero_hp": (0.5, 0.15, 0.85),           # generic hero ability: below this health ...
    "hero_time": (25.0, 5.0, 60.0),         # ... or after this long fighting
    "warden_hp": (0.4, 0.15, 0.8),
    "warden_hurt": (1.0 / 3.0, 0.1, 0.8),        # share of nearby troops hurt before Eternal Tome
    "duke_hp": (0.6, 0.2, 0.9),
    "arrow_aim": (0.0, 0.0, 1.0),           # > 0.5: Giant Arrow is aimed at a heavy defense in reach
    "arrow_reach": (12.0, 5.0, 20.0),
    "arrow_threat": (7.0, 3.0, 10.0),
    "dash_aim": (0.0, 0.0, 1.0),            # > 0.5: Rocket Backpack dashes at a heavy defense in reach
    "dash_reach": (8.0, 4.0, 14.0),
    "dash_threat": (7.0, 3.0, 10.0),
    "distract_reach": (0.0, 0.0, 10.0),     # > 2: a cleanup troop pulls a heavy defense off the push
    "distract_threat": (8.0, 4.0, 10.0),
    "distract_max": (2.0, 0.0, 4.0),
    "lure_time": (-1.0, -5.0, 30.0),        # >= 0: one troop dropped by the Clan Castle at this time
    "eq_core_dist": (0.0, 0.0, 12.0),       # > 2: Earthquakes on the core walls once the push is this close to the TH
    "eq_core_n": (2.0, 1.0, 4.0),
    # from the attack audit (docs/ATTACK_AUDIT.md); off by default until screened
    "deep_drop": (0.0, 0.0, 1.0),           # > 0.5: drop into corridors / pockets on the attack side, as real players do
    "angry_min": (0.0, 0.0, 8.0),           # > 0: Angry Spell when this many push troops chase non-defenses near a defense
    "skeleton_on": (0.0, 0.0, 1.0),         # > 0.5: Skeleton Spell as a distraction by a heavy defense locked on the push
    "bat_on": (0.0, 0.0, 1.0),              # > 0.5: Bat Spell onto defenses near the push
    "tank_lead": (0.0, 0.0, 4.0),           # > 0.3: tanks land first, damage dealers this many seconds later
}
TANKS = {"Ice Golem", "Golem", "Lava Hound", "Ice Hound", "Giant", "Super Giant", "Electro Titan", "P.E.K.K.A", "Yeti",
         "Meteor Golem", "Headhunter"}

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
        last = (min(WORLD - 1.0, max(1.0, CENTER + dx * 24)), min(WORLD - 1.0, max(1.0, CENTER + dy * 24)))
    return last


def _cheb(x, y):
    return max(abs(x - CENTER), abs(y - CENTER))


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
    cc_troops: list = field(default_factory=list)  # Clan Castle troops, released when the siege breaks
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
    charge_hero: str | None = None  # Queen / Champion charge: this hero opens with Healers along the side
    charge_lat: float = 0.0
    charge_at: float = 0.0
    charge_recall_hp: float = 0.35  # Recall the charging hero below this health ...
    charge_len: float = 25.0        # ... or this long after the charge starts
    recall_funnel: bool = False     # Recall then redeploy the charge up the opposite flank (TrophyCoach QC guide)
    split_main: float = 0.0         # > 0: the main wave lands on two flanks this far apart (radians), e.g. two-flank Hydra
    recalled: list = field(default_factory=list)
    _cast_log: list = field(default_factory=list)
    _totem_casts: list = field(default_factory=list)  # (time, x, y)
    _next_brain: float = 0.0
    _phase: str = "funnel"
    _entry: tuple | None = None
    _main_at: float = 0.0
    _zap_done: bool = False
    _cc_released: bool = False

    def P(self, name):
        v = self.pol.get(name)
        return POLICY[name][0] if v is None else v

    def __post_init__(self):
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
        """Problems with spell counts, levels, unlocks and army capacity."""
        out = []
        try:
            quantities = [(name, count) for name, count, _ in self.flank]
            quantities.extend(
                (name, count)
                for wave in self.main + self.support
                for name, count in wave.units
            )
            quantities.extend(self.cleanup + self.breakers)
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

    def require_legal(self):
        # armies replayed from real battles happened, so they are legal by definition
        problems = [] if getattr(self, "observed", False) else self.legal()
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
        hero = next((u for u in charge if u.is_hero and u.name == self.charge_hero), None)
        if hero is None:
            return
        frac = hero.hp / max(1.0, hero.max_hp)
        locked = any(b.alive and b.weapon is not None and b.weapon.target is hero and THREAT.get(b.key, 0) >= 4 for b in battle.buildings)
        if self._have("invis") and t - self._last("invis") > self.P("invis_gap") and t >= hero.invisible_until and (locked or frac < 0.6):
            self._use(battle, "invis", hero.x, hero.y)
        done = t - self.charge_at > self.charge_len
        if self._have("recall") and self._last("recall_charge") < 0 and (frac < self.charge_recall_hp or done):
            self._use(battle, "recall", hero.x, hero.y)
            self._cast_log.append((round(t, 1), "recall_charge"))

    def setup_charge(self, hero, healers, lateral=0.0, at=0.0):
        """A hero charge (Queen Charge, Royal Champion charge): the hero opens
        along the side at `lateral` with up to `healers` of the army's own
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
        self.charge_hero, self._charge_n, self.charge_lat, self.charge_at = hero, taken, lateral, at
        return True

    def deployments(self, battle):
        out = []
        th = self.town_hall
        for name, lateral in self.funnel_heroes:
            x, y = edge_point(battle, self.angle, lateral)
            out.append(Deployment(0.0, name, x, y, group="funnel", level=self._level(name), town_hall=th))
        if self.charge_hero:
            x, y = edge_point(battle, self.angle, self.charge_lat)
            if self.P("deep_drop") > 0.5:
                x, y = self._deep_charge_point(battle, (x, y))
            out.append(Deployment(self.charge_at, self.charge_hero, x, y, group="charge", level=self._level(self.charge_hero), town_hall=th))
            for k in range(self._charge_n):
                out.append(Deployment(self.charge_at + 0.6 + 0.1 * k, "Healer", x, y, group="charge", level=self._level("Healer"), town_hall=th))
        t = 0.5
        for name, count, lateral in self.flank:
            for k in range(count):
                x, y = edge_point(battle, self.angle, lateral + (k - count / 2) * 0.6)
                out.append(Deployment(t, name, x, y, group="funnel", level=self._level(name), town_hall=th))
                t += 0.15
        return out

    def has_offensive_pending(self, battle):
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

    def _drop(self, battle, name, x, y, group, jitter=0.0, *, source="army", at=None):
        if jitter:
            x += battle.rng.uniform(-jitter, jitter)
            y += battle.rng.uniform(-jitter, jitter)
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
            score = 0.5 * _cheb(nearest.x, nearest.y) + 2.0 * max(0.0, nd - 1.5) + 0.3 * abs(lat)
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
        defs = [b for b in battle.buildings if b.alive and b.weapon is not None and THREAT.get(b.key, 0) >= 5
                and abs((math.atan2(b.y - CENTER, b.x - CENTER) - ang + math.pi) % (2 * math.pi) - math.pi) <= 0.8]
        tiles = self._sector_tiles(battle, ang, 0.6)
        if not defs or not tiles:
            return default
        tgt = max(defs, key=lambda b: (THREAT.get(b.key, 0), -math.hypot(b.x - default[0], b.y - default[1])))
        return min(tiles, key=lambda p: math.hypot(p[0] - tgt.x, p[1] - tgt.y))

    def _funnel_progress(self, battle):
        ex, ey = edge_point(battle, self.angle, 0.0)
        return sum(1 for b in battle.buildings if not b.alive and b.counted and math.hypot(b.x - ex, b.y - ey) < 10)

    def _launch_main(self, battle):
        self._entry = self._best_entry(battle)
        ex, ey = self._entry
        if self.siege:
            self._drop(battle, self.siege, ex, ey, "main")
        elif self.cc_troops and not self._cc_released:
            from . import units

            units.release_cc_at(battle, ex, ey, "main")
        e2 = edge_point(battle, self.angle + self.split_main, 0.0) if self.split_main > 0.05 else None
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
            self._snipe_pts = [edge_point(battle, 2 * math.pi * k / 64, 0.0) for k in range(64)] + battle.inside_spots()
            self._snipe_t = battle.t
        return min(self._snipe_pts, key=lambda p: math.hypot(p[0] - b.x, p[1] - b.y))

    def portal_point(self, battle):
        """Redeploy where the most buildings are still standing."""
        best, bs = None, -1
        for k in range(16):
            x, y = edge_point(battle, self.angle + 2 * math.pi * k / 16, 0.0)
            s = sum(1 for b in battle.buildings if b.alive and b.counted and math.hypot(b.x - x, b.y - y) < 11)
            if s > bs:
                best, bs = (x, y), s
        return best

    def on_tick(self, battle):
        t = battle.t
        self.revive_knocked_out(battle)
        self._battle_portal = battle.portal_stash
        if self._later:
            due = [d for d in self._later if d[0] <= t]
            self._later = [d for d in self._later if d[0] > t]
            for _, name, x, y, group, jit in due:
                self._drop(battle, name, x, y, group, jitter=jit)
        hold = self.charge_hero and self._phase == "funnel" and not self.recall_funnel  # a recalled charge comes back with the main push
        if battle.portal_stash and t >= battle.portal_ready_at and self.recall_funnel and self.charge_hero and self._phase == "funnel":
            x, y = edge_point(battle, self.angle, -self.charge_lat if abs(self.charge_lat) > 1 else 8.0)
            heroes.portal_redeploy(battle, x, y)  # recall funnel: the other flank
            hold = True
        if battle.portal_stash and t >= battle.portal_ready_at and not hold:
            x, y = self.portal_point(battle)
            heroes.portal_redeploy(battle, x, y)
        if self._phase == "funnel":
            if not self._zap_done and self.zap_ad != (0, 0):
                self._zap(battle)
            if t >= self.main_max or (t >= self.main_min and self._funnel_progress(battle) >= self.P("commit_progress")):
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
            names = [n for n, c in self.cleanup for _ in range(c)] + [n for n, _lvl, _h in self.recalled]
            # Wiki: Healer, only undeployed reserves count toward battle survival.
            self.cleanup.clear()
            self.recalled.clear()
            army = self.main_units(battle)
            cx, cy = self.centroid(army) if army else (CENTER, CENTER)
            far = sorted((b for b in battle.buildings if b.alive and b.counted), key=lambda b: -math.hypot(b.x - cx, b.y - cy))
            for k, name in enumerate(names):
                if not far:
                    x, y = edge_point(battle, self.angle + math.pi, 0.0)
                else:
                    x, y = self._snipe_point(battle, far[k % min(len(far), max(1, len(names) // 2 + 1))])
                self._drop(battle, name, x, y, "cleanup", jitter=0.3)
            self._phase = "done"
        if not self._lured and self.P("lure_time") >= 0 and t >= self.P("lure_time"):
            self._lured = True
            cc = next((b for b in battle.buildings if b.key == "cc" and b.alive), None)
            name = self._spare_troop() if cc is not None else None
            if name is not None:
                x, y = self._snipe_point_xy(battle, cc.x, cc.y)
                self._drop(battle, name, x, y, "cleanup", jitter=0.2)
                self._cast_log.append((round(t, 1), "lure"))
        if t >= self._next_brain:
            self._next_brain = t + 0.5
            self.hero_abilities(battle)
            if self.charge_hero and self._last("recall_charge") < 0:
                # the charge is managed until the hero is recalled (or dies),
                # also after the main push has gone in
                charge = self.main_units(battle, "charge")
                if charge:
                    self._charge_spells(battle, charge)
                    if self._phase == "funnel":
                        self.generic_spells(battle, charge)
            if self._phase in ("support", "push", "done"):
                self.generic_spells(battle, self.main_units(battle))

    # ---------------------------------------------------------- abilities
    def hero_abilities(self, battle):
        """Players fire abilities to save a hero or at a key moment."""
        t = battle.t
        for u in battle.attackers:
            if not u.alive or not u.is_hero or u.kit is None or u.ability_used:
                continue
            frac = u.hp / max(1.0, u.max_hp)
            engaged = u.target is not None and t - u.spawned_at > 2.0
            if u.name == "Minion Prince" and u.kit.has("Portal Pendant"):
                # pull the push out of a dead or losing spot and drop it fresh
                near = [a for a in battle.attackers_near(u.x, u.y, 7.0) if not a.is_hero and a.kind != "pet" and a.name != "Totem"]
                if near:
                    cx, cy = self.centroid(near)
                    work = any(b.alive and b.counted and b.edge_distance(cx, cy) < 7 for b in battle.buildings)
                    hurt = sum(a.hp / a.max_hp for a in near) / len(near)
                    if len(near) >= 6 and (not work or hurt < 0.45) and t - u.spawned_at > 15.0:
                        heroes.activate(battle, u)
                elif frac < 0.35:
                    heroes.activate(battle, u)
            elif u.name == "Grand Warden":
                near = [a for a in battle.attackers_near(u.x, u.y, 7.0) if a.name != "Totem" and not a.is_hero]
                hurt = sum(1 for a in near if a.hp < 0.55 * a.max_hp)
                if len(near) >= 5 and hurt >= int(len(near) * self.P("warden_hurt") + 1e-9) or frac < self.P("warden_hp"):
                    heroes.activate(battle, u)
            elif self.P("arrow_aim") > 0.5 and u.kit.has("Giant Arrow") and self._aim(battle, u, "arrow"):
                self._fire_aimed(battle, u)
            elif self.P("dash_aim") > 0.5 and u.kit.has("Rocket Backpack") and self._aim(battle, u, "dash"):
                self._fire_aimed(battle, u)
            elif u.name == "Dragon Duke":
                if engaged and (frac < self.P("duke_hp") or getattr(u.target, "is_defense", False)):
                    heroes.activate(battle, u)
            elif frac < self.P("hero_hp") or (engaged and t - u.spawned_at > self.P("hero_time")):
                heroes.activate(battle, u)

    def _aim(self, battle, u, kind):
        """Wait for the current firing line to cross a heavy nearby defense."""
        if kind == "dash":
            return False  # Rocket Backpack follows the village centre (wiki).
        # Wiki: Giant Arrow, direction follows the Queen's current target.
        target = u.target
        if target is None or not target.alive:
            return False
        dx, dy = target.x - u.x, target.y - u.y
        length = math.hypot(dx, dy)
        if length <= 0:
            return False
        reach, thr = self.P(kind + "_reach"), self.P(kind + "_threat")
        best = None
        for b in battle.buildings:
            if b.alive and b.weapon is not None and THREAT.get(b.key, 0) >= thr:
                d = math.hypot(b.x - u.x, b.y - u.y)
                along = ((b.x - u.x) * dx + (b.y - u.y) * dy) / length
                off = abs((b.x - u.x) * dy - (b.y - u.y) * dx) / length
                if d <= reach and along > 0 and off <= b.half_hit + 1.0:
                    if best is None or (THREAT.get(b.key, 0), -d) > best[0]:
                        best = ((THREAT.get(b.key, 0), -d), b)
        if best is None:
            return False
        return True

    @staticmethod
    def _fire_aimed(battle, u):
        """Activate once the hero's current firing line is useful."""
        # Wiki: Giant Arrow, the player times activation, not its direction.
        heroes.activate(battle, u)

    # -------------------------------------------------------------- spells
    def _zap(self, battle, *, single_cast=False, reserved=()):
        if self._zap_done:
            return
        if not hasattr(self, "_zap_left"):
            self._zap_left = list(self.zap_ad)
        ex, ey = edge_point(battle, self.angle, 0.0)
        ads = sorted(
            # Wiki: Giant Arrow, preserve the playbook's later Air Defense targets.
            (
                b
                for b in battle.buildings
                if b.alive and b.key == "ad" and b.id not in reserved
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
        return spells.cast(battle, SPELL_NAMES[kind], x, y)

    def _last(self, kind):
        for t, k in reversed(self._cast_log):
            if k == kind:
                return t
        return -100.0

    def main_units(self, battle, group="main"):
        return [u for u in battle.attackers if u.alive and u.group == group and u.name != "Totem" and u.kind != "pet"]

    @staticmethod
    def centroid(units):
        w = sum(max(1, u.housing) for u in units)
        return sum(u.x * max(1, u.housing) for u in units) / w, sum(u.y * max(1, u.housing) for u in units) / w

    @staticmethod
    def threats_near(battle, x, y, r):
        out = []
        t = battle.t
        for b in battle.buildings:
            if not b.alive or b.weapon is None or b.disabled(t):
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
        if sum(1 for v in stuck if abs(v.wall_target.x - w.x) + abs(v.wall_target.y - w.y) <= 3) < 2:
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
        elif self.spells.get("eq", 0) >= 4:
            # Video: docs/VIDEO_MEASUREMENTS.md:31, spell drops have nonzero spacing.
            if single_cast:
                self._fallback_quakes = [(w.x, w.y)] * 3
            for _ in range(1 if single_cast else 4):
                self._use(battle, "eq", w.x, w.y)
            self._cast_log.append((round(battle.t, 1), "breach"))

    def _spare_lightning(self, battle):
        # Wiki: Electro Dragon, Lightning removes Air Sweepers; Lightning Spell/
        # Home Village, it also destroys other defenses when enough casts remain.
        if not self._have("lightning"):
            return False
        available = self.spells.get("lightning", 0)
        if getattr(self, "_fallback", False):
            available -= sum(
                1
                for st in getattr(self, "steps", [])
                if st["action"] == "spell"
                and st.get("what") == "Lightning Spell"
                and st["id"] not in self._done
                and st["id"] not in self._cancelled
            )
        damage = 0.0
        for stock in self._spell_stock:
            if stock.name != "Lightning Spell" or stock.remaining <= 0:
                continue
            count = min(available, stock.remaining)
            damage += count * stats.get(
                stock.name, self._spell_level(stock), "damage", "Damage"
            )
            available -= count
        hp = {
            b.id: b.hp
            - sum(
                f.value
                for f in battle.fields
                if f.kind == "lightning" and b.edge_distance(f.x, f.y) <= f.radius
            )
            for b in battle.buildings
            if b.alive
        }
        if any(b.alive and b.key == "ad" and hp[b.id] > 1e-9 for b in battle.buildings):
            return False
        targets = [
            b
            for b in battle.buildings
            if b.alive
            and b.is_defense
            and b.key not in spells.STORAGES | {"th", "cc"}
            and not (b.key == "tesla" and not b.revealed)
            and 1e-9 < hp[b.id] <= damage
        ]
        if not targets:
            return False
        target = min(
            targets,
            key=lambda b: (
                0 if not self.ground and b.key == "sweeper" else 1,
                hp[b.id],
            ),
        )
        self._use(battle, "lightning", target.x, target.y)
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
        # Wiki: Lightning Spell/Home Village, surplus casts remove other defenses.
        if self._spare_lightning(battle) and single_cast:
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
            for b, d in sorted(self.threats_near(battle, cx, cy, 12), key=lambda bd: -(prio.get(bd[0].key) or THREAT.get(bd[0].key, 1))):
                if (b.key in prio or THREAT.get(b.key, 0) >= self.P("freeze_min_threat")) and d <= b.weapon.range + self.P("freeze_reach") \
                        and (b.weapon.target is not None or b.weapon.multi):
                    if self.P("freeze_min_units") > 0:
                        inr = sum(1 for u in units if math.hypot(u.x - b.x, u.y - b.y) <= b.weapon.range)
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
                score = sum(THREAT.get(o.key, 1) for o, _ in self.threats_near(battle, b.x, b.y, 6))
                if best is None or score > best[0]:
                    best = (score, b)
            if best is not None and best[0] >= self.P("og_min_score"):
                self._use(battle, "overgrowth", best[1].x, best[1].y)
                if single_cast:
                    return
        if self._have("rage") and engaged >= max(2, int(len(units) * self.P("rage_engaged"))) and t - self._last("rage") > self.P("rage_gap"):
            self._use(battle, "rage", cx, cy)
            if single_cast:
                return
        if self._have("heal") and avg_hp < self.P("heal_hp") and t - self._last("heal") > 6:
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
            hot = [b for b, d in self.threats_near(battle, cx, cy, 11) if THREAT.get(b.key, 0) >= 4 and (b.weapon.target is not None or b.weapon.multi)]
            # Wiki: Battle Blimp, keep its Super Archer/Wizard cargo invisible.
            if cargo or avg_hp < self.P("invis_hp") or len(hot) >= self.P("invis_hot"):
                ix, iy = self.centroid(cargo) if cargo else (cx, cy)
                self._use(battle, "invis", ix, iy)
                if single_cast:
                    return
        if self._have("recall") and t - self._last("recall") > 6.0 and t - self._main_at > self.P("recall_after"):
            # pull a stalled or dying push back and drop it where buildings remain
            work = any(b.alive and b.counted and b.edge_distance(cx, cy) < 7 for b in battle.buildings)
            if len(units) >= 6 and (not work or avg_hp < self.P("recall_hp")):
                self._use(battle, "recall", cx, cy)
                if single_cast:
                    return
        if self._have("clone") and t - self._main_at > 1.0 and t - self._last("clone") > 1.0:
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
        if self._have("haste") and t - self._main_at > self.P("haste_after") and t - self._last("haste") > self.P("haste_gap"):
            self._use(battle, "haste", cx, cy)
            if single_cast:
                return
        if self._have("iceblock") and avg_hp < 0.45 and t - self._last("iceblock") > 8:
            self._use(battle, "iceblock", cx, cy)
            if single_cast:
                return
        if self._have("poison"):
            foes = [d for d in battle.defenders if d.alive and t >= d.active_at and math.hypot(d.x - cx, d.y - cy) < 7]
            if len(foes) >= self.P("poison_min") or any(f.is_hero for f in foes):
                self._use(battle, "poison", sum(f.x for f in foes) / len(foes), sum(f.y for f in foes) / len(foes))
                if single_cast:
                    return
        self._learned_plays(battle, units, cx, cy, single_cast=single_cast)

    def _learned_plays(self, battle, units, cx, cy, *, single_cast=False):
        """Plays switched on by the learned policy (all off by default)."""
        t = battle.t
        # Angry Spell: push troops chasing non-defenses next to a defense turn onto it
        if self.P("angry_min") > 0 and self._have("angry") and t - self._last("angry") > 6:
            astray = [u for u in units if u.target is not None and not getattr(u.target, "is_defense", True)
                      and any(b.alive and b.weapon is not None and math.hypot(b.x - u.x, b.y - u.y) < 7 for b in battle.buildings)]
            if len(astray) >= self.P("angry_min"):
                ax, ay = self.centroid(astray)
                self._use(battle, "angry", ax, ay)
                if single_cast:
                    return
        # Skeleton Spell: a distraction beside a heavy defense that is locked on the push
        if self.P("skeleton_on") > 0.5 and self._have("skeleton") and t - self._last("skeleton") > 8:
            for b, d in self.threats_near(battle, cx, cy, 12):
                if THREAT.get(b.key, 0) >= 5 and b.weapon.target is not None and not b.weapon.multi:
                    self._use(battle, "skeleton", b.x + (cx - b.x) * 0.25, b.y + (cy - b.y) * 0.25)
                    if single_cast:
                        return
                    break
        # Bat Spell: onto the defenses the push is about to meet
        if self.P("bat_on") > 0.5 and self._have("bat") and t - self._last("bat") > 6:
            hot = self.threats_near(battle, cx, cy, 10)
            if len(hot) >= 2:
                self._use(battle, "bat", sum(b.x for b, _ in hot) / len(hot), sum(b.y for b, _ in hot) / len(hot))
                if single_cast:
                    return
        th = battle.th
        # Earthquakes on the core walls between the push and the Town Hall
        d_core = self.P("eq_core_dist")
        n_eq = int(round(self.P("eq_core_n")))
        if d_core > 2 and th is not None and th.alive and self.spells.get("eq", 0) >= n_eq and self._last("eq_core") < 0:
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
        if reach > 2 and self._distracts < int(round(self.P("distract_max"))) and t - self._last("distract") > 3.0:
            for b, d in self.threats_near(battle, cx, cy, 16):
                if THREAT.get(b.key, 0) >= self.P("distract_threat") and b.weapon.range < d <= b.weapon.range + reach:
                    name = self._spare_troop()
                    if name is None:
                        break
                    x, y = self._snipe_point_xy(battle, b.x + (b.x - cx), b.y + (b.y - cy))  # far side of the defense
                    self._drop(battle, name, x, y, "cleanup", jitter=0.3)
                    self._distracts += 1
                    self._cast_log.append((round(t, 1), "distract"))
                    break

    def _spare_troop(self):
        for c in self.cleanup:
            if c[1] > 0:
                c[1] -= 1
                return c[0]
        return None

    def _snipe_point_xy(self, battle, x, y):
        if getattr(self, "_snipe_t", None) != battle.t:
            self._snipe_pts = [edge_point(battle, 2 * math.pi * k / 64, 0.0) for k in range(64)] + battle.inside_spots()
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
    camp = {16: [("Dragon", 8), ("Dragon Rider", 6)],
            17: [("Dragon", 9), ("Dragon Rider", 6)],
            18: [("Dragon", 9), ("Dragon Rider", 6), ("Minion", 6)]}[town_hall]
    return AttackPlan(
        angle=angle, town_hall=town_hall, seed=seed, label="Hydra (Dragons + Dragon Riders, mass Invisibility)",
        funnel_heroes=[("Dragon Duke", -6.0), ("Royal Champion", 6.0)],
        flank=[("Baby Dragon", 1, -4.0)],
        main=[Wave("main", camp, spread=3.0)],
        push_heroes=["Grand Warden", "Minion Prince"],
        siege="Sky Wagon",
        cc_troops=["Dragon", "Dragon", "Baby Dragon"] if town_hall == 16 else ["Super Dragon", "Inferno Dragon"],
        spells={"invis": 9, "revive": 1},
        cc_spells={"freeze": 2, "invis": 1} if town_hall < 18 else {"freeze": 2, "invis": 2},
        ground=False,
        loadouts={
            "Dragon Duke": L("Dragon Duke", ("Revenge Deck", "Rocket Backpack"), "Diggy"),
            "Royal Champion": L("Royal Champion", ("Rocket Spear", "Electro Boots"), "Phoenix"),
            "Grand Warden": L("Grand Warden", ("Eternal Tome", "Rage Gem"), "Electro Owl"),
            "Minion Prince": L("Minion Prince", ("Meteor Staff", "Dark Orb"), "Angry Jelly"),
        },
        main_min=10.0, main_max=20.0,
    )


def throwers(angle=0.0, town_hall=18, seed=0) -> AttackPlan:
    if town_hall == 16:
        # 3* 100% on the user from a TH16
        return AttackPlan(
            angle=angle, town_hall=town_hall, seed=seed, label="Mass Throwers + Healers (Log Launcher)",
            funnel_heroes=[("Barbarian King", -6.0), ("Dragon Duke", 6.0)],
            flank=[("Balloon", 2, 0.0)],
            main=[Wave("main", [("Ice Golem", 2), ("Furnace", 1), ("Thrower", 11), ("Wizard", 2)], spread=2.5)],
            support=[Wave("main", [("Healer", 5)], spread=1.0)],
            push_heroes=["Archer Queen", "Grand Warden"],
            cleanup=[("Archer", 4)],
            breakers=[("Wall Breaker", 2)],
            siege="Log Launcher",
            cc_troops=["Thrower", "Thrower", "Thrower", "Wall Breaker"],
            spells={"totem": 4, "poison": 1, "freeze": 2, "revive": 2},
            cc_spells={"totem": 1, "freeze": 2},
            loadouts={
                "Barbarian King": L("Barbarian King", ("Earthquake Boots", "Spiky Ball"), "Mighty Yak"),
                "Archer Queen": L("Archer Queen", ("Giant Arrow", "Healer Puppet"), "Frosty"),
                "Grand Warden": L("Grand Warden", ("Eternal Tome", "Rage Gem"), "Electro Owl"),
                "Dragon Duke": L("Dragon Duke", ("Fire Heart", "Electro Fangs"), "Phoenix"),
            },
            main_min=8.0, main_max=18.0,
        )
    # 2* 94% on the user from a TH17: 17 Throwers, 4 Healers, 4 Invisibility
    n, archers = {17: (15, 9), 18: (16, 5)}[town_hall]
    return AttackPlan(
        angle=angle, town_hall=town_hall, seed=seed, label="Mass Throwers + Healers (Log Launcher)",
        funnel_heroes=[("Royal Champion", -6.0), ("Dragon Duke", 6.0)],
        flank=[("Balloon", 4, 0.0)],
        main=[Wave("main", [("Ice Golem", 1), ("Thrower", n)], spread=3.0)],
        support=[Wave("main", [("Healer", 4)], spread=1.0)],
        push_heroes=["Archer Queen", "Grand Warden"],
        cleanup=[("Archer", archers)],
        siege="Log Launcher",
        cc_troops=["Thrower", "Thrower", "Thrower", "Balloon", "Wall Breaker"],
        spells={"invis": 4, "freeze": 2, "totem": 3, "revive": 1},
        cc_spells={"totem": 2, "freeze": 1} if town_hall == 17 else {"totem": 2, "freeze": 2},
        loadouts={
            "Archer Queen": L("Archer Queen", ("Healer Puppet", "Magic Mirror"), "Mighty Yak"),
            "Grand Warden": L("Grand Warden", ("Healing Tome", "Eternal Tome"), "Sneezy"),
            "Royal Champion": L("Royal Champion", ("Electro Boots", "Rocket Spear"), "Unicorn"),
            "Dragon Duke": L("Dragon Duke", ("Electro Fangs", "Rocket Backpack"), "Phoenix"),
        },
        main_min=8.0, main_max=18.0,
    )


def edrag(angle=0.0, town_hall=18, seed=0) -> AttackPlan:
    """Electro Dragons + Clone/Haste (3* 100% on the user from a TH17)."""
    camp = {16: [("Electro Dragon", 10), ("Balloon", 2)],
            17: [("Electro Dragon", 11), ("Balloon", 2)],
            18: [("Electro Dragon", 11), ("Minion", 6)]}[town_hall]
    return AttackPlan(
        angle=angle, town_hall=town_hall, seed=seed, label="Electro Dragon spam (Clone + Haste)",
        funnel_heroes=[("Barbarian King", -6.0), ("Archer Queen", 6.0)],
        flank=[("Baby Dragon", 1, -3.0)] if town_hall != 17 else [],
        main=[Wave("main", camp, spread=6.0)],
        push_heroes=["Grand Warden", "Minion Prince"],
        siege="Log Launcher",
        cc_troops=["Super Witch", "Balloon", "Balloon"] if town_hall == 16 else ["Super Witch", "Super Hog Rider", "Sneaky Goblin"],
        spells={"clone": 3, "haste": 2},
        cc_spells={"eq": 1, "freeze": 1, "haste": 1} if town_hall < 18 else {"eq": 1, "freeze": 2, "haste": 1},
        ground=False,
        loadouts={
            "Barbarian King": L("Barbarian King", ("Spiky Ball", "Snake Bracelet"), "Spirit Fox"),
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
            "Grand Warden": L("Grand Warden", ("Eternal Tome", "Life Gem"), "Electro Owl"),
            "Minion Prince": L("Minion Prince", ("Meteor Staff", "Dark Orb"), "Angry Jelly"),
        },
        main_min=5.0, main_max=12.0,
    )


def root_riders(angle=0.0, town_hall=18, seed=0) -> AttackPlan:
    """The user's own Root Rider army (3* 100% vs TH17 twice)."""
    rr = {16: 4, 17: 5, 18: 5}[town_hall]
    minions = {16: 6, 17: 6, 18: 12}[town_hall]
    return AttackPlan(
        angle=angle, town_hall=town_hall, seed=seed, label="Root Riders + Valkyries (Siege Barracks)",
        funnel_heroes=[("Royal Champion", -6.0), ("Dragon Duke", 6.0)],
        flank=[("Rocket Balloon", 4, -4.0), ("Balloon", 2, 4.0)],
        main=[Wave("main", [("Ice Golem", 2), ("Root Rider", rr), ("Valkyrie", 8)], spread=2.0)],
        support=[Wave("main", [("Healer", 5), ("Apprentice Warden", 1)], spread=1.0)],
        push_heroes=["Archer Queen", "Grand Warden"],
        cleanup=[("Minion", minions), ("Archer", 2)],
        siege="Siege Barracks",
        cc_troops=["Super Hog Rider"] * 4 + ["Minion"] if town_hall == 16 else ["Super Hog Rider"] * 4 + ["Minion"] * 3 + ["Archer"],
        spells={"invis": 5, "recall": 1, "freeze": 1, "poison": 1, "overgrowth": 1},
        cc_spells={"rage": 1, "totem": 1} if town_hall < 18 else {"rage": 1, "totem": 2},
        loadouts={
            "Royal Champion": L("Royal Champion", ("Rocket Spear", "Electro Boots"), "Unicorn"),
            "Dragon Duke": L("Dragon Duke", ("Revenge Deck", "Fire Heart"), "Phoenix"),
            "Archer Queen": L("Archer Queen", ("Action Figure", "Giant Arrow"), "Frosty"),
            "Grand Warden": L("Grand Warden", ("Eternal Tome", "Rage Gem"), "Poison Lizard"),
        },
        main_min=8.0, main_max=18.0,
    )


ARMIES = {"hydra": hydra, "throwers": throwers, "edrag": edrag, "rootrider": root_riders}
META_WEIGHTS = {"hydra": 0.271, "throwers": 0.260, "edrag": 0.115, "rootrider": 0.097}
