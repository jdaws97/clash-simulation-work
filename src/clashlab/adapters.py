"""Source-linked entity statistics compiled into declared combat patterns.

This registry covers declared sectors, not full villages. Unsupported
entity behavior cannot be bypassed by supplying an ordinary attack pattern.
"""

from copy import deepcopy

from .combat import COMBAT_RULES, RULESET, PatternCombat, validate_pattern
from .common import InputError, identifier, integer, number, require
from .geometry import footprint
from .healing import (
    RULESET as SUPPORT_RULESET,
    SUPPORT_RULES,
    SupportCombat,
    validate_healing_field,
)
from .spatial import EPSILON, _blocked, _load_actors, simulate_spatial
from .ramping import RULESET as RAMP_RULESET, RAMP_RULES, RampCombat
from .deaths import RULESET as DEATH_RULESET, DEATH_RULES, DeathCombat
from .walls import RULESET as WALL_RULESET, WALL_RULES, WallRouting
from .spells import compile_freeze_spell
from .defense_patterns import (
    RULESET as AREA_DEFENSE_RULESET,
    RULES as AREA_DEFENSE_RULES,
    SCOPE as AREA_DEFENSE_SCOPE,
    compile_defense_pattern,
    compile_scattershot_ammunition,
    compile_bomb_tower_death,
)
from .townhalls import (
    RULESET as TOWN_HALL_RULESET,
    TOWN_HALL_RULES,
    TownHallCombat,
    compile_giga_inferno,
)
from .heroes import (
    RULESET as HERO_RULESET,
    SCOPE as HERO_SCOPE,
    HERO_RULES,
    HEROES,
    EQUIPMENT as HERO_EQUIPMENT,
    HeroCombat,
    compile_hero,
    compile_mirror_clones,
)
from .artillery import (
    RULESET as ARTILLERY_RULESET,
    RULES as ARTILLERY_RULES,
    SCOPE as ARTILLERY_SCOPE,
    ArtilleryCombat,
    compile_artillery,
)
from .traps import (
    RULESET as TRAP_RULESET,
    RULES as TRAP_RULES,
    SCOPE as TRAP_SCOPE,
    IMPACT_KINDS as DAMAGE_TRAPS,
    TrapCombat,
    compile_trap,
)
from .hit_status import (
    RULESET as HIT_RULESET,
    RULES as HIT_RULES,
    SCOPE as HIT_SCOPE,
    HitStatusCombat,
    compile_ice_golem,
)
from .engine_rules import (
    RULESET as EXTENDED_RULESET,
    RULES as EXTENDED_RULES,
    SCOPE as EXTENDED_SCOPE,
)
from .teslas import TeslaCombat, compile_hidden_tesla
from .valkyries import ValkyrieRouting, compile_valkyrie
from .classic_troops import CLASSIC_TROOPS, compile_classic_troop
from .recipe_troops import (
    RECIPE_TROOPS,
    RECIPE_ADAPTERS,
    RecipeTroopCombat,
    compile_recipe_troop,
)
from .buffs import BUFF_SPELLS, BuffCombat, compile_buff_spell
from .buff_rules import (
    RULESET as BUFF_RULESET,
    RULES as BUFF_RULES,
    SCOPE as BUFF_SCOPE,
)


from .indirect_defenses import IndirectDefenseCombat, compile_indirect_defense
from .indirect_rules import (
    RULESET as INDIRECT_RULESET,
    RULES as INDIRECT_RULES,
    SCOPE as INDIRECT_SCOPE,
)


from .sweepers import SweeperCombat, compile_air_sweeper
from .sweeper_rules import (
    RULESET as SWEEPER_RULESET,
    RULES as SWEEPER_RULES,
    SCOPE as SWEEPER_SCOPE,
)


from .defending_heroes import (
    DEFENDING_HEROES,
    DefendingHeroCombat,
    apply_defending_unit_responses,
    compile_defending_hero,
)
from .defending_hero_rules import (
    RULESET as DEFENDING_HERO_RULESET,
    RULES as DEFENDING_HERO_RULES,
    SCOPE as DEFENDING_HERO_SCOPE,
)


from .spell_towers import SpellTowerCombat, compile_spell_tower
from .spell_tower_rules import (
    RULESET as SPELL_TOWER_RULESET,
    RULES as SPELL_TOWER_RULES,
    SCOPE as SPELL_TOWER_SCOPE,
)
from .builder_huts import BuilderHutCombat, compile_builder_hut
from .builder_rules import (
    RULESET as BUILDER_RULESET,
    RULES as BUILDER_RULES,
    SCOPE as BUILDER_SCOPE,
)
from .garrisons import (
    GARRISON_MEMBERS,
    GarrisonCombat,
    compile_garrison_castle,
    compile_garrison_member,
)
from .garrison_rules import (
    RULESET as GARRISON_RULESET,
    RULES as GARRISON_RULES,
    SCOPE as GARRISON_SCOPE,
)


from .firespitters import FirespitterCombat, compile_firespitter
from .firespitter_rules import (
    RULESET as FIRESPITTER_RULESET,
    RULES as FIRESPITTER_RULES,
    SCOPE as FIRESPITTER_SCOPE,
)


from .trap_lifecycle_rules import (
    RULESET as TRAP_LIFECYCLE_RULESET,
    RULES as TRAP_LIFECYCLE_RULES,
    SCOPE as TRAP_LIFECYCLE_SCOPE,
)
from .skeleton_traps import SkeletonTrapCombat, compile_skeleton_reserves
from .tornado_traps import TornadoTrapCombat
from .trap_support import validate_trap_footprints
from .guardians import GUARDIANS, GuardianCombat, compile_guardian, compile_th18_hall
from .guardian_rules import (
    RULESET as GUARDIAN_RULESET,
    RULES as GUARDIAN_RULES,
    SCOPE as GUARDIAN_SCOPE,
)
from .reinforcements import (
    ReinforcementCombat,
    attach_payload_member,
    compile_attacking_reinforcements,
    compile_received_spell,
    validate_received_entity,
)
from .siege_machines import SIEGE_MACHINES, SiegeCombat, compile_siege
from .siege_extensions import (
    BOUND_RECIPE_SIEGES,
    compile_extended_siege,
    recipe_siege_runtime,
    attach_barracks_member,
)
from .siege_lifecycle import (
    BOUND_PERMANENT_SIEGES,
    compile_permanent_siege,
    permanent_siege_runtime,
)
from .siege_barrels import attach_barrel_member
from .siege_rules import (
    RULESET as SIEGE_RULESET,
    RULES as SIEGE_RULES,
    SCOPE as SIEGE_SCOPE,
)
from .hero_pets import (
    SUPPORTED_PETS,
    PetCombat,
    compile_pets,
    compile_pet_healing_policy,
)
from .pet_rules import RULESET as PET_RULESET, RULES as PET_RULES, SCOPE as PET_SCOPE
from .hero_roster_rules import (
    RULESET as HERO_ROSTER_RULESET,
    RULES as HERO_ROSTER_RULES,
    SCOPE as HERO_ROSTER_SCOPE,
    select_duke_isolation_rules,
)
from .hero_roster import HeroRosterCombat
from .termination_rules import (
    RULESET as TERMINATION_RULESET,
    RULES as TERMINATION_RULES,
    SCOPE as TERMINATION_SCOPE,
)
from .heroes import EXTENDED_HEROES, EXTENDED_EQUIPMENT_OWNERS
from .advanced_defense_rules import (
    RULESET as ADVANCED_DEFENSE_RULESET,
    RULES as ADVANCED_DEFENSE_RULES,
    SCOPE as ADVANCED_DEFENSE_SCOPE,
)
from .advanced_defenses import (
    REVENGE_GAPS,
    MultiGearCombat,
    compile_multi_gear,
    compile_super_wizard,
)
from .giga_bombs import GigaBombCombat
from .revenge_towers import compile_revenge_tower
from .defense_variants import (
    GearedCannonCombat,
    attach_explicit_defense_ammunition,
    compile_geared_cannon,
)
from .attack_spell_models import SUPPORTED_ATTACK_SPELLS, compile_attack_spell
from .attack_spells import AttackSpellCombat
from .advanced_spell_models import SUPPORTED_SPELLS as ADVANCED_SPELLS
from .advanced_spell_bindings import (
    validate_binding,
    compile_reserves as compile_spell_reserves,
    SharedAdvancedSpells,
    BOUND_SPELLS,
)
from .recipe_spells import compile_totem_reserve
from .recipe_frosty import compile_frostmite_reserves
from .attacking_extensions import (
    SCOPE as ATTACKING_EXTENSION_SCOPE,
    compile_attacking_extension,
)
from .crafted_bindings import compile_shared_crafted, validate_crafted_owners
from .crafted_defenses import CraftedDefenseCombat
from .troop_line_bindings import (
    LINE_ENTITIES,
    validate_line_binding,
    validate_line_owners,
)
from .electro_titans import ElectroTitanCombat
from .troop_death_buffs import TroopDeathBuffCombat, compile_super_valkyrie
from .wall_breakers import compile_wall_breaker
from .attack_spell_rules import (
    RULESET as ATTACK_SPELL_RULESET,
    RULES as ATTACK_SPELL_RULES,
    SCOPE as ATTACK_SPELL_SCOPE,
)


ADAPTER_VERSION = "catalog-sector-adapters-v29"
SCOPE = "wall_free_sector_without_heroes_pets_traps_defending_troops_or_town_hall"
WALL_SCOPE = (
    "wall_breach_sector_without_heroes_pets_traps_defending_troops_or_town_hall"
)
SUPPORT_SCOPE = (
    "support_and_wall_sector_without_heroes_pets_traps_defending_troops_or_town_hall"
)
RAMP_SCOPE = "lock_ramp_support_wall_sector_without_heroes_pets_traps_defending_troops_or_town_hall"
DEATH_SCOPE = "death_effects_air_support_wall_sector_without_heroes_pets_traps_defending_troops_or_town_hall"
TOWN_HALL_SCOPE = "town_hall_hazards_air_support_wall_sector_without_heroes_pets_traps_or_defending_troops"
UNIT_ADAPTERS = {
    "wall-breaker": ("ground", "radial"),
    **{entity: ("ground", "single") for entity in LINE_ENTITIES},
    "super-valkyrie": ("ground", "radial"),
    "electro-titan": ("ground", "single"),
    **RECIPE_ADAPTERS,
    "archer": ("ground", "single"),
    "barbarian": ("ground", "single"),
    "minion": ("air", "single"),
    "pekka": ("ground", "single"),
    "thrower": ("ground", "single"),
    "dragon": ("air", "radial"),
    "electro-dragon": ("air", "chain"),
    "dragon-rider": ("air", "single"),
    "ice-golem": ("ground", "single"),
    "valkyrie": ("ground", "radial"),
    "giant": ("ground", "single"),
    "wizard": ("ground", "radial"),
    "hog-rider": ("ground", "single"),
}
DEFENSE_ADAPTERS = {
    "firespitter": {"normal": "firespitter_ballistic_bullet"},
    "cannon": {"normal": "single", "gearedUpBurst": "single"},
    "archer-tower": {"normal": "single", "gearedUpFastAttack": "single"},
    "air-defense": {"normal": "single"},
    "x-bow": {"normal": "single", "airAndGround": "single"},
    "multi-archer-tower": {"normal": "multi_target"},
    "ricochet-cannon": {"normal": "chain"},
    "monolith": {"normal": "single"},
    "inferno-tower": {"normal": "single", "multiTarget": "multi_target"},
    "wizard-tower": {"normal": "radial"},
    "scattershot": {"normal": "directional_splash"},
    "bomb-tower": {"normal": "radial"},
    "hidden-tesla": {"normal": "single"},
    "builders-hut": {"normal": "single"},
    "spell-tower": {
        "rage": "reactive_rage_field",
        "poison": "reactive_poison_field",
        "invisibility": "reactive_invisibility_field",
        "earthquake": "instant_maximum_hp_pulse",
    },
}
MISSING_MECHANICS = {
    "ruin-witch": [
        "rubble selection, timed summons, persistent pending summons, and despawn"
    ],
    "druid": [
        "ground movement with wall jumps, healing-chain target count and selection",
        "current Bear statistics and the full timed/defeat transformation lifecycle",
    ],
    "town-hall": [
        "Town Hall-specific weapons, activation, guardians and destruction effects"
    ],
    "clan-castle": [
        "garrison capacity, emergence, targeting and defending-troop aggro"
    ],
}
STATIC_CATEGORIES = {"army", "resource", "research", "other"}
MODIFIERS = {
    "hitpoints_multiplier",
    "damage_multiplier",
    "maximum_hp_damage_multiplier",
    "attack_interval_multiplier",
    "range_multiplier",
    "movement_speed_multiplier",
}


