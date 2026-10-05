"""Enumerate declared wall architectures without fixing a compartment grid.

Design proposals supply topology and placement choices explicitly. Geometry
success does not imply defensive strength; rejected candidates remain visible.
"""

from copy import deepcopy

from .blueprints import generate_blueprint, inspect_blueprint
from .common import InputError, identifier, integer, require, stable_id


def _point(value, label, width, height):
    if not isinstance(value, list) or len(value) != 2:
        raise InputError(f"{label} needs two integer coordinates")
    return (
        integer(value[0], f"{label} x", 0, width - 1),
        integer(value[1], f"{label} y", 0, height - 1),
    )


def architecture_wall_tiles(components, board):
    """Rasterize explicit orthogonal outlines and Manhattan-distance bands."""
    width = integer(require(board, "width"), "architecture board width", 1)
    height = integer(require(board, "height"), "architecture board height", 1)
    if not isinstance(components, list) or not components:
        raise InputError("An architecture needs explicit wall components")
    tiles = set()
    for component in components:
        kind = require(component, "kind")
        identifier(require(component, "source"), "wall component evidence")
        if kind == "orthogonal_polyline":
            if set(component) != {"kind", "source", "points", "closed"}:
                raise InputError("Polyline needs exactly points and closed policy")
            points = require(component, "points")
            if not isinstance(points, list) or len(points) < 2:
                raise InputError("Wall polyline needs at least two points")
            points = [_point(point, "wall point", width, height) for point in points]
            if not isinstance(component["closed"], bool):
                raise InputError("Polyline closure must be explicit boolean")
            if component["closed"]:
                points.append(points[0])
            for (x1, y1), (x2, y2) in zip(points, points[1:]):
                if x1 != x2 and y1 != y2:
                    raise InputError("Wall polylines must use orthogonal steps")
                tiles.update(
                    (x, y)
                    for x in range(min(x1, x2), max(x1, x2) + 1)
                    for y in range(min(y1, y2), max(y1, y2) + 1)
                )
        elif kind == "rectangle_outline":
            if set(component) != {"kind", "source", "top_left", "bottom_right"}:
                raise InputError("Rectangle outline needs its two inclusive corners")
            left, top = _point(component["top_left"], "outline start", width, height)
            right, bottom = _point(
                component["bottom_right"], "outline end", width, height
            )
            if left >= right or top >= bottom:
                raise InputError("Wall outline needs positive width and height")
            tiles.update((x, y) for x in range(left, right + 1) for y in (top, bottom))
            tiles.update((x, y) for x in (left, right) for y in range(top, bottom + 1))
        elif kind == "manhattan_band":
            if set(component) != {"kind", "source", "center", "radius", "thickness"}:
                raise InputError("Manhattan band needs center, radius and thickness")
            cx, cy = _point(component["center"], "band center", width, height)
            radius = integer(component["radius"], "band radius", 1)
            thickness = integer(component["thickness"], "band thickness", 1, radius)
            if (
                cx - radius < 0
                or cy - radius < 0
                or cx + radius >= width
                or cy + radius >= height
            ):
                raise InputError("Manhattan band would leave the declared board")
            tiles.update(
                (x, y)
                for x in range(cx - radius, cx + radius + 1)
                for y in range(cy - radius, cy + radius + 1)
                if radius - thickness < abs(x - cx) + abs(y - cy) <= radius
            )
        else:
            raise InputError(f"Unsupported wall architecture component: {kind}")
    return tiles


def generate_architecture_candidates(target, catalog, specification):
    identifier(require(specification, "source"), "architecture proposal evidence")
    proposals = require(specification, "proposals")
    limit = integer(
        require(specification, "maximum_candidates"), "architecture limit", 1
    )
    if not isinstance(proposals, list) or not proposals:
        raise InputError("Architecture search needs explicit proposal configurations")
    if len(proposals) > limit:
        raise InputError(
            "Declared architecture proposals exceed the supplied search limit"
        )
    probes = require(specification, "geometry_probes")
    identifiers = set()
    accepted = []
    rejected = []
    for proposal in proposals:
        proposal_id = identifier(require(proposal, "id"), "architecture proposal id")
        if proposal_id in identifiers:
            raise InputError("Architecture proposal ids must be unique")
        identifiers.add(proposal_id)
        family = identifier(require(proposal, "family"), "architecture family")
        configuration = deepcopy(require(proposal, "configuration"))
        components = require(proposal, "wall_components")
        try:
            wall_tiles = architecture_wall_tiles(
                components, require(configuration, "board")
            )
            configuration["id"] = proposal_id
            configuration["wall_segments"] = [
                {"x1": x, "y1": y, "x2": x, "y2": y}
                for x, y in sorted(wall_tiles, key=lambda cell: (cell[1], cell[0]))
            ]
            configuration["architecture_provenance"] = {
                "family": family,
                "wall_components": deepcopy(components),
                "proposal_source": specification["source"],
                "geometry_is_not_defense_optimization": True,
            }
            candidate = generate_blueprint(target, catalog, configuration)
            actual_walls = sorted(
                [item["x"], item["y"]]
                for item in candidate["buildings"]
                if item["id"] == "wall"
            )
            accepted.append(
                {
                    "id": proposal_id,
                    "family": family,
                    "declared_component_wall_count": len(wall_tiles),
                    "allocated_remainder_wall_count": len(actual_walls)
                    - len(wall_tiles),
                    "wall_geometry_id": stable_id(actual_walls),
                    "blueprint": candidate,
                    "analysis": inspect_blueprint(candidate, catalog, probes),
                }
            )
        except InputError as error:
            rejected.append(
                {
                    "id": proposal_id,
                    "family": family,
                    "reason": str(error),
                    "proposal": deepcopy(proposal),
                }
            )
    return {
        "status": "DECLARED_ARCHITECTURE_ENUMERATION_NOT_DEFENSE_OPTIMIZATION",
        "source": specification["source"],
        "proposed_count": len(proposals),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "distinct_accepted_wall_geometries": len(
            {item["wall_geometry_id"] for item in accepted}
        ),
        "candidates": accepted,
        "rejections": rejected,
        "performance_winner_selected": False,
        "full_game_prediction": False,
        "remaining": [
            "Validate the board, full inventory and settings in the game editor",
            "Search additional wall/building combinations using calibrated combat and matched human attack plans",
            "Evaluate ranked trophies separately from best incoming war/CWL stars and destruction",
        ],
    }
