"""Static tile-center deployment hypotheses, independent of the combat kernel.

Hidden Teslas/traps never create territory. Square and orthogonal rims are
sensitivity models, not a claim that either matches live corner-tap geometry.
Flood fill describes pockets; deployment does NOT require a path from the edge.
"""

from math import floor

from .common import InputError, integer, number
from .geometry import footprint


def _components(cells):
    remaining = set(cells)
    groups = []
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        pending, group = [seed], {seed}
        while pending:
            x, y = pending.pop()
            for p in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if p in remaining:
                    remaining.remove(p)
                    pending.append(p)
                    group.add(p)
        groups.append(group)
    return groups


def deployment_mask(layout, catalog, policy):
    if set(policy) != {"rim", "hero_banners_block", "source", "state"}:
        raise InputError(
            "Mask needs explicit rim, banner, source and initial-state policy"
        )
    if policy["rim"] not in {"one_tile_square", "one_tile_orthogonal"}:
        raise InputError("Unsupported deployment corner hypothesis")
    if type(policy["hero_banners_block"]) is not bool or not policy["source"]:
        raise InputError("Mask banner/source policy must be explicit")
    if policy["state"] != "initial_hidden_teslas":
        raise InputError("Dynamic destroyed/revealed territory is not implemented")
    width = integer(layout["width"], "mask width", 1, 128)
    height = integer(layout["height"], "mask height", 1, 128)
    board = {(x, y) for x in range(width) for y in range(height)}
    forbidden, walls, excluded = set(), set(), []
    for b in layout["buildings"]:
        category = catalog.entity(b["id"])["category"]
        x, y = integer(b["x"], "mask x", 0), integer(b["y"], "mask y", 0)
        w, h = footprint(b, catalog)
        if x + w > width or y + h > height:
            raise InputError("Mask footprint outside board")
        tiles = {(xx, yy) for xx in range(x, x + w) for yy in range(y, y + h)}
        if category == "wall":
            walls.update(tiles)
        if (
            category in {"trap", "decoration", "obstacle"}
            or b["id"] == "hidden-tesla"
            or (b["id"] == "hero-banner" and not policy["hero_banners_block"])
        ):
            excluded.append(b["instance"])
            continue
        if (
            category
            not in {
                "wall",
                "defense",
                "resource",
                "army",
                "other",
                "research",
                "town-hall",
            }
            and b["id"] != "hero-banner"
        ):
            # Do not silently give a new catalog object a territory rule.
            raise InputError(f"Unclassified territory category: {category}")
        for xx in range(x - 1, x + w + 1):
            for yy in range(y - 1, y + h + 1):
                corner = xx in {x - 1, x + w} and yy in {y - 1, y + h}
                if policy["rim"] == "one_tile_square" or not corner:
                    forbidden.add((xx, yy))
    forbidden &= board
    free = board - forbidden

    def touches_edge(group):
        return any(x in {0, width - 1} or y in {0, height - 1} for x, y in group)

    isolated = [g for g in _components(free) if not touches_edge(g)]
    enclosed = set().union(
        *(g for g in _components(board - walls) if not touches_edge(g))
    )
    return {
        "policy": dict(policy),
        "game_legality_proven": False,
        "live_corner_rule_verified": False,
        "static_initial_state_only": True,
        "free_cells": [list(p) for p in sorted(free)],
        "forbidden_cells": [list(p) for p in sorted(forbidden)],
        "isolated_components": [[list(p) for p in sorted(g)] for g in isolated],
        "wall_enclosed_free_cells": [list(p) for p in sorted(free & enclosed)],
        "edge_connected_free_count": len(free) - sum(map(len, isolated)),
        "excluded_from_territory": sorted(excluded),
        "connectivity_means_drop_permission": False,
    }


def inspect_deployments(layout, catalog, scene, policy):
    """Initial paid deploy commands only; spells, Recall and spawned units differ."""
    mask = deployment_mask(layout, catalog, policy)
    forbidden = {tuple(p) for p in mask["forbidden_cells"]}
    rejected, checked = [], []
    for command in scene.get("effects", []):
        if command.get("kind") != "deploy":
            continue
        for actor, point in command["positions"].items():
            x = number(point["x"], "deployment x", 0)
            y = number(point["y"], "deployment y", 0)
            item = {"command": command["id"], "actor": actor, "point": [x, y]}
            checked.append(item)
            if (
                x >= layout["width"]
                or y >= layout["height"]
                or (floor(x), floor(y)) in forbidden
            ):
                rejected.append(item)
    if rejected:
        raise InputError(f"Initial deploy blocked under selected mask: {rejected[0]}")
    return {
        "checked": checked,
        "policy": policy,
        "game_legality_proven": False,
        "scope": "initial_troop_hero_siege_deploy_commands_only",
    }
