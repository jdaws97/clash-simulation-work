"""Materialize complete TH16 development fixtures from explicit policy data.

The two source designs preserve a maximal declared inventory. This module does
not optimize them, certify game deployment geometry, or select a strongest army.
Missing behavior policies stop construction; no layout object is dropped.
"""

from copy import deepcopy
from math import hypot

from .common import InputError
from .geometry import footprint, validate_layout


def benchmark_army():
    return {
        "troops": [{"id": "dragon", "level": 10, "count": 16}],
        "spells": [
            {"id": "rage-spell", "level": 6, "count": 3},
            {"id": "freeze-spell", "level": 7, "count": 5},
        ],
        "heroes": [],
        "siege": None,
        "clan_castle": {"troops": [], "spells": []},
    }


def termination_policy(army, policies):
    """Bind explicitly classified inventory to the development end hypothesis."""
    policy = deepcopy(policies["battle_termination"])
    policy["spell_inventory"] = []
    classifications = policies["spell_termination_classifications"]
    for origin, spells in (
        ("army", army["spells"]),
        ("clan_castle", army["clan_castle"]["spells"]),
    ):
        for spell in spells:
            if spell["id"] not in classifications:
                raise InputError(
                    f"No development termination classification for {spell['id']}"
                )
            policy["spell_inventory"].append(
                {
                    "origin": origin,
                    "entity": spell["id"],
                    "level": spell["level"],
                    **deepcopy(classifications[spell["id"]]),
                }
            )
    return policy


def counted_layout(blueprint, catalog):
    layout = deepcopy(blueprint)
    for building in layout["buildings"]:
        category = catalog.entity(building["id"])["category"]
        building["counts_for_destruction"] = (
            category not in {"trap", "wall"} and building["id"] != "hero-banner"
        )
        if building["id"] == "clan-castle":
            building["mode"] = "garrison"
            building["settings"] = {
                "garrison": [
                    {"entity": name, "level": level, "count": 2, "donor_town_hall": 16}
                    for name, level in (("dragon", 10), ("wizard", 11), ("archer", 11))
                ]
            }
    layout["design_configuration"].pop("defensive_castle", None)
    layout["destruction_policy"] = {
        "source": "explicit-development-structure-counting-hypothesis",
        "selection": "count_structures_exclude_walls_traps_and_hero_banners",
        "replay_verified": False,
    }
    validate_layout(layout, catalog)
    return layout


def padded_layout(layout, padding=6):
    result = deepcopy(layout)
    result["id"] = f"{layout['id']}-padded-development-board"
    result["width"] += 2 * padding
    result["height"] += 2 * padding
    for building in result["buildings"]:
        building["x"] += padding
        building["y"] += padding
    result["simulation_coordinate_transform"] = {
        "source": "explicit-unverified-deployment-margin-hypothesis",
        "translation_tiles": [padding, padding],
        "original_buildable_rectangle": [
            padding,
            padding,
            layout["width"],
            layout["height"],
        ],
        "deployment_zone_verified": False,
    }
    return result


def _instance(identifier, entity, level, team, x, y, policies):
    source = policies["source"]
    return {
        "id": identifier,
        "entity": entity,
        "level": level,
        "town_hall": 16,
        "mode": "normal",
        "statistics_mode": "normal",
        "supercharge": False,
        "team": team,
        "counts_for_destruction": team == "defense",
        "x": x,
        "y": y,
        "spawn_seconds": 0,
        "first_attack_seconds": 0,
        "modifiers": {
            "source": source,
            "hitpoints_multiplier": 1,
            "damage_multiplier": 1,
            "maximum_hp_damage_multiplier": 1,
            "attack_interval_multiplier": 1,
            "range_multiplier": 1,
            "movement_speed_multiplier": 1,
        },
        "attack_parameters": {"projectile": deepcopy(policies["ordinary_projectile"])},
    }


def _free_points(layout, catalog, origin, count):
    occupied = set()
    for building in layout["buildings"]:
        if (
            catalog.entity(building["id"])["category"] == "trap"
            or building["id"] == "hero-banner"
        ):
            continue
        width, height = footprint(building, catalog)
        occupied.update(
            (x, y)
            for x in range(building["x"], building["x"] + width)
            for y in range(building["y"], building["y"] + height)
        )
    points = [
        (x + 0.5, y + 0.5)
        for y in range(layout["height"])
        for x in range(layout["width"])
        if (x, y) not in occupied
    ]
    points.sort(
        key=lambda point: (hypot(point[0] - origin[0], point[1] - origin[1]), point)
    )
    if len(points) < count:
        raise InputError("Insufficient explicit exterior points for castle release")
    return points[:count]


