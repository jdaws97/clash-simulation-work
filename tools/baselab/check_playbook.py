"""Verify one extracted playbook against its transcript (hallucination guard).

Reads output/sources/playbooks/<id>.raw (the extractor's reply), parses the
JSON object, and checks every step, rule and policy: its quote must appear
in the transcript (case, punctuation and spacing ignored) within 30 s of
the stated time. Unverified items are dropped and counted. Writes
output/sources/playbooks/<id>.json.

Usage: python tools/baselab/check_playbook.py VIDEO_ID [...]   (or --all)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "output" / "sources"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())).strip()


def parse_reply(text: str):
    """The first balanced top-level JSON object in the reply."""
    start = text.find("{")
    while start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def locate(lines, quote):
    """Times (s) where the normalised quote occurs, searching a sliding
    window of caption lines (quotes often span line breaks)."""
    q = norm(quote)
    if len(q) < 6:
        return []
    hits = []
    for i in range(len(lines)):
        window = norm(" ".join(t for _, t in lines[i:i + 4]))
        # whole words only: "ice the queen" must not match "twice the queen"
        if f" {q} " in f" {window} ":
            hits.append(lines[i][0])
    return hits


def check(vid: str) -> dict | None:
    raw = SRC / "playbooks" / f"{vid}.raw"
    tr = SRC / "transcripts" / f"{vid}.json"
    if not raw.exists() or not tr.exists():
        return None
    lines = json.loads(tr.read_text(encoding="utf-8"))["lines"]
    pb = parse_reply(raw.read_text(encoding="utf-8", errors="replace"))
    if pb is None:
        out = {"video_id": vid, "parse_error": True}
    else:
        kept, dropped = 0, 0
        for key in ("base_reading", "steps", "rules", "spell_policy", "ability_policy"):
            good = []
            for item in pb.get(key) or []:
                hits = locate(lines, item.get("quote", ""))
                t = item.get("t")
                ok = bool(hits) and (t is None or any(abs(h - float(t)) <= 30 for h in hits))
                if ok:
                    item["verified_t"] = min(hits, key=lambda h: abs(h - float(t or h)))
                    good.append(item)
                    kept += 1
                else:
                    dropped += 1
            pb[key] = good
        pb["check"] = {"kept": kept, "dropped": dropped}
        out = pb
    (SRC / "playbooks" / f"{vid}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def main():
    ids = sys.argv[1:]
    if ids == ["--all"]:
        ids = [p.stem for p in (SRC / "playbooks").glob("*.raw")]
    tot_k = tot_d = 0
    for vid in ids:
        r = check(vid)
        if r is None:
            continue
        if r.get("parse_error"):
            print(f"{vid}: could not parse the reply")
            continue
        k, d = r["check"]["kept"], r["check"]["dropped"]
        tot_k, tot_d = tot_k + k, tot_d + d
        print(f"{vid}: {r.get('army_family')} TH{r.get('town_hall')} relevant={r.get('relevant')} kept {k}, dropped {d}")
    if tot_k + tot_d:
        print(f"== verified {tot_k}/{tot_k + tot_d} items ({tot_d} dropped as unquoted or misplaced)")


if __name__ == "__main__":
    main()
