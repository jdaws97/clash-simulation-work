"""Explicit full-army integration fixtures, without optimization claims.

These candidates deliberately exercise owned equipment, paired pets, siege
delivery and separate donor inventory. Numerical behavior choices are supplied
by a saved policy file and remain hypotheses until compared with game evidence.
"""

from copy import deepcopy

from .adapters import compile_actor
from .common import InputError
from .development_village import _instance, build_scene
from .heroes import compile_mirror_clones


HERO_PETS = {
    "archer-queen": "unicorn",
    "grand-warden": "electro-owl",
    "royal-champion": "spirit-fox",
    "dragon-duke": "phoenix",
}
TROOP_COUNTS = {
    "air": {"dragon": 16},
    "ground": {"root-rider": 8, "ice-golem": 4, "valkyrie": 10, "archer": 20},
}


def benchmark_army(account, policies, family):
    if family not in TROOP_COUNTS:
        raise InputError("Full-army benchmark family must be air or ground")
    levels = account["levels"]
    donations = account["donation_levels"]
    heroes = []
    for name, pet in HERO_PETS.items():
        heroes.append(
            {
                "id": name,
                "level": levels[name],
                "mode": (
                    "air"
                    if name == "dragon-duke"
                    or (name == "grand-warden" and family == "air")
                    else "ground"
                ),
                "equipment": [
                    {"id": item["entity"], "level": item["level"]}
                    for item in policies["heroes"][name]["equipment"]
                ],
                "pet": {"id": pet, "level": levels[pet]},
            }
        )
    siege = "stone-slammer" if family == "air" else "wall-wrecker"
    return {
        "troops": [
            {"id": name, "level": levels[name], "count": count}
            for name, count in TROOP_COUNTS[family].items()
        ],
        "spells": [
            {"id": "rage-spell", "level": levels["rage-spell"], "count": 3},
            {"id": "freeze-spell", "level": levels["freeze-spell"], "count": 5},
        ],
        "heroes": heroes,
        "siege": {"id": siege, "level": levels[siege], "origin": "own"},
        "clan_castle": {
            "troops": [
                {"id": name, "level": donations[name], "count": 2}
                for name in ("dragon", "wizard", "archer")
            ],
            "spells": [
                {"id": name, "level": donations[name], "count": 1}
                for name in ("rage-spell", "freeze-spell")
            ],
        },
    }


def _troop(actor_id, item, x, y, catalog, base_policies, policies):
    actor = _instance(
        actor_id, item["id"], item["level"], "attack", x, y, base_policies
    )
    actor["spawn_seconds"] = "controlled"
    name = item["id"]
    source = policies["source"]
    if name in {"dragon", "wizard", "valkyrie"}:
        actor["attack_parameters"]["radius"] = 1.5 if name == "valkyrie" else 1
    if name == "wizard":
        actor["wizard_parameters"] = {
            "source": source,
            "splash_layer_policy": "all_declared_target_layers",
        }
        actor["attack_parameters"]["projectile"]["inactive_primary_policy"] = "fizzle"
    if name != "dragon":
        wall = deepcopy(policies["root_rider_walls"])
        if name != "root-rider":
            wall.update(
                source=source,
                cooldown="shared_with_main_weapon",
                range=catalog.entity(name)["range"],
            )
        actor["wall_parameters"] = wall
    if name == "ice-golem":
        actor["ice_parameters"] = deepcopy(policies["ice_golem"])
    if name == "valkyrie":
        actor["valkyrie_parameters"] = deepcopy(policies["valkyrie"])
    return actor


def _hero(item, x, y, base_policies, policies):
    name = item["id"]
    actor = _instance(name, name, item["level"], "attack", x, y, base_policies)
    actor.update(
        mode=item["mode"],
        spawn_seconds="controlled",
        hero_parameters=deepcopy(policies["heroes"][name]),
    )
    if item["mode"] == "ground":
        actor["wall_parameters"] = {
            "kind": "avoid" if name == "archer-queen" else "jump_enemy_walls",
            "source": policies["source"],
        }
    if name == "dragon-duke":
        actor["duke_parameters"] = deepcopy(policies["duke_intrinsic"])
    return actor


def _deploy(actor, time):
    return {
        "id": f"deploy-{actor['id']}",
        "kind": "deploy",
        "time_seconds": time,
        "targets": [actor["id"]],
        "positions": {actor["id"]: {"x": actor["x"], "y": actor["y"]}},
    }


def _received_parameters(account, source):
    return {
        "source": source,
        "donor_town_hall": 18,
        "receiver_clan_castle_level": account["planning_evidence"][
            "recipient_clan_castle_level"
        ],
        "level_basis": "snapshot_receiver_lab_cap_with_unlock_floor",
    }


def _replace_spell_inventory(scene, army, account, policies, duration):
    owned_levels = {item["id"]: item["level"] for item in army["spells"]}
    for collection in ("buff_spells", "freeze_spells"):
        for cast in scene[collection]:
            cast["level"] = owned_levels[cast["entity"]]
        donated = deepcopy(scene[collection][0])
        name = donated["entity"]
        donated.update(
            id=f"donated-{name}",
            origin="clan_castle",
            level=account["donation_levels"][name],
            time_seconds=30 if collection == "buff_spells" else 32,
            x=27,
            y=27,
            received_spell_parameters=_received_parameters(account, policies["source"]),
        )
        scene[collection].append(donated)
        scene[collection] = [
            cast for cast in scene[collection] if cast["time_seconds"] <= duration
        ]
    for cast in scene["buff_spells"]:
        for category in ("hero", "pet"):
            cast["parameters"]["class_scaling"][category] = {
                "damage_bonus_multiplier": 0.5,
                "movement_bonus_multiplier": 0.5,
                "healing_bonus_multiplier": 0.5,
            }