def partial_adapter_status(entity, level=None, role=None, mode=None):
    entity_id = entity["id"]
    if entity_id == "wall-breaker":
        available = role != "defense" and mode in {None, "normal"}
        return {
            "available": available,
            "scope": HERO_ROSTER_SCOPE,
            "replay_validated": False,
            "missing": (
                [] if available else ["Wall Breaker requires attacking normal mode"]
            ),
            "required": [
                "Explicit extension, troop behavior and Wall Breaker blast policies"
            ],
        }
    if entity_id in LINE_ENTITIES:
        available = mode in {None, "normal"}
        return {
            "available": available,
            "scope": HERO_ROSTER_SCOPE,
            "replay_validated": False,
            "missing": [] if available else ["Line weapons require normal mode"],
            "required": [
                "Explicit extension scope, line_binding, line_weapon_parameters; defensive Castle role when applicable"
            ],
        }
    if entity_id == "super-valkyrie":
        available = role != "defense" and mode in {None, "normal"}
        return {
            "available": available,
            "scope": HERO_ROSTER_SCOPE,
            "replay_validated": False,
            "missing": (
                [] if available else ["Death Rage supports attacking normal mode only"]
            ),
            "required": [
                "Explicit attacking extension scope, Valkyrie placement and complete experimental death_buff_parameters"
            ],
        }
    if entity_id == "electro-titan":
        available = role != "defense" and mode in {None, "normal"}
        return {
            "available": available,
            "scope": HERO_ROSTER_SCOPE,
            "replay_validated": False,
            "missing": (
                [] if available else ["Titan aura supports attacking normal mode only"]
            ),
            "required": [
                "Explicit attacking_extension_scope and complete aura_parameters"
            ],
        }
    if entity_id in RECIPE_TROOPS:
        return {
            "available": role != "defense" and mode in {None, "normal"},
            "scope": HERO_ROSTER_SCOPE,
            "replay_validated": False,
            "missing": (
                []
                if role != "defense" and mode in {None, "normal"}
                else [
                    "Recipe troops support explicit attacking normal-mode contracts only"
                ]
            ),
            "required": [
                "Complete recipe_parameters, splash/death geometry, lifecycle and targeting hypotheses"
            ],
        }
    if entity_id in SUPPORTED_ATTACK_SPELLS | ADVANCED_SPELLS:
        bound = entity_id not in ADVANCED_SPELLS or entity_id in BOUND_SPELLS
        available = mode in {None, "normal"} and bound
        return {
            "available": available,
            "scope": ATTACK_SPELL_SCOPE,
            "replay_validated": False,
            "missing": (
                []
                if available
                else [
                    (
                        "Advanced spell shared lifecycle is not yet bound"
                        if not bound
                        else "Unsupported attacking spell mode"
                    )
                ]
            ),
            "required": [
                "Explicit attack_spells cast contracts, quantity mappings, geometry and protection policies",
                *(
                    [
                        "Explicit advanced_spell_binding; compiled finite reserves and trigger policies"
                    ]
                    if entity_id in ADVANCED_SPELLS
                    else []
                ),
                "Explicit repeated Earthquake counters, Poison pulse growth, or visibility acquisition and collision policies where applicable",
            ],
            "limitations": [
                "Conditional source mappings and mechanics are not replay calibrated"
            ],
        }
    if entity_id == "revenge-tower":
        return {
            "available": mode == "stage1",
            "scope": ADVANCED_DEFENSE_SCOPE,
            "replay_validated": False,
            "missing": deepcopy(REVENGE_GAPS["missing"]),
            "source_audit": deepcopy(REVENGE_GAPS),
            "required": [
                "Explicit experimental revenge_parameters with four-phase mapping and caller-supplied HP transitions"
            ],
        }
    if entity_id == "crafting-station":
        return {
            "available": mode in {"passive", "normal"},
            "scope": HERO_ROSTER_SCOPE,
            "replay_validated": False,
            "missing": (
                []
                if mode in {"passive", "normal"}
                else [
                    "Selected crafted weapon requires normal mode and complete conditional policies"
                ]
            ),
        }
    if entity_id in {"multi-gear-tower", "super-wizard-tower", "giga-bomb"}:
        modes = (
            {None, "normal", "fastAttack"}
            if entity_id == "multi-gear-tower"
            else {None, "normal"}
        )
        available = mode in modes
        return {
            "available": available,
            "scope": ADVANCED_DEFENSE_SCOPE,
            "replay_validated": False,
            "missing": [] if available else ["Unsupported advanced defense mode"],
            "required": [
                "Explicit catalog per-hit burst mapping or primary-centered fanout geometry and release policies",
                "Giga Bomb requires all attacker response weights plus trigger, blast, and finite knockback policies",
            ],
            "limitations": [
                "Conditional source mappings and mechanics are not replay calibrated"
            ],
        }
    if entity_id == "logger":
        return {
            "available": False,
            "scope": GUARDIAN_SCOPE,
            "replay_validated": False,
            "missing": ["Logger shared projectile, pushback and continuation bindings"],
        }
    if entity_id in GUARDIANS or (entity_id == "town-hall" and level == 18):
        available = mode in (
            {None, "guardian"} if entity_id == "town-hall" else {None, "normal"}
        )
        return {
            "available": available,
            "scope": GUARDIAN_SCOPE,
            "replay_validated": False,
            "missing": [] if available else ["Unsupported Guardian/Hall mode"],
            "required": [
                "Explicit selected Guardian binding, emergence, patrol, leash and death hypotheses"
            ],
            "limitations": [
                "Longshot and Smasher only; Logger and upgrade absence remain unsupported; no replay calibration"
            ],
        }
    if entity_id in {"skeleton-trap", "tornado-trap"}:
        return {
            "available": (
                entity_id == "tornado-trap" or mode in {None, "ground", "air"}
            ),
            "scope": TRAP_LIFECYCLE_SCOPE,
            "replay_validated": False,
            "required": [
                "Explicit trigger, effect membership and lifecycle policies",
                "Skeleton mode and unarmored summon-statistic hypothesis, or Tornado damage-quantity and finite-motion hypotheses",
            ],
        }
    if entity_id == "firespitter":
        return {
            "available": mode in {None, "normal"},
            "scope": FIRESPITTER_SCOPE,
            "missing": (
                [] if mode in {None, "normal"} else ["Unsupported Firespitter mode"]
            ),
            "limitations": [
                "Explicit orientation, per-shot spread, bullet speed/radius and post-burst gap mapping",
                "Per-shot damage retained separately from conflicting catalog/extraction displayed DPS",
                "Live first-contact projectile simulation is not replay calibrated",
            ],
        }
    if entity_id in SIEGE_MACHINES | BOUND_RECIPE_SIEGES | BOUND_PERMANENT_SIEGES:
        return {
            "available": mode in {None, "normal"},
            "scope": HERO_ROSTER_SCOPE if entity_id == "sky-wagon" else SIEGE_SCOPE,
            "replay_validated": False,
            "missing": [] if mode in {None, "normal"} else ["Unsupported siege mode"],
            "required": [
                "Independent source and receipt levels, named weapon/death statistics and explicit area geometry",
                "Declared deployment regions, travel, decay, termination and linked payload-release hypotheses",
            ],
        }
    if entity_id in SUPPORTED_PETS:
        return {
            "available": True,
            "scope": PET_SCOPE,
            "replay_validated": False,
            "required": [
                "Separate scene pet assignment to one attacking hero and owned pet level",
                "Explicit lifecycle, timing, targeting and status interaction policies",
            ],
        }
    if entity_id == "clan-castle" or (
        role == "defense" and entity_id in GARRISON_MEMBERS
    ):
        return {
            "available": True,
            "scope": GARRISON_SCOPE,
            "replay_validated": False,
            "missing": [],
            "required": [
                "Explicit castle linkage, capacity, donor/receiver level, release and targeting hypotheses"
            ],
        }
    if entity_id == "builders-hut":
        available = mode in {None, "normal"}
        return {
            "available": available,
            "scope": BUILDER_SCOPE,
            "supported_modes": ["normal"],
            "missing": [] if available else ["Builder-only mode is not a building"],
            "limitations": [
                "Level one is passive; later levels combine turret and internal worker",
                "Worker targeting, contact travel, repair timing and stacking are explicit hypotheses",
                "Workers are untargetable and inherit only declared Freeze and Poison status behavior",
                "Lightning target reset requires a separate adapter; not replay calibrated",
            ],
        }
    if entity_id == "spell-tower":
        unlocks = {"rage": 1, "poison": 2, "invisibility": 3, "earthquake": 4}
        modes = {
            selected: {"available_from_level": minimum}
            for selected, minimum in unlocks.items()
            if level is None or level >= minimum
        }
        available = mode is None or mode in modes
        return {
            "available": available,
            "scope": (
                ADVANCED_DEFENSE_SCOPE if mode == "earthquake" else SPELL_TOWER_SCOPE
            ),
            "supported_modes": modes,
            "unsupported_modes": {},
            "missing": (
                []
                if available
                else ["Selected Spell Tower mode is unavailable or unsupported"]
            ),
            "limitations": [
                "Explicit trigger, cast, recharge, death-release and recipient policies",
                "Invisibility uses fresh aggregate structure damage without source attribution",
                "Earthquake requires an explicit maximum-HP pulse hypothesis; no mode is replay calibrated",
            ],
        }
    if role == "defense" and entity_id in DEFENDING_HEROES:
        return {
            "available": True,
            "scope": DEFENDING_HERO_SCOPE,
            "missing": [],
            "required": [
                "Explicit banner, aggro, leash, patrol, healing and destruction policies"
            ],
        }
    if entity_id == "air-sweeper":
        return {
            "available": True,
            "scope": SWEEPER_SCOPE,
            "missing": [],
            "limitations": [
                "Explicit orientation, gust geometry, travel and finite displacement policies",
                "Not replay calibrated",
            ],
        }
    if entity_id in {"mortar", "eagle-artillery"}:
        return {
            "available": True,
            "scope": INDIRECT_SCOPE,
            "missing": [],
            "limitations": [
                "Explicit shell timing, projectile travel and targeting hypotheses",
                "Eagle requires complete activation weights and shockwave policies",
                "Not replay calibrated",
            ],
        }
    if entity_id in BUFF_SPELLS:
        return {
            "available": True,
            "scope": BUFF_SCOPE,
            "replay_validated": False,
            "required": [
                "Explicit duration, additive movement and damage statistic mappings",
                "Continuous area membership, exit linger and strongest-per-axis stacking",
                "Explicit troop, hero, pet, siege and other class scaling",
            ],
        }
    if entity_id in CLASSIC_TROOPS:
        return {
            "available": True,
            "scope": {
                "giant": WALL_SCOPE,
                "wizard": AREA_DEFENSE_SCOPE,
                "hog-rider": HERO_SCOPE,
            }[entity_id],
            "replay_validated": False,
            "required": [
                "Explicit wall behavior; Hog Rider uses shared enemy-wall traversal",
                "Wizard requires explicit splash radius, projectile and layer policies",
                "Defending-troop aggro and replay calibration remain unavailable",
            ],
        }
    if entity_id in {"valkyrie", "hidden-tesla"}:
        return {
            "available": True,
            "scope": EXTENDED_SCOPE,
            "replay_validated": False,
            "required": [
                (
                    "Valkyrie requires source-centered radius and reachable pair-placement parameters"
                    if entity_id == "valkyrie"
                    else "Tesla requires reveal, readiness, threshold and footprint policies"
                ),
                "Geometry and timing remain explicit hypotheses requiring replay calibration",
            ],
        }
    if entity_id == "spring-trap":
        return {
            "available": True,
            "scope": TRAP_SCOPE,
            "replay_validated": False,
            "required": [
                "Explicit single-target or legacy capacity allocation and unit classifications",
                "Explicit oversized damage, push geometry, collision, protection and lockout policies",
            ],
        }
    if entity_id == "ice-golem":
        return {
            "available": True,
            "scope": HIT_SCOPE,
            "replay_validated": False,
            "required": [
                "Explicit hit-slow strength, duration and protection policy",
                "Explicit death-freeze delay, radius scaling and target membership",
                "Defending Ice Golems and garrison behavior remain unsupported",
            ],
        }
    if entity_id in DAMAGE_TRAPS:
        return {
            "available": True,
            "scope": TRAP_SCOPE,
            "replay_validated": False,
            "required": [
                "Explicit arming, delay, travel speed, exclusions and dead-trigger policy",
                "Trap instances belong in the separate traps list, outside destruction actors",
            ],
        }
    if entity_id == "town-hall" and level == 17:
        return {
            "available": True,
            "scope": ARTILLERY_SCOPE,
            "supported_levels": [17],
            "replay_validated": False,
            "required": [
                "Separate always-active projectile lifecycle without a death blast",
                "Explicit impact trigger, flame geometry, growth, overlap and pulse clock",
                "Current numeric values and complete TH17 village behavior remain unverified",
            ],
        }
    if entity_id in HEROES or entity_id in HERO_EQUIPMENT:
        return {
            "available": True,
            "scope": (
                HERO_ROSTER_SCOPE
                if entity_id in EXTENDED_HEROES
                or entity_id in EXTENDED_EQUIPMENT_OWNERS
                else HERO_SCOPE
            ),
            "replay_validated": False,
            "required": [
                "Explicit attacking hero, equipment pair, recovery mapping and manual ability policy",
                "Explicit passive pulse clocks, cast membership or summon geometry for the selected equipment",
                "Supported pets require the v25 or later scope; automatic activation and Warden army following remain unavailable, and defending hero roles require their separate adapter",
            ],
        }
    if entity_id in {"wizard-tower", "scattershot", "bomb-tower"}:
        return {
            "available": True,
            "scope": AREA_DEFENSE_SCOPE,
            "replay_validated": False,
            "required": [
                "Explicit area geometry, projectile destination/dead-primary policy and layer filtering",
                "Scattershot requires initialized finite ammunition and explicit distance falloff mapping",
                "Bomb Tower requires actual-death blast timing, radius and damage scaling",
            ],
        }
    if entity_id == "town-hall" and (level is None or level in {14, 15, 16}):
        return {
            "available": True,
            "scope": TOWN_HALL_SCOPE,
            "supported_levels": [14, 15, 16],
            "additional_scopes": [{"scope": ARTILLERY_SCOPE, "supported_levels": [17]}],
            "replay_validated": False,
            "required": [
                "Explicit weapon level, initial activation state, destruction threshold and readiness",
                "Explicit blast/poison delay, poison geometry/growth/pulses, lingering and protection policies",
            ],
        }
    if entity_id == "freeze-spell":
        return {
            "available": True,
            "scope": "conditional_status_command_in_explicit_pattern_sector",
            "replay_validated": False,
            "required": [
                "Explicit duration/radius modifiers, cast center/time and caster team"
            ],
        }
    if entity_id in {"electro-dragon", "dragon-rider"}:
        return {
            "available": True,
            "scope": DEATH_SCOPE,
            "replay_validated": False,
            "required": [
                "Explicit death statistic quantity, impact sequence, geometry and timing",
                "Explicit chain parameters/readiness for Electro Dragon or target-layer branch for Dragon Rider",
            ],
        }
    if entity_id == "inferno-tower":
        return {
            "available": True,
            "scope": RAMP_SCOPE,
            "replay_validated": False,
            "required": [
                "explicit single-mode timing/reset or multi-beam cadence hypotheses"
            ],
        }
    if entity_id in {"healer", "healing-spell"}:
        return {
            "available": True,
            "scope": SUPPORT_SCOPE,
            "replay_validated": False,
            "required": [
                "explicit healing selection, stacking, projectile and pulse hypotheses"
            ],
        }
    if entity_id in {"root-rider", "wall"}:
        return {
            "available": True,
            "scope": WALL_SCOPE,
            "replay_validated": False,
            "required": [
                "explicit wall motion, routing, range and cooldown hypotheses"
            ],
        }
    if entity_id in MISSING_MECHANICS:
        return {"available": False, "missing": MISSING_MECHANICS[entity_id]}
    if entity_id in UNIT_ADAPTERS or entity_id in DEFENSE_ADAPTERS:
        return {"available": True, "scope": SCOPE, "replay_validated": False}
    if entity["category"] in STATIC_CATEGORIES and entity.get("levels"):
        return {
            "available": True,
            "scope": "passive_structure_in_declared_sector",
            "replay_validated": False,
        }
    return {
        "available": False,
        "missing": ["complete entity-specific behavior adapter"],
    }


