"""Cross-check every engine stat against ClashKing game data (two independent
sources). Usage: python tools/baselab/xcheck_stats.py"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from baselab.engine import stats
ck = json.load(open(Path(__file__).resolve().parents[2] / "data" / "clashking-static-data.json", encoding="utf-8"))
bad, ok, missing = [], 0, []
for cat in ("troops", "heroes", "buildings", "spells", "pets", "traps", "guardians"):
    for e in ck[cat]:
        if e.get("village") not in (None, "home"):
            continue
        name = e["name"]
        try:
            assert any(stats.row(name, lv["level"]) for lv in e.get("levels", []))
        except Exception:
            missing.append((cat, name)); continue
        for lv in e.get("levels", []):
            L = lv.get("level")
            try:
                r = stats.row(name, L) or {}
            except Exception:
                continue
            for key in ("hitpoints", "dps"):
                a, b = lv.get(key), r.get(key)
                if a in (None, 0) or b in (None, ""):
                    continue
                try:
                    b = float(b)
                except Exception:
                    continue
                if abs(a - b) > max(1.0, 0.02 * abs(a)):
                    bad.append((cat, name, L, key, a, b))
                else:
                    ok += 1
print("agree", ok, "disagree", len(bad))
from collections import defaultdict
g = defaultdict(list)
for x in bad: g[(x[0], x[1], x[3])].append(x)
for k, v in sorted(g.items()):
    print(k, len(v), "e.g.", [(x[2], x[4], x[5]) for x in v[:4]])
print("not in engine:", [n for c, n in missing if c in ("troops","heroes","pets","guardians")][:60])
