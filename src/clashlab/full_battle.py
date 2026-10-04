"""Run a complete declared lineup against a complete declared layout.

Completeness concerns the supplied army and inventory, not a maximal village.
This bridge never removes unsupported objects to make a scene executable. The
underlying combat and layout conventions remain conditional and uncalibrated.
"""

from collections import Counter, defaultdict
from copy import deepcopy

from .adapters import compile_actor, compile_entity_scene
from .army import validate_army
from .battle_modifiers import apply_battle_modifiers
from .common import InputError, identifier, integer, number, require, stable_id
from .engine_rules import RULES, SCOPE
from .buff_rules import RULES as BUFF_RULES, SCOPE as BUFF_SCOPE
from .geometry import validate_layout
from .indirect_rules import RULES as INDIRECT_RULES, SCOPE as INDIRECT_SCOPE
from .sweeper_rules import RULES as SWEEPER_RULES, SCOPE as SWEEPER_SCOPE
from .defending_hero_rules import (
    RULES as DEFENDING_HERO_RULES,
    SCOPE as DEFENDING_HERO_SCOPE,
)
from .spell_tower_rules import RULES as SPELL_TOWER_RULES, SCOPE as SPELL_TOWER_SCOPE
from .builder_rules import RULES as BUILDER_RULES, SCOPE as BUILDER_SCOPE
from .garrison_rules import RULES as GARRISON_RULES, SCOPE as GARRISON_SCOPE
from .guardian_rules import RULES as GUARDIAN_RULES, SCOPE as GUARDIAN_SCOPE
from .siege_rules import RULES as SIEGE_RULES, SCOPE as SIEGE_SCOPE
from .pet_rules import RULES as PET_RULES, SCOPE as PET_SCOPE
from .hero_roster_rules import (
    RULES as HERO_ROSTER_RULES,
    SCOPE as HERO_ROSTER_SCOPE,
    select_duke_isolation_rules,
)
from .termination_rules import RULES as TERMINATION_RULES, SCOPE as TERMINATION_SCOPE
from .attack_spell_rules import RULES as ATTACK_SPELL_RULES, SCOPE as ATTACK_SPELL_SCOPE
from .attack_spell_models import SUPPORTED_ATTACK_SPELLS, validate_spell_classifications
from .battle_resources import battle_resource_use
from .battle_termination import (
    BattleTermination,
    CompletionOnlyTermination,
    validate_termination_policy,
)
from .advanced_defense_rules import (
    RULES as ADVANCED_DEFENSE_RULES,
    SCOPE as ADVANCED_DEFENSE_SCOPE,
)
from .hero_pets import validate_pet_inventory
from .reinforcements import (
    ReinforcementCombat,
    compile_attacking_reinforcements,
    validate_reinforcement_inventory,
    validate_spell_origin_counts,
    validate_received_entity,
)
from .guardians import validate_binding
from .firespitter_rules import RULES as FIRESPITTER_RULES, SCOPE as FIRESPITTER_SCOPE
from .trap_lifecycle_rules import (
    RULES as TRAP_LIFECYCLE_RULES,
    SCOPE as TRAP_LIFECYCLE_SCOPE,
)
from .scoring import validate_outcome
from .spatial import EPSILON, simulate_spatial


CONTRACT = "complete-declared-army-and-layout-v1"
SUPPORTED_SPELLS = {
    "freeze-spell": "freeze_spells",
    "healing-spell": "healing_spells",
    "rage-spell": "buff_spells",
    "haste-spell": "buff_spells",
    **{entity: "attack_spells" for entity in SUPPORTED_ATTACK_SPELLS},
}
SCENE_FIELDS = {
    "id",
    "scope",
    "model_rules",
    "statistics_policy",
    "unit_conventions",
    "unsupported_mechanics",
    "width",
    "height",
    "duration_seconds",
    "maximum_step_seconds",
    "recording_interval_seconds",
    "entities",
    "effects",
    "freeze_spells",
    "healing_spells",
    "healing_stacking",
    "persistent_hazards",
    "target_scoring",
    "traps",
    "buff_spells",
    "attack_spells",
    "defending_unit_responses",
    "attacking_reinforcements",
    "pets",
}


def _list(mapping, field):
    values = require(mapping, field)
    if not isinstance(values, list):
        raise InputError(f"{field} must be an explicit list")
    return values


def _indexed(values, field, label):
    indexed = {}
    for item in values:
        key = identifier(require(item, field), label)
        if key in indexed:
            raise InputError(f"Duplicate {label}: {key}")
        indexed[key] = item
    return indexed


def _time(value, limit, label):
    return number(value, label, 0, limit)


def _army_shape(army):
    for field in ("troops", "spells", "heroes"):
        _list(army, field)
    require(army, "clan_castle")
    for field in ("troops", "spells"):
        _list(army["clan_castle"], field)
    if "siege" not in army:
        raise InputError("The army must explicitly select siege or null")
    for hero in army["heroes"]:
        if "pet" not in hero:
            raise InputError("Every hero must explicitly select a pet or null")
        _list(hero, "equipment")


def _unsupported_obligations(army, layout):
    for item in [*army["spells"], *army["clan_castle"]["spells"]]:
        if item["id"] not in SUPPORTED_SPELLS:
            raise InputError(f"Declared spell needs its runtime adapter: {item['id']}")
    castle = layout.get("design_configuration", {}).get("defensive_castle")
    if castle:
        raise InputError(
            "Legacy defensive_castle requirements must bind explicitly through the castle settings.garrison roster"
        )


