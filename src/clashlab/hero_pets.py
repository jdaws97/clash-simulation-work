"""Explicit paired-pet lifecycles without substituting generic combat units.

The selected catalog provides primary combat quantities and level caps. Pet AI,
initial clocks, projectile geometry and unresolved interactions are required
inputs. Frosty is deliberately unavailable: neither supplied dataset contains
the Frostmite combat statistics needed to implement his complete lifecycle.

Publisher behavior references:
https://supercell.com/en/games/clashofclans/blog/game-updates/meet-the-hero-pets-1-2/
https://supercell.com/en/games/clashofclans/blog/release-notes/full-release-notes-2/
https://supercell.com/en/games/clashofclans/blog/release-notes/full-patch-notes-th16/
https://support.supercell.com/clash-of-clans/en/articles/about-heroes-pets-9.html
"""

from collections import defaultdict
from copy import deepcopy
from math import floor, hypot

from .buffs import healing_multiplier
from .combat import validate_pattern
from .common import InputError, identifier, integer, number, require
from .rates import attack_rate, movement_speed, pause_attack_work
from .range_events import first_weapon_range_entry_delay
from .spatial import (
    EPSILON,
    _active,
    _blocked,
    _eligible,
    _remember_route,
    _route,
    _route_length,
    center,
    target_distance,
)


SUPPORTED_PETS = frozenset(
    {"unicorn", "diggy", "phoenix", "spirit-fox", "lassi", "electro-owl"}
)
MISSING_PET_MECHANICS = {
    "frosty": "Frostmite combat statistics, lifetime and impact behavior need an independent supported source",
    "poison-lizard": "Poison ramp, exposure duration and retarget behavior need a complete adapter",
    "mighty-yak": "Wall damage and the owner-defeat rage lifecycle need a complete adapter",
    "angry-jelly": "Temporary owner targeting override and separation need a complete adapter",
    "sneezy": "Booger statistics and summon lifecycle need a complete adapter",
    "greedy-raven": "Resource damage preference and special attack behavior need a complete adapter",
}
PUBLISHER_SOURCES = {
    "original_pets": "https://supercell.com/en/games/clashofclans/blog/game-updates/meet-the-hero-pets-1-2/",
    "th15_lifecycles": "https://supercell.com/en/games/clashofclans/blog/release-notes/full-release-notes-2/",
    "spirit_fox": "https://supercell.com/en/games/clashofclans/blog/release-notes/full-patch-notes-th16/",
    "assignment": "https://support.supercell.com/clash-of-clans/en/articles/about-heroes-pets-9.html",
}
EXTRACTION_SOURCE = (
    "https://raw.githubusercontent.com/ClashKingInc/ClashKingAssets/"
    "b8f42a707fe92d5293d46088bf536450ae422e7b/assets/static_data.json"
)
PET_RULES = {
    "pet_ownership": "one_explicit_pet_per_attacking_hero_no_independent_deployment",
    "pet_statistics": "selected_catalog_quantities_with_explicit_behavior_and_disagreement_provenance",
    "pet_status_classes": "pet_for_healing_buffs_hazards_and_springs_independent_of_owner",
    "pet_received_healing": "explicit_catalog_quantity_branch_or_exclusion_and_separate_Tome_multiplier",
    "pet_owner_death": "declared_rebond_healing_fallback_or_independent_combat",
    "pet_cloak": "acquisition_invisibility_only_existing_impacts_and_splash_continue",
    "pet_diggy_burrow": "finite_internal_motion_while_inactive_then_ordinary_surface_combat",
    "pet_phoenix": "one_lethal_interception_then_unhealable_temporary_life_and_forced_owner_defeat",
}
COMMON_PARAMETERS = {
    "source",
    "spawn_offset",
    "first_attack_delay_seconds",
    "follow_distance_tiles",
    "target_retention",
    "owner_death_policy",
    "pet_death_policy",
    "ground_wall_policy",
    "incoming_status_policy",
    "projectile",
    "behavior",
}
OWNER_DEATH_POLICIES = {
    "unicorn": "nearest_living_hero_then_nearest_living_troop",
    "diggy": "rebond_nearest_living_hero_else_independent",
    "phoenix": "independent_after_temporary_owner_life",
    "spirit-fox": "independent_combat_and_self_cloak",
    "lassi": "independent_combat",
    "electro-owl": "independent_combat",
}
TARGET_RETENTION = {
    "unicorn": "assigned_owner_then_declared_fallback",
    "diggy": "retain_until_ineligible_then_prefer_owner_primary",
    "phoenix": "prefer_owner_primary_then_nearest",
    "spirit-fox": "retain_then_prefer_targets_within_owner_radius",
    "lassi": "retain_then_prefer_targets_within_owner_radius",
    "electro-owl": "prefer_owner_primary_then_nearest",
}
OWNER_RADII = {"lassi": 2.5, "spirit-fox": 4.5}
AIR_PETS = {"phoenix", "electro-owl"}
MODEL_FIELDS = {
    "entity",
    "level",
    "hero_id",
    "statistics_source",
    "publisher_sources",
    "statistic_disagreements",
    "parameters",
    "owner_preference_radius",
    "healing_per_pulse",
    "stun_duration_seconds",
    "revival_duration_seconds",
    "cloak_duration_seconds",
}


def _fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != expected:
        raise InputError(f"{label} needs every explicit supported field")


def _policy(parameters, field, expected, label):
    if parameters[field] != expected:
        raise InputError(f"Unsupported {label} {field}")


