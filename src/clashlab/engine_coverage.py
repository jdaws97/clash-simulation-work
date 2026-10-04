"""Roster-wide evidence and behavior coverage, without changing source statistics.

Catalog unlocks describe technology ceilings, not account ownership or guaranteed
donations. A conditional sector adapter is never promoted to replay calibration
or complete-village readiness by this inventory.
"""

from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256

from .adapters import (
    ADAPTER_VERSION,
    DEFENSE_ADAPTERS,
    HERO_EQUIPMENT,
    HEROES,
    MISSING_MECHANICS,
    UNIT_ADAPTERS,
    partial_adapter_status,
)
from .common import InputError, stable_id
from .defending_heroes import DEFENDING_HEROES
from .garrisons import GARRISON_MEMBERS
from .source_audit import audit_extracted_source


ATTACK_CATEGORIES = {
    "troop",
    "hero",
    "hero-equipment",
    "pet",
    "siege-machine",
    "spell",
}
DONATION_CATEGORIES = {"troop", "spell", "siege-machine"}
DEFENSE_CATEGORIES = {
    "defense",
    "crafted-defense",
    "trap",
    "guardian",
    "town-hall",
    "wall",
    "army",
    "resource",
    "research",
}
NONCOMBAT_ENTITIES = {
    "alchemist",
    "builders-apprentice",
    "lab-assistant",
    "prospector",
}
EXTRACTED_GROUPS = (
    "buildings",
    "traps",
    "troops",
    "guardians",
    "spells",
    "heroes",
    "pets",
    "equipment",
)
STATUS_LABELS = {
    "conditional_mechanics": "Conditional mechanics implemented",
    "passive_target_only": "Passive target only",
    "missing_behavior": "Behavior missing",
    "not_battle_actor": "Not a battle actor",
}
REPLAY_GAP = (
    "Current numeric values, targeting, geometry and timing need independent "
    "replay calibration; sector tests do not establish full-battle fidelity."
)


MISSING_DETAILS = {
    "apprentice-warden": "Following and support-aura membership, strength and stacking.",
    "baby-dragon": "Nearby-air-unit membership and isolated rage transitions.",
    "balloon": "Defense-priority air attacks, bomb splash, release timing and death damage.",
    "rocket-balloon": "Balloon weapon/death behavior plus timed initial movement boost.",
    "super-archer": "Piercing shot geometry, sequential recipients and projectile timing.",
    "super-barbarian": "Timed rage, rate changes and expiry while moving or attacking.",
    "bowler": "Boulder bounce geometry, first and subsequent impacts and timing.",
    "super-bowler": "Extended bounce sequence and per-impact damage allocation.",
    "super-dragon": "Entity-specific repeated splash weapon and timing.",
    "inferno-dragon": "Entity-specific moving ramp weapon, lock resets and interruptions.",
    "electro-titan": "Weapon plus independently pulsed damage aura and membership.",
    "furnace": "Stationary periodic Firemite spawning, autonomous units and fire pools.",
    "giant": "Defense-priority ground troop adapter and wall interaction.",
    "super-giant": "Defense-priority troop behavior and explicit wall-damage bonus.",
    "goblin": "Resource-priority selection and resource damage bonus.",
    "sneaky-goblin": "Resource targeting plus timed initial invisibility.",
    "golem": "Death splitting, Golemite statistics, placement and continued combat.",
    "headhunter": "Hero-priority targeting, wall traversal and attack-applied status.",
    "hog-rider": "Defense-priority movement and entity-specific wall jumping.",
    "super-hog-rider": "Mounted movement, split trigger and independent spawned units.",
    "lava-hound": "Air-defense preference, death splitting and autonomous Lava Pups.",
    "ice-hound": "Air-defense preference, death freeze and spawned-unit lifecycle.",
    "meteor-golem": "Meteormite separation, attacks, partner search and recombination.",
    "miner": "Burrowing, emergence, hidden travel and surface attack transitions.",
    "super-miner": "Burrowing plus ramped attacks and the death-explosion lifecycle.",
    "super-minion": "Finite boosted long-range attacks and subsequent weapon transition.",
    "super-valkyrie": "Source-centered attacks plus death-released rage behavior.",
    "wall-breaker": "Wall selection, self-destruction, damage allocation and death trigger.",
    "super-wall-breaker": "Wall selection and separate attack/death explosion rules.",
    "witch": "Repeated Skeleton spawning, live caps, placement and autonomous combat.",
    "super-witch": "Big Boy spawning, replacement conditions and independent combat.",
    "wizard": "Entity-specific ground splash attack adapter and wall interactions.",
    "super-wizard": "Entity-specific chain weapon, link geometry and timing.",
    "yeti": "Damage-triggered Yetimite spawning, targeting and spawn accounting.",
    "super-yeti": "Damage-triggered electrical summons and their chain reactions.",
    "barbarian-king": "Attacking King lifecycle and selected equipment; defending behavior has a separate conditional adapter.",
    "minion-prince": "Attacking flying-hero lifecycle and selected equipment; defending behavior has a separate conditional adapter.",
    "dragon-duke": "Nearby-air-unit isolation transitions, Royal Rampage and defense AI.",
    "air-sweeper": "Facing, cone membership, pulsed knockback and interrupted movement.",
    "eagle-artillery": "Army-weight activation, target selection, burst travel and impacts.",
    "mortar": "Minimum range, delayed ground splash and optional burst mode.",
    "firespitter": "Fixed facing, firing sector, rapid projectiles and overshoot hits.",
    "multi-gear-tower": "Selected merged-weapon mode, target allocation and burst behavior.",
    "revenge-tower": "Building-death-driven stages and weapon changes.",
    "super-wizard-tower": "Complete chain/splash weapon geometry and target allocation.",
    "crafting-station": "Selected crafted defense, independent modules and active weapon.",
    "giga-bomb": "Its own trigger, timing, damage and displacement lifecycle.",
    "skeleton-trap": "Ground/air mode, finite Skeleton release and defending-unit combat.",
    "tornado-trap": "Area membership, orbit/pull, movement disruption and expiry.",
    "hero-banner": "Indestructible placement metadata requires an explicitly bound defending hero or Warden statue.",
    "rage-spell": "Area attack/movement modifiers, stacking and remaining attack-work clocks.",
    "haste-spell": "Timed movement field, entry/exit membership and overlap.",
    "lightning-spell": "Spell-specific damage, target exclusions and stun semantics.",
    "earthquake-spell": "HP-relative damage, repeated-cast scaling and distinct wall rules.",
    "poison-spell": "Spell-specific damage growth, slows, eligibility and lingering.",
    "jump-spell": "Area-dependent wall traversal and entry/expiry routing changes.",
    "clone-spell": "Housing-limited cloning, spawn positions and clone lifetimes.",
    "invisibility-spell": "Area invisibility, excluded structures and retargeting on expiry.",
    "recall-spell": "Housing-limited pickup, preserved actor state and legal redeployment.",
    "overgrowth-spell": "Structure suppression, targeting changes and restoration at expiry.",
    "revive-spell": "Dead-hero selection, revival state and subsequent combat.",
    "skeleton-spell": "Finite Skeleton generation, spawn timing and autonomous units.",
    "bat-spell": "Bat spawning, target rules, damage exceptions and autonomous units.",
    "ice-block-spell": "Damage reduction with frozen attacks/movement and timed release.",
    "angry-spell": "Temporary defense-priority overrides and movement/status expiry.",
    "totem-spell": "Decoy actor, enemy target override, impact damage/stun and lifetime.",
    "battle-blimp": "Air travel, impact/destruction/manual release and castle payload.",
    "wall-wrecker": "Town-Hall-directed movement, wall damage and castle payload release.",
    "stone-slammer": "Defense-priority air splash and destruction/manual payload release.",
    "siege-barracks": "Stationary lifetime, timed troop spawns and castle payload release.",
    "log-launcher": "Piercing logs, HP decay, travel and castle payload release.",
    "flame-flinger": "Minimum-range targeting, projectile fire pools, decay and payload.",
    "battle-drill": "Burrowing, defense selection, stun and castle payload release.",
    "troop-launcher": "Barrel launch sequence, troop composition, lifetime and payload.",
    "sky-wagon": "Air movement, timed barrels, multi-type summons and payload lifecycle.",
    "lassi": "Hero-linked following, targeting and independent melee combat.",
    "mighty-yak": "Hero-linked following, wall damage and its linked ability lifecycle.",
    "electro-owl": "Hero-linked flying movement and entity-specific chained attacks.",
    "unicorn": "Hero-linked following, healing selection, cadence and hero-loss behavior.",
    "phoenix": "Egg/following phase, hero-death revival and timed post-revival behavior.",
    "poison-lizard": "Hero-linked targeting and attack-applied poison/status behavior.",
    "diggy": "Hero-linked burrowing, target emergence and stun.",
    "frosty": "Hero-linked attacks plus Frostmite spawning and slow effects.",
    "spirit-fox": "Hero-linked following and recurring shared invisibility windows.",
    "angry-jelly": "Hero-linked flying attacks and temporary hero target-priority change.",
    "sneezy": "Following offsets, flying summons and transition after the hero falls.",
    "greedy-raven": "Hero-linked movement, resource preference and damage bonus.",
}

