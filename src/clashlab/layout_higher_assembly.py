"""Selected-inventory assembly using existing shared defense helpers/policies.

The legacy builder requires maximum merges. This layout-owned bridge preserves
its assembly conventions while accepting validated explicit merge selections.
No combat behavior or mixed-army Giga Bomb support is added here.
"""

from copy import deepcopy

from .common import InputError, require
from .development_village import _defense, _free_points, _garrison, _hero, _instance
from .development_village import build_scene as benchmark_scene
from .higher_town_halls import SOURCE
from .layout_inventory import inspect_inventory


def validate_selected_higher(layout, catalog):
    if layout["town_hall"] not in {17, 18}:
        raise InputError("Selected higher-TH assembly requires TH17 or TH18")
    inspect_inventory(layout, catalog, layout["inventory_selection"])
    provenance = require(
        require(layout, "higher_th_configuration"), "coordinate_provenance"
    )
    if (
        not isinstance(provenance, dict)
        or not provenance.get("source")
        or provenance.get("kind") not in {"synthetic", "entered_coordinates"}
    ):
        raise InputError("Coordinates need explicit synthetic or entered provenance")
    heroes = []
    for building in layout["buildings"]:
        if building.get("supercharge", False) is not False:
            raise InputError(
                "Higher-TH assembly requires explicit non-supercharged buildings"
            )
        name = building["id"]
        category = catalog.entity(name)["category"]
        expected = category not in {"trap", "wall"} and name != "hero-banner"
        if building["counts_for_destruction"] is not expected:
            raise InputError("Higher-TH fixture destruction convention differs")
        if name == "hero-banner":
            hero = building["settings"]
            if not catalog.available(hero["hero"], hero["level"], layout["town_hall"]):
                raise InputError("Defending hero exceeds its Town Hall cap")
            heroes.append(hero["hero"])
    if len(heroes) != 4 or len(set(heroes)) != 4:
        raise InputError("Four distinct defending heroes must be selected")


def build_selected_higher_scene(layout, catalog, policies, scope, rules, duration=180):
    validate_selected_higher(layout, catalog)
    town_hall = layout["town_hall"]
    scene = benchmark_scene(
        {**layout, "buildings": []}, catalog, policies, scope, rules, duration
    )
    entities, traps = [], []
    extra = require(policies, "higher_town_halls")
    for b in layout["buildings"]:
        name, category = b["id"], catalog.entity(b["id"])["category"]
        if category == "trap":
            key = (
                name.replace("-", "_")
                if name in {"skeleton-trap", "tornado-trap", "spring-trap", "giga-bomb"}
                else "damage_trap"
            )
            parameters = deepcopy(extra[key] if key == "giga_bomb" else policies[key])
            if key == "giga_bomb":
                # Exact legacy benchmark roster. prepare_case still rejects this
                # for mixed armies; the integration owner must bind that roster.
                parameters["unit_responses"] = {
                    actor["id"]: {
                        "trigger_weight": 20,
                        "damage_multiplier": 1,
                        "push_multiplier": 1,
                    }
                    for actor in scene["entities"]
                }
            trap = {
                "id": b["instance"],
                "entity": name,
                "level": b["level"],
                "town_hall": town_hall,
                "team": "defense",
                "x": b["x"],
                "y": b["y"],
                "parameters": parameters,
            }
            if name == "skeleton-trap":
                trap["mode"] = b["settings"]["target_layer"]
            traps.append(trap)
            continue
        if name == "hero-banner":
            actor = _hero(b, policies)
        elif name == "clan-castle":
            group = _garrison(b, layout, catalog, policies)
            for member in group:
                member["town_hall"] = town_hall
            entities.extend(group)
            continue
        elif name in {
            "town-hall",
            "firespitter",
            "multi-gear-tower",
            "super-wizard-tower",
            "revenge-tower",
        }:
            actor = _instance(
                b["instance"], name, b["level"], "defense", b["x"], b["y"], policies
            )
            key = (
                f"town_hall_{town_hall}"
                if name == "town-hall"
                else name.replace("-", "_")
            )
            actor.update(deepcopy(extra[key]))
            actor["mode"] = b["mode"]
            if name == "firespitter":
                actor["firespitter_parameters"]["orientation_degrees"] = (
                    b["settings"]["facing_degrees"] - 90
                ) % 360
            if name == "town-hall" and town_hall == 18:
                selected = b["settings"]["guardian"]
                if selected["entity"] != "longshot":
                    raise InputError(
                        "This scenario policy selects Longshot; other Guardians need their explicit policy"
                    )
                actor["guardian_binding"] = {"source": SOURCE, **selected}
                point = _free_points(layout, catalog, (b["x"] + 2, b["y"] + 2), 1)[0]
                guardian = _instance(
                    selected["actor_id"],
                    selected["entity"],
                    selected["level"],
                    "defense",
                    *point,
                    policies,
                )
                guardian.update(deepcopy(extra["longshot"]))
                guardian["guardian_parameters"].update(
                    hall_id=b["instance"], home={"x": point[0], "y": point[1]}
                )
                guardian["town_hall"] = town_hall
                entities.append(guardian)
        elif category == "defense" and name != "crafting-station":
            actor = _defense(b, policies)
        else:
            actor = _instance(
                b["instance"], name, b["level"], "defense", b["x"], b["y"], policies
            )
            actor.update(
                mode="passive",
                statistics_mode="none",
                attack_parameters={},
                inactive_attack_interval_seconds=1,
            )
        actor["town_hall"] = town_hall
        actor["counts_for_destruction"] = b["counts_for_destruction"]
        entities.append(actor)
    scene["entities"].extend(entities)
    scene["traps"] = traps
    return scene
