"""Build the local report from reviewed scoreboard observations and hashed frames."""

import json
from pathlib import Path

from clashlab.replay_evidence import summarize_checkpoint_dataset


ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / "data/observations/replays-2026-10-03.json"
    destination = ROOT / "reports/replay-evidence"
    dataset = json.loads(source.read_text(encoding="utf-8"))
    summary = summarize_checkpoint_dataset(dataset, destination)
    (destination / "observations.json").write_text(
        json.dumps(dataset, indent=2) + "\n", encoding="utf-8"
    )
    (destination / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    template = (ROOT / "tools/replay_evidence.html").read_text(encoding="utf-8")
    payload = json.dumps({"dataset": dataset, "summary": summary}).replace("</", "<\\/")
    result = template.replace("__REPLAY_EVIDENCE_JSON__", payload)
    output = destination / "index.html"
    output.write_text(result, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
