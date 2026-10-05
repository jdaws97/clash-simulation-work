"""Explicit TH16-18 inventory selections; no live account or season inference."""

from collections import Counter

from .common import InputError, integer
from .crafted_selection import selected_modules
from .geometry import footprint, validate_layout


MERGES = {
    "ricochet-cannon": {"cannon": 2},
    "multi-archer-tower": {"archer-tower": 2},
    "multi-gear-tower": {"cannon": 1, "archer-tower": 1},
    "super-wizard-tower": {"wizard-tower": 2},
}


def selected_inventory(catalog, town_hall, merges, crafted):
    """Full snapshot counts with explicitly chosen merges and one active Station.

    `crafted` is the shared selection contract, not a weapon-shaped extra building.
    None is allowed only for a declared historical nonseasonal comparison.
    """
    integer(town_hall, "layout Town Hall", 16, 18)
    if set(merges) != set(MERGES):
        raise InputError("Declare all four merge counts, including zeros")
    raw = {"town-hall": 1}
    for name, record in catalog.records.items():
        entity = record["entity"]
        if entity["category"] in {"guardian", "crafted-defense"}:
            continue
        rows = [
            r
            for r in entity.get("availablePerTownHall", [])
            if r["townHallLevel"] == town_hall
        ]
        if rows:
            raw[name] = rows[0]["count"]
    counts = dict(raw)
    for merged, consumed in MERGES.items():
        count = integer(merges[merged], "selected merge count", 0, raw.get(merged, 0))
        counts[merged] = count
        for parent, factor in consumed.items():
            counts[parent] -= factor * count
            if counts[parent] < 0:
                raise InputError(f"Merge consumption exceeds {parent} inventory")
    if crafted is not None:
        selected_modules(crafted, town_hall, catalog)
        counts["crafting-station"] = 1
    return {name: count for name, count in counts.items() if count}


def maximum_merges(catalog, town_hall):
    return {
        name: next(
            (
                r["count"]
                for r in catalog.entity(name)["availablePerTownHall"]
                if r["townHallLevel"] == town_hall
            ),
            0,
        )
        for name in MERGES
    }


def inspect_inventory(layout, catalog, selection):
    """Require full declared inventory; distinguish conditional fit from live legality."""
    if selection["town_hall"] != layout["town_hall"]:
        raise InputError("Inventory selection and layout Town Hall differ")
    expected = selected_inventory(
        catalog, layout["town_hall"], selection["merges"], selection["crafted"]
    )
    if dict(Counter(b["id"] for b in layout["buildings"])) != expected:
        raise InputError("Layout differs from complete selected inventory/merge counts")
    if layout["inventory"] != expected:
        raise InputError("Declared inventory differs from selection")
    for b in layout["buildings"]:
        size = footprint(b, catalog)
        if "footprint" in b and list(b["footprint"]) != list(size):
            raise InputError("Declared footprint differs from catalog")
        for key, value in zip(("width", "height"), size):
            if key in b and b[key] != value:
                raise InputError("Declared dimensions differ from catalog")
    stations = [b for b in layout["buildings"] if b["id"] == "crafting-station"]
    if selection["crafted"] is not None:
        if (
            len(stations) != 1
            or stations[0].get("settings", {}).get("crafted") != selection["crafted"]
        ):
            raise InputError(
                "Exactly one Station must carry the exact selected modules"
            )
    elif any(b.get("settings", {}).get("crafted") is not None for b in stations):
        raise InputError("Unexpected active crafted selection")
    result = validate_layout(layout, catalog)
    return {
        **result,
        "inventory_complete_under_selection": True,
        "merge_conservation": True,
        "game_legality_proven": False,
        "current_season_verified": False,
        "selection": selection,
    }