IMPLEMENTED_DETAILS = {
    "barbarian-king": "Ground-only attacking hero with a shared manual ability charge, Spiky Ball bounces, Giant Gauntlet area swings/reduction, and temporary Stick Horse wall traversal; other King equipment remains unavailable.",
    "minion-prince": "Flying attacking hero with shared manual activation, timed Metal Pants protection, finite Noble Iron weapon boosts, and a travelling Dark Orb with exact contacts and independent slows; Dark Crown and Henchmen remain unavailable.",
    "dragon-duke": "Attacking Duke with exact relative friendly-air isolation boundaries, separate intrinsic damage/rate/trap factors, source-attributed Revenge Deck counters, and Fire Heart healing/death after Phoenix interception; defending Duke remains unavailable.",
    "spiky-ball": "Finite source-persistent bounces with explicit target geometry, tie breaking, protected/dead-target handling and profile-scaled per-target damage.",
    "giant-gauntlet": "Timed incoming damage reduction and source-centered ground splash shared by ordinary and wall swings, plus explicit deployed self-healing pulses.",
    "stick-horse": "One deployment-timed movement/rate bonus and wall-jump duration, followed by a retained exit when the King is inside a wall at expiry.",
    "revenge-deck": "Counters positive actual health loss attributed to a live hostile actor, with a shared cooldown, explicit source/protection rules and healing on release.",
    "fire-heart": "Explicit deployed healing pulses and source-persistent actual-death blast; Phoenix interception defers the blast until final defeat.",
    "metal-pants": "Manual activation applies a timed percentage reduction from the declared numeric source mapping and composes with independent protection.",
    "noble-iron": "A finite number of main-weapon launches capture the source damage/range boost and attack-rate hypothesis, then rescale remaining cooldown when spent.",
    "dark-orb": "Captured travel direction, continuous circle contacts, one hit per eligible target, and independently expiring strongest slow effects persist after source death.",
    "longshot": "Separately bound TH18 Guardian with explicit trigger/emergence, Freeze, patrol/leash/retaliation, permanent death, radial weapon and source-mapped death blast; excluded from building destruction.",
    "smasher": "Separately bound TH18 Guardian with explicit trigger/emergence and movement, source-mapped Hall-death self-rage, and a dropped rage field whose quantities and recipients remain explicit hypotheses.",
    "skeleton-trap": "Ground/air trigger with finite ordered Skeleton release, separate owned reserves and autonomous defending combat; summoned statistics remain an explicit unarmored reference hypothesis.",
    "tornado-trap": "Finite vortex capture, pull/orbit, explicit damage quantity and duration, separate attack pause, and declared priority against Sweeper motion; damage and motion parameters remain hypotheses.",
    "clan-castle": "Counted castle with explicit defensive roster, donor/receiver laboratory mapping, capacity, exterior release positions and paused release clock; seven defending troop adapters persist after castle destruction.",
    "builders-hut": "Travelling defensive repair worker with explicit repair targets, route, pulse timing, interruption and hut destruction linkage.",
    "firespitter": "Oriented 150-degree acquisition, explicit burst-angle sequence and live first-contact ballistic shots; source hit/cadence/DPS conflicts remain visible and the behavior is not calibrated.",
    "giant": "Defense-priority ground attacks with explicit wall-breach behavior.",
    "wizard": "Source-mapped radial ground attacks and explicit wall interaction.",
    "hog-rider": "Defense-priority attacks and declared enemy-wall jumping.",
    "root-rider": "Ground wall penetration with declared routing and wall cooldown rules.",
    "valkyrie": "Source-centered radial attacks and reachable between-target placement.",
    "ice-golem": "Impact slow, independent status expiry and actual-death freeze.",
    "healer": "Explicit healing selector, pulses, projectiles and stacking conventions.",
    "healing-spell": "Source-mapped healing field, membership, pulses and stacking.",
    "freeze-spell": "Source-mapped timed freeze, radius and attack-work pause.",
    "rage-spell": "Paid timed area buff with exact route crossings and explicit damage, speed and source-healing policies.",
    "haste-spell": "Paid timed movement field with exact entry, exit, linger and overlap rules.",
    "mortar": "Explicit dead zone, fixed-destination shell travel and separately timed geared bursts.",
    "eagle-artillery": "Cumulative army/cast activation, HP-density targeting, separate shells and explicit shockwave overlap.",
    "air-sweeper": "Oriented air acquisition, traveling gusts, finite displacement and independent attack pauses.",
    "spell-tower": "Reactive Rage, Poison and Invisibility fields with explicit trigger, cast, recharge and death-release policies; Earthquake remains unsupported.",
    "electro-dragon": "Chain attacks with explicit readiness and death-impact sequence.",
    "dragon-rider": "Air movement, selected target-layer policy and death blast.",
    "hidden-tesla": "Dormancy, proximity/threshold reveal, readiness and explicit footprint policy.",
    "inferno-tower": "Single-lock damage ramp or declared synchronized multi-target beams.",
    "scattershot": "Directional splash, explicit falloff and finite ammunition.",
    "bomb-tower": "Radial weapon and delayed explosion from actual death.",
    "wizard-tower": "Layer-filtered radial defense weapon.",
    "spring-trap": "Explicit allocation, capacity/oversize response and displacement policies.",
    "bomb": "One-use ground proximity trigger and fixed-center damage.",
    "giant-bomb": "One-use ground proximity trigger and fixed-center area damage.",
    "air-bomb": "One-use air trigger with declared delayed splash projectile.",
    "seeking-air-mine": "One-use air trigger with declared locked-target projectile.",
    "wall": "Count-excluded blocking footprint and explicit breach/jump routing.",
}