def _modifiers(instance):
    modifiers = require(instance, "modifiers")
    if set(modifiers) != MODIFIERS | {"source"}:
        raise InputError("Every statistic modifier and its source must be explicit")
    identifier(modifiers["source"], "statistic modifier source")
    for field in MODIFIERS:
        number(modifiers[field], field, 0)
    if (
        modifiers["hitpoints_multiplier"] == 0
        or modifiers["attack_interval_multiplier"] == 0
    ):
        raise InputError("HP and attack interval multipliers must be positive")
    return modifiers


def _pattern(
    entity_id,
    kind,
    mode,
    stats,
    parameters,
    target_kinds,
    target_layers,
    modifiers,
    source,
):
    if entity_id in {"wizard-tower", "scattershot", "bomb-tower"}:
        pattern = compile_defense_pattern(entity_id, mode, stats, parameters, source)
        validate_pattern(pattern)
        return pattern
    needed = {"projectile"}
    if kind == "radial":
        needed.add("radius")
    elif kind == "multi_target":
        needed.add("allocation")
    elif kind == "chain":
        needed |= {
            "jump_metric",
            "jump_delay_seconds",
            "tie_break",
            "allow_protected_links",
        }
        if entity_id == "electro-dragon":
            needed |= {"damage_multipliers", "jump_range"}
    if set(parameters) != needed:
        raise InputError(
            "Attack parameters must exactly cover the selected entity pattern"
        )
    pattern = {
        "kind": kind,
        "source": source,
        "target_kinds": target_kinds,
        "target_layers": target_layers,
        "maximum_hp_fraction": 0,
        **deepcopy(parameters),
    }
    if entity_id == "monolith":
        pattern["maximum_hp_fraction"] = (
            number(
                require(stats, "bonusDamagePercent"),
                "Monolith bonus percentage",
                0,
                100,
            )
            / 100
            * modifiers["maximum_hp_damage_multiplier"]
        )
    elif kind == "multi_target":
        pattern["projectiles_per_volley"] = integer(
            require(stats if entity_id == "inferno-tower" else mode, "numberOfTargets"),
            "multi-target projectile count",
            1,
        )
    elif kind == "chain":
        if entity_id == "electro-dragon":
            multipliers = require(parameters, "damage_multipliers")
            if not isinstance(multipliers, list) or not 1 <= len(multipliers) <= 5:
                raise InputError(
                    "The conditional normal Electro Dragon chain supports at most five explicit links"
                )
            previous = 1
            for multiplier in multipliers:
                number(multiplier, "Electro Dragon chain multiplier", EPSILON, previous)
                previous = multiplier
            if multipliers[0] != 1:
                raise InputError(
                    "Electro Dragon's first link must use the selected full hit"
                )
        else:
            primary = number(require(stats, "damagePerShot"), "primary shot", EPSILON)
            secondary = number(
                require(stats, "secondaryChainDamagePerShot"), "ricochet second shot", 0
            )
            pattern["damage_multipliers"] = [1, secondary / primary]
            pattern["jump_range"] = number(
                require(mode, "chainRange"), "ricochet range", 0
            )
    validate_pattern(pattern)
    return pattern