def _garrison(building, layout, catalog, policies):
    castle = _instance(
        building["instance"],
        "clan-castle",
        building["level"],
        "defense",
        building["x"],
        building["y"],
        policies,
    )
    contents = building["settings"]["garrison"]
    points = iter(
        _free_points(
            layout,
            catalog,
            (building["x"] + 1.5, building["y"] + 1.5),
            sum(item["count"] for item in contents),
        )
    )
    members = []
    for item in contents:
        for ordinal in range(item["count"]):
            x, y = next(points)
            member = _instance(
                f"{building['instance']}:{item['entity']}:{ordinal}",
                item["entity"],
                item["level"],
                "defense",
                x,
                y,
                policies,
            )
            member.update(spawn_seconds="controlled", counts_for_destruction=False)
            member["garrison_member_parameters"] = {
                "source": policies["source"],
                "castle_id": castle["id"],
                "donor_town_hall": item["donor_town_hall"],
                "level_basis": "snapshot_receiver_lab_cap_with_unlock_floor",
            }
            if item["entity"] != "dragon":
                member["wall_parameters"] = {
                    "kind": "avoid",
                    "source": policies["source"],
                }
            if item["entity"] in {"wizard", "dragon"}:
                member["attack_parameters"].update(
                    radius=1, splash_layer_policy="primary_target_layer_only"
                )
                member["attack_parameters"]["projectile"][
                    "inactive_primary_policy"
                ] = "fizzle"
            members.append(member)
    parameters = deepcopy(policies["garrison"])
    parameters["member_ids"] = [member["id"] for member in members]
    parameters["release"]["positions"] = {
        member["id"]: {"x": member["x"], "y": member["y"]} for member in members
    }
    castle.update(
        mode="garrison",
        statistics_mode="none",
        attack_parameters={},
        garrison_parameters=parameters,
    )
    return [castle, *members]


def _hero(building, policies):
    settings = building["settings"]
    actor = _instance(
        f"{building['instance']}:defender",
        settings["hero"],
        settings["level"],
        "defense",
        building["x"] + 1,
        building["y"] + 1,
        policies,
    )
    actor["counts_for_destruction"] = False
    actor["mode"] = "air" if settings["hero"] == "minion-prince" else "ground"
    if actor["mode"] == "ground":
        actor["wall_parameters"] = {"kind": "avoid", "source": policies["source"]}
    parameters = deepcopy(policies["defending_hero"])
    parameters["banner"].update(
        id=building["instance"], x=building["x"], y=building["y"]
    )
    actor["defending_hero_parameters"] = parameters
    return actor


def _defense(building, policies):
    name = building["id"]
    actor = _instance(
        building["instance"],
        name,
        building["level"],
        "defense",
        building["x"],
        building["y"],
        policies,
    )
    actor["mode"] = building["mode"]
    actor["statistics_mode"] = "normal" if name == "x-bow" else building["mode"]
    groups = {
        "scattershot": "scattershot",
        "bomb-tower": "bomb_tower",
        "mortar": "mortar",
        "eagle-artillery": "eagle_artillery",
    }
    if name in groups:
        actor.update(deepcopy(policies[groups[name]]))
    elif name == "wizard-tower":
        actor["attack_parameters"] = deepcopy(policies["area_attack"])
    elif name == "inferno-tower" and actor["mode"] == "normal":
        actor.update(deepcopy(policies["single_inferno"]))
    elif name in {"multi-archer-tower", "inferno-tower"}:
        actor["attack_parameters"]["allocation"] = "distinct_targets_only"
        if name == "inferno-tower":
            actor["beam_parameters"] = deepcopy(policies["multi_inferno"])
    elif name == "ricochet-cannon":
        actor["attack_parameters"].update(
            jump_metric="footprint_distance",
            jump_delay_seconds=0,
            tie_break="distance_then_instance_id",
            allow_protected_links=True,
        )
    elif name == "hidden-tesla":
        actor["tesla_parameters"] = deepcopy(policies["hidden_tesla"])
    elif name == "builders-hut":
        actor["builder_parameters"] = deepcopy(policies["builder_hut"])
    elif name == "air-sweeper":
        parameters = deepcopy(policies["air_sweeper"])
        parameters["orientation_degrees"] = (
            building["settings"]["facing_degrees"] - 90
        ) % 360
        actor.update(attack_parameters={}, sweeper_parameters=parameters)
    elif name == "spell-tower":
        actor.update(
            statistics_mode="mode",
            attack_parameters={},
            spell_tower_parameters=deepcopy(policies["spell_tower"][actor["mode"]]),
        )
    return actor


