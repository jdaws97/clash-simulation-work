"""Two original TH16 architectures versus one fixed, catalog-capped TH17 plan."""

import argparse
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clashlab.architectures import generate_architecture_candidates
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json, write_json
from clashlab.crafted_selection import selection_projection
from clashlab.development_armies import _bind_responses, _deploy
from clashlab.development_village import counted_layout, padded_layout
from clashlab.higher_town_halls import maximum_level
from clashlab.layout_evaluation import (
    candidate_layout_sha256,
    compile_case,
    content_sha,
)
from clashlab.layout_generation import ORIGIN, select_generated_station
from clashlab.layout_inventory import inspect_inventory
from clashlab.layout_scenarios import prepare_case
from clashlab.spatial import AIR_CONTACT_POLICY


def fill_existing_roster(bundle, catalog):
    """Fill TH17 camp/Castle using already represented Dragon/Archer policies."""
    account, army = bundle["account"], bundle["army"]
    scene = bundle["specification"]["entity_scene"]
    capacity = account["capacities"]["army_housing"]
    housing = catalog.entity("dragon")["housingSpace"]
    if capacity % housing:
        raise InputError("This predeclared roster requires whole Dragons")
    count = capacity // housing
    template = next(a for a in scene["entities"] if a["id"] == "army-dragon-0")
    for index in range(army["troops"][0]["count"], count):
        actor = deepcopy(template)
        actor.update(id=f"army-dragon-{index}", y=9.5 + (index % 16) * 2.5)
        scene["entities"].append(actor)
        scene["effects"].append(_deploy(actor, index * 0.15))
    army["troops"][0]["count"] = count
    payload = army["clan_castle"]["troops"]
    used = sum(catalog.entity(t["id"])["housingSpace"] * t["count"] for t in payload)
    remaining = account["capacities"]["clan_castle_troops"] - used
    if remaining < 0 or catalog.entity("archer")["housingSpace"] != 1:
        raise InputError("Unexpected Castle capacity or Archer housing")
    archers = next(t for t in payload if t["id"] == "archer")
    template = next(a for a in scene["entities"] if a["id"] == "cc-archer-0")
    group = scene["attacking_reinforcements"]
    for index in range(archers["count"], archers["count"] + remaining):
        actor = deepcopy(template)
        actor["id"] = f"cc-archer-{index}"
        scene["entities"].append(actor)
        group["member_ids"].append(actor["id"])
        group["release"]["offsets"][actor["id"]] = {"x": 0, "y": 0}
    archers["count"] += remaining
    _bind_responses(
        scene,
        [a for a in scene["entities"] if a["team"] == "attack"],
        scene["pets"],
        catalog,
    )


