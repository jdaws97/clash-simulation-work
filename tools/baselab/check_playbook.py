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
    """Times (s) of the caption lines where the normalised quote starts,
    searching a window of 4 lines from each line (quotes often span line
    breaks). A hit counts only for the line the quote starts in, so the time
    is that line's, not the time of a line up to 3 lines earlier."""
    q = norm(quote)
    if len(q) < 6:
        return []
    texts = [norm(t) for _, t in lines]
    hits = []
    for i in range(len(lines)):
        if not texts[i]:
            continue
        window = " ".join(x for x in texts[i:i + 4] if x)
        # whole words only: "ice the queen" must not match "twice the queen"
        p = f" {window} ".find(f" {q} ")
        if 0 <= p < len(texts[i]):
            hits.append(lines[i][0])
    return hits


def verified_time(lines, quote, t=None, tol=30.0):
    """The located time of a quote closest to its stated time t (within
    tol seconds), or None if it is not in the transcript there."""
    hits = locate(lines, quote)
    if t is not None:
        hits = [h for h in hits if abs(h - float(t)) <= tol]
    return min(hits, key=lambda h: abs(h - float(t if t is not None else h))) if hits else None


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
                vt = verified_time(lines, item.get("quote", ""), item.get("t"))
                if vt is not None:
                    item["verified_t"] = vt
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
