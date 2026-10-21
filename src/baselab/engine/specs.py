"""Behaviour specifications for every attacking unit, pet and summon.

Numbers (HP, damage, range, speed, attack interval, housing) come from the
registry at the requested level. This table adds what the stat tables do not
say: targeting, wall handling, attack shape and special abilities, each taken
from the unit's wiki page (mirrored 2026-10-15; see docs/WIKI_DIGEST.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import stats


@dataclass(frozen=True)
class UnitSpec:
    name: str
    prefer: str = "any"  # any defense air_defense resource wall heroes support th rubble follow none
    walls: str = "normal"  # normal | ignore | smash | fly
    attack: str = "single"  # single splash spin chain bounce pierce beam heal heal_chain suicide none
    splash: float = 0.0
    splash_ground_only: bool = False
    chain: int = 0  # extra targets after the first
    chain_range: float = 3.0
    chain_decay: float = 0.8
    chain_from_primary: bool = False
    bounces: int = 0  # bowlers
    bounce_gap: float = 3.0
    pierce: float = 0.0
    vs_walls: float = 1.0
    vs_resources: float = 1.0
    vs_defenses: float = 1.0
    vs_heroes: float = 1.0
    vs_buildings: float = 1.0
    engages_units: bool = True
    death_damage: str | None = None  # registry column for death damage
    death_radius: float = 0.0
    death_delay: float = 0.0
    death_freeze: str | None = None  # registry column for freeze time
    death_freeze_radius: float = 0.0
    death_spawn: tuple = ()  # (summon name, registry column or int count)
    special: tuple = ()  # names of special hooks implemented in units.py
    heal_air: bool = False
    flying_override: bool | None = None
    notes: str = ""


S = UnitSpec

SPECS: dict[str, UnitSpec] = {
    s.name: s
    for s in [
        # ---------------- Elixir troops
        S("Barbarian"),
        S("Archer"),
        S("Giant", prefer="defense"),
        S("Goblin", prefer="resource", vs_resources=2.0),
        # The wiki's 2-tile "Damage Radius" is the one wiki radius that does not
        # copy the game data (Balloon, Valkyrie, Golem, Dragon Rider, Super Wall
        # Breaker, Super Bowler, Stone Slammer... all equal Radius/100). The blast
        # is centred on the target wall (no SelfAsAoeCenter); radii reach target
        # edges, so 0.8 covers the target wall and its eight neighbours.
        # game data v18.200.9: Wall Breaker.DamageRadius=80 -> 0.8 tiles around the target.
        # game data v18.200.9: Wall Breaker.DieDamageRadius=150 -> 1.5 tiles around himself.
        S("Wall Breaker", prefer="wall", attack="suicide", splash=0.8, vs_walls=40.0, death_damage="Damage when destroyed", death_radius=1.5),
        # game data v18.200.9: Balloon.DieDamageDelay=416 -> the death bomb lands 0.416 s later.
        S("Balloon", prefer="defense", walls="fly", attack="splash", splash=1.2, splash_ground_only=True, engages_units=False, death_damage="Damage Upon Death", death_radius=1.2, death_delay=0.416),
        S("Wizard", attack="splash", splash=0.3),
        S("Healer", prefer="support", walls="fly", attack="heal", splash=1.5, engages_units=False),
        S("Dragon", walls="fly", attack="splash", splash=0.3),
        S("P.E.K.K.A"),
        S("Baby Dragon", walls="fly", attack="splash", splash=0.3, special=("tantrum",)),
        S("Miner", walls="ignore", special=("burrow",)),
        S("Electro Dragon", walls="fly", attack="chain", chain=4, chain_range=3.0, chain_decay=0.8, special=("death_bolts",)),
        S("Yeti", special=("yetimites",)),
        # game data v18.200.9: Dragon Rider.DieDamageDelay=600 -> death damage 0.6 s after death.
        S("Dragon Rider", prefer="defense", walls="fly", engages_units=False, death_damage="Damage Upon Death", death_radius=2.0, death_delay=0.6),
        S("Electro Titan", special=("titan_aura",)),
        S("Root Rider", prefer="defense", walls="smash", engages_units=False),
        S("Thrower"),
        # ---------------- Dark troops
        S("Minion", walls="fly"),
        S("Hog Rider", prefer="defense", walls="ignore", engages_units=False),
        S("Valkyrie", attack="spin", splash=1.0),
        S("Golem", prefer="defense", engages_units=False, death_damage="Damage Upon Death", death_radius=1.5, death_spawn=("Golemite", "Golemites spawned Upon Death")),
        S("Witch", attack="splash", splash=0.3, special=("witch_skeletons",)),
        # The wiki mirror states no death radius ("a small amount of damage in
        # the area"; the earlier 3.5 had no source).
        # game data v18.200.9: Lava Hound.DieDamageRadius=120 -> 1.2 tiles.
        S(
            "Lava Hound",
            prefer="air_defense",
            walls="fly",
            engages_units=False,
            death_damage="Damage Upon Death",
            death_radius=1.2,
            death_spawn=("Lava Pup", "Lava Pups Spawned (After Death) / On Offense"),
        ),
        # game data v18.200.9: Bowler.DamageRadius=30 -> 0.3 tiles.
        # game data v18.200.9: Bowler.ChainShootingDistance=400 -> 4 tiles.
        S("Bowler", attack="bounce", splash=0.3, bounces=1, bounce_gap=4.0),
        S("Ice Golem", prefer="defense", engages_units=False, death_freeze="Freeze Time After Death / On Offense", death_freeze_radius=7.5, special=("chill",)),
        S("Headhunter", prefer="heroes", walls="ignore", vs_heroes=4.0, special=("hh_poison",)),
        S("Apprentice Warden", prefer="follow", walls="ignore", special=("life_aura",)),
        # Wiki: Druid, "bounce between up to 4 targets" (chain=3 extra). The
        # game data's count does not settle it: ProjectileBounces is the
        # total impact count for the Bowler (2 -> two hits) and Super Bowler
        # (3 -> three), which would make the Druid's 3 three recipients.
        # game data v18.200.9: Druid.ProjectileBounces=3 -> 3 (meaning unresolved).
        S("Druid", prefer="support", walls="ignore", attack="heal_chain", chain=3, heal_air=True, engages_units=False, special=("bear_after",)),
        S("Furnace", prefer="none", attack="none", engages_units=False, special=("furnace",)),
        # Wiki: Meteor Golem deals fivefold damage to walls.
        S(
            "Meteor Golem",
            attack="splash",
            splash=1.0,
            vs_walls=5.0,
            special=("meteormites",),
        ),
        S("Ruin Witch", prefer="rubble", attack="none", engages_units=False, special=("ruin_witch",)),
        # ---------------- Super troops
        S("Super Barbarian", special=("start_rage",)),
        # Pierce reach left at the wiki's 11.5 tiles ("arrow range of 11.5
        # tiles", infobox "12 (Projectile)"). The game data gives
        # AttackRange 600 + PenetratingExtraRange 400; whether the extra range
        # runs from the archer's 6-tile reach (10 tiles to a footprint edge,
        # i.e. 11.5 to a 3x3 centre) or from the target centre is not stated,
        # and the wiki also says the arrow travels a fixed distance.
        # game data v18.200.9: Super Archer.PenetratingExtraRange=400 -> 4 tiles past attack range.
        S("Super Archer", attack="pierce", pierce=11.5),
        S("Super Giant", prefer="defense", vs_walls=5.0),
        S("Sneaky Goblin", prefer="resource", vs_resources=2.0, special=("cloak",)),
        # The wiki's 1.6 tiles is the Mega Bomb (death) radius; the arrival
        # blast is the Wall Breaker's, centred on the target wall.
        # game data v18.200.9: Super Wall Breaker.DamageRadius=80 -> 0.8 tiles around the target.
        # game data v18.200.9: Super Wall Breaker.DieDamageRadius=160 -> 1.6 tiles around himself.
        S("Super Wall Breaker", prefer="wall", attack="suicide", splash=0.8, vs_walls=40.0, death_damage="Damage when destroyed", death_radius=1.6, special=("mega_bomb",)),
        # game data v18.200.9: Rocket Balloon.DieDamageDelay=416 -> the death bomb lands 0.416 s later.
        S(
            "Rocket Balloon",
            prefer="defense",
            walls="fly",
            attack="splash",
            splash=1.2,
            splash_ground_only=True,
            death_damage="Damage Upon Death",
            death_radius=1.2,
            death_delay=0.416,
            special=("boosters",),
        ),
        S("Super Wizard", attack="chain", chain=9, chain_range=3.0, chain_decay=0.4, chain_from_primary=True),
        # The wiki's "about 1-tile radius" with its 21-tile shape (5x5 less the
        # corners) is exactly a 1.6 radius from a tile centre measured to tile
        # edges; units.py applies that footprint (_dragon_footprint).
        # game data v18.200.9: Super Dragon.DamageRadius=160 -> 1.6 tiles.
        S("Super Dragon", walls="fly", attack="splash", splash=1.6, special=("burst",)),
        S("Inferno Dragon", walls="fly", attack="beam"),
        S("Super Minion", walls="fly", special=("long_shot",)),
        S("Super Valkyrie", attack="spin", splash=1.0, special=("death_rage",)),
        S("Super Witch", attack="splash", splash=0.3, special=("big_boy",)),
        S(
            "Ice Hound",
            prefer="air_defense",
            walls="fly",
            death_freeze="Freeze Time when Destroyed",
            death_freeze_radius=4.0,
            death_spawn=("Ice Pup", "Ice Pups Spawned / On Offense"),
            special=("ice_chill",),
        ),
        S("Super Bowler", attack="bounce", splash=0.6, bounces=2, bounce_gap=3.0),
        # game data v18.200.9: Super Miner.DieDamageDelay=1000 -> death damage 1 s after death.
        S("Super Miner", walls="ignore", attack="beam", special=("burrow",), death_damage="Damage when Destroyed", death_radius=2.0, death_delay=1.0),
        S("Super Hog Rider", prefer="defense", walls="ignore", special=("hog_split",)),
        S("Super Yeti", special=("electromites",)),
        # ---------------- Siege machines
        S("Wall Wrecker", prefer="th", vs_walls=10.0, engages_units=False, special=("siege_cc",)),
        S("Battle Blimp", prefer="th", walls="fly", attack="none", engages_units=False, special=("siege_cc", "blimp_bombs")),
        # Two hitboxes (wiki: "1 and 3 tile Radius"); units.py applies both.
        # game data v18.200.9: Stone Slammer.DamageRadius=100 -> 1-tile primary hitbox.
        # game data v18.200.9: Stone Slammer.Damage2Radius=300 -> 3-tile secondary hitbox.
        # game data v18.200.9: Stone Slammer.DieDamageRadius=300 -> 3 tiles.
        # game data v18.200.9: Stone Slammer.DieDamageDelay=416 -> death damage 0.416 s after death.
        S(
            "Stone Slammer",
            prefer="defense",
            walls="fly",
            attack="splash",
            splash=1.0,
            engages_units=False,
            death_damage="Damage when Destroyed",
            death_radius=3.0,
            death_delay=0.416,
            special=("siege_cc",),
        ),
        S("Siege Barracks", prefer="none", attack="none", engages_units=False, special=("siege_cc", "siege_barracks")),
        S(
            "Log Launcher",
            prefer="th",
            attack="none",
            vs_walls=4.0,
            engages_units=False,
            special=("siege_cc", "logs"),
        ),
        # Impact splash (the 22 s flame field is a separate spell, not modelled).
        # game data v18.200.9: Flame Flinger.DamageRadius=100 -> 1 tile around the target.
        # game data v18.200.9: Flame Flinger.DamageMultiplierPercent=800 -> x8 to walls.
        S("Flame Flinger", prefer="defense", attack="splash", splash=1.0, vs_walls=8.0, engages_units=False, special=("siege_cc", "flinger")),
        S("Battle Drill", prefer="defense", walls="ignore", engages_units=False, special=("siege_cc", "burrow", "drill_stun")),
        S("Troop Launcher", prefer="none", attack="none", engages_units=False, special=("siege_cc", "troop_launcher")),
        S("Sky Wagon", prefer="defense", walls="fly", attack="none", engages_units=False, special=("siege_cc", "sky_wagon")),
        # ---------------- Summons
        S("Lava Pup", walls="fly"),
        S("Golemite", prefer="defense", engages_units=False, death_damage="Damage Upon Death", death_radius=1.2),
        # Wiki: Yeti/Yetimite gives fourfold defense and half resource damage.
        S(
            "Yetimite",
            prefer="defense",
            walls="ignore",
            attack="splash",
            splash=0.8,
            vs_defenses=4.0,
            vs_resources=0.5,
        ),
        S(
            "Electromite",
            prefer="building",
            walls="ignore",
            attack="chain",
            chain=2,
            chain_range=3.0,
            chain_decay=0.8,
            vs_buildings=4.0,
        ),
        S("Big Boy"),
        S("Ruin Knight", vs_walls=3.0),  # Wiki: Ruin Witch/Ruin Knight.
        S(
            "Firemite", walls="ignore", attack="splash", splash=0.8
        ),  # Wiki: Furnace/Firemite.
        S("Bear", prefer="defense"),
        # ---------------- TH18 Guardians (defend from the Town Hall)
        # game data v18.200.9: Longshot.DieDamageDelay=200 -> death damage 0.2 s after death.
        S("Longshot", attack="splash", splash=1.0, death_damage="Damage Upon Death", death_radius=3.5, death_delay=0.2, special=("guardian",)),
        S("Smasher", attack="splash", splash=2.5, special=("guardian", "smasher")),
        S("Logger", attack="splash", splash=1.5, special=("guardian", "logger")),
        S("Ice Pup", walls="fly", special=("ice_chill",)),
        S("Meteormite", walls="ignore"),  # Wiki: Meteor Golem/Meteormite.
        # Wiki: Frosty/Frostmite.
        # game data v18.200.9: Icemite.DamageRadius=80 -> 0.8 tiles.
        S("Frostmite", prefer="defense", walls="ignore", splash=0.8),
        S("Skeleton"),
        S("Spell Skeleton"),
        S("Bat", prefer="defense", walls="fly", engages_units=False),
        S("Snake", walls="ignore"),
        S("Super Rider", vs_walls=2.0),  # Wiki: Super Hog Rider/Super Rider.
        S("Super Hog", prefer="defense", walls="ignore"),
        S("Henchman", walls="ignore"),
        # The engine's "Lavaloon" is the Lavaloon Puppet summon (heroes.py);
        # the event troop's row has the same radius. Bombs: heroes.summon_tick.
        # game data v18.200.9: GW Equipment Lavaloon.DamageRadius=180 -> 1.8 tiles.
        # game data v18.200.9: GW Equipment Lavaloon.SelfAsAoeCenter=TRUE -> centred on itself.
        S("Lavaloon", prefer="defense", walls="fly", attack="splash", splash=1.8, engages_units=False),
        S("Booger"),
        # game data v18.200.9: Giant Giant.DamageRadius=150 -> 1.5 tiles.
        S(
            "Giant Giant",
            prefer="defense",
            attack="splash",
            splash=1.5,
            engages_units=False,
            vs_walls=2.0,
        ),
        # ---------------- Heroes (equipment handled in heroes.py)
        S("Barbarian King"),
        S("Archer Queen"),
        S("Grand Warden", prefer="follow", walls="ignore"),
        S("Royal Champion", prefer="defense", walls="ignore"),
        S("Minion Prince", walls="fly"),
        S("Dragon Duke", walls="fly", special=("royal_rampage",)),
    ]
}


def spec(name: str) -> UnitSpec:
    if name in ("Royal Ghost", "Battle Ram", "M.E.C.H.A"):
        # Their event abilities need an explicit implementation (individual wiki pages).
        raise ValueError(f"Unsupported temporary troop: {name}")
    if name in SPECS:
        return SPECS[name]
    if name in stats.registry():
        sp = generic_spec(name)
        SPECS[name] = sp
        return sp
    raise KeyError(f"no behaviour spec for {name}")


def generic_spec(name: str) -> UnitSpec:
    """Behaviour inferred from the wiki infobox for limited-time event troops
    that have no hand-written spec: preferred target, flying, splash. Their
    special abilities are not modelled (notes='generic')."""
    a = stats.attrs(name)
    pref_text = (a.get("preferred_target") or "").lower()
    if "defense" in pref_text:
        prefer = "defense"
    elif "resource" in pref_text:
        prefer = "resource"
    elif "wall" in pref_text:
        prefer = "wall"
    else:
        prefer = "any"
    atk = (a.get("attack_type") or "").lower()
    splash = 1.0 if "splash" in atk else 0.0
    walls = "fly" if a.get("is_flying") else "normal"
    return UnitSpec(name, prefer=prefer, walls=walls, attack="splash" if splash else "single", splash=splash, notes="generic")


# Effective housing does not make these summons deployable or donatable.
SUBTROOP_HOUSING = {
    "Spell Skeleton": 1,  # Wiki: Skeleton Spell/Skeleton.
    "Bat": 1,  # Wiki: Bat Spell/Bat.
    "Frostmite": 1,  # Wiki: Clone Spell.
    "Yetimite": 2,  # Wiki: Yeti/Yetimite.
    "Meteormite": 20,  # Wiki: Meteor Golem/Meteormite.
    "Golemite": 6,  # Wiki: Golem/Golemite.
    "Skeleton": 1,  # Wiki: Skeleton.
    # game data v18.200.9: Lava Pup.HousingSpace=1 -> 1 housing space.
    "Lava Pup": 1,
    "Bear": 10,  # Wiki: Druid/Bear.
    "Firemite": 1,  # Wiki: Furnace/Firemite.
    "Big Boy": 20,  # Wiki: Super Witch/Big Boy.
    "Witch Golem Big Boy": 20,  # Wiki: Witch Golem/Big Boy.
    "Super Hog": 5,  # Wiki: Super Hog Rider/Super Hog.
    "Super Rider": 5,  # Wiki: Super Hog Rider/Super Rider.
    "Electromite": 3,  # Wiki: Super Yeti/Electromite.
    "Ice Pup": 1,  # Wiki: Ice Hound/Ice Pup.
    "Lavaloon Pup": 1,  # Wiki: Lavaloon/Lavaloon Pup.
    "Witch Golem Skeleton": 1,  # Wiki: Witch Golem/Skeleton.
}


def movement_speed(name):
    # Wiki: Troop Movement Speed, exact tiles per second.
    exact = {
        "Giant Giant": 1.65,
        "Mighty Yak": 2.5,
        "Log Launcher": 0.625,
        "Flame Flinger": 0.75,
    }
    if name in exact:
        return exact[name]
    a = stats.attrs(name)
    # Keep internal precision; conflicting display values remain in the registry.
    if a.get("speed") is not None:
        return a["speed"]
    display = a.get("speed_display")
    return display / 8.0 if display is not None else 0.0


def attack_range(name):
    # Individual wiki pages: Range or Attack Range precedes extracted reach.
    a = stats.attrs(name)
    raw = a.get("raw", {})
    for key in ("Range", "Attack Range"):
        value = stats.num(raw.get(key))
        if value is not None:
            return value
    for key in ("range", "range_ck"):
        if a.get(key) is not None:
            return a[key]
    return None


def unit_numbers(name: str, level: int) -> dict:
    """Read wiki numbers first, using game data only for missing values."""
    a = stats.attrs(name)
    # Game data first for hitpoints and DPS (stats.get prefers it under the
    # lowercase keys; the wiki columns are the fallback). This also covers the
    # wiki's Inferno Dragon table, which repeats level 11.
    hp = stats.get(name, level, "hitpoints", "Hitpoints", default=0.0)
    interval = a.get("attack_interval")
    if interval is None:
        interval = a.get("attack_interval_ck")
    if interval is None:
        interval = 1.0
    wiki_dps = stats.get(
        name,
        level,
        "Damage per Second",
        "Damage per Second / Initial",
        "~damage per second",
        default=None,
    )
    dps = stats.get(name, level, "dps", default=None)
    if dps is None:
        dps = wiki_dps
    dmg = stats.get(
        name,
        level,
        "Damage per Hit",
        "Damage per Attack",
        "Damage per Hit (Primary Target)",
        "Damage per Hit (Primary)",
        "Damage per Hit / Hitbox 1",  # Wiki: Stone Slammer.
        "Damage per Hit*",  # Wiki: Sky Wagon and Ruin Witch.
        "Damage per Shot",
        "Damage",
        default=None,
    )
    if dmg is None and dps is not None:
        dmg = abs(dps) * interval
    elif (
        dmg is not None
        and dps is not None
        and wiki_dps
        and dps > 0
        and abs(dps - wiki_dps) > max(1.0, 0.02 * dps)
    ):
        # The wiki's per-hit column belongs to its DPS column; where game
        # data's DPS differs (e.g. Flame Flinger L1 127 vs 124, Barbarian King
        # L1 102 vs 51) scale the hit so damage per second follows game data.
        dmg *= dps / wiki_dps
    if dps is not None and dps < 0:  # healers carry negative DPS in game data
        dmg = 0.0
    rng = attack_range(name)
    if name == "Booger":
        # game data v18.200.9: Booger.AttackRange=90 -> 0.9 tiles.
        rng = 0.9
    if name == "Bear":
        # The wiki's 0.2 tiles is out of line with every other melee reach,
        # which copies AttackRange/100 (Super Barbarian 0.6, Hog Rider 0.6).
        # game data v18.200.9: Bear.AttackRange=60 -> 0.6 tiles.
        rng = 0.6
    if name == "Healer":
        # Wiki: Healer gives 5 tiles; ClashKing's 450/100 gives 4.5.
        rng = 5.0
        interval = 0.7  # Heal speed (wiki: Healer).
    speed = movement_speed(name)
    housing = SUBTROOP_HOUSING.get(name, a.get("housing"))
    if housing is None:
        housing = a.get("housing_ck")
    if name == "Druid":
        interval = stats.num(a["raw"]["Heal Speed"])  # Wiki: Druid.
    flying = a.get("is_flying")
    hits_air = a.get("is_air_targeting")
    hits_ground = a.get("is_ground_targeting")
    if flying is None or hits_air is None:
        at = (a.get("attack_type") or "").lower() + " " + (a.get("targets_text") or "").lower()
        hits_air = "air" in at if hits_air is None else hits_air
        hits_ground = ("ground" in at or "air" not in at) if hits_ground is None else hits_ground
        flying = bool(flying)
    if name == "Yetimite":
        # Wiki: Yeti/Yetimite explicitly attacks both air and ground.
        hits_air = hits_ground = True
    return {
        "hp": float(0.0 if hp is None else hp),
        "dmg": float(0.0 if dmg is None else dmg),
        "dps": float(0.0 if dps is None else dps),
        "interval": float(interval),
        "range": float(0.5 if rng is None else rng),
        "speed": float(0.0 if speed is None else speed),
        "housing": int(0 if housing is None else housing),
        "flying": bool(flying),
        "hits_air": bool(hits_air),
        "hits_ground": bool(hits_ground),
    }