def _validate_parameters(entity_id, parameters):
    _fields(parameters, COMMON_PARAMETERS, "Paired pet parameters")
    identifier(parameters["source"], "pet behavior evidence")
    _fields(parameters["spawn_offset"], {"dx", "dy"}, "Pet spawn offset")
    for value in parameters["spawn_offset"].values():
        number(value, "pet spawn offset")
    number(parameters["first_attack_delay_seconds"], "pet first action delay", 0)
    number(parameters["follow_distance_tiles"], "pet follow distance", 0)
    _policy(parameters, "target_retention", TARGET_RETENTION[entity_id], "pet")
    _policy(parameters, "owner_death_policy", OWNER_DEATH_POLICIES[entity_id], "pet")
    _policy(
        parameters,
        "pet_death_policy",
        "stop_future_actions_existing_effects_persist",
        "pet",
    )
    _policy(
        parameters,
        "incoming_status_policy",
        "independent_from_owner_ordinary_unit_effects",
        "pet",
    )
    wall_policy = parameters["ground_wall_policy"]
    if entity_id in AIR_PETS:
        if wall_policy != "not_applicable_air":
            raise InputError("Flying pets cannot select a ground wall policy")
    elif entity_id in {"lassi", "diggy"}:
        if wall_policy != "jump_enemy_walls":
            raise InputError("L.A.S.S.I and surfaced Diggy require enemy-wall crossing")
    elif wall_policy not in {"avoid", "jump_enemy_walls"}:
        raise InputError("Pet ground wall behavior must be explicit")
    behavior = parameters["behavior"]
    if entity_id == "unicorn":
        _fields(
            behavior,
            {
                "healing_basis",
                "stacking_policy",
                "protection_policy",
                "overheal_policy",
            },
            "Unicorn healing",
        )
        for field, expected in {
            "healing_basis": "catalog_healingPerPulse_per_catalog_attackSpeed_scaled_by_source_pet_buff",
            "stacking_policy": "independent_additive_without_healer_diminishing_returns",
            "protection_policy": "healing_ignores_damage_invulnerability",
            "overheal_policy": "cap_at_maximum_without_resurrection",
        }.items():
            _policy(behavior, field, expected, "Unicorn")
        if parameters["projectile"] is not None:
            raise InputError("This Unicorn policy uses immediate single-target healing")
    elif entity_id == "spirit-fox":
        _fields(
            behavior,
            {
                "initial_cloak_delay_seconds",
                "visible_interval_seconds",
                "duration_basis",
                "recipient_policy",
                "cloak_policy",
                "freeze_clock_policy",
            },
            "Spirit Fox cloak",
        )
        number(behavior["initial_cloak_delay_seconds"], "initial cloak delay", 0)
        number(behavior["visible_interval_seconds"], "visible cloak interval", EPSILON)
        for field, expected in {
            "duration_basis": "catalog_invisibilityDuration",
            "recipient_policy": "pet_and_active_owner_regardless_distance",
            "cloak_policy": "acquisition_only_existing_projectiles_and_splash_still_hit",
            "freeze_clock_policy": "continue_periodic_clock_while_frozen",
        }.items():
            _policy(behavior, field, expected, "Spirit Fox")
    elif entity_id == "phoenix":
        _fields(
            behavior,
            {
                "duration_basis",
                "revival_health_policy",
                "splash_radius_tiles",
                "shield_recipients",
                "shield_status_policy",
                "hatch_position_policy",
                "expiry_policy",
                "ability_policy",
                "egg_policy",
            },
            "Phoenix lifecycle",
        )
        number(behavior["splash_radius_tiles"], "Phoenix splash radius", EPSILON)
        for field, expected in {
            "duration_basis": "catalog_reviveDuration",
            "revival_health_policy": "one_hp_sentinel_unhealable_during_temporary_life",
            "shield_recipients": "hero_and_hatched_phoenix",
            "shield_status_policy": "freeze_and_cloak_remain_independent",
            "hatch_position_policy": "current_owner_center",
            "expiry_policy": "owner_defeated_even_if_healed_or_other_protection_remains",
            "ability_policy": "preserve_used_state_without_reactivation",
            "egg_policy": "inactive_unhittable_unhealable_nonattacking_owner_follower",
        }.items():
            _policy(behavior, field, expected, "Phoenix")
    elif entity_id == "diggy":
        _fields(
            behavior,
            {
                "burrow_windup_seconds",
                "emerge_delay_seconds",
                "stun_policy",
                "stun_duration_basis",
                "stun_target_kinds",
                "stun_protection_policy",
                "underground_status_policy",
                "underground_path_policy",
                "freeze_policy",
                "target_motion_policy",
            },
            "Diggy burrow",
        )
        for field in ("burrow_windup_seconds", "emerge_delay_seconds"):
            number(behavior[field], field, 0)
        for field, expected in {
            "stun_policy": "first_successful_hit_each_emergence",
            "stun_duration_basis": "catalog_stunDuration",
            "underground_status_policy": "inactive_untargetable_undamageable_no_new_status",
            "underground_path_policy": "straight_segment_through_obstacles_to_clear_surface_point",
            "freeze_policy": "surface_freeze_delays_dive_underground_movement_continues",
            "target_motion_policy": "fixed_destination_revalidate_after_arrival",
        }.items():
            _policy(behavior, field, expected, "Diggy")
        if behavior["stun_protection_policy"] not in {
            "damage_immunity_blocks_stun",
            "damage_immunity_does_not_block_stun",
        }:
            raise InputError("Diggy stun protection policy must be explicit")
        kinds = behavior["stun_target_kinds"]
        if (
            not isinstance(kinds, list)
            or not kinds
            or len(kinds) != len(set(kinds))
            or not set(kinds) <= {"defense", "building", "unit"}
        ):
            raise InputError("Diggy stun membership needs explicit target kinds")
        if (
            not isinstance(parameters["projectile"], dict)
            or parameters["projectile"].get("timing") != "instant"
        ):
            raise InputError(
                "This Diggy emergence policy requires instant melee impacts"
            )
    elif entity_id == "electro-owl":
        _fields(
            behavior,
            {
                "chain_damage_basis",
                "jump_range_tiles",
                "jump_delay_seconds",
                "jump_metric",
                "tie_break",
                "allow_protected_links",
            },
            "Electro Owl chain",
        )
        _policy(
            behavior,
            "chain_damage_basis",
            "catalog_negative_percent_decay_per_jump",
            "Electro Owl",
        )
        number(behavior["jump_range_tiles"], "Owl chain distance", EPSILON)
        number(behavior["jump_delay_seconds"], "Owl chain delay", 0)
    else:
        _fields(behavior, set(), "L.A.S.S.I behavior")


