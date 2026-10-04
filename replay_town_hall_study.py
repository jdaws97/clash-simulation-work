"""Replay saved controlled Town Hall inputs without relying on workspace helpers."""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from clashlab.adapters import simulate_entity_closed_loop
from clashlab.basecombat import simulate_wall_mechanics_probe
from clashlab.catalog import Catalog
from clashlab.common import read_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", choices=("wall", "death"), required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--trials", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    arguments = parser.parse_args()
    if arguments.trials < 1 or (arguments.limit is not None and arguments.limit < 1):
        parser.error("Trials and an optional case limit must be positive")
    name = (
        "town-hall-wall-combat"
        if arguments.study == "wall"
        else "town-hall-poison-entry"
    )
    matrix = read_json(ROOT / f"reports/{name}.json")
    catalog = Catalog.load(ROOT / "data")
    cases = matrix["cases"]
    if arguments.limit is not None:
        cases = cases[: arguments.limit]
    outputs = []
    for case in cases:
        filename = case["artifact"]
        if Path(filename).name != filename:
            raise ValueError("Saved study outputs must use plain filenames")
        stem = filename.removesuffix("-combat.json")
        if arguments.study == "wall":
            blueprint = read_json(ROOT / f"reports/{case['candidate']}.json")
            specification = read_json(ROOT / f"examples/{stem}-probe.json")
            specification["human"]["seed"] = arguments.seed
            specification["human"]["trials"] = arguments.trials
            result = simulate_wall_mechanics_probe(blueprint, catalog, specification)
        else:
            specification = read_json(ROOT / f"examples/{stem}.json")
            result = simulate_entity_closed_loop(
                specification["scene"],
                catalog,
                specification["plan"],
                specification["profile"],
                arguments.seed,
                arguments.trials,
            )
        destination = arguments.output / filename
        write_json(destination, result)
        outputs.append(str(destination.resolve()))
        print(f"Saved {destination}", flush=True)
    write_json(
        arguments.output / "replay-manifest.json",
        {
            "study": arguments.study,
            "seed": arguments.seed,
            "trials": arguments.trials,
            "case_count": len(outputs),
            "outputs": outputs,
            "full_game_prediction": False,
            "limitations": matrix["limitations"],
        },
    )


if __name__ == "__main__":
    main()
