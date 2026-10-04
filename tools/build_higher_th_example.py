"""Prepare/compile/run a complete conditional higher-TH defense fixture.

Use --layout to supply a separately inspected full higher-TH layout JSON. Without
it coordinates are synthetic. Simulation is single-process and has a wall-time
deadline; timeout is recorded without claiming a completed battle.
"""

import argparse
import gzip
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clashlab.catalog import Catalog
from clashlab.boosts import effective_account
from clashlab.common import read_json, write_json
from clashlab.development_village import (
    benchmark_army,
    padded_layout,
    termination_policy,
)
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.higher_town_halls import (
    build_scene,
    synthetic_layout,
    validate_higher_layout,
)
from clashlab.termination_rules import SCOPE, RULES


def fingerprints():
    files = [
        *sorted((ROOT / "src/clashlab").glob("*.py")),
        *sorted((ROOT / "data/battle-policies").glob("*.json")),
        ROOT / "data/catalog.json",
        ROOT / "data/secondary-raw.json",
        ROOT / "data/mode-rules.json",
        Path(__file__),
    ]
    hashes = {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files
    }
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return {"engine_and_data_sha256": digest, "files": hashes}


def prepare(town_hall, mode, layout=None):
    catalog = Catalog.load(ROOT / "data")
    policies = read_json(ROOT / "data/battle-policies/development-th16.json")
    policies["higher_town_halls"] = read_json(
        ROOT / "data/battle-policies/experimental-higher-th.json"
    )
    original = layout if layout is not None else synthetic_layout(catalog, town_hall)
    if original["town_hall"] != town_hall:
        raise ValueError("Layout Town Hall and requested defender Town Hall differ")
    validation = validate_higher_layout(original, catalog)
    layout = padded_layout(original)
    account = read_json(ROOT / "profiles/sample-th16.json")
    account = effective_account(account, catalog, mode)
    army = benchmark_army()
    scene = build_scene(layout, catalog, policies, SCOPE, RULES)
    specification = {
        "id": f"th16-dragons-vs-th{town_hall}-{mode}-experimental",
        "source": policies["higher_town_halls"]["source"],
        "time_limit_seconds": 180,
        "entity_scene": scene,
        "termination_policy": termination_policy(army, policies),
        "battle_modifier_policy": {
            "profile_id": "none",
            "policy_source": policies["source"],
            **{
                key: "unchanged"
                for key in (
                    "maximum_hp_damage_policy",
                    "trap_damage_policy",
                    "death_damage_policy",
                    "impact_hazard_damage_policy",
                    "equipment_aura_damage_policy",
                    "hero_summon_statistics_policy",
                    "healing_and_status_policy",
                )
            },
        },
    }
    return specification, account, army, layout, validation


def input_fingerprints(destination):
    return {
        name: hashlib.sha256((destination / f"{name}.json").read_bytes()).hexdigest()
        for name in ("input", "account", "army", "layout")
    }


def run_worker(destination, attempt):
    destination = Path(destination)
    started = time.monotonic()
    evidence = {
        **attempt,
        "worker_pid": os.getpid(),
        "completion_proven": False,
        "started_utc": datetime.now(timezone.utc).isoformat(),
    }
    try:
        if fingerprints() != read_json(destination / "fingerprints.json"):
            raise RuntimeError("Engine/data changed after scenario preparation")
        if (
            fingerprints()["engine_and_data_sha256"]
            != attempt["engine_and_data_sha256"]
            or input_fingerprints(destination) != attempt["input_sha256"]
        ):
            raise RuntimeError("Prepared inputs or engine do not match this attempt")
        result = simulate_full_battle(
            read_json(destination / "input.json"),
            read_json(destination / "account.json"),
            read_json(destination / "army.json"),
            read_json(destination / "layout.json"),
            Catalog.load(ROOT / "data"),
            mode_rules=read_json(ROOT / "data/mode-rules.json"),
        )
        if (
            fingerprints()["engine_and_data_sha256"]
            != attempt["engine_and_data_sha256"]
            or input_fingerprints(destination) != attempt["input_sha256"]
        ):
            raise RuntimeError(
                "Engine/data changed during battle; rerun from stable sources"
            )
        with gzip.open(
            destination / "result.json.gz", "wt", encoding="utf-8"
        ) as stream:
            json.dump(result, stream, separators=(",", ":"))
        evidence.update(
            status="COMPLETED_CONDITIONAL_SYNTHETIC_BATTLE",
            completion_proven=True,
            mechanics_verification="EXPERIMENTAL_NOT_REPLAY_CALIBRATED",
            outcome=result["outcome"],
            resource_receipt=result.get("resource_receipt", result.get("resource_use")),
            full_game_prediction=False,
        )
    except Exception:
        evidence.update(status="PYTHON_EXCEPTION", error=traceback.format_exc())
        raise
    finally:
        evidence.update(
            wall_seconds=time.monotonic() - started,
            ended_utc=datetime.now(timezone.utc).isoformat(),
        )
        write_json(destination / "worker-result.json", evidence)


