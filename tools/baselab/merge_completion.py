"""Verify Codex's playbook completions (docs/playbook-completion.md) and merge
the verified steps into data/playbooks/<family>.json.

A step is kept only if every field is in the executor vocabulary, its id is
new, its "after" references exist, and at least one cite quote is found in
that video's transcript within 30 s of the stated time (check_playbook.locate).
Cites that fail are dropped; a step left with no good cite is rejected.
Merged steps carry "completion": true.

Usage: python tools/baselab/merge_completion.py FAMILY [...] [--dry] [--from=completion-cc]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from check_playbook import locate, parse_reply  # noqa: E402

SRC = ROOT / "output" / "sources"
ACTIONS = {"deploy", "spell", "ability", "recall", "redeploy", "release_siege"}
ANCHORS = {"edge", "unit", "unit_ahead", "group", "th", "threat", "defenders", "building"}
TRIGGERS = {"t", "after", "delay", "inside", "group_inside", "near_th", "r", "heavy_fire", "hp_below", "frac",
            "spells_left", "n", "dead", "defenders_near", "destruction", "all", "any"}


def _refs(w, out):
    if isinstance(w, dict):
        for k, v in w.items():
            if k not in TRIGGERS:
                out.append(f"unknown trigger {k}")
            if k == "after":
                out.append(("after", v))
            if k in ("all", "any"):
                for x in v:
                    _refs(x, out)
    return out


def place(steps: list) -> list:
    """Completion steps go right after the step they follow ("after"), or
    at the front for a time trigger: the executor works through ready steps
    in list order, one action at a time, so an appended step would wait
    behind the whole playbook."""
    base = [s for s in steps if not s.get("completion")]
    for st in [s for s in steps if s.get("completion")]:
        w = st.get("when") or {}
        ref = w.get("after") or next((x.get("after") for x in w.get("all", []) + w.get("any", []) if "after" in x), None)
        ids = [s["id"] for s in base]
        if ref in ids:
            # after the referenced step and the original steps that follow
            # it directly (its siblings), so the playbook's own sequence
            # keeps priority
            i = ids.index(ref) + 1
            sib = [j for j, s in enumerate(base) if not s.get("completion") and (s.get("when") or {}).get("after") == ref]
            if sib:
                i = max(i, sib[-1] + 1)
            while i < len(base) and base[i].get("completion"):
                i += 1
        else:
            i = 0 if "t" in w else len(base)
        base.insert(i, st)
    return base


def merge(fam: str, dry: bool, folder: str = "completion") -> str:
    raw = SRC / folder / f"{fam}.raw"
    if not raw.exists():
        return f"{fam}: no reply"
    rep = parse_reply(raw.read_text(encoding="utf-8", errors="replace"))
    if rep is None:
        return f"{fam}: unparseable reply"
    path = ROOT / "data" / "playbooks" / f"{fam}.json"
    pb = json.loads(path.read_text(encoding="utf-8"))
    ids = {s["id"] for s in pb["steps"]}
    kept, rejected = [], []
    for st in rep.get("add_steps", []):
        why = []
        if st.get("id") in ids:
            why.append("id clash")
        if st.get("action") not in ACTIONS:
            why.append(f"action {st.get('action')}")
        if str(st.get("at", "edge:main")).partition(":")[0] not in ANCHORS:
            why.append(f"anchor {st.get('at')}")
        for r in _refs(st.get("when"), []) + _refs(st.get("until"), []):
            if isinstance(r, tuple):
                if r[1] not in ids and r[1] not in {k["id"] for k in kept}:
                    why.append(f"after {r[1]} unknown")
            else:
                why.append(r)
        good = []
        for c in st.get("cite", []):
            tr = SRC / "transcripts" / f"{c.get('video')}.json"
            if not tr.exists():
                continue
            hits = locate(json.loads(tr.read_text(encoding="utf-8"))["lines"], c.get("quote", ""))
            if hits and (c.get("t") is None or any(abs(h - float(c["t"])) <= 30 for h in hits)):
                good.append({**c, "verified_t": min(hits, key=lambda h: abs(h - float(c.get("t") or h)))})
        if not good:
            why.append("no verified quote")
        if why:
            rejected.append((st.get("id"), why))
            continue
        kept.append({**st, "cite": good, "completion": True})
        ids.add(st["id"])
    if not dry and kept:
        pb["steps"] = place(pb["steps"] + kept)
        pb.setdefault("notes", []).append(
            "Steps marked completion: true were added from the source transcripts for units the "
            "consolidated playbook never deployed (docs/playbook-completion.md, merge_completion.py).")
        path.write_text(json.dumps(pb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [f"{fam}: kept {len(kept)}, rejected {len(rejected)}, uncovered {[u.get('what') for u in rep.get('uncovered', [])]}"]
    lines += [f"  + {k['id']}: {k['action']} {k.get('what')} x{k.get('count')} @ {k.get('at')} when {k.get('when')}" for k in kept]
    lines += [f"  - {i}: {w}" for i, w in rejected]
    return "\n".join(lines)


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    folder = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--from=")), "completion")
    for fam in [a for a in sys.argv[1:] if not a.startswith("--")]:
        print(merge(fam, dry, folder))