def build_scene(layout, catalog, policies, scope, rules, duration=180):
    missing = {"garrison", "skeleton_trap", "tornado_trap"} - set(policies)
    if missing:
        raise InputError(
            "Whole-village policy set is incomplete: " + ", ".join(sorted(missing))
        )
    source = policies["source"]
    entities = []
    traps = []
    for building in layout["buildings"]:
        name = building["id"]
        category = catalog.entity(name)["category"]
        if category == "trap":
            policy = "spring_trap" if name == "spring-trap" else "damage_trap"
            if name in {"skeleton-trap", "tornado-trap"}:
                policy = name.replace("-", "_")
            parameters = deepcopy(policies[policy])
            traps.append(
                {
                    "id": building["instance"],
                    "entity": name,
                    "level": building["level"],
                    "town_hall": 16,
                    "team": "defense",
                    "x": building["x"],
                    "y": building["y"],
                    "parameters": parameters,
                }
            )
            if name == "skeleton-trap":
                traps[-1]["mode"] = building["settings"]["target_layer"]
        elif name == "hero-banner":
            entities.append(_hero(building, policies))
        elif name == "clan-castle":
            entities.extend(_garrison(building, layout, catalog, policies))
        elif name == "town-hall":
            hall = _instance(
                building["instance"],
                name,
                16,
                "defense",
                building["x"],
                building["y"],
                policies,
            )
            hall.update(
                mode="gigaInferno",
                statistics_mode="weapon",
                **deepcopy(policies["town_hall_16"]),
            )
            entities.append(hall)
        elif category == "defense":
            entities.append(_defense(building, policies))
        else:
            actor = _instance(
                building["instance"],
                name,
                building["level"],
                "defense",
                building["x"],
                building["y"],
                policies,
            )
            actor.update(
                mode="passive",
                statistics_mode="none",
                attack_parameters={},
                inactive_attack_interval_seconds=1,
                counts_for_destruction=building["counts_for_destruction"],
            )
            entities.append(actor)
    commands = []
    attackers = []
    for ordinal in range(16):
        actor = _instance(
            f"dragon-{ordinal}",
            "dragon",
            10,
            "attack",
            1.5,
            9.5 + ordinal * 2.5,
            policies,
        )
        actor["spawn_seconds"] = "controlled"
        actor["attack_parameters"]["radius"] = 1
        attackers.append(actor)
        commands.append(
            {
                "id": f"deploy-{ordinal}",
                "kind": "deploy",
                "time_seconds": ordinal * 0.2,
                "targets": [actor["id"]],
                "positions": {actor["id"]: {"x": actor["x"], "y": actor["y"]}},
            }
        )
    rage = []
    for index, (time, x, y) in enumerate(((12, 16, 18), (22, 22, 30), (38, 32, 26))):
        rage.append(
            {
                "id": f"rage-{index}",
                "entity": "rage-spell",
                "level": 6,
                "town_hall": 16,
                "time_seconds": time,
                "x": x,
                "y": y,
                "parameters": deepcopy(policies["rage_spell"]),
            }
        )
    freeze = []
    for index, (time, x, y) in enumerate(
        ((15, 19, 20), (25, 26, 28), (35, 30, 26), (45, 34, 22), (60, 35, 35))
    ):
        freeze.append(
            {
                "id": f"freeze-{index}",
                "entity": "freeze-spell",
                "level": 7,
                "town_hall": 16,
                "time_seconds": time,
                "x": x,
                "y": y,
                "parameters": {
                    "source": source,
                    "duration_multiplier": 1,
                    "radius_multiplier": 1,
                    "caster_team": "attack",
                },
            }
        )
    for actor in entities:
        if actor["entity"] == "eagle-artillery":
            activation = actor["indirect_parameters"]["activation"]
            activation["actor_weights"] = {troop["id"]: 20 for troop in attackers}
            activation["command_weights"] = {cast["id"]: 10 for cast in rage} | {
                cast["id"]: 5 for cast in freeze
            }
    return {
        "id": f"whole-village-development-{layout['id']}",
        "scope": scope,
        "model_rules": deepcopy(rules),
        "statistics_policy": {
            "kind": "conditional_pinned_snapshot",
            "snapshot_commit": catalog.snapshot["snapshotCommit"],
        },
        "unit_conventions": {
            "movement_units_per_tile": 8,
            "catalog_attack_speed_unit": "seconds_per_hit",
            "source": source,
        },
        "unsupported_mechanics": [],
        "width": layout["width"],
        "height": layout["height"],
        "duration_seconds": duration,
        "maximum_step_seconds": 0.25,
        "recording_interval_seconds": 1,
        "entities": [*attackers, *entities],
        "traps": traps,
        "effects": commands,
        "healing_stacking": {"source": source, "groups": {}},
        "healing_spells": [],
        "buff_spells": rage,
        "freeze_spells": freeze,
        "persistent_hazards": [],
        "target_scoring": {
            "selection": "arrival_time_then_footprint_distance",
            "source": source,
        },
        "defending_unit_responses": {
            "source": source,
            "actors": {
                actor["id"]: {
                    "primary": "same_tier_as_buildings",
                    "collateral": "allow",
                }
                for actor in attackers
            },
        },
    }