def _layout_actor_id(building):
    if building["id"] == "hero-banner":
        return f"{building['instance']}:defender"
    return building["instance"]


def _layout_defense_facing(layout, building):
    settings = require(building, "settings")
    if set(settings) != {"facing_degrees"}:
        raise InputError(
            "Oriented defense layout settings must supply only facing_degrees"
        )
    facing = number(settings["facing_degrees"], "layout defense facing", 0, 359)
    convention = require(
        require(layout, "design_configuration"), "direction_convention"
    )
    if convention == "clockwise_from_positive_x_in_screen_coordinates":
        return facing
    if (
        convention
        == "draft_grid_north_zero_degrees_clockwise_not_verified_UI_orientation"
    ):
        return (facing - 90) % 360
    raise InputError(
        "Layout direction convention needs an explicit supported conversion"
    )


def _bind_hero_banner(building, instance, layout):
    settings = require(building, "settings")
    if set(settings) != {"hero", "level"}:
        raise InputError("Hero Banner settings need an explicit hero and level")
    expected = {
        "id": _layout_actor_id(building),
        "entity": settings["hero"],
        "level": settings["level"],
        "team": "defense",
        "town_hall": layout["town_hall"],
        "spawn_seconds": 0,
        "counts_for_destruction": building["counts_for_destruction"],
    }
    for field, value in expected.items():
        if require(instance, field) != value:
            raise InputError(
                f"Defending hero differs from layout {field}: {building['instance']}"
            )
    banner = require(require(instance, "defending_hero_parameters"), "banner")
    for field, value in {
        "id": building["instance"],
        "x": building["x"],
        "y": building["y"],
    }.items():
        if require(banner, field) != value:
            raise InputError(f"Defending hero banner differs from layout {field}")
    return {
        "entity": settings["hero"],
        "level": settings["level"],
        "collection": "actors",
        "source_layout_instance": building["instance"],
        "counts_for_destruction": building["counts_for_destruction"],
    }


def _bind_defenders(layout, scene, catalog):
    structures = _indexed(layout["buildings"], "instance", "layout instance")
    defenders = _indexed(
        [item for item in scene["entities"] if item["team"] == "defense"],
        "id",
        "defender instance",
    )
    members = {
        actor_id: defenders.pop(actor_id)
        for actor_id in list(defenders)
        if "garrison_member_parameters" in defenders[actor_id]
    }
    guardians = {
        actor_id: defenders.pop(actor_id)
        for actor_id in list(defenders)
        if "guardian_parameters" in defenders[actor_id]
    }
    traps = _indexed(_list(scene, "traps"), "id", "trap instance")
    expected_ids = {_layout_actor_id(building) for building in structures.values()}
    if len(expected_ids) != len(structures):
        raise InputError("Layout actor identities collide with a derived hero identity")
    if set(defenders) & set(traps) or set(defenders) | set(traps) != expected_ids:
        raise InputError(
            "Every layout instance must bind to exactly one defender or trap"
        )
    bindings = {}
    for key, building in structures.items():
        if building["id"] == "hero-banner":
            actor_id = _layout_actor_id(building)
            if actor_id not in defenders:
                raise InputError("A Hero Banner must bind to a defending hero actor")
            bindings[actor_id] = _bind_hero_banner(
                building, defenders[actor_id], layout
            )
            continue
        entity = catalog.entity(building["id"])
        is_trap = entity["category"] == "trap"
        source = traps if is_trap else defenders
        if key not in source:
            raise InputError(
                f"Layout instance is in the wrong runtime collection: {key}"
            )
        instance = source[key]
        expected = {
            "id": key,
            "entity": building["id"],
            "level": building["level"],
            "town_hall": layout["town_hall"],
            "team": "defense",
            "x": building["x"],
            "y": building["y"],
        }
        for field, value in expected.items():
            if require(instance, field) != value:
                raise InputError(f"Defender/layout {field} binding differs: {key}")
        if building["id"] == "wall" or is_trap:
            if building["counts_for_destruction"] is not False:
                raise InputError(
                    "Walls and traps cannot count toward battle destruction"
                )
        if is_trap:
            if instance.get("counts_for_destruction", False) is not False:
                raise InputError("Runtime traps cannot count toward battle destruction")
            if building["id"] == "skeleton-trap":
                settings = require(building, "settings")
                if not isinstance(settings, dict) or set(settings) != {"target_layer"}:
                    raise InputError(
                        "Skeleton Trap settings require exactly target_layer"
                    )
                if settings["target_layer"] != require(instance, "mode"):
                    raise InputError(
                        f"Skeleton Trap target layer differs from layout: {key}"
                    )
        else:
            if (
                require(instance, "counts_for_destruction")
                != building["counts_for_destruction"]
            ):
                raise InputError(
                    f"Defender destruction flag differs from layout: {key}"
                )
            if require(instance, "spawn_seconds") != 0:
                raise InputError("All declared defenders must exist at battle start")
            if building["id"] == "multi-gear-tower":
                require(building, "mode")
            if "mode" in building and instance["mode"] != building["mode"]:
                raise InputError(f"Defender mode differs from layout: {key}")
            if building["id"] in {"air-sweeper", "firespitter"}:
                facing = _layout_defense_facing(layout, building)
                parameters = (
                    "sweeper_parameters"
                    if building["id"] == "air-sweeper"
                    else "firespitter_parameters"
                )
                if require(instance[parameters], "orientation_degrees") != facing:
                    raise InputError(
                        f"{entity['name']} facing differs from layout: {key}"
                    )
        if building["id"] == "clan-castle":
            bindings.update(_bind_garrison_contents(building, instance, members))
        if building["id"] == "town-hall" and building["level"] == 18:
            bindings.update(_bind_guardian(building, instance, guardians, layout))
        elif building["id"] == "town-hall" and building.get("settings"):
            raise InputError("Guardian settings require a TH18 Hall")
        if building.get("settings") and building["id"] not in {
            "air-sweeper",
            "firespitter",
            "clan-castle",
            "skeleton-trap",
            "town-hall",
        }:
            raise InputError(
                f"Layout settings require a corresponding runtime binding: {key}"
            )
        bindings[key] = {
            "entity": building["id"],
            "level": building["level"],
            "collection": "traps" if is_trap else "actors",
            "counts_for_destruction": building["counts_for_destruction"],
            **(
                {"orientation_degrees": facing}
                if building["id"] in {"air-sweeper", "firespitter"}
                else {}
            ),
        }
    if members:
        raise InputError("Garrison members are not bound to a layout castle")
    if guardians:
        raise InputError("Guardian actors are not bound to the selected TH18 Hall")
    return bindings


