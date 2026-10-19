"""How long real players wait between consecutive playbook steps, measured
from the source videos: for a step triggered "after" another with no stated
delay, both cited from the same video, the gap between their verified
transcript times. Live commentary runs with the battle, so the gap tracks
the player's wait. Gaps outside (0, 90] s (a different attack in the same
video, or a quote said out of order) are dropped; the median per pair is
pooled by whether the step stays in its predecessor's group or changes
group (a new phase: charge -> main push).

Writes data/playbook-gaps.json, read by src/baselab/engine/playbook.py.

Usage: python tools/baselab/step_gaps.py
"""

from __future__ import annotations

import glob
import json
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    same, change = [], []
    for f in sorted(glob.glob(str(ROOT / "data" / "playbooks" / "*.json"))):
        if Path(f).name.startswith("test-"):
            continue
        pb = json.loads(Path(f).read_text(encoding="utf-8"))
        steps = {s["id"]: s for s in pb["steps"]}
        for s in pb["steps"]:
            w = s.get("when") or {}
            ref = w.get("after")
            if not ref or ref not in steps or w.get("delay", 0) != 0:
                continue
            a = {c["video"]: c.get("verified_t", c.get("t")) for c in steps[ref].get("cite", [])}
            b = {c["video"]: c.get("verified_t", c.get("t")) for c in s.get("cite", [])}
            g = [b[v] - a[v] for v in a if v in b and a[v] is not None and b[v] is not None and 0 < b[v] - a[v] <= 90]
            if g:
                (same if s.get("group", "main") == steps[ref].get("group", "main") else change).append(st.median(g))
    out = {
        "note": "Median wait (s) between a step and the step it follows, from same-video cite times (tools/baselab/step_gaps.py).",
        "same_group": {"median": round(st.median(same), 1), "n": len(same), "quartiles": [round(q, 1) for q in st.quantiles(same, n=4)]},
        "group_change": {"median": round(st.median(change), 1), "n": len(change), "quartiles": [round(q, 1) for q in st.quantiles(change, n=4)]},
    }
    (ROOT / "data" / "playbook-gaps.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out))


if __name__ == "__main__":
    main()
