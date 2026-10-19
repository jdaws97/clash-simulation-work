"""Why does a base score well? Measured, not guessed.

1. Ablations: move one key piece at a time (swap it with the same-size
   non-defense building farthest from it, or flip Inferno modes) and re-score
   on the same battles. The change in defense trophies / 3-star rate is what
   that placement is worth.
2. Breakdowns: 3-star rate by attacking army and by attack side.
3. Traits vs a reference base (surrogate features).

Usage: python tools/baselab/explain_base.py BASE.json [--ref data/reference-bases/your-base.json] [--out out.md]
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from baselab.evaluate import evaluate, meta_scenarios, side_scenarios  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.mechanics import BUILDING_TYPES  # noqa: E402
from baselab.surrogate import FEATURES, features  # noqa: E402
from funnel import eval_many, own_levels  # noqa: E402

NAMES = {"th": "Town Hall", "eagle": "Eagle Artillery", "inferno": "Infernos", "scatter": "Scattershots", "mono": "Monolith",
         "xbow": "X-Bows", "ad": "Air Defenses", "wt": "Wizard Towers", "cc": "Clan Castle", "st": "Spell Towers"}


def far_swap(lay, key, center_too=False):
    """Copy of `lay` with every `key` building swapped with the same-size
    non-defense building farthest from it (a different spot each)."""
    new = lay.copy()
    used = set()
    for b in [b for b in new.buildings if b.key == key]:
        cands = [o for o in new.buildings if o.size == b.size and o.key != key and o.key != "th" and
                 BUILDING_TYPES[o.key].kind != "defense" and id(o) not in used]
        if not cands:
            continue
        if center_too:
            o = min(cands, key=lambda o: math.hypot(o.x + o.size / 2 - 22, o.y + o.size / 2 - 22))
        else:
            o = max(cands, key=lambda o: math.hypot(o.x - b.x, o.y - b.y))
        used.add(id(o))
        b.x, o.x = o.x, b.x
        b.y, o.y = o.y, b.y
    return new


def flip_infernos(lay, mode):
    new = lay.copy()
    for b in new.buildings:
        if b.key == "inferno":
            b.mode = mode
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--ref", default=str(ROOT / "data" / "reference-bases" / "your-base.json"))
    ap.add_argument("--out")
    args = ap.parse_args()
    own = own_levels()

    def lv(l):
        l.levels, l.wall_level, l.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
        return l

    base = lv(Layout.load(args.base))
    variants = [("as designed", base)]
    variants.append(("Town Hall moved toward the centre", far_swap(base, "th", center_too=True)))
    for key in ("eagle", "inferno", "scatter", "mono", "xbow", "ad", "wt"):
        variants.append((f"{NAMES[key]} moved far away", far_swap(base, key)))
    infs = [b.mode for b in base.buildings if b.key == "inferno"]
    variants.append(("all Infernos single-target", flip_infernos(base, "single")))
    variants.append(("all Infernos multi-target", flip_infernos(base, "multi")))
    variants = [(n, lv(v)) for n, v in variants]
    lines = [f"# Why {Path(args.base).stem} scores the way it does", ""]
    sc = meta_scenarios("ranked", 8, (5, 6, 7))
    res = eval_many([v for _, v in variants], sc, "ranked")
    s0, ev0 = res[0]
    lines += ["## What each piece is worth (ranked, 408 battles, same battles for every variant)", "",
              "| Change | Defense trophies | 3★ | Change in trophies |", "|---|---|---|---|"]
    for (n, _), (s, ev) in zip(variants, res):
        lines.append(f"| {n} | {ev.ranked_trophies:.1f} | {ev.three_star_rate:.0%} | {ev.ranked_trophies - ev0.ranked_trophies:+.1f} |")
    lines.append(f"\nInferno modes as designed: {', '.join(m or '?' for m in infs)}. Noise on a trophy difference here is about +-0.5.")
    lines += ["", "## By attacking army (ranked)", "", "| Army | 3★ | defense trophies |", "|---|---|---|"]
    for k, v in sorted(ev0.per_army.items(), key=lambda kv: -kv[1]["three"]):
        lines.append(f"| {k.split(':')[-1]} | {v['three']:.0%} | {v['troph']:.1f} |")
    # by side: Root Rider + RC charge from each of 8 sides (your army)
    rr = side_scenarios([("custom:user-rr", 16)], (21, 22, 23), 1.0)
    from baselab.evaluate import run_batch, STRENGTH

    jobs = [(base.to_json(), s, STRENGTH.get(s.army, 1.0)) for s in rr]
    out = run_batch(jobs)
    by_side = {}
    for s, r in zip(rr, out):
        k = round((s.angle - 0.1) / (2 * math.pi) * 8) % 8
        by_side.setdefault(k, []).append(r[0] >= 3)
    lines += ["", "## Your Root Rider + RC charge, 3★ by attack side (0-7 around the base)", "",
              " ".join(f"side {k}: {sum(v) / len(v):.0%}" for k, v in sorted(by_side.items()))]
    th = next(b for b in base.buildings if b.key == "th")
    lines.append(f"\nTown Hall sits at side {math.atan2(th.y + 2 - 22, th.x + 2 - 22) % (2 * math.pi) / (2 * math.pi) * 8:.1f}.")
    ref = lv(Layout.load(args.ref))
    fb, fr = features(base), features(ref)
    keyf = {"g_side_min": "ground damage on the weakest side", "a_side_min": "air damage on the weakest side",
            "g_th": "ground damage covering the TH", "a_th": "air damage covering the TH", "layers_th": "wall layers to the TH",
            "layers_key": "wall layers to key defenses", "frac_outside": "share of buildings reachable without a wall",
            "th_center_dist": "TH distance from the map centre", "key_th_dist": "key defenses' distance from the TH",
            "traps_inside": "share of ground traps behind walls", "traps_near_cov": "damage covering the ground traps"}
    lines += ["", f"## Traits vs {Path(args.ref).stem}", "", "| Trait | This base | Reference |", "|---|---|---|"]
    for k, label in keyf.items():
        i = FEATURES.index(k)
        lines.append(f"| {label} | {fb[i]:.1f} | {fr[i]:.1f} |")
    text = "\n".join(lines)
    print(text, flush=True)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