def _bind_guardian(building, hall, guardians, layout):
    settings = require(building, "settings")
    if not isinstance(settings, dict) or set(settings) != {"guardian"}:
        raise InputError("TH18 Hall settings need exactly one selected Guardian")
    selected = settings["guardian"]
    if not isinstance(selected, dict) or set(selected) != {
        "actor_id",
        "entity",
        "level",
    }:
        raise InputError("Selected Guardian must declare actor ID, entity and level")
    binding = require(hall, "guardian_binding")
    validate_binding(binding)
    if selected != {key: value for key, value in binding.items() if key != "source"}:
        raise InputError("TH18 Hall and layout selected Guardian bindings differ")
    actor_id = selected["actor_id"]
    actor = guardians.pop(actor_id, None)
    if actor is None or any(
        actor.get(key) != value
        for key, value in {
            "id": actor_id,
            "entity": selected["entity"],
            "level": selected["level"],
            "town_hall": layout["town_hall"],
            "team": "defense",
            "spawn_seconds": "controlled",
            "counts_for_destruction": False,
        }.items()
    ):
        raise InputError("Selected Guardian actor role, level or Town Hall differs")
    if require(actor["guardian_parameters"], "hall_id") != hall["id"]:
        raise InputError("Guardian actor links to a different Hall")
    return {
        actor_id: {
            "entity": selected["entity"],
            "level": selected["level"],
            "collection": "actors",
            "counts_for_destruction": False,
            "role": "guardian",
            "hall_id": hall["id"],
        }
    }


def _bind_garrison_contents(building, castle, members):
    settings = require(building, "settings")
    if not isinstance(settings, dict) or set(settings) != {"garrison"}:
        raise InputError(
            "Clan Castle settings need an explicit garrison roster, including an empty list"
        )
    expected = Counter()
    for item in _list(settings, "garrison"):
        if not isinstance(item, dict) or set(item) != {
            "entity",
            "level",
            "count",
            "donor_town_hall",
        }:
            raise InputError(
                "Layout garrison entries require entity, level, count and donor Town Hall"
            )
        entity_id = identifier(item["entity"], "layout garrison entity")
        key = entity_id, item["level"], item["donor_town_hall"]
        if key in expected:
            raise InputError("Layout garrison entries must be unique")
        integer(item["level"], "garrison level", 1)
        integer(item["donor_town_hall"], "garrison donor Town Hall", 1)
        expected[key] = integer(item["count"], "garrison count", 1)
    member_ids = require(require(castle, "garrison_parameters"), "member_ids")
    if not isinstance(member_ids, list) or len(member_ids) != len(set(member_ids)):
        raise InputError("Castle member IDs must be unique")
    actual = Counter()
    bindings = {}
    for member_id in member_ids:
        if member_id not in members:
            raise InputError("Castle roster member is missing or already bound")
        member = members.pop(member_id)
        parameters = member["garrison_member_parameters"]
        if (
            parameters["castle_id"] != castle["id"]
            or member["spawn_seconds"] != "controlled"
            or member["counts_for_destruction"]
        ):
            raise InputError("Garrison member must be its castle's non-counted reserve")
        actual[(member["entity"], member["level"], parameters["donor_town_hall"])] += 1
        bindings[member_id] = {
            "entity": member["entity"],
            "level": member["level"],
            "collection": "actors",
            "source_layout_instance": building["instance"],
            "counts_for_destruction": False,
            "role": "defending_garrison",
        }
    if actual != expected:
        raise InputError(
            "Runtime garrison contents differ from the declared layout roster"
        )
    return bindings