def compile_actor(
    instance,
    catalog,
    movement_units_per_tile,
    allow_walls=False,
    allow_support=False,
    allow_ramps=False,
    allow_deaths=False,
    allow_town_halls=False,
    allow_area_defenses=False,
    allow_heroes=False,
    allow_artillery=False,
    allow_hit_status=False,
    allow_extended=False,
    allow_indirect=False,
    allow_sweepers=False,
    allow_defending_heroes=False,
    allow_spell_towers=False,
    allow_builders=False,
    allow_garrisons=False,
    allow_firespitters=False,
    allow_guardians=False,
    allow_reinforcements=False,
    allow_pets=False,
    allow_advanced_defenses=False,
    allow_hero_extensions=False,
):
    entity_id = require(instance, "entity")
    crafted = entity_id == "crafting-station" and instance.get("mode") == "normal"
    if crafted and not allow_hero_extensions:
        raise InputError("Selected crafted defenses require explicit v27+ scope")
    if not crafted and any(
        key in instance for key in ("crafted_parameters", "crafted_shared_binding")
    ):
        raise InputError("Crafted parameters require the selected normal-mode Station")
    if entity_id == "logger":
        raise InputError(
            "Logger shared projectile, pushback and continuation are not bound"
        )
    if entity_id in {"electro-titan", "super-valkyrie", "wall-breaker"} | LINE_ENTITIES:
        if (
            not allow_hero_extensions
            or instance.get("attacking_extension_scope") != ATTACKING_EXTENSION_SCOPE
        ):
            raise InputError(
                "Bound attacking extensions require the v27+ scope and explicit attacking extension opt-in"
            )
    elif "attacking_extension_scope" in instance or "aura_parameters" in instance:
        raise InputError(
            "Attacking extension parameters require a bound lifecycle owner"
        )
    if entity_id in LINE_ENTITIES:
        validate_line_binding(require(instance, "line_binding"))
    elif "line_binding" in instance or "line_weapon_parameters" in instance:
        raise InputError("Line parameters require a bound line weapon owner")
    if any(
        key in instance
        for key in ("defending_extension_scope", "defending_extension_parameters")
    ) and (entity_id not in LINE_ENTITIES or instance.get("team") != "defense"):
        raise InputError("Defending extension requires a bound defensive lifecycle")
    if "death_buff_parameters" in instance and entity_id != "super-valkyrie":
        raise InputError("Death Rage parameters require Super Valkyrie")
    if "wall_breaker_parameters" in instance and entity_id != "wall-breaker":
        raise InputError("Wall Breaker parameters require their owned troop identity")
    if "aura_parameters" in instance and entity_id != "electro-titan":
        raise InputError("Aura parameters require Electro Titan")
    if "geared_cannon_parameters" in instance and (
        entity_id != "cannon" or instance.get("mode") != "gearedUpBurst"
    ):
        raise InputError("Geared Cannon parameters require their selected owner")
    if "defense_ammunition_parameters" in instance and entity_id != "x-bow":
        raise InputError("Explicit defense ammunition requires X-Bow")
    if "inferno_ammunition_parameters" in instance and entity_id != "inferno-tower":
        raise InputError("Explicit Inferno ammunition requires Inferno Tower")
    if (
        (entity_id == "cannon" and instance.get("mode") == "gearedUpBurst")
        or "defense_ammunition_parameters" in instance
        or "inferno_ammunition_parameters" in instance
        or (entity_id == "spell-tower" and instance.get("mode") == "earthquake")
    ) and not allow_advanced_defenses:
        raise InputError(
            "Experimental defense variants require their behavior adapter in the v26+ scope"
        )
    if entity_id in RECIPE_TROOPS and not allow_hero_extensions:
        raise InputError("Recipe troops require the explicit v27+ lifecycle scope")
    if "recipe_parameters" in instance and entity_id not in RECIPE_TROOPS:
        raise InputError("Recipe parameters require a supported recipe troop")
    if entity_id in SUPPORTED_ATTACK_SPELLS:
        raise InputError("Attacking spells belong in attack_spells, not actor entities")
    advanced_entities = {
        "multi-gear-tower": "multi_gear_parameters",
        "super-wizard-tower": "super_wizard_parameters",
        "revenge-tower": "revenge_parameters",
    }
    if "duke_parameters" in instance and entity_id != "dragon-duke":
        raise InputError("Duke intrinsic parameters require their owning hero")
    if entity_id in advanced_entities and not allow_advanced_defenses:
        raise InputError(
            "Advanced TH17/18 defenses require the explicit v26 sector scope"
        )
    for supported_entity, parameter_field in advanced_entities.items():
        if parameter_field in instance and entity_id != supported_entity:
            raise InputError(
                "Advanced defense parameters cannot attach to another entity"
            )
    if entity_id == "builders-hut" and not allow_builders:
        raise InputError("Builder's Hut requires the explicit v19 sector scope")
    if entity_id != "builders-hut" and "builder_parameters" in instance:
        raise InputError("Builder parameters cannot attach to another entity")
    entity = catalog.entity(entity_id)
    if entity["category"] == "crafted-defense":
        raise InputError("Crafted modules must be selected on one Crafting Station")
    siege = entity["category"] == "siege-machine"
    if siege and not allow_reinforcements:
        raise InputError("Siege carriers require the explicit v24 sector scope")
    if entity_id == "sky-wagon" and not allow_hero_extensions:
        raise InputError("Sky Wagon and its real generated weapons require v27+")
    if not siege and "siege_parameters" in instance:
        raise InputError("Siege parameters cannot attach to another entity")
    if (
        "siege_experimental_opt_in" in instance
        and entity_id not in BOUND_PERMANENT_SIEGES
    ):
        raise InputError("Siege extension opt-in requires a bound permanent carrier")
    if "barracks_member_parameters" in instance and (
        not allow_reinforcements
        or entity_id not in {"pekka", "wizard"}
        or require(instance, "team") != "attack"
        or "payload_member_parameters" in instance
    ):
        raise InputError(
            "Barracks reserves require one independent generated troop owner"
        )
    if "barrel_member_parameters" in instance and (
        not allow_reinforcements
        or not allow_hero_extensions
        or entity_id not in {"minion", "balloon", "baby-dragon"}
        or require(instance, "team") != "attack"
        or any(
            key in instance
            for key in (
                "payload_member_parameters",
                "garrison_member_parameters",
                "barracks_member_parameters",
            )
        )
    ):
        raise InputError(
            "Sky Wagon reserves require one independent v27+ generated troop owner"
        )
    if "payload_member_parameters" in instance:
        if not allow_reinforcements:
            raise InputError("Attacking payloads require the explicit v24 sector scope")
        if entity["category"] != "troop" or require(instance, "team") != "attack":
            raise InputError("Attacking payload parameters require ordinary troops")
        parameters = instance["payload_member_parameters"]
        validate_received_entity(
            entity_id,
            require(instance, "level"),
            require(instance, "town_hall"),
            parameters,
            catalog,
        )
        donor_instance = deepcopy(instance)
        donor_instance.pop("payload_member_parameters")
        donor_instance["town_hall"] = parameters["donor_town_hall"]
        actor = compile_actor(
            donor_instance,
            catalog,
            movement_units_per_tile,
            allow_walls,
            allow_support,
            allow_ramps,
            allow_deaths,
            allow_town_halls,
            allow_area_defenses,
            allow_heroes,
            allow_artillery,
            allow_hit_status,
            allow_extended,
            allow_indirect,
            allow_sweepers,
            allow_defending_heroes,
            allow_spell_towers,
            allow_builders,
            allow_garrisons,
            allow_firespitters,
            allow_guardians,
            allow_reinforcements,
            allow_pets,
            allow_advanced_defenses,
            allow_hero_extensions,
        )
        return attach_payload_member(
            actor,
            instance,
            entity,
            catalog.level(entity_id, instance["level"]),
            catalog,
        )
    guardian = entity["category"] == "guardian"
    guardian_hall = entity_id == "town-hall" and instance.get("level") == 18
    if (guardian or guardian_hall) and not allow_guardians:
        prefix = "Missing town-hall mechanics: " if guardian_hall else ""
        raise InputError(
            f"{prefix}TH18 Guardians require the explicit v23 sector scope"
        )
    if not guardian and any(
        key in instance for key in ("guardian_parameters", "smasher_parameters")
    ):
        raise InputError("Guardian parameters cannot attach to another entity")
    if not guardian_hall and "guardian_binding" in instance:
        raise InputError("Guardian binding requires a TH18 Hall")
    if entity_id == "firespitter" and not allow_firespitters:
        raise InputError("Firespitter requires the explicit v21 sector scope")
    if entity_id != "firespitter" and "firespitter_parameters" in instance:
        raise InputError("Firespitter parameters cannot attach to another entity")
    garrison_member = (
        entity["category"] == "troop" and require(instance, "team") == "defense"
    )
    if (entity_id == "clan-castle" or garrison_member) and not allow_garrisons:
        raise InputError("Defending garrisons require the explicit v20 sector scope")
    if entity_id != "clan-castle" and "garrison_parameters" in instance:
        raise InputError("Garrison parameters require a Clan Castle")
    if not garrison_member and "garrison_member_parameters" in instance:
        raise InputError("Garrison member parameters require a defending troop")
    if entity_id == "spell-tower" and not allow_spell_towers:
        raise InputError("Spell Tower requires the explicit v18 sector scope")
    if entity_id != "spell-tower" and "spell_tower_parameters" in instance:
        raise InputError("Spell Tower parameters cannot attach to another entity")
    defending_hero = (
        entity["category"] == "hero" and require(instance, "team") == "defense"
    )
    if defending_hero and not allow_defending_heroes:
        raise InputError("Defending heroes require the explicit v17 sector scope")
    if not defending_hero and "defending_hero_parameters" in instance:
        raise InputError("Defending hero parameters cannot attach to another role")
    if entity_id == "air-sweeper" and not allow_sweepers:
        raise InputError("Air Sweeper requires the explicit v16 sector scope")
    if entity_id != "air-sweeper" and "sweeper_parameters" in instance:
        raise InputError("Sweeper parameters cannot attach to another entity")
    if entity_id in {"mortar", "eagle-artillery"} and not allow_indirect:
        raise InputError("Indirect weapons require the explicit v15 sector scope")
    if (
        entity_id not in {"mortar", "eagle-artillery"}
        and "indirect_parameters" in instance
    ):
        raise InputError("Indirect weapon parameters cannot attach to another entity")
    if entity_id in {"valkyrie", "hidden-tesla"} and not allow_extended:
        raise InputError(
            "Valkyrie and Tesla require the extended lifecycle sector scope"
        )
    for expected, parameter in (
        ("valkyrie", "valkyrie_parameters"),
        ("hidden-tesla", "tesla_parameters"),
    ):
        if (
            entity_id != expected
            and parameter in instance
            and not (
                entity_id == "super-valkyrie" and parameter == "valkyrie_parameters"
            )
        ):
            raise InputError(f"{parameter} cannot attach to another entity")
    if entity_id == "ice-golem" and not allow_hit_status:
        raise InputError("Ice Golem requires the explicit hit-status sector scope")
    if entity_id != "ice-golem" and "ice_parameters" in instance:
        raise InputError("Ice Golem parameters cannot attach to another entity")
    if entity_id == "wizard" and not allow_area_defenses:
        raise InputError("Wizard requires the explicit area-pattern sector scope")
    if entity_id == "hog-rider" and not allow_heroes:
        raise InputError("Hog Rider requires the shared wall-jump sector scope")
    if entity_id != "wizard" and "wizard_parameters" in instance:
        raise InputError("Wizard parameters cannot attach to another entity")
    if entity["category"] == "trap":
        raise InputError(
            "Trap instances must use the separate traps list and trap scope"
        )
    if entity["category"] == "hero" and not allow_heroes:
        raise InputError("Heroes require the explicit hero/equipment sector scope")
    if entity_id not in HEROES and "hero_parameters" in instance:
        raise InputError("Hero parameters cannot attach to an ordinary entity")
    if entity["category"] == "hero-equipment":
        raise InputError("Hero equipment belongs in the selected hero loadout")
    if (
        entity_id in {"wizard-tower", "scattershot", "bomb-tower"}
        and not allow_area_defenses
    ):
        raise InputError(
            "Area defenses require the explicit area-defense/death-effects sector scope"
        )
    if entity_id == "bomb-tower" and not allow_deaths:
        raise InputError("Bomb Tower requires the explicit death-effects sector scope")
    if entity_id != "bomb-tower" and "bomb_death_parameters" in instance:
        raise InputError("Bomb Tower death parameters cannot attach to another entity")
    if entity_id != "scattershot" and "ammunition_parameters" in instance:
        raise InputError("Scattershot ammunition cannot attach to another entity")
    if entity_id == "town-hall" and not allow_town_halls:
        raise InputError(
            "Town Hall requires the explicit lifecycle/hazard sector scope"
        )
    if entity_id != "town-hall" and "town_hall_parameters" in instance:
        raise InputError(
            "Town Hall lifecycle parameters cannot be attached to another entity"
        )
    if entity_id in {"electro-dragon", "dragon-rider"} and not allow_deaths:
        raise InputError(
            "Air death-effect troops require the explicit death-effects sector scope"
        )
    if entity_id not in {"electro-dragon", "dragon-rider", "longshot"} and any(
        field in instance
        for field in ("death_parameters", "target_layer_policy", "readiness_policy")
    ):
        raise InputError(
            "Air troop lifecycle parameters cannot be attached to another entity"
        )
    if entity_id == "inferno-tower" and not allow_ramps:
        raise InputError("Inferno modes require the explicit lock-ramp sector scope")
    if entity_id != "inferno-tower" and (
        "ramp_parameters" in instance or "beam_parameters" in instance
    ):
        raise InputError("Inferno parameters cannot be attached to another entity")
    if entity_id == "healing-spell":
        raise InputError("Healing Spell belongs in the healing_spells field list")
    if entity_id == "freeze-spell":
        raise InputError("Freeze Spell belongs in the freeze_spells command list")
    if entity_id in BUFF_SPELLS:
        raise InputError("Rage and Haste Spell belong in the buff_spells cast list")
    if entity_id == "healer" and not allow_support:
        raise InputError("Healer requires the support-and-wall sector scope")
    if entity_id != "healer" and "healing_parameters" in instance:
        raise InputError("Healing parameters require a supported healing actor")
    if entity_id in {"root-rider", "wall"} and not allow_walls:
        raise InputError(
            "Root Rider and wall instances require the wall-breach sector scope"
        )
    if not allow_walls and "wall_parameters" in instance:
        raise InputError("Wall parameters require the wall-breach sector scope")
    support = partial_adapter_status(
        entity,
        require(instance, "level"),
        role="defense" if defending_hero or garrison_member else None,
        mode=require(instance, "mode"),
    )
    if not support["available"]:
        raise InputError(
            f"Missing {entity_id} mechanics: {', '.join(support['missing'])}"
        )
    level = integer(require(instance, "level"), "entity level", 1)
    town_hall = integer(
        require(instance, "town_hall"), "entity Town Hall", 1, catalog.maximum_town_hall
    )
    if require(instance, "supercharge") is not False:
        raise InputError("Only explicit non-supercharged entity levels are compiled")
    if (
        not garrison_member
        and not siege
        and "barrel_member_parameters" not in instance
        and not crafted  # Its explicit season/permanent selection is validated below.
        and not catalog.available(entity_id, level, town_hall)
    ):
        raise InputError("Entity level is unavailable at the declared Town Hall")
    row = catalog.level(entity_id, level)
    modifiers = _modifiers(instance)
    selected_mode = require(instance, "mode")
    statistics_mode = require(instance, "statistics_mode")
    team = identifier(require(instance, "team"), "entity team")
    destruction = require(instance, "counts_for_destruction")
    if not isinstance(destruction, bool):
        raise InputError("Destruction eligibility must be explicit")
    actor = {
        "id": identifier(require(instance, "id"), "entity instance"),
        "source": catalog.records[entity_id]["source"],
        "team": team,
        "hitpoints": number(require(row, "hitpoints"), "entity HP", 1)
        * modifiers["hitpoints_multiplier"],
        "first_attack_seconds": number(
            require(instance, "first_attack_seconds"), "first attack time", 0
        ),
        "spawn_seconds": require(instance, "spawn_seconds"),
        "x": require(instance, "x"),
        "y": require(instance, "y"),
        "counts_for_destruction": destruction,
        "minimum_range": 0,
        "entity_adapter": {
            "entity": entity_id,
            "level": level,
            "catalog_category": entity["category"],
            "town_hall": town_hall,
            "mode": selected_mode,
            "statistics_mode": statistics_mode,
            "adapter_version": ADAPTER_VERSION,
            "snapshot_verification": catalog.records[entity_id]["verification"],
            "behavior_verification": "conditional_pattern_not_replay_validated",
            "modifiers": deepcopy(modifiers),
        },
    }
    if crafted:
        return compile_shared_crafted(actor, instance, catalog)
    if siege:
        if entity_id in BOUND_PERMANENT_SIEGES:
            return compile_permanent_siege(
                actor,
                instance,
                entity,
                row,
                modifiers,
                catalog,
                movement_units_per_tile,
            )
        if entity_id in BOUND_RECIPE_SIEGES:
            return compile_extended_siege(
                actor,
                instance,
                entity,
                row,
                modifiers,
                catalog,
                movement_units_per_tile,
            )
        return compile_siege(
            actor, instance, entity, row, modifiers, catalog, movement_units_per_tile
        )
    if guardian:
        return compile_guardian(
            actor, instance, entity, row, modifiers, movement_units_per_tile
        )
    if guardian_hall:
        return compile_th18_hall(actor, instance, entity, row, modifiers)
    if defending_hero:
        return compile_defending_hero(
            actor, instance, entity, row, modifiers, catalog, movement_units_per_tile
        )
    if entity_id == "clan-castle":
        return compile_garrison_castle(actor, instance, entity, row, modifiers)
    if garrison_member and entity_id in LINE_ENTITIES:
        from .defending_cc_extensions import compile_defending_extension

        shadow = deepcopy(instance)
        shadow["team"] = "attack"
        shadow["town_hall"] = require(
            require(instance, "garrison_member_parameters"), "donor_town_hall"
        )
        for key in (
            "garrison_member_parameters",
            "defending_extension_parameters",
            "defending_extension_scope",
        ):
            shadow.pop(key, None)
        actor = compile_actor(
            shadow,
            catalog,
            movement_units_per_tile,
            allow_walls=allow_walls,
            allow_support=allow_support,
            allow_town_halls=allow_town_halls,
            allow_hero_extensions=allow_hero_extensions,
        )
        actor = compile_defending_extension(
            actor,
            instance,
            entity,
            row,
            modifiers,
            catalog,
            movement_units_per_tile,
            enabled_scope=require(instance, "defending_extension_scope"),
        )
        actor["entity_adapter"]["town_hall"] = town_hall
        return actor
    if garrison_member:
        return compile_garrison_member(
            actor, instance, entity, row, modifiers, catalog, movement_units_per_tile
        )
    if entity_id in {"mortar", "eagle-artillery"}:
        return compile_indirect_defense(actor, instance, entity, row, modifiers)
    if entity_id == "air-sweeper":
        return compile_air_sweeper(actor, instance, entity, row, modifiers)
    if entity_id == "firespitter":
        return compile_firespitter(actor, instance, entity, row, modifiers)
    if entity_id == "multi-gear-tower":
        return compile_multi_gear(actor, instance, entity, row, modifiers)
    if entity_id == "super-wizard-tower":
        return compile_super_wizard(actor, instance, entity, row, modifiers)
    if entity_id == "revenge-tower":
        return compile_revenge_tower(actor, instance, entity, row, modifiers)
    if entity_id == "cannon" and selected_mode == "gearedUpBurst":
        return compile_geared_cannon(actor, instance, entity, row, modifiers)
    if entity_id == "builders-hut":
        return compile_builder_hut(
            actor, instance, entity, row, modifiers, movement_units_per_tile
        )
    if entity_id == "spell-tower":
        return compile_spell_tower(actor, instance, entity, row, modifiers)
    if entity_id == "town-hall":
        if level == 17:
            if not allow_artillery:
                raise InputError(
                    "Missing town-hall mechanics: TH17 artillery requires "
                    "its explicit projectile/flame scope"
                )
            return compile_artillery(actor, instance, entity, row, modifiers)
        return compile_giga_inferno(actor, instance, entity, row, modifiers)
    if entity_id in HEROES:
        actor = compile_hero(
            actor,
            instance,
            entity,
            row,
            modifiers,
            catalog,
            movement_units_per_tile,
            allow_pets=allow_pets,
            allow_hero_extensions=allow_hero_extensions,
        )
        if actor["movement"] == "ground":
            parameters = require(instance, "wall_parameters")
            if entity_id in {"royal-champion", "grand-warden"}:
                if (
                    set(parameters) != {"kind", "source"}
                    or parameters["kind"] != "jump_enemy_walls"
                ):
                    raise InputError(
                        "RC and ground Warden require explicit enemy-wall jumping"
                    )
                identifier(parameters["source"], "hero wall-jump evidence")
                actor["wall_behavior"] = deepcopy(parameters)
            else:
                _compile_wall_behavior(actor, instance, entity, row, modifiers)
        elif "wall_parameters" in instance:
            raise InputError("Air heroes cannot select ground wall parameters")
        return actor
    if entity_id == "healer":
        actor = _compile_healer(
            actor, instance, entity, row, modifiers, movement_units_per_tile
        )
        if allow_town_halls:
            actor["hazard_class"] = "troop"
        return actor
    if entity_id in UNIT_ADAPTERS or entity_id == "root-rider":
        if (
            selected_mode != "normal"
            or statistics_mode != "normal"
            or team != "attack"
            or destruction
        ):
            raise InputError(
                "Unit adapters require attacking normal troops outside destruction counts"
            )
        movement, pattern_kind = (
            ("ground", "single")
            if entity_id == "root-rider"
            else UNIT_ADAPTERS[entity_id]
        )
        actor["housing_space"] = require(entity, "housingSpace")
        actor.update(
            {
                "kind": "unit",
                "layer": movement,
                "movement": movement,
                "speed": number(
                    require(entity, "movementSpeed"), "catalog movement speed", EPSILON
                )
                / movement_units_per_tile
                * modifiers["movement_speed_multiplier"],
                "blocking": False,
                "width": 0,
                "height": 0,
                "target_priorities": ["defense", "building"],
                "target_priority_tiers": [["defense", "building"]],
            }
        )
        if allow_support:
            actor["healing_class"] = "troop"
        if allow_town_halls:
            actor["hazard_class"] = "troop"
        if entity_id in {"root-rider", "dragon-rider", "ice-golem"}:
            actor["target_priority_tiers"] = [["defense"], ["building"]]
        mode = entity
    else:
        if team != "defense":
            raise InputError("Sector structures must belong to the defending team")
        width, height = footprint({"id": entity_id}, catalog)
        actor.update(
            {
                "layer": "ground",
                "movement": "stationary",
                "speed": 0,
                "blocking": True,
                "width": width,
                "height": height,
            }
        )
        if entity_id not in DEFENSE_ADAPTERS:
            if "wall_parameters" in instance:
                raise InputError(
                    "Passive structures cannot select troop wall parameters"
                )
            if (
                selected_mode != "passive"
                or statistics_mode != "none"
                or require(instance, "attack_parameters") != {}
            ):
                raise InputError(
                    "Passive structures need an explicit passive mode and empty attack parameters"
                )
            actor.update(
                {
                    "kind": "wall" if entity_id == "wall" else "building",
                    "damage": 0,
                    "attack_interval_seconds": number(
                        require(instance, "inactive_attack_interval_seconds"),
                        "inactive interval",
                        EPSILON,
                    ),
                    "range": 0,
                    "target_priorities": [],
                    "target_layers": [],
                    "attack_model": {"kind": "none", "source": actor["source"]},
                }
            )
            if entity_id == "wall" and destruction:
                raise InputError("Walls do not enter sector destruction counts")
            return actor
        if selected_mode not in DEFENSE_ADAPTERS[entity_id]:
            raise InputError("Defensive mode needs an additional behavior adapter")
        mode = require(require(entity, "modes"), selected_mode)
        if level < mode.get("availableFromLevel", 1):
            raise InputError("Defensive mode is not unlocked at this level")
        pattern_kind = DEFENSE_ADAPTERS[entity_id][selected_mode]
        actor.update(
            {
                "kind": "defense",
                "target_priorities": ["unit"],
                "target_priority_tiers": [["unit"]],
            }
        )
    shared_xbow_stats = (
        entity_id == "x-bow"
        and selected_mode == "airAndGround"
        and statistics_mode == "normal"
    )
    if statistics_mode != selected_mode and not shared_xbow_stats:
        raise InputError(
            "Selected behavior and statistics modes require an explicit supported mapping"
        )
    stats = require(require(row, "stats"), statistics_mode)
    target_type = (
        (
            "both"
            if entity_id in {"baby-dragon", "headhunter", "apprentice-warden"}
            else "ground"
        )
        if entity_id in RECIPE_TROOPS
        else ("ground" if entity_id in LINE_ENTITIES else require(entity, "targetType"))
    )
    if entity_id == "x-bow" and selected_mode == "normal":
        target_layers = ["ground"]
    elif target_type == "both":
        target_layers = ["ground", "air"]
    elif target_type in {"ground", "air"}:
        target_layers = [target_type]
    else:
        raise InputError("Entity target-layer semantics need an adapter")
    if entity_id == "dragon-rider":
        policy = require(instance, "target_layer_policy")
        if set(policy) != {"selection", "source"}:
            raise InputError("Dragon Rider target-layer policy must be explicit")
        identifier(policy["source"], "Dragon Rider layer evidence")
        selections = {
            "snapshot_ground_only_hypothesis": ["ground"],
            "historical_ground_and_air_hypothesis": ["ground", "air"],
        }
        if policy["selection"] not in selections:
            raise InputError("Unrecognized Dragon Rider target-layer branch")
        target_layers = selections[policy["selection"]]
        actor["entity_adapter"]["target_layer_policy"] = deepcopy(policy)
        if "readiness_policy" in instance:
            raise InputError(
                "Dragon Rider cannot silently select an Electro Dragon readiness field"
            )
    elif entity_id == "electro-dragon":
        if "target_layer_policy" in instance:
            raise InputError(
                "Electro Dragon cannot select a Dragon Rider target-layer branch"
            )
        policy = require(instance, "readiness_policy")
        if (
            set(policy) != {"selection", "source"}
            or policy["selection"] != "absolute_first_attack_seconds_hypothesis"
        ):
            raise InputError(
                "Electro Dragon's conditional first-shot readiness must be explicit"
            )
        identifier(policy["source"], "Electro Dragon readiness evidence")
        actor["entity_adapter"]["readiness_policy"] = deepcopy(policy)
    if entity_id in LINE_ENTITIES:
        target_layers = list(validate_line_binding(instance["line_binding"]))
        actor["entity_adapter"].update(
            line_binding=deepcopy(instance["line_binding"]),
            line_weapon_parameters=deepcopy(instance["line_weapon_parameters"]),
        )
    actor["target_layers"] = target_layers
    actor["damage"] = (
        number(require(stats, "damagePerShot"), "catalog damage per shot", EPSILON)
        * modifiers["damage_multiplier"]
    )
    if entity_id == "inferno-tower" and selected_mode == "normal":
        actor["damage"] = (
            number(require(stats, "dpsInitial"), "initial Inferno DPS", EPSILON)
            * number(require(mode, "attackSpeed"), "Inferno pulse interval", EPSILON)
            * modifiers["damage_multiplier"]
        )
    if actor["damage"] == 0:
        raise InputError("Disabling an entity weapon requires a status adapter")
    actor["attack_interval_seconds"] = (
        number(require(mode, "attackSpeed"), "catalog attack interval", EPSILON)
        * modifiers["attack_interval_multiplier"]
    )
    actor["range"] = (
        number(require(mode, "range"), "catalog attack range", 0)
        * modifiers["range_multiplier"]
    )
    if entity_id == "scattershot":
        actor["minimum_range"] = (
            number(require(mode, "minRange"), "Scattershot minimum range", 0)
            * modifiers["range_multiplier"]
        )
        compile_scattershot_ammunition(actor, instance, mode)
    actor["attack_model"] = _pattern(
        entity_id,
        pattern_kind,
        mode,
        stats,
        require(instance, "attack_parameters"),
        actor["target_priorities"],
        target_layers,
        modifiers,
        actor["source"],
    )
    actor["entity_adapter"][
        "selected_statistic"
    ] = "damagePerShot; attackSpeed interpreted as seconds per hit"
    actor["entity_adapter"]["reported_snapshot_dps"] = stats.get("dps")
    if entity_id == "inferno-tower":
        _compile_inferno(actor, instance, mode, stats, modifiers)
    if entity_id in {"electro-dragon", "dragon-rider"}:
        _compile_air_death(actor, instance, stats)
    if entity_id == "bomb-tower":
        compile_bomb_tower_death(actor, instance, row)
    if entity_id == "ice-golem":
        compile_ice_golem(actor, instance, entity, row)
    if entity_id in {
        "hog-rider",
        "headhunter",
        "super-wall-breaker",
        "apprentice-warden",
    }:
        # The troop compiler validates and attaches its wall traversal policy.
        pass
    elif allow_walls and actor["movement"] == "ground":
        _compile_wall_behavior(actor, instance, entity, row, modifiers)
    elif "wall_parameters" in instance:
        raise InputError("Only ground troops can select wall parameters")
    if entity_id == "valkyrie":
        compile_valkyrie(actor, instance)
    if entity_id == "wall-breaker":
        compile_wall_breaker(
            actor, instance, entity, row, modifiers, movement_units_per_tile
        )
        actor["entity_adapter"]["attacking_extension_scope"] = ATTACKING_EXTENSION_SCOPE
    if entity_id == "super-valkyrie":
        compile_super_valkyrie(actor, instance, entity)
        actor["entity_adapter"]["attacking_extension_scope"] = ATTACKING_EXTENSION_SCOPE
    if entity_id == "hidden-tesla":
        compile_hidden_tesla(actor, instance, entity)
    if entity_id in CLASSIC_TROOPS:
        compile_classic_troop(actor, instance, entity)
    if entity_id in RECIPE_TROOPS:
        compile_recipe_troop(actor, instance, entity, row, modifiers)
    if entity_id == "electro-titan" or entity_id in LINE_ENTITIES:
        compile_attacking_extension(
            actor,
            instance,
            entity,
            row,
            modifiers,
            movement_units_per_tile,
            enabled_scope=instance["attacking_extension_scope"],
        )
        actor["entity_adapter"]["attacking_extension_scope"] = ATTACKING_EXTENSION_SCOPE
    if "defense_ammunition_parameters" in instance:
        attach_explicit_defense_ammunition(
            actor, instance["defense_ammunition_parameters"]
        )
    if "inferno_ammunition_parameters" in instance:
        from .defense_upgrades import attach_inferno_ammunition

        attach_inferno_ammunition(actor, instance["inferno_ammunition_parameters"])
    if "barracks_member_parameters" in instance:
        attach_barracks_member(actor, instance, entity, row, catalog)
    if "barrel_member_parameters" in instance:
        attach_barrel_member(actor, instance)
    return actor


