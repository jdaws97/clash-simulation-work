"""How long real players wait between consecutive playbook steps, measured
from the source videos: for a step triggered "after" another with no stated
delay, both cited from the same video, the gap between their verified
transcript times. Live commentary runs with the battle, so the gap tracks
the player's wait. Gaps outside (0, 90] s (a different attack in the same
video, or a quote said out of order) are dropped; the median per pair is
pooled by whether the step stays in its predecessor's group or changes
group (a new phase: charge -> main push).

Cite times are re-located in the transcripts (output/sources/transcripts):
most data/playbooks cites carry only the extractor's stated t, which can be
off by many seconds; see cite_time.

Writes data/playbook-gaps.json, read by src/baselab/engine/playbook.py.

Usage: python tools/baselab/step_gaps.py
"""

from __future__ import annotations

import glob
import json
import statistics as st
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "output" / "sources" / "transcripts"
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from check_playbook import verified_time  # noqa: E402

_LINES: dict = {}
TALLY = Counter()
_SEEN: set = set()


def _tally(c, how):
    key = (c.get("video"), c.get("quote"), c.get("t"))
    if key not in _SEEN:  # a step can be looked up more than once
        _SEEN.add(key)
        TALLY[how] += 1


def cite_time(c):
    """A cite's time, verified where possible: the caption line where its
    quote starts (check_playbook.verified_time, within 30 s of the stated t),
    else a stored verified_t, else the extractor's stated t."""
    vid = c.get("video")
    if vid not in _LINES:
        p = SRC / f"{vid}.json"
        _LINES[vid] = json.loads(p.read_text(encoding="utf-8"))["lines"] if p.exists() else None
    if _LINES[vid] is not None:
        vt = verified_time(_LINES[vid], c.get("quote", ""), c.get("t"))
        if vt is not None:
            _tally(c, "located in transcript")
            return vt
    if c.get("verified_t") is not None:
        _tally(c, "stored verified_t")
        return c["verified_t"]
    _tally(c, "stated t only")
    return c.get("t")


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
            # a video cited more than once in a step: its last cite
            a = {c["video"]: cite_time(c) for c in steps[ref].get("cite", [])}
            b = {c["video"]: cite_time(c) for c in s.get("cite", [])}
            g = [b[v] - a[v] for v in a if v in b and a[v] is not None and b[v] is not None and 0 < b[v] - a[v] <= 90]
            if g:
                (same if s.get("group", "main") == steps[ref].get("group", "main") else change).append(st.median(g))
    print("cite times (unique cites of gap steps):", dict(TALLY))
    out = {
        "note": "Median wait (s) between a step and the step it follows, from same-video cite times (tools/baselab/step_gaps.py).",
        "same_group": {"median": round(st.median(same), 1), "n": len(same), "quartiles": [round(q, 1) for q in st.quantiles(same, n=4)]},
        "group_change": {"median": round(st.median(change), 1), "n": len(change), "quartiles": [round(q, 1) for q in st.quantiles(change, n=4)]},
    }
    (ROOT / "data" / "playbook-gaps.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out))


if __name__ == "__main__":
    main()
