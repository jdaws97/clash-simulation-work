"""Inputs and checks for the Rust engine port (rust/).

The Python engine stays the reference. Production jobs export only prepared
layouts, constructed plans and options; Rust builds and runs their battles.
Battle-state exports remain the reference for setup and tick parity. Static
data comes from a catalog regenerated after every game patch.

  catalog --out rust/data/catalog.json
      the processed registry (stats.registry(), what stats.get reads), every
      unit spec and summon spec, unit_numbers for every unit at every level,
      and the building/trap tables from mechanics.py
  battle  --stage S --k K --out output/parity/battle-S-K.json
      starting state of parity scenario K of stage S (see SCENARIOS)
  trace   --stage S --k K --out output/parity/trace-py-S-K.txt
      the Python engine's per-tick trace of that battle, compared with the
      Rust trace by tools/baselab/trace_diff.py
  jobs --stage S --n N --out output/parity/jobs.json
      prepared layouts/plans/options without constructing Python battles
  parity-setup --stage S --n N
      compare Rust setup field by field, then compare every trace tick
      stage 6: --n 40 covers five troop/siege armies, two bases and four sides
      stage 7: --n 184 covers 23 hero loadouts, two bases and four sides
      stage 8: --n 1584 covers 34 scripted meta builds (99 build/charge pairs),
               four STAGE4_BASES and four sides, including observed Witch/PEKKA

Trace format, one record per line: `T <t>` before each step, then after it
`U <team> <id> <name> <x> <y> <hp>` for every living unit (attackers then
defenders, list order), `B <id> <hp>` for each building whose hp changed,
`W <tx> <ty> <hp>` for walls, `E <log entry>` for new log events. Floats
are written as the 16 hex digits of their IEEE-754 bits (exact; the diff
tool decodes them).

Usage: python tools/baselab/rust_export.py catalog|battle|trace ...
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import struct
import sys
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

os.environ.setdefault("BASELAB_PLAYBOOKS", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))


def fbits(x) -> str:
    return "%016x" % struct.unpack("<Q", struct.pack("<d", float(x)))[0]


# ------------------------------------------------------------------ generic dump
def dump(obj, depth=0):
    """baselab.rust_bridge.dump (the one exporter of engine objects)."""
    from baselab.rust_bridge import dump as bridge_dump

    return bridge_dump(obj, depth)


# ------------------------------------------------------------------ catalog
def catalog():
    from data_manifest import file_hash

    from baselab import mechanics
    from baselab.engine import (
        battle,
        defense,
        heroes,
        plans,
        playbook,
        specs,
        spells,
        stats,
        traps,
    )
    from baselab.engine import units as engine_units

    reg = stats.registry()
    units, numbers = {}, {}
    for name, rec in reg.items():
        if (
            rec.get("kind")
            in ("troop", "super_troop", "siege", "hero", "pet", "summon", "spell")
            or name in specs.SPECS
        ):
            try:
                sp = specs.spec(name)
            except Exception:  # noqa: BLE001 - names without a spec are not units
                continue
            units[name] = {
                "spec": dump(sp),
                "summon_spec": dump(heroes.summon_spec(name, sp)),
            }
            for entry in rec.get("levels", []):
                level = entry.get("level")
                if isinstance(level, int):
                    try:
                        numbers[f"{name}|{level}"] = dump(
                            specs.unit_numbers(name, level)
                        )
                    except Exception:  # noqa: BLE001 - incomplete rows stay absent
                        pass
    # specs.py:352-386 owns CSV inheritance and level clamping. Export its
    # resolved rows, so Rust reads the same data without a second CSV reader.
    game_tables = {}
    for table in (
        "buildings",
        "characters",
        "heroes",
        "pets",
        "projectiles",
        "special_abilities",
        "spells",
    ):
        specs.game_data(table, "")
        game_tables[table] = specs._GAME_TABLES[table]
    # heroes.py constructs pets directly, bypassing unit_numbers. Preserve
    # its range_ck fallback separately from the troop game-range override.
    pet_spawn_ranges = {
        name: stats.attrs(name).get("range_ck", specs.attack_range(name))
        for name, rec in reg.items()
        if rec.get("kind") == "pet"
    }
    # Export the reference helpers' resolved values. Rust must not repeat the
    # ClashKing/CSV precedence rules or infer equipment ability levels itself.
    ability_sources = {
        "Fire Heart": ("DragonCrownRegeneration", 1),
        "Noble Iron": ("MPTurboStart", 0),
        "Giant Arrow": ("ArcherQueenPierceProjectile", 0),
        "Eternal Tome": ("GrandWardenInvulnerability", 0),
        "Heroic Torch": ("GWHeroicTorch", 0),
        "Rocket Backpack": ("DragonDukeDeadlyDashMapCenter", 0),
        "Rage Vial": ("BarbarianKingRage", 0),
    }
    equipment_abilities = {
        f"{name}|{entry['level']}": heroes._ability_data(
            name, entry["level"], csv_name, index=index
        )
        for name, (csv_name, index) in ability_sources.items()
        for entry in reg[name].get("levels", [])
        if isinstance(entry.get("level"), int)
    }
    radius_defaults = {
        "Lightning Spell": 2.0,
        "Earthquake Spell": 4.7,
        "Jump Spell": 3.5,
        "Haste Spell": 4.0,
        "Skeleton Spell": 2.25,
        "Bat Spell": 2.25,
        "Totem Spell": 5.0,
    }
    spell_radii = {
        f"{name}|{entry['level']}": spells._radius(name, entry["level"], default)
        for name, default in radius_defaults.items()
        for entry in reg[name].get("levels", [])
        if isinstance(entry.get("level"), int)
    }
    spell_tower_profiles = {}
    for required in sorted(set(defense.SPELL_TOWER_UNLOCKS.values())):
        profile = stats.clashking_level("Spell Tower", required)
        spell_tower_profiles[str(required)] = {
            "range": profile.get("attack_range", 900) / 100.0,
            "interval": profile.get("attack_speed", 70000) / 1000.0,
        }
    mortar_alternates = {}
    for entry in reg["Mortar"].get("levels", []):
        level = entry.get("level")
        if not isinstance(level, int) or level < defense.GEAR_MINIMUM["mortar"]:
            continue
        row = specs.game_data("buildings", "Mortar", level)
        alternate = stats.clashking_level("Mortar", level).get("alt", {})
        mortar_alternates[str(level)] = {
            "interval": alternate.get("attack_speed", int(row["AltAttackSpeed"]))
            / 1000.0,
            "dps": alternate.get("dps", int(row["AltDPS"])),
        }
    return {
        "game_data": game_tables,
        "note": "Rust engine catalog, exported by tools/baselab/rust_export.py catalog",
        "registry": reg,
        "units": units,
        "unit_numbers": numbers,
        "building_types": {k: dump(v) for k, v in mechanics.BUILDING_TYPES.items()},
        # tables the engine reads from data files mid-battle
        "new_target_delays": engine_units._new_target_delays(),
        "warden_weights": engine_units.warden_weights(),
        "poison_ramp": spells.POISON_RAMP,
        "game_ranges": specs._game_ranges(),
        "pet_spawn_ranges": pet_spawn_ranges,
        "resolved": {
            # The embedded registry includes runtime balance overrides.
            "source_hashes": {
                "registry": file_hash(stats.REGISTRY),
                "balance_overrides": file_hash(stats.BALANCE_OVERRIDES),
            },
            "equipment_abilities": equipment_abilities,
            "revenge_ranges": {
                str(entry["level"]): float(
                    stats.clashking_level("Revenge Deck", entry["level"])["abilities"][
                        0
                    ]["ReflectedRange"]
                )
                / 100.0
                for entry in reg["Revenge Deck"].get("levels", [])
                if isinstance(entry.get("level"), int)
            },
            "scatter_intervals": {
                str(entry["level"]): stats.clashking_level(
                    "Scattershot", entry["level"]
                )["attack_speed"]
                / 1000.0
                for entry in reg["Scattershot"].get("levels", [])
                if isinstance(entry.get("level"), int)
            },
            "spell_radii": spell_radii,
            "zap_radii": {
                f"{name}|{entry['level']}": spells._radius(name, entry["level"], 0.0)
                for name in ("Lightning Spell", "Earthquake Spell")
                for entry in reg[name].get("levels", [])
                if isinstance(entry.get("level"), int)
            },
            "pet_spawn_speeds": {
                name: specs.movement_speed(name) for name in pet_spawn_ranges
            },
            "spell_tower_profiles": spell_tower_profiles,
            "mortar_alternates": mortar_alternates,
        },
        "trap_names": dump(mechanics.TRAP_NAMES),
        "trap_sizes": dump(mechanics.TRAP_SIZES),
        "world": mechanics.WORLD,
        "margin": mechanics.MARGIN,
        "setup": {
            "modifiers": dump(battle.MODIFIERS),
            "inferno_artillery": dump(defense.INFERNO_ARTILLERY),
            "giga_inferno": dump(defense.GIGA_INFERNO),
            "facings": dump(defense.FACINGS),
            "crafted": dump(defense.CRAFTED),
            "ammunition": dump(defense.AMMUNITION),
            "spell_tower_unlocks": dump(defense.SPELL_TOWER_UNLOCKS),
            "gear_minimum": dump(defense.GEAR_MINIMUM),
            "geared_cannon_offsets": dump(defense.GEARED_CANNON_OFFSETS),
            "gear_archer_shots": dump(defense.FAST_ARCHER_SHOTS),
            "artillery_damage": dump(defense.ARTILLERY_DAMAGE),
            "crafting": {
                "phase": defense.CRAFTING_PHASE,
                "start": defense.CRAFTING_WINDOW[0],
                "end": defense.CRAFTING_WINDOW[1],
                "modes": dump(defense.CRAFTED_MODES),
            },
            "cargo_order": dump(engine_units.CARGO_ORDER),
            "default_loadouts": dump(heroes.DEFAULT_LOADOUTS),
            "trap_fuse": dump(traps.FUSE),
            "trap_no_trigger": dump(traps.NO_TRIGGER),
            "donated_laboratory": {
                name: {
                    str(entry["level"]): battle._required_lab(
                        battle._research_name(name), entry["level"]
                    )
                    for entry in reg[name].get("levels", [])
                    if isinstance(entry.get("level"), int)
                }
                for name in units
            },
            "siege_donation_caps": dump(plans._siege_donation_caps()),
            "env": {
                "dt": battle.DT,
                "fast_end": battle.FAST_END,
                "windup": engine_units.WINDUP,
                "flyer_range": os.environ.get("BASELAB_FLYER_RANGE", "gamedata"),
                "pace": float(os.environ.get("BASELAB_PACE", "1.0")),
                "pace_tap": playbook.PACE_TAP,
                "pace_switch": playbook.PACE_SWITCH,
                "pace_ability": playbook.PACE_ABILITY,
            },
        },
    }


# ------------------------------------------------------------------ battles
def own_layout(path):
    from baselab.layout import Layout

    lv = json.loads((ROOT / "data" / "your-levels.json").read_text())
    lay = Layout.load(ROOT / path)
    lay.levels, lay.wall_level, lay.hero_levels = (
        dict(lv["levels"]),
        lv["wall_level"],
        dict(lv["hero_levels"]),
    )
    return lay


def edge_drops(army, angle, seed, gap=0.2):
    """Fixed drops along the edge facing `angle` (layout coords), like the
    Rust spike: [(time, name, x, y, level)]."""
    import random

    rng = random.Random(seed)
    out, k = [], 0
    for name, n in army:
        for i in range(n):
            lat = (i - (n - 1) / 2) * 1.2 + rng.uniform(-0.4, 0.4)
            x = 22.0 + math.cos(angle) * 23.5 - math.sin(angle) * lat
            y = 22.0 + math.sin(angle) * 23.5 + math.cos(angle) * lat
            out.append(
                (gap * k, name, min(43.5, max(0.5, x)), min(43.5, max(0.5, y)), None)
            )
            k += 1
    return out


# Stage 1: battle core, every defense and trap, Clan Castle defenders; plain
# troops dropped at fixed times; no heroes on either side, no spells.
STAGE1_ARMIES = [
    [("P.E.K.K.A", 4), ("Valkyrie", 16), ("Wizard", 12), ("Archer", 12)],
    [("Dragon", 10), ("Balloon", 10), ("Minion", 12)],
    [("Giant", 10), ("Valkyrie", 12), ("Dragon", 6), ("Wizard", 10), ("Barbarian", 12)],
]
STAGE4_BASES = [
    "data/reference-bases/your-base.json",
    "data/reference-bases/real-l6x.json",
    "data/reference-bases/real-l1x.json",
    "data/reference-bases/real-l3x.json",
]
STAGE1_BASES = [
    "data/reference-bases/your-base.json",
    "data/reference-bases/real-l6x.json",
]


# Stage 2: the rest of the user's armies' troops, their summons, and siege
# machines releasing attacker Clan Castle cargo (fixed drops, no heroes or
# spells): (army drops, siege, cargo).
STAGE2_ARMIES = [
    (
        [
            ("Ice Golem", 2),
            ("Root Rider", 4),
            ("Valkyrie", 8),
            ("Healer", 5),
            ("Apprentice Warden", 1),
        ],
        "Siege Barracks",
        ["Super Hog Rider"] * 4 + ["Minion"],
    ),
    (
        [
            ("Ice Golem", 1),
            ("Druid", 2),
            ("Ruin Witch", 2),
            ("Root Rider", 2),
            ("Valkyrie", 3),
            ("Healer", 5),
            ("Archer", 3),
        ],
        "Log Launcher",
        ["Ice Golem", "Ice Golem", "Root Rider"],
    ),
    (
        [
            ("Rocket Balloon", 6),
            ("Super Minion", 3),
            ("Balloon", 4),
            ("Minion", 6),
            ("Super Hog Rider", 4),
        ],
        None,
        [],
    ),
    (
        # attacking burn fields: Flame Flinger fire, Furnace Firemite pools
        [("Giant", 8), ("Furnace", 2), ("Wizard", 10), ("Archer", 10)],
        "Flame Flinger",
        ["Valkyrie", "Valkyrie"],
    ),
]


# Stage 6: declared synthetic coverage for the remaining ranked attacking
# troop paths. Fixed drops, siege and cargo; no heroes or spells. TH17 camp
# housing is 334/340/334/340/340; every cargo uses at most 55 housing.
# Run --stage 6 --n 40: five armies x both STAGE1_BASES x four sides.
STAGE6_ARMIES = [
    (
        # Witch skeleton caps/cooldowns, Super Witch Big Boys, Golem deaths.
        [("Golem", 3), ("Witch", 7), ("Super Witch", 4)],
        "Siege Barracks",
        ["Super Witch", "Witch", "Archer", "Archer", "Archer"],
    ),
    (
        # Super Dragon bursts/retargets/interruptions and Inferno Dragon beams.
        [("Super Dragon", 4), ("Inferno Dragon", 6), ("Balloon", 18)],
        "Stone Slammer",
        ["Inferno Dragon"] * 3 + ["Balloon"] * 2,
    ),
    (
        # Miner hiding/reburrowing, Super Miner beam ramps/deaths, Healer support.
        [("Miner", 24), ("Super Miner", 5), ("Healer", 5)],
        "Wall Wrecker",
        ["Super Miner", "Super Miner", "Miner", "Archer"],
    ),
    (
        # Ice Hound freezes/chill, both hounds' scattered pups, Blimp bombs/cargo.
        [("Ice Hound", 2), ("Lava Hound", 3), ("Balloon", 34)],
        "Battle Blimp",
        ["Balloon"] * 11,
    ),
    (
        # Battle Drill wall emergence/defense stuns and Bowler bounces.
        [("Golem", 4), ("Bowler", 30), ("Wizard", 10)],
        "Battle Drill",
        ["Bowler"] * 8 + ["Wizard", "Archer", "Archer", "Archer"],
    ),
]


# Stage 3: heroes on both sides, with the user's loadouts (equipment, pets);
# abilities fire through the plan's automatic on-KO use. Fixed drops: the
# heroes first, then the army; no spells. (army id, base)
STAGE3_ARMIES = ["custom:user-rr", "custom:user-druid-ruin"]


# Stage 7: declared synthetic fixed-drop equipment/pet coverage. Each row
# brings one attacking Hero, so a full village can force the automatic on-KO
# ability instead of a complete hero squad clearing it with unused abilities.
# All 43 equipment pieces and all 12 pets appear in this table. Each row runs
# eight times (two STAGE1_BASES x four sides), exceeding two uses per piece.
# Columns: Hero, equipment pair, pet. Attacker TH18 unlocks every listed pet;
# the defending villages retain their own TH16 content and defending Heroes.
STAGE7_LOADOUTS = [
    ("Barbarian King", ("Barbarian Puppet", "Rage Vial"), "Mighty Yak"),
    ("Barbarian King", ("Giant Gauntlet", "Vampstache"), "Sneezy"),
    ("Barbarian King", ("Spiky Ball", "Earthquake Boots"), "Greedy Raven"),
    ("Barbarian King", ("Snake Bracelet", "Stick Horse"), "Spirit Fox"),
    ("Archer Queen", ("Archer Puppet", "Invisibility Vial"), "Unicorn"),
    ("Archer Queen", ("Frozen Arrow", "Monolith Arrow"), "Electro Owl"),
    ("Archer Queen", ("Giant Arrow", "Healer Puppet"), "Phoenix"),
    ("Archer Queen", ("Magic Mirror", "Action Figure"), "Diggy"),
    ("Grand Warden", ("Eternal Tome", "Life Gem"), "Poison Lizard"),
    ("Grand Warden", ("Rage Gem", "Healing Tome"), "Frosty"),
    ("Grand Warden", ("Fireball", "Lavaloon Puppet"), "Angry Jelly"),
    ("Grand Warden", ("Heroic Torch", "Life Gem"), "L.A.S.S.I"),
    ("Royal Champion", ("Seeking Shield", "Royal Gem"), "Mighty Yak"),
    ("Royal Champion", ("Hog Rider Puppet", "Haste Vial"), "Sneezy"),
    ("Royal Champion", ("Rocket Spear", "Electro Boots"), "Greedy Raven"),
    ("Royal Champion", ("Frost Flake", "Royal Gem"), "Unicorn"),
    ("Minion Prince", ("Dark Crown", "Henchmen Puppet"), "Spirit Fox"),
    ("Minion Prince", ("Dark Orb", "Meteor Staff"), "Electro Owl"),
    ("Minion Prince", ("Metal Pants", "Noble Iron"), "Diggy"),
    ("Minion Prince", ("Portal Pendant", "Dark Crown"), "Phoenix"),
    ("Dragon Duke", ("Rocket Backpack", "Flame Blower"), "Angry Jelly"),
    ("Dragon Duke", ("Fire Heart", "Revenge Deck"), "L.A.S.S.I"),
    ("Dragon Duke", ("Electro Fangs", "Stun Blaster"), "Frosty"),
]
STAGE7_SIDES = 4
STAGE7_N = len(STAGE7_LOADOUTS) * len(STAGE1_BASES) * STAGE7_SIDES  # 184
STAGE8_SIDES = 4


@contextmanager
def scripted_plans():
    """Force the non-playbook scoring path, restoring the caller's setting."""
    previous = os.environ.get("BASELAB_PLAYBOOKS")
    os.environ["BASELAB_PLAYBOOKS"] = "0"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("BASELAB_PLAYBOOKS", None)
        else:
            os.environ["BASELAB_PLAYBOOKS"] = previous


