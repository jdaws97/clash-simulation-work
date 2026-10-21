"""Cross-check engine hitpoints and DPS against ClashKing game data.

The registry copies ClashKing's own "hitpoints"/"dps" into every level row,
so comparing those keys with ClashKing only tests the copy. This compares
ClashKing with what the engine actually reads (stats.get, where a wiki
column overrides the game-data value) and, separately, with the wiki
column itself (the independent second source).

Usage: python tools/baselab/xcheck_stats.py
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from baselab.engine import stats  # noqa: E402

ck = json.load(open(ROOT / "data" / "clashking-static-data.json", encoding="utf-8"))
WIKI = {"hitpoints": "Hitpoints", "dps": "Damage per Second"}


def close(a, b):
    return abs(a - b) <= max(1.0, 0.02 * abs(a))


tally = Counter()
engine_bad = defaultdict(list)
wiki_bad = defaultdict(list)
missing, dupes = [], []
reg = stats.registry()
for cat in ("troops", "heroes", "buildings", "spells", "pets", "traps", "guardians"):
    entries: dict = {}
    for e in ck[cat]:
        if e.get("village", "home") != "home":
            continue
        if e["name"] in entries:
            dupes.append((cat, e["name"]))
        entries[e["name"]] = e  # the registry keeps the last entry of a name
    for name, e in entries.items():
        if name not in reg:
            missing.append((cat, name))
            continue
        for lv in e.get("levels", []):
            L = lv.get("level")
            try:
                r = stats.row(name, L)
            except KeyError:
                tally["level not in registry"] += 1
                continue
            for key, col in WIKI.items():
                a = lv.get(key)
                if a in (None, 0):
                    continue
                eng = stats.get(name, L, key)
                if eng is None:
                    tally[f"{key}: engine has none"] += 1
                elif close(a, eng):
                    tally[f"{key}: engine = game data"] += 1
                else:
                    engine_bad[(cat, name, key)].append((L, a, eng))
                w = stats.num(r.get(col))
                if w is None:
                    tally[f"{key}: no wiki value"] += 1
                elif close(a, w):
                    tally[f"{key}: wiki = game data"] += 1
                else:
                    wiki_bad[(cat, name, key)].append((L, a, w))
for k in sorted(tally):
    print(f"{k:32s} {tally[k]}")
print(f"engine differs from game data: {sum(map(len, engine_bad.values()))} level rows")
for k, v in sorted(engine_bad.items()):
    print("  ", k, len(v), "e.g. (level, game data, engine)", v[:3])
print(f"wiki differs from game data: {sum(map(len, wiki_bad.values()))} level rows (engine uses the wiki value there)")
if dupes:
    print("ClashKing names listed twice (last one used):", sorted(set(dupes)))
print("not in engine:", [n for c, n in missing if c in ("troops", "heroes", "pets", "guardians")][:60])