ARCHETYPES = [
    {
        "id": "ground-breach",
        "name": "Ground breach and tanking",
        "entities": [
            "root-rider",
            "ice-golem",
            "pekka",
            "valkyrie",
            "golem",
            "giant",
            "wall-breaker",
            "super-wall-breaker",
            "wall-wrecker",
            "log-launcher",
            "rage-spell",
            "jump-spell",
            "healing-spell",
            "freeze-spell",
        ],
        "behavior_dependencies": [
            "Breach choice and wall timing",
            "Tank death/summons",
            "Siege payload",
            "Buff-field interactions",
        ],
    },
    {
        "id": "ranged-support",
        "name": "Ranged damage and support",
        "entities": [
            "thrower",
            "archer",
            "super-archer",
            "wizard",
            "super-wizard",
            "bowler",
            "super-bowler",
            "healer",
            "druid",
            "apprentice-warden",
            "rage-spell",
            "freeze-spell",
            "siege-barracks",
        ],
        "behavior_dependencies": [
            "Piercing and bouncing weapons",
            "Following and healing",
            "Transformations",
            "Support aura membership",
        ],
    },
    {
        "id": "air-chains",
        "name": "Air chains and dragon attacks",
        "entities": [
            "electro-dragon",
            "dragon",
            "dragon-rider",
            "minion",
            "super-dragon",
            "super-minion",
            "balloon",
            "rage-spell",
            "freeze-spell",
            "battle-blimp",
            "stone-slammer",
        ],
        "behavior_dependencies": [
            "Moving chain selection",
            "Air knockback",
            "Siege release",
            "Rage and freeze timing",
        ],
    },
    {
        "id": "air-balloons",
        "name": "Balloons, rockets and air tanks",
        "entities": [
            "balloon",
            "rocket-balloon",
            "lava-hound",
            "ice-hound",
            "minion",
            "haste-spell",
            "rage-spell",
            "freeze-spell",
            "stone-slammer",
        ],
        "behavior_dependencies": [
            "Bomb release/death damage",
            "Initial speed boosts",
            "Air-defense preference",
            "Pup spawns and haste",
        ],
    },
    {
        "id": "hero-charge",
        "name": "Hero charges and hero-led entries",
        "entities": [
            "archer-queen",
            "barbarian-king",
            "grand-warden",
            "royal-champion",
            "healer",
            "wall-breaker",
            "super-wall-breaker",
            "rage-spell",
            "freeze-spell",
            "poison-spell",
            "invisibility-spell",
            "recall-spell",
            "unicorn",
            "spirit-fox",
            "mighty-yak",
        ],
        "behavior_dependencies": [
            "Healer retargeting under pressure",
            "All selected hero equipment",
            "Hero-pet link",
            "Garrison and defending heroes",
        ],
    },
    {
        "id": "witch-summons",
        "name": "Witches and summon-heavy attacks",
        "entities": [
            "witch",
            "super-witch",
            "ruin-witch",
            "furnace",
            "golem",
            "yeti",
            "super-yeti",
            "skeleton-spell",
            "bat-spell",
            "siege-barracks",
        ],
        "behavior_dependencies": [
            "Live summon caps",
            "Rubble consumption",
            "Damage/death-triggered spawns",
            "Autonomous summoned actors",
        ],
    },
    {
        "id": "hogs-miners",
        "name": "Hogs, miners and hybrid routes",
        "entities": [
            "hog-rider",
            "super-hog-rider",
            "miner",
            "super-miner",
            "healing-spell",
            "freeze-spell",
            "poison-spell",
            "siege-barracks",
            "royal-champion",
        ],
        "behavior_dependencies": [
            "Defense-priority wall jumps",
            "Burrow/emerge states",
            "Mounted splitting",
            "Healing and trap interactions",
        ],
    },
]


