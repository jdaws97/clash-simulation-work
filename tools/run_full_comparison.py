"""Bounded serial full-village comparisons with immutable inputs and unscored failures."""

import argparse
from collections import Counter
import csv
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clashlab.attack_search_runner import fingerprints
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json, write_json
from clashlab.layout_evaluation import content_sha, simulate_case
from clashlab.recipe_troops import RecipeTroopCombat
from clashlab.spatial import AIR_CONTACT_POLICY


def identity():
    return {
        **fingerprints(ROOT / "data"),
        "runner_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "air_contact_policy": AIR_CONTACT_POLICY,
        "movement_fidelity": "explicit_uncalibrated_hypothesis_may_change_outcomes",
    }


def worker(bundle_path, output, expected_path):
    expected = read_json(expected_path)
    if expected.get("experimental_air_contact") != AIR_CONTACT_POLICY:
        raise InputError(
            "Explicit consent to provisional air-contact movement is required"
        )
    before = identity()
    bundle = read_json(bundle_path)
    if before != expected["engine"] or content_sha(bundle) != expected["input_sha256"]:
        raise InputError("Worker engine/input differs from frozen parent")
    started = time.monotonic()
    last = started
    prepare = RecipeTroopCombat.prepare

    def progress(self, now, trace):
        nonlocal last
        current = time.monotonic()
        if current - last >= 20:
            print(
                json.dumps(
                    {"wall_seconds": current - started, "simulated_seconds": now}
                ),
                flush=True,
            )
            last = current
        return prepare(self, now, trace)

    RecipeTroopCombat.prepare = progress
    try:
        receipt, result = simulate_case(
            bundle,
            Catalog.load(ROOT / "data"),
            read_json(ROOT / "data/mode-rules.json"),
        )
    finally:
        RecipeTroopCombat.prepare = prepare
    if (
        before != identity()
        or content_sha(read_json(bundle_path)) != expected["input_sha256"]
    ):
        raise InputError("Worker engine/input changed during execution")
    result_path = output / "result.json.gz"
    with gzip.open(result_path, "wt", encoding="utf-8", compresslevel=1) as stream:
        json.dump(result, stream, separators=(",", ":"))
    trace = result["combat"]["trace"]
    if result["combat"].get("air_contact_policy") != AIR_CONTACT_POLICY:
        raise InputError("Result does not identify the accepted movement convention")
    receipt.update(
        attempt=expected["attempt"],
        engine=before,
        wall_seconds=time.monotonic() - started,
        result_sha256=sha256(result_path.read_bytes()).hexdigest(),
        result_file=result_path.name,
        trace_count=len(trace),
        crafted_event_counts=dict(
            Counter(
                row.get("event")
                for row in trace
                if str(row.get("event", "")).startswith("crafted_")
            )
        ),
        paid_observation=result.get("paid_observation"),
        full_game_prediction=False,
        experimental_air_contact=AIR_CONTACT_POLICY,
    )
    write_json(output / "worker-result.json", receipt)


