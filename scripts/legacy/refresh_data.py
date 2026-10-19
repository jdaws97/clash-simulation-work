"""Save a new immutable snapshot without replacing the shipped catalog."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from clashlab.ingest import refresh_snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--workers", type=int, required=True)
    arguments = parser.parse_args()
    result = refresh_snapshot(
        arguments.commit, arguments.destination, arguments.workers
    )
    print(result)


if __name__ == "__main__":
    main()