def _compile_air_death(actor, instance, stats):
    parameters = require(instance, "death_parameters")
    if set(parameters) != {"source", "statistic_basis", "damage_multiplier", "impacts"}:
        raise InputError(
            "Air death effects must declare statistic basis, scaling and every impact"
        )
    source = identifier(require(parameters, "source"), "air death behavior evidence")
    multiplier = number(
        require(parameters, "damage_multiplier"), "death damage multiplier", 0
    )
    impacts = require(parameters, "impacts")
    if not isinstance(impacts, list) or not impacts:
        raise InputError("Air death effects need an explicit finite impact pattern")
    basis = require(parameters, "statistic_basis")
    if instance["entity"] == "dragon-rider":
        if basis != "snapshot_single_blast" or len(impacts) != 1:
            raise InputError(
                "Dragon Rider's conditional crash needs one explicit blast"
            )
    elif basis not in {
        "snapshot_deathDamage_is_per_impact_hypothesis",
        "snapshot_deathDamage_is_total_hypothesis",
    }:
        raise InputError("Electro Dragon deathDamage quantity cannot be inferred")
    effects = []
    fractions = []
    for impact in impacts:
        if set(impact) != {
            "id",
            "source",
            "delay_seconds",
            "offset_x",
            "offset_y",
            "radius",
            "target_kinds",
            "target_layers",
            "damage_fraction",
        }:
            raise InputError(
                "Every death impact needs explicit timing, offsets, radius and filters"
            )
        fraction = number(
            require(impact, "damage_fraction"), "death impact damage fraction", 0, 1
        )
        if basis != "snapshot_deathDamage_is_total_hypothesis" and fraction != 1:
            raise InputError(
                "A per-impact or single-blast statistic needs a full unit fraction"
            )
        fractions.append(fraction)
        effects.append(
            {
                "id": require(impact, "id"),
                "source": require(impact, "source"),
                "kind": "area_damage",
                "delay_seconds": require(impact, "delay_seconds"),
                "amount": number(
                    require(stats, "deathDamage"), "catalog deathDamage", 0
                )
                * multiplier
                * fraction,
                "area": {
                    "offset_x": require(impact, "offset_x"),
                    "offset_y": require(impact, "offset_y"),
                    "radius": require(impact, "radius"),
                    "target_team": "defense",
                    "target_kinds": deepcopy(require(impact, "target_kinds")),
                    "target_layers": deepcopy(require(impact, "target_layers")),
                },
            }
        )
    if (
        basis == "snapshot_deathDamage_is_total_hypothesis"
        and abs(sum(fractions) - 1) > EPSILON
    ):
        raise InputError("Total deathDamage impact fractions must sum to one")
    actor["death_model"] = {
        "kind": "fixed_area_sequence_at_death",
        "geometry": "offsets_from_source_center_at_death",
        "source": source,
        "effects": effects,
    }
    actor["entity_adapter"]["death_statistic_source"] = actor["source"]
    actor["entity_adapter"]["death_parameters"] = deepcopy(parameters)
    actor["entity_adapter"][
        "death_behavior_verification"
    ] = "fixed_pattern_and_statistic_mapping_hypothesis_not_game_validated"