@lru_cache(maxsize=1)
def stage8_cases():
    """Stage-5 ranked builds with every scripted technique, before side/base.

    Pin all three ranked Town Halls so local logs and BASELAB_TH_MIX cannot
    omit a family. The current catalog has 34 builds, including all 12 decoded
    observed builds (witch-17-1 and pekka-17-1), and 99 build/technique pairs.
    Full coverage is len(stage8_cases()) * len(STAGE4_BASES) * STAGE8_SIDES = 1584.
    These are synthetic parity scenarios, not real-game calibration.
    """
    from baselab.evaluate import meta_scenarios

    with scripted_plans():
        scenarios = meta_scenarios(
            "ranked",
            n_angles=1,
            seeds=(0,),
            th_mix={16: 1.0, 17: 1.0, 18: 1.0},
            techniques_on=True,
        )
    return tuple(dict.fromkeys((sc.army, sc.charge) for sc in scenarios))


def equipment_stage(loadout, angle, seed):
    """Synthetic Stage plan: fixed drops, capped levels, automatic KO ability."""
    from baselab.engine import stats
    from baselab.loadouts import HeroLoadout
    from mechanic_tests import Stage

    hero, equipment, pet = loadout
    town_hall = 18
    # Modest escorts give Life Gem/Healing Tome recipients and Dark Crown
    # deaths without replacing the isolated Hero with a full clearing army.
    troops = [("Giant", 6), ("Barbarian", 12), ("Archer", 12)]
    hero_level = stats.max_level(hero, town_hall)
    drops = edge_drops([(hero, 1)] + troops, angle, seed)
    drops = [
        (t, name, x, y, hero_level if name == hero else None)
        for t, name, x, y, _ in drops
    ]
    plan = Stage(drops, town_hall=town_hall)
    plan.loadouts = {hero: HeroLoadout(hero, equipment, pet)}
    plan.hero_levels = {hero: hero_level}
    plan.equipment_levels = {
        name: stats.max_level(name, town_hall) for name in equipment
    }
    plan.pet_levels = {pet: stats.max_level(pet, town_hall)}
    plan.troop_levels = {name: stats.max_level(name, town_hall) for name, _ in troops}
    plan.auto_ability_on_ko = True
    return plan