def _bind_reinforcements(army, account, scene, catalog, attackers):
    instances = {
        actor_id: instance
        for actor_id, instance in attackers.items()
        if "payload_member_parameters" in instance
        or catalog.entity(instance["entity"])["category"] == "siege-machine"
    }
    if "attacking_reinforcements" not in scene:
        if instances or army["clan_castle"]["troops"] or army["siege"] is not None:
            raise InputError(
                "Declared attacking Clan Castle troops and siege need a delivery adapter"
            )
        return {}, None
    if scene["scope"] not in {
        SIEGE_SCOPE,
        PET_SCOPE,
        ADVANCED_DEFENSE_SCOPE,
        HERO_ROSTER_SCOPE,
        TERMINATION_SCOPE,
        ATTACK_SPELL_SCOPE,
    }:
        raise InputError("Attacking reinforcements require the explicit v24 scope")
    compiled = {
        actor_id: compile_actor(
            instance,
            catalog,
            scene["unit_conventions"]["movement_units_per_tile"],
            allow_walls=True,
            allow_support=True,
            allow_ramps=True,
            allow_deaths=True,
            allow_town_halls=True,
            allow_area_defenses=True,
            allow_heroes=True,
            allow_artillery=True,
            allow_hit_status=True,
            allow_extended=True,
            allow_indirect=True,
            allow_sweepers=True,
            allow_defending_heroes=True,
            allow_spell_towers=True,
            allow_builders=True,
            allow_garrisons=True,
            allow_firespitters=True,
            allow_guardians=True,
            allow_reinforcements=True,
        )
        for actor_id, instance in instances.items()
    }
    model = compile_attacking_reinforcements(
        scene["attacking_reinforcements"], catalog, compiled
    )
    bindings = validate_reinforcement_inventory(model, compiled, army, account, catalog)
    return bindings, ReinforcementCombat(
        compiled, model, scene["width"], scene["height"]
    )


def _bind_attackers(army, account, scene, catalog):
    attackers = _indexed(
        [item for item in scene["entities"] if item["team"] == "attack"],
        "id",
        "attacker instance",
    )
    expected_troops = Counter(
        {(item["id"], item["level"]): item["count"] for item in army["troops"]}
    )
    actual_troops = Counter()
    actual_heroes = {}
    bindings, reinforcements = _bind_reinforcements(
        army, account, scene, catalog, attackers
    )
    for actor_id, instance in sorted(attackers.items()):
        entity_id = require(instance, "entity")
        level = require(instance, "level")
        if require(instance, "town_hall") != account["town_hall"]:
            raise InputError(
                f"Attacker Town Hall differs from the validated account: {actor_id}"
            )
        if require(instance, "counts_for_destruction") is not False:
            raise InputError("Attackers must be outside defending destruction counts")
        if actor_id in bindings:
            continue
        category = catalog.entity(entity_id)["category"]
        if category == "troop":
            key = entity_id, level
            actual_troops[key] += 1
            binding = {
                "origin": "army_troops",
                "entity": entity_id,
                "level": level,
                "ordinal": actual_troops[key],
            }
        elif category == "hero":
            if entity_id in actual_heroes:
                raise InputError(f"Duplicate attacking hero: {entity_id}")
            actual_heroes[entity_id] = instance
            binding = {"origin": "army_heroes", "entity": entity_id, "level": level}
        else:
            raise InputError(f"Attacker has no declared army-slot adapter: {entity_id}")
        bindings[actor_id] = binding
    if actual_troops != expected_troops:
        raise InputError(
            "Attacking actor identity, level and count must exactly match every army troop"
        )
    expected_heroes = {item["id"]: item for item in army["heroes"]}
    if set(actual_heroes) != set(expected_heroes):
        raise InputError(
            "Attacking hero actors must exactly match the declared hero lineup"
        )
    for entity_id, selected in expected_heroes.items():
        instance = actual_heroes[entity_id]
        if (
            instance["level"] != selected["level"]
            or instance["mode"] != selected["mode"]
        ):
            raise InputError(f"Hero level or mode differs from the army: {entity_id}")
        parameters = require(instance, "hero_parameters")
        if require(parameters, "loadout_policy") != "exact_two_equipment":
            raise InputError("A complete declared hero cannot use a bare-hero probe")
        expected = Counter(
            (item["id"], item["level"]) for item in selected["equipment"]
        )
        actual = Counter(
            (item["entity"], item["level"]) for item in _list(parameters, "equipment")
        )
        if actual != expected:
            raise InputError(f"Hero equipment differs from the army: {entity_id}")
    return attackers, bindings, reinforcements