def attack_projection(bundle):
    projection = deepcopy(bundle["specification"])
    projection.pop("id")
    scene = projection["entity_scene"]
    scene.pop("id")
    scene["entities"] = [a for a in scene["entities"] if a["team"] == "attack"]
    scene.pop("traps")
    return {
        "account": bundle["account"],
        "army": bundle["army"],
        "specification": projection,
    }


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    catalog = Catalog.load(ROOT / "data")
    rules = read_json(ROOT / "data/mode-rules.json")
    proposals = read_json(ROOT / "examples/architecture-proposals-conditional.json")
    families = {"staggered_compartments", "split_core"}
    proposals["proposals"] = [
        p
        for p in proposals["proposals"]
        if p["family"] in families and p["id"].startswith("ranked-")
    ]
    proposals["maximum_candidates"] = 2
    target = read_json(ROOT / "profiles/target-max-th16-inventory.json")
    generated = generate_architecture_candidates(target, catalog, proposals)
    if len(generated["candidates"]) != 2 or generated["rejections"]:
        raise InputError(
            f"Expected two generated architectures: {generated['rejections']}"
        )
    craft = read_json(
        ROOT / "data/battle-policies/layout-search-crafted-experimental.json"
    )["variants"]["hot-candle"]
    base = read_json(ROOT / "data/battle-policies/development-th16.json")
    base["higher_town_halls"] = read_json(
        ROOT / "data/battle-policies/experimental-higher-th.json"
    )
    policy = read_json(ROOT / "data/battle-policies/development-full-army.json")
    template = read_json(ROOT / "profiles/sample-th16.json")
    mask = {
        "rim": "one_tile_square",
        "hero_banners_block": True,
        "source": "task20-secondary-evidence-static-one-tile-hypothesis-live-corners-unverified",
        "state": "initial_hidden_teslas",
    }
    rows, evidence, attacks, inventories = [], [], [], []
    for item in generated["candidates"]:
        layout = counted_layout(item["blueprint"], catalog)
        layout.update(
            generation_origin=ORIGIN, evaluation_mode="ranked", candidate_id=item["id"]
        )
        layout = select_generated_station(
            layout, catalog, selection_projection(craft["parameters"])
        )
        case = {
            "id": item["id"] + "-th17-air-west",
            "candidate_id": item["id"],
            "candidate_layout_sha256": candidate_layout_sha256(padded_layout(layout)),
            "mode": "ranked",
            "attacker_town_hall": 17,
            "defender_town_hall": 16,
            "family": "air",
            "entry_policy": "west",
            "ability_policy": "scheduled",
            "split": "search",
        }
        bundle = prepare_case(
            case, layout, catalog, template, base, policy, craft, mask
        )
        fill_existing_roster(bundle, catalog)
        bundle["assumptions"][
            0
        ] = "Full catalog-capped TH17 Dragon army and Castle housing; same fixed attack across both TH16 layouts"
        bundle["assumptions"].extend(
            [
                "Explicit opt-in to "
                + AIR_CONTACT_POLICY
                + "; uncalibrated and outcome-changing",
                "Hot Candle phase4/module-level1 is a conditional pinned selection, not current-season certification",
            ]
        )
        admission = compile_case(bundle, catalog, rules)
        inventory = inspect_inventory(
            bundle["layout"], catalog, bundle["layout"]["inventory_selection"]
        )
        attack_hash = content_sha(attack_projection(bundle))
        attacks.append(attack_hash)
        nongeometry = sorted(
            [
                {k: v for k, v in b.items() if k not in {"x", "y"}}
                for b in layout["buildings"]
            ],
            key=lambda b: b["instance"],
        )
        inventories.append(content_sha(nongeometry))
        path = "cases/" + case["id"] + ".json"
        write_json(output / path, bundle)
        write_json(output / "layouts" / (item["id"] + ".json"), layout)
        rows.append(
            {
                "bundle": path,
                "case": case,
                "input_sha256": content_sha(bundle),
                "admission": admission,
            }
        )
        evidence.append(
            {
                "case_id": case["id"],
                "inventory": inventory,
                "attack_projection_sha256": attack_hash,
                "nongeometry_defense_sha256": inventories[-1],
                "capacities": bundle["account"]["capacities"],
                "troops": bundle["army"]["troops"],
                "heroes": bundle["army"]["heroes"],
                "castle": bundle["army"]["clan_castle"],
                "laboratory_level": bundle["account"]["laboratory_level"],
                "th16_dragon_cap": maximum_level(catalog, "dragon", 16),
                "th17_dragon_cap": maximum_level(catalog, "dragon", 17),
            }
        )
        print(case["id"] + " compiled", flush=True)
    if len(set(attacks)) != 1 or len(set(inventories)) != 1:
        raise InputError(
            "Pair differs in attack semantics or defense inventory/settings"
        )
    limits = [
        "Original generated full TH16 inventories versus one identical genuine TH17 synthetic attack; fixed west entry and schedule",
        "Only geometry differs; full nongeometry defense content and attack projection hashes are identical",
        "Legend I profile and conditional phase4 level1 Hot Candle active in both",
        "Pinned catalog legality and conditional footprint admission do not establish live-game placement or current-season availability",
        "Experimental airborne contact movement explicitly accepted; no complete held-out game calibration",
        "One paired attack cannot establish a generally best base or a game recommendation",
    ]
    write_json(
        output / "manifest.json",
        {
            "source": "controlled-generated-th16-defense-pair-20261005",
            "operation": "simulate",
            "timeout_seconds": 240,
            "maximum_total_wall_seconds": 485,
            "cases": rows,
            "comparison_limits": limits,
            "held_out_game_calibrations": 0,
            "experimental_air_contact": AIR_CONTACT_POLICY,
        },
    )
    write_json(
        output / "preparation.json",
        {
            "target_sha256": content_sha(target),
            "proposals_sha256": content_sha(proposals),
            "catalog_snapshot": catalog.snapshot["snapshotCommit"],
            "cases": evidence,
            "same_attack_and_nongeometry_defense": True,
            "limits": limits,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output.resolve())
