"""Fresh, bounded component/compiler checks; no full simulations or crash probes."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


def main():
    root = Path(__file__).resolve().parents[1]
    output = Path(tempfile.mkdtemp(prefix="equipment-pet-check-", dir=root))
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(root / "src"), str(root / "tests"))
    )
    command = [
        sys.executable,
        "-B",
        "-m",
        "unittest",
        "test_equipment_pet_lifecycles",
        "-v",
    ]
    started = datetime.now(timezone.utc).isoformat()
    try:
        result = subprocess.run(
            command,
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        stdout, stderr = result.stdout, result.stderr
        code = result.returncode
        status = (
            "passed"
            if code == 0 and "Ran 8 tests" in stderr and "\nOK\n" in stderr
            else "failed"
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or b""
        stderr = error.stderr or b""
        stdout = (
            stdout.decode(errors="replace") if isinstance(stdout, bytes) else stdout
        )
        stderr = (
            stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr
        )
        code = None
        status = "timeout"
    (output / "stdout.txt").write_text(stdout, encoding="utf-8")
    (output / "stderr.txt").write_text(stderr, encoding="utf-8")
    receipt = {
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "exit_code": code,
        "timeout_seconds": 30,
        "fresh_directory": output.name,
        "checks": "8 synthetic component/compiler tests",
        "full_battle_simulation_run": False,
        "calibrated": False,
    }
    (output / "result.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2))
    raise SystemExit(0 if status == "passed" else 1)


if __name__ == "__main__":
    main()