def _bind_commands(scene, attackers, limit, reinforcements=None):
    command_ids = set()
    deployments = {}
    abilities = {}
    direct_delivery = None
    manual_releases = {}
    for actor_id, instance in attackers.items():
        spawn = require(instance, "spawn_seconds")
        if spawn != "controlled":
            deployments[actor_id] = _time(spawn, limit, "attacker spawn time")
    for command in _list(scene, "effects"):
        command_id = identifier(require(command, "id"), "battle command id")
        if command_id in command_ids:
            raise InputError("Battle command IDs must be unique")
        command_ids.add(command_id)
        time = _time(require(command, "time_seconds"), limit, "battle command time")
        kind = require(command, "kind")
        if reinforcements is not None:
            reinforcements.validate_command(command)
        if kind == "deploy":
            if set(command) - {
                "id",
                "kind",
                "time_seconds",
                "targets",
                "positions",
                "source",
            }:
                raise InputError("Deployment commands cannot contain unbound effects")
            targets = _list(command, "targets")
            if not targets or len(targets) != len(set(targets)):
                raise InputError("Deployment targets must be nonempty and unique")
            if set(require(command, "positions")) != set(targets):
                raise InputError(
                    "Deployment positions must cover exactly their targets"
                )
            for actor_id in targets:
                if actor_id not in attackers or actor_id in deployments:
                    raise InputError(
                        "Deployments may spend each declared attacker once only"
                    )
                if attackers[actor_id]["spawn_seconds"] != "controlled":
                    raise InputError(
                        "Deployment commands require controlled reserve actors"
                    )
                position = command["positions"][actor_id]
                number(
                    require(position, "x"), "deployment x", 0, scene["width"] - EPSILON
                )
                number(
                    require(position, "y"), "deployment y", 0, scene["height"] - EPSILON
                )
                deployments[actor_id] = time
        elif kind == "clan_castle_deploy":
            if reinforcements is None or direct_delivery is not None:
                raise InputError(
                    "Direct reinforcement deployment can spend its one declared group once only"
                )
            direct_delivery = time
        elif kind == "siege_release":
            if set(command) != {"id", "kind", "time_seconds", "target"}:
                raise InputError("Manual siege release cannot contain extra effects")
            target = require(command, "target")
            if (
                reinforcements is None
                or target != reinforcements.parameters["delivery"]["carrier_id"]
                or target in manual_releases
            ):
                raise InputError(
                    "Manual release requires its single declared siege carrier"
                )
            manual_releases[target] = time
        elif kind == "hero_ability":
            if set(command) - {"id", "kind", "time_seconds", "hero_id", "source"}:
                raise InputError("Hero commands cannot contain extra effects")
            hero_id = require(command, "hero_id")
            if hero_id not in attackers or "hero_parameters" not in attackers[hero_id]:
                raise InputError("Hero ability must bind to a declared supported hero")
            if hero_id in abilities:
                raise InputError("Each declared hero has one shared ability command")
            abilities[hero_id] = time
        else:
            raise InputError(
                "Full battles allow only bound deployments, hero abilities and reinforcement controls; spells use their catalog cast lists"
            )
    for hero_id, time in abilities.items():
        if hero_id not in deployments or time < deployments[hero_id] - EPSILON:
            raise InputError(
                "Hero abilities cannot precede the hero's declared deployment"
            )
    for actor_id, time in manual_releases.items():
        if actor_id not in deployments or time < deployments[actor_id] - EPSILON:
            raise InputError(
                "Manual siege release cannot precede its declared deployment"
            )
    return command_ids, deployments, abilities


def _bind_spells(army, account, scene, command_ids, limit, catalog):
    allowance = {
        (origin, item["id"], item["level"]): item["count"]
        for origin, inventory in (
            ("army", army["spells"]),
            ("clan_castle", army["clan_castle"]["spells"]),
        )
        for item in inventory
    }
    casts = defaultdict(list)
    paid_casts = []
    for field in sorted(set(SUPPORTED_SPELLS.values())):
        for instance in scene.get(field, []):
            entity_id = require(instance, "entity")
            if SUPPORTED_SPELLS.get(entity_id) != field:
                raise InputError("A spell cast is in the wrong runtime collection")
            cast_id = identifier(require(instance, "id"), "spell cast id")
            if cast_id in command_ids:
                raise InputError("Spell casts and battle commands need distinct IDs")
            command_ids.add(cast_id)
            if require(instance, "town_hall") != account["town_hall"]:
                raise InputError(
                    "Spell cast Town Hall differs from the validated account"
                )
            origin = instance.get("origin", "army")
            paid_casts.append({**instance, "origin": origin})
            if origin == "clan_castle":
                if scene["scope"] not in {
                    SIEGE_SCOPE,
                    PET_SCOPE,
                    ADVANCED_DEFENSE_SCOPE,
                    HERO_ROSTER_SCOPE,
                    TERMINATION_SCOPE,
                    ATTACK_SPELL_SCOPE,
                }:
                    raise InputError("Received spells require the explicit v24 scope")
                parameters = require(instance, "received_spell_parameters")
                if set(parameters) != {
                    "source",
                    "donor_town_hall",
                    "receiver_clan_castle_level",
                    "level_basis",
                }:
                    raise InputError(
                        "Received spells need complete explicit source and receipt parameters"
                    )
                validate_received_entity(
                    entity_id,
                    instance["level"],
                    account["town_hall"],
                    {**parameters, "group_id": f"spell:{cast_id}"},
                    catalog,
                )
                castle = catalog.level(
                    "clan-castle", parameters["receiver_clan_castle_level"]
                )
                if (
                    account["capacities"]["clan_castle_troops"]
                    != castle["troopCapacity"]
                    or account["capacities"]["clan_castle_spells"]
                    != castle["spellCapacity"]
                ):
                    raise InputError(
                        "Received spell castle differs from confirmed account capacities"
                    )
            elif "received_spell_parameters" in instance:
                raise InputError("Owned spells cannot hide a received-level override")
            time = _time(require(instance, "time_seconds"), limit, "spell cast time")
            number(require(instance, "x"), "spell x", 0, scene["width"])
            number(require(instance, "y"), "spell y", 0, scene["height"])
            if (
                entity_id == "healing-spell"
                and require(instance["parameters"], "target_team") != "attack"
            ):
                raise InputError("Owned Healing Spells must target the attacking army")
            key = origin, entity_id, require(instance, "level")
            casts[key].append({"cast_id": cast_id, "time_seconds": time})
            if len(casts[key]) > allowance.get(key, 0):
                raise InputError(
                    "Spell cast identity, level or count exceeds the declared army"
                )
    validate_spell_origin_counts(army, paid_casts)
    bindings = []
    for (origin, entity_id, level), count in sorted(allowance.items()):
        assigned = sorted(
            casts[origin, entity_id, level], key=lambda item: item["cast_id"]
        )
        for index in range(count):
            bindings.append(
                {
                    "entity": entity_id,
                    "origin": origin,
                    "level": level,
                    "ordinal": index + 1,
                    "cast": assigned[index] if index < len(assigned) else None,
                }
            )
    return bindings


