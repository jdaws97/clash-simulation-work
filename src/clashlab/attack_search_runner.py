"""Serial, process-bounded search receipts and content-addressed completed results."""

from hashlib import sha256
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

from .attack_search import (
    SCHEMA,
    comparison,
    digest,
    enumerate_joint_candidates,
    evaluate_candidate,
    validate_candidate_scenario,
)
from .catalog import Catalog
from .common import InputError, identifier, integer, number, read_json, write_json
from .scoring import validate_outcome


ROOT = Path(__file__).resolve().parents[2]


def _file_tree(root, paths):
    return digest(
        [
            [path.relative_to(root).as_posix(), sha256(path.read_bytes()).hexdigest()]
            for path in sorted(paths)
        ]
    )


def fingerprints(data_directory):
    data_directory = Path(data_directory).resolve()
    return {
        "code_sha256": _file_tree(
            ROOT,
            [*ROOT.joinpath("src").rglob("*.py"), ROOT / "tools/search_attacks.py"],
        ),
        "data_sha256": _file_tree(
            data_directory,
            [path for path in data_directory.rglob("*") if path.is_file()],
        ),
        "runtime": {"python": sys.version, "platform": platform.platform()},
    }


def cache_identity(candidate, fingerprints_value, timeout_seconds, mode_rules):
    return {
        "schema": SCHEMA,
        **fingerprints_value,
        "mode_sha256": digest(
            {"context": candidate["context"], "mode_rules": mode_rules}
        ),
        "input_sha256": digest(candidate),
        "scenario_sha256": candidate["scenario_sha256"],
        "environment_sha256": digest(candidate["scenario_environment"]),
        "timeout_seconds": timeout_seconds,
    }


def validate_result(result, scenario_sha256):
    """Normalize malformed worker/cache receipts to one unscored failed attempt."""
    try:
        if not isinstance(result, dict) or not isinstance(result.get("status"), str):
            raise InputError("Receipt must be an object with a string status")
        status = result["status"]
        if status not in {
            "completed",
            "rejected",
            "failed",
            "timeout",
            "blocked_dependency",
        }:
            raise InputError("Unknown worker status")
        if "objective" not in result:
            raise InputError("Receipt is missing objective")
        if status != "completed":
            if result["objective"] is not None or "outcome" in result:
                raise InputError(
                    "Unscored receipts cannot carry an outcome or objective"
                )
            if status == "blocked_dependency":
                dependencies = result.get("dependencies")
                if not isinstance(dependencies, list) or not dependencies:
                    raise InputError("Blocked receipt needs explicit dependencies")
                for dependency in dependencies:
                    identifier(dependency, "dependency")
            else:
                identifier(result.get("reason"), "failure reason")
            return result
        if result.get("scenario_sha256") != scenario_sha256:
            raise InputError("Completed receipt does not match the pinned scenario")
        objective, outcome = result["objective"], result.get("outcome")
        fields = {"stars", "destruction", "elapsed_seconds", "completion_time_seconds"}
        if (
            not isinstance(objective, dict)
            or set(objective) != fields
            or not isinstance(outcome, dict)
        ):
            raise InputError("Completed receipt needs structured outcome and objective")
        if (
            result.get("full_game_prediction") is not False
            or outcome.get("full_game_prediction") is not False
        ):
            raise InputError("Completed receipt cannot claim game prediction")
        validate_outcome(outcome)
        integer(objective["stars"], "objective stars", 0, 3)
        number(objective["destruction"], "objective destruction", 0, 100)
        limit = number(outcome["time_limit_seconds"], "battle limit", 0.001, 180)
        elapsed = number(objective["elapsed_seconds"], "elapsed time", 0, limit)
        completion = objective["completion_time_seconds"]
        number(outcome["elapsed_seconds"], "outcome elapsed time", 0, limit)
        if outcome["completion_time_seconds"] is not None:
            number(
                outcome["completion_time_seconds"], "outcome completion time", 0, limit
            )
        reason = outcome["end_reason"]
        if reason not in {
            "all_counted_buildings_destroyed",
            "attack_force_exhausted",
            "declared_time_limit",
        }:
            raise InputError("Unknown battle end reason")
        if outcome["destruction"] == 100:
            number(completion, "completion time", 0, limit)
            if completion != elapsed or reason != "all_counted_buildings_destroyed":
                raise InputError("Complete destruction timing/reason disagree")
        elif completion is not None or reason == "all_counted_buildings_destroyed":
            raise InputError("Incomplete destruction cannot have a completion time")
        if reason == "declared_time_limit" and elapsed != limit:
            raise InputError("Time-limit outcome must reach the battle limit")
        if any(
            field not in outcome or objective[field] != outcome[field]
            for field in fields
        ):
            raise InputError("Objective differs from outcome")
        for field in (
            "resource_use",
            "modifier_audit",
            "admission",
            "crafted_event_counts",
        ):
            if not isinstance(result.get(field), dict):
                raise InputError(f"Completed receipt needs {field} object")
        if "crafted_runtime" not in result or (
            result["crafted_runtime"] is not None
            and not isinstance(result["crafted_runtime"], dict)
        ):
            raise InputError("Malformed crafted runtime receipt")
        if not isinstance(result.get("limitations"), list) or not all(
            isinstance(value, str) for value in result["limitations"]
        ):
            raise InputError("Completed receipt needs a limitations list")
        return result
    except (InputError, KeyError, TypeError, ValueError, OverflowError) as error:
        return {
            "status": "failed",
            "objective": None,
            "reason": f"Invalid worker receipt: {error}",
        }


