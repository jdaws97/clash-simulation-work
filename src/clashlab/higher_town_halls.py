"""Complete conditional TH17/18 layouts and defense scene assembly.

Generated coordinates are synthetic packing fixtures, never creator bases.
Real coordinates enter through build_scene(layout, ...), with the same strict
inventory and binding validation; there is no level-upcast of a TH16 layout.
"""

from collections import Counter
from copy import deepcopy

from .common import InputError, require
from .development_village import _defense, _free_points, _garrison, _hero, _instance
from .development_village import build_scene as benchmark_scene
from .geometry import footprint, validate_layout


SOURCE = "synthetic-higher-th-experimental-policy-not-replay-calibrated"


def maximum_level(catalog, name, town_hall):
    return max(
        row["level"]
        for row in catalog.entity(name)["levels"]
        if not row.get("supercharge")
        and catalog.available(name, row["level"], town_hall)
    )


def full_inventory(catalog, town_hall):
    """Fully merged nonseasonal inventory under this pinned source snapshot."""
    if town_hall not in {17, 18}:
        raise InputError("Higher-TH fixtures support TH17 and TH18 only")
    inventory = {"town-hall": 1}
    for name, entry in catalog.records.items():
        entity = entry["entity"]
        if entity["category"] in {"guardian", "crafted-defense"}:
            continue
        rows = [
            r
            for r in entity.get("availablePerTownHall", [])
            if r["townHallLevel"] == town_hall
        ]
        if rows:
            inventory[name] = rows[0].get("countAfterMerges", rows[0]["count"])
    return {name: count for name, count in inventory.items() if count}


