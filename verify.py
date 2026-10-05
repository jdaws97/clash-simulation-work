"""Run the checkout's test suite without requiring installation."""

import argparse
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--private-root",
        type=Path,
        help="Optionally validate private five-replay/44-checkpoint evidence outside Git",
    )
    args = parser.parse_args()
    if args.private_root is None:
        print(
            "Private replay integrity: not requested; portable tests use synthetic evidence.",
            flush=True,
        )
    else:
        from clashlab.common import read_json
        from clashlab.replay_evidence import summarize_checkpoint_dataset

        private_root = args.private_root.resolve()
        summary = summarize_checkpoint_dataset(
            read_json(private_root / "data/observations/replays-2026-10-03.json"),
            private_root / "reports/replay-evidence",
        )
        if (summary["replay_count"], summary["checkpoint_count"]) != (5, 44):
            raise SystemExit(
                "Private replay integrity: expected five cases and 44 checkpoints"
            )
        print(
            "Private replay integrity: five cases and 44 checkpoints verified.",
            flush=True,
        )
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