def hero_stage(army_id, angle, seed):
    """Stage plan carrying a real build's heroes, loadouts and levels."""
    from baselab.meta_armies import build_by_id, make_plan
    from mechanic_tests import Stage

    build = build_by_id(army_id)
    ref = make_plan(army_id, angle, 16, seed)
    heroes = list(build["heroes"])
    troops = [(name, n) for name, n in build["troops"].items()]
    siege = next(
        (
            name
            for name in build["cc"]
            if name
            in (
                "Siege Barracks",
                "Log Launcher",
                "Wall Wrecker",
                "Battle Blimp",
                "Stone Slammer",
                "Flame Flinger",
                "Battle Drill",
                "Troop Launcher",
            )
        ),
        None,
    )
    cargo = [
        name
        for name, n in build["cc"].items()
        for _ in range(int(n))
        if name != siege and not name.endswith("Spell")
    ]
    drops = edge_drops(
        [(h, 1) for h in heroes] + troops + ([(siege, 1)] if siege else []), angle, seed
    )
    drops = [(t, name, x, y, ref.hero_levels.get(name)) for t, name, x, y, _ in drops]
    plan = Stage(drops)
    for attr in (
        "loadouts",
        "hero_levels",
        "equipment_levels",
        "pet_levels",
        "troop_levels",
        "clan_castle_level",
        "auto_ability_on_ko",
    ):
        setattr(plan, attr, getattr(ref, attr))
    plan.cc_troops = cargo
    return plan