def _level_caps(catalog, entity):
    levels = sorted(
        {row["level"] for row in entity.get("levels", []) if not row.get("supercharge")}
    )
    caps = {}
    errors = set()
    for town_hall in range(1, catalog.maximum_town_hall + 1):
        allowed = []
        for level in levels:
            try:
                if catalog.available(entity["id"], level, town_hall):
                    allowed.append(level)
            except InputError as error:
                errors.add(str(error))
        caps[str(town_hall)] = max(allowed) if allowed else None
    return caps, sorted(errors)


def _extracted_index(extracted):
    by_id = {}
    by_name = defaultdict(list)
    home = []
    for group in EXTRACTED_GROUPS:
        for entity in extracted.get(group, []):
            if entity.get("village", "home") != "home":
                continue
            record = {"group": group, "entity": entity}
            if entity["_id"] in by_id:
                raise InputError("Coverage source has duplicate home extraction IDs")
            by_id[entity["_id"]] = record
            by_name[entity["name"].casefold()].append(record)
            home.append(record)
    return by_id, by_name, home


def _matched_source(entity, by_id, by_name):
    if entity.get("dataId") in by_id:
        return by_id[entity["dataId"]], "exact_data_id"
    candidates = by_name.get(entity["name"].casefold(), [])
    if entity.get("dataId") is None and len(candidates) == 1:
        return candidates[0], "unique_exact_name_evidence_only"
    return None, "unmapped"


def _mode_variants(entity):
    supported = DEFENSE_ADAPTERS.get(entity["id"], {})
    return [
        {
            "id": mode,
            "available_from_level": values.get("availableFromLevel", 1),
            "conditional_weapon_registered": mode in supported,
            "pattern": supported.get(mode),
            "requires_entity_lifecycle": entity["id"] in MISSING_MECHANICS
            or entity["id"]
            in {
                "hidden-tesla",
                "inferno-tower",
                "scattershot",
                "bomb-tower",
                "spell-tower",
                "firespitter",
            },
        }
        for mode, values in entity.get("modes", {}).items()
    ]


def _town_hall_variants(entity):
    variants = []
    for row in entity.get("levels", []):
        if row.get("supercharge"):
            continue
        level = row["level"]
        support = partial_adapter_status(entity, level)
        if level in {14, 15, 16}:
            details = "Conditional Giga Inferno activation, beams, blast and persistent poison."
        elif level == 17:
            details = (
                "Conditional always-active projectile weapon and impact flame pools."
            )
        elif level == 18:
            details = "Conditional weaponless TH18 Hall with exactly one separately bound Longshot or Smasher; Logger and absent/upgrading Guardian selections remain unsupported."
        else:
            details = (
                "This Town Hall level has no accepted complete entity compiler path."
            )
        variants.append(
            {
                "level": level,
                "weapon": (row.get("weapon") or {}).get("name"),
                "conditional_adapter": support,
                "detail": details,
                "replay_calibrated": False,
                "complete_battle_ready": False,
            }
        )
    return variants


def _defending_hero_behavior(entity):
    if entity["category"] != "hero":
        return None
    supported = entity["id"] in DEFENDING_HEROES
    if supported:
        registry = deepcopy(partial_adapter_status(entity, role="defense"))
        status = "conditional_mechanics"
        detail = (
            "Stationary Warden statue bound to an indestructible banner; base weapon, aggro, recovery and explicit counted/excluded destruction policy."
            if entity["id"] == "grand-warden"
            else "Banner-bound defending hero with base weapon, ordered patrol, aggro, leash return, home recovery and permanent battle death."
        )
        remaining = [
            "Explicit banner, targeting, movement, recovery and attacker response hypotheses; no attacking equipment, pets or active ability.",
            REPLAY_GAP,
        ]
    else:
        registry = {
            "available": False,
            "missing": ["Entity-specific defending behavior"],
        }
        status = "missing_behavior"
        detail = "Defending entity-specific passive, acquisition and combat lifecycle remain unavailable."
        remaining = [MISSING_DETAILS.get(entity["id"], detail)]
    return {
        "status": status,
        "label": STATUS_LABELS[status],
        "implemented": detail,
        "remaining": remaining,
        "registry": registry,
        "replay_calibrated": False,
        "complete_battle_ready": False,
    }


def _defending_garrison_behavior(entity):
    if entity["id"] not in GARRISON_MEMBERS:
        return None
    return {
        "status": "conditional_mechanics",
        "label": STATUS_LABELS["conditional_mechanics"],
        "implemented": "Castle-bound reserve with source-mapped base weapon, explicit release clock and exterior position; after release, retained hostile-unit pursuit has no leash and survives castle destruction.",
        "remaining": [
            "Explicit castle roster, capacity, donor availability and receiver laboratory mapping are required; a donor candidate does not certify a received level.",
            "Projectile, splash, wall avoidance, trigger layers, release order and attacker response policies remain explicit hypotheses.",
            REPLAY_GAP,
        ],
        "registry": deepcopy(partial_adapter_status(entity, role="defense")),
        "replay_calibrated": False,
        "complete_battle_ready": False,
    }