def _compile_inferno(actor, instance, mode, stats, modifiers):
    if instance["mode"] == "multiTarget":
        if "ramp_parameters" in instance:
            raise InputError(
                "Multi-target Inferno cannot select single-mode ramp parameters"
            )
        parameters = require(instance, "beam_parameters")
        if (
            set(parameters) != {"cadence", "source"}
            or parameters["cadence"] != "synchronized_volley_hypothesis"
        ):
            raise InputError(
                "Multi-Inferno needs an explicit synchronized beam hypothesis"
            )
        identifier(parameters["source"], "multi-beam evidence")
        if actor["attack_model"]["allocation"] != "distinct_targets_only":
            raise InputError(
                "Multi-Inferno beams cannot concentrate by cycling targets"
            )
        actor["entity_adapter"]["beam_parameters"] = deepcopy(parameters)
        return
    if "beam_parameters" in instance:
        raise InputError("Single-target Inferno cannot select multi-beam parameters")
    parameters = require(instance, "ramp_parameters")
    expected = {
        "source",
        "clock_start",
        "freeze_policy",
        "protected_target_policy",
        "middle_stage_after_seconds",
        "maximum_stage_after_seconds",
        "timing_source",
    }
    if set(parameters) != expected:
        raise InputError(
            "All Inferno stage timings and interruption policies must be explicit"
        )
    middle = number(
        require(parameters, "middle_stage_after_seconds"), "middle ramp time", 0
    )
    if middle != 1.5:
        raise InputError(
            "The dpsAfter1p5s statistic requires the explicit 1.5-second mapping"
        )
    maximum = number(
        require(parameters, "maximum_stage_after_seconds"), "maximum ramp time", EPSILON
    )
    timing_source = identifier(
        require(parameters, "timing_source"), "maximum ramp timing evidence"
    )
    pulse = mode["attackSpeed"] * modifiers["damage_multiplier"]
    actor["ramp_model"] = {
        field: deepcopy(parameters[field])
        for field in (
            "source",
            "clock_start",
            "freeze_policy",
            "protected_target_policy",
        )
    }
    actor["ramp_model"]["stages"] = [
        {
            "after_seconds": after,
            "damage_per_hit": number(require(stats, statistic), statistic, EPSILON)
            * pulse,
            "source": actor["source"],
            "statistic": statistic,
            "timing_source": timing_source if statistic == "dps" else actor["source"],
        }
        for after, statistic in (
            (0, "dpsInitial"),
            (middle, "dpsAfter1p5s"),
            (maximum, "dps"),
        )
    ]
    actor["entity_adapter"][
        "selected_statistic"
    ] = "dpsInitial/dpsAfter1p5s/dps times the catalog pulse interval; fixed maximum damagePerShot is not the starting hit"
    actor["entity_adapter"]["ramp_parameters"] = deepcopy(parameters)


def _compile_healer(actor, instance, entity, row, modifiers, movement_units_per_tile):
    if (
        actor["team"] != "attack"
        or actor["counts_for_destruction"]
        or instance["mode"] != "normal"
        or instance["statistics_mode"] != "normal"
        or "wall_parameters" in instance
        or require(instance, "attack_parameters") != {}
    ):
        raise InputError(
            "Healer needs a normal attacking support actor without a weapon"
        )
    if (
        modifiers["damage_multiplier"] != 1
        or modifiers["maximum_hp_damage_multiplier"] != 1
    ):
        raise InputError("Healing amounts require their own explicit multiplier")
    parameters = require(instance, "healing_parameters")
    if (
        set(parameters) - {"pet_healing_basis", "pet_healing_multiplier"}
        != {
            "kind",
            "radius",
            "projectile",
            "selector",
            "stacking_group",
            "amount_multiplier",
            "source",
        }
        or parameters["kind"] != "radial"
    ):
        raise InputError("Healer needs explicit radial healing behavior parameters")
    amount_multiplier = number(
        parameters["amount_multiplier"], "healing multiplier", EPSILON
    )
    stats = require(require(row, "stats"), "normal")
    model = {
        field: deepcopy(parameters[field])
        for field in (
            "kind",
            "radius",
            "projectile",
            "selector",
            "stacking_group",
            "source",
        )
    }
    model.update(
        {
            "target_kinds": ["unit"],
            "target_layers": ["ground"],
            "target_classes": ["troop", "hero"],
            "amounts_by_class": {
                "troop": number(
                    require(stats, "healingPerPulse"), "troop healing pulse", 0
                )
                * amount_multiplier,
                "hero": number(
                    require(stats, "healingPerPulseOnHeroes"), "hero healing pulse", 0
                )
                * amount_multiplier,
            },
        }
    )
    pet_policy, pet_pulse = compile_pet_healing_policy(
        parameters,
        model["amounts_by_class"]["troop"],
        model["amounts_by_class"]["hero"],
    )
    if pet_policy is not None:
        model["pet_healing_policy"] = pet_policy
        if pet_policy["basis"] != "explicitly_excluded":
            model["target_classes"].append("pet")
            model["amounts_by_class"]["pet"] = pet_pulse
    actor.update(
        {
            "kind": "unit",
            "housing_space": require(entity, "housingSpace"),
            "healing_class": "troop",
            "layer": "air",
            "movement": "air",
            "speed": number(
                require(entity, "movementSpeed"), "Healer movement", EPSILON
            )
            / movement_units_per_tile
            * modifiers["movement_speed_multiplier"],
            "blocking": False,
            "width": 0,
            "height": 0,
            "damage": 0,
            "attack_interval_seconds": number(
                require(entity, "attackSpeed"), "Healer pulse interval", EPSILON
            )
            * modifiers["attack_interval_multiplier"],
            "range": number(require(entity, "range"), "Healer range", 0)
            * modifiers["range_multiplier"],
            "target_priorities": [],
            "target_layers": [],
            "attack_model": {"kind": "none", "source": actor["source"]},
            "healing_model": model,
        }
    )
    actor["entity_adapter"].update(
        {
            "selected_statistic": "healingPerPulse and healingPerPulseOnHeroes",
            "healing_amount_multiplier": amount_multiplier,
            "healing_behavior_verification": "selected_hypothesis_not_replay_validated",
        }
    )
    return actor


def compile_healing_spell_field(instance, catalog):
    if require(instance, "entity") != "healing-spell":
        raise InputError("Only Healing Spell has a persistent field adapter")
    level = integer(require(instance, "level"), "spell level", 1)
    town_hall = integer(
        require(instance, "town_hall"), "spell Town Hall", 1, catalog.maximum_town_hall
    )
    if not catalog.available("healing-spell", level, town_hall):
        raise InputError("Healing Spell level is unavailable at this Town Hall")
    entity = catalog.entity("healing-spell")
    row = catalog.level("healing-spell", level)
    parameters = require(instance, "parameters")
    if set(parameters) - {"pet_healing_basis", "pet_healing_multiplier"} != {
        "first_pulse_delay_seconds",
        "amount_multiplier",
        "radius_multiplier",
        "pulse_interval_multiplier",
        "target_team",
        "target_layers",
        "source",
    }:
        raise InputError("Healing Spell needs every unresolved field parameter")
    amount_multiplier = number(
        parameters["amount_multiplier"], "spell healing multiplier", EPSILON
    )
    pulse_count = integer(require(entity, "numberOfPulses"), "spell pulse count", 1)
    ordinary_pulse = number(require(row, "healingPerPulse"), "spell healing pulse", 0)
    if (
        abs(
            ordinary_pulse * pulse_count
            - number(require(row, "totalHealing"), "spell total healing", 0)
        )
        > EPSILON
    ):
        raise InputError("Healing Spell pulse count and total statistics conflict")
    hero_pulse = (
        number(require(row, "totalHealingOnHeroes"), "spell hero total healing", 0)
        / pulse_count
    )
    amounts = {
        "troop": ordinary_pulse * amount_multiplier,
        "hero": hero_pulse * amount_multiplier,
    }
    pet_policy, pet_pulse = compile_pet_healing_policy(
        parameters, amounts["troop"], amounts["hero"]
    )
    if pet_policy is not None and pet_policy["basis"] != "explicitly_excluded":
        amounts["pet"] = pet_pulse
    return {
        "id": identifier(require(instance, "id"), "spell field id"),
        "kind": "healing_field",
        "source": identifier(parameters["source"], "spell behavior evidence"),
        "time_seconds": number(require(instance, "time_seconds"), "spell cast time", 0),
        "first_pulse_delay_seconds": number(
            parameters["first_pulse_delay_seconds"], "first spell pulse delay", 0
        ),
        "pulse_count": pulse_count,
        "pulse_interval_seconds": number(
            require(entity, "timeBetweenPulses"), "spell pulse interval", EPSILON
        )
        * number(
            parameters["pulse_interval_multiplier"],
            "spell pulse interval multiplier",
            EPSILON,
        ),
        "amounts_by_class": amounts,
        **({"pet_healing_policy": pet_policy} if pet_policy is not None else {}),
        "area": {
            "x": require(instance, "x"),
            "y": require(instance, "y"),
            "radius": number(require(entity, "radius"), "spell radius", 0)
            * number(
                parameters["radius_multiplier"], "spell radius multiplier", EPSILON
            ),
            "target_team": parameters["target_team"],
            "target_kinds": ["unit"],
            "target_layers": deepcopy(parameters["target_layers"]),
            "target_classes": list(amounts),
        },
        "entity_adapter": {
            "entity": "healing-spell",
            "level": level,
            "town_hall": town_hall,
            "adapter_version": ADAPTER_VERSION,
            "snapshot_verification": catalog.records["healing-spell"]["verification"],
            "behavior_verification": "conditional_field_not_replay_validated",
        },
    }


def _compile_wall_behavior(actor, instance, entity, row, modifiers):
    parameters = require(instance, "wall_parameters")
    kind = require(parameters, "kind")
    source = identifier(require(parameters, "source"), "wall behavior source")
    if kind == "avoid":
        if entity["id"] == "root-rider":
            raise InputError("Root Rider cannot omit its wall-breach behavior")
        if set(parameters) != {"kind", "source"}:
            raise InputError("Avoid-wall parameters must not hide other settings")
        actor["wall_behavior"] = deepcopy(parameters)
        return
    if set(parameters) != {
        "kind",
        "source",
        "route_cost",
        "cooldown",
        "range",
        "first_attack_seconds",
        "impact_timing",
    }:
        raise InputError("Every unresolved wall behavior setting must be selected")
    root = entity["id"] == "root-rider"
    if not root and (
        kind != "clear_obstructions"
        or parameters["cooldown"] != "shared_with_main_weapon"
    ):
        raise InputError(
            "Ordinary ground troops require clearing with a shared weapon clock"
        )
    if not root and parameters["range"] != actor["range"]:
        raise InputError("Ordinary wall attacks use the selected main weapon range")
    wall_stats = require(require(row, "stats"), "wall") if root else None
    actor["wall_behavior"] = {
        "kind": kind,
        "source": source,
        "route_cost": require(parameters, "route_cost"),
        "weapon": {
            "damage": (
                number(
                    require(wall_stats, "damagePerShot"), "Root Rider wall hit", EPSILON
                )
                * modifiers["damage_multiplier"]
                if root
                else actor["damage"]
            ),
            "attack_interval_seconds": (
                number(
                    require(entity, "wallAttackSpeed"),
                    "Root Rider wall interval",
                    EPSILON,
                )
                * modifiers["attack_interval_multiplier"]
                if root
                else actor["attack_interval_seconds"]
            ),
            "range": require(parameters, "range"),
            "first_attack_seconds": require(parameters, "first_attack_seconds"),
            "timing": require(parameters, "impact_timing"),
            "cooldown": require(parameters, "cooldown"),
            "source": actor["source"],
        },
    }
    actor["entity_adapter"][
        "wall_behavior_verification"
    ] = "selected_hypothesis_not_replay_validated"