def compile_pet(instance, catalog, movement_units_per_tile, heroes):
    """Build one controlled pet actor from a separate, explicit assignment."""
    _fields(
        instance,
        {"id", "entity", "level", "town_hall", "hero_id", "parameters"},
        "Pet assignment",
    )
    entity_id = identifier(instance["entity"], "pet entity")
    if entity_id not in SUPPORTED_PETS:
        reason = MISSING_PET_MECHANICS.get(
            entity_id, "No complete pet behavior adapter"
        )
        raise InputError(f"Unsupported pet {entity_id}: {reason}")
    pet_id = identifier(instance["id"], "pet instance")
    hero_id = identifier(instance["hero_id"], "pet owner")
    owner = heroes.get(hero_id)
    if (
        owner is None
        or owner["team"] != "attack"
        or owner["kind"] != "unit"
        or "hero_model" not in owner
        or owner["counts_for_destruction"]
    ):
        raise InputError("A pet must bind to one compiled attacking hero")
    level = integer(instance["level"], "pet level", 1)
    town_hall = integer(instance["town_hall"], "pet Town Hall", 1)
    if not catalog.available(entity_id, level, town_hall):
        raise InputError("Pet level is unavailable at the selected Town Hall")
    owner_hall = owner.get("entity_adapter", {}).get("town_hall")
    if owner_hall is not None and owner_hall != town_hall:
        raise InputError("Pet and owner must use the same attacking Town Hall")
    parameters = instance["parameters"]
    _validate_parameters(entity_id, parameters)
    entity = catalog.entity(entity_id)
    row = catalog.level(entity_id, level)
    cadence = number(entity["attackSpeed"], "pet attack interval", EPSILON)
    conversion = number(movement_units_per_tile, "pet movement conversion", EPSILON)
    layers = (
        ["ground", "air"] if entity["targetType"] == "both" else [entity["targetType"]]
    )
    source = catalog.records[entity_id]["source"]
    model = {
        "entity": entity_id,
        "level": level,
        "hero_id": hero_id,
        "statistics_source": source,
        "publisher_sources": deepcopy(PUBLISHER_SOURCES),
        "statistic_disagreements": (
            [
                {
                    "field": "range",
                    "selected_catalog_tiles": entity["range"],
                    "extraction_tiles": 5.5,
                    "extraction_source": EXTRACTION_SOURCE,
                    "decision": "retain_selected_catalog_branch_do_not_silently_override",
                }
            ]
            if entity_id == "electro-owl" and entity["range"] != 5.5
            else []
        ),
        "parameters": deepcopy(parameters),
        "owner_preference_radius": OWNER_RADII.get(entity_id),
        "healing_per_pulse": number(row.get("healingPerPulse", 0), "pet healing", 0),
        "stun_duration_seconds": number(row.get("stunDuration", 0), "pet stun", 0),
        "revival_duration_seconds": number(
            row.get("reviveDuration", 0), "pet revival", 0
        ),
        "cloak_duration_seconds": number(
            row.get("invisibilityDuration", 0), "pet cloak", 0
        ),
    }
    damage = (
        0 if entity_id == "unicorn" else number(row["damagePerHit"], "pet damage", 0)
    )
    pattern = {"kind": "none", "source": parameters["source"]}
    if entity_id != "unicorn":
        pattern.update(
            kind="single",
            target_kinds=["defense", "building"],
            target_layers=layers,
            maximum_hp_fraction=0,
            projectile=deepcopy(parameters["projectile"]),
        )
        if entity_id == "phoenix":
            pattern.update(
                kind="radial",
                radius=parameters["behavior"]["splash_radius_tiles"],
                splash_layer_policy="all_declared_target_layers",
            )
        elif entity_id == "electro-owl":
            count = integer(entity["numberOfTargets"], "Owl chain count", 1)
            decay = (
                1 + number(entity["chainDamageDecay"], "Owl chain decay", -100, 0) / 100
            )
            behavior = parameters["behavior"]
            pattern.update(
                kind="chain",
                damage_multipliers=[decay**index for index in range(count)],
                jump_range=behavior["jump_range_tiles"],
                jump_delay_seconds=behavior["jump_delay_seconds"],
                jump_metric=behavior["jump_metric"],
                tie_break=behavior["tie_break"],
                allow_protected_links=behavior["allow_protected_links"],
            )
    validate_pattern(pattern)
    point = center(owner)
    offset = parameters["spawn_offset"]
    actor = {
        "id": pet_id,
        "source": source,
        "team": "attack",
        "kind": "unit",
        "layer": "air" if entity_id in AIR_PETS else "ground",
        "movement": "air" if entity_id in AIR_PETS else "ground",
        "spawn_seconds": "controlled",
        "first_attack_seconds": parameters["first_attack_delay_seconds"],
        "x": point[0] + offset["dx"],
        "y": point[1] + offset["dy"],
        "width": 0,
        "height": 0,
        "blocking": False,
        "counts_for_destruction": False,
        "hitpoints": number(row["hitpoints"], "pet hitpoints", EPSILON),
        "damage": damage,
        "attack_interval_seconds": cadence,
        "speed": number(entity["movementSpeed"], "pet movement speed", EPSILON)
        / conversion,
        "range": number(entity["range"], "pet range", EPSILON),
        "minimum_range": 0,
        "target_priorities": ["defense", "building"],
        "target_priority_tiers": [["defense", "building"]],
        "target_layers": layers,
        "healing_class": "pet",
        "buff_class": "pet",
        "hazard_class": "pet",
        "spring_class": "pet",
        "attack_model": pattern,
        "pet_model": model,
        "entity_adapter": {
            "entity": entity_id,
            "level": level,
            "town_hall": town_hall,
            "snapshot_verification": catalog.records[entity_id]["verification"],
            "behavior_verification": "explicit_paired_pet_hypotheses_not_replay_validated",
            "modifiers": {
                "source": parameters["source"],
                **{
                    field: 1
                    for field in (
                        "hitpoints_multiplier",
                        "damage_multiplier",
                        "maximum_hp_damage_multiplier",
                        "attack_interval_multiplier",
                        "range_multiplier",
                        "movement_speed_multiplier",
                    )
                },
            },
        },
    }
    if actor["movement"] == "ground":
        actor["wall_behavior"] = {
            "kind": parameters["ground_wall_policy"],
            "source": parameters["source"],
        }
    return actor


