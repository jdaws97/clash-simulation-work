"""Bounded serial full-battle cases. Each timeout/error has NO outcome.

Input manifest has cases [{bundle: relative JSON path}], timeout_seconds,
and operation compile/simulate. Never loads Python plugins from a manifest.
"""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json, write_json, number
from clashlab.layout_evaluation import (
    compile_case,
    content_sha,
    simulate_case,
    summarize_cases,
)


def fingerprint():
    paths = [
        *sorted((ROOT / "src/clashlab").glob("*.py")),
        *sorted((ROOT / "data").glob("*.json")),
        Path(__file__),
    ]
    return content_sha(
        {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths
        }
    )


def worker(bundle_path, output, operation, expected_input, expected_engine):
    bundle = read_json(bundle_path)
    before = fingerprint()
    receipt = {
        "case": bundle["case"],
        "input_sha256": content_sha(bundle),
        "engine_data_sha256": before,
        "completion_proven": False,
        "outcome": None,
    }
    try:
        if receipt["input_sha256"] != expected_input or before != expected_engine:
            raise RuntimeError(
                "Worker input/engine differs from frozen parent identity"
            )
        catalog = Catalog.load(ROOT / "data")
        rules = read_json(ROOT / "data/mode-rules.json")
        if operation == "compile":
            receipt.update(compile_case(bundle, catalog, rules))
        else:
            checked, result = simulate_case(bundle, catalog, rules)
            receipt.update(checked)
            trace = output.with_suffix(".result.json.gz")
            with gzip.open(trace, "wt", encoding="utf-8") as stream:
                json.dump(result, stream, separators=(",", ":"))
            receipt["result_sha256"] = hashlib.sha256(trace.read_bytes()).hexdigest()
            receipt["result_file"] = trace.name
        if (
            before != fingerprint()
            or content_sha(read_json(bundle_path)) != expected_input
        ):
            raise RuntimeError("Input/engine changed during attempt")
    except Exception as error:
        receipt.update(
            status="unsupported" if isinstance(error, InputError) else "error",
            reason=f"{type(error).__name__}: {error}",
            outcome=None,
            completion_proven=False,
        )
    write_json(output, receipt)


def run(manifest_path, output):
    manifest_bytes = manifest_path.read_bytes()
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = json.loads(manifest_bytes)
    timeout = number(manifest["timeout_seconds"], "wall budget", 0.1, 120)
    operation = manifest["operation"]
    if (
        operation not in {"compile", "simulate"}
        or not 1 <= len(manifest["cases"]) <= 128
    ):
        raise InputError("Bounded manifest requires compile/simulate and 1..128 cases")
    before = fingerprint()
    # Freeze EVERY planned bundle before starting any worker. Later cases cannot
    # acquire new identities merely because their first execution comes later.
    frozen = []
    for item in manifest["cases"]:
        if "preparation_failure" in item:
            frozen.append(
                {
                    "case": item["case"],
                    "preparation_failure": item["preparation_failure"],
                }
            )
            continue
        path = (manifest_path.parent / item["bundle"]).resolve()
        if not path.is_relative_to(manifest_path.parent.resolve()):
            raise InputError("Bundle must be within manifest directory")
        bundle = read_json(path)
        frozen.append(
            {"case": bundle["case"], "path": path, "input_sha256": content_sha(bundle)}
        )
    cases = [item["case"] for item in frozen]
    # Validate planned identities before any work, including duplicate labels.
    summarize_cases(cases, [])
    output.mkdir(parents=True, exist_ok=False)
    receipts = []

    def unchanged(expected):
        try:
            return (
                hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                == manifest_digest
                and fingerprint() == before
                and (
                    "path" not in expected
                    or content_sha(read_json(expected["path"]))
                    == expected["input_sha256"]
                )
            )
        except (OSError, ValueError):
            return False

    def invalidate(receipt, reason):
        receipt.update(
            status="error", reason=reason, outcome=None, completion_proven=False
        )

    for index, expected in enumerate(frozen):
        destination = output / f"case-{index:03d}.json"
        receipt = {
            "case": expected["case"],
            "input_sha256": expected.get("input_sha256"),
            "engine_data_sha256": before,
            "outcome": None,
            "completion_proven": False,
        }
        if "preparation_failure" in expected or not unchanged(expected):
            receipt.update(
                status="unsupported", reason=expected.get("preparation_failure")
            )
            if not unchanged(expected):
                invalidate(
                    receipt, "Frozen manifest/input/engine changed before execution"
                )
            write_json(destination, receipt)
            receipts.append(receipt)
            continue
        path = expected["path"]
        started = time.monotonic()
        with destination.with_suffix(".log").open("w", encoding="utf-8") as log:
            try:
                child = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(Path(__file__).resolve()),
                        "--worker",
                        str(path),
                        "--output",
                        str(destination),
                        "--operation",
                        operation,
                        "--expected-input-sha256",
                        expected["input_sha256"],
                        "--expected-engine-sha256",
                        before,
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                )
                if child.returncode == 0 and destination.exists():
                    observed = read_json(destination)
                    if (
                        observed.get("input_sha256") != expected["input_sha256"]
                        or observed.get("engine_data_sha256") != before
                        or observed.get("case") != expected["case"]
                    ):
                        invalidate(
                            receipt,
                            "Worker receipt differs from frozen parent identity",
                        )
                        receipt["worker_observed_input_sha256"] = observed.get(
                            "input_sha256"
                        )
                    else:
                        receipt.update(observed)
                else:
                    receipt.update(
                        status="error",
                        reason=f"worker exit {child.returncode}; no accepted outcome",
                    )
            except subprocess.TimeoutExpired:
                receipt.update(
                    status="timeout", reason="Wall budget reached; no battle outcome"
                )
        receipt["wall_seconds"] = time.monotonic() - started
        if not unchanged(expected):
            invalidate(receipt, "Frozen manifest/input/engine changed during execution")
        write_json(destination, receipt)
        receipts.append(receipt)
        print(
            json.dumps({"case": expected["case"]["id"], "status": receipt["status"]}),
            flush=True,
        )
    # Catch changes to earlier cases made while a later worker was running.
    for index, (expected, receipt) in enumerate(zip(frozen, receipts)):
        if not unchanged(expected):
            invalidate(
                receipt, "Frozen manifest/input/engine differs at final verification"
            )
            write_json(output / f"case-{index:03d}.json", receipt)
    summary = summarize_cases(cases, receipts)
    summary.update(
        engine_data_sha256=before,
        manifest_sha256=manifest_digest,
        expected_input_sha256={
            item["case"]["id"]: item.get("input_sha256") for item in frozen
        },
    )
    write_json(output / "summary.json", summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--operation", choices=("compile", "simulate"))
    parser.add_argument("--expected-input-sha256")
    parser.add_argument("--expected-engine-sha256")
    args = parser.parse_args()
    if args.worker:
        if not args.expected_input_sha256 or not args.expected_engine_sha256:
            parser.error("Workers require frozen parent input and engine identities")
        worker(
            args.worker,
            args.output,
            args.operation,
            args.expected_input_sha256,
            args.expected_engine_sha256,
        )
    else:
        run(args.manifest.resolve(), args.output.resolve())