def validate_battle_bindings(specification, account, army, layout, catalog):
    """Validate capacities and exact resource/layout coverage before compilation."""
    required_fields = {"id", "source", "time_limit_seconds", "entity_scene"}
    if not required_fields <= set(specification) or set(
        specification
    ) - required_fields - {"battle_modifier_policy", "termination_policy"}:
        raise InputError(
            "Full battle needs id, source, time limit, its complete entity scene "
            "and optionally one battle modifier policy plus the v28 termination policy"
        )
    identifier(specification["id"], "battle id")
    identifier(specification["source"], "battle model evidence")
    limit = number(specification["time_limit_seconds"], "battle time limit", EPSILON)
    _army_shape(army)
    army_validation = validate_army(army, account, catalog)
    layout_validation = validate_layout(layout, catalog)
    _unsupported_obligations(army, layout)
    scene = require(specification, "entity_scene")
    if not isinstance(scene, dict) or set(scene) - SCENE_FIELDS:
        raise InputError(
            "Full-battle entity scene contains unbound or unsupported fields"
        )
    scope_rules = {
        SCOPE: RULES,
        BUFF_SCOPE: BUFF_RULES,
        INDIRECT_SCOPE: INDIRECT_RULES,
        SWEEPER_SCOPE: SWEEPER_RULES,
        DEFENDING_HERO_SCOPE: DEFENDING_HERO_RULES,
        SPELL_TOWER_SCOPE: SPELL_TOWER_RULES,
        BUILDER_SCOPE: BUILDER_RULES,
        GARRISON_SCOPE: GARRISON_RULES,
        FIRESPITTER_SCOPE: FIRESPITTER_RULES,
        TRAP_LIFECYCLE_SCOPE: TRAP_LIFECYCLE_RULES,
        GUARDIAN_SCOPE: GUARDIAN_RULES,
        SIEGE_SCOPE: SIEGE_RULES,
        PET_SCOPE: PET_RULES,
        ADVANCED_DEFENSE_SCOPE: ADVANCED_DEFENSE_RULES,
        HERO_ROSTER_SCOPE: HERO_ROSTER_RULES,
        TERMINATION_SCOPE: TERMINATION_RULES,
        ATTACK_SPELL_SCOPE: ATTACK_SPELL_RULES,
    }
    selected_scope = require(scene, "scope")
    if "termination_policy" in specification and selected_scope not in {
        TERMINATION_SCOPE,
        ATTACK_SPELL_SCOPE,
    }:
        raise InputError("Force-exhaustion policy requires the explicit v28 scope")
    if selected_scope != ATTACK_SPELL_SCOPE and any(
        item["id"] in SUPPORTED_ATTACK_SPELLS
        for inventory in (army["spells"], army["clan_castle"]["spells"])
        for item in inventory
    ):
        raise InputError("Declared attacking spells require the explicit v29 scope")
    if selected_scope not in {
        SIEGE_SCOPE,
        PET_SCOPE,
        ADVANCED_DEFENSE_SCOPE,
        HERO_ROSTER_SCOPE,
        TERMINATION_SCOPE,
        ATTACK_SPELL_SCOPE,
    } and (
        army["siege"] is not None
        or army["clan_castle"]["troops"]
        or army["clan_castle"]["spells"]
    ):
        raise InputError(
            "Declared attacking reinforcements require the explicit v24 adapter scope"
        )
    if selected_scope not in {
        PET_SCOPE,
        ADVANCED_DEFENSE_SCOPE,
        HERO_ROSTER_SCOPE,
        TERMINATION_SCOPE,
        ATTACK_SPELL_SCOPE,
    } and ("pets" in scene or any(hero["pet"] is not None for hero in army["heroes"])):
        raise InputError("Declared hero pets require the explicit v25 adapter scope")
    if selected_scope not in scope_rules or require(
        scene, "model_rules"
    ) != select_duke_isolation_rules(
        scope_rules[selected_scope],
        [instance.get("duke_parameters") for instance in require(scene, "entities")],
    ):
        raise InputError(
            "Full battle must explicitly select the current combined engine rules"
        )
    if selected_scope == SCOPE and any(
        item["id"] in {"rage-spell", "haste-spell"} for item in army["spells"]
    ):
        raise InputError(
            "Declared buff spell adapters require the complete area-buff scope"
        )
    for field in ("width", "height"):
        if require(scene, field) != layout[field]:
            raise InputError("Combat board dimensions must exactly match the layout")
    if require(scene, "duration_seconds") != limit:
        raise InputError("Combat duration must equal the explicit battle time limit")
    if _list(scene, "persistent_hazards"):
        raise InputError(
            "Preloaded hazards are uncharged effects; runtime lifecycle hazards remain supported"
        )
    for field in ("entities", "effects", "traps", "healing_spells"):
        _list(scene, field)
    for field in ("freeze_spells", "buff_spells", "attack_spells"):
        if field in scene:
            _list(scene, field)
    instances = scene["entities"] + scene["traps"]
    _indexed(instances, "id", "battle instance")
    if any(require(item, "team") not in {"attack", "defense"} for item in instances):
        raise InputError("Battle instances must belong to attack or defense")
    statistic_policy = layout.get(
        "statistics_policy",
        layout.get("design_configuration", {}).get("statistics_policy"),
    )
    if statistic_policy is not None and statistic_policy != require(
        scene, "statistics_policy"
    ):
        raise InputError("Layout and battle must use the same exact statistics policy")
    defenders = _bind_defenders(layout, scene, catalog)
    attackers, attacker_bindings, reinforcements = _bind_attackers(
        army, account, scene, catalog
    )
    if selected_scope in {
        PET_SCOPE,
        ADVANCED_DEFENSE_SCOPE,
        HERO_ROSTER_SCOPE,
        TERMINATION_SCOPE,
        ATTACK_SPELL_SCOPE,
    }:
        attacker_bindings.update(
            validate_pet_inventory(
                scene.get("pets", []), attackers, army, account, catalog
            )
        )
    command_ids, deployments, abilities = _bind_commands(
        scene, attackers, limit, reinforcements
    )
    spell_bindings = _bind_spells(army, account, scene, command_ids, limit, catalog)
    if selected_scope in {TERMINATION_SCOPE, ATTACK_SPELL_SCOPE}:
        validate_termination_policy(
            require(specification, "termination_policy"), spell_bindings
        )
        if selected_scope == ATTACK_SPELL_SCOPE:
            validate_spell_classifications(specification["termination_policy"])
    return {
        "contract": CONTRACT,
        "army": army_validation,
        "layout": layout_validation,
        "account_id": stable_id(account),
        "army_id": stable_id(army),
        "layout_id": stable_id(layout),
        "attacker_bindings": attacker_bindings,
        "defender_bindings": defenders,
        "spell_bindings": spell_bindings,
        "planned_deployments": deployments,
        "planned_abilities": abilities,
        "reserved_attacker_ids": sorted(set(attackers) - set(deployments)),
        "complete_declared_coverage": True,
        "inventory_scope": "explicit_declared_inventory_not_maximal_village",
    }