def _behavior(entity):
    support = deepcopy(partial_adapter_status(entity))
    entity_id = entity["id"]
    category = entity["category"]
    defending = _defending_hero_behavior(entity) or _defending_garrison_behavior(entity)
    if entity_id == "hero-banner":
        status = "not_battle_actor"
        implemented = "Indestructible, nonblocking placement metadata binds a separate defending hero or Warden statue; the banner is not a normal damageable actor."
        missing = [
            "Bind banner settings.hero and settings.level to the separately compiled defender; select explicit statue destruction eligibility when applicable.",
            "Validate unique banners, nonoverlapping footprints, Town Hall slots and role-specific behavior hypotheses.",
            REPLAY_GAP,
        ]
    elif entity_id in NONCOMBAT_ENTITIES:
        status = "not_battle_actor"
        implemented = "Home-village progression helper; not an autonomous battle actor."
        missing = []
    elif (
        support["available"]
        and support.get("scope") == "passive_structure_in_declared_sector"
    ):
        if "size" not in entity:
            status = "missing_behavior"
            implemented = (
                "Registry advertises a passive record, but a footprint is absent."
            )
            missing = [
                "A valid battle-actor schema and footprint are required before compilation."
            ]
        else:
            status = "passive_target_only"
            implemented = "Source-mapped HP, footprint and damageable passive target."
            missing = [
                "Whole-village inventory, destruction eligibility and interactions still need validation."
            ]
    elif support["available"]:
        status = "conditional_mechanics"
        if entity_id in IMPLEMENTED_DETAILS:
            implemented = IMPLEMENTED_DETAILS[entity_id]
        elif entity_id in HEROES:
            implemented = "Attacking hero with supported equipment pairs and explicit manual activation."
        elif entity_id in HERO_EQUIPMENT:
            implemented = (
                "Entity-specific equipment statistics and active/passive lifecycle."
            )
        elif entity_id == "town-hall":
            implemented = "TH14-16 Giga Inferno, TH17 artillery, or weaponless TH18 Hall with a selected supported Guardian; earlier levels require separate behavior."
        elif entity_id in UNIT_ADAPTERS:
            movement, pattern = UNIT_ADAPTERS[entity_id]
            implemented = (
                f"Source-mapped {movement} troop with an explicit {pattern} weapon."
            )
        elif entity_id in DEFENSE_ADAPTERS:
            implemented = (
                "Source-mapped defense with the explicitly registered weapon modes."
            )
        else:
            implemented = (
                "Conditional adapter registered; its declared inputs remain required."
            )
        missing = list(support.get("required", []))
        if category == "hero":
            missing.append(
                "Attacking behavior supports only registered equipment and explicitly paired supported pets. Defending roles use their separate banner-bound adapter; Dragon Duke defense remains unavailable."
            )
        if entity_id == "town-hall":
            missing.append(
                "Logger, absent/upgrading TH18 Guardians and earlier Town Hall weapon lifecycles are not covered."
            )
        missing.append(REPLAY_GAP)
    else:
        status = "missing_behavior"
        implemented = (
            "Attacking behavior is unavailable; a separate conditional defending-hero adapter is implemented."
            if defending and defending["status"] == "conditional_mechanics"
            else "Statistics/metadata only; the entity cannot enter a supported battle adapter."
        )
        missing = list(MISSING_MECHANICS.get(entity_id, []))
        if entity_id in MISSING_DETAILS:
            missing.append(MISSING_DETAILS[entity_id])
        elif category == "hero-equipment":
            description = entity.get(
                "description", "Selected active/passive equipment behavior."
            )
            missing.append(f"No equipment handler for: {description}")
        elif category == "crafted-defense":
            missing.append(
                "Crafting phase selection, module-to-stat mapping and the complete selected weapon."
            )
        elif category == "guardian":
            missing.append(
                "TH18 guardian deployment, movement, targeting, ability and death lifecycle."
            )
        elif not missing:
            missing.extend(
                support.get("missing", ["Complete entity-specific behavior adapter."])
            )
    return {
        "status": status,
        "label": STATUS_LABELS[status],
        "implemented": implemented,
        "remaining": list(dict.fromkeys(missing)),
        "registry": support,
        "replay_calibrated": False,
        "complete_battle_ready": False,
        "defending_hero_behavior": (
            (
                "conditional_banner_bound_defending_behavior"
                if defending["status"] == "conditional_mechanics"
                else "missing_entity_specific_defending_behavior"
            )
            if defending and category == "hero"
            else None
        ),
        "defending_role": defending,
        "supercharge_behavior": (
            "not_supported_by_entity_compiler"
            if any(row.get("supercharge") for row in entity.get("levels", []))
            else "no_supercharged_rows_in_catalog"
        ),
    }