def _cache_read(path, identity):
    try:
        record = read_json(path)
        if (
            record["identity"] == identity
            and record["result_sha256"] == digest(record["result"])
            and validate_result(record["result"], identity["scenario_sha256"])["status"]
            == "completed"
        ):
            return record["result"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def _cache_write(path, identity, result):
    """Atomic replacement avoids treating a partial write as a completed result."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, suffix=".tmp", delete=False
    ) as file:
        staging = Path(file.name)
    try:
        write_json(
            staging,
            {"identity": identity, "result_sha256": digest(result), "result": result},
        )
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def worker(request_path, output_path):
    """No injected code/callbacks; only the existing paid engine can score a row."""
    request = read_json(request_path)
    try:
        data_directory = Path(request["data_directory"])
        if fingerprints(data_directory) != request["fingerprints"]:
            raise InputError("Code/data/runtime changed after manifest capture")
        result = evaluate_candidate(
            request["candidate"],
            Catalog.load(data_directory),
            read_json(data_directory / "mode-rules.json"),
        )
        if fingerprints(data_directory) != request["fingerprints"]:
            raise InputError("Code/data/runtime changed while evaluating candidate")
    except (InputError, KeyError, TypeError, ValueError) as error:
        result = {
            "status": "rejected",
            "objective": None,
            "reason": f"{type(error).__name__}: {error}",
        }
    except Exception as error:
        result = {
            "status": "failed",
            "objective": None,
            "reason": f"{type(error).__name__}: {error}",
        }
    write_json(output_path, result)


def run_search(manifest, data_directory, output_directory, cache_directory):
    data_directory, output_directory, cache_directory = map(
        Path, (data_directory, output_directory, cache_directory)
    )
    mode_rules = read_json(data_directory / "mode-rules.json")
    generated = enumerate_joint_candidates(manifest, mode_rules)
    if output_directory.exists():
        raise InputError(
            "Choose a fresh output directory to preserve previous receipts"
        )
    output_directory.mkdir(parents=True)
    fingerprint = fingerprints(data_directory)
    write_json(output_directory / "input-manifest.json", manifest)
    write_json(output_directory / "expanded-candidates.json", generated)
    write_json(output_directory / "fingerprints.json", fingerprint)
    rows, seen = [], {}
    timeout = manifest["budget"]["timeout_seconds"]
    for ordinal, candidate in enumerate(generated["candidates"]):
        identity = cache_identity(candidate, fingerprint, timeout, mode_rules)
        key = digest(identity)
        cache_path = cache_directory / (key + ".json")
        cache_hit = False
        try:
            validate_candidate_scenario(candidate)
        except (InputError, KeyError, TypeError, ValueError) as error:
            result = {"status": "rejected", "objective": None, "reason": str(error)}
        else:
            result = _cache_read(cache_path, identity)
            cache_hit = result is not None
        duplicate_of = seen.get(key)
        started = time.monotonic()
        if result is None:
            request_path = output_directory / f"{ordinal:03d}-request.json"
            result_path = output_directory / f"{ordinal:03d}-result.json"
            write_json(
                request_path,
                {
                    "candidate": candidate,
                    "fingerprints": fingerprint,
                    "data_directory": str(data_directory.resolve()),
                },
            )
            with (output_directory / f"{ordinal:03d}-worker.log").open(
                "w", encoding="utf-8"
            ) as log:
                try:
                    process = subprocess.run(
                        [
                            sys.executable,
                            "-B",
                            str(ROOT / "tools/search_attacks.py"),
                            "worker",
                            str(request_path.resolve()),
                            str(result_path.resolve()),
                        ],
                        cwd=ROOT,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        timeout=timeout,
                        env={
                            **os.environ,
                            "PYTHONDONTWRITEBYTECODE": "1",
                            "PYTHONHASHSEED": "0",
                        },
                    )
                except subprocess.TimeoutExpired:
                    result = {
                        "status": "timeout",
                        "objective": None,
                        "reason": "Wall budget exhausted; no battle outcome assigned",
                    }
                else:
                    if process.returncode != 0:
                        result = {
                            "status": "failed",
                            "objective": None,
                            "reason": f"Worker exit {process.returncode}; see worker log",
                        }
                    else:
                        try:
                            result = read_json(result_path)
                        except (OSError, ValueError):
                            result = {
                                "status": "failed",
                                "objective": None,
                                "reason": "Missing or invalid worker receipt",
                            }
            result = validate_result(result, candidate["scenario_sha256"])
            if result["status"] == "completed":
                _cache_write(cache_path, identity, result)
        provenance = {
            "roster": candidate["roster"]["provenance"],
            "plan": candidate["plan"]["provenance"],
        }
        row = {
            "candidate_id": candidate["id"],
            "scenario_sha256": candidate["scenario_sha256"],
            "ordinal": ordinal,
            "option_ids": [candidate["roster"]["id"], candidate["plan"]["id"]],
            "role": (
                "external_baseline"
                if any(
                    value["kind"] == "external_baseline"
                    for value in provenance.values()
                )
                else "original_generated"
            ),
            "provenance": provenance,
            "cache_key": key,
            "cache_hit": cache_hit,
            "duplicate_of": duplicate_of,
            "wall_seconds": time.monotonic() - started,
            "result": result,
        }
        seen.setdefault(key, candidate["id"])
        rows.append(row)
        write_json(
            output_directory / "progress.json",
            {"completed_attempts": len(rows), "rows": rows},
        )
    unchanged = fingerprints(data_directory) == fingerprint
    if not unchanged:
        for row in rows:
            row["result"] = {
                "status": "failed",
                "objective": None,
                "reason": "Code/data/runtime changed during run",
            }
    report = {
        "schema": SCHEMA,
        "status": "EXPERIMENTAL_INFRASTRUCTURE_ONLY",
        "manifest_sha256": digest(manifest),
        "fingerprints": fingerprint,
        "context": manifest["context"],
        "scenario_environment": manifest["scenario_environment"],
        "scenario_sha256": generated["candidates"][0]["scenario_sha256"],
        "opponent_inventory": manifest["opponent_inventory"],
        "mechanics": manifest["mechanics"],
        "budget": manifest["budget"],
        "enumeration": {
            key: value for key, value in generated.items() if key != "candidates"
        },
        "rows": rows,
        "comparisons": comparison(rows),
        "full_game_prediction": False,
        "recommendations": [],
        "limitations": [
            "Synthetic scenarios and uncalibrated conventions establish no whole-battle accuracy",
            "Only completed paid-engine outcomes are compared; failures and timeouts have no score",
            "Observation-gated paid actions require explicit complete scheduler policies; omitted policies remain unscored",
            "Incomplete outcomes report elapsed time without rewarding early force exhaustion",
            "Current-opponent crafted identity/module gaps cannot be replaced by an empty Station",
            "Declared product order is deterministic; wall timing and timeout occurrence depend on the machine",
        ],
    }
    write_json(output_directory / "report.json", report)
    return report