def _apply_modifier_policy(compiled, specification, catalog, mode_rules):
    if "battle_modifier_policy" in specification:
        applied = apply_battle_modifiers(
            compiled["scene"],
            specification["battle_modifier_policy"],
            catalog,
            mode_rules,
        )
        compiled["scene"] = applied["scene"]
        audit = {
            "selection": "role_aware_battle_profile",
            "profile_id": applied["application"]["profile_id"],
            "application": applied["application"],
            "full_game_prediction": False,
        }
    else:
        audit = {
            "selection": "independent_entity_modifiers",
            "profile_id": None,
            "application": None,
            "actor_modifiers": {
                actor["id"]: deepcopy(actor["entity_adapter"]["modifiers"])
                for actor in compiled["scene"]["actors"]
                if "entity_adapter" in actor
            },
            "limitations": [
                "Each actor retains its explicit input modifiers; no battle-wide role profile is asserted",
                "Secondary damage and generated summons retain their independently compiled parameters",
            ],
            "full_game_prediction": False,
        }
    compiled["battle_modifier_audit"] = deepcopy(audit)
    return audit


def compile_full_battle(specification, account, army, layout, catalog, mode_rules=None):
    """Compile every validated object, permitting only compiler-generated summons."""
    validation = validate_battle_bindings(specification, account, army, layout, catalog)
    if "battle_modifier_policy" in specification and mode_rules is None:
        raise InputError("A battle modifier policy requires explicit mode_rules")
    compiled = compile_entity_scene(deepcopy(specification["entity_scene"]), catalog)
    modifier_audit = _apply_modifier_policy(
        compiled, specification, catalog, mode_rules
    )
    expected = set(validation["attacker_bindings"]) | {
        key
        for key, item in validation["defender_bindings"].items()
        if item["collection"] == "actors"
    }
    actual = {actor["id"]: actor for actor in compiled["scene"]["actors"]}
    if not expected <= set(actual):
        raise InputError("Compiler omitted a declared battle actor")
    generated = []
    trap_owners = {
        actor_id: trap["id"]
        for trap in compiled["scene"].get("traps", [])
        if trap["entity"] == "skeleton-trap"
        and validation["defender_bindings"].get(trap["id"], {}).get("entity")
        == "skeleton-trap"
        for actor_id in trap["unit_ids"]
    }
    for actor_id in sorted(set(actual) - expected):
        actor = actual[actor_id]
        summon = actor.get("summon_model")
        trap_summon = actor.get("trap_summon_model")
        attacking_summon = (
            isinstance(summon, dict)
            and summon.get("parent") in validation["attacker_bindings"]
            and actor["team"] == "attack"
        )
        defending_summon = (
            isinstance(trap_summon, dict)
            and actor_id in trap_owners
            and trap_summon.get("trap_id") == trap_owners[actor_id]
            and actor["team"] == "defense"
        )
        if (
            not (attacking_summon or defending_summon)
            or actor["counts_for_destruction"]
            or actor["spawn_seconds"] != "controlled"
        ):
            raise InputError(
                "An extra actor must be generated by a declared supported summon lifecycle"
            )
        generated.append(actor_id)
    return {
        "id": specification["id"],
        "source": specification["source"],
        "status": "COMPLETE_DECLARED_BATTLE_CONDITIONAL_MODEL",
        "time_limit_seconds": specification["time_limit_seconds"],
        "validation": validation,
        "generated_summon_ids": generated,
        "battle_modifier_audit": modifier_audit,
        **(
            {"termination_policy": deepcopy(specification["termination_policy"])}
            if "termination_policy" in specification
            else {}
        ),
        "compiled": compiled,
        "full_game_prediction": False,
        "limitations": [
            "Every declared object is included; an underfilled declared army or inventory is not a maximal modern village",
            "Combat, movement, deployment positions, modifiers and unresolved behavior parameters remain explicit uncalibrated conventions",
            "Deployment positions use declared open-board geometry; live-game deployment exclusion zones are not implemented",
            "The modifier audit identifies one selected role-aware battle profile or independent per-entity modifier inputs",
            "Unsupported pet families, siege variants, equipment and spells are rejected; supported pets, attacking reinforcements and defending garrisons require their complete conditional adapters",
            "The explicit time limit is inclusive; complete destruction ends the reported simulation at its first resolved boundary",
        ],
    }


