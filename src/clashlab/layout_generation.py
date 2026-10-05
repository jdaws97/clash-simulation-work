"""Bounded variations of our synthetic seeds; never transforms entered/manual bases."""

from copy import deepcopy
from itertools import combinations
from random import Random

from .common import InputError, integer, stable_id
from .geometry import footprint
from .layout_inventory import inspect_inventory, maximum_merges, selected_inventory


ORIGIN = "project_generated_layout_search_v1"


def _tiles(b, catalog):
    w, h = footprint(b, catalog)
    return {
        (x, y) for x in range(b["x"], b["x"] + w) for y in range(b["y"], b["y"] + h)
    }


def select_generated_station(layout, catalog, crafted):
    """Copies a generated seed and makes its selected Station explicit."""
    if layout.get("generation_origin") != ORIGIN:
        raise InputError(
            "Only project-generated seeds may be varied; manual/V3 bases are protected"
        )
    result = deepcopy(layout)
    stations = [b for b in result["buildings"] if b["id"] == "crafting-station"]
    if len(stations) > 1:
        raise InputError("Multiple physical Stations")
    if not stations:
        occupied = set().union(*(_tiles(b, catalog) for b in result["buildings"]))
        station = {
            "instance": "crafting-station-0",
            "id": "crafting-station",
            "level": 1,
            "mode": "normal",
            "counts_for_destruction": True,
        }
        position = next(
            (
                (x, y)
                for y in range(result["height"] - 2)
                for x in range(result["width"] - 2)
                if not _tiles({**station, "x": x, "y": y}, catalog) & occupied
            ),
            None,
        )
        if position is None:
            raise InputError(
                "Generated seed has no 3x3 Station slot; no existing object moved"
            )
        station.update(x=position[0], y=position[1])
        result["buildings"].append(station)
    else:
        station = stations[0]
    station.update(
        level=1,
        mode="normal",
        counts_for_destruction=True,
        settings={"crafted": deepcopy(crafted)},
    )
    selection = {
        "town_hall": result["town_hall"],
        "merges": maximum_merges(catalog, result["town_hall"]),
        "crafted": deepcopy(crafted),
    }
    result["inventory"] = selected_inventory(
        catalog, result["town_hall"], selection["merges"], crafted
    )
    result["inventory_selection"] = selection
    inspect_inventory(result, catalog, selection)
    return result


def change_cost(parent, candidate):
    before = {b["instance"]: b for b in parent["buildings"]}
    after = {b["instance"]: b for b in candidate["buildings"]}
    changes = []
    for key in sorted(before.keys() | after.keys()):
        a, b = before.get(key), after.get(key)
        if a != b:
            changes.append(
                {"instance": key, "before": deepcopy(a), "after": deepcopy(b)}
            )
    moved = [
        r
        for r in changes
        if r["before"]
        and r["after"]
        and (r["before"]["x"], r["before"]["y"]) != (r["after"]["x"], r["after"]["y"])
    ]
    return {
        "changed_objects": len(changes),
        "moved_objects": len(moved),
        "manhattan_anchor_tiles": sum(
            abs(r["before"]["x"] - r["after"]["x"])
            + abs(r["before"]["y"] - r["after"]["y"])
            for r in moved
        ),
        "changes": changes,
        "cost_units": "object edits and tile distance; no invented resource cost",
    }


def variations(layout, catalog, *, seed, limit=2, attempts=12):
    if layout.get("generation_origin") != ORIGIN:
        raise InputError(
            "Only project-generated seeds may be varied; manual/V3 bases are protected"
        )
    integer(seed, "generation seed", 0)
    integer(limit, "variation limit", 1, 8)
    integer(attempts, "variation attempts", 1, 64)
    inspect_inventory(layout, catalog, layout["inventory_selection"])
    eligible = [
        i
        for i, b in enumerate(layout["buildings"])
        if catalog.entity(b["id"])["category"] == "defense"
        and b["id"] not in {"hidden-tesla", "crafting-station"}
    ]
    pairs = [
        (a, b)
        for a, b in combinations(eligible, 2)
        if footprint(layout["buildings"][a], catalog)
        == footprint(layout["buildings"][b], catalog)
        and layout["buildings"][a]["id"] != layout["buildings"][b]["id"]
    ]
    rng = Random(seed)
    rng.shuffle(pairs)
    accepted = []
    for a, b in pairs[:attempts]:
        candidate = deepcopy(layout)
        first, second = candidate["buildings"][a], candidate["buildings"][b]
        first["x"], second["x"] = second["x"], first["x"]
        first["y"], second["y"] = second["y"], first["y"]
        cost = change_cost(layout, candidate)
        candidate["id"] = f"{layout['id']}-swap-{stable_id(cost)}"
        candidate["generation_receipt"] = {
            "parent_sha": stable_id(layout),
            "seed": seed,
            "operation": "equal_footprint_defense_swap",
            "attempt_bound": attempts,
            "change_cost": cost,
            "origin": ORIGIN,
        }
        inspect_inventory(candidate, catalog, candidate["inventory_selection"])
        accepted.append(candidate)
        if len(accepted) == limit:
            break
    return accepted
