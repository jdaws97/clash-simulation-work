"""Generate bounded original layout variations and frozen conditional case inputs."""

import argparse
from copy import deepcopy
from itertools import product
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clashlab.architectures import generate_architecture_candidates
from clashlab.catalog import Catalog
from clashlab.common import read_json, write_json, InputError
from clashlab.crafted_selection import selection_projection
from clashlab.deployment_mask import deployment_mask
from clashlab.development_village import counted_layout, padded_layout
from clashlab.higher_town_halls import synthetic_layout
from clashlab.layout_evaluation import content_sha, candidate_layout_sha256
from clashlab.layout_generation import (
    ORIGIN,
    select_generated_station,
    variations,
    change_cost,
)
from clashlab.layout_scenarios import prepare_case


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    catalog = Catalog.load(ROOT / "data")
    inputs = {
        "target": read_json(ROOT / "profiles/target-max-th16-inventory.json"),
        "proposals": read_json(
            ROOT / "examples/architecture-proposals-conditional.json"
        ),
    }
    families = {"staggered_compartments", "split_core", "offset_ring"}
    inputs["proposals"]["proposals"] = [
        p for p in inputs["proposals"]["proposals"] if p["family"] in families
    ]
    inputs["proposals"]["maximum_candidates"] = 6
    generated = generate_architecture_candidates(
        inputs["target"], catalog, inputs["proposals"]
    )
    if len(generated["candidates"]) != 6 or generated["rejections"]:
        raise InputError("Expected the six pinned project-generated architecture seeds")
    craft = read_json(
        ROOT / "data/battle-policies/layout-search-crafted-experimental.json"
    )["variants"]
    mask = {
        "rim": "one_tile_square",
        "hero_banners_block": True,
        "source": "task20-secondary-evidence-static-one-tile-hypothesis-live-corners-unverified",
        "state": "initial_hidden_teslas",
    }
    roots = []
    for item in generated["candidates"]:
        layout = counted_layout(item["blueprint"], catalog)
        layout["evaluation_mode"] = (
            "ranked" if item["id"].startswith("ranked-") else "cwl"
        )
        roots.append(layout)
    for th, mode in product((17, 18), ("ranked", "cwl")):
        layout = synthetic_layout(catalog, th)
        layout.update(id=f"{layout['id']}-{mode}", evaluation_mode=mode)
        roots.append(layout)
    records, candidates = [], []
    names = tuple(craft)
    for index, root in enumerate(roots):
        root["generation_origin"] = ORIGIN
        variant = names[index % len(names)]
        selected = select_generated_station(
            root, catalog, selection_projection(craft[variant]["parameters"])
        )
        selected["station_change_cost"] = change_cost(root, selected)
        variants = variations(
            selected, catalog, seed=2400 + index, limit=1, attempts=12
        )
        for layout in [selected, *variants]:
            candidate_id = f"candidate-{len(candidates):02d}"
            layout["candidate_id"] = candidate_id
            write_json(output / "layouts" / f"{candidate_id}.json", layout)
            square = deployment_mask(layout, catalog, mask)
            orthogonal = deployment_mask(
                layout, catalog, {**mask, "rim": "one_tile_orthogonal"}
            )
            write_json(
                output / "masks" / f"{candidate_id}.json",
                {"square": square, "orthogonal": orthogonal},
            )
            records.append(
                {
                    "candidate_id": candidate_id,
                    "layout_id": layout["id"],
                    "layout_sha256": content_sha(layout),
                    "mode": layout["evaluation_mode"],
                    "town_hall": layout["town_hall"],
                    "variant": variant,
                    "object_count": len(layout["buildings"]),
                    "square_pocket_cells": sum(map(len, square["isolated_components"])),
                    "orthogonal_pocket_cells": sum(
                        map(len, orthogonal["isolated_components"])
                    ),
                    "wall_enclosed_free_cells": len(square["wall_enclosed_free_cells"]),
                    "change_cost": layout.get("generation_receipt", {}).get(
                        "change_cost", layout["station_change_cost"]
                    ),
                    "game_legality_proven": False,
                }
            )
            candidates.append(layout)
    base = read_json(ROOT / "data/battle-policies/development-th16.json")
    base["higher_town_halls"] = read_json(
        ROOT / "data/battle-policies/experimental-higher-th.json"
    )
    army_policy = read_json(ROOT / "data/battle-policies/development-full-army.json")
    template = read_json(ROOT / "profiles/sample-th16.json")
    planned, smoke = [], []
    for th, mode in product((16, 17, 18), ("ranked", "cwl")):
        matched = [
            c
            for c in candidates
            if c["town_hall"] == th and c["evaluation_mode"] == mode
        ]
        # Original and first variation are matched against the exact same cases.
        for layout_index, original in enumerate(matched):
            dimensions = (
                product(
                    (16, 17, 18),
                    ("air", "ground"),
                    ("west", "east"),
                    ("scheduled", "delayed_5s"),
                )
                if th == 16
                else product((16,), ("air", "ground"), ("west",), ("scheduled",))
            )
            if th == 16 and layout_index >= 2:
                # Small paired coverage for the other two architecture families;
                # a declared fractional grid, not population occurrence weights.
                attacker = 16 + layout_index // 2
                dimensions = (
                    (attacker, "air", "west", "scheduled"),
                    (attacker, "ground", "east", "delayed_5s"),
                )
            for attacker, family, entry, ability in dimensions:
                case = {
                    "id": f"{original['candidate_id']}-{attacker}-{family}-{entry}-{ability}",
                    "candidate_id": original["candidate_id"],
                    "candidate_layout_sha256": candidate_layout_sha256(
                        padded_layout(original)
                    ),
                    "mode": mode,
                    "attacker_town_hall": attacker,
                    "defender_town_hall": th,
                    "family": family,
                    "entry_policy": entry,
                    "ability_policy": ability,
                    "split": "held_out" if entry == "east" else "search",
                }
                variant = original["inventory_selection"]["crafted"]["variant"]
                try:
                    bundle = prepare_case(
                        case,
                        original,
                        catalog,
                        template,
                        base,
                        army_policy,
                        craft[variant],
                        mask,
                    )
                    path = Path("cases") / f"{case['id']}.json"
                    write_json(output / path, bundle)
                    row = {"bundle": path.as_posix()}
                except (InputError, KeyError, ValueError) as error:
                    row = {
                        "case": case,
                        "preparation_failure": f"{type(error).__name__}: {error}",
                    }
                planned.append(row)
                # Predeclared 12-run coverage sample; untouched paired grid remains
                # visible in all-cases.json. Not enough to rank any candidate.
                chosen_entry = "west" if family == "air" else "east"
                chosen_ability = (
                    "scheduled" if attacker == 16 or family == "air" else "delayed_5s"
                )
                chosen_layout = 2 * (attacker - 16) + int(family == "ground")
                if (
                    th == 16
                    and layout_index == chosen_layout
                    and entry == chosen_entry
                    and ability == chosen_ability
                ):
                    smoke.append(row)
    write_json(
        output / "generation.json",
        {
            "inputs_sha256": {k: content_sha(v) for k, v in inputs.items()},
            "generator_source_sha256": content_sha(
                {
                    p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
                    for p in [
                        *sorted((ROOT / "src/clashlab").glob("*.py")),
                        Path(__file__),
                    ]
                }
            ),
            "catalog_snapshot": catalog.snapshot["snapshotCommit"],
            "original_six_count": len(generated["candidates"]),
            "rejected_original_proposals": generated["rejections"],
            "candidates": records,
            "manual_v3_touched": False,
            "screenshot_used_as_template": False,
            "mask_limit": "No square/orthogonal model proves live corner legality",
            "planned_case_count": len(planned),
            "smoke_case_count": len(smoke),
        },
    )
    for name, rows, operation in (
        ("all-cases", planned, "compile"),
        ("smoke-compile", smoke, "compile"),
        ("smoke-simulate", smoke, "simulate"),
    ):
        write_json(
            output / f"{name}.json",
            {"operation": operation, "timeout_seconds": 8, "cases": rows},
        )
    print(
        f"Generated {len(candidates)} layouts, {len(planned)} planned cases, {len(smoke)} smoke cases",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output.resolve())
