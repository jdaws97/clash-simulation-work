"""Offline joint search; independent CLI so central CLI/kernel ownership stays intact."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clashlab.attack_search_runner import run_search, worker
from clashlab.common import InputError, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("manifest", type=Path)
    run.add_argument("--data", type=Path, default=ROOT / "data")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--cache", type=Path, required=True)
    child = commands.add_parser("worker", help=argparse.SUPPRESS)
    child.add_argument("request", type=Path)
    child.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "worker":
            worker(args.request, args.output)
        else:
            result = run_search(
                read_json(args.manifest), args.data, args.output, args.cache
            )
            counts = {}
            for row in result["rows"]:
                status = row["result"]["status"]
                counts[status] = counts.get(status, 0) + 1
            print(f"Saved {args.output / 'report.json'}; {counts}; no recommendations")
    except (InputError, OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"{type(error).__name__}: {error}\n")


if __name__ == "__main__":
    main()