def _donation(entity, caps, catalog, castle):
    if entity["category"] not in DONATION_CATEGORIES:
        return {"status": "not_a_donatable_category", "candidate": False}
    donor_max = caps.get("18")
    housing = entity.get("housingSpace")
    category = entity["category"]
    capacity_field = {
        "troop": "troopCapacity",
        "spell": "spellCapacity",
        "siege-machine": "siegeMachineCapacity",
    }[category]
    capacity = castle[capacity_field]
    fits = (
        capacity >= 1
        if category == "siege-machine"
        else (housing is not None and housing <= capacity)
    )
    known_eligible = []
    unknown_lab_levels = []
    for row in entity.get("levels", []):
        if row.get("supercharge") or donor_max is None or row["level"] > donor_max:
            continue
        lab = row.get("laboratoryRequired")
        if lab is None and entity.get("troopType") == "super":
            lab = catalog.level(entity["parentTroop"], row["level"]).get(
                "laboratoryRequired"
            )
        if lab is None:
            unknown_lab_levels.append(row["level"])
        elif lab <= castle["labLevelCap"]:
            known_eligible.append(row["level"])
    candidate = donor_max is not None and fits
    return {
        "status": (
            "catalog_candidate_receiver_confirmation_required"
            if candidate
            else "not_a_catalog_candidate"
        ),
        "candidate": candidate,
        "donor_town_hall": 18,
        "donor_catalog_max_level": donor_max,
        "receiver_town_hall": 16,
        "receiver_max_catalog_castle_level": castle["level"],
        "receiver_catalog_lab_level_cap": castle["labLevelCap"],
        "max_level_under_known_catalog_lab_cap": max(known_eligible, default=None),
        "levels_missing_lab_mapping": unknown_lab_levels,
        "housing_per_unit": housing,
        "receiver_capacity": capacity,
        "one_unit_fits_catalog_capacity": fits,
        "receipt_or_owned_level_confirmed": False,
        "note": "Donor ceiling is not a guaranteed received level. Actual account donation caps, receiver rules and availability must be entered; capacity alone does not certify a legal army.",
    }


def _opponent_status(entity, caps, town_hall):
    category = entity["category"]
    if entity["id"] in GARRISON_MEMBERS:
        return (
            "garrison_donor_candidate_conditional_mechanics"
            if caps["18"] is not None
            else "not_unlocked"
        )
    if category == "hero":
        if not caps[str(town_hall)]:
            return "not_unlocked"
        return (
            "available_defending_conditional_mechanics"
            if entity["id"] in DEFENDING_HEROES
            else "available_defending_behavior_missing"
        )
    if category == "crafted-defense":
        if entity.get("isCurrent") is False:
            return "historical_crafted_variant"
        return "module_configuration_unverified" if town_hall == 18 else "not_unlocked"
    if category not in DEFENSE_CATEGORIES and entity["id"] not in {
        "hero-banner",
        "bobs-hut",
        "helper-hut",
    }:
        return "not_a_defending_option"
    counts = [
        row
        for row in entity.get("availablePerTownHall", [])
        if row["townHallLevel"] == town_hall
    ]
    if counts and counts[0]["count"] == 0:
        return "absent_from_town_hall_inventory"
    if entity["id"] == "hero-banner":
        return (
            "available_defending_banner_metadata"
            if counts and counts[0]["count"]
            else "availability_unverified"
        )
    if caps[str(town_hall)] is not None:
        return "catalog_available"
    return "availability_unverified" if not entity.get("levels") else "not_unlocked"


def _opponent_behavior(entity, behavior, town_hall):
    status = behavior["status"]
    detail = behavior["implemented"]
    if entity["category"] == "hero" or entity["id"] in GARRISON_MEMBERS:
        return deepcopy(behavior["defending_role"])
    elif entity["id"] == "town-hall":
        support = partial_adapter_status(entity, town_hall)
        if not support["available"]:
            status = "missing_behavior"
            detail = f"TH{town_hall} Town Hall and its required guardian lifecycle are missing."
        else:
            detail = next(
                item["detail"]
                for item in _town_hall_variants(entity)
                if item["level"] == town_hall
            )
    return {"status": status, "label": STATUS_LABELS[status], "implemented": detail}


def _row(catalog, record, matched, match_kind, differences, selected, castle):
    entity = record["entity"]
    entity_id = entity["id"]
    caps, cap_errors = _level_caps(catalog, entity)
    raw = matched["entity"] if matched else None
    behavior = _behavior(entity)
    row = {
        "id": entity_id,
        "name": entity["name"],
        "category": entity["category"],
        "troop_type": entity.get("troopType"),
        "hero": entity.get("hero"),
        "catalog_data_id": entity.get("dataId"),
        "source_kind": "catalog",
        "catalog_level_count": sum(
            not value.get("supercharge") for value in entity.get("levels", [])
        ),
        "max_level_by_town_hall": caps,
        "level_cap_errors": cap_errors,
        "unlock_basis": "Catalog.available including explicit secondary caps; ownership and seasonal/event acquisition are separate.",
        "th16_attack_eligible": entity["category"] in ATTACK_CATEGORIES
        and caps.get("16") is not None,
        "th18_donation": _donation(entity, caps, catalog, castle),
        "opponent_status_by_town_hall": {
            str(town_hall): _opponent_status(entity, caps, town_hall)
            for town_hall in (16, 17, 18)
        },
        "opponent_behavior_by_town_hall": {
            str(town_hall): _opponent_behavior(entity, behavior, town_hall)
            for town_hall in (16, 17, 18)
        },
        "placement_counts": {
            str(value["townHallLevel"]): {
                key: number for key, number in value.items() if key != "townHallLevel"
            }
            for value in entity.get("availablePerTownHall", [])
            if value["townHallLevel"] in {16, 17, 18}
        },
        "behavior": behavior,
        "mode_variants": _mode_variants(entity),
        "town_hall_variants": (
            _town_hall_variants(entity) if entity_id == "town-hall" else []
        ),
        "crafted_phase": entity.get("craftingPhase"),
        "crafted_current_in_snapshot": entity.get("isCurrent"),
        "archetypes": [
            item["id"] for item in ARCHETYPES if entity_id in item["entities"]
        ],
        "sources": {
            "catalog": record["source"],
            "catalog_verification": record["verification"],
            "extracted_match": match_kind,
            "statistic_comparison_scope": (
                "direct_numeric_id_mappings_only"
                if match_kind == "exact_data_id"
                else "name_or_unmapped_identity_not_compared"
            ),
            "extracted_group": matched["group"] if matched else None,
            "extracted_data_id": raw["_id"] if raw else None,
            "extracted_max_recorded_level": (
                max((value["level"] for value in raw.get("levels", [])), default=None)
                if raw
                else None
            ),
            "direct_statistic_differences": differences,
            "declared_extracted_branch_fields": selected,
            "report_applied_overrides": False,
        },
    }
    if entity.get("troopType") == "super":
        row["additional_availability_requirements"] = [
            "Confirmed activation and active-super-troop limit for self-training."
        ]
    elif entity["category"] == "hero-equipment":
        row["additional_availability_requirements"] = [
            "Correct hero, owned equipment, acquisition availability and two-item loadout."
        ]
    elif entity["category"] in {"pet", "hero"}:
        row["additional_availability_requirements"] = [
            "Owned level, available slot and legal hero/pet assignment."
        ]
    else:
        row["additional_availability_requirements"] = []
    return row


