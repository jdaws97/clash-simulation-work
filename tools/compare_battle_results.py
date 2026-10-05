"""Write a compact numerical comparison of two saved complete-battle results."""

import argparse
import gzip
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clashlab.numerical_checks import compare_battle_results


def load(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tolerance", type=float, default=1e-7)
    arguments = parser.parse_args()
    comparison = compare_battle_results(
        load(arguments.first), load(arguments.second), arguments.tolerance
    )
    comparison["result_files"] = [arguments.first.name, arguments.second.name]
    arguments.output.write_text(
        json.dumps(comparison, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": comparison["status"],
                "trace_lengths": comparison["trace_lengths"],
                "equal_trace_prefix_length": comparison["equal_trace_prefix_length"],
                "first_trace_difference": comparison["first_trace_difference"],
                "first_frame_difference": comparison["first_frame_difference"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