def compile_pets(instances, heroes, catalog, movement_units_per_tile):
    if not isinstance(instances, list):
        raise InputError("Pet assignments must be an explicit list")
    hero_ids = set()
    pet_entities = set()
    ids = set(heroes)
    actors = []
    for instance in instances:
        actor = compile_pet(instance, catalog, movement_units_per_tile, heroes)
        model = actor["pet_model"]
        if (
            actor["id"] in ids
            or model["hero_id"] in hero_ids
            or model["entity"] in pet_entities
        ):
            raise InputError(
                "Pet instances, pet entities and assigned heroes must be unique"
            )
        ids.add(actor["id"])
        hero_ids.add(model["hero_id"])
        pet_entities.add(model["entity"])
        actors.append(actor)
    return actors


def validate_pet_inventory(instances, hero_instances, army, account, catalog):
    """Bind each separate pet declaration to the selected hero and owned level."""
    if not isinstance(instances, list):
        raise InputError("Pet assignments must be an explicit list")
    by_entity = {
        actor["entity"]: actor
        for actor in hero_instances.values()
        if "hero_parameters" in actor
    }
    expected = {}
    for hero in army["heroes"]:
        owner = by_entity.get(hero["id"])
        if owner is None:
            raise InputError("Pet binding requires the declared hero actor")
        if hero["pet"] is not None:
            expected[owner["id"]] = hero["pet"]
        policy = owner["hero_parameters"]["pet_policy"]
        paired = policy == "paired_pet_from_explicit_scene_assignment"
        if paired != (hero["pet"] is not None):
            raise InputError(
                "Hero pet policy differs from the declared army assignment"
            )
    bindings = {}
    owners = set()
    entities = set()
    for instance in instances:
        _fields(
            instance,
            {"id", "entity", "level", "town_hall", "hero_id", "parameters"},
            "Pet assignment",
        )
        pet_id = identifier(instance["id"], "pet instance")
        owner_id = identifier(instance["hero_id"], "pet owner")
        entity_id = identifier(instance["entity"], "pet entity")
        if (
            pet_id in bindings
            or pet_id in hero_instances
            or owner_id in owners
            or entity_id in entities
        ):
            raise InputError(
                "Pet instances, pet entities and assigned heroes must be unique"
            )
        selected = expected.get(owner_id)
        if selected is None or (instance["entity"], instance["level"]) != (
            selected["id"],
            selected["level"],
        ):
            raise InputError(
                "Pet identity, level or assigned hero differs from the army"
            )
        level = integer(instance["level"], "pet level", 1)
        owned = account["levels"].get(entity_id)
        if (
            instance["town_hall"] != account["town_hall"]
            or owned is None
            or level > integer(owned, "owned pet level", 0)
            or not catalog.available(entity_id, level, account["town_hall"])
        ):
            raise InputError(
                "Pet level or Town Hall is unavailable to the attacking account"
            )
        if entity_id not in SUPPORTED_PETS:
            reason = MISSING_PET_MECHANICS.get(
                entity_id, "No complete pet behavior adapter"
            )
            raise InputError(f"Unsupported pet {entity_id}: {reason}")
        _validate_parameters(entity_id, instance["parameters"])
        owners.add(owner_id)
        entities.add(entity_id)
        bindings[pet_id] = {
            "origin": "assigned_hero_pet",
            "entity": entity_id,
            "level": level,
            "hero_id": owner_id,
            "hero_entity": hero_instances[owner_id]["entity"],
        }
    if owners != set(expected):
        raise InputError("Every declared hero pet needs exactly one scene assignment")
    return bindings


def validate_pet_deployment(effect, actors):
    if effect.get("kind") == "deploy" and any(
        "pet_model" in actors[actor_id] for actor_id in effect.get("targets", [])
    ):
        raise InputError("Paired pets cannot be independently deployed")


def compile_pet_healing_policy(parameters, ordinary_pulse, hero_pulse):
    """Require a named quantity branch instead of assigning pets a hero class."""
    fields = {"pet_healing_basis", "pet_healing_multiplier"}
    selected = fields & set(parameters)
    if not selected:
        return None, None
    if selected != fields:
        raise InputError("Pet healing needs both an explicit basis and multiplier")
    basis = parameters["pet_healing_basis"]
    multiplier = number(
        parameters["pet_healing_multiplier"], "pet healing multiplier", 0
    )
    quantities = {
        "ordinary_catalog_pulse": ordinary_pulse,
        "hero_catalog_pulse": hero_pulse,
        "explicitly_excluded": 0,
    }
    if basis not in quantities or (basis == "explicitly_excluded" and multiplier != 0):
        raise InputError("Unsupported pet healing quantity branch or exclusion")
    return (
        {"source": parameters["source"], "basis": basis, "multiplier": multiplier},
        quantities[basis] * multiplier,
    )


