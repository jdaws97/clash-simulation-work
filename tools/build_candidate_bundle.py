"""Export six complete synthetic TH16 geometry candidates, without battle ranking."""

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clashlab.architectures import generate_architecture_candidates
from clashlab.catalog import Catalog
from clashlab.development_village import counted_layout
from clashlab.geometry import footprint, gap, validate_layout


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def render_viewer(output, rows, catalog):
    """Embed synthetic coordinates so the viewer also works directly from disk."""
    layouts = []
    for row in rows:
        layout = json.loads((output / f"{row['id']}.json").read_text(encoding="utf-8"))
        for building in layout["buildings"]:
            building["footprint"] = footprint(building, catalog)
            building["category"] = catalog.entity(building["id"])["category"]
        layouts.append({"summary": row, "layout": layout})
    payload = json.dumps(layouts, ensure_ascii=True).replace("<", "\\u003c")
    template = (ROOT / "tools/candidate_bundle.html").read_text(encoding="utf-8")
    (output / "index.html").write_text(
        template.replace("__CANDIDATES__", payload), encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/candidates")
    args = parser.parse_args()
    inputs = {
        "target": ROOT / "profiles/target-max-th16-inventory.json",
        "proposals": ROOT / "examples/architecture-proposals-conditional.json",
        "catalog": ROOT / "data/catalog.json",
        "secondary": ROOT / "data/secondary-raw.json",
    }
    target = json.loads(inputs["target"].read_text(encoding="utf-8"))
    spec = json.loads(inputs["proposals"].read_text(encoding="utf-8"))
    families = {"staggered_compartments", "split_core", "offset_ring"}
    spec["proposals"] = [p for p in spec["proposals"] if p["family"] in families]
    spec["maximum_candidates"] = 6
    catalog = Catalog.load(ROOT / "data")
    result = generate_architecture_candidates(target, catalog, spec)
    if result["accepted_count"] != 6 or result["rejections"]:
        raise ValueError(f"Expected six accepted candidates: {result['rejections']}")
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "selected-specification.json", spec)
    rows = []
    expected = {key: item["count"] for key, item in target["inventory"].items()}
    for candidate in result["candidates"]:
        layout = counted_layout(candidate["blueprint"], catalog)
        validation = validate_layout(layout, catalog)
        actual = dict(Counter(b["id"] for b in layout["buildings"]))
        if actual != expected or actual.get("wall") != 325:
            raise ValueError("Candidate does not preserve exact target inventory")
        mode = "war-cwl" if candidate["id"].startswith("war-cwl-") else "ranked"
        layout["recommendation_status"] = "SYNTHETIC_COMPARISON_CANDIDATE"
        layout["objective"] = (
            "Protect the Town Hall and challenge two-star access in ranked attacks"
            if mode == "ranked"
            else "Challenge three-star completion after scouting in war/CWL"
        )
        layout["full_game_prediction"] = False
        write_json(args.output / f"{candidate['id']}.json", layout)
        with (args.output / f"{candidate['id']}.csv").open(
            "w", encoding="utf-8", newline=""
        ) as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=["instance", "id", "level", "x", "y", "mode", "settings"],
            )
            writer.writeheader()
            for building in layout["buildings"]:
                row = {key: building.get(key, "") for key in writer.fieldnames}
                row["settings"] = json.dumps(
                    building.get("settings", {}), sort_keys=True
                )
                writer.writerow(row)
        anchors = {
            b["id"]: b
            for b in layout["buildings"]
            if b["id"] in {"town-hall", "monolith", "clan-castle", "eagle-artillery"}
        }
        rows.append(
            {
                "id": candidate["id"],
                "family": candidate["family"],
                "mode": mode,
                "objective": layout["objective"],
                "validation": validation,
                "inventory": actual,
                "declared_wall_tiles": candidate["declared_component_wall_count"],
                "remainder_wall_tiles": candidate["allocated_remainder_wall_count"],
                "wall_geometry_id": candidate["wall_geometry_id"],
                "anchor_coordinates": {
                    key: [b["x"], b["y"]] for key, b in anchors.items()
                },
                "town_hall_monolith_footprint_gap": gap(
                    anchors["town-hall"], anchors["monolith"], catalog
                ),
                "geometry_probes": {
                    key: candidate["analysis"][key]
                    for key in (
                        "status",
                        "town_hall_boundary_distance_tiles",
                        "maximum_key_anchors_under_declared_disc",
                    )
                },
                "json_sha256": digest(args.output / f"{candidate['id']}.json"),
                "csv_sha256": digest(args.output / f"{candidate['id']}.csv"),
            }
        )
    source_files = [
        Path(__file__),
        ROOT / "tools/candidate_bundle.html",
        *sorted((ROOT / "src/clashlab").glob("*.py")),
    ]
    summary = {
        "status": "COMPLETE_SYNTHETIC_GEOMETRY_COMPARISON_NOT_CALIBRATED",
        "candidate_count": len(rows),
        "game_win_ranking": False,
        "optimality_claim": False,
        "battle_simulation_run": False,
        "board_verified_in_game": False,
        "board": {"width": 44, "height": 44, "evidence": "declared_hypothesis"},
        "limitations": [
            "Catalog and inventory are pinned snapshots, not a live patch check",
            "Coordinates and defensive settings require game-editor verification",
            "Destruction classification and defensive garrison are explicit development policies",
            "Geometry probes do not predict stars, trophies or win rates",
            "No opponent-frequency weighting or calibrated performance winner",
        ],
        "input_sha256": {
            p.relative_to(ROOT).as_posix(): digest(p) for p in inputs.values()
        },
        "selected_specification_sha256": digest(
            args.output / "selected-specification.json"
        ),
        "code_sha256": {
            p.relative_to(ROOT).as_posix(): digest(p) for p in source_files
        },
        "candidates": rows,
    }
    write_json(args.output / "summary.json", summary)
    render_viewer(args.output, rows, catalog)
    print(
        json.dumps(
            {
                "candidate_count": len(rows),
                "output": str(args.output),
                "geometry_validated": True,
                "game_win_ranking": False,
            }
        )
    )


if __name__ == "__main__":
    main()
