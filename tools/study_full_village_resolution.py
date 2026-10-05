"""Run identical full-village inputs at several solver steps from one code snapshot."""

import argparse
from copy import deepcopy
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
from time import perf_counter
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/full-village"


def capture_runtime():
    source = ROOT / "src"
    paths = sorted(source.rglob("*.py"))
    files = {path.relative_to(source).as_posix(): path.read_bytes() for path in paths}
    if any(
        path.read_bytes() != files[path.relative_to(source).as_posix()]
        for path in paths
    ):
        raise RuntimeError("Sources changed while copying; rerun the snapshot capture")
    digest = sha256()
    for name, content in files.items():
        digest.update(name.encode() + b"\0" + content + b"\0")
    fingerprint = digest.hexdigest()
    destination = REPORT / f"runtime-{fingerprint[:20]}.zip"
    if not destination.exists():
        with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
            for name, content in files.items():
                metadata = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                metadata.compress_type = ZIP_DEFLATED
                archive.writestr(metadata, content)
    return destination, fingerprint


def write_compressed(path, data):
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, separators=(",", ":"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--steps", type=float, nargs="+", default=[0.25, 0.1])
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument(
        "--template", type=Path, default=REPORT / "ranked-none-180s-input.json"
    )
    arguments = parser.parse_args()
    if not arguments.label.replace("-", "").isalnum():
        parser.error("Label must contain letters, digits and hyphens only")
    if not 0 < arguments.duration <= 180 or any(
        not 0 < step <= 1 for step in arguments.steps
    ):
        parser.error("Duration must be in (0, 180] and solver steps in (0, 1]")
    if len(arguments.steps) != len(set(arguments.steps)):
        parser.error("Solver steps must be unique")
    runtime, fingerprint = capture_runtime()
    sys.path.insert(0, str(runtime))
    # Imports deliberately follow the immutable capture. Both cases use exactly
    # these loaded modules even if other development continues during the study.
    from clashlab.catalog import Catalog
    from clashlab.common import read_json, write_json
    from clashlab.full_battle import simulate_full_battle

    catalog = Catalog.load(ROOT / "data")
    account = read_json(ROOT / "profiles/sample-th16.json")
    army = read_json(REPORT / "army.json")
    layout = read_json(REPORT / "ranked-simulation-layout.json")
    mode_rules = read_json(ROOT / "data/mode-rules.json")
    base = read_json(arguments.template)
    summaries = []
    for step in arguments.steps:
        specification = deepcopy(base)
        specification["time_limit_seconds"] = arguments.duration
        scene = specification["entity_scene"]
        scene["duration_seconds"] = arguments.duration
        scene["maximum_step_seconds"] = step
        for collection in ("effects", "buff_spells", "freeze_spells"):
            scene[collection] = [
                item
                for item in scene[collection]
                if item["time_seconds"] <= arguments.duration
            ]
        selected_casts = {
            item["id"]
            for name in ("buff_spells", "freeze_spells")
            for item in scene[name]
        }
        for actor in scene["entities"]:
            if actor["entity"] == "eagle-artillery":
                activation = actor["indirect_parameters"]["activation"]
                activation["command_weights"] = {
                    key: value
                    for key, value in activation["command_weights"].items()
                    if key in selected_casts
                }
        case_id = f"ranked-none-{arguments.duration:g}s-{arguments.label}-step-{step:g}"
        write_json(REPORT / f"{case_id}-input.json", specification)
        start = perf_counter()
        result = simulate_full_battle(
            specification, account, army, layout, catalog, mode_rules
        )
        seconds = perf_counter() - start
        write_compressed(REPORT / f"{case_id}-result.json.gz", result)
        summary = {
            "case_id": case_id,
            "runtime_archive": runtime.name,
            "runtime_sha256": fingerprint,
            "maximum_step_seconds": step,
            "wall_seconds": seconds,
            "outcome": {
                key: result["outcome"][key]
                for key in (
                    "stars",
                    "destruction",
                    "town_hall_destroyed",
                    "elapsed_seconds",
                    "end_reason",
                )
            },
            "replay_calibrated": False,
            "full_game_prediction": False,
        }
        write_json(REPORT / f"{case_id}-summary.json", summary)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    write_json(REPORT / f"resolution-{arguments.label}.json", summaries)


if __name__ == "__main__":
    main()