class PetCombat:
    """Maintain ownership, private egg/burrow phases and ordinary pet actors."""

    def __init__(self, actors, width, height, base_selector):
        self.actors = actors
        self.width = width
        self.height = height
        self.base_selector = base_selector
        self.models = {}
        self.states = {}
        owners = set()
        entities = set()
        for actor_id, actor in actors.items():
            if "pet_model" not in actor:
                continue
            model = deepcopy(actor["pet_model"])
            _fields(model, MODEL_FIELDS, "Pet runtime model")
            entity_id = model["entity"]
            if entity_id not in SUPPORTED_PETS:
                raise InputError("Unsupported pet runtime entity")
            _validate_parameters(entity_id, model["parameters"])
            integer(model["level"], "runtime pet level", 1)
            identifier(model["statistics_source"], "pet statistics evidence")
            for field, pet in (
                ("healing_per_pulse", "unicorn"),
                ("stun_duration_seconds", "diggy"),
                ("revival_duration_seconds", "phoenix"),
                ("cloak_duration_seconds", "spirit-fox"),
            ):
                value = number(model[field], f"pet {field}", 0)
                if (entity_id == pet and value <= EPSILON) or (
                    entity_id != pet and value != 0
                ):
                    raise InputError("Pet lifecycle quantity does not match its entity")
            if model["owner_preference_radius"] != OWNER_RADII.get(entity_id):
                raise InputError(
                    "Pet owner preference radius does not match its entity"
                )
            expected_layer = "air" if entity_id in AIR_PETS else "ground"
            expected_pattern = {
                "unicorn": "none",
                "phoenix": "radial",
                "electro-owl": "chain",
            }.get(entity_id, "single")
            pattern = actor.get("attack_model", {})
            validate_pattern(pattern)
            if (
                actor["layer"] != expected_layer
                or actor["movement"] != expected_layer
                or actor["blocking"]
                or actor["width"] != 0
                or actor["height"] != 0
                or actor["speed"] <= EPSILON
                or actor["range"] <= EPSILON
                or pattern["kind"] != expected_pattern
                or (entity_id == "unicorn" and actor["damage"] != 0)
                or actor["first_attack_seconds"]
                != model["parameters"]["first_attack_delay_seconds"]
            ):
                raise InputError(
                    "Pet movement, geometry or weapon does not match its entity"
                )
            owner = actors.get(model["hero_id"])
            if (
                owner is None
                or "hero_model" not in owner
                or owner["team"] != "attack"
                or model["hero_id"] in owners
                or entity_id in entities
                or actor["team"] != "attack"
                or actor["kind"] != "unit"
                or actor["spawn_seconds"] != "controlled"
                or actor["counts_for_destruction"]
                or any(
                    actor.get(field) != "pet"
                    for field in (
                        "healing_class",
                        "buff_class",
                        "hazard_class",
                        "spring_class",
                    )
                )
            ):
                raise InputError(
                    "Pet ownership, lifecycle or role classification is invalid"
                )
            owners.add(model["hero_id"])
            entities.add(entity_id)
            self.models[actor_id] = model
            self.states[actor_id] = {
                "phase": "waiting_for_owner",
                "bonded_hero_id": model["hero_id"],
                "deployed_at": None,
                "next_cloak": None,
                "cloak_count": 0,
                "temporary_life_until": None,
                "rescue_used": False,
                "healing_pulses": 0,
                "stun_pending_target": None,
                "burrow": None,
                "dive_at": None,
            }
        self.phoenix_by_hero = {
            model["hero_id"]: pet_id
            for pet_id, model in self.models.items()
            if model["entity"] == "phoenix"
        }
        if self.models:
            for actor in actors.values():
                if actor["team"] == "attack" and "healing_model" in actor:
                    if "pet_healing_policy" not in actor["healing_model"]:
                        raise InputError(
                            "Healers accompanying pets need an explicit pet healing policy"
                        )

    @staticmethod
    def _clear_route(actor):
        actor.pop("_path_signature", None)
        actor.pop("_remaining_path", None)

    def _solid(self, actor, actors, time, blocked):
        if actor.get("wall_behavior", {}).get("kind") != "jump_enemy_walls":
            return blocked
        walls = {
            (item["x"], item["y"])
            for item in actors.values()
            if item["kind"] == "wall"
            and item["team"] != actor["team"]
            and _active(item, time)
        }
        return blocked - walls

    def _validate_position(self, actor, time):
        if not (0 <= actor["x"] < self.width and 0 <= actor["y"] < self.height):
            raise InputError("Pet deployment or emergence is outside the board")
        if actor["movement"] == "ground":
            solid = self._solid(actor, self.actors, time, _blocked(self.actors, time))
            if (floor(actor["x"]), floor(actor["y"])) in solid:
                raise InputError(
                    "Pet deployment or emergence occupies a solid footprint"
                )

    def _route_to(self, actor, target, time, blocked, attack_range=None):
        routed = {
            **actor,
            "range": actor["range"] if attack_range is None else attack_range,
        }
        routed["_terminal_ground_approach"] = True
        solid = self._solid(actor, self.actors, time, blocked)
        route = _route(routed, target, solid, self.width, self.height)
        if route is not None:
            _remember_route(routed, target, route, solid)
            for field in ("_path_signature", "_remaining_path"):
                if field in routed:
                    actor[field] = routed[field]
        return route

    @staticmethod
    def _enemy_eligible(actor, target, time):
        return _eligible(actor, target, time) and not target.get("_tesla_hidden", False)

    def _enemy_target(self, actor, time, blocked, underground=False):
        state = self.states[actor["id"]]
        model = self.models[actor["id"]]
        owner = self.actors[state["bonded_hero_id"]]
        owner_active = _active(owner, time)
        policy = model["parameters"]["target_retention"]
        preferred = []
        if policy == "prefer_owner_primary_then_nearest" and owner_active:
            preferred.append(owner.get("target"))
        preferred.append(actor.get("target"))
        if (
            policy == "retain_until_ineligible_then_prefer_owner_primary"
            and owner_active
        ):
            preferred.append(owner.get("target"))
        for target_id in preferred:
            target = self.actors.get(target_id)
            if target is not None and self._enemy_eligible(actor, target, time):
                route = (
                    [] if underground else self._route_to(actor, target, time, blocked)
                )
                if route is not None:
                    return target, route
        choices = []
        for target in self.actors.values():
            if not self._enemy_eligible(actor, target, time):
                continue
            route = [] if underground else self._route_to(actor, target, time, blocked)
            if route is None:
                continue
            radius = model["owner_preference_radius"]
            outside_owner_radius = (
                radius is not None
                and owner_active
                and target_distance(center(owner), target) > radius + EPSILON
            )
            distance = target_distance(center(actor), target)
            travel = distance if underground else _route_length(actor, route)
            choices.append(
                (
                    outside_owner_radius,
                    actor["_target_ranks"][target["kind"]],
                    travel,
                    distance,
                    target["id"],
                    target,
                    route,
                )
            )
        if not choices:
            return None, None
        selected = min(choices, key=lambda item: item[:5])
        return selected[-2], selected[-1]

    def _healing_target(self, actor, time):
        state = self.states[actor["id"]]
        owner = self.actors[state["bonded_hero_id"]]
        if _active(owner, time):
            return owner
        choices = [
            target
            for target in self.actors.values()
            if _active(target, time)
            and target["team"] == actor["team"]
            and target["kind"] == "unit"
            and target.get("healing_class") in {"hero", "troop"}
        ]
        return min(
            choices,
            key=lambda target: (
                target.get("healing_class") != "hero",
                target_distance(center(actor), target),
                target["id"],
            ),
            default=None,
        )

    def select_target(self, actor, actors, time, blocked, width, height):
        if actor["id"] not in self.models:
            return self.base_selector(actor, actors, time, blocked, width, height)
        if not _active(actor, time):
            return None, None
        if (
            self.models[actor["id"]]["entity"] == "diggy"
            and self.states[actor["id"]]["dive_at"] is not None
        ):
            return None, None
        if self.models[actor["id"]]["entity"] == "unicorn":
            target = self._healing_target(actor, time)
            actor["healing_target"] = target["id"] if target else None
            return None, (
                self._route_to(actor, target, time, blocked) if target else None
            )
        target, route = self._enemy_target(actor, time, blocked)
        actor["target"] = target["id"] if target else None
        if target is not None:
            # Candidate scoring may have cached another route last.
            return target, self._route_to(actor, target, time, blocked)
        owner = actors[self.states[actor["id"]]["bonded_hero_id"]]
        if _active(owner, time):
            route = self._route_to(
                actor,
                owner,
                time,
                blocked,
                self.models[actor["id"]]["parameters"]["follow_distance_tiles"],
            )
        return None, route

    def _deploy(self, pet_id, time, trace):
        actor = self.actors[pet_id]
        model = self.models[pet_id]
        state = self.states[pet_id]
        owner = self.actors[model["hero_id"]]
        offset = model["parameters"]["spawn_offset"]
        point = center(owner)
        actor.update(x=point[0] + offset["dx"], y=point[1] + offset["dy"])
        if model["entity"] == "diggy":
            if not (0 <= actor["x"] < self.width and 0 <= actor["y"] < self.height):
                raise InputError("Diggy deployment is outside the board")
        else:
            self._validate_position(actor, time)
        state["deployed_at"] = time
        if model["entity"] == "phoenix":
            state["phase"] = "egg"
        elif model["entity"] == "diggy":
            state["phase"] = "underground"
        else:
            state["phase"] = "active"
            actor["spawn_seconds"] = time
            actor["next_attack"] = time + actor["first_attack_seconds"]
        if model["entity"] == "spirit-fox":
            state["next_cloak"] = (
                time + model["parameters"]["behavior"]["initial_cloak_delay_seconds"]
            )
        trace.append(
            {
                "event": "pet_deployed",
                "time_seconds": time,
                "pet": pet_id,
                "hero": model["hero_id"],
                "phase": state["phase"],
            }
        )

    def _rebond(self, pet_id, time, trace):
        actor = self.actors[pet_id]
        state = self.states[pet_id]
        owner = self.actors[state["bonded_hero_id"]]
        if _active(owner, time):
            return
        candidates = [
            target
            for target in self.actors.values()
            if "hero_model" in target
            and target["team"] == actor["team"]
            and _active(target, time)
        ]
        if not candidates:
            return
        new_owner = min(
            candidates,
            key=lambda target: (target_distance(center(actor), target), target["id"]),
        )
        previous = state["bonded_hero_id"]
        state["bonded_hero_id"] = new_owner["id"]
        trace.append(
            {
                "event": "pet_rebond",
                "time_seconds": time,
                "pet": pet_id,
                "previous_hero": previous,
                "hero": new_owner["id"],
            }
        )

    def _surface_destination(self, actor, target, time):
        point = center(actor)
        nearest = (
            min(max(point[0], target["x"]), target["x"] + target["width"]),
            min(max(point[1], target["y"]), target["y"] + target["height"]),
        )
        distance = hypot(nearest[0] - point[0], nearest[1] - point[1])
        attack_range = actor["range"]
        candidates = []
        if distance > EPSILON:
            fraction = max(distance - attack_range, 0) / distance
            candidates.append(
                (
                    point[0] + (nearest[0] - point[0]) * fraction,
                    point[1] + (nearest[1] - point[1]) * fraction,
                )
            )
        tx, ty = center(target)
        candidates.extend(
            (
                (target["x"] - attack_range, ty),
                (target["x"] + target["width"] + attack_range, ty),
                (tx, target["y"] - attack_range),
                (tx, target["y"] + target["height"] + attack_range),
            )
        )
        solid = self._solid(actor, self.actors, time, _blocked(self.actors, time))
        candidates = [
            candidate
            for candidate in candidates
            if 0 <= candidate[0] < self.width
            and 0 <= candidate[1] < self.height
            and (floor(candidate[0]), floor(candidate[1])) not in solid
            and target_distance(candidate, target) <= attack_range + EPSILON
        ]
        return min(
            candidates,
            key=lambda candidate: (
                hypot(candidate[0] - point[0], candidate[1] - point[1]),
                candidate,
            ),
            default=None,
        )

    def _begin_burrow(self, pet_id, target, time, trace, follow_owner=False):
        actor = self.actors[pet_id]
        state = self.states[pet_id]
        origin = center(actor)
        if follow_owner:
            point = center(target)
            distance = hypot(point[0] - origin[0], point[1] - origin[1])
            follow_distance = self.models[pet_id]["parameters"]["follow_distance_tiles"]
            if distance <= follow_distance + EPSILON:
                actor["spawn_seconds"] = "controlled"
                actor["target"] = None
                state.update(phase="underground", dive_at=None)
                return
            fraction = (distance - follow_distance) / distance
            destination = tuple(
                origin[axis] + (point[axis] - origin[axis]) * fraction
                for axis in (0, 1)
            )
        else:
            destination = self._surface_destination(actor, target, time)
        if destination is None:
            return
        behavior = self.models[pet_id]["parameters"]["behavior"]
        speed = movement_speed(actor)
        arrival = (
            time + hypot(destination[0] - origin[0], destination[1] - origin[1]) / speed
        )
        state.update(
            phase="underground",
            dive_at=None,
            stun_pending_target=None,
            burrow={
                "target": target["id"],
                "origin": origin,
                "destination": destination,
                "start_seconds": time,
                "arrival_seconds": arrival,
                "surface_seconds": arrival
                + (0 if follow_owner else behavior["emerge_delay_seconds"]),
                "will_surface": not follow_owner,
            },
        )
        actor["spawn_seconds"] = "controlled"
        actor["target"] = None if follow_owner else target["id"]
        self._clear_route(actor)
        trace.append(
            {
                "event": "pet_burrow",
                "time_seconds": time,
                "pet": pet_id,
                "target": target["id"],
                "surface_seconds": state["burrow"]["surface_seconds"],
                "will_surface": not follow_owner,
            }
        )

    def _finish_burrow(self, pet_id, time, trace):
        actor = self.actors[pet_id]
        state = self.states[pet_id]
        burrow = state["burrow"]
        if burrow is None or burrow["surface_seconds"] > time + EPSILON:
            return
        actor["x"], actor["y"] = burrow["destination"]
        state["burrow"] = None
        if not burrow["will_surface"]:
            return
        self._validate_position(actor, time)
        actor["spawn_seconds"] = time
        actor["next_attack"] = time + actor["first_attack_seconds"]
        state.update(phase="active", stun_pending_target=burrow["target"])
        trace.append(
            {
                "event": "pet_emerged",
                "time_seconds": time,
                "pet": pet_id,
                "target": burrow["target"],
            }
        )

    def _prepare_diggy(self, pet_id, time, trace):
        actor = self.actors[pet_id]
        state = self.states[pet_id]
        self._rebond(pet_id, time, trace)
        self._finish_burrow(pet_id, time, trace)
        if (
            state["burrow"] is not None
            or actor["frozen_until"] > time + EPSILON
            or actor.get("_displacement_pause_until", 0) > time + EPSILON
        ):
            return
        target = self.actors.get(actor.get("target"))
        if (
            state["phase"] == "active"
            and target is not None
            and self._enemy_eligible(actor, target, time)
            and target_distance(center(actor), target) <= actor["range"] + EPSILON
        ):
            return
        if state["phase"] == "active":
            if state["dive_at"] is None:
                state["dive_at"] = (
                    time
                    + self.models[pet_id]["parameters"]["behavior"][
                        "burrow_windup_seconds"
                    ]
                )
            if state["dive_at"] > time + EPSILON:
                return
        target, _ = self._enemy_target(
            actor, time, _blocked(self.actors, time), underground=True
        )
        if target is not None:
            self._begin_burrow(pet_id, target, time, trace)
            self._finish_burrow(pet_id, time, trace)
        else:
            owner = self.actors[state["bonded_hero_id"]]
            if _active(owner, time):
                self._begin_burrow(pet_id, owner, time, trace, follow_owner=True)

    def prepare(self, actors, time, trace):
        for pet_id, model in self.models.items():
            actor = actors[pet_id]
            state = self.states[pet_id]
            owner = actors[model["hero_id"]]
            if state["phase"] == "waiting_for_owner":
                if not _active(owner, time):
                    continue
                self._deploy(pet_id, time, trace)
            if actor["hp"] <= 0:
                state["phase"] = "dead"
            expiry = state["temporary_life_until"]
            if expiry is not None and expiry <= time + EPSILON:
                owner["hp"] = 0
                owner["death_time"] = expiry
                owner["_pet_healing_blocked_until"] = 0
                state["temporary_life_until"] = None
                trace.append(
                    {
                        "event": "phoenix_owner_expired",
                        "time_seconds": expiry,
                        "pet": pet_id,
                        "hero": owner["id"],
                    }
                )
            if state["phase"] == "dead":
                continue
            if state["phase"] == "egg":
                actor["x"], actor["y"] = center(owner)
                continue
            if model["entity"] == "diggy":
                self._prepare_diggy(pet_id, time, trace)
            if (
                model["entity"] == "spirit-fox"
                and state["next_cloak"] <= time + EPSILON
            ):
                duration = model["cloak_duration_seconds"]
                recipients = [actor]
                if _active(owner, time):
                    recipients.append(owner)
                for recipient in recipients:
                    recipient["_untargetable_until"] = max(
                        recipient.get("_untargetable_until", 0), time + duration
                    )
                state["next_cloak"] += (
                    duration
                    + model["parameters"]["behavior"]["visible_interval_seconds"]
                )
                state["cloak_count"] += 1
                trace.append(
                    {
                        "event": "pet_cloak",
                        "time_seconds": time,
                        "pet": pet_id,
                        "targets": [recipient["id"] for recipient in recipients],
                        "expires_at": time + duration,
                    }
                )

    def resolve_healing(self, actors, time, trace):
        healing = defaultdict(float)
        for pet_id, model in self.models.items():
            actor = actors[pet_id]
            if (
                model["entity"] != "unicorn"
                or not _active(actor, time)
                or actor["frozen_until"] > time + EPSILON
                or actor.get("_displacement_pause_until", 0) > time + EPSILON
                or actor["next_attack"] > time + EPSILON
            ):
                continue
            target = self._healing_target(actor, time)
            actor["healing_target"] = target["id"] if target else None
            if (
                target is None
                or target_distance(center(actor), target) > actor["range"] + EPSILON
            ):
                continue
            amount = model["healing_per_pulse"] * healing_multiplier(actor)
            healing[target["id"]] += amount
            actor["next_attack"] = time + actor[
                "attack_interval_seconds"
            ] / attack_rate(actor)
            self.states[pet_id]["healing_pulses"] += 1
            trace.append(
                {
                    "event": "pet_healing_pulse",
                    "time_seconds": time,
                    "pet": pet_id,
                    "target": target["id"],
                    "requested_healing": amount,
                }
            )
        return healing

    def impact(self, packet, target, actors, time, trace):
        pet_id = packet["source"]
        if pet_id not in self.models or self.models[pet_id]["entity"] != "diggy":
            return
        model = self.models[pet_id]
        state = self.states[pet_id]
        behavior = model["parameters"]["behavior"]
        if (
            state["stun_pending_target"] != target["id"]
            or not _active(target, time)
            or target["kind"] not in behavior["stun_target_kinds"]
        ):
            return
        state["stun_pending_target"] = None
        if (
            target["immune_until"] > time + EPSILON
            and behavior["stun_protection_policy"] == "damage_immunity_blocks_stun"
        ):
            return
        end = time + model["stun_duration_seconds"]
        pause_attack_work(target, time, end)
        target["frozen_until"] = max(target["frozen_until"], end)
        trace.append(
            {
                "event": "pet_emergence_stun",
                "time_seconds": time,
                "pet": pet_id,
                "target": target["id"],
                "expires_at": end,
            }
        )

    def intercept_lethal(self, actor, time, trace):
        """Called once after aggregated lethal damage, before recording a death.

        Callers must also honor healing_allowed during the shared health phase.
        Ejection, explicit expiration and non-damage removal never call this hook.
        """
        pet_id = self.phoenix_by_hero.get(actor["id"])
        if pet_id is None:
            return False
        state = self.states[pet_id]
        if state["rescue_used"] or state["phase"] != "egg":
            return False
        phoenix = self.actors[pet_id]
        expiry = time + self.models[pet_id]["revival_duration_seconds"]
        state.update(phase="active", rescue_used=True, temporary_life_until=expiry)
        actor.update(hp=1, death_time=None)
        actor["immune_until"] = max(actor["immune_until"], expiry)
        actor["_pet_healing_blocked_until"] = expiry
        phoenix["x"], phoenix["y"] = center(actor)
        phoenix["spawn_seconds"] = time
        phoenix["next_attack"] = time + phoenix["first_attack_seconds"]
        phoenix["immune_until"] = max(phoenix["immune_until"], expiry)
        trace.append(
            {
                "event": "phoenix_hatched",
                "time_seconds": time,
                "pet": pet_id,
                "hero": actor["id"],
                "temporary_life_until": expiry,
            }
        )
        return True

    @staticmethod
    def healing_allowed(actor, time):
        return actor.get("_pet_healing_blocked_until", 0) <= time + EPSILON

    def advance(self, actors, time, duration, trace):
        end = time + number(duration, "pet internal movement duration", 0)
        for pet_id, state in self.states.items():
            burrow = state["burrow"]
            if burrow is None or actors[pet_id]["hp"] <= 0:
                continue
            travel = burrow["arrival_seconds"] - burrow["start_seconds"]
            fraction = (
                1
                if travel <= EPSILON
                else min(1, max(end - burrow["start_seconds"], 0) / travel)
            )
            actors[pet_id]["x"], actors[pet_id]["y"] = tuple(
                burrow["origin"][axis]
                + (burrow["destination"][axis] - burrow["origin"][axis]) * fraction
                for axis in (0, 1)
            )

    def next_boundary(self, time):
        boundaries = []
        for pet_id, state in self.states.items():
            actor = self.actors[pet_id]
            boundaries.extend(
                state[field]
                for field in ("next_cloak", "temporary_life_until", "dive_at")
                if state[field] is not None
            )
            if state["burrow"] is not None:
                boundaries.extend(
                    state["burrow"][field]
                    for field in ("arrival_seconds", "surface_seconds")
                )
            if _active(actor, time):
                boundaries.extend(
                    (
                        actor["next_attack"],
                        actor["frozen_until"],
                        actor.get("_untargetable_until", 0),
                    )
                )
            owner = self.actors[state["bonded_hero_id"]]
            boundaries.append(owner.get("_untargetable_until", 0))
            if state["phase"] == "waiting_for_owner" and isinstance(
                owner["spawn_seconds"], (int, float)
            ):
                boundaries.append(owner["spawn_seconds"])
        future = [value for value in boundaries if value > time + EPSILON]
        return min(future) if future else None

    def range_target(self, actor, time):
        """Expose healing and offensive primaries to the shared contact scheduler."""
        if actor["id"] not in self.models or not _active(actor, time):
            return None
        if self.models[actor["id"]]["entity"] == "unicorn":
            return self._healing_target(actor, time)
        return self.actors.get(actor.get("target"))

    def first_crossing_delay(
        self,
        actor,
        route,
        time,
        horizon,
        effective_speed,
        target_route=(),
        target_speed=0,
    ):
        target = self.range_target(actor, time)
        if target is None:
            return None
        return first_weapon_range_entry_delay(
            actor,
            target,
            route,
            target_route,
            effective_speed,
            target_speed,
            horizon,
        )

    def frame(self, actor, time):
        state = self.states.get(actor["id"])
        if state is not None:
            return {"pet_lifecycle": deepcopy(state)}
        pet_id = self.phoenix_by_hero.get(actor["id"])
        if pet_id is not None:
            return {
                "phoenix_temporary_life_until": self.states[pet_id][
                    "temporary_life_until"
                ]
            }
        return {}

    def result(self):
        return {
            "pets": deepcopy(self.states),
            "behavior_verification": "explicit_paired_pet_hypotheses_not_replay_validated",
            "unsupported_pet_mechanics": deepcopy(MISSING_PET_MECHANICS),
        }
