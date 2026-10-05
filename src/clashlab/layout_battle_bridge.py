"""Separate builder hooks for season-selected layouts; shared kernel stays owned.

Higher-TH assembly preserves the validated explicit merge selection. Shared
defender helpers assemble every selected object, including one ACTIVE Station.
"""

from copy import deepcopy

from .common import InputError
from .crafted_selection import selection_projection
from .development_village import _instance, build_scene as th16_scene
from .layout_higher_assembly import build_selected_higher_scene
from .layout_inventory import inspect_inventory


def bind_selected_station(scene, layout, catalog, base_policies, crafted_policy):
    """Return a fresh scene with exact selected-module and shared-weapon ownership."""
    selection = layout["inventory_selection"]["crafted"]
    if selection is None:
        raise InputError("Active crafted defense is mandatory for this pipeline")
    if selection_projection(crafted_policy["parameters"]) != selection:
        raise InputError(
            "Crafted combat parameters differ from layout selected modules"
        )
    result = deepcopy(scene)
    stations = [b for b in layout["buildings"] if b["id"] == "crafting-station"]
    if len(stations) != 1:
        raise InputError("Exactly one physical Station required")
    b = stations[0]
    result["entities"] = [
        a for a in result["entities"] if a["entity"] != "crafting-station"
    ]
    actor = _instance(
        b["instance"], "crafting-station", 1, "defense", b["x"], b["y"], base_policies
    )
    actor.update(
        town_hall=layout["town_hall"],
        attack_parameters={},
        crafted_parameters=deepcopy(crafted_policy["parameters"]),
        crafted_shared_binding=deepcopy(crafted_policy["shared_binding"]),
    )
    result["entities"].append(actor)
    return result


def build_layout_scene(
    layout, catalog, policies, crafted_policy, scope, rules, duration=180
):
    inspect_inventory(layout, catalog, layout["inventory_selection"])
    if layout["town_hall"] == 16:
        scene = th16_scene(layout, catalog, policies, scope, rules, duration)
    else:
        scene = build_selected_higher_scene(
            layout, catalog, policies, scope, rules, duration
        )
    return bind_selected_station(scene, layout, catalog, policies, crafted_policy)


def assert_crafted_compiled(compiled, layout):
    """An empty Station cannot satisfy active crafted coverage."""
    b = next(b for b in layout["buildings"] if b["id"] == "crafting-station")
    actors = compiled["compiled"]["scene"]["actors"]
    matches = [a for a in actors if a["id"] == b["instance"]]
    if len(matches) != 1 or "crafted_defense_model" not in matches[0]:
        raise InputError("Selected Station has no compiled crafted weapon lifecycle")
    model = matches[0]["crafted_defense_model"]
    if model["variant"] != b["settings"]["crafted"]["variant"]:
        raise InputError("Compiled crafted variant differs from layout")
    return {
        "station": b["instance"],
        "variant": model["variant"],
        "active_weapon_compiled": True,
        "game_calibrated": False,
    }
