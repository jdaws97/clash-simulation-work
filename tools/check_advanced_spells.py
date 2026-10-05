"""Run only permanent-spell contract checks, with a fresh receipt and a hard limit."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run_id = uuid.uuid4().hex
    folder = args.output / run_id
    folder.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    environment.pop("PYTHONFAULTHANDLER", None)
    command = [
        sys.executable,
        "-B",
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-p",
        "test_advanced_spells.py",
        "-v",
    ]
    receipt = {
        "run_id": run_id,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "timeout_seconds": 15,
        "scope": "synthetic_spell_contracts_and_full_battle_compile_rejection_no_simulations",
    }
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
        )
        receipt.update(exit_code=result.returncode, timed_out=False)
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired as error:
        receipt.update(exit_code=124, timed_out=True)
        output = "Bounded spell check timed out; no successful result.\n"
        for part in (error.stdout, error.stderr):
            if part:
                output += (
                    part.decode(errors="replace") if isinstance(part, bytes) else part
                )
    receipt["completed_utc"] = datetime.now(timezone.utc).isoformat()
    (folder / "output.txt").write_text(output, encoding="utf-8")
    (folder / "receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(output, end="")
    print("Fresh receipt:", folder / "receipt.json", flush=True)
    return receipt["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
