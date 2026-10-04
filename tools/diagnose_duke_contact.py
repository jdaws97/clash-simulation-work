"""Observe a preserved Duke contact or an explicitly selected policy experiment.

Input files and detailed output are private evidence; keep them outside Git.
Without --isolation-policy, the observer preserves strict simulation semantics.
The subprocess wall limit applies even when simulated time fails to advance.
"""

import argparse
from collections import deque
from copy import deepcopy
import hashlib
import gzip
import json
from math import hypot
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def worker(args):
    sys.path.insert(0, str(ROOT / "src"))
    from clashlab.catalog import Catalog
    from clashlab.common import InputError
    from clashlab.dragon_duke import DragonDukeCombat
    from clashlab.full_battle import simulate_full_battle
    from clashlab.hero_roster_rules import SAMPLED_DUKE_ISOLATION
    from clashlab.range_events import _segments
    from clashlab.spatial import center, target_distance

    inputs = []
    hashes = {}
    for name in ("input", "account", "army", "layout"):
        raw = (args.fixtures / f"{args.prefix}{name}.json").read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        inputs.append(json.loads(raw))
    if args.step is not None:
        inputs[0]["entity_scene"]["maximum_step_seconds"] = args.step
    policy = None
    if args.isolation_policy:
        policy = json.loads(args.isolation_policy.read_bytes())
        if args.sample_period is not None:
            policy["isolation_update"]["interval_seconds"] = args.sample_period
        instances = [
            instance
            for instance in inputs[0]["entity_scene"]["entities"]
            if instance["id"] == args.duke and instance["entity"] == "dragon-duke"
        ]
        if len(instances) != 1:
            raise InputError("Policy override requires exactly the named Dragon Duke")
        instances[0]["duke_parameters"].update(deepcopy(policy))
        inputs[0]["entity_scene"]["model_rules"][
            "duke_isolation"
        ] = SAMPLED_DUKE_ISOLATION
    effective_input_hash = hashlib.sha256(
        json.dumps(inputs[0], sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    digest = hashlib.sha256()
    for folder in ("src", "data"):
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file() and path.suffix in (".py", ".json"):
                digest.update(path.relative_to(ROOT).as_posix().encode() + b"\0")
                digest.update(path.read_bytes() + b"\0")
    recent = deque(maxlen=6)
    original = DragonDukeCombat.first_crossing_delay
    last_progress = time.perf_counter()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def observe(self, actors, routes, speeds, now, horizon):
        nonlocal last_progress
        if time.perf_counter() - last_progress >= 10:
            last_progress = time.perf_counter()
            progress = args.output.with_suffix(".progress.json")
            temporary = progress.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({"simulated_seconds": now}), encoding="utf-8"
            )
            temporary.replace(progress)
        pair = (args.duke, args.ally)
        if all(key in actors for key in pair) and horizon > 0:
            first, second = (actors[key] for key in pair)
            positions = [center(first), center(second)]
            delta = [positions[0][i] - positions[1][i] for i in (0, 1)]
            distance = hypot(*delta)
            velocities = [
                _segments(
                    actors[key], routes.get(key, []), speeds.get(key, 0), horizon
                )[0][3]
                for key in pair
            ]
            relative = [velocities[0][i] - velocities[1][i] for i in (0, 1)]
            target = actors.get(first.get("target"))
            recent.append(
                {
                    "time_seconds": now,
                    "horizon_seconds": horizon,
                    "isolated": first.get("_duke_isolated"),
                    "range": first["range"],
                    "positions": positions,
                    "distance": distance,
                    "velocities": velocities,
                    "radial_velocity": (
                        sum(delta[i] * relative[i] for i in (0, 1)) / distance
                        if distance
                        else None
                    ),
                    "targets": [actors[key].get("target") for key in pair],
                    "duke_target_distance": (
                        target_distance(positions[0], target) if target else None
                    ),
                    "duke_next_attack": first["next_attack"],
                    "boundary_side": deepcopy(self.boundary_sides.get(pair)),
                }
            )
        return original(self, actors, routes, speeds, now, horizon)

    DragonDukeCombat.first_crossing_delay = observe
    evidence = {
        "input_sha256": hashes,
        "source_data_sha256": digest.hexdigest(),
        "python": sys.version,
        "step_override_seconds": args.step,
        "experimental_policy_override": policy,
        "effective_specification_sha256": effective_input_hash,
        "completion_proven": False,
    }
    started = time.perf_counter()
    try:
        result = simulate_full_battle(
            *inputs,
            Catalog.load(ROOT / "data"),
            mode_rules=json.loads((ROOT / "data/mode-rules.json").read_text()),
        )
        evidence.update(status="completed", completion_proven=True)
        evidence["outcome"] = result.get("outcome")
        comparison = {
            "outcome": result["outcome"],
            "resource_use": result.get("resource_use"),
            "trace": result["combat"]["trace"],
            "actors": result["combat"]["actors"],
        }
        evidence["result_sha256"] = {
            key: hashlib.sha256(
                json.dumps(value, sort_keys=True, allow_nan=False).encode()
            ).hexdigest()
            for key, value in comparison.items()
        }
        evidence["trace_count"] = len(comparison["trace"])
        evidence["duke_result"] = result["combat"]["extended_heroes"]["dragon_duke"]
        if args.save_result:
            with gzip.open(
                args.output.with_suffix(".result.json.gz"), "wt", encoding="utf-8"
            ) as file:
                json.dump(comparison, file, allow_nan=False)
    except InputError as error:
        evidence.update(status="rejected", diagnostic=str(error))
    finally:
        DragonDukeCombat.first_crossing_delay = original
    evidence["worker_wall_seconds"] = time.perf_counter() - started
    evidence["recent_contacts"] = list(recent)
    print(json.dumps(evidence), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", required=True, type=Path)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--duke", required=True)
    parser.add_argument("--ally", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--step", type=float)
    parser.add_argument("--wall-seconds", type=float, default=180)
    parser.add_argument("--isolation-policy", type=Path)
    parser.add_argument("--sample-period", type=float)
    parser.add_argument("--save-result", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.wall_seconds <= 0 or (args.step is not None and args.step <= 0):
        parser.error("Wall limit and step must be positive")
    if args.sample_period is not None and args.isolation_policy is None:
        parser.error("--sample-period requires an explicit --isolation-policy")
    if args.worker:
        worker(args)
        return 0
    started = time.perf_counter()
    try:
        process = subprocess.run(
            [sys.executable, "-B", __file__, *sys.argv[1:], "--worker"],
            capture_output=True,
            text=True,
            timeout=args.wall_seconds,
        )
        if process.returncode:
            evidence = {"status": "worker_error", "stderr": process.stderr}
        else:
            evidence = json.loads(process.stdout)
        evidence["process_returncode"] = process.returncode
    except subprocess.TimeoutExpired:
        evidence = {"status": "wall_timeout", "completion_proven": False}
    evidence["wall_limit_seconds"] = args.wall_seconds
    evidence["total_wall_seconds"] = time.perf_counter() - started
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    summary = {
        key: value
        for key, value in evidence.items()
        if key not in {"recent_contacts", "duke_result"}
    }
    if "outcome" in summary:
        summary["outcome"] = {
            key: value
            for key, value in summary["outcome"].items()
            if not isinstance(value, list)
        }
    print(json.dumps(summary))
    return 0 if evidence["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