def run(manifest_path, output, selected, *, experimental_air_contact=False):
    if not experimental_air_contact:
        raise InputError(
            "Pass --accept-experimental-air-contact for the uncalibrated movement convention; outcomes may change"
        )
    if output.exists():
        raise InputError("Use a fresh output directory; saved evidence is immutable")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    timeout = manifest["timeout_seconds"]
    if not isinstance(timeout, (int, float)) or not 1 <= timeout <= 400:
        raise InputError("Per-case wall budget must be 1..400 seconds")
    cases = manifest["cases"]
    if not 1 <= len(cases) <= 6:
        raise InputError("This prototype accepts at most six predeclared full cases")
    if selected:
        unknown = set(selected) - {row["case"]["id"] for row in cases}
        if unknown:
            raise InputError("Unknown case selection: " + repr(unknown))
        cases = [row for row in cases if row["case"]["id"] in selected]
    frozen = []
    for row in cases:
        path = (manifest_path.parent / row["bundle"]).resolve()
        if not path.is_relative_to(manifest_path.parent):
            raise InputError("Bundle must remain within the manifest directory")
        bundle = read_json(path)
        if content_sha(bundle) != row["input_sha256"] or bundle["case"] != row["case"]:
            raise InputError("Input differs from prepared complete-inventory admission")
        frozen.append((row, path.read_bytes()))
    output.mkdir(parents=True)
    (output / "manifest.json").write_bytes(manifest_bytes)
    before = identity()
    write_json(output / "fingerprints.json", before)
    started = time.monotonic()
    rows = []
    native_failure = False
    for index, (row, bundle_bytes) in enumerate(frozen):
        case_output = output / f"case-{index:02d}"
        case_output.mkdir()
        bundle_path = case_output / "bundle.json"
        bundle_path.write_bytes(bundle_bytes)
        expected = {
            "attempt": uuid4().hex,
            "engine": before,
            "input_sha256": row["input_sha256"],
            "experimental_air_contact": AIR_CONTACT_POLICY,
        }
        write_json(case_output / "attempt.json", expected)
        result = {
            "case": row["case"],
            "input_sha256": row["input_sha256"],
            "status": "not_attempted",
            "completion_proven": False,
            "outcome": None,
        }
        remaining = manifest["maximum_total_wall_seconds"] - (
            time.monotonic() - started
        )
        if native_failure or remaining < 1:
            result["reason"] = (
                "native-process failure stops remaining runs"
                if native_failure
                else "total wall budget exhausted"
            )
        else:
            command = [
                sys.executable,
                "-B",
                str(Path(__file__).resolve()),
                "--worker",
                str(bundle_path),
                "--output",
                str(case_output),
                "--expected",
                str(case_output / "attempt.json"),
            ]
            case_started = time.monotonic()
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0")
            env.pop("PYTHONPATH", None)
            with (case_output / "worker.log").open("w", encoding="utf-8") as log:
                try:
                    code = subprocess.run(
                        command,
                        cwd=ROOT,
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        timeout=min(timeout, remaining),
                    ).returncode
                except subprocess.TimeoutExpired:
                    code = "timeout"
            result.update(exit_code=code, wall_seconds=time.monotonic() - case_started)
            if code == 0:
                receipt = read_json(case_output / "worker-result.json")
                artifact = case_output / receipt["result_file"]
                if any(
                    receipt.get(key) != value for key, value in expected.items()
                ) or not receipt.get("completion_proven"):
                    raise InputError(
                        "Worker receipt is not bound to this fresh attempt"
                    )
                if (
                    sha256(artifact.read_bytes()).hexdigest()
                    != receipt["result_sha256"]
                ):
                    raise InputError("Completed artifact hash mismatch")
                result.update(receipt)
            else:
                result.update(
                    status="timeout" if code == "timeout" else "process_failure",
                    reason="No completed result accepted; see worker.log",
                )
                if isinstance(code, int) and code not in (1, 2):
                    native_failure = True
                    write_json(output / "NATIVE-CRASH-STOP.json", result)
        if before != identity() or manifest_bytes != manifest_path.read_bytes():
            raise InputError("Engine or manifest changed during the comparison")
        result["evidence_directory"] = case_output.name
        rows.append(result)
        write_json(case_output / "receipt.json", result)
        report = {
            "source": manifest["source"],
            "planned_cases": len(frozen),
            "finished_cases": len(rows),
            "rows": rows,
            "engine": before,
            "manifest_sha256": sha256(manifest_bytes).hexdigest(),
            "full_game_prediction": False,
            "held_out_game_calibrations": 0,
            "recommendations": [],
            "limits": manifest.get(
                "comparison_limits",
                [
                    "Original synthetic full TH18 inventory; no screenshot template or opponent weighting",
                    "Compare only within exact defense/mode; modes and crafted design packages are separate",
                    "Sampled engine-state controller has no human-latency or visibility model",
                    "All experimental policies retained in each bundle; TH16 stalled fixture excluded",
                ],
            ),
        }
        write_json(output / "comparison.json", report)
        print(
            json.dumps(
                {
                    "case": row["case"]["id"],
                    "status": result["status"],
                    "wall_seconds": result.get("wall_seconds"),
                    "outcome": result.get("outcome"),
                }
            ),
            flush=True,
        )
    with (output / "comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "case",
                "mode",
                "army",
                "defense",
                "status",
                "stars",
                "destruction",
                "elapsed_seconds",
                "end_reason",
                "wall_seconds",
            ],
        )
        writer.writeheader()
        for row in rows:
            outcome = row.get("outcome") or {}
            writer.writerow(
                {
                    "case": row["case"]["id"],
                    "mode": row["case"]["mode"],
                    "army": row["case"]["family"],
                    "defense": row["case"]["candidate_id"],
                    "status": row["status"],
                    "wall_seconds": row.get("wall_seconds"),
                    **{
                        key: outcome.get(key)
                        for key in (
                            "stars",
                            "destruction",
                            "elapsed_seconds",
                            "end_reason",
                        )
                    },
                }
            )
    return all(row["completion_proven"] for row in rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "examples/full-comparison/manifest.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--expected", type=Path)
    parser.add_argument(
        "--accept-experimental-air-contact",
        action="store_true",
        help="Explicitly accept uncalibrated airborne contact-following movement, which can change outcomes",
    )
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.output, args.expected)
    else:
        if not args.accept_experimental_air_contact:
            parser.error(
                "--accept-experimental-air-contact is required: this uncalibrated movement convention may change outcomes"
            )
        raise SystemExit(
            0
            if run(
                args.manifest.resolve(),
                args.output.resolve(),
                args.case,
                experimental_air_contact=args.accept_experimental_air_contact,
            )
            else 2
        )