def _category_counts(rows):
    groups = {}
    for category in sorted({row["category"] for row in rows}):
        members = [row for row in rows if row["category"] == category]
        counts = Counter(row["behavior"]["status"] for row in members)
        groups[category] = {
            "catalog_entities": len(members),
            **{status: counts[status] for status in STATUS_LABELS},
            "th16_attack_eligible": sum(row["th16_attack_eligible"] for row in members),
            "th16_attack_with_conditional_mechanics": sum(
                row["th16_attack_eligible"]
                and row["behavior"]["status"] == "conditional_mechanics"
                for row in members
            ),
            "th18_donation_candidates": sum(
                row["th18_donation"]["candidate"] for row in members
            ),
            "replay_calibrated": 0,
            "complete_battle_ready": 0,
        }
    return groups


def _archetype_coverage(rows):
    by_id = {row["id"]: row for row in rows}
    output = []
    for definition in ARCHETYPES:
        conditional = []
        missing = []
        unavailable_self = []
        for entity_id in definition["entities"]:
            row = by_id[entity_id]
            if row["behavior"]["status"] == "conditional_mechanics":
                conditional.append(entity_id)
            else:
                missing.append(entity_id)
            if not row["th16_attack_eligible"]:
                unavailable_self.append(entity_id)
        output.append(
            {
                **deepcopy(definition),
                "conditional_entities": conditional,
                "missing_entities": missing,
                "not_self_available_at_th16": unavailable_self,
                "complete_battle_ready": False,
                "purpose": "Coverage family, not a recommended army or a claim every listed option is required together.",
            }
        )
    return output


def _priorities(rows):
    groups = [
        (
            "Complete a TH16 defending village",
            [
                "clan-castle",
                "builders-hut",
                "spell-tower",
                "air-sweeper",
                "eagle-artillery",
                "mortar",
                "skeleton-trap",
                "tornado-trap",
                "hero-banner",
            ],
            "Garrisons, repair, displacement, reactive spells and defending heroes change every attack family.",
        ),
        (
            "Add TH17/18 opposing-village systems",
            [
                "firespitter",
                "multi-gear-tower",
                "revenge-tower",
                "super-wizard-tower",
                "crafting-station",
                "giga-bomb",
                "logger",
                "longshot",
                "smasher",
            ],
            "TH17 artillery alone does not cover the newer defenses, TH18 Town Hall/guardian lifecycle or crafted modules.",
        ),
        (
            "Connect spells and siege payloads",
            [
                "rage-spell",
                "haste-spell",
                "poison-spell",
                "jump-spell",
                "invisibility-spell",
                "clone-spell",
                "battle-blimp",
                "wall-wrecker",
                "stone-slammer",
                "siege-barracks",
                "log-launcher",
            ],
            "These shared systems unblock many distinct army families and must preserve actor identity across deployment/release.",
        ),
        (
            "Broaden moving and spawning troop lifecycles",
            [
                "balloon",
                "rocket-balloon",
                "lava-hound",
                "hog-rider",
                "miner",
                "witch",
                "ruin-witch",
                "druid",
                "bowler",
                "super-archer",
            ],
            "Burrowing, wall jumps, summons, transformations and distinct projectiles cannot be replaced by a generic single-hit troop.",
        ),
        (
            "Complete hero, equipment and pet choices",
            [
                "barbarian-king",
                "minion-prince",
                "dragon-duke",
                "unicorn",
                "spirit-fox",
                "phoenix",
                "diggy",
                "frosty",
            ],
            f"Supported attacking heroes and {len(HERO_EQUIPMENT)} equipment handlers leave most loadout and companion choices uncovered.",
        ),
    ]
    by_id = {row["id"]: row for row in rows}
    result = []
    for title, entities, reason in groups:
        result.append(
            {
                "priority": len(result) + 1,
                "title": title,
                "remaining_entities": [
                    entity_id
                    for entity_id in entities
                    if by_id[entity_id]["behavior"]["status"] != "conditional_mechanics"
                    and entity_id != "hero-banner"
                ],
                "why": reason,
            }
        )
    result.append(
        {
            "priority": len(result) + 1,
            "title": "Calibrate the integrated battle, then evaluate plans and bases",
            "remaining_entities": [],
            "why": "Reconcile per-field sources and game-version/mode rules; verify full inventories, legal deployment, destruction/stars, targeting, timing, and human execution against held-out observations. No entity is replay calibrated yet.",
        }
    )
    return result