def _bind_responses(scene, attackers, pets, catalog):
    weights = {}
    for actor in attackers:
        category = catalog.entity(actor["entity"])["category"]
        if category == "hero":
            weights[actor["id"]] = 25
            compiled = compile_actor(
                actor,
                catalog,
                8,
                allow_walls=True,
                allow_heroes=True,
                allow_pets=True,
                allow_hero_extensions=True,
            )
            for clone in compile_mirror_clones(compiled):
                weights[clone["id"]] = 0
        elif category == "siege-machine":
            weights[actor["id"]] = 1
        else:
            weights[actor["id"]] = catalog.entity(actor["entity"])["housingSpace"]
    weights.update({pet["id"]: 0 for pet in pets})
    source = scene["defending_unit_responses"]["source"]
    scene["defending_unit_responses"] = {
        "source": source,
        "actors": {
            actor_id: {"primary": "same_tier_as_buildings", "collateral": "allow"}
            for actor_id in weights
        },
    }
    for pet in pets:
        if pet["entity"] == "unicorn":
            scene["defending_unit_responses"]["actors"][pet["id"]] = {
                "primary": "ignore",
                "collateral": "ignore",
            }
    for actor in attackers:
        if "siege_parameters" in actor:
            scene["defending_unit_responses"]["actors"][actor["id"]][
                "primary"
            ] = "ignore"
    command_weights = {
        command["id"]: 0 for command in scene["effects"] if command["kind"] != "deploy"
    }
    for collection in ("buff_spells", "freeze_spells"):
        command_weights.update(
            {
                cast["id"]: catalog.entity(cast["entity"])["housingSpace"] * 5
                for cast in scene[collection]
            }
        )
    for actor in scene["entities"]:
        if actor["entity"] == "eagle-artillery":
            actor["indirect_parameters"]["activation"].update(
                actor_weights=deepcopy(weights),
                command_weights=deepcopy(command_weights),
            )


def build_army_scene(
    layout, catalog, base_policies, policies, account, army, scope, rules, duration=180
):
    scene = build_scene(layout, catalog, base_policies, scope, rules, duration)
    defenders = [actor for actor in scene["entities"] if actor["team"] == "defense"]
    attackers = []
    commands = []
    ordinal = 0
    for item in army["troops"]:
        for number in range(item["count"]):
            y = 9.5 + (ordinal % 16) * 2.5
            actor = _troop(
                f"army-{item['id']}-{number}",
                item,
                1.5,
                y,
                catalog,
                base_policies,
                policies,
            )
            attackers.append(actor)
            commands.append(_deploy(actor, ordinal * 0.15))
            ordinal += 1
    pets = []
    for index, item in enumerate(army["heroes"]):
        actor = _hero(item, 2.5, 13.5 + index * 9, base_policies, policies)
        attackers.append(actor)
        commands.append(_deploy(actor, 4 + index * 0.3))
        if item["id"] != "dragon-duke":
            commands.append(
                {
                    "id": f"ability-{item['id']}",
                    "kind": "hero_ability",
                    "hero_id": actor["id"],
                    "time_seconds": 10 + index * 2,
                }
            )
        pet = item["pet"]
        pets.append(
            {
                "id": f"pet-{pet['id']}",
                "entity": pet["id"],
                "level": pet["level"],
                "town_hall": 16,
                "hero_id": actor["id"],
                "parameters": deepcopy(policies["pets"][pet["id"]]),
            }
        )
    carrier = army["siege"]
    siege = _instance(
        "siege", carrier["id"], carrier["level"], "attack", 1.5, 27.5, base_policies
    )
    siege.update(
        spawn_seconds="controlled",
        attack_parameters={},
        siege_parameters=deepcopy(policies["sieges"][carrier["id"]]),
    )
    if carrier["id"] == "wall-wrecker":
        siege["siege_parameters"]["targeting"]["hall_actor_id"] = next(
            actor["id"] for actor in defenders if actor["entity"] == "town-hall"
        )
    attackers.append(siege)
    commands.append(_deploy(siege, 5))
    payload = []
    for item in army["clan_castle"]["troops"]:
        for number in range(item["count"]):
            actor = _troop(
                f"cc-{item['id']}-{number}",
                item,
                1.5,
                27.5,
                catalog,
                base_policies,
                policies,
            )
            actor["payload_member_parameters"] = {
                **_received_parameters(account, policies["source"]),
                "group_id": "reinforcements",
            }
            payload.append(actor)
    attackers.extend(payload)
    group = deepcopy(policies["reinforcements"])
    group["member_ids"] = [actor["id"] for actor in payload]
    group["release"]["offsets"] = {actor["id"]: {"x": 0, "y": 0} for actor in payload}
    group["deployment_policy"]["regions"][0]["bottom"] = layout["height"]
    group["receiver_clan_castle_level"] = account["planning_evidence"][
        "recipient_clan_castle_level"
    ]
    scene.update(
        entities=[*attackers, *defenders],
        effects=[
            command for command in commands if command["time_seconds"] <= duration
        ],
        pets=pets,
        attacking_reinforcements=group,
    )
    _replace_spell_inventory(scene, army, account, policies, duration)
    _bind_responses(scene, attackers, pets, catalog)
    return scene
