"""Run eight bounded paid compact battles plus an unsupported-equipment control.

Synthetic engine demonstration only. This does not evaluate complete villages,
recommend a game army/base, or establish held-out game calibration.
"""

import argparse
from copy import deepcopy
import csv
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clashlab.attack_search_runner import fingerprints, run_search
from clashlab.common import InputError, read_json, write_json


def run(output):
    if output.exists():
        raise InputError("Use a fresh output directory; previous evidence is immutable")
    output.mkdir(parents=True)
    manifests = sorted((ROOT / "examples/prototype").glob("arena-*.json"))
    if len(manifests) != 4:
        raise InputError("Prototype requires its four frozen original input manifests")
    before = fingerprints(ROOT / "data")
    identities = {
        path.name: sha256(path.read_bytes()).hexdigest() for path in manifests
    }
    script_sha = sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    rows = []
    for manifest_path in manifests:
        report = run_search(
            read_json(manifest_path),
            ROOT / "data",
            output / manifest_path.stem,
            output / "cache",
        )
        for row in report["rows"]:
            result = row["result"]
            outcome = result.get("outcome") or {}
            paid = result.get("paid_observation") or {}
            rows.append(
                {
                    "scenario": manifest_path.stem,
                    "roster": row["option_ids"][0],
                    "plan": row["option_ids"][1],
                    "candidate_id": row["candidate_id"],
                    "status": result["status"],
                    "end_reason": outcome.get("end_reason"),
                    "stars": outcome.get("stars"),
                    "destruction": outcome.get("destruction"),
                    "elapsed_seconds": outcome.get("elapsed_seconds"),
                    "paid_actions": len(paid.get("actions", [])),
                    "crafted_event_counts": result.get("crafted_event_counts", {}),
                    "funnel_decisions": paid.get("funnel_decisions", []),
                    "scenario_sha256": result.get("scenario_sha256"),
                    "reason": result.get("reason"),
                    "report": str(
                        (output / manifest_path.stem / "report.json").resolve()
                    ),
                }
            )
        print(
            json.dumps(
                {
                    "scenario": manifest_path.stem,
                    "statuses": [r["result"]["status"] for r in report["rows"]],
                }
            ),
            flush=True,
        )
    unsupported = deepcopy(read_json(manifests[0]))
    unsupported["id"] += "-unsupported-monolith-control"
    unsupported["budget"]["maximum_candidates"] = 1
    roster = unsupported["army_options"][0]
    queen = next(a for a in roster["entity_scene"]["entities"] if a["id"] == "queen")
    queen["hero_parameters"]["equipment"][0] = {
        "entity": "monolith-arrow",
        "level": 27,
        "parameters": {"source": "intentional-unsupported-control"},
    }
    roster["army"]["heroes"][0]["equipment"][0] = {"id": "monolith-arrow", "level": 27}
    unsupported["account"]["levels"]["monolith-arrow"] = 27
    blocked = run_search(
        unsupported, ROOT / "data", output / "unsupported-control", output / "cache"
    )["rows"][0]["result"]
    if (
        blocked["status"] not in {"rejected", "blocked_dependency"}
        or blocked.get("objective") is not None
    ):
        raise InputError("Unsupported control was not explicitly rejected unscored")
    if (
        before != fingerprints(ROOT / "data")
        or identities
        != {path.name: sha256(path.read_bytes()).hexdigest() for path in manifests}
        or script_sha != sha256(Path(__file__).read_bytes()).hexdigest()
    ):
        raise InputError("Engine, inputs or runner changed during prototype execution")
    completed = sum(row["status"] == "completed" for row in rows)
    summary = {
        "status": (
            "complete_compact_demonstration"
            if completed == 8
            else "incomplete_compact_demonstration"
        ),
        "planned_battles": 8,
        "completed_battles": completed,
        "repository_commit": commit,
        "runner_sha256": script_sha,
        "input_sha256": identities,
        "fingerprints": before,
        "rows": rows,
        "unsupported_control": blocked,
        "recommendations": [],
        "full_village_results": 0,
        "complete_held_out_game_calibrations": 0,
        "limits": [
            "Original compact four-building TH18 synthetic defenses with active Hot Candle, Longshot and Giga Bomb; not full villages",
            "TH16 troops320/320; spells3/11; one Queen/Unicorn; empty Castle and no siege; not a competitive loadout claim",
            "Policies, geometry, targeting, Dragon splash and Giga response coefficients are explicit uncalibrated assumptions",
            "Battle profiles: Legend I only in this demo. War/CWL remain separate supported inputs",
            "Different roster response maps use separate scenario identities; the table is descriptive, not a pooled cross-scenario ranking",
            "Root pursuit throughput remains unresolved; no timeout/error is converted to a score",
            "Optional Monolith implementation is excluded; this frozen prototype rejects it",
        ],
    }
    write_json(output / "prototype-summary.json", summary)
    with (output / "comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        keys = [
            "scenario",
            "roster",
            "plan",
            "status",
            "end_reason",
            "stars",
            "destruction",
            "elapsed_seconds",
            "paid_actions",
        ]
        writer = csv.DictWriter(stream, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(
        json.dumps(
            {
                "summary": str(output / "prototype-summary.json"),
                "completed": completed,
                "planned": 8,
                "unsupported_control": blocked["status"],
            }
        ),
        flush=True,
    )
    return completed == 8


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        successful = run(args.output.resolve())
    except (InputError, OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"{type(error).__name__}: {error}\n")
    raise SystemExit(0 if successful else 2)