def scenario_inputs(stage, k):
    """Prepared layout, constructed plan and Battle options for a parity case."""
    from mechanic_tests import Stage

    if stage == 1:
        n_sides = 4
        army = STAGE1_ARMIES[k % len(STAGE1_ARMIES)]
        base = STAGE1_BASES[(k // len(STAGE1_ARMIES)) % len(STAGE1_BASES)]
        side = k // (len(STAGE1_ARMIES) * len(STAGE1_BASES)) % n_sides
        angle, seed = 2 * math.pi * side / n_sides + 0.1 + 0.37 * k, 200 + k
        lay = own_layout(base)
        lay.heroes = []
        return (
            lay,
            Stage(edge_drops(army, angle, seed)),
            {"seed": seed, "town_hall": 16},
        )
    if stage == 2:
        n_sides = 4
        army, siege, cargo = STAGE2_ARMIES[k % len(STAGE2_ARMIES)]
        base = STAGE1_BASES[(k // len(STAGE2_ARMIES)) % len(STAGE1_BASES)]
        side = k // (len(STAGE2_ARMIES) * len(STAGE1_BASES)) % n_sides
        angle, seed = 2 * math.pi * side / n_sides + 0.1 + 0.37 * k, 300 + k
        lay = own_layout(base)
        lay.heroes = []
        drops = edge_drops(army + ([(siege, 1)] if siege else []), angle, seed)
        plan = Stage(drops)
        plan.cc_troops = list(cargo)  # read by Battle._attack_cargo
        return lay, plan, {"seed": seed, "town_hall": 16}
    if stage == 3:
        n_sides = 4
        army = STAGE3_ARMIES[k % len(STAGE3_ARMIES)]
        base = STAGE1_BASES[(k // len(STAGE3_ARMIES)) % len(STAGE1_BASES)]
        side = k // (len(STAGE3_ARMIES) * len(STAGE1_BASES)) % n_sides
        angle, seed = 2 * math.pi * side / n_sides + 0.1 + 0.37 * k, 400 + k
        lay = own_layout(base)  # defending heroes stay on their banners
        return lay, hero_stage(army, angle, seed), {"seed": seed, "town_hall": 16}
    if stage == 4:
        # the user's real armies with their playbook plans and spells, set up
        # exactly like a scored battle (tools/baselab/fingerprint.py run_one)
        from baselab.evaluate import STRENGTH, skill
        from baselab.meta_armies import make_plan

        n_sides = 8
        army = STAGE3_ARMIES[k % len(STAGE3_ARMIES)]
        base = STAGE4_BASES[(k // len(STAGE3_ARMIES)) % len(STAGE4_BASES)]
        side = k // (len(STAGE3_ARMIES) * len(STAGE4_BASES)) % n_sides
        angle, seed = 2 * math.pi * side / n_sides + 0.1, 11 + k
        lay = own_layout(base)
        plan = make_plan(army, angle, 16, seed)
        plan.strength = STRENGTH.get(army, 1.0) * skill(seed)
        return lay, plan, {"seed": seed, "town_hall": 16}
    if stage == 5:
        # the ranked meta armies the base scorer uses (evaluate.meta_scenarios),
        # each with its real playbook plan, set up exactly like a scored battle
        from baselab.evaluate import STRENGTH, skill
        from baselab.meta_armies import make_plan

        armies = meta_armies()
        n_sides = 8
        army = armies[k % len(armies)]
        base = STAGE4_BASES[(k // len(armies)) % len(STAGE4_BASES)]
        side = k // (len(armies) * len(STAGE4_BASES)) % n_sides
        angle, seed = 2 * math.pi * side / n_sides + 0.1, 500 + k
        lay = own_layout(base)
        plan = make_plan(army, angle, 16, seed)
        plan.strength = STRENGTH.get(army, 1.0) * skill(seed)
        return lay, plan, {"seed": seed, "town_hall": 16}
    if stage == 6:
        n_sides = 4
        army, siege, cargo = STAGE6_ARMIES[k % len(STAGE6_ARMIES)]
        base = STAGE1_BASES[(k // len(STAGE6_ARMIES)) % len(STAGE1_BASES)]
        side = k // (len(STAGE6_ARMIES) * len(STAGE1_BASES)) % n_sides
        angle, seed = 2 * math.pi * side / n_sides + 0.1, 600 + k
        lay = own_layout(base)
        lay.heroes = []
        drops = edge_drops(army + [(siege, 1)], angle, seed)
        plan = Stage(drops, town_hall=17)
        plan.cc_troops = list(cargo)
        return lay, plan, {"seed": seed, "town_hall": 17}
    if stage == 7:
        loadout = STAGE7_LOADOUTS[k % len(STAGE7_LOADOUTS)]
        base = STAGE1_BASES[(k // len(STAGE7_LOADOUTS)) % len(STAGE1_BASES)]
        side = k // (len(STAGE7_LOADOUTS) * len(STAGE1_BASES)) % STAGE7_SIDES
        angle = 2 * math.pi * side / STAGE7_SIDES + 0.1
        seed = 700 + k
        lay = own_layout(base)
        return (
            lay,
            equipment_stage(loadout, angle, seed),
            {"seed": seed, "town_hall": 16},
        )
    if stage == 8:
        from baselab.engine.plans import AttackPlan
        from baselab.evaluate import STRENGTH, apply_charge, skill
        from baselab.meta_armies import make_plan

        cases = stage8_cases()
        army, charge = cases[k % len(cases)]
        base = STAGE4_BASES[(k // len(cases)) % len(STAGE4_BASES)]
        side = k // (len(cases) * len(STAGE4_BASES)) % STAGE8_SIDES
        angle, seed = 2 * math.pi * side / STAGE8_SIDES + 0.1, 800 + k
        lay = own_layout(base)
        with scripted_plans():
            plan = make_plan(army, angle, 16, seed)
            if charge is not None:
                apply_charge(plan, charge)
        assert type(plan) is AttackPlan, f"stage 8 requires AttackPlan: {army}"
        plan.strength = STRENGTH.get(army, 1.0) * skill(seed)
        return lay, plan, {"seed": seed, "town_hall": 16}
    raise ValueError(f"no stage {stage}")


def meta_armies():
    """The armies of the ranked scoring mix (evaluate.meta_scenarios)."""
    from baselab.evaluate import meta_scenarios

    return sorted({s.army for s in meta_scenarios("ranked", 4, (0,))})


def scenario(stage, k):
    """Construct the Python reference; jobs exports only need scenario_inputs."""
    from baselab.engine.battle import Battle

    layout, plan, options = scenario_inputs(stage, k)
    return Battle(layout, plan, **options)


def plan_json(plan):
    from baselab.rust_bridge import plan_json as bridge_plan_json

    return bridge_plan_json(plan)


def layout_json(layout):
    return layout.to_json()


def jobs_json(layouts, plans, jobs):
    """Export prepared data, without constructing any Python battles."""
    return {
        "layouts": [layout_json(layout) for layout in layouts],
        "plans": [plan_json(plan) for plan in plans],
        "jobs": [dict(job) for job in jobs],
    }


def battle_state(b):
    """Starting state of a constructed, not yet stepped Battle."""
    validate = getattr(b.plan, "require_legal", None)
    if validate is not None:
        validate()  # Resolve constructed spell-stock levels before the export.
    skip = {
        "plan",
        "log",
        "frames",
        "grid",
        "rng",
        "_bucket_grid",
        "deployments",
        "_dt_cache",
        "_nd_cache",
    }
    scalars = {}
    for k, v in vars(b).items():
        if k in skip or k in (
            "buildings",
            "walls",
            "traps",
            "attackers",
            "defenders",
            "fields",
            "pending",
        ):
            continue
        scalars[k] = dump(v, 1)
    from baselab.engine import battle as B
    from baselab.engine import playbook, units

    version, state, gauss = b.rng.getstate()
    pending = []
    for event in b.pending:
        exported = dump(event)
        trap = event.extra.get("trap_skeleton")
        if trap is not None:
            # Trap has no Python id; preserve identity through battle-list order.
            exported["extra"]["trap_skeleton"] = {
                "$trap": next(i for i, item in enumerate(b.traps) if item is trap)
            }
        pending.append(exported)
    return {
        # random.Random internal state: 624 words and the index (getstate()[1])
        "rng_state": list(state),
        "env": {
            "dt": B.DT,
            "fast_end": B.FAST_END,
            "windup": units.WINDUP,
            "flyer_range": os.environ.get("BASELAB_FLYER_RANGE", "gamedata"),
            "pace": float(os.environ.get("BASELAB_PACE", "1.0")),
            "pace_tap": playbook.PACE_TAP,
            "pace_switch": playbook.PACE_SWITCH,
            "pace_ability": playbook.PACE_ABILITY,
        },
        "scalars": scalars,
        "buildings": [dump(x) for x in b.buildings],
        "walls": [dump(w) for w in b.walls.values()],
        "traps": [dump(t) for t in b.traps],
        "attackers": [dump(u) for u in b.attackers],
        "defenders": [dump(u) for u in b.defenders],
        "fields": [dump(f) for f in b.fields],
        "pending": pending,
        "deployments": [dump(d) for d in b.deployments],
        "plan": plan_json(b.plan),
        "plan_type": type(b.plan).__name__,
    }


def trace(b, max_ticks=10**9):
    lines, last_b, last_w, nlog = [], {}, {}, 0
    b.record = True
    validate = getattr(b.plan, "require_legal", None)
    if validate is not None:
        validate()  # Battle.run() does this before the first step
    ticks = 0
    while not b.ended and b.t < b.max_time and ticks < max_ticks:
        lines.append(f"T {fbits(b.t)}")
        b.step()
        ticks += 1
        for team, pool in (("atk", b.attackers), ("def", b.defenders)):
            for u in pool:
                if u.alive:
                    lines.append(
                        f"U {team} {u.id} {u.name.replace(' ', '_')} {fbits(u.x)} {fbits(u.y)} {fbits(u.hp)}"
                    )
        for x in b.buildings:
            if last_b.get(x.id, x.max_hp) != x.hp:
                last_b[x.id] = x.hp
                lines.append(f"B {x.id} {fbits(x.hp)}")
        for w in b.walls.values():
            if last_w.get((w.tx, w.ty), w.max_hp) != w.hp:
                last_w[(w.tx, w.ty)] = w.hp
                lines.append(f"W {w.tx} {w.ty} {fbits(w.hp)}")
        for entry in b.log[nlog:]:
            lines.append("E " + json.dumps(dump(list(entry), 1)))
        nlog = len(b.log)
        if b.destroyed_counted >= b.total_counted or b.offense_finished():
            break
    r = b.result()
    lines.append(f"R {r.stars} {r.destruction} {fbits(r.time)} {r.units_left}")
    return lines


def engine_executable():
    from baselab.rust_bridge import engine_executable as bridge_executable

    return bridge_executable()


def parity(stage, n, start=0, setup=False):
    """Export scenarios start..start+n-1 of a stage, trace them in both
    engines, and report the first difference of each (rust/ must be built)."""
    import subprocess

    from trace_diff import first_difference

    exe = engine_executable()
    d = ROOT / "output" / "parity"
    d.mkdir(parents=True, exist_ok=True)
    same = 0
    for k in range(start, start + n):
        bj, py, rs = (
            d / f"battle-{stage}-{k}.json",
            d / f"trace-py-{stage}-{k}.txt",
            d / f"trace-rs-{stage}-{k}.txt",
        )
        b = scenario(stage, k)
        bj.write_text(json.dumps(battle_state(b)))
        py.write_text("\n".join(trace(scenario(stage, k))) + "\n")
        if setup:
            layout, plan, options = scenario_inputs(stage, k)
            job_file = d / f"jobs-{stage}-{k}.json"
            job_file.write_text(
                json.dumps(
                    jobs_json([layout], [plan], [{"layout": 0, "plan": 0, **options}])
                )
            )
            check = subprocess.run(
                [str(exe), "setup-check", str(bj), str(job_file)],
                capture_output=True,
                text=True,
            )
            if check.returncode != 0:
                print(f"  {k:3d}  SETUP FAILED")
                print(check.stdout, end="")
                print(check.stderr, end="")
                continue
            command = [str(exe), "trace-job", str(job_file), "0", str(rs)]
        else:
            command = [str(exe), "trace", str(bj), str(rs)]
        run = subprocess.run(command, capture_output=True, text=True)
        if run.returncode != 0:
            msg = (
                " | ".join(
                    l
                    for l in run.stderr.strip().splitlines()
                    if "RUST_BACKTRACE" not in l
                )[-300:]
                or "?"
            )
            print(f"  {k:3d}  RUST FAILED: {msg[:200]}")
            continue
        diff = first_difference(py.read_text().split("\n"), rs.read_text().split("\n"))
        if diff is None:
            same += 1
            print(f"  {k:3d}  identical   {py.read_text().splitlines()[-1]}")
        else:
            print(f"  {k:3d}  DIFFERS {diff}")
    print(f"stage {stage}: {same}/{n} identical")
    return same == n


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("catalog")
    c.add_argument("--out", required=True)
    pa = sub.add_parser("parity")
    pa.add_argument("--stage", type=int, required=True)
    pa.add_argument("--n", type=int, default=24)
    pa.add_argument("--start", type=int, default=0)
    ps = sub.add_parser("parity-setup")
    ps.add_argument("--stage", type=int, required=True)
    ps.add_argument("--n", type=int, default=24)
    ps.add_argument("--start", type=int, default=0)
    jo = sub.add_parser("jobs")
    jo.add_argument("--stage", type=int, required=True)
    jo.add_argument("--n", type=int, default=1)
    jo.add_argument("--start", type=int, default=0)
    jo.add_argument("--out", required=True)
    for name in ("battle", "trace"):
        p = sub.add_parser(name)
        p.add_argument("--stage", type=int, required=True)
        p.add_argument("--k", type=int, default=0)
        p.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.cmd == "parity":
        parity(args.stage, args.n, args.start)
        return
    if args.cmd == "parity-setup":
        raise SystemExit(0 if parity(args.stage, args.n, args.start, setup=True) else 1)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.cmd == "catalog":
        data = catalog()
        out.write_text(json.dumps(data))
        print(
            f"catalog: {len(data['registry'])} registry entries, {len(data['units'])} units, "
            f"{len(data['unit_numbers'])} unit levels -> {out} ({out.stat().st_size // 1024} KB)"
        )
    elif args.cmd == "jobs":
        layouts, plans, jobs = [], [], []
        for k in range(args.start, args.start + args.n):
            layout, plan, options = scenario_inputs(args.stage, k)
            index = len(jobs)
            layouts.append(layout)
            plans.append(plan)
            jobs.append({"layout": index, "plan": index, **options})
        out.write_text(json.dumps(jobs_json(layouts, plans, jobs)))
        print(f"stage {args.stage}: {len(jobs)} prepared jobs -> {out}")
    elif args.cmd == "battle":
        b = scenario(args.stage, args.k)
        out.write_text(json.dumps(battle_state(b), indent=1))
        print(
            f"stage {args.stage} scenario {args.k}: {len(b.buildings)} buildings, {len(b.walls)} walls, "
            f"{len(b.traps)} traps, {len(b.deployments)} deployments -> {out}"
        )
    else:
        b = scenario(args.stage, args.k)
        lines = trace(b)
        out.write_text("\n".join(lines) + "\n")
        print(
            f"stage {args.stage} scenario {args.k}: {len(lines)} trace lines; {lines[-1]} -> {out}"
        )


if __name__ == "__main__":
    main()