def validate_higher_layout(layout, catalog):
    """Check completeness, merge consumption, explicit seasonal/Guardian choices."""
    town_hall = layout["town_hall"]
    expected = full_inventory(catalog, town_hall)
    counts = Counter(b["id"] for b in layout["buildings"])
    if dict(counts) != expected or layout["inventory"] != expected:
        raise InputError(
            "Higher-TH scenario needs the complete fully merged snapshot inventory"
        )
    for parent, merged, factor, gear in (
        ("archer-tower", "multi-archer-tower", 2, counts["multi-gear-tower"]),
        ("cannon", "ricochet-cannon", 2, counts["multi-gear-tower"]),
        ("wizard-tower", "super-wizard-tower", 2, 0),
    ):
        raw = next(
            r["count"]
            for r in catalog.entity(parent)["availablePerTownHall"]
            if r["townHallLevel"] == town_hall
        )
        if counts[parent] + factor * counts[merged] + gear != raw:
            raise InputError(f"Higher-TH merge conservation failed for {parent}")
    if counts["eagle-artillery"]:
        raise InputError("TH17/18 cannot retain the Eagle merged into the Town Hall")
    configuration = require(layout, "higher_th_configuration")
    if configuration.get("crafting") != (
        "uncrafted_station" if town_hall == 18 else "absent_in_pinned_snapshot"
    ):
        raise InputError(
            "Selected crafted defenses require explicit inventory and behavior adapters"
        )
    identifier = configuration.get("coordinate_provenance")
    if (
        not isinstance(identifier, dict)
        or not identifier.get("source")
        or identifier.get("kind") not in {"synthetic", "entered_coordinates"}
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
        expected_flag = category not in {"trap", "wall"} and name != "hero-banner"
        if building["counts_for_destruction"] is not expected_flag:
            raise InputError("Higher-TH fixture destruction convention differs")
        if name == "hero-banner":
            hero = building["settings"]
            if not catalog.available(hero["hero"], hero["level"], town_hall):
                raise InputError("Defending hero exceeds its Town Hall cap")
            heroes.append(hero["hero"])
        elif name == "crafting-station" and building["mode"] != "passive":
            raise InputError(
                "Crafting Station must explicitly be uncrafted and passive"
            )
    if len(heroes) != 4 or len(set(heroes)) != 4:
        raise InputError("Four distinct defending heroes must be selected")
    geometry = validate_layout(layout, catalog)
    return {
        **geometry,
        "inventory_complete": True,
        "merge_conservation": True,
        "status": "COMPLETE_PINNED_INVENTORY_CONDITIONAL_COORDINATES",
        "crafting": configuration["crafting"],
        "replay_calibrated": False,
    }


def synthetic_layout(catalog, town_hall):
    """Pack every footprint inside 44x44; no claim of strategic base quality."""
    inventory = full_inventory(catalog, town_hall)
    buildings = []
    heroes = ("barbarian-king", "archer-queen", "minion-prince", "royal-champion")
    for name, count in inventory.items():
        entity = catalog.entity(name)
        for ordinal in range(count):
            mode = "normal" if entity.get("modes") else "passive"
            mode = {
                "town-hall": "infernoArtillery" if town_hall == 17 else "guardian",
                "clan-castle": "garrison",
                "x-bow": "airAndGround",
                "inferno-tower": "multiTarget",
                "spell-tower": "rage",
                "revenge-tower": "stage1",
            }.get(name, mode)
            b = {
                "instance": f"{name}-{ordinal}",
                "id": name,
                "level": (
                    None
                    if name == "hero-banner"
                    else maximum_level(catalog, name, town_hall)
                ),
                "mode": mode,
                "counts_for_destruction": entity["category"] not in {"trap", "wall"}
                and name != "hero-banner",
            }
            if name == "skeleton-trap" and town_hall == 18:
                # A legal partially upgraded trap, explicitly disclosed below.
                # Level 5 remains rejected because level-2 summon stats are absent.
                b["level"] = 4
            if name in {"air-sweeper", "firespitter"}:
                b["settings"] = {"facing_degrees": 270}
            elif name == "hero-banner":
                hero = heroes[ordinal]
                b["settings"] = {
                    "hero": hero,
                    "level": maximum_level(catalog, hero, town_hall),
                }
                b.pop("mode")
            elif name == "clan-castle":
                b["settings"] = {
                    "garrison": [
                        {
                            "entity": "dragon",
                            "level": maximum_level(catalog, "dragon", town_hall),
                            "count": 2,
                            "donor_town_hall": town_hall,
                        },
                        {
                            "entity": "archer",
                            "level": maximum_level(catalog, "archer", town_hall),
                            "count": catalog.level("clan-castle", b["level"])[
                                "troopCapacity"
                            ]
                            - 40,
                            "donor_town_hall": town_hall,
                        },
                    ]
                }
            elif name == "skeleton-trap":
                b["settings"] = {"target_layer": "air"}
            elif name == "town-hall" and town_hall == 18:
                b["settings"] = {
                    "guardian": {
                        "actor_id": "guardian",
                        "entity": "longshot",
                        "level": maximum_level(catalog, "longshot", 18),
                    }
                }
            buildings.append(b)
    occupied = set()
    # Reserve an empty cell after each building row for defending unit release.
    buildings.sort(
        key=lambda b: (
            -footprint(b, catalog)[0] * footprint(b, catalog)[1],
            b["instance"],
        )
    )
    for b in buildings:
        w, h = footprint(b, catalog)
        placed = False
        for y in range(44 - h + 1):
            for x in range(44 - w + 1):
                tiles = {(xx, yy) for xx in range(x, x + w) for yy in range(y, y + h)}
                if (
                    any(xx % 11 == 10 or yy % 11 == 10 for xx, yy in tiles)
                    or tiles & occupied
                ):
                    continue
                b.update(x=x, y=y)
                occupied.update(tiles)
                placed = True
                break
            if placed:
                break
        if not placed:
            raise InputError("Complete higher-TH inventory cannot fit synthetic board")
    layout = {
        "id": f"synthetic-complete-th{town_hall}-packing",
        "town_hall": town_hall,
        "width": 44,
        "height": 44,
        "inventory": inventory,
        "buildings": buildings,
        "design_configuration": {
            "direction_convention": "draft_grid_north_zero_degrees_clockwise_not_verified_UI_orientation"
        },
        "higher_th_configuration": {
            "crafting": (
                "uncrafted_station" if town_hall == 18 else "absent_in_pinned_snapshot"
            ),
            "level_selection": "snapshot_maximum_except_TH18_skeleton_traps_level4_due_to_missing_level2_summon_stats",
            "coordinate_provenance": {"kind": "synthetic", "source": SOURCE},
        },
        "destruction_policy": {
            "source": SOURCE,
            "selection": "count_structures_exclude_walls_traps_and_hero_banners",
            "replay_verified": False,
        },
    }
    validate_higher_layout(layout, catalog)
    return layout


def build_scene(layout, catalog, policies, scope, rules, duration=180):
    """Assemble entered or synthetic full layout, with a legal TH16 benchmark."""
    validate_higher_layout(layout, catalog)
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
