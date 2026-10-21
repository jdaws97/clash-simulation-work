"""Check consolidated playbooks (output/sources/consolidated/<family>.raw)
before they become sim playbooks: parse the JSON, verify every citation's
quote appears in that video's transcript near the stated time, check the
step vocabulary against src/baselab/engine/playbook.py, and write
data/playbooks/<family>.json with uncited or invalid steps removed.

Usage: python tools/baselab/check_consolidated.py [family ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from check_playbook import parse_reply, verified_time  # noqa: E402

SRC = ROOT / "output" / "sources"
ACTIONS = {"deploy", "spell", "ability", "recall", "redeploy", "release_siege"}
ANCHORS = ("edge:", "unit:", "unit_ahead:", "group:", "th", "threat:", "defenders:", "building:")
TRIGGERS = {"t", "after", "inside", "group_inside", "near_th", "heavy_fire", "hp_below", "spells_left", "dead",
            "defenders_near", "destruction", "all", "any"}


def cite_ok(c, cache):
    vid = c.get("video")
    p = SRC / "transcripts" / f"{vid}.json"
    if not vid or not p.exists():
        return False
    if vid not in cache:
        cache[vid] = json.loads(p.read_text(encoding="utf-8"))["lines"]
    return verified_time(cache[vid], c.get("quote", ""), c.get("t")) is not None


def trigger_ok(w):
    if not w:
        return True
    if not isinstance(w, dict) or not set(w) - {"delay", "r", "frac", "n"} <= TRIGGERS:
        return False
    for k in ("all", "any"):
        if k in w and not all(trigger_ok(x) for x in w[k]):
            return False
    return True


def check(family):
    raw = SRC / "consolidated" / f"{family}.raw"
    pb = parse_reply(raw.read_text(encoding="utf-8", errors="replace")) if raw.exists() else None
    if pb is None:
        print(f"{family}: no parseable playbook")
        return
    cache, kept, dropped, reasons = {}, [], 0, {}
    ids = set()
    for s in pb.get("steps", []):
        good_cites = [c for c in s.get("cite", []) if cite_ok(c, cache)]
        why = None
        if not good_cites:
            why = "no verified citation"
        elif s.get("action") not in ACTIONS:
            why = f"action {s.get('action')}"
        elif s.get("action") not in ("ability", "release_siege") and not str(s.get("at", "edge:main")).startswith(ANCHORS):
            why = f"anchor {s.get('at')}"
        elif not trigger_ok(s.get("when")) or (s.get("until") and not trigger_ok(s["until"])):
            why = "trigger vocabulary"
        if why:
            dropped += 1
            reasons[why] = reasons.get(why, 0) + 1
            continue
        s["cite"] = good_cites
        kept.append(s)
        ids.add(s["id"])
    # triggers that point at a dropped step would never fire: report them
    dangling = [s["id"] for s in kept for w in [json.dumps(s.get("when", {}))] if '"after"' in w and not any(f'"after": "{i}"' in w for i in ids)]
    pb["steps"] = kept
    pb["base_reading"] = [r for r in pb.get("base_reading", []) if any(cite_ok(c, cache) for c in r.get("cite", []))]
    pb["check"] = {"steps_kept": len(kept), "steps_dropped": dropped, "reasons": reasons, "dangling_after": dangling}
    out = ROOT / "data" / "playbooks" / f"{family}.json"
    out.write_text(json.dumps(pb, indent=1), encoding="utf-8")
    print(f"{family}: {len(pb.get('sources', []))} sources, steps kept {len(kept)}, dropped {dropped} {reasons or ''}"
          f"{' dangling: ' + ','.join(dangling) if dangling else ''}")


if __name__ == "__main__":
    fams = sys.argv[1:] or [p.stem for p in (SRC / "consolidated").glob("*.raw")]
    for f in fams:
        check(f)