def collect_outcome(destination, worker, attempt):
    outcome = {
        **attempt,
        "worker_pid": worker.pid,
        "completion_proven": False,
        "process_returncode": worker.exitcode,
        "process_returncode_hex": f"0x{worker.exitcode & 0xFFFFFFFF:08X}",
        "ended_utc": datetime.now(timezone.utc).isoformat(),
    }
    if worker.exitcode != 0:
        outcome["status"] = "WORKER_PROCESS_FAILURE"
        return outcome
    try:
        receipt = read_json(destination / "worker-result.json")
    except (OSError, ValueError):
        outcome["status"] = "MISSING_OR_INVALID_WORKER_RESULT"
        return outcome
    associated = isinstance(receipt, dict) and all(
        receipt.get(key) == value for key, value in attempt.items()
    )
    associated = associated and receipt.get("worker_pid") == worker.pid
    if not associated:
        outcome["status"] = "UNBOUND_WORKER_RESULT_REJECTED"
        return outcome
    if (
        receipt.get("completion_proven") is not True
        or receipt.get("status") != "COMPLETED_CONDITIONAL_SYNTHETIC_BATTLE"
        or not isinstance(receipt.get("outcome"), dict)
        or not (destination / "result.json.gz").is_file()
        or input_fingerprints(destination) != attempt["input_sha256"]
        or fingerprints()["engine_and_data_sha256"] != attempt["engine_and_data_sha256"]
    ):
        outcome["status"] = "INVALID_COMPLETION_REJECTED"
        return outcome
    return {
        **receipt,
        **outcome,
        "status": receipt["status"],
        "completion_proven": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "compile", "simulate"))
    parser.add_argument("--town-hall", type=int, choices=(17, 18), required=True)
    parser.add_argument("--mode", choices=("ranked", "war", "cwl"), required=True)
    parser.add_argument("--layout", type=Path)
    parser.add_argument("--wall-timeout", type=float, default=480)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 0 < args.wall_timeout <= 900:
        parser.error("Wall timeout must be positive and at most 900 seconds")
    run_id = uuid.uuid4().hex
    destination = args.output or (
        ROOT / f"reports/higher-th/th{args.town_hall}-{args.mode}" / run_id
    )
    try:
        destination.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error(
            "Output must be a new directory; prior attempt evidence is preserved"
        )
    specification, account, army, layout, validation = prepare(
        args.town_hall, args.mode, read_json(args.layout) if args.layout else None
    )
    for name, value in (
        ("input", specification),
        ("account", account),
        ("army", army),
        ("layout", layout),
    ):
        write_json(destination / f"{name}.json", value)
    source_fingerprints = fingerprints()
    write_json(destination / "fingerprints.json", source_fingerprints)
    attempt = {
        "run_id": run_id,
        "engine_and_data_sha256": source_fingerprints["engine_and_data_sha256"],
        "input_sha256": input_fingerprints(destination),
    }
    write_json(destination / "attempt.json", attempt)
    summary = {
        **attempt,
        "destination": str(destination),
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "completion_proven": False,
        "attacker_town_hall": 16,
        "defender_town_hall": args.town_hall,
        "mode": args.mode,
        "modifier": "none",
        "mechanics_verification": "EXPERIMENTAL_NOT_REPLAY_CALIBRATED",
        "validation": validation,
        "coordinate_provenance": layout["higher_th_configuration"][
            "coordinate_provenance"
        ],
        "layout_objects": len(layout["buildings"]),
        "inventory": layout["inventory"],
        "level_selection": layout["higher_th_configuration"].get(
            "level_selection", "entered_levels"
        ),
        "replay_calibrated": False,
        "full_game_prediction": False,
    }
    if args.operation != "prepare":
        compiled = compile_full_battle(
            specification,
            account,
            army,
            layout,
            Catalog.load(ROOT / "data"),
            mode_rules=read_json(ROOT / "data/mode-rules.json"),
        )
        summary["compiled"] = True
        summary["resource_validation"] = compiled["validation"].get("army")
        summary["bindings"] = {
            key: len(compiled["validation"][key])
            for key in ("attacker_bindings", "defender_bindings", "spell_bindings")
        }
    write_json(destination / "summary.json", summary)
    print(json.dumps(summary), flush=True)
    if args.operation == "simulate":
        worker = multiprocessing.Process(
            target=run_worker, args=(str(destination), attempt)
        )
        worker.start()
        worker.join(args.wall_timeout)
        if worker.is_alive():
            worker.terminate()
            worker.join(10)
            if worker.is_alive():
                worker.kill()
                worker.join(10)
            write_json(
                destination / "outcome.json",
                {
                    **attempt,
                    "status": "WALL_TIMEOUT",
                    "completion_proven": False,
                    "wall_timeout": args.wall_timeout,
                },
            )
            raise SystemExit(2)
        outcome = collect_outcome(destination, worker, attempt)
        write_json(destination / "outcome.json", outcome)
        summary.update(
            status=outcome["status"],
            completion_proven=outcome["completion_proven"],
            process_returncode=outcome["process_returncode"],
            process_returncode_hex=outcome["process_returncode_hex"],
        )
        write_json(destination / "summary.json", summary)
        print(
            json.dumps(
                {
                    "status": outcome["status"],
                    "completion_proven": outcome["completion_proven"],
                    "run_id": run_id,
                    "process_returncode": worker.exitcode,
                    "process_returncode_hex": outcome["process_returncode_hex"],
                    "wall_seconds": outcome.get("wall_seconds"),
                    "outcome": {
                        k: outcome.get("outcome", {}).get(k)
                        for k in (
                            "stars",
                            "destruction",
                            "elapsed_seconds",
                            "end_reason",
                        )
                    },
                    "error": outcome.get("error"),
                }
            ),
            flush=True,
        )
        raise SystemExit(0 if outcome["completion_proven"] else 3)


if __name__ == "__main__":
    main()