def compile_entity_scene(specification, catalog):
    scope = require(specification, "scope")
    # Each registered version includes the capabilities of its predecessor.
    scopes = {
        SCOPE: (2, RULESET, COMBAT_RULES),
        WALL_SCOPE: (3, WALL_RULESET, WALL_RULES),
        SUPPORT_SCOPE: (4, SUPPORT_RULESET, SUPPORT_RULES),
        RAMP_SCOPE: (5, RAMP_RULESET, RAMP_RULES),
        DEATH_SCOPE: (6, DEATH_RULESET, DEATH_RULES),
        TOWN_HALL_SCOPE: (7, TOWN_HALL_RULESET, TOWN_HALL_RULES),
        AREA_DEFENSE_SCOPE: (8, AREA_DEFENSE_RULESET, AREA_DEFENSE_RULES),
        HERO_SCOPE: (9, HERO_RULESET, HERO_RULES),
        ARTILLERY_SCOPE: (10, ARTILLERY_RULESET, ARTILLERY_RULES),
        TRAP_SCOPE: (11, TRAP_RULESET, TRAP_RULES),
        HIT_SCOPE: (12, HIT_RULESET, HIT_RULES),
        EXTENDED_SCOPE: (13, EXTENDED_RULESET, EXTENDED_RULES),
        BUFF_SCOPE: (14, BUFF_RULESET, BUFF_RULES),
        INDIRECT_SCOPE: (15, INDIRECT_RULESET, INDIRECT_RULES),
        SWEEPER_SCOPE: (16, SWEEPER_RULESET, SWEEPER_RULES),
        DEFENDING_HERO_SCOPE: (17, DEFENDING_HERO_RULESET, DEFENDING_HERO_RULES),
        SPELL_TOWER_SCOPE: (18, SPELL_TOWER_RULESET, SPELL_TOWER_RULES),
        BUILDER_SCOPE: (19, BUILDER_RULESET, BUILDER_RULES),
        GARRISON_SCOPE: (20, GARRISON_RULESET, GARRISON_RULES),
        FIRESPITTER_SCOPE: (21, FIRESPITTER_RULESET, FIRESPITTER_RULES),
        TRAP_LIFECYCLE_SCOPE: (22, TRAP_LIFECYCLE_RULESET, TRAP_LIFECYCLE_RULES),
        GUARDIAN_SCOPE: (23, GUARDIAN_RULESET, GUARDIAN_RULES),
        SIEGE_SCOPE: (24, SIEGE_RULESET, SIEGE_RULES),
        PET_SCOPE: (25, PET_RULESET, PET_RULES),
        ADVANCED_DEFENSE_SCOPE: (26, ADVANCED_DEFENSE_RULESET, ADVANCED_DEFENSE_RULES),
        HERO_ROSTER_SCOPE: (27, HERO_ROSTER_RULESET, HERO_ROSTER_RULES),
        TERMINATION_SCOPE: (28, TERMINATION_RULESET, TERMINATION_RULES),
        ATTACK_SPELL_SCOPE: (29, ATTACK_SPELL_RULESET, ATTACK_SPELL_RULES),
    }
    if scope not in scopes:
        raise InputError(
            "This registry cannot compile full villages or unsupported sector mechanics"
        )
    version, ruleset, rules = scopes[scope]
    allow_walls = version >= 3
    allow_support = version >= 4
    allow_ramps = version >= 5
    allow_deaths = version >= 6
    allow_town_halls = version >= 7
    allow_area_defenses = version >= 8
    allow_heroes = version >= 9
    allow_artillery = version >= 10
    allow_traps = version >= 11
    allow_hit_status = version >= 12
    allow_extended = version >= 13
    allow_buffs = version >= 14
    allow_indirect = version >= 15
    allow_sweepers = version >= 16
    allow_defending_heroes = version >= 17
    allow_spell_towers = version >= 18
    allow_builders = version >= 19
    allow_garrisons = version >= 20
    allow_firespitters = version >= 21
    allow_trap_lifecycles = version >= 22
    allow_guardians = version >= 23
    allow_reinforcements = version >= 24
    allow_pets = version >= 25
    allow_advanced_defenses = version >= 26
    allow_hero_extensions = version >= 27
    allow_attack_spells = version >= 29
    rules = select_duke_isolation_rules(
        rules,
        [
            instance.get("duke_parameters")
            for instance in require(specification, "entities")
        ],
    )
    if require(specification, "model_rules") != rules:
        raise InputError("Sector combat conventions must be explicitly selected")
    statistics = require(specification, "statistics_policy")
    statistic_kind = require(statistics, "kind")
    branch = catalog.snapshot.get("statistic_branch")
    if statistic_kind == "conditional_pinned_snapshot":
        if branch is not None:
            raise InputError("A source branch cannot be labeled an unchanged snapshot")
    elif statistic_kind == "conditional_primary_publications":
        if (
            branch is None
            or branch.get("kind") == "extracted_fields"
            or require(statistics, "branch_policy") != branch["policy"]
        ):
            raise InputError(
                "Sector statistics require the exact selected source branch"
            )
    elif statistic_kind == "conditional_extracted_fields":
        if (
            branch is None
            or branch.get("kind") != "extracted_fields"
            or require(statistics, "branch_policy") != branch["policy"]
        ):
            raise InputError(
                "Sector statistics require the exact selected extraction branch"
            )
    else:
        raise InputError("A verified-current-statistics resolver is not implemented")
    if require(statistics, "snapshot_commit") != catalog.snapshot["snapshotCommit"]:
        raise InputError("Sector statistics do not match the requested snapshot")
    units = require(specification, "unit_conventions")
    movement_units_per_tile = number(
        require(units, "movement_units_per_tile"), "movement conversion", EPSILON
    )
    if require(units, "catalog_attack_speed_unit") != "seconds_per_hit":
        raise InputError("Unsupported catalog attack interval conversion")
    identifier(require(units, "source"), "unit-conversion evidence or assumption")
    unsupported = require(specification, "unsupported_mechanics")
    if not isinstance(unsupported, list) or unsupported:
        raise InputError(
            "Required unsupported mechanics cannot be omitted from sector simulation"
        )
    scene = {
        field: deepcopy(require(specification, field))
        for field in (
            "id",
            "width",
            "height",
            "duration_seconds",
            "maximum_step_seconds",
            "recording_interval_seconds",
            "effects",
        )
    }
    scene.update(
        {
            "ruleset": ruleset,
            "model_rules": deepcopy(rules),
            "unsupported_mechanics": [],
        }
    )

    def compile_instance(instance):
        return compile_actor(
            instance,
            catalog,
            movement_units_per_tile,
            allow_walls,
            allow_support,
            allow_ramps,
            allow_deaths,
            allow_town_halls,
            allow_area_defenses,
            allow_heroes,
            allow_artillery,
            allow_hit_status,
            allow_extended,
            allow_indirect,
            allow_sweepers,
            allow_defending_heroes,
            allow_spell_towers,
            allow_builders,
            allow_garrisons,
            allow_firespitters,
            allow_guardians,
            allow_reinforcements,
            allow_pets,
            allow_advanced_defenses,
            allow_hero_extensions,
        )

    scene["actors"] = [
        compile_instance(instance) for instance in require(specification, "entities")
    ]
    if not scene["actors"]:
        raise InputError("Entity sector needs instances")
    if allow_heroes:
        clones = [
            clone
            for actor in scene["actors"]
            if "hero_model" in actor
            for clone in compile_mirror_clones(actor)
        ]
        scene["actors"].extend(clones)
    if allow_pets:
        assignments = specification.get("pets", [])
        pets = compile_pets(
            assignments,
            {actor["id"]: actor for actor in scene["actors"]},
            catalog,
            movement_units_per_tile,
        )
        paired_owners = {actor["pet_model"]["hero_id"] for actor in pets}
        for actor in scene["actors"]:
            if "hero_model" not in actor:
                continue
            paired = actor["entity_adapter"]["hero_parameters"]["pet_policy"] == (
                "paired_pet_from_explicit_scene_assignment"
            )
            if paired != (actor["id"] in paired_owners):
                raise InputError(
                    "Hero pet policy requires exactly its explicit scene assignment"
                )
        scene["actors"].extend(pets)
        for pet in pets:
            scene["actors"].extend(compile_frostmite_reserves(pet))
    elif "pets" in specification:
        raise InputError("Paired pets require the explicit v25 sector scope")
    if allow_traps:
        trap_instances = require(specification, "traps")
        if not isinstance(trap_instances, list):
            raise InputError("Trap instances must be an explicit list")
        if not allow_advanced_defenses and any(
            item.get("entity") == "giga-bomb" for item in trap_instances
        ):
            raise InputError("Giga Bomb requires the explicit v26 sector scope")
        if not allow_trap_lifecycles and any(
            item.get("entity") in {"skeleton-trap", "tornado-trap"}
            for item in trap_instances
        ):
            raise InputError(
                "Skeleton and Tornado Traps require the explicit v22 scope"
            )
        scene["traps"] = [
            compile_trap(item, catalog, movement_units_per_tile)
            for item in trap_instances
        ]
        for trap in scene["traps"]:
            if trap["entity"] == "skeleton-trap":
                scene["actors"].extend(compile_skeleton_reserves(trap))
    elif "traps" in specification:
        raise InputError("Traps require the explicit trap scope")
    if allow_defending_heroes and (
        "defending_unit_responses" in specification
        or any(
            "defending_hero_model" in actor
            or "garrison_model" in actor
            or "garrison_member_model" in actor
            or "trap_summon_model" in actor
            or "guardian_model" in actor
            for actor in scene["actors"]
        )
    ):
        scene["defending_unit_responses"] = deepcopy(
            require(specification, "defending_unit_responses")
        )
    elif "defending_unit_responses" in specification:
        raise InputError(
            "Defending-unit response policies require the explicit v17 scope"
        )
    if allow_buffs:
        buff_instances = require(specification, "buff_spells")
        if not isinstance(buff_instances, list):
            raise InputError("Area buff casts must be an explicit list")
        scene["buff_fields"] = [
            (
                compile_received_spell(
                    instance,
                    catalog,
                    lambda item, source_catalog: compile_buff_spell(
                        item, source_catalog, movement_units_per_tile
                    ),
                )
                if allow_reinforcements
                else compile_buff_spell(instance, catalog, movement_units_per_tile)
            )
            for instance in buff_instances
        ]
        catalog_entries = {
            actor["id"]: catalog.entity(actor["entity_adapter"]["entity"])
            for actor in scene["actors"]
            if "entity_adapter" in actor
        }
        for actor in scene["actors"]:
            if actor["kind"] == "unit":
                if actor.get("summon_model", {}).get(
                    "equipment"
                ) == "action-figure" or actor.get("summon_model", {}).get("kind") in {
                    "frostmite",
                    "equipment_child",
                }:
                    if actor.get("buff_class") != "troop":
                        raise InputError(
                            "Action Figure requires its explicit troop buff class"
                        )
                    continue
                if "trap_summon_model" in actor:
                    actor["buff_class"] = "troop"
                    continue
                if "siege_model" in actor:
                    actor["buff_class"] = "siege"
                    continue
                # Compiler-generated clones retain their parent's declared class;
                # they deliberately have no independent catalog entity identity.
                source_id = actor.get("summon_model", {}).get("parent", actor["id"])
                category = catalog_entries[source_id]["category"]
                actor["buff_class"] = (
                    category
                    if category in {"troop", "hero", "guardian", "pet"}
                    else "other"
                )
    elif "buff_spells" in specification:
        raise InputError("Area buff spells require their explicit scope")
    freeze_spells = specification.get("freeze_spells", [])
    if not isinstance(freeze_spells, list):
        raise InputError("Freeze commands need an explicit list when supplied")
    for instance in freeze_spells:
        scene["effects"].append(
            compile_received_spell(instance, catalog, compile_freeze_spell)
            if allow_reinforcements
            else compile_freeze_spell(instance, catalog)
        )
    width = integer(scene["width"], "sector width", 1)
    height = integer(scene["height"], "sector height", 1)
    if allow_attack_spells:
        instances = require(specification, "attack_spells")
        if not isinstance(instances, list):
            raise InputError("Attacking spell casts require an explicit list")
        scene["attack_spell_models"] = [
            compile_received_spell(instance, catalog, compile_attack_spell)
            for instance in instances
        ]
        reserved_ids = {
            item["id"]
            for field in ("actors", "effects", "buff_fields", "traps")
            for item in scene.get(field, [])
        }
        for model in scene["attack_spell_models"]:
            if model["id"] in reserved_ids:
                raise InputError("Attacking spell casts require distinct scene IDs")
            reserved_ids.add(model["id"])
            number(model["position"][0], "attacking spell x", 0, width)
            number(model["position"][1], "attacking spell y", 0, height)
            for reserve in compile_totem_reserve(model):
                if reserve["id"] in reserved_ids:
                    raise InputError(
                        "Generated Totem identity collides with a scene object"
                    )
                reserved_ids.add(reserve["id"])
                if "defending_unit_responses" in scene:
                    response = {"primary": "ignore", "collateral": "ignore"}
                    scene["defending_unit_responses"]["actors"][
                        reserve["id"]
                    ] = response
                    reserve["defending_unit_response"] = {
                        "source": scene["defending_unit_responses"]["source"],
                        **response,
                    }
                scene["actors"].append(reserve)
    elif "attack_spells" in specification:
        raise InputError("Attacking spells require the explicit v29 scope")
    advanced_models = [
        m
        for m in scene.get("attack_spell_models", [])
        if m["entity"] in ADVANCED_SPELLS
    ]
    if advanced_models:
        binding = deepcopy(require(specification, "advanced_spell_binding"))
        validate_binding(binding)
        scene["advanced_spell_binding"] = binding
        existing = {actor["id"]: actor for actor in scene["actors"]}
        for reserve in compile_spell_reserves(
            advanced_models, existing, specification["entities"], compile_instance
        ):
            if reserve["id"] in reserved_ids:
                raise InputError(
                    "Generated spell identity collides with a scene object"
                )
            reserved_ids.add(reserve["id"])
            scene["actors"].append(reserve)
    elif "advanced_spell_binding" in specification:
        raise InputError("Advanced spell binding requires a selected advanced spell")
    if "defending_unit_responses" in scene:
        for actor in scene["actors"]:
            if "spell_generated_model" in actor or "spell_clone_model" in actor:
                actor["target_priorities"] = [
                    k for k in actor["target_priorities"] if k != "unit"
                ]
                actor["target_priority_tiers"] = [
                    [k for k in tier if k != "unit"]
                    for tier in actor["target_priority_tiers"]
                ]
                actor["target_priority_tiers"] = [
                    tier for tier in actor["target_priority_tiers"] if tier
                ]
                actor["attack_model"]["target_kinds"] = [
                    k for k in actor["attack_model"]["target_kinds"] if k != "unit"
                ]
        # The supplied map must explicitly include every generated identity.
        # Totems already carry the nonattacking response bound above.
        undecorated = [a for a in scene["actors"] if "defending_unit_response" not in a]
        responses = scene["defending_unit_responses"]
        subset = {
            "actors": undecorated,
            "defending_unit_responses": {
                "source": responses["source"],
                "actors": {
                    k: v
                    for k, v in responses["actors"].items()
                    if k
                    not in {
                        a["id"]
                        for a in scene["actors"]
                        if "defending_unit_response" in a
                    }
                },
            },
        }
        apply_defending_unit_responses(subset)
    if allow_traps:
        if any(item["entity"] == "spring-trap" for item in trap_instances):
            for actor in scene["actors"]:
                if actor["kind"] != "unit":
                    continue
                if "spell_generated_model" in actor or "spell_clone_model" in actor:
                    continue
                if "summon_model" in actor:
                    if actor["summon_model"].get(
                        "equipment"
                    ) == "action-figure" or actor["summon_model"].get("kind") in {
                        "frostmite",
                        "equipment_child",
                    }:
                        if (
                            actor.get("spring_class") != "troop"
                            or "housing_space" not in actor
                        ):
                            raise InputError(
                                "Action Figure requires explicit troop spring weighting"
                            )
                    else:
                        actor["spring_class"] = "other"
                    continue
                if "siege_model" in actor:
                    actor["spring_class"] = "siege"
                    continue
                entry = catalog.entity(actor["entity_adapter"]["entity"])
                category = entry["category"]
                actor["spring_class"] = (
                    category if category in {"troop", "hero", "pet"} else "other"
                )
                if actor["spring_class"] == "troop":
                    actor["housing_space"] = require(entry, "housingSpace")
    if allow_town_halls:
        scene["target_scoring"] = deepcopy(require(specification, "target_scoring"))
    elif "target_scoring" in specification:
        raise InputError(
            "Target scoring selection requires the explicit Town Hall/hazard scope"
        )
    if "giga_bomb_response_binding" in specification:
        if not allow_hero_extensions:
            raise InputError("Giga response binding requires the explicit v27+ scope")
        from .giga_responses import bind_giga_responses

        bind_giga_responses(scene, specification["giga_bomb_response_binding"], catalog)
    actors = _load_actors(scene, width, height)
    reinforcement_runtime = None
    if "attacking_reinforcements" in specification:
        if not allow_reinforcements:
            raise InputError("Attacking reinforcements require the explicit v24 scope")
        scene["attacking_reinforcements"] = compile_attacking_reinforcements(
            specification["attacking_reinforcements"], catalog, actors
        )
        reinforcement_runtime = ReinforcementCombat(
            actors, scene["attacking_reinforcements"], width, height
        )
    elif any(
        "siege_model" in actor
        or "payload_member_model" in actor
        or "barracks_member_model" in actor
        or "barrel_member_model" in actor
        for actor in actors.values()
    ):
        raise InputError(
            "Payloads and siege carriers require their declared delivery group"
        )
    if not allow_reinforcements and any(
        item.get("origin", "army") != "army" or "received_spell_parameters" in item
        for field in ("freeze_spells", "healing_spells", "buff_spells")
        for item in specification.get(field, [])
    ):
        raise InputError("Received spells require the explicit v24 scope")
    if allow_buffs:
        compiled_buffs = BuffCombat(actors, scene["buff_fields"])
        TroopDeathBuffCombat(actors, compiled_buffs)
    if allow_traps:
        validate_trap_footprints(scene["traps"], actors, width, height)
        TrapCombat(
            [
                trap
                for trap in scene["traps"]
                if trap["entity"] not in {"skeleton-trap", "tornado-trap", "giga-bomb"}
            ],
            actors,
            width,
            height,
        )
        if allow_trap_lifecycles:
            SkeletonTrapCombat(
                [trap for trap in scene["traps"] if trap["entity"] == "skeleton-trap"],
                actors,
                width,
                height,
            )
            TornadoTrapCombat(
                [trap for trap in scene["traps"] if trap["entity"] == "tornado-trap"],
                actors,
                width,
                height,
            )
    if allow_extended:
        TeslaCombat(actors, None)
    pattern_combat = PatternCombat(actors)
    GearedCannonCombat(actors, pattern_combat)
    RecipeTroopCombat(actors)
    ElectroTitanCombat(actors)
    validate_line_owners(actors, allow_hero_extensions)
    validate_crafted_owners(actors, allow_hero_extensions)
    if allow_hit_status:
        HitStatusCombat(actors)
    if allow_heroes:
        HeroCombat(actors, pattern_combat, allow_hero_extensions)
    if allow_hero_extensions:
        HeroRosterCombat(
            actors, pattern_combat, HitStatusCombat(actors), None, width, height
        )
    if allow_artillery:
        ArtilleryCombat(actors)
    if allow_ramps:
        RampCombat(actors)
    if allow_deaths:
        DeathCombat(actors)
    if allow_walls:
        wall_routing = WallRouting(actors)
        wall_routing.validate_positions(actors, _blocked(actors, 0), 0)
        if allow_extended:
            ValkyrieRouting(actors, wall_routing.select_target)
    if allow_support:
        scene["healing_stacking"] = deepcopy(require(specification, "healing_stacking"))
        SupportCombat(actors, scene, wall_routing.select_target)
        for instance in require(specification, "healing_spells"):
            field = (
                compile_received_spell(instance, catalog, compile_healing_spell_field)
                if allow_reinforcements
                else compile_healing_spell_field(instance, catalog)
            )
            validate_healing_field(field, actors)
            if allow_pets and pets and "pet_healing_policy" not in field:
                raise InputError(
                    "Healing Spells accompanying pets need an explicit pet healing policy"
                )
            scene["effects"].append(field)
    elif "healing_stacking" in specification or "healing_spells" in specification:
        raise InputError("Healing settings require the support-and-wall scope")
    if allow_town_halls:
        scene["persistent_hazards"] = deepcopy(
            require(specification, "persistent_hazards")
        )
        if not isinstance(scene["persistent_hazards"], list):
            raise InputError("Persistent hazards must be an explicit list")
        town_halls = TownHallCombat(
            actors, scene["persistent_hazards"], wall_routing.select_target
        )
        CraftedDefenseCombat(actors, town_halls.hazards)
    elif "persistent_hazards" in specification:
        raise InputError(
            "Persistent hazards require the explicit Town Hall/hazards scope"
        )
    if allow_indirect:
        IndirectDefenseCombat(actors, pattern_combat, wall_routing.select_target, scene)
    if allow_attack_spells:
        AttackSpellCombat(
            scene["attack_spell_models"], actors, town_halls.hazards, width, height
        )
        if advanced_models:
            SharedAdvancedSpells(
                advanced_models,
                actors,
                scene["advanced_spell_binding"],
                width,
                height,
                wall_routing.select_target,
            )
    if allow_sweepers:
        sweepers = SweeperCombat(actors, width, height)
    if allow_defending_heroes:
        DefendingHeroCombat(actors, wall_routing.select_target, scene)
    if allow_spell_towers:
        SpellTowerCombat(actors, town_halls.hazards)
    if allow_builders:
        BuilderHutCombat(actors, width, height, town_halls.hazards)
    if allow_garrisons:
        GarrisonCombat(actors, wall_routing.select_target, scene)
    if allow_firespitters:
        FirespitterCombat(actors, wall_routing.select_target)
    if allow_guardians:
        GuardianCombat(actors, wall_routing.select_target, scene)
    if reinforcement_runtime is not None:
        permanent_siege_runtime(
            actors, wall_routing.select_target, reinforcement_runtime, width, height
        )
    if allow_pets:
        PetCombat(actors, width, height, wall_routing.select_target)
    if allow_advanced_defenses:
        MultiGearCombat(actors, wall_routing.select_target, pattern_combat)
        GigaBombCombat(
            [trap for trap in scene["traps"] if trap["entity"] == "giga-bomb"],
            actors,
            width,
            height,
            sweepers.motion,
        )
    return {
        "status": "CONDITIONAL_CATALOG_SECTOR_NOT_VALIDATED_CLASH_BATTLE",
        "adapter_version": ADAPTER_VERSION,
        "scope": scope,
        "snapshot_commit": catalog.snapshot["snapshotCommit"],
        "statistic_branch": deepcopy(branch),
        "unit_conventions": deepcopy(units),
        "scene": scene,
        "full_game_prediction": False,
        "limitations": [
            "Statistics remain an unverified pinned snapshot; known balance concerns still need reconciliation",
            "Projectile travel, splash radius and other unresolved pattern parameters are explicit caller inputs",
            "Implemented hero, pet, trap, siege and defending-unit adapters require their explicit scopes; unsupported pet families, siege variants, summons and other behaviors remain unavailable",
            "The generic path, target tie, range geometry and point-unit collision conventions are not replay-validated Clash AI",
            "Wall motion profiles, pulse timing, range, cooldown sharing and route-cost estimates are explicit hypotheses; Root Rider wall statistics alone do not verify them",
            "Healing selection, splash, stacking and first-pulse timing are explicit hypotheses; hero class labels do not supply complete hero or pet behavior",
            "Inferno ramp origins, reset/protection policies and synchronized multi-beam cadence require current game validation; historic timing is not current certification",
            "Air death impact coordinates, count, radius, delay and statistic quantity are explicit inputs; no random bolt pattern, wind-up behavior or Dragon Rider layer rule is inferred",
            "TH14–16 Giga, TH17 artillery and TH18 Longshot/Smasher require their explicit scopes; Guardian emergence, movement and ability geometry remain hypotheses; Logger is unavailable",
            "No stars or triple probabilities are inferred from a sector encounter",
        ],
    }


def simulate_entity_scene(specification, catalog):
    compiled = compile_entity_scene(specification, catalog)
    compiled["combat"] = simulate_spatial(compiled["scene"])
    return compiled


def simulate_entity_closed_loop(specification, catalog, plan, profile, seed, trials):
    from .closed_loop import simulate_closed_loop

    compiled = compile_entity_scene(specification, catalog)
    compiled["human_combat"] = simulate_closed_loop(
        compiled["scene"], plan, profile, seed, trials
    )
    return compiled