def build_engine_coverage(
    catalog, extracted, provenance, selection, unresolved=None, code_files=None
):
    """Build a deterministic audit from current registries and pinned source files."""
    if "statistic_branch" in catalog.snapshot:
        raise InputError(
            "Coverage must inspect the unchanged base catalog; branches are listed separately"
        )
    audit = audit_extracted_source(catalog, extracted, provenance)
    differences = defaultdict(list)
    for row in audit["differences"]:
        differences[row["entity"]].append(deepcopy(row))
    selected = defaultdict(list)
    for row in selection:
        selected[row["entity"]].append(deepcopy(row))
    by_id, by_name, raw_records = _extracted_index(extracted)
    castle_caps, _ = _level_caps(catalog, catalog.entity("clan-castle"))
    castle = catalog.level("clan-castle", castle_caps["16"])
    rows = []
    matched_ids = set()
    for entity_id, record in sorted(catalog.records.items()):
        entity = record["entity"]
        if entity.get("base", "home") != "home":
            continue
        matched, match_kind = _matched_source(entity, by_id, by_name)
        if matched:
            matched_ids.add(matched["entity"]["_id"])
        row = _row(
            catalog,
            record,
            matched,
            match_kind,
            differences[entity_id],
            selected[entity_id],
            castle,
        )
        row["sources"]["unmapped_exact_name_candidates"] = (
            [
                {"group": item["group"], "data_id": item["entity"]["_id"]}
                for item in by_name.get(entity["name"].casefold(), [])
            ]
            if matched is None
            else []
        )
        rows.append(row)
    supplemental = []
    for record in raw_records:
        entity = record["entity"]
        if entity["_id"] in matched_ids:
            continue
        supplemental.append(
            {
                "id": f"extracted-{entity['_id']}",
                "name": entity["name"],
                "group": record["group"],
                "data_id": entity["_id"],
                "seasonal_in_source": entity.get("is_seasonal", False),
                "catalog_exact_name_ids": [
                    item["id"]
                    for item in rows
                    if item["name"].casefold() == entity["name"].casefold()
                ],
                "max_recorded_level": max(
                    (row["level"] for row in entity.get("levels", [])), default=None
                ),
                "current_availability": "unverified_not_added_to_legal_roster",
                "behavior": "No mapped catalog/compiler identity; numeric presence is not availability or behavior support.",
            }
        )
    report = {
        "schema_version": 1,
        "status": "ROSTER_COVERAGE_AUDIT_NOT_COMPLETE_BATTLE_CERTIFICATION",
        "adapter_version": ADAPTER_VERSION,
        "catalog_snapshot": catalog.snapshot["snapshotCommit"],
        "catalog_retrieved_on": catalog.snapshot.get("retrievedOn"),
        "scope": {
            "attacking_town_hall": 16,
            "donor_town_hall": 18,
            "opponent_town_halls": [16, 17, 18],
            "current_loadout_filter_applied": False,
            "all_home_catalog_entities_included": True,
            "complete_battle_ready": False,
            "replay_calibrated": False,
        },
        "status_definitions": STATUS_LABELS,
        "summary": {
            "catalog_entities": len(rows),
            "conditional_mechanics": sum(
                row["behavior"]["status"] == "conditional_mechanics" for row in rows
            ),
            "passive_targets": sum(
                row["behavior"]["status"] == "passive_target_only" for row in rows
            ),
            "missing_behavior": sum(
                row["behavior"]["status"] == "missing_behavior" for row in rows
            ),
            "th16_attack_eligible": sum(row["th16_attack_eligible"] for row in rows),
            "th16_attack_with_conditional_mechanics": sum(
                row["th16_attack_eligible"]
                and row["behavior"]["status"] == "conditional_mechanics"
                for row in rows
            ),
            "th18_donation_candidates": sum(
                row["th18_donation"]["candidate"] for row in rows
            ),
            "defending_heroes_with_conditional_mechanics": sum(
                row["category"] == "hero"
                and row["behavior"]["defending_role"] is not None
                and row["behavior"]["defending_role"]["status"]
                == "conditional_mechanics"
                for row in rows
            ),
            "defending_garrison_troops_with_conditional_mechanics": sum(
                row["id"] in GARRISON_MEMBERS
                and row["behavior"]["defending_role"]["status"]
                == "conditional_mechanics"
                for row in rows
            ),
            "extracted_only_records": len(supplemental),
            "replay_calibrated": 0,
            "complete_battle_ready": 0,
        },
        "by_category": _category_counts(rows),
        "entities": rows,
        "archetypes": _archetype_coverage(rows),
        "prioritized_blockers": _priorities(rows),
        "source_evidence": {
            "extraction": deepcopy(provenance),
            "mapped_statistic_comparisons": audit["mapped_comparisons"],
            "direct_statistic_differences": len(audit["differences"]),
            "comparison_scope": "Only direct numeric-ID mappings are compared. Unique name matches are evidence links, not verified numeric identities or field comparisons.",
            "semantic_exclusions": audit["semantic_exclusions"],
            "declared_extracted_branch_selection": deepcopy(selection),
            "automatic_overrides_applied": False,
            "code_sha256": {
                name: sha256(content).hexdigest()
                for name, content in sorted((code_files or {}).items())
            },
        },
        "extracted_only_records": supplemental,
        "unresolved_announced_content": deepcopy(unresolved or {}),
        "limitations": [
            "Counts inventory entity types; they are not completion percentages, army strength scores or battle predictions.",
            "TH caps use the pinned catalog and its explicit secondary caps. They do not certify current patch truth, account ownership, acquisition, upgrades, or active super troops.",
            "TH18 donation candidates use donor technology and a maximum catalog TH16 castle. Real receiver level, lab cap, capacity and donation availability remain explicit account inputs.",
            "Non-supercharged levels are inventoried. Supercharged rows are identified but the entity compiler rejects supercharge.",
            "Passive HP/footprint actors do not supply lifecycle behavior. Defending heroes, seven Clan Castle troop types and Builder repair use separate conditional adapters; other garrison troops, guardians and crafted weapons remain incomplete.",
            "Attacking and defending hero coverage are reported separately. Five defending heroes have conditional banner-bound behavior; Dragon Duke remains unavailable. Attacking equipment and pets are not imported into defense.",
            "Crafted-defense module upgrades have no single ordinary level cap. Historical phases and incomplete unlock relations stay visible as unresolved metadata.",
            "Extraction name matching is evidence-only, used when an exact catalog numeric ID is absent. It never merges statistics or invents a compiler identity.",
            "Seasonal/extracted-only and announced content are separate from the legal roster until availability and numeric/behavior mappings are verified.",
            "Missing entity adapters cannot be bypassed with generic attack patterns. Full-village ranking requires integrated behavior and held-out replay validation.",
        ],
    }
    report["report_fingerprint"] = stable_id(report)
    return report