def compute_battle_outcome(layout, combat_result, time_limit_seconds):
    """Score actual counted defender deaths, without rounding across thresholds."""
    limit = number(time_limit_seconds, "battle time limit", EPSILON)
    buildings = _list(layout, "buildings")
    _indexed(buildings, "instance", "outcome layout instance")
    if any(
        not isinstance(item.get("counts_for_destruction"), bool) for item in buildings
    ):
        raise InputError("Outcome destruction eligibility must be explicit")
    halls = [item for item in buildings if item["id"] == "town-hall"]
    if len(halls) != 1 or halls[0]["counts_for_destruction"] is not True:
        raise InputError("Outcome needs exactly one counted Town Hall")
    counted = [item for item in buildings if item["counts_for_destruction"]]
    actors = require(combat_result, "actors")
    destroyed = []
    times = []
    for building in counted:
        actor_id = _layout_actor_id(building)
        if actor_id not in actors:
            raise InputError(f"Outcome is missing a counted defender: {actor_id}")
        actor = actors[actor_id]
        if actor["team"] != "defense" or actor["counts_for_destruction"] is not True:
            raise InputError(
                "Outcome actor disagrees with declared defender destruction flags"
            )
        hp = number(require(actor, "hp"), "defender remaining HP", 0)
        death = actor.get("death_time")
        if (death is None and hp == 0) or (death is not None and hp > 0):
            raise InputError("Defender HP and death timestamp contradict each other")
        if death is not None:
            number(death, "defender death time", 0)
            if death <= limit + EPSILON:
                destroyed.append(building["instance"])
                times.append(death)
    total = len(counted)
    hall_destroyed = halls[0]["instance"] in destroyed
    all_destroyed = len(destroyed) == total
    stars = int(hall_destroyed) + int(2 * len(destroyed) >= total) + int(all_destroyed)
    destruction = 100 * len(destroyed) / total
    outcome = {
        "stars": stars,
        "destruction": destruction,
        "town_hall_destroyed": hall_destroyed,
        "destroyed_building_count": len(destroyed),
        "counted_building_count": total,
        "destroyed_instance_ids": sorted(destroyed),
        "excluded_instance_ids": sorted(
            item["instance"] for item in buildings if not item["counts_for_destruction"]
        ),
        "time_limit_seconds": limit,
        "completion_time_seconds": max(times) if all_destroyed else None,
        "elapsed_seconds": min(max(times), limit) if all_destroyed else limit,
        "end_reason": (
            "all_counted_buildings_destroyed"
            if all_destroyed
            else "declared_time_limit"
        ),
        "full_game_prediction": False,
    }
    termination = combat_result.get("termination", {}).get("decision")
    if termination is not None:
        elapsed = number(
            require(termination, "time_seconds"), "actual battle end time", 0, limit
        )
        reason = require(termination, "end_reason")
        if reason not in {
            "all_counted_buildings_destroyed",
            "attack_force_exhausted",
            "declared_time_limit",
        }:
            raise InputError("Unsupported actual battle end reason")
        if (reason == "all_counted_buildings_destroyed") != all_destroyed:
            raise InputError("Battle termination disagrees with complete destruction")
        if any(death > elapsed + EPSILON for death in times):
            raise InputError(
                "Counted destruction occurred after the reported battle end"
            )
        if all_destroyed and abs(max(times) - elapsed) > EPSILON:
            raise InputError(
                "Complete destruction must end at its first settled boundary"
            )
        if reason == "declared_time_limit" and abs(elapsed - limit) > EPSILON:
            raise InputError("A time-limit termination must reach the declared limit")
        if reason == "attack_force_exhausted" and require(
            termination, "continuation_reasons"
        ):
            raise InputError("Force exhaustion cannot retain continuation reasons")
        outcome.update(elapsed_seconds=elapsed, end_reason=reason)
    validate_outcome(outcome)
    return outcome


def simulate_full_battle(
    specification, account, army, layout, catalog, mode_rules=None
):
    """Run the complete bound battle and return its state, resource use, and stars."""
    battle = compile_full_battle(
        specification, account, army, layout, catalog, mode_rules=mode_rules
    )
    scene = battle["compiled"]["scene"]
    bindings = battle["validation"]
    counted_ids = [
        _layout_actor_id(item)
        for item in layout["buildings"]
        if item["counts_for_destruction"]
    ]
    if "termination_policy" in specification:
        termination = BattleTermination(
            specification["termination_policy"],
            counted_ids,
            bindings["attacker_bindings"],
            bindings["spell_bindings"],
            battle["time_limit_seconds"],
        )
    else:
        termination = CompletionOnlyTermination(
            counted_ids, battle["time_limit_seconds"]
        )
    combat = simulate_spatial(scene, termination=termination)
    outcome = compute_battle_outcome(layout, combat, battle["time_limit_seconds"])
    battle.update(
        combat=combat,
        outcome=outcome,
        resource_use=battle_resource_use(bindings, combat, outcome["elapsed_seconds"]),
    )
    return battle
